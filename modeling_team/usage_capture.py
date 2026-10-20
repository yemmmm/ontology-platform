"""Host-private numeric receipts; capture failures never affect model execution."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)
IDENTITY_FIELDS = (
    "task_ref",
    "agent_id",
    "session_id",
    "run_id",
    "operation_id",
    "batch_id",
    "round",
    "role",
    "phase",
    "provider",
    "account_ref",
    "key_ref",
    "requested_model",
    "actual_model",
    "requested_effort",
    "effective_effort",
    "runtime",
    "runtime_session_id",
    "process_instance",
    "thread_id",
    "turn_id",
    "usage_definition_ref",
)
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "cache_write_tokens",
)
CAMEL_FIELDS = {
    "input_tokens": "inputTokens",
    "cached_input_tokens": "cachedInputTokens",
    "output_tokens": "outputTokens",
    "reasoning_output_tokens": "reasoningOutputTokens",
    "cache_write_tokens": "cacheWriteTokens",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(values: dict | None) -> dict:
    return {
        key: value
        for key, value in (values or {}).items()
        if key in IDENTITY_FIELDS and (value is None or type(value) in (str, int))
    }


def numeric_usage(raw: dict) -> tuple[dict, list[str]]:
    """Preserve absence, reject invalid values and provider subset violations."""
    result, invalid = {}, []
    for field in TOKEN_FIELDS:
        value = raw.get(field, raw.get(CAMEL_FIELDS[field]))
        if field == "cache_write_tokens" and field not in raw:
            value = raw.get("cache_write_input_tokens", value)
        if value is not None and (type(value) is not int or value < 0):
            invalid.append(field)
            value = None
        result[field] = value
    for subset, total in (
        ("cached_input_tokens", "input_tokens"),
        ("reasoning_output_tokens", "output_tokens"),
    ):
        if result[subset] is not None and result[total] is not None:
            if result[subset] > result[total]:
                invalid.append(subset)
                result[subset] = None
    return result, invalid


class NumericReceiptWriter:
    """One concrete append-only writer for Delivery usage and proxy attempts.

    ``budget`` is an optional Host-side registration hook.  The writer never
    receives or serializes the budget object in a receipt and capture failures
    remain advisory; runtime admission is performed by the runtime boundary
    immediately before a model request.
    """

    def __init__(
        self,
        path: Path,
        context: dict | None = None,
        *,
        budget: Any | None = None,
        budget_owner_id: str | None = None,
        budget_binding: Any | None = None,
        budget_kind: str = "capture",
    ):
        self.path = Path(path)
        self.context = identity(context)
        self._lock = threading.Lock()
        self.budget = budget
        self.budget_owner_id = budget_owner_id
        if budget is not None and budget_owner_id:
            try:
                from .runtimes.budget import (
                    binding_projection,
                    ensure_source_file,
                    source_identity,
                )

                source_id = source_identity(budget_owner_id, self.path, budget_kind)
                if source_id not in (budget.show("host").get("sources") or {}):
                    ensure_source_file(self.path)
                budget.register_source(
                    source_id,
                    str(self.path.resolve()),
                    budget_kind,
                    binding=binding_projection(budget_binding),
                    owner_id=budget_owner_id,
                    runtime=self.context.get("runtime"),
                )
            except Exception:
                # Source registration is repeated by the runtime gate, where a
                # failure can safely block a new request.  The numeric writer
                # itself must retain its existing advisory capture contract.
                LOG.warning("usage_capture_budget_source_unavailable")

    def __call__(self, event: dict[str, Any]) -> None:
        # Only these two numeric contracts can be persisted. Never store a
        # provider body, header, exception string or full notification.
        safe = {
            "schema_version": "model-usage-capture/v1",
            **self.context,
            **identity(event),
            "received_at": utc_now(),
        }
        for key in (
            "event",
            "request_id",
            "proxy_session_id",
            "attempt_index",
            "status",
            "http_status",
            "start",
            "end",
            "headers_at",
            "monotonic_start_ns",
            "monotonic_end_ns",
            "clock_ref",
            "purpose",
        ):
            value = event.get(key)
            if value is None or type(value) in (int, str):
                safe[key] = value
        if safe.get("event") not in ("thread_usage", "attempt_start", "attempt_end", "response_usage"):
            LOG.warning("usage_capture_incomplete")
            return
        if safe.get("status") not in (
            None,
            "unfinished",
            "transport_error",
            "http_error",
            "completed",
            "stream_error",
            "client_disconnected",
            # A Host admission denial is a local fact: no upstream attempt
            # started and no usage is implied.  Preserve the fixed status so
            # the budget ledger can exclude it from provider settlement.
            "not_admitted",
        ):
            safe["status"] = None
        if event.get("event") == "response_usage":
            from .dsh_usage import MESSAGES_FIELDS, safe_id
            for key in ("response_id", "provider_request_id", "actual_model", "purpose",
                        "usage_semantics", "adapter_definition_ref", "binding_evidence_ref",
                        "time_basis", "clock_ref"):
                safe[key] = safe_id(event.get(key))
            raw = event.get("raw_usage") or {}
            safe["raw_usage"] = {
                key: value if type(value) is int and value >= 0 else None
                for key in MESSAGES_FIELDS.values() for value in [raw.get(key)]
            }
            safe["present_fields"] = [key for key in MESSAGES_FIELDS.values()
                                      if key in event.get("present_fields", [])]
            safe["field_positions"] = {
                key: value for key, value in (event.get("field_positions") or {}).items()
                if key in MESSAGES_FIELDS.values() and type(value) is int and value >= 0}
            # Observer issue codes are fixed, not provider error strings.
            allowed = {"event_too_large", "invalid_sse_event", "truncated_sse_event",
                       "message_stop_missing", "final_output_missing", "usage_after_stop",
                       "response_identity_conflict", "provider_stream_error", "message_start_missing",
                       "duplicate_message_start"}
            allowed |= {prefix + key for prefix in ("invalid_usage:", "usage_decreased:", "input_outside_start:")
                        for key in MESSAGES_FIELDS.values()}
            safe["usage_issues"] = sorted(set(event.get("usage_issues", [])) & allowed)
            for key in ("usage_complete", "message_stop"):
                safe[key] = event.get(key) is True
            if isinstance(event.get("provider_error"), dict):
                diagnostic = event["provider_error"]
                reasons = {"context_window_exceeded", "invalid_tool_history", "authentication",
                           "quota", "rate_limit", "server", "invalid_request"}
                types = {"invalid_request_error", "authentication_error", "permission_error",
                         "rate_limit_error", "api_error", "overloaded_error", "billing_error"}
                safe["provider_error"] = {
                    "reason_code": diagnostic.get("reason_code") if diagnostic.get("reason_code") in reasons else None,
                    "provider_type": diagnostic.get("provider_type") if diagnostic.get("provider_type") in types else None,
                }
                shape = event.get("request_shape") or {}
                safe["request_shape"] = {
                    key: value if type(value) is int and value >= 0 else None
                    for key in ("body_bytes", "message_count", "tool_count", "max_tokens")
                    for value in [shape.get(key)]
                }
        if event.get("event") == "thread_usage":
            safe["total"], safe["invalid_fields"] = numeric_usage(event.get("total") or {})
            safe["present_fields"] = [
                field
                for field in TOKEN_FIELDS
                if field in (event.get("total") or {})
                or CAMEL_FIELDS[field] in (event.get("total") or {})
                or (
                    field == "cache_write_tokens"
                    and "cache_write_input_tokens" in (event.get("total") or {})
                )
            ]
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.path.parent.chmod(0o700)
                descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps(safe, sort_keys=True) + "\n")
        except Exception:
            LOG.warning("usage_capture_incomplete")
