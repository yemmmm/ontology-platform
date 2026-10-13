"""Checkpoint capture credential ownership; no platform or model process starts."""

from types import SimpleNamespace

import pytest

from modeling_team import checkpoint_data
from modeling_team.checkpoints import CHECKPOINT_KIND_PRODUCTION_HANDOFF, CheckpointError
from modeling_team.platform_scope import PlatformScope
from modeling_team.runner import CQWriteAdmission, TeamRunner


@pytest.fixture
def capture_runner(monkeypatch, tmp_path):
    runner = object.__new__(TeamRunner)
    runner._modeling_checkpoints = True
    runner.run = SimpleNamespace(root=tmp_path, run_id="capture-test")
    runner.canonical_base_url = "http://example"
    runner.canonical_admin_key = "revoked-launch-key"
    runner._cq_write_admission = CQWriteAdmission()
    runner._checkpoint_write_positions = lambda _: {"positions": [], "unknown": []}
    runner._checkpoint_configuration = lambda: {}
    package = SimpleNamespace(
        platform_bindings={"project_id": "project", "ontology_ids": ["ontology"]},
        scope_refs={},
    )
    runner._collect_checkpoint_stage = lambda *_: package
    events, saved = [], []
    runner._append_evidence = lambda name, event: events.append((name, event))

    def save(*args, **kwargs):
        saved.append(package.platform_data)
        return {
            "status": "saved",
            "checkpoint_id": "test",
            "manifest_digest": "digest",
            "artifact_count": 1,
        }

    monkeypatch.setattr("modeling_team.runner.save_checkpoint", save)
    return runner, saved


def scope_with_credentials(active_key, calls):
    def bootstrap():
        calls.append(("bootstrap",))
        return "temporary-capture-key", "temporary-capture-id"

    def revoke(key_id):
        calls.append(("revoke", key_id))
        return True

    return PlatformScope(
        "http://example",
        "capture-test",
        bootstrap,
        revoke,
        admin_key=active_key,
        admin_key_id="live-scope-id" if active_key else None,
    )


@pytest.mark.parametrize("sealed", [False, True])
def test_capture_uses_scope_owned_credentials_after_launch_key_expires(
    capture_runner,
    monkeypatch,
    sealed,
):
    runner, saved = capture_runner
    calls = []
    runner.scope = scope_with_credentials(None if sealed else "live-scope-key", calls)
    before = (runner.scope.admin_key, runner.scope.admin_key_id, runner.scope.protocol_key)
    if sealed:
        runner.scope._work_seal = {"write_credentials_non_active": True}
        runner._cq_write_admission.begin_quiescing()
        runner._cq_write_admission.enter_read_only()

    def capture(base, key, action, payload):
        assert base == "http://example" and action == "capture"
        assert payload == {"project_id": "project", "ontology_ids": ["ontology"]}
        calls.append(("capture", key))
        return {"digest": "snapshot"}

    monkeypatch.setattr(checkpoint_data, "platform_data_request", capture)
    runner._save_run_checkpoint_captured(CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="test")

    expected = [("capture", "live-scope-key")]
    if sealed:
        expected = [
            ("bootstrap",),
            ("capture", "temporary-capture-key"),
            ("revoke", "temporary-capture-id"),
        ]
    assert calls == expected
    assert saved == [{"digest": "snapshot"}]
    assert before == (runner.scope.admin_key, runner.scope.admin_key_id, runner.scope.protocol_key)
    assert runner.canonical_admin_key == "revoked-launch-key"
    if sealed:
        assert runner._cq_write_admission.snapshot()["phase"] == "read-only"
        assert runner.scope._work_seal == {"write_credentials_non_active": True}


def test_temporary_capture_key_is_revoked_when_capture_fails(capture_runner, monkeypatch):
    runner, saved = capture_runner
    calls = []
    runner.scope = scope_with_credentials(None, calls)
    failure = CheckpointError("checkpoint_data_unavailable", "capture failed", obj="platform_data")

    def capture(*args):
        raise failure

    monkeypatch.setattr(checkpoint_data, "platform_data_request", capture)
    with pytest.raises(CheckpointError) as caught:
        runner._save_run_checkpoint_captured(CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="test")
    assert caught.value is failure
    assert calls == [("bootstrap",), ("revoke", "temporary-capture-id")]
    assert saved == []
    assert runner.scope.admin_key is None


def test_explicit_canonical_only_capture_still_works(capture_runner, monkeypatch):
    runner, saved = capture_runner
    runner.scope = None
    runner.canonical_admin_key = "explicit-host-key"

    def capture(base, key, action, payload):
        assert key == "explicit-host-key"
        return {"digest": "snapshot"}

    monkeypatch.setattr(checkpoint_data, "platform_data_request", capture)
    runner._save_run_checkpoint_captured(CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="test")
    assert saved == [{"digest": "snapshot"}]


def test_capture_bootstrap_failure_remains_a_recoverable_checkpoint_failure(capture_runner):
    runner, saved = capture_runner
    runner.scope = scope_with_credentials(None, [])

    def bootstrap():
        raise RuntimeError("operator unavailable")

    runner.scope.bootstrap_admin = bootstrap
    with pytest.raises(CheckpointError) as caught:
        runner._save_run_checkpoint_captured(CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="test")
    assert caught.value.reason_code == "checkpoint_data_credentials_missing"
    assert caught.value.retryable is True
    assert saved == []


def test_unconfirmed_temporary_key_revocation_does_not_publish_checkpoint(
    capture_runner,
    monkeypatch,
):
    runner, saved = capture_runner
    runner.scope = scope_with_credentials(None, [])
    runner.scope.revoke_admin = lambda _: False
    monkeypatch.setattr(checkpoint_data, "platform_data_request", lambda *_: {"digest": "snapshot"})
    with pytest.raises(CheckpointError) as caught:
        runner._save_run_checkpoint_captured(CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="test")
    assert caught.value.reason_code == "checkpoint_data_unavailable"
    assert "revocation is unconfirmed" in caught.value.detail
    assert saved == []
