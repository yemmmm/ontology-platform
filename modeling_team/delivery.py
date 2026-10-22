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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from . import host_ops_mcp
from .host_ops import HostOpError, resolve_run_root
from .handoff_materials import (
    HANDOFF_TOOL_NAMES,
    HANDOFF_TOOL_SPECS,
    HandoffMaterials,
    MaterialError,
)
from modeling_team.usage_capture import NumericReceiptWriter

from .model_routing import (
    ProviderSessionManager, load_team_model_profile, preflight_profile_credentials,
    resolve_delivery_model_binding, uses_external_credential_session,
)
from .runtimes.delivery import DeliveryRuntime, DeliveryRuntimeError, DeliveryRuntimeProtocol
from .runtimes.dsh_delivery import DSHDeliveryRuntime, validate_delivery_runtime
from .delivery_verification import start_verification, verification_status, stop_verification
from .efficiency import begin_round, summarize_round
from .delivery_conversation import ConversationLog, ConversationServer, ConversationError, now
from .delivery_host_actions import (
    append_session_event, request_host_action, host_action_state, read_session_journal,
)
from .task_budget import BudgetError, TaskBudget, bind_budget
from .delivery_review import StatusReview, codex_tool_result, routine_event

_PUBLIC_KINDS = {"status", "business_question", "decision_request", "final"}
_READ = {
    "get_run_status", "get_run_events", "get_pending_actions", "get_request_result",
    "inspect_checkpoints", "get_evaluation_status", "get_repair_status",
    "read_platform_record", "reconcile_write_state",
    "get_team_work_board",
    "get_task_budget",
}
_MODEL_QUERIES = {"get_run_status", "get_pending_actions", "get_evaluation_status",
                  "get_request_result"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


# These fields describe current execution and result bindings, not business
# conclusions. Unknown fields remain in the original result with exact coverage.
_STATUS_FIELDS = {
    "run_id", "operation_id", "request_id", "identity", "recorded_state", "stage",
    "first_blocker", "terminal_conclusion", "lifecycle", "work_state", "write_phase",
    "liveness", "status", "kind", "mode", "exit_code", "report_status", "report_binding",
    "request_binding", "control_receipts", "current_role", "record_path", "outcome",
    "action", "reason", "retryable", "next_action", "consumption_evidence", "receipt",
    "limitations", "error", "detail", "retry", "freeze_id", "model_handoff", "code",
    "content_digest", "ack_type", "receipt_ref", "idempotent", "pending_summary",
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

# ``start_repair`` validates the task and its namespace before creating a
# Delivery operation record.  These typed failures therefore prove that no
# repair process was created.  Other failures stay ambiguous: the operation
# owner is retained so a lost acknowledgement cannot be retried or stopped
# as if it never existed.
_REPAIR_PRELAUNCH_ERROR_CODES = frozenset({
    "delivery_argument_invalid",
    "delivery_operation_id_invalid",
    "input_path_invalid",
    "repair_authorization_mismatch",
    "repair_effort_invalid",
    "repair_executor_invalid",
    "repair_isolation_unavailable",
    "repair_scope_invalid",
    "repair_scope_missing",
    "repair_scope_private",
    "repair_task_invalid",
})


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
# Native activity is retained as raw evidence. Only recognized routine events
# are folded; failures, malformed records and new event kinds remain visible.


def _event_needs_action(value: Any) -> bool:
    """Read explicit protocol fields, never infer issues from business prose."""
    if isinstance(value, list):
        return any(_event_needs_action(item) for item in value)
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        if key in {"error", "error_type", "diagnostic", "pending_actions"} and item:
            return True
        if key in {"ok", "complete"} and item is False:
            return True
        if key in {"status", "state", "outcome", "result", "write_state", "mutation_state"} and isinstance(item, str) and item in {
            "unknown", "incomplete", "failed", "blocked", "rejected", "interrupted",
            "pending", "forbidden", "error", "cancelled",
        }:
            return True
        if _event_needs_action(item):
            return True
    return False


def _dsh_tool_results(payload: dict) -> list | None:
    """Decode the native tool envelope; unrecognized results remain decisions."""
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list) or not content:
        return None
    values = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            return None
        try:
            value = json.loads(block.get("text", ""))
        except (ValueError, TypeError):
            return None
        if not isinstance(value, (dict, list)):
            return None
        values.append(value)
    return values


def _dsh_wire_noise(data: dict) -> bool:
    frame = data.get("frame", {})
    if not isinstance(frame, dict):
        return False
    if (set(frame) == {"jsonrpc", "id", "result"} and frame["jsonrpc"] == "2.0"
            and type(frame["id"]) in (str, int) and frame["id"] != ""):
        result = frame["result"]
        if not isinstance(result, dict):
            return False
        if not result:
            return True
        if set(result) == {"messageId"}:
            return isinstance(result["messageId"], str) and bool(result["messageId"])
        if set(result) == {"effectiveBinding", "serverInfo"}:
            return (all(isinstance(value, dict) for value in result.values())
                    and not _event_needs_action(result))
        return (set(result) == {"plugins", "tools"}
                and all(isinstance(value, list) for value in result.values())
                and not _event_needs_action(result["plugins"]))
    params = frame.get("params", {})
    if not isinstance(params, dict):
        return False
    if frame.get("method") == "session.status":
        return params.get("status") in ("running", "idle")
    if frame.get("method") != "session.event":
        return False
    native = params.get("event", {})
    if not isinstance(native, dict) or not isinstance(native.get("data"), dict):
        return False
    kind, payload = native.get("type"), native["data"]
    if kind == "agent/inbox/spliced":
        # The runtime consumes these queue transitions independently. A normal
        # splice does not ask Delivery to decide anything; cancellation/error
        # and unfamiliar shapes remain visible through the original evidence.
        return (set(payload) <= {"target", "start", "inserted", "removedCount"}
                and payload.get("target") == "next-turn"
                and type(payload.get("start")) is int and payload["start"] >= 0
                and type(payload.get("removedCount", 0)) is int
                and payload.get("removedCount", 0) >= 0
                and isinstance(payload.get("inserted"), list)
                and all(isinstance(item, dict) and isinstance(item.get("id"), str)
                        and item["id"] for item in payload["inserted"]))
    if kind == "tool/result":
        message = payload.get("message")
        if isinstance(message, dict) and message.get("isError") is True:
            return False
        values = _dsh_tool_results(payload)
        return (values is not None and not _event_needs_action(values)
                and not any(isinstance(value, dict) and (
                    value.get("isError") is True or value.get("is_error") is True)
                    for value in values))
    reason = payload.get("reason")
    if isinstance(reason, dict) and reason.get("kind") in {"error", "failed", "canceled", "max-tokens"}:
        return False
    if kind == "request/header":
        diagnostic = dict(payload)
        if isinstance(payload.get("header"), dict):
            diagnostic["header"] = {key: value for key, value in payload["header"].items()
                                    if key != "tools"}
        return not _event_needs_action(diagnostic)
    if kind == "turn/end":
        return isinstance(reason, dict) and reason.get("kind") == "completed"
    # Attempts, abnormal activity endings and unknown event kinds stay visible.
    return kind in {
        "turn/start", "step/start", "step/end", "system/message", "user/message",
        "assistant/message", "tool/call", "request/header", "request/context",
    }


def _dsh_wire_metadata(data: dict) -> dict:
    """Keep actual activity/failure identity, without native prompts or tool bodies."""
    frame = data.get("frame", {})
    if not isinstance(frame, dict):
        return {"malformed_frame": True}
    params = frame.get("params", {})
    if not isinstance(params, dict):
        return {"method": frame.get("method"), "malformed_params": True}
    native = params.get("event", {})
    if not isinstance(native, dict):
        native = {}
    payload = native.get("data", {})
    if not isinstance(payload, dict):
        payload = {}
    state = {"method": frame.get("method"), "session_id": params.get("sessionId"),
             "event_type": native.get("type"), "seq": native.get("seq")}
    for value in (params, payload):
        state.update({key: item for key, item in value.items()
                      if key in {"turn", "step", "status", "code", "http_status", "outcome"}
                      and (item is None or type(item) in (str, int, bool))})
    reason = payload.get("reason")
    if isinstance(reason, dict):
        state["reason_kind"] = reason.get("kind")
    errors = []

    def collect(value):
        if isinstance(value, dict):
            fields = {key: item for key, item in value.items()
                      if key in {"code", "status", "http_status", "reason_code", "error_type"}
                      and type(item) in (str, int, bool)}
            if fields and fields not in errors:
                errors.append(fields)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    # Native failure codes occur in turn/end reasons, attempt finish chunks or RPC errors.
    collect(frame.get("error"))
    collect(payload.get("reason"))
    for item in payload.get("stream", []) if isinstance(payload.get("stream"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("chunk"), dict):
            collect(item["chunk"].get("reason"))
    if native.get("type") == "tool/result":
        message = payload.get("message")
        if isinstance(message, dict) and message.get("isError") is True:
            state["tool_error"] = True
        for result in _dsh_tool_results(payload) or []:
            if isinstance(result, dict):
                if (_event_needs_action(result) or result.get("isError") is True
                        or result.get("is_error") is True):
                    state["tool_error"] = True
                collect(result.get("error"))
    if errors:
        state["diagnostics"] = errors
    return state


def _is_decision_event_noise(event: Any) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("corrupt") or event.get("truncated"):
        return False
    source, data = event.get("source"), event.get("data")
    if not isinstance(data, dict):
        return False
    if source == "work-board-events.jsonl" and data.get("schema_version") == "team-work-board/v1":
        # The actual peer message, failure or formal issue still follows its
        # original channel. Advisory report bookkeeping never wakes Delivery.
        return True
    if source == "dsh-wire.jsonl":
        frame = data.get("frame")
        if isinstance(frame, dict):
            params = frame.get("params")
            native = params.get("event") if isinstance(params, dict) else None
            if (set(frame) == {"jsonrpc", "id", "result"}
                    or isinstance(native, dict) and native.get("type") == "request/header"):
                # These known protocol envelopes contain tool schemas. An `error`
                # parameter declaration is not a live runtime diagnostic.
                return _dsh_wire_noise(data)
    # Explicit errors/unknown outcomes override otherwise routine activity.
    if _event_needs_action(data):
        return False
    if source == "auth-barrier.jsonl":
        return data.get("event") == "provider_proxy_ready"
    if source in {"staged-decisions.jsonl", "competency-questions.jsonl"}:
        if data.get("event") in {
            "directories-registered", "protocol-capability-endpoint-started",
            "modeling-capability-endpoint-started", "cq-capability-endpoint-started",
        }:
            return True
    if source == "dsh-dispatch.jsonl":
        return (data.get("event") == "queued" and data.get("runtime") == "dsh"
                and all(isinstance(data.get(key), str) and data[key]
                        for key in ("agent_id", "dispatch_id", "message_id")))
    if source == "dsh-handoff.jsonl":
        normal = (data.get("kind") == "artifact" and data.get("state") == "received"
                  or data.get("kind") == "public-input"
                  and data.get("state") in {"queued", "claimed", "settled"})
        material = data.get("material_ref")
        return (normal and all(isinstance(data.get(key), str) and data[key]
                               for key in ("run_id", "handoff_id"))
                and isinstance(material, dict) and isinstance(material.get("material_id"), str)
                and bool(material["material_id"]))
    if source == "dsh-wire.jsonl":
        return _dsh_wire_noise(data)
    if source == "app-server-events.jsonl":
        method = data.get("method")
        if method == "thread/started":
            params = data.get("params")
            thread = params.get("thread") if isinstance(params, dict) else None
            return isinstance(thread, dict) and bool(thread.get("id"))
        if method == "mcpServer/startupStatus/updated":
            params = data.get("params")
            return isinstance(params, dict) and params.get("status") in {"starting", "ready"}
        if method == "remoteControl/status/changed":
            params = data.get("params")
            return isinstance(params, dict) and params.get("status") == "disabled"
        if method in {"item/started", "item/completed", "turn/completed", "turn/finished"}:
            params = data.get("params")
            if not isinstance(params, dict):
                return False
            item = params.get("item") or params.get("turn")
            if not isinstance(item, dict):
                return False
            # These native content records have no status field. Their text
            # is retained, while actual decisions arrive through Host state.
            if "status" not in item and item.get("type") in {
                "reasoning", "agentMessage", "userMessage",
            }:
                return True
            if not isinstance(item.get("status"), str):
                return False
            # Terminal failures remain visible; ordinary native content is
            # already represented by actual phase/pending/report observations.
            return item.get("status") in {"completed", "inProgress", "running"}
        if method == "mcpServer/elicitation/request":
            params = data.get("params") or {}
            return (isinstance(params, dict)
                    and isinstance(params.get("_meta"), dict)
                    and params["_meta"].get("codex_approval_kind") == "mcp_tool_call")
        if method == "account/rateLimits/updated":
            params = data.get("params") or {}
            limits = params.get("rateLimits") if isinstance(params, dict) else None
            return (isinstance(limits, dict) and bool(limits)
                    and set(limits) <= {
                        "credits", "individualLimit", "limitId", "limitName",
                        "normalModelSlug", "planType", "primary", "secondary",
                        "rateLimitReachedType", "spendControlReached",
                    }
                    and all(value is None for key, value in limits.items()
                            if key != "limitId"))
        return method in {
            "serverRequest/resolved",
            "item/agentMessage/delta", "item/reasoning/textDelta",
            "item/reasoning/summaryTextDelta", "item/reasoning/summaryPartAdded",
            "thread/tokenUsage/updated", "turn/started", "thread/status/changed",
            "item/commandExecution/outputDelta", "item/plan/delta",
        }
    if source == "mcp-elicitations.jsonl":
        return data.get("action") == "accept" and data.get("mode") == "form"
    if source == "formal-candidate-progress.jsonl":
        return data.get("event") == "candidate-receipt-registered"
    if source == "multi-slice-gate.jsonl":
        return data.get("event") in {"ontology-plan-applied", "mapping-reference-ontologies-applied"}
    if source == "coordinator.jsonl":
        return data.get("type") == "coordinator"
    if source == "capability-calls.jsonl":
        # Write and reporting calls may return an application-level unknown;
        # a successful transport acknowledgement alone cannot hide them.
        return data.get("ok") is True and data.get("operation") in {
            "get_ontology_read_model", "get_modeling_batch", "search_semantic_context",
            "get_semantic_context", "protocol_list_platform_artifacts",
        }
    if source == "dynamic-tool-calls.jsonl":
        return data.get("result") == "accepted" and data.get("tool") in {
            "read_handoff_material", "inspect_handoff_material",
            "list_handoff_materials", "get_run_status", "update_work_card",
            "get_work_board", "resolve_work_request",
        }
    if source not in {"provider-attempts.jsonl", "dsh-provider.jsonl"}:
        return False
    receipt = event.get("data")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "model-usage-capture/v1":
        return False
    # Numeric call activity is raw evidence, not new work for Delivery.
    # Errors (including interrupted 2xx streams), unknown statuses and
    # corrupt/truncated placeholders remain decisions.
    if receipt.get("event") == "attempt_start":
        return receipt.get("status") == "unfinished" and receipt.get("http_status") is None
    status = receipt.get("http_status")
    if source == "dsh-provider.jsonl" and receipt.get("event") == "response_usage":
        return (receipt.get("status") == "completed" and type(status) is int
                and 200 <= status < 300 and receipt.get("usage_complete") is True
                and receipt.get("usage_issues") == [])
    return (receipt.get("event") == "attempt_end" and receipt.get("status") == "completed"
            and type(status) is int and 200 <= status < 300)


# Content stays in the original event. Delivery receives identifiers and state;
# CQ question text, answer points and review notes never enter its default input.
_EVENT_METADATA_KEYS = frozenset({
    "event", "type", "status", "state", "ok", "run_id", "agent_id", "sender_id", "delivery_id",
    "recipient_id", "message_kind", "message_id", "terminal", "settles", "phase",
    "review_id", "question_id", "question_ids", "content_version", "content_digest",
    "candidate_digest", "model_revision", "request_id", "issue_id", "reporter_id",
    "control_epoch", "operation_id", "batch_id", "freeze_id", "freeze_digest",
    "decision", "decision_ref", "draft_ref", "review_snapshot_ref", "classification",
    "reason_code", "code", "error", "error_type", "retry", "next_action", "outcome",
    "report_binding", "report_path", "work_state", "method", "tool", "operation",
    "result", "generation", "phase_event", "category", "ack", "ack_type", "denial_category",
    "recorded_at", "message", "reason", "detail", "retryable", "limitations",
})


def _decision_event_metadata(event: Any) -> Any:
    if not isinstance(event, dict):
        return {"event_shape": type(event).__name__, "content_reference": "raw observation"}
    if "data" not in event:
        return event
    if not isinstance(event.get("data"), dict):
        return {**event, "data": {"malformed_data_shape": type(event["data"]).__name__,
                "content_reference": {"source": event.get("source"), "byte_offset": event.get("byte_offset")}}}
    source = event.get("source", "")
    if not isinstance(source, str):
        return event
    data = event["data"]
    if source == "provider-attempts.jsonl":
        return event
    projected = {key: value for key, value in data.items() if key in _EVENT_METADATA_KEYS}
    if isinstance(projected.get("result"), (dict, list)):
        projected.pop("result")
    if (source == "team-transport-events.jsonl"
            and data.get("category") in {"terminal_report_accepted", "runtime_input_pending"}
            and isinstance(data.get("agent"), str)):
        projected["agent_id"] = data["agent"]
    if source == "dsh-provider.jsonl":
        projected.update({key: data[key] for key in (
            "http_status", "usage_complete", "usage_issues", "provider_error", "request_shape",
        ) if key in data})
    if source == "dsh-wire.jsonl":
        projected.update({key: data[key] for key in ("session_id", "process_instance") if key in data})
        projected["runtime_state"] = _dsh_wire_metadata(data)
    if source == "app-server-events.jsonl" and isinstance(data.get("params"), dict):
        params = data["params"]
        anomaly = {key: value for key, value in params.items()
                   if key in {"error", "status", "threadId", "turnId"}}
        for key in ("item", "turn"):
            if isinstance(params.get(key), dict):
                anomaly[key] = {field: value for field, value in params[key].items()
                                if field in {"error", "status", "id", "type", "server", "tool"}}
        if anomaly:
            projected["runtime_state"] = anomaly
    if source == "settled.jsonl" and isinstance(data.get("results"), dict):
        projected["results"] = {
            actor: {key: value for key, value in result.items()
                    if key in {"status", "agent_id", "artifact_refs", "report_ref"}}
            for actor, result in data["results"].items() if isinstance(result, dict)}
    if source.startswith("cq-"):
        # Review decision documents can contain a full modified question. Only
        # scalar identities and question-id lists belong in Delivery input.
        projected = {key: value for key, value in projected.items()
                     if value is None or isinstance(value, (str, bool, int, float))
                     or (key == "question_ids" and isinstance(value, list)
                         and all(isinstance(item, str) for item in value))}
    if projected != data:
        projected["content_reference"] = {
            "source": source, "byte_offset": event.get("byte_offset"),
            "note": "original content retained; read only for an authorized decision gap",
        }
    return {**event, "data": projected}


def _diagnostic_state(event: Any, *, native_operation: str | None = None) -> tuple[str, str, bool] | None:
    """Fold typed diagnostics by current problem state, not append/request identity.

    This is shared by runtimes and unfamiliar plugins. Effectful request identities
    and binding changes stay distinct; opaque payload changes retain their full content. Only
    diagnostic-owned counters/request identities are ignored; business dictionaries
    are untouched.
    """
    if not isinstance(event, dict) or event.get("corrupt") or event.get("truncated"):
        return None
    data, source = event.get("data"), event.get("source")
    if not isinstance(data, dict) or not isinstance(source, str):
        return None
    if (source == "deliveries.jsonl"
            and (data.get("event") == "delivery-deferred" or data.get("type") == "delivery")
            and all(isinstance(data.get(key), str) and data[key]
                    for key in ("delivery_id", "recipient_id"))):
        # Requeueing the same parked message preserves delivery; it is not a
        # new decision until the failure or one of its bindings actually changes.
        current = {key: value for key, value in data.items() if key != "recorded_at"}
        return (_json_bytes([source, data["delivery_id"], data["recipient_id"]]).decode(),
                _digest_bytes(_json_bytes(current)), True)
    native_values = None
    item = codex_tool_result(event)
    if item is not None:
        params = data["params"]
        native_values = {key: item[key] for key in ("arguments", "result") if key in item}
        # Fold only native call/turn identities and timings. Error payloads and
        # failed operation arguments keep their business/protective bindings.
        failed = _event_needs_action(item)
        native_operation = f"{item['server']}/{item['tool']}"
        data = {key: value for key, value in data.items()
                if key not in {"params", "param_keys", "has_request_id", "method"}}
        data["params"] = {key: value for key, value in params.items()
                          if key not in {"item", "turnId", "threadId", "completedAtMs"}}
        data.update(event="native-tool-result", runtime_session_id=params.get("threadId"),
                    operation=native_operation, diagnostic=(
                        {"failed": True, "error": item.get("error"), **native_values}
                        if failed else {"status": "recovered"}))
    if source == "dsh-wire.jsonl":
        if native_operation is None:
            return None
        frame = data.get("frame")
        params = frame.get("params") if isinstance(frame, dict) else None
        native = params.get("event") if isinstance(params, dict) else None
        payload = native.get("data") if isinstance(native, dict) else None
        if not isinstance(payload, dict) or native.get("type") != "tool/result":
            return None
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        values = _dsh_tool_results(payload)
        failed = message.get("isError") is True or _event_needs_action(values)
        if values is None:
            content = message.get("content")
            if (not failed or not isinstance(content, list) or not content
                    or any(not isinstance(block, dict) or block.get("type") != "text"
                           or not isinstance(block.get("text"), str) for block in content)):
                return None
            values = [{"text": block["text"]} for block in content]
        # Fold only native envelope identities, never keys inside the actual
        # business/error payload. A healthy result clears this actor's problem.
        native_values = values
        data = {key: data[key] for key in ("agent_id", "session_id", "process_instance")
                if key in data}
        data.update(event="native-tool-result", operation=native_operation, diagnostic=(
            {"failed": True, "results": values} if failed else {"status": "recovered"}))
    protected = {"write_state", "mutation_state", "control_epoch", "authorization_reference",
                 "authorization_valid_until", "review_id", "content_version", "content_digest",
                 "operation_id", "issue_id", "report_binding", "pending_actions"}

    def has_binding(value):
        if isinstance(value, dict):
            return bool(protected.intersection(value)) or any(has_binding(v) for v in value.values())
        return isinstance(value, list) and any(has_binding(v) for v in value)

    bound = has_binding(data) or has_binding(native_values)
    diagnostic = bool({"code", "error", "error_type", "diagnostic", "usage_issues",
                       "provider_error"}.intersection(data)) or _event_needs_action(data)
    volatile = {"recorded_at", "timestamp", "received_at", "seq", "clock_ref",
                "monotonic_start_ns", "monotonic_end_ns"}
    if diagnostic:
        volatile.update({"provider_request_id", "response_id", "start",
                         "headers_at", "end", "count", "attempt_index", "time_basis"})
        if not bound:
            volatile.add("request_id")
    if data.get("schema_version") == "model-usage-capture/v1":
        volatile.update({"raw_usage", "present_fields", "field_positions", "request_shape"})
    current = {key: value for key, value in data.items() if key not in volatile}
    stream = {key: data[key] for key in ("event", "type", "category", "method", "plugin",
              "agent_id", "agent", "role", "provider", "runtime_session_id", "session_id",
              "process_instance",
              "object", "target", "resource_id", "purpose") if key in data}
    if native_operation is not None:
        stream["operation"] = native_operation
    if bound:
        stream.update({key: data[key] for key in ("request_id", "operation_id", "issue_id", "delivery_id")
                       if key in data})
    return (_json_bytes([source, stream]).decode(), _digest_bytes(_json_bytes(current)), diagnostic)


def _decision_events(run_id: str, events: Any, state: dict[str, dict[str, Any]]) -> Any:
    """Project one incremental events page onto cumulative decision content.

    The projected fingerprint depends on which decision events have already
    been seen, never on which page they arrived in: the empty follow-up page
    after a drained page and an at-least-once re-delivery inside a parked
    window project to the same value as the page that first carried the event.
    Failed event reads and corrupt/truncated placeholder events stay
    decisions; every excluded byte remains in the stored raw observation for
    on-demand reading, and the delivered payload excludes exactly the same
    noise events (:meth:`DeliverySession._model_observation`).
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
    run_state["selected"] = []
    problems = run_state.setdefault("problem_states", {})
    native_calls = run_state.setdefault("native_tool_calls", {})
    for event in page.get("events") or []:
        operation = None
        if isinstance(event, dict) and event.get("source") == "dsh-wire.jsonl":
            data = event.get("data", {})
            frame = data.get("frame") if isinstance(data, dict) else None
            params = frame.get("params") if isinstance(frame, dict) else None
            native = params.get("event") if isinstance(params, dict) else None
            payload = native.get("data") if isinstance(native, dict) else None
            if isinstance(payload, dict):
                message = payload.get("message", {})
                call_id = (payload.get("callId") if native.get("type") == "tool/call"
                           else message.get("toolCallId") if isinstance(message, dict) else None)
                if isinstance(call_id, str):
                    key = _json_bytes([data.get("agent_id"), data.get("session_id"),
                                       data.get("process_instance"), call_id]).decode()
                    if native.get("type") == "tool/call" and isinstance(payload.get("name"), str):
                        native_calls[key] = payload["name"]
                    elif native.get("type") == "tool/result":
                        operation = native_calls.pop(key, None)
        noise = _is_decision_event_noise(event)
        problem = _diagnostic_state(event, native_operation=operation)
        if routine_event(event) and (codex_tool_result(event) is not None
                                    or problem is None or problem[0] not in problems):
            continue
        if noise and (problem is None or not problem[2]):
            continue
        identity: str | None = None
        if isinstance(event, dict):
            source = event.get("source")
            if isinstance(source, str):
                offset = event.get("byte_offset")
                positioned = isinstance(offset, int) and not isinstance(offset, bool)
                identity = f"{source}:{offset if positioned else 'unpositioned'}"
        if identity is not None:
            if identity in run_state["seen"]:
                continue
            run_state["seen"].add(identity)
        if problem is not None:
            key, signature, _ = problem
            previous = problems.get(key)
            problems[key] = signature
            if previous == signature or (noise and previous is None):
                continue
        event = _decision_event_metadata(event)
        run_state["selected"].append(event)
        canonical = ({key: value for key, value in event.items()
                      if key not in _DECISION_EVENT_NOISE_KEYS}
                     if isinstance(event, dict) else event)
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
    projected = copy.deepcopy(observation)
    host_actions = projected.get("host_actions", {})
    host_keys = {"request_id", "session_id", "run_id", "kind", "authorization_reference",
                 "bindings", "content_digest", "request_digest", "source", "status",
                 "result_ref", "result_digest", "journal_ref", "write_state"}
    for collection in ("requests", "results"):
        if collection in host_actions:
            host_actions[collection] = {key: {field: value for field, value in item.items()
                                             if field in host_keys}
                                       for key, item in host_actions[collection].items()}
    for collection in ("pending", "unresolved", "completed"):
        if collection in host_actions:
            host_actions[collection] = [{key: value for key, value in item.items() if key in host_keys}
                                        for item in host_actions[collection]]
    # Strip metadata only at its owning path. Business dictionaries may use
    # exactly the same keys, including evidence_refs and observed_at.
    for run in projected.get("runs", {}).values():
        status = run.get("status", {}).get("data", {})
        # Amount/heartbeat changes are queried on demand. Only the session's
        # stable budget-control identity is a Delivery decision input.
        status.pop("task_budget", None)
        for key in ("observed_at", "events_cursor", "last_verifiable_activity", "evidence_refs"):
            status.pop(key, None)
        progress = status.get("semantic_progress", {})
        for key in ("staged_decision_count", "latest_staged_decision_at"):
            progress.pop(key, None)
        liveness = status.get("liveness", {})
        for owner in (liveness, liveness.get("process_observation", {})):
            for key in ("observed_at", "heartbeat_at", "last_heartbeat_at", "heartbeat_count"):
                owner.pop(key, None)
        pending = run.get("pending", {}).get("data", {})
        pending.pop("observed_at", None)
        for item in pending.get("items", []):
            if item.get("type") == "cq_review":
                item["available_actions"] = [{"action": "request_host_action",
                    "kind": "cq_review", "note": "Host reviews the private snapshot directly; Delivery only checks bindings and receipts"}]
        # Source identity is retained in the raw snapshot, but log append is
        # not an independent decision when the parsed request set is unchanged.
        run.pop("request_ledger", None)
    for collection in ("operations", "repair_verifications"):
        for envelope in projected.get(collection, {}).values():
            data = envelope.get("data", {})
            data.pop("task_budget", None)
            for key in ("log_tails", "stdout_tail", "stderr_tail", "stdout_bytes", "stderr_bytes"):
                data.pop(key, None)
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


def _digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _source_ref(path: Path, raw: bytes) -> dict:
    return {"path": str(path), "scope": "prefix" if path.suffix == ".jsonl" else "file",
            "byte_length": len(raw), "content_digest": _digest_bytes(raw)}


def _utf8_page(raw: bytes, offset: int, budget: int) -> tuple[str, int]:
    if type(offset) is not int or not 0 <= offset <= len(raw):
        raise ValueError("offset is outside the selected range")
    if offset < len(raw) and raw[offset] & 0xC0 == 0x80:
        raise ValueError("offset must be a UTF-8 boundary; use next_offset")
    end = min(offset + budget, len(raw))
    while end < len(raw) and end > offset and raw[end] & 0xC0 == 0x80:
        end -= 1
    if end == offset and offset < len(raw):
        end += 1
        while end < len(raw) and raw[end] & 0xC0 == 0x80:
            end += 1
    return raw[offset:end].decode("utf-8"), end


def _selected_artifact(path: Path, raw: bytes, reference: dict | None,
                       selection: dict, max_bytes: int) -> dict:
    current = _source_ref(path, raw)
    if reference is not None:
        valid = (reference.get("path") == str(path)
                 and reference.get("scope") == current["scope"]
                 and type(reference.get("byte_length")) is int
                 and 0 <= reference["byte_length"] <= len(raw))
        captured = raw[:reference["byte_length"]] if valid else b""
        valid = (valid and _digest_bytes(captured) == reference.get("content_digest")
                 and (current["scope"] == "prefix" or len(captured) == len(raw)))
        if not valid:
            raise HostOpError("artifact_changed", "original artifact identity changed",
                              obj=str(path), retryable=True,
                              next_action="restart selection with the current source identity",
                              passthrough={"source_ref": current})
        raw = captured
    ref = dict(reference or current)
    try:
        if type(max_bytes) is not int or not 1 <= max_bytes <= 16384:
            raise ValueError("max_bytes must be 1..16384")
        if not isinstance(selection, dict):
            raise ValueError("selection must be bytes or literal JSON paths")
        kind = selection.get("kind")
        offset = selection.get("offset", 0)
        if kind == "bytes":
            if set(selection) - {"kind", "offset", "length"}:
                raise ValueError("unknown bytes selection parameter")
            length = selection.get("length", len(raw) - offset)
            if type(length) is not int or length < 0 or type(offset) is not int:
                raise ValueError("invalid byte interval")
            stop = offset + length
            if stop > len(raw):
                raise ValueError("byte interval exceeds captured source")
            if stop < len(raw) and raw[stop] & 0xC0 == 0x80:
                raise ValueError("interval end must be a UTF-8 boundary")
            binding = ref.get("selection_binding")
            if binding and (binding.get("kind") != kind or binding.get("stop") != stop
                            or offset < binding.get("start", 0)):
                raise ValueError("continuation must preserve the original interval")
            ref["selection_binding"] = binding or {"kind": kind, "start": offset, "stop": stop}
            selected = raw[:stop]
            text, end = _utf8_page(selected, offset, max_bytes)
            omitted = {"before": ref["selection_binding"]["start"], "after": len(raw) - stop,
                       "remaining_selected_bytes": stop - end}
            complete = end == stop
            source_complete = complete and ref["selection_binding"]["start"] == 0 and stop == len(raw)
            continuation = {"kind": kind, "offset": end, "length": stop - end}
            missing = []
        elif kind == "json":
            if set(selection) - {"kind", "paths", "offset"}:
                raise ValueError("unknown JSON selection parameter")
            paths = selection.get("paths")
            if (not isinstance(paths, list) or not 1 <= len(paths) <= 16
                    or any(not isinstance(parts, list) or not 1 <= len(parts) <= 16
                           or any(not isinstance(part, str) and
                                  (type(part) is not int or part < 0) for part in parts)
                           for parts in paths)):
                raise ValueError("paths require 1..16 literal paths, each with 1..16 keys/indices")
            binding = {"kind": kind, "paths": paths}
            if ref.get("selection_binding", binding) != binding:
                raise ValueError("continuation must preserve the selected paths and order")
            ref["selection_binding"] = binding
            try:
                document = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise HostOpError("artifact_corrupt", "original JSON cannot be parsed", obj=str(path),
                                  retryable=True, next_action="inspect an approved bytes selection") from exc
            fields, missing = [], []
            for parts in paths:
                value = document
                found = True
                for part in parts:
                    if isinstance(part, str) and isinstance(value, dict) and part in value:
                        value = value[part]
                    elif type(part) is int and isinstance(value, list) and part < len(value):
                        value = value[part]
                    else:
                        found = False
                        break
                entry = {"path": parts, "found": found}
                if found:
                    entry["value"] = value
                else:
                    missing.append(parts)
                fields.append(entry)
            selected = _json_bytes({"fields": fields})
            text, end = _utf8_page(selected, offset, max_bytes)
            stop = len(selected)
            complete, source_complete = end == stop, False
            omitted = {"other_source_fields": True, "remaining_selected_bytes": stop - end}
            continuation = {"kind": kind, "paths": paths, "offset": end}
        else:
            raise ValueError("selection.kind must be bytes or json")
    except (ValueError, TypeError) as exc:
        code = "artifact_corrupt" if isinstance(exc, UnicodeError) else "artifact_selection_invalid"
        raise HostOpError(code, str(exc), obj=str(path), retryable=True,
                          next_action="correct selection; continue only at next_offset") from exc
    return {"path": str(path), "source_ref": ref, "content_digest": ref["content_digest"],
            "selection": selection, "returned_range": {"offset": offset, "end": end, "bytes": end - offset},
            "text": text, "next_offset": end, "read_complete": complete,
            "source_complete": source_complete, "omitted": omitted, "missing_paths": missing,
            "continuation": None if complete else {"source_ref": ref, "selection": continuation},
            "limitations": ["text may be a partial JSON fragment; concatenate all selected pages",
                            "completeness refers to the captured source, not later appends"]}


def _value_changes(before: Any, after: Any, path: tuple = ()) -> list[dict]:
    if before == after:
        return []
    if isinstance(before, list) and isinstance(after, list):
        def identity(item):
            if isinstance(item, dict):
                return item.get("request_id") or item.get("id")
            return None
        old_ids, new_ids = [identity(item) for item in before], [identity(item) for item in after]
        if (all(isinstance(key, str) for key in old_ids + new_ids)
                and len(set(old_ids)) == len(old_ids) and len(set(new_ids)) == len(new_ids)):
            old = dict(zip(old_ids, before))
            new = dict(zip(new_ids, after))
            changes = []
            if set(old_ids) == set(new_ids) and old_ids != new_ids:
                changes.append({"path": list(path), "change": "order", "value": new_ids})
            for index, (key, value) in enumerate(zip(new_ids, after)):
                if key not in old:
                    changes.append({"path": [*path, index], "change": "added", "identity": key, "value": value})
                else:
                    changes.extend(_value_changes(old[key], value, (*path, index)))
            for key in old_ids:
                if key not in new:
                    changes.append({"path": list(path), "change": "removed", "identity": key, "previous": old[key]})
            return changes
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            if key not in after:
                changes.append({"path": [*path, key], "change": "removed", "previous": before[key]})
            elif key not in before:
                changes.append({"path": [*path, key], "change": "added", "value": after[key]})
            else:
                changes.extend(_value_changes(before[key], after[key], (*path, key)))
        return changes
    return [{"path": list(path), "change": "updated", "previous": before, "value": after}]


_LOCAL_SPECS = [
    {"name": "yield_delivery", "description": "Record the current wait and effective decisions, then end this turn. Program observation continues for all bindings; do not poll to confirm the same wait.",
     "inputSchema": {"type": "object", "properties": {
         "input_id": {"type": "string", "minLength": 1},
         "phase": {"type": "string", "minLength": 1},
         "waiting_for": {"type": "array", "minItems": 1, "items": {
             "type": "object", "properties": {
                 **{key: {"type": "string", "minLength": 1} for key in
                    ("run_id", "request_id", "operation_id", "host_request_id", "condition")}},
             "required": ["condition"], "additionalProperties": False}},
         "next_action": {"type": "string", "minLength": 1},
         "reason": {"type": "string", "minLength": 1},
         "next_review_at": {"type": "string", "description": "Optional ISO timestamp with timezone for rechecking unchanged facts; never delays external inputs, new facts or control deadlines."},
         "active_decisions": {"type": "array", "items": {
             "type": "object", "properties": {
                 "decision_id": {"type": "string", "minLength": 1},
                 "text": {"type": "string", "minLength": 1},
                 "source_references": {"type": "array", "minItems": 1,
                     "items": {"type": "string", "minLength": 1}},
                 "replaces": {"type": "array", "items": {"type": "string"}}},
             "required": ["decision_id", "text", "source_references", "replaces"],
             "additionalProperties": False}},
         "evidence_references": {"type": "array", "items": {"type": "object"}},
         "thread_boundary": {"type": ["object", "null"], "description": "Request a phase handoff. Omit to retain a pending handoff across later waits; null explicitly cancels it.", "properties": {
             "phase": {"enum": ["production", "acceptance"]},
             "run_id": {"type": "string", "minLength": 1},
             "request_ids": {"type": "array", "minItems": 1, "uniqueItems": True,
                             "items": {"type": "string", "minLength": 1}}},
             "required": ["phase", "run_id", "request_ids"], "additionalProperties": False}},
         "required": ["input_id", "phase", "waiting_for", "next_action", "reason", "active_decisions"],
         "additionalProperties": False}},
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
    {"name": "read_delivery_artifact", "description": (
        "Read approved sources or bound private run evidence using a supplied reference. "
        "Do not guess authorization/ledger/Host-result paths. Copy the returned selection or "
        "continuation; for remaining bytes use selection={kind:'bytes',offset:0} without length. "
        "length is an exact interval, not a page size; max_bytes caps a page. "
        "For paged decisions use read_remaining or read_original from that view; these read the "
        "minimal projection, not the raw journal bookkeeping. Raw evidence is for a specific gap."),
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "source_ref": {"type": "object",
             "required": ["path", "scope", "byte_length", "content_digest"],
             "description": "Copy the complete source identity including byte_length; requires selection."},
         "selection": {"type": "object", "properties": {
             "kind": {"type": "string", "enum": ["bytes", "json"]},
             "offset": {"type": "integer", "minimum": 0},
             "length": {"type": "integer", "minimum": 0,
                        "description": "Exact byte interval; omit for remaining bytes, never guess a page size."},
             "paths": {"type": "array", "description": "Literal JSON key/index paths for kind=json.",
                       "items": {"type": "array", "items": {"type": ["string", "integer"]}}}},
             "required": ["kind"], "additionalProperties": False},
         "max_bytes": {"type": "integer", "minimum": 1, "maximum": 16384}},
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
_LOCAL_SPECS.append({
    "name": "request_host_action",
    "description": "Request private Host CQ review or platform repair; records a pending handoff, never executes or certifies it.",
    "inputSchema": {"type": "object", "properties": {
        "request_id": {"type": "string"}, "run_id": {"type": "string"},
        "kind": {"enum": ["cq_review", "platform_repair"]},
        "bindings": {"type": "object"}, "expected_behavior": {"type": "string"},
        "actual_behavior": {"type": "string"}, "blocked_step": {"type": "string"},
        "evidence_references": {"type": "array", "items": {"type": "object"}},
        "checked": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {"type": "array", "items": {"type": "string"}},
        "write_state": {"type": "string"}},
        "required": ["request_id", "run_id", "kind", "bindings"],
        "additionalProperties": False},
})
_LOCAL_SPECS.append({
    "name": "get_task_budget",
    "description": "Read this task's local amount estimate, coverage and pause state; no authorization changes or model calls.",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
})
_DELIVERY_HOST_ONLY_TOOLS = frozenset({
    "submit_cq_review", "prepare_repair_task", "start_repair", "verify_repair",
})


class DeliverySession:
    def __init__(self, *, repository_root: Path, session_root: Path, config: dict,
                 resume: bool = False) -> None:
        self.repository_root = repository_root.resolve()
        self.session_root = session_root.resolve()
        self.config = copy.deepcopy(config)
        interval = config.get("status_review_interval_seconds", 90)
        if type(interval) is not int or interval <= 0:
            raise ValueError("status_review_interval_seconds must be a positive integer; correct the configuration and resume")
        self._status_review = StatusReview(interval, _utc_now())
        self._resuming = resume
        boundaries = config.get("phase_thread_boundaries", [])
        if not isinstance(boundaries, list) or any(
                item not in {"production", "acceptance"} for item in boundaries):
            raise ValueError("phase_thread_boundaries must select production and/or acceptance")
        self.phase_thread_history = []
        self._state_lock = threading.RLock()
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
        resource = config.get("resource_authorization") or {}
        if resource.get("mode", "starts") not in {"starts", "amount"}:
            raise ValueError("resource_authorization.mode must be starts or amount")
        self.budget = None
        self.budget_ref = None
        if resource.get("mode") == "amount":
            if not resource.get("budget_ref"):
                raise ValueError("amount authorization requires the original budget_ref")
            self.budget_ref = str(self._path(resource["budget_ref"]))
            self.budget = TaskBudget(self.budget_ref)
            self.budget.show()
        self.resource_authorization = {"mode": "amount", "budget_ref": self.budget_ref} if self.budget else {"mode": "starts"}
        self._budget_control_epoch = None
        self._budget_paused = False
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
        self.runtime_name = validate_delivery_runtime(config, self.binding)
        self.runtime_identity = {"runtime": self.runtime_name}
        self.runtime_task_binding = {key: config.get(key) for key in (
            "task", "profile", "scope", "task_overlay", "objective", "goal", "allowed_sources",
            "business_input_role")}
        self.recovery_pending = self.runtime_name == "dsh" and resume
        if resume:
            previous = json.loads((self.session_root / "session.json").read_text())
            if previous.get("resource_authorization", {"mode": "starts"}) != self.resource_authorization:
                raise ValueError("resumption cannot change the original task budget")
            if previous.get("runtime", "codex") != self.runtime_name:
                raise ValueError("resumption cannot change original Delivery runtime; use an explicit handoff")
            if self.runtime_name == "dsh" and previous.get("runtime_task_binding") != self.runtime_task_binding:
                raise ValueError("resumption cannot change original DSH task/scope/source binding")
            self.runtime_identity = previous.get("runtime_identity", self.runtime_identity)
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
            self.flow_confirmation = previous.get("flow_confirmation")
            self.phase_thread_history = previous.get("phase_thread_history", [])
            self.stop_pending = self.activity == "stopping"
        else:
            # Host may have created the immutable budget before the first Delivery launch.
            if self.session_root.exists():
                if not self.budget or set(p.name for p in self.session_root.iterdir()) != {"cost-budget"}:
                    raise FileExistsError(self.session_root)
            else:
                self.session_root.mkdir(parents=True, mode=0o700)
        if self.budget:
            bind_budget(self.session_root, self.budget_ref, "delivery:" + self.session_id,
                        kind="delivery", session_id=self.session_id)
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
                "budget_ref", "budget_control",
                "handoff_materials", "material_actor_id", "material_recipient_id",
            ):
                properties.pop(name, None)
            schema["additionalProperties"] = False
            self._tools[tool.name] = {"name": tool.name, "description": tool.description,
                                      "inputSchema": schema}
        self._tools.update({item["name"]: copy.deepcopy(item) for item in _LOCAL_SPECS})
        for name in _DELIVERY_HOST_ONLY_TOOLS:
            self._tools.pop(name, None)
        self._restore_decision_inputs()
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
            if source == "work-board-events.jsonl":
                # Routine observations carry bookkeeping only. The explicit
                # board tool provides the authorized on-demand flow projection.
                item = event.get("data", {})
                events.append({**event, "data": {k: item[k] for k in (
                    "schema_version", "kind", "record_seq", "recorded_at") if k in item}})
                continue
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
        with self._state_lock:
            self._save_state(state, **extra)

    def _save_state(self, state: str, **extra: Any) -> None:
        self._last_saved_state = state
        record = {"schema_version": 1, "session_id": self.session_id,
                  "project_id": self.project_id, "activity": self.activity,
                  "work_result": self.work_result,
                  "authorization_valid_until": self.authorization_valid_until,
                  **{field: self.config.get(field) for field in
                     ("production_start_limit", "incremental_request_id", "incremental_run_id")},
                  "authorization_reference": self.authorization, "state": state,
                  "resource_authorization": self.resource_authorization,
                  **({"task_budget": self.budget.show(audience="delivery")} if self.budget else {}),
                  "run_ids": sorted(self.run_ids), "operation_ids": sorted(self.operation_ids),
                  "operation_kinds": self.operation_kinds,
                  "verification_ids": sorted(self.verification_ids),
                  "event_cursors": self._event_cursors,
                  "status_review": self._status_review.state(),
                  "delivery_inputs": getattr(self, "_pending_decisions", []),
                  "repair_task_files": sorted(str(x) for x in self.repair_task_files),
                  "model_profile": self.profile.profile_id,
                  "model_binding": self.binding.as_dict(),
                  "model_binding_source": self.binding_source,
                  "business_input_role": self.business_input_role,
                  "flow_confirmation": self.flow_confirmation,
                  "supervisor_pid": os.getpid(),
                  "native_thread_id": getattr(self, "native_thread_id", None),
                  "runtime": self.runtime_name, "runtime_identity": self.runtime_identity,
                  "runtime_task_binding": self.runtime_task_binding,
                  "phase_thread_history": self.phase_thread_history,
                  "native_pid": getattr(self, "native_pid", None),
                  "close_statistics": getattr(self, "close_statistics", {
                      "schema_version": "team-close-statistics/v1", "view": "task_close",
                      "closure_status": "closing", "report_status": "pending",
                      "coverage_status": "unknown", "limitations": ["delivery_runtime_not_closed"]}),
                  "allowed_operations": sorted(self.allowed_operations), **extra}
        temporary = self.session_root / "session.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        # The queue is already recorded as immutable decision/dispatch events.
        # Keep it in session.json, not in every journal state checkpoint.
        self._append("session-events.jsonl", {key: value for key, value in record.items()
                                             if key != "delivery_inputs"})
        temporary.replace(self.session_root / "session.json")
        if self.conversation:
            state = {"activity": self.activity, "observed_at": now(), "basis": "delivery_state",
                     "delivery_result": self.work_result, "close_statistics": record["close_statistics"]}
            if state != getattr(self, "_public_state", None):
                self.conversation.append("session_state", state=state)
                self._public_state = state

    def _append(self, filename: str, value: dict) -> None:
        if filename == "session-events.jsonl":
            append_session_event(self.session_root, value)
        else:
            with (self.session_root / filename).open("a") as handle:
                handle.write(json.dumps(value, ensure_ascii=False) + "\n")

    def tool_specs(self) -> list[dict]:
        return list(self._tools.values())

    def accept_user_input(self, text: str) -> dict:
        message_id = uuid.uuid4().hex
        packet = {"kind": "user_input", "text": text,
                  "message_id": message_id, "received_at": now(),
                  "trigger": {"kind": "external_input"},
                  "input_role": self.business_input_role,
                  "source_reference": f"delivery:{self.session_id}:{self.business_input_role}:{message_id}",
                  "authorization_reference": self.authorization}
        if not self.conversation:
            self._append("user-input.jsonl", packet)
        return packet

    def sourced_packet(self, message: dict) -> dict:
        packet = {**message, "kind": "user_input", "message_kind": message["kind"],
                  "trigger": {"kind": "external_input", "message_id": message["message_id"]},
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
                "Control each owner by its actual runtime. For DSH production use Host pause_run/"
                "resume_live_run and read the Runner's actual process-control receipt. Keep Delivery "
                "online. For Codex production and unmigrated evaluation relay the sourced instruction "
                "and obtain actual acknowledgements. Record pending owners and in-flight calls separately."
            )
            self.conversation.append("control_result", message_id=message["message_id"],
                                     action=message["action"], status="pending", basis="awaiting_agent_confirmation")
            self._save("active")
        return packet

    def apply_user_control(self, text: str, *, source_reference: str | None = None) -> dict | None:
        if self.budget and text in {"暂停", "继续", "撤回预算"}:
            self._budget_next_check = 0
            if text == "暂停":
                self.budget.request_pause("user_paused", source_reference=source_reference)
            elif text == "撤回预算":
                self.budget.request_pause("authorization_revoked", source_reference=source_reference)
            elif self.business_input_role == "user" and source_reference:
                self.budget.continue_authorized(source_reference, source_reference=source_reference,
                                               clear_reasons=["budget_exhausted", "metering_error", "user_paused"])
            return {"control": text, "source": "user", "task_budget": self.budget.show(audience="delivery")}
        if text in {"暂停", "继续"}:
            # DSH production requires actual process control, while Codex and
            # unmigrated evaluation retain their cooperative owner contract.
            results = {}
            for run_id in sorted(self.run_ids):
                status = self.call_tool("get_run_status", {"run_id": run_id}, _model_view=False)
                if status.get("data", {}).get("identity", {}).get("runtime") != "dsh":
                    continue
                name = "pause_run" if text == "暂停" else "resume_live_run"
                try:
                    results[run_id] = {"ok": True, "data": getattr(host_ops_mcp, name)(
                        run_id=run_id, text=text, source_reference=source_reference,
                        repository_root=self.repository_root)}
                except HostOpError as exc:
                    results[run_id] = {"ok": False, "error": exc.as_envelope()}
            if not results:
                return None
            self.activity = "pause_pending" if text == "暂停" else "resume_pending"
            self._save("active")
            return {"control": text, "owner_results": results, "status": "pending",
                    "limitations": "read actual DSH process-control receipts; other owners need acknowledgements"}
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

    def sync_budget_control(self, runtime) -> bool:
        if not self.budget:
            return False
        if getattr(runtime, "busy", False):
            return False  # Finish the admitted turn, including tools and usage receipts.
        if time.monotonic() < getattr(self, "_budget_next_check", 0):
            return self._budget_paused
        self._budget_next_check = time.monotonic() + 2
        if self.authorization_valid_until and datetime.now(UTC) >= datetime.fromisoformat(self.authorization_valid_until.replace("Z", "+00:00")):
            self.budget.request_pause("authorization_expired", source_reference=self.authorization)
        try:
            self.budget.require_available(operation="supervise")
        except BudgetError:
            pass
        state = self.budget.show()
        paused = not state["admission_open"]
        key = (state["epoch"], paused)
        if key != self._budget_control_epoch and (paused or self._budget_paused):
            self._budget_control_epoch = key
            self._budget_paused = paused
            action = "pause" if paused else "resume"
            owner_id = "delivery:" + self.session_id
            message = {"source": "task_budget", "budget_ref": self.budget_ref, "epoch": state["epoch"],
                "action": action, "reason": ",".join(state["pause_reasons"]),
                "request_id": "budget-" + str(state["epoch"]) + "-" + hashlib.sha256(owner_id.encode()).hexdigest()[:20],
                "instruction": ("停止安排新任务并等待；用 record_flow_confirmation 确认 request_id。"
                                if paused else "沿原任务和原回执继续，勿重复提交；确认 request_id。")}
            message["text"] = json.dumps(message, ensure_ascii=False)
            self._budget_control_message = message
            try:
                self.budget.record_control(owner_id, state["epoch"], "requested", action=action)
            except BudgetError:
                pass  # Recording trouble must not prevent the pause itself.
            try:
                result = runtime.control_budget(message)
                status = result.get("status", "unknown")
                if status not in {"effective", "instruction_delivered", "not_running", "not_started"}:
                    status = "unknown"
            except Exception:
                status = "unknown"
            try:
                self.budget.record_control(owner_id, state["epoch"], status, action=action,
                                           request_id=message["request_id"])
            except BudgetError:
                status = "unknown"
            self._append("session-events.jsonl", {"event": "task_budget_control", **message, "status": status})
        return paused

    def _hold_budget_refusal(self, exc):
        try:
            if self.budget and self.budget.show()["admission_open"]:
                self.budget.request_pause("metering_error", error_code=exc.code,
                                          owner_id="delivery:" + self.session_id)
        except BudgetError:
            pass  # Keep the original ledger and Host control path available.

    def record_held_inputs(self, packets: list[dict], reason: str) -> None:
        """Program feedback while inference is disallowed; original inputs stay pending."""
        recorded = getattr(self, "_held_input_reasons", {})
        for packet in packets:
            identity = packet.get("message_id", packet.get("source_reference"))
            if recorded.get(identity) == reason:
                continue
            self._append("session-events.jsonl", {"event": "delivery_input_held",
                "recorded_at": now(),
                "message_id": packet.get("message_id"), "source_reference": packet.get("source_reference"),
                "reason": reason, "budget_ref": self.budget_ref, "status": "pending"})
            if self.conversation and packet.get("message_id"):
                self.conversation.append("dispatch_result", message_id=packet["message_id"],
                    status="pending", reason=reason)
            print("Delivery input retained: " + reason, flush=True)
            recorded[identity] = reason
        self._held_input_reasons = recorded

    def _read_artifact(self, value: str, *, source_ref: dict | None = None,
                       selection: dict | None = None, max_bytes: int = 16384,
                       internal: bool = False) -> dict:
        host_results = host_action_state(self.session_root)
        bound_host_ref = None
        for result in host_results.get("results", {}).values():
            ref = result.get("result_ref") or {}
            relative = ref.get("path")
            if not isinstance(relative, str):
                continue
            candidate = (self.session_root / relative).resolve()
            if not candidate.is_relative_to(self.session_root / "host-results"):
                continue
            if value == relative or self._path(value) == candidate:
                bound_host_ref = ref
                break
        path = ((self.session_root / bound_host_ref["path"]).resolve()
                if bound_host_ref else self._path(value))
        approved = bound_host_ref is not None or path in self.sources or path in {
            self.session_root / name for name in ("session.json", "session-events.jsonl", "user-input.jsonl", "conversation-events.jsonl", "public-messages.jsonl", "observation.json", "efficiency-round.json", "efficiency-progress.jsonl")
        }
        approved = approved or (
            path.parent == self.session_root / "decision-views"
            and re.fullmatch(r"[0-9a-f]{64}\.json", path.name) is not None
        )
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
                    private_board_files = {"evidence/work-board-events.jsonl",
                        "evidence/work-board-retrospective.json", "evidence/close-statistics.json"}
                    private_board_roots = {"evidence/work-board-retrospectives",
                        "evidence/close-statistics", "evidence/close-statistics-capture"}
                    name = relative.as_posix()
                    if name in private_board_files or any(name.startswith(prefix + "/") for prefix in private_board_roots):
                        raise HostOpError("artifact_forbidden",
                            "raw work-board/statistics originals are Host-private; use get_team_work_board for the authorized flow projection",
                            retryable=True, next_action="select the same run/agent/history through get_team_work_board")
                    approved = relative.parts[0] in {
                        "competency-questions", "acceptance-v3", "evidence", "manifest-snapshots",
                        "early-feedback",
                    } or relative.as_posix() in {
                        "state.json", "baseline-manifest.json", "task.snapshot.yaml", "profile.snapshot.yaml",
                        "model-handoff.json", "control/host-requests.jsonl",
                    }
                    if approved:
                        break
        # Operations grant only their actual record/log files. Resolving both
        # sides of an operation path must not turn a symlink into a grant.
        for operation_id in self.operation_ids:
            record_path = self.repository_root / ".delivery-ops" / f"{operation_id}.json"
            if record_path.is_symlink():
                continue
            try:
                record = json.loads(record_path.read_text())
                if record.get("operation_id") != operation_id:
                    continue
                candidates = [record_path, *[self.repository_root / item
                    for item in (record.get("log_paths") or {}).values() if isinstance(item, str)]]
                approved = approved or any(not item.is_symlink() and item.resolve() == path
                    and item.resolve().is_relative_to(record_path.parent) for item in candidates)
            except (OSError, ValueError):
                continue
        for operation_id in self.verification_ids:
            try:
                status = verification_status(operation_id=operation_id, session_root=self.session_root)
                candidates = [Path(status["record_path"]),
                              *[Path(item) for item in (status.get("logs") or {}).values()]]
                approved = approved or any(not item.is_symlink() and item.resolve() == path
                    and item.resolve().is_relative_to(self.session_root / "repair-verification" / operation_id)
                    for item in candidates)
            except (OSError, ValueError, KeyError):
                continue
        if not approved:
            raise HostOpError("artifact_forbidden", "artifact is outside approved sources and bound run evidence",
                              retryable=True, next_action="select an approved source or bound artifact")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise HostOpError("artifact_unavailable", str(exc), obj=str(path), retryable=True,
                              next_action="check the bound path and retry") from exc
        if bound_host_ref and _digest_bytes(raw) != bound_host_ref.get("content_digest"):
            raise HostOpError("host_result_changed", "Host result original differs from its journal binding",
                retryable=True, next_action="ask the Host to retain and register the current result original")
        if bound_host_ref and source_ref and source_ref.get("path") == bound_host_ref["path"]:
            # Journal Host results use a session-relative path; the private
            # permission and immutable digest checks above bind its absolute identity.
            source_ref = {**source_ref, "path": str(path)}
        if selection is None:
            if source_ref is not None:
                raise HostOpError("artifact_selection_invalid", "source_ref requires a selection",
                                  retryable=True, next_action="use bytes or literal JSON selection")
            if not internal and len(raw) > 2_000_000:
                raise HostOpError("artifact_selection_invalid", "artifact exceeds full read bound",
                                  retryable=True, next_action="use a paginated bytes selection")
            try:
                return {"path": str(path), "text": raw.decode("utf-8"),
                        "content_digest": _digest_bytes(raw), "source_ref": _source_ref(path, raw),
                        "read_complete": True, "source_complete": True}
            except UnicodeError as exc:
                raise HostOpError("artifact_corrupt", "artifact is not UTF-8", obj=str(path),
                                  retryable=True, next_action="inspect or correct the original encoding") from exc
        return _selected_artifact(path, raw, source_ref, selection, max_bytes)

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

    def _discard_prelaunch_owner(
        self, name: str, arguments: dict, exc: BaseException, *, newly_registered: bool
    ) -> None:
        """Release only an owner proven to have failed before launch.

        Delivery registers an intended operation before invoking the Host so a
        lost launch receipt remains observable. A narrow set of typed
        validation errors is the exception: those paths run before
        ``.delivery-ops/<id>.json`` can be created and must not leave a phantom
        owner that traps the stop loop.
        """

        if (
            not newly_registered
            or not isinstance(exc, HostOpError)
            or not ((name == "start_repair" and exc.code in _REPAIR_PRELAUNCH_ERROR_CODES)
                    or (name == "start_evaluation" and exc.code in {
                        "evaluation_handoff_stale", "cq_handoff_immutable"}))
        ):
            return
        operation_id = arguments.get("operation_id")
        if not isinstance(operation_id, str):
            return
        self.operation_ids.discard(operation_id)
        self.operation_kinds.pop(operation_id, None)
        self._save("active")

    def call_tool(self, name: str, arguments: dict, *, call_identity: str | None = None,
                  _model_view: bool = True) -> dict:
        result = self._call_tool_raw(name, arguments, call_identity=call_identity)
        if _model_view and name == "read_delivery_artifact" and result.get("ok"):
            data = result["data"]
            selection = arguments.get("selection")
            if selection is None or selection.get("kind") == "bytes":
                # A read result alone is not native reception. Retain its exact
                # interval until this native turn completes successfully.
                with self._state_lock:
                    self._decision_read_ranges.append({
                        "path": data["path"], "source_ref": data["source_ref"],
                        "range": data.get("returned_range", {
                            "offset": 0, "end": data["source_ref"]["byte_length"]}),
                    })
        if not _model_view or name not in _MODEL_QUERIES:
            return result
        # Keep the full result before constructing a model-only view. This
        # switch is a Python call-site option, never a model tool parameter.
        record = {"event": "delivery_tool_result", "tool": name,
                  "arguments": arguments, "result": result}
        offset, length = append_session_event(self.session_root, record)
        reference = self._journal_reference(offset, length)
        shape_valid = result.get("ok") is not True or isinstance(result.get("data"), dict)
        projected_paths = []
        if result.get("ok") is not True or not isinstance(result.get("data"), dict):
            view = copy.deepcopy(result)
            omitted = []
        else:
            data = result["data"]
            fields = _STATUS_FIELDS | ({"items"} if name == "get_pending_actions" else set())
            selected = {key: value for key, value in data.items() if key in fields}
            if name == "get_pending_actions":
                items = data.get("items")
                shape_valid = isinstance(items, list) and all(isinstance(item, dict) for item in items)
                if shape_valid:
                    selected = _decision_observation({"runs": {"query": {
                        "pending": {"ok": True, "data": selected}}}}, {})["runs"]["query"]["pending"]["data"]
                    projected_paths = [["data", "items", index, "available_actions"]
                        for index, item in enumerate(items) if item.get("type") == "cq_review"]
            omitted = sorted(data.keys() - selected.keys())
            view = {"ok": True, "data": selected}
        view.update(schema_version="delivery-tool-view/v1", evidence=reference,
                    coverage={"complete": shape_valid, "source_complete": not omitted and not projected_paths,
                              "limitations": [] if shape_valid else ["unexpected Host result shape; inspect original before deciding"],
                              "omitted_fields": omitted, "projected_paths": projected_paths,
                              "evidence": reference})
        return self._page_view(view, reference)

    def _call_tool_raw(self, name: str, arguments: dict, *, call_identity: str | None = None) -> dict:
        newly_registered_operation = False
        try:
            if name not in self._tools:
                raise ValueError("undeclared Delivery tool")
            if getattr(self, "recovery_pending", False) and self._permission(name) != "read":
                raise ValueError("DSH recovery reconciliation pending; effectful tools closed")
            if self.activity in {"pause_pending", "paused", "resume_pending"} and self._permission(name) in {
                    "production", "evaluation", "repair"}:
                raise ValueError("user pause pending/effective; no new work until confirmed resume")
            if name in HANDOFF_TOOL_NAMES:
                return self._material_tool(name, arguments)
            try:
                validate(arguments, self._tools[name]["inputSchema"])
            except ValidationError as exc:
                if name == "yield_delivery":
                    raise HostOpError("delivery_yield_invalid", exc.message,
                        retryable=True, next_action="correct the yield schema using the current input_id and bound object identities") from exc
                if exc.validator == "required":
                    missing = sorted(field for field in exc.validator_value if field not in exc.instance)
                    raise HostOpError("delivery_arguments_missing",
                        f"{name}: missing required parameters: {', '.join(missing)}",
                        obj=".".join(["arguments", *map(str, exc.absolute_path)]), retryable=True,
                        next_action=f"provide the named parameters according to the {name} tool schema and retry",
                        passthrough={"tool": name, "missing_parameters": missing}) from exc
                if name == "record_flow_confirmation":
                    field = ".".join(map(str, exc.absolute_path))
                    raise HostOpError("flow_confirmation_invalid", f"invalid confirmation field: {field}",
                        retryable=True,
                        next_action="use evidence_references as an array of strings, the current message_id/action, and status pending/effective/failed/unknown",
                        passthrough={"field": field, "rule": exc.validator,
                                     "expected": exc.validator_value}) from exc
                if name != "read_delivery_artifact":
                    raise
                raise HostOpError("artifact_selection_invalid", "invalid artifact read parameters",
                    retryable=True, next_action="use path, optional source_ref/selection and max_bytes 1..16384") from exc
            if name == "get_task_budget":
                return {"ok": True, "data": self.budget.show(audience="delivery") if self.budget else {
                    "mode": "starts", "budget_ref": None, "limitations": ["historical_start_authorization"]}}
            if name == "yield_delivery":
                try:
                    return self._yield_delivery(arguments)
                except ValueError as exc:
                    raise HostOpError("delivery_yield_binding_invalid", str(exc),
                        retryable=True, next_action="use the retained input_id and current session/run/request/operation bindings") from exc
            if name == "request_host_action":
                if "supervise" not in self.allowed_operations:
                    raise ValueError("Host handoff requires current supervision authorization")
                run_id = arguments["run_id"]
                if run_id not in self.run_ids:
                    raise ValueError("run is outside this Delivery session")
                # Re-reading an already journaled request is not a new Host action.
                # Preserve its identity even after the pending review/issue has closed.
                existing = host_action_state(self.session_root).get("requests", {}).get(arguments["request_id"])
                if existing is not None:
                    replay = copy.deepcopy(arguments)
                    if arguments["kind"] == "cq_review":
                        old_binding = existing.get("bindings", {})
                        required = {"review_id", "content_version", "content_digest", "question_ids"}
                        if (required <= arguments["bindings"].keys()
                                and all(old_binding.get(key) == value for key, value in arguments["bindings"].items())):
                            replay = {"request_id": arguments["request_id"], "run_id": run_id,
                                      "kind": "cq_review", "bindings": old_binding}
                    return {"ok": True, "data": request_host_action(
                        self.session_root, self.session_id, self.run_ids, self.authorization, replay)}
                # Validate against actual pending bindings, never model-selected CQ text.
                pending = self.call_tool("get_pending_actions", {"run_id": run_id}, _model_view=False)
                if not pending.get("ok"):
                    return pending
                binding = arguments["bindings"]
                kind = arguments["kind"]
                if kind == "platform_repair":
                    for ref in arguments.get("evidence_references", []):
                        if ref.get("material_id"):
                            try:
                                self.handoff_materials.authorize_ref("delivery", "runner", ref)
                                if self._is_private_cq_material(ref):
                                    raise MaterialError("material_forbidden", "private CQ material is not repair evidence")
                            except MaterialError as exc:
                                raise HostOpError("host_action_evidence_forbidden", str(exc),
                                    retryable=True, next_action="use an authorized public or technical reference") from exc
                items = pending.get("data", {}).get("items", [])
                required = (("review_id", "content_version", "content_digest", "question_ids")
                            if kind == "cq_review" else ("issue_id", "reporter_id", "control_epoch"))
                matches = [item for item in items
                           if item.get("type") == ("cq_review" if kind == "cq_review" else "issue_wait")
                           and all(binding.get(key) == item.get("bindings", {}).get(key)
                                   and key in binding for key in required)]
                if (kind == "cq_review" or binding.get("issue_id")) and not matches:
                    raise HostOpError("host_action_binding_stale", "current pending binding differs",
                        retryable=True, next_action="read current pending actions and use their exact binding")
                if kind == "cq_review":
                    allowed = {*required, "phase", "review_snapshot_ref", "draft_ref"}
                    if set(binding) - allowed:
                        raise ValueError("CQ handoff contains non-metadata fields")
                    if matches:
                        binding = {key: value for key, value in matches[0]["bindings"].items()
                                   if key in allowed}
                    arguments = {"request_id": arguments["request_id"], "run_id": run_id,
                                 "kind": kind, "bindings": binding}
                return {"ok": True, "data": request_host_action(
                    self.session_root, self.session_id, self.run_ids, self.authorization, arguments)}
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
                return {"ok": True, "data": self._read_artifact(**{("value" if key == "path" else key): value
                    for key, value in arguments.items()})}
            if name == "finish_delivery":
                self.work_result = arguments["conclusion"]
                results = {}
                for run_id in sorted(self.run_ids):
                    results[run_id] = self.call_tool("standby_run", {"run_id": run_id},
                                                     call_identity=call_identity)
                observation = self.observe()
                runs_closed = all(
                    x["status"].get("ok")
                    and x["status"].get("data", {}).get("lifecycle") == "standby"
                    for x in observation["runs"].values()
                )
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
                control = getattr(self, "_budget_control_message", None)
                if self.budget and (not self.conversation or (
                        control and arguments["message_id"] == control["request_id"])):
                    state = self.budget.show()
                    if (not control or arguments["message_id"] != control["request_id"]
                            or arguments["action"] != control["action"]
                            or control["epoch"] != state["epoch"]):
                        current = ({"message_id": control["request_id"], "action": control["action"],
                                    "epoch": control["epoch"]}
                                   if control and control["epoch"] == state["epoch"] else None)
                        raise HostOpError("budget_control_stale", "confirmation is not for the current budget control",
                            retryable=True,
                            next_action="use current_control with actual acknowledgements; if absent, wait for the current control message, do not guess an identity",
                            passthrough={"budget_epoch": state["epoch"], "current_control": current})
                    if arguments["status"] == "effective" and not arguments["evidence_references"]:
                        raise ValueError("effective requires acknowledgement references")
                    self.budget.record_control("delivery:" + self.session_id, control["epoch"],
                        arguments["status"], action=arguments["action"],
                        evidence_references=arguments["evidence_references"])
                    return {"ok": True, "data": {"status": arguments["status"]}}
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
            if self.budget and (name in _PRODUCTION or name in {
                    "start_evaluation", "start_repair", "submit_instruction", "answer_question",
                    "consult_team", "recover_provider"}):
                self.budget.require_available(operation=self._permission(name))
            if self._permission(name) in {"production", "evaluation", "repair"} and self.authorization_valid_until:
                from datetime import datetime, UTC
                deadline = datetime.fromisoformat(self.authorization_valid_until.replace("Z", "+00:00"))
                if deadline.tzinfo is None or datetime.now(UTC) >= deadline:
                    raise ValueError("original authorization expired; no automatic renewal")
            args = dict(arguments)
            if (name in {"submit_instruction", "standby_run", "complete_cq_acceptance", "resolve_issue"}
                    and args.get("request_id") is None):
                identity = (hashlib.sha256(_json_bytes([self.session_id, name, args, call_identity])).hexdigest()
                            if call_identity else uuid.uuid4().hex)
                args["request_id"] = "delivery-" + identity[:32]
            if "base_url" in inspect.signature(getattr(host_ops_mcp, name)).parameters:
                args["base_url"] = self.config.get("base_url")
            for key in ("run_id", "source_run_id", "write_tail_run_id"):
                value = args.get(key)
                if value and not (key == "run_id" and name == "start_run") and value not in self.run_ids:
                    raise ValueError("run is outside this Delivery session")
            if name == "freeze_cq":
                actions = host_action_state(self.session_root)
                reviews = [result for identity, result in actions["results"].items()
                    if result.get("status") == "completed"
                    and actions["requests"][identity].get("kind") == "cq_review"
                    and result.get("run_id") == args["run_id"]]
                if reviews:
                    result = max(reviews, key=lambda row: row["recorded_at"])
                    fields = []
                    if result["result_ref"]["path"].endswith(".json"):
                        metadata = self._read_artifact(
                            str(self.session_root / result["result_ref"]["path"]),
                            selection={"kind": "json", "paths": [["selected_scope_complete"]]})
                        fields = json.loads(metadata["text"])["fields"]
                    if any(field.get("found") and field.get("value") is False for field in fields):
                        raise HostOpError("cq_selected_scope_incomplete",
                            "Host review explicitly leaves selected CQ stages unfinished",
                            retryable=True,
                            next_action="continue the declared remaining CQ stages, then review and freeze the complete selected scope",
                            passthrough={"host_request_id": result["request_id"],
                                         "result_ref": result["result_ref"]})
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
                    if self.budget is None and limit is not None and args.get("run_id") not in self.run_ids and len(self.run_ids) >= limit:
                        raise ValueError("authorized production start limit exhausted")
                    for key in ("task", "profile", "scope", "model_profile", "task_overlay"):
                        if key in self.config and args.get(key, self.config[key]) != self.config[key]:
                            raise ValueError(f"{key} differs from the authorized launch configuration")
                    if args.get("task_overlay") != self.config.get("task_overlay"):
                        raise ValueError("task_overlay differs from the authorized launch configuration")
            if name == "start_evaluation" or (name == "resume_from_checkpoint" and args.get("mode") == "acceptance"):
                selected_runtime = self.config.get("evaluation_runtime", "codex")
                if args.get("runtime", selected_runtime) != selected_runtime:
                    raise ValueError("evaluation runtime differs from the selected binding")
                args["runtime"] = selected_runtime
                selected = self.config.get("evaluation_model_profile", self.config["model_profile"])
                if args.get("model_profile", selected) not in {None, selected}:
                    raise ValueError("evaluation model profile differs from the selected binding")
                args["model_profile"] = selected
            if self.budget and name in _PRODUCTION | {"start_evaluation"}:
                # This argument is absent from the model's tool schema.
                args["budget_ref"] = self.budget_ref
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
            if name == "get_team_work_board":
                args["_projection"] = "delivery"
            inspect.signature(operation).bind(**args)
            if name == "start_run":
                self.run_ids.add(args["run_id"])
                self._register_handoff_actor()
            elif name == "resume_from_checkpoint":
                self.run_ids.add(args["new_run_id"])
                self._register_handoff_actor()
            elif name in {"start_evaluation", "start_repair"}:
                newly_registered_operation = args["operation_id"] not in self.operation_ids
                self.operation_ids.add(args["operation_id"])
                self.operation_kinds[args["operation_id"]] = "repair" if name == "start_repair" else "evaluation"
            # Retain the intended binding even if launch acknowledgement is lost.
            if name not in _READ:
                self._save("active")
            data = operation(**args)
            if name not in _READ and data.get("status") == "submitted":
                data["receipt_tracking"] = {
                    "via": "host_observation", "request_id": data.get("request_id"),
                    "next_action": "yield_delivery and end this turn; program observation delivers the actual receipt; query only a concrete receipt gap or recovery"}
            if name == "get_run_events" and isinstance(data, dict):
                data = self._project_run_events(args["run_id"], data)
            if name == 'reconcile_write_state':
                proof = data.get('reconciliation', {})
                self.reconciled_runs.discard(args['run_id'])
                if data.get('readback_only') is True and proof.get('blocked') == [] and proof.get('scope_drift') == []:
                    self.reconciled_runs.add(args['run_id'])
            return {"ok": True, "data": data}
        except BudgetError as exc:
            return {"ok": False, "error": {"code": exc.code, "message": str(exc),
                    "retryable": True, "next_action": "reconcile the original task budget; preserve existing resources and receipts"}}
        except HostOpError as exc:
            self._discard_prelaunch_owner(
                name, arguments, exc, newly_registered=newly_registered_operation
            )
            return {"ok": False, "error": exc.as_envelope()}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self._discard_prelaunch_owner(
                name, arguments, exc, newly_registered=newly_registered_operation
            )
            return {"ok": False, "error": {"code": "delivery_contract", "message": str(exc)}}
        except Exception as exc:
            # Schema failures can contain the supplied instance. Keep them private.
            self._discard_prelaunch_owner(
                name, arguments, exc, newly_registered=newly_registered_operation
            )
            self._append("tool-errors.jsonl", {"tool": name, "error_type": type(exc).__name__})
            return {"ok": False, "error": {"code": "delivery_tool_failed", "message": "check tool schema and bound inputs"}}

    def observe(self) -> dict:
        return {"host_actions": host_action_state(self.session_root), "runs": {run_id: {
            "status": self.call_tool("get_run_status", {"run_id": run_id}, _model_view=False),
            "pending": self.call_tool("get_pending_actions", {"run_id": run_id}, _model_view=False),
            "events": self._observe_run_events(run_id),
            "request_ledger": self._observe_request_ledger(run_id),
        } for run_id in sorted(self.run_ids)}, "operations": {
            operation_id: self.call_tool("get_repair_status" if self.operation_kinds.get(operation_id) == "repair" else "get_evaluation_status", {"operation_id": operation_id}, _model_view=False)
            for operation_id in sorted(self.operation_ids)
        }, 'repair_verifications': {
            operation_id: self.call_tool('get_repair_verification_status', {'operation_id': operation_id})
            for operation_id in sorted(self.verification_ids)
        }}

    def _observe_request_ledger(self, run_id: str) -> dict:
        try:
            root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
            return {"ok": True, "data": self._read_artifact(
                str(root / "control/host-requests.jsonl"), internal=True)}
        except HostOpError as exc:
            return {"ok": False, "error": exc.as_envelope()}

    def _request_projection(self, run_id: str, ledger: dict) -> dict:
        from .host_ops import _receipt_outcome

        if ledger.get("ok") is not True:
            return ledger
        data = ledger.get("data", {})
        text = data.get("text", "")
        raw = text.encode("utf-8")
        entries, uncorrelated, limitations = {}, [], []
        offset = 0
        for line in raw.splitlines(keepends=True):
            locator = {"path": data.get("path"), "byte_offset": offset, "byte_length": len(line),
                       "source_ref": data.get("source_ref")}
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict) or not line.endswith(b"\n"):
                    raise ValueError("incomplete or non-object ledger line")
                request_id = entry.get("request_id")
                if not isinstance(request_id, str) or not request_id:
                    uncorrelated.append({"run_id": run_id, "action": entry.get("action"),
                        "content_digest": entry.get("content_digest"),
                        "outcome": "uncorrelated", "ledger_ref": locator,
                        "result": {"ok": False, "error": {
                            "code": "request_identity_missing", "object": "request_id",
                            "reason": "retained request has no identity for receipt correlation",
                            "retryable": True,
                            "next_action": "inspect ledger_ref and the original action admission, delivery "
                                "and consumption evidence; do not resend to manufacture an identity; "
                                "continue the original task on the current thread while unresolved"}}})
                else:
                    entries[request_id] = (entry, locator)
            except (ValueError, UnicodeError):
                limitations.append({"code": "request_ledger_corrupt", "ledger_ref": locator,
                                    "content_digest": _digest_bytes(line)})
            offset += len(line)
        receipts = {}
        try:
            root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
            receipt_path = root / "evidence/outer-input-receipts.jsonl"
            receipt_raw = receipt_path.read_bytes() if receipt_path.exists() else b""
            receipt_ref = _source_ref(receipt_path, receipt_raw)
            offset = 0
            for line in receipt_raw.splitlines(keepends=True):
                try:
                    receipt = json.loads(line)
                    if not isinstance(receipt, dict) or not line.endswith(b"\n"):
                        raise ValueError("partial receipt line")
                    if isinstance(receipt.get("request_id"), str):
                        receipts[receipt["request_id"]] = (receipt, {
                            "path": str(receipt_path), "byte_offset": offset,
                            "byte_length": len(line), "source_ref": receipt_ref})
                except (ValueError, UnicodeError):
                    limitations.append({"code": "request_receipt_corrupt", "byte_offset": offset,
                                        "source_ref": receipt_ref})
                offset += len(line)
        except (HostOpError, OSError) as exc:
            limitations.append({"code": "request_receipt_unavailable", "message": str(exc)})
        pending, settled = list(uncorrelated), []
        for request_id, (entry, locator) in entries.items():
            receipt, receipt_locator = receipts.get(request_id, (None, None))
            if receipt is not None:
                if entry.get("content_digest") != receipt.get("content_digest"):
                    result = {"ok": False, "error": {
                        "code": "request_id_conflict", "message": "ledger and receipt digest conflict",
                        "next_action": "inspect the original ledger and receipt before resending"}}
                else:
                    result = {"ok": True, "data": _receipt_outcome(run_id, request_id, receipt)}
                    # Preserve additional rejection facts, including the exact
                    # message/retry binding, without redefining receipt outcome.
                    if result["data"]["outcome"] == "rejected":
                        result["data"]["receipt"] = receipt
            else:
                result = self.call_tool("get_request_result", {"run_id": run_id, "request_id": request_id}, _model_view=False)
                if isinstance(result.get("data"), dict):
                    result = copy.deepcopy(result)
                    result["data"].pop("observed_at", None)
            item = {"run_id": run_id, "request_id": request_id, "action": entry.get("action"),
                    "content_digest": entry.get("content_digest"), "result": result,
                    "ledger_ref": locator, "receipt_ref": receipt_locator}
            if result.get("ok") and result.get("data", {}).get("outcome") in {"accepted", "rejected"}:
                settled.append(item)
            else:
                pending.append(item)
        return {"ok": True, "data": {"pending": pending, "settled": settled,
            "coverage": {"total": len(entries) + len(uncorrelated), "complete": not limitations},
            "limitations": limitations}}

    def _locate_decision_events(self, run_id: str, events: list) -> None:
        """Use source bytes, never the incremental page's local line number."""
        try:
            root, _ = resolve_run_root(run_id, repository_root=self.repository_root)
        except HostOpError:
            return
        sources = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            source, offset = event.get("source"), event.get("byte_offset")
            if not isinstance(source, str) or Path(source).name != source or type(offset) is not int:
                continue
            path = root / "evidence" / source
            if not path.resolve().is_relative_to(root.resolve()):
                continue
            try:
                if source not in sources:
                    sources[source] = path.read_bytes()
                raw = sources[source]
                if not 0 <= offset < len(raw):
                    continue
                end = raw.find(b"\n", offset)
                if end < 0:
                    event["source_limitation"] = "partial source line; not a complete event"
                    continue
                end += 1
                event["byte_length"] = end - offset
                event["source_ref"] = _source_ref(path, raw)
                event["selection"] = {"kind": "bytes", "offset": offset, "length": end - offset}
            except OSError:
                event["source_limitation"] = "original event source unavailable; preserve observation"

    def _journal_reference(self, offset: int, length: int) -> dict:
        journal = self.session_root / "session-events.jsonl"
        with journal.open("rb") as handle:
            raw = handle.read(offset + length)
        return {"path": str(journal), "source_ref": _source_ref(journal, raw),
                "selection": {"kind": "bytes", "offset": offset, "length": length}}

    def _task_context(self) -> dict:
        context = {key: self.config[key] for key in (
            "objective", "goal", "delivery_objective", "authorization_budget",
            "initial_run_id", "freeze_started_at",
            "task", "profile", "scope", "task_overlay", "allowed_sources",
            "readback_scope", "readback_scopes",
            "model_profile", "evaluation_model_profile", "evaluation_runtime", "business_input_role",
            "production_start_limit", "incremental_request_id", "incremental_run_id",
            "deadline", "model_context_window", "model_auto_compact_token_limit",
            "phase_thread_boundaries",
        ) if key in self.config}
        timing = self.config.get("efficiency_round")
        if timing:
            context["efficiency_round"] = {key: timing[key] for key in
                ("identity", "started_at", "start_reference") if key in timing}
        context["quota_remaining"] = "unknown; use original authorization and round records"
        if self.budget:
            context["resource_authorization"] = self.resource_authorization
            context["quota_remaining"] = "amount mode; use get_task_budget, counts are analytics only"
        return context

    def _recovery_context(self) -> dict:
        if self.conversation:
            history = self.conversation.snapshot()
            path = self.conversation.path
            return {"user_messages": [row for row in history["messages"]
                        if row["dispatch"] != "published"],
                    "pending_questions": history["pending_questions"],
                    "history_complete": history["history_complete"],
                    "read_error": history["read_error"],
                    "source_ref": _source_ref(path, path.read_bytes())}
        path = self.session_root / "user-input.jsonl"
        raw = path.read_bytes() if path.exists() else b""
        try:
            messages = [json.loads(line) for line in raw.splitlines()]
            return {"user_messages": messages, "history_complete": True,
                    "source_ref": _source_ref(path, raw)}
        except (ValueError, UnicodeError):
            return {"history_complete": False, "read_error": "user_input_corrupt",
                    "source_ref": _source_ref(path, raw)}

    def _yield_delivery(self, arguments: dict) -> dict:
        if arguments["input_id"] not in self._input_ids:
            raise ValueError("input_id is outside this session's retained decision inputs")
        # Validate before persisting a continuation; a bad time is recoverable.
        next_review = arguments.get("next_review_at")
        try:
            StatusReview(self._status_review.interval, _utc_now()).defer(next_review)
        except ValueError as exc:
            raise HostOpError("delivery_next_review_invalid", str(exc), obj="next_review_at",
                retryable=True, next_action="correct next_review_at using an ISO timestamp with timezone and retry") from None
        actions = host_action_state(self.session_root)
        for waiting in arguments["waiting_for"]:
            run_id = waiting.get("run_id")
            operation_id = waiting.get("operation_id")
            host_id = waiting.get("host_request_id")
            request_id = waiting.get("request_id")
            if not any((run_id, operation_id, host_id, request_id)):
                raise ValueError("waiting_for requires an actual bound object identity")
            if run_id and run_id not in self.run_ids:
                raise ValueError("waiting run is outside this session")
            invalid_owner = (
                operation_id and operation_id not in self.operation_ids | self.verification_ids
                or host_id and (host_id not in actions.get("requests", {})
                               or run_id and actions["requests"][host_id].get("run_id") != run_id)
            )
            if invalid_owner and run_id and request_id:
                current = self._request_projection(run_id, self._observe_request_ledger(run_id))
                data = current.get("data", {})
                if any(item.get("request_id") == request_id
                       for item in data.get("pending", []) + data.get("settled", [])):
                    corrected = [{key: value for key, value in item.items()
                                  if item is not waiting or key not in {"operation_id", "host_request_id"}}
                                 for item in arguments["waiting_for"]]
                    raise HostOpError("delivery_yield_binding_invalid",
                        "this is a retained run request, not an operation or Host action",
                        retryable=True, next_action="retry with corrected_waiting_for; follow the actual request receipt",
                        passthrough={"corrected_waiting_for": corrected})
            if operation_id and operation_id not in self.operation_ids | self.verification_ids:
                raise ValueError("waiting operation is outside this session")
            if host_id and (host_id not in actions.get("requests", {}) or (
                    run_id and actions["requests"][host_id].get("run_id") != run_id)):
                raise ValueError("waiting Host request is outside the bound session/run")
            result = actions.get("results", {}).get(host_id, {})
            if result.get("status") == "completed":
                raise HostOpError("delivery_host_action_completed",
                    "the Host request is complete, not pending", retryable=True,
                    next_action="read the bound Host result and continue remaining work; remove this completed Host request from waiting_for",
                    passthrough={"host_request_id": host_id, "result_ref": result["result_ref"]})
            if request_id:
                requests = self._last_current.get("runs", {}).get(run_id, {}).get("requests", {}).get("data", {})
                matched = next((item for item in requests.get("pending", []) + requests.get("settled", [])
                                if item.get("request_id") == request_id), None)
                known = matched is not None
                if run_id and not known:
                    # A just-submitted request may predate the next program
                    # observation. Reconcile its real ledger here, rather than
                    # requiring an LLM status poll merely to register the wait.
                    current = self._request_projection(run_id, self._observe_request_ledger(run_id))
                    data = current.get("data", {})
                    matched = next((item for item in data.get("pending", []) + data.get("settled", [])
                                    if item.get("request_id") == request_id), None)
                    known = matched is not None
                if not run_id or not known:
                    raise ValueError("waiting request requires its retained run/request binding")
                receipt = matched.get("result", {}).get("data", {})
                if receipt.get("outcome") == "rejected":
                    raise HostOpError("delivery_wait_already_rejected", "the request has a final rejection, not an in-flight receipt",
                        retryable=True, next_action="handle the rejection and current run state; wait only on work that remains pending",
                        passthrough={"run_id": run_id, "request_id": request_id, "receipt": receipt})
        record = {"event": "delivery_yield", "session_id": self.session_id,
                  "recorded_at": now(), **copy.deepcopy(arguments)}
        offset, length = append_session_event(self.session_root, record)
        self.last_yield = record
        self._status_review.defer(next_review)
        self._save("active")
        if "thread_boundary" in arguments:
            self.pending_thread_handoff = record if arguments["thread_boundary"] else None
        return {"ok": True, "data": {"status": "waiting_recorded", "end_current_turn": True,
            "evidence": self._journal_reference(offset, length),
            "note": "End this turn now. All bindings remain under program observation; this is not turn completion."}}

    def _phase_thread_run_blocker(self) -> dict | None:
        """Keep unsafe state in scope without requiring a ledger before startup."""
        for run_id, run in self._last_current.get("runs", {}).items():
            requests = run.get("requests", {})
            status = run.get("status", {})
            data = status.get("data", {})
            if status.get("ok") is not True:
                return {"run_id": run_id, "code": "run_status_unavailable"}
            if data.get("write_phase") in {"unknown", "writing", "applying"}:
                return {"run_id": run_id, "code": "write_phase_unsettled"}
            if requests.get("ok") is not True:
                # A failed startup never created this ledger. Cleanup and the
                # absence of semantic starts are observed facts, not an empty
                # fabricated request history. Retain the original error.
                state = data.get("recorded_state") or {}
                if (requests.get("error", {}).get("code") == "artifact_unavailable"
                        and state.get("state") == "CLEANED"
                        and state.get("has_cleanup_record") is True
                        and data.get("semantic_progress", {}).get("semantic_start_count") == 0):
                    continue
                return {"run_id": run_id,
                        "code": requests.get("error", {}).get("code", "request_ledger_unavailable")}
            if requests.get("data", {}).get("coverage", {}).get("complete") is not True:
                return {"run_id": run_id, "code": "request_coverage_incomplete"}
            for item in requests.get("data", {}).get("pending", []):
                result = item.get("result", {})
                if result.get("ok") is not True or result.get("data", {}).get("outcome") != "rejected":
                    return {"run_id": run_id, "request_id": item.get("request_id"),
                            "code": "request_unsettled"}
        return None

    def _phase_thread_handoff(self) -> dict | None:
        """Surface the enabled natural boundary where Delivery must record its handoff."""
        enabled = self.config.get("phase_thread_boundaries", [])
        current = self._last_current
        for phase in ("acceptance", "production"):
            if phase not in enabled:
                continue
            for run_id, run in current.get("runs", {}).items():
                if any(row.get("run_id") == run_id and row.get("phase") == phase
                       and row.get("status") in {"switched", "attempted"}
                       for row in self.phase_thread_history):
                    continue
                requests = run.get("requests", {})
                if (requests.get("ok") is not True
                        or requests.get("data", {}).get("coverage", {}).get("complete") is not True):
                    continue
                settled = [row for row in requests.get("data", {}).get("settled", [])
                           if row.get("result", {}).get("data", {}).get("outcome") == "accepted"]
                if phase == "production" and any(
                        row.get("action") == "cq_handoff_complete" for row in settled):
                    continue
                action = "cq_handoff_complete" if phase == "acceptance" else "cq_freeze"
                matches = [row for row in settled if row.get("action") == action]
                if not matches:
                    continue
                for blocked_run_id, blocked_run in current.get("runs", {}).items():
                    for item in blocked_run.get("requests", {}).get("data", {}).get("pending", []):
                        if item.get("outcome") == "uncorrelated":
                            return {"status": "deferred", "phase": phase, "run_id": run_id,
                                "blocker": {"run_id": blocked_run_id,
                                    "code": "request_identity_missing", "ledger_ref": item["ledger_ref"]},
                                "next_action": "follow the unresolved request feedback; keep the current "
                                    "thread and do not repeat the handoff or resend the original action"}
                request_id = matches[-1]["request_id"]
                hint = {"thread_boundary": {"phase": phase, "run_id": run_id,
                                            "request_ids": [request_id]},
                        "next_action": "include thread_boundary in yield_delivery, retain effective decisions, then end this turn"}
                if phase == "acceptance":
                    if not any(key in self.operation_ids and value.get("ok") is True
                               and value.get("data", {}).get("run_id") == run_id
                               and value.get("data", {}).get("mode") == "cq-acceptance"
                               and value.get("data", {}).get("status") in {"running", "exited", "standby"}
                               for key, value in current.get("operations", {}).items()):
                        continue
                else:
                    following = settled[settled.index(matches[-1]) + 1:]
                    notifications = [row["request_id"] for row in following
                                     if row.get("action") == "instruction"]
                    if not notifications:
                        continue
                    hint["notification_request_ids"] = notifications
                    hint["next_action"] = (
                        "add the actual accepted freeze-notification instruction request_id to "
                        "thread_boundary.request_ids, retain effective decisions in yield_delivery, "
                        "then end this turn; do not select an unrelated instruction")
                blocker = self._phase_thread_run_blocker()
                if blocker:
                    return {"status": "deferred", "phase": phase, "run_id": run_id,
                        "blocker": blocker,
                        "next_action": "reconcile the identified run's status, ledger or pending receipt; "
                            "keep the current thread and do not resend the handoff"}
                return hint
        return None

    def maybe_switch_phase_thread(self, runtime, *, pending_inputs=()) -> bool:
        """Honor an explicit phase handoff only after the original activity settles."""
        handoff = self.last_yield or {}
        pending = self.pending_thread_handoff or {}
        boundary = pending.get("thread_boundary") or {}
        phase, run_id = boundary.get("phase"), boundary.get("run_id")
        if (phase not in self.config.get("phase_thread_boundaries", [])
                or runtime.busy or pending_inputs
                or any(item["delivery_status"] in {"unknown", "attempted"}
                       for item in self._pending_decisions)
                or self.activity != "active" or self.recovery_pending
                or handoff.get("input_id") != self._last_received_input_id):
            return False
        if any(row.get("run_id") == run_id and row.get("phase") == phase and (
                row.get("status") in {"switched", "attempted"}
                or row.get("input_id") == handoff["input_id"])
                for row in self.phase_thread_history):
            return False
        recovery = self._recovery_context()
        if not recovery.get("history_complete") or any(
                row.get("dispatch") in {"pending", "dispatch_started", "unknown"}
                for row in recovery.get("user_messages", [])):
            return False
        current = self._last_current
        if self._phase_thread_run_blocker():
            return False
        run = current.get("runs", {}).get(run_id, {})
        settled = {item["request_id"]: item for item in
                   run.get("requests", {}).get("data", {}).get("settled", [])
                   if item.get("result", {}).get("data", {}).get("outcome") == "accepted"}
        ids = boundary.get("request_ids", [])
        if not ids or any(request_id not in settled for request_id in ids):
            return False
        actions = {settled[request_id].get("action") for request_id in ids}
        if phase == "production":
            if not {"cq_freeze", "instruction"} <= actions:
                return False
        else:
            operations = [value.get("data", {}) for key, value in current.get("operations", {}).items()
                if key in self.operation_ids and value.get("ok") is True
                and value.get("data", {}).get("run_id") == run_id
                and value.get("data", {}).get("mode") == "cq-acceptance"
                and value.get("data", {}).get("status") in {"running", "exited", "standby"}]
            if "cq_handoff_complete" not in actions or not operations:
                return False
        record = {"event": "delivery_phase_thread", "attempt_id": uuid.uuid4().hex,
                  "phase": phase, "run_id": run_id, "input_id": handoff["input_id"],
                  "requested_input_id": pending["input_id"],
                  "from_identity": copy.deepcopy(runtime.identity), "status": "attempted",
                  "reason": handoff["reason"], "request_ids": ids, "started_at": now()}
        self.phase_thread_history.append(record)
        self._append("session-events.jsonl", record)
        # A failed or uncertain creation still needs a new explicit request;
        # ordinary waits must not hot-retry the same native session creation.
        self.pending_thread_handoff = None
        try:
            identity = runtime.new_thread()
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__, ended_at=now())
            self._append("session-events.jsonl", record)
            self._save("active")
            return False
        record.update(status="switched", to_identity=identity, ended_at=now())
        self.runtime_identity = identity
        self.native_thread_id = runtime.thread_id
        self._append("session-events.jsonl", record)
        # Reuse the full last observation and original messages, not a model
        # summary. A new input owns its own acknowledgement and paging offsets.
        raw = json.loads((self.session_root / "observation.json").read_text())["data"]
        self.record_observation(raw, force_delivery=True)
        self._bootstrap_observation()
        return True

    def _deadline_events(self, observation: dict) -> list[dict]:
        # A fixed due state participates in the existing digest and durable input
        # queue. No timer, inferred heartbeat timeout, action replay or renewal.
        due = []
        def check(kind, identity, value):
            if value is None:
                return
            try:
                deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    raise ValueError("deadline must include a timezone")
                if _utc_now() >= deadline:
                    due.append({"kind": kind, **identity, "deadline": value,
                        "next_action": "reconcile unfinished work and current authorization; do not replay writes"})
            except (ValueError, TypeError, AttributeError):
                due.append({"kind": "deadline_invalid", "deadline_kind": kind,
                            **identity, "value": value, "next_action": "correct the explicit deadline"})
        check("authorization_expired", {"session_id": self.session_id}, self.authorization_valid_until)
        check("task_deadline_reached", {"session_id": self.session_id}, self.config.get("deadline"))
        for operation_id, envelope in observation.get("operations", {}).items():
            data = envelope.get("data", {})
            timeout = (data.get("request_binding") or {}).get("session_timeout")
            if (data.get("status") != "running" or data.get("work_state") == "completed"
                    or type(timeout) not in (int, float) or timeout <= 0 or not data.get("started_at")):
                continue
            try:
                started = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
                check("operation_timeout", {"operation_id": operation_id},
                      (started + timedelta(seconds=timeout)).isoformat())
            except (ValueError, TypeError, OverflowError):
                due.append({"kind": "deadline_invalid", "operation_id": operation_id,
                            "started_at": data["started_at"], "session_timeout": timeout})
        return due

    def _input_view_path(self, input_id: str) -> Path:
        return self.session_root / "decision-views" / (
            hashlib.sha256(input_id.encode()).hexdigest() + ".json")

    def _page_view(self, payload: dict, reference: dict, *, offset: int = 0,
                   frozen_path: Path | None = None) -> dict:
        # Transport acknowledgement and newer-state locators can change during
        # paging. Keep them outside the stable JSON whose offsets we acknowledge.
        encoded = _json_bytes({key: value for key, value in payload.items()
                               if key not in {"delivery_status", "current_state"}})
        if frozen_path is not None:
            if frozen_path.exists():
                encoded = frozen_path.read_bytes()
                payload = {**json.loads(encoded), **{key: payload[key] for key in
                           ("delivery_status", "current_state") if key in payload}}
            else:
                frozen_path.parent.mkdir(exist_ok=True)
                frozen_path.write_bytes(encoded)
        if offset == 0 and len(json.dumps(payload, ensure_ascii=False).encode()) <= 31800:
            return payload
        text, end = _utf8_page(encoded, offset, 12000)
        # Supplemental reads must continue this same model-facing projection.
        # The journal reference still identifies the complete raw evidence, but
        # reading it by default would restore snapshots and internal fingerprints.
        directory = self.session_root / "decision-views"
        directory.mkdir(exist_ok=True)
        path = frozen_path or directory / (
            _digest_bytes(encoded).removeprefix("sha256:") + ".json")
        if not path.exists():
            path.write_bytes(encoded)
        view = {"path": str(path), "source_ref": _source_ref(path, encoded),
                "selection": {"kind": "bytes", "offset": 0, "length": len(encoded)}}
        return {"schema_version": payload["schema_version"],
                **{key: payload[key] for key in ("input_id", "mode", "delivery_status", "current_state")
                   if key in payload},
                "evidence": reference,
                "page": {"text": text, "offset": offset, "next_offset": end,
                         "note": "partial JSON; collect pages or continue with read_remaining before using unreturned facts"},
                "coverage": {"complete": end == len(encoded), "total_bytes": len(encoded),
                             "returned_bytes": end - offset, "source_complete": False,
                             "remaining_bytes": len(encoded) - end},
                "delivery_range": {"next_offset": end, "complete": end == len(encoded)},
                "read_original": view,
                "read_remaining": {**view, "selection": {"kind": "bytes", "offset": end,
                                                        "length": len(encoded) - end}}}

    def _bootstrap_observation(self) -> dict:
        # The newest forced input belongs to this bootstrap only. Historical
        # pending inputs and conversation dispatch positions remain untouched.
        item = self._pending_decisions[-1]
        self._bootstrap_input_id = item["input_id"]
        return self._model_observation(_item=item, _bootstrap=True)

    def _restore_decision_inputs(self) -> None:
        self._pending_decisions = []
        # Unconfirmed tool results deliberately do not survive process recovery.
        # Only the durable native completion receipt below advances reception.
        self._decision_read_ranges = []
        self._last_current = {}
        self._decision_event_state = {}
        self._input_ids = set()
        self._latest_input_id = None
        self._last_received_input_id = None
        self.last_yield = None
        self.pending_thread_handoff = None
        review_records = []
        path = self.session_root / "session-events.jsonl"
        if not path.exists():
            return
        offset = 0
        for line in read_session_journal(self.session_root).splitlines(keepends=True):
            try:
                record = json.loads(line)
            except ValueError:
                raise ValueError(f"session journal is corrupt at byte {offset}; preserve and repair it")
            event = record.get("event")
            if "status_review" in record:
                self._status_review = StatusReview(self._status_review.interval, _utc_now(), record["status_review"])
            if event == "delivery_review_observation":
                record["journal_offset"], record["journal_length"] = offset, len(line)
                review_records.append(record)
            elif event == "delivery_review_confirmed":
                self._status_review.confirm(record["window"])
            if "event_cursors" in record:
                self._event_cursors.update(record["event_cursors"])
            if event == "delivery_decision_input":
                self._latest_input_id = record["input_id"]
                self._input_ids.add(record["input_id"])
                self._pending_decisions.append({"input_id": record["input_id"], "byte_offset": offset,
                    "byte_length": len(line), "offset": 0, "delivery_status": "pending",
                    "trigger": record.get("trigger", {"kind": "recovery"}),
                    "review_window": record.get("periodic_review", {}).get("window")})
                self._last_current = record["fingerprint_state"]
                self._last_decision_digest = record["decision_digest"]
                self._event_cursors.update(record.get("event_cursors", {}))
                self._decision_event_state = {
                    key: {"seen": set(value["seen"]), "chain": value["chain"],
                          "problem_states": value.get("problem_states", {}),
                          "native_tool_calls": value.get("native_tool_calls", {})}
                    for key, value in record.get("decision_event_state", {}).items()}
            elif event == "delivery_yield":
                self.last_yield = record
                if "thread_boundary" in record:
                    self.pending_thread_handoff = record if record["thread_boundary"] else None
            elif event in {"delivery_inputs_coalesced", "delivery_review_superseded"}:
                replaced = set(record["input_ids"])
                self._pending_decisions = [item for item in self._pending_decisions
                                           if item["input_id"] not in replaced]
            elif event == "delivery_phase_thread":
                self.phase_thread_history = [row for row in self.phase_thread_history
                    if row["attempt_id"] != record["attempt_id"]] + [record]
                self.pending_thread_handoff = None
            elif event == "delivery_input_dispatch":
                if record["status"] == "accepted":
                    self._last_received_input_id = record["input_id"]
                for item in list(self._pending_decisions):
                    if item["input_id"] != record["input_id"]:
                        continue
                    item["delivery_status"] = record["status"]
                    if record["status"] == "accepted":
                        if record["complete"]:
                            self._pending_decisions.remove(item)
                        else:
                            # A v1 page offset cannot index a v2 projection.
                            # Resending facts from zero never replays actions.
                            item["offset"] = (record["next_offset"] if
                                record.get("view_schema_version") == "delivery-decision-input/v2" else 0)
            offset += len(line)
        # An attempt without a durable acknowledgement is uncertain, including
        # interruption between native acceptance and journal persistence.
        for item in self._pending_decisions:
            if item["delivery_status"] == "attempted":
                item["delivery_status"] = "unknown"
        self._status_review.records = [row for row in review_records
            if row["seq"] > self._status_review.confirmed_seq]
        # An interrupted process cannot confirm a previous activity by ending a
        # later one. Unconfirmed source ranges remain in the next overview.
        self._status_review.inflight = {}

    def _periodic_review(self, *, bootstrap: bool = False) -> dict:
        review = self._status_review.summary()
        records = self._status_review.records
        if records:
            start = records[0]["journal_offset"]
            end = records[-1]["journal_offset"] + records[-1]["journal_length"]
            review["read_observations"] = self._journal_reference(start, end - start)
        roles = []
        for run_id in sorted(self.run_ids):
            current = self.call_tool("get_team_work_board", {"run_id": run_id}, _model_view=False)
            if current.get("ok") is not True:
                roles.append({"run_id": run_id, "report_status": "unavailable", "error": current.get("error")})
                review["window"]["complete"] = False
                continue
            board = current["data"]
            source = board.get("source_ref")
            cards = list(board.get("cards", []))
            coverage = [{"view": "current", "limitations": board["limitations"]}]
            current_complete = not (set(board.get("limitations", [])) - {"work_board_not_recorded"})
            # Keep the same immutable prefix across all pages of this view.
            cursor = board.get("continuation")
            while cursor:
                page = self.call_tool("get_team_work_board", {"run_id": run_id, "cursor": cursor}, _model_view=False)
                if page.get("ok") is not True:
                    current_complete = False
                    coverage.append({"view": "current", "error": page.get("error"),
                        "read_remaining": {"run_id": run_id, "cursor": cursor}})
                    break
                if set(page["data"].get("limitations", [])) - {"work_board_not_recorded"}:
                    current_complete = False
                    coverage.append({"view": "current", "limitations": page["data"]["limitations"]})
                cards.extend(page["data"].get("cards", []))
                cursor = page["data"].get("continuation")
            current_cursor = cursor
            after = self._status_review.confirmed_sources.get("work_board:" + run_id, {}).get("max_record_seq", 0)
            arguments = {"run_id": run_id, "view": "history", "after_record_seq": after}
            if source:
                arguments["source_ref"] = source
            history = self.call_tool("get_team_work_board", arguments, _model_view=False)
            counts = {}
            transitions = []
            history_complete = True
            while True:
                if history.get("ok") is not True:
                    history_complete = False
                    coverage.append({"error": history.get("error"), "read_remaining": arguments})
                    break
                data = history["data"]
                for row in data.get("history", []):
                    actor = row.get("actor_id", "unknown")
                    facts = counts.setdefault(actor, {"count": 0, "changed_fields": {}})
                    facts["count"] += 1
                    for field in row.get("changed_fields") or []:
                        facts["changed_fields"][field] = facts["changed_fields"].get(field, 0) + 1
                    # Only short typed transitions, never peer/private bodies.
                    if row.get("kind") != "card":
                        transitions.append({key: row[key] for key in (
                            "record_seq", "actor_id", "kind", "request_id", "requester_state",
                            "assignee_report", "recorded_at") if key in row})
                if set(data.get("limitations", [])) - {"work_board_not_recorded"}:
                    history_complete = False
                    coverage.append({"limitations": data["limitations"]})
                cursor = data.get("continuation")
                if not cursor:
                    break
                arguments = {**arguments, "cursor": cursor}
                history = self.call_tool("get_team_work_board", arguments, _model_view=False)
            if not history_complete or not current_complete:
                review["window"]["complete"] = False
            if source and history_complete and current_complete and not cursor:
                review["window"]["through_sources"]["work_board:" + run_id] = source
            if not bootstrap:
                cards = [{**{key: value for key, value in card.items() if key != "card"},
                          "unchanged": True,
                          "read_version": {"run_id": run_id, "view": "version",
                              "agent_id": card["agent_id"], "record_seq": card["record_seq"],
                              "source_ref": source}}
                         if card.get("card") and card.get("record_seq", after + 1) <= after else card
                         for card in cards]
            roles.append({"run_id": run_id, "cards": cards, "changes_by_actor": counts,
                "transitions": transitions, "coverage": coverage,
                "source_ref": source, "current_continuation": current_cursor,
                "read_history": {"run_id": run_id, "view": "history",
                                 "after_record_seq": after, "source_ref": source}})
        review["roles"] = roles
        review["coverage"]["complete"] = review["window"]["complete"]
        review["review_id"] = uuid.uuid4().hex
        return review

    def _next_decision(self) -> dict | None:
        uncertain = next((item for item in self._pending_decisions
            if item["delivery_status"] in {"attempted", "unknown"}), None)
        if uncertain:
            return uncertain
        critical = [item for item in self._pending_decisions
            if item.get("trigger", {}).get("kind") in {"initial", "recovery", "critical_event"}]
        return next((item for item in critical if not item["offset"]),
            critical[0] if critical else self._pending_decisions[0] if self._pending_decisions else None)

    def record_observation(self, observation: dict, *, force_delivery: bool = False,
                           allow_periodic: bool = True) -> bool:
        path = self.session_root / "observation.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        projected = copy.deepcopy(observation)
        projected["host_actions"] = host_action_state(self.session_root)
        for run_id, run in projected.get("runs", {}).items():
            run["requests"] = self._request_projection(run_id, run.get("request_ledger", {}))
        projected["session"] = {"session_id": self.session_id,
            "authorization_reference": self.authorization,
            "authorization_valid_until": self.authorization_valid_until,
            "allowed_operations": sorted(self.allowed_operations), "activity": self.activity,
            "work_result": self.work_result, "flow_confirmation": self.flow_confirmation,
            "task_context": self._task_context()}
        if self.budget:
            state = self.budget.show(audience="delivery")
            projected["session"]["budget_control"] = {key: state.get(key) for key in
                ("budget_ref", "epoch", "admission_open", "pause_reasons", "authorized_amount")}
        projected["deadline_events"] = self._deadline_events(observation)
        decision = _decision_observation(projected, self._decision_event_state)
        # Appendix lengths/digests change with ordinary appends. The identity
        # of a specific request result is the receipt and ledger line itself.
        def remove_source_identity(value):
            if not isinstance(value, dict):
                return
            for item in value.get("data", {}).get("pending", []) + value.get("data", {}).get("settled", []):
                for key in ("ledger_ref", "receipt_ref"):
                    if isinstance(item.get(key), dict):
                        item[key].pop("source_ref", None)
        for run in decision.get("runs", {}).values():
            remove_source_identity(run.get("requests", {}))
        events = [(run_id, event) for run_id, run in observation.get("runs", {}).items()
                  for event in run.get("events", {}).get("data", {}).get("events", [])]
        # The aggregate retains field transitions and exact original positions.
        # No raw dialogue, private review body or second model summary is copied.
        ordinary = copy.deepcopy(decision)
        for run_id, run in ordinary.get("runs", {}).items():
            run.pop("events", None)
            run.get("status", {}).get("data", {})["semantic_progress"] = copy.deepcopy(
                observation["runs"][run_id].get("status", {}).get("data", {}).get("semantic_progress"))
        changes = _value_changes(getattr(self, "_review_previous", {}), ordinary)
        self._review_previous = ordinary
        runtime_facts = {key: {field: value for field, value in run.get("status", {}).get("data", {}).items()
                              if field in {"last_verifiable_activity", "liveness", "current_role"}}
                         for key, run in observation.get("runs", {}).items()}
        row = self._status_review.record(changes, events, runtime_facts,
            {"events:" + key: value for key, value in self._event_cursors.items()},
            _digest_bytes(_json_bytes(ordinary)), _utc_now())
        if row:
            offset, length = append_session_event(self.session_root, row)
            row["journal_offset"], row["journal_length"] = offset, length
        gaps = {_json_bytes(item): item for record in self._status_review.records
                for item in record.get("limitations", [])}
        if gaps:
            projected["observation_gaps"] = list(gaps.values())
            decision["observation_gaps"] = list(gaps.values())
        digest = _digest_bytes(_json_bytes(decision))
        critical = digest != getattr(self, "_last_decision_digest", None)
        trigger = ("recovery" if self._resuming else "initial") if force_delivery or not self._last_current else (
            "critical_event" if critical else self._status_review.due(_utc_now()) if allow_periodic else None)
        if trigger in {"periodic_review", "followup_due"} and self._completed_observations_are_quiet():
            trigger = None
        # One outstanding ordinary overview is sufficient while paging or busy.
        if trigger in {"periodic_review", "followup_due"} and any(
                item.get("trigger", {}).get("kind") in {"periodic_review", "followup_due"}
                for item in self._pending_decisions):
            trigger = None
        changed = trigger is not None
        record = {"observation_count": previous.get("observation_count", 0) + 1,
                  "wake_count": previous.get("wake_count", 0) + int(changed),
                  "decision_digest": digest, "data": observation}
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(_json_bytes(record))
        temporary.replace(path)
        if changed:
            changed_operations = {collection: [key for key, value in decision.get(collection, {}).items()
                if self._last_current and value != self._last_current.get(collection, {}).get(key)]
                for collection in ("operations", "repair_verifications")}
            current = _decision_observation(projected, copy.deepcopy(self._decision_event_state))
            # Keep the actual incremental event bodies in the input, never
            # replace them with the cumulative fingerprint chain.
            excluded = 0
            for run_id, run in current.get("runs", {}).items():
                envelope = projected["runs"][run_id].get("events", {})
                if envelope.get("ok") is True:
                    envelope = copy.deepcopy(envelope)
                    page = envelope.get("data", {})
                    events = page.get("events", [])
                    page["events"] = copy.deepcopy(
                        self._decision_event_state.get(run_id, {}).get("selected", []))
                    excluded += len(events) - len(page["events"])
                    self._locate_decision_events(run_id, page["events"])
                run["events"] = envelope
            current["schema_version"] = "delivery-decision-input/v1"
            current["raw_observation"] = {"path": str(path), "reader": "read_delivery_artifact",
                "source_ref": _source_ref(path, _json_bytes(record)),
                "excluded_noise_event_records": excluded}
            changes = _value_changes(self._last_current, decision)
            request_results = []
            for run_id, run in current.get("runs", {}).items():
                previous_settled = {item["request_id"]: item.get("result") for item in self._last_current.get(
                    "runs", {}).get(run_id, {}).get("requests", {}).get("data", {}).get("settled", [])}
                for item in run.get("requests", {}).get("data", {}).get("settled", []):
                    result = item.get("result", {}).get("data", {})
                    if ((self._last_current and item.get("result") != previous_settled.get(item["request_id"]))
                            or ((force_delivery or not self._last_current)
                                and result.get("outcome") == "rejected")):
                        request_results.append({"run_id": run_id, "request_id": item["request_id"],
                            **{key: value for key, value in item.get("result", {}).get("data", {}).items()
                               if key in _STATUS_FIELDS}})
            input_id = uuid.uuid4().hex
            review = self._periodic_review(bootstrap=trigger in {"initial", "recovery"})
            self._status_review.scheduled(_utc_now())
            packet = {"event": "delivery_decision_input", "input_id": input_id,
                "recorded_at": now(),
                "trigger": {"kind": trigger}, "periodic_review": review,
                "mode": "bootstrap" if force_delivery or not self._last_current else "changes",
                "continuation": copy.deepcopy(self.last_yield),
                "recovery_context": self._recovery_context() if force_delivery or not self._last_current else None,
                "snapshot": current, "changes": changes, "fingerprint_state": decision,
                "changed_operations": changed_operations,
                "request_results": request_results,
                "decision_digest": digest, "event_cursors": self._event_cursors,
                "decision_event_state": {key: {"seen": sorted(value["seen"]), "chain": value["chain"],
                    "problem_states": value.get("problem_states", {}),
                    "native_tool_calls": value.get("native_tool_calls", {})}
                    for key, value in self._decision_event_state.items()}}
            offset, byte_length = append_session_event(self.session_root, packet)
            self._pending_decisions.append({"input_id": input_id, "byte_offset": offset,
                "byte_length": byte_length, "offset": 0, "delivery_status": "pending",
                "trigger": {"kind": trigger}, "review_window": review["window"]})
            self._input_ids.add(input_id)
            self._latest_input_id = input_id
        self._last_current = decision
        self._last_decision_digest = digest
        # Persist the cursor only after the full raw observation and change
        # packet have been saved; recovery can also read the journal first.
        self._save("active")
        return changed

    def _coalesce_pending_decisions(self) -> None:
        """Deliver current facts together with all changes not yet sent to the model.

        Partially received and uncertain inputs keep their own identity and
        offsets. Only observations known not to have been delivered are merged;
        the original journal and formal action receipts remain unchanged.
        """
        pending = [item for item in self._pending_decisions if not item["offset"]
                   and item["delivery_status"] in {"pending", "deferred_budget", "rejected"}]
        if len(pending) < 2:
            return
        packets = []
        with (self.session_root / "session-events.jsonl").open("rb") as handle:
            for item in pending:
                handle.seek(item["byte_offset"])
                packets.append(json.loads(handle.read(item["byte_length"])))
        merged = copy.deepcopy(packets[-1])
        bootstrap = any(packet.get("mode", "bootstrap") == "bootstrap" for packet in packets)
        merged.update(input_id=uuid.uuid4().hex, mode="bootstrap" if bootstrap else "changes",
                      recovery_context=self._recovery_context() if bootstrap else None,
                      coalesced_input_ids=[item["input_id"] for item in pending])
        critical_packet = next((packet for packet in reversed(packets)
            if packet.get("trigger", {}).get("kind") in {"initial", "recovery", "critical_event"}), None)
        if critical_packet:
            merged["trigger"] = critical_packet["trigger"]
        for key in ("changes", "request_results"):
            values = {}
            for packet in packets:
                for value in packet.get(key, []):
                    values[_json_bytes(value)] = value
            merged[key] = list(values.values())
        for run_id, run in merged["snapshot"].get("runs", {}).items():
            page = run.get("events", {}).get("data")
            events = {}
            for packet in packets:
                previous = packet["snapshot"].get("runs", {}).get(run_id, {})
                envelope = previous.get("events", {})
                if envelope.get("ok") is False:
                    merged["changes"].append({"path": ["runs", run_id, "events"],
                        "change": "updated", "value": envelope, "historical": True})
                for event in previous.get("events", {}).get("data", {}).get("events", []):
                    events[_json_bytes(event)] = event
            if isinstance(page, dict):
                page["events"] = list(events.values())
            elif events:
                merged["changes"].append({"path": ["runs", run_id, "events"],
                    "change": "updated", "value": {"ok": True, "data": {
                        "events": list(events.values())}}, "historical": True})
        for key in ("operations", "repair_verifications"):
            merged["changed_operations"][key] = list(dict.fromkeys(
                identity for packet in packets
                for identity in packet.get("changed_operations", {}).get(key, [])))
        offset, length = append_session_event(self.session_root, merged)
        replaced = merged["coalesced_input_ids"]
        self._append("session-events.jsonl", {"event": "delivery_inputs_coalesced",
            "input_ids": replaced, "replacement_input_id": merged["input_id"]})
        self._pending_decisions = [item for item in self._pending_decisions
                                   if item["input_id"] not in replaced]
        self._pending_decisions.append({"input_id": merged["input_id"], "byte_offset": offset,
            "byte_length": length, "offset": 0, "delivery_status": "pending",
            "trigger": merged.get("trigger", {}),
            "review_window": merged.get("periodic_review", {}).get("window")})
        if getattr(self, "_bootstrap_input_id", None) in replaced:
            self._bootstrap_input_id = merged["input_id"]
        self._input_ids.add(merged["input_id"])
        self._latest_input_id = merged["input_id"]

    def _model_observation(self, observation: Any = None, *, _item: dict | None = None,
                           _bootstrap: bool = False) -> dict:
        if not self._pending_decisions:
            if observation is not None:
                self.record_observation(observation)
            if not self._pending_decisions:
                return {"schema_version": "delivery-decision-input/v2", "coverage": {"complete": True}}
        self._coalesce_pending_decisions()
        if _item not in self._pending_decisions:
            _item = None
        item = _item or self._next_decision()
        journal = self.session_root / "session-events.jsonl"
        with journal.open("rb") as handle:
            raw = handle.read(item["byte_offset"] + item["byte_length"])
        packet = json.loads(raw[item["byte_offset"]:])
        reference = {"path": str(journal), "source_ref": _source_ref(journal, raw),
            "selection": {"kind": "bytes", "offset": item["byte_offset"], "length": item["byte_length"]}}
        snapshot = packet["snapshot"]
        def changed(parts):
            return any(tuple(change["path"][:len(parts)]) == parts
                       or parts[:len(change["path"])] == tuple(change["path"])
                       for change in packet["changes"])

        actions = snapshot.get("host_actions", {})
        history_ids = {item["request_id"] for item in actions.get("completed", [])
                       if not changed(("host_actions", "requests", item["request_id"]))
                       and not changed(("host_actions", "results", item["request_id"]))}
        actions["completed"] = [item for item in actions.get("completed", [])
                                if item["request_id"] not in history_ids]
        for collection in ("requests", "results"):
            actions[collection] = {key: value for key, value in actions.get(collection, {}).items()
                                   if key not in history_ids}
        actions["completed_index"] = {"total": len(history_ids), "returned": 0,
                                      "complete": not history_ids, "evidence": reference}
        for run in snapshot.get("runs", {}).values():
            data = run.get("requests", {}).get("data", {})
            history = data.pop("settled", [])
            data["settled_index"] = {"total": len(history), "returned": 0,
                                     "complete": not history, "evidence": reference}
        histories = {}
        for collection in ("operations", "repair_verifications"):
            history = []
            for key, envelope in list(snapshot.get(collection, {}).items()):
                data = envelope.get("data", {})
                terminal = (data.get("status") in {"exited", "stopped", "launch_failed"}
                            or data.get("process", {}).get("state") in {"exited", "stopped"}
                            or (data.get("work_state") == "completed"
                                and data.get("lifecycle") == "standby"))
                # Unqualified reports, failures and pending control/consult stay
                # actionable even after process exit. Never equate exit to PASS.
                qualified = ((data.get("report_binding") or {}).get("valid") is True
                             or (data.get("result") or {}).get("effect_verified") is True
                             or data.get("effect_verified") is True)
                control_pending = any(isinstance(value, dict) and value.get("status")
                    in {"pending", "unknown", "submitted"}
                    for value in (data.get("control_receipts") or {}).values())
                if (envelope.get("ok") is True and terminal and qualified and not control_pending
                        and key not in packet.get("changed_operations", {}).get(collection, [])):
                    history.append({"operation_id": key, "status": data.get("status"),
                        "report_binding": data.get("report_binding"), "result": data.get("result"),
                        "record_path": data.get("record_path")})
                    del snapshot[collection][key]
            histories[collection] = {"total": len(history), "returned": 0,
                                     "complete": not history, "evidence": reference}
        snapshot["operation_history"] = histories
        bootstrap = _bootstrap or packet.get("mode", "bootstrap") == "bootstrap"
        first_blockers = {}
        for key, run in snapshot.get("runs", {}).items():
            blocker = run.get("status", {}).get("data", {}).get("first_blocker")
            if not blocker:
                continue
            encoded_blocker = _json_bytes(blocker)
            if len(encoded_blocker) <= 2048:
                first_blockers[key] = blocker
            else:
                preview, _ = _utf8_page(encoded_blocker, 0, 512)
                first_blockers[key] = {"preview": preview, "preview_complete": False,
                    "total_bytes": len(encoded_blocker), "evidence": reference,
                    "packet_path": ["snapshot", "runs", key, "status", "data", "first_blocker"]}
                # The full body stays in bootstrap/changes and is paged there.
                # The always-present core must not repeat a large stable body.
        core = {**snapshot.get("session", {}),
                "runs": {key: {field: value for field, value in run.get("status", {}).get("data", {}).items()
                              if field in _STATUS_FIELDS - {"first_blocker"}}
                         for key, run in snapshot.get("runs", {}).items()},
                "operations": {key: {field: value for field, value in envelope.get("data", {}).items()
                                      if field in _STATUS_FIELDS}
                               for key, envelope in snapshot.get("operations", {}).items()},
                "first_blockers": first_blockers,
                "deadline_events": snapshot.get("deadline_events", [])}
        if packet["input_id"] == self._latest_input_id:
            handoff = self._phase_thread_handoff()
            if handoff:
                core = {"phase_thread_handoff": handoff, **core}
        objective_in_snapshot = "delivery_objective" in core.get("task_context", {})
        if not bootstrap and objective_in_snapshot:
            # The full Host task is supplied at bootstrap/recovery. Later
            # changes carry any updates; do not repeat its stable body.
            core["task_context"] = {key: value for key, value in core["task_context"].items()
                                    if key != "delivery_objective"}
        omitted_stable = []
        if not bootstrap and not changed(("session", "task_context")):
            core.pop("task_context", None)
            omitted_stable.append("unchanged_task_context")
        for run_id, status in core["runs"].items():
            if not bootstrap and not changed(("runs", run_id, "status", "data", "identity")):
                if "identity" in status:
                    status.pop("identity")
                    if "unchanged_run_identity" not in omitted_stable:
                        omitted_stable.append("unchanged_run_identity")
        unresolved = []
        def add(kind, value, path, **identity):
            if isinstance(value, dict):
                compact = {key: val for key, val in value.items() if key in {
                    "id", "request_id", "operation_id", "type", "kind", "status", "state",
                    "outcome", "bindings", "write_state", "content_digest"}}
            else:
                compact = {"status": "unknown", "limitation": "unexpected object; inspect original"}
            unresolved.append({"kind": kind, **identity, **compact, "packet_path": path})
        for run_id, run in snapshot.get("runs", {}).items():
            for index, value in enumerate(run.get("pending", {}).get("data", {}).get("items", [])):
                add("pending_action", value, ["snapshot", "runs", run_id, "pending", "data", "items", index],
                    run_id=run_id)
            requests = run.get("requests", {}).get("data", {}).get("pending", [])
            for index, value in enumerate(requests):
                add("request", value, ["snapshot", "runs", run_id, "requests", "data", "pending", index],
                    run_id=run_id)
                result = value.get("result", {})
                unresolved[-1]["outcome"] = result.get("data", {}).get("outcome", "unknown")
                unresolved[-1]["result"] = {key: value for key, value in result.get("data", {}).items()
                                            if key in _STATUS_FIELDS}
                if result.get("ok") is False:
                    unresolved[-1]["error"] = result.get("error")
            for kind in ("status", "pending", "requests", "events"):
                if run.get(kind, {}).get("ok") is False:
                    add("read_error", run[kind], ["snapshot", "runs", run_id, kind], run_id=run_id)
                    unresolved[-1]["error"] = run[kind].get("error")
        for collection in ("operations", "repair_verifications"):
            for key, envelope in snapshot.get(collection, {}).items():
                add(collection, envelope.get("data", envelope), ["snapshot", collection, key], operation_id=key)
                if envelope.get("ok") is False:
                    unresolved[-1]["error"] = envelope.get("error")
        for collection in ("pending", "unresolved"):
            for index, value in enumerate(actions.get(collection, [])):
                add("host_request", value, ["snapshot", "host_actions", collection, index])

        changes = []
        if not bootstrap or packet.get("coalesced_input_ids"):
            for change in packet["changes"]:
                parts = change["path"]
                # Event fingerprints are only wakeup bookkeeping. Deliver actual
                # event bodies from the authorized snapshot, never a chain hash.
                if len(parts) >= 3 and parts[0] == "runs" and parts[2] == "events":
                    if change.get("historical"):
                        changes.append(change)
                    continue
                if ("request_results" in packet and len(parts) >= 5
                        and parts[0] == "runs" and parts[2:5] == ["requests", "data", "settled"]):
                    continue  # New receipts are explicit; do not resend the entire settled list.
                if len(parts) == 2 and parts[0] == "runs" and change["change"] == "added":
                    change = {**change, "value": {key: value for key, value in
                              snapshot["runs"][parts[1]].items() if key != "events"}}
                changes.append(change)
            for run_id, run in snapshot.get("runs", {}).items():
                if changed(("runs", run_id, "events")):
                    changes.append({"path": ["runs", run_id, "events"], "change": "updated",
                                    "value": run.get("events", {})})
        review = copy.deepcopy(packet.get("periodic_review"))
        if review:
            # Current cards, retry results and coverage gaps remain visible.
            # Ordinary activity positions/bodies are available in the retained
            # packet instead of being reread before every decision's core.
            counts = {}
            activity = review.get("activity", [])
            for row in activity:
                run_id = row.get("run_id")
                counts[run_id] = counts.get(run_id, 0) + row.get("count", 0)
            review["activity"] = [{"run_id": run_id, "count": count}
                                  for run_id, count in counts.items()]
            review["activity_index"] = {
                "total": len(activity), "returned": 0, "complete": not activity,
                "evidence_ref": "evidence", "packet_path": ["periodic_review", "activity"]}
        payload = {"schema_version": "delivery-decision-input/v2", "input_id": item["input_id"],
                   "mode": "bootstrap" if bootstrap else "changes", "core": core,
                   "unresolved": unresolved,
                   "request_results": packet.get("request_results", []),
                   "changes": changes, "trigger": packet.get("trigger", {"kind": "recovery"}),
                   "periodic_review": review,
                   "source_schema_version": packet.get("schema_version", snapshot.get("schema_version")),
                   "evidence": reference, "delivery_status": item["delivery_status"],
                   "raw_observation": snapshot.get("raw_observation"),
                   "coverage": {"complete": True, "source_complete": False,
                       "omitted_sections": ["settled_history"] + omitted_stable + ([] if bootstrap else
                           ["unchanged_snapshot"] + (["unchanged_delivery_objective"]
                                                     if objective_in_snapshot else [])),
                       "collections": {name: {
                           "total": len(snapshot.get(name, {})) + histories.get(name, {}).get("total", 0),
                           "returned": len(snapshot.get(name, {})) if bootstrap else 0,
                           "complete": bootstrap and not histories.get(name, {}).get("total", 0),
                           "evidence_ref": "evidence"}
                           for name in ("runs", "operations", "repair_verifications")},
                       "unresolved": {"total": len(unresolved), "returned": len(unresolved), "complete": True},
                       "history": {"host_actions": actions["completed_index"], **histories},
                       "changes": {"total": len(changes), "returned": len(changes), "complete": True}}}
        # Each index describes the same retained packet. Keep one precise
        # locator at payload.evidence rather than six copies of its path/hash.
        for entry in payload["coverage"]["history"].values():
            entry.pop("evidence", None)
            entry["evidence_ref"] = "evidence"
        if bootstrap:
            # The initial/recovery view has current necessary bodies, but no
            # full config, native token deltas or settled historical collections.
            payload.update({key: value for key, value in snapshot.items()
                            if key not in {"schema_version", "session", "raw_observation"}})
            payload["continuation"] = packet.get("continuation")
            payload["recovery_context"] = packet.get("recovery_context")
        if len(self._pending_decisions) > 1 and item is not self._pending_decisions[-1]:
            latest = self._pending_decisions[-1]
            # Follow newer facts through the same model-facing projection;
            # reading a raw journal packet would restore internal snapshots.
            self._model_observation(_item=latest)
            latest_path = self._input_view_path(latest["input_id"])
            latest_bytes = latest_path.read_bytes()
            payload["current_state"] = {"input_id": latest["input_id"],
                "path": str(latest_path), "source_ref": _source_ref(latest_path, latest_bytes),
                "selection": {"kind": "bytes", "offset": 0, "length": len(latest_bytes)},
                "budget_control": copy.deepcopy(self._last_current.get("session", {}).get("budget_control")),
                "runs": {key: {"state": value.get("status", {}).get("data", {}).get("recorded_state", {}).get("state"),
                               "write_phase": value.get("status", {}).get("data", {}).get("write_phase"),
                               "pending_summary": value.get("status", {}).get("data", {}).get("pending_summary")}
                         for key, value in self._last_current.get("runs", {}).items()},
                "operation_errors": {key: value.get("error") for key, value in
                    self._last_current.get("operations", {}).items() if value.get("ok") is False},
                "note": "historical input; reconcile newer bindings/control before acting"}
        result = self._page_view(payload, reference, offset=item["offset"],
                                 frozen_path=self._input_view_path(item["input_id"]))
        if "page" not in result:
            encoded = _json_bytes({key: value for key, value in result.items()
                                   if key not in {"delivery_status", "current_state"}})
            result["delivery_range"] = {"next_offset": len(encoded), "complete": True}
        return result

    def _completed_observations_are_quiet(self) -> bool:
        """Retain old pages without repeatedly reasoning about completed work."""
        if not self.work_result or self.activity not in {"standby", "read_only_wait"}:
            return False
        if (self._phase_thread_run_blocker()
                or self._last_current.get("deadline_events")
                or self._last_current.get("observation_gaps")
                or any(item["delivery_status"] in {"unknown", "attempted"}
                       for item in self._pending_decisions)):
            return False
        actions = self._last_current.get("host_actions", {})
        if actions.get("pending") or actions.get("unresolved"):
            return False
        for run in self._last_current.get("runs", {}).values():
            pending = run.get("pending", {})
            unfinished = [item for item in pending.get("data", {}).get("items", [])
                          if not (item.get("type") == "cq_acceptance_closure"
                                  and item.get("status") == "completed"
                                  and item.get("available_actions") == [])]
            if (pending.get("ok") is not True or unfinished
                    or run.get("status", {}).get("data", {}).get("first_blocker")):
                return False
        if any(_event_needs_action(state.get("selected", []))
               for state in self._decision_event_state.values()):
            return False
        for collection in ("operations", "repair_verifications"):
            for envelope in self._last_current.get(collection, {}).values():
                data = envelope.get("data", {})
                if (envelope.get("ok") is not True or _event_needs_action(data)
                        or not (data.get("work_state") == "completed"
                                or data.get("status") in {"exited", "stopped"}
                                or data.get("process", {}).get("state") == "exited")):
                    return False
        return True

    def record_turn_completion(self, status: str | None) -> None:
        """Confirm only contiguous decision bytes returned in a completed turn.

        This is a reception fact, not proof of reasoning or action completion.
        Failed/unknown turns, JSON selections, unread gaps and unknown input
        submissions cannot acknowledge a decision. Resume reuses the existing
        durable input-dispatch receipts rather than reconstructing reads.
        """
        with self._state_lock:
            reads, self._decision_read_ranges = self._decision_read_ranges, []
            if status != "completed":
                self._status_review.inflight = {}
                return
            for item in list(self._pending_decisions):
                if item["delivery_status"] in {"attempted", "unknown"}:
                    continue
                path = self._input_view_path(item["input_id"])
                if not path.exists():
                    continue
                raw = path.read_bytes()
                ref = _source_ref(path, raw)
                intervals = sorted((read["range"]["offset"], read["range"]["end"])
                    for read in reads if read["path"] == str(path)
                    and all(read["source_ref"].get(key) == value for key, value in ref.items()))
                end = item["offset"]
                for start, stop in intervals:
                    if start <= end:
                        end = max(end, stop)
                if end == item["offset"]:
                    continue
                complete = end == len(raw)
                self._append("session-events.jsonl", {
                    "event": "delivery_input_dispatch", "input_id": item["input_id"],
                    "status": "accepted", "via": "tool_read_completed_turn",
                    "view_schema_version": "delivery-decision-input/v2",
                    "next_offset": end, "complete": complete, "source_ref": ref,
                })
                self._last_received_input_id = item["input_id"]
                if item.get("review_window"):
                    self._status_review.received(item["input_id"], item["review_window"], len(raw), intervals)
                if complete:
                    self._pending_decisions.remove(item)
                else:
                    item.update(offset=end, delivery_status="pending")
            for input_id in list(self._status_review.inflight):
                window = self._status_review.complete_reception(input_id)
                if window:
                    self._confirm_review(window, input_id)
            self._save("active")

    def _confirm_review(self, window: dict, input_id: str) -> None:
        if window.get("complete") is False:
            self._append("session-events.jsonl", {"event": "delivery_review_incomplete",
                "input_id": input_id, "window": window,
                "note": "native overview received; source coverage has gaps, confirmation positions retained"})
            return
        self._append("session-events.jsonl", {"event": "delivery_review_confirmed",
            "recorded_at": now(),
            "input_id": input_id, "window": window, "basis": "normal_native_completion"})
        self._status_review.confirm(window)
        superseded = [item["input_id"] for item in self._pending_decisions
            if item["input_id"] != input_id
            and item.get("trigger", {}).get("kind") in {"periodic_review", "followup_due"}
            and item["delivery_status"] not in {"attempted", "unknown"}
            and item.get("review_window", {}).get("through_seq", self._status_review.seq + 1) <= window["through_seq"]]
        if superseded:
            self._append("session-events.jsonl", {"event": "delivery_review_superseded",
                "input_ids": superseded, "confirmed_by": input_id,
                "note": "overview coverage only; original pages are retained, not marked read"})
            self._pending_decisions = [item for item in self._pending_decisions if item["input_id"] not in superseded]

    def record_native_consumption(self, rows: list[dict]) -> None:
        """Reception offsets and native consumption are separate durable facts."""
        previous = getattr(self, "_native_consumption", {})
        for row in rows:
            identity = row["dispatch_id"]
            state = {key: value for key, value in row.items() if key != "payload"}
            if previous.get(identity) == state:
                continue
            self._append("session-events.jsonl", {"event": "delivery_native_consumption", **state})
            packet = row.get("payload", {})
            message_id = packet.get("message_id")
            if self.conversation and message_id:
                self.conversation.append("native_consumption", message_id=message_id, native_receipt=state)
            previous[identity] = state
        self._native_consumption = previous

    def reconcile_native_inputs(self, rows: list[dict]) -> None:
        for row in rows:
            if row["state"] not in {"queued", "claimed", "settled"}:
                continue
            packet = row.get("payload", {})
            data = packet.get("observed_state", packet.get("data", packet))
            item = next((item for item in self._pending_decisions
                         if item["input_id"] == data.get("input_id")), None)
            if item and data.get("delivery_range"):
                received = data["delivery_range"]
                if received["next_offset"] <= item["offset"]:
                    continue
                self._append("session-events.jsonl", {"event": "delivery_input_dispatch",
                    "input_id": item["input_id"], "status": "accepted", "native_receipt": {
                        key: value for key, value in row.items() if key != "payload"},
                    "view_schema_version": data["schema_version"], **received})
                self._last_received_input_id = item["input_id"]
                if item.get("review_window"):
                    # Queue/claim proves native receipt only. A recovered
                    # settled activity may confirm its own complete overview.
                    start = data.get("page", {}).get("offset", 0)
                    self._status_review.received(item["input_id"], item["review_window"],
                        len(self._input_view_path(item["input_id"]).read_bytes()),
                        [(start, received["next_offset"])])
                    reason = row.get("reason")
                    kind = reason.get("kind") if isinstance(reason, dict) else reason
                    if row["state"] == "settled" and kind == "completed":
                        window = self._status_review.complete_reception(item["input_id"])
                        if window:
                            self._confirm_review(window, item["input_id"])
                if received["complete"]:
                    self._pending_decisions.remove(item)
                else:
                    item.update(offset=received["next_offset"], delivery_status="pending")
            if self.conversation and packet.get("message_id"):
                old = self.conversation.receipt(packet["message_id"])
                if old and old["dispatch"] in {"unknown", "pending"}:
                    self.conversation.append("dispatch_result", message_id=packet["message_id"],
                        status="accepted_by_native", native_receipt={
                            key: value for key, value in row.items() if key != "payload"})

    def _dispatch_observation(self, runtime: DeliveryRuntimeProtocol, payload: dict, *, steer: bool) -> bool:
        if steer:
            return False  # Every input waits for natural turn completion on both runtimes.
        data = payload.get("observed_state") if payload.get("kind") in {"delivery_start", "delivery_resume"} else payload.get("data")
        data = data or payload
        item = next((item for item in self._pending_decisions
                     if item["input_id"] == data.get("input_id")), None)
        if item is None:
            return True
        if item["delivery_status"] in {"attempted", "unknown"}:
            return False  # reconcile the original attempt; never blindly replay
        if steer and (item["offset"] or item.get("trigger", {}).get("kind") in {"periodic_review", "followup_due"}):
            return False
        if self.budget:
            try:
                self.budget.require_available(operation="supervise")
            except BudgetError:
                return True  # The unchanged input remains pending on this session.
        self._append("session-events.jsonl", {"event": "delivery_input_dispatch",
            "recorded_at": now(), "input_id": item["input_id"], "status": "attempted"})
        item["delivery_status"] = "attempted"
        try:
            receipt = (runtime.steer if steer else runtime.send)(json.dumps(payload, ensure_ascii=False))
        except BudgetError as exc:
            self._hold_budget_refusal(exc)
            item["delivery_status"] = "pending"
            self._append("session-events.jsonl", {"event": "delivery_input_dispatch",
                "input_id": item["input_id"], "status": "deferred_budget"})
            return True
        except DeliveryRuntimeError as exc:
            status = "rejected" if exc.category == "rejected" else "unknown"
            item["delivery_status"] = status
            self._append("session-events.jsonl", {"event": "delivery_input_dispatch",
                "recorded_at": now(), "input_id": item["input_id"], "status": status})
            self._save("active")
            return False
        received = data["delivery_range"]
        self._append("session-events.jsonl", {"event": "delivery_input_dispatch",
            "recorded_at": now(), "input_id": item["input_id"], "status": "accepted",
            **({"native_receipt": receipt} if receipt else {}),
            "view_schema_version": data["schema_version"], **received})
        self._last_received_input_id = item["input_id"]
        if item.get("review_window"):
            self._status_review.received(item["input_id"], item["review_window"],
                len(self._input_view_path(item["input_id"]).read_bytes()),
                [(item["offset"], received["next_offset"])])
        if received["complete"]:
            self._pending_decisions.remove(item)
        else:
            item["offset"] = received["next_offset"]
            item["delivery_status"] = "pending"
        self._save("active")
        return True


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
    budget_monitor = None
    server = None
    incoming: queue.Queue = queue.Queue()

    def read_input() -> None:
        import sys
        for line in sys.stdin:
            incoming.put(line.rstrip("\n"))
        incoming.put(None)

    try:
        if session.budget:
            budget_monitor = session.budget.start_monitor()
            # Zero or retained pauses reject the first native call without creating a thread.
            try:
                session.budget.require_available(operation="supervise")
            except BudgetError as exc:
                session.budget.record_control("delivery:" + session.session_id,
                    session.budget.show()["epoch"], "not_started")
                session._save("budget_paused", budget_error=exc.code)
                return 2
        base_url = None
        if session.runtime_name == "codex" and uses_external_credential_session(session.binding.provider_id):
            selected = replace(session.profile, bindings={"delivery": session.binding})
            def before_provider_request(receipt: dict) -> None:
                # Runtime turn/start checks the amount. Do not cut off follow-ups
                # inside a turn whose normal token receipt is still pending.
                return None

            providers = ProviderSessionManager(preflight_profile_credentials(selected),
                on_attempt=NumericReceiptWriter(session_root / "native" / "provider-attempts.jsonl",
                    {"session_id": config["session_id"], "phase": "supervision",
                     "role": "delivery"}),
                **({"before_request": before_provider_request} if session.budget else {}))
            providers.start()
            base_url = providers.base_url_for(session.binding.provider_id)
        if session.runtime_name == "dsh":
            runtime = DSHDeliveryRuntime(binding=session.binding, home=session_root / "native",
                instructions=instructions, tools=session.tool_specs(), tool_handler=session.call_tool,
                session_id=session.session_id, profile=session.profile,
                resume=resume and (session_root / "native/dsh-session.json").exists(),
                input_policy="delivery-periodic-review/v1",
                repository_root=repository_root)
        else:
            runtime = DeliveryRuntime(
                binding=session.binding, home=session_root / "native", instructions=instructions,
                usage_context={"session_id": config["session_id"], "phase": "supervision",
                               "role": "delivery",
                               **({"key_ref": providers.credential_ref_for(session.binding.provider_id)}
                                  if providers is not None else {})},
                tools=session.tool_specs(), tool_handler=session.call_tool,
                service_tier=config.get("service_tier", "unset"), provider_base_url=base_url,
                model_context_window=config.get("model_context_window", 544000),
                model_auto_compact_token_limit=config.get("model_auto_compact_token_limit", 489600),
                **({"before_budget_control": lambda text, control_id: providers.authorize_control(
                    session.binding.provider_id, text, control_id,
                )} if providers is not None and session.budget is not None else {}),
            )
        runtime.start()
        session.runtime_identity = getattr(runtime, "identity", {"runtime": "codex"})
        if session.runtime_name == "dsh" and resume:
            session.reconcile_native_inputs(runtime.dispatch_status())
        session.recovery_pending = False
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
        # Startup and explicit recovery both begin from current facts. This
        # bootstrap has its own input identity and cannot acknowledge old pages.
        initial_observation = session.observe()
        session.record_observation(initial_observation, force_delivery=True)
        observed_state = session._bootstrap_observation()
        initial_packet = {"kind": "delivery_resume" if resume else "delivery_start",
                          "observed_state": observed_state,
                          "session_reference": str(session_root / "session.json")}
        if not getattr(session, "stop_pending", False) and session._pending_decisions:
            session._dispatch_observation(runtime, initial_packet, steer=False)
        elif not getattr(session, "stop_pending", False):
            try:
                runtime.send(json.dumps(initial_packet, ensure_ascii=False))
            except BudgetError as exc:
                session._hold_budget_refusal(exc)
        next_observation = 0.0
        pending_input: list[dict] = []
        eof = False
        while not session.finished:
            observations = runtime.poll(0.1)
            failed = any(item.get("status") == "failed" for item in observations)
            if failed:
                session.record_turn_completion("failed")
            else:
                for event in observations:
                    if event.get("event") == "turn_completed":
                        session.record_turn_completion(event.get("status"))
                    elif event.get("event") == "activity_ended":
                        reason = event.get("reason")
                        kind = reason.get("kind") if isinstance(reason, dict) else reason
                        session.record_turn_completion("completed" if kind == "completed" else None)
            if session.runtime_name == "dsh":
                session.runtime_identity = runtime.identity
                native_inputs = runtime.dispatch_status()
                session.record_native_consumption(native_inputs)
                session.reconcile_native_inputs(native_inputs)
            if failed:
                if session.budget and not session.budget.show()["admission_open"]:
                    session._append("session-events.jsonl", {"event": "native_turn_failed_during_budget_pause",
                        "failure_layer": "runtime/infrastructure", "observations": observations})
                else:
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
                        control_text = {"pause": "暂停", "resume": "继续", "cancel": "取消",
                                        "revoke_budget": "撤回预算", "stop": "停止"}.get(message.get("action"), "")
                    else:
                        packet = session.accept_user_input(text)
                        control_text = text
                    packet["_queued_control_text"] = control_text
                    pending_input.append(packet)
            if not runtime.busy and pending_input:
                packet = pending_input[0]
                control_text = packet.pop("_queued_control_text", "")
                control = session.apply_user_control(
                    control_text, source_reference=packet.get("source_reference"))
                if control is not None:
                    packet["host_control_result"] = control
                    if session.conversation:
                        session.conversation.append("control_result", message_id=packet["message_id"],
                            action=packet.get("action"), status="pending", basis="turn_completed")
                    if control_text == "停止":
                        session.stop_message_id = packet.get("message_id")
                        pending_input.pop(0)
            if getattr(session, "stop_pending", False):
                # Submission is not process exit. Keep the Delivery owner online until bound
                # owners have actually stopped; do not start inference while collecting exits.
                observation = session.observe()
                session.record_observation(observation)
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
            if session.sync_budget_control(runtime):
                session.record_held_inputs(pending_input, "task budget does not permit new inference; awaiting authorized resume")
                if time.monotonic() >= next_observation:
                    next_observation = time.monotonic() + 2
                    session.record_observation(session.observe(), allow_periodic=False)
                continue
            # Observe while busy, but leave all model inputs in their queues.
            if runtime.busy and time.monotonic() >= next_observation:
                next_observation = time.monotonic() + 2
                session.record_observation(session.observe(), allow_periodic=False)
            if not runtime.busy:
                uncertain = session._next_decision()
                if uncertain and uncertain["delivery_status"] in {"attempted", "unknown"}:
                    session.record_held_inputs(pending_input, "native input receipt unknown; reconcile the original attempt")
                    # Keep all new messages and apply controls above, while the
                    # original native attempt is reconciled. No second activity.
                    if time.monotonic() >= next_observation:
                        next_observation = time.monotonic() + 2
                        session.record_observation(session.observe(), allow_periodic=False)
                    if eof and server is None:
                        session._save("supervision_interrupted", reason="native input receipt unknown; reconcile before resume")
                        return 2
                    continue
                try:
                    session.maybe_switch_phase_thread(runtime, pending_inputs=pending_input)
                except BudgetError as exc:
                    session._hold_budget_refusal(exc)
                    continue
                if pending_input:
                    current = pending_input.pop(0)
                    if session.conversation:
                        session.conversation.append("dispatch_started", message_id=current["message_id"],
                            dispatch_attempt_id=__import__("uuid").uuid4().hex)
                    try:
                        receipt = runtime.send(json.dumps(current, ensure_ascii=False))
                    except BudgetError as exc:
                        session._hold_budget_refusal(exc)
                        pending_input.insert(0, current)
                        continue
                    except DeliveryRuntimeError as exc:
                        rejected = exc.category == "rejected"
                        if rejected:
                            pending_input.insert(0, current)
                        if session.conversation:
                            session.conversation.append("dispatch_result", message_id=current["message_id"],
                                status="pending" if rejected else "unknown",
                                reason="native_rejected; retry the original packet" if rejected else "native_receipt_unknown")
                        elif not rejected:
                            raise
                    else:
                        if session.conversation:
                            session.conversation.append("dispatch_result", message_id=current["message_id"], status="accepted_by_native",
                                **({"native_receipt": receipt} if receipt else {}))
                elif (session._pending_decisions and not session._completed_observations_are_quiet()
                      and time.monotonic() >= getattr(session, "_dispatch_retry_at", 0)):
                    packet = {"kind": "host_observation", "data": session._model_observation()}
                    if not session._dispatch_observation(runtime, packet, steer=False):
                        status = session._next_decision()["delivery_status"]
                        session._save("native_input_" + status, reason="preserve and reconcile the original input receipt")
                        session._dispatch_retry_at = time.monotonic() + 2
                        if eof and server is None:
                            return 2
                        continue
                elif time.monotonic() >= next_observation:
                    observation = session.observe()
                    next_observation = time.monotonic() + 2
                    if (session.record_observation(observation)
                            and not session._completed_observations_are_quiet()):
                        packet = {"kind": "host_observation", "data": session._model_observation()}
                        if not session._dispatch_observation(runtime, packet, steer=False):
                            status = session._next_decision()["delivery_status"]
                            session._save("native_input_" + status, reason="preserve and reconcile the original input receipt")
                            session._dispatch_retry_at = time.monotonic() + 2
                            if eof and server is None:
                                return 2
                    elif eof and server is None:
                        session._save("supervision_interrupted", reason="business input closed", observation=observation)
                        return 2
        return 0
    except KeyboardInterrupt:
        session._save("supervision_interrupted", reason="operator interrupt", observation=session.observe())
        return 130
    except Exception as exc:
        session._save("supervision_interrupted", reason="Delivery runtime failure",
                      **({"runtime_error": str(exc), "failure_layer": "runtime/infrastructure"}
                         if isinstance(exc, DeliveryRuntimeError) else {}),
                      error_type=type(exc).__name__, observation=session.observe())
        raise
    finally:
        if server is not None:
            server.close()
        try:
            if runtime is not None:
                runtime.close()
                session._append("session-events.jsonl", {
                    "event": "native_runtime_closed", "thread_id": runtime.thread_id,
                    "runtime_identity": session.runtime_identity,
                    "pid": runtime.process.pid if runtime.process is not None else None,
                    "exit_code": runtime.process.poll() if runtime.process is not None else None,
                })
        finally:
            import sys
            close_failed = sys.exc_info()[0] is not None
            try:
                if providers is not None:
                    providers.stop()
            except Exception:
                if not close_failed:
                    raise
            finally:
                if budget_monitor is not None:
                    budget_monitor.stop(timeout=5)
                _publish_delivery_statistics(session)


def _publish_delivery_statistics(session):
    from .close_statistics import publish_close_statistics, register_statistics_link
    try:
        for run_id in sorted(session.run_ids):
            try:
                run_root, _ = resolve_run_root(run_id, repository_root=session.repository_root)
                register_statistics_link(session.session_root, run_root, "delivery-session-run-ledger")
            except (HostOpError, OSError, ValueError):
                pass
        for operation_id in sorted(session.operation_ids):
            register_statistics_link(session.session_root, session.repository_root / ".delivery-ops" / (operation_id + ".owner"),
                                     "delivery-session-operation-ledger")
        session.close_statistics = publish_close_statistics(
            session.session_root, view="task_close", task_ref=session.config.get("task") or session.session_id,
        )
        session._append("session-events.jsonl", {"event": "close_statistics_ready" if session.close_statistics["report_status"] == "ready" else "close_statistics_unavailable",
                                                "close_statistics": session.close_statistics})
        session._save(getattr(session, "_last_saved_state", session.activity))
    except Exception:
        from .usage_capture import LOG
        LOG.warning("close_statistics_report_unavailable")


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
