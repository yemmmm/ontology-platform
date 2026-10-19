"""Phase handoff preserves the task and uses actual receipts, without a model call."""
import json

import pytest

from modeling_team.delivery import DeliverySession
from modeling_team.tests.test_delivery_decision_input import ack, bound_run
from modeling_team.tests.test_delivery_session import ROOT
from modeling_team.tests.test_delivery_token_reduction import yield_args
from modeling_team.tests.test_delivery_wakeups import observation


class PhaseRuntime:
    busy = False
    thread_id = "old-thread"
    switches = 0

    @property
    def identity(self):
        return {"runtime": "codex", "process_instance": "same-process",
                "runtime_session_id": self.thread_id, "activity_id": None}

    def new_thread(self):
        self.switches += 1
        self.thread_id = "new-thread"
        return self.identity


def ready(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    host.config["phase_thread_boundaries"] = ["acceptance"]
    host.config["delivery_objective"] = "Keep all original questions and the original round budget."
    host.accept_user_input("Preserve this earlier user constraint.")
    host.operation_ids.add("op")
    host.operation_kinds["op"] = "evaluation"
    request = {"request_id": "handoff", "content_digest": "d1",
               "action": "cq_handoff_complete"}
    (root / "control/host-requests.jsonl").write_text(json.dumps(request) + "\n")
    (root / "evidence/outer-input-receipts.jsonl").write_text(json.dumps({
        **request, "outcome": "accepted"}) + "\n")
    raw = observation()
    run = raw["runs"]["run"]
    run["request_ledger"] = host._observe_request_ledger("run")
    run["pending"]["data"]["items"] = []
    run["status"]["data"]["write_phase"] = "read-only"
    raw["operations"]["op"]["data"].update(run_id="run", mode="cq-acceptance",
        request_binding={"run_id": "run", "freeze_id": "f1"})
    host.record_observation(raw)
    current = ack(host)
    args = yield_args(current["input_id"])
    args["waiting_for"] = [{"operation_id": "op", "condition": "independent report"}]
    args["thread_boundary"] = {"phase": "acceptance", "run_id": "run",
                               "request_ids": ["handoff"]}
    assert host.call_tool("yield_delivery", args)["ok"]
    return host, raw


def test_phase_switch_rebuilds_facts_constraints_and_decisions_once(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    runtime = PhaseRuntime()
    host.native_thread_id = runtime.thread_id
    host.runtime_identity = runtime.identity
    assert host.maybe_switch_phase_thread(runtime)
    assert host.run_ids == {"run"} and host.operation_ids == {"op"}
    assert runtime.switches == 1 and host.native_thread_id == "new-thread"
    packet = ack(host)
    assert packet["mode"] == "bootstrap"
    assert packet["core"]["task_context"]["delivery_objective"] == host.config["delivery_objective"]
    assert "earlier user constraint" in json.dumps(packet["recovery_context"])
    assert packet["continuation"]["active_decisions"][0]["decision_id"] == "keep-scope"
    assert packet["operations"]["op"]["data"]["request_binding"]["freeze_id"] == "f1"
    assert not host.maybe_switch_phase_thread(runtime)
    saved = json.loads((host.session_root / "session.json").read_text())
    assert saved["phase_thread_history"][-1]["to_identity"]["runtime_session_id"] == "new-thread"
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert reopened.phase_thread_history == host.phase_thread_history
    assert not reopened.maybe_switch_phase_thread(runtime)


@pytest.mark.parametrize("block", ["disabled", "busy", "user_input", "pending_page",
                                   "unknown_receipt", "unknown_write", "missing_operation"])
def test_unsafe_or_disabled_boundary_keeps_original_thread(tmp_path, monkeypatch, block):
    host, raw = ready(tmp_path, monkeypatch)
    runtime = PhaseRuntime()
    pending = []
    if block == "disabled":
        host.config["phase_thread_boundaries"] = []
    elif block == "busy":
        runtime.busy = True
    elif block == "user_input":
        pending = [{"text": "new control"}]
    elif block == "pending_page":
        host.record_observation(raw, force_delivery=True)
    elif block == "unknown_receipt":
        host._last_current["runs"]["run"]["requests"]["data"]["pending"].append({
            "request_id": "unknown", "result": {"ok": True, "data": {"outcome": "unknown"}}})
    elif block == "unknown_write":
        host._last_current["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    elif block == "missing_operation":
        host._last_current["operations"] = {}
    assert not host.maybe_switch_phase_thread(runtime, pending_inputs=pending)
    assert runtime.switches == 0 and runtime.thread_id == "old-thread"


def test_thread_creation_failure_is_recoverable_without_replaying_or_hot_retry(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    runtime = PhaseRuntime()
    def fail():
        runtime.switches += 1
        raise RuntimeError("creation receipt unavailable")
    runtime.new_thread = fail
    assert not host.maybe_switch_phase_thread(runtime)
    assert not host.maybe_switch_phase_thread(runtime)
    assert runtime.switches == 1 and runtime.thread_id == "old-thread"
    assert host.phase_thread_history[-1]["status"] == "failed"
    assert host.run_ids == {"run"} and not host.finished


def test_new_observation_requires_fresh_effective_decisions_before_switch(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    raw["runs"]["run"]["status"]["data"]["stage"] = {"phase": "acceptance"}
    host.record_observation(raw)
    ack(host)
    runtime = PhaseRuntime()
    assert not host.maybe_switch_phase_thread(runtime)
    assert runtime.switches == 0


def test_explicit_empty_effective_decisions_can_cross_a_settled_boundary(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    args = {key: value for key, value in host.last_yield.items() if key in {
        "input_id", "phase", "waiting_for", "next_action", "reason", "active_decisions", "thread_boundary"}}
    args["active_decisions"] = []
    assert host.call_tool("yield_delivery", args)["ok"]
    assert host.maybe_switch_phase_thread(PhaseRuntime())


def test_production_switch_requires_consumed_freeze_and_notification(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.config["phase_thread_boundaries"] = ["production"]
    root = tmp_path / "run"
    requests = [{"request_id": "freeze", "action": "cq_freeze", "content_digest": "d2"},
                {"request_id": "notify", "action": "instruction", "content_digest": "d3"}]
    (root / "control/host-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in requests))
    receipts = root / "evidence/outer-input-receipts.jsonl"
    receipts.write_text(json.dumps({**requests[0], "outcome": "accepted"}) + "\n")
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    packet = ack(host)
    args = yield_args(packet["input_id"])
    args["thread_boundary"] = {"phase": "production", "run_id": "run",
                               "request_ids": ["freeze", "notify"]}
    assert host.call_tool("yield_delivery", args)["ok"]
    runtime = PhaseRuntime()
    assert not host.maybe_switch_phase_thread(runtime)
    receipts.write_text("".join(json.dumps({**r, "outcome": "accepted"}) + "\n" for r in requests))
    host.record_observation(raw)
    args["input_id"] = ack(host)["input_id"]
    assert host.call_tool("yield_delivery", args)["ok"]
    assert host.maybe_switch_phase_thread(runtime)


def test_changed_receipt_is_visible_without_a_followup_model_query(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    request = {"request_id": "notify", "content_digest": "d1", "action": "instruction"}
    (root / "control/host-requests.jsonl").write_text(json.dumps(request) + "\n")
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    ack(host)
    (root / "evidence/outer-input-receipts.jsonl").write_text(json.dumps({
        **request, "outcome": "accepted"}) + "\n")
    host.record_observation(raw)
    packet = ack(host)
    receipt = packet["request_results"][0]
    assert receipt["request_id"] == "notify" and receipt["outcome"] == "accepted"
    assert receipt["action"] == "instruction"
    assert not any(change["path"][:5] == ["runs", "run", "requests", "data", "settled"]
                   for change in packet["changes"])
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "read-only"
    host.record_observation(raw)
    assert ack(host)["request_results"] == []
