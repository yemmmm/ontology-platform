"""Independent R5.0-012 engineering checks; never a real modeling/L1 verdict."""

import hashlib
import json
import subprocess
import threading
from contextlib import contextmanager
from copy import deepcopy

import pytest
import yaml

from ontoweave_modeling.contracts import FrameworkError, TaskBinding, digest


@pytest.fixture
def role_task_file(task_file):
    """Use the normal entry point with no explicit team selection or delegation."""
    task = json.loads(task_file.read_text())
    task.pop("team_contract", None)
    task_file.write_text(json.dumps(task))
    profile_path = task_file.parent / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text())
    for role, effort in (("coordinator", "high"), ("competency-question", "medium")):
        profile["roles"][role] = {
            **profile["roles"]["modeling"],
            "model_reasoning_effort": effort,
        }
    profile_path.write_text(yaml.safe_dump(profile))
    return task_file


def test_default_preparation_activates_specialist_contract_without_agent_delegation(
    role_task_file, tmp_path
):
    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    assert binding.role_team and binding.root_actor == "coordinator"
    assert binding.actor == "coordinator" and binding.role == "coordinator"
    assert binding.data["team_contract"] == "role-team/v1"
    assert set(binding.data["models"]) == {
        "coordinator",
        "competency-question",
        "modeling",
        "acceptance",
    }
    assert binding.model("coordinator").effort == "high"
    assert binding.model("competency-question").effort == "medium"
    assert binding.model("modeling").effort == "low"
    units = {unit["unit_id"]: unit for unit in binding.data["work_units"]}
    assert {"modeler", "cq-public"} <= units.keys()
    assert units["modeler"]["role_id"] == "modeling"
    assert units["modeler"]["work_phase"] == "source_intake"
    assert units["cq-public"]["role_id"] == "competency-question"
    assert units["cq-public"]["work_kind"] == "cq_public"
    assert units["modeler"].get("dependencies", []) == []
    assert units["cq-public"].get("dependencies", []) == []
    assert {unit["parent_id"] for unit in units.values()} == {"coordinator"}


def test_specialists_have_separate_binding_contexts_and_frozen_instructions(
    role_task_file, tmp_path
):
    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    original = deepcopy(binding.data)
    cq = binding.for_unit("cq-public")
    modeler = binding.for_unit("modeler")
    assert len({binding.actor, cq.actor, modeler.actor}) == 3
    assert len({binding.thread_id, cq.thread_id, modeler.thread_id}) == 3
    assert cq.role == "competency-question" and modeler.role == "modeling"
    assert cq.data["instructions"] != modeler.data["instructions"]
    assert cq.data["_parent_actor"] == modeler.data["_parent_actor"] == "coordinator"
    assert binding.data == original
    profile = role_task_file.parent / "profile.yaml"
    profile.write_text("Original input was modified after freezing.\n")
    assert TaskBinding.load(binding.root).data == original
    packages = binding.data["role_packages"]
    assert set(packages) == {"coordinator", "competency-question", "modeling"}
    assert len({package["instructions"] for package in packages.values()}) == 3
    for package in packages.values():
        assert package["instructions"].strip()
    assert (
        binding.data["profile_sha256"]
        == hashlib.sha256((binding.root / "model-profile.yaml").read_bytes()).hexdigest()
    )


def test_custom_cq_prepared_role_instructions_match_frozen_packages_and_goal_boundary(
    role_task_file, tmp_path
):
    task = json.loads(role_task_file.read_text())
    task["custom_cq"] = True
    role_task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(role_task_file, tmp_path / "custom-cq-role-run")
    packages = binding.data["role_packages"]
    assert binding.data["custom_cq"] is True
    assert binding.data["instructions"] == packages["coordinator"]["instructions"]
    assert (
        "Technical representation contracts (not business sources):"
        not in binding.data["instructions"]
    )
    for package in packages.values():
        assert package["sha256"] == digest(
            {key: value for key, value in package.items() if key != "sha256"}
        )
    modeler = binding.for_unit("modeler")
    guidance = modeler.data["instructions"].lower()
    assert "cq" in guidance and "goals" in guidance
    assert "draft" in guidance and "business facts" in guidance
    frozen = deepcopy(binding.data)
    task["custom_cq"] = False
    task["instructions"] = "Changed external Task after preparation"
    role_task_file.write_text(json.dumps(task))
    assert TaskBinding.load(binding.root).data == frozen


@pytest.mark.parametrize("missing_role", ["coordinator", "competency-question"])
def test_missing_specialist_model_is_recoverable_without_modeling_fallback(
    role_task_file, tmp_path, missing_role
):
    profile_path = role_task_file.parent / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text())
    saved = profile["roles"].pop(missing_role)
    profile_path.write_text(yaml.safe_dump(profile))
    run = tmp_path / "role-run"
    with pytest.raises(FrameworkError) as caught:
        TaskBinding.prepare(role_task_file, run)
    assert caught.value.code == "role_model_binding_invalid"
    assert caught.value.recoverable and caught.value.detail["role_id"] == missing_role
    assert not run.exists()
    profile["roles"][missing_role] = saved
    profile_path.write_text(yaml.safe_dump(profile))
    assert TaskBinding.prepare(role_task_file, run).role_team


def test_explicit_other_mode_and_preexisting_binding_keep_original_root(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["team_contract"] = "single-modeler/v1"
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "legacy-run")
    assert not binding.role_team and binding.actor == "modeling"
    assert binding.data["team_contract"] == "single-modeler/v1"
    assert set(binding.data["models"]) == {"modeling", "acceptance"}
    original_thread = binding.thread_id
    # Reproduce a genuine pre-contract binding, without manufacturing new roles/contexts.
    envelope = json.loads((binding.root / "binding.json").read_text())
    envelope["binding"].pop("team_contract")
    envelope["digest"] = digest(envelope["binding"])
    (binding.root / "binding.json").write_text(json.dumps(envelope))
    legacy = TaskBinding.load(binding.root)
    assert not legacy.role_team and legacy.actor == "modeling"
    assert legacy.thread_id == original_thread
    assert "role_packages" not in legacy.data
    assert "team_contract" not in json.loads((legacy.root / "binding.json").read_text())["binding"]


def test_unknown_team_contract_does_not_prepare_resources_or_silently_fallback(
    role_task_file, tmp_path
):
    task = json.loads(role_task_file.read_text())
    task["team_contract"] = "role-team/misspelled"
    role_task_file.write_text(json.dumps(task))
    with pytest.raises(FrameworkError, match="team_contract_unknown"):
        TaskBinding.prepare(role_task_file, tmp_path / "invalid-run")
    assert not (tmp_path / "invalid-run").exists()


def role_result(binding, artifact):
    return {
        "schema_version": "role-work-result/v1",
        "status": "proposed",
        "basis": {
            "source_manifest_digest": binding.data["source_manifest_digest"],
            "scope_ref": None,
            "cq_ref": None,
            "shared_refs": [],
            "model_revisions": {},
            "consumed_refs": [],
        },
        "artifact": artifact,
        "source_refs": [],
        "issues": [],
        "consumed_ids": [],
    }


def test_intake_cannot_smuggle_apply_request_or_pass_with_empty_analysis(role_task_file, tmp_path):
    from ontoweave_modeling.results import ResultContractError, decode_json_result
    from ontoweave_modeling.role_team import result_schema

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run").for_unit("modeler")
    artifact = {
        "schema_version": "source-intake/v1",
        "propositions": ["The source retains an explicit condition."],
        "unknowns": ["An unresolved source detail remains unknown."],
    }
    result = role_result(binding, artifact)
    schema = result_schema(binding, "source_intake")
    assert decode_json_result(json.dumps(result), schema) == result
    artifact["candidate"] = {"items": [{"item_id": "unauthorized-intake-write"}]}
    with pytest.raises(ResultContractError):
        decode_json_result(json.dumps(result), schema)
    artifact.pop("candidate")
    artifact["propositions"] = []
    with pytest.raises(ResultContractError):
        decode_json_result(json.dumps(result), schema)


@pytest.mark.parametrize("forbidden_field", ["candidate", "changes", "actor_id", "role_id"])
def test_coordinator_plan_has_no_unsigned_modeler_body_or_self_selected_author(
    role_task_file, tmp_path, forbidden_field
):
    from ontoweave_modeling.results import ResultContractError, decode_json_result
    from ontoweave_modeling.role_team import result_schema

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    artifact = {
        "schema_version": "integration-plan/v1",
        "plan_id": "bounded-safe-plan",
        "contributions": [],
        "shared_decision_refs": [],
        "deferred": [],
        "ontology_targets": {},
        "check_units": [],
    }
    result = role_result(binding, artifact)
    schema = result_schema(binding, "integrate")
    assert decode_json_result(json.dumps(result), schema) == result
    artifact[forbidden_field] = "modeling" if forbidden_field.endswith("id") else {}
    with pytest.raises(ResultContractError):
        decode_json_result(json.dumps(result), schema)


def test_public_cq_cannot_overwrite_modeler_semantic_authorship(
    role_task_file, tmp_path, workspace
):
    from ontoweave_modeling.semantic_workspace import SemanticWorkspace
    from ontoweave_modeling.work_plan import WorkPlan

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    WorkPlan(binding.data, workspace).row()
    modeler = SemanticWorkspace(workspace, binding.for_unit("modeler").data, "modeler")
    cq = SemanticWorkspace(workspace, binding.for_unit("cq-public").data, "cq-public")
    modeler.write("owned-condition", "definition", "Original condition", {"condition": "A AND B"})
    original = workspace.get("semantic:owned-condition")
    with pytest.raises(FrameworkError) as caught:
        cq.write(
            "owned-condition",
            "definition",
            "Silent rewrite",
            {"condition": "A OR B"},
            expected_revision=original["revision"],
        )
    assert caught.value.recoverable
    assert workspace.get("semantic:owned-condition") == original


def test_specialist_cannot_create_notes_with_another_responsible_unit(
    role_task_file, tmp_path, workspace
):
    from ontoweave_modeling.semantic_workspace import SemanticWorkspace
    from ontoweave_modeling.work_plan import WorkPlan

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    WorkPlan(binding.data, workspace).row()
    cq = SemanticWorkspace(workspace, binding.for_unit("cq-public").data, "cq-public")
    with pytest.raises(FrameworkError) as caught:
        cq.write(
            "forged-owned-condition",
            "definition",
            "Forged Modeler result",
            {"condition": "A OR B"},
            unit_id="modeler",
        )
    assert caught.value.recoverable
    assert workspace.get("semantic:forged-owned-condition") is None


@pytest.fixture
def contribution_case(role_task_file, tmp_path, workspace):
    """Two authored native-compatible candidates, with deliberately identical local IDs."""
    from ontoweave_modeling.work_plan import WorkPlan

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    work_plan = WorkPlan(binding.data, workspace)

    def add_second(plan):
        plan["units"]["modeler"]["work_phase"] = "propose"
        plan["units"]["modeler-b"] = {
            **plan["units"]["modeler"],
            "unit_id": "modeler-b",
            "actor_id": "modeler-b",
            "objective": "Second source-grounded contribution",
        }

    work_plan.change(add_second)
    binding = work_plan.binding(binding)
    scope_ref = workspace.put_reference(
        "integration-scope-v1", "role_artifact", {"scope": "A+B"}, 0
    )
    basis = {
        "source_manifest_digest": binding.data["source_manifest_digest"],
        "scope_ref": scope_ref,
        "cq_ref": None,
        "shared_refs": [],
        "model_revisions": {"ontology": 0},
        "consumed_refs": [],
    }
    selected = []
    for owner in ("modeler", "modeler-b"):

        def item(identity, kind, value, endpoints=None, *, owner=owner):
            return {
                "item_id": identity,
                "item_kind": kind,
                "business_meaning": owner + " requires acceptance AND signature",
                "value": value,
                "relation_endpoints": endpoints,
                "slice_ids": [owner],
                "shared_scope": None,
                "unknowns": [],
            }

        candidate = {
            "schema_version": "r3-0-009-unified-graph/v2",
            "scenario_id": "integration",
            "candidate_id": "local-candidate",
            "revision": 1,
            "items": [
                item("same", "entity", {"label": "same", "description": "same"}),
                item("pred", "property", {"name": "pred", "predicate_kind": "relation"}),
                item(
                    "edge",
                    "relation",
                    {"predicate": {"definition_ref": "pred"}},
                    {"from_item_id": "same", "to_item_id": "same"},
                ),
            ],
            "explicit_unknowns": [owner + " unresolved source detail"],
        }
        changes = {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                {
                    "change_id": "create-" + entry["item_id"],
                    "action": "create",
                    "resource_kind": entry["item_kind"],
                    "item_id": entry["item_id"],
                    "target_ref": None,
                    "fields": None,
                }
                for entry in candidate["items"]
            ],
        }
        prefix = binding.for_unit(owner).identity
        candidate_ref = workspace.put_reference(
            prefix + ":owned-candidate", "candidate", candidate, 0
        )
        changes_ref = workspace.put_reference(prefix + ":owned-changes", "changes", changes, 0)
        artifact_ref = workspace.put_reference(
            prefix + ":owned-artifact",
            "role_artifact",
            {
                "candidate": candidate,
                "changes": changes,
                "ontology_targets": None,
                "review_units": [],
                "shared_conflicts": [],
                "public_cq_disposition": "Bounded proposal retains public CQ pending status",
            },
            0,
        )
        result_ref = workspace.put_reference(
            prefix + ":role-result:0",
            "role_result",
            {
                "schema_version": "role-work-result/v1",
                "status": "proposed",
                "role_id": "modeling",
                "actor_id": owner,
                "generation": 0,
                "unit_id": owner,
                "work_kind": "slice_modeling",
                "basis": deepcopy(basis),
                "candidate_ref": candidate_ref,
                "changes_ref": changes_ref,
                "artifact_ref": artifact_ref,
                "source_refs": [
                    {
                        "material_id": "source",
                        "sha256": binding.data["source_manifest"]["source"]["sha256"],
                    }
                ],
            },
            0,
        )
        workspace.put_reference(
            prefix + ":work",
            "work_unit",
            {
                "role_result_ref": result_ref,
                "status": "proposal_ready",
                "work_generation": 0,
            },
            0,
        )
        selected.append(
            {
                "owner_work_id": owner,
                "generation": 0,
                "result_ref": result_ref,
                "candidate_ref": candidate_ref,
                "changes_ref": changes_ref,
                "selected_change_ids": [change["change_id"] for change in changes["changes"]],
            }
        )
    plan = {
        "schema_version": "integration-plan/v1",
        "plan_id": "two-authored-slices",
        "contributions": selected,
        "shared_decision_refs": [],
        "deferred": [],
        "ontology_targets": {},
        "check_units": ["modeler", "modeler-b"],
    }
    return binding, workspace, plan, basis


def test_combination_preserves_authored_meaning_and_all_local_relation_references(
    contribution_case,
):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    output = compose_integration(binding, repository, plan, basis)
    items = output["candidate"]["items"]
    assert len(items) == 6 and len({item["item_id"] for item in items}) == 6
    ids = {item["item_id"] for item in items}
    for entry in items:
        assert entry["business_meaning"].endswith("requires acceptance AND signature")
        if entry["item_kind"] == "entity":
            assert entry["value"] == {"label": "same", "description": "same"}
        elif entry["item_kind"] == "relation":
            assert entry["value"]["predicate"]["definition_ref"] in ids
            assert entry["relation_endpoints"]["from_item_id"] in ids
            assert entry["relation_endpoints"]["to_item_id"] in ids
    assert len({change["change_id"] for change in output["changes"]["changes"]}) == 6
    assert {origin["owner_work_id"] for origin in output["origins"].values()} == {
        "modeler",
        "modeler-b",
    }
    assert set(output["candidate"]["explicit_unknowns"]) == {
        "modeler unresolved source detail",
        "modeler-b unresolved source detail",
    }


def test_selecting_relation_without_its_local_definition_is_recoverable(contribution_case):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    plan["contributions"][0]["selected_change_ids"] = ["create-edge"]
    with pytest.raises(FrameworkError, match="integration_reference_not_closed") as caught:
        compose_integration(binding, repository, plan, basis)
    assert caught.value.recoverable


def test_old_generation_is_rejected_but_unrelated_current_sibling_is_reusable(contribution_case):
    from ontoweave_modeling.role_team import compose_integration
    from ontoweave_modeling.work_plan import WorkPlan

    binding, repository, plan, basis = contribution_case
    current = WorkPlan(binding.data, repository)
    current.reopen("modeler-b", "Local source question changed")
    binding = current.binding(binding)
    with pytest.raises(FrameworkError, match="contribution_stale_or_wrong_owner"):
        compose_integration(binding, repository, plan, basis)
    plan["contributions"] = plan["contributions"][:1]
    plan["check_units"] = ["modeler"]
    plan["deferred"] = [
        {
            "owner_work_id": "modeler-b",
            "reason": "Original owner is revising",
            "depends_on": ["modeler-b"],
        }
    ]
    safe = compose_integration(binding, repository, plan, basis)
    assert len(safe["candidate"]["items"]) == 3
    assert safe["issues"] == ["Original owner is revising"]


def test_current_source_revision_cannot_use_a_contribution_from_withdrawn_source(contribution_case):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    binding.data["source_manifest"]["source"]["sha256"] = "f" * 64
    binding.data["source_manifest_digest"] = digest(binding.data["source_manifest"])
    basis["source_manifest_digest"] = binding.data["source_manifest_digest"]
    with pytest.raises(FrameworkError) as caught:
        compose_integration(binding, repository, plan, basis)
    assert caught.value.recoverable


def test_shared_native_target_conflict_is_not_last_write_wins(contribution_case):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    retained = []
    for contribution in plan["contributions"]:
        owner = contribution["owner_work_id"]
        prefix = binding.for_unit(owner).identity
        retained.append(repository.read_reference(contribution["result_ref"]))
        request = {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                {
                    "change_id": "update-shared",
                    "action": "update",
                    "resource_kind": "class",
                    "item_id": None,
                    "target_ref": {
                        "artifact_ref": "actual-applied-bindings.json",
                        "path": "/shared-definition",
                    },
                    "fields": {"name": owner + " conflicting name"},
                }
            ],
        }
        changes_ref = repository.put_reference(prefix + ":shared-change", "changes", request, 0)
        artifact_ref = repository.put_reference(
            prefix + ":shared-artifact",
            "role_artifact",
            {
                "candidate": None,
                "changes": request,
                "ontology_targets": None,
                "review_units": [],
                "shared_conflicts": [],
                "public_cq_disposition": "Retain unknowns",
            },
            0,
        )
        result_ref = repository.put_reference(
            prefix + ":role-result:1",
            "role_result",
            {
                **retained[-1],
                "candidate_ref": None,
                "changes_ref": changes_ref,
                "artifact_ref": artifact_ref,
            },
            0,
        )
        work = repository.get(prefix + ":work")
        repository.put_reference(
            prefix + ":work",
            "work_unit",
            {
                **work["content"],
                "role_result_ref": result_ref,
            },
            work["revision"],
        )
        contribution.update(
            candidate_ref=None,
            changes_ref=changes_ref,
            result_ref=result_ref,
            selected_change_ids=["update-shared"],
        )
    with pytest.raises(FrameworkError, match="shared_target_conflict") as caught:
        compose_integration(binding, repository, plan, basis)
    assert caught.value.recoverable
    for index, owner in enumerate(("modeler", "modeler-b")):
        assert (
            repository.get(binding.for_unit(owner).identity + ":role-result:0")["content"]
            == retained[index]
        )


@pytest.mark.parametrize("new_envelope", [False, True])
def test_applied_fixed_contribution_cannot_be_reselected_under_a_new_plan_or_round(
    contribution_case, new_envelope
):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    original = compose_integration(binding, repository, plan, basis)
    operation_ref = repository.put_reference(
        "actual-operation-one",
        "application_reference",
        {
            "status": "completed",
            "model_revisions": {"ontology": 1},
        },
        0,
    )
    repository.put_reference(
        "retained-role-application",
        "role_application",
        {
            "operation_ref": operation_ref,
            "origins": original["origins"],
            "contribution_refs": original["contribution_refs"],
        },
        0,
    )
    plan["plan_id"] = "new-name-does-not-reset-original-write"
    if new_envelope:
        selected = plan["contributions"][0]
        result = repository.read_reference(selected["result_ref"])
        selected["result_ref"] = repository.put_reference(
            binding.for_unit("modeler").identity + ":role-result:new-round",
            "role_result",
            result,
            0,
        )
        work_id = binding.for_unit("modeler").identity + ":work"
        work = repository.get(work_id)
        repository.put_reference(
            work_id,
            "work_unit",
            {
                **work["content"],
                "role_result_ref": selected["result_ref"],
            },
            work["revision"],
        )
    with pytest.raises(FrameworkError, match="contribution_already_applied") as caught:
        compose_integration(binding, repository, plan, basis)
    assert caught.value.recoverable
    assert len(repository.list_kind("role_application")) == 1


@pytest.mark.parametrize("unit_id", [None, "cq-public", "modeler"])
def test_real_native_startup_loads_professional_identity_and_tools_without_inference(
    role_task_file, tmp_path, workspace, monkeypatch, unit_id
):
    from openai_codex.generated.v2_all import (
        ListMcpServerStatusResponse,
        McpServerToolCallResponse,
    )

    from ontoweave_modeling.codex_agent import CodexAgent
    from ontoweave_modeling.execution import CodexInvocation

    task = json.loads(role_task_file.read_text())
    task["custom_cq"] = True
    role_task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    selected = binding.for_unit(unit_id) if unit_id else binding
    (binding.root / "private-runtime.json").write_text(
        json.dumps({"connection": workspace.connection, "workspace_schema": workspace.schema})
    )
    config = tmp_path / "read-config.json"
    config.write_text("{}")
    routes, observed = [], []

    class Bridge:
        def call(self, operation, payload):
            assert operation == "read_config"
            assert payload["role"] == selected.role
            return {"config_ref": str(config)}

        @contextmanager
        def provider(self, execution_id, role, tools, **metadata):
            routes.append((execution_id, role, set(tools), metadata))
            # The overridden run_turn never sends turn/start or an upstream request.
            yield "http://127.0.0.1:9"

    class Probe(CodexAgent):
        def run_turn(self, prompt):
            assert self.active_turn is None
            assert self.binding == selected.model(selected.role)
            assert self.instructions.startswith(
                selected.data["role_packages"][selected.role]["instructions"]
            )
            status = self.client.request(
                "mcpServerStatus/list",
                {"limit": 100},
                response_model=ListMcpServerStatusResponse,
            )
            assert len(status.data) == 1
            tools = set(status.data[0].tools)
            assert {"read_material", "read_handoff_material", "get_work_tree"} <= tools
            assert not tools & {
                "modeling_submit_model_changes",
                "apply",
                "write_model",
                "freeze_competency_questions",
                "run_process_evaluation",
            }
            result = self.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": self.thread_id,
                    "server": "workspace",
                    "tool": "read_material",
                    "arguments": {"material_id": "source"},
                },
                response_model=McpServerToolCallResponse,
            )
            assert not result.is_error, result.content
            text = json.loads(result.content[0]["text"])
            assert "condition" in text["text"]
            context = self.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": self.thread_id,
                    "server": "workspace",
                    "tool": "get_modeling_context",
                    "arguments": {},
                },
                response_model=McpServerToolCallResponse,
            )
            assert not context.is_error, context.content
            public = json.dumps(context.content)
            assert "freeze-1" not in public and "case_count" not in public
            if selected.role == "competency-question":
                forbidden = self.client.request(
                    "mcpServer/tool/call",
                    {
                        "threadId": self.thread_id,
                        "server": "workspace",
                        "tool": "delegate_work",
                        "arguments": {
                            "unit_id": "forged-modeler",
                            "objective": "Role escalation",
                            "role_id": "modeling",
                        },
                    },
                    response_model=McpServerToolCallResponse,
                )
                assert forbidden.is_error
                assert "work_role_forbidden" in json.dumps(forbidden.content)
            observed.append((self.thread_id, tools))
            assert self.active_turn is None
            return {"status": "completed", "final_response": "{}"}

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Probe)
    root = tmp_path / "non-inference-probe"
    root.mkdir()
    actual = CodexInvocation(selected, Bridge())(root, "modeling", "Non-inference probe", [])
    assert actual["status"] == "completed", actual
    assert len(observed) == len(routes) == 1
    assert routes[0][1] == selected.role and routes[0][2] == observed[0][1]
    events = (root / "agent/events.jsonl").read_text()
    assert '"method": "turn/started"' not in events


@pytest.mark.parametrize("actor", ["cq-public", "modeler"])
@pytest.mark.parametrize("operation", ["cross_role_delegate", "sibling_update", "sibling_reopen"])
def test_professional_control_cannot_escalate_role_or_rewrite_a_sibling_assignment(
    role_task_file, tmp_path, workspace, actor, operation
):
    from ontoweave_modeling.work_plan import WorkPlan

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    root = WorkPlan(binding.data, workspace)
    original = root.row()
    specialist = WorkPlan(binding.data, workspace, actor)
    other = "modeler" if actor == "cq-public" else "cq-public"
    with pytest.raises(FrameworkError) as caught:
        if operation == "cross_role_delegate":
            specialist.delegate("forged-coordinator", "Role escalation", role_id="coordinator")
        elif operation == "sibling_update":
            specialist.update(other, objective="Silently change another owner's business scope")
        else:
            specialist.reopen(other, "Force unrelated responsibility to reenter")
    assert caught.value.recoverable
    assert root.row() == original


def test_dependency_cycle_is_actionable_and_original_plan_can_be_corrected(
    role_task_file, tmp_path, workspace
):
    from ontoweave_modeling.work_plan import WorkPlan

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    plan = WorkPlan(binding.data, workspace)
    plan.delegate("alpha", "First bounded definition", role_id="modeling")
    plan.delegate("beta", "Dependent definition", dependencies=["alpha"], role_id="modeling")
    original = plan.row()
    with pytest.raises(FrameworkError, match="work_dependency_cycle") as caught:
        plan.update("alpha", dependencies=["beta"])
    assert caught.value.recoverable
    assert {"alpha", "beta"} <= set(caught.value.detail["cycle"])
    assert plan.row() == original
    plan.update("beta", dependencies=[], reason="Remove the accidental reverse dependency")
    plan.update("alpha", dependencies=["beta"], reason="Use the corrected explicit dependency")
    assert plan.row()["content"]["units"]["alpha"]["dependencies"] == ["beta"]


@pytest.fixture
def scheduler_case(role_task_file, tmp_path, workspace):
    from psycopg import sql
    from test_framework_flow import Platform
    from test_role_team_flow import RoleActors

    task = json.loads(role_task_file.read_text())
    task["unit_concurrency"] = 1
    role_task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    platform = Platform()
    platform_call = platform.call
    platform.call = lambda action, payload=None: platform_call(action, payload)
    actors = RoleActors(binding, workspace, platform)
    original_factory = actors.factory

    def baseline_aware_factory(selected):
        underlying = original_factory(selected)

        def invoke(root, purpose, prompt, inputs):
            result = underlying(root, purpose, prompt, inputs)
            payload = json.loads(prompt)
            if (
                selected.role == "modeling"
                and payload.get("phase") == "propose"
                and payload["actual_baseline"]["model_revisions"].get("ontology", 0) > 0
            ):
                # This fixture has one unchanged source/meaning. A late public CQ does not
                # authorize a fresh duplicate create after that meaning has been applied.
                value = json.loads(result["final_response"])
                value["status"] = "no_change"
                value["artifact"]["candidate"] = None
                value["artifact"]["changes"] = {
                    "schema_version": "r4-3-025-model-changes/v1",
                    "candidate_ref": None,
                    "changes": [],
                }
                result["final_response"] = json.dumps(value)
            return result

        return invoke

    actors.factory = baseline_aware_factory
    schema = workspace.schema + "_independent_role_cp"
    try:
        yield binding, platform, actors, schema
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def test_single_slot_intake_precedes_blocked_coordinator_and_partial_reply_does_not_resolve(
    scheduler_case, workspace
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.human_input import HumanInput
    from ontoweave_modeling.multi_unit import MultiUnitFlow

    binding, platform, actors, schema = scheduler_case

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            response = underlying(root, purpose, prompt, inputs)
            if selected.role == "coordinator" and json.loads(prompt).get("phase") == "plan":
                assert actors.calls[0] == ("modeler", "modeling", "source_intake")
                value = json.loads(response["final_response"])
                replies = [
                    item
                    for item in inputs
                    if item.get("metadata", {}).get("source") == "user"
                    and item.get("metadata", {}).get("request_id")
                ]
                if not any(not item["metadata"].get("partial") for item in replies):
                    value.update(status="waiting_input", artifact=None)
                    value["human_requests"] = (
                        []
                        if json.loads(prompt)["human_context"]["requests"]
                        else [
                            {
                                "question": "Which of the two source interpretations applies?",
                                "reason": "Business ownership remains unresolved",
                                "impact": "Only scope allocation waits; intake and public CQ remain useful",
                            }
                        ]
                    )
                else:
                    value["resolved_request_ids"] = [
                        item["metadata"]["request_id"]
                        for item in replies
                        if not item["metadata"].get("partial")
                    ]
                response["final_response"] = json.dumps(value)
            return response

        return invoke

    scheduler = MultiUnitFlow(binding, workspace, platform, schema, factory)
    first = scheduler.advance()
    assert first["work"]["status"] == "waiting_input", first
    assert actors.calls[0] == ("modeler", "modeling", "source_intake")
    assert ("cq-public", "competency-question", "produce") in actors.calls
    assert len(platform.effects) == 0
    control = TaskControl(workspace)
    assert control.view()["active"] == {}
    human = HumanInput(binding, workspace, control)
    requests = human.requests()
    assert len(requests) == 1 and requests[0]["status"] != "resolved"
    request_id = requests[0]["request_id"]
    human.submit(
        "The first case is clear; the second is still unknown.",
        "partial-scope",
        request_id=request_id,
        partial=True,
    )
    partial = scheduler.advance()
    assert partial["work"]["status"] == "waiting_input", partial
    assert len(human.requests()) == 1 and human.requests()[0]["status"] != "resolved"
    assert actors.calls.count(("modeler", "modeling", "source_intake")) == 1
    assert len(platform.effects) == 0
    human.submit(
        "Use the first interpretation for the full declared scope.",
        "complete-scope",
        request_id=request_id,
    )
    final = scheduler.advance()
    assert final["work"]["status"] == "handoff_ready", final
    assert human.requests()[0]["status"] == "resolved"
    assert len(platform.effects) == 1
    assert actors.calls.count(("modeler", "modeling", "source_intake")) == 1
    assert ("modeler", "modeling", "propose") in actors.calls


def test_parallel_roles_have_overlapping_real_control_activities(scheduler_case, workspace):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.multi_unit import MultiUnitFlow

    binding, platform, actors, schema = scheduler_case
    binding.data["unit_concurrency"] = 2
    intake_started, coordinator_started = threading.Event(), threading.Event()
    overlap_observed = threading.Event()
    overlaps = []

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            phase = json.loads(prompt).get("phase")
            if phase == "source_intake":
                intake_started.set()
                assert coordinator_started.wait(10), "Coordinator did not overlap admitted intake"
                active = TaskControl(workspace).view()["active"]
                overlaps.append({"modeler", binding.data["work_unit_id"]} <= set(active))
                overlap_observed.set()
            elif selected.role == "coordinator" and phase == "plan":
                assert intake_started.wait(10), "Modeler intake was not admitted promptly"
                coordinator_started.set()
                assert overlap_observed.wait(10), "Concurrent activities were not observable"
            return underlying(root, purpose, prompt, inputs)

        return invoke

    result = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
    assert result["work"]["status"] == "handoff_ready", result
    assert overlaps == [True]
    assert len(platform.effects) == 1
    assert TaskControl(workspace).view()["active"] == {}


def test_unknown_application_keeps_first_blocker_and_original_operation(scheduler_case, workspace):
    from ontoweave_modeling.multi_unit import MultiUnitFlow
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, schema = scheduler_case
    platform.uncertain = True
    scheduler = MultiUnitFlow(binding, workspace, platform, schema, actors.factory)
    first = scheduler.advance()
    assert first["work"]["status"] == "uncertain", first
    assert first["work"]["operation_ref"]
    original = first["work"]["operation_ref"]
    assert len(platform.effects) == 1
    WorkPlan(binding.data, workspace).reopen("modeler", "New source input while apply is unknown")
    later = MultiUnitFlow(binding, workspace, platform, schema, actors.factory).advance()
    assert later["work"]["operation_ref"]["object_id"] == original["object_id"]
    assert workspace.read_reference(original)["status"] == "uncertain"
    assert later["work"]["status"] == "uncertain", later
    assert len(platform.effects) == 1


@pytest.mark.parametrize("pause_kind", ["pause", "budget_pause"])
def test_concurrent_pause_drains_every_admitted_role_and_resume_reuses_completed_intake(
    scheduler_case, workspace, pause_kind
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.multi_unit import MultiUnitFlow

    binding, platform, actors, schema = scheduler_case
    binding.data["unit_concurrency"] = 2
    intake_started, release_current = threading.Event(), threading.Event()
    control = TaskControl(workspace)
    intermediate = []

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            phase = json.loads(prompt).get("phase")
            if phase == "source_intake":
                intake_started.set()
                assert release_current.wait(10), "Coordinator did not queue pause during intake"
            elif selected.role == "coordinator" and phase == "plan":
                assert intake_started.wait(10)
                control.enqueue("pause-concurrent-roles", pause_kind)
                observed = control.synchronize()
                intermediate.append(observed)
                release_current.set()
            return underlying(root, purpose, prompt, inputs)

        return invoke

    paused = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
    assert paused["work"]["status"] == "paused", paused
    assert len(intermediate) == 1
    assert intermediate[0]["status"] == "waiting_for_turn_end"
    assert {"modeler", binding.data["work_unit_id"]} <= set(intermediate[0]["active"])
    settled = control.view()
    assert settled["status"] == "settled" and settled["active"] == {}
    assert len(actors.calls) == 2
    assert len(platform.effects) == 0
    control.enqueue(
        "resume-concurrent-roles", "resume" if pause_kind == "pause" else "budget_resume"
    )
    final = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
    assert final["work"]["status"] == "handoff_ready", final
    assert actors.calls.count(("modeler", "modeling", "source_intake")) == 1
    assert actors.calls.count(("coordinator", "coordinator", "plan")) == 1
    assert len(platform.effects) == 1
    assert control.view()["active"] == {}


def test_recursive_coordinator_keeps_leaf_author_and_runs_each_original_check(
    scheduler_case, workspace
):
    from test_framework_flow import tool_event

    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.multi_unit import MultiUnitFlow
    from ontoweave_modeling.team import TeamChannel
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, schema = scheduler_case

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt_text, inputs):
            prompt = json.loads(prompt_text)
            phase = prompt.get("phase")
            if selected.role != "coordinator" or phase != "integrate":
                result = underlying(root, purpose, prompt_text, inputs)
                if selected.role == "coordinator" and phase == "plan":
                    value = json.loads(result["final_response"])
                    root_level = selected.actor == "coordinator"
                    value["artifact"]["assignments"] = [
                        {
                            "unit_id": "middle" if root_level else "nested-modeler",
                            "role_id": "coordinator" if root_level else "modeling",
                            "objective": "Integrate complete bounded meaning"
                            if root_level
                            else "Express the original condition and exception",
                            "material_ids": ["source"],
                            "dependencies": [],
                            "instructions": "Retain full meaning, original authors and actual read-back",
                            "scope_id": "whole-scope" if root_level else "bounded-leaf",
                        }
                    ]
                    result["final_response"] = json.dumps(value)
                return result
            actors.calls.append((selected.actor, selected.role, phase))
            source_ref = {
                "material_id": "source",
                "sha256": selected.data["source_manifest"]["source"]["sha256"],
            }
            events = [
                tool_event(
                    "read_material",
                    {"text": "condition AND exception", "sha256": source_ref["sha256"]},
                    {"material_id": "source"},
                )
            ]
            response = {
                "schema_version": "role-work-result/v1",
                "status": "proposed",
                "basis": deepcopy(prompt["basis"]),
                "artifact": None,
                "source_refs": [source_ref],
                "issues": [],
                "consumed_ids": [item["id"] for item in inputs],
            }
            plan = WorkPlan(selected.data, workspace).row()["content"]
            members = {
                unit_id
                for unit_id, unit in plan["units"].items()
                if unit["parent_id"] == selected.actor
                and unit["status"] == "active"
                and unit["role_id"] in {"coordinator", "modeling"}
            }
            contributions, coordination_refs, owners = [], [], []
            channel = TeamChannel(selected.data, workspace, TaskControl(workspace), selected.actor)
            for entry in prompt["child_results"]:
                if entry["unit_id"] not in members:
                    continue
                work = entry.get("work") or {}
                if work.get("status") != "proposal_ready":
                    continue
                material_ref = work["result_material_ref"]
                read = channel.read(material_ref, limit=1000000)
                events.append(
                    tool_event("read_handoff_material", read, {"reference": material_ref})
                )
                response["basis"]["consumed_refs"].append(material_ref)
                owners.append(entry["unit_id"])
                if entry["role_id"] == "coordinator":
                    coordination_refs.append(work["role_result_ref"])
                else:
                    result = workspace.read_reference(work["role_result_ref"])
                    changes = workspace.read_reference(result["changes_ref"])
                    contributions.append(
                        {
                            "owner_work_id": entry["unit_id"],
                            "generation": entry["generation"],
                            "result_ref": work["role_result_ref"],
                            "candidate_ref": result["candidate_ref"],
                            "changes_ref": result["changes_ref"],
                            "selected_change_ids": [
                                change["change_id"] for change in changes["changes"]
                            ],
                        }
                    )
            response["artifact"] = {
                "schema_version": "integration-plan/v1",
                "plan_id": selected.actor + "-integration",
                "contributions": contributions,
                "coordination_refs": coordination_refs,
                "shared_decision_refs": [],
                "deferred": [],
                "ontology_targets": {},
                "check_units": owners,
            }
            (root / "agent").mkdir()
            (root / "agent/events.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events)
            )
            return {
                "status": "completed",
                "thread_id": selected.actor + "-" + root.name,
                "turn_id": root.name,
                "final_response": json.dumps(response),
            }

        return invoke

    scheduler = MultiUnitFlow(binding, workspace, platform, schema, factory)
    result = scheduler.advance()
    assert result["work"]["status"] == "handoff_ready", result
    assert len(platform.effects) == 1
    application = workspace.list_kind("role_application")
    assert len(application) == 1
    assert {
        origin["owner_work_id"] for origin in application[0]["content"]["origins"].values()
    } == {"nested-modeler"}
    for actor, role in (
        ("nested-modeler", "modeling"),
        ("middle", "coordinator"),
        ("coordinator", "coordinator"),
    ):
        assert (actor, role, "self_check") in actors.calls
    assert (
        actors.calls.index(("nested-modeler", "modeling", "self_check"))
        < actors.calls.index(("middle", "coordinator", "self_check"))
        < actors.calls.index(("coordinator", "coordinator", "self_check"))
    )
    retained = list(actors.calls)
    assert scheduler.advance()["work"]["status"] == "handoff_ready"
    assert actors.calls == retained and len(platform.effects) == 1
    assert TaskControl(workspace).view()["active"] == {}


def test_host_response_exception_is_reconciled_with_original_operation_before_reentry(
    scheduler_case, workspace
):
    from ontoweave_modeling.multi_unit import MultiUnitFlow
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, schema = scheduler_case
    original_call = platform.call
    apply_ids = []
    allow_reconciliation = False

    def lose_first_response(action, payload=None):
        result = original_call(action, payload)
        if action == "apply":
            apply_ids.append(payload["operation_id"])
            if not allow_reconciliation:
                raise FrameworkError(
                    "host_response_unknown", layer="runtime/infrastructure", operation="apply"
                )
        return result

    platform.call = lose_first_response
    first = MultiUnitFlow(binding, workspace, platform, schema, actors.factory).advance()
    assert first["work"]["status"] == "uncertain", first
    original_ref = first["work"]["operation_ref"]
    original = workspace.read_reference(original_ref)
    assert original["issue"]["code"] == "host_response_unknown"
    assert original["issue"]["layer"] == "runtime/infrastructure"
    assert len(platform.effects) == 1
    WorkPlan(binding.data, workspace).reopen("modeler", "New input cannot replace an unknown write")
    allow_reconciliation = True
    final = MultiUnitFlow(binding, workspace, platform, schema, actors.factory).advance()
    assert final["work"]["status"] == "handoff_ready", final
    assert set(apply_ids) == {original["operation_id"]}
    assert len(apply_ids) >= 2 and len(platform.effects) == 1
    assert workspace.read_reference(original_ref) == original


@pytest.mark.parametrize("terminal_proof", ["result_file", "terminal_turn_events"])
def test_lost_native_response_reuses_original_intake_without_invoking_it_again(
    scheduler_case, workspace, terminal_proof
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.multi_unit import MultiUnitFlow

    binding, platform, actors, schema = scheduler_case
    retained = []

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            result = underlying(root, purpose, prompt, inputs)
            if selected.role == "modeling" and json.loads(prompt).get("phase") == "source_intake":
                assert not retained, "An unsettled original intake was invoked a second time"
                retained.append((root, result, (root / "agent/events.jsonl").read_text()))
                raise ConnectionError("Original native result response was lost after dispatch")
            return result

        return invoke

    first = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
    assert len(retained) == 1
    assert first["work"]["status"] != "handoff_ready"
    active = TaskControl(workspace).view()["active"]
    assert "modeler" in active
    original_execution = active["modeler"]
    root, result, reads = retained[0]
    assert root.name == original_execution
    if terminal_proof == "result_file":
        (root / "result.json").write_text(json.dumps(result))
    else:
        events = [
            {
                "method": "turn/started",
                "params": {"threadId": result["thread_id"], "turn": {"id": result["turn_id"]}},
            },
            *(json.loads(line) for line in reads.splitlines()),
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": result["final_response"]}},
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": result["turn_id"], "status": "completed"}},
            },
        ]
        (root / "agent/events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    final = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
    assert final["work"]["status"] == "handoff_ready", final
    assert actors.calls.count(("modeler", "modeling", "source_intake")) == 1
    intakes = [
        row
        for row in workspace.list_kind("role_work_result")
        if row["content"].get("phase") == "source_intake"
    ]
    assert len(intakes) == 1
    assert (
        workspace.read_reference(intakes[0]["content"]["execution_ref"])["intent"]["execution_id"]
        == original_execution
    )
    assert len(platform.effects) == 1
    assert TaskControl(workspace).view()["active"] == {}


@pytest.mark.parametrize("old_binding_without_contract", [False, True])
def test_snapshot_fork_preserves_bound_team_mode_and_starts_fresh_role_work(
    role_task_file, tmp_path, workspace, saver, old_binding_without_contract
):
    from test_snapshot_fork import ForkPlatform

    from ontoweave_modeling.flow import WorkUnitFlow
    from ontoweave_modeling.snapshot_fork import SnapshotFork
    from ontoweave_modeling.snapshots import RunSnapshots
    from ontoweave_modeling.work_plan import WorkPlan

    task = json.loads(role_task_file.read_text())
    if old_binding_without_contract:
        task["team_contract"] = "single-modeler/v1"
    role_task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(role_task_file, tmp_path / "source-run")
    if old_binding_without_contract:
        envelope = json.loads((binding.root / "binding.json").read_text())
        envelope["binding"].pop("team_contract")
        envelope["digest"] = digest(envelope["binding"])
        (binding.root / "binding.json").write_text(json.dumps(envelope))
        binding = TaskBinding.load(binding.root)
    plan = WorkPlan(binding.data, workspace)
    plan.delegate("previous-task-only", "Old assigned work", role_id="modeling")
    (binding.root / "private-runtime.json").write_text(
        json.dumps(
            {
                "connection": workspace.connection,
                "workspace_schema": workspace.schema,
                "checkpoint_schema": workspace.schema + "_cp",
            }
        )
    )
    platform = ForkPlatform()
    flow = WorkUnitFlow(binding, workspace, platform, None)
    state = flow.initialize()
    baseline = workspace.put_reference(
        "fork-test-model", "model_reference", platform.call("snapshot", {}), 0
    )
    flow._save({**state, "baseline_ref": baseline})
    saved = RunSnapshots(binding, workspace).save(
        "bound-team-snapshot", flow.compile(saver), platform, include_platform=True
    )
    destination = tmp_path / "forked-run"
    result = SnapshotFork(binding, workspace, platform).create(
        saved["snapshot_id"],
        destination,
        "explicit-fork-run",
        "Engineering-only fork fixture",
        "test-authorized-fork",
        True,
    )
    assert result["status"] == "prepared"
    forked = TaskBinding.load(destination)
    assert forked.role_team == binding.role_team
    assert forked.root_actor == binding.root_actor
    assert forked.thread_id != binding.thread_id
    if not old_binding_without_contract:
        assert {unit["unit_id"] for unit in forked.data["work_units"]} == {"modeler", "cq-public"}
        assert forked.data["role_packages"] == binding.data["role_packages"]
    else:
        assert forked.data["team_contract"] == "single-modeler/v1"
        assert "role_packages" not in forked.data
    assert not (destination / "executions").exists()


def test_combination_renames_only_reference_slots_and_preserves_business_json_literals(
    contribution_case,
):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    selected = plan["contributions"][0]
    envelope = repository.read_reference(selected["result_ref"])
    artifact = deepcopy(repository.read_reference(envelope["artifact_ref"]))
    literal = {
        "definition_ref": "same",
        "from_item_id": "same",
        "to_item_id": "edge",
        "nested": {"definition_ref": "pred"},
    }
    entity = artifact["candidate"]["items"][0]
    semantic_body = {
        "business_meaning": entity["business_meaning"],
        "definition_ref": "same",
        "from_item_id": "same",
    }
    entity["value"]["properties"] = [
        {"property_ref": {"definition_ref": "pred"}, "value": deepcopy(literal)}
    ]
    entity["value"]["semantic_definition"] = deepcopy(semantic_body)
    prefix = binding.for_unit("modeler").identity
    candidate_ref = repository.put_reference(
        prefix + ":literal-candidate", "model_candidate", artifact["candidate"], 0
    )
    artifact_ref = repository.put_reference(
        prefix + ":literal-artifact", "role_artifact", artifact, 0
    )
    result_ref = repository.put_reference(
        prefix + ":literal-result",
        "role_work_result",
        {
            **envelope,
            "candidate_ref": candidate_ref,
            "artifact_ref": artifact_ref,
        },
        0,
    )
    work = repository.get(prefix + ":work")
    repository.put_reference(
        prefix + ":work",
        "work_unit",
        {
            **work["content"],
            "role_result_ref": result_ref,
        },
        work["revision"],
    )
    selected.update(result_ref=result_ref, candidate_ref=candidate_ref)
    output = compose_integration(binding, repository, plan, basis)
    entity = next(
        item
        for item in output["candidate"]["items"]
        if item["item_kind"] == "entity" and item["slice_ids"] == ["modeler"]
    )
    actual = entity["value"]
    assert actual["properties"][0]["value"] == literal
    assert actual["semantic_definition"] == semantic_body
    assert actual["properties"][0]["property_ref"]["definition_ref"] != "pred"


@pytest.mark.parametrize("claimed_author", ["cq-public", "user"])
def test_public_cq_self_claimed_confirmation_is_rejected_and_draft_correction_is_recoverable(
    scheduler_case, workspace, saver, claimed_author
):
    from ontoweave_modeling.flow import WorkUnitFlow
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, _ = scheduler_case
    WorkPlan(binding.data, workspace).row()
    selected = binding.for_unit("cq-public")
    underlying = actors.factory(selected)
    confirmed = True

    def invoke(root, purpose, prompt, inputs):
        result = underlying(root, purpose, prompt, inputs)
        value = json.loads(result["final_response"])
        question = value["artifact"]["questions"][0]
        question.update(
            criteria_status="confirmed" if confirmed else "draft",
            reference_answer="Unconfirmed proposed answer",
            answer_author=claimed_author,
        )
        result["final_response"] = json.dumps(value)
        return result

    flow = WorkUnitFlow(selected, workspace, platform, invoke)
    first = flow.advance(saver)
    assert first["status"] == "recoverable_issue", first
    assert first["issue"]["code"] == "public_cq_confirmation_basis_required"
    assert WorkPlan(binding.data, workspace).row()["content"].get("public_cq_ref") is None
    confirmed = False
    corrected = flow.advance(saver)
    assert corrected["status"] == "proposal_ready", corrected
    cq_ref = WorkPlan(binding.data, workspace).row()["content"]["public_cq_ref"]
    assert workspace.read_reference(cq_ref)["questions"][0]["criteria_status"] == "draft"
    assert len(platform.effects) == 0


def test_public_cq_can_confirm_only_the_exact_consumed_nonpartial_business_answer(
    scheduler_case, workspace, saver
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.flow import WorkUnitFlow
    from ontoweave_modeling.human_input import HumanInput
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, _ = scheduler_case
    WorkPlan(binding.data, workspace).row()
    selected = binding.for_unit("cq-public")
    underlying = actors.factory(selected)
    question_text = "What is the approved condition?"

    def invoke(root, purpose, prompt, inputs):
        result = underlying(root, purpose, prompt, inputs)
        value = json.loads(result["final_response"])
        if not inputs:
            value.update(
                status="waiting_input",
                artifact=None,
                human_requests=[
                    {
                        "question": question_text,
                        "reason": "Answer criterion needs business confirmation",
                        "impact": "Public CQ reference answer only",
                    }
                ],
            )
        else:
            answer = next(
                item for item in inputs if item.get("metadata", {}).get("source") == "user"
            )
            value["artifact"]["questions"][0].update(
                criteria_status="confirmed",
                reference_answer=answer["body"],
                answer_author=answer["metadata"]["author"],
            )
            value["resolved_request_ids"] = [answer["metadata"]["request_id"]]
        result["final_response"] = json.dumps(value)
        return result

    flow = WorkUnitFlow(selected, workspace, platform, invoke)
    assert flow.advance(saver)["status"] == "waiting_input"
    human = HumanInput(selected, workspace, TaskControl(workspace))
    human.submit(
        "Acceptance AND signature are required.",
        "confirmed-public-answer",
        request_id=human.requests()[0]["request_id"],
        author="business-owner",
    )
    final = flow.advance(saver)
    assert final["status"] == "proposal_ready", final
    public = workspace.read_reference(
        WorkPlan(binding.data, workspace).row()["content"]["public_cq_ref"]
    )
    question = public["questions"][0]
    assert question["criteria_status"] == "confirmed"
    assert question["reference_answer"] == "Acceptance AND signature are required."
    assert question["answer_author"] == "business-owner"
    assert human.requests()[0]["status"] == "resolved"
    assert len(platform.effects) == 0


@pytest.mark.parametrize(
    "mode", ["conflict", "disjoint", "equal", "malformed", "missing_action", "missing_change_id"]
)
def test_actual_host_resolves_target_aliases_before_conflict_check_and_keeps_typed_errors(
    role_task_file, tmp_path, mode
):
    from ontoweave_modeling.host_bridge import HostBridge

    binding = TaskBinding.prepare(role_task_file, tmp_path / "role-run")
    bridge = HostBridge(binding.root)
    program = r"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
from ontoweave_modeling.contracts import TaskBinding
from modeling_team.v5.host.worker import PlatformWorker
import modeling_team.direct_binding as direct
worker = PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
mode = sys.argv[2]
worker.scope = lambda: SimpleNamespace(ontology_id="ontology", ontology_ids=["ontology"])
worker.save_scope = lambda scope: None
worker.forwarder = lambda scope: SimpleNamespace(stop=lambda: None)
worker._close_applied_sessions = lambda *args, **kwargs: None
worker.executor = lambda *args, **kwargs: None
worker.read_binding = lambda scope, reference: {
    "resource_id": "actual-native-class", "resource_iri": "urn:actual:shared-class",
    "resource_kind": "class", "ontology_id": "ontology",
}
forwarded = []
def execute(*args):
    forwarded.append(True)
    return {"status":"completed", "batches":[], "errors":[], "pending_changes":[]}
direct.execute_bound_model_changes = execute
def change(identity, field_values):
    return {"change_id":identity, "action":"update", "resource_kind":"class", "item_id":None,
            "target_ref":{"artifact_ref":identity+"-actual-read.json", "path":"/native-result"},
            "fields":field_values}
second = {"description":"B"} if mode in {"conflict", "missing_change_id"} else (
    {"name":"Revised actual name"} if mode == "disjoint" else {"description":"A"})
changes = [None] if mode == "malformed" else [change("a", {"description":"A"}), change("b", second)]
if mode == "missing_action":
    changes[0].pop("action")
if mode == "missing_change_id":
    changes[0].pop("change_id")
result = worker.apply({"operation_id":"alias-contract", "candidate":None, "changes":{
    "schema_version":"r4-3-025-model-changes/v1", "candidate_ref":None, "changes":changes}})
if mode in {"conflict", "malformed", "missing_action", "missing_change_id"}:
    assert result["status"] == "not_written", result
    assert result["errors"] and not forwarded
    if mode == "conflict":
        assert result["errors"][0]["code"] == "shared_target_conflict", result
else:
    assert result["status"] == "completed" and len(forwarded) == 1, result
assert "modeling_team.runner" not in sys.modules
print(json.dumps({"status":result["status"], "executor_calls":len(forwarded)}))
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root), mode],
        env=bridge.env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["executor_calls"] == (
        0 if mode in {"conflict", "malformed", "missing_action", "missing_change_id"} else 1
    )


@pytest.mark.parametrize("malformation", ["missing_change_id", "changes_not_array"])
def test_modeler_technical_format_error_is_recoverable_and_preserves_native_goal(
    scheduler_case, workspace, saver, malformation
):
    from ontoweave_modeling.flow import WorkUnitFlow
    from ontoweave_modeling.work_plan import WorkPlan

    binding, platform, actors, _ = scheduler_case
    plan = WorkPlan(binding.data, workspace)
    plan.change(lambda value: value["units"]["modeler"].update(work_phase="propose"))
    selected = plan.binding(binding).for_unit("modeler")
    underlying = actors.factory(selected)
    original_goal = selected.data["objective"]
    malformed = True
    native_results = []

    def invoke(root, purpose, prompt, inputs):
        result = underlying(root, purpose, prompt, inputs)
        value = json.loads(result["final_response"])
        if malformed:
            if malformation == "missing_change_id":
                value["artifact"]["changes"]["changes"][0].pop("change_id")
            else:
                value["artifact"]["changes"]["changes"] = "not-an-array"
        result["final_response"] = json.dumps(value)
        native_results.append(result["final_response"])
        return result

    flow = WorkUnitFlow(selected, workspace, platform, invoke)
    first = flow.advance(saver)
    assert first["status"] in {"recoverable_issue", "blocked"}, first
    assert first["issue"]["recoverable"] is True
    location = first["issue"].get("path") or first["issue"].get("detail")
    assert location and "/changes" in str(location), first
    assert ("change_id" if malformation == "missing_change_id" else "array") in str(first["issue"])
    assert len(platform.effects) == 0
    retained = [row["content"] for row in workspace.list_kind("execution")]
    assert any(row.get("result", {}).get("final_response") == native_results[0] for row in retained)
    assert workspace.read_reference(first["binding_ref"])["objective"] == original_goal
    malformed = False
    corrected = flow.advance(saver)
    assert corrected["status"] == "proposal_ready", corrected
    assert workspace.read_reference(corrected["binding_ref"])["objective"] == original_goal
    assert len(platform.effects) == 0


@pytest.mark.parametrize("bad_items", [None, [None]], ids=["items-not-array", "item-not-object"])
def test_candidate_item_technical_shape_error_is_typed_without_mutating_contribution(
    contribution_case, bad_items
):
    from ontoweave_modeling.role_team import compose_integration

    binding, repository, plan, basis = contribution_case
    selected = plan["contributions"][0]
    old_ref = deepcopy(selected["result_ref"])
    original = deepcopy(repository.read_reference(old_ref))
    artifact = deepcopy(repository.read_reference(original["artifact_ref"]))
    artifact["candidate"]["items"] = bad_items
    prefix = binding.for_unit("modeler").identity
    candidate_ref = repository.put_reference(
        prefix + ":bad-items-candidate", "model_candidate", artifact["candidate"], 0
    )
    artifact_ref = repository.put_reference(
        prefix + ":bad-items-artifact", "role_artifact", artifact, 0
    )
    result_ref = repository.put_reference(
        prefix + ":bad-items-result",
        "role_work_result",
        {
            **original,
            "candidate_ref": candidate_ref,
            "artifact_ref": artifact_ref,
        },
        0,
    )
    work = repository.get(prefix + ":work")
    repository.put_reference(
        prefix + ":work",
        "work_unit",
        {
            **work["content"],
            "role_result_ref": result_ref,
        },
        work["revision"],
    )
    selected.update(candidate_ref=candidate_ref, result_ref=result_ref)
    with pytest.raises(FrameworkError) as caught:
        compose_integration(binding, repository, plan, basis)
    assert caught.value.recoverable and caught.value.detail.get("path")
    assert repository.read_reference(old_ref) == original
    assert repository.read_reference(result_ref)["artifact_ref"] == artifact_ref
