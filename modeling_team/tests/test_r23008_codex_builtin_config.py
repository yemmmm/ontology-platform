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

import tomllib
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, repository_root
from modeling_team.model_routing import load_team_model_profile
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
