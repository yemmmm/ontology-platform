"""Data packages and fork plans; no model provider is started by these tests."""

import json
import os
from datetime import UTC, datetime
from shutil import rmtree
from types import SimpleNamespace

import pytest

from modeling_team.checkpoint_data import prepare_fork_plan
from modeling_team.checkpoint_recovery import PlatformReadback, origin_chain_roots
from modeling_team.checkpoints import (
    PLATFORM_DATA_PATH,
    CheckpointError,
    save_checkpoint,
)
from modeling_team.tests.test_r30015_checkpoints import CONFIGURATION, REPO_ROOT, _write_json
from modeling_team.tests.test_r30015_checkpoints import _CheckpointRunner, _freeze, RUNS_ROOT
from modeling_team.tests.test_r30015_resume import _bound_package, _seed_chain_intent
from modeling_team.tests.test_runner import CapturingAdapter
from modeling_team.runner import TeamRunner


def seed(tmp_path, *, data=True):
    root = tmp_path / "source"
    _write_json(root / "evidence/stage.json", {"stage": "saved"})
    _write_json(root / "state.json", {"state": "CLEANED"})
    package = _bound_package()
    if data:
        package.platform_data = {
            "digest": "snapshot-digest",
            "project_id": "proj-r3015",
            "ontology_ids": ["onto-r3015"],
            "completed_operations": [],
            "secret_fixture": "HOST-PRIVATE-ONLY",
        }
    saved = save_checkpoint(root, package, source_run_id="source", configuration=CONFIGURATION)
    return root, package, saved


def plan(root, saved):
    def no_tail_read(*args):
        raise AssertionError("fork must not consult mutable source batches")

    return prepare_fork_plan(
        source_run_root=root,
        checkpoint_id=saved["checkpoint_id"],
        new_run_id="fork-new",
        repository_root=REPO_ROOT,
        readback=PlatformReadback(no_tail_read, "test"),
        authorization_reference="test-authorization",
        fork_reason="unreconciled old chain",
    )


def test_fork_reads_snapshot_not_later_unknown_tail(tmp_path):
    root, package, saved = seed(tmp_path)
    _seed_chain_intent(
        root,
        1,
        key="later-unknown",
        client_batch_id="later",
        session_id="old-session",
        status="unknown",
        with_receipt=False,
    )
    recovered, snapshot = plan(root, saved)
    assert snapshot == package.platform_data
    assert recovered.scope["project_id"] != "proj-r3015"
    assert recovered.scope["ontology_ids"] != ["onto-r3015"]
    assert recovered.origin["root_run_id"] == "fork-new"
    assert "HOST-PRIVATE-ONLY" not in json.dumps(recovered.role_packets)
    assert recovered.origin["old_chain_writes"] == "unchanged; no reconciliation claim"


def test_snapshot_dedup_and_tamper_detection(tmp_path):
    root, package, saved = seed(tmp_path)
    same = save_checkpoint(root, package, source_run_id="source", configuration=CONFIGURATION)
    assert same["status"] == "reused"
    package.platform_data = {**package.platform_data, "digest": "new-snapshot"}
    changed = save_checkpoint(root, package, source_run_id="source", configuration=CONFIGURATION)
    assert changed["checkpoint_id"] != saved["checkpoint_id"]
    path = root / "checkpoints" / saved["checkpoint_id"] / PLATFORM_DATA_PATH
    assert path.stat().st_mode & 0o077 == 0
    path.write_text("{}")
    with pytest.raises(CheckpointError) as error:
        plan(root, saved)
    assert error.value.reason_code == "artifact_changed"


def test_old_checkpoint_cannot_fork(tmp_path):
    root, _, saved = seed(tmp_path, data=False)
    with pytest.raises(CheckpointError) as error:
        plan(root, saved)
    assert error.value.reason_code == "checkpoint_data_missing"


def test_fork_ends_old_write_chain(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    fork = tmp_path / "fork"
    _write_json(
        fork / "recovery/origin.json",
        {
            "schema_version": "r3-0-017-fork/v1",
            "source_run_id": "old",
            "root_run_id": "fork",
        },
    )
    later = tmp_path / "later"
    _write_json(later / "recovery/origin.json", {"source_run_id": "fork", "root_run_id": "fork"})
    assert origin_chain_roots(later, tmp_path) == [fork, later]


def test_runner_captures_and_prepares_fork_with_new_scope(monkeypatch):
    from modeling_team import checkpoint_data
    from uuid import UUID, uuid5

    calls = []
    snapshot = {
        "digest": "snapshot",
        "project_id": "project",
        "ontology_ids": ["ontology"],
        "completed_operations": [],
    }

    def platform(base, key, action, payload):
        calls.append(action)
        if action == "capture":
            assert payload == {"project_id": "project", "ontology_ids": ["ontology"]}
            return snapshot
        project = payload["target_project_id"]
        return {
            "project_id": project,
            "ontology_ids": [str(uuid5(UUID(project), "ontology"))],
            "source_project_id": "project",
            "snapshot_digest": "snapshot",
            "identity_mapping": {},
        }

    monkeypatch.setattr(checkpoint_data, "platform_data_request", platform)
    source = _CheckpointRunner()
    target_id = "r3017-fork-" + os.urandom(4).hex()
    target = None
    try:
        runner = source.prepare()
        runner.scope = SimpleNamespace(project_id="project", ontology_ids=["ontology"])
        runner.canonical_admin_key = "test-host-key"
        frozen = _freeze(runner)
        runner.scope = None
        runner.cleanup()
        target = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=RUNS_ROOT / (target_id + "-ledger"),
            freeze_started_at=datetime.now(UTC).isoformat(),
            canonical_admin_key="test-host-key",
        )
        target.prepare_from_checkpoint(
            source_run_root=source.run_root,
            checkpoint_id="cq_frozen-0001",
            new_run_id=target_id,
            readback=PlatformReadback(lambda *args: (404, None), "test"),
            authorization_reference="test",
            fork_reason="old chain cannot reconcile",
        )
        assert calls == ["capture", "fork"]
        assert target.run.scope["project_id"] != "project"
        assert target.run.scope["fork_created_by_run"] == target_id
        assert target._cq_freeze["snapshot_digest"] == frozen["snapshot_digest"]
        origin = json.loads((target.run.root / "recovery/origin.json").read_text())
        assert origin["root_run_id"] == target_id
        assert origin["platform_fork"]["project_id"] == target.run.scope["project_id"]
        assert "fork_pending" not in origin
        assert "fork_scope" in target._task_text("modeling")
        assert "platform-data.json" not in target._task_text("modeling")
    finally:
        source.runner.scope = None
        source.cleanup()
        if target is not None and target.run is not None:
            target.cleanup()
        rmtree(RUNS_ROOT / target_id, ignore_errors=True)
        rmtree(RUNS_ROOT / (target_id + "-ledger"), ignore_errors=True)
