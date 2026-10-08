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
from .runtimes.delivery import DeliveryRuntime
from .delivery_verification import start_verification, verification_status, stop_verification

_PUBLIC_KINDS = {"status", "business_question", "decision_request", "final"}
_READ = {
    "get_run_status", "get_run_events", "get_pending_actions", "get_request_result",
    "inspect_checkpoints", "get_evaluation_status", "get_repair_status",
    "read_platform_record", "reconcile_write_state",
}
_PRODUCTION = {"start_run", "resume_from_checkpoint"}
_LOCAL_SPECS = [
    {"name": "emit_user_message", "description": "Publish a business-facing message only.",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"enum": sorted(_PUBLIC_KINDS)}, "text": {"type": "string"},
         "question_delivery_id": {"type": "string"}}, "required": ["kind", "text"],
         "additionalProperties": False}},
    {"name": "read_delivery_artifact", "description": "Read approved sources or bound private run evidence.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}},
                     "required": ["path"], "additionalProperties": False}},
    {"name": "finish_delivery", "description": "End supervision after reporting final verified result and limits.",
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
]


class DeliverySession:
    def __init__(self, *, repository_root: Path, session_root: Path, config: dict,
                 resume: bool = False) -> None:
        self.repository_root = repository_root.resolve()
        self.session_root = session_root.resolve()
        self.config = copy.deepcopy(config)
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
            self.run_ids.update(previous["run_ids"])
            self.operation_ids.update(previous["operation_ids"])
            self.operation_kinds.update(previous.get("operation_kinds", {}))
            self.verification_ids.update(previous.get("verification_ids", []))
            self.repair_task_files.update(Path(x) for x in previous.get("repair_task_files", []))
            self.allowed_operations.intersection_update(previous["allowed_operations"])
        else:
            self.session_root.mkdir(parents=True, exist_ok=False, mode=0o700)
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
        self._append("user-input.jsonl", packet)
        return packet

    def apply_user_control(self, text: str) -> dict | None:
        if text not in {"暂停", "取消", "撤回预算"}:
            return None
        # Business controls prevent new launches before the native model replies.
        self.allowed_operations -= {"production", "evaluation", "repair"}
        name = "pause_run" if text == "暂停" else "stop_run"
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
        if text in {"取消", "撤回预算"}:
            for operation_id in sorted(self.verification_ids):
                results["verification:" + operation_id] = stop_verification(
                    operation_id=operation_id, session_root=self.session_root)
            for operation_id in sorted(self.operation_ids):
                try:
                    results[operation_id] = {"ok": True, "data": host_ops_mcp.stop_delivery_operation(
                        operation_id=operation_id, reason=text, repository_root=self.repository_root)}
                except HostOpError as exc:
                    results[operation_id] = {"ok": False, "error": exc.as_envelope()}
        self._save("paused" if text == "暂停" else "cancelled" if text == "取消" else "budget_revoked")
        return {"control": text, "launch_permissions_revoked": True, "results": results}

    def drain_messages(self) -> list[dict]:
        messages, self.messages = self.messages, []
        return messages

    def _read_artifact(self, value: str) -> dict:
        path = self._path(value)
        approved = path in self.sources or path in {
            self.session_root / name for name in ("session.json", "session-events.jsonl", "user-input.jsonl", "public-messages.jsonl")
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

    def call_tool(self, name: str, arguments: dict) -> dict:
        try:
            if name not in self._tools:
                raise ValueError("undeclared Delivery tool")
            validate(arguments, self._tools[name]["inputSchema"])
            if name == "emit_user_message":
                message = dict(arguments)
                self.messages.append(message)
                self._append("public-messages.jsonl", message)
                return {"ok": True}
            if name == "read_delivery_artifact":
                return {"ok": True, "data": self._read_artifact(arguments["path"])}
            if name == "finish_delivery":
                self.finished = True
                self._save("completed", conclusion=arguments["conclusion"])
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
            args = dict(arguments)
            if "base_url" in inspect.signature(getattr(host_ops_mcp, name)).parameters:
                args["base_url"] = self.config.get("base_url")
            for key in ("run_id", "source_run_id", "write_tail_run_id"):
                value = args.get(key)
                if value and not (key == "run_id" and name == "start_run") and value not in self.run_ids:
                    raise ValueError("run is outside this Delivery session")
            if name in {"get_evaluation_status", "get_repair_status", "stop_delivery_operation"}:
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
    providers = None
    runtime = None
    incoming: queue.Queue[str | None] = queue.Queue()

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
        threading.Thread(target=read_input, daemon=True).start()
        runtime.send(json.dumps({"kind": "delivery_resume" if resume else "delivery_start", "config": config,
                                  "observed_state": session.observe() if resume else None,
                                  "session_reference": str(session_root / "session.json")}, ensure_ascii=False))
        last_observation = None
        next_observation = 0.0
        pending_input: list[dict] = []
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
                    packet = session.accept_user_input(text)
                    control = session.apply_user_control(text)
                    if control is not None:
                        packet["host_control_result"] = control
                        runtime.interrupt()
                    pending_input.append(packet)
            if not runtime.busy:
                if pending_input:
                    runtime.send(json.dumps(pending_input.pop(0), ensure_ascii=False))
                elif time.monotonic() >= next_observation:
                    observation = session.observe()
                    serialized = json.dumps(observation, ensure_ascii=False, sort_keys=True)
                    next_observation = time.monotonic() + 2
                    if serialized != last_observation:
                        last_observation = serialized
                        runtime.send(json.dumps({"kind": "host_observation", "data": observation}, ensure_ascii=False))
                    elif eof:
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
