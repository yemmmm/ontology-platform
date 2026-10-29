"""Source changes re-enter selected work and preserve the original effects and evidence."""

import hashlib
import json

import pytest
from psycopg import sql
from test_framework_flow import Actor, Platform

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.revisions import SourceRevisions


def changed_package(binding, tmp_path):
    folder = tmp_path / "revision"
    folder.mkdir()
    manifest = dict(binding.data["source_manifest"])
    (folder / "source.md").write_bytes((binding.materials / "source.md").read_bytes())
    text = "A new local condition; other units are unchanged."
    (folder / "additional.md").write_text(text)
    manifest["additional"] = {
        "path": "additional.md",
        "source_ref": "approved-additional-source",
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def test_source_revision_after_handoff_updates_same_run_and_keeps_originals(
    binding, workspace, saver, tmp_path
):
    platform = Platform()
    actor = Actor(binding, platform)
    before = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    old_binding = (binding.root / "binding.json").read_bytes()
    old_source = (binding.materials / "source.md").read_bytes()
    revision = SourceRevisions(binding, workspace)
    change = {"change_id": "add-local-condition", "reason": "Approved local addition"}
    revision.stage(change, changed_package(binding, tmp_path))
    current = revision.activate()
    assert current.data["run_id"] == binding.data["run_id"]
    assert current.thread_id != binding.thread_id
    assert (binding.materials / "source.md").read_bytes() == old_source
    assert old_binding in [
        p.read_bytes() for p in (binding.root / "binding-versions").glob("*.json")
    ]
    state = workspace.get(binding.identity + ":work")["content"]
    assert state["activity"] == "model" and state["round"] == before["round"] + 1
    assert state["refresh_baseline"]
    after = WorkUnitFlow(current, workspace, platform, Actor(current, platform)).advance(saver)
    assert after["status"] == "handoff_ready" and len(platform.effects) == 2
    assert (
        workspace.read_reference(before["handoff_ref"])["source_manifest_digest"]
        == binding.data["source_manifest_digest"]
    )
    assert after["handoff_ref"] != before["handoff_ref"]
    assert TaskBinding.load(binding.root).data == current.data
    assert revision.stage(change, tmp_path / "revision")["status"] == "activated"
    assert revision.activate().data == current.data


def test_revision_queues_while_native_busy_then_activates_without_replay(
    binding, workspace, tmp_path
):
    control = TaskControl(workspace)
    control.begin_turn("bounded-unit", "original")
    revisions = SourceRevisions(binding, workspace)
    change = {"change_id": "during-generation", "reason": "New approved material"}
    revisions.stage(change, changed_package(binding, tmp_path))
    assert revisions.activate().data == binding.data
    assert "cycle_id" not in TaskBinding.load(binding.root).data
    control.finish_turn("bounded-unit", "original")
    current = revisions.activate()
    assert current.data["cycle_id"] == "during-generation"
    assert revisions.activate().data == current.data


def test_only_selected_child_reopens_and_other_result_is_reused(binding, workspace, tmp_path):
    binding.data["work_units"] = [
        {"unit_id": "a", "objective": "Local scope"},
        {"unit_id": "b", "objective": "Unaffected scope"},
    ]
    platform = Platform()
    for selected in [binding, binding.for_unit("a"), binding.for_unit("b")]:
        flow = WorkUnitFlow(selected, workspace, platform, None)
        flow.initialize()
        flow._save(
            {
                **workspace.get(flow.work_id)["content"],
                "status": "proposal_ready",
                "round": 3,
                "result_material_ref": {"object_id": selected.actor},
            }
        )
    unaffected = workspace.get(binding.for_unit("b").identity + ":work")
    revisions = SourceRevisions(binding, workspace)
    change = {
        "change_id": "local-a",
        "affected_units": ["a"],
        "reason": "Only A uses the new source",
    }
    revisions.stage(change, changed_package(binding, tmp_path))
    current = revisions.activate()
    a = workspace.get(current.for_unit("a").identity + ":work")["content"]
    assert a["status"] == "ready" and a["round"] == 4
    assert workspace.get(current.for_unit("b").identity + ":work") == unaffected


def test_withdrawn_source_is_retained_as_history_not_automatic_falsehood(
    binding, workspace, tmp_path
):
    folder = changed_package(binding, tmp_path)
    revisions = SourceRevisions(binding, workspace)
    revisions.stage({"change_id": "add", "reason": "Additional source"}, folder)
    current = revisions.activate()
    revisions.stage(
        {"change_id": "withdraw", "reason": "Source withdrawn; meaning needs review"},
        binding.materials,
    )
    last = revisions.activate()
    assert "additional" not in last.data["source_manifest"]
    assert (current.materials / "additional.md").exists()
    assert workspace.list_kind("source_change")[-1]["content"]["status"] == "activated"


def test_incremental_multi_unit_flow_reuses_unaffected_execution(binding, workspace, tmp_path):
    binding.data["work_units"] = [
        {"unit_id": "a", "objective": "Local scope"},
        {"unit_id": "b", "objective": "Unchanged scope"},
    ]
    platform = Platform()
    original = platform.call
    platform.call = lambda action, payload=None: (
        {"config_ref": "read-key"} if action == "read_config" else original(action, payload)
    )
    calls = []

    def factory(selected):
        actor = Actor(selected, platform)

        def invoke(root, purpose, prompt, inputs):
            calls.append((selected.actor, purpose))
            result = actor(root, purpose, prompt, inputs)
            response = json.loads(result["final_response"])
            response["consumed_ids"] = [m["id"] for m in inputs]
            result["final_response"] = json.dumps(response)
            return result

        return invoke

    namespace = workspace.schema + "_revision_cp"
    try:
        first = MultiUnitFlow(binding, workspace, platform, namespace, factory).advance()
        assert first["work"]["status"] == "handoff_ready"
        retained = first["units"]["b"]["execution_ref"]
        revisions = SourceRevisions(binding, workspace)
        revisions.stage(
            {"change_id": "a-only", "affected_units": ["a"], "reason": "Approved A-only addition"},
            changed_package(binding, tmp_path),
        )
        selected = revisions.activate()
        second = MultiUnitFlow(selected, workspace, platform, namespace, factory).advance()
        assert second["work"]["status"] == "handoff_ready"
        assert second["units"]["b"]["execution_ref"] == retained
        assert calls.count(("b", "modeling")) == 1
        assert calls.count(("a", "modeling")) == 2
        assert calls.count(("modeling", "modeling")) == 2
        assert len(platform.effects) == 2
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(namespace))
            )


def test_change_arriving_during_generation_does_not_apply_old_candidate(
    binding, workspace, saver, tmp_path
):
    platform = Platform()
    revisions = SourceRevisions(binding, workspace)
    package = changed_package(binding, tmp_path)
    actor = Actor(
        binding,
        platform,
        lambda purpose: (
            revisions.stage(
                {
                    "change_id": "during-model",
                    "reason": "Explicit source change while model is busy",
                },
                package,
            )
            if purpose == "modeling"
            else None
        ),
    )
    state = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert state["status"] == "source_change_pending"
    assert not platform.effects and actor.calls == ["modeling"]
    selected = revisions.activate()
    final = WorkUnitFlow(selected, workspace, platform, Actor(selected, platform)).advance(saver)
    assert final["status"] == "handoff_ready" and len(platform.effects) == 1


def test_rebinding_sources_does_not_allow_silent_scope_change(binding, workspace):
    flow = WorkUnitFlow(binding, workspace, Platform(), None)
    flow.initialize()
    binding.data["scope"] = {**binding.data["scope"], "base_url": "http://other-platform"}
    with pytest.raises(FrameworkError, match="binding_changed_or_incompatible"):
        flow.initialize()
