from modeling_team.runtimes.base import RuntimeDispatchReceipt
from modeling_team.runtimes.dsh_events import DispatchProjection
import pytest


def event(seq, kind, **data):
    return {"seq": seq, "type": kind, "data": data}


def queued(seq, *ids):
    return event(
        seq,
        "agent/inbox/spliced",
        target="next-turn",
        start=0,
        inserted=[{"id": identity} for identity in ids],
    )


def claim(seq, canceled=False):
    return event(
        seq,
        "agent/inbox/spliced",
        target="next-turn",
        start=0,
        removedCount=1,
        inserted=[],
        **({"outcome": "canceled"} if canceled else {}),
    )


def test_enqueue_receipt_never_fabricates_a_turn():
    assert RuntimeDispatchReceipt("start", "old-turn").runtime == "codex"
    r = RuntimeDispatchReceipt("enqueue", None, "dsh", "host-1", "s", "m")
    assert r.turn_id is None
    with pytest.raises(ValueError):
        RuntimeDispatchReceipt("enqueue", "m", "dsh", "host-1", "s", "m")


def test_early_events_busy_adjacent_inputs_and_fast_idle():
    p = DispatchProjection("s")
    p.append(queued(0, "m1", "m2"))
    assert p.status("m1")["state"] == "queued"
    p.append(event(1, "turn/start", turn=1))
    p.append(claim(2))
    p.append(event(3, "turn/end", turn=1, reason={"kind": "error"}))
    assert p.status("m1")["state"] == "settled"
    assert p.status("m1")["reason"] == {"kind": "error"}
    assert p.status("m2")["state"] == "queued"
    assert not p.append(claim(2))


def test_cancel_and_removal_without_turn_are_not_consumption():
    p = DispatchProjection("s")
    p.append(queued(0, "a", "b"))
    p.append(claim(1, canceled=True))
    p.append(claim(2))
    assert p.status("a")["state"] == "canceled"
    assert p.status("b")["state"] == "unknown"


def test_gap_stays_unknown_until_original_event_is_recovered():
    p = DispatchProjection("s")
    p.append(queued(0, "m"))
    p.append(claim(2))
    assert p.status("m")["state"] == "unknown"
    p.append(event(1, "turn/start", turn=1))
    assert p.status("m")["state"] == "claimed"
    p.append(event(3, "turn/end", turn=1, reason={"kind": "max-tokens"}))
    assert p.status("m")["reason"] == {"kind": "max-tokens"}


def test_conflicting_sequence_cannot_be_erased_by_later_events():
    p = DispatchProjection("s")
    p.append(queued(0, "m"))
    p.append(queued(0, "different"))
    p.append(event(1, "turn/start", turn=1))
    assert p.status("m")["state"] == "unknown"
    assert p.status("m")["reason"] == "event-sequence-conflict"


def test_notifications_before_rpc_response_bind_only_the_native_message(tmp_path):
    from types import SimpleNamespace
    from modeling_team.runtimes.dsh import DshRuntimeAdapter, _DshAgent
    from modeling_team.runtimes.base import RuntimeDelivery

    adapter = DshRuntimeAdapter(repository_root=tmp_path)
    agent = _DshAgent("modeling", SimpleNamespace(role="modeling"), tmp_path, "s")
    agent.projection = DispatchProjection("s")
    agent.ready = True
    adapter.agents["modeling"] = agent

    def rpc(role, method, params):
        for item in [
            queued(0, "native-first", "native-second"),
            event(1, "turn/start", turn=1),
            claim(2),
            event(3, "turn/end", turn=1, reason={"kind": "completed"}),
        ]:
            adapter._notification(
                agent, {"method": "session.event", "params": {"sessionId": "s", "event": item}}
            )
        adapter._notification(
            agent, {"method": "session.status", "params": {"sessionId": "s", "status": "idle"}}
        )
        return {"messageId": "native-second"}

    adapter._rpc = rpc
    receipt = adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "fixture")
    )
    assert receipt.message_id == "native-second"
    assert adapter.dispatch_status("modeling")[0]["state"] == "queued"
    from modeling_team.transport_mcp import RoutingError

    with pytest.raises(RoutingError, match="end this activity") as failure:
        adapter.terminal_report_blocked("modeling")
    assert failure.value.code == "runtime_input_pending"
    assert "queued=1" in str(failure.value)
    assert "unknown" not in str(failure.value)
    from modeling_team.transport_mcp import TeamTransportBroker, mcp_response

    import json
    from modeling_team.runner import TeamRunner

    runner = TeamRunner(repository_root=tmp_path, adapter=adapter)
    runner.run = SimpleNamespace(root=tmp_path)
    broker = TeamTransportBroker(
        tmp_path / "broker", set(),
        terminal_report_guard=adapter.terminal_report_blocked,
        transport_event_observer=runner._append_team_transport_event,
    )
    report = {"method": "tools/call", "params": {
        "name": "report_task_result", "arguments": {"status": "completed", "summary": "done"},
    }}
    with pytest.raises(RoutingError, match="queued=1"):
        mcp_response(report, broker=broker, agent_id="modeling")
    evidence = tmp_path / "evidence/team-transport-events.jsonl"
    assert evidence.exists(), "runtime input rejection must reach Host evidence"
    assert json.loads(evidence.read_text().splitlines()[-1])["category"] == "runtime_input_pending"
    assert "modeling" not in broker.results
    assert adapter.terminal_report_blocked("modeling", status="blocked") is False
    agent.projection.append(event(4, "turn/start", turn=2))
    agent.projection.append(claim(5))
    assert adapter.terminal_report_blocked("modeling") is False
    mcp_response(report, broker=broker, agent_id="modeling")
    assert json.loads(evidence.read_text().splitlines()[-1])["category"] == "terminal_report_accepted"
    assert broker.results["modeling"].status == "completed"


def test_pending_input_projection_identifies_the_role_without_raw_report_text():
    from modeling_team.delivery import _decision_event_metadata

    projected = _decision_event_metadata({"source": "team-transport-events.jsonl", "data": {
        "agent": "modeling", "tool": "report_task_result", "status": "rejected",
        "category": "runtime_input_pending", "ack": "not_applicable", "recorded_at_ns": 1,
    }})
    assert projected["data"]["agent_id"] == "modeling"
    assert projected["data"]["category"] == "runtime_input_pending"


def test_unknown_enqueue_has_no_invented_native_id_and_only_exact_response_reconciles(tmp_path):
    from types import SimpleNamespace
    from modeling_team.runtimes.dsh import DshRuntimeAdapter, DshRuntimeError, _DshAgent
    from modeling_team.runtimes.base import RuntimeDelivery

    adapter = DshRuntimeAdapter(repository_root=tmp_path)
    agent = _DshAgent("modeling", SimpleNamespace(role="modeling"), tmp_path, "s")
    agent.projection = DispatchProjection("s")
    agent.ready = True
    adapter.agents["modeling"] = agent

    def timeout(*args):
        error = DshRuntimeError("dsh-rpc-timeout")
        error.request_id = 7
        raise error

    adapter._rpc = timeout
    with pytest.raises(DshRuntimeError):
        adapter.send_message(
            "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "fixture")
        )
    record = adapter.dispatch_status("modeling")[0]
    assert (
        record["state"] == "unknown" and record["message_id"] is None and record["turn_id"] is None
    )
    from modeling_team.transport_mcp import RoutingError

    with pytest.raises(RoutingError, match="unknown=1") as failure:
        adapter.terminal_report_blocked("modeling")
    assert "Host reconciliation" in str(failure.value)
    assert "end this activity" not in str(failure.value)
    old_instance = agent.instance
    agent.instance = "different-process"
    adapter._reconcile_enqueue(agent, {"id": 7, "result": {"messageId": "wrong-instance"}})
    assert adapter.dispatch_status("modeling")[0]["message_id"] is None
    agent.instance = old_instance
    adapter._reconcile_enqueue(agent, {"id": 8, "result": {"messageId": "wrong-request"}})
    assert adapter.dispatch_status("modeling")[0]["message_id"] is None
    adapter._reconcile_enqueue(agent, {"id": 7, "result": {"messageId": "original-native-id"}})
    agent.projection.append(queued(0, "original-native-id"))
    assert adapter.dispatch_status("modeling")[0]["message_id"] == "original-native-id"
    assert adapter.dispatch_status("modeling")[0]["state"] == "queued"


def test_terminal_report_waits_for_original_inflight_dispatch_receipt(tmp_path):
    from types import SimpleNamespace
    from modeling_team.runtimes.dsh import DshRuntimeAdapter, _DshAgent
    from modeling_team.transport_mcp import RoutingError

    adapter = DshRuntimeAdapter(repository_root=tmp_path)
    agent = _DshAgent("modeling", SimpleNamespace(role="modeling"), tmp_path, "s")
    agent.projection = DispatchProjection("s")
    agent.dispatching = 1
    adapter.agents["modeling"] = agent
    with pytest.raises(RoutingError, match="in_flight=1") as failure:
        adapter.terminal_report_blocked("modeling")
    assert "original dispatch receipt" in str(failure.value)
    assert "Host reconciliation" not in str(failure.value)
    agent.dispatching = 0
    assert adapter.terminal_report_blocked("modeling") is False
