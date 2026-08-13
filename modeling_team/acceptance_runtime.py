"""Private runtime helpers for the R2.3-005 Examiner children.

The Runner owns this module.  It deliberately has no semantic authority: the platform
proxy validates a frozen ticket envelope before forwarding to the host-owned canonical
MCP server.  ``ScopedReadProxy`` can still be constructed without a forwarder by
explicit deterministic offline tests; formal Runner children always bind the concrete
``McpReadForwarder`` created by the platform read-key lifecycle.
"""

from __future__ import annotations

import hashlib
import asyncio
import base64
from copy import deepcopy
import json
import os
import queue
import re
import socket
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence


class ChildRuntimeError(RuntimeError):
    """A private child/proxy contract failed closed."""


class ExaminerRuntimeBlocked(ChildRuntimeError):
    """A typed, fail-closed Examiner stop which must not be retried by asking another role."""

    def __init__(self, reason: str, *, role: str | None = None, evidence: Mapping[str, Any] | None = None):
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._/-]{0,79}", reason):
            raise ValueError("Examiner blocked reason is invalid")
        self.reason = reason
        self.role = role
        self.evidence = dict(evidence or {})
        super().__init__(f"BLOCKED/{reason}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ExaminerBlocked/v1",
            "status": "BLOCKED",
            "blocked_reason": self.reason,
            "role": self.role,
            "evidence": dict(self.evidence),
        }


def _packet_json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, MappingProxyType):
        return dict(value)
    raise TypeError(f"unsupported packet value: {type(value).__name__}")


def _packet_canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_packet_json_default,
    ).encode("utf-8")


def _packet_digest(value: Any) -> str:
    return hashlib.sha256(_packet_canonical(value)).hexdigest()


def _packet_tokens(value: Any) -> int:
    """Deterministic provider-neutral estimate used for recomputable accounting."""

    return max(1, (len(_packet_canonical(value)) + 3) // 4)


def _packet_measurement_payload(kind: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Project role-packet accounting without raw source bytes or platform responses."""

    measured = dict(payload)
    if kind == "source" and isinstance(measured.get("approved_sources"), (list, tuple)):
        measured["approved_sources"] = [
            {
                "path": item.get("path"),
                "sha256": item.get("sha256"),
            }
            for item in measured["approved_sources"]
            if isinstance(item, Mapping)
        ]
    if kind == "acceptance":
        # Acceptance receives typed reports and their digests, not raw platform
        # responses; count the report envelope as task context and leave evidence
        # response accounting to the Platform metrics object.
        measured.pop("platform_response", None)
    return measured


def _freeze_packet(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_packet(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_packet(child) for child in value)
    if isinstance(value, tuple):
        return tuple(_freeze_packet(child) for child in value)
    return value


def _unfreeze_packet(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _unfreeze_packet(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_packet(child) for child in value]
    return value


def _require_packet_keys(value: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    if set(value) != set(keys):
        raise ExaminerRuntimeBlocked("acceptance-input", evidence={"packet": label})


@dataclass(frozen=True)
class ExaminerRolePacket:
    """Immutable, digest-bound Host input for one fresh Examiner instance."""

    kind: str
    payload: Mapping[str, Any]
    canonical_digest: str
    field_inventory: tuple[str, ...]
    token_breakdown: Mapping[str, int]
    schema_version: str = "ExaminerRolePacket/v1"

    @classmethod
    def build(cls, kind: str, payload: Mapping[str, Any]) -> "ExaminerRolePacket":
        if kind not in {"source", "platform", "acceptance"}:
            raise ChildRuntimeError("Examiner packet kind is invalid")
        if not isinstance(payload, Mapping):
            raise ChildRuntimeError("Examiner packet payload is invalid")
        normalized = dict(payload)
        expected = {
            "source": {
                "question", "ordinal", "count", "approved_sources", "source_bundle_digest", "report_schema"
            },
            "platform": {
                "question", "ordinal", "count", "model_state", "platform_read_scope",
                "proxy_capability", "request_schema", "report_schema", "ticket_binding",
                "allowed_read_tools"
            },
            "acceptance": {
                "question", "ticket_binding", "ordinal", "count", "source_report", "platform_report",
                "source_report_digest", "platform_report_digest", "verdict_schema",
                "source_evidence_ref_ids", "platform_evidence_ref_ids",
            },
        }[kind]
        _require_packet_keys(normalized, expected, f"{kind} Examiner packet")
        ordinal, count = normalized.get("ordinal"), normalized.get("count")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0 or ordinal > count:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        question = normalized.get("question")
        if not isinstance(question, str) or not question:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        if kind == "source":
            sources = normalized["approved_sources"]
            if not isinstance(sources, (list, tuple)) or not sources:
                raise ExaminerRuntimeBlocked("source-missing", role="source")
            if not isinstance(normalized.get("report_schema"), Mapping):
                raise ExaminerRuntimeBlocked("acceptance-input", role="source")
            for source in sources:
                if not isinstance(source, Mapping) or set(source) != {"path", "sha256", "bytes"}:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                path, digest, content = source["path"], source["sha256"], source["bytes"]
                if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != digest:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ExaminerRuntimeBlocked("source-missing", role="source") from exc
            manifest = [{"path": item["path"], "sha256": item["sha256"]} for item in sources]
            if (
                not isinstance(normalized["source_bundle_digest"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", normalized["source_bundle_digest"])
                or normalized["source_bundle_digest"] != _packet_digest(manifest)
            ):
                raise ExaminerRuntimeBlocked("source-missing", role="source")
        elif kind == "platform":
            for field in (
                "model_state", "platform_read_scope", "proxy_capability", "request_schema",
                "ticket_binding",
            ):
                if not isinstance(normalized[field], Mapping):
                    raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            if not normalized["proxy_capability"].get("capability_id"):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            state = normalized["model_state"]
            scope = normalized["platform_read_scope"]
            if (
                not isinstance(state.get("workspace_version"), str)
                or not state.get("workspace_version")
                or not isinstance(state.get("state_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", state["state_digest"]) is None
                or any(not isinstance(scope.get(field), str) or not scope.get(field) for field in ("project_id", "ontology_id", "graph_set_id"))
            ):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            ticket_digest = normalized["ticket_binding"].get("ticket_digest")
            if not isinstance(ticket_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", ticket_digest):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            allowed_tools = normalized.get("allowed_read_tools")
            if (
                not isinstance(allowed_tools, (list, tuple))
                or not allowed_tools
                or len(set(allowed_tools)) != len(allowed_tools)
                or any(not isinstance(tool, str) or tool not in PLATFORM_PROXY_READ_TOOLS for tool in allowed_tools)
            ):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            request_schema = normalized["request_schema"]
            schemas = request_schema.get("tools") if isinstance(request_schema.get("tools"), Mapping) else request_schema
            if not isinstance(schemas, Mapping) or set(schemas) != set(allowed_tools):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            exact = examiner_proxy_schemas(allowed_tools)
            if any(_packet_digest(schemas[tool]) != _packet_digest(exact[tool]) for tool in allowed_tools):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            if "source" in normalized or "history" in normalized:
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
        else:
            for field in ("ticket_binding", "source_report", "platform_report"):
                if not isinstance(normalized[field], Mapping):
                    raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
            for field in ("source_report_digest", "platform_report_digest"):
                if not isinstance(normalized[field], str) or not re.fullmatch(r"[0-9a-f]{64}", normalized[field]):
                    raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
            try:
                source_report = _validate_report_sink_payload(normalized["source_report"], kind="source")
                platform_report = _validate_report_sink_payload(normalized["platform_report"], kind="platform")
            except ChildRuntimeError as exc:
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance") from exc
            if (
                normalized["source_report_digest"] != _packet_digest(source_report)
                or normalized["platform_report_digest"] != _packet_digest(platform_report)
            ):
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
            if not isinstance(normalized["ticket_binding"].get("ticket_digest"), str) or re.fullmatch(
                r"[0-9a-f]{64}", normalized["ticket_binding"]["ticket_digest"]
            ) is None:
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
            if not isinstance(normalized.get("verdict_schema"), Mapping):
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
            for field in ("source_evidence_ref_ids", "platform_evidence_ref_ids"):
                values = normalized.get(field)
                if (
                    not isinstance(values, (list, tuple))
                    or not values
                    or any(not isinstance(item, str) or not item for item in values)
                    or len(set(values)) != len(values)
                ):
                    raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
            if "approved_sources" in normalized or "platform_response" in normalized or "history" in normalized:
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
        frozen = _freeze_packet(normalized)
        canonical = _packet_digest(_unfreeze_packet(frozen))
        inventory = tuple(sorted(str(key) for key in normalized))
        measured_payload = _packet_measurement_payload(kind, normalized)
        breakdown = {
            "system_safety_prefix_tokens": 0,
            "host_packet_tokens": _packet_tokens(measured_payload),
            "source_bytes_tokens": (
                sum(_packet_tokens(bytes(item["bytes"])) for item in normalized["approved_sources"])
                if kind == "source" else 0
            ),
            "platform_response_tokens": 0,
            "task_tokens": _packet_tokens({key: normalized[key] for key in inventory if key in {"question", "ticket_binding", "ordinal", "count"}}),
            "evidence_tokens": 0,
        }
        if breakdown["host_packet_tokens"] > 4096:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind, evidence={"host_packet_tokens": breakdown["host_packet_tokens"]})
        return cls(kind, frozen, canonical, inventory, MappingProxyType(breakdown))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "payload": _unfreeze_packet(self.payload),
            "canonical_digest": self.canonical_digest,
            "field_inventory": list(self.field_inventory),
            "token_breakdown": dict(self.token_breakdown),
        }


def build_source_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("source", payload)


def build_platform_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("platform", payload)


def build_acceptance_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("acceptance", payload)


@dataclass(frozen=True)
class ExaminerTransportReceipt:
    sender: str
    recipient: str
    status: str
    reason: str
    receipt_digest: str


class ExaminerTransport:
    """Role-private transport that rejects all lateral collaboration before send."""

    def __init__(self, *, owner_id: str):
        if not isinstance(owner_id, str) or not owner_id:
            raise ChildRuntimeError("Examiner transport owner is invalid")
        self.owner_id = owner_id
        self.receipts: list[ExaminerTransportReceipt] = []

    def send(self, *, sender: str, recipient: str, payload: Mapping[str, Any]) -> ExaminerTransportReceipt:
        if recipient != self.owner_id:
            receipt_data = {
                "sender": sender,
                "recipient": recipient,
                "status": "rejected",
                "reason": "collaboration/routing",
                "payload_digest": _packet_digest(payload),
            }
            receipt = ExaminerTransportReceipt(
                sender=str(sender),
                recipient=str(recipient),
                status="rejected",
                reason="collaboration/routing",
                receipt_digest=_packet_digest(receipt_data),
            )
            self.receipts.append(receipt)
            return receipt
        receipt_data = {"sender": sender, "recipient": recipient, "status": "accepted", "payload_digest": _packet_digest(payload)}
        receipt = ExaminerTransportReceipt(str(sender), str(recipient), "accepted", "owner", _packet_digest(receipt_data))
        self.receipts.append(receipt)
        return receipt


_TOKEN_FIELDS = (
    "inputTokens", "cachedInputTokens", "cacheWriteInputTokens", "outputTokens",
    "reasoningOutputTokens", "totalTokens", "modelContextWindow",
)


@dataclass
class ExaminerRunMetrics:
    """Recomputable per-child metrics for Codex App Server notifications."""

    role: str
    thread_id: str | None = None
    turn_start_count: int = 0
    inference_steps: int = 0
    ttft_ms: float | None = None
    terminal_wall_ms: float | None = None
    proxy_time_ms: float = 0.0
    collaboration_rejections: int = 0
    first_turn_input_digest: str | None = None
    first_turn_input_fields: tuple[str, ...] = ()
    inherited_turns: int = 0
    packet_tokens: int = 0
    source_bytes_tokens: int = 0
    platform_response_tokens: int = 0
    terminal_report: bool = False
    blocked: ExaminerRuntimeBlocked | None = None
    _started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _first_token_monotonic: float | None = field(default=None, repr=False)
    _last_usage: dict[str, int] = field(default_factory=dict, repr=False)
    _increments: list[dict[str, int]] = field(default_factory=list, repr=False)
    _totals: dict[str, int] = field(default_factory=lambda: {name: 0 for name in _TOKEN_FIELDS}, repr=False)
    _first_input_tokens: int | None = field(default=None, repr=False)
    _turn_id: str | None = field(default=None, repr=False)
    terminal_event: bool = False

    def record_turn_start(self) -> None:
        """Record the Host-issued fresh turn exactly once."""

        if self.turn_start_count == 0:
            self.turn_start_count = 1

    def bind_thread(self, thread_id: str) -> None:
        if not isinstance(thread_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", thread_id):
            raise ChildRuntimeError("fresh Examiner thread identity is invalid")
        if self.thread_id is not None and self.thread_id != thread_id:
            raise ChildRuntimeError("fresh Examiner thread identity changed")
        self.thread_id = thread_id

    def bind_first_turn_input(self, value: Sequence[Mapping[str, Any]], *, inherited_turns: int = 0, packet: ExaminerRolePacket | None = None) -> None:
        if inherited_turns != 0:
            self.blocked = ExaminerRuntimeBlocked("acceptance-input", role=self.role, evidence={"inherited_turns": inherited_turns})
            raise self.blocked
        fields: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                fields.extend(str(key) for key in sorted(item))
        self.inherited_turns = 0
        self.first_turn_input_fields = tuple(fields)
        self.first_turn_input_digest = _packet_digest(list(value))
        if packet is not None:
            self.packet_tokens = int(packet.token_breakdown.get("host_packet_tokens", 0))
            self.source_bytes_tokens = int(packet.token_breakdown.get("source_bytes_tokens", 0))

    def observe_notification(self, value: Mapping[str, Any]) -> bool:
        if not isinstance(value, Mapping):
            raise ChildRuntimeError("Examiner notification is invalid")
        method = value.get("method")
        params = value.get("params") if isinstance(value.get("params"), Mapping) else {}
        if method in {"turn/started", "turn/start"}:
            self.record_turn_start()
        if method in {
            "item/agentMessage/delta", "item/reasoning/summaryTextDelta", "item/reasoning/textDelta",
            "item/commandExecution/outputDelta", "item/fileChange/outputDelta", "process/outputDelta",
        } and self._first_token_monotonic is None:
            self._first_token_monotonic = time.monotonic()
            self.ttft_ms = (self._first_token_monotonic - self._started_monotonic) * 1000
        if method != "thread/tokenUsage/updated":
            if method in {"turn/completed", "turn/finished"}:
                self.terminal_event = True
                if self.terminal_wall_ms is None:
                    self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000
            return False
        event_thread_id = params.get("threadId")
        if self.thread_id is not None and event_thread_id is not None and event_thread_id != self.thread_id:
            self.blocked = ExaminerRuntimeBlocked(
                "runtime-metrics", role=self.role, evidence={"thread_id": self.thread_id}
            )
            raise self.blocked
        event_turn_id = params.get("turnId")
        if event_turn_id is not None:
            if not isinstance(event_turn_id, str) or not event_turn_id:
                self.blocked = ExaminerRuntimeBlocked("runtime-metrics", role=self.role)
                raise self.blocked
            if self._turn_id is not None and event_turn_id != self._turn_id:
                self.blocked = ExaminerRuntimeBlocked(
                    "runtime-metrics", role=self.role, evidence={"turn_id": self._turn_id}
                )
                raise self.blocked
            self._turn_id = event_turn_id
        usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), Mapping) else params.get("token_usage")
        if not isinstance(usage, Mapping):
            return False
        cumulative = usage.get("total") if isinstance(usage.get("total"), Mapping) else usage
        current: dict[str, int] = {}
        for token_name in _TOKEN_FIELDS:
            raw = cumulative.get(token_name)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                continue
            current[token_name] = raw
        if not current:
            return False
        increments: dict[str, int] = {}
        for token_name, raw in current.items():
            prior = self._last_usage.get(token_name, 0)
            delta = raw - prior
            if delta < 0:
                self.blocked = ExaminerRuntimeBlocked("runtime-metrics", role=self.role, evidence={"field": token_name})
                raise self.blocked
            increments[token_name] = delta
            self._totals[token_name] = raw
        positive = any(value > 0 for key, value in increments.items() if key != "modelContextWindow")
        self._last_usage.update(current)
        if not positive:
            return False
        if self.inference_steps >= 3:
            self.blocked = ExaminerRuntimeBlocked("runtime-budget", role=self.role, evidence={"steps": self.inference_steps + 1})
            raise self.blocked
        self.inference_steps += 1
        self._increments.append(increments)
        # Bind the first positive inference usage only.  A zero/no-op cumulative
        # notification is not an inference and must not freeze first-input accounting.
        if self._first_input_tokens is None and "inputTokens" in current:
            self._first_input_tokens = current["inputTokens"]
        # Usage notifications are cumulative and normally arrive immediately before
        # turn/completed; TTFT is therefore sourced only from output/delta events.
        return True

    def record_proxy_time(self, elapsed_ms: float) -> None:
        if isinstance(elapsed_ms, (int, float)) and elapsed_ms >= 0:
            self.proxy_time_ms += float(elapsed_ms)

    def record_platform_response(self, response: Mapping[str, Any]) -> None:
        if isinstance(response, Mapping):
            self.platform_response_tokens += _packet_tokens(response)

    def record_collaboration_rejection(self) -> None:
        self.collaboration_rejections += 1

    def record_terminal_report(self, report: Mapping[str, Any]) -> None:
        if not isinstance(report, Mapping) or set(report) != _REPORT_SEMANTIC_FIELDS:
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        self.terminal_report = True
        # A report-sink callback can arrive before the provider's terminal turn
        # notification.  Keep terminal timing tied to that notification rather
        # than the callback race; ``observe_notification`` owns the timestamp.
        if self.terminal_event and self.terminal_wall_ms is None:
            self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000

    def record_terminal_verdict(self, verdict: Mapping[str, Any]) -> None:
        """Record the real Acceptance terminal output; no synthetic report is accepted."""

        required = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        sequence = {"question_ordinal", "question_count", "previous_question_ordinal", "next_question_ordinal", "final"}
        if not isinstance(verdict, Mapping) or not required.issubset(verdict) or set(verdict) - required - sequence:
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        if verdict["status"] not in {"PASS", "FAIL", "BLOCKED"}:
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        if not isinstance(verdict["answer"], str) or not verdict["answer"]:
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        if not isinstance(verdict["evidence_ref_ids"], list) or not all(
            isinstance(item, str) and item for item in verdict["evidence_ref_ids"]
        ):
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        if not isinstance(verdict["current"], bool) or not isinstance(verdict["usable"], bool):
            self.blocked = ExaminerRuntimeBlocked("acceptance-evidence", role=self.role)
            raise self.blocked
        self.terminal_report = True
        if self.terminal_event and self.terminal_wall_ms is None:
            self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000

    def allow_inference(self) -> None:
        if self.blocked is not None:
            raise self.blocked
        if self.inference_steps >= 3:
            self.blocked = ExaminerRuntimeBlocked("runtime-budget", role=self.role, evidence={"steps": self.inference_steps})
            raise self.blocked

    @property
    def token_usage_increments(self) -> tuple[Mapping[str, int], ...]:
        return tuple(MappingProxyType(dict(item)) for item in self._increments)

    def as_dict(self) -> dict[str, Any]:
        totals = dict(self._totals)
        return {
            "schema_version": "ExaminerRunMetrics/v1",
            "role": self.role,
            "fresh_thread_id": self.thread_id,
            "fresh_thread": self.thread_id is not None and self.inherited_turns == 0,
            "metrics_complete": bool(
                self.thread_id
                and self.inference_steps > 0
                and self.ttft_ms is not None
                and self.terminal_event
            ),
            "inherited_turns": self.inherited_turns,
            "first_turn_input": {
                "fields": list(self.first_turn_input_fields),
                "digest": self.first_turn_input_digest,
            },
            "turn_start_count": self.turn_start_count,
            "inference_steps": self.inference_steps,
            "token_usage_increments": [dict(item) for item in self._increments],
            "first_input_tokens": self._first_input_tokens or 0,
            "total_tokens": totals.get("totalTokens", 0),
            "cached_input_tokens": totals.get("cachedInputTokens", 0),
            "cache_write_input_tokens": totals.get("cacheWriteInputTokens", 0),
            "output_tokens": totals.get("outputTokens", 0),
            "reasoning_output_tokens": totals.get("reasoningOutputTokens", 0),
            "model_context_window": totals.get("modelContextWindow", 0),
            "token_estimate_algorithm": "canonical_utf8_bytes_div_4_ceil",
            "estimated_task_tokens": self.packet_tokens,
            "estimated_evidence_tokens": self.source_bytes_tokens + self.platform_response_tokens,
            "task_tokens": self.packet_tokens,
            "evidence_tokens": self.source_bytes_tokens + self.platform_response_tokens,
            "ttft_ms": self.ttft_ms,
            "terminal_wall_ms": self.terminal_wall_ms,
            "proxy_time_ms": self.proxy_time_ms,
            "collaboration_rejections": self.collaboration_rejections,
            "terminal_report": self.terminal_report,
            "blocked": self.blocked.as_dict() if self.blocked else None,
        }


def aggregate_ordered_examiner_verdicts(verdicts: Iterable[Mapping[str, Any]], *, count: int | None = None) -> dict[str, Any]:
    rows = [dict(value) for value in verdicts]
    expected = len(rows) if count is None else count
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0 or len(rows) != expected:
        raise ChildRuntimeError("ordered Examiner verdict count is invalid")
    def row_ordinal(row: Mapping[str, Any]) -> Any:
        return row.get("question_ordinal", row.get("ordinal"))

    if [row_ordinal(row) for row in rows] != list(range(1, expected + 1)):
        raise ChildRuntimeError("ordered Examiner verdict ordinals are not contiguous")
    statuses = [row.get("status", row.get("verdict")) for row in rows]
    if any(status not in {"PASS", "FAIL", "BLOCKED"} for status in statuses):
        raise ChildRuntimeError("ordered Examiner verdict status is invalid")
    for index, row in enumerate(rows, start=1):
        if row_ordinal(row) != index:
            raise ChildRuntimeError("ordered Examiner verdict ordinal is invalid")
        if row.get("question_count", row.get("count")) != expected:
            raise ChildRuntimeError("ordered Examiner verdict count is invalid")
        if row.get("previous_question_ordinal") != (index - 1 if index > 1 else None):
            raise ChildRuntimeError("ordered Examiner previous ordinal is invalid")
        if row.get("next_question_ordinal") != (index + 1 if index < expected else None):
            raise ChildRuntimeError("ordered Examiner next ordinal is invalid")
        if row.get("final") is not (index == expected):
            raise ChildRuntimeError("ordered Examiner final marker is invalid")
    status = "BLOCKED" if "BLOCKED" in statuses else "FAIL" if "FAIL" in statuses else "PASS"
    return {
        "schema_version": "ExaminerOrderedVerdicts/v1",
        "count": expected,
        "verdicts": rows,
        "status": status,
        "previous": rows[-1].get("previous_question_ordinal"),
        "next": rows[-1].get("next_question_ordinal"),
        "final": True,
    }


class LeanExaminerRuntime:
    """Small opt-in host orchestration seam for fresh Source/Platform/Acceptance roles.

    Executors are intentionally injected: the production Codex adapter can provide a
    process-backed executor, while independent tests use deterministic executors.  Every
    call receives a new packet and metrics object; no prior report is passed to the next CQ.
    """

    def __init__(
        self,
        *,
        source_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        platform_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        acceptance_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        codex_adapter: Any | None = None,
        platform_read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        child_timeout_seconds: float = 90.0,
    ):
        if codex_adapter is not None:
            if any(executor is not None for executor in (source_executor, platform_executor, acceptance_executor)):
                raise ChildRuntimeError("Lean Examiner executors cannot mix Codex wiring")
            runner = getattr(codex_adapter, "run_lean_examiner_child", None)
            if not callable(runner):
                raise ChildRuntimeError("Codex Examiner executor is unavailable")

            def run_source(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                return runner(packet, metrics, timeout_seconds=child_timeout_seconds)

            def run_platform(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                if not isinstance(platform_read_key, str) or not platform_read_key:
                    raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
                return runner(
                    packet,
                    metrics,
                    read_key=platform_read_key,
                    platform_forwarder=platform_forwarder,
                    timeout_seconds=child_timeout_seconds,
                )

            def run_acceptance(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                return runner(packet, metrics, timeout_seconds=child_timeout_seconds)

            source_executor, platform_executor, acceptance_executor = (
                run_source,
                run_platform,
                run_acceptance,
            )
        if not all(callable(executor) for executor in (source_executor, platform_executor, acceptance_executor)):
            raise ChildRuntimeError("Lean Examiner executors are incomplete")
        self.source_executor = source_executor
        self.platform_executor = platform_executor
        self.acceptance_executor = acceptance_executor
        self._failure_metrics: tuple[dict[str, Any], ...] = ()

    @property
    def failure_metrics(self) -> tuple[dict[str, Any], ...]:
        """Return copied per-role snapshots captured by the last failed run."""

        return tuple(deepcopy(row) for row in self._failure_metrics)

    def _capture_failure_metrics(
        self,
        metrics: Sequence[ExaminerRunMetrics],
        error: BaseException,
    ) -> None:
        """Retain only recomputable metrics for a failed role stage."""

        snapshots = list(metrics)
        if isinstance(error, ExaminerRuntimeBlocked) and snapshots and snapshots[-1].blocked is None:
            snapshots[-1].blocked = error
        self._failure_metrics = tuple(metric.as_dict() for metric in snapshots)

    def run(self, questions: Sequence[Mapping[str, Any]], *, source_packets: Sequence[Mapping[str, Any]], platform_packets: Sequence[Mapping[str, Any]], ticket_binding: Mapping[str, Any], verdict_schema: Mapping[str, Any]) -> dict[str, Any]:
        count = len(questions)
        if count <= 0 or len(source_packets) != count or len(platform_packets) != count:
            raise ChildRuntimeError("Lean Examiner question/packet count is invalid")
        self._failure_metrics = ()
        verdicts: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        completed_metrics: list[ExaminerRunMetrics] = []
        for ordinal, question in enumerate(questions):
            source_payload = dict(source_packets[ordinal])
            platform_payload = dict(platform_packets[ordinal])
            question_ordinal = ordinal + 1
            source_payload.update(question=question.get("question"), ordinal=question_ordinal, count=count)
            platform_payload.update(
                question=question.get("question"),
                ordinal=question_ordinal,
                count=count,
                ticket_binding=platform_payload.get("ticket_binding", dict(ticket_binding)),
                allowed_read_tools=platform_payload.get("allowed_read_tools", list(PLATFORM_PROXY_READ_TOOLS)),
            )
            source_packet = build_source_examiner_packet(**source_payload)
            platform_packet = build_platform_examiner_packet(**platform_payload)
            source_metrics = ExaminerRunMetrics("source")
            try:
                source_metrics.bind_first_turn_input([{"type": "packet", "digest": source_packet.canonical_digest}], packet=source_packet)
                source_report = self.source_executor(source_packet, source_metrics)
                source_evidence_ids = _source_report_evidence_ids(source_packet, source_report)
                source_metrics.record_terminal_report(source_report)
            except BaseException as exc:
                self._capture_failure_metrics([*completed_metrics, source_metrics], exc)
                raise
            platform_metrics = ExaminerRunMetrics("platform")
            try:
                platform_metrics.bind_first_turn_input([{"type": "packet", "digest": platform_packet.canonical_digest}], packet=platform_packet)
                platform_report = self.platform_executor(platform_packet, platform_metrics)
                platform_evidence_ids = _platform_report_ref_ids(platform_report)
                platform_metrics.record_terminal_report(platform_report)
            except BaseException as exc:
                self._capture_failure_metrics([*completed_metrics, source_metrics, platform_metrics], exc)
                raise
            source_digest, platform_digest = _packet_digest(source_report), _packet_digest(platform_report)
            acceptance_metrics = ExaminerRunMetrics("acceptance")
            try:
                acceptance_packet = build_acceptance_examiner_packet(
                    question=question.get("question"), ticket_binding=dict(ticket_binding), ordinal=question_ordinal, count=count,
                    source_report=dict(source_report), platform_report=dict(platform_report),
                    source_report_digest=source_digest, platform_report_digest=platform_digest,
                    source_evidence_ref_ids=sorted(source_evidence_ids),
                    platform_evidence_ref_ids=sorted(platform_evidence_ids),
                    verdict_schema=dict(verdict_schema),
                )
                acceptance_metrics.bind_first_turn_input([{"type": "packet", "digest": acceptance_packet.canonical_digest}], packet=acceptance_packet)
                verdict = dict(self.acceptance_executor(acceptance_packet, acceptance_metrics))
                _validate_acceptance_evidence_ids(verdict, source_evidence_ids | platform_evidence_ids)
                verdict.setdefault("question_ordinal", question_ordinal)
                verdict.setdefault("question_count", count)
                verdict.setdefault("previous_question_ordinal", question_ordinal - 1 if question_ordinal > 1 else None)
                verdict.setdefault("next_question_ordinal", question_ordinal + 1 if question_ordinal < count else None)
                verdict.setdefault("final", question_ordinal == count)
                acceptance_metrics.record_terminal_verdict(verdict)
            except BaseException as exc:
                self._capture_failure_metrics([*completed_metrics, source_metrics, platform_metrics, acceptance_metrics], exc)
                raise
            verdicts.append(verdict)
            metrics.extend([source_metrics.as_dict(), platform_metrics.as_dict(), acceptance_metrics.as_dict()])
            completed_metrics.extend([source_metrics, platform_metrics, acceptance_metrics])
            if not (
                verdict.get("status", verdict.get("verdict")) == "PASS"
                and verdict.get("current") is True
                and verdict.get("usable") is True
            ):
                return {
                    "schema_version": "ExaminerOrderedVerdicts/v1",
                    "count": count,
                    "verdicts": verdicts,
                    "status": verdict.get("status", verdict.get("verdict")),
                    "complete": False,
                    "stopped_at": question_ordinal,
                    "next": question_ordinal + 1 if question_ordinal < count else None,
                    "final": question_ordinal == count,
                    "metrics": metrics,
                }
        result = aggregate_ordered_examiner_verdicts(verdicts, count=count)
        result["complete"] = True
        result["metrics"] = metrics
        return result


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


def _safe_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


_REPORT_SEMANTIC_FIELDS = frozenset(
    {"answerability", "conclusion", "evidence", "coverage", "gaps", "evidence_refs"}
)
_REPORT_PLATFORM_LOCATOR_FIELDS = frozenset(
    {"ref_id", "tool", "request_digest", "response_digest", "artifact_path", "page"}
)


def _validate_report_sink_payload(value: Any, *, kind: str) -> dict[str, Any]:
    """Validate the kind-specific child payload before invoking the Host callback."""

    if kind == "acceptance":
        expected = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ChildRuntimeError("acceptance verdict fields drift")
        if value["status"] not in {"PASS", "FAIL", "BLOCKED"} or not isinstance(value["answer"], str) or not value["answer"]:
            raise ChildRuntimeError("acceptance verdict is invalid")
        if not isinstance(value["evidence_ref_ids"], list) or any(not isinstance(item, str) or not item for item in value["evidence_ref_ids"]):
            raise ChildRuntimeError("acceptance verdict evidence refs are invalid")
        if not isinstance(value["current"], bool) or not isinstance(value["usable"], bool):
            raise ChildRuntimeError("acceptance verdict flags are invalid")
        if value["status"] == "PASS" and (value["failure_layer"] is not None or value["blocked_reason"] is not None):
            raise ChildRuntimeError("acceptance PASS carries failure fields")
        return dict(value)
    if kind not in {"source", "platform"}:
        raise ChildRuntimeError("report sink kind is invalid")
    if not isinstance(value, Mapping) or set(value) != _REPORT_SEMANTIC_FIELDS:
        raise ChildRuntimeError("report payload fields drift")
    if value["answerability"] not in {"answerable", "insufficient-evidence", "unavailable"}:
        raise ChildRuntimeError("report answerability is invalid")
    if not isinstance(value["conclusion"], str) or not value["conclusion"]:
        raise ChildRuntimeError("report conclusion is invalid")
    if not isinstance(value["evidence"], list) or not isinstance(value["gaps"], list):
        raise ChildRuntimeError("report evidence/gaps are invalid")
    coverage = value["coverage"]
    if (
        not isinstance(coverage, Mapping)
        or set(coverage) != {"queries_or_sections", "complete"}
        or not isinstance(coverage["queries_or_sections"], list)
        or not isinstance(coverage["complete"], bool)
    ):
        raise ChildRuntimeError("report coverage is invalid")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or not refs:
        raise ChildRuntimeError("report evidence_refs are invalid")
    for ref in refs:
        if not isinstance(ref, Mapping):
            raise ChildRuntimeError("report evidence locator is invalid")
        if kind == "source":
            if set(ref) != {"location"} or not isinstance(ref["location"], str) or not ref["location"]:
                raise ChildRuntimeError("source evidence locator is invalid")
            path = ref["location"].split("#", 1)[0]
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ChildRuntimeError("source evidence locator path is invalid")
        else:
            if set(ref) != _REPORT_PLATFORM_LOCATOR_FIELDS:
                raise ChildRuntimeError("platform evidence locator fields drift")
            if not isinstance(ref["ref_id"], str) or not ref["ref_id"]:
                raise ChildRuntimeError("platform evidence locator ref_id is invalid")
            if not isinstance(ref["tool"], str) or not ref["tool"]:
                raise ChildRuntimeError("platform evidence locator tool is invalid")
            for field in ("request_digest", "response_digest"):
                if not isinstance(ref[field], str) or len(ref[field]) != 64 or any(
                    char not in "0123456789abcdef" for char in ref[field]
                ):
                    raise ChildRuntimeError(f"platform evidence locator {field} is invalid")
            path = ref["artifact_path"]
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ChildRuntimeError("platform evidence locator path is invalid")
            page = ref["page"]
            if not isinstance(page, Mapping) or set(page) != {
                "ordinal", "input_cursor", "output_cursor", "has_more", "sequence_complete"
            }:
                raise ChildRuntimeError("platform evidence locator page is invalid")
            if not isinstance(page["ordinal"], int) or page["ordinal"] < 0:
                raise ChildRuntimeError("platform evidence locator page ordinal is invalid")
            if not isinstance(page["input_cursor"], (str, type(None))) or not isinstance(
                page["output_cursor"], (str, type(None))
            ):
                raise ChildRuntimeError("platform evidence locator page cursors are invalid")
            if not isinstance(page["has_more"], bool) or not isinstance(
                page["sequence_complete"], bool
            ):
                raise ChildRuntimeError("platform evidence locator page flags are invalid")
            if page["has_more"] and page["sequence_complete"]:
                raise ChildRuntimeError("platform evidence locator page is incomplete and complete")
    return dict(value)


def _source_report_evidence_ids(packet: ExaminerRolePacket, report: Mapping[str, Any]) -> set[str]:
    """Bind Source report locations to this packet's approved manifest."""

    approved: dict[str, str] = {}
    sources = packet.payload.get("approved_sources")
    if not isinstance(sources, (list, tuple)):
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="source")
    for source in sources:
        if not isinstance(source, Mapping):
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="source")
        path, digest = source.get("path"), source.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or path in approved:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="source")
        approved[path] = digest
    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list) or not refs:
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="source")
    seen_paths: set[str] = set()
    result: set[str] = set()
    for ref in refs:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("location"), str):
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="source")
        path = ref["location"].split("#", 1)[0]
        if path not in approved or path in seen_paths:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="source", evidence={"path": path}
            )
        seen_paths.add(path)
        result.add(f"source:{_packet_digest({'path': path, 'sha256': approved[path]})}")
    return result


def _platform_report_ref_ids(report: Mapping[str, Any]) -> set[str]:
    """Return only report-local Platform ref IDs after shape validation."""

    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list) or not refs:
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
    result: set[str] = set()
    for ref in refs:
        ref_id = ref.get("ref_id") if isinstance(ref, Mapping) else None
        if not isinstance(ref_id, str) or not ref_id or ref_id in result:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        result.add(ref_id)
    return result


def _validate_platform_report_receipts(report: Mapping[str, Any], resource: Any) -> set[str]:
    """Bind every Platform locator to one current-child proxy receipt and page."""

    proxy = getattr(resource, "proxy", None)
    snapshots = getattr(proxy, "receipt_snapshot", None) if proxy is not None else None
    if callable(snapshots):
        snapshots = snapshots()
    if not isinstance(snapshots, (list, tuple)):
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
    receipts = tuple(snapshots)
    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "report-refs-invalid",
                "report_ref_count": 0,
                "proxy_receipt_count": len(receipts),
            },
        )
    if not receipts:
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "receipts-empty",
                "report_ref_count": len(refs),
                "proxy_receipt_count": 0,
            },
        )
    if len(refs) != len(receipts):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "receipt-count-mismatch",
                "report_ref_count": len(refs),
                "proxy_receipt_count": len(receipts),
            },
        )
    result: set[str] = set()
    previous_ref: Mapping[str, Any] | None = None
    previous_page: Mapping[str, Any] | None = None
    for index, ref in enumerate(refs):
        if not isinstance(ref, Mapping):
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        receipt = receipts[index]
        if getattr(receipt, "ordinal", None) != index:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        key = tuple(ref.get(name) for name in ("tool", "request_digest", "response_digest", "artifact_path"))
        receipt_key = tuple(
            getattr(receipt, name, None)
            for name in ("tool", "request_digest", "response_digest", "artifact_path")
        )
        if key != receipt_key:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        page = ref.get("page")
        if (
            not isinstance(page, Mapping)
            or not isinstance(page.get("ordinal"), int)
            or page.get("ordinal") < 0
            or not isinstance(page.get("input_cursor"), (str, type(None)))
            or not isinstance(page.get("output_cursor"), (str, type(None)))
            or not isinstance(page.get("has_more"), bool)
            or not isinstance(page.get("sequence_complete"), bool)
        ):
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        if page["ordinal"] == 0:
            if page["input_cursor"] is not None or (previous_page is not None and previous_page.get("has_more")):
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        else:
            if (
                previous_ref is None
                or previous_page is None
                or previous_page.get("has_more") is not True
                or ref.get("tool") != previous_ref.get("tool")
                or page["ordinal"] != previous_page.get("ordinal", -1) + 1
                or page["input_cursor"] != previous_page.get("output_cursor")
            ):
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        if page["has_more"]:
            if page["sequence_complete"] or not isinstance(page["output_cursor"], str) or not page["output_cursor"]:
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
            if index == len(refs) - 1:
                raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        elif page["sequence_complete"] is not True or page["output_cursor"] is not None:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        ref_id = ref.get("ref_id")
        if not isinstance(ref_id, str) or not ref_id or ref_id in result:
            raise ExaminerRuntimeBlocked("acceptance-evidence", role="platform")
        result.add(ref_id)
        previous_ref, previous_page = ref, page
    return result


def _validate_acceptance_evidence_ids(verdict: Mapping[str, Any], allowed_ids: set[str]) -> None:
    """Accept only current Source/Platform evidence IDs; PASS must cite one."""

    ids = verdict.get("evidence_ref_ids") if isinstance(verdict, Mapping) else None
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
    if len(ids) != len(set(ids)) or any(item not in allowed_ids for item in ids):
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")
    if verdict.get("status") == "PASS" and not ids:
        raise ExaminerRuntimeBlocked("acceptance-evidence", role="acceptance")


def _private_dir(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ChildRuntimeError("private runtime directory is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise ChildRuntimeError("private runtime directory is not 0700")


def _write_private(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise ChildRuntimeError("private runtime artifact already exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _copy_private(source: Path, target: Path, mode: int) -> None:
    """Copy one trusted regular file into a private tree without following links."""
    try:
        metadata = os.lstat(source)
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ChildRuntimeError("private source is invalid")
    _private_dir(target.parent)
    descriptor = -1
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ChildRuntimeError("private source is invalid")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            payload = stream.read()
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _write_private(target, payload, mode)


PLATFORM_PROXY_READ_TOOLS: tuple[str, ...] = (
    "check_platform_health",
    "get_project_build_context",
    "get_build_session",
    "get_modeling_context",
    "get_ontology_workspace_context",
    "get_ontology_read_model",
    "get_entity_statement_context",
    "get_semantic_read_model",
    "query_semantic_context",
    "semantic_sparql_query",
    "describe_semantic_graph_set",
    "list_semantic_derived_pointers",
    "inspect_semantic_projection_status",
    "list_evidence_references",
    "get_evidence_reference",
    "get_ontology_lineage",
    "inspect_semantic_statement_provenance",
    "get_semantic_reasoning_run",
    "get_semantic_validation_run",
    "list_semantic_reasoning_runs",
    "list_semantic_validation_runs",
)


# The R2.3-006 wrapper schema is deliberately represented as a small JSON-Schema
# subset.  It is frozen here rather than inferred from a backend response: unknown,
# missing, and wrong-type arguments therefore fail before a forwarder is queued.
_EXAMINER_SCOPE_SCHEMA: dict[str, Any] = {
    "project_id": {"type": "string"},
    "ontology_id": {"type": "string"},
    "graph_set_id": {"type": "string"},
    "ticket_digest": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
    "model_state_digest": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
}
_EXAMINER_TOOL_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "check_platform_health": {},
    "get_project_build_context": {
        "recent_session_limit": {"type": "integer", "minimum": 0},
        "recent_session_cursor": {"type": "integer", "minimum": 0},
    },
    "get_build_session": {
        "session_id": {"type": "string"},
        "checkpoint_limit": {"type": "integer", "minimum": 1},
        "checkpoint_cursor": {"type": ["integer", "null"], "minimum": 0},
    },
    "get_modeling_context": {},
    "get_ontology_workspace_context": {},
    "get_ontology_read_model": {
        "model_name": {"type": "string", "enum": ["classes", "entities", "facts", "rules"]},
        "include": {"type": "string", "enum": ["asserted"]},
        "allow_stale_derived": {"type": "boolean", "const": False},
        "field_set": {"type": "string", "enum": ["summary", "full"]},
        "limit": {"type": "integer", "minimum": 1},
        "entity_iri": {"type": "string"}, "class_iri": {"type": "string"},
        "kind": {"type": "string"}, "q": {"type": "string"},
    },
    "get_entity_statement_context": {"entity_iri": {"type": "string"}},
    "get_semantic_read_model": {
        "model_name": {"type": "string"},
        "include": {"type": "string"},
        "allow_stale_derived": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1},
    },
    "query_semantic_context": {
        "scope_mode": {"type": "string", "const": "ontologies"},
        "query": {"type": ["string", "null"]}, "queries": {"type": ["array", "null"], "items": {"type": "string"}},
        "ontology_ids": {"type": "array", "items": {"type": "string"}},
        "resource_types": {"type": ["array", "null"], "items": {"type": "string"}},
        "assertion_types": {"type": ["array", "null"], "items": {"type": "string"}}, "search_mode": {"type": "string"},
        "depth": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1},
        "context_limit": {"type": "integer", "minimum": 1},
        "match_cursor": {"type": "string"}, "context_cursor": {"type": "string"},
    },
    "semantic_sparql_query": {
        "scope_mode": {"type": "string", "const": "ontologies"}, "query": {"type": "string"},
        "ontology_ids": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": ["number", "null"]},
        "result_limit": {"type": ["integer", "null"], "minimum": 1},
    },
    "describe_semantic_graph_set": {},
    "list_semantic_derived_pointers": {
        "result_kind": {"type": "string"}, "status": {"type": "string"},
    },
    "inspect_semantic_projection_status": {},
    "list_evidence_references": {
        "search": {"type": "string"}, "limit": {"type": "integer", "minimum": 1},
        "offset": {"type": "integer", "minimum": 0},
    },
    "get_evidence_reference": {"reference_id": {"type": "string"}},
    "get_ontology_lineage": {
        "target_type": {"type": "string"}, "target_id": {"type": "string"},
        "include_history": {"type": "boolean"}, "max_depth": {"type": "integer", "minimum": 1},
        "limit": {"type": "integer", "minimum": 1},
    },
    "inspect_semantic_statement_provenance": {
        "statement_iri": {"type": "string"}, "include": {"type": "string"},
    },
    "get_semantic_reasoning_run": {"reasoning_run_id": {"type": "string"}},
    "get_semantic_validation_run": {"validation_run_id": {"type": "string"}},
    "list_semantic_reasoning_runs": {
        "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0},
        "kind": {"type": "string"},
    },
    "list_semantic_validation_runs": {
        "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0},
        "kind": {"type": "string"},
    },
}


def examiner_proxy_schemas(tools: Iterable[str] = PLATFORM_PROXY_READ_TOOLS) -> dict[str, dict[str, Any]]:
    """Return detached exact schemas for the requested read-tool inventory."""

    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if tool not in PLATFORM_PROXY_READ_TOOLS:
            raise ChildRuntimeError("Examiner proxy schema contains a non-read tool")
        properties = {**_EXAMINER_SCOPE_SCHEMA, **_EXAMINER_TOOL_FIELDS.get(tool, {})}
        required = list(_EXAMINER_SCOPE_SCHEMA)
        required.extend({
            "get_project_build_context": [],
            "get_build_session": ["session_id"],
            "get_modeling_context": [],
            "get_ontology_workspace_context": [],
            "get_ontology_read_model": ["model_name"],
            "get_entity_statement_context": ["entity_iri"],
            "get_semantic_read_model": ["model_name"],
            "query_semantic_context": ["scope_mode", "ontology_ids"],
            "semantic_sparql_query": ["scope_mode", "query", "ontology_ids"],
            "describe_semantic_graph_set": [],
            "list_semantic_derived_pointers": [],
            "inspect_semantic_projection_status": [],
            "list_evidence_references": [],
            "get_evidence_reference": ["reference_id"],
            "get_ontology_lineage": ["target_type", "target_id"],
            "inspect_semantic_statement_provenance": ["statement_iri"],
            "get_semantic_reasoning_run": ["reasoning_run_id"],
            "get_semantic_validation_run": ["validation_run_id"],
            "list_semantic_reasoning_runs": [],
            "list_semantic_validation_runs": [],
        }.get(tool, []))
        schema: dict[str, Any] = {
            "type": "object",
            "properties": json.loads(json.dumps(properties)),
            "required": required,
            "additionalProperties": False,
        }
        if tool == "query_semantic_context":
            schema["anyOf"] = [{"required": ["query"]}, {"required": ["queries"]}]
        schemas[tool] = schema
    return schemas


def _schema_type_matches(value: Any, expected: str | Sequence[str]) -> bool:
    if isinstance(expected, (list, tuple)):
        return any(_schema_type_matches(value, item) for item in expected)
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def validate_examiner_proxy_arguments(tool: str, arguments: Mapping[str, Any], schema: Mapping[str, Any], *, scope: Mapping[str, str]) -> dict[str, Any]:
    """Validate one exact proxy call without invoking a forwarder/backend."""

    if not isinstance(arguments, Mapping) or not isinstance(schema, Mapping):
        raise ChildRuntimeError("Examiner proxy arguments/schema are invalid")
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or schema.get("additionalProperties") is not False:
        raise ChildRuntimeError("Examiner proxy schema must be closed")
    required = schema.get("required", ())
    if not isinstance(required, list) or set(arguments) - set(properties) or set(required) - set(arguments):
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any(
        isinstance(branch, Mapping) and isinstance(branch.get("required"), list)
        and set(branch["required"]).issubset(arguments)
        for branch in any_of
    ) is False:
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    for key, rule in properties.items():
        if key not in arguments or not isinstance(rule, Mapping):
            continue
        value = arguments[key]
        if "const" in rule and value != rule["const"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if "enum" in rule and value not in rule["enum"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if not _schema_type_matches(value, rule.get("type", "")):
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        item_schema = rule.get("items")
        if isinstance(item_schema, Mapping) and isinstance(value, list):
            for item in value:
                if not _schema_type_matches(item, item_schema.get("type", "")):
                    raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if isinstance(value, (int, float)) and "minimum" in rule and value < rule["minimum"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        pattern = rule.get("pattern")
        if isinstance(pattern, str) and (not isinstance(value, str) or re.fullmatch(pattern, value) is None):
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    for key, value in scope.items():
        if key in required and arguments.get(key) != value:
            raise ChildRuntimeError(f"exact scope rejected for {tool}")
    if tool == "query_semantic_context" and (
        ("query" in arguments and "queries" in arguments)
        or ("query" not in arguments and "queries" not in arguments)
    ):
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    return dict(arguments)


@dataclass(frozen=True)
class ProxyReceipt:
    # This is a child-visible virtual identity, never the host AF_UNIX path.  Host paths
    # are runtime-only and must not enter child-config or durable cleanup evidence.
    socket_identity: str
    token_digest: str
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    allowed_tools: tuple[str, ...]
    config_digest: str


@dataclass(frozen=True)
class ProxyCallReceipt:
    """Sanitized receipt for one successful scoped read.

    The receipt intentionally contains no key, token, raw response, socket path, or
    host filesystem location.  ``artifact_path`` is a Runner-relative retained
    evidence name and is safe for the child to echo in its typed report reference.
    """

    ordinal: int
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    model_state_digest: str
    tool: str
    request_digest: str
    response_digest: str
    artifact_path: str


class ScopedReadProxy:
    """A Runner-owned, ticket-bound AF_UNIX read proxy.

    ``read_key`` is intentionally retained only in this object.  It is never written to
    the child home, environment, config, receipt, or proxy response.  The optional
    ``forward`` callback is the only place an integration may attach a real platform
    read; leaving it unset gives deterministic tests a safe offline proxy.
    """

    def __init__(
        self,
        *,
        socket_path: Path,
        token: str,
        read_key: str,
        project_id: str,
        ontology_id: str,
        graph_set_id: str,
        ticket_digest: str,
        model_state_digest: str,
        allowed_tools: list[str] | tuple[str, ...],
        forward: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        acceptance_round_id: str | None = None,
        child_handle_digest: str | None = None,
        exact_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.token = token
        self._read_key: str | None = read_key
        self.project_id = _safe_id(project_id, "project_id")
        self.ontology_id = _safe_id(ontology_id, "ontology_id")
        self.graph_set_id = _safe_id(graph_set_id, "graph_set_id")
        self.ticket_digest = _safe_digest(ticket_digest, "ticket_digest")
        self.model_state_digest = _safe_digest(model_state_digest, "model_state_digest")
        normalized = tuple(str(tool) for tool in allowed_tools)
        if (
            not normalized
            or len(set(normalized)) != len(normalized)
            or any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized)
        ):
            raise ChildRuntimeError("platform proxy allowlist is not read-only")
        self.allowed_tools = normalized
        self.exact_schemas = (
            {str(tool): json.loads(json.dumps(schema)) for tool, schema in exact_schemas.items()}
            if exact_schemas is not None
            else None
        )
        if self.exact_schemas is not None and set(self.exact_schemas) != set(self.allowed_tools):
            raise ChildRuntimeError("Examiner proxy exact schema inventory is incomplete")
        self._forward = forward
        self.acceptance_round_id = (
            _safe_id(acceptance_round_id, "acceptance_round_id")
            if acceptance_round_id is not None
            else "offline-round"
        )
        self.child_handle_digest = (
            _safe_digest(child_handle_digest, "child_handle_digest")
            if child_handle_digest is not None
            else "0" * 64
        )
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.requests: list[dict[str, Any]] = []
        self._call_receipts: list[ProxyCallReceipt] = []
        self.post_revoke_denials = 0
        self.backend_calls = 0
        self.schema_rejections = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._read_key is not None

    @property
    def token_digest(self) -> str:
        return hashlib.sha256(self.token.encode("utf-8")).hexdigest()

    @property
    def receipt(self) -> ProxyReceipt:
        config = {
            "server": "platform_read_proxy",
            "scope": {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
            },
            "ticket_digest": self.ticket_digest,
            "model_state_digest": self.model_state_digest,
            "allowed_tools": list(self.allowed_tools),
        }
        return ProxyReceipt(
            socket_identity="/agent/home/platform-proxy.sock",
            token_digest=self.token_digest,
            project_id=self.project_id,
            ontology_id=self.ontology_id,
            graph_set_id=self.graph_set_id,
            ticket_digest=self.ticket_digest,
            allowed_tools=self.allowed_tools,
            config_digest=_digest(config),
        )

    @property
    def receipt_snapshot(self) -> tuple[ProxyCallReceipt, ...]:
        """Return immutable sanitized receipts for successful calls only."""

        with self._lock:
            return tuple(self._call_receipts)

    def start(self) -> ProxyReceipt:
        with self._lock:
            if self._server is not None:
                return self.receipt
            self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.socket_path.exists() or self.socket_path.is_symlink():
                raise ChildRuntimeError("platform proxy socket already exists")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(self.socket_path))
                os.chmod(self.socket_path, 0o600)
                server.listen(8)
            except Exception:
                server.close()
                self.socket_path.unlink(missing_ok=True)
                raise
            self._server = server
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="acceptance-read-proxy", daemon=True)
            self._thread.start()
            return self.receipt

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2.0)
                try:
                    raw = b""
                    while b"\n" not in raw and len(raw) < 128 * 1024:
                        block = conn.recv(8192)
                        if not block:
                            break
                        raw += block
                    request = json.loads(raw.split(b"\n", 1)[0].decode("utf-8")) if raw else {}
                    response = self.handle(request)
                except Exception as exc:
                    response = {"ok": False, "error": "proxy-request-invalid", "code": type(exc).__name__}
                try:
                    conn.sendall(_canonical(response) + b"\n")
                except OSError:
                    pass

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ChildRuntimeError("proxy request is invalid")
        with self._lock:
            if self._read_key is None:
                self.post_revoke_denials += 1
                return {"ok": False, "error": "read-key-revoked", "code": "read-key-revoked"}
            if request.get("token") != self.token:
                return {"ok": False, "error": "proxy-token-invalid", "code": "proxy-token-invalid"}
            operation = request.get("operation")
            if operation == "tools/list":
                return {"ok": True, "tools": list(self.allowed_tools)}
            if operation != "tools/call":
                return {"ok": False, "error": "proxy-operation-denied", "code": "proxy-operation-denied"}
            tool = request.get("tool")
            arguments = request.get("arguments")
            if not isinstance(tool, str) or tool not in self.allowed_tools:
                return {"ok": False, "error": "read-tool-denied", "code": "read-tool-denied"}
            if not isinstance(arguments, Mapping):
                self.schema_rejections += 1
                return {"ok": False, "error": "read-arguments-invalid", "code": "read-arguments-invalid", "backend_calls": 0}
            required = {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
                "ticket_digest": self.ticket_digest,
                "model_state_digest": self.model_state_digest,
            }
            if any(arguments.get(key) != value for key, value in required.items()):
                return {"ok": False, "error": "read-scope-denied", "code": "read-scope-denied", "backend_calls": 0}
            if (
                self.exact_schemas is not None
                and tool in {"query_semantic_context", "semantic_sparql_query"}
                and arguments.get("ontology_ids") != [self.ontology_id]
            ):
                return {
                    "ok": False,
                    "error": "read-scope-denied",
                    "code": "read-scope-denied",
                    "backend_calls": 0,
                }
            if self.exact_schemas is not None:
                try:
                    arguments = validate_examiner_proxy_arguments(
                        tool, arguments, self.exact_schemas[tool], scope=required
                    )
                except ChildRuntimeError:
                    self.schema_rejections += 1
                    return {
                        "ok": False,
                        "error": "read-arguments-schema",
                        "code": "read-arguments-schema",
                        "backend_calls": 0,
                    }
            request_digest = _digest({"tool": tool, "arguments": dict(arguments)})
            self.requests.append({"tool": tool, "request_digest": request_digest})
            if self._forward is None:
                return {"ok": False, "error": "platform-forwarding-unconfigured", "code": "platform-forwarding-unconfigured"}
            try:
                self.backend_calls += 1
                result = dict(self._forward(tool, arguments, self._read_key))
            except Exception:
                return {"ok": False, "error": "platform-forward-failed", "code": "platform-forward-failed", "backend_calls": self.backend_calls}
            response_digest = _digest(result)
            artifact_path = (
                f"acceptance/{self.acceptance_round_id}/platform-read/"
                f"{self.child_handle_digest}/{len(self._call_receipts)}.json"
            )
            self._call_receipts.append(
                ProxyCallReceipt(
                    ordinal=len(self._call_receipts),
                    project_id=self.project_id,
                    ontology_id=self.ontology_id,
                    graph_set_id=self.graph_set_id,
                    ticket_digest=self.ticket_digest,
                    model_state_digest=self.model_state_digest,
                    tool=tool,
                    request_digest=request_digest,
                    response_digest=response_digest,
                    artifact_path=artifact_path,
                )
            )
            call_total = len(self._call_receipts)
            return {
                "ok": True,
                "result": result,
                "request_digest": request_digest,
                "response_digest": response_digest,
                "artifact_path": artifact_path,
                "call_ordinal": len(self._call_receipts) - 1,
                "call_total": call_total,
            }

    def revoke(self) -> dict[str, Any]:
        with self._lock:
            self._read_key = None
            return {"status": "revoked", "post_revoke_denials": self.post_revoke_denials}

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            finally:
                self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)

    def destroy(self) -> None:
        self.revoke()
        self.stop()


@dataclass
class _ForwardRequest:
    tool: str
    arguments: Mapping[str, Any]
    result: Any = None
    error: BaseException | None = None
    complete: threading.Event = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.complete = threading.Event()


class McpReadForwarder:
    """Host-side synchronous facade over the canonical backend MCP server.

    The forwarder owns the only subprocess environment containing the temporary read
    key.  Its environment is allowlisted and its child-facing API is restricted to the
    ticket's read tools.  Calls are serialized through one MCP ``ClientSession`` so
    pagination cursors and result envelopes remain byte-for-byte typed values rather
    than being reimplemented by the Runner.
    """

    _SCOPED_ENVELOPE_FIELDS = frozenset(
        {"ticket_digest", "model_state_digest"}
    )

    def __init__(
        self,
        *,
        repository_root: Path,
        read_key: str,
        expected_tools: list[str] | tuple[str, ...],
        command: str | None = None,
        args: list[str] | None = None,
        process_env: Mapping[str, str] | None = None,
        client_factory: Callable[..., Any] | None = None,
        exact_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if not isinstance(read_key, str) or not read_key:
            raise ChildRuntimeError("forwarder read key is unavailable")
        normalized = tuple(str(tool) for tool in expected_tools)
        if not normalized or len(set(normalized)) != len(normalized):
            raise ChildRuntimeError("forwarder tool inventory is invalid")
        if any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized):
            raise ChildRuntimeError("forwarder tool inventory is not read-only")
        self.repository_root = repository_root.resolve()
        self.read_key = read_key
        self.expected_tools = normalized
        self.command = command or str(self.repository_root / "backend" / ".venv" / "bin" / "python")
        self.args = list(args or ["-m", "app.mcp.server"])
        backend_root = self.repository_root / "backend"
        # Never inherit the caller's environment wholesale: especially do not leak a
        # broader API key, proxy, plugin, or Codex credential into the canonical server.
        allowlisted = {
            "ONTOLOGY_MCP_API_KEY": read_key,
            "PYTHONPATH": str(backend_root),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(backend_root),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if process_env:
            for name in ("DATABASE_URL", "OXIGRAPH_URL", "EMBEDDING_BASE_URL", "EMBEDDING_MODEL"):
                value = process_env.get(name)
                if isinstance(value, str) and value:
                    allowlisted[name] = value
        self.process_env = allowlisted
        self.client_factory = client_factory
        self.exact_schemas = (
            {str(tool): json.loads(json.dumps(schema)) for tool, schema in exact_schemas.items()}
            if exact_schemas is not None
            else None
        )
        self.backend_calls = 0
        self.schema_rejections = 0
        self._queue: queue.Queue[_ForwardRequest | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._startup_error: BaseException | None = None
        self._tool_schemas: dict[str, Mapping[str, Any]] = {}
        self._inventory_digest: str | None = None

    @property
    def inventory_digest(self) -> str | None:
        return self._inventory_digest

    @property
    def active(self) -> bool:
        return self._thread is not None and not self._stopped.is_set()

    def start(self, *, timeout: float = 20.0) -> "McpReadForwarder":
        if self._thread is not None:
            if self._startup_error is not None:
                raise ChildRuntimeError("canonical MCP forwarder failed to start") from self._startup_error
            return self
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="acceptance-mcp-forwarder", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=max(0.1, timeout)):
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup timed out")
        if self._startup_error is not None:
            error = self._startup_error
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup failed") from error
        return self

    def _run(self) -> None:
        try:
            asyncio.run(self._session_loop())
        except BaseException as exc:  # surfaced to start()/forward() without leaking text
            self._startup_error = exc
            self._ready.set()
            while True:
                request = self._queue.get()
                if request is None:
                    return
                request.error = ChildRuntimeError("canonical MCP forwarder is unavailable")
                request.complete.set()

    async def _session_loop(self) -> None:
        # Imports are deferred so deterministic offline tests do not need to start the
        # backend or initialize its dependency graph.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        parameters = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=dict(self.process_env),
            cwd=str(self.repository_root / "backend"),
        )
        factory = self.client_factory or stdio_client
        async with factory(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                tools = getattr(listed, "tools", ())
                inventory: dict[str, Mapping[str, Any]] = {}
                for tool in tools if isinstance(tools, (list, tuple)) else ():
                    name = getattr(tool, "name", None)
                    if isinstance(name, str):
                        schema = getattr(tool, "inputSchema", None)
                        inventory[name] = schema if isinstance(schema, Mapping) else {}
                # The canonical server may expose additional write tools.  We require
                # every frozen read wrapper to exist and expose only the exact ticket
                # inventory through this proxy; no extra tool can cross the boundary.
                missing = set(self.expected_tools) - set(inventory)
                if missing:
                    raise ChildRuntimeError("canonical MCP read tool inventory is incomplete")
                self._tool_schemas = {name: inventory[name] for name in self.expected_tools}
                self._inventory_digest = _digest(
                    {"canonical_tools": sorted(inventory), "ticket_tools": list(self.expected_tools)}
                )
                self._ready.set()
                while not self._stopped.is_set():
                    request = await asyncio.to_thread(self._queue.get)
                    if request is None:
                        return
                    try:
                        schema = self._tool_schemas.get(request.tool)
                        if schema is None:
                            raise ChildRuntimeError("forwarder tool is outside ticket inventory")
                        arguments = dict(request.arguments)
                        exact = self.exact_schemas.get(request.tool) if self.exact_schemas is not None else None
                        if exact is not None:
                            scope = {
                                key: arguments[key]
                                for key in ("project_id", "ontology_id", "graph_set_id", "ticket_digest", "model_state_digest")
                                if key in arguments
                            }
                            arguments = validate_examiner_proxy_arguments(
                                request.tool, arguments, exact, scope=scope
                            )
                        properties = schema.get("properties") if isinstance(schema, Mapping) else None
                        # The wrapper validates the complete ticket envelope first;
                        # this explicit projection then removes only wrapper control
                        # fields not accepted by the canonical backend tool.
                        if isinstance(properties, Mapping):
                            arguments = {
                                key: value for key, value in arguments.items() if key in properties
                            }
                        self.backend_calls += 1
                        result = await session.call_tool(request.tool, arguments)
                        request.result = self._decode_result(result)
                    except BaseException as exc:
                        if isinstance(exc, ChildRuntimeError) and "schema" in str(exc):
                            self.schema_rejections += 1
                        request.error = exc
                    finally:
                        request.complete.set()

    @staticmethod
    def _decode_result(result: Any) -> Mapping[str, Any]:
        if bool(getattr(result, "isError", False)):
            raise ChildRuntimeError("canonical MCP read tool returned an error")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, Mapping):
            return dict(structured)
        content = getattr(result, "content", ())
        for item in content if isinstance(content, (list, tuple)) else ():
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                return dict(value)
            return {"value": value}
        raise ChildRuntimeError("canonical MCP read tool returned no typed data")

    def forward(self, tool: str, arguments: Mapping[str, Any], read_key: str) -> Mapping[str, Any]:
        if read_key != self.read_key or not self.active:
            raise ChildRuntimeError("forwarder read key is unavailable")
        request = _ForwardRequest(tool=tool, arguments=dict(arguments))
        self._queue.put(request)
        if not request.complete.wait(timeout=30):
            raise ChildRuntimeError("canonical MCP read tool timed out")
        if request.error is not None:
            raise ChildRuntimeError("canonical MCP read tool failed") from request.error
        if not isinstance(request.result, Mapping):
            raise ChildRuntimeError("canonical MCP read result is not typed")
        return dict(request.result)

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout=2)
        self._thread = None
        self.read_key = ""
        self.process_env.pop("ONTOLOGY_MCP_API_KEY", None)


class ReportSinkServer:
    """Write-only private child report endpoint; never Team Transport."""

    def __init__(
        self,
        socket_path: Path,
        token: str,
        submit: Callable[[Mapping[str, Any]], Any],
        kind: str | None = None,
    ):
        self.socket_path = socket_path
        self.token = token
        self._submit = submit
        if kind is not None and kind not in {"source", "platform", "acceptance"}:
            raise ChildRuntimeError("report sink kind is invalid")
        self.kind = kind
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._submitted = False

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise ChildRuntimeError("report sink socket already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(2)
        except Exception:
            server.close()
            self.socket_path.unlink(missing_ok=True)
            raise
        server.settimeout(0.2)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="acceptance-report-sink", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(128 * 1024)
                    request = json.loads(data.decode("utf-8")) if data else {}
                    if not isinstance(request, Mapping):
                        response = {"ok": False, "code": "report-invalid"}
                    elif request.get("token") != self.token:
                        response = {"ok": False, "code": "report-token-invalid"}
                    elif self._submitted:
                        response = {"ok": False, "code": "report-already-submitted"}
                    elif not isinstance(request.get("report"), Mapping):
                        response = {"ok": False, "code": "report-invalid"}
                    else:
                        report = request["report"]
                        if self.kind is not None:
                            report = _validate_report_sink_payload(report, kind=self.kind)
                        self._submit(report)
                        self._submitted = True
                        response = {"ok": True}
                    conn.sendall(_canonical(response))
                except Exception:
                    try:
                        conn.sendall(_canonical({"ok": False, "code": "report-rejected"}))
                    except OSError:
                        pass

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            server.close()
        self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)


def child_config_digest(config: Mapping[str, Any]) -> str:
    """Compute a public config binding without retaining secrets."""
    return _digest(config)


def prepare_child_tree(
    *,
    private_root: Path,
    source_bytes: Mapping[str, bytes] | None = None,
    host_auth: Path | None = None,
    instructions: bytes = b"",
    skill_name: str,
    skill_bytes: bytes,
) -> dict[str, Path]:
    """Create the private child home/work/skills tree with strict modes."""
    _private_dir(private_root)
    home, work, skills = private_root / "home", private_root / "work", private_root / "skills"
    for path in (home, work, skills):
        _private_dir(path, create=True)
    if host_auth is not None:
        _copy_private(host_auth, home / "auth.json", 0o600)
    _write_private(home / "instructions.md", instructions, 0o400)
    skill_dir = skills / skill_name
    _private_dir(skill_dir, create=True)
    _write_private(skill_dir / "SKILL.md", skill_bytes, 0o444)
    if source_bytes:
        for relative, payload in source_bytes.items():
            target = home / "sources" / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ChildRuntimeError("source path escapes child home")
            _write_private(target, payload, 0o400)
    return {"home": home, "work": work, "skills": skills}


__all__ = [
    "ChildRuntimeError",
    "ExaminerRuntimeBlocked",
    "ExaminerRolePacket",
    "ExaminerTransportReceipt",
    "ExaminerTransport",
    "ExaminerRunMetrics",
    "LeanExaminerRuntime",
    "aggregate_ordered_examiner_verdicts",
    "build_source_examiner_packet",
    "build_platform_examiner_packet",
    "build_acceptance_examiner_packet",
    "examiner_proxy_schemas",
    "validate_examiner_proxy_arguments",
    "PLATFORM_PROXY_READ_TOOLS",
    "ProxyReceipt",
    "ScopedReadProxy",
    "McpReadForwarder",
    "ReportSinkServer",
    "child_config_digest",
    "prepare_child_tree",
]
