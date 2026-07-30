"""Codex app-server implementation; its Thread and turn fields stay private here."""

from __future__ import annotations

import json
import os
import re
import select
import shlex
import signal
import socket
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..contracts import AgentPackage, digest_file
from .base import AgentRuntimeIdentity, AgentState, RuntimeAdapter, RuntimeDelivery, RuntimeMessage


class CodexRuntimeError(RuntimeError):
    pass


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
        self._private_credentials_destroyed: dict[str, bool] = {}

    def start_roster(self, run: Any, agents: Any) -> list[AgentRuntimeIdentity]:
        self._run_root = run.root
        identities: list[AgentRuntimeIdentity] = []
        for profile_agent in agents:
            package = profile_agent.package
            base = run.root / "runtime" / profile_agent.agent_id
            home, work, skills = base / "home", base / "work", base / "skills"
            for path in (home, work, skills):
                path.mkdir(parents=True, mode=0o700, exist_ok=False)
            agent = _Agent(profile_agent.agent_id, package, home, work, skills)
            self.agents[agent.agent_id] = agent
            self._stage_skills(agent)
            self._write_config(run, agent)
            agent.process = self._start_process(agent)
            self._initialize(agent)
            identities.append(
                AgentRuntimeIdentity(agent.agent_id, f"codex-thread:{agent.thread_id}")
            )
        return identities

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
        # Only the Protocol receives its key/config; no secret is persisted outside its private home.
        host_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        host_auth = host_home / "auth.json"
        if not host_auth.is_file():
            raise CodexRuntimeError(
                "host Codex authentication is unavailable for private staging"
            )
        shutil.copyfile(host_auth, agent.home / "auth.json")
        os.chmod(agent.home / "auth.json", 0o600)
        shutil.copyfile(
            self.root / "modeling_team" / "transport_mcp.py",
            agent.home / "transport_mcp.py",
        )
        shutil.copytree(run.root / "sources", agent.home / "sources")
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
                [
                    "[mcp_servers.ontology_platform]",
                    'command = "/backend/.venv/bin/python"',
                    'args = ["-m", "app.mcp.server"]',
                    'cwd = "/backend"',
                    "required = true",
                    'enabled_tools = ["check_platform_health"]',
                    "[mcp_servers.ontology_platform.env]",
                    'PYTHONPATH = "/agent/home/platform"',
                    f'ONTOLOGY_MCP_API_KEY = "{key}"',
                    'ONTOLOGY_MCP_BASE_URL = "http://127.0.0.1:8001"',
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
            "/agent/bin/codex",
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
        command[command.index("--chdir") : command.index("--chdir")] = [
            "--dir",
            "/agent/bin",
            "--ro-bind",
            binary,
            "/agent/bin/codex",
        ]
        return command

    def _transport_root(self) -> Path:
        if self._run_root is None:
            raise CodexRuntimeError("Runtime is missing its run root")
        state_file = self._run_root / "transport-root"
        if state_file.is_file():
            return Path(state_file.read_text(encoding="utf-8"))
        return self._run_root / "transport" / "broker"

    def _start_process(self, agent: _Agent) -> subprocess.Popen[str]:
        return self.process_factory(
            self.namespace_command(agent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def _rpc(
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
            expected["ontology_platform"] = {"check_platform_health"}
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
            if all(observed.get(name) == tools for name, tools in expected.items()) and (
                agent.package.role == "protocol" or "ontology_platform" not in observed
            ):
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
            # App Server routes MCP tool approval through elicitation.  Accept only the two
            # preflight-locked Profile servers; all other interactive requests fail closed.
            schema = params.get("requestedSchema")
            server_name = str(params.get("serverName", ""))
            expected = server_name == "team_transport" or (
                agent.package.role == "protocol" and server_name == "ontology_platform"
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
        if method == "item/agentMessage/delta":
            item_id, delta = params.get("itemId"), params.get("delta")
            if isinstance(item_id, str) and isinstance(delta, str):
                agent.message_deltas.setdefault(item_id, []).append(delta)
        if method in {"item/completed", "item/updated"}:
            self._complete_agent_message(agent, params)
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
            staged = self._dynamic_read_path(agent, virtual_path)
            if staged is None:
                return self._dynamic_tool_error("dynamic exec path is not permitted")
            try:
                value = staged.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return self._dynamic_tool_error("dynamic exec read failed")
            content.append(value[:remaining])
            remaining -= len(content[-1])
            if remaining <= 0:
                break
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": "".join(content)}],
        }

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

    def _team_transport_dynamic_result(
        self, agent: _Agent, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute only frozen Profile transport tools through the Agent-owned socket."""
        request = {"method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(10)
                connection.connect(str(self._transport_root() / f"{agent.agent_id}.sock"))
                connection.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
                response = connection.makefile("r", encoding="utf-8").readline()
            result = json.loads(response)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._dynamic_tool_error(f"Team Transport failed: {exc}")
        if not isinstance(result, dict) or "error" in result:
            return self._dynamic_tool_error("Team Transport rejected the request")
        return {
            "success": True,
            "contentItems": [{"type": "inputText", "text": json.dumps(result)}],
        }

    @staticmethod
    def _dynamic_tool_error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "contentItems": [{"type": "inputText", "text": message}],
        }

    def receive_messages(self) -> list[RuntimeMessage]:
        for agent in self.agents.values():
            if agent.process is None or agent.process.stdout is None:
                continue
            while True:
                line = self._read_output_line(agent, 0)
                if line is None:
                    break
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    agent.state = "failed"
                    raise CodexRuntimeError("malformed app-server JSON") from exc
                self._notification(agent, value)
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
