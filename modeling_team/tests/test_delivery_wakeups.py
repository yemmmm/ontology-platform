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


def changed_value(payload, *path):
    """Read one explicit v2 change, not an inferred or reconstructed snapshot."""
    return next(row["value"] for row in payload["changes"] if row["path"] == list(path))


def changed_events(payload):
    return changed_value(payload, "runs", "run", "events")


def observe_after_bootstrap(raw=None):
    """Introduce the tested change after the new current-state bootstrap."""
    calls = 0
    def observe(self):
        nonlocal calls
        calls += 1
        return copy.deepcopy((raw or observation()) if calls > 1 else {"runs": {}, "operations": {}, "repair_verifications": {}})
    return observe


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


@pytest.mark.parametrize(("method", "params"), [
    ("mcpServer/startupStatus/updated", {"status": "starting", "error": None}),
    ("mcpServer/startupStatus/updated", {"status": "ready", "error": None}),
    ("remoteControl/status/changed", {"status": "disabled"}),
])
def test_successful_runtime_status_is_retained_without_waking_delivery(tmp_path, method, params):
    host = session(tmp_path)
    host.record_observation(observation())
    raw = observation()
    event = {"source": "app-server-events.jsonl", "byte_offset": 100,
             "data": {"method": method, "params": params}}
    raw["runs"]["run"]["events"] = _events_page([event], next_cursor="status-1")
    assert not host.record_observation(raw)
    stored = json.loads((host.session_root / "observation.json").read_text())
    assert stored["data"]["runs"]["run"]["events"]["data"]["events"] == [event]
    event["byte_offset"] = 200
    event["data"]["params"] = {**params, "error": {"message": "startup unavailable"}}
    assert host.record_observation(raw)


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


def test_critical_host_observation_steers_before_natural_turn_boundary(tmp_path, monkeypatch):
    import importlib
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", observe_after_bootstrap())
    runtime, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [], run_ids=["bound"])
    assert result == 2
    assert len(runtime.steered) == 1
    assert json.loads(runtime.steered[0])["kind"] == "host_observation"
    assert runtime.events.index("steer") < runtime.events.index("turn_completed")


def test_automatic_observation_keeps_decision_for_next_turn(tmp_path, monkeypatch):
    import importlib
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", observe_after_bootstrap())
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


@pytest.mark.parametrize("agent", ["modeling", "coordinator"])
def test_terminal_role_receipt_keeps_identity_private_body_and_single_wakeup(tmp_path, agent):
    from modeling_team.delivery import _decision_event_metadata

    event = {"source": "team-transport-events.jsonl", "byte_offset": 100,
             "data": {"agent": agent, "category": "terminal_report_accepted",
                      "status": "accepted", "tool": "report_task_result",
                      "report": {"summary": "PRIVATE BODY"}}}
    metadata = _decision_event_metadata(event)
    assert metadata["data"]["agent_id"] == agent
    assert "PRIVATE BODY" not in json.dumps(metadata)
    host = session(tmp_path)
    assert host.record_observation(observation())
    arrival = observation()
    arrival["runs"]["run"]["events"] = _events_page([event], next_cursor="terminal-1")
    assert host.record_observation(arrival)
    assert not host.record_observation(arrival)
    drained = observation()
    drained["runs"]["run"]["events"] = _events_page([], next_cursor="terminal-2")
    assert not host.record_observation(drained)
    assert _decision_event_metadata({**event, "source": "other.jsonl"})["data"].get("agent_id") is None


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
    assert payload["unresolved"][0]["id"] == "question-2"
    assert [item["source"] for item in changed_events(payload)["data"]["events"]] == [
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
    assert event in changed_events(host._model_observation())["data"]["events"]
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
    assert event in changed_events(host._model_observation())["data"]["events"]


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
    assert observe_calls >= 3
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
    # The deferred automatic input uses the same filtered view.
    steered = json.loads(stub.steered[0])
    assert steered["kind"] == "host_observation"
    assert _HUGE_DELTA not in json.dumps(steered, ensure_ascii=False)
    # The complete record was persisted before delivery, at the referenced path.
    raw_ref = state["raw_observation"]
    assert raw_ref["reader"] == "read_delivery_artifact"
    stored = json.loads(Path(raw_ref["path"]).read_text())
    page = stored["data"]["runs"]["run"]["events"]["data"]
    assert page["events"][0]["data"]["params"]["delta"] == _HUGE_DELTA
    assert stored["observation_count"] >= 3 and stored["wake_count"] == 2


def test_deferred_payload_excludes_only_raw_app_server_records(tmp_path, monkeypatch):
    raw = _huge_delta_observation()
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", observe_after_bootstrap(raw))
    runtime, result, _record = _run_delivery_with_stub(
        tmp_path, monkeypatch, [], run_ids=["bound"])
    assert result == 2
    steered = json.loads(runtime.steered[0])
    assert steered["kind"] == "host_observation"
    delivered = json.dumps(steered, ensure_ascii=False)
    assert _HUGE_DELTA not in delivered
    page = changed_events(steered["data"])["data"]
    assert [event["source"] for event in page["events"]] == ["outer-input-receipts.jsonl"]
    # Decisions stay byte-complete: receipt, pending item, request ledger.
    assert page["events"][0] == _receipt_event(620_021, "req-9")
    assert (changed_value(steered["data"], "runs", "run")["pending"]["data"]["items"]
            == observation()["runs"]["run"]["pending"]["data"]["items"])
    assert "request_ledger" not in changed_value(steered["data"], "runs", "run")
    assert changed_value(steered["data"], "runs", "run")["requests"]["data"]["coverage"]["complete"] is False
    assert steered["data"]["raw_observation"]["excluded_noise_event_records"] == 1


def test_turn_boundary_send_carries_no_raw_app_server_records(tmp_path, monkeypatch):
    raw = _huge_delta_observation()
    raw["runs"]["run"]["events"]["data"]["events"] =         raw["runs"]["run"]["events"]["data"]["events"][:1]
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.DeliverySession, "observe", observe_after_bootstrap(raw))
    runtime, result, _record = _run_delivery_with_stub(
        tmp_path, monkeypatch, [], run_ids=["bound"], steer_failures=1)
    assert result == 2
    assert runtime.steered == [] and runtime.steer_attempts == 1
    sent = json.loads(runtime.sent[1])
    assert sent["kind"] == "host_observation"
    delivered = json.dumps(sent, ensure_ascii=False)
    assert _HUGE_DELTA not in delivered
    assert changed_events(sent["data"])["data"]["events"] == []
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
    assert changed_events(projected) == {
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
])
def test_r4329_anomalies_and_ambiguous_write_success_remain_visible(tmp_path, event):
    host = session(tmp_path)
    host.record_observation(observation())
    host._dispatch_observation(_StubNativeRuntime(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    update = observation()
    update["runs"]["run"]["events"] = _events_page([event], next_cursor="next")
    assert host.record_observation(update)
    delivered = changed_events(host._model_observation())["data"]["events"]
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


def _dsh_wire(kind, data):
    return {'source': 'dsh-wire.jsonl', 'byte_offset': 0, 'data': {
        'agent_id': 'modeling', 'process_instance': 'process-1', 'session_id': 'session-1',
        'frame': {'jsonrpc': '2.0', 'method': 'session.event', 'params': {
            'sessionId': 'session-1', 'event': {'type': kind, 'seq': 12, 'data': data}}}}}


@pytest.mark.parametrize('source,data', [
    ('dsh-dispatch.jsonl', {'event': 'queued', 'runtime': 'dsh', 'agent_id': 'modeling',
                          'dispatch_id': 'dispatch-1', 'message_id': 'message-1'}),
    ('dsh-handoff.jsonl', {'kind': 'artifact', 'state': 'received', 'handoff_id': 'artifact-1',
                         'run_id': 'run', 'material_ref': {'material_id': 'material-1'}}),
    *[('dsh-handoff.jsonl', {'kind': 'public-input', 'state': state,
                           'handoff_id': 'public-1', 'run_id': 'run',
                           'dispatch_id': 'dispatch-1', 'recipient_id': 'modeling',
                           'material_ref': {'material_id': 'material-1'}})
      for state in ('queued', 'claimed', 'settled')],
])
def test_successful_dsh_handoff_bookkeeping_is_retained_without_waking(tmp_path, source, data):
    host = session(tmp_path)
    host.record_observation(observation())
    raw = observation()
    event = {'source': source, 'byte_offset': 0, 'data': data}
    raw['runs']['run']['events'] = _events_page([event], next_cursor='handoff')
    assert not host.record_observation(raw)
    assert json.loads((host.session_root / 'observation.json').read_text())['data'] == raw


@pytest.mark.parametrize('data', [
    {'kind': 'public-input', 'state': 'unknown', 'handoff_id': 'h1', 'run_id': 'run'},
    {'kind': 'public-input', 'state': 'failed', 'handoff_id': 'h1', 'run_id': 'run'},
    {'kind': 'public-input', 'state': 'canceled', 'handoff_id': 'h1', 'run_id': 'run'},
    {'kind': 'public-input', 'state': 'pending', 'handoff_id': 'h1', 'run_id': 'run'},
    {'kind': 'artifact', 'state': 'received', 'handoff_id': 'h1', 'run_id': 'run',
     'error': 'target could not be verified'},
    {'kind': 'future-kind', 'state': 'settled', 'handoff_id': 'h1', 'run_id': 'run'},
    {'kind': 'public-input', 'state': 'settled'},
])
def test_dsh_handoff_errors_pending_and_unknown_shapes_still_wake(tmp_path, data):
    host = session(tmp_path)
    host.record_observation(observation())
    raw = observation()
    raw['runs']['run']['events'] = _events_page([
        {'source': 'dsh-handoff.jsonl', 'byte_offset': 0, 'data': data}], next_cursor='error')
    assert host.record_observation(raw)


@pytest.mark.parametrize('text', ['Error: tool rejected', '{"ok":true}'])
def test_native_tool_error_flag_stays_visible_even_with_success_shaped_body(tmp_path, text):
    from modeling_team.tests.test_delivery_decision_input import ack

    host = session(tmp_path)
    host.record_observation(observation())
    ack(host)
    raw = observation()
    raw['runs']['run']['events'] = _events_page([_dsh_wire('tool/result', {'message': {
        'isError': True, 'content': [{'type': 'text', 'text': text}]}})], next_cursor='error')
    assert host.record_observation(raw)
    payload = host._model_observation()
    assert changed_events(payload)['data']['events'][0]['data']['runtime_state']['tool_error'] is True


@pytest.mark.parametrize('frame', [
    {'jsonrpc': '2.0', 'id': 1, 'result': {'messageId': 'message-1'}},
    {'jsonrpc': '2.0', 'id': 2, 'result': {}},
    {'jsonrpc': '2.0', 'method': 'session.status',
     'params': {'sessionId': 'session-1', 'status': 'idle'}},
])
def test_successful_dsh_dispatch_ack_and_idle_do_not_wake_delivery(tmp_path, frame):
    host = session(tmp_path)
    host.record_observation(observation())
    raw = observation()
    event = {'source': 'dsh-wire.jsonl', 'byte_offset': 0,
             'data': {'agent_id': 'modeling', 'frame': frame}}
    raw['runs']['run']['events'] = _events_page([event], next_cursor='next')
    assert not host.record_observation(raw)
    assert json.loads((host.session_root / 'observation.json').read_text())['data'] == raw


@pytest.mark.parametrize('frame', [
    {'jsonrpc': '2.0', 'id': 1, 'error': {'message': 'dispatch failed'}},
    {'jsonrpc': '2.0', 'id': 2, 'result': {'unexpected': 'future-result'}},
    {'jsonrpc': '2.0', 'id': 3, 'result': {'messageId': None}},
    {'jsonrpc': '2.0', 'id': None, 'result': {}},
    {'jsonrpc': '2.0', 'method': 'session.status',
     'params': {'sessionId': 'session-1', 'status': 'failed'}},
    {'jsonrpc': '2.0', 'method': 'session.status',
     'params': {'sessionId': 'session-1', 'status': []}},
])
def test_dsh_dispatch_errors_and_unknown_responses_still_wake(tmp_path, frame):
    host = session(tmp_path)
    host.record_observation(observation())
    raw = observation()
    raw['runs']['run']['events'] = _events_page([
        {'source': 'dsh-wire.jsonl', 'data': {'agent_id': 'modeling', 'frame': frame}},
    ], next_cursor='next')
    assert host.record_observation(raw)


@pytest.mark.parametrize('kind,data', [
    ('step/start', {'turn': 1, 'step': 2}),
    ('step/end', {'turn': 1, 'step': 2}),
    ('turn/end', {'turn': 1, 'reason': {'kind': 'completed'}}),
    ('agent/inbox/spliced', {'target': 'next-turn', 'start': 0,
                            'inserted': [{'id': 'message-1', 'content': []}]}),
    ('agent/inbox/spliced', {'target': 'next-turn', 'start': 0,
                            'removedCount': 1, 'inserted': []}),
    ('assistant/message', {'message': {'role': 'assistant', 'content': [
        {'type': 'reasoning', 'text': 'PRIVATE REASONING'}]}}),
    ('user/message', {'content': [{'type': 'text', 'text': 'PRIVATE SOURCE'}]}),
    ('tool/call', {'name': 'read_role_material', 'arguments': {'id': 'material-1'}}),
    ('tool/result', {'message': {'content': [{'type': 'text', 'text': '{"ok":true}'}]}}),
])
def test_dsh_routine_wire_does_not_wake_or_enter_decision_input(tmp_path, kind, data):
    host = session(tmp_path)
    host.record_observation(observation())
    host._dispatch_observation(_StubNativeRuntime(), {
        'kind': 'host_observation', 'data': host._model_observation()}, steer=False)
    event = _dsh_wire(kind, data)
    update = observation()
    update['runs']['run']['events'] = _events_page([event], next_cursor='dsh-next')
    assert not host.record_observation(update)
    assert json.loads((host.session_root / 'observation.json').read_text())['data'] == update
    update['runs']['run']['pending']['data']['items'][0]['id'] = 'new-question'
    assert host.record_observation(update)
    payload = host._model_observation()
    assert 'dsh-wire.jsonl' not in json.dumps(payload['changes'])
    assert payload['raw_observation']['excluded_noise_event_records'] == 1


@pytest.mark.parametrize('event,status,extra', [
    ('attempt_start', 'unfinished', {}),
    ('attempt_end', 'completed', {'http_status': 200}),
    ('response_usage', 'completed', {'http_status': 200, 'usage_complete': True,
                                   'usage_issues': [], 'raw_usage': {'input_tokens': 50}}),
])
def test_dsh_numeric_activity_does_not_wake(tmp_path, event, status, extra):
    host = session(tmp_path)
    host.record_observation(observation())
    update = observation()
    update['runs']['run']['events'] = _events_page([{
        'source': 'dsh-provider.jsonl', 'byte_offset': 0, 'data': {
            'schema_version': 'model-usage-capture/v1', 'event': event,
            'status': status, 'http_status': None, **extra}}], next_cursor='next')
    assert not host.record_observation(update)


@pytest.mark.parametrize('kind,data', [
    ('turn/end', {'turn': 1, 'reason': {'kind': 'error', 'error': {'code': 'INVALID_REQUEST'}}}),
    ('assistant/attempt', {'stream': [{'chunk': {'type': 'finish', 'reason': {
        'kind': 'error', 'failure': {'code': 'MALFORMED_RESPONSE', 'status': 400}}}}]}),
    ('tool/result', {'message': {'content': [{'type': 'text', 'text':
        '{"ok":false,"error":{"code":"scope_binding_required"}}'}]}}),
    ('tool/result', {'message': {'content': [{'type': 'text', 'text': 'unrecognized result'}]}}),
    ('tool/result', {'message': {'content': [{'type': 'text', 'text': '{"isError":true}'}]}}),
    ('step/end', {'reason': {'kind': 'error'}}),
    ('agent/inbox/spliced', {'target': 'next-turn', 'outcome': 'canceled'}),
    ('future/event', {'status': 'unknown'}),
    ('agent/inbox/spliced', {'target': 'future-queue', 'start': 0, 'inserted': []}),
    ('agent/inbox/spliced', {'target': 'next-turn', 'start': 0, 'inserted': 'bad'}),
])
def test_dsh_decisions_keep_runtime_identity_and_typed_error_without_content(tmp_path, kind, data):
    host = session(tmp_path)
    host.record_observation(observation())
    host._dispatch_observation(_StubNativeRuntime(), {
        'kind': 'host_observation', 'data': host._model_observation()}, steer=False)
    update = observation()
    event = _dsh_wire(kind, data)
    update['runs']['run']['events'] = _events_page([event], next_cursor='next')
    assert host.record_observation(update)
    metadata = changed_events(host._model_observation())['data']['events'][0]['data']
    assert metadata['runtime_state']['event_type'] == kind
    assert metadata['runtime_state']['session_id'] == 'session-1'
    assert metadata['process_instance'] == 'process-1'
    assert metadata['content_reference']
    for code in ['INVALID_REQUEST', 'MALFORMED_RESPONSE', 'scope_binding_required']:
        if code in json.dumps(data):
            assert code in json.dumps(metadata)
    if kind == 'tool/result' and ('scope_binding_required' in json.dumps(data) or 'isError' in json.dumps(data)):
        assert metadata['runtime_state']['tool_error'] is True


@pytest.mark.parametrize('extra', [{'usage_complete': False}, {'usage_issues': ['truncated_sse_event']},
                                {'status': 'http_error', 'http_status': 400}, {'corrupt': True}])
def test_dsh_usage_anomalies_still_wake(tmp_path, extra):
    host = session(tmp_path)
    host.record_observation(observation())
    update = observation()
    event = {'source': 'dsh-provider.jsonl', 'byte_offset': 0, 'data': {
        'schema_version': 'model-usage-capture/v1', 'event': 'response_usage',
        'status': 'completed', 'http_status': 200, 'usage_complete': True, 'usage_issues': []}}
    if 'corrupt' in extra:
        event.update(extra)
    else:
        event['data'].update(extra)
    update['runs']['run']['events'] = _events_page([event], next_cursor='next')
    assert host.record_observation(update)


def test_dsh_tool_error_projection_does_not_copy_business_codes_or_source_text(tmp_path):
    from modeling_team.delivery import _decision_event_metadata
    event = _dsh_wire('tool/result', {'message': {'content': [{'type': 'text', 'text':
        json.dumps({'ok': False, 'error': {'code': 'scope_binding_required', 'message': 'PRIVATE SOURCE'},
                    'data': {'code': 'PRIVATE BUSINESS CODE'}})}]}})
    metadata = _decision_event_metadata(event)
    assert 'scope_binding_required' in json.dumps(metadata)
    assert 'PRIVATE' not in json.dumps(metadata)


def test_dsh_provider_failure_input_keeps_safe_cause_and_request_numbers():
    from modeling_team.delivery import _decision_event_metadata
    event = {'source': 'dsh-provider.jsonl', 'byte_offset': 0, 'data': {
        'event': 'response_usage', 'status': 'http_error', 'http_status': 400,
        'request_id': 'request-1', 'usage_complete': False,
        'provider_error': {'reason_code': 'context_window_exceeded', 'provider_type': 'invalid_request_error'},
        'request_shape': {'body_bytes': 1000, 'max_tokens': 256000},
        'usage_issues': ['message_start_missing']}}
    assert _decision_event_metadata(event)['data'] == event['data']


@pytest.mark.parametrize('data', [{'frame': None}, {'frame': {'params': None}},
                               {'frame': {'method': 'session.event', 'params': {'event': None}}}])
def test_malformed_dsh_wire_stays_an_observable_decision(tmp_path, data):
    host = session(tmp_path)
    host.record_observation(observation())
    update = observation()
    update['runs']['run']['events'] = _events_page([
        {'source': 'dsh-wire.jsonl', 'byte_offset': 0, 'data': data}], next_cursor='next')
    assert host.record_observation(update)


def _diagnostic_update(index, *, source="new-plugin.jsonl", **fields):
    raw = observation()
    data = {"event": "diagnostic", "code": "meter_unavailable", "status": "degraded",
            "request_id": f"request-{index}", "recorded_at": f"time-{index}",
            "count": index, **fields}
    raw["runs"]["run"]["events"] = _events_page([
        {"source": source, "byte_offset": index * 100, "data": data}],
        next_cursor=f"diagnostic-{index}")
    return raw


@pytest.mark.parametrize("source", ["new-plugin.jsonl", "dsh-provider.jsonl"])
def test_diagnostic_state_changes_not_log_appends_wake(tmp_path, source):
    host = session(tmp_path)
    host.record_observation(observation())
    extra = ({"schema_version": "model-usage-capture/v1", "event": "response_usage",
              "status": "completed", "http_status": 200, "usage_complete": False,
              "usage_issues": ["input_outside_start:input_tokens"]}
             if source == "dsh-provider.jsonl" else {})
    assert host.record_observation(_diagnostic_update(1, source=source, **extra))
    for index in range(2, 13):
        assert not host.record_observation(_diagnostic_update(index, source=source, **extra))
    while host._pending_decisions:
        host._dispatch_observation(_StubNativeRuntime(), {
            "kind": "host_observation", "data": host._model_observation()}, steer=False)
    # A real business change wakes, without reinjecting the repeated diagnostic.
    current = _diagnostic_update(13, source=source, **extra)
    current["runs"]["run"]["pending"]["data"]["items"][0]["id"] = "new-review"
    assert host.record_observation(current)
    payload = host._model_observation()
    assert not any(row["path"][:3] == ["runs", "run", "events"] for row in payload["changes"])
    assert payload["raw_observation"]["excluded_noise_event_records"] == 1
    assert json.loads((host.session_root / "observation.json").read_text())["data"] == current


def test_diagnostic_change_recovery_and_recurrence_wake(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    assert host.record_observation(_diagnostic_update(1))
    assert not host.record_observation(_diagnostic_update(2))
    assert host.record_observation(_diagnostic_update(3, code="different_fault"))
    assert host.record_observation(_diagnostic_update(4, status="recovered", code="meter_unavailable"))
    assert not host.record_observation(_diagnostic_update(5, status="recovered", code="meter_unavailable"))
    assert host.record_observation(_diagnostic_update(6))
    assert host.record_observation(_diagnostic_update(7, object="another-affected-object"))


def test_successful_meter_receipt_wakes_only_for_recovery(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    good = {"schema_version": "model-usage-capture/v1", "event": "response_usage",
            "code": None, "status": "completed", "http_status": 200,
            "usage_complete": True, "usage_issues": []}
    assert not host.record_observation(_diagnostic_update(1, source="dsh-provider.jsonl", **good))
    assert host.record_observation(_diagnostic_update(2, source="dsh-provider.jsonl",
        **{**good, "usage_complete": False, "usage_issues": ["missing_input"]}))
    assert host.record_observation(_diagnostic_update(3, source="dsh-provider.jsonl", **good))
    assert not host.record_observation(_diagnostic_update(4, source="dsh-provider.jsonl", **good))


def test_diagnostic_dedup_survives_delivery_restore(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    assert host.record_observation(_diagnostic_update(1))
    restored = type(host)(repository_root=host.repository_root, session_root=host.session_root,
                          config=host.config, resume=True)
    assert not restored.record_observation(_diagnostic_update(2))
    assert restored.record_observation(_diagnostic_update(3, code="new_fault"))


@pytest.mark.parametrize("binding", ["write_state", "mutation_state", "control_epoch",
                                     "authorization_reference", "review_id", "operation_id"])
def test_problem_folding_preserves_binding_changes_without_repeating_same_problem(tmp_path, binding):
    host = session(tmp_path)
    host.record_observation(observation())
    fields = {binding: "unknown", "request_id": "same-request"}
    assert host.record_observation(_diagnostic_update(1, **fields))
    assert not host.record_observation(_diagnostic_update(2, **fields))
    assert host.record_observation(_diagnostic_update(3, **{**fields, binding: "changed-binding"}))
    assert host.record_observation(_diagnostic_update(4, **{**fields, "request_id": "another-request"}))


def test_unfamiliar_ordinary_records_remain_in_review_without_waking(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    def update(index, value):
        raw = observation()
        raw["runs"]["run"]["events"] = _events_page([{
            "source": "future-plugin.jsonl", "byte_offset": index * 100,
            "data": {"event": "future-notification", "seq": index,
                     "recorded_at": str(index), "opaque": {"value": value}}}],
            next_cursor=str(index))
        return raw
    assert not host.record_observation(update(1, "first"))
    assert not host.record_observation(update(2, "first"))
    assert not host.record_observation(update(3, "changed"))
    assert sum(row["count"] for row in host._status_review.summary()["activity"]) == 3
