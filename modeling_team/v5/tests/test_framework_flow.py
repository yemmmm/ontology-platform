"""Real PostgreSQL/checkpointer, deterministic actors; no semantic or platform PASS."""

import json

import pytest
from psycopg import sql

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import ExecutionManager
from ontoweave_modeling.flow import WorkUnitFlow


@pytest.fixture
def binding(task_file, tmp_path):
    return TaskBinding.prepare(task_file, tmp_path / "run")


@pytest.fixture
def saver(workspace):
    namespace = workspace.schema + "_cp"
    try:
        with workspace.checkpointer(namespace) as saver:
            yield saver
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(namespace))
            )


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


def test_bad_json_is_corrected_as_new_admitted_turn(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    actor.bad_first_result = True
    state = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert state["status"] == "handoff_ready" and state["round"] == 1
    assert actor.calls == ["modeling", "modeling", "self_check"]


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
