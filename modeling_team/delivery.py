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
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

from . import host_ops_mcp
from .host_ops import HostOpError, resolve_run_root
from .handoff_materials import (
    HANDOFF_TOOL_NAMES,
    HANDOFF_TOOL_SPECS,
    HandoffMaterials,
    MaterialError,
)
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
_MATERIAL_HOST_TOOLS = {"answer_question", "submit_instruction", "consult_team"}
# Evidence streams that carry an existing public Delivery/Team handoff.  A
# generic evidence directory is deliberately not a material source: CQ,
# acceptance and report streams may contain private references whose recipient
# is the Runner as an implementation detail.
_PUBLIC_RUN_EVENT_SOURCES = frozenset({
    "deliveries.jsonl", "coordination.jsonl", "coordination-phase.jsonl",
    "outer-instruction.jsonl", "outer-question.jsonl", "outer-user.jsonl",
    "terminal-result-handoff.jsonl", "settled.jsonl",
})
_PUBLIC_MATERIAL_ROLES = frozenset({"coordinator", "modeling", "protocol"})


# Pure pagination/window bookkeeping on an incremental ``get_run_events``
# page.  ``next_cursor``/``has_more``/``ordering``/``complete`` describe the
# read position, not the run; ``line_no``/``byte_offset`` locate one line
# inside one evidence file; page-level ``limitations`` only restate the
# corrupt/truncated placeholder events, which stay visible themselves.  All of
# them change with every (re)read without carrying a decision.
_DECISION_EVENT_NOISE_KEYS = frozenset({
    "next_cursor", "has_more", "ordering", "complete", "limitations",
    "line_no", "byte_offset",
})
# The raw app-server notification log replays every token/reasoning delta and
# turn-progress notification of the Team's native sessions.  It is retained as
# run evidence and inside the stored raw observation, but it is model
# activity, never a Delivery decision, so it must not wake the model and must
# not be pushed back into the model context either:
# :meth:`DeliverySession._model_observation` excludes exactly these sources
# from every payload handed to the native model.
_DECISION_EVENT_NOISE_SOURCES = frozenset({"app-server-events.jsonl"})


def _decision_events(run_id: str, events: Any, state: dict[str, dict[str, Any]]) -> Any:
    """Project one incremental events page onto cumulative decision content.

    The projected fingerprint depends on which decision events have already
    been seen, never on which page they arrived in: the empty follow-up page
    after a drained page and an at-least-once re-delivery inside a parked
    window project to the same value as the page that first carried the event.
    Failed event reads and corrupt/truncated placeholder events stay
    decisions; every excluded byte remains in the stored raw observation for
    on-demand reading, and the delivered payload excludes exactly the same
    noise sources (:meth:`DeliverySession._model_observation`).
    """
    if not isinstance(events, dict) or not isinstance(events.get("data"), dict):
        # Failure envelopes and unexpected shapes stay decisions.
        return events
    page = events["data"]
    # The raw ``events`` list is replaced by the cumulative chain below: the
    # page window itself must never re-enter the wakeup fingerprint.
    projected = {key: value for key, value in page.items()
                 if key not in _DECISION_EVENT_NOISE_KEYS and key != "events"}
    run_state = state.setdefault(run_id, {"seen": set(), "chain": ""})
    for event in page.get("events") or []:
        if isinstance(event, dict) and event.get("source") in _DECISION_EVENT_NOISE_SOURCES:
            continue
        canonical: Any = event
        identity: str | None = None
        if isinstance(event, dict):
            canonical = {key: value for key, value in event.items()
                         if key not in _DECISION_EVENT_NOISE_KEYS}
            source = event.get("source")
            if isinstance(source, str):
                offset = event.get("byte_offset")
                positioned = isinstance(offset, int) and not isinstance(offset, bool)
                identity = f"{source}:{offset if positioned else 'unpositioned'}"
        if identity is not None:
            if identity in run_state["seen"]:
                continue
            run_state["seen"].add(identity)
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
        run_state["chain"] = hashlib.sha256(
            (run_state["chain"] + "\x00" + encoded).encode("utf-8")).hexdigest()
    projected["decision_events_chain"] = run_state["chain"]
    return {**events, "data": projected}


def _decision_observation(observation: dict,
                          event_state: dict[str, dict[str, Any]]) -> dict:
    """Keep decisions and their bindings, while ignoring observation-only traffic.

    ``event_state`` is the caller's per-process cumulative seen-event state;
    it is updated in place even when the observation does not wake the model.
    Incremental events pages are reduced by :func:`_decision_events`; the
    run-status ``evidence_refs`` listing only mirrors which evidence files
    exist, which is log-growth information, not a decision.  No decision
    source is dropped: new pending questions, content versions, phase and
    terminal states, blockers, write receipts, public handoffs, request
    receipts, user messages, reports and tool failures all keep waking the
    model, and none of the excluded material is lost because the caller
    stores the full raw observation.
    """
    noise = {
        "observed_at", "events_cursor", "last_verifiable_activity",
        "heartbeat_at", "last_heartbeat_at", "heartbeat_count",
        "log_bytes", "stdout_bytes", "stderr_bytes", "log_tails",
        "stdout_tail", "stderr_tail", "staged_decision_count", "latest_staged_decision_at",
        "evidence_refs",
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
    for run_id, run in projected.get("runs", {}).items():
        status = run.get("status", {}).get("data", {})
        stage = status.get("stage")
        if isinstance(stage, dict):
            stage.pop("recorded_at", None)
            stage.pop("ordinal", None)
        if "events" in run:
            run["events"] = _decision_events(run_id, run["events"], event_state)
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
         "material_refs": {"type": "array", "items": {"type": "object"}},
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

# These tools are mounted on the Delivery runtime itself.  They deliberately
# remain separate from ``read_delivery_artifact``: the latter reads an
# already-approved host path, while these operations create and consume an
# immutable, recipient-scoped handoff package.
_LOCAL_SPECS.extend(HANDOFF_TOOL_SPECS)


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
        # ``get_run_events`` is incremental.  Keep its opaque cursor outside
        # the observation payload so the same page is not repeatedly offered
        # to the native Delivery model.  Imported run materials are cached by
        # their originating run/material/member identity and restored from a
        # small session-local ledger on resume.
        self._event_cursors: dict[str, str | None] = {}
        self._run_material_imports: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        self.repair_task_files = {self._path(x) for x in config.get("repair_task_files", [])}
        self._handoff_recipients = {
            str(item)
            for item in config.get("handoff_recipients", config.get("material_recipients", ["runner"]))
            if isinstance(item, str) and item
        }
        self._handoff_source_recipients = {
            str(alias): {str(recipient) for recipient in recipients}
            for alias, recipients in (config.get("handoff_source_recipients") or {}).items()
            if isinstance(alias, str) and isinstance(recipients, (list, set, tuple))
        }
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
            for field in ("production_start_limit", "incremental_request_id", "incremental_run_id"):
                if previous.get(field) != config.get(field):
                    raise ValueError(f"resumption cannot change original {field}")
            if previous.get("authorization_valid_until") != self.authorization_valid_until:
                raise ValueError("resumption cannot change the original authorization deadline")
            self.run_ids.update(previous["run_ids"])
            self.operation_ids.update(previous["operation_ids"])
            self.operation_kinds.update(previous.get("operation_kinds", {}))
            self.verification_ids.update(previous.get("verification_ids", []))
            self.repair_task_files.update(Path(x) for x in previous.get("repair_task_files", []))
            self._event_cursors.update(previous.get("event_cursors", {}))
            self.allowed_operations.intersection_update(previous["allowed_operations"])
            self.activity = previous.get("activity", "active")
            self.work_result = previous.get("work_result")
        else:
            self.session_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.handoff_materials = HandoffMaterials(
            self.session_root / "handoff-materials", self.session_id
        )
        # Source mappings are reconstructed from the current authorization and
        # run ids. Published packages remain immutable under this session root.
        self._register_handoff_actor()
        self._load_run_material_imports()
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
            for name in (
                "repository_root", "host_session_ref", "base_url",
                "handoff_materials", "material_actor_id", "material_recipient_id",
            ):
                properties.pop(name, None)
            schema["additionalProperties"] = False
            self._tools[tool.name] = {"name": tool.name, "description": tool.description,
                                      "inputSchema": schema}
        self._tools.update({item["name"]: copy.deepcopy(item) for item in _LOCAL_SPECS})
        self._save("ready")

    def _path(self, value: str) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else self.repository_root / path).resolve()

    def _register_handoff_actor(self) -> None:
        """Refresh the Delivery actor's currently authorized source mapping.

        A Delivery process may acquire run ids after ``start_run`` or restore
        them while resuming.  Registering the actor again adds those bounded
        run evidence roots without exposing the repository or another run's
        workspace.  The helper stores immutable packages below the session
        root; re-registration never changes an existing package's bytes.
        """

        sources: dict[str, Path] = {}
        for path in sorted(self.sources, key=str):
            sources[str(path)] = path
            try:
                relative = path.relative_to(self.repository_root)
            except ValueError:
                continue
            sources[relative.as_posix()] = path
        # Only public/run-level evidence that the Delivery reader already has
        # permission to inspect is registered here.  Private CQ/review and
        # hidden acceptance report trees are intentionally absent.
        run_relative_sources = (
            "state.json", "model-handoff.json", "baseline-manifest.json",
            "competency-questions/public",
        )
        for run_id in sorted(self.run_ids):
            try:
                root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
            except (HostOpError, OSError, ValueError):
                continue
            for relative in run_relative_sources:
                candidate = root / relative
                if candidate.is_file() or candidate.is_dir():
                    sources[str(candidate)] = candidate
        # A delivery material is consumed by the Host/Runner route.  Explicit
        # recipient configuration narrows this default; it never grants a new
        # Team Transport edge.
        self.handoff_materials.register_actor(
            "delivery", sources, self._handoff_recipients,
            self._handoff_source_recipients,
        )

    def _load_run_material_imports(self) -> None:
        """Restore the origin index for run packages already relayed here."""

        path = self.session_root / "handoff-material-origins.jsonl"
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                record = json.loads(line)
                key = record.get("cache_key")
                if (
                    isinstance(key, list)
                    and len(key) == 3
                    and isinstance(key[0], str)
                    and isinstance(key[1], str)
                    and (key[2] is None or isinstance(key[2], str))
                ):
                    self._run_material_imports[(key[0], key[1], key[2])] = record
            except (TypeError, ValueError):
                # The immutable package remains readable even if this
                # advisory index has a corrupt line; a new observation can
                # re-establish the origin record.
                continue

    def _record_run_material_import(self, key: tuple[str, str, str | None], record: dict) -> None:
        """Persist only non-secret origin/binding metadata for one relay."""

        self._run_material_imports[key] = record
        payload = {"cache_key": list(key), **record}
        try:
            with (self.session_root / "handoff-material-origins.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            # Material publication is already immutable and complete.  A
            # failure to append this local provenance index must not replace a
            # valid handoff with a different package or expose a host path.
            return

    def _material_tool(self, name: str, arguments: dict) -> dict:
        try:
            return {"ok": True, "data": self.handoff_materials.call("delivery", name, arguments)}
        except MaterialError as exc:
            return {"ok": False, "error": {
                "code": exc.code, "message": str(exc),
                **({"retry": exc.data["retry"]} if isinstance(exc.data, dict) and exc.data.get("retry") else {}),
            }}

    def _target_handoff_store(self, run_id: str) -> HandoffMaterials:
        """Open the bounded handoff store belonging to one authorized run."""

        return self._run_handoff_store(run_id)

    def _run_handoff_store(self, run_id: str) -> HandoffMaterials:
        """Open a run store with the recorded role/source grants.

        A result reference may have been published by a production Agent and
        later relayed by the Runner.  Re-registering the recorded actors here
        lets the helper re-check the original publisher, source alias and
        recipient grant before Delivery copies bytes into its session store.
        It does not add a Team edge or mount a role workspace into Delivery.
        """

        try:
            run_root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
        except (HostOpError, OSError, ValueError) as exc:
            raise MaterialError("material_source_unavailable", "bound run is unavailable") from exc
        store = HandoffMaterials(run_root / "handoff-materials", run_id)
        try:
            profile = yaml.safe_load((run_root / "profile.snapshot.yaml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise MaterialError("material_source_unavailable", "run role bindings are unavailable") from exc
        if not isinstance(profile, dict) or not isinstance(profile.get("agents"), list):
            raise MaterialError("material_binding_changed", "run role bindings are invalid")

        agents = [agent for agent in profile["agents"] if isinstance(agent, dict)]
        agent_ids = {
            str(agent["agent_id"])
            for agent in agents
            if isinstance(agent.get("agent_id"), str) and agent["agent_id"]
        }
        role_by_agent = {
            str(agent["agent_id"]): str(agent.get("package") or "")
            for agent in agents
            if isinstance(agent.get("agent_id"), str) and agent["agent_id"]
        }
        communication = profile.get("communication") or []
        edges: dict[str, set[str]] = {agent_id: set() for agent_id in agent_ids}
        for rule in communication:
            if not isinstance(rule, dict) or not isinstance(rule.get("from"), str):
                continue
            targets = rule.get("to")
            if isinstance(targets, str):
                targets = [targets]
            if isinstance(targets, list):
                edges.setdefault(rule["from"], set()).update(
                    target for target in targets if isinstance(target, str)
                )

        task: dict[str, Any] = {}
        try:
            loaded_task = yaml.safe_load((run_root / "task.snapshot.yaml").read_text(encoding="utf-8"))
            if isinstance(loaded_task, dict):
                task = loaded_task
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            # A handoff published solely from an output directory does not
            # need the task snapshot.  Source-role aliases below do.
            task = {}
        role_sources = task.get("role_sources") if isinstance(task.get("role_sources"), list) else []
        schema_version = task.get("schema_version")
        allowed_sources = task.get("allowed_sources") if isinstance(task.get("allowed_sources"), list) else []

        for agent_id, role in role_by_agent.items():
            recipients = set(edges.get(agent_id, set()))
            # Runner is the existing host route. CQ has no production Team
            # edge and acceptance/private reports stay on their own sink.
            recipients.add("runner")
            if role == "competency-question":
                recipients = {"runner"}
            sources: dict[str, Path] = {}
            filters: dict[str, set[str]] = {}
            work = run_root / "runtime" / agent_id / "work"
            if role not in {"competency-question", "acceptance"}:
                sources["/agent/work"] = work
                sources[str(work)] = work
            for source in role_sources:
                if not isinstance(source, dict) or role not in (source.get("roles") or []):
                    continue
                relative = source.get("path")
                if not isinstance(relative, str) or not relative:
                    continue
                target = run_root / "sources" / role / relative
                alias = "/agent/home/sources/" + relative
                sources[alias] = target
                filters[alias] = {
                    other_id
                    for other_id, other_role in role_by_agent.items()
                    if other_role in (source.get("roles") or [])
                } | {"runner"}
            if schema_version == 1:
                for source in allowed_sources:
                    if isinstance(source, str):
                        sources["/agent/home/sources/" + Path(source).name] = run_root / "sources" / Path(source).name
            # Public projection roots are runner-readable and appear in
            # manifests created by the staged handoff paths.
            for relative in ("competency-questions/public", "value-semantics", "stage3-neutral-graph"):
                target = run_root / relative
                if target.exists() and role in _PUBLIC_MATERIAL_ROLES:
                    alias = "/agent/work/" + relative
                    sources[alias] = target
                    sources[str(target)] = target
            store.register_actor(agent_id, sources, recipients, filters)
        store.register_actor("runner", {}, agent_ids)
        return store

    def _run_agent_ids(self, run_id: str) -> set[str]:
        """Read only the role identities needed for a run-bound relay."""

        try:
            run_root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
            profile = yaml.safe_load((run_root / "profile.snapshot.yaml").read_text(encoding="utf-8"))
        except (HostOpError, OSError, UnicodeDecodeError, yaml.YAMLError):
            return set()
        agents = profile.get("agents") if isinstance(profile, dict) else None
        return {
            str(agent.get("agent_id"))
            for agent in agents or []
            if isinstance(agent, dict) and isinstance(agent.get("agent_id"), str)
            and agent.get("agent_id")
        }

    def _run_material_recipient(self, run_id: str, name: str, arguments: dict) -> str:
        """Resolve the existing downstream role for an outer Host action."""

        agents: list[dict] = []
        try:
            run_root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
            profile = yaml.safe_load((run_root / "profile.snapshot.yaml").read_text(encoding="utf-8"))
            agents = profile.get("agents") if isinstance(profile, dict) else []
        except (HostOpError, OSError, UnicodeDecodeError, yaml.YAMLError):
            pass
        role = "coordinator"
        if name == "answer_question":
            role = (
                "competency-question"
                if arguments.get("channel") == "cq_interview"
                else "modeling"
            )
        for agent in agents or []:
            if isinstance(agent, dict) and agent.get("package") == role:
                if isinstance(agent.get("agent_id"), str) and agent["agent_id"]:
                    return agent["agent_id"]
        return role

    def _run_material_roles(self, run_id: str) -> dict[str, str]:
        """Return the recorded agent-id → package-role binding for one run."""

        repository_root = getattr(self, "repository_root", None)
        if repository_root is None:
            return {}
        try:
            run_root, _ = resolve_run_root(run_id, repository_root=repository_root)
            profile = yaml.safe_load((run_root / "profile.snapshot.yaml").read_text(encoding="utf-8"))
        except (HostOpError, OSError, UnicodeDecodeError, yaml.YAMLError):
            return {}
        agents = profile.get("agents") if isinstance(profile, dict) else []
        return {
            str(agent["agent_id"]): str(agent.get("package") or "")
            for agent in agents or []
            if isinstance(agent, dict)
            and isinstance(agent.get("agent_id"), str)
            and agent.get("agent_id")
        }

    def _public_material_recipient(self, run_id: str, recipient_id: str) -> bool:
        """Check the current production/public recipient grant.

        A material published to the Runner is eligible only when its event is
        itself a public production handoff; CQ, acceptance and report role ids
        stay excluded from this observation surface.
        """

        if recipient_id == "runner":
            return True
        return self._run_material_roles(run_id).get(recipient_id) in _PUBLIC_MATERIAL_ROLES

    @staticmethod
    def _is_private_cq_source(manifest: dict[str, Any]) -> bool:
        """Recognize only the existing CQ private/review source roots."""

        for field in ("source_alias", "source_path"):
            value = manifest.get(field)
            if not isinstance(value, str):
                continue
            parts = [part for part in value.replace("\\", "/").split("/") if part]
            if any(
                parts[index:index + 2] in (["competency-questions", "private"],
                                            ["competency-questions", "reviews"])
                for index in range(len(parts) - 1)
            ):
                return True
        return False

    def _is_private_cq_material(self, ref: dict) -> bool:
        """Retain CQ privacy after a Host relay replaces the source alias."""

        manifest, _digest = self.handoff_materials._manifest("delivery", ref["material_id"])
        if self._is_private_cq_source(manifest):
            return True
        for record in getattr(self, "_run_material_imports", {}).values():
            target = record.get("target_ref")
            if not isinstance(target, dict) or target.get("material_id") != ref.get("material_id"):
                continue
            binding = record.get("origin_binding")
            origin_run_id = record.get("origin_run_id")
            if not isinstance(binding, dict) or not isinstance(origin_run_id, str):
                continue
            publisher_id = binding.get("publisher_id")
            recipient_id = binding.get("recipient_id")
            if (
                isinstance(publisher_id, str)
                and recipient_id == "runner"
                and self._run_material_roles(origin_run_id).get(publisher_id)
                == "competency-question"
            ):
                return True
        return False

    def _assert_material_route(self, run_id: str, ref: dict, recipient_id: str) -> None:
        """Keep original private CQ bindings on the existing CQ route."""

        if not self._is_private_cq_material(ref):
            return
        role = self._run_material_roles(run_id).get(recipient_id)
        if role != "competency-question":
            raise MaterialError(
                "material_forbidden",
                "private CQ material is restricted to the existing CQ review channel",
            )

    @staticmethod
    def _event_source_public(source: Any) -> bool:
        return isinstance(source, str) and source in _PUBLIC_RUN_EVENT_SOURCES

    def _import_run_material_ref(
        self,
        run_id: str,
        ref: dict,
        *,
        source: str,
        origin_agent_id: str | None = None,
    ) -> tuple[dict, dict]:
        """Relay one public run reference into the Delivery session store.

        The run material remains immutable and its original manifest is read
        with the publisher's current role/source binding.  Delivery receives a
        session-scoped reference whose provenance points back to the run; a
        raw run reference is never exposed to the native model.
        """

        if not self._event_source_public(source):
            raise MaterialError("material_forbidden", "event is not a public handoff source")
        if not isinstance(ref, dict) or not isinstance(ref.get("material_id"), str):
            raise MaterialError("material_path_invalid", "material reference is invalid")
        path = ref.get("path")
        if path is not None and not isinstance(path, str):
            raise MaterialError("material_path_invalid", "material member path is invalid")
        origin_store = self._run_handoff_store(run_id)
        # The manifest is the authority for publisher/recipient.  Inspect it
        # through the helper so scope, digest and source grants are checked
        # before any byte is copied.
        try:
            # The original recipient may be a production Agent rather than
            # Runner.  Find the manifest through one of the recorded actors;
            # every candidate still goes through HandoffMaterials' scope,
            # digest and source-grant checks.
            raw_manifest: dict[str, Any] | None = None
            digest: str | None = None
            candidates = ["runner", *self._run_material_roles(run_id).keys()]
            for actor_id in dict.fromkeys(candidates):
                try:
                    raw_manifest, digest = origin_store._manifest(actor_id, ref["material_id"])
                    break
                except MaterialError:
                    continue
            if raw_manifest is None or digest is None:
                raise MaterialError("material_forbidden", "material has no current run binding")
            publisher_id = raw_manifest.get("publisher_id")
            recipient_id = raw_manifest.get("recipient_id")
            if not isinstance(publisher_id, str) or not isinstance(recipient_id, str):
                raise MaterialError("material_binding_changed", "material binding is incomplete")
            # Ensure the actor named by the immutable manifest is the one that
            # passed the previous lookup.  This prevents a host-only recipient
            # lookup from becoming a propagation grant.
            raw_manifest, digest = origin_store._manifest(publisher_id, ref["material_id"])
            if not self._public_material_recipient(run_id, recipient_id):
                raise MaterialError("material_forbidden", "material recipient is not public in this run")
            if origin_agent_id:
                role = self._run_material_roles(run_id).get(origin_agent_id)
                if role and role not in _PUBLIC_MATERIAL_ROLES and origin_agent_id != "runner":
                    raise MaterialError("material_forbidden", "material publisher is private in this run")
            # Resolve the selected member while the original binding is still
            # active.  Auxiliary directory refs are relayed as the complete
            # immutable package; validate every member before copying it.
            if path is not None:
                origin_store._bytes(publisher_id, ref["material_id"], path)
            else:
                for entry in raw_manifest.get("entries") or []:
                    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                        raise MaterialError("material_digest_mismatch", "material entry is invalid")
                    origin_store._bytes(publisher_id, ref["material_id"], entry["path"])
        except MaterialError:
            raise
        except (KeyError, TypeError, OSError) as exc:
            raise MaterialError("material_source_unavailable", "run material cannot be read") from exc

        key = (run_id, ref["material_id"], path)
        cached = self._run_material_imports.get(key)
        if cached:
            target_ref = cached.get("target_ref")
            if isinstance(target_ref, dict) and isinstance(target_ref.get("material_id"), str):
                return dict(target_ref), dict(cached)
        try:
            target_ref = self.handoff_materials.relay_ref(
                "delivery", "runner", ref,
                origin_store=origin_store,
                origin_actor_id=publisher_id,
            )
        except MaterialError:
            raise
        except (KeyError, TypeError, OSError) as exc:
            raise MaterialError("material_source_unavailable", "run material relay failed") from exc
        origin = {
            "origin_run_id": run_id,
            "origin_scope_id": run_id,
            "origin_material_id": ref["material_id"],
            **({"origin_path": path} if path is not None else {}),
            "origin_manifest_digest": digest,
            "origin_binding": {
                "publisher_id": raw_manifest.get("publisher_id"),
                "recipient_id": raw_manifest.get("recipient_id"),
                "source_alias": raw_manifest.get("source_alias"),
            },
            "source_event": source,
            "target_ref": target_ref,
        }
        self._record_run_material_import(key, origin)
        return dict(target_ref), origin

    @staticmethod
    def _strip_material_fields(value: Any) -> Any:
        """Remove raw refs from an event that is outside the public surface."""

        if isinstance(value, dict):
            return {
                key: DeliverySession._strip_material_fields(item)
                for key, item in value.items()
                if key not in {"body_ref", "material_refs", "material_origins"}
            }
        if isinstance(value, list):
            return [DeliverySession._strip_material_fields(item) for item in value]
        return value

    def _rewrite_event_materials(
        self,
        run_id: str,
        value: Any,
        *,
        source: str,
        origin_agent_id: str | None = None,
        role_by_agent: dict[str, str] | None = None,
    ) -> tuple[Any, list[dict], bool]:
        """Translate public event refs and omit unusable/private raw refs."""

        if not self._event_source_public(source):
            return self._strip_material_fields(value), [], False
        if isinstance(value, list):
            output, origins, had_failure = [], [], False
            for item in value:
                rewritten, nested, failed = self._rewrite_event_materials(
                    run_id, item, source=source, origin_agent_id=origin_agent_id,
                    role_by_agent=role_by_agent,
                )
                output.append(rewritten)
                origins.extend(nested)
                had_failure = had_failure or failed
            return output, origins, had_failure
        if not isinstance(value, dict):
            return value, [], False

        inherited_agent = origin_agent_id
        for field in ("source_id", "agent_id", "publisher_id"):
            candidate = value.get(field)
            if isinstance(candidate, str):
                inherited_agent = candidate
                break
        output: dict[str, Any] = {}
        origins: list[dict] = []
        had_failure = False
        for key, item in value.items():
            if key == "body_ref":
                if not isinstance(item, dict):
                    had_failure = True
                    continue
                try:
                    translated, origin = self._import_run_material_ref(
                        run_id, item, source=source, origin_agent_id=inherited_agent
                    )
                except MaterialError:
                    had_failure = True
                    continue
                output[key] = translated
                origins.append({"role": "body", **origin})
                continue
            if key == "material_refs":
                if not isinstance(item, list):
                    had_failure = True
                    continue
                translated_refs: list[dict] = []
                for ref in item:
                    if not isinstance(ref, dict):
                        had_failure = True
                        continue
                    try:
                        translated, origin = self._import_run_material_ref(
                            run_id, ref, source=source, origin_agent_id=inherited_agent
                        )
                    except MaterialError:
                        had_failure = True
                        continue
                    translated_refs.append(translated)
                    origins.append({"role": "auxiliary", **origin})
                if translated_refs:
                    output[key] = translated_refs
                continue
            if key == "material_origins":
                # Never pass origin metadata containing raw run references
                # through.  The translated entries below are authoritative.
                continue
            child_agent = inherited_agent
            if isinstance(item, dict) and key in (role_by_agent or {}):
                # ``settled.results`` is keyed by agent id rather than carrying
                # an ``agent_id`` field inside every result object.
                child_agent = key
            nested, nested_origins, nested_failed = self._rewrite_event_materials(
                run_id, item, source=source, origin_agent_id=child_agent,
                role_by_agent=role_by_agent,
            )
            output[key] = nested
            origins.extend(nested_origins)
            had_failure = had_failure or nested_failed
        if origins:
            output["material_origins"] = origins
        return output, origins, had_failure

    def _project_run_events(self, run_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Expose only session-readable refs in a Host event page."""

        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            return data
        projected = dict(data)
        events: list[Any] = []
        omitted = False
        role_by_agent = self._run_material_roles(run_id)
        for event in data["events"]:
            if not isinstance(event, dict):
                events.append(event)
                continue
            source = event.get("source")
            if not self._event_source_public(source):
                events.append(self._strip_material_fields(event))
                continue
            item, _origins, failed = self._rewrite_event_materials(
                run_id, event.get("data"), source=source, role_by_agent=role_by_agent
            )
            copied = dict(event)
            copied["data"] = item
            events.append(copied)
            omitted = omitted or failed
        projected["events"] = events
        if omitted:
            limitations = list(projected.get("limitations") or [])
            limitations.append("one or more event material references were omitted because their current public binding could not be verified")
            projected["limitations"] = sorted(set(limitations))
        return projected

    def _observe_run_events(self, run_id: str) -> dict:
        result = self.call_tool(
            "get_run_events",
            {"run_id": run_id, "cursor": self._event_cursors.get(run_id), "limit": 200},
        )
        if result.get("ok"):
            data = result.get("data") or {}
            cursor = data.get("next_cursor")
            if isinstance(cursor, str) and cursor != self._event_cursors.get(run_id):
                self._event_cursors[run_id] = cursor
                self._save("active")
        return result

    def _copy_material_to_run(
        self, run_id: str, ref: dict, target: HandoffMaterials, *, full_package: bool,
        recipient_id: str,
    ) -> tuple[dict, dict]:
        """Copy an authorized session package into the bound run by bytes.

        A session-local material id is deliberately never sent to a Runner:
        the Runner reads the run-owned immutable snapshot.  The returned
        second value records the original reference for audit/attribution.
        """

        try:
            listing = self.handoff_materials.list("delivery", ref["material_id"], max_entries=100)
            entries = list(listing.get("entries") or [])
            cursor = listing.get("next_cursor")
            while cursor:
                page = self.handoff_materials.list(
                    "delivery", ref["material_id"], cursor=cursor, max_entries=100
                )
                entries.extend(page.get("entries") or [])
                cursor = page.get("next_cursor")
            selected_path = ref.get("path")
            if listing.get("kind") == "file":
                if (
                    selected_path is not None
                    and entries
                    and selected_path != entries[0].get("path")
                ):
                    raise MaterialError("material_member_missing", "path is not a published member")
                selected_path = entries[0]["path"] if entries else None
            elif not full_package:
                if not isinstance(selected_path, str) or not selected_path:
                    raise MaterialError("material_member_required", "select a published member")
                if not any(item.get("path") == selected_path for item in entries):
                    raise MaterialError("material_member_missing", "path is not a published member")
            if not full_package and selected_path is not None:
                # Resolve once before relay so a deleted/corrupt member is a
                # typed source error, while relay still copies every byte of a
                # directory package for the auxiliary-ref case.
                self.handoff_materials.resolve(
                    "delivery", {"material_id": ref["material_id"], "path": selected_path}
                )
            if not full_package and listing.get("kind") == "directory":
                # A directory body reference names exactly one formal member;
                # do not expose the other selected members merely because the
                # original auxiliary package happened to contain them.
                assert isinstance(selected_path, str)
                content = self.handoff_materials.resolve(
                    "delivery", {"material_id": ref["material_id"], "path": selected_path}
                )
                relay_dir = f"relay-{uuid.uuid4().hex}"
                target.write_output("runner", f"{relay_dir}/{selected_path}", content)
                published = target.publish(
                    "runner", recipient_id,
                    f"/agent/handoff-output/{relay_dir}/{selected_path}",
                )
                # The selected member is republished as a single target file.
                # Its package-relative path is therefore the target file's
                # basename, rather than the source directory path.  Preserve
                # a resolvable ref for the Runner instead of copying a stale
                # source ``path`` into the new package.
                translated = {"material_id": published["material_id"]}
                entries = published.get("entries") or []
                if entries and isinstance(entries[0].get("path"), str):
                    translated["path"] = entries[0]["path"]
            else:
                translated = target.relay_ref(
                    "runner", recipient_id, ref,
                    origin_store=self.handoff_materials,
                    origin_actor_id="delivery",
                )
            origin = {
                "material_id": ref.get("material_id"),
                **({"path": ref["path"]} if ref.get("path") is not None else {}),
                "manifest_digest": listing.get("manifest_digest"),
                "source_binding": dict(listing.get("binding") or {}),
                "run_id": run_id,
                "recipient_id": recipient_id,
            }
            return translated, origin
        except MaterialError:
            raise
        except (KeyError, TypeError, OSError) as exc:
            raise MaterialError("material_source_unavailable", "material package cannot be transferred") from exc

    def _resolve_material_submission(self, name: str, arguments: dict) -> dict:
        """Resolve a formal body reference before writing the Host FIFO.

        ``text`` remains the complete formal content consumed by the existing
        Runner validators.  ``display_text`` is a separate short explanation
        for the runtime/UI and is never concatenated into that content.
        Auxiliary ``material_refs`` retain their identities but do not become
        formal content automatically.
        """

        resolved = dict(arguments)
        run_id = resolved.get("run_id")
        if not isinstance(run_id, str) or run_id not in self.run_ids:
            raise ValueError("run is outside this Delivery session")
        if resolved.get("body_ref") is None and not resolved.get("material_refs"):
            return resolved
        target = self._target_handoff_store(run_id)
        target_recipient = self._run_material_recipient(run_id, name, resolved)
        origins: list[dict] = []
        body_ref = resolved.get("body_ref")
        if body_ref is not None:
            try:
                self.handoff_materials.authorize_ref("delivery", "runner", body_ref)
                self._assert_material_route(run_id, body_ref, target_recipient)
                translated, origin = self._copy_material_to_run(
                    run_id, body_ref, target, full_package=False,
                    recipient_id=target_recipient,
                )
                full_text = self.handoff_materials.resolve("delivery", body_ref)
            except MaterialError:
                raise
            display = resolved.get("text")
            resolved["text"] = full_text
            resolved["display_text"] = display or (
                f"Formal content is in handoff material {translated.get('material_id')}"
            )
            resolved["body_ref"] = translated
            origins.append({"role": "body", "from": origin, "to": translated})
        translated_aux: list[dict] = []
        for ref in resolved.get("material_refs") or []:
            try:
                self.handoff_materials.authorize_ref("delivery", "runner", ref)
                self._assert_material_route(run_id, ref, target_recipient)
                translated, origin = self._copy_material_to_run(
                    run_id, ref, target, full_package=True,
                    recipient_id=target_recipient,
                )
            except MaterialError:
                raise
            translated_aux.append(translated)
            origins.append({"role": "auxiliary", "from": origin, "to": translated})
        if translated_aux:
            resolved["material_refs"] = translated_aux
        if origins:
            resolved["material_origins"] = origins
        # The op-layer receives the target run store in-process and preserves
        # the formal content/attribution separately from the display hint.
        resolved["handoff_materials"] = target
        resolved["material_actor_id"] = "runner"
        resolved["material_recipient_id"] = target_recipient
        return resolved

    def _save(self, state: str, **extra: Any) -> None:
        record = {"schema_version": 1, "session_id": self.session_id,
                  "project_id": self.project_id, "activity": self.activity,
                  "work_result": self.work_result,
                  "authorization_valid_until": self.authorization_valid_until,
                  **{field: self.config.get(field) for field in
                     ("production_start_limit", "incremental_request_id", "incremental_run_id")},
                  "authorization_reference": self.authorization, "state": state,
                  "run_ids": sorted(self.run_ids), "operation_ids": sorted(self.operation_ids),
                  "operation_kinds": self.operation_kinds,
                  "verification_ids": sorted(self.verification_ids),
                  "event_cursors": self._event_cursors,
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
                        "early-feedback",
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
            if name in HANDOFF_TOOL_NAMES:
                return self._material_tool(name, arguments)
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
                material_refs = arguments.get("material_refs") or []
                if material_refs:
                    try:
                        for ref in material_refs:
                            self.handoff_materials.authorize_ref("delivery", "runner", ref)
                            if self._is_private_cq_material(ref):
                                raise MaterialError(
                                    "material_forbidden",
                                    "private CQ material is not an approved repair reference",
                                )
                    except MaterialError as exc:
                        raise ValueError(f"{exc.code}: {exc}") from exc
                    public_refs.update(
                        f"material:{ref.get('material_id')}"
                        for ref in material_refs if isinstance(ref, dict)
                    )
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
            if name in _MATERIAL_HOST_TOOLS:
                try:
                    args = self._resolve_material_submission(name, args)
                except MaterialError as exc:
                    return {"ok": False, "error": {
                        "code": exc.code, "message": str(exc),
                        **({"retry": exc.data["retry"]} if isinstance(exc.data, dict) and exc.data.get("retry") else {}),
                    }}
            if name in {"get_evaluation_status", "get_repair_status", "stop_delivery_operation", "relay_evaluation_message"}:
                if args["operation_id"] not in self.operation_ids:
                    raise ValueError("operation is outside this Delivery session")
            if name in _PRODUCTION:
                args["host_session_ref"] = str(self.session_root / "session.json")
                if name == "start_run":
                    if self.config.get("incremental_request_id"):
                        if args.get("run_id") != self.config["incremental_run_id"]:
                            raise ValueError("incremental launch must retain its original run_id")
                        if args.get("request_id") != self.config["incremental_request_id"]:
                            raise ValueError("incremental launch must retain its original request_id")
                    limit = self.config.get("production_start_limit")
                    if limit is not None and args.get("run_id") not in self.run_ids and len(self.run_ids) >= limit:
                        raise ValueError("authorized production start limit exhausted")
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
            if name == "start_run" and args.get("run_id") in self.run_ids:
                from .host_ops import read_launch_record
                launch = read_launch_record(args["run_id"], repository_root=self.repository_root)
                if launch is not None:
                    if launch.get("request_id") != args.get("request_id"):
                        raise ValueError("launch request identity differs from the retained request")
                    return {"ok": True, "data": {"launch": launch, "run_id": args["run_id"],
                            "status": "existing_launch", "note": "observe this launch; do not replay"}}
                raise ValueError("start result is unknown; reconcile the original run before retry")
            operation = getattr(host_ops_mcp, name)
            if name == "submit_cq_review":
                args["content_digest_value"] = args.pop("content_digest")
            args["repository_root"] = self.repository_root
            inspect.signature(operation).bind(**args)
            if name == "start_run":
                self.run_ids.add(args["run_id"])
                self._register_handoff_actor()
            elif name == "resume_from_checkpoint":
                self.run_ids.add(args["new_run_id"])
                self._register_handoff_actor()
            elif name in {"start_evaluation", "start_repair"}:
                self.operation_ids.add(args["operation_id"])
                self.operation_kinds[args["operation_id"]] = "repair" if name == "start_repair" else "evaluation"
            # Retain the intended binding even if launch acknowledgement is lost.
            if name not in _READ:
                self._save("active")
            data = operation(**args)
            if name == "get_run_events" and isinstance(data, dict):
                data = self._project_run_events(args["run_id"], data)
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
            "events": self._observe_run_events(run_id),
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
        """Persist the full observation; wake the model only for decision changes.

        The wakeup fingerprint is computed from
        :func:`_decision_observation`, which folds each run's incremental
        events page into a per-process cumulative chain of seen decision
        events.  The full raw observation is still persisted below; a wakeup
        delivers its :meth:`_model_observation` view, which leaves out only
        the pure noise-source records and points at this stored artifact.
        """
        path = self.session_root / "observation.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        event_state = getattr(self, "_decision_event_state", None)
        if event_state is None:
            # Per-process like ``_last_decision_digest``: on resume the first
            # page re-folds its decision events once, matching the resumed
            # context rebuild; nothing is persisted beyond the raw
            # observation and the existing event cursors.
            event_state = {}
            self._decision_event_state = event_state
        decision = json.dumps(
            _decision_observation(observation, event_state), ensure_ascii=False, sort_keys=True)
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

    def _model_observation(self, observation: Any) -> Any:
        """Project the observation handed to the native model.

        All three delivery paths — the initial resume ``observed_state``, a
        busy-turn steer and an idle send — use this one view: records whose
        source is in ``_DECISION_EVENT_NOISE_SOURCES`` are dropped from each
        run's incremental events page, because the raw app-server log is
        native model activity, never a Delivery decision.  Everything else
        passes through complete and unmodified — status, pending questions,
        blockers, write and request receipts, reports, public handoffs,
        failed tool envelopes and truncated placeholders included — and
        nothing is truncated, summarized or re-written.  The payload carries
        the raw-observation reference so the model can read the excluded
        records on demand through the existing ``read_delivery_artifact``
        tool; the complete observation itself stays in the stored
        ``observation.json``.
        """
        if not isinstance(observation, dict):
            return observation
        excluded = 0
        runs: dict[str, Any] = {}
        for run_id, run in (observation.get("runs") or {}).items():
            events = run.get("events") if isinstance(run, dict) else None
            page = events.get("data") if isinstance(events, dict) else None
            if (isinstance(page, dict) and events.get("ok") is True
                    and isinstance(page.get("events"), list)):
                kept: list[Any] = []
                for event in page["events"]:
                    if (isinstance(event, dict)
                            and event.get("source") in _DECISION_EVENT_NOISE_SOURCES):
                        excluded += 1
                        continue
                    kept.append(event)
                if len(kept) != len(page["events"]):
                    run = {**run, "events": {**events, "data": {**page, "events": kept}}}
            runs[run_id] = run
        payload = {**observation, "runs": runs}
        payload["raw_observation"] = {
            "path": str(self.session_root / "observation.json"),
            "reader": "read_delivery_artifact",
            "excluded_noise_event_records": excluded,
            "excluded_noise_sources": sorted(_DECISION_EVENT_NOISE_SOURCES),
            "note": ("Pure native app-server notification records are excluded "
                     "from this payload; the complete raw observation including "
                     "every excluded record is stored at the path above and "
                     "readable on demand. No business, approval or receipt "
                     "content was truncated or summarized."),
        }
        return payload


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
        observed_state = None
        if resume:
            initial_observation = session.observe()
            # Persist the complete raw observation (the existing
            # observation.json record) before the first model-facing payload,
            # so the native log records excluded below are readable on demand
            # from the first turn.  One startup observe feeds both the stored
            # record and the delivered state, so no events page is consumed
            # twice and no duplicate startup observation is recorded.
            session.record_observation(initial_observation)
            observed_state = session._model_observation(initial_observation)
        runtime.send(json.dumps({"kind": "delivery_resume" if resume else "delivery_start", "config": config,
                                  "observed_state": observed_state,
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
                    pending_observation = {"kind": "host_observation",
                                           "data": session._model_observation(observation)}
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
                        runtime.send(json.dumps(
                            {"kind": "host_observation",
                             "data": session._model_observation(observation)}, ensure_ascii=False))
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
