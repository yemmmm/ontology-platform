"""Output reduction must retain source meaning, identity and old frozen contracts."""

import json
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.execution import CodexInvocation


@pytest.fixture
def professional_binding(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["team_contract"] = "role-team/v1"
    task["unit_concurrency"] = 1
    task_file.write_text(json.dumps(task))
    profile_path = task_file.parent / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text())
    for role in ("coordinator", "competency-question"):
        profile["roles"][role] = dict(profile["roles"]["modeling"])
    profile_path.write_text(yaml.safe_dump(profile))
    return TaskBinding.prepare(task_file, tmp_path / "professional-run")


def test_intake_and_check_keep_business_method_without_candidate_grammar(professional_binding):
    binding = professional_binding.for_unit("modeler")
    invoke = CodexInvocation(binding, None)
    intake = invoke._instructions_for("source_intake", '{"phase":"source_intake"}')
    propose = invoke._instructions_for("slice_modeling", '{"phase":"propose"}')
    check = invoke._instructions_for("self_check", "{}")
    for text in (intake, check):
        assert "Technical representation contracts" not in text
        assert len(text) < len(propose) / 2
        for word in ("conditions", "exceptions", "negation", "unknowns", "source"):
            assert word in text
    assert "source-intake/v1" in intake
    assert "not proposing" in check
    assert "Technical representation contracts" in propose


def test_old_frozen_role_package_and_explicit_override_keep_original_instructions(
    professional_binding,
):
    binding = professional_binding.for_unit("modeler")
    package = binding.data["role_packages"]["modeling"]
    package.pop("phase_instructions")
    invoke = CodexInvocation(binding, None)
    assert invoke._instructions_for("source_intake", "{}") == binding.data["instructions"]
    invoke = CodexInvocation(binding, None, instructions="Explicit frozen evaluation method")
    assert invoke._instructions_for("self_check", "{}") == "Explicit frozen evaluation method"


def test_proposal_guidance_exposes_canonical_fields_without_losing_aggregate_feedback(
    professional_binding, workspace, tmp_path
):
    import asyncio

    from test_role_candidates import _candidate

    from ontoweave_modeling.material_tools import material_server
    from ontoweave_modeling.role_artifacts import submit_role_artifact
    from ontoweave_modeling.role_team import result_schema

    binding = professional_binding.for_unit("modeler")
    context = {"execution_id": "schema-probe", "phase": "propose", "basis": {}}
    config = tmp_path / "team.json"
    config.write_text(
        json.dumps(
            {
                "task": binding.data,
                "connection": workspace.connection,
                "schema": workspace.schema,
                "actor": binding.actor,
                "role_submission": context,
            }
        )
    )
    server = material_server(binding.materials, team_config=config)
    tool = next(
        tool for tool in asyncio.run(server.list_tools()) if tool.name == "submit_role_artifact"
    )
    shown = tool.inputSchema["properties"]["artifact"]["anyOf"][0]
    expected = result_schema(binding, "propose", guidance=True)["properties"]["artifact"]["anyOf"][
        0
    ]
    assert shown == expected
    candidate = shown["properties"]["candidate"]
    assert candidate["properties"]["schema_version"]["const"] == "r3-0-009-unified-graph/v2"
    assert set(candidate["required"]) == set(_candidate())
    assert "business_meaning" in candidate["properties"]["items"]["items"]["required"]
    body = {
        "candidate": _candidate(item_count=2),
        "changes": None,
        "ontology_targets": {},
        "review_units": [],
        "shared_conflicts": [],
        "public_cq_disposition": "Pending public goals",
    }
    for item in body["candidate"]["items"]:
        item.pop("business_meaning")
    # The advertised schema is complete; execution still returns all canonical
    # issues instead of letting generic argument validation hide them.
    with pytest.raises(Exception, match="model_candidate_invalid") as error:
        asyncio.run(server.call_tool("submit_role_artifact", {"artifact": body}))
    assert "/items/0" in str(error.value) and "/items/1" in str(error.value)
    body["candidate"] = _candidate()
    assert submit_role_artifact(binding, workspace, context, body)["status"] == "staged"


def test_submitted_intake_is_bound_to_author_execution_and_actual_basis(
    professional_binding, workspace
):
    from ontoweave_modeling.role_artifacts import read_submitted_artifact, submit_role_artifact

    binding = professional_binding.for_unit("modeler")
    context = {
        "execution_id": "modeler--role-00000",
        "phase": "source_intake",
        "basis": {"source_manifest_digest": binding.data["source_manifest_digest"]},
    }
    artifact = {
        "schema_version": "source-intake/v1",
        "propositions": ["Preserve the source condition AND exception"],
        "unknowns": ["An explicit unknown"],
    }
    receipt = submit_role_artifact(binding, workspace, context, artifact)
    assert "artifact" not in receipt
    assert len(json.dumps(receipt)) < 1000
    assert read_submitted_artifact(binding, workspace, context, receipt["artifact_ref"]) == artifact
    next_context = {**context, "execution_id": "next", "basis": {"new_cq": "owner reassessed"}}
    reused = submit_role_artifact(
        binding, workspace, next_context, artifact_ref=receipt["artifact_ref"]
    )
    assert reused["artifact_ref"] == receipt["artifact_ref"]
    assert (
        read_submitted_artifact(binding, workspace, next_context, reused["artifact_ref"])
        == artifact
    )
    with pytest.raises(FrameworkError):
        submit_role_artifact(
            professional_binding, workspace, context, artifact_ref=receipt["artifact_ref"]
        )
    for field, value in [("execution_id", "other"), ("phase", "propose"), ("basis", {})]:
        changed = {**context, field: value}
        with pytest.raises(FrameworkError):
            read_submitted_artifact(binding, workspace, changed, receipt["artifact_ref"])
    with pytest.raises(FrameworkError):
        read_submitted_artifact(professional_binding, workspace, context, receipt["artifact_ref"])
    broken = deepcopy(artifact)
    broken.pop("propositions")
    with pytest.raises(FrameworkError) as error:
        submit_role_artifact(binding, workspace, context, broken)
    assert error.value.detail["path"] == []
    assert "propositions" in str(error.value.detail)


def test_professional_flow_accepts_tool_body_and_small_final_envelope(
    professional_binding, workspace
):
    from test_role_team_flow import RoleActors, RolePlatform

    from ontoweave_modeling.multi_unit import MultiUnitFlow
    from ontoweave_modeling.role_artifacts import submit_role_artifact

    platform = RolePlatform()
    actors = RoleActors(professional_binding, workspace, platform)
    staged = []

    def factory(binding):
        original = actors.factory(binding)

        def invoke(root, purpose, prompt, inputs):
            result = original(root, purpose, prompt, inputs)
            if binding.role == "modeling" and purpose != "self_check":
                request = json.loads(prompt)
                if request["phase"] == "propose":
                    advertised = request["result_schema"]["properties"]["artifact"]["anyOf"][0]
                    assert "schema_version" in advertised["properties"]["candidate"]["required"]
                response = json.loads(result["final_response"])
                receipt = submit_role_artifact(
                    binding,
                    workspace,
                    {
                        "execution_id": root.name,
                        "phase": request["phase"],
                        "basis": request["basis"],
                    },
                    response["artifact"],
                )
                response.update(artifact=None, artifact_ref=receipt["artifact_ref"])
                result["final_response"] = json.dumps(response)
                staged.append(request["phase"])
            return result

        return invoke

    schema = workspace.schema + "_output_cp"
    try:
        result = MultiUnitFlow(professional_binding, workspace, platform, schema, factory).advance()
        assert staged[0] == "source_intake"
        assert set(staged[1:]) == {"propose"}
        assert result["work"]["status"] == "handoff_ready", result
        assert len(platform.effects) == 1
    finally:
        from psycopg import sql

        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.parametrize("tool_package", [False, True])
def test_only_legacy_package_can_reuse_retained_body_without_submission_receipt(
    professional_binding, workspace, saver, tool_package
):
    from test_role_team_flow import RoleActors, RolePlatform

    from ontoweave_modeling.flow import WorkUnitFlow

    binding = professional_binding.for_unit("modeler")
    if not tool_package:
        binding.data["role_packages"]["modeling"].pop("artifact_submission")
    platform = RolePlatform()
    base = RoleActors(professional_binding, workspace, platform).factory(binding)
    calls = []

    def invoke(root, purpose, prompt_text, inputs):
        prompt = json.loads(prompt_text)
        native = base(root, purpose, prompt_text, inputs)
        result = json.loads(native["final_response"])
        calls.append(prompt)
        if len(calls) == 1:
            result["source_refs"] = []
        else:
            assert prompt["retained_artifact_ref"]
            result.update(artifact=None, artifact_ref=prompt["retained_artifact_ref"])
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    assert flow.advance(saver)["status"] == "recoverable_issue"
    second = flow.advance(saver)
    if tool_package:
        assert second["status"] == "recoverable_issue", second
        assert second["issue"]["code"] == "role_artifact_reuse_forbidden"
    else:
        assert second["status"] == "proposal_ready", second


def test_cq_invalid_artifact_reference_feedback_offers_inline_correction(
    professional_binding, workspace, saver
):
    from test_role_team_flow import RoleActors, RolePlatform

    from ontoweave_modeling.flow import WorkUnitFlow

    binding = professional_binding.for_unit("cq-public")
    platform = RolePlatform()
    base = RoleActors(professional_binding, workspace, platform).factory(binding)

    def invoke(root, purpose, prompt, inputs):
        native = base(root, purpose, prompt, inputs)
        result = json.loads(native["final_response"])
        result.update(
            artifact=None,
            artifact_ref={"object_id": "published-cq-material", "revision": 1, "digest": "a" * 64},
        )
        native["final_response"] = json.dumps(result)
        return native

    result = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert result["issue"]["code"] == "role_artifact_reuse_forbidden"
    instruction = result["issue"]["instruction"]
    assert "inline" in instruction
    assert "submit_role_artifact" not in instruction
    assert "retained_artifact_ref" in instruction


def test_normal_new_cq_can_reuse_own_exact_source_reads_without_reusing_old_body(
    professional_binding, workspace
):
    from ontoweave_modeling.role_work import _continued_reads

    binding = professional_binding.for_unit("modeler")
    basis = {"source_manifest_digest": binding.data["source_manifest_digest"], "cq_ref": None}
    path = binding.root / "executions/previous/agent/events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("")
    reference = workspace.put_reference(
        binding.identity + ":execution:previous",
        "execution",
        {
            "intent": {"execution_id": "previous"},
            "prompt": json.dumps({"basis": basis}),
            "result": {"status": "completed"},
        },
        0,
    )
    flow = SimpleNamespace(binding=binding, repository=workspace)
    state = {"execution_ref": reference}
    assert _continued_reads(flow, state, {**basis, "cq_ref": {"revision": 2}}) == [reference]
    assert _continued_reads(flow, state, {**basis, "source_manifest_digest": "changed"}) == []
    path.unlink()
    assert _continued_reads(flow, state, basis) == []
    path.write_text("{broken event")
    assert _continued_reads(flow, state, basis) == []
    path.write_text("")
    assert _continued_reads(flow, {"execution_ref": {**reference, "digest": "bad"}}, basis) == []
    assert (
        _continued_reads(
            SimpleNamespace(binding=professional_binding, repository=workspace), state, basis
        )
        == []
    )


def test_proposal_handoff_index_keeps_full_body_available_without_copying_it(
    professional_binding, workspace
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.role_work import _publish
    from ontoweave_modeling.team import TeamChannel

    binding = professional_binding.for_unit("modeler")
    control = TaskControl(workspace)
    author = TeamChannel(binding.data, workspace, control, binding.actor)
    body = {
        "candidate": {"items": [{"value": "Complete condition and exception. " * 1000}]},
        "changes": {"changes": [{"change_id": "create-one"}]},
        "shared_conflicts": ["A genuine unresolved definition conflict"],
    }
    envelope = {"phase": "propose", "artifact_ref": {"object_id": "body"}}
    result_ref = {"object_id": "result", "revision": 1, "digest": "a" * 64}
    index_ref = _publish(SimpleNamespace(binding=binding, team=author), result_ref, envelope, body)
    reader = TeamChannel(professional_binding.data, workspace, control, "coordinator")
    index = json.loads(reader.read(index_ref, limit=100000)["text"])
    assert "artifact" not in index
    assert index["change_ids"] == ["create-one"]
    assert index["shared_conflicts"] == body["shared_conflicts"]
    assert len(json.dumps(index)) < 2000
    full = reader.read(index["artifact_material_ref"], limit=100000)
    assert json.loads(full["text"])["artifact"] == body


def test_glm_tool_loop_does_not_force_placeholder_json_before_reading(
    professional_binding, tmp_path, monkeypatch
):
    from ontoweave_modeling import codex_agent

    binding = professional_binding.for_unit("modeler")
    (binding.root / "private-runtime.json").write_text(
        json.dumps({"connection": {"host": "localhost"}, "workspace_schema": "test"})
    )
    captured = []

    class Agent:
        def __init__(self, root, model, **kwargs):
            captured.append(kwargs)

        def start(self):
            pass

        def run_turn(self, prompt, *, output_schema=None):
            # The real GLM probe returned only "starting read" with outputSchema;
            # keep structural checks in the staging tool and small-envelope decoder.
            assert output_schema is None
            return {"status": "completed"}

        def close(self):
            pass

    class Bridge:
        def call(self, method, payload):
            assert method == "read_config"
            return {"config_ref": None}

        @contextmanager
        def provider(self, *args):
            yield "http://127.0.0.1:9/v1"

    monkeypatch.setattr(codex_agent, "CodexAgent", Agent)
    root = tmp_path / "execution"
    root.mkdir()
    prompt = json.dumps({"phase": "source_intake", "basis": {}, "result_schema": {}})
    CodexInvocation(binding, Bridge())(root, "source_intake", prompt, [])
    assert "Technical representation contracts" not in captured[0]["instructions"]
    assert "submit_role_artifact" in captured[0]["allowed_tools"]
    context = json.loads((root / "team-private.json").read_text())["role_submission"]
    assert context == {"phase": "source_intake", "basis": {}, "execution_id": root.name}


def test_scope_shared_declarations_accept_real_root_actor_and_reject_unknown(
    professional_binding, workspace
):
    from test_role_team_flow import RolePlatform

    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.multi_unit import MultiUnitFlow
    from ontoweave_modeling.role_work import _install_scope
    from ontoweave_modeling.team import TeamChannel
    from ontoweave_modeling.work_plan import WorkPlan

    binding = professional_binding
    control = TaskControl(workspace)
    team = TeamChannel(binding.data, workspace, control, binding.actor)
    MultiUnitFlow(binding, workspace, RolePlatform(), workspace.schema + "_unused").initialize()
    artifact = {
        "schema_version": "scope-plan/v1",
        "scope": "Full original source",
        "assignments": [
            {
                "unit_id": unit,
                "role_id": role,
                "objective": "Original source responsibility",
                "material_ids": ["source"],
                "dependencies": [],
                "instructions": "Preserve actual author",
            }
            for unit, role in [("modeler", "modeling"), ("cq-public", "competency-question")]
        ],
        "shared_definitions": [
            {
                "definition_id": "scope-boundary",
                "maintainer_unit_id": "coordinator",
                "user_unit_ids": ["coordinator", "modeler", "cq-public"],
                "decision": "Coordinator maintains scope; each semantic contribution keeps its author",
            }
        ],
        "unassigned": [],
        "confirmation_points": [],
        "integration_obligations": [],
    }
    reference = workspace.put_reference("scope-body", "role_artifact", artifact, 0)
    material = team.publish("scope", text=json.dumps(artifact))
    flow = SimpleNamespace(binding=binding, repository=workspace, control=control, team=team)
    _install_scope(flow, artifact, reference, material)
    assert (
        WorkPlan(binding.data, workspace).row()["content"]["scope_refs"]["coordinator"] == reference
    )
    bad = deepcopy(artifact)
    bad["shared_definitions"][0]["maintainer_unit_id"] = "absent"
    with pytest.raises(FrameworkError, match="shared_maintainer_missing"):
        _install_scope(flow, bad, reference, material)


def test_cq_same_body_new_observation_delivers_distinct_exact_materials_once(
    professional_binding, workspace
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.role_work import _refresh_cq
    from ontoweave_modeling.team import TeamChannel
    from ontoweave_modeling.work_plan import WorkPlan

    binding = professional_binding.for_unit("cq-public")
    control = TaskControl(workspace)
    team = TeamChannel(binding.data, workspace, control, binding.actor)
    artifact = {"questions": [], "unknowns": [], "coverage_gaps": []}
    reference = workspace.put_reference("cq-body", "role_artifact", artifact, 0)
    result_ref = workspace.put_reference(
        "cq-result",
        "role_work_result",
        {"basis": {"model_revisions": {}, "source_manifest_digest": "source"}},
        0,
    )
    work_id = binding.identity + ":work"
    workspace.put_reference(work_id, "work", {"role_result_ref": result_ref}, 0)
    plan = WorkPlan(binding.data, workspace)

    def ready(data):
        data["units"]["modeler"]["work_phase"] = "propose"
        data["public_cq_ref"] = reference

    plan.change(ready)
    flow = SimpleNamespace(
        binding=binding, repository=workspace, control=control, team=team, work_id=work_id
    )
    first = team.publish("observation-one", text="First exact observation")
    second = team.publish("observation-two", text="Second exact observation")
    _refresh_cq(flow, reference, first, artifact, "review")
    _refresh_cq(flow, reference, second, artifact, "review")
    _refresh_cq(flow, reference, second, artifact, "review")
    delivered = [
        m for m in control.view()["messages"] if m["metadata"].get("phase") == "self_check"
    ]
    assert [m["metadata"]["material_refs"] for m in delivered] == [[first], [second]]


def test_bound_public_cq_is_readable_before_a_modeler_notification_and_other_materials_stay_private(
    professional_binding, workspace
):
    from ontoweave_modeling.control import TaskControl
    from ontoweave_modeling.team import TeamChannel
    from ontoweave_modeling.work_plan import WorkPlan

    control = TaskControl(workspace)
    cq = TeamChannel(professional_binding.data, workspace, control, "cq-public")
    public = cq.publish(
        "public-goals", text="Attributed public goals, not confirmed business facts"
    )
    other = cq.publish("other-note", text="Not a bound public input")
    WorkPlan(professional_binding.data, workspace).change(
        lambda plan: plan.update(public_cq_material_ref=public)
    )
    modeler = TeamChannel(professional_binding.data, workspace, control, "modeler")
    assert modeler.messages() == []
    assert modeler.read(public)["reference"] == public
    with pytest.raises(FrameworkError, match="handoff_material_forbidden"):
        modeler.read(other)
    with pytest.raises(FrameworkError, match="(team_actor|handoff_material)_forbidden"):
        TeamChannel(professional_binding.data, workspace, control, "stranger").read(public)


@pytest.mark.parametrize("mount_validator", [False, True])
def test_candidate_validator_is_available_in_real_isolated_tool_process(
    professional_binding, workspace, tmp_path, monkeypatch, mount_validator
):
    import socket

    from openai_codex.generated.v2_all import McpServerToolCallResponse

    from ontoweave_modeling import codex_agent
    from ontoweave_modeling.codex_agent import CodexAgent

    if not mount_validator:
        original_namespace = codex_agent.namespace_command

        def without_validator(*args, read_only_mounts, **kwargs):
            mounts = tuple(
                item
                for item in read_only_mounts
                if not item[1].startswith("/agent/runtime/modeling_team/")
            )
            return original_namespace(*args, read_only_mounts=mounts, **kwargs)

        monkeypatch.setattr(codex_agent, "namespace_command", without_validator)

    binding = professional_binding.for_unit("modeler")
    connection = dict(workspace.connection)
    connection["hostaddr"] = socket.gethostbyname(connection["host"])
    config = tmp_path / "team.json"
    config.write_text(
        json.dumps(
            {
                "task": binding.data,
                "connection": connection,
                "schema": workspace.schema,
                "actor": binding.actor,
                "role_submission": {"execution_id": "probe", "phase": "propose", "basis": {}},
            }
        )
    )
    agent = CodexAgent(
        tmp_path / "isolated-validator",
        binding.model("modeling"),
        provider_base_url="http://127.0.0.1:9/v1",
        materials=binding.materials,
        team_config=config,
        instructions="Non-inference canonical validator boundary only",
        allowed_tools=("submit_role_artifact",),
        on_event=lambda *_: None,
    )
    try:
        agent.start()
        result = agent.client.request(
            "mcpServer/tool/call",
            {
                "threadId": agent.thread_id,
                "server": "workspace",
                "tool": "submit_role_artifact",
                "arguments": {
                    "artifact": {
                        "candidate": {"items": [{"item_id": "incomplete", "item_kind": "entity"}]},
                        "changes": None,
                        "review_units": [],
                        "ontology_targets": {},
                        "shared_conflicts": [],
                        "public_cq_disposition": "Public goals remain draft",
                    }
                },
            },
            response_model=McpServerToolCallResponse,
        )
        assert result.is_error
        expected = (
            "model_candidate_invalid" if mount_validator else "candidate_validator_unavailable"
        )
        assert expected in json.dumps(result.content)
        assert '"method": "turn/started"' not in (agent.root / "events.jsonl").read_text()
    finally:
        agent.close()
