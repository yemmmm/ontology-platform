from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS
from modeling_team.contracts import _load_package, repository_root
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
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)
        adapter._write_config(run, agent)
        config = (agent.home / "config.toml").read_text(encoding="utf-8")
        assert 'model = "deepseek-v4-flash"' in config
        assert 'model_provider = "deepseek"' in config
        assert 'name = "DeepSeek"' in config
        assert 'base_url = "https://api.deepseek.com/"' in config
        assert 'wire_api = "responses"' in config
        assert 'env_key = "DEEPSEEK_API_KEY"' in config
        assert 'model_reasoning_effort = "max"' in config
        assert '[shell_environment_policy]' in config
        assert 'inherit = "core"' in config
        assert 'exclude = ["DEEPSEEK_API_KEY"]' in config
        assert "process-secret" not in config
        adapter._start_process(agent)
        env = calls[-1][1]["env"]
        assert env["DEEPSEEK_API_KEY"] == "process-secret"

    assert len(calls) == 4
    for command, kwargs in calls:
        assert "process-secret" not in " ".join(command)
        assert kwargs["env"]["PATH"] == "/usr/local/bin:/usr/bin:/bin"
        assert kwargs["env"]["TERM"] == "xterm-256color"
        assert kwargs["env"]["LANG"] == "C.UTF-8"
        assert kwargs["env"]["LC_ALL"] == "C.UTF-8"


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
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    def rpc(_agent: _Agent, method: str, _params: dict[str, object]) -> dict[str, object]:
        if method == "thread/start":
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
    assert 'name = "DeepSeek"' in config
    assert 'base_url = "https://api.deepseek.com/"' in config
    assert 'wire_api = "responses"' in config
    assert 'env_key = "DEEPSEEK_API_KEY"' in config
    assert 'model_reasoning_effort = "max"' in config
    assert '[shell_environment_policy]' in config
    assert 'inherit = "core"' in config
    assert 'exclude = ["DEEPSEEK_API_KEY"]' in config
    assert "child-secret" not in config
    command, kwargs = calls[0]
    assert "child-secret" not in " ".join(command)
    assert kwargs["env"]["DEEPSEEK_API_KEY"] == "child-secret"
    resource.destroy()


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


def test_missing_key_fails_before_persistent_process_factory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    calls: list[object] = []

    def process_factory(*_args: object, **_kwargs: object) -> _Process:
        calls.append(True)
        raise AssertionError("process_factory must not run without a provider key")

    adapter = CodexRuntimeAdapter(
        repository_root=root,
        use_bwrap=False,
        process_factory=process_factory,
    )
    adapter._coordination_enabled = True
    agent = _Agent(
        "coordinator",
        SimpleNamespace(role="coordinator"),
        tmp_path / "home",
        tmp_path / "work",
        tmp_path / "skills",
    )
    with pytest.raises(CodexRuntimeError):
        adapter._start_process(agent)
    assert calls == []
