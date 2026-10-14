from __future__ import annotations

from modeling_team.handoff_materials import HANDOFF_TOOL_NAMES

import json
import tomllib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS
from modeling_team.contracts import _load_package, repository_root
from modeling_team.deepseek_provider_proxy import preflight_deepseek_credential
from modeling_team.model_routing import (
    DEFAULT_MODEL_PROFILE_ID,
    MODEL_PROFILE_PACKAGE_IDS,
    ProviderSessionManager,
    RoleModelBinding,
    load_team_model_profile,
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


class _SessionsDouble:
    """Minimal ProviderSessionManager double for config/env unit tests."""

    def __init__(self, base_urls: dict[str, str] | None = None) -> None:
        self._base_urls = base_urls or {"deepseek-direct": "http://127.0.0.1:49152"}

    def base_url_for(self, provider_id: str) -> str:
        return self._base_urls[provider_id]

    def listening(self) -> bool:
        return True

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {provider_id: {"listening": True} for provider_id in self._base_urls}

    def secret_values(self) -> tuple[bytes, ...]:
        return ()

    def stop(self) -> dict[str, dict[str, bool | int]]:
        return {}


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
    adapter._team_model_profile = load_team_model_profile(repo, DEFAULT_MODEL_PROFILE_ID)
    adapter._provider_sessions = _SessionsDouble()
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)
        adapter._write_config(run, agent)
        config = (agent.home / "config.toml").read_text(encoding="utf-8")
        assert 'model = "deepseek-v4-flash"' in config
        assert 'model_provider = "deepseek-direct"' in config
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


def test_formal_config_is_parseable_with_one_model_binding(tmp_path: Path) -> None:
    repo = repository_root()
    run = _formal_run(tmp_path / "run")
    adapter = CodexRuntimeAdapter(repository_root=repo, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(repo, DEFAULT_MODEL_PROFILE_ID)
    adapter._provider_sessions = _SessionsDouble()
    agent = _agent(tmp_path, "coordinator")
    try:
        adapter._write_config(run, agent)
        parsed = tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
    finally:
        adapter.stop()

    assert parsed["model"] == "deepseek-v4-flash"
    assert parsed["model_provider"] == "deepseek-direct"
    assert parsed["model_reasoning_effort"] == "max"
    assert parsed["model_providers"]["deepseek-direct"]["wire_api"] == "responses"
    assert "env_key" not in parsed["model_providers"]["deepseek-direct"]
    assert set(parsed["model_providers"]["deepseek-direct"]) == {
        "name",
        "base_url",
        "wire_api",
    }


def test_formal_startup_exception_unwinds_and_wipes_provider_sessions(
    monkeypatch, tmp_path: Path
) -> None:
    credential = tmp_path / "deepseek.env"
    credential.write_text("DEEPSEEK_API_KEY=startup-sentinel\n", encoding="utf-8")
    credential.chmod(0o600)
    run = _formal_run(tmp_path / "run")
    run.team_model_profile = load_team_model_profile(
        repository_root(), DEFAULT_MODEL_PROFILE_ID
    )
    run.provider_credential_bindings = {
        "deepseek-direct": preflight_deepseek_credential(credential)
    }
    created: list[ProviderSessionManager] = []

    class _SpyManager(ProviderSessionManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(
        "modeling_team.runtimes.codex.ProviderSessionManager", _SpyManager
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
    assert created[0].secret_values() == ()
    assert created[0].listening() is False
    assert adapter._provider_sessions is None
    assert adapter._secret_audit_values == []


@pytest.mark.parametrize("formal", [True, False])
def test_thread_start_model_binding_is_formal_only(
    monkeypatch, tmp_path: Path, formal: bool
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = formal
    if formal:
        adapter._team_model_profile = load_team_model_profile(
            repository_root(), DEFAULT_MODEL_PROFILE_ID
        )
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
    adapter._team_model_profile = load_team_model_profile(
        repository_root(), DEFAULT_MODEL_PROFILE_ID
    )

    expected = {
        package_id: {
            "model_provider": "deepseek-direct",
            "model": "deepseek-v4-flash",
            "requested_effort": "max",
            "effective_effort": "max",
        }
        for package_id in MODEL_PROFILE_PACKAGE_IDS
    }
    assert {
        package_id: adapter._validated_formal_role_binding(package_id).as_dict()
        for package_id in MODEL_PROFILE_PACKAGE_IDS
    } == expected


def test_formal_model_binding_fails_closed_before_process_on_binding_or_package_drift(
    tmp_path: Path,
) -> None:
    def _binding(
        package_id: str,
        *,
        provider_id: str = "deepseek-direct",
        model: str = "deepseek-v4-flash",
    ) -> RoleModelBinding:
        return RoleModelBinding(package_id, provider_id, model, "max", "max")

    class DriftedProfile:
        profile_id = DEFAULT_MODEL_PROFILE_ID

        def binding_for(self, package_id: str) -> RoleModelBinding:
            if package_id == "coordinator":
                return _binding(package_id, model="gpt-5.5")
            raise KeyError(package_id)

    calls: list[object] = []
    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(),
        use_bwrap=False,
        process_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    adapter._coordination_enabled = True
    adapter._team_model_profile = DriftedProfile()  # type: ignore[assignment]
    agent = _agent(tmp_path, "coordinator")

    with pytest.raises(CodexRuntimeError, match="binding drifted"):
        adapter._start_process(agent)
    assert calls == []

    with pytest.raises(CodexRuntimeError, match="package binding"):
        adapter._validated_formal_role_binding("platform-examiner")
    with pytest.raises(CodexRuntimeError, match="package binding"):
        adapter._validated_formal_role_binding("unknown-package")


def test_formal_start_roster_ignores_ambient_deepseek_and_llm_sentinels(
    monkeypatch, tmp_path: Path
) -> None:
    credential = tmp_path / "formal-deepseek.env"
    credential.write_text("DEEPSEEK_API_KEY=file-only-sentinel\n", encoding="utf-8")
    credential.chmod(0o600)
    binding = preflight_deepseek_credential(credential)
    run = _formal_run(tmp_path / "run")
    run.team_model_profile = load_team_model_profile(
        repository_root(), DEFAULT_MODEL_PROFILE_ID
    )
    run.provider_credential_bindings = {"deepseek-direct": binding}
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
    assert adapter._provider_sessions is not None
    assert adapter._provider_sessions.base_url_for("deepseek-direct").startswith(
        "http://127.0.0.1:"
    )
    adapter.stop()


def _multi_slice_run(root: Path) -> SimpleNamespace:
    for role in ("coordinator", "modeling", "protocol", "competency-question"):
        (root / "sources" / role).mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        run_id="deepseek-multi-slice-run",
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r3-0-006-real-full")
        ),
        acceptance=None,
    )


_ROSTER_ROLES = ("coordinator", "modeling", "protocol", "competency-question")


def test_multi_slice_profile_binding_covers_roster_and_cq_children(
    tmp_path: Path,
) -> None:
    # R3.0-006 real validation: a non-formal multi-slice run with an explicit
    # Team Model Profile resolves every roster role -- and both CQ acceptance
    # children the carrier launches (Platform Examiner production side and
    # the Judge) -- from the frozen profile, with no OpenAI fallback.
    repo = repository_root()
    adapter = CodexRuntimeAdapter(repository_root=repo)
    assert adapter._coordination_enabled is False
    adapter._team_model_profile = load_team_model_profile(repo, "deepseek-flash-max")
    try:
        for role in _ROSTER_ROLES:
            agent = _agent(tmp_path / "roster", role)
            binding = adapter._validated_model_override(agent.package, formal=False)
            assert isinstance(binding, RoleModelBinding)
            assert binding.package_id == role
            assert binding.provider_id == "deepseek-direct"
            assert binding.model == "deepseek-flash"
            assert binding.effective_effort == "max"
        for child in ("platform-examiner", "acceptance"):
            package = SimpleNamespace(role="source-specialist", package_id=child)
            binding = adapter._validated_model_override(package, formal=False)
            assert binding.package_id == child
            assert (binding.provider_id, binding.model) == ("deepseek-direct", "deepseek-flash")
    finally:
        adapter.stop()


def test_multi_slice_profile_bound_config_and_env_cover_all_roster_roles(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository_root()
    run = _multi_slice_run(tmp_path / "run")
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
    # Deliberately NOT formal: provider binding must survive without
    # formal-only coordination.
    adapter._coordination_enabled = False
    adapter._team_model_profile = load_team_model_profile(repo, "deepseek-flash-max")
    adapter._provider_sessions = _SessionsDouble()
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    try:
        for role in _ROSTER_ROLES:
            agent = _agent(tmp_path, role)
            adapter._write_config(run, agent)
            config = (agent.home / "config.toml").read_text(encoding="utf-8")
            assert 'model = "deepseek-flash"' in config
            assert 'model_provider = "deepseek-direct"' in config
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
    finally:
        adapter.stop()


def test_multi_slice_thread_start_model_binding_follows_the_profile(
    tmp_path: Path,
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = False
    adapter._team_model_profile = load_team_model_profile(
        repository_root(), "deepseek-flash-max"
    )
    starts: dict[str, dict[str, object]] = {}

    for role in _ROSTER_ROLES:
        agent = _agent(tmp_path / "profile-bound", role)

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

    assert set(starts) == set(_ROSTER_ROLES)
    assert {params["model"] for params in starts.values()} == {"deepseek-flash"}
    adapter.stop()


def test_multi_slice_start_roster_starts_and_stops_provider_sessions(
    monkeypatch, tmp_path: Path
) -> None:
    credential = tmp_path / "multi-slice-deepseek.env"
    credential.write_text("DEEPSEEK_API_KEY=file-only-sentinel\n", encoding="utf-8")
    credential.chmod(0o600)
    run = _multi_slice_run(tmp_path / "run")
    run.team_model_profile = load_team_model_profile(
        repository_root(), "deepseek-flash-max"
    )
    run.provider_credential_bindings = {
        "deepseek-direct": preflight_deepseek_credential(credential)
    }
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ambient-deepseek-sentinel")
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
    monkeypatch.setattr(
        adapter,
        "_resolve_deepseek_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("profile-bound runtime resolved ambient key")),
    )
    try:
        assert adapter.start_roster(run, []) == []
        assert adapter._coordination_enabled is False
        assert adapter._provider_sessions is not None
        assert adapter._provider_sessions.base_url_for("deepseek-direct").startswith(
            "http://127.0.0.1:"
        )
        assert all(
            sentinel.encode() not in adapter._secret_audit_values
            for sentinel in ("ambient-deepseek-sentinel", "file-only-sentinel")
        )
    finally:
        adapter.stop()
    # The profile-bound non-formal lifecycle must stop and wipe its sessions
    # exactly like the formal one; a live listener may never outlive stop().
    assert adapter._provider_sessions is None


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
    adapter._team_model_profile = load_team_model_profile(repo, DEFAULT_MODEL_PROFILE_ID)
    adapter._provider_sessions = _SessionsDouble()
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)
    thread_starts: list[dict[str, object]] = []

    def rpc(_agent: _Agent, method: str, _params: dict[str, object]) -> dict[str, object]:
        if method == "thread/start":
            thread_starts.append(dict(_params))
            return {"thread": {"id": f"{kind}-thread"}}
        if method == "turn/start":
            return {"turn": {"id": f"{kind}-turn"}}
        if method == "mcpServerStatus/list":
            tools = [{"name": "submit_examiner_report"}, *({"name": name} for name in sorted(HANDOFF_TOOL_NAMES))]
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

    if kind == "source":
        # A formal Source Examiner now requires the carrier-staged approved
        # bytes (R2.3-009 start21 SOURCE_TEXT_JSON seam); stage a minimal
        # manifest-shaped tree for the formal fixtures.
        sources = private_root / "sources"
        sources.mkdir()
        (sources / "source.md").write_text("# approved source\n", encoding="utf-8")
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
    assert 'model_provider = "deepseek-direct"' in config
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
    adapter._team_model_profile = load_team_model_profile(
        repository_root(), DEFAULT_MODEL_PROFILE_ID
    )
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


# --- R3.0-011 standalone acceptance carrier provider sessions ------------------
#
# ``cq-acceptance`` starts no roster, so nothing opened the loopback provider
# sessions a formal v3 child bound to an external credential route needs at
# launch: the child start failed with "formal provider sessions are unavailable"
# although the bound profile's credential was valid.  These checks use the real
# ``glm-max`` profile fixture and the adapter's existing child-factory seam.


class _CarrierSessionsDouble(_SessionsDouble):
    """The session double above, counting the lifecycle the carrier owns."""

    def __init__(self, bindings: dict[str, object], *, on_failure: object = None) -> None:
        super().__init__({"glm-direct": "http://127.0.0.1:49152"})
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> dict[str, dict[str, bool | int]]:
        self.stopped += 1
        return {}


def _install_carrier_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_CarrierSessionsDouble]:
    """Replace the session manager and the external-route credential preflight."""

    created: list[_CarrierSessionsDouble] = []

    def fake_manager(
        bindings: dict[str, object],
        *,
        on_failure: object = None,
        session_factory: object = None,
        on_attempt: object = None,
    ) -> _CarrierSessionsDouble:
        assert callable(on_attempt)
        assert "glm-direct" in bindings, "the profile's external route must be preflighted"
        manager = _CarrierSessionsDouble(bindings, on_failure=on_failure)
        created.append(manager)
        return manager

    monkeypatch.setattr("modeling_team.runtimes.codex.ProviderSessionManager", fake_manager)
    monkeypatch.setattr(
        "modeling_team.runtimes.codex.preflight_profile_credentials",
        lambda profile, **_overrides: {"glm-direct": {"sentinel": True}},
    )
    return created


def _standalone_adapter(factory: object = None) -> CodexRuntimeAdapter:
    """A ``cq-acceptance`` carrier bound to the external-route ``glm-max`` profile."""

    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(),
        use_bwrap=False,
        acceptance_child_factory=factory,
    )
    adapter.bind_acceptance_model_profile(load_team_model_profile(repository_root(), "glm-max"))
    return adapter


def test_standalone_acceptance_starts_and_stops_its_own_provider_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The child sees live sessions at launch, and normal completion stops them."""

    from modeling_team.runtimes.codex import _CodexChildResource
    from modeling_team.tests.test_r3011_acceptance_runtime import (
        _FakeSink,
        _IdleProcess,
        _batch_contract,
        _batch_packet,
        _verdict_entry,
    )

    created = _install_carrier_sessions(monkeypatch)
    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    live_at_launch: list[object] = []
    adapter: CodexRuntimeAdapter | None = None

    def factory(spec: dict) -> object:
        # The formal launch guard reads the adapter's sessions, so reaching the
        # child factory with them started is exactly what the defect broke.
        live_at_launch.append(adapter._provider_sessions)
        resource = _CodexChildResource(spec, None, report_sink=_FakeSink(contract))
        resource.submitted_reports = spec["_submitted_reports"]
        resource.submitted_reports.extend(
            [_verdict_entry(packet.batch_id, "cq-1"), _verdict_entry(packet.batch_id, "cq-2")]
        )
        resource.process = _IdleProcess()
        return resource

    adapter = _standalone_adapter(factory)
    returned = adapter.run_v3_acceptance_child(
        packet,
        role_instructions="judge the batch in order",
        reports=[],
        timeout_seconds=5.0,
    )
    assert [report["question_id"] for report in returned] == ["cq-1", "cq-2"]
    assert live_at_launch == [created[0]]
    assert (created[0].started, created[0].stopped) == (1, 1)
    assert adapter._provider_sessions is None
    assert adapter._standalone_provider_sessions is None


def test_standalone_acceptance_stops_its_sessions_after_a_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child that never started must not leak the carrier's sessions."""

    from modeling_team.tests.test_r3011_acceptance_runtime import _batch_packet

    created = _install_carrier_sessions(monkeypatch)

    def failing_factory(spec: dict) -> object:
        raise RuntimeError("probe: child start failed")

    adapter = _standalone_adapter(failing_factory)
    with pytest.raises(RuntimeError, match="probe: child start failed"):
        adapter.run_v3_acceptance_child(
            _batch_packet(role="acceptance"),
            role_instructions="judge the batch in order",
            reports=[],
            timeout_seconds=5.0,
        )
    assert (created[0].started, created[0].stopped) == (1, 1)
    assert adapter._provider_sessions is None
    assert adapter._standalone_provider_sessions is None


def test_standalone_acceptance_leaves_a_roster_owned_manager_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manager another lifecycle owns is neither duplicated nor stopped."""

    created = _install_carrier_sessions(monkeypatch)
    adapter = _standalone_adapter()
    roster_owned = _SessionsDouble()
    adapter._provider_sessions = roster_owned

    adapter._ensure_standalone_provider_sessions()
    adapter._stop_standalone_provider_sessions()
    assert created == []
    assert adapter._provider_sessions is roster_owned


@pytest.mark.parametrize("profile_id", [None, "openai-luna-medium"])
def test_standalone_acceptance_is_a_no_op_without_an_external_route(
    monkeypatch: pytest.MonkeyPatch, profile_id: str | None
) -> None:
    """An unbound or OpenAI-only profile opens and stops nothing."""

    created = _install_carrier_sessions(monkeypatch)
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
    if profile_id is not None:
        adapter.bind_acceptance_model_profile(
            load_team_model_profile(repository_root(), profile_id)
        )

    adapter._ensure_standalone_provider_sessions()
    adapter._stop_standalone_provider_sessions()
    assert created == []
    assert adapter._provider_sessions is None
