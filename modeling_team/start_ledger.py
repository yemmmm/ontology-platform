"""Append-only, cross-run authorization ledger for semantic starts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from .contracts import TeamConfigurationError


_RETRYABLE = {"runtime/infrastructure", "platform-contract", "collaboration/routing"}
_MAX_FREEZE_AGE = timedelta(minutes=20)
_MAX_FUTURE_FREEZE_SKEW = timedelta(minutes=1)
_INITIAL_START_CAP = 2
_MAX_ADDITIONAL_STARTS = 2
_DEFAULT_LEDGER_FILENAME = ".r2-3-002-start-ledger.jsonl"
_DEFAULT_LOCK_FILENAME = ".r2-3-002-start-ledger.lock"
_DEFAULT_REQUIREMENT_ID = "R2.3-002"
_FORMAL_REQUIREMENT_ID = "R2.3-005"
_FORMAL_LEDGER_FILENAME = ".r2-3-005-start-ledger.jsonl"
_FORMAL_LOCK_FILENAME = ".r2-3-005-start-ledger.lock"
_FORMAL_INITIAL_START_CAP = 1
_FORMAL_ADDITIONAL_STARTS = 3
R2_3_002_REQUIREMENT_ID = _DEFAULT_REQUIREMENT_ID
R2_3_005_REQUIREMENT_ID = _FORMAL_REQUIREMENT_ID
_GATE_BINDING_FIELDS = (
    "proof_matrix_path",
    "proof_matrix_digest",
    "p2a_pass_path",
    "p2a_pass_digest",
    "source_run_id",
)


@dataclass(frozen=True)
class StartLedgerConfig:
    """Immutable identity and policy for one requirement-owned start ledger."""

    requirement_id: str
    ledger_filename: str
    lock_filename: str
    initial_start_cap: int
    authorization_increment: int
    strict_sequence: bool = False
    allow_incomplete_modeling_quality_repair: bool = False


_LEDGER_CONFIGS = MappingProxyType(
    {
        _DEFAULT_REQUIREMENT_ID: StartLedgerConfig(
            requirement_id=_DEFAULT_REQUIREMENT_ID,
            ledger_filename=_DEFAULT_LEDGER_FILENAME,
            lock_filename=_DEFAULT_LOCK_FILENAME,
            initial_start_cap=_INITIAL_START_CAP,
            authorization_increment=_MAX_ADDITIONAL_STARTS,
        ),
        _FORMAL_REQUIREMENT_ID: StartLedgerConfig(
            requirement_id=_FORMAL_REQUIREMENT_ID,
            ledger_filename=_FORMAL_LEDGER_FILENAME,
            lock_filename=_FORMAL_LOCK_FILENAME,
            initial_start_cap=_FORMAL_INITIAL_START_CAP,
            authorization_increment=_FORMAL_ADDITIONAL_STARTS,
            strict_sequence=True,
            allow_incomplete_modeling_quality_repair=True,
        ),
    }
)


def resolve_ledger_config(
    requirement_id: str | None = None,
    *,
    ledger_filename: str | None = None,
    lock_filename: str | None = None,
    initial_start_cap: int | None = None,
    authorization_increment: int | None = None,
) -> StartLedgerConfig:
    """Resolve one of the fixed requirement ledger policies before file access.

    ``None`` means that the requirement-owned default is selected.  Explicit
    overrides are accepted only when they exactly match that policy, which
    prevents a caller from changing the ledger namespace or budget semantics.
    """

    selected_id = _DEFAULT_REQUIREMENT_ID if requirement_id is None else requirement_id
    if not isinstance(selected_id, str) or selected_id not in _LEDGER_CONFIGS:
        raise TeamConfigurationError("unknown start-ledger requirement ID")
    config = _LEDGER_CONFIGS[selected_id]
    if ledger_filename is not None and ledger_filename != config.ledger_filename:
        raise TeamConfigurationError("ledger filename does not match requirement configuration")
    if lock_filename is not None and lock_filename != config.lock_filename:
        raise TeamConfigurationError("lock filename does not match requirement configuration")
    if initial_start_cap is not None:
        if not isinstance(initial_start_cap, int) or isinstance(initial_start_cap, bool) or initial_start_cap < 1:
            raise TeamConfigurationError("initial start cap is invalid")
        if initial_start_cap != config.initial_start_cap:
            raise TeamConfigurationError("initial start cap does not match requirement configuration")
    if authorization_increment is not None:
        if (
            not isinstance(authorization_increment, int)
            or isinstance(authorization_increment, bool)
            or authorization_increment < 1
        ):
            raise TeamConfigurationError("authorization increment is invalid")
        if authorization_increment != config.authorization_increment:
            raise TeamConfigurationError(
                "authorization increment does not match requirement configuration"
            )
    # Validate all fixed policy values at the resolver boundary too.  This is
    # deliberately redundant with the constructor checks: a corrupted future
    # config table must fail before a path is created or opened.
    StartLedger._validate_filename(config.ledger_filename, "ledger filename")
    StartLedger._validate_filename(config.lock_filename, "lock filename")
    return config


class StartLedger:
    """A deliberately small local ledger; records are never rewritten or removed."""

    def __init__(
        self,
        root: Path,
        now: Callable[[], datetime] | None = None,
        *,
        ledger_filename: str | None = None,
        lock_filename: str | None = None,
        initial_start_cap: int | None = None,
        requirement_id: str | None = None,
        authorization_increment: int | None = None,
        config: StartLedgerConfig | None = None,
    ):
        if ledger_filename is not None:
            self._validate_filename(ledger_filename, "ledger filename")
        if lock_filename is not None:
            self._validate_filename(lock_filename, "lock filename")
        if ledger_filename is not None and lock_filename is not None and ledger_filename == lock_filename:
            raise TeamConfigurationError("ledger and lock filenames must differ")
        if config is not None:
            if not isinstance(config, StartLedgerConfig):
                raise TeamConfigurationError("start-ledger configuration is invalid")
            if requirement_id is not None and requirement_id != config.requirement_id:
                raise TeamConfigurationError("start-ledger requirement configuration drifts")
            resolved = resolve_ledger_config(
                config.requirement_id,
                ledger_filename=ledger_filename,
                lock_filename=lock_filename,
                initial_start_cap=initial_start_cap,
                authorization_increment=authorization_increment,
            )
            if resolved != config:
                raise TeamConfigurationError("start-ledger configuration is immutable")
        else:
            resolved = resolve_ledger_config(
                requirement_id,
                ledger_filename=ledger_filename,
                lock_filename=lock_filename,
                initial_start_cap=initial_start_cap,
                authorization_increment=authorization_increment,
            )
        ledger_filename = self._validate_filename(resolved.ledger_filename, "ledger filename")
        lock_filename = self._validate_filename(resolved.lock_filename, "lock filename")
        if ledger_filename == lock_filename:
            raise TeamConfigurationError("ledger and lock filenames must differ")
        self.path = root / ledger_filename
        self.lock_path = root / lock_filename
        self.config = resolved
        self._initial_start_cap = resolved.initial_start_cap
        self._authorization_increment = resolved.authorization_increment
        self.requirement_id = resolved.requirement_id
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _validate_filename(value: str, field: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or Path(value).is_absolute()
            or Path(value).name != value
            or "/" in value
            or "\\" in value
        ):
            raise TeamConfigurationError(f"{field} is invalid")
        return value

    @property
    def identity(self) -> dict[str, str]:
        return {"filename": self.path.name, "requirement_id": self.requirement_id}

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
        """Append one consumed, user-authorized requirement-specific extension."""
        if (
            not isinstance(additional_starts, int)
            or isinstance(additional_starts, bool)
            or additional_starts != self._authorization_increment
            or not isinstance(authorization_id, str)
            or not authorization_id.strip()
            or not isinstance(reference, str)
            or not reference.strip()
        ):
            raise TeamConfigurationError("budget authorization is invalid")

        def write(records: list[dict[str, Any]]) -> None:
            if self.config.strict_sequence:
                self._validate_strict_replay(records)
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
            if self.config.strict_sequence:
                self._validate_strict_budget_predecessor(records)
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
        if self.config.strict_sequence and (not isinstance(run_id, str) or not run_id.strip()):
            raise TeamConfigurationError("semantic start run ID is invalid")
        normalized_gate = self._normalize_gate_binding(gate_binding)

        def write(records: list[dict[str, Any]]) -> None:
            if self.config.strict_sequence:
                self._validate_strict_replay(records)
            cap = self._start_cap(records)
            if self._semantic_start_count(records) >= cap:
                raise TeamConfigurationError(
                    f"{self.requirement_id} semantic-start budget is exhausted"
                )
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
        if self.config.strict_sequence and (
            not isinstance(run_id, str)
            or not run_id.strip()
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise TeamConfigurationError("presemantic release is invalid")

        def write(records: list[dict[str, Any]]) -> bool:
            if self.config.strict_sequence:
                self._validate_strict_replay(records)
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
        if self.config.strict_sequence:
            if not isinstance(run_id, str) or not run_id.strip():
                raise TeamConfigurationError("failed run ID is invalid")
            if not isinstance(complete_modeling_quality_result, bool):
                raise TeamConfigurationError("complete modeling-quality result is invalid")

        def write(records: list[dict[str, Any]]) -> None:
            if self.config.strict_sequence:
                self._validate_strict_replay(records)
                starts = [record for record in records if record.get("event") == "semantic_start"]
                if not starts or starts[-1].get("run_id") != run_id:
                    raise TeamConfigurationError("terminal failure must classify the latest semantic start")
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
        if (
            not isinstance(failed_run_id, str)
            or not failed_run_id.strip()
            or not isinstance(repair_reference, str)
            or not repair_reference.strip()
            or not isinstance(baseline_hash, str)
            or not baseline_hash.strip()
        ):
            raise TeamConfigurationError("repair authorization needs tested repair evidence")
        normalized_gate = self._normalize_gate_binding(gate_binding)

        def write(records: list[dict[str, Any]]) -> None:
            if self.config.strict_sequence:
                self._validate_strict_replay(records)
            failure = self._latest(records, failed_run_id, "terminal_failure")
            if not self._repair_failure_eligible(failure):
                raise TeamConfigurationError("failed run cannot authorize a second start")
            repairs = [
                record
                for record in records
                if record.get("event") == "repair_authorization" and record.get("run_id") == failed_run_id
            ]
            if repairs:
                if not self.config.strict_sequence:
                    self._validate_repair_rebind(records, failed_run_id, repairs[-1], baseline_hash)
                else:
                    self._validate_strict_repair_rebind(
                        records, failed_run_id, repairs[-1], baseline_hash
                    )
                if not self._gate_equal(repairs[-1].get("gate_binding"), normalized_gate):
                    raise TeamConfigurationError("repair authorization gate binding is immutable")
            elif self.config.strict_sequence:
                self._validate_strict_first_repair(records, failed_run_id, failure, baseline_hash)
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

    def _repair_failure_eligible(self, failure: dict[str, Any] | None) -> bool:
        """Return whether one terminal failure may receive a repair authorization."""
        if (
            not isinstance(failure, dict)
            or failure.get("complete_modeling_quality_result") is not False
        ):
            return False
        classification = failure.get("classification")
        if classification in _RETRYABLE:
            return True
        return (
            classification == "modeling-quality"
            and self.config.allow_incomplete_modeling_quality_repair
        )

    def _validate_strict_replay(self, records: list[dict[str, Any]]) -> None:
        """Replay the formal R2.3-005 state machine without mutating the file."""

        reservations: dict[str, tuple[int, dict[str, Any]]] = {}
        started: set[str] = set()
        released: set[str] = set()
        failures: dict[str, tuple[int, dict[str, Any]]] = {}
        repairs: dict[str, list[dict[str, Any]]] = {}
        authorization_ids: set[str] = set()
        references: set[str] = set()
        cap = self._initial_start_cap
        semantic_count = 0
        known_events = {
            "reservation",
            "semantic_start",
            "presemantic_release",
            "terminal_failure",
            "budget_authorization",
            "repair_authorization",
        }
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("event") not in known_events:
                raise TeamConfigurationError("start ledger replay is invalid")
            event = record["event"]
            if event == "reservation":
                run_id = record.get("run_id")
                baseline = record.get("baseline_hash")
                freeze_started_at = record.get("freeze_started_at")
                if (
                    not isinstance(run_id, str)
                    or not run_id.strip()
                    or run_id in reservations
                    or not isinstance(baseline, str)
                    or not baseline.strip()
                    or not isinstance(freeze_started_at, str)
                    or not freeze_started_at.strip()
                ):
                    raise TeamConfigurationError("start ledger replay is invalid")
                try:
                    parsed_freeze = datetime.fromisoformat(freeze_started_at)
                    if parsed_freeze.tzinfo is None:
                        raise ValueError("timezone is required")
                except (TypeError, ValueError) as exc:
                    raise TeamConfigurationError("start ledger replay is invalid") from exc
                active_ids = set(reservations) - started - released
                if active_ids:
                    raise TeamConfigurationError("start ledger replay is invalid")
                if semantic_count >= cap:
                    raise TeamConfigurationError("budget authorization ledger is invalid")
                if record.get("gate_binding") is not None:
                    self._normalize_gate_binding(record.get("gate_binding"))
                if semantic_count:
                    previous = [
                        item for item in records[:index] if item.get("event") == "semantic_start"
                    ][-1]
                    previous_run_id = previous.get("run_id")
                    failure = failures.get(previous_run_id)
                    repair_list = repairs.get(previous_run_id, [])
                    if (
                        failure is None
                        or not self._repair_failure_eligible(failure[1])
                        or not repair_list
                        or repair_list[-1].get("baseline_hash") != baseline
                    ):
                        raise TeamConfigurationError("start ledger replay is invalid")
                    repair_index = records.index(repair_list[-1])
                    if not self._gate_equal(
                        repair_list[-1].get("gate_binding"), record.get("gate_binding")
                    ):
                        raise TeamConfigurationError("start ledger replay is invalid")
                    failure_index = failure[0]
                    if repair_index == failure_index + 1:
                        if semantic_count >= cap:
                            raise TeamConfigurationError("start ledger replay is invalid")
                    elif repair_index == failure_index + 2:
                        if records[repair_index - 1].get("event") != "budget_authorization":
                            raise TeamConfigurationError("start ledger replay is invalid")
                    else:
                        self._validate_strict_repair_rebind(
                            records[:index], previous_run_id, repair_list[-2], baseline
                        )
                reservations[run_id] = (index, record)
                continue
            run_id = record.get("run_id")
            if event in {"semantic_start", "presemantic_release", "terminal_failure", "repair_authorization"} and (
                not isinstance(run_id, str) or not run_id.strip()
            ):
                raise TeamConfigurationError("start ledger replay is invalid")
            if event == "semantic_start":
                if run_id not in reservations or run_id in started or run_id in released:
                    raise TeamConfigurationError("start ledger replay is invalid")
                reservation = reservations[run_id][1]
                if not self._gate_equal(
                    reservation.get("gate_binding"), record.get("gate_binding")
                ):
                    raise TeamConfigurationError("start ledger replay is invalid")
                semantic_count += 1
                if semantic_count > cap:
                    raise TeamConfigurationError("budget authorization ledger is invalid")
                started.add(run_id)
                continue
            if event == "presemantic_release":
                if (
                    run_id not in reservations
                    or run_id in started
                    or run_id in released
                    or not isinstance(record.get("reason"), str)
                    or not record.get("reason", "").strip()
                ):
                    raise TeamConfigurationError("start ledger replay is invalid")
                released.add(run_id)
                continue
            if event == "terminal_failure":
                classification = record.get("classification")
                complete = record.get("complete_modeling_quality_result")
                if (
                    run_id not in started
                    or run_id in failures
                    or classification not in _RETRYABLE | {"modeling-quality"}
                    or not isinstance(complete, bool)
                    or not any(
                        item.get("event") == "semantic_start" and item.get("run_id") == run_id
                        for item in records[:index]
                    )
                ):
                    raise TeamConfigurationError("start ledger replay is invalid")
                prior_starts = [
                    item for item in records[:index] if item.get("event") == "semantic_start"
                ]
                if not prior_starts or prior_starts[-1].get("run_id") != run_id:
                    raise TeamConfigurationError("terminal failure must classify the latest semantic start")
                failures[run_id] = (index, record)
                continue
            if event == "budget_authorization":
                additional = record.get("additional_starts")
                authorization_id = record.get("authorization_id")
                reference = record.get("reference")
                if (
                    not isinstance(additional, int)
                    or isinstance(additional, bool)
                    or additional != self._authorization_increment
                    or not isinstance(authorization_id, str)
                    or not authorization_id.strip()
                    or not isinstance(reference, str)
                    or not reference.strip()
                    or authorization_id in authorization_ids
                    or reference in references
                    or semantic_count != cap
                    or index == 0
                    or records[index - 1].get("event") != "terminal_failure"
                ):
                    raise TeamConfigurationError("budget authorization ledger is invalid")
                failure = records[index - 1]
                if (
                    failure.get("classification") not in _RETRYABLE
                    or failure.get("complete_modeling_quality_result") is not False
                    or failure.get("run_id") not in failures
                    or failures[failure["run_id"]][0] != index - 1
                ):
                    raise TeamConfigurationError("budget authorization ledger is invalid")
                authorization_ids.add(authorization_id)
                references.add(reference)
                cap += self._authorization_increment
                continue
            # repair_authorization
            baseline = record.get("baseline_hash")
            repair_reference = record.get("repair_reference")
            if (
                not isinstance(baseline, str)
                or not baseline.strip()
                or not isinstance(repair_reference, str)
                or not repair_reference.strip()
                or run_id not in failures
                or not self._repair_failure_eligible(failures[run_id][1])
            ):
                raise TeamConfigurationError("start ledger replay is invalid")
            prior_repairs = repairs.setdefault(run_id, [])
            if not prior_repairs:
                failure_index = failures[run_id][0]
                if index <= failure_index:
                    raise TeamConfigurationError("repair authorization ordering is invalid")
                prior_event = records[index - 1]
                if prior_event.get("event") == "budget_authorization":
                    # The budget validator above already proved this event is
                    # the exact predecessor of the failure it follows.
                    pass
                elif index != failure_index + 1 or semantic_count >= cap:
                    raise TeamConfigurationError("repair authorization requires the exact budget event")
                reservation = reservations[run_id][1]
                if baseline == reservation.get("baseline_hash"):
                    raise TeamConfigurationError("repair authorization baseline is not fresh")
            else:
                self._validate_strict_repair_rebind(
                    records[:index], run_id, prior_repairs[-1], baseline
                )
            prior_repairs.append(record)

    def _validate_strict_budget_predecessor(self, records: list[dict[str, Any]]) -> None:
        starts = [record for record in records if record.get("event") == "semantic_start"]
        if not starts or not records or records[-1].get("event") != "terminal_failure":
            raise TeamConfigurationError("budget authorization requires the latest retryable failure")
        failure = records[-1]
        if (
            failure.get("run_id") != starts[-1].get("run_id")
            or failure.get("classification") not in _RETRYABLE
            or failure.get("complete_modeling_quality_result") is not False
        ):
            raise TeamConfigurationError("budget authorization requires the latest retryable failure")

    def _validate_strict_first_repair(
        self,
        records: list[dict[str, Any]],
        failed_run_id: str,
        failure: dict[str, Any],
        baseline_hash: str,
    ) -> None:
        if not records:
            raise TeamConfigurationError("repair authorization ordering is invalid")
        failure_index = records.index(failure)
        cap = self._start_cap(records)
        starts = self._semantic_start_count(records)
        if records[-1] is failure:
            if starts >= cap:
                raise TeamConfigurationError("repair authorization requires the exact budget event")
        elif (
            records[-1].get("event") != "budget_authorization"
            or failure_index != len(records) - 2
        ):
            raise TeamConfigurationError("repair authorization ordering is invalid")
        if baseline_hash == self._reservation_baseline(records, failed_run_id):
            raise TeamConfigurationError("repair authorization baseline is not fresh")

    def _validate_strict_repair_rebind(
        self,
        records: list[dict[str, Any]],
        failed_run_id: str,
        prior_repair: dict[str, Any],
        baseline_hash: str,
    ) -> None:
        prior_baseline = prior_repair.get("baseline_hash")
        if (
            not isinstance(prior_baseline, str)
            or not prior_baseline.strip()
            or not isinstance(baseline_hash, str)
            or not baseline_hash.strip()
            or baseline_hash == prior_baseline
        ):
            raise TeamConfigurationError("repair authorization is immutable")
        repair_index = records.index(prior_repair)
        later_reservations = [
            (index, record)
            for index, record in enumerate(records[repair_index + 1 :], repair_index + 1)
            if record.get("event") == "reservation"
        ]
        if len(later_reservations) != 1:
            raise TeamConfigurationError("repair authorization is immutable")
        reservation_index, reservation = later_reservations[0]
        reservation_run_id = reservation.get("run_id")
        if (
            not isinstance(reservation_run_id, str)
            or reservation_run_id == failed_run_id
            or reservation.get("baseline_hash") != prior_baseline
            or any(
                record.get("event") == "semantic_start"
                and record.get("run_id") == reservation_run_id
                for record in records[reservation_index + 1 :]
            )
            or not any(
                record.get("event") == "presemantic_release"
                and record.get("run_id") == reservation_run_id
                for record in records[reservation_index + 1 :]
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

    @staticmethod
    def _reservation_baseline(records: list[dict[str, Any]], run_id: str) -> str | None:
        for record in records:
            if record.get("event") == "reservation" and record.get("run_id") == run_id:
                baseline = record.get("baseline_hash")
                return baseline if isinstance(baseline, str) else None
        return None

    def _validate_strict_next_start(
        self,
        records: list[dict[str, Any]],
        *,
        previous_run_id: str,
        previous_index: int,
        failure: dict[str, Any] | None,
        repair: dict[str, Any] | None,
        baseline_hash: str,
        cap: int,
    ) -> None:
        if (
            not failure
            or records.index(failure) <= previous_index
            or not self._repair_failure_eligible(failure)
            or not repair
            or records.index(repair) <= records.index(failure)
            or repair.get("baseline_hash") != baseline_hash
        ):
            raise TeamConfigurationError("next start lacks a frozen narrow repair baseline")
        starts = self._semantic_start_count(records)
        repair_index = records.index(repair)
        if repair_index == records.index(failure) + 1:
            if starts >= cap:
                raise TeamConfigurationError("next start lacks the exact budget authorization")
        elif repair_index == records.index(failure) + 2:
            if records[repair_index - 1].get("event") != "budget_authorization":
                raise TeamConfigurationError("next start lacks the exact budget authorization")
        elif len(
            [
                record
                for record in records
                if record.get("event") == "repair_authorization"
                and record.get("run_id") == previous_run_id
            ]
        ) > 1:
            # Every later rebind is validated against the immediately prior
            # repair and its one released, never-started reservation.
            repairs = [
                record
                for record in records
                if record.get("event") == "repair_authorization"
                and record.get("run_id") == previous_run_id
            ]
            self._validate_strict_repair_rebind(records, previous_run_id, repairs[-2], repair.get("baseline_hash"))
        else:
            raise TeamConfigurationError("next start lacks a frozen narrow repair baseline")

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
        if self.config.strict_sequence and (
            not isinstance(run_id, str)
            or not run_id.strip()
            or not isinstance(baseline_hash, str)
            or not baseline_hash.strip()
        ):
            raise TeamConfigurationError("reservation is invalid")
        if self.config.strict_sequence:
            self._validate_strict_replay(records)
        frozen_at = self._validate_freeze_time(freeze_started_at, invalid_message="freeze time is invalid")
        if any(record.get("run_id") == run_id for record in records):
            raise TeamConfigurationError("semantic start run ID is already recorded")
        active = [record for record in records if record.get("event") == "reservation"]
        released = {record.get("run_id") for record in records if record.get("event") == "presemantic_release"}
        started = {record.get("run_id") for record in records if record.get("event") == "semantic_start"}
        active = [record for record in active if record.get("run_id") not in released and record.get("run_id") not in started]
        if active:
            raise TeamConfigurationError(
                f"another {self.requirement_id} start reservation is active"
            )
        consumed = [record for record in records if record.get("event") == "semantic_start"]
        cap = self._start_cap(records)
        if len(consumed) >= cap:
            raise TeamConfigurationError(
                f"{self.requirement_id} semantic-start budget is exhausted"
            )
        if consumed:
            previous = consumed[-1]
            previous_index = records.index(previous)
            failure = self._latest(records, previous["run_id"], "terminal_failure")
            repair = self._latest(records, previous["run_id"], "repair_authorization")
            if self.config.strict_sequence:
                self._validate_strict_next_start(
                    records,
                    previous_run_id=previous["run_id"],
                    previous_index=previous_index,
                    failure=failure,
                    repair=repair,
                    baseline_hash=baseline_hash,
                    cap=cap,
                )
            elif (
                not failure
                or records.index(failure) <= previous_index
                or not self._repair_failure_eligible(failure)
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

    def _start_cap(self, records: list[dict[str, Any]]) -> int:
        """Replay the earned cap, rejecting authorizations before the prior tranche is consumed."""
        if self.config.strict_sequence:
            self._validate_strict_replay(records)
        authorization_ids: set[str] = set()
        references: set[str] = set()
        cap = self._initial_start_cap
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
                or additional_starts != self._authorization_increment
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
            cap += self._authorization_increment
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
            raise TeamConfigurationError(
                f"{self.requirement_id} 20-minute freeze-to-start gate expired"
            )
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
