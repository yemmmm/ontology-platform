"""Small, host-private task amount budgets for R4.4-002.

The module owns a numeric projection and admission receipt.  It deliberately
does not start providers, pause processes, or interpret business content.  A
Host/runtime registers the real owner and numeric receipt sources, calls
``tick`` (normally every two seconds), and performs the control action recorded
by ``record_control``.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Callable, Iterable

from .dsh_usage import DSH_SEMANTICS, native_numeric_event, normalize_dsh_usage
from .usage_capture import TOKEN_FIELDS, numeric_usage
from .usage_report import account_usage_units, estimate_budget_cost, estimate_tail_bound

SCHEMA = "task-budget/v1"
STATE_SCHEMA = "task-budget-state/v1"
BINDING_SCHEMA = "task-budget-binding/v1"
AUTHORIZATION_FILENAME = "authorization.json"
EVENTS_FILENAME = "events.jsonl"
STATE_FILENAME = "state.json"
LOCK_FILENAME = "budget.lock"
BINDING_FILENAME = "task-budget-binding.json"
DEFAULT_PRICES_PATH = Path(__file__).with_name("task-budget-prices.json")
HEARTBEAT_TIMEOUT_SECONDS = 10.0
PENDING_SETTLEMENT_SECONDS = 10.0
MAX_TICK_BYTES = 4 * 1024 * 1024
MAX_TICK_RECORDS = 4096
DEFAULT_OPERATIONS = ("read", "supervise", "production", "evaluation", "repair")
_CONTROL_STATUS_RANK = {
    "requested": 0,
    "submitted": 1,
    "pending": 1,
    "unknown": 1,
    "failed": 1,
    "instruction_delivered": 2,
    "effective": 3,
    "not_running": 3,
    "not_started": 3,
}
# A native DSH subtotal can be used as a partial budget source when its
# provider original is absent.  It remains visible in coverage, but this
# informational gap alone does not make the numeric projection unsafe.
_INFORMATIONAL_METERING_ISSUES = {"dsh_provider_original_missing"}
_MISSING = object()
_HISTORY_STATE_KEYS = {"_records", "_native_records", "_attempts", "_replay_targets"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _timestamp(value: Any) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _json_default(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _copy(value):
    return copy.deepcopy(value)


def _event_view(state: dict) -> dict:
    """Return the durable delta view without normalized token history."""
    return {
        key: _copy(value)
        for key, value in state.items()
        if key not in _HISTORY_STATE_KEYS and key != "event_offset"
    }


def _delta(before: dict, after: dict) -> dict:
    """Build a recursive JSON patch for changed state metadata."""
    set_values = {}
    deleted = []
    nested = {}
    for key in sorted(set(before) | set(after)):
        if key not in after:
            deleted.append(key)
            continue
        if key not in before:
            set_values[key] = _copy(after[key])
            continue
        old, new = before[key], after[key]
        if isinstance(old, dict) and isinstance(new, dict):
            child = _delta(old, new)
            if child["set"] or child["delete"] or child["nested"]:
                nested[key] = child
        elif old != new:
            set_values[key] = _copy(new)
    return {"set": set_values, "delete": deleted, "nested": nested}


def _apply_delta(state: dict, patch: dict, *, skip_sources: bool = False) -> None:
    for key in patch.get("delete", []):
        if not (skip_sources and key == "sources"):
            state.pop(key, None)
    for key, value in patch.get("set", {}).items():
        if skip_sources and key == "sources":
            continue
        state[key] = _copy(value)
    for key, child in patch.get("nested", {}).items():
        if skip_sources and key == "sources":
            continue
        target = state.setdefault(key, {})
        if not isinstance(target, dict):
            target = {}
            state[key] = target
        _apply_delta(target, child, skip_sources=False)


def _decimal(value: Any, *, code: str = "budget_config_invalid", allow_zero: bool = True) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BudgetError(code, {"value": value}) from None
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise BudgetError(code, {"value": str(value)})
    return number


def _decimal_text(value: Any) -> str:
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return format(number, "f")


def _budget_state_precision(state: dict) -> int:
    token_digits = 1
    for collection in (state.get("_records", {}).values(), state.get("_native_records", {}).values()):
        for row in _expanded_records(collection):
            for value in (row.get("usage") or {}).values():
                if type(value) is int:
                    token_digits = max(token_digits, len(str(abs(value))))
    rate_digits = 1
    rate_scale = 0
    for price in state.get("price_versions", []):
        for raw in (price.get("rates") or {}).values():
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError):
                continue
            rate_digits = max(rate_digits, len(value.as_tuple().digits))
            rate_scale = max(rate_scale, max(0, -value.as_tuple().exponent))
    amount_digits = 1
    amount_scale = 0
    for field in (
        "authorized_amount",
        "priced_amount",
        "provisional_amount",
        "charged_estimate",
        "remaining_estimate",
        "overspend_estimate",
    ):
        try:
            value = Decimal(str(state.get(field, "0")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if not value.is_finite():
            continue
        amount_digits = max(amount_digits, len(value.as_tuple().digits))
        amount_scale = max(amount_scale, max(0, -value.as_tuple().exponent))
    count = max(
        1,
        len(state.get("_records", {}))
        + len(state.get("_native_records", {}))
        + len(state.get("authorization_events", {})),
    )
    return max(
        80,
        token_digits
        + rate_digits
        + rate_scale
        + amount_digits
        + amount_scale
        + len(str(count))
        + 24,
    )


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode()
    ).hexdigest()


def _blocking_metering_issue(issue: dict) -> bool:
    return issue.get("code") not in _INFORMATIONAL_METERING_ISSUES


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_json(path: Path, default: Any = _MISSING):
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        if default is not _MISSING:
            return _copy(default)
        raise


def _valid_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise BudgetError("budget_config_invalid", {"field": name})
    return value.strip()


def _normalise_rates(raw: dict) -> dict:
    rates = raw.get("rates") if isinstance(raw.get("rates"), dict) else raw
    aliases = {
        "cached_input_tokens": (
            "cached_input_tokens", "cached_input_per_million", "cache_read_input_tokens", "cache_read_per_million"
        ),
        "uncached_input_tokens": (
            "uncached_input_tokens", "uncached_input_per_million", "input_per_million", "input_tokens"
        ),
        "output_tokens": ("output_tokens", "output_per_million", "output"),
    }
    result = {}
    for canonical, names in aliases.items():
        value = next((rates[name] for name in names if name in rates), _MISSING)
        if value is _MISSING:
            continue
        result[canonical] = _decimal(value, code="budget_config_invalid")
    return {key: _decimal_text(value) for key, value in result.items()}


def _normalise_price(raw: dict, currency: str, index: int) -> dict:
    if not isinstance(raw, dict):
        raise BudgetError("budget_config_invalid", {"field": "prices", "index": index})
    provider = raw.get("provider") or raw.get("provider_id")
    model = raw.get("actual_model", raw.get("model"))
    if provider is None:
        raise BudgetError("budget_config_invalid", {"field": "prices.provider", "index": index})
    if model is None:
        raise BudgetError("budget_config_invalid", {"field": "prices.actual_model", "index": index})
    provider = _valid_id(provider, "provider")
    model = _valid_id(model, "actual_model")
    route = raw.get("route", raw.get("access_route", raw.get("provider_route")))
    if route is not None:
        route = _valid_id(route, "route")
    rates = _normalise_rates(raw)
    version = raw.get("version") or raw.get("price_version") or f"v{index + 1}"
    version = _valid_id(version, "price_version")
    price_currency = raw.get("currency", currency)
    if not isinstance(price_currency, str) or not price_currency:
        raise BudgetError("budget_currency_mismatch", {"currency": price_currency})
    if price_currency != currency:
        raise BudgetError("budget_currency_mismatch", {"currency": price_currency, "expected": currency})
    unit = _decimal(raw.get("unit_tokens", 1_000_000), code="budget_config_invalid", allow_zero=False)
    if unit != Decimal("1000000"):
        raise BudgetError(
            "budget_config_invalid",
            {"field": "unit_tokens", "expected": "1000000", "value": _decimal_text(unit)},
        )
    return {
        "provider": provider,
        "actual_model": model,
        **({"route": route} if route is not None else {}),
        "currency": currency,
        "version": version,
        "price_version": version,
        "unit_tokens": "1000000",
        "rates": rates,
        "source_ref": raw.get("source_ref", "task-authorization"),
        "definition_ref": raw.get("definition_ref", "task-budget-three-bucket/v1"),
    }


def _normalise_config(ref: Path, config: dict, *, for_add: bool = False) -> dict:
    if not isinstance(config, dict):
        raise BudgetError("budget_config_invalid", {"field": "config"})
    currency = config.get("currency", "CNY")
    if not isinstance(currency, str) or not currency.strip():
        raise BudgetError("budget_currency_mismatch", {"currency": currency})
    currency = currency.strip()
    amount_key = "delta_amount" if for_add and "delta_amount" in config else "amount"
    amount = config.get(amount_key, config.get("authorized_amount"))
    if amount is not None:
        amount = _decimal(amount, code="budget_config_invalid")
    elif not for_add:
        raise BudgetError("budget_config_invalid", {"field": "amount"})
    budget_id = config.get("budget_id") or config.get("task_ref") or ref.name
    budget_id = _valid_id(budget_id, "budget_id")
    task_ref = _valid_id(config.get("task_ref", budget_id), "task_ref")
    authorization_reference = config.get("authorization_reference", config.get("authorization_id"))
    if not isinstance(authorization_reference, str) or not authorization_reference.strip():
        raise BudgetError("authorization_reference_required", {"field": "authorization_reference"})
    prices = config.get("prices", config.get("price_snapshot", []))
    if isinstance(prices, dict):
        prices = [prices]
    if prices is None:
        prices = []
    if not isinstance(prices, list):
        raise BudgetError("budget_config_invalid", {"field": "prices"})
    normalised_prices = [_normalise_price(price, currency, index) for index, price in enumerate(prices)]
    # Exact selector/version pairs are immutable in a task snapshot.
    selectors = set()
    for price in normalised_prices:
        key = (
            price.get("provider"), price.get("actual_model"), price.get("route"), price["version"]
        )
        if key in selectors:
            raise BudgetError("budget_config_invalid", {"field": "prices", "duplicate": key})
        selectors.add(key)
    coverage = config.get("coverage") if isinstance(config.get("coverage"), dict) else {}
    coverage_gaps = config.get("coverage_gaps", coverage.get("gaps", []))
    if coverage_gaps is None:
        coverage_gaps = []
    if not isinstance(coverage_gaps, list):
        raise BudgetError("budget_config_invalid", {"field": "coverage_gaps"})
    limits = config.get("limits", config.get("tail_limits", {}))
    if limits is None:
        limits = {}
    if not isinstance(limits, dict):
        raise BudgetError("budget_config_invalid", {"field": "limits"})
    out_of_scope = config.get("out_of_scope", coverage.get("out_of_scope", []))
    if out_of_scope is None:
        out_of_scope = []
    if not isinstance(out_of_scope, list) or any(not isinstance(item, dict) for item in out_of_scope):
        raise BudgetError("budget_config_invalid", {"field": "out_of_scope"})
    known_scopes = {item.get("scope") for item in out_of_scope}
    for scope in ("host", "unwired_auxiliary"):
        if scope not in known_scopes:
            out_of_scope.append({"scope": scope, "status": "unknown", "amount": None, "deducted": False})
    normalized_scope = []
    for item in out_of_scope:
        item_currency = item.get("currency", currency)
        if item_currency != currency:
            raise BudgetError("budget_currency_mismatch", {"currency": item_currency, "expected": currency})
        normalized_scope.append({
            **_copy(item),
            "scope": _valid_id(item.get("scope"), "out_of_scope.scope"),
            "status": item.get("status", "known" if item.get("amount") is not None else "unknown"),
            "deducted": False,
            "amount": None if item.get("amount") is None else _decimal_text(_decimal(item["amount"])),
            "currency": item.get("currency", currency),
        })
    if "allowed_bindings" in config:
        allowed_bindings = config["allowed_bindings"]
        if not isinstance(allowed_bindings, list):
            raise BudgetError("budget_config_invalid", {"field": "allowed_bindings"})
    else:
        # A price row is itself an exact authorization selector.  Deriving
        # this list keeps an omitted field scoped to the frozen provider/model
        # pairs instead of turning an empty list into a wildcard.
        allowed_bindings = []
        for price in normalised_prices:
            selector = {
                "provider": price["provider"],
                "actual_model": price["actual_model"],
            }
            if price.get("route") is not None:
                selector["route"] = price["route"]
            if selector not in allowed_bindings:
                allowed_bindings.append(selector)
    normalized_bindings = []
    for index, item in enumerate(allowed_bindings):
        if not isinstance(item, dict):
            raise BudgetError("budget_config_invalid", {"field": "allowed_bindings", "index": index})
        provider = item.get("provider") or item.get("provider_id")
        model = item.get("actual_model") or item.get("model")
        if provider is None or model is None:
            raise BudgetError(
                "budget_config_invalid",
                {"field": "allowed_bindings", "index": index, "reason": "provider_and_model_required"},
            )
        selector = {
            "provider": _valid_id(provider, "allowed_bindings.provider"),
            "actual_model": _valid_id(model, "allowed_bindings.actual_model"),
        }
        route = item.get("route", item.get("access_route", item.get("provider_route")))
        if route is not None:
            selector["route"] = _valid_id(route, "allowed_bindings.route")
        if selector not in normalized_bindings:
            normalized_bindings.append(selector)
    return {
        "schema_version": SCHEMA,
        "budget_id": budget_id,
        "task_ref": task_ref,
        "authorization_reference": authorization_reference,
        "currency": currency,
        **({"amount": _decimal_text(amount)} if amount is not None else {}),
        "prices": normalised_prices,
        "allowed_bindings": normalized_bindings,
        "allowed_operations": _copy(
            config["allowed_operations"] if "allowed_operations" in config else list(DEFAULT_OPERATIONS)
        ),
        "limits": _copy(limits),
        "coverage_gaps": _copy(coverage_gaps),
        "out_of_scope": normalized_scope,
        "origin_session_ref": config.get("origin_session_ref"),
        "created_at": config.get("created_at", _iso()),
    }


def _configured_prices(authorization: dict) -> list[dict]:
    """Snapshot CNY defaults only for explicitly authorized model bindings."""
    if authorization["currency"] != "CNY" or not authorization["allowed_bindings"]:
        return []
    try:
        prices = _read_json(DEFAULT_PRICES_PATH)
        if not isinstance(prices, list):
            raise ValueError("expected a price list")
        normalized = [_normalise_price(row, "CNY", index) for index, row in enumerate(prices)]
    except (OSError, ValueError, TypeError) as exc:
        raise BudgetError("budget_config_invalid", {
            "field": "default_prices", "path": str(DEFAULT_PRICES_PATH),
        }) from exc
    return [price for price in normalized if any(
        all(price.get(key) == binding.get(key) for key in ("provider", "actual_model", "route"))
        for binding in authorization["allowed_bindings"]
    )]


class BudgetError(ValueError):
    """Typed, recoverable admission or metering feedback."""

    def __init__(self, code: str, details: dict | str | None = None, message: str | None = None):
        self.code = str(code)
        if isinstance(details, str):
            self.details = {"message": details}
            text = message or details
        else:
            self.details = _copy(details or {})
            text = message or self.details.get("message") or self.code
        super().__init__(text)


def _binding_path(root: Path) -> Path:
    return root / BINDING_FILENAME


class BudgetMonitor:
    """A tiny optional 2-second monitor owned by the Host process."""

    def __init__(self, budget: "TaskBudget", callback: Callable[[dict], Any] | None, interval: float):
        self.budget = budget
        self.callback = callback
        self.interval = max(0.1, float(interval))
        self.stop_event = threading.Event()
        self.owner_id = f"monitor:{os.getpid()}:{id(self)}"
        self.last_error: dict | None = None
        self.thread = threading.Thread(target=self._run, name="task-budget-monitor", daemon=True)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                projection = self.budget.tick(monitor_id=self.owner_id)
                if self.callback:
                    self.callback(projection)
            except Exception as exc:
                # A monitor failure is itself a metering fact.  Preserve the
                # first failure in memory and make the safety pause durable so
                # a transient callback/runtime exception cannot be lost.
                if self.last_error is None:
                    self.last_error = {
                        "code": "metering_error",
                        "error": type(exc).__name__,
                        "message": str(exc)[:256],
                        "owner_id": self.owner_id,
                    }
                try:
                    self.budget.request_pause(
                        "metering_error",
                        monitor_id=self.owner_id,
                        monitor_error=type(exc).__name__,
                        message=str(exc)[:256],
                    )
                except Exception as pause_exc:
                    # Keep the original blocker and retain the persistence
                    # failure for the caller inspecting the monitor handle.
                    self.last_error.setdefault("persistence_error", {
                        "error": type(pause_exc).__name__,
                        "message": str(pause_exc)[:256],
                    })
            self.stop_event.wait(self.interval)

    def start(self) -> "BudgetMonitor":
        if not self.thread.is_alive():
            self.budget._claim_monitor(self.owner_id)
            self.thread.start()
        return self

    def stop(self, timeout: float | None = None) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout)
        # A stopped monitor must give up its lease before a same-process
        # continuation tries to start a fresh monitor.  If the callback is
        # still running after the caller's timeout, keep the lease until the
        # thread really exits rather than allowing two readers to race.
        if not self.thread.is_alive():
            self.budget._release_monitor(self.owner_id)


class TaskBudget:
    """Persistent amount budget referenced by one or more runtime sessions."""

    def __init__(self, ref: str | Path):
        self.ref = Path(ref).expanduser().resolve()
        self.authorization_path = self.ref / AUTHORIZATION_FILENAME
        self.events_path = self.ref / EVENTS_FILENAME
        self.state_path = self.ref / STATE_FILENAME
        self.lock_path = self.ref / LOCK_FILENAME
        self._thread_lock = threading.RLock()

    @classmethod
    def create(cls, ref: str | Path, config: dict) -> "TaskBudget":
        path = Path(ref).expanduser().resolve()
        normalised = _normalise_config(path, config)
        use_defaults = "prices" not in config and "price_snapshot" not in config
        budget = cls(path)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Creation is immutable and must be serialized with add/tick.  The
        # timestamp is audit metadata, so retrying the same authorization is
        # idempotent even though each normalization obtains a fresh time.
        with budget._locked():
            if budget.authorization_path.exists():
                try:
                    existing = _read_json(budget.authorization_path, {})
                except (OSError, ValueError, TypeError) as exc:
                    raise BudgetError(
                        "budget_unavailable",
                        {"ref": str(path), "error": type(exc).__name__},
                    ) from exc
                immutable_existing = {key: value for key, value in existing.items() if key != "created_at"}
                if use_defaults:
                    # Retrying creation preserves the original snapshot even
                    # after shared defaults change.
                    normalised["prices"] = _copy(existing.get("prices", []))
                immutable_requested = {key: value for key, value in normalised.items() if key != "created_at"}
                if immutable_existing == immutable_requested:
                    return budget
                raise BudgetError("budget_exists", {"ref": str(path)})
            if use_defaults:
                normalised["prices"] = _configured_prices(normalised)
            _atomic_json(budget.authorization_path, normalised)
            os.chmod(budget.authorization_path, 0o600)
            budget.events_path.touch(mode=0o600, exist_ok=True)
            os.chmod(budget.events_path, 0o600)
            initial = budget._initial_state(normalised)
            _atomic_json(budget.state_path, initial)
            os.chmod(budget.state_path, 0o600)
        return budget

    def _initial_state(self, auth: dict) -> dict:
        amount = Decimal(auth.get("amount", "0"))
        prices = _copy(auth.get("prices", []))
        tail_bound = estimate_tail_bound(prices=prices, limits=auth.get("limits", {}))
        state = {
            "schema_version": STATE_SCHEMA,
            "budget_ref": str(self.ref),
            "budget_id": auth["budget_id"],
            "task_ref": auth["task_ref"],
            "currency": auth["currency"],
            "authorized_amount": _decimal_text(amount),
            "priced_amount": "0",
            "provisional_amount": "0",
            "charged_estimate": "0",
            "remaining_estimate": _decimal_text(amount),
            "overspend_estimate": "0",
            "pending_settlement": 0,
            "inflight_count": 0,
            "metered_through": None,
            "observed_at": None,
            "tail_bound": tail_bound,
            "heartbeat_at": None,
            "price_version": prices[0].get("version") if len(prices) == 1 else [p.get("version") for p in prices],
            "price_versions": prices,
            "allowed_bindings": _copy(auth.get("allowed_bindings", [])),
            "coverage": {
                "status": "unknown", "units": 0, "known": 0, "unknown": 0, "provisional": 0,
                "issues": [], "by_role": {}, "by_model": {}, "by_role_model": {},
            },
            "coverage_gaps": _copy(auth.get("coverage_gaps", [])),
            "limits": _copy(auth.get("limits", {})),
            "out_of_scope": _copy(auth.get("out_of_scope", [])),
            "control_status": "open",
            "admission_open": amount > 0,
            "pause_epoch": 0,
            "pause_reasons": [],
            "monitor": {
                "owner_id": None,
                "status": "not_started",
                "lease_until": None,
                "heartbeat_at": None,
            },
            "owners": {},
            "sources": {},
            "authorization_events": [],
            "units": {},
            "_records": {},
            "_native_records": {},
            "_attempts": {},
            "_control_grants": {},
            "event_seq": 0,
            "event_offset": 0,
            "source_round_robin": 0,
        }
        if amount <= 0:
            _ensure_pause(state, "budget_exhausted", {"charged_estimate": "0"})
            state["control_status"] = _control_status(state)
        return state

    def _auth(self) -> dict:
        try:
            auth = _read_json(self.authorization_path)
        except (OSError, ValueError, TypeError) as exc:
            raise BudgetError(
                "budget_unavailable",
                {"ref": str(self.ref), "error": type(exc).__name__},
            ) from exc
        if not isinstance(auth, dict) or auth.get("schema_version") != SCHEMA:
            raise BudgetError("budget_uninitialized", {"ref": str(self.ref)})
        return auth

    def _load_state(self) -> dict:
        try:
            state = _read_json(self.state_path, None)
        except (OSError, ValueError, TypeError) as exc:
            raise BudgetError(
                "budget_unavailable",
                {"ref": str(self.ref), "error": type(exc).__name__},
            ) from exc
        if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA:
            state = self._initial_state(self._auth())
        committed = int(state.get("event_seq", 0))
        offset = int(state.get("event_offset", 0))
        replay_targets = _copy(state.pop("_replay_targets", {}))
        replay_sources = _copy(state.get("sources", {}))
        try:
            with self.events_path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                if offset < 0 or offset > size:
                    raise BudgetError(
                        "metering_error",
                        {"reason": "event_offset_invalid", "offset": offset, "size": size},
                    )
                stream.seek(offset)
                position = offset
                line_number = 0
                for raw_line in stream:
                    line_number += 1
                    end = position + len(raw_line)
                    position = end
                    if not raw_line.endswith(b"\n"):
                        # A crash can leave a partial final event.  It is not
                        # committed; the next append truncates this tail.
                        break
                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError, TypeError) as exc:
                        raise BudgetError(
                            "metering_error",
                            {
                                "reason": "event_corrupt",
                                "path": str(self.events_path),
                                "offset": end - len(raw_line),
                                "line": line_number,
                                "error": type(exc).__name__,
                            },
                        ) from exc
                    if not isinstance(event, dict) or type(event.get("seq")) is not int:
                        raise BudgetError(
                            "metering_error",
                            {
                                "reason": "event_invalid",
                                "path": str(self.events_path),
                                "offset": end - len(raw_line),
                            },
                        )
                    sequence = event["seq"]
                    if sequence <= committed:
                        continue
                    if sequence != committed + 1:
                        raise BudgetError(
                            "metering_error",
                            {
                                "reason": "event_sequence_gap",
                                "expected": committed + 1,
                                "received": sequence,
                            },
                        )
                    if isinstance(event.get("delta"), dict):
                        delta = event["delta"]
                        if event.get("kind") == "tick":
                            source_delta = (delta.get("nested") or {}).get("sources")
                            if isinstance(source_delta, dict):
                                _apply_delta(replay_sources, source_delta)
                                replay_targets = {
                                    source_id: {
                                        "cursor": int(source.get("cursor", 0)),
                                        "line_count": int(source.get("line_count", 0)),
                                    }
                                    for source_id, source in replay_sources.items()
                                    if isinstance(source, dict)
                                }
                        else:
                            # Registration and binding events carry their
                            # source metadata normally; keep the parallel
                            # source view aligned before the next tick patch.
                            _apply_delta(state, delta, skip_sources=False)
                            replay_sources = _copy(state.get("sources", {}))
                            committed = sequence
                            state["event_seq"] = sequence
                            state["event_offset"] = end
                            continue
                        # A source tick's checkpoint may be ahead of state when
                        # a process crashed after append and before state.json.
                        # Keep the old cursor so the next tick re-reads the
                        # source; amount/unit projections remain a safe bound.
                        _apply_delta(
                            state,
                            delta,
                            skip_sources=event.get("kind") == "tick",
                        )
                    elif isinstance(event.get("state"), dict):
                        # Read old WIP ledgers once; all new commits use only
                        # deltas and never copy this full state into events.
                        state = _copy(event["state"])
                    else:
                        raise BudgetError(
                            "metering_error",
                            {"reason": "event_delta_missing", "sequence": sequence},
                        )
                    committed = sequence
                    state["event_seq"] = sequence
                    state["event_offset"] = end
        except BudgetError:
            raise
        except OSError as exc:
            if committed == 0 and not self.events_path.exists():
                return state
            raise BudgetError(
                "budget_unavailable",
                {"ref": str(self.ref), "error": type(exc).__name__},
            ) from exc
        if replay_targets:
            state["_replay_targets"] = replay_targets
        return state

    @contextmanager
    def _locked(self):
        self.ref.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _truncate_partial_event_tail(self) -> int:
        """Drop only an unterminated final event before appending."""
        with self.events_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            if end == 0:
                return 0
            stream.seek(end - 1)
            if stream.read(1) == b"\n":
                return end
            cursor = end
            while cursor:
                chunk_start = max(0, cursor - 65536)
                stream.seek(chunk_start)
                chunk = stream.read(cursor - chunk_start)
                index = chunk.rfind(b"\n")
                if index >= 0:
                    boundary = chunk_start + index + 1
                    stream.truncate(boundary)
                    return boundary
                cursor = chunk_start
            stream.truncate(0)
            return 0

    def _commit(
        self,
        kind: str,
        state: dict,
        payload: dict | None = None,
        *,
        before: dict | None = None,
    ) -> None:
        sequence = int(state.get("event_seq", 0)) + 1
        state["event_seq"] = sequence
        before_view = before if before is not None else _event_view(state)
        after_view = _event_view(state)
        delta = _delta(before_view, after_view)
        self._truncate_partial_event_tail()
        event = {
            "schema_version": SCHEMA,
            "seq": sequence,
            "kind": kind,
            "recorded_at": _iso(),
            "payload": _copy(payload or {}),
            "delta": delta,
        }
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            state["event_offset"] = stream.buffer.tell()
        _atomic_json(self.state_path, state)

    def _mutate(self, kind: str, callback: Callable[[dict], Any], payload: dict | None = None):
        with self._thread_lock, self._locked():
            state = self._load_state()
            before = _event_view(state)
            result = callback(state)
            self._commit(kind, state, payload, before=before)
            return result

    def _refresh_summary(self, state: dict, *, now: str | None = None) -> None:
        # A task can legitimately contain very large cumulative token counts
        # and prices with many fractional digits.  Keep the whole projection
        # (including role/model subtotals and the remaining amount) in one
        # context sized from the observed data; the default Decimal28 would
        # otherwise round a long accumulation before the admission check.
        with localcontext() as context:
            context.prec = _budget_state_precision(state)
            self._refresh_summary_unbounded(state, now=now)

    def _refresh_summary_unbounded(self, state: dict, *, now: str | None = None) -> None:
        prices = state.get("price_versions", [])
        records = _expanded_records(state.get("_records", {}).values())
        native = _expanded_records(state.get("_native_records", {}).values())
        cumulative = [
            row for row in records
            if row.get("_cumulative") or row.get("source_mode") == "dsh_assistant_cumulative"
        ]
        # The persisted map is sorted by digest. Restore append order for each
        # source before the shared accounting core checks cumulative resets.
        cumulative.sort(key=lambda row: (
            (row.get("sources") or [{}])[0].get("source_id", ""),
            (row.get("sources") or [{}])[0].get("byte_offset", 0),
        ))
        ordinary = [row for row in records if row not in cumulative]
        try:
            accounted = account_usage_units(ordinary, cumulative=cumulative, native=native)
        except (KeyError, TypeError, ValueError) as exc:
            accounted = {"units": [], "ambiguous": [], "observed": [], "issues": [{"code": "metering_error", "message": str(exc)}]}
        units = accounted["units"]
        native_comparisons = accounted.get("dsh_native_comparisons", [])
        # Native replacement is scoped to the exact accounting identity.  A
        # known native session may suppress its duplicate proxy lifecycle, but
        # it must never mask an unrelated DSH session or a Codex activity
        # attempt in the same task.  Missing identity fields are deliberately
        # not treated as a wildcard: the raw paid attempt remains observable.
        native_primary_keys = {
            self._attempt_scope_key(item)
            for item in native_comparisons
            if item.get("selected_source") == "partial_native"
            and self._attempt_scope_key(item) is not None
        }

        def native_primary_for(attempt):
            return self._attempt_scope_key(attempt) in native_primary_keys
        unit_map = {}
        priced = Decimal(0)
        provisional = Decimal(0)
        pending = 0
        inflight = 0
        latest = None
        cost_units = []
        metered_sources = set()
        issues = list(accounted.get("issues", []))
        # Source parser failures are current projection blockers; historical
        # issue entries remain in the private source log but do not keep a
        # repaired source paused forever.
        for source in state.get("sources", {}).values():
            for issue in source.get("current_issues", []):
                if issue.get("code") == "source_unavailable":
                    continue
                if issue not in issues:
                    issues.append(_copy(issue))
        by_role = {}
        by_model = {}
        by_role_model = {}

        def aggregate(bucket, entry):
            bucket["units"] = int(bucket.get("units", 0)) + 1
            amount = entry.get("amount")
            if amount is None:
                bucket["unknown"] = int(bucket.get("unknown", 0)) + 1
                return
            amount_text = "provisional_amount" if entry.get("provisional") else "known_amount"
            bucket[amount_text] = _decimal_text(
                Decimal(str(bucket.get(amount_text, "0"))) + Decimal(str(amount))
            )

        for row in units:
            key = _record_key(row, fallback=_stable_digest(row.get("sources", [])))
            # Pin the price version when a usage unit is first priced.  A
            # later authorization may add a new version for the same
            # provider/model, but that must never reprice already-used units.
            stored = state.get("_records", {}).get(key) or state.get("_native_records", {}).get(key)
            stored_rows = _expanded_records([stored]) if stored else []
            price = self._price_for(state, row, strict=False)
            if price is not None:
                for stored_row in stored_rows:
                    if not stored_row.get("_budget_price_version"):
                        stored_row["_budget_price_version"] = price.get("version")
            estimate = estimate_budget_cost(row, price)
            status = estimate.get("status")
            if status == "usage_priced" and estimate.get("amount") is not None:
                amount = Decimal(str(estimate["amount"]))
                priced += amount
                for stored_row in stored_rows:
                    stored_row["_budget_last_amount"] = _decimal_text(amount)
            elif estimate.get("provisional") and estimate.get("amount") is not None:
                amount = Decimal(str(estimate["amount"]))
                provisional += amount
                for stored_row in stored_rows:
                    stored_row["_budget_last_amount"] = _decimal_text(amount)
            elif row.get("conflict") and row.get("_budget_last_amount") is not None:
                # Keep an already observed unit subtotal while the shared
                # deduplicator reports the new final/final conflict.  This
                # prevents a late contradictory row from silently refunding
                # the earlier known charge; the metering pause still blocks
                # new admission until the source is corrected.
                try:
                    prior_amount = Decimal(str(row["_budget_last_amount"]))
                except (InvalidOperation, TypeError, ValueError):
                    prior_amount = None
                if prior_amount is not None and prior_amount.is_finite() and prior_amount >= 0:
                    priced += prior_amount
                    status = "metering_error"
            elif status in {"pending_settlement", "unknown"}:
                if row.get("status") in {None, "", "unfinished", "inflight", "started"}:
                    inflight += 1
                else:
                    pending += 1
            elif status in {"budget_price_missing", "metering_error"}:
                issues.append({"code": status, "source": (row.get("sources") or [{}])[0]})
            stamp = row.get("timestamp") or row.get("settled_at") or row.get("received_at")
            if _timestamp(stamp) is not None and (latest is None or _timestamp(stamp) > _timestamp(latest)):
                latest = stamp
            entry = {
                "identity": _public_identity(row),
                "amount": (str(estimate["amount"]) if estimate.get("amount") is not None else None),
                "status": status,
                "provisional": bool(estimate.get("provisional")),
                "currency": estimate.get("currency") or state.get("currency"),
                "source": (row.get("sources") or [{}])[0],
            }
            unit_map[key] = entry
            cost_units.append(entry)
            if entry["amount"] is not None:
                metered_sources.update(ref["source_id"] for ref in row.get("sources", []))
            role = row.get("role") or row.get("semantic_role") or "unassigned"
            model = row.get("actual_model") or row.get("requested_model") or row.get("model") or "unassigned"
            aggregate(by_role.setdefault(str(role), {}), entry)
            aggregate(by_model.setdefault(str(model), {}), entry)
            aggregate(by_role_model.setdefault(f"{role}|{model}", {}), entry)
        # Codex's shared proxy records transport, not token receipts. Successful
        # transport is covered by its explicitly linked native numeric stream;
        # do not fabricate a second per-request receipt or charge it again.
        native_coverage = {}
        native_samples = {}
        native_usage_max = {}
        previous_usage = {}
        for row in cumulative:
            if row.get("runtime") != "codex":
                continue
            stamp = _timestamp(row.get("timestamp") or row.get("received_at"))
            for ref in row.get("sources", []):
                source_id = ref["source_id"]
                metadata = state.get("sources", {}).get(source_id, {}).get("metadata", {})
                capture_session = metadata.get("native_capture_session_id")
                selector = (capture_session, row.get("provider"), row.get("key_ref"),
                            row.get("actual_model") or row.get("requested_model"))
                if (source_id not in metered_sources or None in selector or stamp is None
                        or "" in selector):
                    continue
                sample = (row.get("runtime_session_id"),
                          tuple(row["usage"].get(field) for field in TOKEN_FIELDS))
                native_samples.setdefault(selector, set()).add(sample)
                segment = row.get("binding", {}).get("cumulative_segment", {})
                stream_key = (source_id, row.get("runtime_session_id"), segment.get("id"))
                previous = previous_usage.get(stream_key, segment.get("baseline") or {})
                if stream_key not in previous_usage and segment.get("fresh_zero_baseline"):
                    previous = {"input_tokens": 0, "output_tokens": 0}
                maxima = native_usage_max.setdefault(selector, {})
                for field in ("input_tokens", "output_tokens"):
                    before, current = previous.get(field), row["usage"].get(field)
                    if before is not None and current is not None and current >= before:
                        maxima[field] = max(maxima.get(field, 0), current - before)
                maxima["evidence_reference"] = f"{source_id}@{ref.get('byte_offset', 0)}"
                previous_usage[stream_key] = row["usage"]
                if stamp >= native_coverage.get(selector, {}).get("through", float("-inf")):
                    native_coverage[selector] = {"source": ref, "through": stamp, "additive": False}
        transport_groups = {}
        for attempt_key, attempt in state.get("_attempts", {}).items():
            attempt.pop("native_coverage", None)
            source = state.get("sources", {}).get((attempt.get("source") or {}).get("source_id"), {})
            metadata = source.get("metadata", {})
            if (attempt.get("status") not in {"not_admitted", "unfinished", "inflight", "started", None}
                    and not attempt.get("has_usage")
                    and attempt_key not in state.get("_attempt_estimates", {})
                    and metadata.get("shared") is True and metadata.get("runtime") == "codex"
                    and metadata.get("capture_session_id") == attempt.get("session_id")):
                selector = (attempt.get("session_id"), attempt.get("provider"), attempt.get("key_ref"),
                            attempt.get("actual_model") or attempt.get("requested_model"))
                transport_groups.setdefault(selector, []).append(attempt)
        for selector, attempts in transport_groups.items():
            covered = native_coverage.get(selector)
            if not covered:
                continue
            deficit = max(0, len(attempts) - len(native_samples[selector]))
            if deficit:
                maxima = native_usage_max[selector]
                if not maxima.get("input_tokens") or not maxima.get("output_tokens"):
                    continue
                estimated_row = {
                    "provider": selector[1], "key_ref": selector[2], "actual_model": selector[3],
                    "usage": {field: 2 * deficit * maxima[field]
                              for field in ("input_tokens", "output_tokens")},
                }
                estimate = estimate_budget_cost(
                    estimated_row, self._price_for(state, estimated_row, strict=False)
                )
                if estimate.get("amount") is None:
                    continue
                provisional += Decimal(str(estimate["amount"]))
                roles = {attempt.get("role") for attempt in attempts}
                role = next(iter(roles)) if len(roles) == 1 and None not in roles else "unassigned"
                entry = {
                    "identity": {"provider": selector[1], "key_ref": selector[2],
                                 "actual_model": selector[3], "capture_session_id": selector[0],
                                 "role": role},
                    "amount": str(estimate["amount"]), "provisional": True,
                    "status": "native_unmatched_estimate", "currency": state["currency"],
                    "source": covered["source"], "estimated_attempts": deficit,
                    "basis": "native_transport_deficit_peer_2x_not_upper_bound",
                    "evidence_reference": maxima["evidence_reference"],
                }
                unit_map["native-unmatched:" + _stable_digest(selector)] = entry
                cost_units.append(entry)
                aggregate(by_role.setdefault(role, {}), entry)
                aggregate(by_model.setdefault(selector[3], {}), entry)
                aggregate(by_role_model.setdefault(f"{role}|{selector[3]}", {}), entry)
            for attempt in attempts:
                # Aggregate coverage is not a measured receipt for this request.
                attempt["native_coverage"] = {**_copy(covered), "provisional_deficit": deficit}
        # Missing calls without any credible numeric basis retain their grace
        # and pause. New native receipts replace a group's deficit estimate.
        now_stamp = _timestamp(now) if now is not None else _now().timestamp()
        for attempt_key, attempt in state.get("_attempts", {}).items():
            if attempt.get("native_coverage"):
                continue
            source_kinds = set(attempt.get("source_kinds") or [])
            if attempt.get("native_lifecycle"):
                if not native_primary_for(attempt):
                    continue
            elif (
                native_primary_for(attempt)
                and source_kinds.intersection({"dsh_capture", "activity"})
            ):
                continue
            status = attempt.get("status")
            if status == "not_admitted":
                continue
            if status in {"unfinished", "inflight", "started", None}:
                inflight += 1
            elif not attempt.get("has_usage"):
                host_estimate = state.get("_attempt_estimates", {}).get(attempt_key)
                if host_estimate:
                    estimated_row = {
                        **attempt,
                        "actual_model": attempt.get("actual_model") or attempt.get("requested_model"),
                        "usage": host_estimate["usage_estimate"],
                    }
                    estimate = estimate_budget_cost(
                        estimated_row, self._price_for(state, estimated_row, strict=False)
                    )
                    if estimate.get("amount") is not None:
                        provisional += Decimal(str(estimate["amount"]))
                        entry = {
                            "identity": _public_identity(estimated_row),
                            "amount": str(estimate["amount"]), "provisional": True,
                            "status": "host_usage_estimate", "currency": state["currency"],
                            "source": attempt.get("source"),
                            "basis": host_estimate["basis"],
                            "evidence_reference": host_estimate["evidence_reference"],
                        }
                        unit_map["attempt-estimate:" + attempt_key] = entry
                        cost_units.append(entry)
                        role = attempt.get("role") or "unassigned"
                        model = estimated_row["actual_model"] or "unassigned"
                        aggregate(by_role.setdefault(role, {}), entry)
                        aggregate(by_model.setdefault(model, {}), entry)
                        aggregate(by_role_model.setdefault(f"{role}|{model}", {}), entry)
                        continue
                started = _timestamp(attempt.get("settled_at") or attempt.get("received_at"))
                if started is None or now_stamp - started <= PENDING_SETTLEMENT_SECONDS:
                    pending += 1
                else:
                    issues.append({"code": "metering_error", "source": attempt.get("source")})
        state["units"] = unit_map
        state["priced_amount"] = _decimal_text(priced)
        state["provisional_amount"] = _decimal_text(provisional)
        charged = priced + provisional
        authorised = Decimal(str(state.get("authorized_amount", "0")))
        state["charged_estimate"] = _decimal_text(charged)
        state["remaining_estimate"] = _decimal_text(authorised - charged)
        state["overspend_estimate"] = _decimal_text(max(Decimal(0), charged - authorised))
        state["pending_settlement"] = pending
        state["inflight_count"] = inflight
        state["metered_through"] = latest
        state["observed_at"] = now or _iso()
        known_zero_sources = bool(state.get("sources")) and all(
            source.get("status") == "closed_empty"
            and source.get("known_zero") is True
            for source in state.get("sources", {}).values()
        )
        state["coverage"] = {
            "status": (
                "complete" if units and not issues and not any(item["provisional"] for item in cost_units)
                else "complete" if known_zero_sources and not issues
                else "partial" if units else "unknown"
            ),
            "units": len(cost_units),
            "known": sum(1 for item in cost_units if item["amount"] is not None),
            "unknown": sum(1 for item in cost_units if item["amount"] is None),
            "provisional": sum(1 for item in cost_units if item["provisional"]),
            "issues": _copy(issues),
            "ambiguous": len(accounted.get("ambiguous", [])),
            "by_role": by_role,
            "by_model": by_model,
            "by_role_model": by_role_model,
            "known_zero_sources": sum(
                1 for source in state.get("sources", {}).values() if source.get("known_zero") is True
            ),
        }
        configured_limits = _copy(state.get("limits") or {})
        dynamic_inflight = []
        for attempt in state.get("_attempts", {}).values():
            source_kinds = set(attempt.get("source_kinds") or [])
            if attempt.get("native_lifecycle") and not native_primary_for(attempt):
                continue
            if (
                not attempt.get("native_lifecycle")
                and native_primary_for(attempt)
                and source_kinds.intersection({"dsh_capture", "activity"})
            ):
                continue
            if (
                attempt.get("has_usage")
                or attempt.get("status") == "not_admitted"
                or attempt.get("status") not in {"unfinished", "inflight", "started", None}
            ):
                continue
            dynamic_inflight.append(attempt.get("tail_limit") or attempt.get("limits") or attempt)
        if dynamic_inflight:
            configured_limits["inflight"] = dynamic_inflight
        elif any(
            not attempt.get("has_usage")
            and attempt.get("status") != "not_admitted"
            and (
                not native_primary_for(attempt)
                or attempt.get("native_lifecycle")
                or not set(attempt.get("source_kinds") or []).intersection({"dsh_capture", "activity"})
            )
            for attempt in state.get("_attempts", {}).values()
        ):
            configured_limits["inflight"] = [{}]
        late_usage = [
            row.get("tail_limit") or row.get("limits") or {}
            for row in units
            if row.get("status") not in {None, "", "unfinished", "inflight", "started"}
            and unit_map.get(_record_key(row), {}).get("amount") is None
        ]
        if late_usage:
            configured_limits["late_usage"] = late_usage
        active_owners = [
            value for value in (state.get("owners") or {}).values()
            if value.get("status", "active") not in {"exited", "not_started"}
        ]
        if state.get("pause_reasons") and not configured_limits.get("control_turns") and active_owners:
            configured_limits["control_turns"] = [{} for _ in active_owners]
        if state.get("pause_reasons") and not configured_limits.get("control_delay"):
            configured_limits["control_delay"] = [{}]
        state["tail_bound"] = estimate_tail_bound(prices=prices, limits=configured_limits)
        if charged >= authorised:
            _ensure_pause(state, "budget_exhausted", {"charged_estimate": _decimal_text(charged)})
        blocking_issues = [item for item in issues if _blocking_metering_issue(item)]
        if blocking_issues:
            _ensure_pause(state, "metering_error", {"issues": _copy(issues[-8:])})
        state["admission_open"] = not state.get("pause_reasons") and charged < authorised
        if state.get("pause_reasons"):
            state["control_status"] = _control_status(state)
        else:
            state["control_status"] = "open"

    def _price_for(self, state: dict, row: dict, *, strict: bool = True) -> dict | None:
        provider = row.get("provider") or row.get("provider_id")
        model = row.get("actual_model") or row.get("requested_model") or row.get("model")
        route = row.get("route") or row.get("access_route") or row.get("provider_route")
        pinned_version = row.get("_budget_price_version") or row.get("price_version")
        matches = []
        for price in state.get("price_versions", []):
            if price.get("provider") != provider:
                continue
            if price.get("actual_model") != model:
                continue
            if price.get("route") not in (None, route):
                continue
            if pinned_version is not None and price.get("version") != pinned_version:
                continue
            matches.append(price)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 and pinned_version is None:
            # Multiple immutable versions for one exact selector are safe for
            # a previously unpriced unit only when route identity is the same;
            # use the newest snapshot in that case.  An unknown route remains
            # ambiguous and must pause metering rather than guess.
            selectors = {(item.get("provider"), item.get("actual_model"), item.get("route")) for item in matches}
            if len(selectors) == 1:
                return matches[-1]
        return None

    def show(self, audience: str = "host") -> dict:
        if audience not in {"host", "delivery"}:
            raise BudgetError("budget_audience_invalid", {"audience": audience})
        with self._thread_lock:
            try:
                state = self._load_state()
            except BudgetError as exc:
                details = exc.details if isinstance(exc.details, dict) else {}
                if exc.code != "metering_error" or details.get("reason") not in {
                    "event_corrupt", "event_invalid", "event_sequence_gap",
                    "event_delta_missing", "event_offset_invalid",
                }:
                    raise
                state = self._safe_state_after_load_fault(details)
        result = {key: _copy(value) for key, value in state.items() if not key.startswith("_")}
        result["epoch"] = result.get("pause_epoch", 0)
        result["pause_reasons"] = [
            item.get("reason") if isinstance(item, dict) else item
            for item in state.get("pause_reasons", [])
        ]
        result["pause_reason_details"] = _copy(state.get("pause_reasons", []))
        if audience == "delivery":
            # Delivery receives the amount/admission projection and bounded
            # aggregate coverage only.  The per-unit map, owner identities,
            # source paths and pause metadata remain Host-private.
            delivery_fields = {
                "schema_version", "budget_ref", "budget_id", "task_ref", "currency",
                "authorized_amount", "priced_amount", "provisional_amount", "charged_estimate",
                "remaining_estimate", "overspend_estimate", "pending_settlement", "inflight_count",
                "metered_through", "observed_at", "coverage", "control_status", "admission_open",
                "pause_epoch", "epoch", "pause_reasons", "heartbeat_at", "monitor",
                "coverage_gaps", "out_of_scope", "tail_bound",
            }
            result = {key: value for key, value in result.items() if key in delivery_fields}
            if isinstance(result.get("monitor"), dict):
                result["monitor"] = {
                    key: value for key, value in result["monitor"].items()
                    if key in {"status", "heartbeat_at", "lease_until"}
                }
            result["coverage"] = {
                key: value for key, value in (state.get("coverage") or {}).items()
                if key not in {"issues", "ambiguous"}
            }
        return result

    def _safe_state_after_load_fault(self, details: dict) -> dict:
        """Expose the last atomic checkpoint without hiding a ledger fault.

        A read of ``show`` must remain useful when the append-only ledger has a
        malformed middle line.  The checkpoint is already an atomic, known
        safe subtotal; do not replay, repair, or write from this read path.
        Admission is closed in the returned projection until a mutating path
        can reconcile the source and event log.
        """
        try:
            state = _read_json(self.state_path, None)
        except (OSError, ValueError, TypeError):
            state = None
        if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA:
            state = self._initial_state(self._auth())
        state = _copy(state)
        state["admission_open"] = False
        reasons = state.setdefault("pause_reasons", [])
        if not any(
            (item.get("reason") if isinstance(item, dict) else item) == "metering_error"
            for item in reasons
        ):
            fault_epoch = int(state.get("pause_epoch", 0)) + 1
            state["pause_epoch"] = fault_epoch
            reasons.append({
                "reason": "metering_error",
                "epoch": fault_epoch,
                "requested_at": _iso(),
                "metadata": {"reason": "event_ledger_corrupt", **_copy(details)},
            })
        state["control_status"] = _control_status(state)
        coverage = state.setdefault("coverage", {})
        issues = coverage.setdefault("issues", [])
        fault = {"code": "metering_error", **_copy(details), "reason": "event_ledger_corrupt"}
        if fault not in issues:
            issues.append(fault)
        return state

    def add(self, config: dict) -> dict:
        normalised = _normalise_config(self.ref, config, for_add=True)
        delta = Decimal(normalised.get("amount", "0"))
        authorization_id = config.get("authorization_id") or config.get("authorization_reference")
        if authorization_id is None:
            authorization_id = f"add-{_stable_digest({k: v for k, v in normalised.items() if k != 'created_at'})[:24]}"
        authorization_id = _valid_id(authorization_id, "authorization_id")
        continue_authorized = config.get("continue_authorized") is True
        authorization_reference = config.get("authorization_reference") or config.get("authorization_id")
        digest = _stable_digest({
            "authorization_id": authorization_id,
            "authorization_reference": authorization_reference,
            "amount": _decimal_text(delta),
            "prices": normalised.get("prices", []),
            "continue_authorized": continue_authorized,
        })

        def update(state):
            for event in state.get("authorization_events", []):
                if event.get("authorization_id") != authorization_id:
                    continue
                if event.get("digest") != digest:
                    raise BudgetError("authorization_conflict", {"authorization_id": authorization_id})
                return self._public_from_state(state)
            if normalised.get("currency") != state.get("currency"):
                raise BudgetError("budget_currency_mismatch", {"currency": normalised.get("currency")})
            allowed_bindings = self._auth().get("allowed_bindings", [])
            for incoming in normalised.get("prices", []):
                if not self._binding_allowed(allowed_bindings, incoming):
                    raise BudgetError(
                        "budget_binding_not_allowed",
                        {"binding": _public_identity(incoming)},
                    )
            with localcontext() as context:
                context.prec = max(
                    _budget_state_precision(state),
                    len(str(state.get("authorized_amount", "0")))
                    + len(str(delta))
                    + 32,
                )
                state["authorized_amount"] = _decimal_text(
                    Decimal(state["authorized_amount"]) + delta
                )
            if normalised.get("prices"):
                self._merge_prices(state, normalised["prices"])
            state.setdefault("authorization_events", []).append({
                "type": "add",
                "authorization_id": authorization_id,
                "amount": _decimal_text(delta),
                "digest": digest,
                "authorization_reference": authorization_reference,
                "continue_authorized": continue_authorized,
                "at": _iso(),
            })
            self._refresh_summary(state)
            if continue_authorized:
                self._continue_state(
                    state,
                    authorization_id,
                    clear_reasons=config.get("clear_reasons"),
                    metadata={
                        "authorization_reference": authorization_reference,
                        "source": "authorization_add",
                    },
                )
            return self._public_from_state(state)

        return self._mutate(
            "authorization_add",
            update,
            {
                "authorization_id": authorization_id,
                "authorization_reference": authorization_reference,
                "continue_authorized": continue_authorized,
                "digest": digest,
            },
        )

    def _merge_prices(self, state: dict, prices: list[dict]) -> None:
        current = state.setdefault("price_versions", [])
        for incoming in prices:
            key = (incoming.get("provider"), incoming.get("actual_model"), incoming.get("route"), incoming.get("version"))
            existing = next((item for item in current if (item.get("provider"), item.get("actual_model"), item.get("route"), item.get("version")) == key), None)
            if existing is not None and existing != incoming:
                raise BudgetError("budget_price_conflict", {"price_version": incoming.get("version")})
            if existing is None:
                current.append(_copy(incoming))
        versions = [item.get("version") for item in current]
        state["price_version"] = versions[0] if len(versions) == 1 else versions

    def bind_owner(self, owner_id: str, **metadata) -> dict:
        owner_id = _valid_id(owner_id, "owner_id")

        def update(state):
            owner = state.setdefault("owners", {}).get(owner_id)
            incoming = {"owner_id": owner_id, **_copy(metadata)}
            if owner:
                # Rebinding a process is allowed to update liveness metadata,
                # while preserving prior control receipts.
                prior_control = owner.get("control", {})
                incoming = {**owner, **incoming, "control": prior_control}
            else:
                incoming["status"] = metadata.get("status", "active")
                incoming["control"] = {}
            state["owners"][owner_id] = incoming
            if state.get("pause_reasons"):
                state["control_status"] = _control_status(state)
            return self._public_from_state(state)

        return self._mutate("owner_bind", update, {"owner_id": owner_id})

    def register_source(self, source_id: str, path: str | Path, kind: str, binding: dict | None = None, **meta) -> dict:
        source_id = _valid_id(source_id, "source_id")
        if not isinstance(kind, str) or not kind:
            raise BudgetError("budget_source_invalid", {"source_id": source_id})
        source_path = Path(path).expanduser().resolve()
        binding = _copy(binding or {})

        def update(state):
            existing = state.setdefault("sources", {}).get(source_id)
            requested = {
                "source_id": source_id,
                "path": str(source_path),
                "kind": kind,
                "binding": binding,
                "metadata": _copy(meta),
            }
            if existing:
                if existing.get("path") != requested["path"] or existing.get("kind") != requested["kind"]:
                    raise BudgetError("budget_source_conflict", {"source_id": source_id})
                existing["binding"] = {**(existing.get("binding") or {}), **binding}
                existing["metadata"] = {**(existing.get("metadata") or {}), **_copy(meta)}
                existing["heartbeat_at"] = existing.get("heartbeat_at") or _iso()
                return self._public_from_state(state)
            state["sources"][source_id] = {
                **requested,
                "cursor": 0,
                "line_count": 0,
                "status": "registered",
                "known_zero": False,
                "registered_at": _iso(),
                "last_progress_at": None,
                "heartbeat_at": _iso(),
                "issues": [],
                "current_issues": [],
                "backlog_since": None,
            }
            if state.get("heartbeat_at") is None:
                state["heartbeat_at"] = _iso()
            owner_id = binding.get("owner_id") or meta.get("owner_id")
            if owner_id and owner_id not in state.setdefault("owners", {}):
                state["owners"][owner_id] = {"owner_id": owner_id, "status": "active", "control": {}}
            return self._public_from_state(state)

        return self._mutate("source_register", update, {"source_id": source_id, "path": str(source_path), "kind": kind})

    def _parse_row(self, row: dict, source: dict, offset: int, now: str) -> tuple[str, dict | None]:
        if not isinstance(row, dict):
            return "invalid", None
        # The runtime writes this terminal receipt when local admission is
        # denied before an upstream request.  It is retained in the source
        # file for auditability, but it is not a provider attempt and must not
        # enter the missing-usage grace window (or manufacture zero usage).
        if row.get("event") == "attempt_end" and row.get("status") == "not_admitted":
            return "ignored", None
        binding = source.get("binding") or {}
        kind = source.get("kind")
        metadata = source.get("metadata") or {}
        expected_session = metadata.get("capture_session_id")
        if expected_session is not None:
            observed_session = (
                row.get("session_id")
                or row.get("proxy_session_id")
                or row.get("runtime_session_id")
            )
            if observed_session != expected_session:
                # Shared provider receipts are one physical file.  A source
                # registration with a capture session is the explicit slice;
                # rows from other sessions (and rows without that identity)
                # are consumed but never attributed to this budget.
                return "ignored", None
        window = metadata.get("window") or binding.get("window")
        if isinstance(window, dict):
            stamp = _timestamp(
                row.get("timestamp")
                or row.get("end")
                or row.get("received_at")
            )
            start = _timestamp(window.get("start"))
            end = _timestamp(window.get("end"))
            if None in (stamp, start, end) or not start <= stamp < end:
                return "ignored", None

        def binding_value(name: str):
            if name == "provider":
                return binding.get("provider") or binding.get("provider_id")
            if name == "actual_model":
                return (
                    binding.get("actual_model")
                    or binding.get("model")
                    or binding.get("requested_model")
                )
            if name == "runtime_session_id":
                return binding.get("runtime_session_id") or binding.get("thread_id")
            return binding.get(name)

        def row_value(name: str):
            if name == "provider":
                return row.get("provider") or row.get("provider_id")
            if name == "actual_model":
                return row.get("actual_model") or row.get("model") or row.get("requested_model")
            if name == "runtime_session_id":
                return row.get("runtime_session_id") or row.get("thread_id")
            return row.get(name)

        binding_conflicts = [
            name
            for name in (
                "task_ref", "provider", "key_ref", "actual_model", "runtime",
                "runtime_session_id", "process_instance", "thread_id", "turn_id",
                "role", "phase", "operation_id",
            )
            if binding_value(name) is not None
            and row_value(name) is not None
            and binding_value(name) != row_value(name)
        ]
        task_ref = self._auth().get("task_ref")
        if row.get("task_ref") is not None and row.get("task_ref") != task_ref:
            binding_conflicts.append("task_ref")
        if kind == "activity":
            event = row.get("event")
            call_id = row.get("call_id")
            if event not in {"llm_start", "llm_end"}:
                # Tool/lifecycle activity is useful to close statistics but
                # does not represent a model call for the budget projection.
                return "activity", None
            if not isinstance(call_id, str) or not call_id:
                return "invalid", None
            activity = {
                key: row.get(key, binding.get(key))
                for key in (
                    "task_ref", "agent_id", "session_id", "run_id", "operation_id", "batch_id",
                    "round", "role", "phase", "provider", "provider_id", "account_ref", "key_ref",
                    "requested_model", "actual_model", "model", "requested_effort", "effective_effort",
                    "runtime", "runtime_session_id", "process_instance", "thread_id", "turn_id",
                    "purpose",
                )
            }
            activity["provider"] = activity.get("provider") or activity.get("provider_id")
            activity["actual_model"] = (
                activity.get("actual_model")
                or activity.get("model")
                or activity.get("requested_model")
            )
            activity["task_ref"] = activity.get("task_ref") or task_ref
            activity["event"] = event
            activity["call_id"] = call_id
            logical_call_id = row.get("logical_call_id")
            activity["logical_call_id"] = (
                logical_call_id if isinstance(logical_call_id, str) and logical_call_id else call_id
            )
            activity["status"] = row.get("status")
            activity["received_at"] = row.get("recorded_at") or row.get("received_at") or now
            activity["timestamp"] = activity["received_at"]
            activity["sources"] = [{"source_id": source["source_id"], "byte_offset": offset}]
            activity["binding"] = _copy(binding)
            if binding_conflicts:
                activity["binding_conflicts"] = sorted(set(binding_conflicts))
                activity["_source_issues"] = [
                    {
                        "code": "binding_identity_conflict",
                        "source_id": source["source_id"],
                        "byte_offset": offset,
                        "fields": sorted(set(binding_conflicts)),
                    }
                ]
            return "activity", activity
        native = None
        frame = row.get("frame") if isinstance(row.get("frame"), dict) else {}
        if kind == "dsh_native" or row.get("type") in {"assistant/message", "assistant/attempt", "llm/retry-started", "compaction/summary"} or frame.get("method") == "session.event":
            try:
                native = native_numeric_event(row)
            except (TypeError, ValueError, KeyError):
                return "invalid", None
            if native is None:
                return "ignored", None
            for name in ("runtime_session_id", "process_instance"):
                bound_value = binding_value(name)
                native_value = native.get(name)
                if bound_value is not None and native_value is not None and bound_value != native_value:
                    binding_conflicts.append(name)
            observed = {**binding, **{key: value for key, value in native.items() if value is not None}, "task_ref": binding.get("task_ref", task_ref)}
            observed["sources"] = [{"source_id": source["source_id"], "byte_offset": offset}]
            observed["binding"] = _copy(binding)
            observed["received_at"] = now
            if binding_conflicts:
                observed["binding_conflicts"] = sorted(set(binding_conflicts))
                observed["_source_issues"] = [
                    {
                        "code": "binding_identity_conflict",
                        "source_id": source["source_id"],
                        "byte_offset": offset,
                        "fields": sorted(set(binding_conflicts)),
                    }
                ]
                observed["usage"] = {field: None for field in TOKEN_FIELDS}
            return "native", observed
        usage = None
        invalid = []
        raw_usage = row.get("raw_usage")
        semantics = row.get("usage_semantics") or binding.get("usage_semantics")
        if raw_usage is not None and semantics == DSH_SEMANTICS:
            fields = set(raw_usage) if isinstance(raw_usage, dict) else set()
            mode = "messages" if fields & {"cache_read_input_tokens", "cache_creation_input_tokens"} else "native"
            usage, invalid = normalize_dsh_usage(raw_usage if isinstance(raw_usage, dict) else {}, mode)
        elif isinstance(row.get("usage"), dict):
            usage, invalid = numeric_usage(row["usage"])
        elif isinstance(raw_usage, dict):
            # NumericReceiptWriter preserves ordinary provider response usage
            # under raw_usage.  Rehydrate canonical fields when no DSH bucket
            # definition is present; DSH-specific names remain unknown unless
            # their explicit semantics binding is available.
            usage, invalid = numeric_usage(raw_usage)
        elif isinstance(row.get("total"), dict):
            usage, invalid = numeric_usage(row["total"])
            row = {**row, "source_mode": row.get("source_mode", "thread_cumulative"), "_cumulative": True}
        if usage is None and row.get("event") == "thread_usage":
            usage, invalid = numeric_usage(row.get("total") or row.get("usage") or {})
            row = {**row, "source_mode": "thread_cumulative", "_cumulative": True}
        if usage is None and row.get("event") in {"attempt_start", "attempt_end"}:
            return "attempt", None
        identity = {
            key: row.get(key, binding.get(key))
            for key in (
                "task_ref", "agent_id", "session_id", "run_id", "operation_id", "batch_id", "round", "role", "phase",
                "provider", "provider_id", "account_ref", "key_ref", "requested_model", "actual_model", "model", "requested_effort", "effective_effort",
                "runtime", "runtime_session_id", "process_instance", "thread_id", "turn_id", "usage_definition_ref",
                "response_id", "request_id", "timestamp", "status", "settled_at", "purpose", "route", "access_route",
                "provider_route", "usage_semantics", "source_mode", "unique_request_evidence_ref",
                "input_max_tokens", "output_max_tokens", "i_max", "o_max", "tail_limit", "limits",
                "usage_complete", "native_type", "native_seq", "native_turn", "native_step",
            )
        }
        identity["provider"] = identity.get("provider") or identity.get("provider_id")
        identity["actual_model"] = identity.get("actual_model") or identity.get("model") or identity.get("requested_model")
        identity["task_ref"] = identity.get("task_ref") or task_ref
        identity["timestamp"] = identity.get("timestamp") or row.get("end") or row.get("received_at") or now
        identity["received_at"] = row.get("received_at") or now
        identity["raw_usage"] = _copy(raw_usage) if isinstance(raw_usage, dict) else None
        identity["usage"] = usage or {field: None for field in TOKEN_FIELDS}
        if binding_conflicts:
            identity["binding_conflicts"] = sorted(set(binding_conflicts))
            identity["_source_issues"] = [
                {
                    "code": "binding_identity_conflict",
                    "source_id": source["source_id"],
                    "byte_offset": offset,
                    "fields": sorted(set(binding_conflicts)),
                }
            ]
            identity["usage"] = {field: None for field in TOKEN_FIELDS}
        identity["sources"] = [{"source_id": source["source_id"], "byte_offset": offset}]
        identity["binding_evidence_refs"] = [binding.get("binding_evidence_ref", source["source_id"])]
        identity["binding"] = _copy(binding)
        identity["invalid_fields"] = invalid
        explicit_complete = row.get("usage_complete") if "usage_complete" in row else None
        if (
            explicit_complete is False
            and semantics != DSH_SEMANTICS
            and not invalid
            and all(identity["usage"].get(field) is not None for field in TOKEN_FIELDS[:3])
        ):
            explicit_complete = True
        identity["usage_complete"] = (
            explicit_complete is True if explicit_complete is not None else not invalid
        )
        identity["_cumulative"] = bool(row.get("_cumulative") or row.get("source_mode") in {"thread_cumulative", "dsh_assistant_cumulative"})
        if identity.get("_cumulative"):
            identity["source_mode"] = identity.get("source_mode") or "thread_cumulative"
        return "record", identity

    @staticmethod
    def _attempt_scope_key(row: dict) -> tuple | None:
        """Return the complete metering identity used for native replacement.

        A missing component is unknown, never a wildcard.  This keeps a
        native receipt for one runtime/session from closing a different
        attempt that happens to share the task budget.
        """
        values = (
            row.get("runtime"),
            row.get("runtime_session_id"),
            row.get("provider") or row.get("provider_id"),
            row.get("key_ref"),
        )
        if any(value is None or value == "" for value in values):
            return None
        return values

    @staticmethod
    def _attempt_aliases(row: dict) -> set[str]:
        aliases = set()
        request_id = row.get("request_id")
        proxy_session_id = row.get("proxy_session_id")
        attempt_index = row.get("attempt_index")
        valid_request = (
            isinstance(request_id, (str, int))
            and not isinstance(request_id, bool)
            and str(request_id)
        )
        valid_proxy_session = (
            isinstance(proxy_session_id, (str, int))
            and not isinstance(proxy_session_id, bool)
            and str(proxy_session_id)
        )
        valid_attempt_index = type(attempt_index) is int and attempt_index >= 1
        if valid_request:
            if valid_attempt_index:
                if valid_proxy_session:
                    aliases.add(
                        f"proxy-attempt:{proxy_session_id}:{request_id}:{attempt_index}"
                    )
                else:
                    aliases.add(f"request-attempt:{request_id}:{attempt_index}")
            else:
                # Legacy response receipts may carry only request_id.  Keep
                # that compatibility path when no retry discriminator was
                # supplied; numbered proxy attempts use only the composite.
                aliases.add(str(request_id))
        for key in ("provider_request_id", "response_id", "call_id", "logical_call_id"):
            value = row.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value):
                aliases.add(str(value))
        thread_id = row.get("thread_id")
        turn_id = row.get("turn_id")
        if isinstance(thread_id, (str, int)) and not isinstance(thread_id, bool) and str(thread_id):
            if isinstance(turn_id, (str, int)) and not isinstance(turn_id, bool) and str(turn_id):
                aliases.add(f"thread-turn:{thread_id}:{turn_id}")
        session_id = row.get("runtime_session_id")
        native_turn = row.get("native_turn")
        if native_turn is None:
            native_turn = turn_id
        native_step = row.get("native_step")
        if isinstance(session_id, str) and session_id and native_turn is not None:
            if native_step is not None:
                aliases.add(f"session-turn-step:{session_id}:{native_turn}:{native_step}")
            else:
                aliases.add(f"session-turn:{session_id}:{native_turn}")
        return aliases

    def _update_attempt(
        self,
        state: dict,
        row: dict,
        source: dict,
        offset: int,
        now: str,
        *,
        parsed: dict | None = None,
        activity: bool = False,
    ) -> None:
        """Merge ActivityRecorder boundaries and numeric receipt lifecycle.

        The activity and numeric files are independent append-only sources and
        can arrive in either order.  Match their stable call/request aliases
        before creating an attempt.  Only identity/timing is retained here;
        token values remain in the shared usage records.
        """
        not_admitted = row.get("event") == "attempt_end" and row.get("status") == "not_admitted"
        attempts = state.setdefault("_attempts", {})
        aliases = self._attempt_aliases(row)
        if parsed is not None:
            aliases.update(self._attempt_aliases(parsed))
        key = None
        attempt = None
        for candidate_key, candidate in attempts.items():
            if aliases.intersection(self._attempt_aliases(candidate)):
                key, attempt = candidate_key, candidate
                break
        if row.get("event") == "thread_usage" and attempt is None:
            # A cumulative snapshot is a numeric completion/update, not a
            # request identity.  Only attach it to an existing activity/native
            # turn whose thread/session and turn identity are explicit.
            return
        if not_admitted and attempt is None:
            # No attempt_start is expected for a local admission refusal.  If
            # a recorder did emit an activity boundary first, the existing
            # attempt is handled below without turning this refusal into a
            # missing-usage settlement.
            return
        if attempt is None:
            primary = next(iter(sorted(aliases)), None)
            if primary is None:
                return
            key = primary
            attempt = {
                "request_id": row.get("request_id") or row.get("provider_request_id") or primary,
                "received_at": (parsed or row).get("received_at") or now,
                "source": {"source_id": source["source_id"], "byte_offset": offset},
                "has_usage": False,
            }
            attempts[key] = attempt
        source_kind = source.get("kind")
        if source_kind:
            source_kinds = attempt.setdefault("source_kinds", [])
            if source_kind not in source_kinds:
                source_kinds.append(source_kind)
        # Lifecycle rows commonly carry only the event fields.  The source
        # binding is their durable runtime/session/provider/key context; use it
        # as a default while keeping an explicit row value authoritative.
        observed = {
            **(source.get("binding") or {}),
            **(parsed or row),
        }
        for field in (
            "request_id", "provider_request_id", "response_id", "call_id", "logical_call_id",
            "proxy_session_id", "attempt_index",
            "task_ref", "agent_id", "session_id", "run_id", "operation_id", "role", "phase",
            "provider", "key_ref", "requested_model", "actual_model", "runtime",
            "runtime_session_id", "process_instance", "thread_id", "turn_id", "purpose",
        ):
            value = observed.get(field)
            if value is not None and attempt.get(field) is None:
                attempt[field] = _copy(value)
        if attempt.get("received_at") is None:
            attempt["received_at"] = observed.get("received_at") or row.get("recorded_at") or now
        attempt.setdefault("source", {"source_id": source["source_id"], "byte_offset": offset})
        if not_admitted:
            if not attempt.get("has_usage"):
                attempt["status"] = "not_admitted"
                attempt["admission_status"] = "not_admitted"
                attempt["settled_at"] = row.get("end") or row.get("received_at") or now
            return
        if activity:
            event = row.get("event")
            if event == "llm_start":
                attempt["activity_started"] = True
                attempt.setdefault("started_at", observed.get("received_at") or now)
                if not attempt.get("has_usage") and not attempt.get("activity_ended"):
                    attempt["status"] = "inflight"
            elif event == "llm_end":
                attempt["activity_ended"] = True
                attempt["settled_at"] = observed.get("received_at") or now
                attempt["status"] = row.get("status") or "completed"
                if attempt.get("has_usage"):
                    attempt["status"] = "completed"
        else:
            event = row.get("event")
            if event == "response_usage" and parsed is not None:
                attempt["has_usage"] = True
            elif event == "thread_usage" and parsed is not None:
                usage = parsed.get("usage") or {}
                if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
                    attempt["has_usage"] = True
            if event == "attempt_start":
                attempt["status"] = row.get("status") or "inflight"
                attempt.setdefault("started_at", row.get("start") or row.get("received_at") or now)
            elif event == "attempt_end":
                attempt["status"] = row.get("status") or "completed"
                attempt["settled_at"] = row.get("end") or row.get("received_at") or now
            elif event == "response_usage":
                attempt["status"] = row.get("status") or "completed"
                if row.get("end") or row.get("received_at"):
                    attempt["settled_at"] = row.get("end") or row.get("received_at")
        limit = row.get("tail_limit") or row.get("limits")
        if limit is None and any(key in row for key in ("input_max_tokens", "output_max_tokens", "i_max", "o_max")):
            limit = {
                key: row.get(key)
                for key in ("input_max_tokens", "output_max_tokens", "i_max", "o_max")
                if key in row
            }
        if limit is not None:
            attempt["tail_limit"] = _copy(limit)
        if parsed and parsed.get("_source_issues"):
            attempt["source_issues"] = _copy(parsed["_source_issues"])

    def _update_native_attempt(
        self,
        state: dict,
        row: dict,
        source: dict,
        offset: int,
        now: str,
    ) -> None:
        """Track native completion without inventing a provider request id.

        DSH native events carry only the session/sequence/turn/step identity.
        Keep that exact identity in the existing lifecycle map and let the
        019/034 accounting path choose native versus provider usage.  Native
        retry markers are not completed calls and therefore do not enter the
        settlement grace window.
        """
        native_type = row.get("native_type")
        if native_type == "llm/retry-started":
            return
        if native_type not in {"assistant/message", "assistant/attempt", "compaction/summary"}:
            return
        session_id = row.get("runtime_session_id")
        sequence = row.get("native_seq")
        if not isinstance(session_id, str) or not session_id or type(sequence) is not int or sequence < 0:
            return
        key = f"native:{session_id}:{sequence}"
        attempts = state.setdefault("_attempts", {})
        attempt = attempts.get(key)
        if not isinstance(attempt, dict):
            aliases = self._attempt_aliases(row)
            for candidate_key, candidate in attempts.items():
                if aliases.intersection(self._attempt_aliases(candidate)):
                    key, attempt = candidate_key, candidate
                    break
        if not isinstance(attempt, dict):
            attempt = {
                "native_lifecycle": True,
                "native_identity": {
                    "runtime_session_id": session_id,
                    "native_seq": sequence,
                },
                "source": {"source_id": source["source_id"], "byte_offset": offset},
                "source_kinds": ["dsh_native"],
                "has_usage": False,
            }
            attempts[key] = attempt
        else:
            attempt["native_lifecycle"] = True
            attempt.setdefault("native_identity", {}).update({
                "runtime_session_id": session_id,
                "native_seq": sequence,
            })
            source_kinds = attempt.setdefault("source_kinds", [])
            if "dsh_native" not in source_kinds:
                source_kinds.append("dsh_native")
        for field in (
            "native_type", "native_turn", "native_step", "runtime", "provider",
            "key_ref", "actual_model", "role", "purpose",
        ):
            if row.get(field) is not None:
                attempt[field] = _copy(row[field])
        # Preserve the explicit DSH identity as flat attempt fields too.  A
        # later ActivityRecorder boundary can then join in either append
        # order through the same session/turn(/step) aliases, without
        # manufacturing a provider request id.
        attempt["runtime_session_id"] = session_id
        if row.get("native_turn") is not None:
            attempt["turn_id"] = _copy(row["native_turn"])
        stamp = row.get("timestamp") or now
        attempt["received_at"] = attempt.get("received_at") or stamp
        attempt["settled_at"] = stamp
        attempt["status"] = "completed"
        # A later native replacement may complete an earlier partial event;
        # never downgrade a completed usage observation from a duplicate copy.
        usage = row.get("usage") or {}
        complete = not row.get("invalid_fields") and all(
            usage.get(field) is not None for field in TOKEN_FIELDS[:4]
        )
        attempt["has_usage"] = bool(attempt.get("has_usage") or complete)

    def _read_source(
        self,
        state: dict,
        source: dict,
        now: str,
        *,
        byte_budget: int = MAX_TICK_BYTES,
        record_budget: int = MAX_TICK_RECORDS,
    ) -> tuple[list[dict], list[dict], int, int, int, bool]:
        path = Path(source["path"])
        cursor = int(source.get("cursor", 0))
        records, native, issues = [], [], []
        byte_budget = max(0, int(byte_budget))
        record_budget = max(0, int(record_budget))
        if byte_budget == 0 or record_budget == 0:
            return records, native, 0, 0, 0, False
        try:
            stat = path.stat()
            if stat.st_size < cursor:
                issue = {"code": "source_truncated", "source_id": source["source_id"], "cursor": cursor, "size": stat.st_size}
                issues.append(issue)
                source["status"] = "error"
                source["current_issues"] = [issue]
                source.setdefault("issues", []).append(issue)
                source["backlog_since"] = None
                return records, native, 0, 0, 0, False
            with path.open("rb") as stream:
                stream.seek(cursor)
                raw = stream.read(min(MAX_TICK_BYTES, byte_budget))
            read_bytes = len(raw)
            consumed = 0
            count = 0
            backlog = stat.st_size > cursor + read_bytes
            for line in raw.splitlines(keepends=True):
                if count >= min(MAX_TICK_RECORDS, record_budget):
                    backlog = True
                    break
                if not line.endswith(b"\n"):
                    break
                offset = cursor + consumed
                consumed += len(line)
                count += 1
                try:
                    row = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, TypeError):
                    issue = {"code": "invalid_json_line", "source_id": source["source_id"], "byte_offset": offset}
                    issues.append(issue)
                    continue
                status, parsed = self._parse_row(row, source, offset, now)
                if status == "record" and parsed is not None:
                    records.append(parsed)
                elif status == "native" and parsed is not None:
                    native.append(parsed)
                    self._update_native_attempt(state, parsed, source, offset, now)
                elif status == "activity" and parsed is not None:
                    self._update_attempt(
                        state,
                        row,
                        source,
                        offset,
                        now,
                        parsed=parsed,
                        activity=True,
                    )
                if parsed is not None:
                    issues.extend(parsed.get("_source_issues") or [])
                elif status == "invalid":
                    issues.append({"code": "invalid_usage_record", "source_id": source["source_id"], "byte_offset": offset})
                # Attempt state is numeric and bounded; it lets the projection
                # distinguish in-flight from a completed call with no usage.
                event = row.get("event")
                if event in {"attempt_start", "attempt_end", "response_usage", "thread_usage"} and self._attempt_aliases(row):
                    self._update_attempt(
                        state,
                        row,
                        source,
                        offset,
                        now,
                        parsed=parsed if status == "record" else None,
                    )
            if consumed:
                source["cursor"] = cursor + consumed
                source["line_count"] = int(source.get("line_count", 0)) + count
                source["last_progress_at"] = now
                source["status"] = "observed"
                source["known_zero"] = False
            elif stat.st_size == 0 and (
                (source.get("metadata") or {}).get("closed") is True
                or (source.get("metadata") or {}).get("closed_at") is not None
                or (source.get("binding") or {}).get("closed") is True
            ):
                # An explicitly closed empty source is a known zero, not a
                # missing usage record.  Keep its heartbeat alive while
                # preserving the distinction from a source that never closed.
                source["status"] = "closed_empty"
                source["known_zero"] = True
            else:
                source["status"] = "observed"
                source["known_zero"] = False
            if backlog:
                source["backlog_since"] = source.get("backlog_since") or now
            else:
                source["backlog_since"] = None
            source["heartbeat_at"] = now
            source["current_issues"] = list(issues)
            source["issues"] = (source.get("issues") or [])[-64:] + issues
            return records, native, consumed, read_bytes, count, backlog
        except OSError:
            issue = {"code": "source_unavailable", "source_id": source["source_id"]}
            source["status"] = "unavailable"
            source["current_issues"] = [issue]
            source["backlog_since"] = None
            source.setdefault("issues", []).append(issue)
            return records, native, 0, 0, 0, False

    def _claim_monitor(self, owner_id: str) -> dict:
        owner_id = _valid_id(owner_id, "monitor_owner_id")
        now = _now()
        now_value = _iso(now)
        lease_value = _iso(datetime.fromtimestamp(now.timestamp() + HEARTBEAT_TIMEOUT_SECONDS, timezone.utc))

        def update(state):
            monitor = state.setdefault("monitor", {
                "owner_id": None,
                "status": "not_started",
                "lease_until": None,
                "heartbeat_at": None,
            })
            current_owner = monitor.get("owner_id")
            current_lease = _timestamp(monitor.get("lease_until"))
            if current_owner and current_owner != owner_id and current_lease is not None and current_lease > now.timestamp():
                raise BudgetError(
                    "budget_monitor_owned",
                    {"owner_id": current_owner, "lease_until": monitor.get("lease_until")},
                )
            monitor.update({
                "owner_id": owner_id,
                "status": "active",
                "heartbeat_at": now_value,
                "lease_until": lease_value,
            })
            state["heartbeat_at"] = now_value
            return self._public_from_state(state)

        return self._mutate("monitor_claim", update, {"owner_id": owner_id})

    def _touch_monitor(self, state: dict, owner_id: str, now_value: str) -> None:
        monitor = state.setdefault("monitor", {
            "owner_id": None,
            "status": "not_started",
            "lease_until": None,
            "heartbeat_at": None,
        })
        now_stamp = _timestamp(now_value) or _now().timestamp()
        current_owner = monitor.get("owner_id")
        current_lease = _timestamp(monitor.get("lease_until"))
        if current_owner and current_owner != owner_id and current_lease is not None and current_lease > now_stamp:
            raise BudgetError(
                "budget_monitor_owned",
                {"owner_id": current_owner, "lease_until": monitor.get("lease_until")},
            )
        monitor.update({
            "owner_id": owner_id,
            "status": "active",
            "heartbeat_at": now_value,
            "lease_until": _iso(datetime.fromtimestamp(now_stamp + HEARTBEAT_TIMEOUT_SECONDS, timezone.utc)),
        })

    def _release_monitor(self, owner_id: str) -> dict:
        """Release a monitor lease after its worker has actually exited."""
        owner_id = _valid_id(owner_id, "monitor_owner_id")

        def update(state):
            monitor = state.setdefault("monitor", {})
            if monitor.get("owner_id") == owner_id:
                monitor.update({
                    "owner_id": None,
                    "status": "stopped",
                    "lease_until": None,
                })
            return self._public_from_state(state)

        return self._mutate("monitor_release", update, {"owner_id": owner_id})

    def tick(self, now: str | datetime | None = None, *, monitor_id: str | None = None) -> dict:
        now_value = _iso(now) if isinstance(now, datetime) else (now or _iso())

        def update(state):
            replay_targets = _copy(state.get("_replay_targets") or {})
            if monitor_id is not None:
                self._touch_monitor(state, monitor_id, now_value)
            had_source_issues = any(
                source.get("current_issues") for source in state.get("sources", {}).values()
            )
            new_records, new_native = [], []
            source_items = list(state.get("sources", {}).items())
            if source_items:
                start = int(state.get("source_round_robin", 0)) % len(source_items)
                ordered_sources = source_items[start:] + source_items[:start]
            else:
                ordered_sources = []
            bytes_left = MAX_TICK_BYTES
            records_left = MAX_TICK_RECORDS
            for source_id, source in ordered_sources:
                if bytes_left <= 0 or records_left <= 0:
                    try:
                        unread = Path(source["path"]).stat().st_size > int(source.get("cursor", 0))
                    except OSError:
                        unread = False
                    backlog = unread
                    if backlog:
                        source["backlog_since"] = source.get("backlog_since") or now_value
                    continue
                records, native, _, read_bytes, read_records, backlog = self._read_source(
                    state,
                    source,
                    now_value,
                    byte_budget=bytes_left,
                    record_budget=records_left,
                )
                bytes_left -= read_bytes
                records_left -= read_records
                new_records.extend(records)
                new_native.extend(native)
                if backlog:
                    source["backlog_since"] = source.get("backlog_since") or now_value
            if source_items:
                state["source_round_robin"] = (start + 1) % len(source_items)
            for record in new_records:
                key = _record_key(record)
                previous = state.setdefault("_records", {}).get(key)
                state["_records"][key] = _merge_record(previous, record) if previous else record
            for record in new_native:
                key = _record_key(record, fallback=f"native:{record.get('runtime_session_id')}:{record.get('native_seq')}")
                previous = state.setdefault("_native_records", {}).get(key)
                state["_native_records"][key] = _merge_record(previous, record) if previous else record
            # Numeric recomputation is needed for new/replacement units and
            # pending settlements.  A healthy no-data tick only advances the
            # observation/heartbeat projection; it does not rescan all old
            # token records.
            replay_pending = False
            if replay_targets:
                replay_pending = any(
                    source_id not in state.get("sources", {})
                    or int(state["sources"][source_id].get("cursor", 0)) < int(target.get("cursor", 0))
                    for source_id, target in replay_targets.items()
                )
            if replay_pending:
                # The replayed event already contains the last committed safe
                # subtotal.  Until every source cursor reaches that event's
                # checkpoint, recomputing from the old token-history snapshot
                # would drop units that were only present in the event delta.
                # Keep the checkpoint subtotal and close the catch-up window
                # on the next complete source pass.
                state["_replay_targets"] = replay_targets
            elif replay_targets:
                state.pop("_replay_targets", None)
            replay_complete = bool(replay_targets) and not replay_pending
            if (
                not replay_pending
                and (
                    replay_complete
                    or
                    new_records
                    or new_native
                    or state.get("pending_settlement")
                    or state.get("inflight_count")
                    or not state.get("units")
                    or had_source_issues
                    or any(source.get("current_issues") for source in state.get("sources", {}).values())
                )
            ):
                self._refresh_summary(state, now=now_value)
            elif not replay_pending:
                state["observed_at"] = now_value
            # Source unavailability and a stalled heartbeat are recoverable
            # safety stops; normal no-new-data ticks remain healthy.
            now_stamp = _timestamp(now_value) or _now().timestamp()
            for source in state.get("sources", {}).values():
                heartbeat = _timestamp(source.get("heartbeat_at"))
                if source.get("status") in {"unavailable", "error"}:
                    last = _timestamp(source.get("last_progress_at") or source.get("registered_at"))
                    if last is None or now_stamp - last > HEARTBEAT_TIMEOUT_SECONDS:
                        _ensure_pause(state, "metering_error", {"source_id": source["source_id"], "status": source.get("status")})
                backlog_since = _timestamp(source.get("backlog_since"))
                if backlog_since is not None and now_stamp - backlog_since > HEARTBEAT_TIMEOUT_SECONDS:
                    _ensure_pause(
                        state,
                        "metering_error",
                        {"source_id": source["source_id"], "reason": "source_backlog"},
                    )
                elif heartbeat is not None and now_stamp - heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                    _ensure_pause(state, "metering_error", {"source_id": source["source_id"], "heartbeat_at": source.get("heartbeat_at")})
            state["heartbeat_at"] = now_value
            state["admission_open"] = not state.get("pause_reasons") and Decimal(state["charged_estimate"]) < Decimal(state["authorized_amount"])
            return self._public_from_state(state)

        return self._mutate("tick", update, {"observed_at": now_value})

    def check(self, now: str | datetime | None = None) -> dict:
        """Check monitor health and request a recoverable pause if stale."""
        now_value = _iso(now) if isinstance(now, datetime) else (now or _iso())

        def update(state):
            now_stamp = _timestamp(now_value) or _now().timestamp()
            stale = []
            for source in state.get("sources", {}).values():
                heartbeat = _timestamp(source.get("heartbeat_at"))
                if heartbeat is None or now_stamp - heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                    stale.append({"source_id": source["source_id"], "heartbeat_at": source.get("heartbeat_at")})
            budget_heartbeat = _timestamp(state.get("heartbeat_at"))
            if budget_heartbeat is None or now_stamp - budget_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                stale.append({"source_id": "budget-monitor", "heartbeat_at": state.get("heartbeat_at")})
            monitor = state.get("monitor") or {}
            lease = _timestamp(monitor.get("lease_until"))
            if monitor.get("owner_id") and (lease is None or now_stamp > lease):
                stale.append({"source_id": "budget-monitor-lease", "owner_id": monitor.get("owner_id"), "lease_until": monitor.get("lease_until")})
            if stale:
                _ensure_pause(state, "metering_error", {"stale": stale})
            return self._public_from_state(state)

        return self._mutate("watchdog", update, {"checked_at": now_value})

    watchdog = check

    def start_monitor(self, callback: Callable[[dict], Any] | None = None, *, interval: float = 2.0) -> BudgetMonitor:
        return BudgetMonitor(self, callback, interval).start()

    def monitor(self, callback: Callable[[dict], Any] | None = None, *, interval: float = 2.0) -> BudgetMonitor:
        return self.start_monitor(callback, interval=interval)

    def _consume_control_admission(self, control_id: str) -> dict:
        control_id = _valid_id(control_id, "control_id")

        def update(state):
            epoch = int(state.get("pause_epoch", 0))
            grants = state.setdefault("_control_grants", {})
            key = f"{epoch}:{control_id}"
            if key in grants:
                # The grant is durable admission state, not an idempotent
                # success response.  A retry after an RPC timeout or process
                # restart must stop before a second model turn is started.
                raise BudgetError(
                    "control_turn_already_consumed",
                    {
                        "budget_ref": str(self.ref),
                        "control_id": control_id,
                        "pause_epoch": epoch,
                        "admission": "control",
                    },
                )
            grants[key] = {
                "control_id": control_id,
                "epoch": epoch,
                "granted_at": _iso(),
            }
            # Retain every grant in the current epoch: D13 is once per
            # member/control id/epoch, including after a restart.  Old epochs
            # may be compacted when the task has accumulated many receipts.
            if len(grants) > 1024:
                old = [
                    (item_key, item)
                    for item_key, item in grants.items()
                    if int(item.get("epoch", -1)) != epoch
                ]
                old.sort(key=lambda pair: pair[1].get("granted_at", ""))
                for item_key, _item in old[: max(0, len(grants) - 1024)]:
                    grants.pop(item_key, None)
            return {
                "ok": True,
                "control_id": control_id,
                "pause_epoch": epoch,
                "budget_ref": str(self.ref),
                "admission": "control",
            }

        return self._mutate("control_admission", update, {"control_id": control_id})

    def require_available(self, operation: str | None = None, binding: dict | None = None, control_id: str | None = None) -> dict:
        with self._thread_lock:
            state = self._load_state()
        if operation is None and control_id:
            # Runtime pause/resume handling gets one control turn per epoch.
            # It remains available while ordinary model admission is closed;
            # the durable receipt rejects a retry before any model call.
            return self._consume_control_admission(control_id)
        if state.get("sources"):
            heartbeat = _timestamp(state.get("heartbeat_at"))
            now_stamp = _now().timestamp()
            monitor = state.get("monitor") or {}
            lease = _timestamp(monitor.get("lease_until"))
            monitor_stale = monitor.get("owner_id") and (lease is None or now_stamp > lease)
            if heartbeat is None or now_stamp - heartbeat > HEARTBEAT_TIMEOUT_SECONDS or monitor_stale:
                self.request_pause("metering_error", source_id="budget-monitor", heartbeat_at=state.get("heartbeat_at"))
                state = self._load_state()
        reasons = state.get("pause_reasons") or []
        if reasons:
            reason = reasons[0].get("reason") if isinstance(reasons[0], dict) else str(reasons[0])
            code = reason if reason in {"budget_exhausted", "metering_error", "authorization_revoked", "user_paused"} else "budget_paused"
            raise BudgetError(code, {
                "budget_ref": str(self.ref),
                "pause_epoch": state.get("pause_epoch"),
                "pause_reasons": _copy(reasons),
                "control_id": control_id,
            })
        if not state.get("admission_open", True) or Decimal(state.get("charged_estimate", "0")) >= Decimal(state.get("authorized_amount", "0")):
            raise BudgetError("budget_exhausted", self._admission_details(state, control_id))
        if operation is not None:
            allowed = self._auth().get("allowed_operations", [])
            if allowed and operation not in allowed:
                raise BudgetError("budget_operation_not_allowed", {"operation": operation})
        selector = _copy(binding or {})
        if selector and not self._binding_allowed(self._auth().get("allowed_bindings", []), selector):
            raise BudgetError("budget_binding_not_allowed", {"binding": _public_identity(selector)})
        if selector:
            with self._thread_lock:
                state = self._load_state()
            price = self._price_for(state, selector, strict=False)
            if price is None or set((price.get("rates") or {})) != {"cached_input_tokens", "uncached_input_tokens", "output_tokens"}:
                raise BudgetError("budget_price_missing", {"binding": _public_identity(selector)})
        return {
            "ok": True,
            "budget_ref": str(self.ref),
            "budget_id": state.get("budget_id"),
            "pause_epoch": state.get("pause_epoch", 0),
            "control_id": control_id,
            "remaining_estimate": state.get("remaining_estimate"),
        }

    def record_attempt_estimate(
        self, *, proxy_session_id: str, request_id: str, attempt_index: int,
        usage_estimate: dict, evidence_reference: str, basis: str,
    ) -> dict:
        """Host-only, evidenced provisional cost; never a fabricated usage receipt.

        The exact ended attempt remains unchanged. Its actual numeric receipt,
        if it arrives later, automatically takes precedence on recomputation.
        This method neither adds authorization nor clears a pause.
        """
        evidence_reference = _valid_id(evidence_reference, "evidence_reference")
        basis = _valid_id(basis, "basis")
        normalized, invalid = numeric_usage(usage_estimate)
        if invalid or any(normalized.get(field) is None for field in ("input_tokens", "output_tokens")):
            raise BudgetError("budget_estimate_invalid", {"fields": invalid})

        def update(state):
            matches = [(key, attempt) for key, attempt in state.get("_attempts", {}).items()
                       if attempt.get("proxy_session_id") == proxy_session_id
                       and attempt.get("request_id") == request_id
                       and attempt.get("attempt_index") == attempt_index]
            if len(matches) != 1:
                raise BudgetError("budget_attempt_not_found", {"request_id": request_id})
            key, attempt = matches[0]
            if attempt.get("status") not in {"completed", "client_disconnected", "stream_error", "transport_error", "http_error"}:
                raise BudgetError("budget_attempt_not_ended", {"request_id": request_id})
            state.setdefault("_attempt_estimates", {})[key] = {
                "usage_estimate": normalized, "basis": basis,
                "evidence_reference": evidence_reference,
            }
            self._refresh_summary(state)
            return self._public_from_state(state)

        return self._mutate("host_attempt_estimate", update, {
            "proxy_session_id": proxy_session_id, "request_id": request_id,
            "attempt_index": attempt_index, "evidence_reference": evidence_reference,
        })

    def request_pause(self, reason: str, **meta) -> dict:
        reason = _valid_id(reason, "reason")

        def update(state):
            _ensure_pause(state, reason, meta)
            state["admission_open"] = False
            state["control_status"] = _control_status(state)
            return self._public_from_state(state)

        return self._mutate("pause_request", update, {"reason": reason, **_copy(meta)})

    def _metering_recovered(self, state: dict) -> bool:
        """Return whether the current observable inputs support resuming metering."""
        now_stamp = _now().timestamp()
        for source in state.get("sources", {}).values():
            if source.get("status") in {"unavailable", "error"}:
                return False
            heartbeat = _timestamp(source.get("heartbeat_at"))
            if heartbeat is None or now_stamp - heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                return False
        monitor = state.get("monitor") or {}
        lease = _timestamp(monitor.get("lease_until"))
        if monitor.get("owner_id") and (lease is None or lease <= now_stamp):
            return False
        for source in state.get("sources", {}).values():
            if any(_blocking_metering_issue(issue) for issue in source.get("current_issues", [])):
                return False
        for issue in (state.get("coverage") or {}).get("issues", []):
            if _blocking_metering_issue(issue):
                return False
        return True

    def _continue_state(
        self,
        state: dict,
        authorization_id: str,
        *,
        clear_reasons: Iterable[str] | None = None,
        metadata: dict | None = None,
    ) -> bool:
        requested = clear_reasons
        if requested is None:
            requested_reasons = {"budget_exhausted"}
        elif isinstance(requested, str):
            requested_reasons = {requested}
        else:
            requested_reasons = {str(item) for item in requested}
        reasons = state.get("pause_reasons", [])
        current_reasons = {
            item.get("reason") if isinstance(item, dict) else str(item)
            for item in reasons
        }
        if "authorization_revoked" in requested_reasons:
            raise BudgetError("authorization_revoked", {"authorization_id": authorization_id})
        if "metering_error" in requested_reasons and "metering_error" in current_reasons:
            self._refresh_summary(state)
            if not self._metering_recovered(state):
                raise BudgetError(
                    "metering_error",
                    {
                        "authorization_id": authorization_id,
                        "reason": "metering_inputs_not_recovered",
                        "coverage": _copy(state.get("coverage", {})),
                    },
                )
        removable = current_reasons & requested_reasons
        if not removable:
            return False
        state["pause_reasons"] = [
            item for item in reasons
            if (item.get("reason") if isinstance(item, dict) else str(item)) not in removable
        ]
        state["pause_epoch"] = int(state.get("pause_epoch", 0)) + 1
        state["owners"] = {
            owner: {**value, "control": {}}
            for owner, value in state.get("owners", {}).items()
        }
        self._refresh_summary(state)
        state["admission_open"] = (
            not state.get("pause_reasons")
            and Decimal(state["charged_estimate"]) < Decimal(state["authorized_amount"])
        )
        state["control_status"] = _control_status(state) if state.get("pause_reasons") else "open"
        return True

    def continue_authorized(self, authorization_id: str | None = None, **meta) -> dict:
        authorization_id = authorization_id or meta.pop("authorization_reference", None)
        if not authorization_id:
            raise BudgetError("authorization_required", {"action": "continue"})
        authorization_id = _valid_id(authorization_id, "authorization_id")
        digest = _stable_digest({"authorization_id": authorization_id, "metadata": meta})

        def update(state):
            for event in state.get("authorization_events", []):
                if event.get("type") != "continue" or event.get("authorization_id") != authorization_id:
                    continue
                if event.get("digest") != digest:
                    raise BudgetError("authorization_conflict", {"authorization_id": authorization_id})
                return self._public_from_state(state)
            self._refresh_summary(state)
            self._continue_state(
                state,
                authorization_id,
                clear_reasons=meta.get("clear_reasons"),
                metadata=meta,
            )
            state["authorization_events"].append({
                "type": "continue",
                "authorization_id": authorization_id,
                "digest": digest,
                "at": _iso(),
                "metadata": _copy(meta),
            })
            return self._public_from_state(state)

        return self._mutate(
            "continue_authorized",
            update,
            {"authorization_id": authorization_id, "digest": digest, **_copy(meta)},
        )

    def record_control(self, owner_id: str, epoch: int, status: str, **meta) -> dict:
        owner_id = _valid_id(owner_id, "owner_id")
        if not isinstance(epoch, int) or epoch < 0:
            raise BudgetError("control_epoch_invalid", {"epoch": epoch})
        if status not in {"requested", "submitted", "instruction_delivered", "effective", "unknown", "failed", "pending", "not_running", "not_started"}:
            raise BudgetError("control_status_invalid", {"status": status})

        def update(state):
            current_epoch = int(state.get("pause_epoch", 0))
            if epoch < current_epoch:
                return {
                    **self._public_from_state(state),
                    "status": "stale_control",
                    "stale_epoch": epoch,
                    "epoch": current_epoch,
                }
            if epoch > current_epoch:
                raise BudgetError("control_epoch_mismatch", {"expected": state.get("pause_epoch"), "received": epoch})
            owner = state.setdefault("owners", {}).setdefault(owner_id, {"owner_id": owner_id, "status": "active", "control": {}})
            controls = owner.setdefault("control", {})
            prior = controls.get(str(epoch))
            if prior is not None:
                prior_status = prior.get("status")
                if _CONTROL_STATUS_RANK.get(status, 0) < _CONTROL_STATUS_RANK.get(prior_status, 0):
                    return {
                        **self._public_from_state(state),
                        "status": "control_receipt_unchanged",
                        "owner_id": owner_id,
                        "epoch": epoch,
                        "control_status": state.get("control_status"),
                    }
            controls[str(epoch)] = {
                "status": status,
                "recorded_at": _iso(),
                **_copy(meta),
            }
            state["control_status"] = _control_status(state)
            return self._public_from_state(state)

        return self._mutate("control_receipt", update, {"owner_id": owner_id, "epoch": epoch, "status": status})

    def _public_from_state(self, state: dict) -> dict:
        return self.show_from_state(state)

    @staticmethod
    def show_from_state(state: dict) -> dict:
        return {key: _copy(value) for key, value in state.items() if not key.startswith("_")}

    def _admission_details(self, state: dict, control_id: str | None = None) -> dict:
        return {
            "budget_ref": str(self.ref),
            "authorized_amount": state.get("authorized_amount"),
            "charged_estimate": state.get("charged_estimate"),
            "remaining_estimate": state.get("remaining_estimate"),
            "overspend_estimate": state.get("overspend_estimate"),
            "pause_epoch": state.get("pause_epoch"),
            "control_id": control_id,
        }

    def _binding_allowed(self, allowed: list, binding: dict) -> bool:
        if not isinstance(allowed, list) or not allowed:
            return False
        for item in allowed:
            if not isinstance(item, dict):
                continue
            provider = binding.get("provider") or binding.get("provider_id")
            model = binding.get("actual_model") or binding.get("model") or binding.get("requested_model")
            item_provider = item.get("provider") or item.get("provider_id")
            item_model = item.get("actual_model") or item.get("model")
            item_route = item.get("route", item.get("access_route", item.get("provider_route")))
            binding_route = binding.get("route") or binding.get("access_route") or binding.get("provider_route")
            if item_provider == provider and item_model == model and item_route in (None, binding_route):
                return True
        return False


def _public_identity(row: dict) -> dict:
    fields = (
        "task_ref", "agent_id", "session_id", "run_id", "operation_id", "role", "phase", "provider", "key_ref",
        "requested_model", "actual_model", "runtime", "runtime_session_id", "process_instance", "thread_id", "turn_id",
        "response_id", "request_id", "purpose", "source_mode", "route", "access_route", "provider_route",
    )
    return {field: row.get(field) for field in fields if row.get(field) is not None}


def _record_key(row: dict, fallback: str | None = None) -> str:
    provider = row.get("provider")
    key_ref = row.get("key_ref")
    if row.get("response_id") and provider and key_ref:
        return _stable_digest([provider, key_ref, "response", row["response_id"]])
    if row.get("request_id") and provider and key_ref and row.get("unique_request_evidence_ref"):
        return _stable_digest([provider, key_ref, "request", row["request_id"]])
    source = (row.get("sources") or [{}])[0]
    return _stable_digest(fallback or [source.get("source_id"), source.get("byte_offset"), row.get("native_seq")])


def _expanded_records(rows: Iterable[dict]) -> list[dict]:
    """Expand retained conflicts without exposing the private wrapper.

    ``TaskBudget`` keeps one map entry per response identity for bounded
    persistence.  A final/final conflict is represented by a small variants
    list inside that entry so the shared 019/034 deduplicator can still see
    both observations and report the conflict.  Normal copies and
    partial-to-final revisions remain one row.
    """
    expanded = []
    for row in rows:
        variants = row.get("_conflict_variants") if isinstance(row, dict) else None
        if isinstance(variants, list) and variants:
            expanded.extend(variants)
        else:
            expanded.append(row)
    return expanded


def _record_is_partial(row: dict) -> bool:
    return (
        row.get("usage_complete") is False
        or bool(row.get("invalid_fields"))
        or row.get("status") in {"unfinished", "inflight", "started"}
    )


def _record_known_conflict(previous: dict, current: dict) -> bool:
    left = previous.get("usage") or {}
    right = current.get("usage") or {}
    for field in TOKEN_FIELDS:
        if left.get(field) is not None and right.get(field) is not None and left[field] != right[field]:
            return True
    left_raw = previous.get("raw_usage") or {}
    right_raw = current.get("raw_usage") or {}
    for field in set(left_raw) & set(right_raw):
        if left_raw.get(field) is not None and right_raw.get(field) is not None and left_raw[field] != right_raw[field]:
            return True
    return False


def _record_identity_conflict(previous: dict, current: dict) -> bool:
    # These fields determine attribution and price selection.  A missing
    # value can be completed by a later source, but two observed values must
    # remain visible to the shared conflict checker.
    fields = (
        "task_ref", "provider", "key_ref", "response_id", "request_id",
        "actual_model", "runtime", "runtime_session_id", "process_instance",
        "thread_id", "turn_id", "role", "phase", "operation_id",
        "usage_semantics",
    )
    return any(
        previous.get(field) is not None
        and current.get(field) is not None
        and previous.get(field) != current.get(field)
        for field in fields
    )


def _record_final_metadata_conflict(previous: dict, current: dict) -> bool:
    if _record_is_partial(previous) or _record_is_partial(current):
        return False
    for field in (
        "timestamp", "status", "settled_at",
        "native_type", "native_turn", "native_step",
    ):
        if (
            previous.get(field) is not None
            and current.get(field) is not None
            and previous.get(field) != current.get(field)
        ):
            return True
    return False


def _record_sources(*rows: dict) -> list[dict]:
    result = []
    seen = set()
    for row in rows:
        for source in row.get("sources") or []:
            marker = _stable_digest(source)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(_copy(source))
    return result


def _merge_compatible_record(previous: dict, current: dict, *, replace: bool = False) -> dict:
    """Merge a copy or an evidenced partial-to-final revision."""
    if replace:
        result = _copy(current)
        for key, value in previous.items():
            if key not in result or result.get(key) is None:
                result[key] = _copy(value)
        previous_usage = previous.get("usage") or {}
        current_usage = result.get("usage") or {}
        result["usage"] = {
            field: current_usage.get(field)
            if current_usage.get(field) is not None
            else previous_usage.get(field)
            for field in TOKEN_FIELDS
        }
        if previous.get("_budget_last_amount") is not None and result.get("_budget_last_amount") is None:
            result["_budget_last_amount"] = previous.get("_budget_last_amount")
    else:
        result = _copy(previous)
        previous_usage = result.get("usage") or {}
        current_usage = current.get("usage") or {}
        result["usage"] = {
            field: previous_usage.get(field)
            if previous_usage.get(field) is not None
            else current_usage.get(field)
            for field in TOKEN_FIELDS
        }
        # A richer final copy may provide the status/settlement metadata;
        # an unfinished copy must never overwrite an already final one.
        if not _record_is_partial(previous) and _record_is_partial(current):
            pass
        else:
            for key, value in current.items():
                if key.startswith("_") or key in {"usage", "sources", "binding_evidence_refs"}:
                    continue
                if value is not None:
                    result[key] = _copy(value)
        if current.get("_budget_last_amount") is not None:
            result["_budget_last_amount"] = current.get("_budget_last_amount")
    result["sources"] = _record_sources(previous, current)
    refs = {
        ref
        for row in (previous, current)
        for ref in row.get("binding_evidence_refs") or []
    }
    if refs:
        result["binding_evidence_refs"] = sorted(refs)
    return result


def _merge_record(previous: dict, current: dict) -> dict:
    """Merge source copies while retaining final conflicts for 019/034.

    A later complete row can replace an explicitly partial observation when
    its identity is still the same.  Two complete rows with conflicting
    known values are kept as variants; choosing the newer row here would
    silently erase the evidence and could refund an already observed unit.
    """
    previous_variants = (
        list(previous.get("_conflict_variants"))
        if isinstance(previous, dict) and isinstance(previous.get("_conflict_variants"), list)
        else [previous]
    )
    for index, variant in enumerate(previous_variants):
        identity_conflict = _record_identity_conflict(variant, current)
        known_conflict = _record_known_conflict(variant, current)
        metadata_conflict = _record_final_metadata_conflict(variant, current)
        if identity_conflict or metadata_conflict:
            continue
        if not known_conflict:
            previous_variants[index] = _merge_compatible_record(
                variant,
                current,
                replace=_record_is_partial(variant) and not _record_is_partial(current),
            )
            return _record_container(previous_variants)
        # A known difference is a valid correction only when the prior row
        # explicitly proves it was partial/incomplete.  Final/final rows stay
        # separate so the canonical usage core can emit its locator.
        if _record_is_partial(variant) and not _record_is_partial(current):
            previous_variants[index] = _merge_compatible_record(variant, current, replace=True)
            return _record_container(previous_variants)
    previous_variants.append(_copy(current))
    return _record_container(previous_variants)


def _record_container(variants: list[dict]) -> dict:
    if len(variants) == 1:
        return variants[0]
    return {
        "_conflict_variants": variants,
        "_conflict": True,
    }


def _ensure_pause(state: dict, reason: str, meta: dict | None = None) -> int:
    reasons = state.setdefault("pause_reasons", [])
    for item in reasons:
        if (item.get("reason") if isinstance(item, dict) else item) == reason:
            return int(state.get("pause_epoch", 0))
    state["pause_epoch"] = int(state.get("pause_epoch", 0)) + 1
    reasons.append({"reason": reason, "epoch": state["pause_epoch"], "requested_at": _iso(), "metadata": _copy(meta or {})})
    return state["pause_epoch"]


def _control_status(state: dict) -> str:
    reasons = state.get("pause_reasons") or []
    if not reasons:
        return "open"
    epoch = str(state.get("pause_epoch", 0))
    owners = state.get("owners") or {}
    active = [
        value for value in owners.values()
        if value.get("status", "active") not in {"exited", "not_started"}
    ]
    if all((value.get("control") or {}).get(epoch, {}).get("status") in {"effective", "not_running", "not_started"} for value in active):
        return "paused_confirmed"
    return "pause_pending"


def bind_budget(root: str | Path, ref: str | Path, owner_id: str, **metadata) -> TaskBudget:
    """Bind a session/runtime root to a host-private budget reference."""
    root_path = Path(root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    budget = TaskBudget(ref)
    # Loading here detects an invalid/missing reference before publishing the
    # binding file; it does not require session.json or native env variables.
    budget._auth()
    incoming_owner = _valid_id(owner_id, "owner_id")
    existing = None
    existing_path = None
    for candidate in (
        _binding_path(root_path),
        root_path / ".task-budget-binding.json",
        root_path / "cost-budget-binding.json",
        root_path / "cost-budget" / "binding.json",
    ):
        if not candidate.exists():
            continue
        try:
            value = _read_json(candidate)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, TypeError) as exc:
            raise BudgetError(
                "budget_binding_unavailable",
                {"path": str(candidate), "error": type(exc).__name__},
            ) from exc
        if not isinstance(value, dict):
            raise BudgetError("budget_binding_invalid", {"path": str(candidate)})
        existing = value
        existing_path = candidate
        break
    if existing is not None:
        existing_ref = existing.get("budget_ref") or existing.get("ref")
        if not existing_ref:
            raise BudgetError("budget_binding_invalid", {"path": str(existing_path)})
        if Path(existing_ref).expanduser().resolve() != budget.ref:
            raise BudgetError(
                "budget_binding_conflict",
                {"root": str(root_path), "existing_ref": str(Path(existing_ref).expanduser().resolve()), "requested_ref": str(budget.ref)},
            )
    previous_metadata = existing.get("metadata", {}) if isinstance(existing, dict) else {}
    if not isinstance(previous_metadata, dict):
        raise BudgetError("budget_binding_invalid", {"path": str(existing_path), "field": "metadata"})
    previous_owners = existing.get("owner_ids", []) if isinstance(existing, dict) else []
    if not isinstance(previous_owners, list):
        previous_owners = []
    owners = sorted({str(item) for item in previous_owners if item} | {incoming_owner} | ({str(existing.get("owner_id"))} if existing and existing.get("owner_id") else set()))
    binding = {
        "schema_version": BINDING_SCHEMA,
        "budget_ref": str(budget.ref),
        "owner_id": existing.get("owner_id", incoming_owner) if existing else incoming_owner,
        "owner_ids": owners,
        # Existing identity evidence wins on key collisions; new call sites
        # may only supplement metadata for an already-bound root.
        "metadata": {**_copy(metadata), **_copy(previous_metadata)},
        "bound_at": existing.get("bound_at", _iso()) if existing else _iso(),
    }
    _atomic_json(_binding_path(root_path), binding)
    budget.bind_owner(incoming_owner, root=str(root_path), **metadata)
    return budget


def budget_for(root: str | Path) -> TaskBudget | None:
    """Resolve a binding from a Host-private root without environment injection."""
    root_path = Path(root).expanduser().resolve()
    candidates = (
        _binding_path(root_path),
        root_path / ".task-budget-binding.json",
        root_path / "cost-budget-binding.json",
        root_path / "cost-budget" / "binding.json",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            value = _read_json(path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, TypeError) as exc:
            raise BudgetError(
                "budget_binding_unavailable",
                {"path": str(path), "error": type(exc).__name__},
            ) from exc
        if not isinstance(value, dict) or value.get("schema_version") not in {None, BINDING_SCHEMA}:
            continue
        ref = value.get("budget_ref") or value.get("ref")
        if ref:
            return TaskBudget(ref)
    return None


__all__ = [
    "BudgetError",
    "BudgetMonitor",
    "TaskBudget",
    "bind_budget",
    "budget_for",
]
