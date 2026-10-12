"""R4.3-005 decision-driven observation, without a live semantic run."""
import copy
import json

import pytest

from modeling_team.tests.test_delivery_session import session


def _events_page(events, *, next_cursor, has_more=False, limitations=("none",)):
    """One incremental ``get_run_events`` page as Delivery's tool layer wraps it."""
    return {"ok": True, "data": {
        "run_id": "run", "events": events, "next_cursor": next_cursor,
        "has_more": has_more, "ordering": "recorded_at-approximate",
        "complete": True, "limitations": list(limitations),
    }}


def _app_server_delta(byte_offset, line_no, delta, recorded_at="2026-10-12T09:00:00Z"):
    """One app-server notification line: the raw token/reasoning delta stream."""
    return {"source": "app-server-events.jsonl", "line_no": line_no,
            "byte_offset": byte_offset, "recorded_at": recorded_at,
            "data": {"agent_id": "modeling", "method": "item/agentMessage/delta",
                     "has_request_id": False, "param_keys": ["delta", "itemId"],
                     "params": {"delta": delta}}}


def _receipt_event(byte_offset, request_id, recorded_at="2026-10-12T09:00:05Z"):
    """One request receipt line from evidence/outer-input-receipts.jsonl."""
    return {"source": "outer-input-receipts.jsonl", "line_no": 1,
            "byte_offset": byte_offset, "recorded_at": recorded_at,
            "data": {"request_id": request_id, "ack_type": "accepted",
                     "content_digest": "sha256:" + "0" * 16, "recorded_at": recorded_at}}


def observation():
    return {
        "runs": {"run": {
            "status": {"ok": True, "data": {
                "observed_at": "t1", "events_cursor": "cursor1",
                "recorded_state": {"state": "RUNNING"},
                "stage": {"phase": "modeling", "recorded_at": "t1", "ordinal": 1},
                "last_verifiable_activity": {"recorded_at": "t1"},
                "semantic_progress": {"staged_decision_count": 1},
                "liveness": {"process_observation": {"observed_at": "t1", "pid_alive": True}},
            }},
            "pending": {"ok": True, "data": {"observed_at": "t1", "items": [
                {"id": "question-1", "bindings": {"content_version": 1}}
            ]}},
            "events": _events_page([], next_cursor="cursor-1"),
            "request_ledger": {"ok": True, "data": {"text": "request-1"}},
        }},
        "operations": {"op": {"ok": True, "data": {
            "status": "running", "report_status": "no_new_report", "log_tails": {"stdout": "log1"},
            "stdout_tail": "log1", "stdout_bytes": 1,
        }}},
        "repair_verifications": {},
    }


def test_noise_is_retained_without_repeated_model_wakeup(tmp_path):
    host = session(tmp_path)
    first = observation()
    assert host.record_observation(first)
    update = copy.deepcopy(first)
    status = update["runs"]["run"]["status"]["data"]
    status.update(observed_at="t2", events_cursor="cursor2", last_verifiable_activity={"recorded_at": "t2"})
    status["stage"].update(recorded_at="t2", ordinal=2)
    status["semantic_progress"]["staged_decision_count"] = 99
    status["liveness"]["process_observation"]["observed_at"] = "t2"
    update["runs"]["run"]["pending"]["data"]["observed_at"] = "t2"
    update["operations"]["op"]["data"].update(stdout_tail="log2", stdout_bytes=99,
                                                  log_tails={"stdout": "log2"})
    assert not host.record_observation(update)
    result = host.call_tool("read_delivery_artifact", {"path": str(host.session_root / "observation.json")})
    stored = json.loads(result["data"]["text"])
    assert stored["data"] == update
    assert stored["observation_count"] == 2 and stored["wake_count"] == 1


@pytest.mark.parametrize("change", ["question", "version", "phase", "terminal", "failure",
                                   "request", "receipt", "report", "liveness", "verification"])
def test_actionable_updates_wake_even_with_same_counts(tmp_path, change):
    host = session(tmp_path)
    before = observation()
    assert host.record_observation(before)
    after = copy.deepcopy(before)
    run = after["runs"]["run"]
    if change == "question":
        run["pending"]["data"]["items"][0]["id"] = "question-2"
    elif change == "version":
        run["pending"]["data"]["items"][0]["bindings"]["content_version"] = 2
    elif change == "phase":
        run["status"]["data"]["stage"]["phase"] = "review"
    elif change == "terminal":
        run["status"]["data"]["recorded_state"]["state"] = "SETTLED"
    elif change == "failure":
        run["status"]["data"]["first_blocker"] = {"kind": "runtime_failure", "event": "failed"}
    elif change == "request":
        run["request_ledger"]["data"]["text"] = "request-2"
    elif change == "receipt":
        run["events"]["data"]["events"] = [_receipt_event(0, "req-9")]
    elif change == "report":
        after["operations"]["op"]["data"]["report_status"] = "new_report_bound"
    elif change == "liveness":
        run["status"]["data"]["liveness"]["process_observation"]["pid_alive"] = False
    elif change == "verification":
        after["repair_verifications"] = {"repair": {"ok": True, "data": {"result": {"status": "verified"}}}}
    assert host.record_observation(after)
    assert not host.record_observation(after)


def test_observation_tool_failures_are_decisions(tmp_path):
    host = session(tmp_path)
    before = observation()
    host.record_observation(before)
    before["runs"]["run"]["status"] = {"ok": False, "error": {"code": "unavailable"}}
    assert host.record_observation(before)


def test_actionable_host_observation_steers_busy_turn(tmp_path, monkeypatch):
    import importlib
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", lambda self: observation())
    runtime, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [], run_ids=["bound"])
    assert result == 2
    assert len(runtime.steered) == 1
    assert json.loads(runtime.steered[0])["kind"] == "host_observation"
    assert runtime.events.index("steer") < runtime.events.index("turn_completed")


def test_observation_steer_race_keeps_decision_for_next_turn(tmp_path, monkeypatch):
    import importlib
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", lambda self: observation())
    runtime, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [], run_ids=["bound"], steer_failures=1)
    assert result == 2
    assert runtime.steer_attempts == 1
    assert json.loads(runtime.sent[1])["kind"] == "host_observation"


def test_token_delta_pages_and_cursor_advances_do_not_wake(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    second = observation()
    second["runs"]["run"]["events"] = _events_page(
        [_app_server_delta(0, 1, "\u6b63\u5728\u6838\u5bf9"), _app_server_delta(96, 2, "\u6620\u5c04")],
        next_cursor="cursor-2", has_more=True)
    assert not host.record_observation(second)
    third = observation()
    third["runs"]["run"]["events"] = _events_page(
        [_app_server_delta(192, 3, "\u5b8c\u6210", recorded_at="2026-10-12T09:00:01Z")],
        next_cursor="cursor-3")
    assert not host.record_observation(third)
    result = host.call_tool("read_delivery_artifact",
                            {"path": str(host.session_root / "observation.json")})
    stored = json.loads(result["data"]["text"])
    # The raw delta stream and pagination metadata stay on disk, readable by
    # Delivery on demand; only the wakeup fingerprint ignored them.
    page = stored["data"]["runs"]["run"]["events"]["data"]
    assert page["events"][0]["data"]["params"]["delta"] == "\u5b8c\u6210"
    assert page["next_cursor"] == "cursor-3" and page["has_more"] is False
    assert stored["observation_count"] == 3 and stored["wake_count"] == 1


def test_new_decision_event_wakes_once_and_page_settle_stays_quiet(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    arrival = observation()
    arrival["runs"]["run"]["events"] = _events_page(
        [_receipt_event(0, "req-9"), _app_server_delta(2048, 7, "\u7ee7\u7eed")],
        next_cursor="cursor-2")
    assert host.record_observation(arrival)
    # At-least-once re-delivery of the same parked line is not a new decision.
    redelivered = observation()
    redelivered["runs"]["run"]["events"] = _events_page(
        [_receipt_event(0, "req-9")], next_cursor="cursor-2")
    assert not host.record_observation(redelivered)
    # The drained follow-up page (event consumed, cursor advanced) is the same
    # decision as the page that carried the event, not one more wakeup.
    drained = observation()
    drained["runs"]["run"]["events"] = _events_page([], next_cursor="cursor-3")
    assert not host.record_observation(drained)
    stored = json.loads(host.call_tool("read_delivery_artifact", {
        "path": str(host.session_root / "observation.json")})["data"]["text"])
    assert stored["observation_count"] == 4 and stored["wake_count"] == 2


def test_truncated_placeholder_and_events_failure_stay_decisions(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    placeholder = {"source": "settled.jsonl", "line_no": 4, "byte_offset": 4096,
                   "truncated": True, "byte_length": 262144}
    truncated = observation()
    truncated["runs"]["run"]["events"] = _events_page(
        [placeholder], next_cursor="cursor-2",
        limitations=("settled.jsonl line 4 exceeds the 262144-byte event cap "
                     "and is truncated",))
    assert host.record_observation(truncated)
    # The page-level limitation only restates the placeholder event itself;
    # neither a re-read without it nor the drained page wakes again.
    repeat = observation()
    repeat["runs"]["run"]["events"] = _events_page([placeholder], next_cursor="cursor-2")
    assert not host.record_observation(repeat)
    assert not host.record_observation(observation())
    # A failed incremental events read stays a decision, like other tool failures.
    failed = observation()
    failed["runs"]["run"]["events"] = {"ok": False, "error": {
        "code": "run_missing", "message": "bound run is unavailable"}}
    assert host.record_observation(failed)


def test_new_evidence_file_listing_alone_does_not_wake(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    grown = observation()
    grown["runs"]["run"]["status"]["data"]["evidence_refs"] = [
        {"path": "evidence/app-server-events.jsonl", "readable": True},
        {"path": "evidence/runtime-failure.jsonl", "readable": True},
    ]
    assert not host.record_observation(grown)
