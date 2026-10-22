"""Standalone Host-private Codex thread for the Delivery supervisor."""
from __future__ import annotations

import json
import inspect
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.close_statistics import ActivityRecorder
from .budget import (
    binding_with_key_ref,
    normalize_control_epoch,
    runtime_budget,
    valid_key_ref,
)
from modeling_team.task_budget import BudgetError

from modeling_team.model_routing import (
    RoleModelBinding, codex_auth_cache_path, preflight_codex_subscription_auth,
)
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter, _formal_codex_builtin_config_lines,
    _formal_provider_config_lines, _minimal_codex_process_env,
)


class DeliveryRuntimeError(RuntimeError):
    """Native transport failure, without provider-controlled diagnostic text."""
    def __init__(self, message: str, *, category: str = "unknown"):
        super().__init__(message)
        self.category = category


class DeliveryRuntimeProtocol(Protocol):
    """The existing Host loop's narrow runtime contract."""
    process: subprocess.Popen | None
    thread_id: str | None
    @property
    def busy(self) -> bool: ...
    @property
    def turn_id(self) -> str | None: ...
    @property
    def identity(self) -> dict: ...
    def start(self) -> None: ...
    def new_thread(self) -> dict: ...
    def send(self, text: str) -> dict | None: ...
    def steer(self, text: str) -> dict | None: ...
    def poll(self, timeout: float = 0) -> list[dict]: ...
    def interrupt(self) -> dict | None: ...
    def close(self) -> None: ...


# The installed Codex app-server (verified against /agent/bin/real-codex
# 0.161.0 and the mounted --experimental protocol schemas) has no single
# "disable default tools" switch: ``default_tools_enabled`` is not a ``Config``
# key, so a thread/start request carrying it is accepted and silently ignored
# while the model still receives the native builtins (captured outbound
# ``exec_command``/``write_stdin`` calls in the R4.0-023 Delivery incident).
# The supported mechanism is the per-capability projection below.  Every entry
# is a real schema key whose effect was confirmed on the installed server by
# capturing its outbound model request, which then contained only the dynamic
# Host tools:
#   features.shell_tool=False        removes exec_command/write_stdin
#   features.sleep_tool=False        removes the native sleep tool
#   features.view_image=False        removes view_image
#   features.goals=False             removes get/create/update_goal
#   features.multi_agent(_v2)=False  removes the multi_agent_v1 namespace
#   tools.experimental_request_user_input.enabled=False removes
#                                   request_user_input
#   tools.update_plan.enabled=False  removes update_plan
#   web_search="disabled"            removes the web_search tool
_NATIVE_TOOL_BOUNDARY_CONFIG: dict[str, Any] = {
    "web_search": "disabled",
    "features": {
        "shell_tool": False,
        "sleep_tool": False,
        "view_image": False,
        "goals": False,
        "multi_agent": False,
        "multi_agent_v2": False,
    },
    "tools": {
        "experimental_request_user_input": {"enabled": False},
        "update_plan": {"enabled": False},
    },
}
# Feature-gated builtins the running app-server must report as off for this
# exact thread before any turn is allowed.  ``tools.*`` and ``web_search`` have
# no feature-list surface, so their effective state rests on the captured
# outbound-tool evidence above plus the offline wire tests, not this check.
_REQUIRED_DISABLED_FEATURES = (
    "shell_tool",
    "sleep_tool",
    "view_image",
    "goals",
    "multi_agent",
    "multi_agent_v2",
)


def _native_tool_boundary_config() -> dict[str, Any]:
    """Return the per-thread config overlay that removes native builtins."""

    return json.loads(json.dumps(_NATIVE_TOOL_BOUNDARY_CONFIG))


class DeliveryRuntime:
    def __init__(
        self, *, binding: RoleModelBinding, home: Path, instructions: str,
        tools: list[dict[str, Any]], tool_handler: Callable[[str, dict], Any],
        codex_binary: str = "codex", authenticate: bool = True,
        service_tier: str = "unset", provider_base_url: str | None = None,
        model_context_window: int | None = None,
        model_auto_compact_token_limit: int | None = None,
        usage_context: dict | None = None,
        budget: object | None = None,
        budget_owner_id: str | None = None,
        before_budget_control: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.binding = binding
        self._usage_context = dict(usage_context or {})
        self._budget_binding = binding_with_key_ref(
            binding, valid_key_ref(self._usage_context.get("key_ref"))
        )
        self._usage_writer = NumericReceiptWriter(Path(home) / "usage-events.jsonl", {
            **self._usage_context, "provider": binding.provider_id,
            "requested_model": binding.model, "requested_effort": binding.requested_effort,
            "effective_effort": binding.effective_effort,
        })
        self.home = Path(home).resolve()
        self.instructions = instructions
        self.tools = tools
        self.tool_handler = tool_handler
        self.codex_binary = codex_binary
        self.authenticate = authenticate
        self.service_tier = service_tier
        self.provider_base_url = provider_base_url
        self.model_context_window = model_context_window
        self.model_auto_compact_token_limit = model_auto_compact_token_limit
        self.process: subprocess.Popen | None = None
        self.thread_id: str | None = None
        self.busy = False
        self.stdout_buffer = b""
        self._request_id = 0
        self._stderr = None
        self._observations: list[dict] = []
        self._turn_id: str | None = None
        self._activity_turn_id: str | None = None
        self.process_instance = uuid.uuid4().hex
        self.activity = None
        self._budget_source = budget
        self._budget_owner_id = budget_owner_id or (
            f"delivery:{(usage_context or {}).get('session_id', 'runtime')}:{self.process_instance}"
        )
        self._before_budget_control = before_budget_control
        self._budget = None
        self._budget_control_epochs: set[str] = set()
        self._budget_control_receipts: dict[str, dict] = {}
        self._queued_inputs: list[tuple[str, Any]] = []

    @property
    def identity(self) -> dict:
        return {"runtime": "codex", "process_instance": self.process_instance,
                "runtime_session_id": self.thread_id, "activity_id": self.turn_id}

    def start(self) -> None:
        if self.process is not None:
            raise DeliveryRuntimeError("Delivery runtime already started")
        self._budget = runtime_budget(
            self.home.parent,
            self._budget_owner_id,
            binding=self._budget_binding,
            runtime="codex",
            explicit=self._budget_source,
            session_id=(self._usage_writer.context.get("session_id")),
            process_instance=self.process_instance,
            role="delivery",
        )
        self._budget.register_source(self.home / "usage-events.jsonl", "capture")
        if self.provider_base_url:
            self._budget.register_source(
                self.home / "provider-attempts.jsonl", "capture", shared=True,
                capture_session_id=self._usage_writer.context.get("session_id"),
            )
        self.activity = ActivityRecorder(self.home.parent, {
            **self._usage_writer.context, "runtime": "codex", "agent_id": "delivery",
            "role": "delivery", "process_instance": self.process_instance,
        }, usage_sources=[{"path": str(self.home / "usage-events.jsonl"), "kind": "capture"},
                          *([{"path": str(self.home / "provider-attempts.jsonl"), "kind": "capture",
                              "shared": True,
                              "capture_session_id": self._usage_writer.context.get("session_id")}] if self.provider_base_url else [])],
            fresh_session=True,
            budget=self._budget.budget,
            budget_owner_id=self._budget_owner_id,
            budget_binding=self._budget.binding,
            budget_runtime="codex")
        self._usage_writer.context.update(self.activity.context)
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
        # These are root TOML keys, before the provider and environment tables.
        # Optional settings belong to the selected Delivery session, not the
        # shared role provider helper or isolated test business answerers.
        context_lines = []
        for name in ("model_context_window", "model_auto_compact_token_limit"):
            value = getattr(self, name)
            if value is not None:
                if type(value) is not int or value <= 0:
                    raise DeliveryRuntimeError(f"{name} must be a positive integer")
                context_lines.append(f"{name} = {value}")
        if self.provider_base_url and self.model_context_window is not None:
            # Codex 0.162.1 clamps unknown models to its 272000-token fallback
            # maximum even with model_context_window configured.  Supply the
            # exact external model's session budget in a startup-only catalog.
            # Other fields retain the native unknown-model defaults; built-in
            # models continue using their own metadata and capacity limits.
            catalog_path = self.home / "delivery-model-catalog.json"
            catalog_path.write_text(json.dumps({"models": [{
                "slug": self.binding.model,
                "display_name": self.binding.model,
                "base_instructions": "",
                "supported_reasoning_levels": [],
                "shell_type": "unified_exec",
                "visibility": "none",
                "supported_in_api": True,
                "priority": 99,
                "include_apps_usage_instructions": False,
                "default_reasoning_summary": "auto",
                "support_verbosity": False,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "context_window": self.model_context_window,
                "max_context_window": self.model_context_window,
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
            }]}))
            context_lines.append(f"model_catalog_json = {json.dumps(str(catalog_path))}")
        lines = [*context_lines, *lines]
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
            self.new_thread()
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
                    detail = value["error"].get("message", "")
                    category, _ = CodexRuntimeAdapter._classify_steer_message(detail)
                    raise DeliveryRuntimeError(f"Delivery native RPC failed: {method}",
                        category="rejected" if method == "turn/steer" and category in {
                            "no_active_turn_to_steer", "active_turn_mismatch"} else "unknown")
                return value.get("result", {})
            self._handle(value)
        raise DeliveryRuntimeError(f"Delivery native RPC timed out: {method}")

    def _verify_native_tool_boundary(self, thread_id=None) -> None:
        """Fail closed unless the live app-server reports the builtins off.

        An accepted ``thread/start`` cannot prove the effective boundary on its
        own: unsupported config keys are silently ignored, which is exactly how
        the previous ``default_tools_enabled`` flag failed.  The
        ``experimentalFeature/list`` answer is computed from this thread's
        refreshed config, so a renamed or re-forced builtin feature is caught
        here, before any turn can drive native tool traffic.
        """
        result = self._rpc("experimentalFeature/list", {"threadId": thread_id or self.thread_id})
        reported: dict[str, Any] = {}
        for entry in result.get("data") or []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                reported[entry["name"]] = entry.get("enabled")
        still_enabled = sorted(
            name for name in _REQUIRED_DISABLED_FEATURES
            if reported.get(name) is not False
        )
        if still_enabled:
            raise DeliveryRuntimeError(
                "Delivery native tool boundary not effective for thread"
                f" (not reported off: {', '.join(still_enabled)})"
            )

    def _activity_turn_start(self, turn_id: str | None) -> None:
        """Record one native Delivery turn start for budget inflight state."""

        if not isinstance(turn_id, str) or not turn_id:
            return
        if self.activity is None or self._activity_turn_id == turn_id:
            return
        self.activity.emit(
            "llm_start",
            call_id=f"{self.thread_id}:{turn_id}",
            turn_id=turn_id,
        )
        self._activity_turn_id = turn_id

    def _activity_turn_end(self, turn_id: str | None, status: str | None) -> None:
        """Close only the native Delivery turn that was actually started."""

        if not isinstance(turn_id, str) or turn_id != self._activity_turn_id:
            return
        if self.activity is not None:
            self.activity.emit(
                "llm_end",
                call_id=f"{self.thread_id}:{turn_id}",
                turn_id=turn_id,
                status=status or "completed",
            )
        self._activity_turn_id = None

    def new_thread(self) -> dict:
        if self.busy or self.process is None or self.process.poll() is not None:
            raise DeliveryRuntimeError("Delivery runtime unavailable or busy")
        result = self._rpc("thread/start", {
            "cwd": str(self.home / "work"), "model": self.binding.model,
            "baseInstructions": "", "developerInstructions": self.instructions,
            "approvalPolicy": "never", "sandbox": "read-only",
            "config": _native_tool_boundary_config(),
            "dynamicTools": [{"type": "function", **tool} for tool in self.tools],
        })
        thread_id = result["thread"]["id"]
        self._verify_native_tool_boundary(thread_id)
        self.thread_id, self._turn_id = thread_id, None
        self.activity.bind(thread_id)
        self._usage_writer.context.update(self.activity.context)
        return self.identity

    def _remove_auth(self) -> None:
        (self.home / "auth.json").unlink(missing_ok=True)

    def _handle(self, value: dict) -> None:
        method = value.get("method")
        if method == "thread/tokenUsage/updated":
            params = value.get("params") or {}
            try:
                self._usage_writer({"event": "thread_usage",
                    "thread_id": params.get("threadId"), "turn_id": params.get("turnId"),
                    "runtime_session_id": params.get("threadId"),
                    "total": (params.get("tokenUsage") or {}).get("total") or {}})
            except Exception:
                from modeling_team.usage_capture import LOG
                LOG.warning("usage_capture_incomplete")
        elif method == "turn/started":
            params = value.get("params") or {}
            turn = params.get("turn") if isinstance(params, dict) else None
            turn_id = turn.get("id") if isinstance(turn, dict) else params.get("turnId")
            if isinstance(turn_id, str):
                self._turn_id = turn_id
                self._activity_turn_start(turn_id)
        elif method == "item/tool/call" and "id" in value:
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
                from contextlib import nullcontext
                with self.activity.tool(params.get('callId', value['id']), name) if self.activity else nullcontext():
                    if "call_identity" in inspect.signature(self.tool_handler).parameters:
                        result = self.tool_handler(name, arguments,
                            call_identity=f"{self.thread_id}:{params.get('callId', value['id'])}")
                    else:
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
            params = value.get("params", {})
            if (params.get("threadId", self.thread_id) != self.thread_id
                    or (self._turn_id is not None
                        and params.get("turn", {}).get("id") != self._turn_id)):
                return
            turn = params.get("turn", {})
            completed_turn_id = (
                turn.get("id") if isinstance(turn, dict) else None
            ) or params.get("turnId") or self._turn_id
            status = turn.get("status") if isinstance(turn, dict) else None
            self._activity_turn_end(completed_turn_id, status)
            self.busy = False
            self._remove_auth()
            self._observations.append({"event": "turn_completed", "status": status})
        # Agent messages, reasoning, provider errors and tool logs remain private.

    def send(self, text: str) -> None:
        if self.busy or not self.thread_id:
            raise DeliveryRuntimeError("Delivery thread is unavailable or busy")
        if self._budget is not None:
            self._budget.require("start")
        self.busy = True
        try:
            result = self._rpc("turn/start", {"threadId": self.thread_id, "input": [
                {"type": "text", "text": text, "text_elements": []},
            ]})
            self._turn_id = result["turn"]["id"]
            self._activity_turn_start(self._turn_id)
        except Exception:
            self.busy = False
            raise
        finally:
            self._remove_auth()

    @property
    def turn_id(self) -> str | None:
        """Id of the most recently started turn, as reported by the server."""
        return self._turn_id

    def steer(self, text: str) -> None:
        """Compatibility entry point: enqueue without interrupting generation."""
        self._queued_inputs.append(("message", text))

    def control_budget(self, message: dict) -> dict:
        """Apply one bounded task-budget control to the native Codex turn.

        The Host process and its monitor remain alive. A busy native turn queues
        the control; after natural completion it starts one control turn.
        Repeated requests for the same epoch are acknowledged without another
        model call.
        """

        if not isinstance(message, dict):
            raise DeliveryRuntimeError("task-budget control message is invalid", category="rejected")
        action = message.get("action")
        epoch = message.get("epoch")
        if action not in {"pause", "resume"} or epoch is None:
            raise DeliveryRuntimeError("task-budget control binding is invalid", category="rejected")
        try:
            epoch = normalize_control_epoch(epoch)
        except ValueError as exc:
            raise DeliveryRuntimeError("task-budget control epoch is invalid", category="rejected") from exc
        key = f"{action}:{epoch}"
        if self.busy:
            if not any(kind == "control" and value.get("action") == action
                       and value.get("epoch") == epoch for kind, value in self._queued_inputs):
                self._queued_inputs.append(("control", message))
            return {"status": "pending", "action": action, "epoch": epoch,
                    "basis": "queued_until_turn_end", **self.identity}
        if key in self._budget_control_epochs:
            return {
                **self._budget_control_receipts.get(key, {
                    "status": "already_recorded", "action": action, "epoch": epoch, **self.identity
                }),
                "deduplicated": True,
            }
        if self._budget is not None:
            try:
                self._budget.require(
                    "control", control_id=str(message.get("control_id") or key)
                )
            except BudgetError as exc:
                if exc.code != "control_turn_already_consumed":
                    raise
                # A durable grant is consumed even when the prior native RPC
                # receipt was lost.  Keep this retry from issuing a second
                # control turn and expose the persisted member outcome.
                receipt = self._budget.control_receipt(epoch)
                result = {
                    "status": (receipt or {}).get("status", "pending"),
                    "action": action,
                    "epoch": epoch,
                    "deduplicated": True,
                    **self.identity,
                    **({"receipt": receipt} if receipt else {}),
                }
                self._budget_control_epochs.add(key)
                self._budget_control_receipts[key] = result
                return result
        if self.process is None or self.process.poll() is not None or not self.thread_id:
            if self._budget is not None:
                self._budget.record_control(epoch, "not_running", action=action)
            result = {"status": "not_running", "action": action, "epoch": epoch, **self.identity}
            self._budget_control_epochs.add(key)
            self._budget_control_receipts[key] = result
            return result
        text = message.get("text")
        if not isinstance(text, str) or not text:
            text = (
                "Task budget pause: stop starting new work and wait for the Host control path."
                if action == "pause"
                else "Task budget resumed: continue the authorized work on this thread."
            )
        control_id = str(message.get("control_id") or key)
        try:
            if self._before_budget_control is not None:
                # The callback reserves the one provider-side control request
                # only after the durable TaskBudget grant above and immediately
                # before the native RPC.  A rejected callback therefore leaves
                # no model request in flight and is reported as pending below.
                self._before_budget_control(text, control_id)
            self.busy = True
            result = self._rpc("turn/start", {
                "threadId": self.thread_id,
                "input": [{"type": "text", "text": text}],
            })
            self._turn_id = result["turn"]["id"]
            self._budget_control_epochs.add(key)
            result = {"status": "instruction_delivered", "action": action, "epoch": epoch, **self.identity}
            self._budget_control_receipts[key] = result
            if self._budget is not None:
                self._budget.record_control(epoch, "instruction_delivered", action=action)
            return result
        except Exception:
            if self._budget is not None:
                self._budget.record_control(epoch, "pending", action=action)
            self._budget_control_epochs.add(key)
            self._budget_control_receipts[key] = {
                "status": "pending", "action": action, "epoch": epoch, **self.identity
            }
            raise

    def poll(self, timeout: float = 0) -> list[dict]:
        # Drain a bounded burst before the owner does synchronous observation.
        # Text deltas must not make a tool/completion wait one observer cycle each.
        for index in range(256):
            value = self._read(timeout if index == 0 else 0)
            if value is None:
                break
            self._handle(value)
        if not self.busy and self._queued_inputs:
            kind, value = self._queued_inputs[0]
            try:
                if kind == "control":
                    self.control_budget(value)
                else:
                    self.send(value)
            except BudgetError:
                pass
            else:
                self._queued_inputs.pop(0)
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
        if self.process is not None:
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                try:
                    value = self._read(0)
                except DeliveryRuntimeError:
                    # EOF is normal after wait(); statistics never replace the
                    # original process/cleanup outcome with a reader failure.
                    break
                if value is None:
                    break
                if value.get("method") == "thread/tokenUsage/updated":
                    self._handle(value)
        if self.activity:
            self.activity.exit(self.process.poll() if self.process else None,
                               startup_failed=self.process is None)
        self.busy = False
