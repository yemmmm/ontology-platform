"""R2.3-008 deterministic regression: per-home Codex models-cache seeding.

Defect (start3, runtime/infrastructure): with no usable ``models_cache.json``
entry, Codex 0.147.0's ``thread/start`` runs an online models refresh whose
slow-path abort (``timeout waiting for child process to exit``) races between a
tolerated fallback and a fatal JSON-RPC ``-32603`` — the third started role hit
the fatal branch.  Seeding a version-matched, fresh cache entry per agent home
makes the ``online_if_uncached`` strategy hit the cache and skip the refresh
entirely.  These tests pin the seeding behavior without launching any binary.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tomllib
import pytest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, repository_root
from modeling_team.model_routing import RoleModelBinding, load_team_model_profile
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

ROOT = repository_root()

_SNAPSHOT_PATH = ROOT / "modeling_team" / "references" / "codex-models-cache-0.147.0.json"


def _adapter() -> CodexRuntimeAdapter:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-luna-medium")
    return adapter


def _formal_run(root: Path) -> SimpleNamespace:
    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        (root / "sources" / role).mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        run_id="r23008-run",
        formal_contract=SimpleNamespace(requirement_id="R2.3-008"),
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r2-3-008-formal-acceptance"),
            profile=SimpleNamespace(profile_id="r2-3-008-modeling-team"),
        ),
        acceptance=None,
        scope={"mode": "create"},
    )


def _agent(root: Path, role: str) -> _Agent:
    home, work, skills = (
        root / f"{role}-home",
        root / f"{role}-work",
        root / f"{role}-skills",
    )
    for path in (home, work, skills):
        path.mkdir(parents=True)
        path.chmod(0o700)
    return _Agent(role, _load_package(ROOT, role), home, work, skills)


def test_snapshot_is_secret_free_and_version_labeled() -> None:
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snapshot["client_version"] == "0.147.0"
    slugs = {entry["slug"] for entry in snapshot["models"]}
    # The frozen formal route model must be covered by the snapshot.
    assert "gpt-5.6-luna" in slugs
    raw = _SNAPSHOT_PATH.read_text(encoding="utf-8")
    # Infrastructure metadata only: no credential-shaped keys or opaque blobs.
    for forbidden in ("auth.json", "Bearer ", "access_token", "refresh_token"):
        assert forbidden not in raw


def test_builtin_projection_seeds_fresh_models_cache(tmp_path: Path) -> None:
    adapter = _adapter()
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
    run = _formal_run(tmp_path / "run")
    try:
        for role in ("coordinator", "modeling", "protocol"):
            agent = _agent(tmp_path, role)
            adapter._write_config(run, agent)
            cache_path = agent.home / "models_cache.json"
            assert cache_path.is_file(), role
            seeded = json.loads(cache_path.read_text(encoding="utf-8"))
            snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            # Model metadata is the official snapshot verbatim...
            assert seeded["models"] == snapshot["models"], role
            assert seeded["client_version"] == "0.147.0", role
            # ...only the freshness stamp is launch-relative so the
            # online_if_uncached strategy hits the cache instead of refreshing.
            fetched = datetime.fromisoformat(seeded["fetched_at"].replace("Z", "+00:00"))
            assert fetched.tzinfo == timezone.utc, role
            assert (datetime.now(timezone.utc) - fetched).total_seconds() < 600, role
            assert not stat.S_IMODE(cache_path.stat().st_mode) & 0o077, role
            # Seeding must not disturb the corrected config projection.
            parsed = tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
            assert parsed["model_provider"] == "openai", role
            assert "features" in parsed, role
    finally:
        adapter.stop()


def test_seed_skips_models_missing_from_snapshot(tmp_path: Path) -> None:
    adapter = _adapter()
    agent = _agent(tmp_path, "coordinator")
    adapter._seed_models_cache(agent.home, "gpt-not-in-snapshot")
    assert not (agent.home / "models_cache.json").exists()
    adapter.stop()


class _ChildProcessLaunchSentinel(RuntimeError):
    pass


def _launch_formal_source_child(tmp_path: Path, binding: RoleModelBinding | None) -> dict:
    """Drive ``_launch_acceptance_child_impl`` through the config write.

    ``process_factory`` raises a sentinel so the child never spawns a real
    app-server; everything up to that point (private tree, config.toml, models
    cache seeding) is the real filesystem path a formal Examiner child takes.
    """

    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-luna-medium")
    if binding is not None:
        adapter._validated_formal_role_binding = lambda _package_id: binding  # type: ignore[method-assign]
        if binding.provider_id != "openai-codex":
            adapter._provider_sessions = SimpleNamespace(  # type: ignore[assignment]
                base_url_for=lambda _pid: "http://127.0.0.1:65535"
            )
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
    adapter.process_factory = lambda *_args, **_kwargs: (_ for _ in ()).throw(  # type: ignore[assignment]
        _ChildProcessLaunchSentinel()
    )
    private_root = tmp_path / "private-root"
    private_root.mkdir(mode=0o700)
    private_input = tmp_path / "input.json"
    private_input.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()
    spec = {
        "kind": "source",
        "task_id": "r2-3-008-formal-acceptance",
        "private_root": str(private_root),
        "private_input": str(private_input),
        "child_handle_digest": digest,
    }
    try:
        with pytest.raises(_ChildProcessLaunchSentinel):
            adapter._launch_acceptance_child_impl(spec)
    finally:
        sink = spec.get("_runtime_report_sink")
        stopper = getattr(sink, "stop", None)
        if callable(stopper):
            stopper()
        socket_root = spec.get("_runtime_socket_root")
        if isinstance(socket_root, str):
            shutil.rmtree(socket_root, ignore_errors=True)
        adapter.stop()
    return spec


def test_formal_builtin_child_seeds_models_cache_in_child_home(tmp_path: Path) -> None:
    # R2.3-008 R5-D1: the fresh Examiner child home runs the same thread/start
    # models lookup after semantic_start, so the builtin child route must be
    # seeded exactly like the persistent roles.
    spec = _launch_formal_source_child(tmp_path, binding=None)
    home = Path(spec["private_root"]) / "home"
    cache_path = home / "models_cache.json"
    assert cache_path.is_file()
    seeded = json.loads(cache_path.read_text(encoding="utf-8"))
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert seeded["models"] == snapshot["models"]
    assert seeded["client_version"] == "0.147.0"
    fetched = datetime.fromisoformat(seeded["fetched_at"].replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - fetched).total_seconds() < 600
    config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    assert config["model_provider"] == "openai"


def test_external_credential_child_does_not_seed_models_cache(tmp_path: Path) -> None:
    binding = RoleModelBinding(
        package_id="source-examiner",
        provider_id="deepseek-direct",
        model="deepseek-chat",
        requested_effort="max",
        effective_effort="max",
    )
    spec = _launch_formal_source_child(tmp_path, binding=binding)
    home = Path(spec["private_root"]) / "home"
    assert not (home / "models_cache.json").exists()


def test_unknown_slug_child_does_not_seed_models_cache(tmp_path: Path) -> None:
    binding = RoleModelBinding(
        package_id="source-examiner",
        provider_id="openai-codex",
        model="gpt-not-in-snapshot",
        requested_effort="medium",
        effective_effort="medium",
    )
    spec = _launch_formal_source_child(tmp_path, binding=binding)
    home = Path(spec["private_root"]) / "home"
    assert not (home / "models_cache.json").exists()
