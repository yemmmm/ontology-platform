from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.candidate_progress import (
    FORMAL_CANDIDATE_KIND,
    FormalCandidateError,
    FormalCandidateProgress,
    FormalCandidateProgressTimeout,
    FormalCandidateRoutingError,
    formal_candidate_digests,
)
from modeling_team.interventions import IssueResolution
from modeling_team.protocol_mechanics import ProtocolRetrievalFallbackError, build_candidate_conflict
from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker
from modeling_team.runtimes.base import AgentState, RuntimeDelivery, RuntimeDispatchReceipt


def _candidate(revision: int = 1) -> dict[str, object]:
    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": revision,
        "scope": "dify-workflow",
        "constraints": ["preserve explicit unknowns"],
        "items": [
            {
                "item_id": "workflow-1",
                "item_kind": "entity",
                "semantic": {"label": "Workflow"},
                "evidence_citations": [{"document": "tools.mdx"}],
            }
        ],
    }


def _delivery(sender: str, recipient: str, text: str, delivery_id: str, *, reply_to: str | None = None) -> RuntimeDelivery:
    return RuntimeDelivery(
        sender,
        recipient,
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=True,
        reply_to_delivery_id=reply_to,
    )


def _progress(clock):
    return FormalCandidateProgress(clock=clock)


def test_conflict_builder_binds_complete_formal_candidate() -> None:
    value = build_candidate_conflict(_candidate(), "missing_label", "label is required")
    assert set(value) == {
        "status",
        "candidate_revision",
        "semantic_digest",
        "candidate_digest",
        "conflict_code",
        "conflict_detail",
    }
    assert value["status"] == "conflict"
    assert value["candidate_revision"] == 1

    malformed = dict(_candidate())
    malformed["unexpected"] = True
    with pytest.raises(ProtocolRetrievalFallbackError):
        build_candidate_conflict(malformed, "invalid", "must fail")


def test_formal_progress_accepts_only_exact_bound_receipt() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    candidate = _candidate()
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    invalid = _delivery(
        "protocol",
        "modeling",
        json.dumps({"status": "accepted", "candidate_revision": 1}),
        "r1",
        reply_to="d1",
    )
    assert progress.observe_delivery(
        invalid,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) is None
    assert progress.state == "awaiting_receipt"
    identity = progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "r2", reply_to="d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "accepted"
    assert progress.state == "complete"


def test_conflict_requires_full_revision_and_rebinds_pending_identity() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    candidate = _candidate()
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    identity = progress.identity
    assert identity is not None
    conflict = build_candidate_conflict(candidate, "unsupported", "relation is not declared")
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(conflict), "c1", reply_to="d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "conflict"
    assert progress.state == "awaiting_revision"
    revised = _candidate(2)
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(revised), "d2", reply_to="c1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "revision"
    assert progress.identity is not None and progress.identity.original_delivery_id == "d2"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    revised_identity = progress.identity
    assert revised_identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": revised_identity.candidate_revision,
        "semantic_digest": revised_identity.semantic_digest,
        "candidate_digest": revised_identity.candidate_digest,
    }
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "r2", reply_to="d2"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "accepted"


def test_turn_barrier_allows_one_redrive_then_exhausts() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(_candidate()), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    states = [AgentState("protocol", "idle", "turn-1", "turn-1")]
    assert progress.observe_states(states, protocol_agent_id="protocol")
    assert progress.redrive_ready()
    progress.mark_redrive_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    progress.observe_states([AgentState("protocol", "idle", "turn-2", "turn-2")], protocol_agent_id="protocol")
    with pytest.raises(FormalCandidateRoutingError):
        progress.redrive_ready()
    assert progress.state == "exhausted"


def test_timeout_is_injected_and_latched_after_dispatch_deadline() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(_candidate()), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    now[0] = 120.0
    with pytest.raises(FormalCandidateProgressTimeout):
        progress.check_deadline()


def _started_progress(now: list[float]) -> tuple[FormalCandidateProgress, dict[str, object]]:
    candidate = _candidate()
    progress = _progress(lambda: now[0])
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    return progress, candidate


def _receipt_for(progress: FormalCandidateProgress) -> dict[str, object]:
    identity = progress.identity
    assert identity is not None
    return {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }


def _observe_late(
    progress: FormalCandidateProgress,
    payload: dict[str, object],
    delivery_id: str,
    *,
    reply_to: str = "d1",
) -> str | None:
    return progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(payload), delivery_id, reply_to=reply_to),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    )


def test_exhausted_progress_ignores_late_receipt_and_conflict() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    progress.observe_states([AgentState("protocol", "idle", "turn-1", "turn-1")], protocol_agent_id="protocol")
    assert progress.redrive_ready()
    progress.mark_redrive_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    progress.observe_states([AgentState("protocol", "idle", "turn-2", "turn-2")], protocol_agent_id="protocol")
    with pytest.raises(FormalCandidateRoutingError):
        progress.redrive_ready()
    identity = progress.identity
    conflict = build_candidate_conflict(candidate, "late", "late response")
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") is None
    assert _observe_late(progress, conflict, "late-conflict") is None
    assert progress.state == "exhausted"
    assert progress.identity == identity


def test_receipt_timeout_ignores_late_receipt_and_conflict_and_latches_deadline() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    now[0] = 120.0
    with pytest.raises(FormalCandidateProgressTimeout):
        progress.check_deadline()
    identity = progress.identity
    conflict = build_candidate_conflict(candidate, "late", "late response")
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") is None
    assert _observe_late(progress, conflict, "late-conflict") is None
    assert progress.state == "awaiting_receipt"
    assert progress.identity == identity
    assert progress.timeout_latched is True
    with pytest.raises(FormalCandidateProgressTimeout):
        progress.check_deadline()
    assert progress.timeout_latched is True


def test_revision_timeout_ignores_late_complete_revision_and_conflict() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    conflict = build_candidate_conflict(candidate, "needs_revision", "revise item")
    assert _observe_late(progress, conflict, "conflict-1") == "conflict"
    identity = progress.identity
    assert identity is not None
    now[0] = 120.0
    with pytest.raises(FormalCandidateProgressTimeout):
        progress.check_deadline()
    revised = _candidate(2)
    revision = _delivery(
        "modeling",
        "protocol",
        json.dumps(revised),
        "late-revision",
        reply_to="conflict-1",
    )
    assert progress.observe_delivery(
        revision,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) is None
    assert _observe_late(progress, conflict, "late-conflict") is None
    assert progress.state == "awaiting_revision"
    assert progress.identity == identity
    assert progress.timeout_latched is True


def test_terminal_failure_latch_ignores_all_late_progress() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    identity = progress.identity
    progress.mark_terminal_failure()
    conflict = build_candidate_conflict(candidate, "late", "late response")
    revised = _candidate(2)
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") is None
    assert _observe_late(progress, conflict, "late-conflict") is None
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(revised), "late-revision", reply_to="conflict-1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) is None
    assert progress.state == "awaiting_receipt"
    assert progress.identity == identity
    assert progress.terminal_failure_latched is True


def test_formal_candidate_rejects_non_string_constraints() -> None:
    invalid = _candidate()
    invalid["constraints"] = ["ok", {"not": "a string"}]
    with pytest.raises(FormalCandidateError):
        FormalCandidateProgress(clock=lambda: 0.0).observe_delivery(
            _delivery("modeling", "protocol", json.dumps(invalid), "d1"),
            modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
        )


def test_redrive_retains_exact_candidate_bytes_and_runtime_attribution() -> None:
    original_text = (
        '{"candidate_kind":"platform-neutral-candidate-v2",'
        '"candidate_revision":1,"scope":"工作流-é",'
        '"constraints":["preserve explicit unknowns"],'
        '"items":[{"item_id":"workflow-1","item_kind":"entity",'
        '"semantic":{"label":"工作流"},'
        '"evidence_citations":[{"document":"tools.mdx"}]}]}\n  '
    )
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    delivery = _delivery("modeling", "protocol", original_text, "d1")
    assert progress.observe_delivery(
        delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    attribution = progress.original_runtime_attribution
    assert attribution is not None
    assert attribution.text == original_text
    assert progress.redrive_text() == original_text
    assert attribution.sender_id == delivery.sender_id
    assert attribution.recipient_id == delivery.recipient_id
    assert attribution.delivery_id == delivery.delivery_id
    assert attribution.expects_reply == delivery.expects_reply
    assert attribution.reply_to_delivery_id == delivery.reply_to_delivery_id


def test_formal_broker_reopens_one_occupied_or_acknowledged_reply_slot(tmp_path: Path) -> None:
    for acknowledged in (False, True):
        broker = TeamTransportBroker(
            tmp_path / ("acknowledged" if acknowledged else "occupied"),
            {("modeling", "protocol"), ("protocol", "modeling")},
            modeling_agent_id="modeling",
        )
        request = broker.send("modeling", "protocol", "candidate", expects_reply=True)
        invalid = broker.send(
            "protocol",
            "modeling",
            "not-json",
            expects_reply=True,
            reply_to_delivery_id=request.delivery_id,
        )
        if acknowledged:
            broker.ack_delivery(invalid.delivery_id)
        broker.reopen_formal_reply_slot(
            original_delivery_id=request.delivery_id,
            invalid_reply_delivery_id=invalid.delivery_id,
            modeling_agent_id="modeling",
            protocol_agent_id="protocol",
            formal_candidate=True,
        )
        if not acknowledged:
            broker.ack_delivery(invalid.delivery_id)
        replacement = broker.send(
            "protocol",
            "modeling",
            "valid-receipt",
            expects_reply=True,
            reply_to_delivery_id=request.delivery_id,
        )
        broker.ack_delivery(replacement.delivery_id)
        with pytest.raises(RoutingError, match="active reversed"):
            broker.send(
                "protocol",
                "modeling",
                "duplicate",
                reply_to_delivery_id=request.delivery_id,
            )
        assert len(broker._delivery_by_id) == 3
        with pytest.raises(RoutingError, match="already consumed"):
            broker.reopen_formal_reply_slot(
                original_delivery_id=request.delivery_id,
                invalid_reply_delivery_id=invalid.delivery_id,
                modeling_agent_id="modeling",
                protocol_agent_id="protocol",
                formal_candidate=True,
            )


def test_runner_reopens_invalid_reply_then_accepts_exact_redrive_reply(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate_text = json.dumps(_candidate(), ensure_ascii=False, separators=(",", ":"))
    original = runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)
    runner.transport.send(
        "protocol",
        "modeling",
        "Please resend the candidate",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    redrives = [delivery for _, delivery in adapter.sent if delivery.kind == "candidate-redrive"]
    assert len(redrives) == 1
    assert not any(
        recipient == "modeling" and delivery.text == "Please resend the candidate"
        for recipient, delivery in adapter.sent
    )
    assert redrives[0].text == candidate_text
    assert redrives[0].delivery_id == original.delivery_id
    identity = runner._candidate_progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(receipt),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "complete"
    assert len([delivery for _, delivery in adapter.sent if delivery.kind == "candidate-redrive"]) == 1
    assert len(runner.transport._delivery_by_id) == 3


def test_runner_quarantines_invalid_guidance_then_binds_revision_to_formal_conflict(
    tmp_path: Path,
) -> None:
    """A malformed Protocol guidance response cannot become a revision anchor."""

    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate = _candidate()
    original = runner.transport.send(
        "modeling",
        "protocol",
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
    )
    guidance = runner.transport.send(
        "protocol",
        "modeling",
        "Please send a complete, self-contained candidate revision",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )

    # The malformed guidance is reopened for the formal slot and then dropped;
    # the only Runtime dispatch is the bounded candidate redrive.
    runner.drain()
    assert runner._candidate_progress.state == "redrive_sent"
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    assert not any(
        recipient == "modeling" and delivery.delivery_id == guidance.delivery_id
        for recipient, delivery in adapter.sent
    )
    progress_events = [
        json.loads(line)
        for line in (tmp_path / "run" / "evidence" / "formal-candidate-progress.jsonl")
        .read_text()
        .splitlines()
    ]
    progress_event_names = [event["event"] for event in progress_events]
    assert progress_event_names.index("invalid-response-quarantined") > progress_event_names.index(
        "invalid-response-slot-reopened"
    )

    conflict = build_candidate_conflict(candidate, "competency_question_count_mismatch", "scope mismatch")
    conflict_delivery = runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(conflict, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "awaiting_revision"
    assert any(
        recipient == "modeling" and delivery.delivery_id == conflict_delivery.delivery_id
        for recipient, delivery in adapter.sent
    )

    revised = _candidate(2)
    # After the formal conflict, the original request is no longer an active
    # revision slot; only the conflict delivery may be reversed by Modeling.
    with pytest.raises(RoutingError, match="active reversed"):
        runner.transport.send(
            "modeling",
            "protocol",
            json.dumps(revised, ensure_ascii=False, separators=(",", ":")),
            expects_reply=True,
            reply_to_delivery_id=original.delivery_id,
        )
    revision_delivery = runner.transport.send(
        "modeling",
        "protocol",
        json.dumps(revised, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
        reply_to_delivery_id=conflict_delivery.delivery_id,
    )
    candidate_digest, semantic_digest = formal_candidate_digests(revised)
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(
            {
                "status": "accepted",
                "candidate_revision": revised["candidate_revision"],
                "semantic_digest": semantic_digest,
                "candidate_digest": candidate_digest,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        reply_to_delivery_id=revision_delivery.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "complete"


class _FormalProgressAdapter:
    def __init__(self, *, missing_receipt: bool = False) -> None:
        self.missing_receipt = missing_receipt
        self.sent: list[tuple[str, RuntimeDelivery]] = []
        self.turns = {"protocol": (None, None)}

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        self.sent.append((recipient, delivery))
        if recipient == "protocol" and delivery.kind == "peer":
            if self.missing_receipt:
                return None
            self.turns["protocol"] = ("turn-1", "turn-1")
            return RuntimeDispatchReceipt("start", "turn-1")
        if recipient == "protocol" and delivery.kind == "candidate-redrive":
            self.turns["protocol"] = ("turn-2", "turn-2")
            return RuntimeDispatchReceipt("start", "turn-2")
        return RuntimeDispatchReceipt("start", "other")

    def receive_messages(self):
        return []

    def get_agent_states(self):
        started, completed = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, completed)]


class _IssueRecoveryProgressAdapter(_FormalProgressAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.complete_original = False

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        if recipient == "protocol" and delivery.kind == "peer":
            self.sent.append((recipient, delivery))
            self.turns["protocol"] = ("candidate-turn", None)
            return RuntimeDispatchReceipt("start", "candidate-turn")
        if recipient == "protocol" and delivery.kind == "candidate-redrive":
            self.sent.append((recipient, delivery))
            self.turns["protocol"] = ("redrive-turn", None)
            return RuntimeDispatchReceipt("start", "redrive-turn")
        return super().send_message(recipient, delivery)

    def get_agent_states(self):
        if self.complete_original:
            self.turns["protocol"] = ("candidate-turn", "candidate-turn")
        started, completed = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, completed)]


def _formal_progress_runner(
    tmp_path: Path,
    adapter: _FormalProgressAdapter,
    *,
    issue_escalation_enabled: bool = False,
) -> TeamRunner:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=agents, parameters={}),
    )
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True)
    runner = TeamRunner(repository_root=tmp_path, adapter=adapter, monotonic_clock=lambda: 0.0)
    runner.run = SimpleNamespace(run_id="run-1", root=run_root, scope={"mode": "create"}, configuration=configuration)
    permissions = {("modeling", "protocol"), ("protocol", "modeling")}
    if issue_escalation_enabled:
        permissions.update({("modeling", "coordinator"), ("coordinator", "modeling")})
    runner.transport = TeamTransportBroker(
        run_root / "broker",
        permissions,
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
        terminal_dependencies={},
        issue_escalation_enabled=issue_escalation_enabled,
    )
    runner._candidate_progress = FormalCandidateProgress(clock=lambda: 0.0)
    return runner


def test_runner_missing_formal_turn_id_fails_platform_contract(tmp_path: Path) -> None:
    from modeling_team.candidate_progress import FormalCandidatePlatformContractError

    runner = _formal_progress_runner(tmp_path, _FormalProgressAdapter(missing_receipt=True))
    runner.transport.send("modeling", "protocol", json.dumps(_candidate()), expects_reply=True)
    with pytest.raises(FormalCandidatePlatformContractError):
        runner.drain()
    assert json.loads((tmp_path / "run" / "state.json").read_text())[
        "state"
    ] == "TERMINAL_FAILURE_PENDING_CLEANUP"


def test_runner_turn_barrier_sends_one_candidate_redrive(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate_text = json.dumps(_candidate())
    original = runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)
    runner.drain()
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    redrive = adapter.sent[-1][1]
    assert redrive.text == candidate_text
    assert redrive.sender_id == original.sender_id
    assert redrive.recipient_id == original.recipient_id
    assert redrive.delivery_id == original.delivery_id
    assert redrive.expects_reply == original.expects_reply
    assert redrive.reply_to_delivery_id == original.reply_to_delivery_id


def test_issue_pending_latches_candidate_before_recovery_turn_overwrites_state(tmp_path: Path) -> None:
    adapter = _IssueRecoveryProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter, issue_escalation_enabled=True)
    candidate_text = json.dumps(_candidate())
    runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)

    # The original dispatch is started, but its completion notification has not
    # arrived during this drain.  The issue is then reported before the next
    # main-loop iteration.
    runner.drain()
    progress = runner._candidate_progress
    assert progress is not None and progress.pending is not None
    assert progress.pending.turn_barrier_complete is False
    identity = progress.identity
    assert identity is not None
    ledger = runner.transport.issue_ledger
    assert ledger is not None
    issue = ledger.report(
        reporter_id="modeling",
        category="runtime_recovery",
        summary="Protocol needs recovery guidance",
        failing_operation="receipt",
        error="recovery turn required",
        mutation_state="not_started",
        requested_action="pause and resume",
        thread_id="runtime-agent:protocol",
        candidate_identity=identity.__dict__,
    )

    # While the issue is pending, Runner must retain the original delivery and
    # observe its completion, but must not redrive yet.
    adapter.complete_original = True
    runner.drain()
    assert progress.pending is not None and progress.pending.turn_barrier_complete is True
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer"]

    # A later recovery turn overwrites the adapter's last-completed turn.  Once
    # the issue is resolved, the latched barrier still permits exactly one
    # candidate redrive.
    adapter.complete_original = False
    adapter.turns["protocol"] = ("recovery-turn", "recovery-turn")
    pause = ledger.control(
        issue_id=issue.issue_id,
        coordinator_id="coordinator",
        reporter_id="modeling",
        action="pause",
        control_epoch=issue.control_epoch,
    )
    ledger.mark_dispatch(pause)
    resolution = IssueResolution(
        run_id=issue.run_id,
        issue_id=issue.issue_id,
        reporter_id="modeling",
        resolution_type="guidance",
        control_epoch=issue.control_epoch,
        resolution_text="Resume the same candidate turn.",
    )
    ledger.persist_resolution(resolution)
    resume = ledger.control(
        issue_id=issue.issue_id,
        coordinator_id="coordinator",
        reporter_id="modeling",
        action="resume",
        control_epoch=issue.control_epoch,
        resolution=resolution,
    )
    ledger.mark_dispatch(resume)

    runner.drain()
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    assert progress.state == "redrive_sent"
