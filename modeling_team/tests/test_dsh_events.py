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
    assert adapter.terminal_report_blocked("modeling", status="blocked") is False
    agent.projection.append(event(4, "turn/start", turn=2))
    agent.projection.append(claim(5))
    assert adapter.terminal_report_blocked("modeling") is False


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
