"""Local, single-conversation Delivery entry point backed by native Host tools."""
from __future__ import annotations

import asyncio
import copy
import fcntl
import hashlib
import inspect
import json
import os
import queue
import re
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from . import host_ops_mcp
from .host_ops import HostOpError, resolve_run_root
from .model_routing import (
    ProviderSessionManager, load_team_model_profile, preflight_profile_credentials,
    resolve_delivery_model_binding, uses_external_credential_session,
)
from .runtimes.delivery import DeliveryRuntime, DeliveryRuntimeError
from .delivery_verification import start_verification, verification_status, stop_verification
from .efficiency import begin_round, summarize_round
from .delivery_conversation import ConversationLog, ConversationServer, ConversationError, now

_PUBLIC_KINDS = {"status", "business_question", "decision_request", "final"}
_READ = {
    "get_run_status", "get_run_events", "get_pending_actions", "get_request_result",
    "inspect_checkpoints", "get_evaluation_status", "get_repair_status",
    "read_platform_record", "reconcile_write_state",
}
_PRODUCTION = {"start_run", "resume_from_checkpoint"}


def _decision_observation(observation: dict) -> dict:
    """Keep decisions and their bindings, while ignoring observation-only traffic."""
    noise = {
        "observed_at", "events_cursor", "last_verifiable_activity",
        "heartbeat_at", "last_heartbeat_at", "heartbeat_count",
        "log_bytes", "stdout_bytes", "stderr_bytes", "log_tails",
        "stdout_tail", "stderr_tail", "staged_decision_count", "latest_staged_decision_at",
    }

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in noise}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    projected = clean(observation)
    # Stage timestamp/ordinal alone may advance as the same phase emits more
    # progress. The phase, batch/review identity and classification are decisions.
    for run in projected.get("runs", {}).values():
        status = run.get("status", {}).get("data", {})
        stage = status.get("stage")
        if isinstance(stage, dict):
            stage.pop("recorded_at", None)
            stage.pop("ordinal", None)
    return projected


_LOCAL_SPECS = [
    {"name": "record_efficiency_progress", "description": "Append evidence-backed timing intervals or verified completion to the Host-configured round; never resets its start or judges semantic PASS.",
     "inputSchema": {"type": "object", "properties": {
         "intervals": {"type": "array", "items": {"type": "object"}},
         "completion": {"type": "object"}, "counts": {"type": "object"},
         "question_set": {"type": "string"}}, "additionalProperties": False}},
    {"name": "emit_user_message", "description": "Publish a business-facing message only.",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"enum": sorted(_PUBLIC_KINDS)}, "text": {"type": "string"},
         "question_delivery_id": {"type": "string"},
         "reply_to_message_ids": {"type": "array", "items": {"type": "string"}},
         "resolved_question_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["kind", "text"],
         "additionalProperties": False}},
    {"name": "read_delivery_artifact", "description": "Read approved sources or bound private run evidence.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}},
                     "required": ["path"], "additionalProperties": False}},
    {"name": "finish_delivery", "description": "Record verified result and limits, then retain this Delivery and the existing Team in standby. Only explicit user/Host stop destroys them.",
     "inputSchema": {"type": "object", "properties": {"conclusion": {"type": "string"}},
                     "required": ["conclusion"], "additionalProperties": False}},
    {"name": "prepare_repair_task", "description": "Create a narrow, publicly evidenced repair task under the selected repair scope.",
     "inputSchema": {"type": "object", "properties": {
         "operation_id": {"type": "string"}, "text": {"type": "string"},
         "source_references": {"type": "array", "items": {"type": "string"}},
         "owned_paths": {"type": "array", "items": {"type": "string"}}},
         "required": ["operation_id", "text", "source_references", "owned_paths"],
         "additionalProperties": False}},
    {"name": "verify_repair", "description": "Start fixed Host checks and explicitly authorized deployment for one completed owned repair. This is not semantic acceptance.",
     "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string"}},
                     "required": ["operation_id"], "additionalProperties": False}},
    {"name": "get_repair_verification_status", "description": "Read actual fixed-check, deployment and health receipts; drift invalidates retained PASS.",
     "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string"}},
                     "required": ["operation_id"], "additionalProperties": False}},
    {"name": "record_flow_confirmation", "description": "Record actual sourced Agent acknowledgements of pause/resume. A delivered instruction alone is not a confirmation or a write seal.",
     "inputSchema": {"type": "object", "properties": {
         "message_id": {"type": "string"}, "action": {"enum": ["pause", "resume"]},
         "status": {"enum": ["pending", "effective", "failed", "unknown"]},
         "evidence_references": {"type": "array", "items": {"type": "string"}},
         "limitations": {"type": "string"}},
         "required": ["message_id", "action", "status", "evidence_references"],
         "additionalProperties": False}},
]


class DeliverySession:
    def __init__(self, *, repository_root: Path, session_root: Path, config: dict,
                 resume: bool = False) -> None:
        self.repository_root = repository_root.resolve()
        self.session_root = session_root.resolve()
        self.config = copy.deepcopy(config)
        self.project_id = config.get("project_id") or config.get("readback_scope", {}).get("project_id")
        self.authorization_valid_until = config.get("authorization_valid_until")
        self.activity = "active"
        self.work_result = None
        self.conversation = None
        self.flow_confirmation = None
        self.session_id = config["session_id"]
        if not isinstance(self.session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.session_id):
            raise ValueError("session_id is required")
        self.authorization = config["authorization_reference"]
        if not isinstance(self.authorization, str) or not self.authorization.strip():
            raise ValueError("authorization_reference is required")
        self.allowed_operations = set(config.get("allowed_operations", ["read"]))
        self.business_input_role = config.get("business_input_role", "user")
        if self.business_input_role not in {"user", "test-answerer"}:
            raise ValueError("business_input_role must be user or test-answerer")
        if not self.allowed_operations <= {"read", "supervise", "production", "evaluation", "repair"}:
            raise ValueError("unsupported allowed_operations")
        if "production" in self.allowed_operations and any(not config.get(key) for key in ("task", "profile", "scope")):
            raise ValueError("production authorization requires a selected task, profile and scope")
        self.sources = {self._path(value) for value in config.get("allowed_sources", [])}
        self.run_ids = set(config.get("run_ids", []))
        self.operation_ids: set[str] = set()
        self.operation_kinds: dict[str, str] = {}
        self.verification_ids: set[str] = set()
        self.reconciled_runs: set[str] = set()
        self.repair_task_files = {self._path(x) for x in config.get("repair_task_files", [])}
        self.messages: list[dict] = []
        self.finished = False
        self.profile = load_team_model_profile(self.repository_root, config["model_profile"])
        self.binding, self.binding_source = resolve_delivery_model_binding(self.profile)
        if resume:
            previous = json.loads((self.session_root / "session.json").read_text())
            if previous["authorization_reference"] != self.authorization:
                raise ValueError("resumption requires the original authorization reference")
            if previous["model_binding"] != self.binding.as_dict():
                raise ValueError("resumption requires the original model binding")
            if previous.get("project_id") and previous["project_id"] != self.project_id:
                raise ValueError("resumption requires the original project binding")
            if previous.get("authorization_valid_until") != self.authorization_valid_until:
                raise ValueError("resumption cannot change the original authorization deadline")
            self.run_ids.update(previous["run_ids"])
            self.operation_ids.update(previous["operation_ids"])
            self.operation_kinds.update(previous.get("operation_kinds", {}))
            self.verification_ids.update(previous.get("verification_ids", []))
            self.repair_task_files.update(Path(x) for x in previous.get("repair_task_files", []))
            self.allowed_operations.intersection_update(previous["allowed_operations"])
            self.activity = previous.get("activity", "active")
            self.work_result = previous.get("work_result")
        else:
            self.session_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        if self.project_id:
            if not isinstance(self.project_id, str):
                raise ValueError("project_id must be an explicit string binding")
            for scope in self._readback_scopes():
                if scope.get("project_id") and scope["project_id"] != self.project_id:
                    raise ValueError("bound runs must belong to the same project")
            self.conversation = ConversationLog(self.session_root, project_id=self.project_id,
                                                delivery_session_id=self.session_id)
        timing = config.get("efficiency_round")
        if timing is not None:
            timing_path = self.session_root / "efficiency-round.json"
            if not timing_path.exists():
                begin_round(timing_path, **timing)
            else:
                recorded = json.loads(timing_path.read_text())
                if (recorded["started_at"] != timing["started_at"]
                        or recorded["start_reference"] != timing["start_reference"]):
                    raise ValueError("resumption cannot reset the efficiency round start")
        self._tools: dict[str, dict] = {}
        for tool in asyncio.run(host_ops_mcp.mcp.list_tools()):
            schema = copy.deepcopy(tool.inputSchema)
            properties = schema.get("properties", {})
            for name in ("repository_root", "host_session_ref", "base_url"):
                properties.pop(name, None)
            schema["additionalProperties"] = False
            self._tools[tool.name] = {"name": tool.name, "description": tool.description,
                                      "inputSchema": schema}
        self._tools.update({item["name"]: copy.deepcopy(item) for item in _LOCAL_SPECS})
        self._save("ready")

    def _path(self, value: str) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else self.repository_root / path).resolve()

    def _save(self, state: str, **extra: Any) -> None:
        record = {"schema_version": 1, "session_id": self.session_id,
                  "project_id": self.project_id, "activity": self.activity,
                  "work_result": self.work_result,
                  "authorization_valid_until": self.authorization_valid_until,
                  "authorization_reference": self.authorization, "state": state,
                  "run_ids": sorted(self.run_ids), "operation_ids": sorted(self.operation_ids),
                  "operation_kinds": self.operation_kinds,
                  "verification_ids": sorted(self.verification_ids),
                  "repair_task_files": sorted(str(x) for x in self.repair_task_files),
                  "model_profile": self.profile.profile_id,
                  "model_binding": self.binding.as_dict(),
                  "model_binding_source": self.binding_source,
                  "business_input_role": self.business_input_role,
                  "supervisor_pid": os.getpid(),
                  "native_thread_id": getattr(self, "native_thread_id", None),
                  "native_pid": getattr(self, "native_pid", None),
                  "allowed_operations": sorted(self.allowed_operations), **extra}
        temporary = self.session_root / "session.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        self._append("session-events.jsonl", record)
        temporary.replace(self.session_root / "session.json")
        if self.conversation:
            state = {"activity": self.activity, "observed_at": now(), "basis": "delivery_state",
                     "delivery_result": self.work_result}
            if state != getattr(self, "_public_state", None):
                self.conversation.append("session_state", state=state)
                self._public_state = state

    def _append(self, filename: str, value: dict) -> None:
        with (self.session_root / filename).open("a") as handle:
            handle.write(json.dumps(value, ensure_ascii=False) + "\n")

    def tool_specs(self) -> list[dict]:
        return list(self._tools.values())

    def accept_user_input(self, text: str) -> dict:
        import uuid
        packet = {"kind": "user_input", "text": text,
                  "input_role": self.business_input_role,
                  "source_reference": f"delivery:{self.session_id}:{self.business_input_role}:{uuid.uuid4().hex}",
                  "authorization_reference": self.authorization}
        if not self.conversation:
            self._append("user-input.jsonl", packet)
        return packet

    def sourced_packet(self, message: dict) -> dict:
        packet = {**message, "kind": "user_input", "message_kind": message["kind"],
                  "input_role": "test-answerer" if message["sender"]["kind"] == "test_answerer" else "user",
                  "authorization_reference": self.authorization,
                  "source_reference": message.get("source_reference") or f"delivery:{self.session_id}:{message['message_id']}"}
        if message.get("reply_to_message_id"):
            original = self.conversation.receipt(message["reply_to_message_id"])
            packet["question"] = {"message_id": original["message_id"], "text": original["text"],
                                  "question_delivery_id": original.get("question_delivery_id")}
        if message.get("action") in {"pause", "resume"}:
            self.flow_confirmation = message["message_id"]
            self.activity = "pause_pending" if message["action"] == "pause" else self.activity
            packet["flow_instruction"] = (
                "Relay this user/Host instruction to the actual current Coordinator, or evaluation owner "
                "and current Consumer/Judge. Agents stop continuing their tasks and acknowledge waiting. "
                "Resume only on the explicit next instruction, using the original task/thread; do not use "
                "pause_run/resume_live_run, revoke permissions, freeze processes or interrupt inference. "
                "Record actual acknowledgements separately from mere delivery and disclose in-flight calls."
            )
            self.conversation.append("control_result", message_id=message["message_id"],
                                     action=message["action"], status="pending", basis="awaiting_agent_confirmation")
            self._save("active")
        return packet

    def apply_user_control(self, text: str) -> dict | None:
        if text in {"暂停", "继续"}:
            # Cooperative instructions are handled by Delivery, never a launch gate.
            return None
        if text not in {"取消", "撤回预算", "停止"}:
            return None
        # Business controls prevent new launches before the native model replies.
        self.allowed_operations -= {"production", "evaluation", "repair"}
        name = "stop_run"
        results = {}
        if text != "撤回预算":
            for run_id in sorted(self.run_ids):
                arguments = {"run_id": run_id}
                if name == "stop_run":
                    arguments["reason"] = "user cancellation through Delivery"
                try:
                    results[run_id] = {"ok": True, "data": getattr(host_ops_mcp, name)(
                        **arguments, repository_root=self.repository_root)}
                except HostOpError as exc:
                    results[run_id] = {"ok": False, "error": exc.as_envelope()}
        if text in {"取消", "撤回预算", "停止"}:
            for operation_id in sorted(self.verification_ids):
                results["verification:" + operation_id] = stop_verification(
                    operation_id=operation_id, session_root=self.session_root)
            for operation_id in sorted(self.operation_ids):
                try:
                    results[operation_id] = {"ok": True, "data": host_ops_mcp.stop_delivery_operation(
                        operation_id=operation_id, reason=text, repository_root=self.repository_root)}
                except HostOpError as exc:
                    results[operation_id] = {"ok": False, "error": exc.as_envelope()}
        if text == "停止":
            self.activity = "stopping"
            self.stop_pending = True
        self._save("stopping" if text == "停止" else "cancelled" if text == "取消" else "budget_revoked")
        return {"control": text, "launch_permissions_revoked": True, "results": results}

    def drain_messages(self) -> list[dict]:
        messages, self.messages = self.messages, []
        return messages

    def _read_artifact(self, value: str) -> dict:
        path = self._path(value)
        approved = path in self.sources or path in {
            self.session_root / name for name in ("session.json", "session-events.jsonl", "user-input.jsonl", "public-messages.jsonl", "observation.json", "efficiency-round.json", "efficiency-progress.jsonl")
        }
        approved = approved or path in {
            self.repository_root / '.delivery-ops' / f'{operation_id}.{suffix}'
            for operation_id in self.operation_ids if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', operation_id)
            for suffix in ('repair-result.patch', 'repair-result.json')
        }
        if not approved:
            for run_id in self.run_ids:
                try:
                    root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
                except HostOpError:
                    continue
                if path.is_relative_to(root):
                    relative = path.relative_to(root)
                    approved = relative.parts[0] in {
                        "competency-questions", "acceptance-v3", "evidence", "manifest-snapshots",
                    } or relative.as_posix() in {
                        "state.json", "baseline-manifest.json", "task.snapshot.yaml", "profile.snapshot.yaml",
                        "model-handoff.json", "control/host-requests.jsonl",
                    }
                    if approved:
                        break
        if not approved or not path.is_file():
            raise ValueError("artifact is outside approved sources and bound run evidence")
        if path.stat().st_size > 2_000_000:
            raise ValueError("artifact exceeds read bound; use incremental run events")
        raw = path.read_bytes()
        return {"path": str(path), "text": raw.decode("utf-8"),
                "content_digest": "sha256:" + hashlib.sha256(raw).hexdigest()}

    def _permission(self, name: str) -> str:
        if name in _READ:
            return "read"
        if name in _PRODUCTION:
            return "production"
        if name == "start_evaluation":
            return "evaluation"
        if name == "start_repair":
            return "repair"
        return "supervise"

    def _readback_scopes(self) -> list[dict]:
        scopes = [self.config.get("readback_scope", {})]
        for run_id in self.run_ids:
            try:
                root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
                state = json.loads((root / "state.json").read_text())
                binding = state.get("platform_binding")
                if isinstance(binding, dict):
                    scopes.append(binding)
            except (HostOpError, OSError, ValueError):
                continue
        return scopes

    def call_tool(self, name: str, arguments: dict, *, call_identity: str | None = None) -> dict:
        try:
            if name not in self._tools:
                raise ValueError("undeclared Delivery tool")
            validate(arguments, self._tools[name]["inputSchema"])
            if name == "record_efficiency_progress":
                from datetime import datetime, timezone
                path = self.session_root / "efficiency-round.json"
                if not path.exists():
                    raise ValueError("Host configuration contains no authorized efficiency round")
                record = json.loads(path.read_text())
                record["run_ids"] = sorted(set(record["run_ids"]) | self.run_ids)
                record["intervals"].extend(arguments.get("intervals", []))
                if "question_set" in arguments:
                    record["identity"]["question_set"] = arguments["question_set"]
                for key in ("counts", "completion"):
                    if key in arguments:
                        record[key] = arguments[key]
                report = summarize_round(record, observed_at=datetime.now(timezone.utc).isoformat())
                self._append("efficiency-progress.jsonl", dict(arguments))
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                temporary.replace(path)
                return {"ok": True, "data": report}
            if name == "emit_user_message":
                message = dict(arguments)
                if self.conversation:
                    published = self.conversation.publish(message, call_identity)
                    self.messages.append(published)
                    return {"ok": True, "data": {"message_id": published["message_id"]}}
                self.messages.append(message)
                self._append("public-messages.jsonl", message)
                return {"ok": True}
            if name == "read_delivery_artifact":
                return {"ok": True, "data": self._read_artifact(arguments["path"])}
            if name == "finish_delivery":
                self.work_result = arguments["conclusion"]
                results = {}
                for run_id in sorted(self.run_ids):
                    results[run_id] = self.call_tool("standby_run", {"run_id": run_id})
                observation = self.observe()
                runs_closed = all(x["status"].get("ok") and x["status"].get("data", {}).get("recorded_state", {}).get("lifecycle") == "standby"
                                  for x in observation["runs"].values())
                pending_owners = []
                for operation_id, status in observation["operations"].items():
                    data = status.get("data", {})
                    closed = data.get("work_state") == "completed" or (
                        data.get("status") in {"exited", "stopped", "failed"}
                        and isinstance(data.get("exit_code"), int))
                    if not status.get("ok") or not closed:
                        pending_owners.append(operation_id)
                for operation_id, status in observation["repair_verifications"].items():
                    if not status.get("ok") or status.get("data", {}).get("process", {}).get("state") != "exited":
                        pending_owners.append(operation_id)
                self.activity = "standby" if runs_closed and not pending_owners else "read_only_wait"
                self._save(self.activity, conclusion=self.work_result)
                return {"ok": True, "data": {"activity": self.activity, "runs": results,
                    "pending_owners": pending_owners,
                    "note": "Work result recorded; original Team retained until explicit stop. This is not semantic PASS."}}
            if name == "record_flow_confirmation":
                if not self.conversation:
                    raise ValueError("unified conversation has not been enabled")
                original = self.conversation.receipt(arguments["message_id"])
                if not original or original.get("action") != arguments["action"]:
                    raise ValueError("confirmation must bind the actual control message")
                if arguments["status"] == "effective" and not arguments["evidence_references"]:
                    raise ValueError("effective requires actual Agent acknowledgement references")
                self.conversation.append("control_result", message_id=arguments["message_id"],
                    action=arguments["action"], status=arguments["status"],
                    basis={"evidence_references": arguments["evidence_references"],
                           "limitations": arguments.get("limitations")})
                if arguments["status"] == "effective":
                    self.activity = "paused" if arguments["action"] == "pause" else "active"
                self._save("active")
                return {"ok": True}
            if name == "prepare_repair_task":
                if "repair" not in self.allowed_operations:
                    raise ValueError("repair is outside the recorded authorization")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", arguments["operation_id"]):
                    raise ValueError("invalid repair operation ID")
                public_refs = set(self.config.get("public_repair_references", []))
                public_refs.update(str(x) for x in self.sources)
                public_refs.update(self.config.get("allowed_sources", []))
                if not arguments["source_references"] or not set(arguments["source_references"]) <= public_refs:
                    raise ValueError("repair requires approved public evidence references")
                scope = {self._path(x) for x in self.config.get("repair_owned_paths", [])}
                owned = {self._path(x) for x in arguments["owned_paths"]}
                if not owned or not all(any(path == base or path.is_relative_to(base) for base in scope) for path in owned):
                    raise ValueError("repair files are outside the selected scope")
                directory = self.session_root / "repair-tasks"
                directory.mkdir(exist_ok=True)
                path = directory / (arguments["operation_id"] + ".md")
                task = ("Authorized bounded repair. You are not alone in this checkout; preserve others' edits.\n"
                        "Use only these public references; no hidden CQ or answer evidence.\n"
                        + json.dumps({"authorization_reference": self.authorization,
                                      "source_references": arguments["source_references"],
                                      "owned_paths": arguments["owned_paths"]}, ensure_ascii=False)
                        + "\n" + arguments["text"])
                with path.open("x") as handle:
                    handle.write(task)
                self.repair_task_files.add(path)
                self._save("active")
                return {"ok": True, "data": {"repair_task_file": str(path)}}
            if name in {"verify_repair", "get_repair_verification_status"}:
                operation_id = arguments['operation_id']
                if self.operation_kinds.get(operation_id) != 'repair':
                    raise ValueError('repair operation is outside this Delivery session')
                if name == 'verify_repair':
                    if 'repair' not in self.allowed_operations:
                        raise ValueError('repair verification is outside the recorded authorization')
                    allow_deployment = self.config.get('repair', {}).get('allow_deployment') is True
                    repair = host_ops_mcp.get_repair_status(operation_id=operation_id, repository_root=self.repository_root)
                    paths = repair['request_binding']['owned_paths']
                    deploy_needed = any(path.startswith(('backend/', 'frontend/')) or path == 'scripts/start-local.sh' for path in paths)
                    scopes = []
                    if allow_deployment and deploy_needed:
                        for run_id in sorted(self.run_ids):
                            root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
                            state = json.loads((root / 'state.json').read_text())
                            scope = state.get('platform_binding') or self.config.get('readback_scope')
                            if not scope:
                                raise ValueError('read the bound scope before reconciling write state')
                            bound = {'run_id': run_id, 'project_id': scope['project_id'], 'ontology_ids': scope['ontology_ids']}
                            proof = self.call_tool('reconcile_write_state', bound)
                            if not proof.get('ok') or run_id not in self.reconciled_runs:
                                raise ValueError('current write reconciliation is blocked; keep the original write/receipt evidence')
                            scopes.append(bound)
                    data = start_verification(operation_id=operation_id, repository_root=self.repository_root,
                                              session_root=self.session_root, authorization_reference=self.authorization,
                                              allow_deployment=allow_deployment, reconciliation_scopes=scopes,
                                              base_url=self.config.get('base_url'))
                    self.verification_ids.add(operation_id)
                    self._save('active')
                else:
                    if operation_id not in self.verification_ids:
                        raise ValueError('verification has not been started in this session')
                    data = verification_status(operation_id=operation_id, session_root=self.session_root)
                return {'ok': True, 'data': data}
            if self._permission(name) not in self.allowed_operations:
                raise ValueError("operation is outside the recorded authorization")
            if self._permission(name) in {"production", "evaluation", "repair"} and self.authorization_valid_until:
                from datetime import datetime, UTC
                deadline = datetime.fromisoformat(self.authorization_valid_until.replace("Z", "+00:00"))
                if deadline.tzinfo is None or datetime.now(UTC) >= deadline:
                    raise ValueError("original authorization expired; no automatic renewal")
            args = dict(arguments)
            if "base_url" in inspect.signature(getattr(host_ops_mcp, name)).parameters:
                args["base_url"] = self.config.get("base_url")
            for key in ("run_id", "source_run_id", "write_tail_run_id"):
                value = args.get(key)
                if value and not (key == "run_id" and name == "start_run") and value not in self.run_ids:
                    raise ValueError("run is outside this Delivery session")
            if name in {"get_evaluation_status", "get_repair_status", "stop_delivery_operation", "relay_evaluation_message"}:
                if args["operation_id"] not in self.operation_ids:
                    raise ValueError("operation is outside this Delivery session")
            if name in _PRODUCTION:
                args["host_session_ref"] = str(self.session_root / "session.json")
                if name == "start_run":
                    for key in ("task", "profile", "scope", "model_profile", "task_overlay"):
                        if key in self.config and args.get(key, self.config[key]) != self.config[key]:
                            raise ValueError(f"{key} differs from the authorized launch configuration")
                    if args.get("task_overlay") != self.config.get("task_overlay"):
                        raise ValueError("task_overlay differs from the authorized launch configuration")
            if name == "start_evaluation" or (name == "resume_from_checkpoint" and args.get("mode") == "acceptance"):
                selected = self.config.get("evaluation_model_profile", self.config["model_profile"])
                if args.get("model_profile", selected) not in {None, selected}:
                    raise ValueError("evaluation model profile differs from the selected binding")
                args["model_profile"] = selected
            if name in {"submit_instruction", "resume_from_checkpoint", "start_repair"}:
                if args.get("authorization_reference") != self.authorization:
                    raise ValueError("authorization reference does not match this session")
            if name == 'resolve_issue' and args.get('resolution_type') == 'repair_completed':
                matching = []
                for operation_id in self.verification_ids:
                    repair = host_ops_mcp.get_repair_status(operation_id=operation_id, repository_root=self.repository_root)
                    verification = verification_status(operation_id=operation_id, session_root=self.session_root)
                    if repair['request_binding'].get('issue_id') == args['issue_id'] and (verification.get('result') or {}).get('effect_verified') is True:
                        matching.append(verification['record_path'])
                if args.get('verification_reference') not in matching:
                    raise ValueError('repair_completed requires actual current verification bound to this issue; use guidance for input correction')
            if name == "start_repair":
                if self._path(args["repair_task_file"]) not in self.repair_task_files:
                    raise ValueError("repair task file has not been approved")
                for key in ("executor", "model", "effort"):
                    if args[key] != self.config.get("repair", {}).get(key):
                        raise ValueError("repair executor/model/effort differs from the selected binding")
            if name in {"read_platform_record", "reconcile_write_state"}:
                ontologies = args.get("ontology_ids", [args.get("ontology_id")])
                if not any(args["project_id"] == scope.get("project_id") and set(ontologies) <= set(scope.get("ontology_ids", [])) for scope in self._readback_scopes()):
                    raise ValueError("platform read is outside authorized reconciliation scope")
            operation = getattr(host_ops_mcp, name)
            if name == "submit_cq_review":
                args["content_digest_value"] = args.pop("content_digest")
            args["repository_root"] = self.repository_root
            inspect.signature(operation).bind(**args)
            if name == "start_run":
                self.run_ids.add(args["run_id"])
            elif name == "resume_from_checkpoint":
                self.run_ids.add(args["new_run_id"])
            elif name in {"start_evaluation", "start_repair"}:
                self.operation_ids.add(args["operation_id"])
                self.operation_kinds[args["operation_id"]] = "repair" if name == "start_repair" else "evaluation"
            # Retain the intended binding even if launch acknowledgement is lost.
            if name not in _READ:
                self._save("active")
            data = operation(**args)
            if name == 'reconcile_write_state':
                proof = data.get('reconciliation', {})
                self.reconciled_runs.discard(args['run_id'])
                if data.get('readback_only') is True and proof.get('blocked') == [] and proof.get('scope_drift') == []:
                    self.reconciled_runs.add(args['run_id'])
            return {"ok": True, "data": data}
        except HostOpError as exc:
            return {"ok": False, "error": exc.as_envelope()}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return {"ok": False, "error": {"code": "delivery_contract", "message": str(exc)}}
        except Exception as exc:
            # Schema failures can contain the supplied instance. Keep them private.
            self._append("tool-errors.jsonl", {"tool": name, "error_type": type(exc).__name__})
            return {"ok": False, "error": {"code": "delivery_tool_failed", "message": "check tool schema and bound inputs"}}

    def observe(self) -> dict:
        return {"runs": {run_id: {
            "status": self.call_tool("get_run_status", {"run_id": run_id}),
            "pending": self.call_tool("get_pending_actions", {"run_id": run_id}),
            "request_ledger": self.call_tool("read_delivery_artifact", {
                "path": f"workspaces/modeling-runs/{run_id}/control/host-requests.jsonl",
            }),
        } for run_id in sorted(self.run_ids)}, "operations": {
            operation_id: self.call_tool("get_repair_status" if self.operation_kinds.get(operation_id) == "repair" else "get_evaluation_status", {"operation_id": operation_id})
            for operation_id in sorted(self.operation_ids)
        }, 'repair_verifications': {
            operation_id: self.call_tool('get_repair_verification_status', {'operation_id': operation_id})
            for operation_id in sorted(self.verification_ids)
        }}

    def record_observation(self, observation: dict) -> bool:
        """Persist the full observation; wake the model only for decision changes."""
        path = self.session_root / "observation.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        decision = json.dumps(_decision_observation(observation), ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(decision.encode()).hexdigest()
        changed = digest != getattr(self, "_last_decision_digest", None)
        self._last_decision_digest = digest
        record = {
            "observation_count": previous.get("observation_count", 0) + 1,
            "wake_count": previous.get("wake_count", 0) + int(changed),
            "decision_digest": digest,
            "data": observation,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False))
        temporary.replace(path)
        return changed


def _run_delivery(config: dict, *, repository_root: Path, resume: bool) -> int:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", config["session_id"]):
        raise ValueError("invalid Delivery session ID")
    session_root = repository_root / "workspaces/delivery-sessions" / config["session_id"]
    # Session IDs are local names, never user-selected path components.
    if session_root.parent != repository_root / "workspaces/delivery-sessions":
        raise ValueError("invalid Delivery session ID")
    session = DeliverySession(repository_root=repository_root, session_root=session_root, config=config, resume=resume)
    package = repository_root / "modeling_team/agent-packages/delivery"
    instructions = (package / "instructions.md").read_text()
    instructions += "\n" + (repository_root / "modeling_team/skills/delivery/SKILL.md").read_text()
    # The restricted Delivery has no shell or arbitrary repository reader.
    # Mount the timing method as instructions only when this Host configured it.
    if config.get("efficiency_round") is not None:
        instructions += "\n" + (repository_root / "modeling_team/references/efficiency-round-record.md").read_text()
    providers = None
    runtime = None
    server = None
    incoming: queue.Queue = queue.Queue()

    def read_input() -> None:
        import sys
        for line in sys.stdin:
            incoming.put(line.rstrip("\n"))
        incoming.put(None)

    try:
        base_url = None
        if uses_external_credential_session(session.binding.provider_id):
            selected = replace(session.profile, bindings={"delivery": session.binding})
            providers = ProviderSessionManager(preflight_profile_credentials(selected))
            providers.start()
            base_url = providers.base_url_for(session.binding.provider_id)
        runtime = DeliveryRuntime(
            binding=session.binding, home=session_root / "native", instructions=instructions,
            tools=session.tool_specs(), tool_handler=session.call_tool,
            service_tier=config.get("service_tier", "unset"), provider_base_url=base_url,
        )
        runtime.start()
        session.native_thread_id = runtime.thread_id
        session.native_pid = runtime.process.pid
        session._save("active", native_thread_id=runtime.thread_id,
                      native_pid=runtime.process.pid, service_tier=config.get("service_tier", "unset"))
        if session.conversation:
            server = ConversationServer(repository_root, session.conversation, incoming.put,
                lambda: {"native_available": runtime.process.poll() is None,
                         "activity": session.activity})
            server.start()
            # Only never-attempted accepted messages can be requeued on explicit Host resume.
            for message in session.conversation.snapshot()["messages"]:
                if message.get("dispatch") == "pending":
                    incoming.put({key: value for key, value in message.items() if key not in {
                        "received_seq", "recorded_at", "dispatch", "dispatch_reason", "control"}})
        threading.Thread(target=read_input, daemon=True).start()
        runtime.send(json.dumps({"kind": "delivery_resume" if resume else "delivery_start", "config": config,
                                  "observed_state": session.observe() if resume else None,
                                  "session_reference": str(session_root / "session.json")}, ensure_ascii=False))
        next_observation = 0.0
        pending_input: list[dict] = []
        pending_observation: dict | None = None
        steer_blocked_turn: str | None = None
        eof = False
        while not session.finished:
            observations = runtime.poll(0.1)
            if any(item.get("status") == "failed" for item in observations):
                raise RuntimeError("Delivery native turn failed")
            for message in session.drain_messages():
                print(message["text"], flush=True)
            while not incoming.empty():
                text = incoming.get_nowait()
                if text is None:
                    eof = True
                else:
                    if session.conversation:
                        if isinstance(text, str):
                            import uuid
                            action = {"暂停": "pause", "继续": "resume", "取消": "cancel", "撤回预算": "revoke_budget", "停止": "stop"}.get(text)
                            actor = {"kind": "test_answerer" if session.business_input_role == "test-answerer" else "user",
                                     "reference": session.session_id}
                            message = {"message_id": str(uuid.uuid4()), "kind": "control" if action else "message",
                                       "text": text, "sender": actor, "submitted_by": actor, "entrypoint": "stdin"}
                            if action:
                                message["action"] = action
                            try:
                                _, created = session.conversation.receive(message)
                            except ConversationError as exc:
                                print(f"Delivery input not accepted: {exc.code}", flush=True)
                                continue
                            if not created:
                                continue
                        else:
                            message = text
                        packet = session.sourced_packet(message)
                        control_text = {"cancel": "取消", "revoke_budget": "撤回预算", "stop": "停止"}.get(message.get("action"), "")
                    else:
                        packet = session.accept_user_input(text)
                        control_text = text
                    control = session.apply_user_control(control_text)
                    if control is not None:
                        packet["host_control_result"] = control
                        if session.conversation:
                            session.conversation.append("control_result", message_id=packet["message_id"],
                                action=message["action"], status="pending", basis="host_control_submitted")
                        runtime.interrupt()
                    pending_input.append(packet)
                    if control_text == "停止":
                        session.stop_message_id = packet.get("message_id")
            if getattr(session, "stop_pending", False):
                # Submission is not process exit. Keep the Delivery owner online until bound
                # owners have actually stopped; do not start inference while collecting exits.
                observation = session.observe()
                runs_stopped = all(
                    result.get("status", {}).get("data", {}).get("recorded_state", {}).get("state") in {"CLEANED", "STOPPED"}
                    and (result.get("status", {}).get("data", {}).get("liveness", {}).get("process_observation", {}).get("pid_alive") is False
                         or result.get("status", {}).get("data", {}).get("liveness", {}).get("process_observation", {}).get("report", {}).get("writer_process_exited") is True)
                    for result in observation.get("runs", {}).values())
                operations_stopped = all(result.get("data", {}).get("status") in {"exited", "stopped", "launch_failed"}
                                         for result in observation.get("operations", {}).values())
                verifications_stopped = all(result.get("data", {}).get("process", {}).get("state") != "running"
                                             and result.get("ok") is True
                                             for result in observation.get("repair_verifications", {}).values())
                if runs_stopped and operations_stopped and verifications_stopped:
                    session.finished = True
                    session.activity = "stopped"
                    session._save("stopped")
                    if session.conversation and getattr(session, "stop_message_id", None):
                        session.conversation.append("control_result", message_id=session.stop_message_id,
                                                    action="stop", status="effective", basis="bound_owners_exited")
                continue
            if runtime.busy and pending_input and steer_blocked_turn != runtime.turn_id:
                # An active turn must not starve later sourced input: deliver
                # the original packets promptly onto the same live thread and
                # turn through the supported turn/steer API, in queue order.
                while pending_input and runtime.busy and steer_blocked_turn != runtime.turn_id:
                    current = pending_input[0]
                    if session.conversation:
                        session.conversation.append("dispatch_started", message_id=current["message_id"],
                            dispatch_attempt_id=__import__("uuid").uuid4().hex)
                    try:
                        runtime.steer(json.dumps(current, ensure_ascii=False))
                    except DeliveryRuntimeError as exc:
                        if session.conversation:
                            rejected = exc.category == "rejected"
                            session.conversation.append("dispatch_result", message_id=current["message_id"],
                                status="rejected" if rejected else "unknown", reason="native_rejected" if rejected else "native_receipt_unknown")
                            if not rejected:
                                pending_input.pop(0)
                        # End-of-turn race: the turn completed server-side
                        # between the busy check and the steer request.  Keep
                        # the packet queued; the idle branch below delivers it
                        # with a fresh turn/start once the completion event is
                        # read, so a stale turn is never fatal or retried hot.
                        steer_blocked_turn = runtime.turn_id
                        break
                    pending_input.pop(0)
                    if session.conversation:
                        session.conversation.append("dispatch_result", message_id=current["message_id"], status="accepted_by_native")
            # Continue program observation during an active inference too. Send
            # decisions on its current turn; a heartbeat never starts a turn.
            if (runtime.busy and (session.run_ids or session.operation_ids or session.verification_ids)
                    and time.monotonic() >= next_observation):
                observation = session.observe()
                next_observation = time.monotonic() + 2
                if session.record_observation(observation):
                    pending_observation = {"kind": "host_observation", "data": observation}
            if (runtime.busy and not pending_input and pending_observation is not None
                    and steer_blocked_turn != runtime.turn_id):
                try:
                    runtime.steer(json.dumps(pending_observation, ensure_ascii=False))
                except DeliveryRuntimeError:
                    steer_blocked_turn = runtime.turn_id
                else:
                    pending_observation = None
            if not runtime.busy:
                if pending_input:
                    current = pending_input.pop(0)
                    if session.conversation:
                        session.conversation.append("dispatch_started", message_id=current["message_id"],
                            dispatch_attempt_id=__import__("uuid").uuid4().hex)
                    try:
                        runtime.send(json.dumps(current, ensure_ascii=False))
                    except DeliveryRuntimeError:
                        if session.conversation:
                            session.conversation.append("dispatch_result", message_id=current["message_id"], status="unknown", reason="native_receipt_unknown")
                        else:
                            raise
                    else:
                        if session.conversation:
                            session.conversation.append("dispatch_result", message_id=current["message_id"], status="accepted_by_native")
                    steer_blocked_turn = None
                elif pending_observation is not None:
                    runtime.send(json.dumps(pending_observation, ensure_ascii=False))
                    pending_observation = None
                    steer_blocked_turn = None
                elif time.monotonic() >= next_observation:
                    observation = session.observe()
                    next_observation = time.monotonic() + 2
                    if session.record_observation(observation):
                        runtime.send(json.dumps({"kind": "host_observation", "data": observation}, ensure_ascii=False))
                    elif eof and server is None:
                        session._save("supervision_interrupted", reason="business input closed", observation=observation)
                        return 2
        return 0
    except KeyboardInterrupt:
        session._save("supervision_interrupted", reason="operator interrupt", observation=session.observe())
        return 130
    except Exception as exc:
        session._save("supervision_interrupted", reason="Delivery runtime failure",
                      error_type=type(exc).__name__, observation=session.observe())
        raise
    finally:
        if server is not None:
            server.close()
        if runtime is not None:
            runtime.close()
            session._append("session-events.jsonl", {
                "event": "native_runtime_closed", "thread_id": runtime.thread_id,
                "pid": runtime.process.pid if runtime.process is not None else None,
                "exit_code": runtime.process.poll() if runtime.process is not None else None,
            })
        if providers is not None:
            providers.stop()


def run_delivery(config_path: Path, *, repository_root: Path, resume: bool = False) -> int:
    config = yaml.safe_load(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError("Delivery config must be a YAML object")
    session_id = config.get("session_id")
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", session_id):
        raise ValueError("invalid Delivery session ID")
    parent = repository_root / "workspaces/delivery-sessions"
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (parent / (".supervisor-" + session_id + ".lock")).open("a") as ownership:
        try:
            fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("this Delivery session already has an active supervisor") from exc
        return _run_delivery(config, repository_root=repository_root, resume=resume)
