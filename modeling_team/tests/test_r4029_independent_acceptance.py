"""Independent R4.0-029 controlled contract acceptance; no semantic production."""
from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from modeling_team.incremental import IncrementalError, prepare_incremental, start_incremental
from modeling_team.delivery import DeliverySession
from modeling_team.platform_scope import PlatformScope, PlatformScopeError
from modeling_team.staged_decisions import (
    StagedBatchForwardUnknown, StagedSubmissionRejection, build_identity_binding, projection_digest,
    unified_identity_issue,
)
from modeling_team.tests.test_v43_production_refs import CANDIDATE, PLAN1, production  # noqa: F401

# ruff: noqa: F811 - reuse the existing production contract fixture, not product writes


class CurrentModelAPI:
    """Record side effects while providing exact current Project membership."""

    def __init__(self):
        self.calls = []
        self.ontologies = [
            {"id": "model-a", "name": "Shared name"},
            {"id": "model-b", "name": "Shared name"},
        ]
        self.active = []
        self.unknown_create = False

    def __call__(self, method, path, body, key):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path == "/api/projects/project-p/ontologies":
            if method == "GET":
                return 200, copy.deepcopy(self.ontologies)
            if method == "POST":
                self.ontologies.append({"id": "created-this-run", "name": body["name"]})
                if self.unknown_create:
                    raise TimeoutError("response lost after create")
                return 201, {"id": "created-this-run"}
        if path.endswith("workspace-context"):
            identity = path.split("/")[-2]
            return 200, {"state": "ready", "ontology_id": identity, "model_revision": 7}
        if path.endswith("modeling-context"):
            return 200, {"semantic_base_iri": "urn:current:", "workspace": {"model_revision": 7},
                         "project": {"id": "project-p"}, "ontology": {"id": path.split("/")[-2]}}
        if path.endswith("modeling-batches"):
            return 200, {"items": []}
        if path.endswith("build-context"):
            return 200, {"agent_state": {"active_sessions": self.active, "recent_sessions": []}}
        if path == "/api/auth/me":
            return 200, {"user_id": "operator"}
        if path == "/api/api-keys" and method == "POST":
            return 201, {"id": "new-run-key", "plaintext_key": "controlled-key"}
        if path.endswith(":revoke"):
            return 200, {"revoked_at": "controlled-now"}
        return 200, {"id": "project-p"}

    @property
    def creates(self):
        return [call for call in self.calls if call[:2] == ("POST", "/api/projects/project-p/ontologies")]


def bound_scope(api, ids=None, **options):
    scope = PlatformScope("http://unused", "independent-new-run", lambda: ("admin", "admin-id"),
                          lambda _: True, request=api)
    scope.prepare({"mode": "existing", "project_id": "project-p",
                   "ontology_ids": ids or ["model-a", "model-b"], **options})
    return scope


def test_a3_exact_multi_identity_with_same_names():
    api = CurrentModelAPI()
    scope = bound_scope(api)
    assert scope.ontology_ids == ["model-a", "model-b"]
    assert scope.owned is False
    assert not api.creates
    for identity in scope.ontology_ids:
        assert ("GET", f"/api/ontologies/{identity}/workspace-context", None) in api.calls


@pytest.mark.parametrize("ids", [["missing"], ["foreign-project-model"], ["model-a", "model-a"]])
def test_a3_invalid_scope_never_creates_replacement(ids):
    api = CurrentModelAPI()
    with pytest.raises(PlatformScopeError):
        bound_scope(api, ids)
    assert not api.creates


def test_a3_legacy_single_identity_preserved():
    api = CurrentModelAPI()
    scope = PlatformScope("http://unused", "single-run", lambda: ("admin", "admin-id"),
                          lambda _: True, request=api)
    scope.prepare({"mode": "existing", "project_id": "project-p", "ontology_id": "model-b"})
    assert scope.ontology_id == "model-b"
    assert not api.creates


def test_a6_unauthorized_topology_has_no_partial_create():
    api = CurrentModelAPI()
    scope = bound_scope(api)
    with pytest.raises(PlatformScopeError, match="authoriz"):
        scope.apply_ontology_plan([{"ontology_id": "model-a", "slice_ids": ["current"]},
                                   {"name": "Shared name", "slice_ids": ["new"]}])
    assert not api.creates


def test_a6_new_topology_uses_own_receipt_and_not_same_name():
    api = CurrentModelAPI()
    scope = bound_scope(api, allow_new_ontologies=True)
    plan = [{"ontology_id": "model-b", "slice_ids": ["current"]},
            {"name": "Shared name", "slice_ids": ["new"]}]
    assert scope.apply_ontology_plan(plan) == ["model-b", "created-this-run"]
    assert scope.apply_ontology_plan(plan) == ["model-b", "created-this-run"]
    assert len(api.creates) == 1


def test_a3_subset_topology_keeps_entire_original_authorized_scope():
    api = CurrentModelAPI()
    scope = bound_scope(api)
    assert scope.apply_ontology_plan([{"ontology_id": "model-b", "slice_ids": ["current"]}]) == ["model-b"]
    assert scope.ontology_ids == ["model-a", "model-b"]
    assert scope.ontology_plan_ids == ["model-b"]
    assert set(scope.read_protocol_context()["ontology_ids"].split(",")) == {"model-a", "model-b"}


def test_a6_mapping_uses_ordered_plan_ids_without_shrinking_scope():
    api = CurrentModelAPI()
    scope = bound_scope(api, allow_new_ontologies=True)
    plan = [{"ontology_id": "model-b", "slice_ids": ["current"]},
            {"name": "Shared name", "slice_ids": ["new"]}]
    assert scope.apply_ontology_plan(plan) == ["model-b", "created-this-run"]
    scope.apply_mapping_reference_ontologies({"cross_slice_dependencies": [{
        "from_slice": "new", "to_slice": "current", "direction": "approved connection",
        "connection_points": ["stable-definition"]}]}, plan,
        dependent_direction="from_slice_depends_on_to_slice")
    patches = [(path, body) for method, path, body in api.calls if method == "PATCH"]
    assert patches == [("/api/ontologies/created-this-run", {"reference_ontology_ids": ["model-b"]})]
    assert scope.ontology_ids == ["model-a", "model-b", "created-this-run"]
    assert scope.ontology_plan_ids == ["model-b", "created-this-run"]


def test_a6_unknown_create_is_not_blindly_replayed():
    api = CurrentModelAPI()
    scope = bound_scope(api, allow_new_ontologies=True)
    api.unknown_create = True
    plan = [{"ontology_id": "model-a", "slice_ids": ["current"]},
            {"name": "Shared name", "slice_ids": ["new"]}]
    with pytest.raises((TimeoutError, PlatformScopeError)):
        scope.apply_ontology_plan(plan)
    with pytest.raises(PlatformScopeError, match="unknown|reconcil"):
        scope.apply_ontology_plan(plan)
    assert len(api.creates) == 1


def test_a6_definite_prewrite_rejection_allows_corrected_same_request_retry():
    class PrewriteRejection(CurrentModelAPI):
        def __call__(self, method, path, body, key):
            if method == "POST" and path.endswith("/ontologies") and not self.creates:
                self.calls.append((method, path, copy.deepcopy(body)))
                return 422, {"detail": "repairable rejected input; no resources created"}
            return super().__call__(method, path, body, key)
    api = PrewriteRejection()
    scope = bound_scope(api, allow_new_ontologies=True)
    plan = [{"ontology_id": "model-a", "slice_ids": ["current"]},
            {"name": "approved-new", "slice_ids": ["new"]}]
    with pytest.raises(PlatformScopeError):
        scope.apply_ontology_plan(plan)
    assert len(api.creates) == 1
    assert len(api.ontologies) == 2
    assert next(iter(scope.ontology_plan_receipts.values()))["status"] == "rejected"
    assert scope.apply_ontology_plan(plan) == ["model-a", "created-this-run"]
    assert len(api.creates) == 2
    assert len(api.ontologies) == 3


def test_a8_active_writer_prevents_new_scope_credentials():
    api = CurrentModelAPI()
    api.active = [{"id": "old-active-writer"}]
    with pytest.raises(PlatformScopeError, match="active|in.flight"):
        bound_scope(api)
    assert not any(method == "POST" and path == "/api/api-keys"
                   for method, path, _ in api.calls)
    assert not api.creates


def test_a8_cleanup_preserves_existing_and_newly_created_models():
    api = CurrentModelAPI()
    scope = bound_scope(api, allow_new_ontologies=True)
    scope.apply_ontology_plan([{"ontology_id": "model-a", "slice_ids": ["current"]},
                               {"name": "Shared name", "slice_ids": ["new"]}])
    scope.cleanup()
    assert not any(method == "DELETE" for method, _, _ in api.calls)
    assert {item["id"] for item in api.ontologies} == {"model-a", "model-b", "created-this-run"}


def test_a8_failed_run_cancels_only_its_own_sessions():
    class Sessions(CurrentModelAPI):
        def __init__(self):
            super().__init__()
            self.states = {"own-session": "active", "other-run-session": "active"}
        def __call__(self, method, path, body, key):
            if path.startswith("/api/build-sessions/"):
                self.calls.append((method, path, copy.deepcopy(body)))
                identity = path.rsplit("/", 1)[1].removesuffix(":cancel")
                if method == "POST":
                    self.states[identity] = "cancelled"
                return 200, {"session": {"id": identity, "project_id": "project-p",
                                       "status": self.states[identity], "revision": 1},
                             "involved_ontology_ids": ["model-a"], "modeling_batches": [], "leases": []}
            return super().__call__(method, path, body, key)
    api = Sessions()
    scope = bound_scope(api)
    api.active = [{"id": identity} for identity in api.states]
    scope.owned_session_ids.add("own-session")
    scope.cleanup()
    assert api.states == {"own-session": "cancelled", "other-run-session": "active"}
    assert not any(method == "DELETE" for method, _, _ in api.calls)


@pytest.fixture
def incremental_request(tmp_path):
    origin = Path(__file__).resolve().parents[2]
    for folder in ("tasks", "profiles", "agent-packages", "skills", "references", "model-profiles"):
        shutil.copytree(origin / "modeling_team" / folder, tmp_path / "modeling_team" / folder)
    source = tmp_path / "approved/business.md"
    source.parent.mkdir()
    source.write_text("Public confirmed source; limited scope and unresolved business meaning remain explicit.")
    request = {"request_id": str(uuid4()), "project_id": "project-p",
               "ontology_ids": ["model-a", "model-b"], "objective": "Add the approved bounded business scope",
               "approved_sources": [{"path": "approved/business.md", "source_reference": "business-owner-confirmed",
                                     "valid_at": "2026-10-12"}],
               "profile": "modeling_team/profiles/r3-0-011-competency-question.yaml",
               "model_profile": "openai-sol-medium", "authorization_reference": "explicit-test-host-authority",
               "valid_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
               "production_start_limit": 1, "acceptance_scope": "new, related and affected old questions"}
    return tmp_path, request


def write_request(root, request):
    path = root / "request.yaml"
    path.write_text(yaml.safe_dump(request))
    return path


def test_a1_a9_prepare_normal_new_task_with_exact_current_scope(incremental_request):
    root, request = incremental_request
    scopes = []
    result = prepare_incremental(request, repository_root=root,
                                 scope_probe=lambda scope: scopes.append(scope) or {"revision": 7, "partial": True})
    config = yaml.safe_load((root / result["config"]).read_text())
    task = yaml.safe_load((root / config["task"]).read_text())
    assert result["semantic_start"] == "not_observed"
    assert result["run_id"] != result["session_id"]
    assert scopes == [config["readback_scope"]]
    assert scopes[0]["ontology_ids"] == ["model-a", "model-b"]
    assert scopes[0]["mode"] == "existing"
    assert result["current_scope"] == {"revision": 7, "partial": True}
    assert task["schema_version"] == 2
    assert task["parameters"]["competency_question_acceptance"] is True
    assert request["acceptance_scope"] in task["objective"]
    assert "checkpoint" not in config and "task_overlay" not in config
    approved = [item for item in task["role_sources"] if item["classification"] == "business-source"]
    assert len(approved) == 1
    assert "business-owner-confirmed" in (root / approved[0]["path"]).read_text()


def test_a10_stable_request_id_never_launches_delivery_twice(incremental_request):
    root, request = incremental_request
    launches = []
    def launcher(*args, **kwargs):
        launches.append((args, kwargs))
        return SimpleNamespace(pid=23456)
    path = write_request(root, request)
    first = start_incremental(path, repository_root=root, launcher=launcher, scope_probe=lambda _: {})
    second = start_incremental(path, repository_root=root, launcher=launcher, scope_probe=lambda _: {})
    assert len(launches) == 1
    assert first["run_id"] == second["run_id"]
    assert first["status"] == "delivery_launch_accepted"
    assert second["status"] == "delivery_launch_recorded"
    assert "semantic start" in first["note"]


def test_a10_unknown_delivery_launch_keeps_identity_without_replay(incremental_request):
    root, request = incremental_request
    launches = []
    def uncertain_launch(*args, **kwargs):
        launches.append(1)
        raise OSError("unknown process launch")
    path = write_request(root, request)
    with pytest.raises(OSError):
        start_incremental(path, repository_root=root, launcher=uncertain_launch, scope_probe=lambda _: {})
    result = start_incremental(path, repository_root=root, launcher=uncertain_launch, scope_probe=lambda _: {})
    assert launches == [1]
    assert result["delivery_launch"]["status"] == "unknown"


@pytest.mark.parametrize("started", [True, False])
def test_a10_expired_authority_allows_only_observing_prior_launch(incremental_request, monkeypatch, started):
    import modeling_team.incremental as module
    root, request = incremental_request
    launches = []
    def launcher(*a, **kw):
        launches.append(1)
        return SimpleNamespace(pid=1234)
    path = write_request(root, request)
    if started:
        start_incremental(path, repository_root=root, launcher=launcher, scope_probe=lambda _: {})
    else:
        prepare_incremental(request, repository_root=root, scope_probe=lambda _: {})
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=2)
    monkeypatch.setattr(module, "datetime", Later)
    if started:
        result = start_incremental(path, repository_root=root, launcher=launcher, scope_probe=lambda _: {})
        assert result["status"] == "delivery_launch_recorded" and launches == [1]
    else:
        with pytest.raises(IncrementalError) as rejection:
            start_incremental(path, repository_root=root, launcher=launcher, scope_probe=lambda _: {})
        assert rejection.value.code == "incremental_authorization_expired"
        assert not launches


@pytest.mark.parametrize("change", [{"production_start_limit": 0}, {"valid_until": "2020-01-01T00:00:00Z"},
                                  {"authorization_reference": ""}, {"allowed_operations": ["code-fix", "deploy"]}])
def test_a10_invalid_authority_never_reaches_launch(incremental_request, change):
    root, request = incremental_request
    request.update(change)
    launches = []
    with pytest.raises(IncrementalError):
        start_incremental(write_request(root, request), repository_root=root,
                          launcher=lambda *a, **kw: launches.append(1), scope_probe=lambda _: {})
    assert not launches


def test_a7_feedback_whitelists_public_projection_and_preserves_unknown(incremental_request):
    root, request = incremental_request
    request["feedback_ids"] = ["feedback-public"]
    result = prepare_incremental(request, repository_root=root, scope_probe=lambda _: {},
                                 feedback_reader=lambda p, f: {"project_id": p, "feedback_id": f,
                                     "observation": "Possible issue, unconfirmed", "status": "open",
                                     "hidden_answer": "PRIVATE-MARKER", "judge_reason": "PRIVATE-REASON"})
    config = yaml.safe_load((root / result["config"]).read_text())
    assert "PRIVATE-MARKER" not in "".join((root / p).read_text() for p in config["allowed_sources"])
    feedback = (root / result["config"]).parent / "public-feedback.json"
    assert "Possible issue, unconfirmed" in feedback.read_text()
    assert "PRIVATE-REASON" not in feedback.read_text()


def test_a7_old_run_material_cannot_be_approved_source(incremental_request):
    root, request = incremental_request
    private = root / "workspaces/modeling-runs/old/answer.md"
    private.parent.mkdir(parents=True)
    private.write_text("old hidden answer")
    request["approved_sources"][0]["path"] = str(private.relative_to(root))
    with pytest.raises(IncrementalError, match="old runs|private"):
        prepare_incremental(request, repository_root=root, scope_probe=lambda _: {})


@pytest.mark.parametrize("tool,args", [
    ("start_run", {"run_id": "different-run", "request_id": "same-request"}),
    ("start_run", {"run_id": "same-run", "request_id": "different-request"}),
    ("start_repair", {}), ("deploy_code", {}),
])
def test_a10_delivery_cannot_change_bound_launch_or_escalate_operations(tmp_path, tool, args):
    host = DeliverySession(repository_root=Path(__file__).resolve().parents[2],
                           session_root=tmp_path / "delivery", config={
        "session_id": "independent-029", "model_profile": "openai-sol-medium",
        "authorization_reference": "bounded-user-authorization", "allowed_sources": [],
        "task": "modeling_team/tasks/r4-0-029-existing-model-incremental.yaml",
        "profile": "modeling_team/profiles/r3-0-011-competency-question.yaml", "scope": "controlled-existing.yaml",
        "allowed_operations": ["read", "supervise", "production", "evaluation"],
        "production_start_limit": 1, "incremental_run_id": "same-run",
        "incremental_request_id": "same-request", "run_ids": []})
    result = host.call_tool(tool, args)
    assert result["ok"] is False
    assert not host.run_ids


@pytest.mark.parametrize("field,value", [("production_start_limit", 10),
                                         ("incremental_request_id", "replacement-request"),
                                         ("incremental_run_id", "replacement-run")])
def test_a10_delivery_resume_preserves_original_authorized_launch(tmp_path, field, value):
    config = {"session_id": "resume-029", "model_profile": "openai-sol-medium",
              "authorization_reference": "original-user-reference", "allowed_sources": [],
              "allowed_operations": ["read"], "production_start_limit": 1,
              "incremental_request_id": "original-request", "incremental_run_id": "original-run"}
    args = {"repository_root": Path(__file__).resolve().parents[2], "session_root": tmp_path / "delivery"}
    DeliverySession(**args, config=config)
    with pytest.raises(ValueError, match=field):
        DeliverySession(**args, config={**config, field: value}, resume=True)


def observed_reuse(production, *, native_content=False):
    plan_path = production.run_root / PLAN1
    plan = json.loads(plan_path.read_text())
    ontology = plan["projection"]["ontology_id"]
    envelope = {"ok": True, "data": {"model_revision": 1,
               "items": [{"entity_iri": "urn:independent:stable-definition"}],
               "has_more": True, "restricted": True}}
    wire = {"content": [{"type": "text", "text": json.dumps(envelope)}]} if native_content else {"structuredContent": envelope}
    result = production.runner.acceptance.register_platform_tool_result(
        tool="get_ontology_read_model", arguments={"ontology_id": ontology, "model_name": "entity-list"},
        result=wire)
    plan["projection"]["items"] = []
    plan["projection"]["decision_bindings"] = []
    plan["projection"]["identity_bindings"] = [build_identity_binding(
        candidate_item_id="item-entity", resource_iri="urn:independent:stable-definition",
        evidence_ref=result["artifact_path"])]
    plan["projection_digest"] = projection_digest(plan["projection"])
    plan_path.write_text(json.dumps(plan))
    return plan


def test_a4_native_content_read_uses_same_governed_reuse_contract(production):
    observed_reuse(production, native_content=True)
    result = production.runner._handle_check_plan_coverage({
        "candidate_ref": CANDIDATE, "plan_refs": [PLAN1], "dispositions": []})
    assert result["items"][0]["reuse_binding"]["resource_iri"] == "urn:independent:stable-definition"
    assert (production.run_root / "evidence/plan-coverage.jsonl").is_file()


def test_a8_no_change_plan_cannot_hide_pending_unknown_write(production):
    original = production.runner.staged_batch_forwarder
    def lose_reply(batch):
        if batch["mode"] == "apply_atomic":
            raise StagedBatchForwardUnknown("unknown actual write result")
        return original(batch)
    production.runner.staged_batch_forwarder = lose_reply
    first = production.runner._handle_execute_approved_plans({"protocol_id": "protocol", "plan_refs": [PLAN1],
        "lease_tokens": {identity: "owned-lease" for identity in production.versions}})
    assert first["ok"] is False
    assert first["error"]["reason_code"] == "staged_batch_forward_unknown", first
    observed_reuse(production)
    second = production.runner._handle_execute_approved_plans({"protocol_id": "protocol", "plan_refs": [PLAN1]})
    assert second["ok"] is False
    assert second["error"]["reason_code"] == "staged_unreconciled_batch"
    assert len(production.calls) == 1  # Only original dry-run; apply reply is unknown.


def test_a3_batch_cannot_write_outside_round_bound_ontology_ids(production):
    scope = PlatformScope("http://unused", "existing-run", lambda: ("admin", "id"), lambda _: True)
    scope.mode = "existing"
    scope.project_id = "same-project"
    scope.ontology_ids = ["urn:only:authorized-model"]
    production.runner.scope = scope
    result = production.runner._handle_execute_approved_plans({"protocol_id": "protocol", "plan_refs": [PLAN1],
        "lease_tokens": {identity: "owned-lease" for identity in production.versions}})
    assert result["ok"] is False
    assert result["error"]["reason_code"] == "forbidden_scope"
    assert not production.calls


@pytest.mark.parametrize("unknown", [False, True])
def test_a8_actual_topology_gate_retries_same_run_without_unknown_create_replay(production, unknown):
    runner = production.runner
    api = CurrentModelAPI()
    runner.scope = bound_scope(api, allow_new_ontologies=unknown)
    decision_path = runner._multi_slice_artifact_paths["topology_decision"]
    decision = json.loads(decision_path.read_text())
    original = copy.deepcopy(decision["ontology_plan"])
    decision["ontology_plan"] = [
        {"ontology_id": "model-a", "slice_ids": original[0]["slice_ids"]},
        {"name": "Shared name", "slice_ids": original[1]["slice_ids"]}]
    decision_path.write_text(json.dumps(decision))
    api.unknown_create = unknown
    run_identity = runner.run.run_id
    runner._multi_slice_gate_opened = False
    runner._check_multi_slice_topology_gate()
    assert runner._multi_slice_gate_opened is False
    gate = json.loads((production.run_root / "candidate-gate/state.json").read_text())
    assert gate["reason_code"] == "topology_apply_incomplete"
    if unknown:
        assert len(api.creates) == 1
        runner._check_multi_slice_topology_gate()
        assert len(api.creates) == 1
        assert runner._multi_slice_gate_opened is False
    else:
        assert not api.creates
        decision["ontology_plan"][1] = {"ontology_id": "model-b", "slice_ids": original[1]["slice_ids"]}
        decision_path.write_text(json.dumps(decision))
        runner._check_multi_slice_topology_gate()
        assert runner._multi_slice_gate_opened is True
        assert json.loads((production.run_root / "candidate-gate/state.json").read_text())["state"] == "open"
        assert runner.run.protocol_context["ontology_ids"] == "model-a,model-b"
    assert runner.run.run_id == run_identity
    assert not production.calls


def test_a4_observed_reuse_covers_only_that_item_and_executes_no_write(production):
    observed_reuse(production)
    args = {"candidate_ref": CANDIDATE, "plan_refs": [PLAN1], "dispositions": []}
    coverage = production.runner._handle_check_plan_coverage(args)
    assert coverage["unaccounted_item_ids"] == ["relation-1"]
    reused = next(row for row in coverage["items"] if row["candidate_item_id"] == "item-entity")
    assert reused["reuse_binding"]["resource_iri"] == "urn:independent:stable-definition"
    assert not reused["applied_plan_refs"]
    args["dispositions"] = [{"candidate_item_id": "relation-1", "disposition": "deferred",
                            "reason": "explicit unresolved business scope"}]
    assert production.runner._handle_check_plan_coverage(args)["status"] == "COMPLETE"
    executed = production.runner._handle_execute_approved_plans({"protocol_id": "protocol", "plan_refs": [PLAN1]})
    assert executed["ok"] and executed["completed"][0]["status"] == "reused"
    assert not production.calls


def test_a8_reuse_current_revision_drift_rejects_then_same_run_can_continue(production):
    observed_reuse(production)
    forward = production.runner.staged_plan_read_forwarder
    def changed(tool, args):
        result = copy.deepcopy(forward(tool, args))
        result["data"]["workspace"]["model_revision"] = 5
        return result
    production.runner.staged_plan_read_forwarder = changed
    args = {"candidate_ref": CANDIDATE, "plan_refs": [PLAN1], "dispositions": []}
    with pytest.raises(StagedSubmissionRejection) as rejection:
        production.runner._handle_check_plan_coverage(args)
    assert rejection.value.data["reason_code"] == "approval_stale"
    assert not production.calls
    production.runner.staged_plan_read_forwarder = forward
    assert production.runner._handle_check_plan_coverage(args)["items"][0]["reuse_binding"]


@pytest.mark.parametrize("command,target,expected", [
    ("create_entity", None, False), ("update_entity", "urn:independent:stable-definition", True),
    ("delete_entity", "urn:independent:stable-definition", True),
    ("update_entity", "urn:another:unrelated-definition", False),
])
def test_a5_existing_identity_commands_preserve_exact_target(production, command, target, expected):
    plan = json.loads((production.run_root / PLAN1).read_text())
    projection = plan["projection"]
    projection["identity_bindings"] = [build_identity_binding(
        candidate_item_id="item-entity", resource_iri="urn:independent:stable-definition", evidence_ref="read.json")]
    item = projection["items"][0]
    item["command_kind"] = command
    if target is not None:
        item["payload"] = {"entity_iri": target, "label": "approved change"}
    candidate = json.loads((production.run_root / CANDIDATE).read_text())
    issue = unified_identity_issue(projection, {row["item_id"]: row for row in candidate["items"]})
    assert (issue is None) is expected
