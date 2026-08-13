"""Callable retained-workspace acceptance operation for R2.3-006.

The operation is deliberately narrow: it validates the frozen R2.3-003 ticket,
constructs two lean Examiner packet sets, owns one temporary Project read key,
and proves cleanup plus model/ledger invariance.  It never starts a modeling run
or calls a semantic write API.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Protocol

from .acceptance import PlatformApiReadKeyLifecycle
from .acceptance_runtime import (
    ExaminerRuntimeBlocked,
    PLATFORM_PROXY_READ_TOOLS,
    LeanExaminerRuntime,
    McpReadForwarder,
    examiner_proxy_schemas,
)
from .deepseek_provider_proxy import preflight_deepseek_credential
from .model_manifest import (
    FORMAL_MODEL_PROFILE_ID,
    FORMAL_MODEL_TASK_ID,
    load_formal_model_manifest,
)
from .report_sink_mcp import report_schema
from .runtimes.codex import CodexRuntimeAdapter


OPERATION_SCHEMA = "R23006RetainedAcceptanceOperation/v1"
TICKET_SCHEMA = "r2-3-003-acceptance-only-ticket/v1"
OPERATION_RELATIVE = Path("workspaces/modeling-acceptance/r23003-acceptance-only-start20-1")
TICKET_RELATIVE = OPERATION_RELATIVE / "runtime/acceptance-ticket.json"
STANDARD_RELATIVE = Path("modeling_team/references/r2-3-003-acceptance-standard.json")
SOURCE_MANIFEST_RELATIVE = Path(
    "docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json"
)
LEDGER_RELATIVE = Path("workspaces/modeling-runs/.r2-3-003-start-ledger.jsonl")
EXPECTED_SCOPE = {
    "project_id": "7fc146d8-c76f-417b-9314-854544f269fc",
    "ontology_id": "fd762f52-2f5e-4bc0-902a-5583135ab64d",
    "graph_set_id": "277fd804-e485-5156-b7a7-ca6a1081f950",
    "workspace_version": "18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0",
    "workspace_state": "ready",
}
EXPECTED_TICKET_DIGEST = "6134dcf73d9b46f86bc81afd1574c70a2c316fcf1973a81e275f23a5963190b0"
EXPECTED_LIMITS = {
    "start_ledger_calls": 0,
    "semantic_writes": 0,
    "build_session_or_lease_calls": 0,
    "producer_handoff_calls": 0,
    "validation_reasoning_mutations": 0,
    "read_key_create_count": 1,
    "read_key_revoke_count": 1,
}


class R23006OperationError(RuntimeError):
    """A deterministic operation or completion gate failed closed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R23006OperationError(f"operation input is unreadable: {path.name}") from exc
    if not isinstance(value, Mapping):
        raise R23006OperationError(f"operation input is not an object: {path.name}")
    return value


@dataclass(frozen=True)
class PreparedR23006Operation:
    ticket: Mapping[str, Any]
    questions: tuple[Mapping[str, Any], ...]
    source_packets: tuple[Mapping[str, Any], ...]
    platform_packets: tuple[Mapping[str, Any], ...]
    ticket_binding: Mapping[str, Any]
    verdict_schema: Mapping[str, Any]
    input_digest: str
    config_digest: str
    ledger_path: Path
    allowed_tools: tuple[str, ...]
    before_inventory: Mapping[str, Any]


def prepare_r23006_operation(repository_root: Path) -> PreparedR23006Operation:
    """Validate the retained ticket and construct the two immutable packet inputs."""

    root = Path(repository_root).resolve()
    ticket = dict(_read_json(root / TICKET_RELATIVE))
    unsigned = {key: value for key, value in ticket.items() if key != "ticket_digest"}
    if (
        ticket.get("schema_version") != TICKET_SCHEMA
        or ticket.get("ticket_digest") != EXPECTED_TICKET_DIGEST
        or ticket.get("ticket_digest") != _digest(unsigned)
    ):
        raise R23006OperationError("retained ticket digest is invalid")
    if ticket.get("continuation_id") != "r23003-acceptance-only-start20-2":
        raise R23006OperationError("retained continuation identity drifted")
    if ticket.get("scope") != EXPECTED_SCOPE or ticket.get("operation_limits") != EXPECTED_LIMITS:
        raise R23006OperationError("retained scope or operation limits drifted")

    standard_path = root / STANDARD_RELATIVE
    manifest_path = root / SOURCE_MANIFEST_RELATIVE
    before_binding = ticket.get("before_inventory")
    if not isinstance(before_binding, Mapping) or not isinstance(before_binding.get("path"), str):
        raise R23006OperationError("retained before-inventory binding is invalid")
    before_path = root / before_binding["path"]
    standard = dict(_read_json(standard_path))
    manifest = dict(_read_json(manifest_path))
    before_inventory = dict(_read_json(before_path))
    standard_binding = ticket.get("acceptance_standard")
    manifest_binding = ticket.get("source_manifest")
    if (
        not isinstance(standard_binding, Mapping)
        or standard_binding.get("path") != str(STANDARD_RELATIVE)
        or standard_binding.get("sha256") != _digest(standard_path.read_bytes())
        or not isinstance(manifest_binding, Mapping)
        or manifest_binding.get("path") != str(SOURCE_MANIFEST_RELATIVE)
        or manifest_binding.get("sha256") != _digest(manifest_path.read_bytes())
        or before_binding.get("sha256") != _digest(before_path.read_bytes())
    ):
        raise R23006OperationError("retained standard or source manifest drifted")
    model_state_binding = ticket.get("model_state")
    inventory_ledger = before_inventory.get("start_ledger")
    ledger_binding = ticket.get("ledger_invariance")
    if (
        not isinstance(model_state_binding, Mapping)
        or not isinstance(inventory_ledger, Mapping)
        or not isinstance(ledger_binding, Mapping)
        or any(before_inventory.get(key) != value for key, value in EXPECTED_SCOPE.items())
        or any(
            before_inventory.get(key) != value
            for key, value in model_state_binding.items()
        )
        or inventory_ledger.get("sha256") != ledger_binding.get("before_sha256")
        or inventory_ledger.get("record_count") != ledger_binding.get("before_record_count")
    ):
        raise R23006OperationError("retained before inventory or model state drifted")

    ticket_questions = ticket.get("competency_questions")
    standard_questions = standard.get("competency_questions")
    if not isinstance(ticket_questions, list) or len(ticket_questions) != 2:
        raise R23006OperationError("retained operation must contain exactly two questions")
    if not isinstance(standard_questions, list) or len(standard_questions) != 2:
        raise R23006OperationError("acceptance standard must contain exactly two questions")
    expected_ids = ["cq-001", "cq-002"]
    if [item.get("question_id") for item in ticket_questions if isinstance(item, Mapping)] != expected_ids:
        raise R23006OperationError("retained question order drifted")
    for ticket_question, standard_question in zip(ticket_questions, standard_questions, strict=True):
        if not isinstance(ticket_question, Mapping) or not isinstance(standard_question, Mapping):
            raise R23006OperationError("retained question is invalid")
        if (
            ticket_question.get("question_id") != standard_question.get("id")
            or ticket_question.get("question") != standard_question.get("question")
            or ticket_question.get("approved_source_paths")
            != standard_question.get("approved_source_paths")
        ):
            raise R23006OperationError("ticket and acceptance standard questions drifted")

    entries = list(manifest.get("base_source_files", ())) + list(
        manifest.get("incremental_source_files", ())
    )
    source_index: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise R23006OperationError("source manifest entry is invalid")
        path, sha256 = entry.get("path"), entry.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str) or path in source_index:
            raise R23006OperationError("source manifest identity is invalid")
        source_path = root / path
        content = source_path.read_bytes()
        if _digest(content) != sha256:
            raise R23006OperationError(f"approved source digest drifted: {path}")
        source_index[path] = {"path": path, "sha256": sha256, "bytes": content}

    request_allowlist = ticket.get("request_allowlist")
    if not isinstance(request_allowlist, list) or not request_allowlist:
        raise R23006OperationError("retained request allowlist is invalid")
    allowed_tools = tuple(
        item.get("tool") for item in request_allowlist if isinstance(item, Mapping)
    )
    if (
        len(allowed_tools) != len(request_allowlist)
        or len(set(allowed_tools)) != len(allowed_tools)
        or any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in allowed_tools)
    ):
        raise R23006OperationError("retained request allowlist is unsupported")
    for item in request_allowlist:
        if item.get("scope") != {
            key: EXPECTED_SCOPE[key] for key in ("project_id", "ontology_id", "graph_set_id")
        }:
            raise R23006OperationError("retained request allowlist scope drifted")
    schemas = examiner_proxy_schemas(allowed_tools)
    scope = dict(EXPECTED_SCOPE)
    ticket_digest = str(ticket["ticket_digest"])
    ticket_binding = {
        "ticket_digest": ticket_digest,
        "standard_digest": str(standard_binding["sha256"]),
        "continuation_id": str(ticket["continuation_id"]),
    }
    model_state = {
        "workspace_version": scope["workspace_version"],
        "state_digest": _digest(scope),
    }
    source_packets: list[Mapping[str, Any]] = []
    platform_packets: list[Mapping[str, Any]] = []
    questions: list[Mapping[str, Any]] = []
    for ticket_question in ticket_questions:
        approved_paths = ticket_question["approved_source_paths"]
        if not isinstance(approved_paths, list) or not approved_paths:
            raise R23006OperationError("question approved sources are invalid")
        try:
            approved = [dict(source_index[path]) for path in approved_paths]
        except (KeyError, TypeError) as exc:
            raise R23006OperationError("question references an unapproved source") from exc
        source_packets.append(
            {
                "approved_sources": approved,
                "source_bundle_digest": _digest(
                    [{"path": item["path"], "sha256": item["sha256"]} for item in approved]
                ),
                "report_schema": report_schema("source"),
            }
        )
        platform_packets.append(
            {
                "model_state": dict(model_state),
                "platform_read_scope": {
                    "project_id": scope["project_id"],
                    "ontology_id": scope["ontology_id"],
                    "graph_set_id": scope["graph_set_id"],
                },
                "proxy_capability": {
                    "capability_id": _digest(
                        {"ticket_digest": ticket_digest, "question_id": ticket_question["question_id"]}
                    )
                },
                "request_schema": {"tools": schemas},
                "report_schema": report_schema("platform"),
                "ticket_binding": dict(ticket_binding),
                "allowed_read_tools": list(allowed_tools),
            }
        )
        questions.append(
            {
                "question_id": ticket_question["question_id"],
                "question": ticket_question["question"],
            }
        )

    input_digest = _digest(
        {
            "ticket_digest": ticket_digest,
            "questions": questions,
            "source_bundles": [item["source_bundle_digest"] for item in source_packets],
        }
    )
    config_digest = _digest(
        {
            "model": "deepseek-v4-flash",
            "tools": list(allowed_tools),
            "schemas": schemas,
        }
    )
    return PreparedR23006Operation(
        ticket=ticket,
        questions=tuple(questions),
        source_packets=tuple(source_packets),
        platform_packets=tuple(platform_packets),
        ticket_binding=ticket_binding,
        verdict_schema=report_schema("acceptance"),
        input_digest=input_digest,
        config_digest=config_digest,
        ledger_path=root / LEDGER_RELATIVE,
        allowed_tools=allowed_tools,
        before_inventory=before_inventory,
    )


class R23006OperationHost(Protocol):
    def start(self, prepared: PreparedR23006Operation) -> None: ...

    def snapshot(self, prepared: PreparedR23006Operation) -> Mapping[str, Any]: ...

    def create_read_key(self, prepared: PreparedR23006Operation) -> None: ...

    def run_examiner(self, prepared: PreparedR23006Operation) -> Mapping[str, Any]: ...

    def failure_metrics(self) -> tuple[Mapping[str, Any], ...]: ...

    def revoke_read_key(self) -> None: ...

    def key_evidence(self) -> Mapping[str, Any]: ...

    def stop(self) -> Mapping[str, Any]: ...


def _validate_result(result: Mapping[str, Any]) -> None:
    verdicts = result.get("verdicts")
    metrics = result.get("metrics")
    if (
        result.get("schema_version") != "ExaminerOrderedVerdicts/v1"
        or result.get("status") != "PASS"
        or result.get("complete") is not True
        or result.get("count") != 2
        or not isinstance(verdicts, list)
        or len(verdicts) != 2
    ):
        raise R23006OperationError("ordered N=2 verdict gate failed")
    for ordinal, verdict in enumerate(verdicts, 1):
        if (
            not isinstance(verdict, Mapping)
            or verdict.get("status") != "PASS"
            or verdict.get("current") is not True
            or verdict.get("usable") is not True
            or verdict.get("question_ordinal") != ordinal
            or verdict.get("question_count") != 2
        ):
            raise R23006OperationError("retained verdict is not current and usable")
    if not isinstance(metrics, list) or len(metrics) != 6:
        raise R23006OperationError("six Examiner metrics records are required")
    expected_roles = ["source", "platform", "acceptance"] * 2
    token_fields = {
        "inputTokens", "cachedInputTokens", "cacheWriteInputTokens", "outputTokens",
        "reasoningOutputTokens", "totalTokens", "modelContextWindow",
    }
    thread_ids: set[str] = set()
    for expected_role, metric in zip(expected_roles, metrics, strict=True):
        if not isinstance(metric, Mapping) or metric.get("role") != expected_role:
            raise R23006OperationError("Examiner metric role order drifted")
        thread_id = metric.get("fresh_thread_id")
        first_turn = metric.get("first_turn_input")
        increments = metric.get("token_usage_increments")
        numeric_totals = (
            "first_input_tokens", "total_tokens", "cached_input_tokens",
            "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens",
            "model_context_window", "estimated_task_tokens", "estimated_evidence_tokens",
            "task_tokens", "evidence_tokens", "collaboration_rejections",
        )
        increments_valid = bool(
            isinstance(increments, list)
            and increments
            and all(
                isinstance(row, Mapping)
                and row
                and set(row) == token_fields
                and all(
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                    for value in row.values()
                )
                and any(value > 0 for key, value in row.items() if key != "modelContextWindow")
                for row in increments
            )
        )
        if (
            metric.get("schema_version") != "ExaminerRunMetrics/v1"
            or metric.get("metrics_complete") is not True
            or metric.get("fresh_thread") is not True
            or not isinstance(thread_id, str)
            or not thread_id
            or thread_id in thread_ids
            or metric.get("inherited_turns") != 0
            or not isinstance(metric.get("turn_start_count"), int)
            or isinstance(metric.get("turn_start_count"), bool)
            or not 1 <= metric["turn_start_count"] <= 3
            or not isinstance(metric.get("inference_steps"), int)
            or isinstance(metric.get("inference_steps"), bool)
            or not 1 <= metric["inference_steps"] <= 3
            or not increments_valid
            or any(
                not isinstance(metric.get(field), int)
                or isinstance(metric.get(field), bool)
                or metric[field] < 0
                for field in numeric_totals
            )
            or metric["first_input_tokens"] <= 0
            or metric["total_tokens"] <= 0
            or not isinstance(metric.get("ttft_ms"), (int, float))
            or isinstance(metric.get("ttft_ms"), bool)
            or not math.isfinite(metric["ttft_ms"])
            or metric["ttft_ms"] < 0
            or not isinstance(metric.get("terminal_wall_ms"), (int, float))
            or isinstance(metric.get("terminal_wall_ms"), bool)
            or not math.isfinite(metric["terminal_wall_ms"])
            or metric["terminal_wall_ms"] < metric["ttft_ms"]
            or metric["terminal_wall_ms"] > 90_000
            or not isinstance(first_turn, Mapping)
            or not isinstance(first_turn.get("fields"), list)
            or not first_turn["fields"]
            or any(not isinstance(field, str) or not field for field in first_turn["fields"])
            or not isinstance(first_turn.get("digest"), str)
            or len(first_turn["digest"]) != 64
            or any(character not in "0123456789abcdef" for character in first_turn["digest"])
            or metric.get("terminal_report") is not True
            or metric.get("blocked") is not None
        ):
            raise R23006OperationError("Examiner metrics completion gate failed")
        if (
            not isinstance(metric.get("proxy_time_ms"), (int, float))
            or isinstance(metric.get("proxy_time_ms"), bool)
            or not math.isfinite(metric["proxy_time_ms"])
            or metric["proxy_time_ms"] < 0
            or (expected_role == "platform" and metric["proxy_time_ms"] <= 0)
        ):
            raise R23006OperationError("Platform proxy timing is unavailable")
        token_totals = {
            "cachedInputTokens": "cached_input_tokens",
            "cacheWriteInputTokens": "cache_write_input_tokens",
            "outputTokens": "output_tokens",
            "reasoningOutputTokens": "reasoning_output_tokens",
            "totalTokens": "total_tokens",
            "modelContextWindow": "model_context_window",
        }
        if metric["first_input_tokens"] != increments[0]["inputTokens"] or any(
            sum(row[token_name] for row in increments) != metric[metric_name]
            for token_name, metric_name in token_totals.items()
        ):
            raise R23006OperationError("Examiner token metrics do not match cumulative increments")
        thread_ids.add(thread_id)


def _reject_secret_evidence(value: Any, *, field: str = "root") -> None:
    """Fail before persistence when an injected host returns credential material."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).lower()
            if (
                ("plaintext" in name and name != "plaintext_released")
                or name in {
                    "authorization", "bearer", "api_key", "read_key", "admin_key",
                    "credential", "secret", "socket", "socket_path",
                }
                or name.endswith(("_secret", "_credential", "_authorization", "_socket_path"))
            ):
                raise R23006OperationError(f"secret-bearing evidence field is forbidden: {field}")
            _reject_secret_evidence(child, field=f"{field}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_evidence(child, field=f"{field}[{index}]")
        return
    if isinstance(value, str) and value.startswith(("sk_read_", "sk_admin_", "Bearer ")):
        raise R23006OperationError(f"secret-bearing evidence value is forbidden: {field}")


_SAFE_BLOCKED_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}")
_BLOCKED_ROLES = frozenset({"source", "platform", "acceptance"})
_BLOCKED_EVIDENCE_FIELDS = frozenset({
    "failure_category", "reason_code", "packet", "field", "thread_id", "turn_id",
    "path", "steps", "host_packet_tokens", "inherited_turns", "read_key", "forwarder",
    "report_received", "terminal_event", "proxy_receipt_count", "binding_code", "report_ref_count",
})
_BLOCKED_CODE_FIELDS = frozenset({
    # Keep this allowlist synchronized with every production
    # ExaminerRuntimeBlocked(..., evidence={...}) key (currently confirmed by
    # rg across acceptance_runtime.py and runtimes/codex.py).
    "failure_category", "reason_code", "packet", "field", "thread_id", "turn_id", "path", "binding_code",
})
_BLOCKED_INTEGER_FIELDS = frozenset({
    "steps", "host_packet_tokens", "inherited_turns", "proxy_receipt_count", "report_ref_count", "index",
})
_BLOCKED_BOOLEAN_FIELDS = frozenset({"read_key", "forwarder", "report_received", "terminal_event"})
_PLATFORM_BINDING_CODES = frozenset({
    "report-refs-invalid", "receipts-empty", "receipt-count-mismatch",
    "locator-shape", "ordinal-mismatch", "locator-key-mismatch", "page-shape",
    "page-first-invalid", "page-sequence-invalid", "page-has-more-invalid",
    "page-truncated-locator", "page-final-invalid", "ref-id-invalid",
})
_PACKET_LABELS = {
    "source Examiner packet": "source-examiner-packet",
    "platform Examiner packet": "platform-examiner-packet",
    "acceptance Examiner packet": "acceptance-examiner-packet",
}


def _blocked_result(blocked: ExaminerRuntimeBlocked) -> dict[str, Any]:
    """Project one typed Examiner stop into a provider- and credential-free result."""

    raw = blocked.as_dict()
    if raw.get("schema_version") != "ExaminerBlocked/v1" or raw.get("status") != "BLOCKED":
        raise R23006OperationError("typed Examiner blocked evidence is invalid")

    reason = raw.get("blocked_reason")
    role = raw.get("role")
    if (
        not isinstance(reason, str)
        or not _SAFE_BLOCKED_CODE.fullmatch(reason)
        or (role is not None and (not isinstance(role, str) or role not in _BLOCKED_ROLES))
    ):
        raise R23006OperationError("typed Examiner blocked identity is invalid")

    details = raw.get("evidence")
    if not isinstance(details, Mapping):
        raise R23006OperationError("typed Examiner blocked evidence is invalid")
    safe_details: dict[str, Any] = {}
    for field, value in details.items():
        if not isinstance(field, str) or field not in _BLOCKED_EVIDENCE_FIELDS:
            raise R23006OperationError("typed Examiner blocked evidence fields are unsupported")

        # The two boolean launch flags are deliberately accepted only as bools,
        # then renamed so the retained artifact cannot be mistaken for a key or
        # callable handle.  Every other field is checked as a fixed scalar below.
        if field in _BLOCKED_BOOLEAN_FIELDS:
            if not isinstance(value, bool):
                _reject_secret_evidence({field: value}, field=f"blocked.evidence.{field}")
                raise R23006OperationError("typed Examiner blocked evidence value is invalid")
            safe_details[
                "read_key_present"
                if field == "read_key"
                else "forwarder_callable"
                if field == "forwarder"
                else field
            ] = value
            continue

        _reject_secret_evidence({field: value}, field=f"blocked.evidence.{field}")
        if field in _BLOCKED_CODE_FIELDS:
            if not isinstance(value, str):
                raise R23006OperationError("typed Examiner blocked evidence value is invalid")
            if field == "binding_code" and value not in _PLATFORM_BINDING_CODES:
                raise R23006OperationError("typed Examiner blocked evidence value is invalid")
            if field == "packet":
                if value not in _PACKET_LABELS:
                    raise R23006OperationError("typed Examiner blocked evidence value is invalid")
                value = _PACKET_LABELS[value]
            if (
                not _SAFE_BLOCKED_CODE.fullmatch(value)
                or (field == "path" and (Path(value).is_absolute() or ".." in Path(value).parts))
            ):
                raise R23006OperationError("typed Examiner blocked evidence value is invalid")
            safe_details[field] = value
            continue
        if (
            field in _BLOCKED_INTEGER_FIELDS
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            safe_details[field] = value
            continue
        raise R23006OperationError("typed Examiner blocked evidence value is invalid")

    failure_category = safe_details.get("failure_category")
    reason_code = safe_details.get("reason_code")
    return {
        "schema_version": "ExaminerBlocked/v1",
        "status": "BLOCKED",
        "complete": False,
        "blocked_reason": reason,
        "role": role,
        "failure_category": failure_category,
        "reason_code": reason_code,
        "evidence": safe_details,
    }


def _blocked_outer_error(result: Mapping[str, Any]) -> R23006OperationError:
    """Build a safe CLI-visible summary without retaining provider exception text."""

    role = result.get("role") or "unspecified"
    reason = result.get("blocked_reason") or "unspecified"
    category = result.get("failure_category") or "unspecified"
    reason_code = result.get("reason_code") or "unspecified"
    return R23006OperationError(
        "Examiner blocked: "
        f"role={role} reason={reason} category={category} code={reason_code}"
    )


_EXAMINER_METRIC_FIELDS = frozenset({
    "schema_version", "role", "fresh_thread_id", "fresh_thread", "metrics_complete",
    "inherited_turns", "first_turn_input", "turn_start_count", "inference_steps",
    "token_usage_increments", "first_input_tokens", "total_tokens", "cached_input_tokens",
    "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens",
    "model_context_window", "token_estimate_algorithm", "estimated_task_tokens",
    "estimated_evidence_tokens", "task_tokens", "evidence_tokens", "ttft_ms",
    "terminal_wall_ms", "proxy_time_ms", "collaboration_rejections", "terminal_report", "blocked",
})
_EXAMINER_METRIC_BOOL_FIELDS = frozenset({"fresh_thread", "metrics_complete", "terminal_report"})
_EXAMINER_METRIC_ROLE_ORDER = ("source", "platform", "acceptance") * 2


def _validate_partial_metrics(
    value: Any,
    expected_blocked: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Accept only bounded, internal ``ExaminerRunMetrics/v1`` snapshots."""

    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or len(value) > len(_EXAMINER_METRIC_ROLE_ORDER):
        raise R23006OperationError("partial Examiner metrics are invalid")
    retained: list[dict[str, Any]] = []
    for index, raw_metric in enumerate(value):
        if not isinstance(raw_metric, Mapping) or set(raw_metric) != _EXAMINER_METRIC_FIELDS:
            raise R23006OperationError("partial Examiner metrics are invalid")
        metric = deepcopy(dict(raw_metric))
        if (
            metric.get("schema_version") != "ExaminerRunMetrics/v1"
            or metric.get("role") != _EXAMINER_METRIC_ROLE_ORDER[index]
        ):
            raise R23006OperationError("partial Examiner metric role order drifted")
        for field in _EXAMINER_METRIC_BOOL_FIELDS:
            if not isinstance(metric.get(field), bool):
                raise R23006OperationError("partial Examiner metric value is invalid")
        blocked = metric.pop("blocked")
        if blocked is None:
            sanitized_blocked = None
        else:
            if not isinstance(blocked, Mapping) or set(blocked) != {
                "schema_version", "status", "blocked_reason", "role", "evidence"
            }:
                raise R23006OperationError("partial Examiner metric blocked value is invalid")
            blocked_reason = blocked.get("blocked_reason")
            blocked_role = blocked.get("role")
            blocked_evidence = blocked.get("evidence")
            if (
                blocked.get("schema_version") != "ExaminerBlocked/v1"
                or blocked.get("status") != "BLOCKED"
                or not isinstance(blocked_reason, str)
                or not _SAFE_BLOCKED_CODE.fullmatch(blocked_reason)
                or (blocked_role is not None and blocked_role not in _BLOCKED_ROLES)
                or not isinstance(blocked_evidence, Mapping)
            ):
                raise R23006OperationError("partial Examiner metric blocked value is invalid")
            sanitized_blocked = _blocked_result(
                ExaminerRuntimeBlocked(
                    blocked_reason,
                    role=blocked_role,
                    evidence=dict(blocked_evidence),
                )
            )
        if index < len(value) - 1:
            if sanitized_blocked is not None:
                raise R23006OperationError("partial Examiner metric blocked stage is invalid")
        elif sanitized_blocked != dict(expected_blocked):
            raise R23006OperationError("partial Examiner metric does not match outer block")
        _reject_secret_evidence(metric, field=f"partial_metrics[{index}]")
        metric["blocked"] = sanitized_blocked
        retained.append(metric)
    return retained


class R23006AcceptanceOperation:
    """Host-owned exactly-once lifecycle around one retained N=2 run."""

    def __init__(
        self,
        repository_root: Path,
        output_root: Path,
        *,
        host_factory: Callable[[Path, Path], R23006OperationHost] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.host_factory = host_factory or _ProductionOperationHost

    def run(self) -> dict[str, Any]:
        prepared = prepare_r23006_operation(self.repository_root)
        host = self.host_factory(self.repository_root, self.output_root)
        before: Mapping[str, Any] | None = None
        after: Mapping[str, Any] | None = None
        result: Mapping[str, Any] | None = None
        key_create_attempted = False
        cleanup: Mapping[str, Any] = {}
        operation_error: BaseException | None = None
        blocked_error: ExaminerRuntimeBlocked | None = None
        try:
            host.start(prepared)
            before = dict(host.snapshot(prepared))
            key_create_attempted = True
            host.create_read_key(prepared)
            result = dict(host.run_examiner(prepared))
            _validate_result(result)
        except BaseException as exc:
            operation_error = exc
            if isinstance(exc, ExaminerRuntimeBlocked):
                blocked_error = exc
        finally:
            if key_create_attempted:
                try:
                    host.revoke_read_key()
                except BaseException as exc:
                    operation_error = exc
            if before is not None:
                try:
                    after = dict(host.snapshot(prepared))
                except BaseException as exc:
                    operation_error = operation_error or exc
            try:
                cleanup = dict(host.stop())
            except BaseException as exc:
                operation_error = exc
        if operation_error is not None and blocked_error is not operation_error:
            if isinstance(operation_error, R23006OperationError):
                raise operation_error
            raise R23006OperationError("retained acceptance operation failed") from operation_error
        if before is None or after is None or before != after:
            raise R23006OperationError("retained model or ledger changed")
        key_evidence = dict(host.key_evidence())
        if (
            key_evidence.get("create_count") != 1
            or key_evidence.get("revoke_count") != 1
            or key_evidence.get("post_revoke_status") not in {401, 403}
            or key_evidence.get("post_revoke_denied") is not True
        ):
            raise R23006OperationError("read key lifecycle evidence is incomplete")
        if not all(cleanup.get(field) is True for field in (
            "provider_stopped", "children_stopped", "forwarder_stopped",
            "runtime_root_removed", "admin_key_revoked", "plaintext_released",
        )):
            raise R23006OperationError("operation cleanup evidence is incomplete")
        if blocked_error is not None:
            blocked_result = _blocked_result(blocked_error)
            failure_metrics = getattr(host, "failure_metrics", ())
            try:
                partial_metrics = failure_metrics() if callable(failure_metrics) else failure_metrics
            except BaseException as exc:
                raise R23006OperationError("partial Examiner metrics are unavailable") from exc
            partial_metrics = _validate_partial_metrics(partial_metrics, blocked_result)
            evidence = {
                "schema_version": OPERATION_SCHEMA,
                "status": "BLOCKED",
                "ticket_digest": prepared.ticket["ticket_digest"],
                "scope": dict(EXPECTED_SCOPE),
                "operation_limits": dict(EXPECTED_LIMITS),
                "result": blocked_result,
                "partial_metrics": partial_metrics,
                "key_lifecycle": key_evidence,
                "invariance": {"before": dict(before), "after": dict(after), "equal": True},
                "cleanup": dict(cleanup),
            }
            _reject_secret_evidence(evidence)
            self._write_evidence(evidence)
            raise _blocked_outer_error(blocked_result) from blocked_error
        assert result is not None
        evidence = {
            "schema_version": OPERATION_SCHEMA,
            "ticket_digest": prepared.ticket["ticket_digest"],
            "scope": dict(EXPECTED_SCOPE),
            "operation_limits": dict(EXPECTED_LIMITS),
            "result": dict(result),
            "key_lifecycle": key_evidence,
            "invariance": {"before": dict(before), "after": dict(after), "equal": True},
            "cleanup": dict(cleanup),
        }
        _reject_secret_evidence(evidence)
        self._write_evidence(evidence)
        return evidence

    def _write_evidence(self, evidence: Mapping[str, Any]) -> Path:
        self.output_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.output_root, 0o700)
        target = self.output_root / "r23006-retained-acceptance.json"
        descriptor, temporary = tempfile.mkstemp(prefix=".r23006-", dir=self.output_root)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(evidence) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            Path(temporary).unlink(missing_ok=True)
            raise
        return target


class _ProductionOperationHost:
    """Production adapter; backend/provider imports remain deferred for unit tests."""

    def __init__(self, repository_root: Path, output_root: Path) -> None:
        self.root = repository_root
        self.output_root = output_root
        self.runtime_root = output_root / "runtime-private"
        self.adapter: CodexRuntimeAdapter | None = None
        self.lifecycle: PlatformApiReadKeyLifecycle | None = None
        self.read_key_id: str | None = None
        self.admin_key_id: Any | None = None
        self.admin_key = ""
        self.session_factory: Any | None = None
        self.create_count = 0
        self.revoke_count = 0
        self.revoke_attempted = False
        self.preexisting_key_ids: set[str] = set()
        self._key_evidence: dict[str, Any] = {}
        self._failure_metrics: tuple[Mapping[str, Any], ...] = ()

    def _request(self, method: str, path: str, body: Mapping[str, Any] | None, key: str) -> tuple[int, Any]:
        payload = None if body is None else _canonical(body)
        request = urllib.request.Request(
            "http://127.0.0.1:8001" + path,
            data=payload,
            method=method,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                value = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                value = None
            return exc.code, value

    def start(self, prepared: PreparedR23006Operation) -> None:
        backend = self.root / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        from app.core.config import Settings
        from app.repositories.postgres import create_session_factory
        from app.security.auth import create_api_key

        self.output_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.runtime_root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.session_factory = create_session_factory(Settings(_env_file=backend / ".env"))
        with self.session_factory() as session:
            admin_record, self.admin_key = create_api_key(
                session, name="r23006-retained-admin", project_id=None, scopes=["admin"]
            )
            self.admin_key_id = admin_record.id
        scope = SimpleNamespace(
            project_id=EXPECTED_SCOPE["project_id"],
            admin_key=self.admin_key,
            request=self._request,
        )

        def forwarder_factory(**kwargs: Any) -> McpReadForwarder:
            return McpReadForwarder(
                **kwargs,
                exact_schemas=examiner_proxy_schemas(kwargs["expected_tools"]),
            )

        self.lifecycle = PlatformApiReadKeyLifecycle(
            scope,
            repository_root=self.root,
            forwarder_factory=forwarder_factory,
        )
        status, keys = self._request("GET", "/api/api-keys", None, self.admin_key)
        if status != 200 or not isinstance(keys, list):
            raise R23006OperationError("pre-operation key inventory is unavailable")
        self.preexisting_key_ids = {
            str(item["id"])
            for item in keys
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        }
        self.adapter = CodexRuntimeAdapter(repository_root=self.root)
        run = SimpleNamespace(
            root=self.runtime_root,
            run_id="r23006-retained-acceptance",
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id=FORMAL_MODEL_TASK_ID),
                profile=SimpleNamespace(profile_id=FORMAL_MODEL_PROFILE_ID, parameters={}),
            ),
            acceptance=None,
            model_manifest=load_formal_model_manifest(self.root),
            deepseek_credential_binding=preflight_deepseek_credential(),
            formal_contract=None,
            scope={"mode": "read", **EXPECTED_SCOPE},
        )
        self.adapter.start_roster(run, [])

    def snapshot(self, prepared: PreparedR23006Operation) -> Mapping[str, Any]:
        if not self.admin_key:
            raise R23006OperationError("admin snapshot credential is unavailable")
        paths = (
            f"/api/projects/{EXPECTED_SCOPE['project_id']}",
            f"/api/projects/{EXPECTED_SCOPE['project_id']}/ontologies",
            f"/api/ontologies/{EXPECTED_SCOPE['ontology_id']}/workspace-context",
            f"/api/ontologies/{EXPECTED_SCOPE['ontology_id']}/modeling-context",
            f"/api/projects/{EXPECTED_SCOPE['project_id']}/build-context?recent_session_limit=100&recent_session_cursor=0",
            f"/api/ontologies/{EXPECTED_SCOPE['ontology_id']}/modeling-batches?limit=100",
        )
        platform: dict[str, Any] = {}
        for path in paths:
            status, value = self._request("GET", path, None, self.admin_key)
            if status != 200:
                raise R23006OperationError(f"retained snapshot failed with HTTP {status}")
            platform[path] = value
        build_context_path = paths[4]
        build_context = platform.get(build_context_path)
        if isinstance(build_context, Mapping):
            platform[build_context_path] = {
                key: value for key, value in build_context.items() if key != "generated_at"
            }
        workspace = platform.get(paths[2])
        if not isinstance(workspace, Mapping) or (
            workspace.get("state") != EXPECTED_SCOPE["workspace_state"]
            or workspace.get("default_graph_set_id") != EXPECTED_SCOPE["graph_set_id"]
        ):
            raise R23006OperationError("retained workspace state drifted")
        modeling_context = platform.get(paths[3])
        modeling_workspace = (
            modeling_context.get("workspace")
            if isinstance(modeling_context, Mapping)
            else None
        )
        if not isinstance(modeling_workspace, Mapping) or (
            modeling_workspace.get("state") != EXPECTED_SCOPE["workspace_state"]
            or modeling_workspace.get("workspace_version")
            != EXPECTED_SCOPE["workspace_version"]
        ):
            raise R23006OperationError("retained modeling workspace version drifted")
        from datetime import UTC, datetime

        from sqlalchemy import func, select

        from app.repositories.models import (
            ApiKeyModel,
            BuildSessionModel,
            ModelingBatchAttemptModel,
            ModelingBatchModel,
            OntologyLeaseModel,
            OntologyModel,
        )

        if self.session_factory is None:
            raise R23006OperationError("snapshot database boundary is unavailable")
        with self.session_factory() as session:
            live_summary = {
                "ontology_count_in_project": int(session.scalar(select(func.count(OntologyModel.id)).where(
                    OntologyModel.project_id == EXPECTED_SCOPE["project_id"]
                )) or 0),
                "active_session_count": int(session.scalar(select(func.count(BuildSessionModel.id)).where(
                    BuildSessionModel.project_id == EXPECTED_SCOPE["project_id"],
                    BuildSessionModel.status == "active",
                )) or 0),
                "active_lease_count": int(session.scalar(select(func.count(OntologyLeaseModel.ontology_id)).where(
                    OntologyLeaseModel.project_id == EXPECTED_SCOPE["project_id"],
                    OntologyLeaseModel.released_at.is_(None),
                    OntologyLeaseModel.expires_at > datetime.now(UTC),
                )) or 0),
                "active_attempt_count": int(session.scalar(
                    select(func.count(ModelingBatchAttemptModel.id))
                    .join(ModelingBatchModel, ModelingBatchModel.id == ModelingBatchAttemptModel.batch_id)
                    .where(
                        ModelingBatchModel.project_id == EXPECTED_SCOPE["project_id"],
                        ModelingBatchAttemptModel.status.in_(("validating", "applying", "recovering")),
                    )
                ) or 0),
                "active_project_key_count": int(session.scalar(select(func.count(ApiKeyModel.id)).where(
                    ApiKeyModel.project_id == EXPECTED_SCOPE["project_id"],
                    ApiKeyModel.revoked_at.is_(None),
                )) or 0),
                "modeling_batch_count": int(session.scalar(select(func.count(ModelingBatchModel.id)).where(
                    ModelingBatchModel.ontology_id == EXPECTED_SCOPE["ontology_id"]
                )) or 0),
            }
        for field in live_summary:
            if live_summary[field] != prepared.before_inventory.get(field):
                raise R23006OperationError(f"retained live inventory drifted: {field}")
        try:
            ledger_bytes = prepared.ledger_path.read_bytes()
        except OSError as exc:
            raise R23006OperationError("retained start ledger is unreadable") from exc
        records = [line for line in ledger_bytes.splitlines() if line.strip()]
        binding = prepared.ticket.get("ledger_invariance")
        if (
            not isinstance(binding, Mapping)
            or binding.get("path") != str(LEDGER_RELATIVE)
            or binding.get("before_sha256") != _digest(ledger_bytes)
            or binding.get("before_record_count") != len(records)
        ):
            raise R23006OperationError("retained start ledger drifted before operation")
        return {
            "platform_digest": _digest({"responses": platform, "live_summary": live_summary}),
            "ledger_sha256": _digest(ledger_bytes),
            "ledger_record_count": len(records),
        }

    def create_read_key(self, prepared: PreparedR23006Operation) -> None:
        if self.lifecycle is None:
            raise R23006OperationError("read key lifecycle is unavailable")
        record = self.lifecycle.create(
            project_id=EXPECTED_SCOPE["project_id"],
            ontology_id=EXPECTED_SCOPE["ontology_id"],
            acceptance_round_id="r23006-retained-n2",
            ticket_digest_value=str(prepared.ticket["ticket_digest"]),
            input_digest=prepared.input_digest,
            config_digest=prepared.config_digest,
        )
        self.read_key_id = record.key_id
        self.create_count += 1

    def run_examiner(self, prepared: PreparedR23006Operation) -> Mapping[str, Any]:
        if self.lifecycle is None or self.adapter is None or self.read_key_id is None:
            raise R23006OperationError("production Examiner runtime is unavailable")
        plaintext = self.lifecycle.plaintext_for(self.read_key_id)
        forward = self.lifecycle.forwarder_for(
            self.read_key_id, expected_tools=prepared.allowed_tools
        )
        runtime = LeanExaminerRuntime(
            codex_adapter=self.adapter,
            platform_read_key=plaintext,
            platform_forwarder=forward,
            child_timeout_seconds=90,
        )
        self._failure_metrics = ()
        try:
            return runtime.run(
                prepared.questions,
                source_packets=prepared.source_packets,
                platform_packets=prepared.platform_packets,
                ticket_binding=prepared.ticket_binding,
                verdict_schema=prepared.verdict_schema,
            )
        except ExaminerRuntimeBlocked:
            self._failure_metrics = runtime.failure_metrics
            raise
        finally:
            del runtime
            del forward
            del plaintext

    def failure_metrics(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(deepcopy(row) for row in self._failure_metrics)

    def revoke_read_key(self) -> None:
        if self.lifecycle is None:
            raise R23006OperationError("read key lifecycle is unavailable")
        if self.revoke_attempted:
            raise R23006OperationError("read key revoke was already attempted")
        self.revoke_attempted = True
        if self.read_key_id is not None:
            try:
                self.lifecycle.revoke(self.read_key_id)
            finally:
                self.revoke_count += 1
                self._key_evidence = dict(self.lifecycle.evidence(self.read_key_id))
                forwarder = getattr(self.lifecycle, "_forwarders", {}).pop(
                    self.read_key_id, None
                )
                if forwarder is not None:
                    stopper = getattr(forwarder, "stop", None)
                    if callable(stopper):
                        stopper()
                getattr(self.lifecycle, "_plaintext", {}).pop(self.read_key_id, None)
            return
        status, keys = self._request("GET", "/api/api-keys", None, self.admin_key)
        if status != 200 or not isinstance(keys, list):
            raise R23006OperationError("partial read key creation could not be reconciled")
        candidates = [
            item
            for item in keys
            if isinstance(item, Mapping)
            and item.get("id") not in self.preexisting_key_ids
            and item.get("name") == "r2-3-005-acceptance-r23006-retained-n2"
            and item.get("project_id") == EXPECTED_SCOPE["project_id"]
            and item.get("revoked_at") is None
        ]
        if len(candidates) > 1:
            raise R23006OperationError("partial read key creation produced ambiguous residue")
        if not candidates:
            raise R23006OperationError("partial read key creation could not prove zero residue")
        key_id = str(candidates[0]["id"])
        try:
            revoke_status, _ = self._request(
                "POST", f"/api/api-keys/{key_id}:revoke", None, self.admin_key
            )
            if revoke_status != 200:
                raise R23006OperationError("partial read key residue revoke failed")
        finally:
            self.revoke_count += 1

    def key_evidence(self) -> Mapping[str, Any]:
        return {
            **self._key_evidence,
            "create_count": self.create_count,
            "revoke_count": self.revoke_count,
        }

    def stop(self) -> Mapping[str, Any]:
        errors: list[BaseException] = []
        if self.lifecycle is not None:
            if not self.revoke_attempted and self.read_key_id is not None:
                try:
                    self.revoke_read_key()
                except BaseException as exc:
                    errors.append(exc)
            for forwarder in list(getattr(self.lifecycle, "_forwarders", {}).values()):
                try:
                    stopper = getattr(forwarder, "stop", None)
                    if callable(stopper):
                        stopper()
                except BaseException as exc:
                    errors.append(exc)
            getattr(self.lifecycle, "_forwarders", {}).clear()
            getattr(self.lifecycle, "_plaintext", {}).clear()
        if self.adapter is not None:
            try:
                self.adapter.stop()
            except BaseException as exc:
                errors.append(exc)
        admin_revoked = False
        if self.session_factory is not None and self.admin_key_id is not None:
            try:
                from app.repositories.models import ApiKeyModel
                from app.security.auth import revoke_key

                with self.session_factory() as session:
                    record = session.get(ApiKeyModel, self.admin_key_id)
                    if record is not None:
                        revoke_key(session, record)
                        admin_revoked = bool(record.revoked_at)
            except BaseException as exc:
                errors.append(exc)
        self.admin_key = ""
        provider_stopped = True
        children_stopped = True
        if self.adapter is not None:
            runtime_cleanup = self.adapter.cleanup_identifiers()
            aggregate = runtime_cleanup.get("aggregate_secret_audit")
            if not isinstance(aggregate, Mapping) or (
                aggregate.get("private_credentials_destroyed") is not True
                or aggregate.get("cleanup_error_count") != 0
                or aggregate.get("active_resources") is True
                or aggregate.get("zero_child_residue") is not True
            ):
                errors.append(R23006OperationError("Codex runtime cleanup proof is incomplete"))
            provider = getattr(self.adapter, "_formal_provider_proxy", None)
            provider_stopped = provider is None
            children_stopped = not bool(getattr(self.adapter, "_acceptance_children", {}))
        forwarder_stopped = True
        if self.lifecycle is not None:
            forwarder_stopped = not bool(getattr(self.lifecycle, "_forwarders", {}))
        shutil.rmtree(self.runtime_root, ignore_errors=True)
        cleanup = {
            "provider_stopped": provider_stopped,
            "children_stopped": children_stopped,
            "forwarder_stopped": forwarder_stopped,
            "runtime_root_removed": not self.runtime_root.exists(),
            "admin_key_revoked": admin_revoked,
            "plaintext_released": not self.admin_key and bool(
                self.lifecycle is None or not getattr(self.lifecycle, "_plaintext", {})
            ),
        }
        if errors:
            raise R23006OperationError("one or more production cleanup steps failed") from errors[0]
        return cleanup


def run_r23006_acceptance_operation(
    repository_root: Path,
    output_root: Path,
    *,
    host_factory: Callable[[Path, Path], R23006OperationHost] | None = None,
) -> dict[str, Any]:
    return R23006AcceptanceOperation(
        repository_root, output_root, host_factory=host_factory
    ).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run retained R2.3-006 N=2 acceptance")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    evidence = run_r23006_acceptance_operation(
        arguments.repository_root, arguments.output_root
    )
    print(json.dumps({
        "schema_version": evidence["schema_version"],
        "status": evidence["result"]["status"],
        "evidence_path": str(arguments.output_root / "r23006-retained-acceptance.json"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
