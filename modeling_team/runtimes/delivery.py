"""Standalone Host-private Codex thread for the Delivery supervisor."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from modeling_team.model_routing import (
    RoleModelBinding, codex_auth_cache_path, preflight_codex_subscription_auth,
)
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter, _formal_codex_builtin_config_lines,
    _formal_provider_config_lines, _minimal_codex_process_env,
)


class DeliveryRuntimeError(RuntimeError):
    """Native transport failure, without provider-controlled diagnostic text."""


class DeliveryRuntime:
    def __init__(
        self, *, binding: RoleModelBinding, home: Path, instructions: str,
        tools: list[dict[str, Any]], tool_handler: Callable[[str, dict], Any],
        codex_binary: str = "codex", authenticate: bool = True,
        service_tier: str = "unset", provider_base_url: str | None = None,
    ) -> None:
        self.binding = binding
        self.home = Path(home).resolve()
        self.instructions = instructions
        self.tools = tools
        self.tool_handler = tool_handler
        self.codex_binary = codex_binary
        self.authenticate = authenticate
        self.service_tier = service_tier
        self.provider_base_url = provider_base_url
        self.process: subprocess.Popen | None = None
        self.thread_id: str | None = None
        self.busy = False
        self.stdout_buffer = b""
        self._request_id = 0
        self._stderr = None
        self._observations: list[dict] = []
        self._turn_id: str | None = None

    def start(self) -> None:
        if self.process is not None:
            raise DeliveryRuntimeError("Delivery runtime already started")
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)
        work = self.home / "work"
        work.mkdir(exist_ok=True)
        if self.provider_base_url:
            lines = _formal_provider_config_lines(self.binding, self.provider_base_url)
        else:
            if self.binding.provider_id != "openai-codex":
                raise DeliveryRuntimeError("external provider requires its Host-owned route")
            lines = _formal_codex_builtin_config_lines(self.binding)
        tier = self.service_tier
        if tier == "unset":
            tier = os.environ.get("MODELING_TEAM_CODEX_SERVICE_TIER", "default")
        if tier not in {"default", "fast"}:
            raise DeliveryRuntimeError("unsupported Delivery service tier")
        if tier == "fast" and not self.provider_base_url:
            lines = ['service_tier = "fast"', *lines, "[features]", "fast_mode = true"]
        (self.home / "config.toml").write_text("\n".join(lines) + "\n")
        try:
            if self.authenticate and not self.provider_base_url:
                preflight_codex_subscription_auth()
                shutil.copyfile(codex_auth_cache_path(), self.home / "auth.json")
                os.chmod(self.home / "auth.json", 0o600)
            self._stderr = (self.home / "native.stderr.log").open("a")
            executable = shutil.which(self.codex_binary)
            if executable is None:
                raise DeliveryRuntimeError("Codex executable unavailable")
            self.process = subprocess.Popen(
                [executable, "app-server"], cwd=work,
                env=_minimal_codex_process_env(self.home), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self._stderr, text=True,
            )
            self._rpc("initialize", {
                "clientInfo": {"name": "modeling-team-delivery", "version": "1"},
                "capabilities": {"experimentalApi": True},
            })
            self._write({"method": "initialized"})
            result = self._rpc("thread/start", {
                "cwd": str(work), "model": self.binding.model,
                "baseInstructions": "", "developerInstructions": self.instructions,
                "approvalPolicy": "never", "sandbox": "read-only",
                "config": {"default_tools_enabled": False, "web_search": "disabled"},
                "dynamicTools": [{"type": "function", **tool} for tool in self.tools],
            })
            self.thread_id = result["thread"]["id"]
        except Exception:
            self.close()
            raise

    def _write(self, value: dict) -> None:
        if self.process is None or self.process.stdin is None:
            raise DeliveryRuntimeError("Delivery native process unavailable")
        try:
            self.process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise DeliveryRuntimeError("Delivery native input closed") from exc

    def _read(self, timeout: float) -> dict | None:
        try:
            line = CodexRuntimeAdapter._read_output_line(self, timeout)
            return json.loads(line) if line is not None else None
        except Exception as exc:
            raise DeliveryRuntimeError("Delivery native output unavailable or invalid") from exc

    def _rpc(self, method: str, params: dict) -> dict:
        self._request_id += 1
        request_id = self._request_id
        self._write({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = self._read(min(0.25, deadline - time.monotonic()))
            if value is None:
                continue
            if value.get("id") == request_id and "method" not in value:
                if "error" in value:
                    raise DeliveryRuntimeError(f"Delivery native RPC failed: {method}")
                return value.get("result", {})
            self._handle(value)
        raise DeliveryRuntimeError(f"Delivery native RPC timed out: {method}")

    def _remove_auth(self) -> None:
        (self.home / "auth.json").unlink(missing_ok=True)

    def _handle(self, value: dict) -> None:
        method = value.get("method")
        if method == "item/tool/call" and "id" in value:
            # Authentication must disappear before any model-directed Host call.
            self._remove_auth()
            params = value.get("params", {})
            try:
                name = params["tool"]
                if name not in {tool["name"] for tool in self.tools}:
                    raise ValueError("unknown tool")
                if params.get("threadId") != self.thread_id:
                    raise ValueError("incorrect thread")
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise ValueError("invalid arguments")
                result = self.tool_handler(name, arguments)
                response = {"success": True, "contentItems": [
                    {"type": "inputText", "text": json.dumps(result, ensure_ascii=False)}
                ]}
            except Exception:
                response = {"success": False, "contentItems": [
                    {"type": "inputText", "text": '{"error":"delivery_tool_failed"}'}
                ]}
            self._write({"id": value["id"], "result": response})
        elif "id" in value and method:
            self._write({"id": value["id"], "error": {
                "code": -32601, "message": "Delivery permits only declared Host tools",
            }})
        elif method == "turn/completed":
            self.busy = False
            self._remove_auth()
            status = value.get("params", {}).get("turn", {}).get("status")
            self._observations.append({"event": "turn_completed", "status": status})
        # Agent messages, reasoning, provider errors and tool logs remain private.

    def send(self, text: str) -> None:
        if self.busy or not self.thread_id:
            raise DeliveryRuntimeError("Delivery thread is unavailable or busy")
        self.busy = True
        try:
            result = self._rpc("turn/start", {"threadId": self.thread_id, "input": [
                {"type": "text", "text": text, "text_elements": []},
            ]})
            self._turn_id = result["turn"]["id"]
        except Exception:
            self.busy = False
            raise
        finally:
            self._remove_auth()

    def poll(self, timeout: float = 0) -> list[dict]:
        value = self._read(timeout)
        if value is not None:
            self._handle(value)
        observations, self._observations = self._observations, []
        return observations

    def interrupt(self) -> None:
        if self.busy and self._turn_id:
            self._rpc("turn/interrupt", {"threadId": self.thread_id, "turnId": self._turn_id})

    def close(self) -> None:
        self._remove_auth()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self._stderr is not None:
            self._stderr.close()
        self.busy = False
