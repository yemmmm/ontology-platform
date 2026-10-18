"""R4.3-031 production-only DSH adapter, one isolated process/session per role."""

from __future__ import annotations

import dataclasses
import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    AgentRuntimeIdentity,
    AgentState,
    RuntimeAdapter,
    RuntimeDelivery,
    RuntimeDispatchReceipt,
    RuntimeMessage,
)
from .dsh_build import PLUGINS, digest, freeze_build
from .dsh_events import DispatchProjection
from .role_isolation import namespace_base, stage_skills
from ..capability_mcp import ROLE_MATERIAL_TOOL
from ..deepseek_provider_proxy import preflight_deepseek_credential, read_deepseek_credential
from ..messages_provider_proxy import MessagesProviderSession
from ..usage_capture import NumericReceiptWriter
from ..model_routing import validate_runtime_model_profile


class DshRuntimeError(RuntimeError):
    category = "runtime/infrastructure"

    def __init__(self, message, *, category="runtime/infrastructure"):
        super().__init__(message)
        self.category = category
        self.reason_code = message.split(":", 1)[0]


@dataclass
class _DshAgent:
    agent_id: str
    package: Any
    base: Path
    session_id: str
    instance: str = field(default_factory=lambda: uuid.uuid4().hex)
    process: Any = None
    state: str = "idle"
    responses: dict = field(default_factory=dict)
    response_condition: Any = field(default_factory=threading.Condition)
    write_lock: Any = field(default_factory=threading.Lock)
    projection: Any = None
    dispatches: dict = field(default_factory=dict)
    dispatching: int = 0
    terminal: bool = False
    wait: dict | None = None
    recovery: str | None = None
    next_rpc: int = 0
    pid_identity: str | None = None
    expected_tools: list = field(default_factory=list)
    material_manifest: dict = field(default_factory=dict)
    mounts: list = field(default_factory=list)
    stderr: Any = None
    pump: Any = None
    owned_pids: dict = field(default_factory=dict)
    ready: bool = False
    provider_error_epoch: int = 0
    recovery_error_epoch: int = 0
    recovering: bool = False


class DshRuntimeAdapter(RuntimeAdapter):
    runtime = "dsh"

    def __init__(
        self,
        *,
        repository_root: Path,
        harness_root: Path | None = None,
        process_factory=subprocess.Popen,
        provider_factory=MessagesProviderSession,
    ):
        self.root = Path(repository_root)
        self.harness_root = harness_root or Path("/home/yangxiang/deepseek-harness")
        self.process_factory = process_factory
        self.provider_factory = provider_factory
        self.agents: dict[str, _DshAgent] = {}
        self._lock = threading.RLock()
        self._messages = queue.SimpleQueue()
        self._wait_events = queue.SimpleQueue()
        self._failures = queue.SimpleQueue()
        self._paused = False
        self._closed = False
        self._run = None
        self._provider = None
        self._cleanup = {}
        self._control_epoch = 0
        self._build = None

    def _record(self, name, value):
        if self._run is None:
            return
        path = self._run.root / "evidence" / f"dsh-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Host-only files. DSH namespaces never mount the run evidence directory.
        with self._lock, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")

    def _register_usage(self, agent, binding, **context):
        self._provider.register_usage_session(agent.session_id, {
            "role": agent.package.role, "process_instance": agent.instance,
            "provider": binding.provider_id, "requested_model": binding.model,
            "requested_effort": binding.requested_effort,
            "effective_effort": binding.effective_effort, **context,
        }, evidence_ref="dsh-baseline.jsonl")

    @staticmethod
    def _socket(path, request):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(15)
            connection.connect(str(path))
            connection.sendall((json.dumps(request) + "\n").encode())
            return json.loads(connection.makefile("r").readline())

    def start_roster(self, run, agents):
        retry_load = False
        if self.agents:
            if not self._cleanup.get("complete"):
                raise DshRuntimeError("runtime still owns role processes; stop before reusing it")
            if self._run.run_id == run.run_id:
                if any(agent.dispatches for agent in self.agents.values()):
                    raise DshRuntimeError(
                        "original session has admitted or unknown input; explicitly reconcile and restore it"
                    )
                retry_load = True
            self.agents.clear()
        validate_runtime_model_profile("dsh", run.team_model_profile)
        self._run, self._closed = run, False
        self._cleanup = {}
        self._paused = False
        self._messages = queue.SimpleQueue()
        self._wait_events = queue.SimpleQueue()
        self._failures = queue.SimpleQueue()
        self._build = freeze_build(self.harness_root)
        credential = bytearray(
            read_deepseek_credential(run.provider_credential_bindings["deepseek-official"])
        )
        self._provider = self.provider_factory(
            credential, on_attempt=NumericReceiptWriter(run.root / "evidence" / "dsh-provider.jsonl")
        )
        credential[:] = b"\0" * len(credential)
        try:
            self._provider.start()
            for configured in agents:
                if "dsh" not in configured.package.runtime:
                    raise DshRuntimeError(
                        f"package {configured.package.package_id} requires runtime.dsh"
                    )
                agent = _DshAgent(
                    configured.agent_id,
                    configured.package,
                    run.root / "runtime" / configured.agent_id,
                    f"{run.run_id}-{configured.agent_id}-{uuid.uuid4().hex[:12]}",
                )
                if retry_load:
                    agent.base /= "load-" + agent.instance
                agent.projection = DispatchProjection(agent.session_id)
                self.agents[agent.agent_id] = agent
                self._stage(agent)
                self._launch(agent)
                binding = run.team_model_profile.binding_for(
                    agent.package.package_id, semantic_role=agent.package.role
                )
                self._register_usage(agent, binding, run_id=run.run_id, phase="production")
                result = self._rpc(
                    agent,
                    "initialize",
                    {
                        "cwd": "/agent/work",
                        "provider": binding.provider_id,
                        "model": binding.model,
                        "reasoningEffort": binding.effective_effort,
                    },
                )
                effective = result.get("effectiveBinding", {})
                if any(
                    effective.get(key) != expected
                    for key, expected in (
                        ("provider", binding.provider_id),
                        ("model", binding.model),
                        ("reasoningEffort", binding.effective_effort),
                    )
                ):
                    raise DshRuntimeError(
                        "dsh-model-binding-drift; correct the explicit model profile"
                    )
                inspection = self._rpc(agent, "host/inspect", {})
                self._check_tools(agent, inspection)
                agent.ready = True
                self._record(
                    "baseline",
                    {
                        "agent_id": agent.agent_id,
                        "session_id": agent.session_id,
                        "process_instance": agent.instance,
                        "build": self._build,
                        "composition_sha256": digest(
                            self.root / "modeling_team/runtimes/dsh_node/entry.mjs"
                        ),
                        "server_info": result,
                        "requested_binding": binding.as_dict(),
                        "effective_binding": effective,
                        "actual_tools": inspection,
                        "materials": agent.material_manifest,
                    },
                )
        except Exception:
            self.stop()
            raise
        return [self.runtime_identity(agent_id) for agent_id in self.agents]

    def _stage(self, agent):
        home, work, skills = (agent.base / name for name in ("home", "work", "skills"))
        for path in (home, work, skills):
            path.mkdir(parents=True, mode=0o700, exist_ok=False)
        stage_skills(agent.package, skills)
        for name in (
            "transport_mcp.py",
            "interventions.py",
            "capability_mcp.py",
            "read_proxy_mcp.py",
        ):
            shutil.copyfile(self.root / "modeling_team" / name, home / name)
        source_root = self._run.root / "sources"
        if self._run.configuration.task.schema_version == 2:
            source_root /= agent.package.role
        shutil.copytree(source_root, home / "sources")
        manifest = {}

        def material(source, original):
            identity = f"material-{len(manifest) + 1}"
            target = home / "materials" / f"{identity}.txt"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(source.read_bytes())
            target.chmod(0o444)
            manifest[identity] = {
                "file": f"/agent/home/materials/{target.name}",
                "source": str(original),
                "sha256": digest(target),
            }

        material(
            agent.package.instructions_path, agent.package.instructions_path.relative_to(self.root)
        )
        for path in sorted(skills.rglob("*")):
            if path.is_file():
                material(path, f"/skills/{path.relative_to(skills)}")
        for source in self._run.configuration.task.role_sources:
            if agent.package.role in source.roles:
                material(home / "sources" / source.relative_path, source.relative_path)
        for source in agent.package.references:
            for path in [source] if source.is_file() else sorted(source.rglob("*")):
                if path.is_file():
                    material(path, path.relative_to(self.root))
        agent.material_manifest = manifest
        (home / "role-materials.json").write_text(json.dumps(manifest))
        transport_root = getattr(self._run, "transport_root", self._run.root / "transport/broker")
        transport_socket = Path(transport_root) / f"{agent.agent_id}.sock"
        agent.mounts.append((transport_socket, "/agent/transport/role.sock"))
        servers = [
            {
                "serverName": "team_transport",
                "args": ["/agent/home/transport_mcp.py"],
                "env": {"TEAM_TRANSPORT_SOCKET": "/agent/transport/role.sock"},
            }
        ]
        listing = self._socket(transport_socket, {"method": "tools/list", "id": 1})
        expected = [("team_transport", tool) for tool in listing["tools"]]
        carrier = getattr(self._run, "acceptance", None)
        descriptor = getattr(carrier, "capability_descriptors", {}).get(agent.package.role)
        # The carrier retains historical formal Coordinator metadata even when
        # this run starts only the direct Modeling and CQ endpoints.
        if agent.package.role == "coordinator" and self._run.formal_contract is None:
            descriptor = None
        parameters = self._run.configuration.task.parameters or {}
        if (
            agent.package.role == "modeling"
            and parameters.get("unified_semantic_graph") is True
            and (
                not descriptor
                or "modeling_submit_model_changes" not in descriptor.get("operations", [])
            )
        ):
            raise DshRuntimeError(
                "platform-contract: required Modeling capability missing; bind the original direct-modeling endpoint"
            )
        if (
            agent.package.role == "competency-question"
            and parameters.get("competency_question_acceptance") is True
            and (
                not descriptor
                or "cq_publish_question_draft" not in descriptor.get("operations", [])
            )
        ):
            raise DshRuntimeError(
                "platform-contract: required private CQ capability missing; bind the original role endpoint"
            )
        if descriptor and descriptor.get("operations"):
            token = carrier.capability_token_path(agent.package.role)
            shutil.copyfile(token, home / "capability.token")
            (home / "capability.token").chmod(0o400)
            capability_socket = carrier.capability_socket_path(agent.package.role)
            agent.mounts.append((capability_socket, "/agent/home/capability.sock"))
            servers.append(
                {
                    "serverName": "runner_capability",
                    "args": [
                        "/agent/home/capability_mcp.py",
                        "--stdio",
                        "--socket",
                        "/agent/home/capability.sock",
                        "--token-file",
                        "/agent/home/capability.token",
                    ],
                    "env": {},
                }
            )
            request = {"token": token.read_text().strip(), "method": "tools/list", "id": 1}
            listing = self._socket(capability_socket, request)["result"]
            expected += [("runner_capability", tool) for tool in listing["tools"]]
        proxy = getattr(self._run, "modeling_read_proxy", None)
        if (
            agent.package.role == "modeling"
            and parameters.get("unified_semantic_graph") is True
            and proxy is None
        ):
            raise DshRuntimeError(
                "platform-contract: required Modeling read proxy missing; bind the original governed read surface"
            )
        if agent.package.role == "modeling" and proxy is not None:
            from ..read_proxy_mcp import _modeling_tool_schema

            (home / "read.token").write_text(proxy.token)
            (home / "read.token").chmod(0o400)
            agent.mounts.append((proxy.socket_path, "/agent/home/read.sock"))
            servers.append(
                {
                    "serverName": "modeling_read_proxy",
                    "args": [
                        "/agent/home/read_proxy_mcp.py",
                        "--stdio",
                        "--socket",
                        "/agent/home/read.sock",
                        "--token-file",
                        "/agent/home/read.token",
                    ],
                    "env": {
                        "PLATFORM_PROXY_MODE": "modeling",
                        "PLATFORM_PROXY_PROJECT_ID": str(proxy.project_id),
                        "PLATFORM_PROXY_ONTOLOGY_ID": str(proxy.ontology_id),
                    },
                }
            )
            expected += [
                ("modeling_read_proxy", _modeling_tool_schema(name)) for name in proxy.allowed_tools
            ]
        servers.append(
            {
                "serverName": "role_materials",
                "args": [
                    "/agent/home/capability_mcp.py",
                    "--role-materials",
                    "/agent/home/role-materials.json",
                ],
                "env": {},
            }
        )
        expected.append(("role_materials", ROLE_MATERIAL_TOOL))
        agent.expected_tools = expected
        instructions = agent.package.instructions_path.read_text()
        instructions += "\n" + "\n".join(path.read_text() for path in agent.package.required_skills)
        instructions += (
            "\nFrozen role material manifest (read_role_material reads original text):\n"
        )
        instructions += json.dumps(
            {key: {k: v for k, v in item.items() if k != "file"} for key, item in manifest.items()}
        )
        instructions += (
            "\nDSH runtime: no shell or general filesystem tool is available. "
            "For Coordinator scenario-map artifacts, use write_handoff_output with "
            "scenario-map/ relative paths; the supervising Host transfers your exact bytes "
            "to the existing Runner paths. Receive dynamic public CQ projections and freeze "
            "confirmation through sourced Host messages; do not guess material IDs. "
            "If terminal reporting says native input is pending, naturally end this activity "
            "to consume the original inbox, then retry once consumed. This ordinary wait "
            "requires no retrieval, rewrite, new issue or blocked terminal result."
        )
        config = {
            "modules": {
                key: "/dsh/" + str(Path(value).relative_to(self.harness_root))
                for key, value in self._build["modules"].items()
            },
            "providerURL": self._provider.base_url,
            "instructions": instructions,
            "servers": servers,
        }
        (home / "dsh.json").write_text(json.dumps(config))
        shutil.copyfile(self.root / "modeling_team/runtimes/dsh_node/entry.mjs", home / "entry.mjs")

    @staticmethod
    def _public_name(server, raw):
        import hashlib
        import re

        joined = f"mcp__{server}__{raw}"
        normalized = re.sub(r"[^A-Za-z0-9_-]", "_", joined)
        if normalized == joined and len(normalized) <= 64:
            return normalized
        suffix = hashlib.sha256(f"{server}\0{raw}".encode()).hexdigest()[:12]
        return normalized[:51] + "_" + suffix

    def _check_tools(self, agent, inspection):
        expected = {
            self._public_name(server, tool["name"]): tool for server, tool in agent.expected_tools
        }
        actual = {tool["name"]: tool for tool in inspection["tools"]}
        if len(actual) != len(inspection["tools"]) or set(expected) != set(actual):
            raise DshRuntimeError(
                f"dsh-tool-set-drift: role={agent.agent_id} missing={sorted(set(expected) - set(actual))} "
                f"extra={sorted(set(actual) - set(expected))}; correct composition/MCP config and retry role loading",
                category="platform-contract",
            )
        for name, tool in actual.items():
            # ToolRuntime calls MCP inputSchema `parameters`; the value stays exact.
            schema = tool.get("parameters", tool.get("inputSchema"))
            if schema != expected[name]["inputSchema"]:
                raise DshRuntimeError(
                    f"dsh-tool-schema-drift: {name}; restore the original MCP schema and retry role loading",
                    category="platform-contract",
                )
        allowed = set(PLUGINS) - {"@deepseek-ai/dsh-sdk-jsonrpc-server"}
        if set(inspection["plugins"]) != allowed:
            raise DshRuntimeError(
                "dsh-plugin-set-drift: restore the pinned composition and retry role loading",
                category="platform-contract",
            )

    def namespace_command(self, agent):
        command = namespace_base()
        command += ["--bind", str(agent.base / "home"), "/agent/home"]
        mode = agent.package.runtime["dsh"]["sandbox"]
        command += [
            "--bind" if mode == "workspace-write" else "--ro-bind",
            str(agent.base / "work"),
            "/agent/work",
            "--ro-bind",
            str(agent.base / "skills"),
            "/skills",
        ]
        for source in self._build["mounts"]:
            command += [
                "--ro-bind",
                source,
                "/dsh/" + str(Path(source).relative_to(self.harness_root)),
            ]
        for source, target in agent.mounts:
            command += ["--bind", str(source), target]
        node = shutil.which("node")
        if not node:
            raise DshRuntimeError("node is required for the pinned DSH build")
        command += [
            "--ro-bind",
            node,
            "/agent/node",
            "--chdir",
            "/agent/work",
            "--setenv",
            "DSH_PROXY_TOKEN",
            self._provider.proxy_token,
            "--",
            "/agent/node",
            "/agent/home/entry.mjs",
            "/agent/home/dsh.json",
        ]
        return command

    def _launch(self, agent):
        agent.stderr = (agent.base / "stderr.log").open("a", encoding="utf-8")
        agent.process = self.process_factory(
            self.namespace_command(agent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=agent.stderr,
            text=True,
            bufsize=1,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(agent.base / "home"), "LANG": "C.UTF-8"},
        )
        agent.pid_identity = self._process_info(agent.process.pid)[2]
        agent.pump = threading.Thread(target=self._pump, args=(agent,), daemon=True)
        agent.pump.start()

    def _rpc(self, agent, method, params, timeout=30):
        with agent.write_lock:
            agent.next_rpc += 1
            request_id = agent.next_rpc
            try:
                agent.process.stdin.write(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
                    )
                    + "\n"
                )
                agent.process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise DshRuntimeError("dsh-process-unavailable; inspect retained role log") from exc
        deadline = time.monotonic() + timeout
        with agent.response_condition:
            while request_id not in agent.responses:
                if agent.process.poll() is not None:
                    raise DshRuntimeError(
                        f"dsh-process-exited: role={agent.agent_id}; inspect retained role log"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    error = DshRuntimeError(
                        f"dsh-rpc-timeout: {method}; do not blindly replay unknown enqueue"
                    )
                    error.request_id = request_id
                    raise error
                agent.response_condition.wait(min(remaining, 0.2))
            response = agent.responses.pop(request_id)
        if "error" in response:
            error = DshRuntimeError(
                f"dsh-rpc-rejected: {method}: {response['error'].get('message', 'unknown')[:300]}"
            )
            error.rejected = True
            raise error
        return response["result"]

    def _pump(self, agent):
        try:
            for line in agent.process.stdout:
                value = json.loads(line)
                self._record(
                    "wire",
                    {
                        "agent_id": agent.agent_id,
                        "session_id": agent.session_id,
                        "process_instance": agent.instance,
                        "frame": value,
                    },
                )
                if "id" in value:
                    self._reconcile_enqueue(agent, value)
                    with agent.response_condition:
                        agent.responses[value["id"]] = value
                        agent.response_condition.notify_all()
                else:
                    self._notification(agent, value)
        except Exception as exc:
            self._failures.put(
                (
                    agent.agent_id,
                    {
                        "category": "runtime/infrastructure",
                        "reason_code": "dsh-event-pump-failed",
                        "detail": type(exc).__name__,
                    },
                )
            )
        finally:
            with agent.response_condition:
                agent.response_condition.notify_all()
            if not self._closed:
                self._enter_wait(agent, "process-exited")

    def _reconcile_enqueue(self, agent, response):
        with self._lock:
            for dispatch_id, record in list(agent.dispatches.items()):
                if (
                    not isinstance(record, dict)
                    or record.get("rpc_id") is None
                    or record.get("rpc_id") != response.get("id")
                    or record.get("process_instance") != agent.instance
                ):
                    continue
                message_id = response.get("result", {}).get("messageId")
                if message_id:
                    agent.dispatches[dispatch_id] = RuntimeDispatchReceipt(
                        "enqueue",
                        None,
                        "dsh",
                        dispatch_id,
                        agent.session_id,
                        message_id,
                        agent.instance,
                    )
                    self._record(
                        "dispatch",
                        {
                            "event": "enqueue-reconciled",
                            "agent_id": agent.agent_id,
                            "dispatch_id": dispatch_id,
                            "message_id": message_id,
                        },
                    )
                elif "error" in response:
                    record["state"] = "failed"

    def _notification(self, agent, value):
        params = value.get("params", {})
        if params.get("sessionId") != agent.session_id:
            self._record("unbound-event", {"agent_id": agent.agent_id, "frame": value})
            return
        with self._lock:
            if value["method"] == "session.event":
                event = params["event"]
                fresh = agent.projection.append(event)
                if agent.projection.gap:
                    self._recover_event_gap(agent)
                if not fresh:
                    return
                if event["type"] == "assistant/message":
                    content = event["data"]["message"].get("content", [])
                    text = "\n".join(
                        block.get("text", "") for block in content if block.get("type") == "text"
                    )
                    if text:
                        self._messages.put(RuntimeMessage(agent.agent_id, text))
                if agent.recovery and self._dispatch_record(agent, agent.recovery)["state"] in {
                    "claimed",
                    "settled",
                }:
                    if agent.provider_error_epoch != agent.recovery_error_epoch:
                        agent.recovery = None
                        return
                    self._record(
                        "provider-wait",
                        {
                            "event": "recovery-effective",
                            "agent_id": agent.agent_id,
                            "wait_id": agent.wait["wait_id"],
                            "dispatch_id": agent.recovery,
                            "session_id": agent.session_id,
                            "control_epoch": self._control_epoch,
                        },
                    )
                    agent.wait = None
                    agent.recovery = None
            elif value["method"] == "session.status":
                agent.state = params["status"]
            elif value["method"] == "host/provider-error":
                agent.provider_error_epoch += 1
                self._enter_wait(
                    agent, params.get("code", "provider-error"), params.get("http_status")
                )

    def _recover_event_gap(self, agent):
        # Read original persisted JSONL only; no guessed boundaries or synthetic claims.
        for path in (agent.base / "home/sessions").rglob("*.jsonl"):
            try:
                for line in path.read_text().splitlines():
                    event = json.loads(line)
                    if (
                        isinstance(event, dict)
                        and "seq" in event
                        and "type" in event
                        and "data" in event
                    ):
                        agent.projection.append(event)
            except (OSError, ValueError):
                continue

    def runtime_identity(self, agent_id):
        agent = self.agents.get(agent_id)
        if agent is None:
            return None
        return AgentRuntimeIdentity(
            agent_id,
            agent.session_id,
            "dsh",
            agent.instance,
            str(agent.projection.activity) if agent.projection.activity is not None else None,
        )

    def _dispatch_record(self, agent, dispatch_id):
        receipt = agent.dispatches[dispatch_id]
        if isinstance(receipt, dict):
            return dict(receipt)
        return {**dataclasses.asdict(receipt), **agent.projection.status(receipt.message_id)}

    def dispatch_status(self, agent_id):
        with self._lock:
            agent = self.agents[agent_id]
            return [self._dispatch_record(agent, identity) for identity in agent.dispatches]

    def start_task(self, agent_id, task_text, skill_paths, roster):
        self.send_message(agent_id, RuntimeDelivery("runner", agent_id, "task", task_text))

    def send_message(self, agent_id, delivery):
        agent = self.agents[agent_id]
        dispatch_id = "host-" + uuid.uuid4().hex
        with self._lock:
            if self._closed or self._paused or agent.terminal or not agent.ready:
                raise DshRuntimeError(
                    "dsh-dispatch-closed; retain input for authorized resume or terminal review"
                )
            if agent.wait is not None and delivery.kind != "provider-recovery":
                raise DshRuntimeError("provider wait pending; recover the original wait_id first")
            agent.dispatching += 1
        try:
            result = self._rpc(
                agent,
                "session/prompt",
                {
                    "sessionId": agent.session_id,
                    "contentBlocks": [
                        {
                            "type": "text",
                            "text": json.dumps(dataclasses.asdict(delivery), ensure_ascii=False),
                        }
                    ],
                },
            )
            receipt = RuntimeDispatchReceipt(
                "enqueue",
                None,
                "dsh",
                dispatch_id,
                agent.session_id,
                result["messageId"],
                agent.instance,
            )
            with self._lock:
                agent.dispatches[dispatch_id] = receipt
                self._record(
                    "dispatch",
                    {
                        "event": "queued",
                        **dataclasses.asdict(receipt),
                        "agent_id": agent_id,
                        "delivery_id": delivery.delivery_id,
                    },
                )
            return receipt
        except Exception as exc:
            # A lost response is not evidence that admission failed. Block terminal until reconciled.
            with self._lock:
                agent.dispatches[dispatch_id] = {
                    "runtime": "dsh",
                    "dispatch_id": dispatch_id,
                    "runtime_identity": agent.session_id,
                    "process_instance": agent.instance,
                    "message_id": None,
                    "turn_id": None,
                    "rpc_id": getattr(exc, "request_id", None),
                    "state": "failed" if getattr(exc, "rejected", False) else "unknown",
                }
                with agent.response_condition:
                    late = agent.responses.get(getattr(exc, "request_id", None))
                if late is not None:
                    self._reconcile_enqueue(agent, late)
            raise
        finally:
            with self._lock:
                agent.dispatching -= 1

    def terminal_report_blocked(self, agent_id, already_synchronized=False, status="completed"):
        with self._lock:
            agent = self.agents[agent_id]
            blocked = bool(
                status == "completed"
                and (
                    agent.dispatching
                    or any(
                        row["state"] in {"queued", "unknown"}
                        for row in self.dispatch_status(agent_id)
                    )
                )
            )
            if blocked:
                from ..transport_mcp import RoutingError

                raise RoutingError(
                    "unconsumed DSH input; end this activity to receive queued handoffs, "
                    "then retry report_task_result; unknown dispatches require Host reconciliation",
                    code="runtime_input_pending",
                )
            return False

    def commit_terminal(self, agent_id, status):
        with self._lock:
            if self.terminal_report_blocked(agent_id, status=status):
                from ..transport_mcp import RoutingError

                raise RoutingError(
                    "unconsumed runtime input; receive pending handoffs before reporting"
                )
            self.agents[agent_id].terminal = True

    def receive_messages(self):
        values = []
        while not self._messages.empty():
            values.append(self._messages.get())
        return values

    def get_agent_states(self):
        with self._lock:
            return [
                AgentState(
                    agent.agent_id,
                    "paused" if self._paused else agent.state,
                    runtime="dsh",
                    runtime_identity=agent.session_id,
                    activity_id=self.runtime_identity(agent.agent_id).activity_id,
                    pending_dispatches=tuple(self.dispatch_status(agent.agent_id)),
                )
                for agent in self.agents.values()
            ]

    def wait_settled(self, agent_ids, timeout):
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if all(
                    self.agents[key].projection.activity is None
                    and not any(
                        row["state"] in {"queued", "claimed", "unknown"}
                        for row in self.dispatch_status(key)
                    )
                    and self.agents[key].dispatching == 0
                    for key in agent_ids
                ):
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    def _enter_wait(self, agent, reason, status=None):
        with self._lock:
            if agent.wait is not None:
                agent.wait.update(
                    variant=reason, reason_code=reason, http_status=status, recovery_state="waiting"
                )
                agent.recovery = None
                return
            agent.wait = {
                "wait_id": "wait-" + uuid.uuid4().hex,
                "agent_id": agent.agent_id,
                "role": agent.package.role,
                "session_id": agent.session_id,
                "process_instance": agent.instance,
                "variant": reason,
                "http_status": status,
                "control_epoch": self._control_epoch,
                "state": "waiting",
                "reason_code": reason,
                "recovery_state": "waiting",
                "activity_id": self.runtime_identity(agent.agent_id).activity_id,
            }
            self._wait_events.put((agent.agent_id, dict(agent.wait)))
            self._record("provider-wait", agent.wait)

    def provider_wait_status(self, agent_id):
        with self._lock:
            agent = self.agents.get(agent_id)
            value = agent.wait if agent is not None else None
            return dict(value) if value else None

    def consume_provider_waits(self):
        values = []
        while not self._wait_events.empty():
            values.append(self._wait_events.get())
        return values

    def restore_session(self, agent_id, *, writes_reconciled=False):
        """Explicit recovery of original durable history; sends no new semantic input."""
        agent = self.agents[agent_id]
        with self._lock:
            if self._paused or self._closed or not writes_reconciled:
                raise DshRuntimeError(
                    "session restore requires open user control and reconciled writes"
                )
            if agent.process.poll() is None:
                raise DshRuntimeError(
                    "original role is still alive; resume it without a replacement process"
                )
            self._recover_event_gap(agent)
            if agent.projection.gap or agent.projection.conflict:
                raise DshRuntimeError(
                    "persisted session history has unresolved gaps; no replacement session created"
                )
            old_instance = agent.instance
            agent.ready = False
            agent.instance = uuid.uuid4().hex
            agent.responses.clear()
            agent.next_rpc = 0
            self._launch(agent)
        binding = self._run.team_model_profile.binding_for(
            agent.package.package_id, semantic_role=agent.package.role
        )
        self._register_usage(agent, binding, run_id=self._run.run_id, phase="production")
        try:
            self._rpc(
                agent,
                "initialize",
                {
                    "cwd": "/agent/work",
                    "provider": binding.provider_id,
                    "model": binding.model,
                    "reasoningEffort": binding.effective_effort,
                },
            )
            self._rpc(agent, "session/resume", {"sessionId": agent.session_id})
            self._check_tools(agent, self._rpc(agent, "host/inspect", {}))
        except Exception:
            self._record(
                "restore",
                {
                    "agent_id": agent_id,
                    "session_id": agent.session_id,
                    "process_instance": agent.instance,
                    "status": "failed",
                    "replacement_session_created": False,
                },
            )
            if agent.process.poll() is None:
                os.killpg(agent.process.pid, signal.SIGKILL)
                agent.process.wait(timeout=3)
            raise
        agent.ready = True
        self._record(
            "restore",
            {
                "agent_id": agent_id,
                "session_id": agent.session_id,
                "old_process_instance": old_instance,
                "process_instance": agent.instance,
                "semantic_input_sent": False,
            },
        )

    def recover_provider_wait(self, agent_id, text, *, wait_id=None, sender_id="user/outer"):
        agent = self.agents[agent_id]
        with self._lock:
            if self._paused or self._closed:
                raise DshRuntimeError("user pause/stop takes precedence over provider recovery")
            if not agent.wait or (wait_id is not None and agent.wait["wait_id"] != wait_id):
                raise DshRuntimeError(
                    "provider wait_id changed; refresh current provider wait status"
                )
            if agent.recovery:
                return agent.dispatches[agent.recovery]
            if agent.recovering or any(
                row["state"] == "unknown" for row in self.dispatch_status(agent_id)
            ):
                raise DshRuntimeError(
                    "recovery or unknown enqueue pending; reconcile the original dispatch before retry"
                )
            if agent.process.poll() is not None:
                raise DshRuntimeError(
                    "original process exited; reconcile writes then explicitly restore persisted session"
                )
            agent.recovery_error_epoch = agent.provider_error_epoch
            agent.recovering = True
        try:
            refresh = getattr(self._provider, "refresh_credential", None)
            if callable(refresh):
                original = self._run.provider_credential_bindings["deepseek-official"]
                repaired = preflight_deepseek_credential(original.path)
                credential = bytearray(read_deepseek_credential(repaired))
                try:
                    refresh(credential)
                finally:
                    credential[:] = b"\0" * len(credential)
                self._record(
                    "provider-wait",
                    {
                        "event": "host-credential-refreshed",
                        "agent_id": agent_id,
                        "wait_id": agent.wait["wait_id"],
                        "session_id": agent.session_id,
                        "control_epoch": self._control_epoch,
                    },
                )
            receipt = self.send_message(
                agent_id, RuntimeDelivery(sender_id, agent_id, "provider-recovery", text)
            )
        finally:
            with self._lock:
                agent.recovering = False
        with self._lock:
            agent.recovery = receipt.dispatch_id
            agent.wait["recovery_state"] = "submitted"
            if agent.provider_error_epoch != agent.recovery_error_epoch:
                agent.recovery = None
                agent.wait["recovery_state"] = "waiting"
                return receipt
            # Events may have arrived before the enqueue response.
            if self._dispatch_record(agent, receipt.dispatch_id)["state"] in {"claimed", "settled"}:
                self._record("provider-wait", {**agent.wait, "event": "recovery-effective"})
                agent.wait = None
                agent.recovery = None
        return receipt

    def consume_runtime_failures(self):
        values = []
        while not self._failures.empty():
            values.append(self._failures.get())
        return values

    @staticmethod
    def _process_info(pid):
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
            values = raw[raw.rfind(")") + 2 :].split()
            return values[0], int(values[2]), values[19], int(values[1])
        except (OSError, ValueError, IndexError):
            return None, None, None, None

    def _group(self, agent):
        pid = agent.process.pid
        state, pgid, identity, _ = self._process_info(pid)
        if identity != agent.pid_identity or pgid != pid:
            raise DshRuntimeError(
                f"role process identity changed: {agent.agent_id}; do not signal reused PID"
            )
        processes = {
            int(path.name): self._process_info(int(path.name))
            for path in Path("/proc").iterdir()
            if path.name.isdigit()
        }
        owned = {key for key, info in processes.items() if info[1] == pgid}
        while True:
            children = {key for key, info in processes.items() if info[3] in owned}
            if children <= owned:
                break
            owned.update(children)
        for key in owned:
            agent.owned_pids[key] = processes[key][2]
        return [
            {
                "pid": key,
                "pgid": processes[key][1],
                "state": processes[key][0],
                "start_identity": processes[key][2],
            }
            for key in sorted(owned)
            if processes[key][0] != "Z"
        ]

    def pause(self):
        with self._lock:
            self._paused = True
            self._control_epoch += 1
            for agent in self.agents.values():
                self._group(agent)
                os.killpg(agent.process.pid, signal.SIGSTOP)
        deadline = time.monotonic() + 3
        while True:
            groups = {key: self._group(agent) for key, agent in self.agents.items()}
            for members in groups.values():
                for item in members:
                    if item["state"] not in {"T", "t"}:
                        try:
                            os.kill(item["pid"], signal.SIGSTOP)
                        except ProcessLookupError:
                            pass
            if all(
                members and all(item["state"] in {"T", "t"} for item in members)
                for members in groups.values()
            ):
                self._record(
                    "control",
                    {
                        "action": "pause",
                        "status": "effective",
                        "control_epoch": self._control_epoch,
                        "groups": groups,
                    },
                )
                return groups
            if time.monotonic() >= deadline:
                self._record(
                    "control", {"action": "pause", "status": "pause-pending", "groups": groups}
                )
                raise DshRuntimeError(
                    "pause-pending: not all owned DSH/MCP processes are stopped; retry pause or stop"
                )
            time.sleep(0.02)

    def resume(self):
        with self._lock:
            if self._closed:
                raise DshRuntimeError("runtime is stopped; cannot resume")
            groups = {key: self._group(agent) for key, agent in self.agents.items()}
            for agent in self.agents.values():
                os.killpg(agent.process.pid, signal.SIGCONT)
                for item in groups[agent.agent_id]:
                    if item["pgid"] != agent.process.pid:
                        os.kill(item["pid"], signal.SIGCONT)
            self._paused = False
            self._control_epoch += 1
            self._record(
                "control",
                {
                    "action": "resume",
                    "status": "effective",
                    "control_epoch": self._control_epoch,
                    "groups": groups,
                },
            )
            return groups

    def probe_role_visibility(self, run):
        results = {}
        for key, agent in self.agents.items():
            # A new process inside the same mount tree; no SDK prompt or provider request.
            command = self.namespace_command(agent)
            marker = command.index("--")
            script = (
                "import fs from 'node:fs'; const paths=JSON.parse(process.argv[1]); "
                "const result=Object.fromEntries(paths.map(p=>[p,fs.existsSync(p)])); "
                "for(const name of ['DEEPSEEK_API_KEY','GLM_API_KEY','OPENAI_API_KEY',"
                "'ONTOLOGY_PLATFORM_ADMIN_API_KEY']) result['env:'+name]=Object.hasOwn(process.env,name); "
                "console.log(JSON.stringify(result));"
            )
            denied = [
                str(self.root),
                str(Path.home()),
                "/agent/home/../modeling",
                "/agent/home/../competency-question",
                "/proc/1/root" + str(Path.home()),
            ]
            denied += [
                f"/agent/home/sources/{source.relative_path}"
                for source in run.configuration.task.role_sources
                if agent.package.role not in source.roles
            ]
            allowed = ["/agent/home/role-materials.json", "/agent/home/sources"]
            allowed += [
                f"/agent/home/sources/{source.relative_path}"
                for source in run.configuration.task.role_sources
                if agent.package.role in source.roles
            ]
            paths = [*allowed, *denied]
            probe = subprocess.run(
                command[: marker + 1]
                + ["/agent/node", "--input-type=module", "-e", script, json.dumps(paths)],
                capture_output=True,
                text=True,
                timeout=30,
                env={"PATH": "/usr/bin:/bin"},
            )
            if probe.returncode:
                raise DshRuntimeError(f"visibility-probe-failed: role={key}")
            observed = json.loads(probe.stdout)
            if (
                not all(observed[p] for p in allowed)
                or any(observed[p] for p in denied)
                or any(value for name, value in observed.items() if name.startswith("env:"))
            ):
                raise DshRuntimeError(f"role-visibility-drift: role={key}")
            results[key] = {"paths": observed, "tools": self._rpc(agent, "host/inspect", {})}
        self._record("visibility", results)
        return results

    def stop(self):
        with self._lock:
            self._closed = True
        residuals = []
        roles = {}
        for key, agent in self.agents.items():
            process = agent.process
            if process is None:
                continue
            try:
                if process.poll() is None:
                    members = self._group(agent)
                    if self._paused:
                        # MCP's stdio transport can own detached child groups. Signal
                        # every observed descendant while business admission stays closed.
                        for item in reversed(members):
                            if item["pgid"] != process.pid:
                                try:
                                    os.kill(item["pid"], signal.SIGTERM)
                                    os.kill(item["pid"], signal.SIGCONT)
                                except ProcessLookupError:
                                    pass
                        os.killpg(process.pid, signal.SIGTERM)
                        os.killpg(process.pid, signal.SIGCONT)
                    else:
                        try:
                            self._rpc(agent, "shutdown", {}, timeout=2)
                        except DshRuntimeError:
                            os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                if agent.pump:
                    agent.pump.join(timeout=2)
                if agent.stderr:
                    agent.stderr.close()
                for name in ("capability.token", "read.token"):
                    (agent.base / "home" / name).unlink(missing_ok=True)
                roles[key] = {
                    "session_id": agent.session_id,
                    "process_instance": agent.instance,
                    "pid": process.pid,
                    "pgid": process.pid,
                    "returncode": process.poll(),
                }
                deadline = time.monotonic() + 2
                while (
                    any(
                        self._process_info(pid)[2] == identity
                        and self._process_info(pid)[0] not in {None, "Z"}
                        for pid, identity in agent.owned_pids.items()
                    )
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                for pid, identity in agent.owned_pids.items():
                    info = self._process_info(pid)
                    if info[2] == identity and info[0] not in {None, "Z"}:
                        residuals.append(
                            {"agent_id": key, "pid": pid, "reason": "owned-process-still-alive"}
                        )
            except Exception as exc:
                residuals.append({"agent_id": key, "reason": type(exc).__name__})
        provider_ok = self._provider.stop() if self._provider else True
        self._cleanup = {
            "runtime": "dsh",
            "roles": roles,
            "residuals": residuals,
            "provider_stopped": provider_ok,
            "complete": not residuals and provider_ok,
        }
        self._record("cleanup", self._cleanup)

    def cleanup_identifiers(self):
        return dict(self._cleanup)
