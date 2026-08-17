"""R2.3-008 deterministic regression: Protocol interpreter namespace surface.

Defect (start4, runtime/infrastructure): ``backend/.venv/bin/python`` is a
uv-managed absolute symlink into the uv Python store.  ``namespace_command``'s
Protocol branch bound only the fully resolved interpreter runtime, so the
symlink's literal absolute target path dangled inside the bwrap namespace and
the required ``ontology_platform`` MCP server died with ``No such file or
directory (os error 2)`` at ``thread/start``.  These tests pin the namespace
surface (every absolute symlink target's interpreter prefix is bound at its
own path, with ancestor mount points created first) without launching any
binary.
"""

from __future__ import annotations

import os
from pathlib import Path

from modeling_team.contracts import _load_package, repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

ROOT = repository_root()


def _triples(command: list[str]) -> set[tuple[str, str, str]]:
    return {
        tuple(command[index : index + 3])
        for index in range(len(command) - 2)
        if command[index].startswith("--")
    }


def _pairs(command: list[str]) -> set[tuple[str, str]]:
    return {
        tuple(command[index : index + 2])
        for index in range(len(command) - 1)
        if command[index].startswith("--")
    }


def _interpreter_prefix_chain(venv: Path) -> list[Path]:
    """The absolute symlink-target prefixes of the venv interpreter, host side."""
    prefixes: list[Path] = []
    resolved_venv = venv.resolve()
    link: Path | None = venv / "bin" / "python"
    visited: set[Path] = set()
    while link is not None and link not in visited and len(visited) < 8:
        visited.add(link)
        if not link.is_symlink():
            break
        target = Path(os.readlink(link))
        candidate = target if target.is_absolute() else link.parent / target
        prefix = candidate.parent.parent
        inside_venv = prefix == resolved_venv or resolved_venv in prefix.parents
        if not inside_venv and prefix not in prefixes:
            prefixes.append(prefix)
        link = candidate
    return prefixes


def _real_repo_agent(role: str, base: Path, schema_version: int) -> _Agent:
    home, work, skills = (
        base / f"{role}-home",
        base / f"{role}-work",
        base / f"{role}-skills",
    )
    for path in (home, work, skills):
        path.mkdir(parents=True)
        path.chmod(0o700)
    return _Agent(
        role,
        _load_package(ROOT, role),
        home,
        work,
        skills,
        schema_version=schema_version,
    )


def test_protocol_namespace_binds_interpreter_symlink_target_prefixes(tmp_path: Path) -> None:
    # The live defect host layout: the venv interpreter is an absolute symlink
    # whose target prefix must exist at its own path inside the namespace.
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=True)
    base = tmp_path / "run"
    adapter._run_root = base
    (base / "transport" / "broker").mkdir(parents=True)
    (base / "transport" / "broker" / "protocol.sock").touch()
    agent = _real_repo_agent("protocol", base, schema_version=2)
    adapter.agents[agent.agent_id] = agent
    try:
        command = adapter.namespace_command(agent)
        triples = _triples(command)
        assert ("--ro-bind", str(ROOT / "backend" / "app"), "/backend/app") in triples
        assert ("--ro-bind", str(ROOT / "backend" / ".venv"), "/backend/.venv") in triples
        # The fully resolved runtime stays bound (pyvenv.cfg/sysconfig lookups).
        resolved = (ROOT / "backend" / ".venv" / "bin" / "python").resolve()
        assert ("--ro-bind", str(resolved.parent.parent), str(resolved.parent.parent)) in triples
        for prefix in _interpreter_prefix_chain(ROOT / "backend" / ".venv"):
            assert ("--ro-bind", str(prefix), str(prefix)) in triples, prefix
            # Every non-base ancestor mount point must be created before the
            # subtree bind: bwrap applies mounts in argument order.
            bind_index = command.index(str(prefix))
            ancestor = Path("/")
            for part in prefix.parts[1:-1]:
                ancestor = ancestor / part
                assert ancestor not in (
                    Path("/usr"),
                    Path("/bin"),
                    Path("/lib"),
                    Path("/lib64"),
                    Path("/etc"),
                )
                assert command.index(str(ancestor)) < bind_index, ancestor
    finally:
        adapter.stop()


def test_non_protocol_roles_do_not_receive_interpreter_binds(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=True)
    base = tmp_path / "run"
    adapter._run_root = base
    (base / "transport" / "broker").mkdir(parents=True)
    try:
        for role in ("coordinator", "modeling"):
            agent = _real_repo_agent(role, base, schema_version=2)
            adapter.agents[agent.agent_id] = agent
            (base / "transport" / "broker" / f"{agent.agent_id}.sock").touch()
            command = adapter.namespace_command(agent)
            triples = _triples(command)
            resolved = (ROOT / "backend" / ".venv" / "bin" / "python").resolve()
            assert (
                "--ro-bind",
                str(resolved.parent.parent),
                str(resolved.parent.parent),
            ) not in triples
            for prefix in _interpreter_prefix_chain(ROOT / "backend" / ".venv"):
                assert ("--ro-bind", str(prefix), str(prefix)) not in triples, prefix
            assert "/backend" not in command
    finally:
        adapter.stop()


def test_interpreter_mounts_follow_absolute_and_relative_symlink_chains(tmp_path: Path) -> None:
    # Scratch repository root: a venv interpreter that hops through one
    # absolute symlink into an external prefix, plus venv-internal relative
    # aliases that must not produce any extra external bind.
    scratch = tmp_path / "scratch-repo"
    venv_bin = scratch / "backend" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    external = tmp_path / "external-prefix" / "py" / "runtime"
    (external / "bin").mkdir(parents=True)
    (external / "bin" / "python3").write_text("#!stub\n", encoding="utf-8")
    os.symlink(str(external / "bin" / "python3"), venv_bin / "python")
    os.symlink("python", venv_bin / "python3")
    adapter = CodexRuntimeAdapter(repository_root=scratch, use_bwrap=True)
    base = tmp_path / "run"
    adapter._run_root = base
    (base / "transport" / "broker").mkdir(parents=True)
    agent = _real_repo_agent("protocol", base, schema_version=1)
    adapter.agents[agent.agent_id] = agent
    (base / "transport" / "broker" / "protocol.sock").touch()
    try:
        command = adapter.namespace_command(agent)
        triples = _triples(command)
        # The absolute target's interpreter prefix is bound at its own path...
        assert ("--ro-bind", str(external), str(external)) in triples
        # ...with its ancestors created as mount points, and no bind of the
        # venv-internal relative alias target directory.
        pairs = _pairs(command)
        for ancestor in (tmp_path, tmp_path / "external-prefix", tmp_path / "external-prefix" / "py"):
            assert ("--dir", str(ancestor)) in pairs
        assert ("--ro-bind", str(venv_bin), str(venv_bin)) not in triples
    finally:
        adapter.stop()
