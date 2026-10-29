from test_framework_flow import Actor, Platform

from ontoweave_modeling.cli import dispatch, parser
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.memory import SharedMemory
from ontoweave_modeling.snapshots import RunSnapshots


def test_snapshot_freezes_memory_work_and_checkpoint_without_replaying(binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    flow.advance(saver)
    memory = SharedMemory(workspace, "a")
    memory.write("scope", "decision", "Scope", "first")
    snapshots = RunSnapshots(binding, workspace)
    first = snapshots.save("before review", flow.compile(saver), platform)
    memory.write("scope", "decision", "Scope", "first with exception", expected_revision=1)
    second = snapshots.save("after review", flow.compile(saver), platform)
    frozen = snapshots.read(first["snapshot_id"])
    assert (
        next(r for r in frozen["objects"] if r["object_id"] == "memory:scope")["content"]["body"]
        == "first"
    )
    assert frozen["workflow"]["checkpoint_config"]["configurable"]["checkpoint_id"]
    delta = snapshots.diff("before review", "after review")
    assert (
        next(c for c in delta["changes"] if c["object_id"] == "memory:scope")["after_revision"] == 2
    )
    assert delta["before_model_revisions"] == delta["after_model_revisions"] == {"ontology": 1}
    assert actor.calls == ["modeling", "self_check"] and len(platform.effects) == 1
    assert len(snapshots.list()) == 2 and first["snapshot_id"] != second["snapshot_id"]


def test_observation_snapshot_does_not_require_busy_agent_to_stop(binding, workspace, saver):
    platform = Platform()
    flow = WorkUnitFlow(binding, workspace, platform, None)
    flow.initialize()
    flow.control.begin_activity(binding.data["work_unit_id"], "busy-turn")
    snapshots = RunSnapshots(binding, workspace)
    saved = snapshots.save("busy observation", flow.compile(saver), platform)
    data = snapshots.read(saved["snapshot_id"])
    control = next(r for r in data["objects"] if r["kind"] == "task_control")["content"]
    assert control["active"][binding.data["work_unit_id"]] == "busy-turn"
    assert flow.control.view()["active"] == control["active"]


def test_saved_snapshot_can_be_viewed_without_loading_runtime_or_original_sources(
    binding, workspace, saver
):
    platform = Platform()
    flow = WorkUnitFlow(binding, workspace, platform, None)
    flow.initialize()
    saved = RunSnapshots(binding, workspace).save("portable record", flow.compile(saver), platform)
    (binding.root / "materials/source.md").write_text("Changed after snapshot")
    args = parser().parse_args(
        ["snapshot-show", "--run-dir", str(binding.root), "--snapshot", saved["snapshot_id"]]
    )
    assert dispatch(args)["name"] == "portable record"
