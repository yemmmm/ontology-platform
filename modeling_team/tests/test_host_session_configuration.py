"""R4.0-019 host launch overrides and actual isolated Codex config generation.

Launch fixtures never run a business Team, call a model or touch the platform.
Config subprocesses stop at the existing pre-process fixture sentinel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from modeling_team import host_ops


class _ExitedProcess:
    pid = 424242

    def wait(self, timeout=None):
        return 0


def _launch(tmp_path, monkeypatch, entry, tier, launcher):
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, "fixture-admin-never-record")
    # Retain the registration deterministically for assertions; no real child.
    monkeypatch.setattr(host_ops, "_spawn_exit_reaper", lambda *_args: None)
    common = dict(
        repository_root=tmp_path,
        launcher=launcher,
        service_tier=tier,
        run_root_wait_seconds=0,
    )
    if entry == "start":
        return host_ops.start_run(
            run_id="new-run", task="task.yaml", profile="profile.yaml",
            scope="scope.yaml", model_profile="openai-sol-medium",
            freeze_started_at="2026-10-04T00:00:00+00:00", **common,
        )
    args = dict(
        source_run_id="source", checkpoint_id="production_handoff-0001",
        new_run_id="new-run", authorization_reference="fixture-auth",
    )
    if entry == "production":
        args.update(mode="production", freeze_started_at="2026-10-04T00:00:00+00:00")
    else:
        args.update(mode="acceptance", question_visibility=entry,
                    model_profile="openai-sol-medium")
    return host_ops.resume_from_checkpoint(**args, **common)


@pytest.mark.parametrize("entry", ["start", "production", "public", "hidden"])
@pytest.mark.parametrize("tier", ["unset", "fast", "default"])
@pytest.mark.parametrize("ambient", [None, "fast"])
def test_per_launch_env_and_record_are_explicit_and_local(
    tmp_path, monkeypatch, entry, tier, ambient,
):
    if ambient is None:
        monkeypatch.delenv("MODELING_TEAM_CODEX_SERVICE_TIER", raising=False)
    else:
        monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", ambient)
    source = tmp_path / "workspaces/modeling-runs/source"
    source.mkdir(parents=True)
    retained = source / "state.json"
    retained.write_text('{"state":"CLEANED"}')
    source_bytes = retained.read_bytes()
    captured = []

    def launcher(argv, **kwargs):
        captured.append((argv, kwargs["env"]))
        return _ExitedProcess()

    _launch(tmp_path, monkeypatch, entry, tier, launcher)
    argv, env = captured[0]
    expected = ambient if tier == "unset" else ("fast" if tier == "fast" else None)
    assert env.get("MODELING_TEAM_CODEX_SERVICE_TIER") == expected
    assert os.environ.get("MODELING_TEAM_CODEX_SERVICE_TIER") == ambient
    record_path, _ = host_ops.launch_record_path("new-run", repository_root=tmp_path)
    record = json.loads(record_path.read_text())
    assert record["service_tier"] == tier
    assert "fixture-admin-never-record" not in record_path.read_text()
    assert "env" not in record
    assert "--service-tier" not in argv  # no invented CLI flag
    if entry == "production":
        assert "--model-profile" not in argv  # bound source profile
    else:
        assert argv[argv.index("--model-profile") + 1] == "openai-sol-medium"
    assert retained.read_bytes() == source_bytes


CONFIG_SCRIPT = """
import sys
from pathlib import Path
from modeling_team.model_routing import load_team_model_profile
from modeling_team.tests import test_r23008_codex_builtin_config as fixture
root = Path(sys.argv[1])
base_adapter = fixture._adapter
def adapter():
    item = base_adapter()
    item._team_model_profile = load_team_model_profile(fixture.ROOT, 'openai-sol-medium')
    return item
fixture._adapter = adapter
for role in ('coordinator', 'modeling', 'protocol', 'acceptance'):
    target = root / role
    target.mkdir(parents=True)
    item, _ = fixture._write_builtin_config(target, role)
    item.stop()
for kind in ('source', 'platform', 'acceptance'):
    target = root / (kind + '-child')
    target.mkdir(parents=True)
    fixture._write_child_config(target, kind, 'openai-codex')
"""


def _generate_configs(root: Path, env: dict[str, str]):
    # A real isolated Python process sees the exact env captured at the host
    # boundary, so ambient fast in this test process cannot leak into it.
    result = subprocess.run(
        [sys.executable, "-c", CONFIG_SCRIPT, str(root)],
        cwd=host_ops.default_repository_root(), env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    configs = list(root.rglob("config.toml"))
    assert len(configs) == 7
    return configs


@pytest.mark.parametrize("ambient", [None, "fast"])
@pytest.mark.parametrize("tier", ["unset", "fast", "default"])
def test_launch_env_generates_actual_seven_role_tomls(tmp_path, monkeypatch, ambient, tier):
    if ambient is None:
        monkeypatch.delenv("MODELING_TEAM_CODEX_SERVICE_TIER", raising=False)
    else:
        monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", ambient)
    captured = []

    def launcher(argv, **kwargs):
        captured.append(kwargs["env"])
        return _ExitedProcess()

    _launch(tmp_path, monkeypatch, "start", tier, launcher)
    configs = _generate_configs(tmp_path / "generated", captured[0])
    expected_fast = tier == "fast" or (tier == "unset" and ambient == "fast")
    for path in configs:
        parsed = tomllib.loads(path.read_text())
        assert parsed["model"] == "gpt-6.1-sol"
        assert parsed["model_reasoning_effort"] == "medium"
        if expected_fast:
            assert parsed["service_tier"] == "fast"
            assert parsed["features"]["fast_mode"] is True
        else:
            assert "service_tier" not in parsed
            assert "fast_mode" not in parsed["features"]
    assert os.environ.get("MODELING_TEAM_CODEX_SERVICE_TIER") == ambient


def test_new_default_configs_do_not_rewrite_old_fast_thread_configs(tmp_path):
    fast_env = dict(os.environ, MODELING_TEAM_CODEX_SERVICE_TIER="fast")
    old_configs = _generate_configs(tmp_path / "old", fast_env)
    before = {path: path.read_bytes() for path in old_configs}
    default_env = dict(fast_env)
    default_env.pop("MODELING_TEAM_CODEX_SERVICE_TIER")
    for path in _generate_configs(tmp_path / "new", default_env):
        assert "service_tier" not in tomllib.loads(path.read_text())
    assert all(path.read_bytes() == content for path, content in before.items())


def test_invalid_service_tier_is_retryable_and_never_launches(tmp_path, monkeypatch):
    with pytest.raises(host_ops.HostOpError) as exc:
        _launch(tmp_path, monkeypatch, "start", "normal", lambda *_a, **_kw: pytest.fail())
    assert exc.value.code == "launch_arguments_invalid"
    assert exc.value.obj == "service_tier"
    assert exc.value.retryable
    assert not (tmp_path / "workspaces/modeling-runs/.host-launches").exists()
