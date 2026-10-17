"""R4.3-005 decision-driven observation, without a live semantic run."""
import copy
import importlib
import json
from pathlib import Path

import pytest

from modeling_team.tests.test_delivery_session import (
    _StubNativeRuntime, _run_delivery_with_stub, session,
)

ROOT = Path(__file__).resolve().parents[2]


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


def _provider_attempt(byte_offset, event, status, http_status=None):
    return {"source": "provider-attempts.jsonl", "byte_offset": byte_offset,
            "data": {"schema_version": "model-usage-capture/v1", "event": event,
                     "status": status, "http_status": http_status, "request_id": "request-1"}}


def test_provider_success_and_inflight_receipts_do_not_wake(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    for index, event in enumerate([
        _provider_attempt(0, "attempt_start", "unfinished"),
        _provider_attempt(256, "attempt_end", "completed", 200),
    ], 1):
        updated = observation()
        updated["runs"]["run"]["events"] = _events_page([event], next_cursor=f"cursor-{index + 1}")
        assert not host.record_observation(updated)
        stored = json.loads((host.session_root / "observation.json").read_text())
        assert stored["data"] == updated
        assert stored["wake_count"] == 1


def test_provider_noise_is_excluded_when_business_pending_wakes(tmp_path):
    host = session(tmp_path)
    assert host.record_observation(observation())
    assert host._dispatch_observation(_StubNativeRuntime(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    updated = observation()
    updated["runs"]["run"]["pending"]["data"]["items"][0]["id"] = "question-2"
    updated["runs"]["run"]["events"] = _events_page([
        _provider_attempt(0, "attempt_start", "unfinished"),
        _provider_attempt(256, "attempt_end", "completed", 200),
        _receipt_event(0, "req-9"),
    ], next_cursor="cursor-2")
    assert host.record_observation(updated)
    payload = host._model_observation()
    run = payload["runs"]["run"]
    assert run["pending"]["data"]["items"][0]["id"] == "question-2"
    assert [item["source"] for item in run["events"]["data"]["events"]] == [
        "outer-input-receipts.jsonl"]
    assert payload["raw_observation"]["excluded_noise_event_records"] == 2


@pytest.mark.parametrize("status,http_status", [
    ("transport_error", None), ("http_error", 429), ("stream_error", 200),
    ("client_disconnected", 200), ("completed", 500), (None, 200),
])
def test_provider_failures_and_unknown_receipts_still_wake(tmp_path, status, http_status):
    host = session(tmp_path)
    assert host.record_observation(observation())
    assert host._dispatch_observation(_StubNativeRuntime(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    event = _provider_attempt(0, "attempt_end", status, http_status)
    updated = observation()
    updated["runs"]["run"]["events"] = _events_page([event], next_cursor="cursor-2")
    assert host.record_observation(updated)
    assert event in host._model_observation()["runs"]["run"]["events"]["data"]["events"]
    assert not host.record_observation(updated)


@pytest.mark.parametrize("event", [
    {"source": "provider-attempts.jsonl", "byte_offset": 0, "corrupt": True},
    {"source": "provider-attempts.jsonl", "byte_offset": 0, "truncated": True},
    {"source": "runtime-failure.jsonl", "byte_offset": 0, "data": {"event": "failed"}},
])
def test_provider_corruption_and_runtime_failures_still_wake(tmp_path, event):
    host = session(tmp_path)
    assert host.record_observation(observation())
    assert host._dispatch_observation(_StubNativeRuntime(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    updated = observation()
    updated["runs"]["run"]["events"] = _events_page([event], next_cursor="cursor-2")
    assert host.record_observation(updated)
    assert event in host._model_observation()["runs"]["run"]["events"]["data"]["events"]


# --- R4.3-013: the delivered payload never carries raw app-server records ----

_HUGE_DELTA = "\u6bb5" * 204_007


def _huge_delta_observation():
    """One observation whose events page replays a huge native app delta.

    The real resume failure carried single app-server-events records of
    ~204007 characters; the page here mirrors that shape and keeps one real
    receipt event beside it.
    """
    raw = observation()
    raw["runs"]["run"]["events"] = _events_page(
        [_app_server_delta(0, 1, _HUGE_DELTA), _receipt_event(620_021, "req-9")],
        next_cursor="cursor-9")
    return raw


def _prepare_stub_repository(tmp_path):
    """Mirror the minimal offline repository used by _run_delivery_with_stub."""
    import shutil
    profiles = tmp_path / 'modeling_team/model-profiles'
    profiles.mkdir(parents=True)
    shutil.copyfile(ROOT / 'modeling_team/model-profiles/openai-sol-medium.yaml',
                    profiles / 'openai-sol-medium.yaml')
    package = tmp_path / 'modeling_team/agent-packages/delivery'
    package.mkdir(parents=True)
    (package / 'instructions.md').write_text('stub delivery instructions')
    skill = tmp_path / 'modeling_team/skills/delivery'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('stub delivery skill')


def _run_resume_with_stub(tmp_path, monkeypatch, observations, *, run_ids, **stub_kwargs):
    """Drive ``_run_delivery`` with ``resume=True`` against a prepared session.

    ``observations`` is one observation or a per-call sequence; the session is
    created once beforehand so the resumed process restores its original
    authorization and model binding.
    """
    import os
    import sys
    module = importlib.import_module("modeling_team.delivery")
    _prepare_stub_repository(tmp_path)
    config = {'session_id': 'steer-probe', 'model_profile': 'openai-sol-medium',
              'authorization_reference': 'user-test', 'allowed_sources': [],
              'allowed_operations': ['read'], 'run_ids': list(run_ids)}
    session_root = tmp_path / 'workspaces/delivery-sessions/steer-probe'
    module.DeliverySession(repository_root=tmp_path, session_root=session_root,
                           config=config, resume=False)
    sequence = [copy.deepcopy(item) for item in (
        observations if isinstance(observations, list) else [observations])]
    calls = {"count": 0}

    def fake_observe(self):
        index = min(calls["count"], len(sequence) - 1)
        calls["count"] += 1
        return copy.deepcopy(sequence[index])

    monkeypatch.setattr(module.DeliverySession, "observe", fake_observe)
    stub = _StubNativeRuntime(**stub_kwargs)
    monkeypatch.setattr(module, 'DeliveryRuntime', lambda **kwargs: stub)
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(sys, 'stdin', os.fdopen(read_fd, 'r'))
    os.close(write_fd)
    result = module._run_delivery(config, repository_root=tmp_path, resume=True)
    return stub, result, calls["count"]


def test_resume_persists_full_observation_then_delivers_filtered_state(tmp_path, monkeypatch):
    raw = _huge_delta_observation()
    settled = copy.deepcopy(raw)
    settled["runs"]["run"]["status"]["data"]["recorded_state"]["state"] = "SETTLED"
    stub, result, observe_calls = _run_resume_with_stub(
        tmp_path, monkeypatch, [raw, settled], run_ids=["bound"])
    assert result == 2
    # One startup observe fed both the stored record and the delivered state;
    # the busy observation and the final idle observation follow.
    assert observe_calls == 3
    resume_message = json.loads(stub.sent[0])
    assert resume_message["kind"] == "delivery_resume"
    state = resume_message["observed_state"]
    delivered = json.dumps(state, ensure_ascii=False)
    assert _HUGE_DELTA not in delivered
    assert len(delivered) < 40_000
    events = state["runs"]["run"]["events"]["data"]["events"]
    assert [event["source"] for event in events] == ["outer-input-receipts.jsonl"]
    assert events[0] == _receipt_event(620_021, "req-9")
    assert state["runs"]["run"]["events"]["data"]["next_cursor"] == "cursor-9"
    assert state["raw_observation"]["excluded_noise_event_records"] == 1
    # The busy steer uses the same filtered view.
    steered = json.loads(stub.steered[0])
    assert steered["kind"] == "host_observation"
    assert _HUGE_DELTA not in json.dumps(steered, ensure_ascii=False)
    # The complete record was persisted before delivery, at the referenced path.
    raw_ref = state["raw_observation"]
    assert raw_ref["reader"] == "read_delivery_artifact"
    stored = json.loads(Path(raw_ref["path"]).read_text())
    page = stored["data"]["runs"]["run"]["events"]["data"]
    assert page["events"][0]["data"]["params"]["delta"] == _HUGE_DELTA
    assert stored["observation_count"] == 3 and stored["wake_count"] == 2


def test_busy_steer_payload_excludes_only_raw_app_server_records(tmp_path, monkeypatch):
    raw = _huge_delta_observation()
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", lambda self: copy.deepcopy(raw))
    runtime, result, _record = _run_delivery_with_stub(
        tmp_path, monkeypatch, [], run_ids=["bound"])
    assert result == 2
    steered = json.loads(runtime.steered[0])
    assert steered["kind"] == "host_observation"
    delivered = json.dumps(steered, ensure_ascii=False)
    assert _HUGE_DELTA not in delivered
    page = steered["data"]["runs"]["run"]["events"]["data"]
    assert [event["source"] for event in page["events"]] == ["outer-input-receipts.jsonl"]
    # Decisions stay byte-complete: receipt, pending item, request ledger.
    assert page["events"][0] == _receipt_event(620_021, "req-9")
    assert (steered["data"]["runs"]["run"]["pending"]["data"]["items"]
            == observation()["runs"]["run"]["pending"]["data"]["items"])
    assert "request_ledger" not in steered["data"]["runs"]["run"]
    assert steered["data"]["runs"]["run"]["requests"]["data"]["coverage"]["complete"] is False
    assert steered["data"]["raw_observation"]["excluded_noise_event_records"] == 1


def test_idle_send_after_steer_race_carries_no_raw_app_server_records(tmp_path, monkeypatch):
    raw = _huge_delta_observation()
    raw["runs"]["run"]["events"]["data"]["events"] =         raw["runs"]["run"]["events"]["data"]["events"][:1]
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", lambda self: copy.deepcopy(raw))
    runtime, result, _record = _run_delivery_with_stub(
        tmp_path, monkeypatch, [], run_ids=["bound"], steer_failures=1)
    assert result == 2
    assert runtime.steered == [] and runtime.steer_attempts == 1
    sent = json.loads(runtime.sent[1])
    assert sent["kind"] == "host_observation"
    delivered = json.dumps(sent, ensure_ascii=False)
    assert _HUGE_DELTA not in delivered
    assert sent["data"]["runs"]["run"]["events"]["data"]["events"] == []
    assert sent["data"]["raw_observation"]["excluded_noise_event_records"] == 1
    assert sent["data"]["raw_observation"]["path"].endswith("observation.json")


def test_raw_observation_reference_is_readable_on_demand(tmp_path):
    host = session(tmp_path)
    raw = _huge_delta_observation()
    host.record_observation(raw)
    payload = host._model_observation(raw)
    assert _HUGE_DELTA not in json.dumps(payload, ensure_ascii=False)
    result = host.call_tool("read_delivery_artifact",
                            {"path": payload["raw_observation"]["path"]})
    assert result["ok"]
    stored = json.loads(result["data"]["text"])
    page = stored["data"]["runs"]["run"]["events"]["data"]
    assert page["events"][0]["data"]["params"]["delta"] == _HUGE_DELTA
    assert page["events"][1]["data"]["request_id"] == "req-9"


def test_model_observation_keeps_decisions_complete_and_failures_untouched(tmp_path):
    host = session(tmp_path)
    raw = observation()
    placeholder = {"source": "settled.jsonl", "line_no": 4, "byte_offset": 4096,
                   "truncated": True, "byte_length": 262144}
    raw["runs"]["run"]["events"] = _events_page(
        [placeholder, _receipt_event(620_021, "req-9"), _app_server_delta(0, 1, "delta")],
        next_cursor="cursor-9", limitations=("settled.jsonl line 4 is truncated",))
    raw["runs"]["run"]["status"] = {"ok": False,
                                    "error": {"code": "unavailable", "message": "down"}}
    payload = host._model_observation(raw)
    page = payload["runs"]["run"]["events"]["data"]
    assert [event["source"] for event in page["events"]] == [
        "settled.jsonl", "outer-input-receipts.jsonl"]
    assert page["events"][0] == placeholder
    assert page["limitations"] == ["settled.jsonl line 4 is truncated"]
    assert page["next_cursor"] == "cursor-9"
    assert payload["runs"]["run"]["status"] == {
        "ok": False, "error": {"code": "unavailable", "message": "down"}}
    assert payload["runs"]["run"]["pending"]["data"]["items"] == raw["runs"]["run"]["pending"]["data"]["items"]
    assert "request_ledger" not in payload["runs"]["run"]
    assert json.loads((host.session_root / "observation.json").read_text())["data"] == raw
    host._dispatch_observation(_StubNativeRuntime(), {"kind": "host_observation", "data": payload}, steer=False)
    # A failed events read is an error decision, not a noise page: untouched.
    failed = observation()
    failed["runs"]["run"]["events"] = {"ok": False,
                                       "error": {"code": "run_missing", "message": "gone"}}
    projected = host._model_observation(failed)
    assert projected["runs"]["run"]["events"] == {
        "ok": False, "error": {"code": "run_missing", "message": "gone"}}


@pytest.mark.parametrize("source,data", [
    ("coordinator.jsonl", {"type": "coordinator", "text": "ordinary model discussion"}),
    ("app-server-events.jsonl", {"method": "thread/tokenUsage/updated", "params": {"tokens": 12}}),
    ("dynamic-tool-calls.jsonl", {"tool": "read_handoff_material", "result": "accepted"}),
    ("capability-calls.jsonl", {"operation": "get_ontology_read_model", "ok": True}),
])
def test_r4329_known_routine_activity_does_not_wake(tmp_path, source, data):
    host = session(tmp_path)
    assert host.record_observation(observation())
    update = observation()
    update["runs"]["run"]["events"] = _events_page([
        {"source": source, "byte_offset": 0, "data": data}], next_cursor="next")
    assert not host.record_observation(update)
    assert json.loads((host.session_root / "observation.json").read_text())["data"] == update


@pytest.mark.parametrize("event", [
    {"source": "coordinator.jsonl", "data": {"type": "coordinator", "status": "blocked"}},
    {"source": "app-server-events.jsonl", "corrupt": True},
    {"source": "app-server-events.jsonl", "data": {"method": "error", "params": {"error": "down"}}},
    {"source": "app-server-events.jsonl", "data": {"method": "new/unknown"}},
    {"source": "app-server-events.jsonl", "data": {"method": "item/completed", "params": "malformed"}},
    {"source": "app-server-events.jsonl", "data": {"method": "item/completed", "params": {"item": {"status": {"unexpected": True}}}}},
    {"source": "dynamic-tool-calls.jsonl", "data": {"tool": "read_handoff_material", "result": "accepted", "status": "unknown"}},
    {"source": "capability-calls.jsonl", "data": {"operation": "modeling_apply_batch", "ok": True}},
    {"source": "dynamic-tool-calls.jsonl", "data": {"tool": "read_handoff_material", "result": "accepted", "data": {"write_state": "unknown"}}},
    {"source": "unknown-new-event.jsonl", "data": {"event": "unrecognized"}},
])
def test_r4329_anomalies_and_ambiguous_write_success_remain_visible(tmp_path, event):
    host = session(tmp_path)
    host.record_observation(observation())
    host._dispatch_observation(_StubNativeRuntime(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    update = observation()
    update["runs"]["run"]["events"] = _events_page([event], next_cursor="next")
    assert host.record_observation(update)
    delivered = host._model_observation()["runs"]["run"]["events"]["data"]["events"]
    assert delivered[0]["source"] == event["source"]


def test_r4329_private_cq_body_is_referenced_without_default_injection(tmp_path):
    host = session(tmp_path)
    update = observation()
    update["runs"]["run"]["events"] = _events_page([{
        "source": "cq-review-request.jsonl", "byte_offset": 0,
        "data": {"review_id": "review-1", "content_digest": "digest", "question_ids": ["q1"],
                 "text": "PRIVATE QUESTION", "mandatory_answer_points": ["HIDDEN ANSWER"],
                 "material_refs": [{"body": "PRIVATE SOURCE"}]},
    }], next_cursor="next")
    host.record_observation(update)
    payload = host._model_observation()
    encoded = json.dumps(payload)
    assert "PRIVATE QUESTION" not in encoded and "HIDDEN ANSWER" not in encoded
    assert "PRIVATE SOURCE" not in encoded
    metadata = payload["runs"]["run"]["events"]["data"]["events"][0]["data"]
    assert metadata["review_id"] == "review-1" and metadata["content_reference"]
    assert json.loads((host.session_root / "observation.json").read_text())["data"] == update


@pytest.mark.parametrize('source,data', [
    ('app-server-events.jsonl', {'method': 'item/started', 'params': {'item': {'type': 'reasoning'}}}),
    ('app-server-events.jsonl', {'method': 'item/completed', 'params': {'item': {'type': 'reasoning'}}}),
    ('app-server-events.jsonl', {'method': 'item/completed', 'params': {'item': {'type': 'userMessage'}}}),
    ('app-server-events.jsonl', {'method': 'serverRequest/resolved', 'params': {'requestId': 1}}),
    ('app-server-events.jsonl', {'method': 'mcpServer/elicitation/request', 'params': {'_meta': {'codex_approval_kind': 'mcp_tool_call'}}}),
    ('app-server-events.jsonl', {'method': 'account/rateLimits/updated', 'params': {'rateLimits': {'primary': None, 'secondary': None, 'rateLimitReachedType': None}}}),
    ('mcp-elicitations.jsonl', {'action': 'accept', 'mode': 'form', 'server_name': 'team_transport'}),
])
def test_recognized_native_bookkeeping_does_not_restart_delivery(tmp_path, source, data):
    host = session(tmp_path)
    assert host.record_observation(observation())
    update = observation()
    event = {'source': source, 'byte_offset': 0, 'data': data}
    update['runs']['run']['events'] = _events_page([event], next_cursor='next')
    assert not host.record_observation(update)
    assert event in json.loads((host.session_root / 'observation.json').read_text())['data']['runs']['run']['events']['data']['events']


@pytest.mark.parametrize('data', [
    {'method': 'item/completed', 'params': {'item': {'type': 'reasoning', 'error': 'failed'}}},
    {'method': 'mcpServer/elicitation/request', 'params': {'message': 'business decision'}},
    {'method': 'account/rateLimits/updated', 'params': {'rateLimits': {'primary': {'usedPercent': 100}}}},
    {'method': 'item/completed', 'params': {'item': {'type': 'futureType'}}},
])
def test_native_errors_real_limits_and_unrecognized_events_still_wake(tmp_path, data):
    host = session(tmp_path)
    assert host.record_observation(observation())
    update = observation()
    update['runs']['run']['events'] = _events_page([{'source': 'app-server-events.jsonl', 'byte_offset': 0, 'data': data}], next_cursor='next')
    assert host.record_observation(update)
