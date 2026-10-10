"""R4.0-028 lifecycle boundaries; these deterministic checks do not judge semantics."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from modeling_team.runner import TeamRunner
from modeling_team.interventions import RecoverableOuterInputError
from modeling_team.platform_scope import PlatformScope, PlatformScopeError
from modeling_team.tests.test_platform_scope import RetainedProducerClient
from modeling_team.runtimes.base import RuntimeMessage
from modeling_team.checkpoint_recovery import POSSIBLY_LIVE_STATES, acquire_acceptance_lock, acquire_root_run_lock
from modeling_team.evaluation_owner import EvaluationOwner
from modeling_team.acceptance_runtime import ExaminerRunMetrics, ExaminerRuntimeBlocked


def runner(tmp_path):
    root = tmp_path / "run"
    (root / "evidence").mkdir(parents=True)
    adapter = SimpleNamespace(agents={}, messages=[], receive_messages=lambda: [])
    adapter.send_message = lambda agent, delivery: adapter.messages.append((agent, delivery))
    item = TeamRunner(repository_root=tmp_path, adapter=adapter)
    item.run = SimpleNamespace(run_id="source", root=root, configuration=SimpleNamespace(profile=SimpleNamespace(
        agents=[SimpleNamespace(agent_id="coordinator", package=SimpleNamespace(role="coordinator"))])))
    item.transport = SimpleNamespace(drain=lambda: [])
    ready = {"pending_agents": [], "pending_writes": False, "unknown_writes": [], "in_flight_writes": 0}
    item._cq_production_readiness = lambda: ready
    item._issue_coordinator_id = lambda: "coordinator"
    item.scope = SimpleNamespace(project_id="project", ontology_ids=["ontology"], seal_work=lambda: {
        "write_credentials_non_active": True, "model_revisions": {"ontology": 1}})
    return item, ready


def test_pending_work_does_not_quiesce_or_destroy_run(tmp_path):
    item, ready = runner(tmp_path)
    ready["pending_agents"] = ["modeling"]
    with pytest.raises(RecoverableOuterInputError, match="still have work"):
        item.standby()
    assert item._cq_write_admission.snapshot()["phase"] == "open"
    assert not hasattr(item, "_standby_receipt")


def test_unknown_write_stays_recoverable_then_seals_and_consults_original_thread(tmp_path):
    item, ready = runner(tmp_path)
    ready.update(pending_writes=True, unknown_writes=[{"intent": "unknown"}])
    with pytest.raises(RecoverableOuterInputError):
        item.standby()
    assert item._cq_write_admission.snapshot()["phase"] == "quiescing"
    ready.update(pending_writes=False, unknown_writes=[])
    item._coordinator_final_captured = True
    receipt = item.standby()
    assert receipt["lifecycle"] == "standby"
    assert item._cq_write_admission.admit("later-write") is None
    original = root_bytes = (item.run.root / "state.json").read_bytes()
    item.receive_outer({"action": "consult", "text": "解释原决定"})
    assert item.adapter.messages[-1][0] == "coordinator"
    assert "解释原决定" in item.adapter.messages[-1][1].text
    assert (item.run.root / "state.json").read_bytes() == original == root_bytes
    item.adapter.receive_messages = lambda: [RuntimeMessage("coordinator", "沿原上下文解释")]
    assert item.drain()[0]["type"] == "consult-reply"
    assert item._coordinator_final_captured is True


def test_pause_and_resume_are_messages_without_runtime_freeze(tmp_path):
    item, _ = runner(tmp_path)
    item.drain = lambda: []
    for action in ("pause", "resume"):
        output = item.receive_outer({"action": action, "request_id": action})
        assert output[0]["confirmation"] == "pending"
    assert [message.kind for _, message in item.adapter.messages] == ["user-control", "user-control"]
    assert item._cq_write_admission.snapshot()["phase"] == "open"


def test_scope_seal_reuses_terminal_readback_and_revokes_only_keys_without_deleting_model():
    class Client(RetainedProducerClient):
        def __call__(self, method, path, body, key):
            if path.endswith("workspace-context"):
                return 200, {"state": "ready", "ontology_id": "ontology-1", "model_revision": 1}
            return super().__call__(method, path, body, key)
    client = Client()
    scope = PlatformScope("http://fixture", "run", lambda: ("admin", "admin-id"), lambda _: True, client)
    scope.prepare({"mode": "create"})
    client.written = True
    result = scope.seal_work()
    assert result["write_credentials_non_active"] and result["terminal"]["sessions_terminal"]
    assert scope.protocol_key is None and scope.admin_key is None
    assert scope.cleanup()["scope_disposition"] == "sealed-retained"
    assert not any(method == "DELETE" for method, _ in client.calls)


def test_live_standby_remains_writer_for_production_and_acceptance_lock_is_separate(tmp_path):
    assert {"STANDBY", "READ_ONLY_WAIT"} <= POSSIBLY_LIVE_STATES
    production = acquire_root_run_lock("same-root", tmp_path)
    try:
        acceptance = acquire_acceptance_lock("same-root", tmp_path)
        acceptance.release()
    finally:
        production.release()


def test_stage_pause_holds_next_role_until_explicit_resume(tmp_path):
    owner = EvaluationOwner(tmp_path)
    def send(action):
        with (tmp_path / "input.fifo").open("w") as stream:
            stream.write(json.dumps({"request_id": action, "action": action, "text": action}) + "\n")
    send("pause")
    worker = threading.Thread(target=owner.before_next_task)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while not owner.pending_pause and time.monotonic() < deadline:
            time.sleep(0.01)
        assert owner.pending_pause == "pause"
        assert worker.is_alive() and owner.current is None and not owner.retained
        assert json.loads((tmp_path / "state.json").read_text())["stage_waiting"]
        send("resume")
        worker.join(2)
        assert not worker.is_alive() and owner.pending_pause is None
    finally:
        owner.pending_pause = None
        worker.join(2)
        owner.close()


def test_explicit_control_turn_preserves_usage_and_rejects_unrequested_turn():
    metrics = ExaminerRunMetrics("consumer", max_inference_steps=None)
    metrics.bind_thread("same-thread")
    def usage(turn, count):
        metrics.observe_notification({"method": "thread/tokenUsage/updated", "params": {
            "threadId": "same-thread", "turnId": turn,
            "tokenUsage": {"total": {"totalTokens": count, "inputTokens": count, "outputTokens": 0}}}})
    usage("first", 10)
    metrics.allow_control_turn()
    usage("explicit-resume", 20)
    assert metrics.thread_id == "same-thread" and metrics._totals["totalTokens"] == 20
    with pytest.raises(ExaminerRuntimeBlocked):
        usage("unrequested", 30)


@pytest.mark.parametrize("invalid", ["active", "lease", "attempt", "malformed"])
def test_existing_scope_cannot_seal_active_or_unsettled_resources(invalid):
    scope = PlatformScope.__new__(PlatformScope)
    scope.project_id, scope.ontology_ids = "project", ["ontology"]
    detail = {"session": {"project_id": "project", "status": "completed"},
              "involved_ontology_ids": ["ontology"], "leases": [], "modeling_batches": []}
    if invalid == "active": detail["session"]["status"] = "active"
    if invalid == "lease": detail["leases"] = [{"state": "active"}]
    if invalid == "attempt": detail["modeling_batches"] = [{"latest_attempt": {"attempt_status": "applying"}}]
    if invalid == "malformed": detail["leases"] = {}
    scope._ok = lambda method, path: {"agent_state": {"recent_sessions": [{"id": "session"}]}} if path.endswith("build-context") else detail
    with pytest.raises(PlatformScopeError):
        scope._work_terminal_state([])


def test_closed_continuation_uses_new_report_and_rejects_source_drift(tmp_path):
    from modeling_team import checkpoint_recovery as cr
    from modeling_team.checkpoints import manifest_path, manifest_digest
    source, output = tmp_path / "source", tmp_path / "continuation"
    handoff = source / "acceptance-v3/production-handoff.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("original frozen source")
    manifest = manifest_path(source, "checkpoint-0001")
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    recovery = output / cr.RECOVERY_DIRECTORY
    recovery.mkdir(parents=True)
    origin = {"kind": "acceptance_continuation", "source_run_id": source.name,
              "new_run_id": output.name, "handoff_digest": cr.file_digest(handoff),
              "checkpoint_id": "checkpoint-0001", "checkpoint_digest": manifest_digest(manifest),
              "batch_id": "batch", "freeze_digest": "freeze"}
    (recovery / "origin.json").write_text(json.dumps(origin))
    cr.write_acceptance_continuation_record(output, {"source_run_id": source.name,
        "new_run_id": output.name, "report_published": True, "batch_id": "batch", "attempt_id": "attempt"})
    report = output / "acceptance-v3/reports/batch/attempt/batch-report.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"run_id": source.name, "batch_id": "batch", "freeze_digest": "freeze",
        "sessions": {"cleanup": {"tasks_closed": True}}}))
    assert cr.acceptance_continuation_report(source, output) == report
    assert handoff.read_text() == "original frozen source"
    handoff.write_text("changed")
    with pytest.raises(cr.CheckpointError):
        cr.acceptance_continuation_report(source, output)
