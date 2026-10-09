"""R4.3-005 decision-driven observation, without a live semantic run."""
import copy
import json

import pytest

from modeling_team.tests.test_delivery_session import session


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
                                   "request", "report", "liveness", "verification"])
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
