"""Cooperative, run-local issue escalation for the formal Modeling Team.

The issue path is intentionally separate from ``TaskResult`` and from Runtime
pause/interrupt primitives.  Agents report a typed issue to the Broker; the
Coordinator receives a typed control; and the Runner performs the actual
delivery on its main loop.  This module contains no Runtime or platform code,
which keeps the state machine deterministic and easy to persist as append-only
evidence.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping


ISSUE_CATEGORIES = frozenset(
    {
        "business_clarification",
        "protocol_guidance",
        "platform_repair",
        "runtime_recovery",
    }
)
ISSUE_CONTROL_ACTIONS = frozenset({"pause", "resume", "abort"})
ISSUE_RESOLUTION_TYPES = frozenset({"guidance", "repair_completed", "abort"})
ISSUE_STATES = frozenset(
    {
        "reported",
        "pause_sent",
        "waiting_owner",
        "waiting_repair",
        "resolution_ready",
        "resume_sent",
        "resolved",
        "aborted",
        "rebind_required",
    }
)

_ID_PATTERN = re.compile(r"[a-z][a-z0-9_:/.-]{0,127}")
_FORBIDDEN_SECRET_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization\s*:\s*bearer|password\s*[:=]|secret\s*[:=]|token\s*[:=])",
    re.IGNORECASE,
)


class IssueError(ValueError):
    """A malformed, out-of-order, or replayed issue operation."""


def _required_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or not _ID_PATTERN.fullmatch(value):
        raise IssueError(f"{name} is invalid")
    return value


def _required_text(value: Any, name: str, *, allow_newlines: bool = True) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 32_000:
        raise IssueError(f"{name} is invalid")
    if not allow_newlines and any(char in value for char in "\r\n"):
        raise IssueError(f"{name} is invalid")
    if _FORBIDDEN_SECRET_PATTERN.search(value):
        raise IssueError(f"{name} contains a forbidden secret marker")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _optional_id(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_id(value, name)


def _canonical_mapping(value: Any, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise IssueError(f"{name} is invalid")
    result = dict(value)
    if any(not isinstance(key, str) or not key for key in result):
        raise IssueError(f"{name} is invalid")
    return result


def _requires_mutation_reconciliation(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in ("unknown", "uncertain", "indeterminate"))


@dataclass(frozen=True)
class IssueReport:
    run_id: str
    issue_id: str
    reporter_id: str
    coordinator_id: str
    category: str
    summary: str
    failing_operation: str
    error: str
    mutation_state: str
    requested_action: str
    control_epoch: int
    timestamp: float
    thread_id: str | None = None
    candidate_identity: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _required_id(self.run_id, "run_id")
        _required_id(self.issue_id, "issue_id")
        _required_id(self.reporter_id, "reporter_id")
        _required_id(self.coordinator_id, "coordinator_id")
        if self.category not in ISSUE_CATEGORIES:
            raise IssueError("issue category is invalid")
        for name, value in (
            ("summary", self.summary),
            ("failing_operation", self.failing_operation),
            ("error", self.error),
            ("mutation_state", self.mutation_state),
            ("requested_action", self.requested_action),
        ):
            _required_text(value, name)
        if isinstance(self.control_epoch, bool) or not isinstance(self.control_epoch, int) or self.control_epoch <= 0:
            raise IssueError("issue control epoch is invalid")
        if not isinstance(self.timestamp, (int, float)) or isinstance(self.timestamp, bool) or self.timestamp <= 0:
            raise IssueError("issue timestamp is invalid")
        _optional_id(self.thread_id, "thread_id")
        _canonical_mapping(self.candidate_identity, "candidate_identity")

    def as_dict(self, *, state: str) -> dict[str, Any]:
        if state not in ISSUE_STATES:
            raise IssueError("issue state is invalid")
        return {
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "reporter_id": self.reporter_id,
            "coordinator_id": self.coordinator_id,
            "category": self.category,
            "summary": self.summary,
            "failing_operation": self.failing_operation,
            "error": self.error,
            "mutation_state": self.mutation_state,
            "requested_action": self.requested_action,
            "control_epoch": self.control_epoch,
            "timestamp": self.timestamp,
            "thread_id": self.thread_id,
            "candidate_identity": self.candidate_identity,
            "state": state,
        }


@dataclass(frozen=True)
class IssueResolution:
    run_id: str
    issue_id: str
    reporter_id: str
    resolution_type: str
    control_epoch: int
    resolution_text: str | None = None
    repair_component: str | None = None
    before_digest: str | None = None
    after_digest: str | None = None
    verification_reference: str | None = None
    mutation_reconciliation: str | None = None

    def __post_init__(self) -> None:
        _required_id(self.run_id, "run_id")
        _required_id(self.issue_id, "issue_id")
        _required_id(self.reporter_id, "reporter_id")
        if self.resolution_type not in ISSUE_RESOLUTION_TYPES:
            raise IssueError("issue resolution type is invalid")
        if isinstance(self.control_epoch, bool) or not isinstance(self.control_epoch, int) or self.control_epoch <= 0:
            raise IssueError("issue resolution epoch is invalid")
        if self.resolution_type == "guidance":
            _required_text(self.resolution_text, "resolution_text")
            if any(value is not None for value in (self.repair_component, self.before_digest, self.after_digest, self.verification_reference, self.mutation_reconciliation)):
                raise IssueError("guidance resolution contains repair fields")
        elif self.resolution_type == "repair_completed":
            for name, value in (
                ("repair_component", self.repair_component),
                ("before_digest", self.before_digest),
                ("after_digest", self.after_digest),
                ("verification_reference", self.verification_reference),
                ("mutation_reconciliation", self.mutation_reconciliation),
            ):
                _required_text(value, name, allow_newlines=False)
            if self.resolution_text is not None:
                raise IssueError("repair resolution contains guidance text")
        else:
            _required_text(self.resolution_text, "resolution_text")
            if any(value is not None for value in (self.repair_component, self.before_digest, self.after_digest, self.verification_reference, self.mutation_reconciliation)):
                raise IssueError("abort resolution contains repair fields")

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "reporter_id": self.reporter_id,
            "resolution_type": self.resolution_type,
            "control_epoch": self.control_epoch,
            "resolution_text": self.resolution_text,
            "repair_component": self.repair_component,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "verification_reference": self.verification_reference,
            "mutation_reconciliation": self.mutation_reconciliation,
        }


@dataclass(frozen=True)
class IssueControl:
    run_id: str
    issue_id: str
    coordinator_id: str
    reporter_id: str
    action: str
    control_epoch: int
    resolution: IssueResolution | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _required_id(self.run_id, "run_id")
        _required_id(self.issue_id, "issue_id")
        _required_id(self.coordinator_id, "coordinator_id")
        _required_id(self.reporter_id, "reporter_id")
        if self.action not in ISSUE_CONTROL_ACTIONS:
            raise IssueError("issue control action is invalid")
        if isinstance(self.control_epoch, bool) or not isinstance(self.control_epoch, int) or self.control_epoch <= 0:
            raise IssueError("issue control epoch is invalid")
        if self.action == "resume" and self.resolution is None:
            raise IssueError("resume control requires a resolution")
        if (
            self.action == "resume"
            and self.resolution is not None
            and self.resolution.resolution_type == "abort"
        ):
            raise IssueError("resume control cannot carry an abort resolution")
        if self.action != "resume" and self.resolution is not None:
            raise IssueError("non-resume control cannot contain a resolution")
        if self.action == "abort":
            _required_text(self.reason, "abort reason", allow_newlines=False)
        elif self.reason is not None:
            _required_text(self.reason, "control reason", allow_newlines=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "coordinator_id": self.coordinator_id,
            "reporter_id": self.reporter_id,
            "action": self.action,
            "control_epoch": self.control_epoch,
            "resolution": self.resolution.as_dict() if self.resolution else None,
            "reason": self.reason,
        }


@dataclass
class _IssueState:
    report: IssueReport
    state: str = "reported"
    resolution: IssueResolution | None = None
    pause_dispatched: bool = False
    resume_dispatched: bool = False
    transitions: list[dict[str, Any]] = field(default_factory=list)


class RecoverableIssueLedger:
    """A one-active-issue CAS ledger owned by one TeamRunner."""

    def __init__(self, *, run_id: str, coordinator_id: str, clock: Any = time.time):
        self.run_id = _required_id(run_id, "run_id")
        self.coordinator_id = _required_id(coordinator_id, "coordinator_id")
        self.clock = clock
        self._active: _IssueState | None = None
        self._next_issue = 0
        self._reports: list[IssueReport] = []
        self._controls: list[IssueControl] = []
        self._evidence: list[dict[str, Any]] = []

    @property
    def active(self) -> _IssueState | None:
        return self._active

    @property
    def active_issue(self) -> IssueReport | None:
        return self._active.report if self._active else None

    @property
    def state(self) -> str | None:
        return self._active.state if self._active else None

    @property
    def pending(self) -> bool:
        return self._active is not None and self._active.state not in {"resolved", "aborted", "rebind_required"}

    def report(
        self,
        *,
        reporter_id: str,
        category: str,
        summary: str,
        failing_operation: str,
        error: str,
        mutation_state: str,
        requested_action: str,
        thread_id: str | None = None,
        candidate_identity: Mapping[str, Any] | None = None,
    ) -> IssueReport:
        if self._active is not None and self._active.state != "resolved":
            raise IssueError("an active issue already exists")
        reporter = _required_id(reporter_id, "reporter_id")
        self._next_issue += 1
        issue_id = f"issue-{self._next_issue}"
        issue = IssueReport(
            run_id=self.run_id,
            issue_id=issue_id,
            reporter_id=reporter,
            coordinator_id=self.coordinator_id,
            category=category,
            summary=summary,
            failing_operation=failing_operation,
            error=error,
            mutation_state=mutation_state,
            requested_action=requested_action,
            control_epoch=1,
            timestamp=float(self.clock()),
            thread_id=thread_id,
            candidate_identity=dict(candidate_identity) if candidate_identity is not None else None,
        )
        state = _IssueState(issue)
        self._active = state
        self._reports.append(issue)
        self._record("reported", issue_id=issue.issue_id, reporter_id=reporter)
        return issue

    def drain_reports(self) -> list[IssueReport]:
        values, self._reports = self._reports[:], []
        return values

    def bind_context(
        self,
        *,
        issue_id: str,
        reporter_id: str,
        thread_id: str | None,
        candidate_identity: Mapping[str, Any] | None,
    ) -> IssueReport:
        """Attach Runner-observed thread/candidate identity without changing semantics."""
        active = self._require_active(issue_id, reporter_id)
        if active.state != "reported":
            raise IssueError("issue context is no longer bindable")
        normalized_thread = _optional_id(thread_id, "thread_id")
        normalized_candidate = _canonical_mapping(candidate_identity, "candidate_identity")
        active.report = replace(
            active.report,
            thread_id=normalized_thread,
            candidate_identity=normalized_candidate,
        )
        return active.report

    def control(
        self,
        *,
        issue_id: str,
        coordinator_id: str,
        reporter_id: str,
        action: str,
        control_epoch: int,
        resolution: IssueResolution | None = None,
        reason: str | None = None,
    ) -> IssueControl:
        active = self._require_active(issue_id, reporter_id)
        coordinator = _required_id(coordinator_id, "coordinator_id")
        if coordinator != self.coordinator_id:
            raise IssueError("issue control coordinator is invalid")
        if control_epoch != active.report.control_epoch:
            raise IssueError("issue control epoch is stale")
        control = IssueControl(
            run_id=self.run_id,
            issue_id=issue_id,
            coordinator_id=coordinator,
            reporter_id=reporter_id,
            action=action,
            control_epoch=control_epoch,
            resolution=resolution,
            reason=reason,
        )
        if action == "pause":
            if active.state != "reported":
                raise IssueError("issue pause is not valid in current state")
            active.state = "pause_sent"
            self._record("pause_sent", issue_id=issue_id)
            active.state = "waiting_repair" if active.report.category == "platform_repair" else "waiting_owner"
            self._record(active.state, issue_id=issue_id)
        elif action == "resume":
            if active.state != "resolution_ready" or active.resolution is None:
                raise IssueError("issue resume requires persisted resolution")
            if resolution is None or resolution != active.resolution:
                raise IssueError("issue resume resolution does not match persisted resolution")
            active.state = "resume_sent"
            self._record("resume_sent", issue_id=issue_id)
        else:
            if (
                active.state != "resolution_ready"
                or active.resolution is None
                or active.resolution.resolution_type != "abort"
            ):
                raise IssueError("issue abort requires a persisted outer abort resolution")
            if reason != active.resolution.resolution_text:
                raise IssueError("issue abort reason does not match persisted resolution")
            active.state = "aborted"
            self._record("aborted", issue_id=issue_id, reason=reason)
        self._controls.append(control)
        return control

    def drain_controls(self) -> list[IssueControl]:
        values, self._controls = self._controls[:], []
        return values

    def persist_resolution(self, resolution: IssueResolution) -> IssueResolution:
        active = self._require_active(resolution.issue_id, resolution.reporter_id)
        if resolution.run_id != self.run_id or resolution.control_epoch != active.report.control_epoch:
            raise IssueError("issue resolution binding is invalid")
        if active.state not in {"waiting_owner", "waiting_repair"}:
            raise IssueError("issue resolution is not valid in current state")
        if active.resolution is not None:
            if active.resolution != resolution:
                raise IssueError("issue resolution replay conflicts")
            raise IssueError("issue resolution was already persisted")
        if (
            resolution.resolution_type != "abort"
            and _requires_mutation_reconciliation(active.report.mutation_state)
            and (
                resolution.resolution_type != "repair_completed"
                or resolution.mutation_reconciliation
                not in {
                    "reconciled",
                    "receipt_readback_reconciled",
                    "confirmed_no_write",
                }
            )
        ):
            raise IssueError("unknown mutation state requires formal reconciliation")
        active.resolution = resolution
        active.state = "resolution_ready"
        self._record("resolution_ready", issue_id=resolution.issue_id, resolution_type=resolution.resolution_type)
        return resolution

    def mark_dispatch(self, control: IssueControl) -> None:
        active = self._require_active(control.issue_id, control.reporter_id)
        if control.action == "pause":
            if active.state not in {"waiting_owner", "waiting_repair"} or active.pause_dispatched:
                raise IssueError("issue pause dispatch is invalid")
            active.pause_dispatched = True
        elif control.action == "resume":
            if active.state != "resume_sent" or active.resume_dispatched:
                raise IssueError("issue resume dispatch is invalid")
            active.resume_dispatched = True
            active.state = "resolved"
            self._record("resolved", issue_id=control.issue_id)

    def fail_rebind(self, *, issue_id: str, reporter_id: str, reason: str) -> None:
        active = self._require_active(issue_id, reporter_id)
        if active.state in {"resolved", "aborted", "rebind_required"}:
            raise IssueError("issue is already terminal")
        active.state = "rebind_required"
        self._record("rebind_required", issue_id=issue_id, reason=_required_text(reason, "reason", allow_newlines=False))

    def can_terminal(self) -> bool:
        return not self.pending

    def evidence(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._evidence]

    def _require_active(self, issue_id: str, reporter_id: str) -> _IssueState:
        _required_id(issue_id, "issue_id")
        reporter = _required_id(reporter_id, "reporter_id")
        active = self._active
        if active is None or active.report.issue_id != issue_id:
            raise IssueError("issue is not active")
        if active.report.reporter_id != reporter:
            raise IssueError("issue reporter binding is invalid")
        return active

    def _record(self, state: str, **details: Any) -> None:
        self._evidence.append(
            {
                "sequence": len(self._evidence) + 1,
                "run_id": self.run_id,
                "state": state,
                "recorded_at": float(self.clock()),
                **details,
            }
        )


def validate_issue_report_arguments(arguments: Any) -> dict[str, Any]:
    """Validate direct ``report_issue`` MCP arguments without model-side JSON wrappers."""

    if not isinstance(arguments, Mapping):
        raise IssueError("report_issue arguments are invalid")
    expected = {
        "category",
        "summary",
        "failing_operation",
        "error",
        "mutation_state",
        "requested_action",
    }
    if set(arguments) != expected:
        raise IssueError("report_issue arguments are not exact")
    result = dict(arguments)
    if result["category"] not in ISSUE_CATEGORIES:
        raise IssueError("issue category is invalid")
    for key in expected - {"category"}:
        _required_text(result[key], key)
    return result


__all__ = [
    "ISSUE_CATEGORIES",
    "ISSUE_CONTROL_ACTIONS",
    "ISSUE_RESOLUTION_TYPES",
    "ISSUE_STATES",
    "IssueControl",
    "IssueError",
    "IssueReport",
    "IssueResolution",
    "RecoverableIssueLedger",
    "validate_issue_report_arguments",
]
