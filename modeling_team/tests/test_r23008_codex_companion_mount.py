"""R2.3-008 deterministic regression: Codex companion binary namespace mount.

Defect (start6, runtime/infrastructure): Codex 0.147.0 spawns
``codex-code-mode-host`` for every tool/shell execution and resolves it
relative to its own executable directory.  The Runtime namespaces mounted only
``codex`` at ``/agent/bin/codex``, so every tool call inside a namespace failed
with ``failed to spawn code-mode host /agent/bin/codex-code-mode-host: No such
file or directory (os error 2)`` — all four roles returned Blocked.  These
tests pin the additive companion bind at both codex-binary mount sites, and
the clean degradation when an installed Codex has no companion.
"""

from __future__ import annotations

from pathlib import Path

from modeling_team.contracts import _load_package, repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

ROOT = repository_root()

_COMPANION_MOUNT = "/agent/bin/codex-code-mode-host"


def _triples(command: list[str]) -> set[tuple[str, str, str]]:
    return {
        tuple(command[index : index + 3])
        for index in range(len(command) - 2)
        if command[index].startswith("--")
    }


def _persistent_agent(adapter: CodexRuntimeAdapter, base: Path, role: str) -> _Agent:
    home, work, skills = (
        base / f"{role}-home",
        base / f"{role}-work",
        base / f"{role}-skills",
    )
    for path in (home, work, skills):
        path.mkdir(parents=True)
    agent = _Agent(role, _load_package(ROOT, role), home, work, skills, schema_version=2)
    adapter.agents[agent.agent_id] = agent
    (base / "transport" / "broker").mkdir(parents=True, exist_ok=True)
    (base / "transport" / "broker" / f"{agent.agent_id}.sock").touch()
    return agent


def test_persistent_namespace_mounts_companion_for_every_role(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=True)
    adapter._run_root = tmp_path / "run"
    try:
        companion = adapter._codex_companion_binary()
        assert companion is not None, "host Codex 0.147.0 companion must resolve"
        for role in ("coordinator", "modeling", "protocol", "acceptance"):
            agent = _persistent_agent(adapter, tmp_path / "run", role)
            command = adapter.namespace_command(agent)
            assert ("--ro-bind", str(companion), _COMPANION_MOUNT) in _triples(command), role
            # The bind must precede the bwrap "--" separator (all mounts are
            # options; everything after "--" is the exec payload).
            separator = command.index("--")
            assert command.index(_COMPANION_MOUNT) < separator, role
    finally:
        adapter.stop()


def test_absent_companion_degrades_cleanly_for_persistent_roles(tmp_path: Path) -> None:
    # A Codex layout without the companion keeps today's namespace surface.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_bytes(b"#!/bin/sh\n")
    fake_codex.chmod(0o755)
    adapter = CodexRuntimeAdapter(
        repository_root=ROOT, use_bwrap=True, codex_binary=str(fake_codex)
    )
    adapter._run_root = tmp_path / "run"
    try:
        assert adapter._codex_companion_binary() is None
        agent = _persistent_agent(adapter, tmp_path / "run", "coordinator")
        command = adapter.namespace_command(agent)
        assert _COMPANION_MOUNT not in command
        # Startup shape unchanged: codex still mounted and still the exec payload.
        assert ("--ro-bind", str(fake_codex), "/agent/bin/codex") in _triples(command)
        assert command[command.index("--") + 1] == "/agent/bin/codex"
    finally:
        adapter.stop()


def test_invalid_companion_shapes_are_rejected_not_bound(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_bytes(b"#!/bin/sh\n")
    fake_codex.chmod(0o755)

    def adapter_with(companion_setup) -> CodexRuntimeAdapter:
        companion_setup()
        return CodexRuntimeAdapter(
            repository_root=ROOT, use_bwrap=True, codex_binary=str(fake_codex)
        )

    adapter = adapter_with(lambda: (fake_bin / "codex-code-mode-host").symlink_to(fake_codex))
    try:
        # Symlinked companion: refuse rather than bind an unverified path.
        assert adapter._codex_companion_binary() is None
    finally:
        adapter.stop()

    (fake_bin / "codex-code-mode-host").unlink()
    non_executable = fake_bin / "codex-code-mode-host"
    non_executable.write_bytes(b"payload")
    non_executable.chmod(0o644)
    adapter = adapter_with(lambda: None)
    try:
        assert adapter._codex_companion_binary() is None
    finally:
        adapter.stop()


def test_acceptance_child_namespace_mounts_companion_before_separator(tmp_path: Path) -> None:
    home, work, skills = (tmp_path / value for value in ("home", "work", "skills"))
    for path in (home, work, skills):
        path.mkdir()
    report = tmp_path / "report.sock"
    report.touch()
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=True)
    try:
        companion = adapter._codex_companion_binary()
        assert companion is not None, "host Codex 0.147.0 companion must resolve"
        command = adapter._acceptance_namespace_command(
            home=home,
            work=work,
            skills=skills,
            proxy_socket=None,
            report_socket=report,
        )
        assert ("--ro-bind", str(companion), _COMPANION_MOUNT) in _triples(command)
        separator = command.index("--")
        assert command.index(_COMPANION_MOUNT) < separator
        # Examiner children execute tools too: the exec payload stays codex.
        assert command[separator + 1] == "/agent/bin/codex"
    finally:
        adapter.stop()


def test_acceptance_child_namespace_without_companion_is_unchanged(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_bytes(b"#!/bin/sh\n")
    fake_codex.chmod(0o755)
    home, work, skills = (tmp_path / value for value in ("home", "work", "skills"))
    for path in (home, work, skills):
        path.mkdir()
    report = tmp_path / "report.sock"
    report.touch()
    adapter = CodexRuntimeAdapter(
        repository_root=ROOT, use_bwrap=True, codex_binary=str(fake_codex)
    )
    try:
        command = adapter._acceptance_namespace_command(
            home=home,
            work=work,
            skills=skills,
            proxy_socket=None,
            report_socket=report,
        )
        assert _COMPANION_MOUNT not in command
        assert command[command.index("--") + 1] == "/agent/bin/codex"
    finally:
        adapter.stop()
