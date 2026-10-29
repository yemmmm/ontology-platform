"""One bounded Codex execution; scheduling, controls and accounting stay outside."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from openai_codex import CodexConfig
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import (
    ListMcpServerStatusResponse,
    SkillsConfigWriteResponse,
    SkillsListResponse,
)

from .contracts import outbound_tool_names  # noqa: F401 - public compatibility re-export
from .preflight import ModelBinding, candidate_config, namespace_command


class CodexAgent:
    def __init__(
        self,
        root: Path,
        binding: ModelBinding,
        *,
        provider_base_url: str,
        materials: Path,
        instructions: str,
        on_event: Callable[[str, dict], None],
        allowed_tools: tuple[str, ...] = ("read_material",),
        workspace_config: Path | None = None,
        platform_config: Path | None = None,
        team_config: Path | None = None,
        config_overrides: dict | None = None,
    ):
        self.root = root.resolve()
        self.binding = binding
        self.provider_base_url = provider_base_url
        self.materials = materials.resolve()
        self.instructions = instructions
        self.on_event = on_event
        self.allowed_tools = allowed_tools
        self.workspace_config = workspace_config
        self.platform_config = platform_config
        self.team_config = team_config
        self.config_overrides = config_overrides or {}
        self.thread_id: str | None = None
        self.active_turn: str | None = None
        self.client: CodexClient | None = None

    def record(self, method: str, payload: dict) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"method": method, "params": payload}, ensure_ascii=False) + "\n"
            )
        self.on_event(method, payload)

    def start(self, *, resume: bool = False) -> dict:
        self.root.mkdir(parents=True, exist_ok=resume, mode=0o700)
        home, work = self.root / "home", self.root / "work"
        home.mkdir(mode=0o700, exist_ok=resume)
        work.mkdir(mode=0o700, exist_ok=resume)
        config_text = candidate_config(self.binding, provider_base_url=self.provider_base_url)
        config_text = (
            "".join(
                f"{key} = {json.dumps(value)}\n" for key, value in self.config_overrides.items()
            )
            + config_text
        )
        # P0 failures return to the program for diagnosis. Do not stack proxy
        # retries and harness retries while establishing the wire contract.
        config_text += "request_max_retries = 0\nstream_max_retries = 0\n"
        args = ["-m", "ontoweave_modeling.material_tools", "--root", "/agent/materials"]
        mounts = [
            (Path(sys.prefix), "/agent/venv"),
            (Path(__file__).parent, "/agent/runtime/ontoweave_modeling"),
            (self.materials, "/agent/materials"),
        ]
        if self.workspace_config is not None:
            args.extend(("--workspace-config", "/agent/workspace.json"))
            mounts.append((self.workspace_config, "/agent/workspace.json"))
        if self.platform_config is not None:
            args.extend(("--platform-config", "/agent/platform.json"))
            mounts.append((self.platform_config, "/agent/platform.json"))
        if self.team_config is not None:
            args.extend(("--team-config", "/agent/team.json"))
            mounts.append((self.team_config, "/agent/team.json"))
        config_text += '\n[mcp_servers.workspace]\ncommand = "/agent/venv/bin/python"\n'
        config_text += f"args = {json.dumps(args)}\nenabled_tools = {json.dumps(self.allowed_tools)}\nrequired = true\n"
        for tool in self.allowed_tools:
            config_text += f'[mcp_servers.workspace.tools.{tool}]\napproval_mode = "approve"\n'
        config_text += '[mcp_servers.workspace.env]\nPYTHONPATH = "/agent/runtime"\n'
        (home / "config.toml").write_text(config_text, encoding="utf-8")
        command = namespace_command(
            home,
            work,
            network=True,
            read_only_mounts=tuple(mounts),
        )
        config = CodexConfig(
            launch_args_override=(
                *command,
                "/agent/bin/codex",
                "app-server",
                "--listen",
                "stdio://",
            ),
            cwd=str(work),
            client_name="ontoweave_v5_agent",
            experimental_api=False,
        )
        self.client = CodexClient(config, approval_handler=lambda *_: {"decision": "decline"})
        self.client.start()
        initialized = self.client.initialize()
        self.record("initialize", initialized.model_dump(mode="json", by_alias=True))
        skills = self.client.request(
            "skills/list",
            {"cwds": ["/agent/work"], "forceReload": True},
            response_model=SkillsListResponse,
        )
        for entry in skills.data:
            for skill in entry.skills:
                if skill.enabled:
                    self.client.request(
                        "skills/config/write",
                        {"path": skill.model_dump(mode="json")["path"], "enabled": False},
                        response_model=SkillsConfigWriteResponse,
                    )
        skills = self.client.request(
            "skills/list",
            {"cwds": ["/agent/work"], "forceReload": True},
            response_model=SkillsListResponse,
        )
        self.record("skills/list", skills.model_dump(mode="json", by_alias=True))
        if any(skill.enabled for entry in skills.data for skill in entry.skills):
            raise RuntimeError("unapproved Skills remain enabled; inspect skills/list evidence")
        params = {
            "cwd": "/agent/work",
            "model": self.binding.model,
            "modelProvider": self.binding.provider,
            "baseInstructions": "",
            "developerInstructions": self.instructions,
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }
        if resume:
            prior = json.loads((self.root / "thread-binding.json").read_text())
            thread = self.client.thread_resume(prior["thread_id"], params)
        else:
            thread = self.client.thread_start(params)
        self.thread_id = thread.thread.id
        result = thread.model_dump(mode="json", by_alias=True)
        self.record("thread/resume" if resume else "thread/start", result)
        (self.root / "thread-binding.json").write_text(
            json.dumps(
                {
                    "thread_id": self.thread_id,
                    "provider": self.binding.provider,
                    "model": self.binding.model,
                    "effort": self.binding.effort,
                }
            )
            + "\n"
        )
        if (thread.model_provider, thread.model, thread.reasoning_effort.value) != (
            self.binding.provider,
            self.binding.model,
            self.binding.effort,
        ):
            raise RuntimeError("effective model binding differs from authorization")
        mcp = self.client.request(
            "mcpServerStatus/list",
            {"limit": 100},
            response_model=ListMcpServerStatusResponse,
        )
        self.record("mcpServerStatus/list", mcp.model_dump(mode="json", by_alias=True))
        return result

    def run_turn(self, prompt: str, *, output_schema: dict | None = None) -> dict:
        if self.client is None or self.thread_id is None:
            raise RuntimeError("start or reconcile the Agent before starting a turn")
        if self.active_turn is not None:
            raise RuntimeError("Agent is busy; queue input until the native turn ends")
        started = self.client.turn_start(
            self.thread_id,
            prompt,
            {"effort": self.binding.effort, "outputSchema": output_schema},
        )
        self.active_turn = started.turn.id
        self.record(
            "turn/started",
            {
                "threadId": self.thread_id,
                "turn": {"id": self.active_turn},
            },
        )
        messages = []
        while True:
            event = self.client.next_turn_notification(self.active_turn)
            payload = event.payload.model_dump(mode="json", by_alias=True)
            self.record(event.method, payload)
            if event.method == "item/completed":
                item = payload.get("item", {})
                if item.get("type") == "agentMessage":
                    messages.append(item["text"])
            elif event.method == "turn/completed":
                turn_id = self.active_turn
                self.active_turn = None
                return {
                    "thread_id": self.thread_id,
                    "turn_id": turn_id,
                    "status": payload["turn"]["status"],
                    "error": payload["turn"].get("error"),
                    "final_response": "\n".join(messages),
                }

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
