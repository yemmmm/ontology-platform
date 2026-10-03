"""Independent capture/restore checks on synthetic conclusion revision chains."""

from __future__ import annotations

import pytest

from modeling_team.checkpoint_recovery import restore_checkpoint_artifacts
from modeling_team.checkpoints import (
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    file_digest,
    public_role_projection,
)
from modeling_team.staged_decisions import staged_artifact_issues, staged_decision_artifact_paths
from modeling_team.tests.test_r30015_checkpoints import (
    _CheckpointRunner,
    _conclusion_entry,
    _conclusions,
    _confirmed_entry,
    _outer_save,
    _read_manifest,
    _settled_apply_intent,
    _tree_state,
    _write_json,
)


@pytest.mark.parametrize("has_history", [True, False])
def test_capture_save_restore_keeps_real_archive_or_reports_missing_history(tmp_path, has_history):
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        root = runner.run.root
        _settled_apply_intent(runner)
        paths = staged_decision_artifact_paths(root)
        ids = [f"independent-{number}" for number in range(7)]
        _write_json(
            paths["conclusions"],
            _conclusions(
                [_confirmed_entry(conclusion_id=identity, revision=5) for identity in ids]
            ),
        )
        expected = []
        if has_history:
            for identity in ids:
                for revision in range(1, 5):
                    p = paths["conclusions_archive_dir"] / f"{identity}.r{revision}.json"
                    _write_json(
                        p,
                        _conclusion_entry(
                            conclusion_id=identity, revision=revision, status="analyzed"
                        ),
                    )
                    expected.append(p.relative_to(root).as_posix())
        # A plausible-looking archive symlink may not substitute for original bytes.
        paths["conclusions_archive_dir"].mkdir(parents=True, exist_ok=True)
        symlink = paths["conclusions_archive_dir"] / f"{ids[0]}.r9.json"
        symlink.symlink_to(paths["conclusions"])
        original_bytes = {p: (root / p).read_bytes() for p in expected}
        current_bytes = paths["conclusions"].read_bytes()
        result = _outer_save(runner, CHECKPOINT_KIND_MATERIALIZATION_PROGRESS)
        manifest = _read_manifest(root, result["checkpoint_id"])
        archives = {
            a["source"]: a for a in manifest["artifacts"] if "conclusions-archive/" in a["source"]
        }
        assert set(archives) == set(expected)
        assert symlink.relative_to(root).as_posix() not in archives
        assert len(archives) == (28 if has_history else 0)
        model_view = public_role_projection(manifest, "modeling")
        visible = {a["source"] for a in model_view["visible_artifacts"]}
        assert set(expected).issubset(visible)
        for source, artifact in archives.items():
            assert artifact["owner"] == "modeling"
            assert artifact["host_private"] is False
            assert artifact["digest"] == file_digest(root / source)

        before = _tree_state(root)
        restored = tmp_path / "independent-restored"
        restore_checkpoint_artifacts(manifest, root, restored)
        assert _tree_state(root) == before
        assert paths["conclusions"].read_bytes() == current_bytes
        assert (
            restored / "value-semantics/conclusions/analysis-conclusions.json"
        ).read_bytes() == current_bytes
        assert {source: (restored / source).read_bytes() for source in expected} == original_bytes
        assert not (restored / symlink.relative_to(root)).exists()
        issues = staged_artifact_issues(restored)
        if has_history:
            assert issues == ()
        else:
            # No archive is manufactured by saving or restoring current r5 data.
            assert not list((restored / "value-semantics/conclusions-archive").glob("*.json"))
            assert len(issues) == 7
            assert {issue.reason_code for issue in issues} == {"conclusions_revision_regression"}
    finally:
        harness.cleanup()
