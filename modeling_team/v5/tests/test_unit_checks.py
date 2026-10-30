import json
from contextlib import contextmanager

import pytest
from test_framework_flow import Actor, Platform

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow
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


def test_local_actual_read_back_reuses_proof_until_model_changes(binding, workspace, saver):
    selected, platform = proposed_child(binding, workspace, saver)
    actor = Actor(selected, platform)
    original = check_unit(binding, workspace, platform, "local", invoke=actor)
    assert original["result"]["status"] == "ready"
    assert original["basis"]["model_revisions"] == {"ontology": 1}
    assert check_unit(binding, workspace, platform, "local", invoke=actor) == original
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
        if args[1] == "self_check":
            result = json.loads(native["final_response"])
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
