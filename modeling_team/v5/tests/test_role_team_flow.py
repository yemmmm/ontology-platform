"""Professional lifecycle on real PostgreSQL/checkpoints with deterministic actors."""

import json
from copy import deepcopy

import pytest
import yaml
from psycopg import sql
from test_framework_flow import Platform, tool_event

from ontoweave_modeling.contracts import TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.team import TeamChannel


@pytest.fixture
def role_binding(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task.pop("team_contract")
    task["unit_concurrency"] = 1
    task_file.write_text(json.dumps(task))
    profile_path = task_file.parent / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text())
    for role in ("coordinator", "competency-question"):
        profile["roles"][role] = dict(profile["roles"]["modeling"])
    profile_path.write_text(yaml.safe_dump(profile))
    return TaskBinding.prepare(task_file, tmp_path / "role-run")


class RoleActors:
    def __init__(self, binding, repository, platform):
        self.binding, self.repository, self.platform = binding, repository, platform
        self.calls = []

    def factory(self, selected):
        def invoke(root, purpose, prompt_text, inputs):
            prompt = json.loads(prompt_text)
            phase = "self_check" if purpose == "self_check" else prompt["phase"]
            self.calls.append((selected.actor, selected.role, phase))
            folder = root / "agent"
            folder.mkdir()
            source = selected.data["source_manifest"]["source"]
            source_ref = {"material_id": "source", "sha256": source["sha256"]}
            events = [
                tool_event(
                    "read_material",
                    {"text": "actual source", "sha256": source["sha256"]},
                    {"material_id": "source"},
                )
            ]
            if phase in {"self_check", "review"}:
                events.append(
                    tool_event(
                        "query_semantic_context",
                        {
                            "ok": True,
                            "scope": {
                                "ontologies": [
                                    {
                                        "ontology_id": "ontology",
                                        "model_revision": len(self.platform.effects),
                                    }
                                ]
                            },
                        },
                    )
                )
            if phase == "self_check":
                response = {
                    "status": "ready",
                    "issues": [],
                    "consumed_ids": [m["id"] for m in inputs],
                }
            else:
                response = {
                    "schema_version": "role-work-result/v1",
                    "status": "proposed",
                    "basis": deepcopy(prompt["basis"]),
                    "artifact": None,
                    "source_refs": [source_ref],
                    "issues": [],
                    "consumed_ids": [m["id"] for m in inputs],
                }
                if phase == "source_intake":
                    response["artifact"] = {
                        "schema_version": "source-intake/v1",
                        "propositions": ["Condition AND exception from actual original source"],
                        "unknowns": [],
                    }
                elif selected.role == "competency-question":
                    response["artifact"] = {
                        "schema_version": "public-cq-set/v1",
                        "questions": [
                            {
                                "cq_id": "public-one",
                                "question": "What is the approved condition?",
                                "coverage_kind": "panorama",
                                "scope_ids": ["full-objective"],
                                "source_refs": [source_ref],
                                "reference_answer": None,
                                "criteria_status": "unknown",
                                "answer_author": None,
                            }
                        ],
                        "reused_ids": [],
                        "revised_ids": [],
                        "new_ids": ["public-one"],
                        "unknowns": [],
                        "coverage_gaps": [],
                    }
                elif selected.role == "modeling":
                    response["artifact"] = {
                        "candidate": None,
                        "changes": {
                            "schema_version": "r4-3-025-model-changes/v1",
                            "candidate_ref": None,
                            "changes": [
                                {
                                    "change_id": "create-one",
                                    "action": "create",
                                    "resource_kind": "class",
                                    "item_id": None,
                                    "target_ref": None,
                                    "fields": {
                                        "name": "Actual approved condition",
                                        "description": "Preserved condition AND exception",
                                    },
                                }
                            ],
                        },
                        "ontology_targets": None,
                        "review_units": [],
                        "shared_conflicts": [],
                        "public_cq_disposition": "Current public question reviewed or still pending",
                    }
                elif phase == "plan":
                    response["artifact"] = {
                        "schema_version": "scope-plan/v1",
                        "scope": selected.data["objective"],
                        "assignments": [
                            {
                                "unit_id": "modeler",
                                "role_id": "modeling",
                                "objective": "Express approved condition",
                                "material_ids": ["source"],
                                "dependencies": [],
                                "instructions": "Keep the source exception",
                                "scope_id": "full-objective",
                            }
                        ],
                        "shared_definitions": [],
                        "unassigned": [],
                        "confirmation_points": [],
                        "integration_obligations": ["Whole-source condition and exception"],
                    }
                else:
                    contributions = []
                    channel = TeamChannel(
                        selected.data, self.repository, TaskControl(self.repository), selected.actor
                    )
                    for entry in prompt["child_results"]:
                        work = entry.get("work") or {}
                        if entry["role_id"] != "modeling" or work.get("status") != "proposal_ready":
                            continue
                        material_ref = work["result_material_ref"]
                        read = channel.read(material_ref, limit=1000000)
                        events.append(
                            tool_event("read_handoff_material", read, {"reference": material_ref})
                        )
                        response["basis"]["consumed_refs"].append(material_ref)
                        result = self.repository.read_reference(work["role_result_ref"])
                        changes = self.repository.read_reference(result["changes_ref"])
                        contributions.append(
                            {
                                "owner_work_id": entry["unit_id"],
                                "generation": entry["generation"],
                                "result_ref": work["role_result_ref"],
                                "candidate_ref": result["candidate_ref"],
                                "changes_ref": result["changes_ref"],
                                "selected_change_ids": [c["change_id"] for c in changes["changes"]],
                            }
                        )
                    response["artifact"] = {
                        "schema_version": "integration-plan/v1",
                        "plan_id": "one-integration",
                        "contributions": contributions,
                        "shared_decision_refs": [],
                        "deferred": [],
                        "ontology_targets": {},
                        "check_units": [c["owner_work_id"] for c in contributions],
                    }
            (folder / "events.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events) + "\n"
            )
            return {
                "status": "completed",
                "thread_id": selected.actor + "-" + root.name,
                "turn_id": root.name,
                "final_response": json.dumps(response),
            }

        return invoke


class RolePlatform(Platform):
    def call(self, action, payload=None):
        return super().call(action, payload)


@pytest.mark.parametrize("concurrency", [1, 2])
def test_default_specialist_lifecycle_and_repeated_resume_do_not_replay(
    role_binding, workspace, concurrency
):
    role_binding.data["unit_concurrency"] = concurrency
    platform = RolePlatform()
    actors = RoleActors(role_binding, workspace, platform)
    schema = workspace.schema + "_role_cp"
    try:
        scheduler = MultiUnitFlow(role_binding, workspace, platform, schema, actors.factory)
        result = scheduler.advance()
        assert result["work"]["status"] == "handoff_ready", result
        assert (
            actors.calls[0] == ("modeler", "modeling", "source_intake")
            if concurrency == 1
            else True
        )
        assert ("coordinator", "coordinator", "plan") in actors.calls
        assert ("coordinator", "coordinator", "integrate") in actors.calls
        assert ("modeler", "modeling", "propose") in actors.calls
        assert ("modeler", "modeling", "self_check") in actors.calls
        assert ("cq-public", "competency-question", "review") in actors.calls
        assert ("coordinator", "coordinator", "self_check") in actors.calls
        assert actors.calls.count(("modeler", "modeling", "source_intake")) == 1
        assert len(platform.effects) == 1
        handoff = workspace.read_reference(result["work"]["handoff_ref"])
        assert handoff["team_contract"] == "role-team/v1"
        assert set(handoff["role_results"]) >= {"modeler", "cq-public"}
        assert len(workspace.list_kind("role_application")) == 1
        before = list(actors.calls)
        assert scheduler.advance()["work"]["status"] == "handoff_ready"
        assert actors.calls == before and len(platform.effects) == 1
        assert TaskControl(workspace).view()["active"] == {}
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )
