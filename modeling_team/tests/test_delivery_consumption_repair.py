"""Delivery consumption regressions with actual views and native turn receipts."""

import copy
import importlib
import json
from pathlib import Path

import pytest

from modeling_team.delivery import DeliverySession
from modeling_team.tests.test_delivery_decision_input import ack, read
from modeling_team.tests.test_delivery_paged_phase_handoff import ready
from modeling_team.tests.test_delivery_session import ROOT, session
from modeling_team.tests.test_delivery_wakeups import _events_page, observation


def paged_input(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "Business scope. " * 6000
    host.record_observation(raw)
    first = ack(host)
    assert first["page"]["offset"] == 0 and not first["coverage"]["complete"]
    return host, raw, first


def read_remaining(host, first):
    ref = first["read_remaining"]
    while True:
        result = read(host, ref["path"], source_ref=ref["source_ref"],
                      selection=ref["selection"])
        assert result["ok"], result
        if result["data"]["read_complete"]:
            return
        ref = {"path": result["data"]["path"], **result["data"]["continuation"]}


def test_successful_native_turn_confirms_supplemental_pages_and_keeps_new_state(tmp_path):
    host, raw, first = paged_input(tmp_path)
    read_remaining(host, first)
    assert host._pending_decisions[0]["offset"] == 12000
    changed = copy.deepcopy(raw)
    changed["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    host.record_observation(changed)

    host.record_turn_completion("completed")

    assert first["input_id"] not in {item["input_id"] for item in host._pending_decisions}
    packet = host._model_observation()
    assert packet["input_id"] != first["input_id"]
    assert "unknown" in json.dumps(packet)
    restored = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert first["input_id"] not in {item["input_id"] for item in restored._pending_decisions}


@pytest.mark.parametrize("status", ["failed", "interrupted", None])
def test_unsuccessful_turn_never_confirms_supplemental_pages(tmp_path, status):
    host, _, first = paged_input(tmp_path)
    read_remaining(host, first)
    host.record_turn_completion(status)
    host.record_turn_completion("completed")  # A later turn cannot confirm the failed one.
    assert host._pending_decisions[0]["input_id"] == first["input_id"]
    assert host._pending_decisions[0]["offset"] == 12000


def test_partial_read_does_not_skip_an_unread_gap_or_ack_unknown_delivery(tmp_path):
    host, _, first = paged_input(tmp_path)
    ref = first["read_original"]
    result = read(host, ref["path"], source_ref=ref["source_ref"],
                  selection={"kind": "bytes", "offset": 30000})
    assert result["ok"]
    host.record_turn_completion("completed")
    assert host._pending_decisions[0]["offset"] == 12000
    read_remaining(host, first)
    host._pending_decisions[0]["delivery_status"] = "unknown"
    host.record_turn_completion("completed")
    assert host._pending_decisions[0]["delivery_status"] == "unknown"
    assert host._pending_decisions[0]["offset"] == 12000


@pytest.mark.parametrize("case", ["json_selection", "changed_view", "process_recovery"])
def test_only_the_exact_confirmed_byte_view_advances_reception(tmp_path, case):
    host, _, first = paged_input(tmp_path)
    ref = first["read_original"]
    if case == "json_selection":
        result = read(host, ref["path"], source_ref=ref["source_ref"],
                      selection={"kind": "json", "paths": [["core"]]})
        assert result["ok"]
    else:
        read_remaining(host, first)
    if case == "changed_view":
        path = Path(ref["path"])
        path.write_bytes(path.read_bytes() + b"\n")
    elif case == "process_recovery":
        host = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    host.record_turn_completion("completed")
    assert host._pending_decisions[0]["offset"] == 12000


def test_new_run_delta_does_not_repeat_the_same_event_body(tmp_path):
    host = session(tmp_path)
    host.record_observation({"runs": {}, "operations": {}, "repair_verifications": {}})
    ack(host)
    raw = observation()
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "outer-input-receipts.jsonl", "byte_offset": 1,
        "data": {"request_id": "unique-receipt", "outcome": "accepted",
                 "detail": "UNIQUE-RECEIPT-BODY"},
    }], next_cursor="new")
    host.record_observation(raw)
    packet = ack(host)
    assert json.dumps(packet).count("UNIQUE-RECEIPT-BODY") == 1


@pytest.mark.parametrize(("source", "data"), [
    ("auth-barrier.jsonl", {"event": "provider_proxy_ready", "agent_id": "modeling"}),
    ("staged-decisions.jsonl", {"event": "directories-registered"}),
    ("app-server-events.jsonl", {"method": "thread/started", "params": {"thread": {"id": "native"}}}),
])
def test_routine_startup_records_do_not_wake_but_their_errors_do(tmp_path, source, data):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    ack(host)
    event = {"source": source, "byte_offset": 1, "data": data}
    raw["runs"]["run"]["events"] = _events_page([event], next_cursor="startup")
    assert not host.record_observation(raw)
    event = copy.deepcopy(event)
    event["byte_offset"] = 2
    event["data"]["error"] = {"code": "startup_failed"}
    raw["runs"]["run"]["events"] = _events_page([event], next_cursor="error")
    assert host.record_observation(raw)
    assert "startup_failed" in json.dumps(ack(host))


def test_completed_closure_is_not_an_unfinished_action(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.work_result = "Completed independent acceptance"
    host.activity = "read_only_wait"
    raw["operations"]["op"]["data"].update(work_state="completed", report_binding={"valid": True})
    raw["runs"]["run"]["pending"]["data"]["items"] = [{
        "type": "cq_acceptance_closure", "status": "completed", "id": "attempt-0001",
        "available_actions": [], "bindings": {"cq_verdict": "pass"},
    }]
    host.record_observation(raw)
    assert host._completed_observations_are_quiet()

    raw["runs"]["run"]["pending"]["data"]["items"][0]["status"] = "pending"
    host.record_observation(raw)
    assert not host._completed_observations_are_quiet()


def test_known_wait_binding_error_offers_the_exact_request_wait(tmp_path, monkeypatch):
    from modeling_team.tests.test_delivery_cost_regressions import bound_run
    from modeling_team.tests.test_delivery_token_reduction import yield_args

    host, root = bound_run(tmp_path, monkeypatch)
    (root / "control/host-requests.jsonl").write_text(json.dumps({
        "request_id": "acceptance-close", "action": "cq_acceptance_complete",
        "content_digest": "close-digest",
    }) + "\n")
    host.record_observation(observation())
    args = yield_args(host._model_observation()["input_id"])
    args["waiting_for"] = [{"run_id": "run", "request_id": "acceptance-close",
                            "operation_id": "run", "condition": "closure receipt"}]
    result = host.call_tool("yield_delivery", args)
    assert not result["ok"]
    assert result["error"]["corrected_waiting_for"] == [{
        "run_id": "run", "request_id": "acceptance-close", "condition": "closure receipt",
    }]


@pytest.mark.parametrize("runtime", ["codex", "dsh", "provider_failure"])
def test_program_confirms_reads_only_on_successful_native_completion(tmp_path, monkeypatch, runtime):
    module = importlib.import_module("modeling_team.delivery")
    seen = []
    original = module.DeliverySession.record_turn_completion
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub, _StubNativeRuntime

    def record(self, status):
        seen.append(status)
        return original(self, status)

    monkeypatch.setattr(module.DeliverySession, "record_turn_completion", record)
    if runtime != "codex":
        class Native(_StubNativeRuntime):
            def poll(self, timeout=0):
                events = super().poll(timeout)
                if runtime == "provider_failure" and events:
                    return [{"event": "provider_error", "status": "failed"}, *events]
                return [{"event": "activity_ended", "status": "ended",
                         "reason": {"kind": "completed"}} if event["event"] == "turn_completed"
                        else event for event in events]

        original_run = module._run_delivery

        def run(config, **kwargs):
            monkeypatch.setattr(module, "DeliveryRuntime", lambda **kw: Native())
            return original_run(config, **kwargs)

        monkeypatch.setattr(module, "_run_delivery", run)
    if runtime == "provider_failure":
        with pytest.raises(RuntimeError, match="Delivery native turn failed"):
            _run_delivery_with_stub(tmp_path, monkeypatch, [])
        assert seen == ["failed"]
        return
    _, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [])
    assert result == 2  # stdin EOF, after the real native completion observation.
    assert "completed" in seen
