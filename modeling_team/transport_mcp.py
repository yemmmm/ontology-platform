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
        RecoverableIssueLedger,
        normalize_issue_control_arguments,
        validate_issue_report_arguments,
    )
else:
    from interventions import (
        IssueControl,
        IssueError,
        IssueResolution,
        RecoverableIssueLedger,
        normalize_issue_control_arguments,
        validate_issue_report_arguments,
    )


_TERMINAL_ROLE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
TERMINAL_REPORT_GUARD_ERROR = (
    "Protocol retrieval evidence is incomplete; retry the required query or verifier before terminal report"
)
COORDINATION_OBSERVER_ERROR = "coordination evidence observer failed"
_MCP_TOOL_ERROR_CODE = -32000
_MCP_TOOL_ERROR_MESSAGE = "Team Transport request rejected"


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
    pass


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


@dataclass(frozen=True)
class TaskResult:
    agent_id: str
    status: str
    summary: str
    timestamp: float


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
            raise RoutingError(str(exc)) from None
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

    def send(
        self,
        sender_id: str,
        recipient_id: str,
        text: str,
        expects_reply: bool = False,
        reply_to_delivery_id: str | None = None,
    ) -> Delivery:
        if (
            not isinstance(text, str)
            or (sender_id, recipient_id) not in self.permissions
            or not isinstance(expects_reply, bool)
            or (reply_to_delivery_id is not None and not isinstance(reply_to_delivery_id, str))
        ):
            raise RoutingError("recipient is not allowed by frozen Profile")
        if self.pre_send_validator is not None:
            self.pre_send_validator(
                sender_id,
                recipient_id,
                text,
                expects_reply,
                reply_to_delivery_id,
            )
        with self._lock:
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
                    raise RoutingError("Team Transport reply is not an active reversed request")
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
            raise RoutingError("formal reply slot reopen is not authorized")
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
                raise RoutingError("formal reply slot reopen binding is invalid")
            if original_delivery_id in self._formal_reply_reopens:
                raise RoutingError("formal reply slot reopen was already consumed")

            pending_marker = object()
            current = self._pending_replies.get(original_delivery_id, pending_marker)
            occupied = current == invalid_reply_delivery_id
            acknowledged = (
                current is pending_marker
                and invalid_reply_delivery_id in self._acknowledged_deliveries
            )
            if not (occupied or acknowledged):
                raise RoutingError("formal reply slot is not occupied by the exact invalid reply")

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
    ) -> TaskResult:
        if self.terminal_report_guard is not None:
            try:
                allowed = _call_terminal_report_guard(
                    self.terminal_report_guard,
                    agent_id,
                    already_synchronized,
                    status,
                )
            except Exception:
                raise RoutingError(TERMINAL_REPORT_GUARD_ERROR) from None
            if allowed is not False:
                raise RoutingError(TERMINAL_REPORT_GUARD_ERROR)
        if status not in {"completed", "blocked"} or not isinstance(summary, str):
            raise RoutingError("terminal result is invalid")
        with self._lock:
            if self._issues is not None and self._issues.pending:
                raise RoutingError("terminal result is blocked by an active issue")
            if agent_id in self._results:
                raise RoutingError("Agent already reported a terminal result")
            if agent_id == self.modeling_agent_id:
                pending = [
                    delivery_id
                    for delivery_id in self._pending_replies
                    if self._delivery_by_id[delivery_id].sender_id == agent_id
                ]
                if pending:
                    raise RoutingError("terminal result requires delivered reply")
                inbound_revision_requests = [
                    delivery_id
                    for delivery_id in self._pending_replies
                    if self._delivery_by_id[delivery_id].recipient_id == agent_id
                ]
                if status == "completed" and inbound_revision_requests:
                    raise RoutingError("completed terminal result requires an explicit revision response")
                requested = any(
                    delivery.sender_id == agent_id and delivery.expects_reply
                    for delivery in self._delivery_by_id.values()
                )
                if status == "completed" and not requested:
                    raise RoutingError("completed terminal result requires an established reply request")
            missing = sorted(
                dependency
                for dependency in self.terminal_dependencies.get(agent_id, frozenset())
                if dependency not in self._results or (agent_id, dependency) not in self._terminal_handoff_acks
            )
            if missing:
                if not all(isinstance(role, str) and _TERMINAL_ROLE_ID.fullmatch(role) for role in missing):
                    raise RoutingError("terminal result dependencies are invalid")
                raise RoutingError("terminal result requires terminal handoffs: " + ", ".join(missing))
            result = TaskResult(agent_id, status, summary, time.time())
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
        "text": delivery.text,
        "timestamp": delivery.timestamp,
        "delivery_id": delivery.delivery_id,
        "expects_reply": delivery.expects_reply,
        "reply_to_delivery_id": delivery.reply_to_delivery_id,
    }
    if delivery.owner_answer_id is not None:
        payload["owner_answer_id"] = delivery.owner_answer_id
    if delivery.release_id is not None:
        payload["release_id"] = delivery.release_id
    return payload


def _report_rejection_category(error: RoutingError) -> str:
    """Map a Broker rejection to the small, non-sensitive event vocabulary."""
    message = str(error)
    if message.startswith("terminal result requires terminal handoffs: "):
        missing = message.rsplit(": ", 1)[-1].split(", ")
        if "modeling" in missing:
            return "missing_modeling_handoff"
    return "broker_rejection"


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
                        "Do not include credentials or platform write instructions."
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
                            "The schema is action-specific: pause has four fields, abort has "
                            "those four plus a required persisted-resolution reason, and resume "
                            "uses one of its explicit resolution branches."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "oneOf": [
                                {
                                    "title": "pause",
                                    "properties": {
                                        **issue_control_common_properties,
                                        "action": {"type": "string", "enum": ["pause"]},
                                    },
                                    "required": [
                                        "issue_id",
                                        "reporter_id",
                                        "action",
                                        "control_epoch",
                                    ],
                                    "additionalProperties": False,
                                },
                                {
                                    "title": "abort",
                                    "properties": {
                                        **issue_control_common_properties,
                                        "action": {"type": "string", "enum": ["abort"]},
                                        "reason": {"type": "string", "minLength": 1},
                                    },
                                    "required": [
                                        "issue_id",
                                        "reporter_id",
                                        "action",
                                        "control_epoch",
                                        "reason",
                                    ],
                                    "additionalProperties": False,
                                },
                                {
                                    "title": "resume-guidance",
                                    "properties": {
                                        **issue_control_common_properties,
                                        "action": {"type": "string", "enum": ["resume"]},
                                        "resolution_type": {
                                            "type": "string",
                                            "enum": ["guidance"],
                                        },
                                        "resolution_text": {"type": "string", "minLength": 1},
                                    },
                                    "required": [
                                        "issue_id",
                                        "reporter_id",
                                        "action",
                                        "control_epoch",
                                        "resolution_type",
                                        "resolution_text",
                                    ],
                                    "additionalProperties": False,
                                },
                                {
                                    "title": "resume-repair-completed",
                                    "properties": {
                                        **issue_control_common_properties,
                                        "action": {"type": "string", "enum": ["resume"]},
                                        "resolution_type": {
                                            "type": "string",
                                            "enum": ["repair_completed"],
                                        },
                                        "repair_component": {"type": "string", "minLength": 1},
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
                                        "resolution_type",
                                        "repair_component",
                                        "before_digest",
                                        "after_digest",
                                        "verification_reference",
                                        "mutation_reconciliation",
                                    ],
                                    "additionalProperties": False,
                                },
                            ],
                        },
                    }
                )
        return {"tools": tools}
    if method != "tools/call" or not isinstance(params, dict):
        raise RoutingError("unsupported Team Transport request")
    name, args = params.get("name"), params.get("arguments", {})
    if not isinstance(args, dict):
        raise RoutingError("invalid Team Transport arguments")
    if name == "send_team_message":
        if set(args) - {"recipient_id", "text", "expects_reply", "reply_to_delivery_id"}:
            raise RoutingError("invalid Team Transport arguments")
        value = broker.send(
            agent_id,
            args.get("recipient_id"),
            args.get("text"),
            args.get("expects_reply", False),
            args.get("reply_to_delivery_id"),
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(_delivery_payload(value), ensure_ascii=False)}
            ]
        }
    if name == "report_task_result":
        if set(args) != {"status", "summary"}:
            raise RoutingError("invalid Team Transport arguments")
        already_synchronized = request.get("already_synchronized") is True
        try:
            value = broker.report(
                agent_id,
                args.get("status"),
                args.get("summary"),
                already_synchronized=already_synchronized,
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
        return {
            "content": [
                {"type": "text", "text": json.dumps(value.__dict__, ensure_ascii=False)}
            ]
        }
    if name == "send_coordination":
        if broker.coordination_phase_callback is None:
            raise RoutingError("coordination capability is unavailable")
        if set(args) != {"recipient_id", "message_kind", "text", "generation"}:
            raise RoutingError("invalid coordination arguments")
        value = broker.send_coordination(
            agent_id,
            args.get("recipient_id"),
            args.get("message_kind"),
            args.get("text"),
            args.get("generation"),
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(value.__dict__, ensure_ascii=False)}
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
                    raise RoutingError("issue_control resolution fields are invalid")
            elif resolution_type == "repair_completed":
                required = common | {
                    "repair_component",
                    "before_digest",
                    "after_digest",
                    "verification_reference",
                    "mutation_reconciliation",
                }
                if set(args) != required:
                    raise RoutingError("issue_control repair fields are invalid")
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
                raise RoutingError(str(exc)) from None
        elif action == "pause":
            if set(args) != {"issue_id", "reporter_id", "action", "control_epoch"}:
                raise RoutingError("issue_control pause fields are invalid")
        elif action == "abort":
            if set(args) != {"issue_id", "reporter_id", "action", "control_epoch", "reason"}:
                raise RoutingError("issue_control abort fields are invalid")
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
            wire_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": _MCP_TOOL_ERROR_CODE,
                    "message": _MCP_TOOL_ERROR_MESSAGE,
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
