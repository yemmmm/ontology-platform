"""The real 044328 pause instructions and confirmations share one wire contract."""

import json
from types import SimpleNamespace

import pytest

from modeling_team.runner import TeamRunner
from modeling_team.tests.test_task_budget import make_budget


def pause_runner(tmp_path):
    sent = []

    class Adapter:
        runtime = "codex"

        def runtime_identity(self, agent_id):
            return {"thread_id": agent_id}

        def send_message(self, agent_id, delivery):
            sent.append(json.loads(delivery.text))

    runner = TeamRunner.__new__(TeamRunner)
    runner.adapter = Adapter()
    runner.run = SimpleNamespace(run_id="run-a", configuration=SimpleNamespace(
        profile=SimpleNamespace(agents=[SimpleNamespace(agent_id="modeling")])) )
    runner.budget = make_budget(tmp_path)
    runner.budget.request_pause("metering_error")
    runner._flow_requests = {}
    runner._issue_coordinator_id = lambda: "coordinator"
    runner._append_evidence = lambda *args, **kwargs: None
    runner._state = lambda *args, **kwargs: None
    message = {"source": "task_budget", "action": "pause", "epoch": 1,
               "request_id": "pause-actual-id"}
    runner._relay_budget_members("pause", message)
    return runner, sent[0]


def test_pause_has_direct_reply_contract_accepted_without_team_tool(tmp_path):
    runner, instruction = pause_runner(tmp_path)
    assert instruction["expected_reply"] == {
        "flow_confirmation": {"request_id": "pause-actual-id", "action": "pause"}}
    assert instruction["text"]  # control_budget must receive the actual instruction, not its fallback
    assert runner._observe_flow_confirmation(SimpleNamespace(
        agent_id="modeling", text=json.dumps(instruction["expected_reply"])))
    assert runner._budget_member_control["confirmed"] == ["modeling"]
    assert runner.budget.show()["owners"]["run:run-a"]["control"]["1"]["status"] == "effective"


@pytest.mark.parametrize("request_id,action,agent_id,accepted", [
    ("pause-actual-id", "pause", "modeling", True),
    ("wrong-id", "pause", "modeling", False),
    ("pause-actual-id", "resume", "modeling", False),
    ("pause-actual-id", "pause", "unknown-agent", False),
])
def test_retained_prefixed_pause_reply_keeps_actual_binding_checks(
    tmp_path, request_id, action, agent_id, accepted,
):
    runner, _ = pause_runner(tmp_path)
    reply = 'flow_confirmation=' + json.dumps({"request_id": request_id, "action": action})
    reply += "\n\nPausing now; applied work remains retained."
    assert runner._observe_flow_confirmation(SimpleNamespace(
        agent_id=agent_id, text=reply)) is accepted
