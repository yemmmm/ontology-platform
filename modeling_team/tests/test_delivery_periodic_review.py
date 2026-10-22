"""R4.4-003 offline contracts. No paid calls or semantic acceptance."""
import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from modeling_team.delivery import DeliverySession
from modeling_team.tests.test_delivery_session import ROOT, session
from modeling_team.tests.test_delivery_wakeups import observation, _events_page


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 10, 22, tzinfo=UTC)]
    monkeypatch.setattr(importlib.import_module("modeling_team.delivery"), "_utc_now", lambda: current[0])
    return current


def finish(host):
    packet = host._model_observation()
    native = type("Native", (), {"send": lambda self, text: None})()
    assert host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=False)
    host.record_turn_completion("completed")
    return packet


def test_ordinary_hundred_updates_are_one_due_window(tmp_path, clock):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    for index in range(100):
        raw["runs"]["run"]["status"]["data"]["semantic_progress"]["staged_decision_count"] = index + 2
        raw["runs"]["run"]["events"] = _events_page([{
            "source": "capability-calls.jsonl", "byte_offset": index,
            "data": {"agent_id": "modeling", "operation": "get_ontology_read_model", "ok": True},
        }], next_cursor=str(index))
        assert not host.record_observation(raw)
    assert not host._pending_decisions
    clock[0] += timedelta(seconds=89)
    assert not host.record_observation(raw)
    clock[0] += timedelta(seconds=1)
    assert host.record_observation(raw)
    packet = host._model_observation()
    assert packet["trigger"]["kind"] == "periodic_review"
    review = packet["periodic_review"]
    assert sum(row["count"] for row in review["activity"]) == 100
    assert review["window"]["after_seq"] < review["window"]["through_seq"]
    assert not host.record_observation(raw)


def test_busy_coalesces_due_periods_and_silent_work_is_reviewed(tmp_path, clock):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    for seconds in (90, 200, 500):
        clock[0] = datetime(2026, 10, 22, tzinfo=UTC) + timedelta(seconds=seconds)
        assert not host.record_observation(raw, allow_periodic=False)
    assert host.record_observation(raw)
    finish(host)
    assert not host.record_observation(raw)
    clock[0] += timedelta(seconds=90)
    assert host.record_observation(raw)  # no card change cannot disable reviews forever


@pytest.mark.parametrize("status", ["failed", None, "completed"])
def test_review_confirmation_requires_normal_native_completion(tmp_path, clock, status):
    host = session(tmp_path)
    host.record_observation(observation())
    packet = host._model_observation()
    native = type("Native", (), {"send": lambda self, text: None})()
    assert host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=False)
    assert host._status_review.confirmed_seq == 0
    host.record_turn_completion(status)
    assert (host._status_review.confirmed_seq > 0) == (status == "completed")
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert reopened._status_review.confirmed_seq == host._status_review.confirmed_seq


def test_recoverable_tool_retry_is_batched_unknown_anomaly_is_immediate(tmp_path, clock):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    for index in range(3):
        raw["runs"]["run"]["events"] = _events_page([{
            "source": "capability-calls.jsonl", "byte_offset": index,
            "data": {"agent_id": "modeling", "operation": "read_model", "ok": False,
                     "error": {"code": "bad_argument", "retryable": True}},
        }], next_cursor=str(index))
        assert not host.record_observation(raw)
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "unknown-plugin.jsonl", "byte_offset": 0,
        "data": {"agent_id": "modeling", "error": "unclassified failure"},
    }], next_cursor="unknown")
    assert host.record_observation(raw)
    assert host._model_observation()["trigger"]["kind"] == "critical_event"


def test_invalid_interval_is_field_specific_and_correctable(tmp_path):
    host = session(tmp_path)
    for value in (0, -1, True, 1.5, "90"):
        config = {**host.config, "status_review_interval_seconds": value}
        with pytest.raises(ValueError, match="status_review_interval_seconds"):
            DeliverySession(repository_root=ROOT, session_root=tmp_path / "invalid",
                            config=config)


def wait_args(input_id, **extra):
    return {"input_id": input_id, "phase": "modeling",
            "waiting_for": [{"operation_id": "op", "condition": "actual provider call"}],
            "next_action": "check the original receipt", "reason": "normal in-flight work",
            "active_decisions": [], **extra}


def test_explicit_defer_only_suppresses_unchanged_facts(tmp_path, clock):
    host = session(tmp_path)
    host.operation_ids.add("op")
    raw = observation()
    host.record_observation(raw)
    packet = finish(host)
    args = wait_args(packet["input_id"], next_review_at=(clock[0] + timedelta(seconds=600)).isoformat())
    assert host.call_tool("yield_delivery", args)["ok"]
    clock[0] += timedelta(seconds=90)
    assert not host.record_observation(raw)
    raw["runs"]["run"]["status"]["data"]["semantic_progress"]["staged_decision_count"] += 1
    assert host.record_observation(raw)
    finish(host)
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    assert host.record_observation(raw)
    assert host._model_observation()["trigger"]["kind"] == "critical_event"


def test_new_card_fact_is_not_suppressed_by_a_previous_defer(tmp_path, clock):
    host = session(tmp_path)
    host.operation_ids.add("op")
    raw = observation()
    host.record_observation(raw)
    packet = finish(host)
    assert host.call_tool("yield_delivery", wait_args(packet["input_id"],
        next_review_at=(clock[0] + timedelta(seconds=600)).isoformat()))["ok"]
    clock[0] += timedelta(seconds=90)
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "work-board-events.jsonl", "byte_offset": 100,
        "data": {"schema_version": "team-work-board/v1", "kind": "card", "record_seq": 1},
    }], next_cursor="card")
    assert host.record_observation(raw)
    assert host._model_observation()["trigger"]["kind"] == "periodic_review"


def test_due_followup_is_once_and_survives_resume(tmp_path, clock):
    host = session(tmp_path)
    host.operation_ids.add("op")
    host.record_observation(observation())
    packet = finish(host)
    next_time = clock[0] + timedelta(seconds=30)
    assert host.call_tool("yield_delivery", wait_args(packet["input_id"], next_review_at=next_time.isoformat()))["ok"]
    host = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                           config=host.config, resume=True)
    clock[0] = next_time
    assert host.record_observation(observation())
    assert finish(host)["trigger"]["kind"] == "followup_due"
    assert not host.record_observation(observation())


@pytest.mark.parametrize("value", ["tomorrow", "2026-10-22T03:00:00"])
def test_invalid_followup_is_recoverable_field_feedback(tmp_path, clock, value):
    host = session(tmp_path)
    host.operation_ids.add("op")
    host.record_observation(observation())
    packet = finish(host)
    result = host.call_tool("yield_delivery", wait_args(packet["input_id"], next_review_at=value))
    assert not result["ok"] and result["error"]["retryable"]
    assert result["error"]["object"] == "next_review_at"
    assert host.last_yield is None


@pytest.mark.parametrize("runtime_name", ["codex", "dsh"])
def test_critical_is_selected_but_waits_for_natural_completion(tmp_path, clock, runtime_name):
    host = session(tmp_path)
    host.runtime_name = runtime_name
    raw = observation()
    host.record_observation(raw)
    finish(host)
    clock[0] += timedelta(seconds=90)
    host.record_observation(raw)
    old = host._pending_decisions[0]
    old["offset"] = 1  # a known partial ordinary page is still outstanding
    native = type("Native", (), {"send": lambda self, text: None})()
    assert not host._dispatch_observation(native,
        {"kind": "host_observation", "data": host._model_observation()}, steer=True)
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    assert host.record_observation(raw, allow_periodic=False)
    packet = host._model_observation()
    assert packet["input_id"] != old["input_id"]
    assert packet["trigger"]["kind"] == "critical_event"
    assert not host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=True)
    assert host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=False)
    assert old in host._pending_decisions
    host.record_turn_completion("completed")
    assert old not in host._pending_decisions
    journal = (host.session_root / "session-events.jsonl").read_text()
    assert "delivery_review_superseded" in journal


@pytest.mark.parametrize("failed_first", [False, True])
def test_paged_review_confirms_only_contiguous_normal_pages(tmp_path, clock, failed_first):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "important scope " * 6000
    host.record_observation(raw)
    native = type("Native", (), {"send": lambda self, text: None})()
    first = True
    while host._pending_decisions:
        packet = host._model_observation()
        assert "page" in packet
        assert host._dispatch_observation(native, {"kind": "host_observation", "data": packet}, steer=False)
        host.record_turn_completion("failed" if first and failed_first else "completed")
        first = False
    assert (host._status_review.confirmed_seq == 0) == failed_first
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "current scope"
    host.record_observation(raw, force_delivery=True)
    finish(host)
    assert host._status_review.confirmed_seq > 0


def test_completion_stops_reviews_but_new_failure_still_wakes(tmp_path, clock):
    host = session(tmp_path)
    raw = {"runs": {}, "operations": {}, "repair_verifications": {}}
    host.work_result, host.activity = "verified delivery", "standby"
    host.record_observation(raw)
    finish(host)
    clock[0] += timedelta(seconds=600)
    assert not host.record_observation(raw)
    raw["operations"]["late"] = {"ok": False, "error": {"code": "owner_failed"}}
    assert host.record_observation(raw)


def test_observation_gap_after_completion_remains_actionable(tmp_path, clock, monkeypatch):
    from modeling_team.tests.test_delivery_phase_threads import ready
    host, raw = ready(tmp_path, monkeypatch)
    raw["operations"]["op"]["data"].update(work_state="completed", report_binding={"valid": True})
    host.work_result, host.activity = "verified delivery", "standby"
    host.record_observation(raw)
    finish(host)
    assert host._completed_observations_are_quiet()
    raw["runs"]["run"]["events"] = _events_page([
        {"source": "capability-calls.jsonl", "data": {"ok": True}}], next_cursor="gap")
    assert host.record_observation(raw)
    assert host._last_current["observation_gaps"]
    assert not host._completed_observations_are_quiet()


def test_unknown_input_preserves_window_and_is_not_blindly_replayed(tmp_path, clock):
    from modeling_team.runtimes.delivery import DeliveryRuntimeError
    host = session(tmp_path)
    host.record_observation(observation())
    packet = host._model_observation()
    calls = []
    class Native:
        def send(self, text):
            calls.append(text)
            raise DeliveryRuntimeError("receipt lost")
    assert not host._dispatch_observation(Native(), {"kind": "host_observation", "data": packet}, steer=False)
    host.record_turn_completion("completed")
    assert host._status_review.confirmed_seq == 0
    assert not host._dispatch_observation(Native(), {"kind": "host_observation", "data": packet}, steer=False)
    assert len(calls) == 1 and host._pending_decisions[0]["delivery_status"] == "unknown"


def test_out_of_order_event_positions_are_counted_once(tmp_path, clock):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    for position in (100, 50, 100, 150):
        raw["runs"]["run"]["events"] = _events_page([{
            "source": "capability-calls.jsonl", "byte_offset": position,
            "data": {"agent_id": "modeling", "operation": "get_ontology_read_model", "ok": True},
        }], next_cursor=str(position))
        assert not host.record_observation(raw)
    assert sum(row["count"] for row in host._status_review.summary()["activity"]) == 3


def test_work_card_window_uses_actual_frozen_history_and_omits_unchanged_body(tmp_path, clock, monkeypatch):
    from modeling_team.tests.test_work_board import call, host_setup
    from modeling_team.transport_mcp import TeamTransportBroker
    broker = TeamTransportBroker(tmp_path / "run/transport/broker", {("a", "b"), ("b", "a")},
        run_id="run", agent_roles={"a": "modeling", "b": "coordinator", "judge": "acceptance"})
    root, _ = host_setup(broker)
    for name in ("modeling_team.delivery", "modeling_team.host_ops"):
        monkeypatch.setattr(importlib.import_module(name), "resolve_run_root", lambda *a, **k: (root, tmp_path))
    host = session(tmp_path)
    host.run_ids.add("run")
    call(broker, "a", "update_work_card", card={"current_work": "initial work"})
    raw = observation()
    host.record_observation(raw)
    first = finish(host)
    assert first["periodic_review"]["roles"][0]["cards"][0]["card"]
    for index in range(65):
        call(broker, "a", "update_work_card", card={"current_work": "work " + str(index)})
    clock[0] += timedelta(seconds=90)
    host.record_observation(raw)
    second = finish(host)
    roles = second["periodic_review"]["roles"][0]
    assert roles["changes_by_actor"]["a"]["count"] == 65
    assert roles["source_ref"]["max_record_seq"] == 66
    assert "judge" not in json.dumps(roles["cards"])
    clock[0] += timedelta(seconds=90)
    host.record_observation(raw)
    third = finish(host)["periodic_review"]["roles"][0]
    card = next(card for card in third["cards"] if card["agent_id"] == "a")
    assert card["unchanged"] and "card" not in card
    assert third["changes_by_actor"] == {}


@pytest.mark.parametrize("failed_view", ["current_page", "history"])
def test_failed_card_sources_expose_continuation_and_keep_positions(tmp_path, clock, monkeypatch, failed_view):
    host = session(tmp_path)
    host.record_observation(observation())
    finish(host)
    before = host._status_review.confirmed_seq
    host.run_ids.add("run")
    original = host.call_tool
    def tool(name, arguments, **kwargs):
        if name != "get_team_work_board":
            return original(name, arguments, **kwargs)
        if arguments.get("cursor") or arguments.get("view") == "history" and failed_view == "history":
            return {"ok": False, "error": {"code": "source_unavailable"}}
        return {"ok": True, "data": {"cards": [], "history": [], "source_ref": {"max_record_seq": 9},
                "limitations": [], "continuation": "fixed-current-cursor" if failed_view == "current_page" else None}}
    monkeypatch.setattr(host, "call_tool", tool)
    clock[0] += timedelta(seconds=90)
    host.record_observation(observation())
    packet = finish(host)
    review = packet["periodic_review"]
    assert not review["coverage"]["complete"]
    assert "source_unavailable" in json.dumps(review)
    assert "read_remaining" in json.dumps(review)
    assert host._status_review.confirmed_seq == before
    assert "work_board:run" not in host._status_review.confirmed_sources


def test_missing_event_position_is_explicit_and_unconfirmed(tmp_path, clock):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    before = host._status_review.confirmed_seq
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "capability-calls.jsonl", "data": {"operation": "read_model", "ok": True},
    }], next_cursor="unpositioned")
    assert host.record_observation(raw)
    review = finish(host)["periodic_review"]
    assert any(item["code"] == "event_position_unknown" for item in review["coverage"]["limitations"])
    assert host._status_review.confirmed_seq == before


@pytest.mark.parametrize("status", ["pending", "incomplete", "forbidden"])
def test_unknown_explicit_problem_is_immediate(tmp_path, clock, status):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    finish(host)
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "future-plugin.jsonl", "byte_offset": 0, "data": {"status": status},
    }], next_cursor=status)
    assert host.record_observation(raw)


def test_native_retries_preserve_latest_recovery_and_exact_references(tmp_path, clock):
    from modeling_team.tests.test_delivery_tuning_regressions import native_result, observe_event
    host = session(tmp_path)
    host.record_observation(observation())
    finish(host)
    for index in range(1, 4):
        assert not observe_event(host, index, native_result(index, {
            "ok": False, "error": {"code": "bad_argument", "retryable": True}}))
    observe_event(host, 4, native_result(4, {"ok": True}))
    rows = host._status_review.summary()["retries"]
    retry = next(row for row in rows if row["operation"] == "report_task_result")
    assert retry["failure_count"] == 3
    assert retry["latest_result"]["status"] == "completed"
    assert retry["latest_result"]["latest"]["byte_offset"] == 400


def test_idle_external_rejection_retries_original_identity(tmp_path, monkeypatch):
    from modeling_team.tests.test_delivery_session import _StubNativeRuntime, _run_delivery_with_stub
    from modeling_team.runtimes.delivery import DeliveryRuntimeError
    module = importlib.import_module("modeling_team.delivery")
    attempts = []
    class Native(_StubNativeRuntime):
        def start(self):
            super().start()
            self._hold = False

        def send(self, text):
            packet = json.loads(text)
            if packet.get("kind") == "user_input":
                attempts.append(packet)
                if len(attempts) == 1:
                    raise DeliveryRuntimeError("activity finished", category="rejected")
            return super().send(text)

    original = module._run_delivery
    def run(config, **kwargs):
        monkeypatch.setattr(module, "DeliveryRuntime", lambda **kw: Native())
        return original(config, **kwargs)
    monkeypatch.setattr(module, "_run_delivery", run)
    _, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, ["keep this exact input"])
    assert result == 2 and len(attempts) == 2
    assert attempts[0] == attempts[1]


def test_custom_positive_interval_is_used(tmp_path, clock):
    original = session(tmp_path)
    host = DeliverySession(repository_root=ROOT, session_root=tmp_path / "custom",
        config={**original.config, "status_review_interval_seconds": 7})
    host.record_observation(observation())
    finish(host)
    clock[0] += timedelta(seconds=6)
    assert not host.record_observation(observation())
    clock[0] += timedelta(seconds=1)
    assert host.record_observation(observation())


def test_program_loop_keeps_busy_periodic_reviews_out_of_steer(tmp_path, clock, monkeypatch):
    from modeling_team.tests.test_delivery_session import _StubNativeRuntime, _run_delivery_with_stub
    module = importlib.import_module("modeling_team.delivery")
    count, ticks = 0, 0
    native = None
    def observe(self):
        nonlocal count
        count += 1
        if 1 < count <= 4:
            clock[0] += timedelta(seconds=90)
        if count == 6:
            self.finished = True
        return observation()

    def monotonic():
        nonlocal ticks
        ticks += 3
        return ticks

    class Native(_StubNativeRuntime):
        def poll(self, timeout=0):
            if self.busy and count >= 4:
                self.busy = False
                return [{"event": "turn_completed", "status": "completed"}]
            return []

    original = module._run_delivery
    def run(config, **kwargs):
        nonlocal native
        native = Native()
        monkeypatch.setattr(module, "DeliveryRuntime", lambda **kw: native)
        monkeypatch.setattr(module.time, "monotonic", monotonic)
        return original(config, **kwargs)
    monkeypatch.setattr(module, "_run_delivery", run)
    monkeypatch.setattr(module.DeliverySession, "observe", observe)
    _, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [],
        config_overrides={"project_id": "project"})
    assert result == 0 and count == 6
    assert not native.steered and len(native.sent) == 2
    assert json.loads(native.sent[1])["data"]["trigger"]["kind"] == "periodic_review"
