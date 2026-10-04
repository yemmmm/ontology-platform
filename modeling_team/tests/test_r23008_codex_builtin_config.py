"""R2.3-008 deterministic regression: formal ``openai-codex`` config projection.

Defect (start1/start2, runtime/infrastructure): the formal built-in-provider
splice dropped the leading ``sandbox_mode``/``web_search`` scalars and the
``[features]`` table header from ``config.toml``, leaving the feature flags as
bare top-level keys.  Codex CLI 0.147.0 parses those names as typed top-level
tables (e.g. ``AppsConfigToml``), so the ``skills/list`` handshake step failed
its config reload with JSON-RPC -32603 before any ``thread/start``.  These
tests pin the corrected projection without launching any real binary.
"""

from __future__ import annotations

import hashlib
import shutil
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.contracts import _load_package, repository_root
from modeling_team.model_routing import RoleModelBinding, load_team_model_profile
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

ROOT = repository_root()

_EXPECTED_FEATURE_FLAGS = {
    "apps",
    "plugins",
    "multi_agent",
    "multi_agent_v2",
    "browser_use",
    "computer_use",
    "image_generation",
    "memories",
    "hooks",
    "skill_search",
    "tool_suggest",
}


@pytest.fixture(autouse=True)
def _clear_session_service_tier(monkeypatch):
    monkeypatch.delenv("MODELING_TEAM_CODEX_SERVICE_TIER", raising=False)


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


def _write_builtin_config(tmp_path: Path, role: str = "coordinator") -> tuple[CodexRuntimeAdapter, dict]:
    adapter = _adapter()
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
    run = _formal_run(tmp_path / "run")
    agent = _agent(tmp_path, role)
    adapter._write_config(run, agent)
    parsed = tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
    return adapter, parsed


def test_builtin_projection_keeps_features_table_header_and_scalars(
    tmp_path: Path,
) -> None:
    adapter, parsed = _write_builtin_config(tmp_path)
    # The splice must not drop the leading scalar settings: they carry the
    # read-only sandbox and disabled web search config intent.
    assert parsed["sandbox_mode"] == "read-only"
    assert parsed["web_search"] == "disabled"
    # Every frozen feature flag stays inside the [features] table...
    assert set(parsed["features"]) == _EXPECTED_FEATURE_FLAGS
    assert all(parsed["features"][name] is False for name in _EXPECTED_FEATURE_FLAGS)
    # ...and none of them leaks to the top level, where Codex 0.147.0 parses
    # them as typed tables (the start1/start2 -32603 "expected struct
    # AppsConfigToml" failure).
    assert not (_EXPECTED_FEATURE_FLAGS & set(parsed))
    # The built-in provider projection keeps its frozen shape.
    assert parsed["model_provider"] == "openai"
    assert "model_providers" not in parsed
    assert parsed["shell_environment_policy"]["inherit"] == "core"
    adapter.stop()


def test_builtin_projection_top_level_surface_is_closed(tmp_path: Path) -> None:
    adapter, parsed = _write_builtin_config(tmp_path, role="modeling")
    # The exact allowed top-level surface for the Luna builtin projection:
    # scalars first, [features] flags, MCP tables, then the shell policy table.
    assert set(parsed) == {
        "model",
        "model_provider",
        "model_reasoning_effort",
        "sandbox_mode",
        "web_search",
        "features",
        "mcp_servers",
        "shell_environment_policy",
    }
    assert parsed["model_reasoning_effort"] == "medium"
    assert "team_transport" in parsed["mcp_servers"]
    adapter.stop()


def test_builtin_projection_splices_every_formal_role(tmp_path: Path) -> None:
    # Every role that can take the built-in route must produce a config whose
    # feature flags all live under [features]; a single bare top-level flag is
    # the regression signature.
    adapter = _adapter()
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth  # type: ignore[method-assign]
    run = _formal_run(tmp_path / "run")
    try:
        for role in ("coordinator", "modeling", "protocol", "acceptance"):
            agent = _agent(tmp_path, role)
            adapter._write_config(run, agent)
            parsed = tomllib.loads(
                (agent.home / "config.toml").read_text(encoding="utf-8")
            )
            assert not (_EXPECTED_FEATURE_FLAGS & set(parsed)), role
            assert set(parsed["features"]) == _EXPECTED_FEATURE_FLAGS, role
            # Duplicate-key splices would already fail the tomllib parse above;
            # additionally pin that the model trio appears exactly once.
            assert parsed["model_provider"] == "openai"
    finally:
        adapter.stop()


@pytest.mark.parametrize("tier", [None, "unknown", "fast"])
def test_session_fast_projects_all_builtin_production_roles(tmp_path, monkeypatch, tier):
    if tier is not None:
        monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", tier)
    adapter = _adapter()
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-sol-medium")
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth
    run = _formal_run(tmp_path / "run")
    try:
        for role in ("coordinator", "modeling", "protocol", "acceptance"):
            agent = _agent(tmp_path, role)
            adapter._write_config(run, agent)
            parsed = tomllib.loads((agent.home / "config.toml").read_text())
            assert parsed["model"] == "gpt-6.1-sol"
            assert parsed["model_reasoning_effort"] == "medium"
            assert parsed["model_provider"] == "openai"
            assert "model_providers" not in parsed
            if tier == "fast":
                assert parsed["service_tier"] == "fast"
                assert parsed["features"]["fast_mode"] is True
            else:
                assert "service_tier" not in parsed
                assert "fast_mode" not in parsed["features"]
    finally:
        adapter.stop()


class _ChildConfigWritten(RuntimeError):
    pass


def _write_child_config(tmp_path: Path, kind: str, provider: str) -> dict:
    # Same deterministic pre-launch sentinel used by the cache-seed regression:
    # exercise the actual child config write without starting any app-server.
    adapter = _adapter()
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-sol-medium")
    if provider != "openai-codex":
        binding = RoleModelBinding(
            package_id=f"{kind}-examiner" if kind != "acceptance" else "acceptance",
            provider_id=provider,
            model="deepseek-chat" if provider == "deepseek-direct" else "glm-5",
            requested_effort="medium",
            effective_effort="medium",
        )
        adapter._validated_formal_role_binding = lambda _package: binding
        adapter._provider_sessions = SimpleNamespace(
            base_url_for=lambda _provider: "http://127.0.0.1:65535"
        )
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter.preflight_host_auth = lambda: host_auth

    def stop_before_process(*_args, **_kwargs):
        raise _ChildConfigWritten()

    adapter.process_factory = stop_before_process
    private_root = tmp_path / "private-root"
    private_root.mkdir(mode=0o700)
    sources = private_root / "sources"
    sources.mkdir()
    (sources / "source.md").write_text("# approved fixture source\n")
    private_input = tmp_path / "input.json"
    private_input.write_text("{}")
    spec = {
        "kind": kind,
        "task_id": "r2-3-008-formal-acceptance",
        "private_root": str(private_root),
        "private_input": str(private_input),
        "child_handle_digest": hashlib.sha256(str(tmp_path).encode()).hexdigest(),
    }
    if kind == "platform":
        spec.update(
            read_key_plaintext="fixture-read-key",
            platform_read_scope={
                "project_id": "fixture-project",
                "ontology_id": "fixture-ontology",
                "graph_set_id": "fixture-graph",
            },
            ticket_digest="a" * 64,
            model_state_digest="b" * 64,
            acceptance_round_id="fixture-round",
            allowed_read_tools=["query_semantic_context"],
        )
    try:
        with pytest.raises(_ChildConfigWritten):
            adapter._launch_acceptance_child_impl(spec)
        return tomllib.loads((private_root / "home" / "config.toml").read_text())
    finally:
        for key in ("_runtime_report_sink", "_runtime_proxy"):
            resource = spec.get(key)
            if resource is not None:
                resource.stop()
        socket_root = spec.get("_runtime_socket_root")
        if isinstance(socket_root, str):
            shutil.rmtree(socket_root, ignore_errors=True)
        adapter.stop()


@pytest.mark.parametrize("kind", ["source", "platform", "acceptance"])
@pytest.mark.parametrize("tier", [None, "unknown", "fast"])
def test_session_fast_projects_builtin_examiner_and_judge(tmp_path, monkeypatch, kind, tier):
    if tier is not None:
        monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", tier)
    parsed = _write_child_config(tmp_path, kind, "openai-codex")
    assert parsed["model"] == "gpt-6.1-sol"
    assert parsed["model_reasoning_effort"] == "medium"
    assert parsed["model_provider"] == "openai"
    assert "model_providers" not in parsed
    if tier == "fast":
        assert parsed["service_tier"] == "fast"
        assert parsed["features"]["fast_mode"] is True
    else:
        assert "service_tier" not in parsed
        assert "fast_mode" not in parsed["features"]


@pytest.mark.parametrize("provider", ["deepseek-direct", "glm-direct"])
def test_session_fast_does_not_project_external_routes(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", "fast")
    parsed = _write_child_config(tmp_path, "acceptance", provider)
    assert parsed["model_provider"] == provider
    assert "service_tier" not in parsed
    assert "fast_mode" not in parsed["features"]


@pytest.mark.parametrize("provider", ["deepseek-direct", "glm-direct"])
def test_session_fast_does_not_project_external_production_roles(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", "fast")
    adapter = _adapter()
    binding = RoleModelBinding(
        package_id="coordinator",
        provider_id=provider,
        model="deepseek-chat" if provider == "deepseek-direct" else "glm-5",
        requested_effort="medium",
        effective_effort="medium",
    )
    adapter._validated_model_override = lambda _package, **_kwargs: binding
    adapter._provider_sessions = SimpleNamespace(
        base_url_for=lambda _provider: "http://127.0.0.1:65535"
    )
    agent = _agent(tmp_path, "coordinator")
    try:
        adapter._write_config(_formal_run(tmp_path / "run"), agent)
        parsed = tomllib.loads((agent.home / "config.toml").read_text())
        assert parsed["model_provider"] == provider
        assert "service_tier" not in parsed
        assert "fast_mode" not in parsed["features"]
    finally:
        adapter.stop()
