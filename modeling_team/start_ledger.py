"""Append-only, cross-run authorization ledger for R2.3-002 semantic starts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .contracts import TeamConfigurationError


_RETRYABLE = {"runtime/infrastructure", "platform-contract", "collaboration/routing"}
_MAX_FREEZE_AGE = timedelta(minutes=20)
_MAX_FUTURE_FREEZE_SKEW = timedelta(minutes=1)
_INITIAL_START_CAP = 2
_MAX_ADDITIONAL_STARTS = 2
_GATE_BINDING_FIELDS = (
    "proof_matrix_path",
    "proof_matrix_digest",
    "p2a_pass_path",
    "p2a_pass_digest",
    "source_run_id",
)


class StartLedger:
    """A deliberately small local ledger; records are never rewritten or removed."""

    def __init__(self, root: Path, now: Callable[[], datetime] | None = None):
        self.path = root / ".r2-3-002-start-ledger.jsonl"
        self.lock_path = root / ".r2-3-002-start-ledger.lock"
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def baseline_hash(manifest: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def reserve(
        self,
        run_id: str,
        baseline_hash: str,
        freeze_started_at: str,
        gate_binding: dict[str, Any] | None = None,
    ) -> None:
        normalized_gate = self._normalize_gate_binding(gate_binding)
        self._locked(
            lambda records: self._reserve(
                records, run_id, baseline_hash, freeze_started_at, normalized_gate
            )
        )

    def authorize_budget(self, additional_starts: int, authorization_id: str, reference: str) -> None:
        """Append one consumed, user-authorized +2 extension; ordinary run paths cannot create it."""
        if (
            not isinstance(additional_starts, int)
            or isinstance(additional_starts, bool)
            or additional_starts != _MAX_ADDITIONAL_STARTS
            or not isinstance(authorization_id, str)
            or not authorization_id.strip()
            or not isinstance(reference, str)
            or not reference.strip()
        ):
            raise TeamConfigurationError("budget authorization is invalid")

        def write(records: list[dict[str, Any]]) -> None:
            cap = self._start_cap(records)
            authorizations = [
                record for record in records if record.get("event") == "budget_authorization"
            ]
            if any(
                record.get("authorization_id") == authorization_id
                or record.get("reference") == reference
                for record in authorizations
            ):
                raise TeamConfigurationError("budget authorization is immutable")
            if self._semantic_start_count(records) != cap:
                raise TeamConfigurationError("budget authorization is not yet consumed")
            self._append(
                {
                    "event": "budget_authorization",
                    "additional_starts": additional_starts,
                    "authorization_id": authorization_id,
                    "reference": reference,
                }
            )

        self._locked(write)

    def mark_semantic_start(
        self, run_id: str, gate_binding: dict[str, Any] | None = None
    ) -> None:
        normalized_gate = self._normalize_gate_binding(gate_binding)

        def write(records: list[dict[str, Any]]) -> None:
            cap = self._start_cap(records)
            if self._semantic_start_count(records) >= cap:
                raise TeamConfigurationError("R2.3-002 semantic-start budget is exhausted")
            reservation = self._latest(records, run_id, "reservation")
            if (
                not reservation
                or self._latest(records, run_id, "semantic_start")
                or self._latest(records, run_id, "presemantic_release")
            ):
                raise TeamConfigurationError("semantic start is not an active unique reservation")
            self._validate_freeze_time(
                reservation.get("freeze_started_at"),
                invalid_message="start reservation has invalid freeze time",
            )
            reserved_gate = reservation.get("gate_binding")
            if not self._gate_equal(reserved_gate, normalized_gate):
                raise TeamConfigurationError("semantic start gate binding drifts from reservation")
            record: dict[str, Any] = {"event": "semantic_start", "run_id": run_id}
            if normalized_gate is not None:
                record["gate_binding"] = normalized_gate
            self._append(record)

        self._locked(write)

    def release_presemantic(self, run_id: str, reason: str) -> bool:
        def write(records: list[dict[str, Any]]) -> bool:
            if self._latest(records, run_id, "semantic_start"):
                raise TeamConfigurationError("a recorded semantic start cannot be uncounted")
            if not self._latest(records, run_id, "reservation"):
                raise TeamConfigurationError("reservation is unavailable")
            if self._latest(records, run_id, "presemantic_release"):
                return False
            self._append({"event": "presemantic_release", "run_id": run_id, "reason": reason})
            return True

        return self._locked(write)

    def terminal_failure(
        self, run_id: str, classification: str, complete_modeling_quality_result: bool, repair_baseline_hash: str | None = None
    ) -> None:
        if classification not in _RETRYABLE | {"modeling-quality"}:
            raise TeamConfigurationError("failure classification is invalid")
        def write(records: list[dict[str, Any]]) -> None:
            if self._latest(records, run_id, "terminal_failure"):
                raise TeamConfigurationError("terminal failure classification is immutable")
            self._append(
                {
                    "event": "terminal_failure",
                    "run_id": run_id,
                    "classification": classification,
                    "complete_modeling_quality_result": complete_modeling_quality_result,
                    "repair_baseline_hash": repair_baseline_hash,
                }
            )

        self._locked(write)

    def authorize_repair(
        self,
        failed_run_id: str,
        repair_reference: str,
        baseline_hash: str,
        gate_binding: dict[str, Any] | None = None,
    ) -> None:
        if not repair_reference or not baseline_hash:
            raise TeamConfigurationError("repair authorization needs tested repair evidence")
        normalized_gate = self._normalize_gate_binding(gate_binding)

        def write(records: list[dict[str, Any]]) -> None:
            failure = self._latest(records, failed_run_id, "terminal_failure")
            if (
                not failure
                or failure.get("classification") not in _RETRYABLE
                or failure.get("complete_modeling_quality_result") is not False
            ):
                raise TeamConfigurationError("failed run cannot authorize a second start")
            repairs = [
                record
                for record in records
                if record.get("event") == "repair_authorization" and record.get("run_id") == failed_run_id
            ]
            if repairs:
                self._validate_repair_rebind(records, failed_run_id, repairs[-1], baseline_hash)
                if not self._gate_equal(repairs[-1].get("gate_binding"), normalized_gate):
                    raise TeamConfigurationError("repair authorization gate binding is immutable")
            self._append(
                {
                    "event": "repair_authorization",
                    "run_id": failed_run_id,
                    "baseline_hash": baseline_hash,
                    "repair_reference": repair_reference,
                    **({"gate_binding": normalized_gate} if normalized_gate is not None else {}),
                }
            )

        self._locked(write)

    @staticmethod
    def _validate_repair_rebind(
        records: list[dict[str, Any]], failed_run_id: str, prior_repair: dict[str, Any], baseline_hash: str
    ) -> None:
        prior_baseline = prior_repair.get("baseline_hash")
        if not isinstance(prior_baseline, str) or not prior_baseline or baseline_hash == prior_baseline:
            raise TeamConfigurationError("repair authorization is immutable")
        repair_index = records.index(prior_repair)
        later_reservations = [
            record
            for record in records[repair_index + 1 :]
            if record.get("event") == "reservation"
        ]
        if len(later_reservations) != 1:
            raise TeamConfigurationError("repair authorization is immutable")
        reservation = later_reservations[0]
        reservation_run_id = reservation.get("run_id")
        reservation_index = records.index(reservation)
        if (
            not isinstance(reservation_run_id, str)
            or reservation_run_id == failed_run_id
            or reservation.get("baseline_hash") != prior_baseline
            or any(
                record.get("event") == "semantic_start" and record.get("run_id") == reservation_run_id
                for record in records
            )
            or not any(
                record.get("event") == "presemantic_release"
                and record.get("run_id") == reservation_run_id
                and records.index(record) > reservation_index
                for record in records
            )
        ):
            raise TeamConfigurationError("repair authorization is immutable")
        active = {
            record.get("run_id")
            for record in records
            if record.get("event") == "reservation"
        }
        released_or_started = {
            record.get("run_id")
            for record in records
            if record.get("event") in {"presemantic_release", "semantic_start"}
        }
        if active - released_or_started:
            raise TeamConfigurationError("repair authorization is immutable")

    def _reserve(
        self,
        records: list[dict[str, Any]],
        run_id: str,
        baseline_hash: str,
        freeze_started_at: str | None,
        gate_binding: dict[str, str] | None = None,
    ) -> None:
        frozen_at = self._validate_freeze_time(freeze_started_at, invalid_message="freeze time is invalid")
        if any(record.get("run_id") == run_id for record in records):
            raise TeamConfigurationError("semantic start run ID is already recorded")
        active = [record for record in records if record.get("event") == "reservation"]
        released = {record.get("run_id") for record in records if record.get("event") == "presemantic_release"}
        started = {record.get("run_id") for record in records if record.get("event") == "semantic_start"}
        active = [record for record in active if record.get("run_id") not in released and record.get("run_id") not in started]
        if active:
            raise TeamConfigurationError("another R2.3-002 start reservation is active")
        consumed = [record for record in records if record.get("event") == "semantic_start"]
        cap = self._start_cap(records)
        if len(consumed) >= cap:
            raise TeamConfigurationError("R2.3-002 semantic-start budget is exhausted")
        if consumed:
            previous = consumed[-1]
            previous_index = records.index(previous)
            failure = self._latest(records, previous["run_id"], "terminal_failure")
            repair = self._latest(records, previous["run_id"], "repair_authorization")
            if (
                not failure
                or records.index(failure) <= previous_index
                or failure.get("classification") not in _RETRYABLE
                or failure.get("complete_modeling_quality_result") is not False
                or not repair
                or records.index(repair) <= records.index(failure)
                or repair.get("baseline_hash") != baseline_hash
            ):
                raise TeamConfigurationError("next start lacks a frozen narrow repair baseline")
            if not self._gate_equal(repair.get("gate_binding"), gate_binding):
                raise TeamConfigurationError("reservation gate binding drifts from repair authorization")
        record: dict[str, Any] = {
            "event": "reservation",
            "run_id": run_id,
            "baseline_hash": baseline_hash,
            "freeze_started_at": frozen_at,
        }
        if gate_binding is not None:
            record["gate_binding"] = gate_binding
        self._append(record)

    @staticmethod
    def _start_cap(records: list[dict[str, Any]]) -> int:
        """Replay the earned cap, rejecting authorizations before the prior tranche is consumed."""
        authorization_ids: set[str] = set()
        references: set[str] = set()
        cap = _INITIAL_START_CAP
        semantic_start_count = 0
        for record in records:
            event = record.get("event")
            if event == "semantic_start":
                semantic_start_count += 1
                if semantic_start_count > cap:
                    raise TeamConfigurationError("budget authorization ledger is invalid")
                continue
            if event != "budget_authorization":
                continue
            additional_starts = record.get("additional_starts")
            authorization_id = record.get("authorization_id")
            reference = record.get("reference")
            if (
                not isinstance(additional_starts, int)
                or isinstance(additional_starts, bool)
                or additional_starts != _MAX_ADDITIONAL_STARTS
                or not isinstance(authorization_id, str)
                or not authorization_id.strip()
                or not isinstance(reference, str)
                or not reference.strip()
                or authorization_id in authorization_ids
                or reference in references
                or semantic_start_count != cap
            ):
                raise TeamConfigurationError("budget authorization ledger is invalid")
            authorization_ids.add(authorization_id)
            references.add(reference)
            cap += _MAX_ADDITIONAL_STARTS
        return cap

    @staticmethod
    def _semantic_start_count(records: list[dict[str, Any]]) -> int:
        return sum(record.get("event") == "semantic_start" for record in records)

    @staticmethod
    def _normalize_gate_binding(value: Any) -> dict[str, str] | None:
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != set(_GATE_BINDING_FIELDS):
            raise TeamConfigurationError("gate binding fields are invalid")
        result: dict[str, str] = {}
        for field in _GATE_BINDING_FIELDS:
            item = value.get(field)
            if not isinstance(item, str) or not item:
                raise TeamConfigurationError(f"gate binding {field} is invalid")
            result[field] = item
        for field in ("proof_matrix_digest", "p2a_pass_digest"):
            if len(result[field]) != 64:
                raise TeamConfigurationError(f"gate binding {field} is invalid")
            try:
                int(result[field], 16)
            except ValueError as exc:
                raise TeamConfigurationError(f"gate binding {field} is invalid") from exc
        if result["proof_matrix_path"].startswith("/") or result["p2a_pass_path"].startswith("/"):
            raise TeamConfigurationError("gate binding path is invalid")
        return result

    @staticmethod
    def _gate_equal(left: Any, right: Any) -> bool:
        """Compare canonical JSON bytes; absent optional bindings stay legacy-compatible."""
        if left is None or right is None:
            return left is None and right is None
        try:
            left_bytes = json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            right_bytes = json.dumps(right, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return False
        return left_bytes == right_bytes

    def _validate_freeze_time(self, value: object, *, invalid_message: str) -> str:
        try:
            frozen_at = datetime.fromisoformat(str(value))
            if frozen_at.tzinfo is None:
                raise ValueError("timezone is required")
            frozen_at = frozen_at.astimezone(UTC)
        except (TypeError, ValueError) as exc:
            raise TeamConfigurationError(invalid_message) from exc
        delta = self._now() - frozen_at
        if delta > _MAX_FREEZE_AGE:
            raise TeamConfigurationError("R2.3-002 20-minute freeze-to-start gate expired")
        if delta < -_MAX_FUTURE_FREEZE_SKEW:
            raise TeamConfigurationError("freeze time is unreasonably in the future")
        return str(value)

    @staticmethod
    def _latest(records: list[dict[str, Any]], run_id: str, event: str) -> dict[str, Any] | None:
        return next((record for record in reversed(records) if record.get("run_id") == run_id and record.get("event") == event), None)

    def _locked(self, action: Any) -> Any:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return action(self._records())
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TeamConfigurationError("start ledger is corrupt") from exc
            if not isinstance(record, dict):
                raise TeamConfigurationError("start ledger record is invalid")
            records.append(record)
        return records

    def _append(self, value: dict[str, Any]) -> None:
        envelope = {"recorded_at": self._now().isoformat(), **value}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
