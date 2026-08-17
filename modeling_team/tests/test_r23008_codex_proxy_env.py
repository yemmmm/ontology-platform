"""R2.3-008 deterministic regression: Host proxy environment passthrough.

Defect (start5, runtime/infrastructure): this host reaches chatgpt.com only
through the local proxy (``http_proxy``/``https_proxy`` on 127.0.0.1:1080),
but ``_minimal_codex_process_env`` built an explicit minimal environment with
no proxy variables.  Codex 0.147.0's ``outbound_proxy_policy: ReqwestDefault``
then connected directly, so every sampling, analytics, and models request
timed out at the network layer in all four roles.  The fix forwards only the
Host's proxy variables (both cases) so reqwest uses the proxy while
``no_proxy`` keeps in-namespace loopback targets direct.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.contracts import _load_package, repository_root
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes.codex import (
    _PROXY_ENV_KEYS,
    CodexRuntimeAdapter,
    _Agent,
    _minimal_codex_process_env,
)

ROOT = repository_root()

_BASE_KEYS = {"CODEX_HOME", "HOME", "PATH", "TERM", "LANG", "LC_ALL"}


class _ChildProcessLaunchSentinel(RuntimeError):
    pass


def test_proxy_vars_forwarded_when_host_sets_them(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    # Both cases must travel: reqwest reads whichever the Host exported.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1080")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1080")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1")
    env = _minimal_codex_process_env(tmp_path)
    assert env["HTTP_PROXY"] == "http://127.0.0.1:1080"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:1080"
    assert env["NO_PROXY"] == "localhost,127.0.0.1,::1"
    assert "http_proxy" not in env and "https_proxy" not in env and "no_proxy" not in env


def test_proxy_vars_absent_when_host_sets_none(monkeypatch, tmp_path: Path) -> None:
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    env = _minimal_codex_process_env(tmp_path)
    assert set(env) == _BASE_KEYS
    # Empty values are never invented or forwarded.
    monkeypatch.setenv("http_proxy", "")
    env = _minimal_codex_process_env(tmp_path)
    assert set(env) == _BASE_KEYS


def test_proxy_passthrough_leaks_nothing_else(monkeypatch, tmp_path: Path) -> None:
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "formal-secret-sentinel")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-secret-sentinel")
    env = _minimal_codex_process_env(tmp_path)
    # Formal route: no provider key, no unrelated Host variable crosses over.
    assert "DEEPSEEK_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert set(env) == _BASE_KEYS
    non_formal = _minimal_codex_process_env(tmp_path, "deepseek-key")
    assert non_formal["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert set(non_formal) == _BASE_KEYS | {"DEEPSEEK_API_KEY"}


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


def test_persistent_start_process_env_carries_proxy_vars(monkeypatch, tmp_path: Path) -> None:
    # Call site 1: ``_start_process`` (persistent roles).
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1080")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:1080")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,::1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    captured: list[dict] = []

    def process_factory(_command, **kwargs):
        captured.append(kwargs["env"])
        raise _ChildProcessLaunchSentinel()

    adapter = CodexRuntimeAdapter(
        repository_root=ROOT, use_bwrap=False, process_factory=process_factory
    )
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-luna-medium")
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
    agent = _agent(tmp_path, "coordinator")
    adapter.agents[agent.agent_id] = agent
    run = SimpleNamespace(
        root=tmp_path / "run",
        run_id="r23008-proxy",
        formal_contract=SimpleNamespace(requirement_id="R2.3-008"),
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r2-3-008-formal-acceptance"),
            profile=SimpleNamespace(profile_id="r2-3-008-modeling-team"),
        ),
        acceptance=None,
        scope={"mode": "create"},
    )
    (tmp_path / "run" / "sources" / "coordinator").mkdir(parents=True)
    try:
        adapter._write_config(run, agent)
        with pytest.raises(_ChildProcessLaunchSentinel):
            adapter._start_process(agent)
    finally:
        adapter.stop()
    assert captured, "process env was never captured"
    env = captured[0]
    assert env["http_proxy"] == "http://127.0.0.1:1080"
    assert env["https_proxy"] == "http://127.0.0.1:1080"
    assert env["no_proxy"] == "localhost,127.0.0.1,::1"
    # Formal mode keeps its existing guarantee despite the Host variable.
    assert "DEEPSEEK_API_KEY" not in env


def test_acceptance_child_env_carries_proxy_vars(monkeypatch, tmp_path: Path) -> None:
    # Call site 2: ``_launch_acceptance_child_impl`` (fresh Examiner children).
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1080")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,::1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    captured: list[dict] = []

    def process_factory(_command, **kwargs):
        captured.append(kwargs["env"])
        raise _ChildProcessLaunchSentinel()

    adapter = CodexRuntimeAdapter(
        repository_root=ROOT, use_bwrap=False, process_factory=process_factory
    )
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-luna-medium")
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
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
    assert captured, "child process env was never captured"
    env = captured[0]
    assert env["http_proxy"] == "http://127.0.0.1:1080"
    assert env["no_proxy"] == "localhost,127.0.0.1,::1"
    assert "DEEPSEEK_API_KEY" not in env
