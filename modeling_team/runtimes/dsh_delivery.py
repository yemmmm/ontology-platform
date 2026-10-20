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
from ..close_statistics import ActivityRecorder, clock_ref
from ..model_routing import preflight_profile_credentials, PROVIDER_CATALOG
from ..task_budget import BudgetError
from .budget import (
    binding_with_key_ref,
    normalize_control_epoch,
    runtime_budget,
    valid_key_ref,
)


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
                 harness_root=None, provider_factory=MessagesProviderSession,
                 budget=None, budget_owner_id=None):
        self.binding, self.home = binding, Path(home)
        self.instructions, self.tools, self.tool_handler = instructions, tools, tool_handler
        self.session_id, self.profile, self._resume_existing = session_id, profile, resume
        self.root = Path(repository_root or Path(__file__).resolve().parents[2])
        self.harness_root = Path(harness_root or "/home/yangxiang/deepseek-harness")
        self.provider_factory = provider_factory
        self.process_instance = uuid.uuid4().hex
        self.runtime_session_id = None
        self._retired_sessions = set()
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
        self.activity = None
        self._budget_source = budget
        self._budget_owner_id = budget_owner_id or f"delivery:{session_id}:{self.process_instance}"
        self._budget = None
        self._budget_control_epochs: set[str] = set()
        self._budget_control_receipts: dict[str, dict] = {}
        self._native_pid_identity = None

    def _record(self, kind, **value):
        with self._lock:
            with (self.home / f"dsh-{kind}.jsonl").open("a") as stream:
                stream.write(json.dumps({"runtime": "dsh", "process_instance": self.process_instance,
                    "runtime_session_id": self.runtime_session_id, **value}, ensure_ascii=False) + "\n")

    def _before_provider_request(self, receipt):
        """Admit a Delivery Messages request before it reaches the provider."""

        if self._budget is None or getattr(self._budget, "budget", None) is None:
            return
        session_id = receipt.get("runtime_session_id")
        # This provider instance belongs only to this Delivery session.  The
        # DSH harness normally sends the session header; a missing header is
        # still unambiguous here, unlike the shared production adapter.
        if session_id is not None and session_id != self.runtime_session_id:
            raise BudgetError(
                "budget_member_identity_missing",
                {"runtime_session_id": session_id, "expected": self.runtime_session_id},
            )
        self._budget.require("send")

    def _record_budget_control(self, epoch, status, **metadata):
        """Persist a receipt when possible without blocking physical control."""

        if self._budget is None:
            return
        try:
            self._budget.record_control(epoch, status, **metadata)
        except Exception:
            # SIGSTOP/SIGCONT remains authoritative even if the shared budget
            # ledger is unavailable or corrupt.  The local Host evidence keeps
            # that fact visible for later reconciliation.
            self._record(
                "budget-control",
                action=metadata.get("action"),
                epoch=epoch,
                status="unavailable",
                requested_status=status,
            )

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
        credential_binding = None
        if self.profile is not None:
            from dataclasses import replace
            selected = replace(self.profile, bindings={"delivery": self.binding})
            credential_bindings = preflight_profile_credentials(selected)
            credential_binding = credential_bindings.get(self.binding.provider_id)
        key_ref = valid_key_ref(getattr(credential_binding, "key_ref", None))
        budget_binding = binding_with_key_ref(self.binding, key_ref)
        self._budget = runtime_budget(
            self.home.parent,
            self._budget_owner_id,
            binding=budget_binding,
            runtime="dsh",
            explicit=self._budget_source,
            session_id=self.session_id,
            process_instance=self.process_instance,
            role="delivery",
        )
        self._budget.register_source(self.home / "dsh-provider.jsonl", "dsh_capture")
        self._budget.register_source(self.home / "dsh-native-delivery.jsonl", "dsh_native")
        self.activity = ActivityRecorder(self.home.parent, {
            "runtime": "dsh", "agent_id": "delivery", "role": "delivery",
            "session_id": self.session_id, "process_instance": self.process_instance,
            "provider": self.binding.provider_id, "requested_model": self.binding.model,
            "requested_effort": self.binding.requested_effort,
            "effective_effort": self.binding.effective_effort,
        }, usage_sources=[
            {"path": str(self.home / "dsh-provider.jsonl"), "kind": "dsh_capture"},
            {"path": str(self.home / "dsh-native-delivery.jsonl"), "kind": "dsh_native"},
        ],
            budget=self._budget.budget,
            budget_owner_id=self._budget_owner_id,
            budget_binding=self._budget.binding,
            budget_runtime="dsh")
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        state = self.home / "dsh-session.json"
        if self._resume_existing:
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
        self._retired_sessions = set(json.loads(state.read_text()).get("previous_session_ids", []))
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
            reader = read_glm_credential if self.binding.provider_id == "glm-messages" else read_deepseek_credential
            credential.extend(reader(credential_binding))
        self.provider = self.provider_factory(credential,
            **({"provider_id": self.binding.provider_id} if self.binding.provider_id == "glm-messages" else {}),
            on_attempt=NumericReceiptWriter(
                self.home / "dsh-provider.jsonl",
                budget=self._budget.budget,
                budget_owner_id=self._budget_owner_id,
                budget_binding=self._budget.binding,
                budget_kind="dsh_capture",
            ),
            before_request=self._before_provider_request,
        )
        self._usage_context = {
            "session_id": self.session_id, "agent_id": "delivery", "role": "delivery", "phase": "supervision",
            "process_instance": self.process_instance, "provider": self.binding.provider_id,
            "requested_model": self.binding.model,
            "requested_effort": self.binding.requested_effort,
            "effective_effort": self.binding.effective_effort,
            **({"key_ref": key_ref} if key_ref is not None else {}),
        }
        self.provider.register_usage_session(self.runtime_session_id, self._usage_context,
                                             evidence_ref="dsh-baseline.jsonl")
        credential[:] = b"\0" * len(credential)
        try:
            self.provider.start()
            directory = self.root / "modeling_team/runtimes/dsh_node"
            for name in ("entry.mjs", "delivery.mjs", "activity.mjs"):
                shutil.copyfile(directory / name, self.home / "home" / name)
            config = {"clockRef": clock_ref(), "modules": {key: "/dsh/" + str(Path(path).relative_to(self.harness_root))
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
            self._native_pid_identity = self._process_info(self.process.pid)[2]
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
                "composition": {name: digest(directory / name) for name in ("entry.mjs", "delivery.mjs", "activity.mjs")},
                "instructions_sha256": hashlib.sha256(self.instructions.encode()).hexdigest()}
            baseline_path = self.home / "dsh-baseline.jsonl"
            if self._resume_existing and baseline_path.exists():
                previous = json.loads(baseline_path.read_text().splitlines()[-1])
                changed = [key for key in baseline if baseline[key] != previous.get(key)]
                if changed:
                    raise DeliveryRuntimeError(f"dsh-recovery-binding-drift: {', '.join(changed)}; no replacement created")
            self._record("baseline", **baseline)
            if self._resume_existing:
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
                if value.get("method") != "host/activity":
                    session_id = value.get("params", {}).get("sessionId", self.runtime_session_id)
                    self._record("wire", frame=value, runtime_session_id=session_id)
                    if value.get("method") == "session.event":
                        self._record(
                            "native-delivery",
                            frame=value,
                        )
                if value.get("method") == "host/activity":
                    params = value.get("params", {})
                    if self.activity and params.get("sessionId") == self.runtime_session_id:
                        if not self.activity.context.get("runtime_session_id"):
                            self.activity.bind(self.runtime_session_id)
                        fields = {k: v for k, v in params.items() if k != "event"}
                        if str(fields.get("monotonic_ns", "")).isdigit():
                            fields["monotonic_ns"] = int(fields["monotonic_ns"])
                        self.activity.emit(params.get("event"), **fields)
                elif value.get("method") == "ontoweave/delivery/tool" and "id" in value:
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
                        if params.get("sessionId") in self._retired_sessions:
                            continue  # Retained on wire; cannot finish the new activity.
                        raise DeliveryRuntimeError("DSH Delivery unbound session event")
                    event = params["event"]
                    if self.activity and not self.activity.context.get("runtime_session_id"):
                        self.activity.bind(self.runtime_session_id)
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
                     if row.get("message_id") and row.get("runtime_session_id") == self.runtime_session_id
                     else {})} for row in self.dispatches.values()]

    def new_thread(self):
        with self._lock:
            if self.busy or self._closed:
                raise DeliveryRuntimeError("DSH Delivery unavailable or busy")
        new_id = "delivery-" + uuid.uuid4().hex
        result = self._rpc("ontoweave/delivery/new-session", {
            "sessionId": self.runtime_session_id, "newSessionId": new_id})
        if result.get("sessionId") != new_id:
            raise DeliveryRuntimeError("DSH phase session reservation unconfirmed")
        self.provider.register_usage_session(new_id, self._usage_context,
                                             evidence_ref="dsh-baseline.jsonl")
        with self._lock:
            for row in self.dispatch_status():
                self.dispatches[row["dispatch_id"]] = row
                self._record("dispatch", **row)
            self._retired_sessions.add(self.runtime_session_id)
            self.runtime_session_id = new_id
            self.projection = DispatchProjection(new_id)
            self.activity.bind(new_id)
            path = self.home / "dsh-session.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"runtime_session_id": new_id,
                "previous_session_ids": sorted(self._retired_sessions)}))
            temporary.replace(path)
        return self.identity

    def _dispatch(self, text, active):
        if self._closed:
            raise DeliveryRuntimeError("DSH Delivery is closed", category="rejected")
        if self._budget is not None:
            self._budget.require("steer" if active else "start")
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

    @staticmethod
    def _process_info(pid):
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
            values = raw[raw.rfind(")") + 2 :].split()
            return values[0], int(values[2]), values[19], int(values[1])
        except (OSError, ValueError, IndexError):
            return None, None, None, None

    def _native_group(self):
        """Return the currently owned native process group after PID checks."""

        if self.process is None or self.process.poll() is not None:
            raise DeliveryRuntimeError("DSH Delivery native process is not running", category="rejected")
        pid = self.process.pid
        state, pgid, identity, _ = self._process_info(pid)
        if identity != self._native_pid_identity or pgid != pid:
            raise DeliveryRuntimeError("DSH Delivery native PID identity changed")
        rows = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            child = int(path.name)
            child_state, child_pgid, child_identity, parent = self._process_info(child)
            if child_pgid == pid and child_identity:
                rows.append({
                    "pid": child,
                    "pgid": child_pgid,
                    "state": child_state,
                    "start_identity": child_identity,
                    "parent_pid": parent,
                })
        if not any(row["pid"] == pid for row in rows):
            rows.append({"pid": pid, "pgid": pgid, "state": state, "start_identity": identity})
        return sorted(rows, key=lambda row: row["pid"])

    def pause(self, *, epoch=None, _budget_checked=False):
        """Freeze only the DSH native process group; Host polling stays live."""

        if epoch is None:
            epoch = 0
            if self._budget is not None:
                show = getattr(self._budget.budget, "show", None)
                if callable(show):
                    try:
                        epoch = show("delivery").get("epoch", 0)
                    except Exception:
                        pass
        epoch = normalize_control_epoch(epoch)
        if self._closed or self.process is None or self.process.poll() is not None:
            self._record_budget_control(epoch, "not_running", action="pause")
            evidence = {"status": "not_running", "epoch": epoch, **self.identity}
            self._budget_control_epochs.add(f"pause:{epoch}")
            self._budget_control_receipts[f"pause:{epoch}"] = evidence
            return evidence
        key = f"pause:{epoch}"
        if key in self._budget_control_epochs:
            return {"status": "already_recorded", "epoch": epoch, **self.identity}
        self._native_group()
        os.killpg(self.process.pid, signal.SIGSTOP)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current = self._native_group()
            if current and all(item["state"] in {"T", "t"} for item in current):
                self._budget_control_epochs.add(key)
                evidence = {"status": "effective", "epoch": epoch, "groups": current, **self.identity}
                self._record("control", action="pause", **evidence)
                self._record_budget_control(epoch, "effective", action="pause", groups=current)
                self._budget_control_receipts[key] = evidence
                return evidence
            time.sleep(0.02)
        current = self._native_group()
        self._record("control", action="pause", status="pause_pending", epoch=epoch, groups=current, **self.identity)
        self._record_budget_control(epoch, "pending", action="pause", groups=current)
        self._budget_control_receipts[key] = {
            "status": "pending", "epoch": epoch, "groups": current, **self.identity
        }
        raise DeliveryRuntimeError("pause-pending: DSH native process group did not stop")

    def resume(self, *, epoch=None, _budget_checked=False):
        """Resume only the previously validated DSH native process group."""

        if epoch is None:
            epoch = 0
            if self._budget is not None:
                show = getattr(self._budget.budget, "show", None)
                if callable(show):
                    try:
                        epoch = show("delivery").get("epoch", 0)
                    except Exception:
                        pass
        epoch = normalize_control_epoch(epoch)
        key = f"resume:{epoch}"
        if key in self._budget_control_epochs:
            return {"status": "already_recorded", "epoch": epoch, **self.identity}
        if self._closed or self.process is None or self.process.poll() is not None:
            self._record_budget_control(epoch, "not_running", action="resume")
            evidence = {"status": "not_running", "epoch": epoch, **self.identity}
            self._budget_control_epochs.add(key)
            self._budget_control_receipts[key] = evidence
            return evidence
        group = self._native_group()
        os.killpg(self.process.pid, signal.SIGCONT)
        deadline = time.monotonic() + 3
        current = group
        while time.monotonic() < deadline:
            try:
                current = self._native_group()
            except DeliveryRuntimeError:
                self._record_budget_control(epoch, "pending", action="resume", groups=group)
                self._record("control", action="resume", status="resume_pending", epoch=epoch,
                             groups=group, **self.identity)
                raise
            if current and all(item["state"] not in {"T", "t"} for item in current):
                break
            time.sleep(0.02)
        if not current or any(item["state"] in {"T", "t"} for item in current):
            self._record("control", action="resume", status="resume_pending", epoch=epoch,
                         groups=current, **self.identity)
            self._record_budget_control(epoch, "pending", action="resume", groups=current)
            self._budget_control_receipts[key] = {
                "status": "pending", "epoch": epoch, "groups": current, **self.identity
            }
            raise DeliveryRuntimeError("resume-pending: DSH native process group did not resume")
        self._budget_control_epochs.add(key)
        evidence = {"status": "effective", "epoch": epoch, "groups": current, **self.identity}
        self._record("control", action="resume", **evidence)
        self._record_budget_control(epoch, "effective", action="resume", groups=current)
        self._budget_control_receipts[key] = evidence
        return evidence

    def control_budget(self, message: dict) -> dict:
        if not isinstance(message, dict) or message.get("action") not in {"pause", "resume"}:
            raise DeliveryRuntimeError("task-budget control binding is invalid", category="rejected")
        action = message["action"]
        epoch = message.get("epoch")
        if epoch is None:
            raise DeliveryRuntimeError("task-budget control epoch is invalid", category="rejected")
        try:
            epoch = normalize_control_epoch(epoch)
        except ValueError as exc:
            raise DeliveryRuntimeError("task-budget control epoch is invalid", category="rejected") from exc
        key = f"{action}:{epoch}"
        if key in self._budget_control_epochs:
            return {
                **self._budget_control_receipts.get(key, {
                    "status": "already_recorded", "action": action, "epoch": epoch, **self.identity
                }),
                "deduplicated": True,
            }
        if action == "resume" and self._budget is not None:
            budget_core = self._budget.budget
            show = getattr(budget_core, "show", None)
            if callable(show):
                try:
                    state = show("delivery")
                except Exception:
                    # A broken budget ledger must not prevent physical native
                    # process control; the local control evidence remains the
                    # source of truth until Host reconciliation.
                    state = None
                if state is not None and (
                    not state.get("admission_open") or state.get("pause_reasons")
                ):
                    evidence = {
                        "status": "pending", "action": action, "epoch": epoch,
                        "pause_reasons": state.get("pause_reasons", []), **self.identity,
                    }
                    self._record_budget_control(
                        epoch,
                        "pending",
                        action=action,
                        pause_reasons=state.get("pause_reasons", []),
                    )
                    self._budget_control_receipts[key] = evidence
                    return evidence
        return (
            self.pause(epoch=epoch, _budget_checked=True)
            if action == "pause"
            else self.resume(epoch=epoch, _budget_checked=True)
        )

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
            if self.activity and hasattr(self.provider, "snapshot") and self.provider.snapshot().get("usage_capture_dropped"):
                self.activity.emit("capture_gap", status="unknown")
        if self._stderr:
            self._stderr.close()
        if self.activity:
            self.activity.exit(self.process.poll() if self.process else None,
                               startup_failed=self.process is None)
