"""A narrow, mechanically attributed broker for run-local Team Transport."""

from __future__ import annotations

import inspect
import json
import os
import socket
import threading
import time
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

# The Runtime stages this module as a standalone script next to its small
# dependency rather than exposing the repository package or PYTHONPATH.  Keep
# the package import for in-repository use, while making that isolated launch
# boundary explicit for `/usr/bin/python3 /agent/home/transport_mcp.py`.
if __package__:
    from .interventions import (
        IssueControl,
        IssueError,
        IssueResolution,
        REPAIR_COMPONENTS,
        RecoverableIssueLedger,
        normalize_issue_control_arguments,
        validate_issue_report_arguments,
    )
else:
    from interventions import (
        IssueControl,
        IssueError,
        IssueResolution,
        REPAIR_COMPONENTS,
        RecoverableIssueLedger,
        normalize_issue_control_arguments,
        validate_issue_report_arguments,
    )


_TERMINAL_ROLE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
# R3.0-016 protocol gate: the bare "retry" sentence hid why fresh evidence was
# required — every successful apply_atomic submit resets retrieval_state to
# query_required, so evidence gathered before the last write never counts.  The
# extension names the reset cause and both accepted exits while staying a fixed
# value-free literal within the 200-char broker relay bound.  Like the legacy
# sentence, it must stay free of regex metacharacters: suites interpolate it
# unescaped into anchored patterns.
TERMINAL_REPORT_GUARD_ERROR = (
    "Protocol retrieval evidence is incomplete: a stateful call reset it to query_required;"
    " before terminal report re-run query_semantic_context or pass verify_scoped_retrieval_fallback"
)
# Shared with the Runner and native transport relay: only fixed prerequisite
# messages may cross the Agent boundary, never internal exception payloads.
TERMINAL_REPORT_GUARD_REJECTIONS = {
    "issue_pending": "terminal result is blocked by an active issue; wait for its resolution and automatic resume",
    "cq_handoff_pending": "terminal result awaits CQ freeze and Host cq_handoff_complete; continue the existing CQ session",
    "acceptance_settlement_pending": "terminal result awaits Acceptance settlement; continue the existing acceptance handoff",
    "acceptance_checklist_missing": "terminal result requires joint-acceptance/joint-acceptance-checklist.json for full_joint",
    "acceptance_checklist_unparsable": "terminal result requires a readable joint acceptance checklist for full_joint; correct its JSON",
    "acceptance_checklist_schema_mismatch": "terminal result requires a valid joint acceptance checklist for full_joint; correct the reported fields",
    "terminal_guard_failed": "terminal result guard failed; preserve writes and report the runtime failure for diagnosis",
}
COORDINATION_OBSERVER_ERROR = "coordination evidence observer failed"
_MCP_TOOL_ERROR_CODE = -32000
_MCP_TOOL_ERROR_MESSAGE = "Team Transport request rejected"
# The broker socket is an internal transport whose ``{"error": ...}`` payload
# is the string form of a ``RoutingError``: a fixed, non-secret sentence naming
# the violated routing/argument rule (or the JSON-decode complaint, which
# carries no payload bytes).  Relaying it keeps the role able to diagnose its
# own call; a non-string payload or an implausibly long one still falls back to
# the generic sentence so no structured broker state is reflected to the Agent.
_BROKER_ERROR_MAX_CHARS = 200


def _broker_error_message(value: object) -> str:
    """Return the broker's own bounded rejection text, else the generic one."""

    if isinstance(value, str):
        text = value.strip()
        if text and len(text) <= _BROKER_ERROR_MAX_CHARS:
            return text
    return _MCP_TOOL_ERROR_MESSAGE


def _issue_control_field_error(
    kind: str,
    args: dict[str, object],
    required: set[str],
    allowed: set[str] | None = None,
) -> RoutingError:
    """Name the rejected issue_control fields instead of a bare "invalid".

    A bare sentence forced the Coordinator to re-derive which of its fields was
    rejected by trial and error.  Field names come from the fixed schema
    vocabulary only, so the rendered sentence stays value-free and short; the
    codex relay re-renders it from these same fixed names (see
    TERMINAL_REPLY_BINDING_PATTERNS-style relaying in runtimes/codex.py).
    """

    unexpected = sorted(set(args) - (required if allowed is None else allowed))
    missing = sorted(required - set(args))
    message = f"issue_control {kind} fields are invalid"
    parts = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if unexpected:
        parts.append("unexpected: " + ", ".join(unexpected))
    if parts:
        message += " (" + "; ".join(parts) + ")"
    return RoutingError(message)


def _call_terminal_report_guard(
    guard: Callable[..., object],
    agent_id: str,
    already_synchronized: bool,
    status: str,
) -> object:
    """Invoke a status-aware guard while preserving the legacy two-argument contract.

    A guard is a host callback, so an internal ``TypeError`` must remain a real
    guard failure rather than triggering a second invocation with a different
    argument shape.  Inspect the callable once to choose the compatible arity.
    """

    try:
        signature = inspect.signature(guard)
    except (TypeError, ValueError):
        # Some extension/builtin callables do not expose a signature.  Keep
        # their legacy two-argument contract rather than invoking an opaque
        # callback twice and risking duplicate side effects.
        return guard(agent_id, already_synchronized)
    try:
        signature.bind(agent_id, already_synchronized, status)
    except TypeError:
        try:
            signature.bind(agent_id, already_synchronized)
        except TypeError:
            raise
        return guard(agent_id, already_synchronized)
    return guard(agent_id, already_synchronized, status)


class RoutingError(ValueError):
    """A frozen-profile routing or reply-slot violation with a typed code.

    R2.3-009: ``code`` lets the capability-MCP boundary surface a readable,
    typed rejection to the responsible Agent instead of an opaque string.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Delivery:
    sequence: int
    sender_id: str
    recipient_id: str
    text: str
    timestamp: float
    delivery_id: str
    expects_reply: bool = False
    reply_to_delivery_id: str | None = None
    owner_answer_id: str | None = None
    release_id: str | None = None
    display_text: str | None = None
    body_ref: dict | None = None
    material_refs: tuple[dict, ...] = ()


@dataclass(frozen=True)
class TaskResult:
    agent_id: str
    status: str
    summary: str
    timestamp: float
    display_summary: str | None = None
    body_ref: dict | None = None
    material_refs: tuple[dict, ...] = ()


@dataclass(frozen=True)
class CoordinationMessage:
    sender_id: str
    recipient_id: str
    message_kind: str
    text: str
    timestamp: float
    message_id: str
    terminal: bool = False
    settles: bool = False
    phase_event: dict[str, object] | None = None
    display_text: str | None = None
    body_ref: dict | None = None
    material_refs: tuple[dict, ...] = ()


_COORDINATION_ROLE_KINDS: dict[str, tuple[str, str]] = {
    "modeling": ("ready_for_acceptance", "coordinator"),
    "protocol": ("silent_for_acceptance", "coordinator"),
    "coordinator": ("acceptance_start", "acceptance"),
    "acceptance": ("acceptance_verdict_route", "coordinator"),
}


class TeamTransportBroker:
    def __init__(
        self,
        root: Path,
        permissions: set[tuple[str, str]],
        terminal_dependencies: dict[str, set[str]] | None = None,
        modeling_agent_id: str | None = None,
        terminal_report_guard: Callable[..., object] | None = None,
        transport_event_observer: Callable[[dict[str, object]], None] | None = None,
        coordination_phase_callback: Callable[[str, str, str, str, int], object] | None = None,
        coordination_event_observer: Callable[[dict[str, object]], None] | None = None,
        coordinator_agent_id: str | None = None,
        issue_escalation_enabled: bool = False,
        issue_event_callback: Callable[[dict[str, object]], object] | None = None,
        pre_send_validator: Callable[[str, str, str, bool, str | None], object] | None = None,
        materials: object | None = None,
        terminal_commit: Callable[[str, str], None] | None = None,
    ):
        self.evidence_root = root
        requested_root = root
        # Linux Unix sockets have a short pathname limit. The run-local requested path is
        # retained as evidence; only the live private socket directory uses a hashed /tmp path.
        if len(str(root / "source-specialist.sock")) >= 100:
            root = Path("/tmp") / f"mt-{sha256(str(root).encode()).hexdigest()[:24]}"
        self.root, self.permissions = root, permissions
        self.terminal_dependencies = {
            agent_id: frozenset(dependencies)
            for agent_id, dependencies in (terminal_dependencies or {}).items()
        }
        self.modeling_agent_id = modeling_agent_id
        self.coordinator_agent_id = coordinator_agent_id
        self.issue_escalation_enabled = issue_escalation_enabled is True
        self.issue_event_callback = issue_event_callback
        self.pre_send_validator = pre_send_validator
        self.materials = materials
        self.terminal_commit = terminal_commit
        self._issue_lock = threading.Lock()
        self._issues: RecoverableIssueLedger | None = None
        if self.issue_escalation_enabled:
            if not isinstance(coordinator_agent_id, str) or not coordinator_agent_id:
                raise RoutingError("issue escalation requires a Coordinator identity")
            self._issues = RecoverableIssueLedger(
                run_id=self._infer_run_id(requested_root),
                coordinator_id=coordinator_agent_id,
            )
        self.terminal_report_guard = terminal_report_guard
        self.transport_event_observer = transport_event_observer
        self.coordination_phase_callback = coordination_phase_callback
        self.coordination_event_observer = coordination_event_observer
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._deliveries: list[Delivery] = []
        self._delivery_sequence = 0
        self._delivery_by_id: dict[str, Delivery] = {}
        self._pending_replies: dict[str, str | None] = {}
        self._reply_delivery_ids: dict[str, str] = {}
        # Formal R2.3-005 may reopen one invalid response binding without deleting
        # the immutable request/reply history.  The map records the exact invalid
        # reply that consumed the one replacement allowance for each request.
        self._formal_reply_reopens: dict[str, str] = {}
        self._owner_answer_by_question: dict[str, str] = {}
        self._owner_answer_by_release: dict[str, str] = {}
        self._owner_answer_ids: dict[str, str] = {}
        self._acknowledged_deliveries: set[str] = set()
        self._results: dict[str, TaskResult] = {}
        self._coordination: list[CoordinationMessage] = []
        self._coordination_sequence = 0
        self._coordination_failure: dict[str, object] | None = None
        self._terminal_handoff_acks: set[tuple[str, str]] = set()
        self._lock = threading.Lock()
        self._coordination_emit_lock = threading.Lock()
        self._servers: list[socket.socket] = []

    @staticmethod
    def _infer_run_id(root: Path) -> str:
        """Derive the run identity from the canonical run-local broker path."""
        # ``root`` is normally ``<run-root>/transport/broker``.  Keep the fallback
        # deterministic for focused Broker tests that use a temporary directory.
        parts = root.parts
        if "modeling-runs" in parts:
            index = parts.index("modeling-runs")
            if index + 1 < len(parts) and parts[index + 1]:
                return parts[index + 1]
        return f"transport-{sha256(str(root).encode()).hexdigest()[:24]}"

    def endpoint(self, agent_id: str) -> Path:
        return self.root / f"{agent_id}.sock"

    @property
    def issue_ledger(self) -> RecoverableIssueLedger | None:
        return self._issues

    def report_issue(
        self,
        reporter_id: str,
        *,
        category: str,
        summary: str,
        failing_operation: str,
        error: str,
        mutation_state: str,
        requested_action: str,
        thread_id: str | None = None,
        candidate_identity: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Create one non-terminal issue and enqueue it for Runner main-loop handling.

        The Broker callback is deliberately invoked after the ledger has released all
        state locks (the ledger itself is run-local and synchronous).  It may only enqueue
        work; Runtime delivery/evidence writes happen in ``TeamRunner.drain``.
        """
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        if not isinstance(reporter_id, str) or (
            reporter_id != self.coordinator_agent_id
            and (reporter_id, self.coordinator_agent_id) not in self.permissions
        ):
            # Coordinator is the fixed recipient even though the issue is not a normal
            # peer Delivery.  Require the Profile to contain the corresponding edge.
            raise RoutingError("issue reporter is not allowed by frozen Profile")
        try:
            arguments = validate_issue_report_arguments(
                {
                    "category": category,
                    "summary": summary,
                    "failing_operation": failing_operation,
                    "error": error,
                    "mutation_state": mutation_state,
                    "requested_action": requested_action,
                }
            )
            with self._issue_lock:
                report = self._issues.report(
                    reporter_id=reporter_id,
                    **arguments,
                    thread_id=thread_id,
                    candidate_identity=candidate_identity,
                )
        except IssueError as exc:
            raise RoutingError(str(exc)) from None
        payload = report.as_dict(state="reported")
        callback = self.issue_event_callback
        if callback is not None:
            try:
                callback({"kind": "issue_report", "issue": payload})
            except Exception as exc:
                # The issue remains in the immutable ledger; model-visible output is a
                # fixed transport error and the Runner can recover through evidence.
                raise RoutingError("issue callback enqueue failed") from exc
        return payload

    def issue_control(
        self,
        coordinator_id: str,
        *,
        issue_id: str,
        reporter_id: str,
        action: str,
        control_epoch: int,
        resolution: IssueResolution | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        """Queue one constrained Coordinator control for Runner main-loop dispatch."""
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        if coordinator_id != self.coordinator_agent_id:
            raise RoutingError("issue control is Coordinator-only")
        if reporter_id != coordinator_id and (coordinator_id, reporter_id) not in self.permissions:
            raise RoutingError("issue control reporter is not allowed by frozen Profile")
        try:
            with self._issue_lock:
                control = self._issues.control(
                    issue_id=issue_id,
                    coordinator_id=coordinator_id,
                    reporter_id=reporter_id,
                    action=action,
                    control_epoch=control_epoch,
                    resolution=resolution,
                    reason=reason,
                )
        except IssueError as exc:
            raise RoutingError(str(exc)) from None
        payload = {"kind": "issue_control", "control": control.as_dict()}
        callback = self.issue_event_callback
        if callback is not None:
            try:
                callback(payload)
            except Exception as exc:
                raise RoutingError("issue callback enqueue failed") from exc
        return control.as_dict()

    def persist_issue_resolution(self, resolution: IssueResolution) -> dict[str, object]:
        """Persist a Runner-owned outer resolution before Coordinator delivery."""
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        try:
            with self._issue_lock:
                value = self._issues.persist_resolution(resolution)
        except IssueError as exc:
            raise RoutingError(str(exc), code="issue-resolution-rejected") from None
        return value.as_dict()

    def bind_issue_context(
        self,
        *,
        issue_id: str,
        reporter_id: str,
        thread_id: str | None,
        candidate_identity: dict[str, object] | None,
    ) -> dict[str, object]:
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        try:
            with self._issue_lock:
                report = self._issues.bind_context(
                    issue_id=issue_id,
                    reporter_id=reporter_id,
                    thread_id=thread_id,
                    candidate_identity=candidate_identity,
                )
        except IssueError as exc:
            raise RoutingError(str(exc)) from None
        return report.as_dict(state="reported")

    def mark_issue_dispatch(self, control: IssueControl) -> None:
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        try:
            with self._issue_lock:
                self._issues.mark_dispatch(control)
        except IssueError as exc:
            raise RoutingError(str(exc)) from None

    def fail_issue_rebind(self, *, issue_id: str, reporter_id: str, reason: str) -> None:
        if not self.issue_escalation_enabled or self._issues is None:
            raise RoutingError("issue escalation capability is unavailable")
        try:
            with self._issue_lock:
                self._issues.fail_rebind(issue_id=issue_id, reporter_id=reporter_id, reason=reason)
        except IssueError as exc:
            raise RoutingError(str(exc)) from None

    def start(self, agent_ids: list[str]) -> None:
        """Publish one Unix endpoint per Agent; endpoint identity is the sender identity."""
        for agent_id in agent_ids:
            endpoint = self.endpoint(agent_id)
            endpoint.unlink(missing_ok=True)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(endpoint))
            os.chmod(endpoint, 0o600)
            server.listen()
            self._servers.append(server)
            threading.Thread(
                target=self._serve, args=(server, agent_id), daemon=True
            ).start()

    def _serve(self, server: socket.socket, agent_id: str) -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                try:
                    request = json.loads(
                        connection.makefile("r", encoding="utf-8").readline()
                    )
                    response = mcp_response(request, broker=self, agent_id=agent_id)
                except (json.JSONDecodeError, RoutingError) as exc:
                    response = {"error": str(exc)}
                connection.sendall(
                    (json.dumps(response, ensure_ascii=False) + "\n").encode()
                )

    def stop(self) -> None:
        for server in self._servers:
            server.close()
        self._servers.clear()
        if self.root.exists():
            for endpoint in self.root.glob("*.sock"):
                endpoint.unlink(missing_ok=True)
            self.root.rmdir()

    def normalize_materials(self, actor_id, recipient_id, text, body_ref=None, material_refs=None):
        from .handoff_materials import MaterialError
        refs = material_refs if material_refs is not None else []
        if not isinstance(refs, list):
            raise RoutingError("material_path_invalid: material_refs must be a list")
        if body_ref is None and not refs:
            return text, None, ()
        if self.materials is None:
            raise RoutingError("material_forbidden: material capability is unavailable")
        try:
            for ref in refs + ([body_ref] if body_ref is not None else []):
                self.materials.authorize_ref(actor_id, recipient_id, ref)
            normalized = self.materials.resolve(actor_id, body_ref) if body_ref is not None else text
        except MaterialError as exc:
            raise RoutingError(str(exc), code=exc.code) from None
        display = text or "Read the referenced material through read_handoff_material."
        return normalized, display, tuple(refs)

    def send(
        self,
        sender_id: str,
        recipient_id: str,
        text: str,
        expects_reply: bool = False,
        reply_to_delivery_id: str | None = None,
        *, body_ref: dict | None = None, material_refs: list[dict] | None = None,
    ) -> Delivery:
        if (
            not isinstance(text, str)
            or (sender_id, recipient_id) not in self.permissions
            or not isinstance(expects_reply, bool)
            or (reply_to_delivery_id is not None and not isinstance(reply_to_delivery_id, str))
        ):
            raise RoutingError(
                "recipient is not allowed by frozen Profile",
                code="recipient-not-allowed",
            )
        text, display_text, refs = self.normalize_materials(
            sender_id, recipient_id, text, body_ref, material_refs
        )
        if self.pre_send_validator is not None:
            self.pre_send_validator(
                sender_id,
                recipient_id,
                text,
                expects_reply,
                reply_to_delivery_id,
            )
        with self._lock:
            if self.terminal_commit is not None and recipient_id in self._results:
                raise RoutingError("recipient already accepted terminal result; retain late input for Host review",
                                   code="recipient-terminal")
            if reply_to_delivery_id is not None:
                original = self._delivery_by_id.get(reply_to_delivery_id)
                if (
                    not original
                    or original.sender_id != recipient_id
                    or original.recipient_id != sender_id
                    or not original.expects_reply
                    or reply_to_delivery_id not in self._pending_replies
                    or self._pending_replies[reply_to_delivery_id] is not None
                ):
                    raise RoutingError(
                        "Team Transport reply is not an active reversed request",
                        code="reply-slot-not-active",
                    )
            self._delivery_sequence += 1
            delivery = Delivery(
                self._delivery_sequence,
                sender_id,
                recipient_id,
                text,
                time.time(),
                f"delivery-{self._delivery_sequence}",
                expects_reply,
                reply_to_delivery_id,
                display_text=display_text, body_ref=body_ref, material_refs=refs,
            )
            self._deliveries.append(delivery)
            self._delivery_by_id[delivery.delivery_id] = delivery
            if expects_reply:
                self._pending_replies[delivery.delivery_id] = None
            if reply_to_delivery_id is not None:
                self._pending_replies[reply_to_delivery_id] = delivery.delivery_id
                self._reply_delivery_ids[delivery.delivery_id] = reply_to_delivery_id
            return delivery

    def publish_owner_answer(
        self,
        *,
        question_delivery_id: str,
        owner_answer_id: str,
        release_id: str,
        text: str,
        display_text: str | None = None, body_ref: dict | None = None,
        material_refs: tuple[dict, ...] = (),
    ) -> Delivery:
        """Queue one Runner-owned answer for the Modeling question that spawned it.

        This is intentionally narrower than ``send``.  The original request must be an
        acknowledged Modeling-to-Coordinator request with an active, unanswered reply slot.
        The special sender is created only after the Runner has persisted its immutable
        outer-user record; ordinary Team Transport callers cannot invoke this path through MCP.
        """
        if any(
            not isinstance(value, str) or not value
            for value in (question_delivery_id, owner_answer_id, release_id, text)
        ):
            raise RoutingError("owner answer delivery is invalid")
        with self._lock:
            original = self._delivery_by_id.get(question_delivery_id)
            if (
                original is None
                or self.modeling_agent_id is None
                or original.sender_id != self.modeling_agent_id
                or self.coordinator_agent_id is None
                or original.recipient_id != self.coordinator_agent_id
                or not original.expects_reply
                or original.reply_to_delivery_id is not None
                or question_delivery_id not in self._acknowledged_deliveries
                or self._pending_replies.get(question_delivery_id) is not None
                or question_delivery_id not in self._pending_replies
                or question_delivery_id in self._owner_answer_by_question
            ):
                raise RoutingError(
                    "owner answer request is not an active acknowledged Modeling question"
                )
            if (
                release_id in self._delivery_by_id
                or release_id in self._owner_answer_by_release
                or release_id in self._owner_answer_ids
                or owner_answer_id in self._delivery_by_id
                or owner_answer_id in self._owner_answer_by_release
                or owner_answer_id in self._owner_answer_ids
            ):
                raise RoutingError("owner answer delivery ID collision")
            self._delivery_sequence += 1
            delivery = Delivery(
                self._delivery_sequence,
                "user/outer",
                original.sender_id,
                text,
                time.time(),
                release_id,
                False,
                question_delivery_id,
                owner_answer_id,
                release_id,
                display_text=display_text, body_ref=body_ref, material_refs=material_refs,
            )
            self._deliveries.append(delivery)
            self._delivery_by_id[release_id] = delivery
            self._pending_replies[question_delivery_id] = release_id
            self._reply_delivery_ids[release_id] = question_delivery_id
            self._owner_answer_by_question[question_delivery_id] = release_id
            self._owner_answer_by_release[release_id] = question_delivery_id
            self._owner_answer_ids[owner_answer_id] = release_id
            return delivery

    def reopen_formal_reply_slot(
        self,
        *,
        original_delivery_id: str,
        invalid_reply_delivery_id: str,
        modeling_agent_id: str,
        protocol_agent_id: str,
        formal_candidate: bool = False,
    ) -> None:
        """Atomically restore one formal candidate reply slot after an invalid response.

        This is a Runner-owned, formal-only escape hatch.  It never removes either
        delivery from immutable history; it only restores the original request's
        pending value to ``None`` so exactly one later reversed reply can be queued.
        """

        if (
            formal_candidate is not True
            or not all(
                isinstance(value, str) and value
                for value in (
                    original_delivery_id,
                    invalid_reply_delivery_id,
                    modeling_agent_id,
                    protocol_agent_id,
                )
            )
        ):
            raise RoutingError(
                "formal reply slot reopen is not authorized",
                code="formal-reply-slot-reopen-rejected",
            )
        with self._lock:
            original = self._delivery_by_id.get(original_delivery_id)
            invalid = self._delivery_by_id.get(invalid_reply_delivery_id)
            if (
                original is None
                or invalid is None
                or original.sender_id != modeling_agent_id
                or original.recipient_id != protocol_agent_id
                or not original.expects_reply
                or original.reply_to_delivery_id is not None
                or invalid.sender_id != protocol_agent_id
                or invalid.recipient_id != modeling_agent_id
                or invalid.reply_to_delivery_id != original_delivery_id
                or invalid_reply_delivery_id not in self._reply_delivery_ids
                or self._reply_delivery_ids[invalid_reply_delivery_id] != original_delivery_id
            ):
                raise RoutingError(
                    "formal reply slot reopen binding is invalid",
                    code="formal-reply-slot-reopen-rejected",
                )
            if original_delivery_id in self._formal_reply_reopens:
                raise RoutingError(
                    "formal reply slot reopen was already consumed",
                    code="formal-reply-slot-reopen-rejected",
                )

            pending_marker = object()
            current = self._pending_replies.get(original_delivery_id, pending_marker)
            occupied = current == invalid_reply_delivery_id
            acknowledged = (
                current is pending_marker
                and invalid_reply_delivery_id in self._acknowledged_deliveries
            )
            if not (occupied or acknowledged):
                raise RoutingError(
                    "formal reply slot is not occupied by the exact invalid reply",
                    code="formal-reply-slot-reopen-rejected",
                )

            self._formal_reply_reopens[original_delivery_id] = invalid_reply_delivery_id
            # ``None`` is the broker's active-but-unanswered marker.  A later
            # reversed send is therefore accepted exactly once; duplicate sends
            # remain rejected after that replacement occupies the slot.
            self._pending_replies[original_delivery_id] = None

    def send_coordination(
        self,
        sender_id: str,
        recipient_id: str,
        message_kind: str,
        text: str = "",
        generation: int | None = None,
        *, body_ref: dict | None = None, material_refs: list[dict] | None = None,
    ) -> CoordinationMessage:
        """Record a non-terminal phase message outside TaskResult settlement.

        ``ready_for_acceptance`` and ``silent_for_acceptance`` are intentionally
        ordinary coordination state.  They never enter ``results`` and cannot
        satisfy terminal dependencies.  The Coordinator can also emit the
        ``acceptance_start`` event after both acknowledgements are present.
        """
        allowed_kinds = {kind for kind, _ in _COORDINATION_ROLE_KINDS.values()}
        if (
            message_kind not in allowed_kinds
            or not isinstance(text, str)
            or not isinstance(sender_id, str)
            or not isinstance(recipient_id, str)
            or (sender_id, recipient_id) not in self.permissions
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation <= 0
        ):
            raise RoutingError("coordination message is not allowed by frozen Profile")
        role_kind = _COORDINATION_ROLE_KINDS.get(sender_id)
        if role_kind != (message_kind, recipient_id):
            raise RoutingError("coordination role/kind/recipient is not allowed")
        text, display_text, refs = self.normalize_materials(
            sender_id, recipient_id, text, body_ref, material_refs
        )
        phase_event: dict[str, object] | None = None
        with self._coordination_emit_lock:
            with self._lock:
                if self._coordination_failure is not None:
                    raise RoutingError(COORDINATION_OBSERVER_ERROR)
                if self.coordination_phase_callback is not None:
                    try:
                        observed = self.coordination_phase_callback(
                            sender_id,
                            recipient_id,
                            message_kind,
                            text,
                            generation,
                        )
                    except Exception as exc:
                        raise RoutingError("coordination phase rejected") from exc
                    if observed is not None and not isinstance(observed, dict):
                        raise RoutingError("coordination phase callback returned invalid evidence")
                    phase_event = observed
                self._coordination_sequence += 1
                message = CoordinationMessage(
                    sender_id,
                    recipient_id,
                    message_kind,
                    text,
                    time.time(),
                    f"coordination-{self._coordination_sequence}",
                    phase_event=phase_event,
                    display_text=display_text, body_ref=body_ref, material_refs=refs,
                )
                self._coordination.append(message)
            if self.coordination_event_observer is not None:
                try:
                    self.coordination_event_observer(message.__dict__.copy())
                except Exception:
                    # The phase callback has already advanced its in-memory state, so
                    # a failed authoritative evidence write must permanently poison
                    # this broker.  The fixed metadata below is the only failure
                    # surface; the observer's exception text is never model-visible.
                    failure = {
                        "status": "fatal",
                        "code": "coordination_evidence_observer_failed",
                        "message": COORDINATION_OBSERVER_ERROR,
                        "sender_id": message.sender_id,
                        "recipient_id": message.recipient_id,
                        "message_kind": message.message_kind,
                        "message_id": message.message_id,
                        "generation": (
                            message.phase_event.get("generation")
                            if isinstance(message.phase_event, dict)
                            else None
                        ),
                    }
                    with self._lock:
                        self._coordination_failure = failure
                        if isinstance(message.phase_event, dict):
                            message.phase_event.update(
                                {
                                    "fatal": True,
                                    "failure_code": failure["code"],
                                }
                            )
                    raise RoutingError(COORDINATION_OBSERVER_ERROR) from None
            return message

    @property
    def coordination_failure(self) -> dict[str, object] | None:
        with self._lock:
            return dict(self._coordination_failure) if self._coordination_failure else None

    def drain_coordination(self) -> list[CoordinationMessage]:
        """Claim non-terminal coordination state without touching TaskResult state."""
        with self._lock:
            values, self._coordination = self._coordination[:], []
            return values

    def ack_delivery(self, delivery_id: str) -> None:
        with self._lock:
            if (
                not isinstance(delivery_id, str)
                or delivery_id not in self._delivery_by_id
                or delivery_id in self._acknowledged_deliveries
            ):
                raise RoutingError("Team Transport delivery acknowledgement is invalid")
            self._acknowledged_deliveries.add(delivery_id)
            request_id = self._reply_delivery_ids.get(delivery_id)
            if request_id is not None:
                reopened_reply = self._formal_reply_reopens.get(request_id)
                if reopened_reply == delivery_id:
                    current = self._pending_replies.get(request_id)
                    # A formal reopen may happen while the invalid delivery is
                    # occupied, before its normal acknowledgement.  Do not let
                    # that acknowledgement close or invalidate the restored slot.
                    if current != delivery_id:
                        return
                    del self._pending_replies[request_id]
                    return
                if self._pending_replies.get(request_id) != delivery_id:
                    raise RoutingError("Team Transport reply acknowledgement is invalid")
                del self._pending_replies[request_id]

    def requeue(self, deliveries: list[Delivery]) -> None:
        """Return claimed deliveries to the FIFO queue without changing history.

        Cooperative issue pause uses this only for deliveries already claimed by the
        Runner's main loop.  No acknowledgement/reply state is mutated, so the same
        immutable delivery can be processed once after resume.
        """
        if not isinstance(deliveries, list):
            raise RoutingError("Team Transport requeue payload is invalid")
        with self._lock:
            by_id = {delivery.delivery_id: delivery for delivery in deliveries}
            if len(by_id) != len(deliveries) or any(
                delivery_id not in self._delivery_by_id for delivery_id in by_id
            ):
                raise RoutingError("Team Transport requeue delivery is unknown")
            queued_ids = {delivery.delivery_id for delivery in self._deliveries}
            if queued_ids.intersection(by_id):
                raise RoutingError("Team Transport requeue delivery is duplicated")
            self._deliveries = sorted(
                [*self._deliveries, *deliveries], key=lambda item: item.sequence
            )

    def ack_terminal_handoff(self, recipient_id: str, source_id: str) -> None:
        with self._lock:
            pair = (recipient_id, source_id)
            if (
                pair in self._terminal_handoff_acks
                or source_id not in self._results
                or source_id not in self.terminal_dependencies.get(recipient_id, frozenset())
            ):
                raise RoutingError("terminal handoff acknowledgement is invalid")
            self._terminal_handoff_acks.add(pair)

    def report(
        self,
        agent_id: str,
        status: str,
        summary: str,
        *,
        already_synchronized: bool = False,
        body_ref: dict | None = None, material_refs: list[dict] | None = None,
    ) -> TaskResult:
        summary, display, refs = self.normalize_materials(
            agent_id, "runner", summary, body_ref, material_refs
        )
        if self.terminal_report_guard is not None:
            try:
                allowed = _call_terminal_report_guard(
                    self.terminal_report_guard,
                    agent_id,
                    already_synchronized,
                    status,
                )
            except RoutingError:
                raise
            except Exception:
                raise RoutingError(
                    TERMINAL_REPORT_GUARD_REJECTIONS["terminal_guard_failed"],
                    code="terminal_guard_failed",
                ) from None
            if allowed is not False:
                raise RoutingError(TERMINAL_REPORT_GUARD_ERROR)
        if status not in {"completed", "blocked"} or not isinstance(summary, str):
            raise RoutingError("terminal result is invalid")
        with self._lock:
            if self._issues is not None and self._issues.pending:
                raise RoutingError("terminal result is blocked by an active issue")
            if agent_id in self._results:
                raise RoutingError("Agent already reported a terminal result")
            missing = sorted(
                dependency
                for dependency in self.terminal_dependencies.get(agent_id, frozenset())
                if dependency not in self._results or (agent_id, dependency) not in self._terminal_handoff_acks
            )
            # R2.3-009 follow-up (user 2026-08-20): a role self-declares that
            # its task is complete or definitively stuck.  ``blocked`` therefore
            # never requires upstream terminal handoffs -- start3 died precisely
            # because Protocol could not report blocked while the acceptance
            # handoff was blocked by the retrieval gate.  ``completed`` still
            # requires them: a role whose inputs never arrived cannot have
            # completed its task.
            if missing and status == "completed":
                if not all(isinstance(role, str) and _TERMINAL_ROLE_ID.fullmatch(role) for role in missing):
                    raise RoutingError("terminal result dependencies are invalid")
                raise RoutingError("terminal result requires terminal handoffs: " + ", ".join(missing))
            if self.terminal_commit is not None:
                if status == "completed" and any(item.recipient_id == agent_id for item in self._deliveries):
                    raise RoutingError("pending broker input; receive required handoffs before reporting")
                # The Adapter atomically checks native dispatch state and closes new
                # dispatch admission. Reporting within the active claimed turn is valid.
                self.terminal_commit(agent_id, status)
            result = TaskResult(agent_id, status, summary, time.time(), display, body_ref, refs)
            self._results[agent_id] = result
            return result

    def drain(self) -> list[Delivery]:
        with self._lock:
            values, self._deliveries = self._deliveries[:], []
            return values

    def drain_for(
        self,
        *,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        delivery_id: str | None = None,
    ) -> list[Delivery]:
        """Claim only the queued deliveries owned by one transport consumer.

        The ordinary ``drain`` operation remains the FIFO Runner operation.  A producer that
        injects a delivery directly into the real Runtime must instead claim that exact delivery
        (or select its reply direction) so it cannot mistake its own outbound request for an
        Agent reply.  Unmatched deliveries remain queued and retain their original order.
        """
        if (
            sender_id is None
            and recipient_id is None
            and delivery_id is None
        ):
            raise RoutingError("targeted Team Transport drain requires a selector")
        with self._lock:
            selected: list[Delivery] = []
            remaining: list[Delivery] = []
            for delivery in self._deliveries:
                matches = (
                    (sender_id is None or delivery.sender_id == sender_id)
                    and (recipient_id is None or delivery.recipient_id == recipient_id)
                    and (delivery_id is None or delivery.delivery_id == delivery_id)
                )
                if matches:
                    selected.append(delivery)
                else:
                    remaining.append(delivery)
            self._deliveries = remaining
            return selected

    @property
    def results(self) -> dict[str, TaskResult]:
        return dict(self._results)


def _delivery_payload(delivery: Delivery) -> dict[str, object]:
    payload: dict[str, object] = {
        "sequence": delivery.sequence,
        "sender_id": delivery.sender_id,
        "recipient_id": delivery.recipient_id,
        "text": delivery.display_text if delivery.display_text is not None else delivery.text,
        "timestamp": delivery.timestamp,
        "delivery_id": delivery.delivery_id,
        "expects_reply": delivery.expects_reply,
        "reply_to_delivery_id": delivery.reply_to_delivery_id,
    }
    if delivery.body_ref is not None or delivery.material_refs:
        payload.update(body_ref=delivery.body_ref, material_refs=list(delivery.material_refs))
    if delivery.owner_answer_id is not None:
        payload["owner_answer_id"] = delivery.owner_answer_id
    if delivery.release_id is not None:
        payload["release_id"] = delivery.release_id
    return payload


def report_rejection_category(message: str) -> str:
    """Map one sanitized rejection message to the event vocabulary.

    Shared by the Broker's own observer and by a Runtime that records the same
    refusal, so one refusal is one category in every evidence stream.
    """

    if message.startswith("terminal result requires terminal handoffs: "):
        missing = message.rsplit(": ", 1)[-1].split(", ")
        if "modeling" in missing:
            return "missing_modeling_handoff"
    if message.startswith("terminal result requires delivered reply"):
        return TERMINAL_REPLY_UNDELIVERED
    if message.startswith("completed terminal result requires an explicit revision response"):
        return TERMINAL_REVISION_PENDING
    if message.startswith("completed terminal result requires an established reply request"):
        return TERMINAL_REPLY_REQUEST_MISSING
    return "broker_rejection"


def _report_rejection_category(error: RoutingError) -> str:
    """Map a Broker rejection to the small, non-sensitive event vocabulary."""
    return report_rejection_category(str(error))


# --- locatable terminal reply-binding refusals (R3.0-015 issue-4) --------------
#
# The incident's first failure was the bare ``terminal result requires
# delivered reply``: no request identity, no peer, no legal exit, so neither the
# reporter nor the host could tell which delivery was outstanding or that
# ``blocked`` was still available.  The guard is unchanged; only its refusal is
# now typed, locatable and re-renderable from validated tokens (a Runtime that
# reflects broker errors to an Agent never returns broker-controlled text).

TERMINAL_REPLY_UNDELIVERED = "terminal_reply_undelivered"
TERMINAL_REVISION_PENDING = "terminal_revision_pending"
TERMINAL_REPLY_REQUEST_MISSING = "terminal_reply_request_missing"

_REPLY_PEER_FRAGMENT = r"(?P<peer>[A-Za-z0-9][A-Za-z0-9._:-]{0,127})"
_DELIVERY_ID_FRAGMENT = r"(?P<delivery_id>delivery-[0-9]{1,9})"
TERMINAL_REPLY_BINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        TERMINAL_REPLY_UNDELIVERED,
        re.compile(
            "^terminal result requires delivered reply: the reply to "
            + _REPLY_PEER_FRAGMENT
            + " for delivery_id="
            + _DELIVERY_ID_FRAGMENT
            + " is still undelivered; obtain it, or report blocked$"
        ),
    ),
    (
        TERMINAL_REVISION_PENDING,
        re.compile(
            "^completed terminal result requires an explicit revision response: the reply to "
            + _REPLY_PEER_FRAGMENT
            + " for delivery_id="
            + _DELIVERY_ID_FRAGMENT
            + " is still owed; answer it, or report blocked$"
        ),
    ),
)


def terminal_reply_binding_error(gate: str, delivery_id: str, peer_id: str) -> str:
    """Render one locatable reply-binding refusal from validated tokens."""

    if gate == TERMINAL_REPLY_UNDELIVERED:
        return (
            "terminal result requires delivered reply: the reply to "
            f"{peer_id} for delivery_id={delivery_id} is still undelivered; "
            "obtain it, or report blocked"
        )
    if gate == TERMINAL_REVISION_PENDING:
        return (
            "completed terminal result requires an explicit revision response: the reply to "
            f"{peer_id} for delivery_id={delivery_id} is still owed; "
            "answer it, or report blocked"
        )
    raise RoutingError("unsupported terminal reply binding gate")


# --- locatable issue_control refusals (R3.0-016 #20 family) -------------------
#
# issue_control refusals now name the rejected arguments and, on a resume/abort
# equality replay mismatch, the first differing resolution field summarized as
# a character length plus a 10-hex sha256 prefix — never the offending text.  A
# Runtime that relays broker errors re-renders these sentences from validated
# tokens (field-name charset, digest shape) and never returns the received
# bytes, mirroring the reply-binding relaying above.

_ISSUE_FIELD_NAME = r"[a-z_][a-z0-9_]{0,63}"
_ISSUE_FIELD_LIST = rf"{_ISSUE_FIELD_NAME}(?:, {_ISSUE_FIELD_NAME})*"
_ISSUE_FIELD_CLAUSES = (
    rf"(?:(?:missing: (?P<missing_names>{_ISSUE_FIELD_LIST})"
    rf"(?:; unexpected: (?P<unexpected_names>{_ISSUE_FIELD_LIST}))?)"
    rf"|(?:unexpected: (?P<unexpected_only>{_ISSUE_FIELD_LIST})))?"
)
_ISSUE_DIGEST_SUMMARY = r"(?:[0-9]{1,5}ch )?sha256:[0-9a-f]{10}"
_ISSUE_MISMATCH_TAIL = (
    rf": differing (?P<field>{_ISSUE_FIELD_NAME}) "
    rf"\(persisted (?P<persisted>{_ISSUE_DIGEST_SUMMARY}), "
    rf"provided (?P<provided>{_ISSUE_DIGEST_SUMMARY})\)"
    r"(?: \(\+(?P<extra>[0-9]{1,2}) more field\(s\) differ\))?"
)


def _issue_control_field_pattern(prefix: str, joiner: str, suffix: str) -> tuple[re.Pattern[str], str, str, str]:
    return (
        re.compile(
            "^" + re.escape(prefix) + re.escape(joiner) + _ISSUE_FIELD_CLAUSES + re.escape(suffix) + "$"
        ),
        prefix,
        joiner,
        suffix,
    )


# (pattern, prefix, joiner, suffix): re-rendering is prefix + clauses + suffix.
_ISSUE_CONTROL_FIELD_COMPILED: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    _issue_control_field_pattern("issue_control arguments are invalid", ": ", ""),
    _issue_control_field_pattern("issue_control resolution fields are invalid", " (", ")"),
    _issue_control_field_pattern("issue_control repair fields are invalid", " (", ")"),
    _issue_control_field_pattern("issue_control pause fields are invalid", " (", ")"),
    _issue_control_field_pattern("issue_control abort fields are invalid", " (", ")"),
)
_ISSUE_CONTROL_MISMATCH_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile("^" + re.escape(prefix) + _ISSUE_MISMATCH_TAIL + "$"), prefix)
    for prefix in (
        "issue resume resolution does not match persisted resolution",
        "issue abort reason does not match persisted resolution",
    )
)


def _issue_field_names(raw: str | None) -> list[str]:
    """Validated, canonically ordered field names ([] when the clause is absent)."""

    if not raw:
        return []
    names = [name.strip() for name in raw.split(",")]
    if any(re.fullmatch(_ISSUE_FIELD_NAME, name) is None for name in names):
        return []
    return sorted(names)


def issue_control_transport_error(value: object) -> str | None:
    """Re-render one locatable issue_control refusal from validated tokens."""

    if not isinstance(value, str) or len(value) > 200:
        return None
    for pattern, prefix, joiner, suffix in _ISSUE_CONTROL_FIELD_COMPILED:
        match = pattern.fullmatch(value)
        if match is None:
            continue
        missing = _issue_field_names(match.group("missing_names"))
        unexpected = _issue_field_names(
            match.group("unexpected_names") or match.group("unexpected_only")
        )
        clauses = []
        if missing:
            clauses.append("missing: " + ", ".join(missing))
        if unexpected:
            clauses.append("unexpected: " + ", ".join(unexpected))
        if not clauses:
            return prefix
        return prefix + joiner + "; ".join(clauses) + suffix
    for pattern, prefix in _ISSUE_CONTROL_MISMATCH_COMPILED:
        match = pattern.fullmatch(value)
        if match is None:
            continue
        rendered = (
            f"{prefix}: differing {match.group('field')} "
            f"(persisted {match.group('persisted')}, provided {match.group('provided')})"
        )
        extra = match.group("extra")
        if extra:
            rendered += f" (+{int(extra)} more field(s) differ)"
        return rendered
    return None


def _observe_report_event(
    broker: TeamTransportBroker,
    agent_id: str,
    *,
    status: str,
    category: str,
    already_synchronized: bool,
) -> None:
    """Notify the host with only the fixed, sanitized terminal-report metadata."""
    observer = broker.transport_event_observer
    # Dynamic App Server callbacks already append this exact event through the Adapter.  The
    # private marker is intentionally accepted only at the top-level request, after the exact
    # MCP argument check, so ordinary stdio requests cannot opt out of host observation.
    if observer is None or already_synchronized:
        return
    if not isinstance(agent_id, str) or not _TERMINAL_ROLE_ID.fullmatch(agent_id):
        return
    event = {
        "agent": agent_id,
        "tool": "report_task_result",
        "status": status,
        "category": category,
        "ack": "not_applicable",
        "recorded_at_ns": time.time_ns(),
    }
    try:
        observer(event)
    except Exception:
        # Evidence is best-effort and must never change the Broker's transport contract.
        return


def mcp_response(
    request: dict[str, object], *, broker: TeamTransportBroker, agent_id: str
) -> dict[str, object]:
    """Small stdio-MCP-compatible handler used by an Agent-private transport process."""
    method, params = request.get("method"), request.get("params", {})
    from .handoff_materials import HANDOFF_TOOL_NAMES, HANDOFF_TOOL_SPECS, MaterialError, REF_SCHEMA
    if method == "tools/list":
        tools = [
                {
                    "name": "send_team_message",
                    "description": "Deliver exact text to one Profile-authorized teammate.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "recipient_id": {"type": "string"},
                            "text": {"type": "string"},
                            "expects_reply": {"type": "boolean"},
                            "reply_to_delivery_id": {"type": ["string", "null"]},
                        },
                        "required": ["recipient_id", "text"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "report_task_result",
                    "description": "Report this Agent's single terminal result to the Team Runner.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["completed", "blocked"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["status", "summary"],
                        "additionalProperties": False,
                    },
                },
            ]
        if broker.coordination_phase_callback is not None and agent_id in _COORDINATION_ROLE_KINDS:
            message_kind, recipient_id = _COORDINATION_ROLE_KINDS[agent_id]
            tools.append(
                {
                    "name": "send_coordination",
                    "description": "Submit this role's fixed coordination phase signal.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "recipient_id": {"type": "string", "enum": [recipient_id]},
                            "message_kind": {"type": "string", "enum": [message_kind]},
                            "text": {"type": "string"},
                            "generation": {"type": "integer", "minimum": 1},
                        },
                        "required": ["recipient_id", "message_kind", "text", "generation"],
                        "additionalProperties": False,
                    },
                }
            )
        if broker.issue_escalation_enabled:
            tools.append(
                {
                    "name": "report_issue",
                    "description": (
                        "Report one non-terminal typed issue to the Coordinator. "
                        "If you are the Coordinator reporter, immediately call the "
                        "bound issue_control pause. Do not include credentials or "
                        "platform write instructions."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": sorted(
                                    (
                                        "business_clarification",
                                        "protocol_guidance",
                                        "platform_repair",
                                        "runtime_recovery",
                                    )
                                ),
                            },
                            "summary": {"type": "string"},
                            "failing_operation": {"type": "string"},
                            "error": {"type": "string"},
                            "mutation_state": {"type": "string"},
                            "requested_action": {"type": "string"},
                        },
                        "required": [
                            "category",
                            "summary",
                            "failing_operation",
                            "error",
                            "mutation_state",
                            "requested_action",
                        ],
                        "additionalProperties": False,
                    },
                }
            )
            if agent_id == broker.coordinator_agent_id:
                issue_control_common_properties = {
                    "issue_id": {"type": "string"},
                    "reporter_id": {"type": "string"},
                    "control_epoch": {"type": "integer", "minimum": 1},
                }
                tools.append(
                    {
                        "name": "issue_control",
                        "description": (
                            "Coordinator-only cooperative pause/resume/abort control. "
                            "Flat fields: action=pause needs issue_id/reporter_id/control_epoch; "
                            "action=abort additionally needs a persisted-resolution reason; "
                            "action=resume additionally needs the persisted resolution fields "
                            "(guidance: resolution_type=guidance + resolution_text; "
                            "repair_completed: repair_component is required; resolution_text, "
                            "digests, verification_reference and mutation_reconciliation are "
                            "optional for confirmed no-write repairs and remain accepted in the "
                            "legacy five-field form."
                        ),
                        # 2026-09-11 auth006-start9: the previous oneOf form made
                        # the model emit empty tool-call arguments, so the pause
                        # dispatch never reached transport and the cooperative
                        # flow wedged at state `reported`.  The server-side
                        # normalize/validate already enforces every
                        # action-specific rule, so a flat schema keeps the same
                        # mechanical contract without the serialization hazard.
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                **issue_control_common_properties,
                                "action": {
                                    "type": "string",
                                    "enum": ["pause", "resume", "abort"],
                                },
                                "reason": {"type": "string", "minLength": 1},
                                "resolution_type": {
                                    "type": "string",
                                    "enum": ["guidance", "repair_completed"],
                                },
                                "resolution_text": {"type": "string", "minLength": 1},
                                "repair_component": {
                                    "type": "string",
                                    "enum": sorted(REPAIR_COMPONENTS),
                                },
                                "before_digest": {"type": "string", "minLength": 1},
                                "after_digest": {"type": "string", "minLength": 1},
                                "verification_reference": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "mutation_reconciliation": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                            "required": [
                                "issue_id",
                                "reporter_id",
                                "action",
                                "control_epoch",
                            ],
                            "additionalProperties": False,
                        },
                    }
                )
        for spec in tools:
            if broker.materials is not None and spec["name"] in {"send_team_message", "send_coordination", "report_task_result"}:
                spec["inputSchema"]["properties"].update(
                    material_refs={"type": "array", "items": REF_SCHEMA})
                spec["inputSchema"]["properties"][
                    "summary_ref" if spec["name"] == "report_task_result" else "body_ref"
                ] = REF_SCHEMA
                required = spec["inputSchema"]["required"]
                required.remove("summary" if spec["name"] == "report_task_result" else "text")
        if broker.materials is not None:
            tools.extend(HANDOFF_TOOL_SPECS)
        return {"tools": tools}
    if method != "tools/call" or not isinstance(params, dict):
        raise RoutingError("unsupported Team Transport request")
    name, args = params.get("name"), params.get("arguments", {})
    if not isinstance(args, dict):
        raise RoutingError("invalid Team Transport arguments")
    if name in HANDOFF_TOOL_NAMES:
        if broker.materials is None:
            raise RoutingError("material_forbidden: material capability is unavailable")
        try:
            value = broker.materials.call(agent_id, name, args)
        except MaterialError as exc:
            raise RoutingError(str(exc), code=exc.code) from None
        return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
    if name == "send_team_message":
        if set(args) - {"recipient_id", "text", "expects_reply", "reply_to_delivery_id", "body_ref", "material_refs"}:
            raise RoutingError("invalid Team Transport arguments")
        value = broker.send(
            agent_id,
            args.get("recipient_id"),
            args.get("text", "" if args.get("body_ref") else None),
            args.get("expects_reply", False),
            args.get("reply_to_delivery_id"),
            body_ref=args.get("body_ref"), material_refs=args.get("material_refs"),
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(_delivery_payload(value), ensure_ascii=False)}
            ]
        }
    if name == "report_task_result":
        if set(args) - {"status", "summary", "summary_ref", "material_refs"} or "status" not in args:
            raise RoutingError("invalid Team Transport arguments")
        already_synchronized = request.get("already_synchronized") is True
        try:
            value = broker.report(
                agent_id,
                args.get("status"),
                args.get("summary", "" if args.get("summary_ref") else None),
                already_synchronized=already_synchronized,
                body_ref=args.get("summary_ref"), material_refs=args.get("material_refs"),
            )
        except RoutingError as error:
            _observe_report_event(
                broker,
                agent_id,
                status="rejected",
                category=_report_rejection_category(error),
                already_synchronized=already_synchronized,
            )
            raise
        _observe_report_event(
            broker,
            agent_id,
            status="accepted",
            category="terminal_report_accepted",
            already_synchronized=already_synchronized,
        )
        payload = {"agent_id": value.agent_id, "status": value.status,
                   "summary": value.display_summary if value.display_summary is not None else value.summary,
                   "timestamp": value.timestamp}
        if value.body_ref is not None or value.material_refs:
            payload.update(summary_ref=value.body_ref, material_refs=list(value.material_refs))
        return {
            "content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
            ]
        }
    if name == "send_coordination":
        if broker.coordination_phase_callback is None:
            raise RoutingError("coordination capability is unavailable")
        if set(args) - {"recipient_id", "message_kind", "text", "generation", "body_ref", "material_refs"} or not {"recipient_id", "message_kind", "generation"} <= set(args):
            raise RoutingError("invalid coordination arguments")
        value = broker.send_coordination(
            agent_id,
            args.get("recipient_id"),
            args.get("message_kind"),
            args.get("text", ""),
            args.get("generation"),
            body_ref=args.get("body_ref"), material_refs=args.get("material_refs"),
        )
        payload = {
            **value.__dict__,
            "text": value.display_text if value.display_text is not None else value.text,
        }
        if value.body_ref is not None and value.phase_event is not None:
            payload["phase_event"] = {
                key: item for key, item in value.phase_event.items()
                if key not in {"text", "objective"}
            }
        return {
            "content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
            ]
        }
    if name == "report_issue":
        if not broker.issue_escalation_enabled:
            raise RoutingError("issue escalation capability is unavailable")
        try:
            value = broker.report_issue(agent_id, **validate_issue_report_arguments(args))
        except IssueError as exc:
            raise RoutingError(str(exc)) from None
        return {
            "content": [
                {"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}
            ]
        }
    if name == "issue_control":
        if not broker.issue_escalation_enabled or agent_id != broker.coordinator_agent_id:
            raise RoutingError("issue control is Coordinator-only")
        try:
            args = normalize_issue_control_arguments(args)
        except IssueError as exc:
            raise RoutingError(str(exc)) from None
        action = args.get("action")
        resolution: IssueResolution | None = None
        if action == "resume":
            resolution_type = args.get("resolution_type")
            common = {"issue_id", "reporter_id", "action", "control_epoch", "resolution_type"}
            if resolution_type == "guidance" or resolution_type == "abort":
                required = common | {"resolution_text"}
                if set(args) != required:
                    raise _issue_control_field_error("resolution", args, required)
            elif resolution_type == "repair_completed":
                required = common | {"repair_component"}
                allowed = required | {
                    "resolution_text",
                    "before_digest",
                    "after_digest",
                    "verification_reference",
                    "mutation_reconciliation",
                }
                if not required.issubset(args) or set(args) - allowed:
                    raise _issue_control_field_error("repair", args, required, allowed)
            else:
                raise RoutingError("issue_control resolution type is invalid")
            try:
                resolution = IssueResolution(
                    run_id=broker.issue_ledger.run_id if broker.issue_ledger else "",
                    issue_id=args["issue_id"],
                    reporter_id=args["reporter_id"],
                    resolution_type=resolution_type,
                    control_epoch=args["control_epoch"],
                    resolution_text=args.get("resolution_text"),
                    repair_component=args.get("repair_component"),
                    before_digest=args.get("before_digest"),
                    after_digest=args.get("after_digest"),
                    verification_reference=args.get("verification_reference"),
                    mutation_reconciliation=args.get("mutation_reconciliation"),
                )
            except IssueError as exc:
                code = None
                if resolution_type == "repair_completed":
                    component = args.get("repair_component")
                    if not isinstance(component, str) or component not in REPAIR_COMPONENTS:
                        code = "repair_rebind_required"
                raise RoutingError(str(exc), code=code) from None
        elif action == "pause":
            # ``reason`` is declared by the flat schema for abort.  It has no
            # meaning for pause, so tolerate a non-null schema-declared value
            # while retaining strict rejection of unknown/resolution fields.
            args.pop("reason", None)
            if set(args) != {"issue_id", "reporter_id", "action", "control_epoch"}:
                raise _issue_control_field_error(
                    "pause", args, {"issue_id", "reporter_id", "action", "control_epoch"}
                )
        elif action == "abort":
            if set(args) != {"issue_id", "reporter_id", "action", "control_epoch", "reason"}:
                raise _issue_control_field_error(
                    "abort", args, {"issue_id", "reporter_id", "action", "control_epoch", "reason"}
                )
        else:
            raise RoutingError("issue_control action is invalid")
        value = broker.issue_control(
            agent_id,
            issue_id=args["issue_id"],
            reporter_id=args["reporter_id"],
            action=action,
            control_epoch=args["control_epoch"],
            resolution=resolution,
            reason=args.get("reason"),
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}
            ]
        }
    raise RoutingError("unknown Team Transport tool")


def main() -> int:
    endpoint = os.environ.get("TEAM_TRANSPORT_SOCKET")
    if not endpoint:
        raise SystemExit("TEAM_TRANSPORT_SOCKET is required")
    for line in __import__("sys").stdin:
        request = json.loads(line)
        if request.get("method") == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "team-transport", "version": "1"},
            }
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
                ),
                flush=True,
            )
            continue
        if request.get("method") == "notifications/initialized":
            continue
        if request.get("method") == "ping":
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request.get("id"), "result": {}}
                ),
                flush=True,
            )
            continue
        # `already_synchronized` is a Host-internal marker used only by the legacy dynamic
        # callback.  The Agent-controlled stdio envelope cannot set it for the Broker.
        line = json.dumps(
            {key: value for key, value in request.items() if key != "already_synchronized"},
            ensure_ascii=False,
        ) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(endpoint)
            connection.sendall(line.encode())
            response = connection.makefile("r", encoding="utf-8").readline()
        broker_response = json.loads(response)
        if isinstance(broker_response, dict) and "error" in broker_response:
            # The broker socket is an internal transport and returns a compact
            # error object.  Do not place that object under JSON-RPC ``result``:
            # an MCP client expects either a CallToolResult or a JSON-RPC error.
            # The broker's own fixed text is relayed (bounded, string-only) so
            # the role can distinguish a rejected call from a transport fault.
            wire_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": _MCP_TOOL_ERROR_CODE,
                    "message": _broker_error_message(broker_response.get("error")),
                },
            }
        elif isinstance(broker_response, dict):
            wire_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": broker_response,
            }
        else:
            wire_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": _MCP_TOOL_ERROR_CODE,
                    "message": _MCP_TOOL_ERROR_MESSAGE,
                },
            }
        print(json.dumps(wire_response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
