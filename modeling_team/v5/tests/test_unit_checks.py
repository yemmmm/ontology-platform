import json
from contextlib import contextmanager

import pytest
from test_framework_flow import Actor, Platform

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.semantic_workspace import SemanticWorkspace
from ontoweave_modeling.team import TeamChannel
from ontoweave_modeling.unit_checks import check_unit
from ontoweave_modeling.work_plan import WorkPlan


def proposed_child(binding, workspace, saver):
    binding.data["work_units"] = [{"unit_id": "local", "objective": "Own this source meaning."}]
    WorkPlan(binding.data, workspace).row()
    selected = binding.for_unit("local")
    platform = Platform()
    original_call = platform.call
    platform.call = lambda action, payload=None: original_call(action, payload)
    actor = Actor(selected, platform)
    assert (
        WorkUnitFlow(selected, workspace, platform, actor).advance(saver)["status"]
        == "proposal_ready"
    )
    platform.call("apply", {"operation_id": "actual-root-write"})
    return selected, platform


def test_original_unit_check_receives_existing_workspace_navigation(binding, workspace, saver):
    binding.data["semantic_workspace"] = True
    selected, platform = proposed_child(binding, workspace, saver)
    space = SemanticWorkspace(workspace, selected.data, selected.actor)
    space.observe_models({"ontology": 0})
    space.write(
        "old-local-coverage",
        "coverage",
        "Old coverage",
        "Known missing expression",
        states={"expression": "partial"},
        unit_id="root",
    )
    actor = Actor(selected, platform)

    def inspect(*args):
        context = json.loads(args[2])["workspace_context"]
        row = context["local"]["records"][0]
        assert row["record_id"] == "old-local-coverage"
        assert row["states"]["expression"] == "partial"
        assert row["freshness"]["state"] == "needs_review"
        return actor(*args)

    check_unit(binding, workspace, platform, "local", invoke=inspect)
    assert space.read("old-local-coverage")["states"]["expression"] == "partial"


@pytest.mark.parametrize("parent_closed", [False, True])
def test_local_actual_read_back_reuses_proof_until_model_changes(
    binding, workspace, saver, parent_closed
):
    selected, platform = proposed_child(binding, workspace, saver)
    if parent_closed:
        workspace.put_reference(
            binding.identity + ":work", "work_unit", {"status": "handoff_ready"}, 0
        )
    actor = Actor(selected, platform)
    original = check_unit(binding, workspace, platform, "local", invoke=actor)
    assert original["result"]["status"] == "ready"
    assert original["basis"]["model_revisions"] == {"ontology": 1}
    parent = TeamChannel(binding.data, workspace, TaskControl(workspace))
    check_ref = workspace.get(selected.identity + ":work")["content"]["check_material_ref"]
    assert json.loads(parent.read(check_ref)["text"])["basis"] == original["basis"]
    reads = json.loads(parent.read(original["governed_read_material_ref"])["text"])
    assert reads[0]["data"]["scope"]["ontologies"][0]["model_revision"] == 1
    message_count = len(parent.messages())
    assert check_unit(binding, workspace, platform, "local", invoke=actor) == original
    assert len(parent.messages()) == message_count
    assert actor.calls == ["self_check"]
    assert workspace.get(selected.identity + ":work")["content"]["status"] == "proposal_ready"
    platform.call("apply", {"operation_id": "second-root-write"})
    updated = check_unit(binding, workspace, platform, "local", invoke=actor)
    assert updated["basis"]["model_revisions"] == {"ontology": 2}
    assert actor.calls == ["self_check", "self_check"]


def test_local_revision_reopens_original_unit_and_parent_without_writes(binding, workspace, saver):
    selected, platform = proposed_child(binding, workspace, saver)
    actor = Actor(selected, platform)

    def revise(*args):
        native = actor(*args)
        result = json.loads(native["final_response"])
        result.update(
            status="revise", issues=["The applied expression misses an approved condition."]
        )
        native["final_response"] = json.dumps(result)
        return native

    proof = check_unit(binding, workspace, platform, "local", invoke=revise)
    assert proof["result"]["status"] == "revise"
    plan = WorkPlan(binding.data, workspace).row()["content"]
    assert plan["root_generation"] == 1 and plan["units"]["local"]["generation"] == 1
    assert len(platform.effects) == 1
    assert workspace.get(selected.identity + ":work")["content"]["local_self_check_ref"]


def test_unknown_unit_is_not_dispatched(binding, workspace):
    with pytest.raises(FrameworkError, match="work_unit_not_found"):
        check_unit(binding, workspace, Platform(), "unknown")


def test_native_failure_keeps_the_runtime_layer_and_original_cause(binding, workspace, saver):
    selected, platform = proposed_child(binding, workspace, saver)
    actor = Actor(selected, platform)
    native_error = {"message": "stream disconnected before completion"}

    def failed(*args):
        native = actor(*args)
        return {**native, "status": "failed", "error": native_error}

    with pytest.raises(FrameworkError) as caught:
        check_unit(binding, workspace, platform, "local", invoke=failed)
    assert caught.value.layer == "runtime/infrastructure"
    assert caught.value.detail["cause"]["native_error"] == native_error
    assert workspace.get(selected.identity + ":work")["content"]["status"] == "proposal_ready"
    assert (
        check_unit(binding, workspace, platform, "local", invoke=actor)["result"]["status"]
        == "ready"
    )
    assert len(platform.effects) == 1


def test_local_check_feedback_preserves_allowed_input_ids_for_same_unit_retry(
    binding, workspace, saver
):
    selected, platform = proposed_child(binding, workspace, saver)
    actor = Actor(selected, platform)

    def wrong_consumption(*args):
        native = actor(*args)
        result = json.loads(native["final_response"])
        result["consumed_ids"] = ["historical-answer"]
        native["final_response"] = json.dumps(result)
        return native

    with pytest.raises(FrameworkError, match="unit_check_needs_correction"):
        check_unit(binding, workspace, platform, "local", invoke=wrong_consumption)

    def corrected(*args):
        prompt = json.loads(args[2])
        assert prompt["contract_feedback"]["allowed_ids"] == []
        assert prompt["contract_feedback"]["unexpected_ids"] == ["historical-answer"]
        assert "Historical answers" in prompt["instruction"]
        return actor(*args)

    proof = check_unit(binding, workspace, platform, "local", invoke=corrected)
    assert proof["result"]["status"] == "ready"
    assert len(platform.effects) == 1


def test_parent_requests_original_child_read_back_before_handoff(
    binding, workspace, saver, monkeypatch
):
    import ontoweave_modeling.flow as flow_module

    selected, platform = proposed_child(binding, workspace, saver)
    parent_actor, child_actor = Actor(binding, platform), Actor(selected, platform)

    def parent(*args):
        native = parent_actor(*args)
        result = json.loads(native["final_response"])
        result["consumed_ids"] = [item["id"] for item in args[3]]
        if args[1] == "self_check":
            result["review_units"] = ["local"]
        native["final_response"] = json.dumps(result)
        return native

    monkeypatch.setattr(
        flow_module,
        "check_unit",
        lambda b, r, p, unit: check_unit(b, r, p, unit, invoke=child_actor),
    )
    work = WorkUnitFlow(binding, workspace, platform, parent).advance(saver)
    assert work["status"] == "handoff_ready"
    assert child_actor.calls == ["self_check"]
    proof = workspace.get(selected.identity + ":work")["content"]["local_self_check_ref"]
    assert workspace.read_reference(proof)["basis"]["model_revisions"] == {"ontology": 2}


@pytest.mark.parametrize("purpose", ["modeling", "self_check"])
def test_child_prompt_keeps_proposal_and_actual_check_roles_separate(
    binding, workspace, tmp_path, monkeypatch, purpose
):
    binding.data["work_units"] = [{"unit_id": "local", "objective": "Bounded child meaning."}]
    selected = binding.for_unit("local")
    (binding.root / "private-runtime.json").write_text(
        json.dumps(
            {
                "connection": workspace.connection,
                "workspace_schema": workspace.schema,
            }
        )
    )
    config = tmp_path / "read.json"
    config.write_text("{}")
    observed = []

    class Bridge:
        def call(self, *args):
            return {"config_ref": str(config)}

        @contextmanager
        def provider(self, *args):
            yield "http://127.0.0.1:9"

    class Agent:
        def __init__(self, *args, instructions, **kwargs):
            observed.append(instructions)

        def start(self):
            pass

        def run_turn(self, prompt):
            return {"status": "completed"}

        def close(self):
            pass

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Agent)
    root = tmp_path / purpose
    root.mkdir()
    CodexInvocation(selected, Bridge())(root, purpose, "Only this phase", [])
    assert ("changes may be null because" in observed[0]) == (purpose == "modeling")
    assert ("not proposing" in observed[0]) == (purpose == "self_check")


def test_declared_local_checks_run_before_parent_semantic_check(
    binding, workspace, saver, monkeypatch
):
    import ontoweave_modeling.flow as flow_module

    selected, platform = proposed_child(binding, workspace, saver)
    parent_actor, child_actor = Actor(binding, platform), Actor(selected, platform)
    order = []

    def child(*args):
        order.append("local-check")
        return child_actor(*args)

    def parent(*args):
        native = parent_actor(*args)
        result = json.loads(native["final_response"])
        result["consumed_ids"] = [item["id"] for item in args[3]]
        if args[1] == "modeling":
            result["review_units"] = ["local"]
        else:
            order.append("parent-check")
            assert workspace.get(selected.identity + ":work")["content"].get("local_self_check_ref")
        native["final_response"] = json.dumps(result)
        return native

    monkeypatch.setattr(
        flow_module, "check_unit", lambda b, r, p, unit: check_unit(b, r, p, unit, invoke=child)
    )
    result = WorkUnitFlow(binding, workspace, platform, parent).advance(saver)
    assert result["status"] == "handoff_ready"
    assert order == ["local-check", "parent-check"]


def test_declared_local_rework_precedes_parent_check_without_touching_sibling(
    binding, workspace, saver, monkeypatch
):
    import ontoweave_modeling.flow as flow_module

    selected, platform = proposed_child(binding, workspace, saver)
    plan = WorkPlan(binding.data, workspace)
    plan.delegate("unaffected", "Unchanged independent scope")
    parent_actor, child_actor = Actor(binding, platform), Actor(selected, platform)

    def child(*args):
        native = child_actor(*args)
        result = json.loads(native["final_response"])
        result.update(status="revise", issues=["Original local condition is missing."])
        native["final_response"] = json.dumps(result)
        return native

    def parent(*args):
        assert args[1] == "modeling", "Do not redo the local failure in a parent self-check"
        native = parent_actor(*args)
        result = json.loads(native["final_response"])
        result["review_units"] = ["local"]
        native["final_response"] = json.dumps(result)
        return native

    monkeypatch.setattr(
        flow_module, "check_unit", lambda b, r, p, unit: check_unit(b, r, p, unit, invoke=child)
    )
    result = WorkUnitFlow(binding, workspace, platform, parent).advance(saver)
    assert result["status"] == "work_change_pending"
    current = plan.row()["content"]
    assert current["units"]["local"]["generation"] == current["root_generation"] == 1
    assert current["units"]["unaffected"]["generation"] == 0
    assert parent_actor.calls == ["modeling"]


@pytest.mark.parametrize("leaf_revise", [False, True])
def test_nested_declared_checks_are_bottom_up_and_bind_child_proofs(
    binding, workspace, saver, leaf_revise
):
    binding.data["work_units"] = [
        {"unit_id": "group", "objective": "Own the combined meaning."},
        {"unit_id": "leaf", "parent_id": "group", "objective": "Own the local meaning."},
        {"unit_id": "unaffected", "objective": "Unchanged other scope."},
    ]
    plan = WorkPlan(binding.data, workspace)
    plan.row()
    platform = Platform()
    original = platform.call
    platform.call = lambda action, payload=None: original(action, payload)
    for unit in ["leaf", "group"]:
        selected = binding.for_unit(unit)
        actor = Actor(selected, platform)

        def propose(*args, actor=actor, unit=unit):
            native = actor(*args)
            result = json.loads(native["final_response"])
            result["review_units"] = ["leaf"] if unit == "group" else []
            native["final_response"] = json.dumps(result)
            return native

        assert (
            WorkUnitFlow(selected, workspace, platform, propose).advance(saver)["status"]
            == "proposal_ready"
        )
    platform.call("apply", {"operation_id": "actual-root-write"})
    order = []
    actor = Actor(binding, platform)

    def inspect(*args):
        prompt = json.loads(args[2])
        leaf = prompt["objective"] == "Own the local meaning."
        order.append("leaf" if leaf else "group")
        assert bool(prompt["child_self_checks"]) == (not leaf)
        native = actor(*args)
        result = json.loads(native["final_response"])
        result["consumed_ids"] = [item["id"] for item in args[3]]
        if leaf and leaf_revise:
            result.update(status="revise", issues=["An approved local condition is missing."])
        native["final_response"] = json.dumps(result)
        return native

    proof = check_unit(binding, workspace, platform, "group", invoke=inspect)
    if leaf_revise:
        assert proof["status"] == "work_change_pending" and order == ["leaf"]
        assert not workspace.get(binding.for_unit("group").identity + ":work")["content"].get(
            "local_self_check_ref"
        )
        current = plan.row()["content"]
        assert (
            current["root_generation"]
            == current["units"]["group"]["generation"]
            == current["units"]["leaf"]["generation"]
            == 1
        )
        assert current["units"]["unaffected"]["generation"] == 0
    else:
        assert order == ["leaf", "group"]
        assert proof["basis"]["child_check_refs"]["leaf"]
        assert check_unit(binding, workspace, platform, "group", invoke=inspect) == proof
        assert order == ["leaf", "group"]
    assert len(platform.effects) == 1


def test_check_proof_routes_to_self_check_without_model_wakeup(binding, workspace, saver):
    from ontoweave_modeling.human_input import HumanInput

    selected, platform = proposed_child(binding, workspace, saver)
    check_unit(binding, workspace, platform, "local", invoke=Actor(selected, platform))
    human = HumanInput(binding, workspace, TaskControl(workspace))
    assert not any(":host-check-" in row["id"] for row in human.pending("model"))
    assert any(":host-check-" in row["id"] for row in human.pending("self_check"))
