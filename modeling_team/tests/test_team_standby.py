"""R4.0-028 lifecycle boundaries; these deterministic checks do not judge semantics."""
import json
import hashlib
import os
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
    assert result["ontology_ids"] == ["ontology-1"]
    assert result["model_revisions"] == {"ontology-1": 1}
    assert result["terminal"]["session_ids"] == ["session-1"]
    assert scope.protocol_key is None and scope.admin_key is None
    assert scope.cleanup()["scope_disposition"] == "sealed-retained"
    assert not any(method == "DELETE" for method, _ in client.calls)


@pytest.mark.parametrize("ontology_ids", [[], ["ontology-1", "ontology-2"]])
def test_scope_seal_reads_each_real_revision_and_keeps_plan_identity(ontology_ids):
    class Client(RetainedProducerClient):
        def __call__(self, method, path, body, key):
            if path.endswith("workspace-context"):
                self.calls.append((method, path))
                identity = path.split("/")[-2]
                return 200, {"state": "ready", "ontology_id": identity,
                             "workspace": {"model_revision": {"ontology-1": 2, "ontology-2": 3}[identity]}}
            return super().__call__(method, path, body, key)
    client = Client()
    scope = PlatformScope("http://fixture", "run", lambda: ("admin", "admin-id"), lambda _: True, client)
    scope.prepare({"mode": "create"})
    scope.ontology_ids = list(ontology_ids)
    client.written = True
    result = scope.seal_work()
    expected = {identity: {"ontology-1": 2, "ontology-2": 3}[identity]
                for identity in ontology_ids or ["ontology-1"]}
    assert result["model_revisions"] == expected
    assert result["ontology_ids"] == list(expected)
    assert scope.ontology_ids == ontology_ids
    assert result["terminal"]["session_ids"] == ["session-1"]
    assert all(("GET", f"/api/ontologies/{identity}/workspace-context") in client.calls for identity in expected)


@pytest.mark.parametrize("defect", ["active", "lease", "missing-revision"])
def test_singleton_seal_rejects_unsettled_source_before_revoking_keys(defect):
    class Client(RetainedProducerClient):
        def __call__(self, method, path, body, key):
            if path.endswith("workspace-context"):
                return 200, {"state": "ready", **({"model_revision": 2} if defect != "missing-revision" else {})}
            status, value = super().__call__(method, path, body, key)
            if path == "/api/build-sessions/session-1" and defect == "lease":
                value["leases"] = [{"state": "active"}]
            return status, value
    client = Client()
    scope = PlatformScope("http://fixture", "run", lambda: ("admin", "admin-id"), lambda _: True, client)
    scope.prepare({"mode": "create"})
    client.written = True
    if defect == "active":
        client.session_status = "active"
    with pytest.raises(PlatformScopeError):
        scope.seal_work()
    assert scope.protocol_key and scope.admin_key
    assert not any(path.endswith(":revoke") or method == "DELETE" for method, path in client.calls)


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


@pytest.fixture
def legacy_singleton_source(tmp_path, monkeypatch):
    from modeling_team import checkpoint_recovery as cr, host_ops
    from modeling_team.checkpoints import CheckpointArtifactSpec, StagePackage, save_checkpoint
    from modeling_team.competency_questions import CQ_FREEZE_SCHEMA, freeze_question_pool

    source = tmp_path / "modeling_team" / "runs" / "source"
    frozen_dir = source / "competency-questions" / "frozen"
    frozen_dir.mkdir(parents=True)
    frozen = freeze_question_pool({
        "schema_version": CQ_FREEZE_SCHEMA, "batch_id": "batch-offline", "material_digest": "offline",
        "panorama_question_ids": ["cq-1"], "slice_question_ids": [], "ordering": ["cq-1"],
        "review_binding": {"review_id": "review-1", "review_content_version": 1,
                           "decision_digest": "sha256:" + "0" * 64},
        "questions": [{"question_id": "cq-1", "scope": {"kind": "panorama", "slice_ids": []},
                       "question": "Synthetic public question?", "answer_points": ["synthetic"],
                       "evidence_refs": [{"source": "synthetic", "locator": "section 1"}],
                       "unknown": [], "proposed_visibility": "public", "content_version": 1}],
    })
    (frozen_dir / "freeze-0001.json").write_text(json.dumps(frozen))
    handoff_path = source / "acceptance-v3" / "production-handoff.json"
    handoff_path.parent.mkdir()
    handoff_path.write_text(json.dumps({
        "schema_version": "r3-0-012-production-handoff/v1", "run_id": source.name,
        "scope_binding": {"project_id": "project-1", "ontology_ids": ["ontology-1"]},
        "freeze_id": frozen["batch_id"], "batch_id": frozen["batch_id"],
        "freeze_digest": frozen["snapshot_digest"], "write_phase": "read-only",
        "ready": True, "pending_writes": False, "unknown_writes": [],
    }))
    snapshot = {
        "schema_version": "r4-0-026-platform-data/v3", "project_id": "project-1",
        "ontology_ids": ["ontology-1"],
        "tables": {"ontologies": [{"id": "ontology-1", "project_id": "project-1", "model_revision": 2}]},
        "graphs": {}, "completed_operations": [],
    }
    snapshot["digest"] = hashlib.sha256(json.dumps(
        snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()
    saved = save_checkpoint(source, StagePackage(
        kind=cr.CHECKPOINT_KIND_PRODUCTION_HANDOFF, scope_refs={"freeze_id": frozen["batch_id"]},
        artifacts=[CheckpointArtifactSpec("acceptance-v3/production-handoff.json", "host", ("host",), host_private=True)],
        platform_bindings={"project_id": "project-1", "ontology_ids": ["ontology-1"]}, platform_data=snapshot,
    ), source_run_id=source.name)
    checkpoint_id = saved["checkpoint_id"]
    state = {
        "state": "READ_ONLY_WAIT", "owner_pid": os.getpid(), "standby_request_id": "standby-1",
        "write_phase": "read-only", "readiness": {"in_flight_writes": 0, "unknown_writes": []},
        "handoff_digest": cr.file_digest(source / "acceptance-v3/production-handoff.json"),
        "write_seal": {
            "project_id": "project-1", "ontology_ids": [], "model_revisions": {},
            "write_credentials_non_active": True, "terminal": {"sessions_terminal": True, "session_ids": []},
            "project_scoped_keys": [{"id": "model-key"}],
            "second_stage": {"org_admin_key": {"id": "admin-id"}},
        },
    }
    (source / "state.json").write_text(json.dumps(state))
    receipt = {"outcome": "accepted", "action": "standby"}
    monkeypatch.setattr(host_ops, "get_request_result", lambda *args, **kwargs: dict(receipt))
    monkeypatch.setattr(host_ops, "get_run_status", lambda *args, **kwargs: {
        "liveness": {"process_observation": {"pid": os.getpid()}}})
    responses = {
        "/api/api-keys/model-key": {"id": "model-key", "revoked_at": "now"},
        "/api/api-keys/admin-id": {"id": "admin-id", "revoked_at": "now"},
        "/api/ontologies/ontology-1/workspace-context": {
            "state": "ready", "ontology_id": "ontology-1", "workspace": {"model_revision": 2}},
        "/api/projects/project-1/build-context": {
            "agent_state": {"active_sessions": [], "recent_sessions": [{"id": "session-1"}]}},
        "/api/build-sessions/session-1": {
            "session": {"project_id": "project-1", "status": "completed"},
            "involved_ontology_ids": ["ontology-1"], "leases": [{"state": "released"}], "modeling_batches": []},
    }
    calls = []
    def request(method, path, body, key):
        assert method == "GET" and body is None
        calls.append(path)
        if path.split("?")[0].endswith("modeling-batches"):
            return 200, {"items": [], "next_cursor": None}
        return 200, responses[path]
    return SimpleNamespace(source=source, checkpoint_id=checkpoint_id, state=state,
                           receipt=receipt, responses=responses, calls=calls,
                           readback=cr.PlatformReadback(request, "offline-readback"))


@pytest.mark.parametrize("revision", [2, 3])
def test_s4_recovers_old_singleton_from_checkpoint_without_source_mutation(legacy_singleton_source, revision):
    from modeling_team import checkpoint_recovery as cr
    fixture = legacy_singleton_source
    # Exercise both observed production revisions with a consistent immutable
    # snapshot; all fixture construction happens before the read-only check.
    if revision == 3:
        _replace_legacy_snapshot(fixture, lambda value: value["tables"]["ontologies"][0].update(model_revision=3))
        fixture.responses["/api/ontologies/ontology-1/workspace-context"]["workspace"]["model_revision"] = 3
    before = {path.relative_to(fixture.source): path.read_bytes()
              for path in fixture.source.rglob("*") if path.is_file()}
    continuation = cr.prepare_acceptance_continuation(
        source_run_root=fixture.source, checkpoint_id=fixture.checkpoint_id, new_run_id="acceptance-new",
        readback=fixture.readback, live_source_request_id="standby-1",
        question_visibility="public",
    )
    live = continuation.writer["live_source_seal"]
    assert live["model_revisions"] == {"ontology-1": revision}
    assert live["model_revision_basis"]["checkpoint_id"] == fixture.checkpoint_id
    assert {path.relative_to(fixture.source): path.read_bytes()
            for path in fixture.source.rglob("*") if path.is_file()} == before
    assert {"/api/api-keys/model-key", "/api/api-keys/admin-id", "/api/build-sessions/session-1"} <= set(fixture.calls)
    assert not (fixture.source.parent / "acceptance-new").exists()


def _replace_legacy_snapshot(fixture, change):
    """Construct a different test checkpoint before verification starts."""
    from modeling_team import checkpoint_recovery as cr
    manifest_path = cr.manifest_path(fixture.source, fixture.checkpoint_id)
    manifest = json.loads(manifest_path.read_text())
    path = manifest_path.parent / cr.PLATFORM_DATA_PATH
    value = json.loads(path.read_text())
    change(value)
    value["digest"] = hashlib.sha256(json.dumps(
        {key: item for key, item in value.items() if key != "digest"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()
    path.write_text(json.dumps(value))
    manifest["platform_data"].update(digest=cr.file_digest(path), snapshot_digest=value["digest"])
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("defect,code", [
    ("changed-model", "acceptance_binding_changed"), ("explicit-old-seal", "acceptance_binding_changed"),
    ("active-source", "source_active"), ("stale-receipt", "source_active"),
    ("unrevoked-key", "source_active"), ("unknown-write", "source_active"),
    ("active-session", "source_active"), ("active-lease", "source_active"),
    ("applying-attempt", "source_active"), ("missing-keys", "source_active"),
    ("missing-snapshot", "source_active"), ("snapshot-tamper", "source_active"),
    ("snapshot-scope", "acceptance_binding_changed"), ("snapshot-bool-revision", "acceptance_binding_changed"),
    ("handoff-tamper", "acceptance_binding_changed"), ("multi-scope", "source_active"),
])
def test_s4_legacy_recovery_keeps_integrity_gates(legacy_singleton_source, defect, code):
    from modeling_team import checkpoint_recovery as cr
    fixture = legacy_singleton_source
    state, responses = fixture.state, fixture.responses
    if defect == "changed-model":
        responses["/api/ontologies/ontology-1/workspace-context"]["workspace"]["model_revision"] = 3
    elif defect == "explicit-old-seal":
        state["write_seal"]["model_revisions"] = {"ontology-1": 1}
    elif defect == "active-source":
        state["state"] = "RUNNING"
    elif defect == "stale-receipt":
        state["standby_request_id"] = "previous-standby"
    elif defect == "unrevoked-key":
        responses["/api/api-keys/model-key"]["revoked_at"] = None
    elif defect == "unknown-write":
        state["readiness"]["unknown_writes"] = ["unresolved"]
    elif defect == "active-session":
        responses["/api/build-sessions/session-1"]["session"]["status"] = "active"
    elif defect == "active-lease":
        responses["/api/build-sessions/session-1"]["leases"][0]["state"] = "active"
    elif defect == "applying-attempt":
        responses["/api/build-sessions/session-1"]["modeling_batches"] = [{"latest_attempt": {"attempt_status": "applying"}}]
    elif defect == "missing-keys":
        state["write_seal"]["project_scoped_keys"] = []
    elif defect in {"missing-snapshot", "snapshot-tamper"}:
        path = cr.manifest_path(fixture.source, fixture.checkpoint_id).parent / cr.PLATFORM_DATA_PATH
        if defect == "missing-snapshot":
            path.unlink()
        else:
            path.write_text("{}")
    elif defect == "snapshot-scope":
        _replace_legacy_snapshot(fixture, lambda value: value.update(project_id="foreign-project"))
    elif defect == "snapshot-bool-revision":
        _replace_legacy_snapshot(fixture, lambda value: value["tables"]["ontologies"][0].update(model_revision=True))
    elif defect == "handoff-tamper":
        (fixture.source / "acceptance-v3/production-handoff.json").write_text("{}")
    elif defect == "multi-scope":
        state["write_seal"]["ontology_ids"] = ["ontology-1", "ontology-2"]
    (fixture.source / "state.json").write_text(json.dumps(state))
    before = {path.relative_to(fixture.source): path.read_bytes()
              for path in fixture.source.rglob("*") if path.is_file()}
    with pytest.raises(cr.CheckpointError) as error:
        cr.prepare_acceptance_continuation(
            source_run_root=fixture.source, checkpoint_id=fixture.checkpoint_id, new_run_id="acceptance-new",
            readback=fixture.readback, live_source_request_id="standby-1",
            question_visibility="public",
        )
    assert error.value.reason_code == code
    assert {path.relative_to(fixture.source): path.read_bytes()
            for path in fixture.source.rglob("*") if path.is_file()} == before
