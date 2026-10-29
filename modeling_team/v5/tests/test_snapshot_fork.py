"""Snapshot forks isolate business state, retain original evidence and never replay uncertain copies."""

import json
from uuid import UUID, uuid5

import pytest

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.semantic_workspace import SemanticWorkspace
from ontoweave_modeling.snapshot_fork import SnapshotFork
from ontoweave_modeling.snapshots import RunSnapshots


class ForkPlatform:
    def __init__(self):
        self.forks = []
        self.unknown = False

    def call(self, action, payload):
        if action == "snapshot":
            return {
                "project_id": "source-project",
                "ontology_ids": ["source-ontology"],
                "model_revisions": {"source-ontology": 3},
            }
        if action == "capture_data":
            return {
                "data": {
                    "project_id": "source-project",
                    "ontology_ids": ["source-ontology"],
                    "digest": "captured-platform-digest",
                },
                "credential": {"revoked": True},
            }
        if action == "cleanup":
            return {"aggregate_keys_non_active": True, "scope_disposition": "written-retained"}
        if action == "fork_data":
            self.forks.append(payload)
            if self.unknown:
                raise FrameworkError("host_response_unknown")
            return {
                "data": {
                    "project_id": payload["target_project_id"],
                    "ontology_ids": [
                        str(uuid5(UUID(payload["target_project_id"]), "source-ontology"))
                    ],
                    "source_project_id": "source-project",
                },
                "credential": {"revoked": True},
            }
        raise AssertionError(action)


def save_data_snapshot(binding, workspace, saver):
    platform = ForkPlatform()
    (binding.root / "private-runtime.json").write_text(
        json.dumps(
            {
                "connection": workspace.connection,
                "workspace_schema": workspace.schema,
                "checkpoint_schema": workspace.schema + "_cp",
            }
        )
    )
    flow = WorkUnitFlow(binding, workspace, platform, None)
    state = flow.initialize()
    baseline = workspace.put_reference(
        "test-model", "model_reference", platform.call("snapshot", {}), 0
    )
    flow._save({**state, "baseline_ref": baseline})
    space = SemanticWorkspace(workspace, binding.data)
    space.write(
        "condition",
        "proposition",
        "Condition",
        "Condition and unknown preserved",
        [{"material_id": "source"}],
    )
    saved = RunSnapshots(binding, workspace).save(
        "with-data", flow.compile(saver), platform, include_platform=True
    )
    return platform, saved


def test_data_snapshot_fork_isolates_control_and_preserves_source(
    binding, workspace, saver, tmp_path
):
    platform, saved = save_data_snapshot(binding, workspace, saver)
    original_source = (binding.materials / "source.md").read_bytes()
    destination = tmp_path / "fork"
    fork = SnapshotFork(binding, workspace, platform)
    with pytest.raises(FrameworkError, match="archive_source_acknowledgment_required"):
        fork.create(
            saved["snapshot_id"],
            destination,
            "fork-run",
            "Compare workflow",
            "test-authorized-fork",
        )
    result = fork.create(
        saved["snapshot_id"],
        destination,
        "fork-run",
        "Compare workflow",
        "test-authorized-fork",
        True,
    )
    assert result["status"] == "prepared" and len(platform.forks) == 1
    assert (binding.materials / "source.md").read_bytes() == original_source
    assert TaskControl(workspace).view()["mode"] == "stopped"
    new = TaskBinding.load(destination)
    assert new.data["task_ref"] == binding.data["task_ref"]
    assert new.data["workspace_ref"] != binding.data["task_ref"]
    from ontoweave_modeling.cli import repository

    target, _ = repository(new)
    assert TaskControl(target).view()["mode"] == "running"
    imported = SemanticWorkspace(target, new.data).read("condition")
    assert imported["body"] == "Condition and unknown preserved"
    assert imported["freshness"]["state"] == "needs_review"
    assert not target.list_kind("execution") and not target.list_kind("handoff")
    assert fork.create(
        saved["snapshot_id"],
        destination,
        "fork-run",
        "Compare workflow",
        "test-authorized-fork",
        True,
    )["replayed"]
    assert len(platform.forks) == 1


def test_unknown_fork_retains_preallocated_target_and_never_retries(
    binding, workspace, saver, tmp_path
):
    platform, saved = save_data_snapshot(binding, workspace, saver)
    platform.unknown = True
    fork = SnapshotFork(binding, workspace, platform)
    destination = tmp_path / "unknown-fork"
    with pytest.raises(FrameworkError, match="host_response_unknown"):
        fork.create(
            saved["snapshot_id"],
            destination,
            "unknown-fork",
            "Recovery experiment",
            "test-authorization",
            True,
        )
    pending = json.loads((destination / "fork-pending.json").read_text())
    assert pending["status"] == "unknown" and pending["target_project_id"]
    with pytest.raises(FrameworkError, match="fork_result_unknown"):
        fork.create(
            saved["snapshot_id"],
            destination,
            "unknown-fork",
            "Recovery experiment",
            "test-authorization",
            True,
        )
    assert len(platform.forks) == 1
