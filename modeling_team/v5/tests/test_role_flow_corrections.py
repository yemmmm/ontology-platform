"""Actual failure shapes across role delivery, correction and production read-back."""

import json
from copy import deepcopy

import pytest
from psycopg import sql
from test_role_team_flow import RoleActors, RolePlatform
from test_role_team_flow import role_binding as role_binding  # noqa: PLC0414

from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.role_work import _correction_invocation
from ontoweave_modeling.work_plan import WorkPlan


def without_source_reads(root):
    path = root / "agent/events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text(
        "".join(
            json.dumps(event) + "\n"
            for event in events
            if event["params"]["item"].get("tool") != "read_material"
        )
    )


def test_technical_invocation_retains_original_native_context_without_mutating_factory(
    role_binding, workspace
):
    invocation = CodexInvocation(role_binding, RolePlatform(), instructions="Bound role contract")
    flow = WorkUnitFlow(role_binding, workspace, invocation.bridge, invocation)
    root = role_binding.root / "executions/retained-turn"
    (root / "agent").mkdir(parents=True)
    (root / "agent/thread-binding.json").write_text(json.dumps({"thread_id": "original-role"}))
    ref = workspace.put_reference(
        role_binding.identity + ":execution:retained-turn",
        "execution",
        {
            "intent": {"execution_id": "retained-turn"},
            "result": {"status": "completed", "thread_id": "original-role"},
        },
        0,
    )
    continued = _correction_invocation(flow, [ref])
    assert continued is not invocation
    assert continued.resume_from == root / "agent"
    assert continued.instructions == invocation.instructions
    assert invocation.resume_from is None
    assert _correction_invocation(flow, []) is invocation


def test_json_syntax_feedback_reaches_original_role_without_losing_location(
    role_binding, workspace, saver
):
    platform = RolePlatform()
    base = RoleActors(role_binding, workspace, platform).factory(role_binding)
    prompts = []
    malformed = '{"schema_version":"role-work-result/v1",\n "artifact": {,}}'

    def invoke(root, purpose, text, inputs):
        prompt = json.loads(text)
        prompts.append(prompt)
        native = base(root, purpose, text, inputs)
        if len(prompts) == 1:
            native["final_response"] = malformed
        else:
            assert prompt["feedback"]["json_error"]["line"] == 2
            assert prompt["feedback"]["json_error"]["column"] == 15
        return native

    flow = WorkUnitFlow(role_binding, workspace, platform, invoke)
    rejected = flow.advance(saver)
    assert rejected["status"] == "recoverable_issue"
    assert rejected["issue"]["json_error"]["message"] == (
        "Expecting property name enclosed in double quotes"
    )
    original = workspace.read_reference(rejected["execution_ref"])["result"]["final_response"]
    assert original == malformed
    assert flow.advance(saver)["status"] == "waiting_children"
    assert len(prompts) == 2
    assert not platform.effects


def test_partial_source_read_cannot_be_upgraded_by_technical_retry(role_binding, workspace, saver):
    platform = RolePlatform()
    base = RoleActors(role_binding, workspace, platform).factory(role_binding)
    calls = []

    def invoke(root, purpose, text, inputs):
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        calls.append(root)
        if len(calls) == 1:
            result["source_refs"] = []
            path = root / "agent/events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            for event in events:
                item = event["params"]["item"]
                if item.get("tool") == "read_material":
                    item["result"]["structuredContent"]["total_characters"] = 100
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
        else:
            without_source_reads(root)
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(role_binding, workspace, platform, invoke)
    assert flow.advance(saver)["status"] == "recoverable_issue"
    result = flow.advance(saver)
    assert result["status"] == "recoverable_issue"
    assert result["issue"]["code"] == "source_read_missing"
    assert not platform.effects


@pytest.mark.parametrize("first_failure", ["missing_sources", "progress_only"])
@pytest.mark.parametrize("technical_notice", [False, True])
def test_technical_retry_reuses_actual_read_proof_and_owned_artifact(
    role_binding, workspace, saver, first_failure, technical_notice
):
    platform = RolePlatform()
    actors = RoleActors(role_binding, workspace, platform)
    base = actors.factory(role_binding)
    turns = []

    def invoke(root, purpose, text, inputs):
        prompt = json.loads(text)
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        turns.append(prompt)
        if len(turns) == 1:
            if first_failure == "missing_sources":
                result["source_refs"] = []
            else:
                native["final_response"] = "Sources analysed. I will now deliver the full result."
                return native
        else:
            assert prompt["reusable_read_execution_refs"]
            without_source_reads(root)
            if first_failure == "missing_sources":
                assert prompt["retained_artifact_ref"]
                result.update(artifact=None, artifact_ref=prompt["retained_artifact_ref"])
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(role_binding, workspace, platform, invoke)
    first = flow.advance(saver)
    assert first["status"] == "recoverable_issue", first
    original = workspace.read_reference(first["execution_ref"])["result"]["final_response"]
    if technical_notice:
        flow.human.submit(
            "Technical envelope correction only; preserve business content.",
            "technical-only",
            author="host-technical",
        )
    second = flow.advance(saver)
    assert second["status"] == "waiting_children", second
    assert len(turns) == 2
    assert workspace.read_reference(first["execution_ref"])["result"]["final_response"] == original
    assert not platform.effects


@pytest.mark.parametrize("changed", ["model", "reference", "human", "technical_business"])
def test_correction_cannot_reuse_stale_or_other_artifact(role_binding, workspace, saver, changed):
    platform = RolePlatform()
    base = RoleActors(role_binding, workspace, platform).factory(role_binding)
    calls = []

    def invoke(root, purpose, text, inputs):
        prompt = json.loads(text)
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        calls.append(prompt)
        if len(calls) == 1:
            result["source_refs"] = []
        else:
            reference = deepcopy(first["retained_artifact_ref"])
            if changed == "reference":
                reference["digest"] = "wrong-digest"
            result.update(artifact=None, artifact_ref=reference)
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(role_binding, workspace, platform, invoke)
    first = flow.advance(saver)
    assert first["status"] == "recoverable_issue"
    if changed == "model":
        platform.call("apply", {"operation_id": "external-revision"})
    if changed == "human":
        flow.control.enqueue(
            "new-business-answer",
            "input",
            "The approved condition includes an additional exception.",
            metadata={
                "source": "user",
                "author": "business-owner",
                "run_id": role_binding.data["run_id"],
            },
        )
    if changed == "technical_business":
        request = flow.human.ask(
            "model",
            [
                {
                    "question": "Which exception applies?",
                    "reason": "Source needs clarification",
                    "impact": "Candidate condition",
                }
            ],
            first["binding_ref"],
            first["execution_ref"],
        )[0]
        flow.human.submit(
            "The approved condition includes an additional exception.",
            "bound-business-answer",
            request_id=request,
            author="host-technical",
        )
    result = flow.advance(saver)
    assert result["status"] == "recoverable_issue", result
    assert result["issue"]["code"] == "role_artifact_reuse_forbidden"
    if changed in {"model", "human", "technical_business"}:
        # New business/model basis invalidates the body, not this same actor's
        # real reads of the unchanged original source version.
        assert calls[-1]["reusable_read_execution_refs"]
        assert calls[-1]["retained_artifact_ref"] is None


@pytest.mark.parametrize("semantic_change", [False, True])
def test_cq_evidence_refresh_does_not_reenter_modeling_but_real_unknown_change_does(
    role_binding, workspace, semantic_change
):
    platform = RolePlatform()
    actors = RoleActors(role_binding, workspace, platform)

    # Start with the same public business goals already available, as in the live
    # run before application. An outstanding *initial* CQ change is not proof-only.
    source = role_binding.data["source_manifest"]["source"]
    cq = {
        "schema_version": "public-cq-set/v1",
        "questions": [
            {
                "cq_id": "public-one",
                "question": "What is the approved condition?",
                "coverage_kind": "panorama",
                "scope_ids": ["full-objective"],
                "source_refs": [{"material_id": "source", "sha256": source["sha256"]}],
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
    seed = workspace.put_reference("existing-public-goals", "role_artifact", cq, 0)
    WorkPlan(role_binding.data, workspace).change(lambda plan: plan.update(public_cq_ref=seed))

    def factory(selected):
        base = actors.factory(selected)

        def invoke(root, purpose, text, inputs):
            native = base(root, purpose, text, inputs)
            if purpose != "self_check":
                result = json.loads(native["final_response"])
                if selected.role == "competency-question" and json.loads(text)["phase"] == "review":
                    result["artifact"]["model_support"] = [
                        {
                            "cq_id": "public-one",
                            "status": "supported",
                            "evidence": ["Actual governed condition body"],
                        }
                    ]
                    if semantic_change:
                        result["artifact"]["unknowns"].append(
                            "A new source qualification needs reassessment"
                        )
                if selected.role == "modeling" and result["status"] == "no_change":
                    result["artifact"]["candidate"] = None
                    result["artifact"]["changes"] = None
                    result["artifact"]["review_units"] = [selected.actor]
                native["final_response"] = json.dumps(result)
            return native

        return invoke

    schema = workspace.schema + "_proof_refresh_cp"
    try:
        result = MultiUnitFlow(role_binding, workspace, platform, schema, factory).advance()
        assert result["work"]["status"] == "handoff_ready", result
        assert actors.calls.count(("modeler", "modeling", "propose")) == (
            2 if semantic_change else 1
        )
        assert ("modeler", "modeling", "self_check") in actors.calls
        assert ("coordinator", "coordinator", "self_check") in actors.calls
        assert len(platform.effects) == 1
        assert len(workspace.list_kind("role_application")) == 1
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )
