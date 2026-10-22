"""Regressions for the retained Codex Delivery paging/phase-switch failure."""

import copy
import importlib
import json
from pathlib import Path

import pytest

from modeling_team.tests.test_delivery_decision_input import ack, bound_run
from modeling_team.tests.test_delivery_phase_threads import PhaseRuntime, ready
from modeling_team.tests.test_delivery_session import (
    _run_delivery_with_stub,
    _StubNativeRuntime,
    session,
)
from modeling_team.tests.test_delivery_token_reduction import yield_args
from modeling_team.tests.test_delivery_wakeups import observation


def test_coalesced_updates_keep_delta_without_repeating_known_snapshot(tmp_path):
    host = session(tmp_path)
    host.config["delivery_objective"] = "ALREADY-KNOWN-OBJECTIVE"
    raw = observation()
    host.record_observation(raw)
    ack(host)
    raw["runs"]["run"]["status"]["data"]["stage"]["phase"] = "production"
    host.record_observation(raw)
    raw["operations"]["op"]["data"]["current_role"] = "judge"
    host.record_observation(raw)

    packet = ack(host)

    assert packet["mode"] == "changes"
    assert "runs" not in packet and "operations" not in packet
    assert "task_context" not in packet["core"]
    assert "ALREADY-KNOWN-OBJECTIVE" not in json.dumps(packet)
    assert "production" in json.dumps(packet["changes"])
    assert "judge" in json.dumps(packet["changes"])


def test_paged_phase_hint_is_immutable_across_new_observation_and_resume(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    text = "Retained stage detail. " * 4000
    raw["runs"]["run"]["status"]["data"]["terminal_conclusion"] = text
    host.record_observation(raw)
    first = ack(host)
    original_id = first["input_id"]
    assert first["page"]["offset"] == 0 and not first["coverage"]["complete"]

    raw["operations"]["op"]["data"]["current_role"] = "judge"
    host.record_observation(raw)
    module = importlib.import_module("modeling_team.delivery")
    host = module.DeliverySession(
        repository_root=host.repository_root,
        session_root=host.session_root,
        config=host.config,
        resume=True,
    )
    chunks = [first["page"]["text"]]
    while any(item["input_id"] == original_id for item in host._pending_decisions):
        original = next(item for item in host._pending_decisions if item["input_id"] == original_id)
        page = ack(host, item=original)
        assert page["input_id"] == original_id
        assert page["read_original"] == first["read_original"]
        chunks.append(page["page"]["text"])
    packet = json.loads("".join(chunks))
    assert packet["core"]["phase_thread_handoff"]["thread_boundary"]["phase"] == "acceptance"
    assert text in json.dumps(packet)


def test_phase_switch_preserves_pending_pages_and_latest_facts(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    raw["runs"]["run"]["status"]["data"]["terminal_conclusion"] = "Known detail. " * 5000
    host.record_observation(raw)
    page = ack(host)
    arguments = yield_args(page["input_id"])
    arguments["thread_boundary"] = {
        "phase": "acceptance", "run_id": "run", "request_ids": ["handoff"],
    }
    assert host.call_tool("yield_delivery", arguments)["ok"]
    retained = copy.deepcopy(host._pending_decisions[0])
    raw["operations"]["op"]["data"]["current_role"] = "NEW-JUDGE-STATE"
    host.record_observation(raw)

    runtime = PhaseRuntime()
    assert host.maybe_switch_phase_thread(runtime)
    assert runtime.switches == 1
    assert host.run_ids == {"run"} and host.operation_ids == {"op"}
    assert next(item for item in host._pending_decisions
                if item["input_id"] == retained["input_id"]) == retained
    bootstrap = host._model_observation()
    original = bootstrap.get("read_original")
    body = json.loads(Path(original["path"]).read_text()) if original else bootstrap
    assert "NEW-JUDGE-STATE" in json.dumps(body)
    assert host.phase_thread_history[-1]["status"] == "switched"


@pytest.mark.parametrize("status", ["unknown", "attempted"])
def test_uncertain_native_delivery_still_blocks_phase_switch(tmp_path, monkeypatch, status):
    host, raw = ready(tmp_path, monkeypatch)
    host.record_observation(raw, force_delivery=True)
    host._pending_decisions[-1]["delivery_status"] = status
    assert not host.maybe_switch_phase_thread(PhaseRuntime())


def test_unseen_update_does_not_excuse_a_missing_yield_for_received_input(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    raw["runs"]["run"]["status"]["data"]["stage"]["phase"] = "new-received-phase"
    host.record_observation(raw)
    ack(host)
    raw["operations"]["op"]["data"]["current_role"] = "new-unsent-state"
    host.record_observation(raw)
    assert not host.maybe_switch_phase_thread(PhaseRuntime())


def test_historical_page_current_state_reads_the_model_projection(tmp_path, monkeypatch):
    host, _ = bound_run(tmp_path, monkeypatch)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "Details. " * 8000
    host.record_observation(raw)
    ack(host)
    raw["runs"]["run"]["pending"]["data"]["items"] = []
    raw["runs"]["run"]["status"]["data"]["stage"]["phase"] = "LATEST-PHASE"
    host.record_observation(raw)

    historical = host._model_observation(_item=host._pending_decisions[0])
    current = historical["current_state"]
    assert "/decision-views/" in current["path"]
    data = host.call_tool("read_delivery_artifact", {
        "path": current["path"], "source_ref": current["source_ref"],
        "selection": current["selection"],
    })
    assert data["ok"], data
    assert "LATEST-PHASE" in data["data"]["text"]
    assert "fingerprint_state" not in data["data"]["text"]
    assert "snapshot" not in json.loads(Path(current["path"]).read_text())


@pytest.mark.parametrize("change", ["unknown_write", "request", "host_work", "control", "native"])
def test_completion_does_not_hide_unresolved_work(tmp_path, monkeypatch, change):
    host, raw = ready(tmp_path, monkeypatch)
    host.work_result = "Accepted semantic result"
    host.activity = "read_only_wait"
    raw["operations"]["op"]["data"].update(
        work_state="completed", report_binding={"valid": True},
    )
    host.record_observation(raw)
    assert host._completed_observations_are_quiet()

    if change == "unknown_write":
        raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    elif change == "request":
        root = tmp_path / "run"
        with (root / "control/host-requests.jsonl").open("a") as stream:
            stream.write(json.dumps({"request_id": "unsettled", "action": "standby",
                                     "content_digest": "new"}) + "\n")
        raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    elif change == "host_work":
        from modeling_team.delivery_host_actions import request_host_action
        request_host_action(host.session_root, host.session_id, host.run_ids,
                            host.authorization, {
                                "request_id": "repair-needed", "run_id": "run",
                                "kind": "platform_repair", "bindings": {},
                            })
    elif change == "control":
        raw["operations"]["op"]["data"]["control_receipts"] = {
            "pause": {"status": "pending"},
        }
    else:
        host._pending_decisions[-1]["delivery_status"] = "unknown"
    host.record_observation(raw)
    assert not host._completed_observations_are_quiet()


@pytest.mark.parametrize("late_unknown", [False, True])
def test_completed_delivery_keeps_old_pages_quiet_but_surfaces_unknown(
    tmp_path, monkeypatch, late_unknown,
):
    module = importlib.import_module("modeling_team.delivery")
    count = 0
    ticks = 0
    native = None
    host = None

    def observe(self):
        nonlocal count, host
        host = self
        count += 1
        if count == 8:
            self.finished = True
        raw = {"runs": {}, "operations": {}, "repair_verifications": {}}
        if count == 1:
            self.config["delivery_objective"] = "Original task detail. " * 5000
        if late_unknown and count >= 6:
            raw["operations"]["op"] = {
                "ok": False, "error": {"code": "artifact_unavailable"},
            }
        return raw

    def monotonic():
        nonlocal ticks
        ticks += 3
        return ticks

    class Native(_StubNativeRuntime):
        def poll(self, timeout=0):
            if not self.busy:
                return []
            host.work_result = "Completed authorized work"
            host.activity = "read_only_wait"
            self.busy = False
            return [{"event": "turn_completed", "status": "completed"}]

    def factory(**kwargs):
        nonlocal native
        native = Native()
        return native

    original = module._run_delivery

    def run(config, **kwargs):
        monkeypatch.setattr(module, "DeliveryRuntime", factory)
        monkeypatch.setattr(module.time, "monotonic", monotonic)
        return original(config, **kwargs)

    monkeypatch.setattr(module, "_run_delivery", run)
    monkeypatch.setattr(module.DeliverySession, "observe", observe)
    _, result, _ = _run_delivery_with_stub(
        tmp_path, monkeypatch, [], config_overrides={"project_id": "project"},
    )
    assert result == 0 and count == 8
    if late_unknown:
        assert "artifact_unavailable" in native.sent[1]
    else:
        assert len(native.sent) == 1
        assert host._pending_decisions  # retained, never falsely acknowledged
