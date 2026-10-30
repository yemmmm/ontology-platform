"""Independent PostgreSQL child waits and parent composition, without semantic claims."""

import json
import threading
import time

import pytest
from psycopg import sql
from test_framework_flow import Actor, Platform, tool_event

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.human_input import HumanInput
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.snapshots import RunSnapshots
from ontoweave_modeling.team import TeamChannel


def test_safe_parent_group_applies_while_other_child_waits_without_final_handoff(
    binding, workspace, saver
):
    from ontoweave_modeling.flow import WorkUnitFlow
    from ontoweave_modeling.work_plan import WorkPlan

    binding.data["work_units"] = [
        {"unit_id": "ready-child", "objective": "Independent ready meaning."},
        {"unit_id": "waiting-child", "objective": "Needs a scoped answer."},
    ]
    WorkPlan(binding.data, workspace).row()
    platform = Platform()
    for unit, status in [("ready-child", "proposal_ready"), ("waiting-child", "waiting_input")]:
        selected = binding.for_unit(unit)
        flow = WorkUnitFlow(selected, workspace, platform, None)
        flow._save({**flow.initialize(), "status": status})
    actor = Actor(binding, platform)
    parent = WorkUnitFlow(binding, workspace, platform, actor)
    first = parent.advance(saver)
    assert len(platform.effects) == 1
    assert first["status"] == "waiting_children"
    assert first["activity"] == "model" and first.get("handoff_ref") is None
    assert workspace.read_reference(first["self_check_ref"])["result"]["status"] == "ready"


def test_original_structured_hitl_result_is_reparsed_without_repeating_native_turn(
    binding, workspace, saver, monkeypatch
):
    import ontoweave_modeling.flow as flow_module

    platform = Platform()
    actor = Actor(binding, platform)
    calls = []
    control = TaskControl(workspace)
    real_decode = flow_module.decode_work_result

    def invoke(root, purpose, prompt, inputs):
        calls.append(root.name)
        result = actor(root, purpose, prompt, inputs)
        value = json.loads(result["final_response"])
        value.update(
            status="waiting_input",
            candidate=None,
            changes=None,
            issues=[],
            human_requests=[
                {
                    "question": "Which name?",
                    "reason": "Scoped name unresolved",
                    "impact": "Only this unit",
                }
            ],
        )
        result["final_response"] = json.dumps(value)
        return result

    def old_decode(message, manifest, **kwargs):
        control.enqueue("pause-for-contract-repair", "pause")
        raise FrameworkError("unresolved_reason_required")

    monkeypatch.setattr(flow_module, "decode_work_result", old_decode)
    first = flow_module.WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert first["status"] == "paused" and len(calls) == 1
    original = (binding.root / "executions/model-00000/result.json").read_bytes()
    monkeypatch.setattr(flow_module, "decode_work_result", real_decode)
    control.enqueue("resume-after-contract-repair", "resume")
    second = flow_module.WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert second["status"] == "waiting_input" and len(calls) == 1
    assert (binding.root / "executions/model-00000/result.json").read_bytes() == original
    assert len(HumanInput(binding, workspace, control).requests()) == 1


@pytest.mark.parametrize("answer_while_b_busy", [False, True])
def test_local_hitl_wait_sibling_progress_restart_and_parent_single_apply(
    binding, workspace, answer_while_b_busy
):
    binding.data["work_units"] = [
        {"unit_id": "needs-answer", "objective": "Clarify the scoped name."},
        {"unit_id": "independent", "objective": "Prepare an independent source-grounded proposal."},
    ]
    binding.data["unit_concurrency"] = 2
    platform = Platform()
    original_call = platform.call
    platform.call = lambda action, payload=None: (
        {"config_ref": "prepared-read-key"}
        if action == "read_config"
        else original_call(action, payload)
    )
    calls = []
    entered_b = threading.Event()
    observed_wait = []
    answer_used = threading.Event()
    source = binding.data["source_manifest"]["source"]

    def factory(selected):
        if not selected.is_child:
            actor = Actor(selected, platform)

            def parent(root, purpose, prompt, inputs):
                if purpose == "modeling":
                    material_refs = json.loads(prompt)["child_results"]
                    assert len(material_refs) == 2
                    if any(item["status"] != "proposal_ready" for item in material_refs):
                        result = actor(root, purpose, prompt, inputs)
                        response = json.loads(result["final_response"])
                        response.update(
                            status="waiting_children",
                            candidate=None,
                            changes=None,
                            consumed_ids=[m["id"] for m in inputs],
                        )
                        result["final_response"] = json.dumps(response)
                        return result
                    channel = TeamChannel(binding.data, workspace, TaskControl(workspace))
                    for item in material_refs:
                        assert item["status"] == "proposal_ready" and "changes" not in item
                        assert (
                            json.loads(channel.read(item["material_ref"])["text"])["status"]
                            == "proposed"
                        )
                calls.append(("parent", purpose))
                result = actor(root, purpose, prompt, inputs)
                response = json.loads(result["final_response"])
                response["consumed_ids"] = [m["id"] for m in inputs]
                result["final_response"] = json.dumps(response)
                return result

            return parent

        def child(root, purpose, prompt, inputs):
            calls.append((selected.actor, purpose))
            folder = root / "agent"
            folder.mkdir()
            event = tool_event(
                "read_material",
                {"text": "source", "sha256": source["sha256"]},
                {"material_id": "source"},
            )
            (folder / "events.jsonl").write_text(json.dumps(event) + "\n")
            waiting = selected.actor == "needs-answer" and not inputs
            if waiting:
                assert entered_b.wait(10)
            elif selected.actor == "independent":
                entered_b.set()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    row = workspace.get(binding.for_unit("needs-answer").identity + ":work")
                    if row["content"]["status"] == "waiting_input":
                        observed_wait.append(True)
                        break
                    time.sleep(0.02)
                assert observed_wait
                if answer_while_b_busy:
                    human = HumanInput(binding, workspace, TaskControl(workspace))
                    request = human.requests()[0]
                    human.submit(
                        "Approved test name", "unit-answer", request_id=request["request_id"]
                    )
                    # A must consume its answer before B's original native activity ends.
                    assert answer_used.wait(10)
            response = {
                "status": "waiting_input" if waiting else "proposed",
                "candidate": None,
                "changes": None
                if waiting
                else {"schema_version": "r4-3-025-model-changes/v1", "changes": []},
                "source_refs": [{"material_id": "source", "sha256": source["sha256"]}],
                "issues": ["Missing scoped name"] if waiting else [],
                "consumed_ids": [m["id"] for m in inputs],
            }
            if waiting:
                response["human_requests"] = [
                    {
                        "question": "Which name?",
                        "reason": "Source leaves name open",
                        "impact": "Only this unit",
                    }
                ]
            elif selected.actor == "needs-answer":
                response["resolved_request_ids"] = [m["metadata"]["request_id"] for m in inputs]
                answer_used.set()
            return {"status": "completed", "final_response": json.dumps(response)}

        return child

    namespace = workspace.schema + "_multi_cp"
    try:
        scheduler = MultiUnitFlow(binding, workspace, platform, namespace, factory)
        first = scheduler.advance()
        if answer_while_b_busy:
            assert first["work"]["status"] == "handoff_ready"
            assert answer_used.is_set() and len(platform.effects) == 1
            assert calls.count(("independent", "modeling")) == 1
            assert calls.count(("needs-answer", "modeling")) == 2
            return
        assert first["work"]["status"] == "waiting_children"
        assert first["units"]["needs-answer"]["status"] == "waiting_input"
        assert first["units"]["independent"]["status"] == "proposal_ready"
        assert not platform.effects
        control = TaskControl(workspace)
        assert control.view()["mode"] == "running" and not control.view()["active"]
        human = HumanInput(binding, workspace, control)
        request = human.requests()[0]
        assert HumanInput(binding.for_unit("independent"), workspace, control).requests() == []
        with workspace.checkpointer(namespace) as saver:
            graph = scheduler.parent.compile(saver)
            receipt = RunSnapshots(binding, workspace).save("local-wait", graph, platform)
        frozen = RunSnapshots(root=binding.root).read(receipt["snapshot_id"])
        assert frozen["workflow"]["units"]["needs-answer"]["next"] == ["wait_input"]
        human.submit("Approved test name", "unit-answer", request_id=request["request_id"])
        assert control.view()["messages"][-1]["target"] == "needs-answer"
        # A new scheduler/checkpointer connection consumes the persisted answer and B's exact result.
        second = MultiUnitFlow(binding, workspace, platform, namespace, factory).advance()
        assert second["work"]["status"] == "handoff_ready"
        assert len(platform.effects) == 1
        assert calls.count(("independent", "modeling")) == 1
        assert calls.count(("needs-answer", "modeling")) == 2
        assert human.requests()[0]["status"] == "resolved"
        assert human.context()["answers"][0]["body"] == "Approved test name"
        before = list(calls)
        assert (
            MultiUnitFlow(binding, workspace, platform, namespace, factory).advance()["work"][
                "status"
            ]
            == "handoff_ready"
        )
        assert calls == before
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(namespace))
            )


def test_scheduler_does_not_start_model_over_an_active_original_unit_check(binding, workspace):
    from ontoweave_modeling.flow import WorkUnitFlow

    binding.data["work_units"] = [{"unit_id": "local", "objective": "Original local scope"}]
    platform = Platform()
    original = platform.call
    platform.call = lambda action, payload=None: (
        {"config_ref": "read-config"} if action == "read_config" else original(action, payload)
    )
    parent = WorkUnitFlow(binding, workspace, platform, None)
    parent._save(
        {
            **parent.initialize(),
            "status": "waiting_input",
            "activity": "wait_input",
            "resume_activity": "model",
        }
    )
    child = WorkUnitFlow(binding.for_unit("local"), workspace, platform, None)
    child._save({**child.initialize(), "status": "ready"})
    control = TaskControl(workspace)
    control.enqueue("new-local-input", "input", "Retain until the existing turn ends", "local")
    control.begin_activity("local", "original-check-in-progress")
    result = MultiUnitFlow(
        binding,
        workspace,
        platform,
        "v5_check_" + workspace.schema,
        invoke_factory=lambda selected: Actor(selected, platform),
    ).advance()
    assert result["units"]["local"]["status"] == "ready"
    assert control.view()["active"] == {"local": "original-check-in-progress"}
