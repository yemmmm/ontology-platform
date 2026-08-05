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
)
from modeling_team.protocol_mechanics import ProtocolRetrievalFallbackError, build_candidate_conflict
from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import TeamTransportBroker
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


def _formal_progress_runner(tmp_path: Path, adapter: _FormalProgressAdapter) -> TeamRunner:
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
    runner.transport = TeamTransportBroker(
        run_root / "broker",
        {("modeling", "protocol"), ("protocol", "modeling")},
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
        terminal_dependencies={},
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
    runner.transport.send("modeling", "protocol", json.dumps(_candidate()), expects_reply=True)
    runner.drain()
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    assert "build_candidate_receipt" in adapter.sent[-1][1].text
