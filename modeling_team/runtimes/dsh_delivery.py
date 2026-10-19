"""Private Delivery DSH session; the Host owns tools, credentials and effects."""
from __future__ import annotations

import json
import hashlib
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .delivery import DeliveryRuntimeError
from .dsh_build import composition_plugins, digest, freeze_build
from .dsh_events import DispatchProjection
from .role_isolation import namespace_base
from ..deepseek_provider_proxy import read_deepseek_credential, read_glm_credential
from ..messages_provider_proxy import MessagesProviderSession
from ..usage_capture import NumericReceiptWriter
from ..model_routing import preflight_profile_credentials, PROVIDER_CATALOG


def validate_delivery_runtime(config, binding):
    runtime = config.get("runtime", "codex")
    if runtime not in {"codex", "dsh"}:
        raise ValueError("runtime must be codex or dsh")
    if (PROVIDER_CATALOG[binding.provider_id].wire_api == "messages") != (runtime == "dsh"):
        raise ValueError(f"unsupported-runtime-provider: runtime={runtime} provider={binding.provider_id}")
    if runtime == "dsh":
        for field in ("service_tier", "model_context_window", "model_auto_compact_token_limit"):
            if field in config:
                raise ValueError(f"unsupported-runtime-setting: runtime=dsh field={field}")
    return runtime


class DSHDeliveryRuntime:
    runtime = "dsh"
    thread_id = None  # Never place a DSH message/session in a Codex identity field.

    def __init__(self, *, binding, home, instructions, tools, tool_handler,
                 session_id, profile=None, resume=False, repository_root=None,
                 harness_root=None, provider_factory=MessagesProviderSession):
        self.binding, self.home = binding, Path(home)
        self.instructions, self.tools, self.tool_handler = instructions, tools, tool_handler
        self.session_id, self.profile, self.resume = session_id, profile, resume
        self.root = Path(repository_root or Path(__file__).resolve().parents[2])
        self.harness_root = Path(harness_root or "/home/yangxiang/deepseek-harness")
        self.provider_factory = provider_factory
        self.process_instance = uuid.uuid4().hex
        self.runtime_session_id = None
        self.process = self.provider = self._stderr = None
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._write_lock = threading.Lock()
        self._responses, self.dispatches = {}, {}
        self._rpc_id = 0
        self._events = queue.SimpleQueue()
        self._tools = ThreadPoolExecutor(max_workers=1, thread_name_prefix="delivery-host-tools")
        self._inflight = 0
        self._closed = False
        self._pump_failed = False
        self.projection = None

    def _record(self, kind, **value):
        with self._lock:
            with (self.home / f"dsh-{kind}.jsonl").open("a") as stream:
                stream.write(json.dumps({"runtime": "dsh", "process_instance": self.process_instance,
                    "runtime_session_id": self.runtime_session_id, **value}, ensure_ascii=False) + "\n")

    @property
    def identity(self):
        return {"runtime": "dsh", "process_instance": self.process_instance,
                "runtime_session_id": self.runtime_session_id, "activity_id": self.turn_id}

    @property
    def turn_id(self):
        # Local activity token for the supervision loop, never persisted as a Codex turn.
        return str(self.projection.activity) if self.projection and self.projection.activity is not None else None

    @property
    def busy(self):
        with self._lock:
            if self._pump_failed or (self.process and self.process.poll() is not None):
                return True  # unavailable is never idle
            return bool(self._inflight or (self.projection and (
                self.projection.activity is not None or self.projection.gap or self.projection.conflict))
                or any(row["state"] in {"attempted", "queued", "claimed", "unknown"}
                       for row in self.dispatch_status()))

    def namespace_command(self):
        command = namespace_base() + ["--bind", str(self.home / "home"), "/agent/home",
            "--ro-bind", str(self.home / "work"), "/agent/work"]
        for source in self.build["mounts"]:
            command += ["--ro-bind", source, "/dsh/" + str(Path(source).relative_to(self.harness_root))]
        node = shutil.which("node")
        if not node:
            raise DeliveryRuntimeError("node is required for DSH Delivery")
        return command + ["--ro-bind", node, "/agent/node", "--chdir", "/agent/work",
            "--setenv", "DSH_PROXY_TOKEN", self.provider.proxy_token, "--", "/agent/node",
            "/agent/home/entry.mjs", "/agent/home/dsh.json"]

    def start(self):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        state = self.home / "dsh-session.json"
        if self.resume:
            if not state.exists():
                raise DeliveryRuntimeError("original DSH session missing; no replacement created")
            self.runtime_session_id = json.loads(state.read_text())["runtime_session_id"]
        else:
            if state.exists():
                if (self.home / "dsh-dispatch.jsonl").exists():
                    raise DeliveryRuntimeError("DSH session has admitted/unknown input; use explicit resume")
                self.runtime_session_id = json.loads(state.read_text())["runtime_session_id"]
            else:
                self.runtime_session_id = "delivery-" + uuid.uuid4().hex
                state.write_text(json.dumps({"runtime_session_id": self.runtime_session_id}))
        self.projection = DispatchProjection(self.runtime_session_id)
        dispatch_path = self.home / "dsh-dispatch.jsonl"
        if dispatch_path.exists():
            for line in dispatch_path.read_text().splitlines():
                record = json.loads(line)
                self.dispatches[record["dispatch_id"]] = record
        self.build = freeze_build(self.harness_root)
        for part in ("home", "work"):
            (self.home / part).mkdir(exist_ok=True, mode=0o700)
        credential = bytearray()
        if self.profile is not None:
            from dataclasses import replace
            selected = replace(self.profile, bindings={"delivery": self.binding})
            reader = read_glm_credential if self.binding.provider_id == "glm-messages" else read_deepseek_credential
            credential.extend(reader(preflight_profile_credentials(selected)[self.binding.provider_id]))
        self.provider = self.provider_factory(credential,
            **({"provider_id": self.binding.provider_id} if self.binding.provider_id == "glm-messages" else {}),
            on_attempt=NumericReceiptWriter(self.home / "dsh-provider.jsonl"))
        self.provider.register_usage_session(self.runtime_session_id, {
            "session_id": self.session_id, "role": "delivery", "phase": "supervision",
            "process_instance": self.process_instance, "provider": self.binding.provider_id,
            "requested_model": self.binding.model,
            "requested_effort": self.binding.requested_effort,
            "effective_effort": self.binding.effective_effort,
        }, evidence_ref="dsh-baseline.jsonl")
        credential[:] = b"\0" * len(credential)
        try:
            self.provider.start()
            directory = self.root / "modeling_team/runtimes/dsh_node"
            for name in ("entry.mjs", "delivery.mjs"):
                shutil.copyfile(directory / name, self.home / "home" / name)
            config = {"modules": {key: "/dsh/" + str(Path(path).relative_to(self.harness_root))
                      for key, path in self.build["modules"].items()},
                "instructions": self.instructions, "providerURL": self.provider.base_url,
                "servers": [], "deliveryTools": self.tools, "sessionId": self.runtime_session_id,
                "reasoningEffort": self.binding.effective_effort,
                "provider": self.binding.provider_id, "model": self.binding.model}
            (self.home / "home/dsh.json").write_text(json.dumps(config))
            self._stderr = (self.home / "stderr.log").open("a")
            self.process = subprocess.Popen(self.namespace_command(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self._stderr, text=True, bufsize=1,
                start_new_session=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
            self._pump_thread = threading.Thread(target=self._pump, daemon=True)
            self._pump_thread.start()
            result = self._rpc("initialize", {"cwd": "/agent/work",
                "provider": self.binding.provider_id, "model": self.binding.model,
                "reasoningEffort": self.binding.effective_effort})
            effective = result.get("effectiveBinding", {})
            if any(effective.get(key) != expected for key, expected in (
                    ("provider", self.binding.provider_id), ("model", self.binding.model),
                    ("reasoningEffort", self.binding.effective_effort))):
                raise DeliveryRuntimeError("dsh-model-binding-drift")
            actual = self._rpc("host/inspect", {})
            expected = [{"name": t["name"], "description": t["description"],
                         "parameters": t["inputSchema"]} for t in self.tools]
            if (sorted(actual["tools"], key=lambda t: t["name"]) != sorted(expected, key=lambda t: t["name"])
                    or set(actual["plugins"]) != (set(composition_plugins(self.binding.provider_id)) | {"@deepseek-ai/dsh-token-meter"}) - {
                        "@deepseek-ai/dsh-sdk-jsonrpc-server", "@deepseek-ai/dsh-mcp-client"}):
                raise DeliveryRuntimeError("dsh-tool-boundary-drift; correct composition and retry")
            baseline = {"build": self.build, "tools": actual, "binding": self.binding.as_dict(),
                "composition": {name: digest(directory / name) for name in ("entry.mjs", "delivery.mjs")},
                "instructions_sha256": hashlib.sha256(self.instructions.encode()).hexdigest()}
            baseline_path = self.home / "dsh-baseline.jsonl"
            if self.resume and baseline_path.exists():
                previous = json.loads(baseline_path.read_text().splitlines()[-1])
                changed = [key for key in baseline if baseline[key] != previous.get(key)]
                if changed:
                    raise DeliveryRuntimeError(f"dsh-recovery-binding-drift: {', '.join(changed)}; no replacement created")
            self._record("baseline", **baseline)
            if self.resume:
                self._check_tool_recovery()
                self._recover_events()
                self._rpc("session/resume", {"sessionId": self.runtime_session_id})
                self._rpc("host/checkpoint", {"sessionId": self.runtime_session_id})
                self._recover_events()
                self._reconcile_dispatches()
                if self.projection.gap or self.projection.conflict or any(
                        r["state"] in {"attempted", "unknown", "claimed"} for r in self.dispatch_status()):
                    raise DeliveryRuntimeError("dsh-recovery-unresolved; reconcile original inbox/tools; no new input sent")
        except Exception:
            self.close()
            raise

    def _write(self, value):
        with self._write_lock:
            try:
                self.process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
            except (OSError, ValueError, AttributeError) as exc:
                raise DeliveryRuntimeError("DSH Delivery transport closed") from exc

    def _rpc(self, method, params, *, dispatch_id=None, timeout=30):
        with self._lock:
            self._rpc_id += 1
            identity = self._rpc_id
            if dispatch_id:
                self.dispatches[dispatch_id]["rpc_id"] = identity
        self._write({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        with self._condition:
            while identity not in self._responses:
                if self._pump_failed or self.process.poll() is not None:
                    raise DeliveryRuntimeError("DSH Delivery process/event pump unavailable")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DeliveryRuntimeError(f"DSH Delivery RPC receipt unknown: {method}")
                self._condition.wait(min(remaining, .2))
            response = self._responses.pop(identity)
        if "error" in response:
            raise DeliveryRuntimeError(f"DSH Delivery RPC rejected: {method}", category="rejected")
        return response.get("result", {})

    def _pump(self):
        try:
            for line in self.process.stdout:
                value = json.loads(line)
                self._record("wire", frame=value)
                if value.get("method") == "ontoweave/delivery/tool" and "id" in value:
                    with self._lock:
                        self._inflight += 1
                    self._tools.submit(self._tool, value)
                elif "id" in value and "method" not in value:
                    with self._condition:
                        for row in self.dispatches.values():
                            if row.get("rpc_id") == value["id"] and row.get("process_instance") == self.process_instance:
                                message = value.get("result", {}).get("messageId")
                                row.update(message_id=message, state="queued" if message else
                                           "rejected" if "error" in value else "unknown")
                                self._record("dispatch", **row)
                        self._responses[value["id"]] = value
                        self._condition.notify_all()
                elif value.get("method") == "session.event":
                    params = value["params"]
                    if params.get("sessionId") != self.runtime_session_id:
                        raise DeliveryRuntimeError("DSH Delivery unbound session event")
                    event = params["event"]
                    with self._lock:
                        fresh = self.projection.append(event)
                        if self.projection.gap:
                            self._recover_events()
                    if fresh and event["type"] == "turn/end":
                        reason = event["data"]["reason"]
                        kind = reason.get("kind") if isinstance(reason, dict) else reason
                        self._events.put({"event": "activity_ended", "reason": reason,
                                          "status": "failed" if kind in {"error", "failed", "blocked", "max-tokens"} else "ended",
                                          **self.identity})
                elif value.get("method") == "host/provider-error":
                    params = value.get("params", {})
                    self._events.put({"event": "provider_error", "status": "failed",
                                      "code": params.get("code"),
                                      "http_status": params.get("http_status"), **self.identity})
                elif "id" in value:
                    self._write({"jsonrpc": "2.0", "id": value["id"], "error": {
                        "code": -32601, "message": "undeclared Delivery callback"}})
                elif value.get("method") != "session.status":
                    self._events.put({"event": "unknown_runtime_notification", "status": "failed", **self.identity})
            if not self._closed:
                raise DeliveryRuntimeError("DSH Delivery EOF")
        except Exception:
            self._pump_failed = True
            self._events.put({"event": "event_pump_unavailable", "status": "failed", **self.identity})

    def _tool(self, value):
        params = value.get("params", {})
        identity = f"{self.session_id}:{self.runtime_session_id}:{params.get('callId')}"
        try:
            if (self._closed or params.get("sessionId") != self.runtime_session_id
                    or not params.get("callId") or params.get("name") not in {t["name"] for t in self.tools}):
                raise ValueError("undeclared tool or invalid native call identity")
            self._record("tools", state="admitted", call_identity=identity, request=params)
            result = self.tool_handler(params["name"], params.get("arguments", {}), call_identity=identity)
            self._record("tools", state="settled", call_identity=identity, result=result)
            try:
                self._write({"jsonrpc": "2.0", "id": value["id"], "result": result})
            except DeliveryRuntimeError:
                self._record("tools", state="receipt_unknown", call_identity=identity, result=result)
        except Exception as exc:
            self._record("tools", state="unknown", call_identity=identity, error_type=type(exc).__name__)
            self._write({"jsonrpc": "2.0", "id": value["id"], "error": {
                "code": -32000, "message": "delivery_tool_failed; inspect Host tool receipt"}})
        finally:
            with self._lock:
                self._inflight -= 1

    def _recover_events(self):
        for path in sorted((self.home / "home/sessions").rglob("*.jsonl")):
            if self.runtime_session_id not in str(path):
                continue
            for line in path.read_text().splitlines():
                event = json.loads(line)
                if isinstance(event, dict) and {"seq", "type", "data"} <= event.keys():
                    self.projection.append(event)

    def _check_tool_recovery(self):
        path = self.home / "dsh-tools.jsonl"
        latest = {}
        if path.exists():
            for line in path.read_text().splitlines():
                row = json.loads(line)
                latest[row["call_identity"]] = row
        pending = [key for key, row in latest.items() if row["state"] not in {"settled", "receipt_unknown"}]
        if pending:
            raise DeliveryRuntimeError("dsh-recovery-tool-outcome-unknown: " + ", ".join(pending)
                + "; reconcile original Host tool/write receipts before resume")

    def _reconcile_dispatches(self):
        # The exact Host envelope is in durable inbox insertion events, including
        # its dispatch ID. This also repairs a lost prompt RPC response.
        for event in self.projection.events.values():
            if event["type"] != "agent/inbox/spliced":
                continue
            for message in event["data"]["inserted"]:
                text = "".join(b.get("text", "") for b in message.get("content", []) if b.get("type") == "text")
                try:
                    dispatch_id = json.loads(text)["host_dispatch_id"]
                except (ValueError, KeyError, TypeError):
                    continue
                if dispatch_id in self.dispatches:
                    self.dispatches[dispatch_id].update(message_id=message["id"], state="queued")

    def dispatch_status(self):
        with self._lock:
            return [{**row, **(self.projection.status(row["message_id"])
                     if row.get("message_id") else {})} for row in self.dispatches.values()]

    def _dispatch(self, text, active):
        if self._closed:
            raise DeliveryRuntimeError("DSH Delivery is closed", category="rejected")
        dispatch_id = uuid.uuid4().hex
        payload = {"host_dispatch_id": dispatch_id, "payload": json.loads(text)}
        if any(row.get("payload") == payload["payload"] and row["state"] in {
                "attempted", "queued", "claimed", "unknown"} for row in self.dispatch_status()):
            raise DeliveryRuntimeError("DSH input already queued or unknown; reconcile original dispatch")
        row = {"dispatch_id": dispatch_id, **self.identity, "state": "attempted", "payload": payload["payload"]}
        with self._lock:
            self.dispatches[dispatch_id] = row
            self._record("dispatch", **row)
        method = "ontoweave/delivery/steer" if active else "session/prompt"
        content = json.dumps(payload, ensure_ascii=False)
        params = {"sessionId": self.runtime_session_id,
                  **({"text": content} if active else {"contentBlocks": [{"type": "text", "text": content}]})}
        try:
            result = self._rpc(method, params, dispatch_id=dispatch_id)
            if not result.get("messageId"):
                raise DeliveryRuntimeError("DSH Delivery enqueue receipt missing messageId")
            row.update(message_id=result["messageId"], state="queued")
        except DeliveryRuntimeError as exc:
            row["state"] = "rejected" if exc.category == "rejected" else "unknown"
            raise
        finally:
            self._record("dispatch", **row)
        return {key: value for key, value in row.items() if key != "payload"}

    def send(self, text):
        return self._dispatch(text, False)

    def steer(self, text):
        return self._dispatch(text, True)

    def interrupt(self):
        return self._rpc("ontoweave/delivery/interrupt", {"sessionId": self.runtime_session_id})

    def poll(self, timeout=0):
        result = []
        try:
            result.append(self._events.get(timeout=timeout))
        except queue.Empty:
            pass
        while not self._events.empty():
            result.append(self._events.get())
        with self._lock:
            if self.projection and (self.projection.gap or self.projection.conflict):
                self._recover_events()
                if self.projection.gap or self.projection.conflict:
                    raise DeliveryRuntimeError("dsh-event-sequence-unresolved; inspect original session events before resume")
        if self.process and self.process.poll() is not None and not self._closed:
            raise DeliveryRuntimeError("DSH Delivery process exited; preserve original session")
        return result

    def close(self):
        self._closed = True
        if self.process and self.process.poll() is None:
            try:
                self._rpc("shutdown", {}, timeout=3)
                self.process.wait(timeout=3)
            except (DeliveryRuntimeError, subprocess.TimeoutExpired):
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        if hasattr(self, "_pump_thread"):
            self._pump_thread.join(timeout=2)
        self._tools.shutdown(wait=False, cancel_futures=True)
        if self.provider:
            self.provider.stop()
        if self._stderr:
            self._stderr.close()
