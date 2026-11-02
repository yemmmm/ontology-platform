"""Real PostgreSQL/checkpointer, deterministic actors; no semantic or platform PASS."""

import json

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import CodexInvocation, ExecutionManager
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.semantic_workspace import SemanticWorkspace


def tool_event(tool, data, arguments=None):
    return {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "mcpToolCall",
                "tool": tool,
                "status": "completed",
                "arguments": arguments or {},
                "result": {"structuredContent": data},
            }
        },
    }


class Platform:
    def __init__(self):
        self.calls, self.effects = [], {}
        self.uncertain = False

    def call(self, action, payload):
        self.calls.append((action, payload))
        if action == "apply":
            self.effects.setdefault(payload["operation_id"], payload)
            return {"status": "uncertain" if self.uncertain else "completed", "batches": []}
        return {
            "project_id": "project",
            "ontology_ids": ["ontology"],
            "model_revisions": {"ontology": len(self.effects)},
            "resource_bindings": {},
        }


class Actor:
    def __init__(self, binding, platform, callback=None):
        self.binding, self.platform, self.callback = binding, platform, callback
        self.calls = []
        self.bad_first_result = False
        self.waiting = False

    def __call__(self, root, purpose, prompt, inputs):
        self.calls.append(purpose)
        folder = root / "agent"
        folder.mkdir()
        source = self.binding.data["source_manifest"]["source"]
        if purpose == "modeling":
            event = tool_event(
                "read_material",
                {"text": "approved source", "sha256": source["sha256"]},
                {"material_id": "source"},
            )
            response = {
                "status": "waiting_input" if self.waiting else "proposed",
                "candidate": None,
                "changes": None
                if self.waiting
                else {
                    "schema_version": "r4-3-025-model-changes/v1",
                    "candidate_ref": None,
                    "changes": [],
                },
                "source_refs": [{"material_id": "source", "sha256": source["sha256"]}],
                "issues": ["A business meaning is missing"] if self.waiting else [],
                "consumed_ids": [],
            }
        else:
            event = tool_event(
                "query_semantic_context",
                {
                    "ok": True,
                    "scope": {
                        "ontologies": [
                            {
                                "ontology_id": "ontology",
                                "model_revision": len(self.platform.effects),
                            },
                        ]
                    },
                },
            )
            response = {"status": "ready", "issues": [], "consumed_ids": []}
        (folder / "events.jsonl").write_text(json.dumps(event) + "\n")
        if self.callback:
            self.callback(purpose)
        final = (
            "invalid JSON"
            if self.bad_first_result and len(self.calls) == 1
            else json.dumps(response)
        )
        return {
            "thread_id": "native-thread",
            "turn_id": root.name,
            "status": "completed",
            "final_response": final,
        }


def test_root_self_check_locates_old_coverage_without_program_semantic_completion(
    binding, workspace, saver
):
    binding.data["semantic_workspace"] = True
    space = SemanticWorkspace(workspace, binding.data)
    space.observe_models({"ontology": 0})
    space.write(
        "existing-root-coverage",
        "coverage",
        "Root coverage",
        "Unfinished expression",
        states={"expression": "partial"},
    )
    platform = Platform()
    actor = Actor(binding, platform)

    def inspect(*args):
        if args[1] == "self_check":
            row = json.loads(args[2])["workspace_context"]["local"]["records"][0]
            assert row["record_id"] == "existing-root-coverage"
            assert row["states"]["expression"] == "partial"
            assert row["freshness"]["state"] == "needs_review"
        return actor(*args)

    assert (
        WorkUnitFlow(binding, workspace, platform, inspect).advance(saver)["status"]
        == "handoff_ready"
    )
    assert space.read("existing-root-coverage")["states"]["expression"] == "partial"


def test_whole_model_ready_returns_missing_reads_before_handoff(binding, workspace, saver):
    binding.data["evaluation"]["model_read_scope"] = "whole_model"
    control = TaskControl(workspace)
    platform = Platform()
    actor = Actor(
        binding,
        platform,
        lambda purpose: (
            control.enqueue("pause-after-check", "pause") if purpose == "self_check" else None
        ),
    )

    def inspect(root, purpose, prompt, inputs):
        if purpose == "self_check":
            assert json.loads(prompt)["model_read_scope"] == "whole_model"
        return actor(root, purpose, prompt, inputs)

    state = WorkUnitFlow(binding, workspace, platform, inspect).advance(saver)
    assert state["status"] == "paused"
    assert state["issue"]["code"] == "self_check_needs_correction"
    assert state["issue"]["coverage"]["materials"][0]["material_id"] == "source"
    assert state["issue"]["coverage"]["models"][0]["missing_inventory"] is True
    assert workspace.get(binding.identity + ":work")["content"].get("handoff_ref") is None


def test_actual_provider_429_pauses_before_next_turn_and_preserves_terminal_receipt(
    binding, workspace
):
    control = TaskControl(workspace)
    manager = ExecutionManager(workspace, control, binding)
    calls = []

    def invoke(root, purpose, prompt, inputs):
        calls.append(root.name)
        (root / "provider-usage.jsonl").write_text(
            json.dumps({"http_status": 429, "request_id": "limited-upstream"}) + "\n"
        )
        return {"status": "failed", "error": {"message": "upstream rejected"}, "final_response": ""}

    ref = manager.run("limited-turn", "modeling", "bounded task", invoke)
    assert workspace.read_reference(ref)["result"]["status"] == "failed"
    assert control.view()["mode"] == "paused" and control.view()["active"] == {}
    limit = json.loads((binding.root / "provider-limit.json").read_text())
    assert limit["http_status"] == 429 and limit["window_attribution"] == "unknown"
    with pytest.raises(FrameworkError, match="execution_not_admitted"):
        manager.run("next-turn", "modeling", "must not dispatch", invoke)
    assert calls == ["limited-turn"]


def test_provider_preparation_failure_has_no_native_turn_and_can_resume(
    binding, workspace, tmp_path
):
    from contextlib import contextmanager

    class Bridge:
        def call(self, action, payload):
            return {"config_ref": str(tmp_path / "read.json")}

        @contextmanager
        def provider(self, *args):
            raise FrameworkError("host_operation_failed", layer="runtime/infrastructure")
            yield  # pragma: no cover

    control = TaskControl(workspace)
    manager = ExecutionManager(workspace, control, binding)
    invocation = CodexInvocation(binding, Bridge())
    ref = manager.run("prepare-failure", "modeling", "bounded task", invocation)
    result = workspace.read_reference(ref)["result"]
    assert result["status"] == "failed" and result["native_start_requested"] is False
    assert not control.view()["active"]
    assert manager.run("prepare-failure", "modeling", "bounded task", invocation) == ref


def test_full_reference_graph_is_separate_from_semantic_acceptance(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    state = flow.advance(saver)
    assert state["status"] == "handoff_ready"
    assert state["semantic_acceptance"] == "unverified"
    assert actor.calls == ["modeling", "self_check"]
    assert len(platform.effects) == 1
    checkpoint = flow.compile(saver).get_state({"configurable": {"thread_id": "framework-run"}})
    assert "candidate" not in checkpoint.values and "final_response" not in checkpoint.values
    assert WorkUnitFlow(binding, workspace, platform, actor).advance(saver) == state
    assert len(actor.calls) == 2


def test_no_change_path_still_self_checks_actual_model_without_apply(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)

    def invoke(root, purpose, prompt, inputs):
        result = actor(root, purpose, prompt, inputs)
        if purpose == "modeling":
            response = json.loads(result["final_response"])
            response.update(status="no_change", candidate=None, changes=None)
            result["final_response"] = json.dumps(response)
        return result

    final = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert final["status"] == "handoff_ready" and not platform.effects
    assert actor.calls == ["modeling", "self_check"]


def test_self_check_diagnostics_do_not_force_an_extra_model_turn(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)

    def invoke(root, purpose, prompt, inputs):
        result = actor(root, purpose, prompt, inputs)
        if purpose == "self_check":
            value = json.loads(result["final_response"])
            value["self_check"] = {"observed_versions": {"ontology": 1}}
            result["final_response"] = json.dumps(value)
        return result

    assert (
        WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)["status"]
        == "handoff_ready"
    )
    assert actor.calls == ["modeling", "self_check"]


def test_external_model_drift_reenters_modeling_before_any_owned_apply(binding, workspace, saver):
    platform = Platform()
    inserted = False

    def change_actual(purpose):
        nonlocal inserted
        if purpose == "modeling" and not inserted:
            inserted = True
            platform.effects["external-change"] = {"origin": "another-client"}

    actor = Actor(binding, platform, change_actual)
    final = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert final["status"] == "handoff_ready"
    assert actor.calls == ["modeling", "modeling", "self_check"]
    assert set(platform.effects) == {"external-change", "apply-00001"}


def test_bad_json_is_corrected_as_new_admitted_turn(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    actor.bad_first_result = True
    state = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert state["status"] == "handoff_ready" and state["round"] == 1
    assert actor.calls == ["modeling", "modeling", "self_check"]


def test_compiler_correction_receives_original_proposal_not_just_error_paths(
    binding, workspace, saver
):
    platform = Platform()
    actual_call = platform.call
    failed = False

    def call(action, payload):
        nonlocal failed
        if action == "apply" and not failed:
            failed = True
            return {
                "status": "not_written",
                "errors": [{"code": "field_needs_correction", "path": "/changes/0"}],
            }
        return actual_call(action, payload)

    platform.call = call
    actor = Actor(binding, platform)
    previous = []

    def invoke(root, purpose, prompt, inputs):
        data = json.loads(prompt)
        if purpose == "modeling" and failed:
            previous.append(data["previous_proposal"]["content"])
            assert previous[-1]["changes"]["schema_version"] == "r4-3-025-model-changes/v1"
        return actor(root, purpose, prompt, inputs)

    final = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert final["status"] == "handoff_ready" and len(previous) == 1
    assert len(platform.effects) == 1


def test_pause_preserves_candidate_and_never_dispatches_application(binding, workspace, saver):
    platform = Platform()
    control = TaskControl(workspace)
    actor = Actor(
        binding,
        platform,
        lambda purpose: control.enqueue("pause", "pause") if purpose == "modeling" else None,
    )
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    paused = flow.advance(saver)
    assert paused["status"] == "paused" and paused["activity"] == "apply"
    assert paused["candidate_ref"] and not platform.effects
    assert control.view()["status"] == "settled"
    control.enqueue("resume", "resume")
    assert flow.advance(saver)["status"] == "handoff_ready"
    assert actor.calls == ["modeling", "self_check"]


def test_pause_keeps_first_result_error_for_resume(binding, workspace, saver):
    platform = Platform()
    control = TaskControl(workspace)
    actor = Actor(
        binding,
        platform,
        lambda purpose: control.enqueue("pause", "pause") if len(actor.calls) == 1 else None,
    )
    actor.bad_first_result = True
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    paused = flow.advance(saver)
    assert paused["status"] == "paused"
    assert paused["issue"]["code"] == "work_result_invalid"
    control.enqueue("resume", "resume")
    assert flow.advance(saver)["status"] == "handoff_ready"
    assert len(platform.effects) == 1


@pytest.mark.parametrize("material_channel", [False, True])
def test_invalid_result_repair_receives_rejected_output_before_old_applied_proposal(
    binding, workspace, saver, material_channel
):
    binding.data["work_management"] = material_channel
    platform = Platform()
    platform.effects["old-applied"] = {}
    control = TaskControl(workspace)
    actor = Actor(binding, platform)
    rejected = []
    flow = None

    def invoke(root, purpose, prompt, inputs):
        if purpose == "modeling" and actor.calls:
            previous = json.loads(prompt)["previous_proposal"]
            content = (
                flow.team.read(previous["material_ref"])["text"]
                if material_channel
                else previous["content"]
            )
            assert content == rejected[0]
            assert previous["application_state"] == "not_applied"
        result = actor(root, purpose, prompt, inputs)
        if purpose == "modeling" and len(actor.calls) == 1:
            body = json.loads(result["final_response"])
            body.update(status="已提出", issues=["new unapplied definition links"])
            result["final_response"] = json.dumps(body, ensure_ascii=False)
            rejected.append(result["final_response"])
            control.enqueue("pause", "pause")
        return result

    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    state = flow.initialize()
    old = workspace.put_reference(
        binding.identity + ":older-applied-proposal",
        "candidate",
        {"issues": ["older applied scope"]},
        0,
    )
    flow._save({**state, "candidate_ref": old})
    paused = flow.advance(saver)
    assert paused["issue"]["code"] == "work_result_invalid"
    assert len(platform.effects) == 1
    control.enqueue("resume", "resume")
    assert flow.advance(saver)["status"] == "handoff_ready"
    assert len(platform.effects) == 2


def test_unknown_apply_keeps_original_activity_and_operation(binding, workspace, saver):
    platform = Platform()
    platform.uncertain = True
    flow = WorkUnitFlow(binding, workspace, platform, Actor(binding, platform))
    first = flow.advance(saver)
    assert first["status"] == "uncertain"
    assert TaskControl(workspace).view()["active"] == {"bounded-unit:platform": "apply-00000"}
    assert flow.advance(saver)["status"] == "uncertain"
    assert len(platform.effects) == 1
    platform.uncertain = False
    assert flow.advance(saver)["status"] == "handoff_ready"
    assert len(platform.effects) == 1


def test_corrected_self_check_uses_new_snapshot_without_overwriting_history(
    binding, workspace, saver, monkeypatch
):
    platform = Platform()
    control = TaskControl(workspace)
    actor = Actor(binding, platform)
    targets = []
    original_put = workspace.put_reference
    original_call = platform.call
    refreshed = False

    def put(object_id, kind, content, revision):
        ref = original_put(object_id, kind, content, revision)
        if ":target:" in object_id:
            targets.append(ref)
        return ref

    def platform_call(action, payload):
        value = original_call(action, payload)
        if action == "snapshot" and refreshed:
            value["resource_refs"] = {
                "definition": {"artifact_ref": "applied-bindings.json", "path": "/definition"}
            }
        return value

    def invoke(root, purpose, prompt, inputs):
        value = actor(root, purpose, prompt, inputs)
        if purpose == "self_check" and actor.calls.count("self_check") == 1:
            control.enqueue("pause", "pause")
            value["final_response"] = "invalid JSON"
        return value

    monkeypatch.setattr(workspace, "put_reference", put)
    monkeypatch.setattr(platform, "call", platform_call)
    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    assert flow.advance(saver)["status"] == "paused"
    refreshed = True
    control.enqueue("resume", "resume")
    assert flow.advance(saver)["status"] == "handoff_ready"
    assert len(platform.effects) == 1 and len(targets) == 2
    assert targets[0] != targets[1]
    assert "resource_refs" not in workspace.read_reference(targets[0])
    assert "resource_refs" in workspace.read_reference(targets[1])


def test_missing_business_input_waits_without_guessing(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    actor.waiting = True
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    assert flow.advance(saver)["status"] == "waiting_input"
    assert not platform.effects
    assert flow.advance(saver)["status"] == "waiting_input"
    assert len(actor.calls) == 1


def test_stop_during_native_turn_prevents_application_and_stays_stopped(binding, workspace, saver):
    platform = Platform()
    control = TaskControl(workspace)
    actor = Actor(binding, platform, lambda purpose: control.enqueue("stop", "stop"))
    state = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert state["status"] == "stopped" and state["candidate_ref"]
    assert not platform.effects and control.view()["status"] == "settled"


def test_model_result_survives_failure_before_graph_checkpoint(
    binding, workspace, saver, monkeypatch
):
    platform = Platform()
    actor = Actor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    original = flow._save
    crashed = False

    def save(state):
        nonlocal crashed
        if state["activity"] == "apply" and not crashed:
            crashed = True
            raise RuntimeError("failure after candidate commit")
        return original(state)

    monkeypatch.setattr(flow, "_save", save)
    with pytest.raises(RuntimeError, match="after candidate"):
        flow.advance(saver)
    rebuilt = WorkUnitFlow(binding, workspace, platform, actor)
    assert rebuilt.advance(saver)["status"] == "handoff_ready"
    assert actor.calls == ["modeling", "self_check"]


def test_native_completion_event_recovers_without_another_model_call(binding, workspace):
    control = TaskControl(workspace)
    manager = ExecutionManager(workspace, control, binding)
    calls = []

    def crash(root, *_):
        calls.append(1)
        (root / "agent").mkdir()
        events = [
            {"method": "turn/started", "params": {"threadId": "thread", "turn": {"id": "turn"}}},
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": "original"}},
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn", "status": "completed"}}},
        ]
        (root / "agent/events.jsonl").write_text("\n".join(map(json.dumps, events)))
        raise RuntimeError("lost response")

    with pytest.raises(RuntimeError):
        manager.run("exec-1", "modeling", "same prompt", crash)
    assert control.view()["active"]
    ref = manager.run("exec-1", "modeling", "same prompt", crash)
    assert workspace.read_reference(ref)["result"]["final_response"] == "original"
    assert not control.view()["active"] and len(calls) == 1


def test_unknown_native_execution_is_not_restarted(binding, workspace):
    manager = ExecutionManager(workspace, TaskControl(workspace), binding)
    calls = []

    def unknown(*_):
        calls.append(1)
        raise RuntimeError("connection lost")

    with pytest.raises(RuntimeError):
        manager.run("exec-1", "modeling", "prompt", unknown)
    with pytest.raises(FrameworkError, match="reconciliation_required"):
        manager.run("exec-1", "modeling", "prompt", unknown)
    assert len(calls) == 1


def test_stop_is_not_reset_by_resume_and_phantom_consumption_keeps_active(workspace):
    control = TaskControl(workspace)
    control.begin_turn("unit", "exec")
    with pytest.raises(ValueError, match="consumption"):
        control.finish_turn("unit", "exec", consumed_ids=("never-delivered",))
    assert control.view()["active"]
    control.enqueue("stop", "stop")
    control.finish_turn("unit", "exec")
    control.enqueue("resume", "resume")
    assert control.synchronize()["mode"] == "stopped"


def test_source_read_feedback_names_missing_material_and_can_resume(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    control = TaskControl(workspace)
    prompts = []

    def invoke(root, purpose, prompt, inputs):
        result = actor(root, purpose, prompt, inputs)
        if purpose == "modeling":
            prompts.append(json.loads(prompt))
            if len(prompts) == 1:
                (root / "agent/events.jsonl").write_text("")
                control.enqueue("pause-after-unread-source", "pause")
        return result

    state = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert state["status"] == "paused" and not platform.effects
    assert state["issue"]["code"] == "source_read_missing"
    assert state["issue"]["material_ids"] == ["source"]
    assert "this native turn" in prompts[0]["contract"]
    control.enqueue("resume-source-correction", "resume")
    final = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert final["status"] == "handoff_ready" and len(platform.effects) == 1
    assert prompts[1]["feedback"]["material_ids"] == ["source"]


def test_work_tree_child_wait_does_not_require_a_static_peer_roster(binding, workspace, saver):
    binding.data["work_units"] = [{"unit_id": "local", "objective": "Delegated meaning"}]
    platform = Platform()
    actor = Actor(binding, platform)

    def waiting(*args):
        native = actor(*args)
        result = json.loads(native["final_response"])
        result.update(status="waiting_peer", changes=None, issues=["Await original child result"])
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(binding, workspace, platform, waiting)
    first = flow.advance(saver)
    assert first["status"] == "waiting_peer"
    assert flow.advance(saver)["status"] == "waiting_peer"
    assert actor.calls == ["modeling"] and not platform.effects


def test_input_arriving_during_final_check_is_delivered_before_handoff(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    control = TaskControl(workspace)
    model_inputs = []
    added = False

    def invoke(root, purpose, prompt, inputs):
        nonlocal added
        native = actor(root, purpose, prompt, inputs)
        result = json.loads(native["final_response"])
        result["consumed_ids"] = [item["id"] for item in inputs]
        if purpose == "modeling":
            model_inputs.append(result["consumed_ids"])
            if added:
                result.update(status="no_change", candidate=None, changes=None)
        elif not added:
            control.enqueue(
                "new-child-result", "input", "New scoped result", binding.data["work_unit_id"]
            )
            added = True
        native["final_response"] = json.dumps(result)
        return native

    result = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert result["status"] == "handoff_ready"
    assert model_inputs == [[], ["new-child-result"]]
    assert len(platform.effects) == 1
    assert control.view()["messages"][0]["status"] == "consumed"
