"""Regression cases from the retained DSH input-fixes run; no model calls."""
import copy
import json

import pytest

from modeling_team import host_ops
from modeling_team.delivery_host_actions import record_host_action_result, request_host_action
from modeling_team.tests.test_delivery_decision_input import ack, read
from modeling_team.tests.test_delivery_phase_threads import PhaseRuntime, ready
from modeling_team.tests.test_delivery_session import session
from modeling_team.tests.test_delivery_token_reduction import yield_args
from modeling_team.tests.test_delivery_wakeups import _dsh_wire, _events_page, observation
from modeling_team.tests.test_host_ops import _append_evidence, _issue_report, _make_run


@pytest.mark.parametrize("state", ["claimed", "settled"])
def test_native_recovery_effective_removes_the_host_issue_wait(tmp_path, state):
    repo, root = _make_run(tmp_path)
    _append_evidence(root, "issue-report", [_issue_report("t-run")])
    _append_evidence(root, "issue-control", [{
        "event": "recovery-effective", "issue_id": "issue-1", "reporter_id": "modeling",
        "control_epoch": 3, "dispatch_id": "dispatch-1",
        "native_dispatch": {"dispatch_id": "dispatch-1", "state": state},
    }])
    assert host_ops.get_pending_actions("t-run", repository_root=repo)["items"] == []
    assert host_ops.get_run_status("t-run", repository_root=repo)["first_blocker"] is None


@pytest.mark.parametrize("patch", [
    {"event": "recovery-submitted"}, {"control_epoch": 2}, {"reporter_id": "other"},
    {"native_dispatch": {"dispatch_id": "other", "state": "claimed"}},
    {"native_dispatch": {"dispatch_id": "dispatch-1", "state": "queued"}},
])
def test_unconfirmed_or_unbound_native_recovery_stays_pending(tmp_path, patch):
    repo, root = _make_run(tmp_path)
    _append_evidence(root, "issue-report", [_issue_report("t-run")])
    record = {"event": "recovery-effective", "issue_id": "issue-1",
              "reporter_id": "modeling", "control_epoch": 3, "dispatch_id": "dispatch-1",
              "native_dispatch": {"dispatch_id": "dispatch-1", "state": "claimed"}}
    _append_evidence(root, "issue-control", [{**record, **patch}])
    assert [v["type"] for v in host_ops.get_pending_actions(
        "t-run", repository_root=repo)["items"]] == ["issue_wait"]


@pytest.mark.parametrize("native_session,closed", [("reporter-session", True), ("other-session", False)])
def test_retained_native_recovery_without_reporter_field_uses_the_exact_thread_binding(
    tmp_path, native_session, closed
):
    repo, root = _make_run(tmp_path)
    report = {**_issue_report("t-run"), "thread_id": "reporter-session:process-1"}
    _append_evidence(root, "issue-report", [report])
    _append_evidence(root, "issue-control", [{
        "event": "recovery-effective", "issue_id": "issue-1", "control_epoch": 3,
        "dispatch_id": "dispatch-1", "native_dispatch": {
            "dispatch_id": "dispatch-1", "state": "claimed",
            "runtime_identity": native_session, "process_instance": "process-1"},
    }])
    pending = host_ops.get_pending_actions("t-run", repository_root=repo)["items"]
    assert (pending == []) is closed


def native_result(index, value, *, error=False):
    text = value if isinstance(value, str) else json.dumps(value)
    event = _dsh_wire("tool/result", {"turn": index, "step": index, "message": {
        "id": f"message-{index}", "toolCallId": f"call-{index}", "isError": error,
        "source": {"kind": "tool", "callId": f"call-{index}"},
        "content": [{"type": "text", "text": text}],
    }})
    event["byte_offset"] = index * 100
    event["data"]["frame"]["params"]["event"].update(seq=index, time=index * 1000)
    return event


def observe_event(host, index, event, *, operation="report_task_result"):
    raw = observation()
    events = [event]
    native = event.get("data", {}).get("frame", {}).get("params", {}).get("event", {})
    if native.get("type") == "tool/result":
        call = _dsh_wire("tool/call", {"callId": f"call-{index}", "name": operation})
        call["data"].update({key: event["data"][key]
                             for key in ("agent_id", "session_id", "process_instance")})
        call["byte_offset"] = event["byte_offset"] - 1
        events.insert(0, call)
    raw["runs"]["run"]["events"] = _events_page(events, next_cursor=str(index))
    return host.record_observation(raw)


@pytest.mark.parametrize("value,error", [
    ("Error: unconsumed DSH input; end this activity and receive queued inputs", True),
    ({"ok": False, "error": {"code": "material_forbidden", "message": "not addressed"}}, False),
])
def test_same_native_problem_not_native_call_identity_drives_wakeup(tmp_path, value, error):
    host = session(tmp_path)
    host.record_observation(observation())
    ack(host)
    assert observe_event(host, 1, native_result(1, value, error=error))
    ack(host)
    assert not observe_event(host, 2, native_result(2, value, error=error))
    assert observe_event(host, 3, native_result(3, {"ok": True}))
    ack(host)
    assert not observe_event(host, 4, native_result(4, {"ok": True}))
    assert observe_event(host, 5, native_result(5, value, error=error))
    ack(host)
    changed = value + " changed" if isinstance(value, str) else {
        "ok": False, "error": {"code": "material_forbidden", "message": "different target"}}
    assert observe_event(host, 6, native_result(6, changed, error=error))


def test_native_business_bindings_and_opaque_changes_are_not_folded(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    for index in (1, 2):
        assert observe_event(host, index, native_result(index, {
            "ok": False, "write_state": "unknown", "operation_id": "apply-1",
            "error": {"code": "unconfirmed"}}))
    assert observe_event(host, 3, native_result(3, "opaque payload A", error=True))
    assert observe_event(host, 4, native_result(4, "opaque payload B", error=True))


def test_unrelated_success_does_not_recover_the_current_native_problem(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    error = "Error: unconsumed DSH input"
    assert observe_event(host, 1, native_result(1, error, error=True))
    ack(host)
    assert not observe_event(host, 2, native_result(2, {"ok": True}), operation="send_team_message")
    assert not observe_event(host, 3, native_result(3, error, error=True))
    assert observe_event(host, 4, native_result(4, {"ok": True}))
    assert observe_event(host, 5, native_result(5, error, error=True))


def test_another_native_session_does_not_recover_the_current_problem(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    error = "Error: unconsumed DSH input"
    assert observe_event(host, 1, native_result(1, error, error=True))
    ack(host)
    other_session = native_result(2, {"ok": True})
    other_session["data"]["session_id"] = "other-session"
    assert not observe_event(host, 2, other_session)
    assert not observe_event(host, 3, native_result(3, error, error=True))


def test_tool_schema_error_parameter_is_not_a_runtime_failure(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    event = _dsh_wire("request/header", {"header": {"tools": [{"parameters": {
        "properties": {"error": {"type": "string"}}}}]}, "reason": {"kind": "initial"}})
    assert not observe_event(host, 1, event)
    event = copy.deepcopy(event)
    event["byte_offset"] = 100
    event["data"]["frame"]["params"]["event"]["data"]["reason"] = {"kind": "error"}
    assert observe_event(host, 2, event)


def test_routine_header_does_not_hide_errors_outside_the_tool_catalog(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    event = _dsh_wire("request/header", {"header": {"tools": []},
                      "error": {"code": "request_failed"}})
    assert observe_event(host, 1, event)


def test_initialization_result_does_not_hide_a_plugin_failure(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    event = {"source": "dsh-wire.jsonl", "byte_offset": 0, "data": {"agent_id": "modeling",
             "frame": {"jsonrpc": "2.0", "id": 1, "result": {
                 "plugins": [{"name": "tooling", "status": "failed", "error": "connection failed"}],
                 "tools": []}}}}
    assert observe_event(host, 1, event)


@pytest.mark.parametrize("result", [
    {"effectiveBinding": {"model": "test"}, "serverInfo": {"name": "dsh"}},
    {"plugins": [], "tools": [{"parameters": {"properties": {"error": {"type": "string"}}}}]},
])
def test_known_successful_native_initialization_does_not_wake(tmp_path, result):
    host = session(tmp_path)
    host.record_observation(observation())
    event = {"source": "dsh-wire.jsonl", "byte_offset": 0, "data": {"agent_id": "modeling",
             "frame": {"jsonrpc": "2.0", "id": 1, "result": result}}}
    assert not observe_event(host, 1, event)
    event = copy.deepcopy(event)
    event["byte_offset"] = 100
    event["data"]["frame"] = {"jsonrpc": "2.0", "id": 2, "error": {"code": "unavailable"}}
    assert observe_event(host, 2, event)


def test_configured_acceptance_handoff_is_actionable_in_the_current_input(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.record_observation(raw, force_delivery=True)
    packet = ack(host)
    hint = packet["core"]["phase_thread_handoff"]
    assert hint["thread_boundary"] == {
        "phase": "acceptance", "run_id": "run", "request_ids": ["handoff"]}
    assert hint["next_action"] == "include thread_boundary in yield_delivery, retain effective decisions, then end this turn"
    host.config["phase_thread_boundaries"] = []
    host.record_observation(raw, force_delivery=True)
    assert "phase_thread_handoff" not in ack(host)["core"]


def test_production_hint_names_consumed_freeze_and_notification_candidates(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.config["phase_thread_boundaries"] = ["production"]
    root = tmp_path / "run"
    rows = [{"request_id": "freeze", "action": "cq_freeze", "content_digest": "f"},
            {"request_id": "notify", "action": "instruction", "content_digest": "n"}]
    (root / "control/host-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    receipts = root / "evidence/outer-input-receipts.jsonl"
    receipts.write_text(json.dumps({**rows[0], "outcome": "accepted"}) + "\n")
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw, force_delivery=True)
    assert "phase_thread_handoff" not in ack(host)["core"]
    receipts.write_text("".join(json.dumps({**r, "outcome": "accepted"}) + "\n" for r in rows))
    host.record_observation(raw)
    packet = ack(host)
    hint = packet["core"]["phase_thread_handoff"]
    assert hint["thread_boundary"] == {"phase": "production", "run_id": "run", "request_ids": ["freeze"]}
    assert hint["notification_request_ids"] == ["notify"]
    args = yield_args(packet["input_id"])
    args["thread_boundary"] = {**hint["thread_boundary"], "request_ids": ["freeze", "notify"]}
    assert host.call_tool("yield_delivery", args)["ok"]
    assert host.maybe_switch_phase_thread(PhaseRuntime())
    host.record_observation(raw, force_delivery=True)
    assert "phase_thread_handoff" not in ack(host)["core"]


def test_failed_phase_switch_can_offer_a_new_explicit_handoff(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    runtime = PhaseRuntime()

    def fail():
        raise RuntimeError("thread creation failed")

    runtime.new_thread = fail
    assert not host.maybe_switch_phase_thread(runtime)
    assert host.phase_thread_history[-1]["status"] == "failed"
    host.record_observation(raw, force_delivery=True)
    assert ack(host)["core"]["phase_thread_handoff"]["thread_boundary"]["phase"] == "acceptance"


def test_completed_production_does_not_offer_its_earlier_freeze_boundary(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.config["phase_thread_boundaries"] = ["production"]
    root = tmp_path / "run"
    rows = [{"request_id": "freeze", "action": "cq_freeze", "content_digest": "f"},
            {"request_id": "notify", "action": "instruction", "content_digest": "n"},
            {"request_id": "handoff", "action": "cq_handoff_complete", "content_digest": "h"}]
    (root / "control/host-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (root / "evidence/outer-input-receipts.jsonl").write_text("".join(
        json.dumps({**r, "outcome": "accepted"}) + "\n" for r in rows))
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw, force_delivery=True)
    assert "phase_thread_handoff" not in ack(host)["core"]


def test_registered_private_host_result_reference_can_be_copied_unchanged(tmp_path):
    host = session(tmp_path)
    host.run_ids.add("run")
    request_host_action(host.session_root, host.session_id, {"run"}, "user-test", {
        "request_id": "repair-1", "run_id": "run", "kind": "platform_repair", "bindings": {}})
    original = host.session_root / "host-results/result.json"
    original.parent.mkdir(exist_ok=True)
    original.write_text('{"status":"completed"}\n')
    result = record_host_action_result(host.session_root, "repair-1", "completed", original)
    reference = result["result_ref"]
    source_ref = {**reference, "scope": "file"}
    copied = copy.deepcopy(source_ref)
    data = read(host, reference["path"], source_ref=source_ref,
                selection={"kind": "json", "paths": [["status"]]})
    assert data["ok"]
    assert json.loads(data["data"]["text"])["fields"][0]["value"] == "completed"
    assert source_ref == copied
    wrong = {**source_ref, "path": "host-results/another-result.json"}
    assert not read(host, reference["path"], source_ref=wrong,
                    selection={"kind": "bytes", "offset": 0})["ok"]
