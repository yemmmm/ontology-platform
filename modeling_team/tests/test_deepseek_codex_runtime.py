from __future__ import annotations

import json
import tomllib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS
from modeling_team.contracts import _load_package, repository_root
from modeling_team.deepseek_provider_proxy import DeepSeekProviderProxy
from modeling_team.deepseek_provider_proxy import preflight_deepseek_credential
from modeling_team.model_manifest import (
    FORMAL_MODEL_PACKAGE_IDS,
    FORMAL_MODEL_TUPLE,
    load_formal_model_manifest,
)
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter,
    CodexRuntimeError,
    _Agent,
)


class _Process:
    def __init__(self, command: list[str], kwargs: dict[str, object]) -> None:
        self.command = command
        self.kwargs = kwargs
        self.pid = 0
        self.stdin = None
        self.stdout = None

    def poll(self) -> int:
        return 0


def _formal_run(root: Path) -> SimpleNamespace:
    for role in ("coordinator", "modeling", "protocol"):
        (root / "sources" / role).mkdir(parents=True)
    (root / "sources" / "acceptance").mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        run_id="deepseek-run",
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance")
        ),
        acceptance=None,
    )


def _agent(root: Path, role: str) -> _Agent:
    home, work, skills = (root / f"{role}-home", root / f"{role}-work", root / f"{role}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True)
        path.chmod(0o700)
    return _Agent(role, _load_package(repository_root(), role), home, work, skills)


def test_formal_persistent_configs_and_process_env_cover_all_four_roles(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository_root()
    run = _formal_run(tmp_path / "run")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def process_factory(command: list[str], **kwargs: object) -> _Process:
        calls.append((command, kwargs))
        return _Process(command, kwargs)

    adapter = CodexRuntimeAdapter(
        repository_root=repo,
        use_bwrap=False,
        process_factory=process_factory,
    )
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = load_formal_model_manifest(repo)
    proxy = DeepSeekProviderProxy(b"formal-secret")
    proxy.start()
    adapter._formal_provider_proxy = proxy
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)
        adapter._write_config(run, agent)
        config = (agent.home / "config.toml").read_text(encoding="utf-8")
        assert 'model = "deepseek-v4-flash"' in config
        assert 'model_provider = "deepseek"' in config
        assert 'model_reasoning_effort = "max"' in config
        assert "base_url = \"http://127.0.0.1:" in config
        assert 'env_key = "DEEPSEEK_API_KEY"' not in config
        assert "process-secret" not in config
        adapter._start_process(agent)
        env = calls[-1][1]["env"]
        assert "DEEPSEEK_API_KEY" not in env
        assert not (agent.home / "auth.json").exists()
        assert agent.auth_path is None
        assert agent.credential_mode == "provider_proxy"

    assert len(calls) == 4
    for command, kwargs in calls:
        assert "process-secret" not in " ".join(command)
        assert kwargs["env"]["PATH"] == "/usr/local/bin:/usr/bin:/bin"
        assert kwargs["env"]["TERM"] == "xterm-256color"
        assert kwargs["env"]["LANG"] == "C.UTF-8"
        assert kwargs["env"]["LC_ALL"] == "C.UTF-8"
    adapter.stop()
    proxy.stop()


def test_formal_config_is_parseable_with_one_model_binding(tmp_path: Path) -> None:
    repo = repository_root()
    run = _formal_run(tmp_path / "run")
    adapter = CodexRuntimeAdapter(repository_root=repo, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = load_formal_model_manifest(repo)
    proxy = DeepSeekProviderProxy(b"formal-secret")
    proxy.start()
    adapter._formal_provider_proxy = proxy
    agent = _agent(tmp_path, "coordinator")
    try:
        adapter._write_config(run, agent)
        parsed = tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
    finally:
        adapter.stop()
        proxy.stop()

    assert parsed["model"] == "deepseek-v4-flash"
    assert parsed["model_provider"] == "deepseek"
    assert parsed["model_reasoning_effort"] == "max"
    assert parsed["model_providers"]["deepseek"]["wire_api"] == "responses"


def test_formal_startup_exception_unwinds_and_wipes_provider_proxy(
    monkeypatch, tmp_path: Path
) -> None:
    credential = tmp_path / "deepseek.env"
    credential.write_text("DEEPSEEK_API_KEY=startup-sentinel\n", encoding="utf-8")
    credential.chmod(0o600)
    run = _formal_run(tmp_path / "run")
    run.model_manifest = load_formal_model_manifest(repository_root())
    run.deepseek_credential_binding = preflight_deepseek_credential(credential)
    created: list[DeepSeekProviderProxy] = []

    class _SpyProxy(DeepSeekProviderProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(
        "modeling_team.runtimes.codex.DeepSeekProviderProxy", _SpyProxy
    )
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
    monkeypatch.setattr(
        adapter,
        "_stage_skills",
        lambda _agent: (_ for _ in ()).throw(CodexRuntimeError("startup seam")),
    )

    with pytest.raises(CodexRuntimeError, match="startup seam"):
        adapter.start_roster(run, [_agent(run.root, "coordinator")])

    assert len(created) == 1
    assert created[0].secret_snapshot() == b""
    assert created[0].snapshot()["listening"] is False
    assert adapter._formal_provider_proxy is None
    assert adapter._secret_audit_values == []


@pytest.mark.parametrize("formal", [True, False])
def test_thread_start_model_binding_is_formal_only(
    monkeypatch, tmp_path: Path, formal: bool
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = formal
    if formal:
        adapter._formal_model_manifest = load_formal_model_manifest(repository_root())
    starts: dict[str, dict[str, object]] = {}

    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path / ("formal" if formal else "legacy"), role)

        def rpc(_agent: _Agent, method: str, params: dict[str, object]) -> dict[str, object]:
            if method == "skills/list":
                return {
                    "data": [
                        {
                            "skills": [
                                {
                                    "name": path.parent.name,
                                    "path": f"/skills/{path.parent.name}/SKILL.md",
                                    "enabled": True,
                                }
                                for path in agent.package.required_skills
                            ]
                        }
                    ]
                }
            if method == "thread/start":
                starts[role] = dict(params)
                return {"thread": {"id": f"thread-{role}"}}
            return {}

        adapter._rpc = rpc  # type: ignore[method-assign]
        adapter._require_expected_mcp_servers = lambda _agent: None  # type: ignore[method-assign]
        adapter._initialize(agent)

    assert set(starts) == {"coordinator", "modeling", "protocol", "acceptance"}
    if formal:
        assert {params["model"] for params in starts.values()} == {"deepseek-v4-flash"}
    else:
        assert all("model" not in params for params in starts.values())


def test_formal_model_binding_covers_all_six_packages() -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = load_formal_model_manifest(repository_root())

    assert {
        package_id: adapter._validated_formal_model_override(package_id)
        for package_id in FORMAL_MODEL_PACKAGE_IDS
    } == {package_id: FORMAL_MODEL_TUPLE for package_id in FORMAL_MODEL_PACKAGE_IDS}


def test_formal_model_binding_fails_closed_before_process_on_tuple_or_package_drift(
    tmp_path: Path,
) -> None:
    class DriftedManifest:
        def override_for(self, package_id: str) -> tuple[str, str, str]:
            if package_id == "coordinator":
                return ("gpt-5.5", "openai", "max")
            raise KeyError(package_id)

    calls: list[object] = []
    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(),
        use_bwrap=False,
        process_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = DriftedManifest()  # type: ignore[assignment]
    agent = _agent(tmp_path, "coordinator")

    with pytest.raises(CodexRuntimeError, match="tuple drifted"):
        adapter._start_process(agent)
    assert calls == []

    with pytest.raises(CodexRuntimeError, match="package binding"):
        adapter._validated_formal_model_override("platform-examiner")
    with pytest.raises(CodexRuntimeError, match="package binding"):
        adapter._validated_formal_model_override("unknown-package")


def test_formal_start_roster_ignores_ambient_deepseek_and_llm_sentinels(
    monkeypatch, tmp_path: Path
) -> None:
    credential = tmp_path / "formal-deepseek.env"
    credential.write_text("DEEPSEEK_API_KEY=file-only-sentinel\n", encoding="utf-8")
    credential.chmod(0o600)
    binding = preflight_deepseek_credential(credential)
    run = _formal_run(tmp_path / "run")
    run.model_manifest = load_formal_model_manifest(repository_root())
    run.deepseek_credential_binding = binding
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ambient-deepseek-sentinel")
    monkeypatch.setenv("LLM_API_KEY", "ambient-llm-sentinel")
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
    monkeypatch.setattr(
        adapter,
        "_resolve_deepseek_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("formal runtime resolved ambient key")),
    )
    assert adapter.start_roster(run, []) == []
    assert all(
        sentinel.encode() not in adapter._secret_audit_values
        for sentinel in ("ambient-deepseek-sentinel", "ambient-llm-sentinel")
    )
    assert adapter._formal_provider_proxy is not None
    assert adapter._formal_provider_proxy.base_url.startswith("http://127.0.0.1:")
    adapter.stop()


@pytest.mark.parametrize("kind", ["source", "platform"])
def test_formal_examiner_config_env_and_argv_are_secret_free(
    monkeypatch, tmp_path: Path, kind: str
) -> None:
    repo = repository_root()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "child-secret")
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def process_factory(command: list[str], **kwargs: object) -> _Process:
        calls.append((command, kwargs))
        return _Process(command, kwargs)

    adapter = CodexRuntimeAdapter(
        repository_root=repo,
        use_bwrap=False,
        process_factory=process_factory,
    )
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = load_formal_model_manifest(repo)
    proxy = DeepSeekProviderProxy(b"formal-secret")
    proxy.start()
    adapter._formal_provider_proxy = proxy
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)
    thread_starts: list[dict[str, object]] = []

    def rpc(_agent: _Agent, method: str, _params: dict[str, object]) -> dict[str, object]:
        if method == "thread/start":
            thread_starts.append(dict(_params))
            return {"thread": {"id": f"{kind}-thread"}}
        if method == "turn/start":
            return {"turn": {"id": f"{kind}-turn"}}
        if method == "mcpServerStatus/list":
            tools = [{"name": "submit_examiner_report"}]
            servers = [{"name": "examiner_report", "tools": tools}]
            if kind == "platform":
                servers.append(
                    {
                        "name": "platform_read_proxy",
                        "tools": [{"name": name} for name in PLATFORM_PROXY_READ_TOOLS],
                    }
                )
            return {"data": servers}
        return {}

    adapter._rpc = rpc  # type: ignore[method-assign]
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    (private_root / "input.json").write_text("{}", encoding="utf-8")
    spec: dict[str, object] = {
        "task_id": "r2-3-005-formal-acceptance",
        "acceptance_round_id": "round-1",
        "kind": kind,
        "attempt": 0,
        "session_id": "session-1",
        "child_handle_digest": "a" * 64,
        "ticket_digest": "b" * 64,
        "input_digest": "c" * 64,
        "private_root": str(private_root),
        "private_input": str(private_root / "input.json"),
        "descriptor": {"kind": f"{kind}_examiner", "package_digest": "d" * 64},
        "timeout_seconds": 30,
    }
    if kind == "platform":
        spec.update(
            {
                "read_key_id": "read-key",
                "read_key_digest": "e" * 64,
                "platform_read_scope": {
                    "project_id": "project",
                    "ontology_id": "ontology",
                    "graph_set_id": "graph",
                },
                "model_state_digest": "f" * 64,
                "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
                "read_key_plaintext": "platform-secret",
                "read_key_revoke": lambda _key: None,
            }
        )

    resource = adapter.acceptance_child_factory(spec)
    config = (private_root / "home" / "config.toml").read_text(encoding="utf-8")
    assert 'model = "deepseek-v4-flash"' in config
    assert 'model_provider = "deepseek"' in config
    assert 'model_reasoning_effort = "max"' in config
    assert "base_url = \"http://127.0.0.1:" in config
    assert 'env_key = "DEEPSEEK_API_KEY"' not in config
    assert "child-secret" not in config
    command, kwargs = calls[0]
    assert "child-secret" not in " ".join(command)
    assert "DEEPSEEK_API_KEY" not in kwargs["env"]
    # Formal first-turn barrier is a provider-proxy readiness transition; no
    # copied auth file exists and the ambient sentinel is not inspected.
    assert not (private_root / "home" / "auth.json").exists()
    assert len(thread_starts) == 1
    assert thread_starts[0]["model"] == "deepseek-v4-flash"
    assert "model_provider" not in thread_starts[0]
    assert "model_reasoning_effort" not in thread_starts[0]
    assert resource._child_agent is not None
    assert resource._child_agent.credential_mode == "provider_proxy"
    adapter._unlink_auth_barrier(resource._child_agent)
    assert resource._child_agent.provider_proxy_ready_monotonic is not None
    resource.destroy()
    proxy.stop()


def test_examiner_bwrap_inherits_minimal_parent_env_without_clearenv(monkeypatch, tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=True)
    monkeypatch.setattr(
        "modeling_team.runtimes.codex.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else "/usr/local/bin/codex",
    )
    home, work, skills, report = (tmp_path / value for value in ("home", "work", "skills", "report.sock"))
    for path in (home, work, skills):
        path.mkdir()
    report.touch()
    command = adapter._acceptance_namespace_command(
        home=home,
        work=work,
        skills=skills,
        proxy_socket=None,
        report_socket=report,
    )
    assert "--clearenv" not in command
    assert "DEEPSEEK_API_KEY" not in command


def test_command_approval_is_declined_with_sanitized_evidence_and_no_shell_execution(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    agent = _agent(tmp_path, "protocol")
    agent.process = SimpleNamespace(stdin=StringIO())
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._run_root = root
    secret = "do-not-retain-command-or-reason"

    adapter._notification(
        agent,
        {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-secret",
                "turnId": "turn-secret",
                "itemId": "item-secret",
                "command": f"/bin/sh -c {secret}",
                "cwd": "/private/cwd",
                "reason": secret,
            },
        },
    )

    response = json.loads(agent.process.stdin.getvalue())
    assert response == {"jsonrpc": "2.0", "id": 41, "result": {"decision": "decline"}}
    evidence = (root / "evidence" / "command-approval-events.jsonl").read_text(
        encoding="utf-8"
    )
    event = json.loads(evidence)
    assert event == {
        "agent_id": "protocol",
        "decision": "decline",
        "method": "item/commandExecution/requestApproval",
        "param_keys": ["command", "cwd", "itemId", "reason", "threadId", "turnId"],
    }
    assert secret not in evidence
    assert "/private/cwd" not in evidence


@pytest.mark.parametrize(
    "content",
    [
        "LLM_API_KEY=\n",
        "LLM_API_KEY = spaced\n",
        "export LLM_API_KEY=exported\n",
        "LLM_API_KEY=\"quoted\"\n",
        "OTHER=value\n",
    ],
)
def test_fallback_file_rejects_missing_or_malformed_assignment(tmp_path: Path, content: str) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    fallback = root / "backend" / ".env"
    fallback.write_text(content, encoding="utf-8")
    fallback.chmod(0o600)
    adapter = CodexRuntimeAdapter(repository_root=root)
    with pytest.raises(CodexRuntimeError):
        adapter._resolve_deepseek_api_key()


@pytest.mark.parametrize("mode", [0o640, 0o604])
def test_fallback_file_rejects_group_or_other_permissions(tmp_path: Path, mode: int) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    fallback = root / "backend" / ".env"
    fallback.write_text("LLM_API_KEY=fallback-secret\n", encoding="utf-8")
    fallback.chmod(mode)
    adapter = CodexRuntimeAdapter(repository_root=root)
    with pytest.raises(CodexRuntimeError, match="insecure"):
        adapter._resolve_deepseek_api_key()


def test_process_key_takes_precedence_over_fallback(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    fallback = root / "backend" / ".env"
    fallback.write_text("LLM_API_KEY=fallback-secret\n", encoding="utf-8")
    fallback.chmod(0o600)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    assert CodexRuntimeAdapter(repository_root=root)._resolve_deepseek_api_key() == "process-secret"


def test_formal_process_factory_does_not_resolve_deepseek_key(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    calls: list[object] = []

    def process_factory(*_args: object, **_kwargs: object) -> _Process:
        calls.append(True)
        return _Process([], _kwargs)

    adapter = CodexRuntimeAdapter(
        repository_root=root,
        use_bwrap=False,
        process_factory=process_factory,
    )
    adapter._coordination_enabled = True
    adapter._formal_model_manifest = load_formal_model_manifest(repository_root())
    monkeypatch.setattr(
        adapter,
        "_resolve_deepseek_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("formal DeepSeek resolver called")),
    )
    agent = _Agent(
        "coordinator",
        SimpleNamespace(role="coordinator", package_id="coordinator"),
        tmp_path / "home",
        tmp_path / "work",
        tmp_path / "skills",
    )
    process = adapter._start_process(agent)
    assert process is not None
    assert calls == [True]
    assert "DEEPSEEK_API_KEY" not in process.kwargs["env"]
