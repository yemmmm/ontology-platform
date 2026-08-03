"""Codex app-server implementation; its Thread and turn fields stay private here."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shlex
import signal
import socket
import shutil
import subprocess
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..contracts import AgentPackage, digest_file
from ..protocol_mcp_launch import protocol_mcp_launch_spec
from ..protocol_mechanics import protocol_mechanics_contract_bytes
from ..transport_mcp import TERMINAL_REPORT_GUARD_ERROR
from .base import AgentRuntimeIdentity, AgentState, RuntimeAdapter, RuntimeDelivery, RuntimeMessage


class CodexRuntimeError(RuntimeError):
    pass


_RETRIEVAL_BLOCKING_WARNINGS = frozenset(
    {
        "evidence_missing",
        "lineage_missing",
        "lineage_partial",
        "lineage_truncated",
        "legacy_lineage_unavailable",
    }
)


@dataclass
class _Agent:
    agent_id: str
    package: AgentPackage
    home: Path
    work: Path
    skills: Path
    process: subprocess.Popen[str] | None = None
    thread_id: str | None = None
    active_turn_id: str | None = None
    state: str = "starting"
    request_id: int = 0
    first_turn_input: list[dict[str, Any]] = field(default_factory=list)
    stdout_buffer: bytes = b""
    dynamic_tool_calls: int = 0
    message_deltas: dict[str, list[str]] = field(default_factory=dict)
    completed_message_ids: set[str] = field(default_factory=set)
    platform_tools: frozenset[str] = field(default_factory=frozenset)
    app_server_host_pid: int | None = None
    mechanics_contract_path: Path | None = None
    retrieval_mcp_path: Path | None = None
    retrieval_verifier_path: Path | None = None
    proof_v2_path: Path | None = None
    retrieval_asset_fds: tuple[int, ...] = ()
    schema_version: int = 1
    fallback_eligible: bool = False
    retrieval_episode: int = 0
    retrieval_state: str = "idle"
    completed_mcp_item_ids: set[str] = field(default_factory=set)
    io_lock: threading.RLock = field(default_factory=threading.RLock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)


class CodexRuntimeAdapter(RuntimeAdapter):
    """One app-server process and persistent Codex Thread per frozen Agent."""

    def __init__(
        self,
        *,
        repository_root: Path,
        codex_binary: str = "codex",
        use_bwrap: bool = True,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ):
        self.root, self.codex_binary, self.use_bwrap, self.process_factory = (
            repository_root,
            codex_binary,
            use_bwrap,
            process_factory,
        )
        self.agents: dict[str, _Agent] = {}
        self._messages: list[RuntimeMessage] = []
        self._run_root: Path | None = None
        self._run_id: str | None = None
        self._private_credentials_destroyed: dict[str, bool] = {}

    @staticmethod
    def preflight_host_auth() -> Path:
        """Validate the host auth source without opening or emitting its contents."""
        host_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        host_auth = host_home / "auth.json"
        try:
            metadata = os.lstat(host_auth)
        except OSError as exc:
            raise CodexRuntimeError("host Codex authentication is unavailable for private staging") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CodexRuntimeError("host Codex authentication is unavailable for private staging")
        return host_auth

    def start_roster(self, run: Any, agents: Any) -> list[AgentRuntimeIdentity]:
        self._run_root = run.root
        self._run_id = run.run_id
        identities: list[AgentRuntimeIdentity] = []
        scope = getattr(run, "scope", {})
        scope_mode = scope.get("mode") if isinstance(scope, dict) else getattr(scope, "mode", None)
        for profile_agent in agents:
            package = profile_agent.package
            base = run.root / "runtime" / profile_agent.agent_id
            home, work, skills = base / "home", base / "work", base / "skills"
            for path in (home, work, skills):
                path.mkdir(parents=True, mode=0o700, exist_ok=False)
            tools = (
                frozenset(run.configuration.task.protocol_tools)
                if package.role == "protocol" and run.configuration.task.schema_version == 2
                else frozenset({"check_platform_health"})
            )
            agent = _Agent(
                profile_agent.agent_id,
                package,
                home,
                work,
                skills,
                platform_tools=tools,
                schema_version=run.configuration.task.schema_version,
                fallback_eligible=(
                    package.role == "protocol"
                    and run.configuration.task.schema_version == 2
                    and scope_mode == "create"
                ),
            )
            self.agents[agent.agent_id] = agent
            self._stage_protocol_mechanics_contract(run, agent)
            self._stage_protocol_retrieval_mcp(run, agent)
            self._stage_skills(agent)
            self._write_config(run, agent)
            agent.process = self._start_process(agent)
            self._initialize(agent)
            agent.app_server_host_pid = self._app_server_host_pid(agent)
            identities.append(
                AgentRuntimeIdentity(agent.agent_id, f"codex-thread:{agent.thread_id}")
            )
        return identities

    @staticmethod
    def _stage_protocol_mechanics_contract(run: Any, agent: _Agent) -> None:
        """Publish the v2 Protocol-only mechanics asset outside every Agent home."""
        task = getattr(getattr(run, "configuration", None), "task", None)
        if agent.package.role != "protocol" or getattr(task, "schema_version", 1) != 2:
            return
        run_id = getattr(run, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            raise CodexRuntimeError("v2 Protocol mechanics contract requires a run ID")
        assets = run.root / "runtime-assets"
        protocol_assets = assets / "protocol"
        protocol_assets.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(assets, 0o700)
        os.chmod(protocol_assets, 0o700)
        contract = protocol_assets / "mechanics-contract.json"
        try:
            descriptor = os.open(contract, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            raise CodexRuntimeError("v2 Protocol mechanics contract already exists") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(protocol_mechanics_contract_bytes(run_id))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(contract, 0o444)
        agent.mechanics_contract_path = contract

    def _stage_protocol_retrieval_mcp(self, run: Any, agent: _Agent) -> None:
        """Stage the sole v2 Protocol retrieval MCP wrapper and verifier as immutable assets."""
        task = getattr(getattr(run, "configuration", None), "task", None)
        if agent.package.role != "protocol" or getattr(task, "schema_version", 1) != 2:
            return
        assets = run.root / "runtime-assets" / "protocol"
        assets.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(assets.parent, 0o700)
        os.chmod(assets, 0o700)
        for directory in (assets.parent, assets):
            metadata = os.lstat(directory)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP asset directory is invalid")
        wrapper = assets / "protocol-retrieval-mcp.py"
        verifier = assets / "protocol_mechanics.py"
        proof_v2 = assets / "proof_v2.py"
        source_specs = (
            (wrapper, self.root / "modeling_team" / "protocol_retrieval_mcp.py", "protocol_retrieval_mcp", 0o444),
            (verifier, self.root / "modeling_team" / "protocol_mechanics.py", "protocol_retrieval_verifier", 0o444),
            (proof_v2, self.root / "modeling_team" / "proof_v2.py", "proof_v2", 0o600),
        )
        baseline_path = run.root / "baseline-manifest.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
        expected_digests = baseline.get("files", {}) if isinstance(baseline, dict) else {}
        for target, source, baseline_key, mode in source_specs:
            try:
                metadata = os.lstat(source)
            except OSError as exc:
                raise CodexRuntimeError("Protocol retrieval MCP source is unavailable") from exc
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP source is invalid")
            if expected_digests and expected_digests.get(baseline_key) != digest_file(source):
                raise CodexRuntimeError("Protocol retrieval MCP source drifts from baseline")
            try:
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            except FileExistsError as exc:
                raise CodexRuntimeError("Protocol retrieval MCP asset already exists") from exc
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(source.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                target.unlink(missing_ok=True)
                raise
            os.chmod(target, mode)
            staged = os.lstat(target)
            if (
                stat.S_ISLNK(staged.st_mode)
                or not stat.S_ISREG(staged.st_mode)
                or stat.S_IMODE(staged.st_mode) != mode
                or staged.st_uid != os.getuid()
            ):
                raise CodexRuntimeError("Protocol retrieval MCP staged asset metadata is invalid")
        agent.retrieval_mcp_path, agent.retrieval_verifier_path, agent.proof_v2_path = wrapper, verifier, proof_v2

    def probe_role_visibility(self, run: Any) -> dict[str, Any]:
        """Run only path-readability probes inside each Agent's own bwrap namespace."""
        if not self.use_bwrap:
            raise CodexRuntimeError("visibility probes require bubblewrap isolation")
        result: dict[str, Any] = {}
        forbidden_common = (
            "/home/yangxiang/projects/ontology-platform",
            "/agent/home/sources/../../protocol/home",
            "/agent/home/sources/docs/requirements/requirements-v2.3.md",
            "/agent/home/sources/docs/delivery/records/r2-3-002.md",
            "/agent/home/sources/docs/evaluation-scenarios/ontology-modeling-team-l3/tester-only/answer-contract.json",
            "/agent/home/tester-only",
            "/agent/home/history",
            "/agent/home/secrets",
        )
        for agent in self.agents.values():
            sibling_process_paths = []
            for candidate in self.agents.values():
                if candidate.agent_id == agent.agent_id:
                    continue
                pid = candidate.app_server_host_pid
                if not isinstance(pid, int) or pid <= 0:
                    raise CodexRuntimeError("sibling app-server host PID is unavailable for visibility probe")
                sibling_process_paths.append(f"/proc/{pid}/environ")
            allowed = [
                "/agent/home/sources/" + source.relative_path.as_posix()
                for source in run.configuration.task.role_sources
                if agent.package.role in source.roles
            ]
            checks = " ".join(shlex.quote(path) for path in allowed)
            sibling_socket = next(
                f"/agent/transport/{candidate.agent_id}.sock"
                for candidate in self.agents.values()
                if candidate.agent_id != agent.agent_id
            )
            denied = " ".join(
                shlex.quote(path)
                for path in (*forbidden_common, sibling_socket, *sibling_process_paths)
            )
            script = (
                "set -eu; "
                "test -e /proc/self/environ; "
                f"for path in {checks}; do test -r \"$path\"; done; "
                f"for path in {denied}; do test ! -e \"$path\"; done"
            )
            command = self.namespace_command(agent)
            separator = command.index("--")
            probe_command = command[: separator + 1] + ["/bin/sh", "-c", script]
            descriptors = agent.retrieval_asset_fds
            try:
                completed = subprocess.run(
                    probe_command,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    pass_fds=descriptors,
                )
            finally:
                self._close_retrieval_asset_fds(agent)
            if completed.returncode != 0:
                raise CodexRuntimeError(f"role Runtime visibility probe failed for {agent.agent_id}")
            result[agent.agent_id] = {
                "allowed_path_count": len(allowed),
                "forbidden_path_categories": ["repo", "sibling", "socket", "tester", "history", "sibling-process", "secret"],
            }
        return result

    def _stage_skills(self, agent: _Agent) -> None:
        seen: set[str] = set()
        for source in agent.package.required_skills:
            skill_dir = source.parent
            target = agent.skills / skill_dir.name
            if target.name in seen:
                raise CodexRuntimeError("duplicate staged Skill directory")
            seen.add(target.name)
            shutil.copytree(skill_dir, target, symlinks=False)
            for item in target.rglob("*"):
                if item.is_symlink():
                    raise CodexRuntimeError("Skill staging refuses symlinks")
                if item.is_file():
                    os.chmod(item, 0o444)

    def _write_config(self, run: Any, agent: _Agent) -> None:
        task = getattr(getattr(run, "configuration", None), "task", None)
        if agent.package.role == "protocol" and getattr(task, "schema_version", 1) == 2:
            run_id = getattr(run, "run_id", None)
            if not isinstance(run_id, str) or not run_id:
                raise CodexRuntimeError(
                    "v2 Protocol mechanics MCP requires a run ID runtime binding"
                )
            if self._run_id is not None and self._run_id != run_id:
                raise CodexRuntimeError(
                    "v2 Protocol mechanics MCP run ID drifts from the active runtime"
                )
        # Only the Protocol receives its key/config; no secret is persisted outside its private home.
        host_auth = self.preflight_host_auth()
        shutil.copyfile(host_auth, agent.home / "auth.json")
        os.chmod(agent.home / "auth.json", 0o600)
        shutil.copyfile(
            self.root / "modeling_team" / "transport_mcp.py",
            agent.home / "transport_mcp.py",
        )
        source_root = run.root / "sources"
        if getattr(task, "schema_version", 1) == 2:
            source_root = source_root / agent.package.role
        shutil.copytree(source_root, agent.home / "sources")
        os.chmod(agent.home / "transport_mcp.py", 0o444)
        # This private config deliberately does not inherit the user's Codex config.  The
        # CLI flags below are a second, command-line enforced layer because several of
        # these are stable features enabled by default in interactive Codex installations.
        # A Team Profile owns the only model-visible tool surface for this experiment.
        lines = [
            'sandbox_mode = "read-only"',
            'web_search = "disabled"',
            "[features]",
            "apps = false",
            "plugins = false",
            "multi_agent = false",
            "multi_agent_v2 = false",
            "browser_use = false",
            "computer_use = false",
            "image_generation = false",
            "memories = false",
            "hooks = false",
            "skill_search = false",
            "tool_suggest = false",
            "[mcp_servers.team_transport]",
            'command = "/usr/bin/python3"',
            'args = ["/agent/home/transport_mcp.py"]',
            "required = true",
            "[mcp_servers.team_transport.env]",
            f'TEAM_TRANSPORT_SOCKET = "/agent/transport/{agent.agent_id}.sock"',
        ]
        if agent.package.role == "protocol":
            key = run.protocol_key
            if not key:
                raise CodexRuntimeError(
                    "Protocol key is required before Runtime startup"
                )
            platform = agent.home / "platform"
            shutil.copytree(self.root / "backend" / "app", platform / "app")
            lines.extend(
                protocol_mcp_launch_spec(
                    agent.platform_tools,
                    schema_version=getattr(task, "schema_version", 1),
                ).config_lines(api_key=key)
            )
            if getattr(task, "schema_version", 1) == 2:
                lines.extend(
                    [
                        "[mcp_servers.protocol_mechanics]",
                        'command = "/usr/bin/python3"',
                        'args = ["/opt/protocol-retrieval-mcp.py"]',
                        "required = true",
                        "[mcp_servers.protocol_mechanics.env]",
                        f'PROTOCOL_RUNTIME_RUN_ID = {json.dumps(run_id)}',
                    ]
                )
        (agent.home / "config.toml").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        os.chmod(agent.home / "config.toml", 0o600)

    def namespace_command(self, agent: _Agent) -> list[str]:
        binary = shutil.which(self.codex_binary) or self.codex_binary
        if not self.use_bwrap:
            return [binary, "app-server"]
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise CodexRuntimeError("bubblewrap is required for per-Agent isolation")
        # No host root or repo mount: only immutable runtime libraries and this Agent's private inputs.
        command = [
            bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]
        for source in (
            "/usr",
            "/bin",
            "/lib",
            "/lib64",
            "/etc/ld.so.cache",
            "/etc/resolv.conf",
            "/etc/hosts",
            "/etc/nsswitch.conf",
            "/etc/ssl/certs",
        ):
            if Path(source).exists():
                command.extend(["--ro-bind", source, source])
        command += [
            "--dir",
            "/agent",
            "--bind",
            str(agent.home),
            "/agent/home",
            "--bind",
            str(agent.work),
            "/agent/work",
            "--ro-bind",
            str(agent.skills),
            "/skills",
            "--dir",
            "/agent/transport",
            "--bind",
            str(self._transport_root() / f"{agent.agent_id}.sock"),
            f"/agent/transport/{agent.agent_id}.sock",
            "--chdir",
            "/agent/work",
            "--setenv",
            "CODEX_HOME",
            "/agent/home",
            "--setenv",
            "TERM",
            "xterm-256color",
        ]
        app_server_command = [
            "--config",
            'web_search="disabled"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "multi_agent_v2",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "image_generation",
            "--disable",
            "memories",
            "--disable",
            "hooks",
            "app-server",
        ]
        if agent.package.role == "protocol":
            resolved_python = (self.root / "backend" / ".venv" / "bin" / "python").resolve()
            runtime_root = resolved_python.parent.parent
            runtime_dirs: list[str] = []
            current = Path("/")
            for part in runtime_root.parent.parts[1:]:
                current /= part
                runtime_dirs.extend(["--dir", str(current)])
            command[command.index("--chdir") : command.index("--chdir")] = [
                "--dir",
                "/backend",
                "--ro-bind",
                str(self.root / "backend" / "app"),
                "/backend/app",
                "--ro-bind",
                str(self.root / "backend" / ".venv"),
                "/backend/.venv",
                *runtime_dirs,
                "--ro-bind",
                str(runtime_root),
                str(runtime_root),
            ]
            if agent.mechanics_contract_path is not None:
                self._read_protocol_mechanics_contract(agent)
                command[command.index("--chdir") : command.index("--chdir")] = [
                    "--dir",
                    "/opt",
                    "--ro-bind",
                    str(agent.mechanics_contract_path),
                    "/opt/mechanics-contract.json",
                ]
            if (
                agent.retrieval_mcp_path is not None
                or agent.retrieval_verifier_path is not None
                or agent.proof_v2_path is not None
            ):
                descriptors = self._open_protocol_retrieval_assets(agent)
                command[command.index("--chdir") : command.index("--chdir")] = [
                    "--dir",
                    "/opt",
                    "--ro-bind",
                    f"/proc/self/fd/{descriptors[0]}",
                    "/opt/protocol-retrieval-mcp.py",
                    "--ro-bind",
                    f"/proc/self/fd/{descriptors[1]}",
                    "/opt/protocol_mechanics.py",
                    "--ro-bind",
                    f"/proc/self/fd/{descriptors[2]}",
                    "/opt/proof_v2.py",
                ]
            if agent.schema_version == 2:
                reasoner = self._protocol_reasoner_script()
                command[command.index("--chdir") : command.index("--chdir")] = [
                    "--dir",
                    "/backend/scripts",
                    "--ro-bind",
                    str(reasoner),
                    "/backend/scripts/dev_owl_reasoner.py",
                ]
        command[command.index("--chdir") : command.index("--chdir")] = [
            "--dir",
            "/agent/bin",
            "--ro-bind",
            binary,
            "/agent/bin/codex",
        ]
        return command + ["--", "/agent/bin/codex", *app_server_command]

    def _protocol_reasoner_script(self) -> Path:
        script = self.root / "backend" / "scripts" / "dev_owl_reasoner.py"
        try:
            metadata = os.lstat(script)
        except OSError as exc:
            raise CodexRuntimeError("Protocol reasoner script is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CodexRuntimeError("Protocol reasoner script is unavailable")
        return script

    def _transport_root(self) -> Path:
        if self._run_root is None:
            raise CodexRuntimeError("Runtime is missing its run root")
        state_file = self._run_root / "transport-root"
        if state_file.is_file():
            return Path(state_file.read_text(encoding="utf-8"))
        return self._run_root / "transport" / "broker"

    def _start_process(self, agent: _Agent) -> subprocess.Popen[str]:
        command = self.namespace_command(agent)
        descriptors = agent.retrieval_asset_fds
        try:
            return self.process_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                pass_fds=descriptors,
            )
        finally:
            self._close_retrieval_asset_fds(agent)

    def _open_protocol_retrieval_assets(self, agent: _Agent) -> tuple[int, ...]:
        """Open immutable wrapper/verifier/proof descriptors for the Protocol-only bwrap mount."""
        if agent.retrieval_asset_fds:
            if len(agent.retrieval_asset_fds) != 3:
                raise CodexRuntimeError("Protocol retrieval MCP descriptor state is invalid")
            return agent.retrieval_asset_fds
        if (
            self._run_root is None
            or agent.package.role != "protocol"
            or agent.schema_version != 2
            or self.agents.get(agent.agent_id) is not agent
        ):
            raise CodexRuntimeError("Protocol retrieval MCP Agent identity is invalid")
        expected_root = self._run_root / "runtime-assets" / "protocol"
        expected = (
            (agent.retrieval_mcp_path, expected_root / "protocol-retrieval-mcp.py", self.root / "modeling_team/protocol_retrieval_mcp.py", 0o444),
            (agent.retrieval_verifier_path, expected_root / "protocol_mechanics.py", self.root / "modeling_team/protocol_mechanics.py", 0o444),
            (agent.proof_v2_path, expected_root / "proof_v2.py", self.root / "modeling_team/proof_v2.py", 0o600),
        )
        descriptors: list[int] = []
        try:
            for path, expected_path, source, mode in expected:
                if path != expected_path:
                    raise CodexRuntimeError("Protocol retrieval MCP asset path is invalid")
                parent = os.lstat(expected_path.parent)
                if (
                    stat.S_ISLNK(parent.st_mode)
                    or not stat.S_ISDIR(parent.st_mode)
                    or stat.S_IMODE(parent.st_mode) != 0o700
                    or parent.st_uid != os.getuid()
                ):
                    raise CodexRuntimeError("Protocol retrieval MCP asset parent is invalid")
                try:
                    descriptor = os.open(expected_path, os.O_RDONLY | os.O_NOFOLLOW)
                except OSError as exc:
                    raise CodexRuntimeError("Protocol retrieval MCP asset is unavailable") from exc
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != mode
                    or metadata.st_uid != os.getuid()
                ):
                    os.close(descriptor)
                    raise CodexRuntimeError("Protocol retrieval MCP asset metadata is invalid")
                payload = bytearray()
                while chunk := os.read(descriptor, 65536):
                    payload.extend(chunk)
                if hashlib.sha256(payload).hexdigest() != digest_file(source):
                    os.close(descriptor)
                    raise CodexRuntimeError("Protocol retrieval MCP asset digest is invalid")
                descriptors.append(descriptor)
            agent.retrieval_asset_fds = tuple(descriptors)
            return tuple(descriptors)
        except Exception:
            for descriptor in descriptors:
                os.close(descriptor)
            raise

    @staticmethod
    def _close_retrieval_asset_fds(agent: _Agent) -> None:
        for descriptor in agent.retrieval_asset_fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        agent.retrieval_asset_fds = ()

    @staticmethod
    def _host_child_pids(pid: int) -> list[int]:
        children = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            return [int(value) for value in children.read_text(encoding="utf-8").split()]
        except (OSError, ValueError) as exc:
            raise CodexRuntimeError("cannot inspect app-server process tree") from exc

    @staticmethod
    def _host_process_identity(pid: int) -> tuple[str, str]:
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
            name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CodexRuntimeError("cannot inspect app-server process identity") from exc
        return name, command

    def _app_server_host_pid(self, agent: _Agent) -> int:
        """Resolve the inner app-server PID, never retaining wrapper PIDs as evidence."""
        wrapper_pid = getattr(agent.process, "pid", None)
        if not isinstance(wrapper_pid, int) or wrapper_pid <= 0:
            raise CodexRuntimeError("app-server wrapper host PID is unavailable")
        pending = [wrapper_pid]
        leaves: list[int] = []
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            children = self._host_child_pids(current)
            if children:
                pending.extend(children)
            else:
                leaves.append(current)
        identities = {
            pid: self._host_process_identity(pid) for pid in seen - {wrapper_pid}
        }
        candidates = [
            pid for pid, (name, command) in identities.items() if name != "bwrap" and "app-server" in command
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(leaves) != 1 or leaves[0] == wrapper_pid:
            raise CodexRuntimeError("cannot resolve a unique app-server host PID")
        return leaves[0]

    def _rpc(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        with agent.io_lock:
            return self._rpc_locked(agent, method, params)

    def _rpc_locked(
        self, agent: _Agent, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if (
            agent.process is None
            or agent.process.stdin is None
            or agent.process.stdout is None
        ):
            raise CodexRuntimeError("app-server is unavailable")
        agent.request_id += 1
        request_id = agent.request_id
        agent.process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            + "\n"
        )
        agent.process.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = self._read_output_line(agent, deadline - time.monotonic())
            if line is None:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CodexRuntimeError("malformed app-server JSON") from exc
            if value.get("id") == request_id:
                if "error" in value:
                    raise CodexRuntimeError(
                        f"app-server {method} failed: {value['error']}"
                    )
                return value.get("result", {})
            self._notification(agent, value)
        raise CodexRuntimeError(f"app-server did not answer {method}")

    def _drain_agent_output_locked(self, agent: _Agent) -> None:
        """Apply every App Server notification already readable while holding its I/O lock."""
        if agent.process is None or agent.process.stdout is None:
            return
        while True:
            line = self._read_output_line(agent, 0)
            if line is None:
                return
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                with agent.state_lock:
                    agent.state = "failed"
                raise CodexRuntimeError("malformed app-server JSON") from exc
            self._notification(agent, value)

    @staticmethod
    def _read_output_line(agent: _Agent, timeout: float) -> str | None:
        """Read one JSON line without losing TextIO-buffered App Server responses."""
        if agent.process is None or agent.process.stdout is None:
            raise CodexRuntimeError("app-server is unavailable")
        if b"\n" in agent.stdout_buffer:
            line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
            return line.decode("utf-8")
        if timeout <= 0:
            readable, _, _ = select.select([agent.process.stdout], [], [], 0)
            if not readable:
                return None
            data = os.read(agent.process.stdout.fileno(), 65536)
            if not data:
                raise CodexRuntimeError("app-server closed its output")
            agent.stdout_buffer += data
            if b"\n" in agent.stdout_buffer:
                line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
                return line.decode("utf-8")
            return None
        deadline = time.monotonic() + max(timeout, 0)
        while time.monotonic() < deadline:
            if b"\n" in agent.stdout_buffer:
                line, _, agent.stdout_buffer = agent.stdout_buffer.partition(b"\n")
                return line.decode("utf-8")
            remaining = deadline - time.monotonic()
            readable, _, _ = select.select(
                [agent.process.stdout], [], [], min(remaining, 0.25)
            )
            if not readable:
                continue
            data = os.read(agent.process.stdout.fileno(), 65536)
            if not data:
                raise CodexRuntimeError("app-server closed its output")
            agent.stdout_buffer += data
        return None

    def _initialize(self, agent: _Agent) -> None:
        self._rpc(
            agent,
            "initialize",
            {"clientInfo": {"name": "modeling-team", "version": "1"}},
        )
        # Discovery is a hard preflight, not a structured-input hint.
        self._rpc(agent, "skills/extraRoots/set", {"extraRoots": ["/skills"]})
        listed = self._rpc(
            agent, "skills/list", {"cwds": ["/agent/work"], "forceReload": True}
        )
        entries = listed.get("data", [])
        if not isinstance(entries, list) or len(entries) != 1:
            raise CodexRuntimeError("Skill discovery returned no exact cwd result")
        entry = entries[0]
        if not isinstance(entry, dict) or entry.get("errors"):
            raise CodexRuntimeError("Skill discovery reported an error")
        available = entry.get("skills", [])
        expected = {
            path.parent.name: f"/skills/{path.parent.name}/SKILL.md"
            for path in agent.package.required_skills
        }
        found: dict[str, str] = {}
        for item in available if isinstance(available, list) else []:
            if (
                isinstance(item, dict)
                and item.get("enabled") is True
                and not item.get("error")
            ):
                found[str(item.get("name"))] = str(
                    item.get("path", item.get("canonicalPath", ""))
                )
        if set(found) & set(expected) != set(expected) or any(
            found[name] != path for name, path in expected.items()
        ):
            raise CodexRuntimeError(
                "Skill discovery did not return exact enabled staged paths"
            )
        result = self._rpc(
            agent,
            "thread/start",
            {
                "cwd": "/agent/work",
                "baseInstructions": "",
                # Do not leave this null: app-server otherwise retains ambient developer
                # material from the authenticated interactive Codex environment.
                "developerInstructions": agent.package.instructions_path.read_text(
                    encoding="utf-8"
                ),
                "config": {
                    "web_search": "disabled",
                    "default_tools_enabled": False,
                    "developer_instructions": agent.package.instructions_path.read_text(
                        encoding="utf-8"
                    ),
                },
                "sandbox": agent.package.runtime["codex"]["sandbox"],
            },
        )
        thread_id = (
            result.get("thread", result).get("id") if isinstance(result, dict) else None
        )
        if not isinstance(thread_id, str):
            raise CodexRuntimeError("thread/start lacked Thread identity")
        agent.thread_id, agent.state = thread_id, "idle"
        self._require_expected_mcp_servers(agent)

    def _require_expected_mcp_servers(self, agent: _Agent) -> None:
        """Fail before the first turn unless the frozen per-role MCP surface is live."""
        expected = {"team_transport": {"send_team_message", "report_task_result"}}
        if agent.package.role == "protocol":
            expected["ontology_platform"] = set(agent.platform_tools)
            if agent.schema_version == 2:
                expected["protocol_mechanics"] = {
                    "build_candidate_receipt",
                    "verify_scoped_retrieval_fallback",
                    "write_candidate_item_evidence_map",
                }
        deadline = time.monotonic() + 25
        observed: dict[str, set[str]] = {}
        while time.monotonic() < deadline:
            result = self._rpc(agent, "mcpServerStatus/list", {"detail": "full"})
            data = result.get("data", []) if isinstance(result, dict) else []
            servers = {
                str(item.get("name")): item
                for item in data
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            observed = {}
            for name, item in servers.items():
                observed[name] = self._mcp_tool_names(item.get("tools", []))
            if observed == expected:
                return
            time.sleep(0.25)
        actual = {name: sorted(tools) for name, tools in observed.items()}
        raise CodexRuntimeError(
            f"MCP preflight failed for {agent.agent_id}: expected {sorted(expected)}, got {actual}"
        )

    @staticmethod
    def _mcp_tool_names(raw_tools: Any) -> set[str]:
        """Normalize the object and array forms emitted by app-server status."""
        if isinstance(raw_tools, dict):
            return {
                str(name)
                for name, tool in raw_tools.items()
                if isinstance(tool, dict)
                and isinstance(tool.get("name"), str)
                and tool["name"] == name
            }
        if isinstance(raw_tools, list):
            return {
                str(tool.get("name"))
                for tool in raw_tools
                if isinstance(tool, dict) and isinstance(tool.get("name"), str)
            }
        return set()

    def start_task(
        self, agent_id: str, task_text: str, skill_paths: list[str], roster: list[str]
    ) -> None:
        agent = self.agents[agent_id]
        injected = []
        for path in skill_paths:
            source = Path(path)
            staged = f"/skills/{source.parent.name}/SKILL.md"
            injected.append(
                {
                    "type": "skill",
                    "name": source.parent.name,
                    "path": staged,
                }
            )
        prompt = task_text + "\n\nFrozen roster: " + ", ".join(roster)
        agent.first_turn_input = injected + [{"type": "text", "text": prompt}]
        # Retain model-visible material, then verify exact Skills were included.
        if any(not digest_file(Path(path)) for path in skill_paths):
            raise CodexRuntimeError("Skill injection evidence drift")
        result = self._rpc(
            agent,
            "turn/start",
            {"threadId": agent.thread_id, "input": agent.first_turn_input},
        )
        agent.active_turn_id = self._turn_id(result)
        agent.state = "running"

    @staticmethod
    def _turn_id(result: dict[str, Any]) -> str | None:
        turn = result.get("turn", result)
        return (
            turn.get("id")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str)
            else None
        )

    @staticmethod
    def _expected_active_turn_id(error: str) -> str | None:
        match = re.search(r"found `([^`]+)`", error)
        return match.group(1) if match else None

    @staticmethod
    def _delivery_input(delivery: RuntimeDelivery) -> list[dict[str, str]]:
        """Render the stable Runner delivery envelope without changing its text field."""
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "sender_id": delivery.sender_id,
                        "recipient_id": delivery.recipient_id,
                        "kind": delivery.kind,
                        "text": delivery.text,
                        "delivery_id": delivery.delivery_id,
                        "expects_reply": delivery.expects_reply,
                        "reply_to_delivery_id": delivery.reply_to_delivery_id,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        ]

    def send_message(self, agent_id: str, delivery: RuntimeDelivery) -> None:
        # A turn/start notification may be queued before an outer message arrives. Pump it
        # first so turn/steer uses the App Server's active turn identity, not a stale reply.
        self.receive_messages()
        agent = self.agents[agent_id]
        if agent.active_turn_id:
            try:
                self._rpc(
                    agent,
                    "turn/steer",
                    {
                        "threadId": agent.thread_id,
                        "expectedTurnId": agent.active_turn_id,
                        "input": self._delivery_input(delivery),
                    },
                )
                return
            except CodexRuntimeError as exc:
                # App-server may finish a turn between its notification and our steer.
                # Its explicit rejection means the text was not accepted, so a fresh turn is safe.
                if "no active turn to steer" in str(exc):
                    agent.active_turn_id, agent.state = None, "idle"
                else:
                    active = self._expected_active_turn_id(str(exc))
                    if active:
                        # The server explicitly rejected the first request and supplies its
                        # active turn. One retry preserves the text without duplicating it.
                        agent.active_turn_id = active
                        self._rpc(
                            agent,
                            "turn/steer",
                            {
                                "threadId": agent.thread_id,
                                "expectedTurnId": agent.active_turn_id,
                                "input": self._delivery_input(delivery),
                            },
                        )
                        return
                    states = {item.agent_id: item.state for item in self.get_agent_states()}
                    if states.get(agent_id) == "running":
                        raise
        result = self._rpc(
            agent,
            "turn/start",
            {
                "threadId": agent.thread_id,
                "input": self._delivery_input(delivery),
            },
        )
        agent.active_turn_id, agent.state = self._turn_id(result), "running"

    def _notification(self, agent: _Agent, value: dict[str, Any]) -> None:
        method, params = value.get("method"), value.get("params", {})
        if isinstance(method, str):
            self._append_runtime_evidence(
                "app-server-events",
                {
                    "agent_id": agent.agent_id,
                    "method": method,
                    "has_request_id": "id" in value,
                    "param_keys": sorted(params) if isinstance(params, dict) else [],
                },
            )
        if method == "item/tool/call" and "id" in value and isinstance(params, dict):
            self._respond_dynamic_tool(agent, value["id"], params)
            return
        if (
            method == "mcpServer/elicitation/request"
            and "id" in value
            and isinstance(params, dict)
        ):
            # App Server routes MCP tool approval through elicitation. Accept only the preflight-
            # locked Profile servers plus the v2 Protocol-only native verifier; all other requests
            # fail closed.
            schema = params.get("requestedSchema")
            server_name = str(params.get("serverName", ""))
            expected = server_name == "team_transport" or (
                agent.package.role == "protocol" and server_name == "ontology_platform"
            ) or (
                agent.package.role == "protocol"
                and agent.schema_version == 2
                and server_name == "protocol_mechanics"
            )
            action = "accept" if expected else "decline"
            self._append_runtime_evidence(
                "mcp-elicitations",
                {
                    "agent_id": agent.agent_id,
                    "server_name": server_name,
                    "mode": str(params.get("mode", "")),
                    "schema_keys": sorted(schema) if isinstance(schema, dict) else [],
                    "action": action,
                },
            )
            self._respond_server_request(agent, value["id"], {"action": action, "content": {}})
            return
        if not isinstance(params, dict):
            return
        with agent.state_lock:
            if method == "item/agentMessage/delta":
                item_id, delta = params.get("itemId"), params.get("delta")
                if isinstance(item_id, str) and isinstance(delta, str):
                    agent.message_deltas.setdefault(item_id, []).append(delta)
            if method in {"item/completed", "item/updated"}:
                self._complete_agent_message(agent, params)
            if method == "item/completed":
                self._complete_retrieval_gate_item(agent, params)
            if method == "turn/started":
                turn = params.get("turn")
                if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                    agent.active_turn_id, agent.state = turn["id"], "running"
            if method in {"turn/completed", "turn/finished"}:
                agent.active_turn_id, agent.state = None, "idle"
            if method in {"turn/failed", "thread/error"}:
                agent.state = "failed"

    def _respond_dynamic_tool(
        self, agent: _Agent, request_id: Any, params: dict[str, Any]
    ) -> None:
        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        tool = params.get("tool")
        arguments = params.get("arguments")
        metadata = self._dynamic_tool_metadata(agent, tool, arguments)
        result = self._dynamic_tool_result(agent, tool, arguments)
        denial_category = self._dynamic_tool_denial_category(tool, arguments, result)
        self._append_runtime_evidence(
            "dynamic-tool-calls",
            {
                **metadata,
                "result": "accepted" if result.get("success") else "rejected",
                "content_item_count": len(result.get("contentItems", [])),
                **({"denial_category": denial_category} if denial_category else {}),
            },
        )
        self._respond_server_request(agent, request_id, result)

    @staticmethod
    def _respond_server_request(agent: _Agent, request_id: Any, result: dict[str, Any]) -> None:
        if agent.process is None or agent.process.stdin is None:
            raise CodexRuntimeError("app-server is unavailable")
        agent.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n"
        )
        agent.process.stdin.flush()

    def _dynamic_tool_metadata(
        self, agent: _Agent, tool: Any, arguments: Any
    ) -> dict[str, Any]:
        """Persist callback evidence without retaining request text or credentials."""
        agent.dynamic_tool_calls += 1
        safe_arguments = arguments if isinstance(arguments, dict) else {}
        argument_keys = sorted(safe_arguments)
        return {
            "agent_id": agent.agent_id,
            "callback_sequence": agent.dynamic_tool_calls,
            "tool": str(tool).rsplit("__", 1)[-1],
            "argument_keys": argument_keys,
            "argument_types": {
                key: type(value).__name__
                for key, value in safe_arguments.items()
            },
        }

    def _append_runtime_evidence(self, name: str, value: dict[str, Any]) -> None:
        if self._run_root is None:
            return
        evidence = self._run_root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (evidence / f"{name}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _dynamic_tool_result(
        self, agent: _Agent, tool: Any, arguments: Any
    ) -> dict[str, Any]:
        """Serve only the read-only files the frozen task exposes to the Agent."""
        transport_tool = str(tool).rsplit("__", 1)[-1]
        if transport_tool in {"send_team_message", "report_task_result"}:
            if not isinstance(arguments, dict):
                return self._dynamic_tool_error("Team Transport arguments are invalid")
            return self._team_transport_dynamic_result(agent, transport_tool, arguments)
        if tool != "exec" or not isinstance(arguments, dict):
            return self._dynamic_tool_error("unsupported dynamic tool")
        command = arguments.get("cmd", arguments.get("command"))
        if not isinstance(command, str) or not command:
            return self._dynamic_tool_error("dynamic exec requires a command string")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return self._dynamic_tool_error("dynamic exec syntax is not permitted")
        if len(tokens) < 2 or tokens[0] != "cat" or any(
            item.startswith("-") for item in tokens[1:]
        ):
            return self._dynamic_tool_error("dynamic exec command is not permitted")
        content: list[str] = []
        remaining = 100000
        for virtual_path in tokens[1:]:
            try:
                value = self._dynamic_read_content(agent, virtual_path)
            except CodexRuntimeError:
                return self._dynamic_tool_error("dynamic exec read failed")
            if value is None:
                return self._dynamic_tool_error("dynamic exec path is not permitted")
            content.append(value[:remaining])
            remaining -= len(content[-1])
            if remaining <= 0:
                break
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": "".join(content)}],
        }

    def _dynamic_read_content(self, agent: _Agent, virtual_path: str) -> str | None:
        if virtual_path == "/opt/mechanics-contract.json":
            return self._read_protocol_mechanics_contract(agent)
        staged = self._dynamic_read_path(agent, virtual_path)
        if staged is None:
            return None
        try:
            return staged.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CodexRuntimeError("dynamic exec read failed") from exc

    def _read_protocol_mechanics_contract(self, agent: _Agent) -> str:
        """Read the sole Protocol /opt asset through one verified descriptor."""
        if self._run_root is None or not isinstance(self._run_id, str) or not self._run_id:
            raise CodexRuntimeError("v2 Protocol mechanics contract has no active run")
        if agent.package.role != "protocol" or self.agents.get(agent.agent_id) is not agent:
            raise CodexRuntimeError("v2 Protocol mechanics contract Agent identity is invalid")
        expected = self._run_root / "runtime-assets" / "protocol" / "mechanics-contract.json"
        if agent.mechanics_contract_path != expected:
            raise CodexRuntimeError("v2 Protocol mechanics contract path is invalid")
        try:
            file_lstat = os.lstat(expected)
            parent_lstat = os.lstat(expected.parent)
            if (
                stat.S_ISLNK(file_lstat.st_mode)
                or stat.S_ISLNK(parent_lstat.st_mode)
                or not stat.S_ISDIR(parent_lstat.st_mode)
                or stat.S_IMODE(parent_lstat.st_mode) != 0o700
                or expected.resolve(strict=True) != expected
            ):
                raise CodexRuntimeError("v2 Protocol mechanics contract path is invalid")
            descriptor = os.open(expected, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise CodexRuntimeError("v2 Protocol mechanics contract is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o444:
                raise CodexRuntimeError("v2 Protocol mechanics contract metadata is invalid")
            payload = bytearray()
            while chunk := os.read(descriptor, 65536):
                payload.extend(chunk)
            actual = bytes(payload)
            expected_bytes = protocol_mechanics_contract_bytes(self._run_id)
            if (
                actual != expected_bytes
                or hashlib.sha256(actual).digest() != hashlib.sha256(expected_bytes).digest()
            ):
                raise CodexRuntimeError("v2 Protocol mechanics contract digest is invalid")
            try:
                return actual.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CodexRuntimeError("v2 Protocol mechanics contract encoding is invalid") from exc
        finally:
            os.close(descriptor)

    @staticmethod
    def _dynamic_read_path(agent: _Agent, virtual_path: str) -> Path | None:
        roots = {
            "/skills/": agent.skills,
            "/agent/home/sources/": agent.home / "sources",
        }
        for prefix, root in roots.items():
            if not virtual_path.startswith(prefix):
                continue
            try:
                resolved = (root / virtual_path.removeprefix(prefix)).resolve(strict=True)
                resolved.relative_to(root.resolve(strict=True))
            except (OSError, ValueError):
                return None
            return resolved if resolved.is_file() else None
        return None

    @staticmethod
    def _dynamic_tool_denial_category(
        tool: Any, arguments: Any, result: dict[str, Any]
    ) -> str | None:
        if result.get("success") or tool != "exec" or not isinstance(arguments, dict):
            return None
        command = arguments.get("cmd", arguments.get("command"))
        if not isinstance(command, str):
            return "invalid-exec"
        if "/proc/" in command:
            return "proc"
        if "/agent/transport/" in command:
            return "broker-socket"
        if "/skills/../" in command or "/agent/home/sources/../" in command:
            return "path-traversal"
        if any(token in command for token in ("curl", "wget", "POST", "PUT", "PATCH")):
            return "platform-write"
        if "/workspaces/" in command or "/runtime/" in command:
            return "host-run-root"
        return "exec-policy"

    def _complete_agent_message(self, agent: _Agent, params: dict[str, Any]) -> None:
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            return
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in agent.completed_message_ids:
            return
        text = item.get("text")
        if not isinstance(text, str):
            text = "".join(agent.message_deltas.get(item_id, []))
        agent.message_deltas.pop(item_id, None)
        if text:
            agent.completed_message_ids.add(item_id)
            self._messages.append(RuntimeMessage(agent.agent_id, text))

    def _complete_retrieval_gate_item(self, agent: _Agent, params: dict[str, Any]) -> None:
        with agent.state_lock:
            self._complete_retrieval_gate_item_locked(agent, params)

    def _complete_retrieval_gate_item_locked(
        self, agent: _Agent, params: dict[str, Any]
    ) -> None:
        """Advance the v2 fresh-create Protocol retrieval gate from completed MCP items only."""
        if not agent.fallback_eligible:
            return
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcpToolCall":
            return
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in agent.completed_mcp_item_ids:
            return
        agent.completed_mcp_item_ids.add(item_id)
        server, tool = item.get("server"), item.get("tool")
        if not isinstance(server, str) or not isinstance(tool, str):
            return
        if server == "ontology_platform" and tool == "query_semantic_context":
            self._complete_retrieval_query(agent, item)
            return
        if server == "protocol_mechanics" and tool == "verify_scoped_retrieval_fallback":
            self._complete_retrieval_verifier(agent, item)
            return
        if server == "ontology_platform" and tool in {
            "submit_modeling_batch",
            "run_semantic_validation",
            "run_semantic_reasoning",
        }:
            self._complete_retrieval_mutation(agent, item)

    def _complete_retrieval_query(self, agent: _Agent, item: dict[str, Any]) -> None:
        if item.get("status") not in {"completed", "failed"}:
            return
        arguments = item.get("arguments")
        if not self._eligible_query_arguments(arguments):
            return
        assert isinstance(arguments, dict)
        agent.retrieval_episode += 1
        previous = agent.retrieval_state
        formal = self._formal_mcp_result(item)
        state = (
            "complete"
            if item.get("status") == "completed"
            and self._complete_generic_retrieval(formal, arguments["ontology_ids"])
            else "fallback_required"
        )
        agent.retrieval_state = state
        self._record_retrieval_transition(
            agent,
            tool="query_semantic_context",
            previous=previous,
            current=state,
            reason="generic_complete" if state == "complete" else "fallback_required",
        )

    def _complete_retrieval_verifier(self, agent: _Agent, item: dict[str, Any]) -> None:
        previous = agent.retrieval_state
        if previous not in {"fallback_required", "complete"}:
            return
        arguments = item.get("arguments")
        result = item.get("result")
        complete, category = self._native_verifier_completion(item, result)
        self._append_runtime_evidence(
            "native-verifier-events",
            {
                "role": agent.package.role,
                "tool": "verify_scoped_retrieval_fallback",
                "status": "accepted" if complete else "rejected",
                "complete": complete,
                "proof_arguments_sha256": self._safe_json_digest(arguments),
                "result_envelope_sha256": self._safe_json_digest(result),
                "category": category,
                "recorded_at_ns": time.time_ns(),
            },
        )
        if not complete:
            return
        if previous == "fallback_required":
            agent.retrieval_state = "fallback_satisfied"
            self._record_retrieval_transition(
                agent,
                tool="verify_scoped_retrieval_fallback",
                previous=previous,
                current="fallback_satisfied",
                reason="verifier_completed",
            )

    @staticmethod
    def _safe_json_digest(value: object) -> str:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CodexRuntimeError("native verifier event payload is not JSON") from exc
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _native_verifier_completion(
        cls, item: dict[str, Any], result: object
    ) -> tuple[bool, str]:
        """Classify only an actual native verifier completion, without retaining its payload."""
        if item.get("status") != "completed":
            return False, "failed"
        if not isinstance(item.get("arguments"), dict):
            return False, "invalid_arguments"
        if "error" in item:
            return False, "protocol_error"
        if not isinstance(result, dict) or result.get("isError") is True or "error" in result:
            return False, "protocol_error"
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            return False, "invalid_envelope"
        if structured.get("ok") is True:
            data = structured.get("data")
            if not isinstance(data, dict):
                return False, "invalid_envelope"
            return (True, "complete") if data.get("complete") is True else (False, "incomplete")
        # The native stdio facade projects its successful `{complete: true, ...}`
        # result directly as structuredContent.  Keep accepting that real result
        # shape while rejecting any missing/false completion marker.
        if structured.get("complete") is True and "error" not in structured:
            return True, "complete"
        return False, "incomplete"

    def _complete_retrieval_mutation(self, agent: _Agent, item: dict[str, Any]) -> None:
        if item.get("status") != "completed":
            return
        tool = item.get("tool")
        arguments = item.get("arguments")
        if tool == "submit_modeling_batch" and (
            not isinstance(arguments, dict) or arguments.get("mode") != "apply_atomic"
        ):
            return
        formal = self._formal_mcp_result(item)
        if not self._formal_success(formal):
            return
        previous = agent.retrieval_state
        agent.retrieval_state = "query_required"
        self._record_retrieval_transition(
            agent,
            tool=tool,
            previous=previous,
            current="query_required",
            reason="semantic_state_changed",
        )

    @staticmethod
    def _eligible_query_arguments(arguments: object) -> bool:
        if not isinstance(arguments, dict) or arguments.get("scope_mode") != "ontologies":
            return False
        ontology_ids = arguments.get("ontology_ids")
        return isinstance(ontology_ids, list) and bool(ontology_ids) and all(
            isinstance(ontology_id, str) and bool(ontology_id.strip()) for ontology_id in ontology_ids
        )

    @staticmethod
    def _formal_mcp_result(item: dict[str, Any]) -> dict[str, Any] | None:
        result = item.get("result")
        if not isinstance(result, dict):
            return None
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        return None

    @staticmethod
    def _formal_success(value: object) -> bool:
        return isinstance(value, dict) and value.get("ok") is True and isinstance(value.get("data"), dict)

    def _complete_generic_retrieval(
        self, formal: dict[str, Any] | None, requested_ontology_ids: object
    ) -> bool:
        if not self._formal_success(formal) or not isinstance(requested_ontology_ids, list):
            return False
        assert formal is not None
        data = formal["data"]
        if data.get("result_status") != "matched":
            return False
        recall, matches_page, context_page = (
            data.get("recall"),
            data.get("matches_page"),
            data.get("context_page"),
        )
        if (
            not isinstance(recall, dict)
            or recall.get("completeness") != "complete"
            or data.get("truncated") is not False
            or not isinstance(matches_page, dict)
            or matches_page.get("truncated") is not False
            or matches_page.get("next_match_cursor") is not None
            or not isinstance(context_page, dict)
            or context_page.get("truncated") is not False
            or context_page.get("next_context_cursor") is not None
        ):
            return False
        requested = set(requested_ontology_ids)
        if not requested or not self._warnings_are_complete(data.get("warnings")):
            return False
        for collection in (data.get("primary_matches"), data.get("related_context")):
            if not isinstance(collection, list):
                return False
            for item in collection:
                if not isinstance(item, dict) or item.get("ontology_id") not in requested:
                    return False
                if item.get("assertion_kind") == "asserted" and item.get("evidence_status") != "supported":
                    return False
                lineage = item.get("lineage")
                if not isinstance(lineage, dict) or lineage.get("status") != "complete":
                    return False
                if not self._warnings_are_complete(item.get("warnings")):
                    return False
        return True

    @staticmethod
    def _warnings_are_complete(warnings: object) -> bool:
        if not isinstance(warnings, list):
            return False
        for warning in warnings:
            if not isinstance(warning, dict) or not isinstance(warning.get("code"), str):
                return False
            if warning["code"] in _RETRIEVAL_BLOCKING_WARNINGS:
                return False
        return True

    def _record_retrieval_transition(
        self,
        agent: _Agent,
        *,
        tool: object,
        previous: str,
        current: str,
        reason: str,
    ) -> None:
        self._append_runtime_evidence(
            "protocol-retrieval-gate",
            {
                "agent_id": agent.agent_id,
                "tool": str(tool),
                "episode": agent.retrieval_episode,
                "from": previous,
                "to": current,
                "reason": reason,
            },
        )

    def terminal_report_blocked(
        self, agent_id: str, already_synchronized: bool = False
    ) -> bool:
        """Synchronize pending Agent output before the Broker decides a terminal report."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        if already_synchronized is not True:
            if not agent.io_lock.acquire(blocking=False):
                return True
            try:
                self._drain_agent_output_locked(agent)
            except Exception:
                return True
            finally:
                agent.io_lock.release()
        with agent.state_lock:
            blocked = agent.fallback_eligible and agent.retrieval_state in {
                "fallback_required",
                "query_required",
            }
            if blocked:
                self._record_retrieval_transition(
                    agent,
                    tool="report_task_result",
                    previous=agent.retrieval_state,
                    current=agent.retrieval_state,
                    reason="terminal_blocked",
                )
            return blocked

    def _team_transport_dynamic_result(
        self, agent: _Agent, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute only frozen Profile transport tools through the Agent-owned socket."""
        request = {"method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        if tool == "report_task_result":
            # This request originates inside ordered App Server notification dispatch.  It alone
            # has already synchronized stdout before the Broker calls the Runtime guard.
            request["already_synchronized"] = True
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(10)
                connection.connect(str(self._transport_root() / f"{agent.agent_id}.sock"))
                connection.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
                response = connection.makefile("r", encoding="utf-8").readline(4097)
            if len(response) > 4096:
                return self._dynamic_tool_error("Team Transport rejected the request")
            result = json.loads(response)
        except (OSError, ValueError, json.JSONDecodeError):
            return self._dynamic_tool_error("Team Transport is unavailable")
        if not isinstance(result, dict):
            if tool == "report_task_result":
                self._append_runtime_evidence(
                    "team-transport-events",
                    {
                        "agent": agent.agent_id,
                        "tool": "report_task_result",
                        "status": "rejected",
                        "category": "transport_protocol_error",
                        "ack": "not_applicable",
                        "recorded_at_ns": time.time_ns(),
                    },
                )
            return self._dynamic_tool_error("Team Transport rejected the request")
        if "error" in result:
            error = self._safe_transport_error(agent, result["error"])
            if error is None:
                if tool == "report_task_result":
                    self._append_runtime_evidence(
                        "team-transport-events",
                        {
                            "agent": agent.agent_id,
                            "tool": "report_task_result",
                            "status": "rejected",
                            "category": "untrusted_broker_error",
                            "ack": "not_applicable",
                            "recorded_at_ns": time.time_ns(),
                        },
                    )
                return self._dynamic_tool_error("Team Transport rejected the request")
            if tool == "report_task_result":
                category = (
                    "missing_modeling_handoff"
                    if error.startswith("terminal result requires terminal handoffs: ")
                    and "modeling" in error.rsplit(": ", 1)[-1].split(", ")
                    else "broker_rejection"
                )
                self._append_runtime_evidence(
                    "team-transport-events",
                    {
                        "agent": agent.agent_id,
                        "tool": "report_task_result",
                        "status": "rejected",
                        "category": category,
                        "ack": "not_applicable",
                        "recorded_at_ns": time.time_ns(),
                    },
                )
            return self._dynamic_tool_error(f"Team Transport rejected the request: {error}")
        if tool == "report_task_result":
            self._append_runtime_evidence(
                "team-transport-events",
                {
                    "agent": agent.agent_id,
                    "tool": "report_task_result",
                    "status": "accepted",
                    "category": "terminal_report_accepted",
                    "ack": "not_applicable",
                    "recorded_at_ns": time.time_ns(),
                },
            )
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": json.dumps(result)}],
        }

    def _safe_transport_error(self, agent: _Agent, value: object) -> str | None:
        """Accept only fixed broker RoutingError text; never reflect socket-controlled data."""
        if not isinstance(value, str) or len(value) > 200:
            return None
        fixed = {
            TERMINAL_REPORT_GUARD_ERROR,
            "recipient is not allowed by frozen Profile",
            "terminal result is invalid",
            "Agent already reported a terminal result",
            "terminal result dependencies are invalid",
            "unsupported Team Transport request",
            "invalid Team Transport arguments",
            "unknown Team Transport tool",
            "terminal result requires delivered reply",
            "completed terminal result requires an established reply request",
            "Team Transport reply arguments are invalid",
            "Team Transport reply is not an active reversed request",
            "Team Transport delivery acknowledgement is invalid",
            "Team Transport reply acknowledgement is invalid",
            "terminal handoff acknowledgement is invalid",
        }
        if value in fixed:
            return value
        prefix = "terminal result requires terminal handoffs: "
        if not value.startswith(prefix):
            return None
        if agent.package.role not in {"coordinator", "protocol"} or self.agents.get(agent.agent_id) is not agent:
            return None
        expected: list[str] = []
        dependency_roles = ("modeling", "protocol") if agent.package.role == "coordinator" else ("modeling",)
        for role in dependency_roles:
            matching = [
                candidate.agent_id
                for candidate in self.agents.values()
                if candidate.package.role == role
            ]
            if len(matching) != 1:
                return None
            expected.extend(matching)
        expected_count = 2 if agent.package.role == "coordinator" else 1
        if len(set(expected)) != expected_count:
            return None
        role_names = value[len(prefix) :].split(", ")
        if ", ".join(role_names) != value[len(prefix) :]:
            return None
        return value if role_names == sorted(expected) else None

    @staticmethod
    def _dynamic_tool_error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "contentItems": [{"type": "inputText", "text": message}],
        }

    def receive_messages(self) -> list[RuntimeMessage]:
        for agent in self.agents.values():
            with agent.io_lock:
                self._drain_agent_output_locked(agent)
        values, self._messages = self._messages[:], []
        return values

    def get_agent_states(self) -> list[AgentState]:
        return [AgentState(key, value.state) for key, value in self.agents.items()]

    def wait_settled(self, agent_ids: list[str], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(
                self.agents[key].state not in {"starting", "running"}
                for key in agent_ids
            ):
                return True
            time.sleep(0.05)
        return False

    def pause(self) -> None:
        for agent in self.agents.values():
            if agent.active_turn_id:
                self._rpc(
                    agent,
                    "turn/interrupt",
                    {"threadId": agent.thread_id, "turnId": agent.active_turn_id},
                )
                agent.state = "idle"

    def resume(self) -> None:
        return None

    def stop(self) -> None:
        for agent in self.agents.values():
            self._close_retrieval_asset_fds(agent)
            if agent.process and agent.process.poll() is None:
                try:
                    os.killpg(os.getpgid(agent.process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    agent.process.terminate()
                try:
                    agent.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(agent.process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        agent.process.kill()
                    agent.process.wait(timeout=5)
            for name in ("auth.json", "config.toml"):
                credential = agent.home / name
                credential.unlink(missing_ok=True)
            self._private_credentials_destroyed[agent.agent_id] = True
            agent.state = "stopped"

    def cleanup_identifiers(self) -> dict[str, Any]:
        return {
            key: {
                "thread_id": value.thread_id,
                "pid": value.process.pid if value.process else None,
                "private_credentials_destroyed": self._private_credentials_destroyed.get(
                    key, False
                ),
            }
            for key, value in self.agents.items()
        }
