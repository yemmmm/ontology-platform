"""Inputs wait for natural turn completion; no paid model calls."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.runtimes.base import RuntimeDelivery
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent
from modeling_team.tests.test_delivery_session import session
from modeling_team.tests.test_delivery_wakeups import observation


def queued_adapter(tmp_path):
    adapter = CodexRuntimeAdapter(repository_root=Path(__file__).resolve().parents[2])
    agent = _Agent("modeling", SimpleNamespace(role="modeling"), tmp_path, tmp_path, tmp_path)
    agent.thread_id = "native-thread"
    agent.active_turn_id = "turn-current"
    agent.state = "running"
    adapter.agents = {agent.agent_id: agent}
    adapter._drain_agent_output_locked = lambda _: None
    calls = []
    adapter._rpc = lambda agent, method, params: (
        calls.append((method, params)) or {"turn": {"id": "turn-" + str(len(calls))}}
    )
    adapter._activity_turn_start = lambda *args: None
    return adapter, agent, calls


def test_codex_busy_messages_wait_fifo_for_natural_completion(tmp_path):
    adapter, agent, calls = queued_adapter(tmp_path)
    receipts = [adapter.send_message("modeling", RuntimeDelivery("coordinator", "modeling", "peer", text))
                for text in ["first", "second"]]
    assert not calls
    assert [receipt.mode for receipt in receipts] == ["enqueue", "enqueue"]
    assert all(receipt.turn_id is None for receipt in receipts)
    adapter.receive_messages()
    assert not calls
    agent.active_turn_id, agent.state = None, "idle"
    adapter.receive_messages()
    assert len(calls) == 1 and calls[0][0] == "turn/start"
    assert "first" in json.dumps(calls[0][1])
    adapter.receive_messages()
    assert len(calls) == 1
    agent.active_turn_id, agent.state = None, "idle"
    adapter.receive_messages()
    assert len(calls) == 2 and "second" in json.dumps(calls[1][1])


def test_codex_budget_pause_waits_without_steer_or_interrupt(tmp_path):
    adapter, agent, calls = queued_adapter(tmp_path)
    agent.process = SimpleNamespace(poll=lambda: None)
    result = adapter.control_budget({"action": "pause", "epoch": 1, "text": "pause"})
    assert not calls
    assert result["status"] == "pending"
    agent.active_turn_id, agent.state = None, "idle"
    adapter.receive_messages()
    assert [method for method, _ in calls] == ["turn/start"]


@pytest.mark.parametrize("runtime", ["codex", "dsh"])
def test_critical_observation_remains_queued_while_busy(tmp_path, runtime):
    host = session(tmp_path)
    host.runtime_name = runtime
    host.record_observation(observation())
    packet = host._model_observation()
    calls = []
    native = SimpleNamespace(busy=True, steer=lambda text: calls.append(text))
    assert not host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=True)
    assert not calls
    assert host._pending_decisions[0]["delivery_status"] == "pending"


def test_inflight_provider_request_is_not_rejected_when_amount_exhausted(tmp_path):
    adapter, _, _ = queued_adapter(tmp_path)
    budget = SimpleNamespace(require_available=lambda **_: pytest.fail("per-request budget cutoff"))
    adapter._request_budget = lambda: budget
    adapter._before_provider_request({"provider": "glm-direct", "requested_model": "glm-5.3-flash"})


def test_runner_budget_threshold_does_not_pause_an_active_turn(tmp_path):
    from modeling_team.runner import TeamRunner
    from modeling_team.runtimes.base import AgentState
    runner = TeamRunner.__new__(TeamRunner)
    runner.adapter = SimpleNamespace(get_agent_states=lambda: [AgentState("modeling", "running")])
    runner.budget = SimpleNamespace(require_available=lambda **_: pytest.fail("mid-turn pause"))
    assert runner._sync_task_budget() is False


def test_runner_stop_is_queued_until_current_turn_finishes(tmp_path):
    from modeling_team.runner import TeamRunner
    from modeling_team.runtimes.base import AgentState
    runner = TeamRunner.__new__(TeamRunner)
    runner.run = SimpleNamespace(run_id="test-run")
    runner.adapter = SimpleNamespace(get_agent_states=lambda: [AgentState("modeling", "running")])
    runner._append_evidence = lambda *args: None
    message = {"action": "stop", "request_id": "original-stop"}
    assert runner.receive_outer(message)[0]["status"] == "queued"
    assert runner._queued_outer_controls == [message]
    runner.adapter.get_agent_states = lambda: [AgentState("modeling", "idle")]
    consumed = []
    runner.receive_outer = lambda value: consumed.append(value) or [{"type": "stopped"}]
    assert runner.drain() == [{"type": "stopped"}]
    assert consumed == [message]


def test_evaluation_stop_waits_for_active_consumer(tmp_path):
    from modeling_team.evaluation_owner import EvaluationOwner, EvaluationStopped
    owner = EvaluationOwner(tmp_path / "evaluation.owner")
    child = SimpleNamespace(active_turn_id="current-turn")
    resource = SimpleNamespace(_child_agent=child, spec={}, thread_id="consumer-thread",
                               process=SimpleNamespace(poll=lambda: None, pid=123))
    owner.active = [resource]
    control = {"request_id": "stop-current", "action": "stop", "text": "stop"}
    pending = [control]
    owner._next_budget_control = lambda: pending.pop(0) if pending else None
    try:
        owner.poll()
        assert not owner.stopping
        assert owner.receipts["stop-current"]["status"] == "queued"
        child.active_turn_id = None
        with pytest.raises(EvaluationStopped):
            owner.poll()
    finally:
        owner.active = []
        owner.close()


def test_queued_candidate_uses_actual_turn_without_counting_queue_time():
    from modeling_team.candidate_progress import FormalCandidateProgress
    from modeling_team.runtimes.base import AgentState, RuntimeDispatchReceipt
    from modeling_team.tests.test_r23005_candidate_progress import _candidate, _delivery
    clock = [0.0]
    progress = FormalCandidateProgress(clock=lambda: clock[0])
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(_candidate()), "candidate-1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol",
        run_id="run-1", protocol_thread_id="protocol-thread")
    progress.bind_dispatch(RuntimeDispatchReceipt(
        "enqueue", None, "codex", "dispatch-1", "protocol-thread", "candidate-1"))
    clock[0] = 1000.0
    assert not progress.check_deadline()
    state = AgentState("protocol", "running", "actual-turn", "old-turn", pending_dispatches=(
        {"dispatch_id": "dispatch-1", "turn_id": "actual-turn", "state": "claimed"},))
    assert not progress.observe_states([state], protocol_agent_id="protocol")
    clock[0] += 500
    progress.observe_states([state], protocol_agent_id="protocol")
    assert progress.check_deadline()  # polling the queue cannot reset the active clock
    newer = AgentState("protocol", "running", "next-turn", "actual-turn", pending_dispatches=(
        {"dispatch_id": "dispatch-1", "turn_id": "actual-turn", "state": "settled"},))
    assert progress.observe_states([newer], protocol_agent_id="protocol")
