"""Regressions from real role-team inputs and native MCP wire shapes; no paid calls."""

import hashlib
import json
import threading
from pathlib import Path

import pytest
from psycopg import sql
from test_framework_flow import tool_event
from test_role_team_flow import RoleActors, RolePlatform
from test_role_team_independent import role_task_file as role_task_file  # noqa: PLC0414

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.role_work import _read_materials
from ontoweave_modeling.team import TeamChannel
from ontoweave_modeling.work_plan import WorkPlan


@pytest.fixture
def seed_task(role_task_file):
    """Use the actual public Demo seed without importing any historical model or answers."""
    task = json.loads(role_task_file.read_text())
    materials = Path(task["materials"])
    payload = (
        Path(__file__).resolve().parents[3] / "examples/llm-access-lab/competency-questions.json"
    ).read_bytes()
    (materials / "public-cq.json").write_bytes(payload)
    manifest = json.loads((materials / "manifest.json").read_text())
    manifest["public-cq"] = {
        "path": "public-cq.json",
        "source_ref": "approved-public-demo-goals",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "material_type": "competency_goal",
    }
    (materials / "manifest.json").write_text(json.dumps(manifest))
    return role_task_file


@pytest.mark.parametrize("serialized", [False, True])
def test_complete_handoff_uses_success_receipt_regardless_of_argument_encoding(
    tmp_path, serialized
):
    reference = {"object_id": "material:owner:contribution", "revision": 2, "digest": "a" * 64}
    argument = json.dumps(reference) if serialized else reference
    # Native MCP may retain a string argument after the server has parsed it successfully.
    data = {"reference": reference, "offset": 0, "total_characters": 12, "text": "full content"}
    event = tool_event("read_handoff_material", data, {"reference": argument})
    event["params"]["item"]["result"] = {"content": [{"type": "text", "text": json.dumps(data)}]}
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(event) + "\n")
    _read_materials(path, [reference])


@pytest.mark.parametrize("defect", ["partial", "wrong_digest", "failed"])
def test_handoff_still_requires_complete_success_of_exact_version(tmp_path, defect):
    ref = {"object_id": "material:owner:contribution", "revision": 2, "digest": "a" * 64}
    data = {"reference": dict(ref), "offset": 0, "total_characters": 12, "text": "full content"}
    if defect == "partial":
        data["text"] = "full"
    if defect == "wrong_digest":
        data["reference"]["digest"] = "b" * 64
    event = tool_event("read_handoff_material", data, {"reference": json.dumps(ref)})
    if defect == "failed":
        event["params"]["item"]["result"]["isError"] = True
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(event) + "\n")
    with pytest.raises(FrameworkError, match="role_material_not_consumed"):
        _read_materials(path, [ref])


@pytest.mark.parametrize("concurrency", [1, 2])
def test_public_seed_existing_cq_and_native_reference_encoding_complete_lifecycle(
    seed_task, tmp_path, workspace, concurrency
):
    task = json.loads(seed_task.read_text())
    task["unit_concurrency"] = concurrency
    seed_task.write_text(json.dumps(task))
    binding = TaskBinding.prepare(seed_task, tmp_path / "live-shapes-run")
    platform = RolePlatform()
    actors = RoleActors(binding, workspace, platform)

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            native = underlying(root, purpose, prompt, inputs)
            if purpose != "self_check":
                result = json.loads(native["final_response"])
                if selected.role == "coordinator" and json.loads(prompt)["phase"] == "plan":
                    result["artifact"]["assignments"].append(
                        {
                            "unit_id": "cq-public",
                            "role_id": "competency-question",
                            "objective": "Review the public goals across the complete objective",
                            "material_ids": ["source", "public-cq"],
                            "dependencies": [],
                            "instructions": "Reuse public questions; preserve draft criteria",
                            "scope_id": "public-goals",
                        }
                    )
                native["final_response"] = json.dumps(result)
            path = root / "agent/events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            for event in events:
                item = event["params"]["item"]
                if item["tool"] == "read_handoff_material":
                    item["arguments"]["reference"] = json.dumps(item["arguments"]["reference"])
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            return native

        return invoke

    schema = workspace.schema + "_live_cp"
    try:
        flow = MultiUnitFlow(binding, workspace, platform, schema, factory)
        result = flow.advance()
        assert result["work"]["status"] == "handoff_ready", result
        plan = WorkPlan(binding.data, workspace).row()["content"]
        assert plan["units"]["cq-public"]["role_id"] == "competency-question"
        assert plan["units"]["cq-public"]["parent_id"] == "coordinator"
        assert ("modeler", "modeling", "propose") in actors.calls
        assert ("cq-public", "competency-question", "review") in actors.calls
        assert len(platform.effects) == 1
        prior = list(actors.calls)
        assert flow.advance()["work"]["status"] == "handoff_ready"
        assert prior == actors.calls and len(platform.effects) == 1
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.parametrize("defect", ["schema", "private", "confirmed", "duplicate"])
def test_invalid_goal_input_is_recoverable_before_run_directory_is_created(
    seed_task, tmp_path, defect
):
    task = json.loads(seed_task.read_text())
    materials = Path(task["materials"])
    path = materials / "public-cq.json"
    seed = json.loads(path.read_text())
    if defect == "schema":
        seed["schema_version"] = "unknown/v1"
    elif defect == "private":
        seed["visibility"] = "private"
    elif defect == "confirmed":
        seed["criteria_status"] = "confirmed"
    else:
        seed["questions"].append(seed["questions"][0])
    path.write_text(json.dumps(seed))
    manifest = json.loads((materials / "manifest.json").read_text())
    manifest["public-cq"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (materials / "manifest.json").write_text(json.dumps(manifest))
    root = tmp_path / "invalid-goal-run"
    with pytest.raises(FrameworkError, match="public_cq_seed_invalid") as failure:
        TaskBinding.prepare(seed_task, root)
    assert failure.value.detail["path"] == "public-cq.json"
    assert failure.value.detail["instruction"]
    assert not root.exists()


def test_scope_basis_feedback_names_actual_values_and_same_unit_can_correct(
    role_task_file, tmp_path, workspace, saver
):
    binding = TaskBinding.prepare(role_task_file, tmp_path / "basis-run")
    platform = RolePlatform()
    underlying = RoleActors(binding, workspace, platform).factory(binding)
    first = True

    def invoke(root, purpose, prompt, inputs):
        nonlocal first
        native = underlying(root, purpose, prompt, inputs)
        result = json.loads(native["final_response"])
        if first:
            result["basis"]["scope_ref"] = {
                "object_id": "new-plan",
                "revision": 1,
                "digest": "a" * 64,
            }
            first = False
        else:
            feedback = json.loads(prompt)["feedback"]
            assert feedback["field"] == "basis.scope_ref"
            assert feedback["expected"] is None
            assert feedback["received"]["object_id"] == "new-plan"
            assert feedback["instruction"]
            previous = json.loads(prompt)["previous_result_material_ref"]
            assert previous
            retained = TeamChannel(binding.data, workspace, flow.control, binding.actor).read(
                previous
            )
            original = json.loads(retained["text"])
            assert original["basis"]["scope_ref"]["object_id"] == "new-plan"
            assert original["artifact"]["schema_version"] == "scope-plan/v1"
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    rejected = flow.advance(saver)
    assert rejected["issue"]["code"] == "role_scope_basis_changed"
    assert rejected["issue"].get("field") == "basis.scope_ref"
    assert rejected["issue"]["expected"] is None
    assert rejected["rejected_result_material_ref"]
    corrected = flow.advance(saver)
    assert corrected["status"] == "waiting_children", corrected
    assert corrected["role_phase"] == "integrate"
    assert corrected["rejected_result_material_ref"] is None
    assert not platform.effects


def test_complete_scope_artifact_is_installed_before_waiting_for_children(
    role_task_file, tmp_path, workspace, saver
):
    binding = TaskBinding.prepare(role_task_file, tmp_path / "waiting-plan-run")
    platform = RolePlatform()
    underlying = RoleActors(binding, workspace, platform).factory(binding)

    def invoke(root, purpose, prompt, inputs):
        native = underlying(root, purpose, prompt, inputs)
        result = json.loads(native["final_response"])
        result["status"] = "waiting_children"
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    state = flow.advance(saver)
    assert state["status"] == "waiting_children"
    assert state["role_phase"] == "integrate", state
    plan = WorkPlan(binding.data, workspace).row()["content"]
    assert plan["scope_refs"][binding.actor]
    assert plan["units"]["modeler"]["work_phase"] == "propose"


@pytest.mark.parametrize("defect", ["wrong_role", "duplicate"])
def test_existing_cq_reuse_keeps_owner_and_unique_assignment_guards(
    role_task_file, tmp_path, workspace, saver, defect
):
    binding = TaskBinding.prepare(role_task_file, tmp_path / "cq-owner-run")
    platform = RolePlatform()
    underlying = RoleActors(binding, workspace, platform).factory(binding)

    def invoke(root, purpose, prompt, inputs):
        native = underlying(root, purpose, prompt, inputs)
        value = json.loads(native["final_response"])
        assignment = {
            "unit_id": "cq-public",
            "role_id": "modeling" if defect == "wrong_role" else "competency-question",
            "objective": "Public goal review",
            "material_ids": ["source"],
            "dependencies": [],
            "instructions": "Preserve the current owner",
            "scope_id": "public-goals",
        }
        value["artifact"]["assignments"].append(assignment)
        if defect == "duplicate":
            value["artifact"]["assignments"].append(assignment)
        native["final_response"] = json.dumps(value)
        return native

    state = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert state["status"] == "recoverable_issue"
    expected = "work_owner_forbidden" if defect == "wrong_role" else "work_unit_identity_conflict"
    assert state["issue"]["code"] == expected
    plan = WorkPlan(binding.data, workspace).row()["content"]
    assert plan["units"]["cq-public"]["role_id"] == "competency-question"
    assert not plan.get("scope_refs")
    assert not platform.effects


def test_source_revision_rejects_invalid_goal_before_copy_or_queue(seed_task, tmp_path, workspace):
    from ontoweave_modeling.revisions import SourceRevisions

    binding = TaskBinding.prepare(seed_task, tmp_path / "source-revision-run")
    materials = Path(json.loads(seed_task.read_text())["materials"])
    path = materials / "public-cq.json"
    value = json.loads(path.read_text())
    value["criteria_status"] = "confirmed"
    path.write_text(json.dumps(value))
    manifest = json.loads((materials / "manifest.json").read_text())
    manifest["public-cq"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (materials / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(FrameworkError, match="public_cq_seed_invalid"):
        SourceRevisions(binding, workspace).stage(
            {"change_id": "invalid-goals", "reason": "changed goals"}, materials
        )
    assert workspace.list_kind("source_change") == []
    assert not (binding.root / "source-revisions").exists()


def test_public_seed_answer_is_not_confirmation_authority(seed_task, tmp_path, workspace, saver):
    binding = TaskBinding.prepare(seed_task, tmp_path / "draft-authority-run")
    selected = binding.for_unit("cq-public")
    platform = RolePlatform()
    underlying = RoleActors(binding, workspace, platform).factory(selected)
    original = json.loads((binding.materials / "public-cq.json").read_text())["questions"][0]

    def invoke(root, purpose, prompt, inputs):
        native = underlying(root, purpose, prompt, inputs)
        value = json.loads(native["final_response"])
        question = value["artifact"]["questions"][0]
        question.update(
            cq_id=original["external_id"],
            question=original["question"],
            reference_answer="Self-authored answer cannot confirm a draft",
            answer_author="user",
            criteria_status="confirmed",
        )
        value["artifact"]["new_ids"] = [original["external_id"]]
        native["final_response"] = json.dumps(value)
        return native

    state = WorkUnitFlow(selected, workspace, platform, invoke).advance(saver)
    assert state["issue"]["code"] == "public_cq_confirmation_basis_required", state
    assert not WorkPlan(binding.data, workspace).row()["content"].get("public_cq_ref")


def test_public_goal_snapshot_keeps_confirmed_identity_and_detects_tampering(tmp_path):
    from test_custom_cq import snapshot

    from ontoweave_modeling.custom_cq import public_goal_questions

    value = snapshot(ready=True)
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(value))
    manifest = {"cq-goals": {"path": "snapshot.json", "material_type": "competency_goal"}}
    rows = public_goal_questions(tmp_path, manifest)
    assert list(rows) == ["project-q1"]
    assert rows["project-q1"]["content_revision"] == 2
    assert rows["project-q1"]["cq_definition"]["criteria_status"] == "confirmed"
    value["questions"][0]["question"] = "Changed without a new snapshot digest"
    path.write_text(json.dumps(value))
    with pytest.raises(FrameworkError, match="public_cq_seed_invalid"):
        public_goal_questions(tmp_path, manifest)


def test_late_public_cq_rechecks_unchanged_meaning_without_recreating_applied_change(
    role_task_file, tmp_path, workspace
):
    task = json.loads(role_task_file.read_text())
    task["unit_concurrency"] = 2
    role_task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(role_task_file, tmp_path / "late-cq-run")
    applied = threading.Event()

    class DelayedCQPlatform(RolePlatform):
        def call(self, action, payload=None):
            result = super().call(action, payload)
            if action == "apply":
                applied.set()
            return result

    platform = DelayedCQPlatform()
    actors = RoleActors(binding, workspace, platform)

    def factory(selected):
        underlying = actors.factory(selected)

        def invoke(root, purpose, prompt, inputs):
            if (
                selected.role == "competency-question"
                and json.loads(prompt).get("phase") == "produce"
            ):
                assert applied.wait(30), "Public CQ must not block the first safe application"
            return underlying(root, purpose, prompt, inputs)

        return invoke

    schema = workspace.schema + "_late_cq_cp"
    try:
        result = MultiUnitFlow(binding, workspace, platform, schema, factory).advance()
        assert result["work"]["status"] == "handoff_ready", result
        assert actors.calls.count(("modeler", "modeling", "propose")) >= 2
        assert len(platform.effects) == 1
        work = workspace.get(binding.for_unit("modeler").identity + ":work")["content"]
        retained = workspace.read_reference(work["role_result_ref"])
        assert retained["status"] == "no_change"
        assert retained["basis"]["model_revisions"] == {"ontology": 1}
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def test_nested_scope_still_refreshes_public_cq_without_rebinding_root_scope(
    role_task_file, tmp_path, workspace, saver
):
    from ontoweave_modeling.role_work import _install_scope

    binding = TaskBinding.prepare(role_task_file, tmp_path / "nested-cq-refresh-run")
    platform = RolePlatform()
    actors = RoleActors(binding, workspace, platform)
    root = WorkUnitFlow(binding, workspace, platform, actors.factory(binding))
    assert root.advance(saver)["role_phase"] == "integrate"
    manager = WorkPlan(binding.data, workspace)
    manager.delegate("middle", "Coordinate one bounded source scope", role_id="coordinator")
    before = dict(manager.row()["content"]["units"]["cq-public"])
    child = manager.binding(binding).for_unit("middle")
    flow = WorkUnitFlow(child, workspace, platform, None)
    artifact = {
        "schema_version": "scope-plan/v1",
        "scope": "New nested boundary within the original objective",
        "assignments": [],
        "shared_definitions": [],
        "unassigned": ["Nested expression remains with its original responsibility"],
        "confirmation_points": [],
        "integration_obligations": [],
    }
    reference = workspace.put_reference("nested-scope", "role_artifact", artifact, 0)
    material = flow.team.publish("nested-scope", text=json.dumps(artifact))
    _install_scope(flow, artifact, reference, material)
    after = manager.row()["content"]["units"]["cq-public"]
    assert after["generation"] == before["generation"] + 1
    assert after["scope_ref"] == before["scope_ref"]
    assert after["work_phase"] == "produce"
