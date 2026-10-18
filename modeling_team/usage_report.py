"""R4.3-019: deterministic, offline Host usage reports from explicitly bound receipts.

No credentials, provider calls, model input or run state are read or changed.
See modeling_team/README.md for the scope and evidence contracts.
"""

from __future__ import annotations

import argparse
import decimal
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dsh_usage import (
    DSH_SEMANTICS, MESSAGES_FIELDS, NATIVE_FIELDS, PROJECTION_FIELDS,
    native_numeric_event, normalize_dsh_usage,
)
from .usage_capture import IDENTITY_FIELDS, TOKEN_FIELDS, identity, numeric_usage

FIELDS = (*TOKEN_FIELDS, "uncached_input_tokens")
REQUIRED = TOKEN_FIELDS[:4]
GROUP = (
    "runtime",
    "runtime_session_id",
    "provider",
    "account_ref",
    "key_ref",
    "requested_model",
    "actual_model",
    "requested_effort",
    "effective_effort",
    "session_id",
    "run_id",
    "round",
    "operation_id",
    "role",
    "phase",
)
SOURCE_KINDS = {"rollout", "app_server", "capture", "receipts", "timing", "metrics", "batch_report", "dsh_capture", "dsh_native"}


class ScopeError(ValueError):
    """A local input contract error; never includes source content."""


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def window_contains(window, timestamp):
    start, end, stamp = instant(window.get("start")), instant(window.get("end")), instant(timestamp)
    return start is not None and end is not None and stamp is not None and start <= stamp < end


def with_derived(usage):
    result = dict(usage)
    input_, cached = result.get("input_tokens"), result.get("cached_input_tokens")
    result["uncached_input_tokens"] = input_ - cached if None not in (input_, cached) else None
    return result


def summarize(records):
    values, coverage = {}, {}
    for field in FIELDS:
        known = [r["usage"][field] for r in records if r["usage"].get(field) is not None]
        values[field] = sum(known) if known else None
        coverage[field] = {"known": len(known), "unknown": len(records) - len(known)}
    # Never divide sums having different sample coverage.
    paired = [
        r
        for r in records
        if r["usage"].get("cached_input_tokens") is not None
        and r["usage"].get("input_tokens") is not None
    ]
    denominator = sum(r["usage"]["input_tokens"] for r in paired)
    values["cache_rate"] = (
        sum(r["usage"]["cached_input_tokens"] for r in paired) / denominator
        if denominator
        else None
    )
    return {
        "tokens": values,
        "field_coverage": coverage,
        "cache_rate_input_coverage": denominator if paired else None,
        "cost_units": len(records),
    }


def _issue(issues, code, locator=None, **meta):
    issues.append({"code": code, **({"source": locator} if locator else {}), **meta})


def validate_scope(scope):
    if not isinstance(scope, dict) or scope.get("schema_version") != "model-usage-scope/v1":
        raise ScopeError("expected model-usage-scope/v1")
    if not isinstance(scope.get("task_ref"), str) or not scope["task_ref"]:
        raise ScopeError("task_ref is required")
    for field in ("sources", "bindings", "layer_coverage"):
        if not isinstance(scope.get(field, []), list):
            raise ScopeError(f"{field} must be a list")
    for field in ("task_window", "billing_scope"):
        if scope.get(field) is not None and not isinstance(scope[field], dict):
            raise ScopeError(f"{field} must be an object")
    prices = scope.get("price_versions", [])
    if not isinstance(prices, list) or any(not isinstance(p, dict) for p in prices):
        raise ScopeError("price_versions must be a list of objects")
    ids = set()
    for source in scope.get("sources", []):
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("id"), str)
            or source["id"] in ids
            or not isinstance(source.get("path"), str)
        ):
            raise ScopeError("sources require unique id and path")
        if not isinstance(source.get("root", "."), str):
            raise ScopeError("source root must be a path")
        ids.add(source["id"])
        for key in ("byte_offset", "byte_length"):
            if key in source and (type(source[key]) is not int or source[key] < 0):
                raise ScopeError("source byte ranges must be nonnegative integers")
    for binding in scope.get("bindings", []):
        if not isinstance(binding, dict) or binding.get("source_id") not in ids:
            raise ScopeError("binding requires a declared source_id")
        for field in ("window", "cumulative_segment"):
            if field in binding and not isinstance(binding[field], dict):
                raise ScopeError(f"binding {field} must be an object")
        if "response_ids" in binding and not isinstance(binding["response_ids"], list):
            raise ScopeError("response_ids must be a list")
    return scope


def _session_key(record):
    runtime = record.get("runtime") or "codex"
    return runtime, record.get("runtime_session_id") if runtime != "codex" else (
        record.get("runtime_session_id") or record.get("thread_id"))


def _binding(scope, source_id, record, issues, locator):
    matches = []
    for b in scope.get("bindings", []):
        if b["source_id"] != source_id or not b.get("evidence_ref"):
            continue
        if b.get("thread_id") and record.get("thread_id") and b["thread_id"] != record["thread_id"]:
            continue
        if any(b.get(key) and record.get(key) and b[key] != record[key]
               for key in ("runtime", "runtime_session_id", "process_instance")):
            continue
        if b.get("runtime") == "dsh" and not record.get("runtime_session_id"):
            continue
        if "response_ids" in b and record.get("response_id") not in b["response_ids"]:
            continue
        if b.get("window") and not window_contains(b["window"], record.get("timestamp")):
            continue
        matches.append(b)
    if len(matches) != 1:
        _issue(issues, "binding_ambiguous" if matches else "binding_missing", locator)
        observed = identity(record)
        observed["task_ref"] = None
        return observed, {}
    b = matches[0]
    result = identity(b)
    if b.get("shared_thread") and not b.get("window") and not b.get("response_ids"):
        result["task_ref"] = None
        _issue(issues, "shared_thread_unsliced", locator)
    # A binding can confirm attribution but cannot replace an observed identity.
    for key, value in identity(record).items():
        if value is None:
            continue
        if result.get(key) not in (None, value):
            _issue(issues, "binding_identity_conflict", locator, field=key)
            result[key] = None
        else:
            result[key] = value
    if b.get("shared_thread") and not b.get("window") and not b.get("response_ids"):
        result["task_ref"] = None
    if not result.get("runtime") and result.get("thread_id"):
        result["runtime"] = "codex"
        result["runtime_session_id"] = result["thread_id"]
    if result.get("runtime") == "dsh":
        if result.get("thread_id") or result.get("turn_id"):
            _issue(issues, "dsh_codex_identity_not_applicable", locator)
        result.pop("thread_id", None)
        result.pop("turn_id", None)
    return result, b


def _read_sources(scope, base, issues):
    receipts, cumulative, attempts, timings, compactions, sources = [], [], [], [], [], []
    snapshots = []
    native = []
    for spec in scope.get("sources", []):
        root = (base / spec.get("root", ".")).resolve()
        path = (root / spec["path"]).resolve()
        if not path.is_relative_to(root):
            raise ScopeError("source path escapes its explicit root")
        source = {
            "id": spec["id"],
            "kind": spec.get("kind"),
            "path": str(path),
            "byte_offset": spec.get("byte_offset", 0),
        }
        sources.append(source)
        if spec.get("kind") not in SOURCE_KINDS:
            source["status"] = "unsupported_source"
            _issue(issues, "unsupported_source", {"source_id": spec["id"]})
            continue
        try:
            with path.open("rb") as stream:
                offset = source["byte_offset"]
                boundary_ok = True
                if offset:
                    stream.seek(offset - 1)
                    boundary_ok = stream.read(1) == b"\n"
                stream.seek(offset)
                raw = stream.read(spec.get("byte_length", -1))
        except OSError:
            source["status"] = "missing"
            _issue(issues, "source_unavailable", {"source_id": spec["id"]})
            continue
        source.update(
            byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest(), status="observed"
        )
        if "byte_length" in spec and len(raw) != spec["byte_length"]:
            _issue(issues, "source_truncated", {"source_id": spec["id"]})
        if spec["kind"] == "batch_report":
            snapshots.extend(_read_consumer_snapshots(scope, spec, raw, issues))
            continue
        thread_id = spec.get("thread_id")
        config = {}
        position = offset
        for line in raw.splitlines(keepends=True):
            locator = {"source_id": spec["id"], "byte_offset": position, "byte_length": len(line)}
            position += len(line)
            if not boundary_ok:
                _issue(issues, "partial_first_line", locator)
                boundary_ok = True
                continue
            if not line.endswith(b"\n"):
                _issue(issues, "truncated_line", locator)
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                _issue(issues, "invalid_json_line", locator)
                continue
            kind = spec["kind"]
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                _issue(issues, "invalid_payload", locator)
                continue
            timestamp = event.get("timestamp", event.get("received_at"))
            record = None
            mode = None
            try:
                if kind == "rollout":
                    if event.get("type") == "session_meta":
                        thread_id = payload.get("id")
                    elif event.get("type") == "turn_context":
                        config = {
                            "requested_model": payload.get("model"),
                            "requested_effort": payload.get("effort"),
                        }
                    elif event.get("type") == "compacted":
                        compactions.append(
                            {
                                "response_id": payload.get("compaction_response_id"),
                                "thread_id": thread_id,
                                "source": locator,
                            }
                        )
                    elif event.get("type") == "token_usage_record":
                        record = {
                            **config,
                            "thread_id": payload.get("thread_id", thread_id),
                            "turn_id": payload.get("turn_id", payload.get("root_turn_id")),
                            "response_id": payload.get("response_id"),
                            "request_id": payload.get("request_id"),
                            "actual_model": payload.get("model"),
                            "usage": payload.get("usage"),
                        }
                        mode = "response"
                    elif event.get("type") == "event_msg" and payload.get("type") == "token_count":
                        info = payload.get("info") or {}
                        record = {"thread_id": thread_id, "usage": info.get("total_token_usage")}
                        mode = "thread_cumulative"
                elif kind == "app_server" and event.get("method") == "thread/tokenUsage/updated":
                    params = event.get("params") or {}
                    record = {
                        "thread_id": params.get("threadId"),
                        "turn_id": params.get("turnId"),
                        "usage": (params.get("tokenUsage") or {}).get("total"),
                    }
                    mode = "thread_cumulative"
                elif kind == "dsh_native":
                    record = native_numeric_event(event, spec.get("runtime_session_id"))
                    mode = "dsh_native"
                    if record:
                        timestamp = record.get("timestamp", timestamp)
                elif kind in ("capture", "dsh_capture"):
                    if event.get("event") == "response_usage":
                        record = {**identity(event), **{key: event.get(key) for key in (
                            "response_id", "request_id", "status", "raw_usage", "purpose",
                            "usage_semantics", "usage_complete", "present_fields", "usage_issues",
                            "adapter_definition_ref", "provider_request_id", "field_positions")},
                            "usage": {}, "request_started_at": event.get("start"),
                            "billing_time_evidence_ref": event.get("binding_evidence_ref"),
                            "unique_request_evidence_ref": event.get("binding_evidence_ref")}
                        timestamp = event.get("end", timestamp)
                        mode = "response"
                        if not event.get("usage_complete") or event.get("status") != "completed":
                            _issue(issues, "dsh_provider_usage_partial", locator)
                    elif event.get("event") == "thread_usage":
                        record = {**identity(event), "usage": event.get("total")}
                        mode = "thread_cumulative"
                    elif event.get("event") in ("attempt_start", "attempt_end"):
                        bound, _ = _binding(scope, spec["id"], event, issues, locator)
                        attempts.append(
                            {
                                **bound,
                                **{
                                    k: event.get(k)
                                    for k in (
                                        "event",
                                        "request_id",
                                        "proxy_session_id",
                                        "attempt_index",
                                        "status",
                                        "http_status",
                                        "start",
                                        "end",
                                        "headers_at",
                                    )
                                },
                                "source": locator,
                            }
                        )
                elif kind == "receipts":
                    mode = event.get("source_mode", "response")
                    record = {
                        **identity(event),
                        **{
                            k: event.get(k)
                            for k in (
                                "response_id",
                                "request_id",
                                "unique_request_evidence_ref",
                                "usage",
                                "status",
                                "request_started_at",
                                "settled_at",
                                "billing_time_evidence_ref",
                            )
                        },
                    }
                    if event.get("usage_semantics") == DSH_SEMANTICS:
                        record.update(raw_usage=event.get("raw_usage"),
                                      usage_semantics=DSH_SEMANTICS,
                                      usage={})
                    if event.get("compaction_response_id"):
                        compactions.append(
                            {
                                "response_id": event["compaction_response_id"],
                                "thread_id": event.get("thread_id"),
                                "source": locator,
                            }
                        )
                elif kind == "timing":
                    timings.append(
                        {
                            **identity(event),
                            **{
                                k: event.get(k)
                                for k in (
                                    "response_id",
                                    "request_id",
                                    "kind",
                                    "start",
                                    "end",
                                    "clock_ref",
                                    "start_source",
                                    "end_source",
                                    "binding_evidence_ref",
                                    "status",
                                )
                            },
                            "source": locator,
                        }
                    )
                elif kind == "metrics":
                    # Examiner TTFT can include tools: retain an explicit gap rather
                    # than interpreting it as provider timing or response usage.
                    _issue(issues, "metrics_not_response_usage_or_provider_ttft", locator)
            except (AttributeError, TypeError, KeyError, ValueError, OverflowError):
                _issue(issues, "invalid_source_record", locator)
                continue
            if record is None:
                continue
            for field in (
                "response_id",
                "request_id",
                "unique_request_evidence_ref",
                "status",
                "request_started_at",
                "settled_at",
                "billing_time_evidence_ref",
            ):
                if record.get(field) is not None and not isinstance(record[field], str):
                    _issue(issues, "invalid_record_identity", locator, field=field)
                    record[field] = None
            if timestamp is not None and not isinstance(timestamp, str):
                _issue(issues, "invalid_timestamp", locator)
                timestamp = None
            if timestamp is not None and instant(timestamp) is None:
                _issue(issues, "invalid_timestamp", locator)
                timestamp = None
            if record.get("runtime") == "dsh":
                record["status"] = {"http_error": "failed", "stream_error": "failed",
                                    "transport_error": "failed", "client_disconnected": "aborted"
                                    }.get(record.get("status"), record.get("status"))
            if record.get("status") not in (None, "completed", "failed", "aborted", "unknown"):
                _issue(issues, "invalid_status", locator)
                record["status"] = None
            record["timestamp"] = timestamp
            if not isinstance(record.get("usage"), dict):
                _issue(issues, "usage_missing", locator)
                continue
            bound, binding = _binding(scope, spec["id"], record, issues, locator)
            if record.get("usage_semantics") == DSH_SEMANTICS and not isinstance(record.get("raw_usage"), dict):
                _issue(issues, "dsh_raw_usage_invalid", locator)
                record["raw_usage"] = {}
            if bound.get("runtime") == "dsh" and record.get("usage_semantics") != DSH_SEMANTICS:
                _issue(issues, "dsh_definition_unknown", locator)
                usage, invalid = dict.fromkeys(TOKEN_FIELDS), []
            elif record.get("usage_semantics") == DSH_SEMANTICS:
                usage, invalid = normalize_dsh_usage(record.get("raw_usage") or {},
                                                     "native" if mode == "dsh_native" else "projection" if mode == "dsh_assistant_cumulative" else "messages")
                if not bound.get("usage_definition_ref"):
                    _issue(issues, "dsh_definition_unknown", locator)
                    usage["input_tokens"] = None
            else:
                usage, invalid = numeric_usage(record["usage"])
            invalid = sorted(set(invalid) | set(record.get("invalid_fields", [])))
            for field in invalid:
                _issue(issues, "invalid_usage", locator, field=field)
            if kind == "capture" and event.get("invalid_fields"):
                _issue(issues, "capture_invalid_usage", locator)
            if record.get("usage_semantics") == DSH_SEMANTICS:
                fields = (NATIVE_FIELDS if mode == "dsh_native" else
                          PROJECTION_FIELDS if mode == "dsh_assistant_cumulative" else MESSAGES_FIELDS)
                record["raw_usage"] = {
                    key: value if type(value) is int and value >= 0 else None
                    for key in fields.values() for value in [(record.get("raw_usage") or {}).get(key)]
                }
            normalized = {
                "schema_version": "model-usage-record/v1",
                "binding_evidence_refs": [binding["evidence_ref"]]
                if binding.get("evidence_ref")
                else [],
                **bound,
                "response_id": record.get("response_id"),
                "request_id": record.get("request_id"),
                "unique_request_evidence_ref": record.get("unique_request_evidence_ref"),
                "timestamp": timestamp,
                "status": record.get("status"),
                "source_mode": mode,
                "usage": with_derived(usage),
                "sources": [locator],
                **{
                    k: record.get(k)
                    for k in ("request_started_at", "settled_at", "billing_time_evidence_ref")
                },
                "binding": binding,
                "invalid_fields": invalid,
                **{key: record.get(key) for key in (
                    "raw_usage", "usage_semantics", "purpose", "usage_complete", "present_fields",
                    "usage_issues", "adapter_definition_ref", "provider_request_id", "field_positions",
                    "native_type", "native_seq", "native_turn", "native_step")
                    if key in record},
            }
            if kind in ("capture", "dsh_capture") and event.get("event") == "response_usage":
                if normalized.get("response_id"):
                    for timing_kind, start_field in (("request_completion", "start"),
                                                     ("after_headers", "headers_at")):
                        timings.append({**bound, "kind": timing_kind,
                            "response_id": normalized["response_id"],
                            "request_id": normalized.get("request_id"),
                            "start": event.get(start_field), "end": event.get("end"),
                            "clock_ref": event.get("clock_ref"), "status": normalized.get("status"),
                            "binding_evidence_ref": binding.get("evidence_ref"),
                            "start_source": "proxy_" + start_field, "end_source": "proxy_end",
                            "source": locator})
            if mode == "dsh_native":
                native.append(normalized)
            elif mode in ("thread_cumulative", "dsh_assistant_cumulative"):
                cumulative.append(normalized)
            elif mode == "response":
                receipts.append(normalized)
            else:
                _issue(issues, "unsupported_record_mode", locator)
    return receipts, cumulative, attempts, timings, compactions, sources, snapshots, native


def _read_consumer_snapshots(scope, spec, raw, issues):
    """Read numeric task snapshots only; never copy CQ text or answer material."""
    locator = {
        "source_id": spec["id"],
        "byte_offset": spec.get("byte_offset", 0),
        "byte_length": len(raw),
    }
    try:
        tasks = json.loads(raw)["sessions"]["platform_examiner"]["tasks"]
        if not isinstance(tasks, list):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        _issue(issues, "consumer_snapshot_invalid", locator)
        return []
    records = []
    for index, task in enumerate(tasks):
        source = {
            **locator,
            "json_pointer": f"/sessions/platform_examiner/tasks/{index}/model_usage",
        }
        metrics = task.get("model_usage") if isinstance(task, dict) else None
        if (not isinstance(metrics, dict)
                or not isinstance(metrics.get("fresh_thread_id"), str)
                or not metrics["fresh_thread_id"].strip()):
            _issue(issues, "consumer_snapshot_missing", source)
            continue
        increments = metrics.get("token_usage_increments")
        # A task snapshot is a thread subtotal only for a genuinely fresh child.
        if (
            metrics.get("fresh_thread") is not True
            or not isinstance(increments, list)
            or not increments
        ):
            _issue(issues, "consumer_snapshot_baseline_unproven", source)
            continue
        rows = []
        for increment in increments:
            values, invalid = numeric_usage(
                increment if isinstance(increment, dict) else {}
            )
            if invalid or not isinstance(increment, dict):
                _issue(issues, "invalid_usage", source)
            rows.append(values)
        usage = {
            field: sum(row[field] for row in rows)
            if all(row[field] is not None for row in rows)
            else None
            for field in TOKEN_FIELDS
        }
        observed = {
            "thread_id": metrics["fresh_thread_id"],
            "timestamp": task.get("finished_at"),
        }
        bound, binding = _binding(scope, spec["id"], observed, issues, source)
        if not binding or not all(
            bound.get(k) for k in ("task_ref", "provider", "key_ref")
        ):
            _issue(issues, "consumer_snapshot_binding_unproven", source)
            continue
        records.append(
            {
                **bound,
                "timestamp": observed["timestamp"],
                "source_mode": "partial_thread_snapshot",
                "usage": with_derived(usage),
                "sources": [source],
                "response_id": None,
                "request_id": None,
                "binding_evidence_refs": [binding["evidence_ref"]],
            }
        )
    return records


def _reconcile_consumer_snapshots(units, snapshots, issues):
    """Native usage wins; a snapshot is a partial fallback, never an addition."""
    groups = defaultdict(list)
    key_fields = ("task_ref", "provider", "key_ref", "thread_id")
    for row in snapshots:
        groups[tuple(row.get(k) for k in key_fields)].append(row)
    comparisons, fallbacks = [], []
    for key, rows in groups.items():
        snapshot = dict(rows[0])
        snapshot["sources"] = [source for row in rows for source in row["sources"]]
        snapshot["usage"] = {}
        for field in FIELDS:
            values = {row["usage"].get(field) for row in rows} - {None}
            snapshot["usage"][field] = next(iter(values)) if len(values) == 1 else None
            if len(values) > 1:
                _issue(
                    issues,
                    "consumer_snapshot_conflict",
                    rows[0]["sources"][0],
                    field=field,
                )
        snapshot["usage"], invalid = numeric_usage(snapshot["usage"])
        snapshot["usage"] = with_derived(snapshot["usage"])
        for field in invalid:
            _issue(issues, "invalid_merged_usage", rows[0]["sources"][0], field=field)
        native = [row for row in units if tuple(row.get(k) for k in key_fields) == key]
        comparison = {
            "thread_id": key[-1],
            "snapshot_usage": snapshot["usage"],
            "snapshot_sources": snapshot["sources"],
        }
        if native:
            final = summarize(native)["tokens"]
            difference = {
                field: final[field] - snapshot["usage"][field]
                if None not in (final[field], snapshot["usage"][field])
                else None
                for field in FIELDS
            }
            comparison.update(
                selected_source="bound_records",
                native_usage=final,
                native_sources=[s for row in native for s in row["sources"]],
                difference=difference,
            )
            if any(value is not None and value < 0 for value in difference.values()):
                _issue(issues, "consumer_native_below_snapshot", snapshot["sources"][0])
        elif any(row.get("thread_id") == key[-1] for row in units):
            comparison["selected_source"] = "binding_conflict"
            _issue(issues, "consumer_native_binding_conflict", snapshot["sources"][0])
        else:
            comparison["selected_source"] = "partial_snapshot"
            fallbacks.append(snapshot)
            _issue(issues, "consumer_snapshot_not_final", snapshot["sources"][0])
        comparisons.append(comparison)
    return [*units, *fallbacks], comparisons


def _deduplicate(receipts, issues):
    groups, ambiguous = defaultdict(list), []
    for r in receipts:
        unique = r.get("response_id") or (
            r.get("request_id") if r.get("unique_request_evidence_ref") else None
        )
        if not unique or not r.get("provider") or not r.get("key_ref"):
            r["ambiguous"] = True
            ambiguous.append(r)
            _issue(issues, "ambiguous_response_identity", r["sources"][0])
        else:
            key = (
                r["provider"],
                r["key_ref"],
                "response" if r.get("response_id") else "request",
                unique,
            )
            groups[key].append(r)
    canonical = []
    for rows in groups.values():
        r = dict(rows[0])
        r["sources"] = [s for row in rows for s in row["sources"]]
        r["binding_evidence_refs"] = sorted(
            {ref for row in rows for ref in row["binding_evidence_refs"]}
        )
        r["usage"] = {}
        for field in TOKEN_FIELDS:
            values = {row["usage"].get(field) for row in rows} - {None}
            r["usage"][field] = next(iter(values)) if len(values) == 1 else None
            if len(values) > 1:
                r["conflict"] = True
                _issue(issues, "response_usage_conflict", r["sources"][0], field=field)
        # Revalidate subset relations after merging partial receipts.
        r["usage"], invalid = numeric_usage(r["usage"])
        r["usage"] = with_derived(r["usage"])
        for field in invalid:
            _issue(issues, "invalid_merged_usage", r["sources"][0], field=field)
        for field in (
            *IDENTITY_FIELDS,
            "timestamp",
            "status",
            "request_started_at",
            "settled_at",
            "billing_time_evidence_ref",
        ):
            values = {row.get(field) for row in rows} - {None}
            r[field] = next(iter(values)) if len(values) == 1 else None
            if len(values) > 1:
                _issue(issues, "response_attribution_conflict", r["sources"][0], field=field)
        if any(row.get("usage_semantics") == DSH_SEMANTICS for row in rows):
            for field in ("purpose", "usage_semantics"):
                values = {row.get(field) for row in rows} - {None}
                r[field] = next(iter(values)) if len(values) == 1 else None
                if len(values) > 1:
                    _issue(issues, "dsh_definition_or_purpose_conflict", r["sources"][0])
                    r["usage"] = with_derived(dict.fromkeys(TOKEN_FIELDS))
            if len({row.get("usage_definition_ref") for row in rows} - {None}) > 1:
                _issue(issues, "dsh_definition_or_purpose_conflict", r["sources"][0])
                r["usage"] = with_derived(dict.fromkeys(TOKEN_FIELDS))
            r["raw_usage"] = {}
            for field in {key for row in rows for key in row.get("raw_usage", {})}:
                values = {row.get("raw_usage", {}).get(field) for row in rows} - {None}
                r["raw_usage"][field] = next(iter(values)) if len(values) == 1 else None
            r["usage_complete"] = all(row.get("usage_complete") for row in rows)
        canonical.append(r)
    return canonical, ambiguous


def _account(canonical, cumulative, issues):
    """Only a proven continuous segment can supplement response-level cost."""
    units = list(canonical)
    segments, observed = defaultdict(list), []
    for r in cumulative:
        b = r["binding"]
        segment = b.get("cumulative_segment") or {}
        if not _session_key(r)[1] or not segment.get("evidence_ref") or not segment.get("id"):
            _issue(issues, "cumulative_baseline_unproven", r["sources"][0])
            observed.append(r)
            continue
        segments[(r.get("provider"), r.get("key_ref"), _session_key(r), segment["id"])].append(r)
    accepted_windows = defaultdict(list)
    for rows in segments.values():
        # Event order is file order, not field-wise maxima. Copies are accepted
        # only if identical sequences; multiple source streams must agree.
        streams = defaultdict(list)
        for r in rows:
            streams[r["sources"][0]["source_id"]].append(r)
        sequences = list(streams.values())

        def signature(seq):
            return [(r["timestamp"], r["usage"]) for r in seq]

        if any(signature(seq) != signature(sequences[0]) for seq in sequences[1:]):
            _issue(issues, "cumulative_sources_not_aligned", rows[0]["sources"][0])
            observed.extend(rows)
            continue
        sequence = sequences[0]
        last = sequence[-1]
        segment = last["binding"]["cumulative_segment"]
        baseline, _ = numeric_usage(segment.get("baseline") or {})
        if segment.get("fresh_zero_baseline") is True:
            baseline = dict.fromkeys(TOKEN_FIELDS, 0)
        if not segment.get("start") or not segment.get("end"):
            _issue(issues, "cumulative_window_missing", last["sources"][0])
            observed.extend(rows)
            continue
        if (
            instant(segment["start"]) is None
            or instant(segment["end"]) is None
            or any(
                not window_contains(
                    {"start": segment["start"], "end": segment["end"]}, r["timestamp"]
                )
                and instant(r["timestamp"]) != instant(segment["end"])
                for r in sequence
            )
        ):
            _issue(issues, "cumulative_window_not_aligned", last["sources"][0])
            observed.extend(rows)
            continue
        delta = {}
        for field in TOKEN_FIELDS:
            values = [baseline[field], *(r["usage"].get(field) for r in sequence)]
            valid = all(v is not None for v in values)
            if valid and any(a > b for a, b in zip(values, values[1:])):
                valid = False
                _issue(issues, "cumulative_reset", last["sources"][0], field=field)
            delta[field] = values[-1] - values[0] if valid else None
        delta, invalid = numeric_usage(delta)
        if invalid:
            _issue(issues, "invalid_cumulative_delta", last["sources"][0])
        total = {
            **last,
            "usage": with_derived(delta),
            "source_mode": "thread_delta",
            "cumulative_basis": {
                "evidence_ref": segment["evidence_ref"],
                "baseline": baseline,
                "fresh_zero_baseline": segment.get("fresh_zero_baseline", False),
            },
            "sources": [s for row in rows for s in row["sources"]],
            "window": {"start": segment["start"], "end": segment["end"]},
            "response_id": None,
            "request_id": None,
            "timestamp": None,
        }
        thread_key = (last.get("provider"), last.get("key_ref"), _session_key(last))
        begin, end = instant(segment["start"]), instant(segment["end"])
        if any(begin < b and a < end for a, b in accepted_windows[thread_key]):
            _issue(issues, "cumulative_segments_overlap", last["sources"][0])
            observed.append(total)
            continue
        details = [
            r
            for r in canonical
            if _session_key(r) == _session_key(last)
            and r.get("provider") == last.get("provider")
            and r.get("key_ref") == last.get("key_ref")
            and window_contains(total["window"], r.get("timestamp"))
        ]
        if details:
            ids = {r.get("response_id") for r in details}
            proven = set(segment.get("includes_response_ids", []))
            same_scope = all(
                all(r.get(k) == last.get(k) for k in (*GROUP, "task_ref"))
                and window_contains(total["window"], r.get("timestamp"))
                for r in details
            )
            if not ids <= proven or not same_scope:
                _issue(issues, "cumulative_overlap_unproven", last["sources"][0])
                observed.append(total)
                continue
            subtotal = summarize(details)["tokens"]
            residual = {}
            for field in FIELDS:
                known = subtotal.get(field)
                value = total["usage"].get(field)
                if value is not None and known is not None and value < known:
                    _issue(issues, "cumulative_detail_conflict", last["sources"][0], field=field)
                    total["usage"][field] = None
                    residual[field] = None
                else:
                    residual[field] = value - known if None not in (value, known) else None
            total["unitemized_residual"] = residual
            units = [r for r in units if r not in details]
        accepted_windows[thread_key].append((begin, end))
        units.append(total)
    return units, observed


def _account_dsh_native(native, canonical, issues):
    """Native history is a cross-check; absent provider originals allow only partial sums."""
    sessions = defaultdict(list)
    for row in native:
        sessions[(row.get("provider"), row.get("key_ref"), _session_key(row))].append(row)
    units, comparisons = [], []
    for (provider, key_ref, session), rows in sessions.items():
        by_seq = defaultdict(list)
        for row in rows:
            seq = row.get("native_seq")
            if type(seq) is not int or seq < 0 or not session[1]:
                _issue(issues, "dsh_native_identity_missing", row["sources"][0])
                continue
            by_seq[seq].append(row)
        settled, slot = [], None
        conflict = False
        for seq in sorted(by_seq):
            copies = by_seq[seq]
            row = dict(copies[0])
            def signature(r):
                return (r.get("native_type"), r.get("native_turn"), r.get("native_step"), r["usage"])
            if any(signature(other) != signature(row) for other in copies[1:]):
                conflict = True
                _issue(issues, "dsh_native_seq_conflict", row["sources"][0])
                continue
            row["sources"] = [source for copy in copies for source in copy["sources"]]
            if len({copy.get("task_ref") for copy in copies}) > 1:
                row["task_ref"] = None
                _issue(issues, "dsh_native_attribution_conflict", row["sources"][0])
            kind = row["native_type"]
            current = (row.get("native_turn"), row.get("native_step"))
            if kind == "llm/retry-started":
                if slot and slot[:2] == current:
                    slot = None
                continue
            if not row.get("raw_usage"):
                continue
            if kind == "compaction/summary":
                row["purpose"] = "compaction"
                settled.append(row)
                continue
            if None in current:
                _issue(issues, "dsh_native_step_missing", row["sources"][0])
                continue
            row["purpose"] = "assistant"
            if slot and slot[:2] == current:
                index = slot[2]
                settled[index] = row
            else:
                index = len(settled)
                settled.append(row)
            slot = (*current, index)
        if conflict:
            # Neither version of a conflicted sequence proves an accurate subtotal.
            settled = []
        provider_rows = [r for r in canonical if r.get("provider") == provider
                         and r.get("key_ref") == key_ref and _session_key(r) == session]
        ordinary = [r for r in provider_rows if r.get("purpose") == "assistant"]
        native_ordinary = [r for r in settled if r.get("purpose") == "assistant"]
        left, right = summarize(ordinary), summarize(native_ordinary)
        comparisons.append({"runtime": session[0], "runtime_session_id": session[1],
                            "provider_usage": left, "native_assistant_usage": right,
                            "additive": False,
                            "difference": {field: left["tokens"][field] - right["tokens"][field]
                                if None not in (left["tokens"][field], right["tokens"][field])
                                else None for field in FIELDS},
                            "selected_source": "provider" if provider_rows else "partial_native"})
        if provider_rows and native_ordinary and (
            len(ordinary) != len(native_ordinary) or any(
                right["tokens"][field] is not None
                and left["tokens"][field] != right["tokens"][field]
                for field in REQUIRED)
        ):
            _issue(issues, "dsh_native_provider_difference", native_ordinary[0]["sources"][0])
        if not provider_rows and settled:
            _issue(issues, "dsh_provider_original_missing", settled[0]["sources"][0])
            for row in settled:
                row["source_mode"] = "partial_dsh_native"
                # No provider response ID is invented from session/seq/message IDs.
                row["response_id"] = row["request_id"] = None
            units.extend(settled)
    return units, comparisons


def _groups(units):
    groups = defaultdict(list)
    for r in units:
        groups[tuple(r.get(k) for k in GROUP)].append(r)
    return [
        {"identity": dict(zip(GROUP, keys)), **summarize(rows)} for keys, rows in groups.items()
    ]


def _costs(units, prices):
    result = []
    for index, r in enumerate(units):
        candidates = []
        for p in prices:
            if (
                p.get("provider") != r.get("provider")
                or p.get("model") != r.get("actual_model")
                or not p.get("model")
                or not p.get("source_ref")
                or not p.get("version")
                or not p.get("currency")
                or not p.get("verified_at")
            ):
                continue
            times = [r.get("timestamp")]
            if r.get("window"):
                # Half-open price intervals may exactly enclose a segment.
                w = r["window"]
                covered = (
                    instant(p.get("start")) is not None
                    and instant(p.get("end")) is not None
                    and instant(w["start"]) >= instant(p["start"])
                    and instant(w["end"]) <= instant(p["end"])
                )
            else:
                covered = all(window_contains(p, t) for t in times)
            if covered:
                candidates.append(p)
        entry = {
            "cost_unit": index,
            "amount": None,
            "currency": None,
            "status": "unknown",
            "basis": "local_estimate",
        }
        if len(candidates) == 1:
            p = candidates[0]
            # Explicit category coefficients express this provider's actual
            # cache-write/reasoning definition; no provider formula is assumed.
            rates = p.get("rates") or {}
            try:
                if p.get("billing_mode") != "api" or not rates or not p.get("definition_ref"):
                    raise ValueError
                unit = Decimal(str(p["unit_tokens"]))
                if unit <= 0 or not unit.is_finite():
                    raise ValueError
                charge_tokens = dict(r["usage"])
                if r.get("usage_semantics") == DSH_SEMANTICS:
                    if "input_tokens" in rates or "reasoning_output_tokens" in rates:
                        raise ValueError  # overlapping categories need an explicit definition
                    if "cache_write_tokens" in rates:
                        uncached, write = (charge_tokens.get(key) for key in (
                            "uncached_input_tokens", "cache_write_tokens"))
                        if uncached is None or write is None or write > uncached:
                            raise ValueError
                        charge_tokens["uncached_input_tokens"] = uncached - write
                    if not r.get("usage_definition_ref") or p.get("definition_ref") != r["usage_definition_ref"]:
                        raise ValueError
                amount = Decimal(0)
                for field, rate in rates.items():
                    if field not in FIELDS or r["usage"].get(field) is None:
                        raise ValueError
                    rate = Decimal(str(rate))
                    if rate < 0 or not rate.is_finite():
                        raise ValueError
                    amount += Decimal(charge_tokens[field]) * rate / unit
                if p.get("rounding_quantum"):
                    quantum = Decimal(p["rounding_quantum"])
                    mode = p.get("rounding_mode")
                    if (
                        mode not in ("ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_DOWN", "ROUND_UP")
                        or quantum <= 0
                        or not quantum.is_finite()
                        or quantum.normalize().as_tuple().digits != (1,)
                    ):
                        raise ValueError
                    amount = amount.quantize(quantum, rounding=getattr(decimal, mode))
                entry.update(
                    amount=str(amount),
                    currency=p["currency"],
                    status="estimated",
                    price_version=p["version"],
                    price_source=p["source_ref"],
                    price_definition=p["definition_ref"],
                    rates=rates,
                    unit_tokens=p["unit_tokens"],
                    formula="sum(charge_tokens[category]*rate)/unit_tokens",
                    charge_tokens=charge_tokens,
                )
            except (KeyError, ValueError, InvalidOperation, TypeError):
                pass
        result.append(entry)
    return result


def _billing(scope, canonical, units, attempts, issues):
    billing = scope.get("billing_scope")
    if not billing:
        return {"status": "NOT_PROVIDED"}, {"status": "NOT_PROVIDED"}
    needed = (
        "provider",
        "account_ref",
        "key_ref",
        "model",
        "start",
        "end",
        "timezone",
        "time_basis",
        "definition_ref",
        "source_ref",
        "key_binding_evidence_ref",
    )
    complete = all(billing.get(k) for k in needed)
    complete = complete and billing.get("inventory_complete") is True
    try:
        ZoneInfo(billing.get("timezone") or "")
    except (ZoneInfoNotFoundError, ValueError):
        complete = False
    complete = complete and instant(billing.get("start")) is not None
    complete = complete and instant(billing.get("end")) is not None
    selected, boundaries = [], []
    for r in units:
        if any(r.get(k) != billing.get(k) for k in ("provider", "key_ref")):
            continue
        if r.get("source_mode") in ("partial_thread_snapshot", "partial_dsh_native"):
            boundaries.append(r)
            continue
        if r.get("actual_model") != billing.get("model") or not r.get("actual_model"):
            boundaries.append(r)
            continue
        if r.get("usage_definition_ref") != billing.get("definition_ref") or not r.get(
            "usage_definition_ref"
        ):
            boundaries.append(r)
            continue
        if r.get("account_ref") != billing.get("account_ref"):
            boundaries.append(r)
            continue
        time_basis = billing.get("time_basis")
        stamp = r.get("timestamp") if time_basis == "usage_completion" else None
        if time_basis in ("request_start", "settlement") and r.get("billing_time_evidence_ref"):
            stamp = r.get("request_started_at" if time_basis == "request_start" else "settled_at")
        if instant(stamp) is None:
            # A cumulative segment is usable only when the billing window fully
            # contains it and the explicit time basis agrees.
            w = r.get("window")
            enclosed = (
                w
                and billing.get("time_basis") == "usage_completion"
                and instant(billing.get("start")) is not None
                and instant(billing.get("end")) is not None
                and instant(w["start"]) >= instant(billing["start"])
                and instant(w["end"]) <= instant(billing["end"])
            )
            if not enclosed:
                boundaries.append(r)
                continue
        elif not window_contains(billing, stamp):
            continue
        selected.append(r)
    attribution_only = {
        "binding_missing",
        "binding_ambiguous",
        "shared_thread_unsliced",
        "response_attribution_conflict",
        "binding_identity_conflict",
        "compaction_binding_unknown",
        "task_window_incomplete",
        "task_timestamp_unknown",
        "task_cumulative_boundary_unknown",
    }
    numeric_gaps = [issue for issue in issues if issue["code"] not in attribution_only]
    complete = bool(complete and not boundaries and not numeric_gaps)
    categories = {"target_task": [], "other_task": [], "unallocated": []}
    for r in selected:
        category = (
            "target_task"
            if r.get("task_ref") == scope["task_ref"]
            else "other_task"
            if r.get("task_ref")
            else "unallocated"
        )
        categories[category].append(r)
    local = summarize(selected)
    fields = {}
    matched = True
    vendor = billing.get("vendor_usage") or {}
    _, invalid_vendor_fields = numeric_usage(vendor)
    for field in FIELDS:
        value = vendor.get(field)
        if value is None:
            continue
        if type(value) is not int or value < 0 or field in invalid_vendor_fields:
            complete = False
            fields[field] = {
                "vendor": None,
                "local_matched": local["tokens"][field],
                "raw_difference": None,
                "status": "invalid_vendor_value",
            }
            continue
        local_value = local["tokens"].get(field)
        diff = value - local_value if local_value is not None else None
        field_complete = local["field_coverage"][field]["unknown"] == 0
        if not field_complete or local_value is None:
            complete = False
        matched = matched and diff == 0
        fields[field] = {
            "vendor": value,
            "local_matched": local_value,
            "difference" if complete else "raw_difference": diff,
        }
    complete = complete and bool(fields)
    # Attempt metadata cannot close usage coverage, even on a successful HTTP.
    unknown_attempts = len(attempts)
    if unknown_attempts and not billing.get("attempt_usage_binding_evidence_ref"):
        complete = False
    for values in fields.values():
        if not complete and "difference" in values:
            values["raw_difference"] = values.pop("difference")
    token_status = "MATCHED" if complete and matched else "MISMATCH" if complete else "PARTIAL"
    amount = _billing_amount(billing, selected, scope.get("price_versions", []))
    status = token_status
    if billing.get("vendor_amount") is not None:
        if amount["status"] == "PARTIAL" or not complete:
            status = "PARTIAL"
        elif amount["status"] == "MISMATCH":
            status = "MISMATCH"
    attribution = "complete" if not categories["unallocated"] and complete else "partial"
    return (
        {
            "categories": {k: summarize(v) for k, v in categories.items()},
            "local_matched": local,
            "boundary_unknown": len(boundaries),
            "attempt_events_without_usage_binding": unknown_attempts,
            "outside_inventory_unknown": billing.get("inventory_complete") is not True,
        },
        {
            "status": status,
            "token_status": token_status,
            "attribution_status": attribution,
            "tokens": fields,
            "amount": amount,
        },
    )


def _billing_amount(billing, records, prices):
    vendor = billing.get("vendor_amount")
    try:
        if vendor is not None and not Decimal(str(vendor)).is_finite():
            raise ValueError
    except (InvalidOperation, ValueError):
        return {
            "status": "PARTIAL",
            "vendor": None,
            "local_estimate": None,
            "raw_difference": None,
            "currency": billing.get("currency"),
        }
    costs = _costs(records, prices)
    result = {
        "status": "PARTIAL" if vendor is not None else "NOT_PROVIDED",
        "vendor": vendor,
        "local_estimate": None,
        "raw_difference": None,
        "currency": billing.get("currency"),
    }
    try:
        if (
            vendor is None
            or not costs
            or any(c["amount"] is None or c["currency"] != billing.get("currency") for c in costs)
        ):
            return result
        local = sum(Decimal(c["amount"]) for c in costs)
        vendor = Decimal(str(vendor))
        if not vendor.is_finite():
            return result
        result.update(local_estimate=str(local), raw_difference=str(vendor - local))
        # A local API estimate becomes comparable only under a supplied vendor
        # rule (tax, discount and rounding cannot be guessed).
        if billing.get("amount_rule_ref") and billing.get("price_version_refs") == sorted(
            {c["price_version"] for c in costs}
        ):
            result["difference"] = result.pop("raw_difference")
            result["status"] = "MATCHED" if vendor == local else "MISMATCH"
    except (InvalidOperation, TypeError):
        pass
    return result


def _timing(canonical, timings, task_units, task_window):
    result = []
    known_output = summarize(task_units)["tokens"]["output_tokens"]
    output_complete = all(r["usage"].get("output_tokens") is not None for r in task_units)
    for kind in ("request_completion", "after_headers", "generation", "agent_turn"):
        for status in ("completed", "failed", "aborted", "unknown"):
            eligible = [t for t in timings if t.get("kind") == kind and t.get("status") == status]
            expected = set()
            for r in canonical:
                associated = [
                    t
                    for t in timings
                    if (
                        (t.get("response_id") == r.get("response_id"))
                        if kind != "agent_turn"
                        else (
                            t.get("thread_id") == r.get("thread_id")
                            and t.get("turn_id") == r.get("turn_id")
                            and t.get("turn_id")
                        )
                    )
                    and t.get("provider") == r.get("provider")
                    and t.get("key_ref") == r.get("key_ref")
                    and t.get("kind") == kind
                ]
                states = {t.get("status") for t in associated if t.get("status")}
                inferred = next(iter(states)) if len(states) == 1 else r.get("status") or "unknown"
                if inferred == status:
                    expected.add(
                        (
                            r.get("provider"),
                            r.get("key_ref"),
                            (r.get("thread_id"), r.get("turn_id"))
                            if kind == "agent_turn"
                            else r.get("response_id"),
                        )
                    )
            samples, used_ids = [], set()
            for t in eligible:
                rows = [
                    r
                    for r in canonical
                    if r.get("provider") == t.get("provider")
                    and r.get("key_ref") == t.get("key_ref")
                    and (
                        (t.get("response_id") and r.get("response_id") == t["response_id"])
                        if kind != "agent_turn"
                        else (
                            t.get("turn_id")
                            and r.get("thread_id") == t.get("thread_id")
                            and r.get("turn_id") == t["turn_id"]
                        )
                    )
                ]
                siblings = [
                    other
                    for other in eligible
                    if other.get("provider") == t.get("provider")
                    and other.get("key_ref") == t.get("key_ref")
                    and other.get("response_id") == t.get("response_id")
                    and other.get("turn_id") == t.get("turn_id")
                ]
                if (
                    len(
                        {
                            (other.get("start"), other.get("end"), other.get("clock_ref"))
                            for other in siblings
                        }
                    )
                    > 1
                ):
                    continue
                start, end = instant(t.get("start")), instant(t.get("end"))
                if (
                    not t.get("binding_evidence_ref")
                    or not t.get("start_source")
                    or not t.get("end_source")
                    or not rows
                    or (kind != "agent_turn" and len(rows) != 1)
                    or start is None
                    or end is None
                    or end <= start
                    or any(r["usage"].get("output_tokens") is None for r in rows)
                ):
                    continue
                key = tuple(
                    (r.get("provider"), r.get("key_ref"), r.get("response_id")) for r in rows
                )
                if key in used_ids:
                    continue
                used_ids.add(key)
                samples.append(
                    {
                        "output": sum(r["usage"]["output_tokens"] for r in rows),
                        "start": start,
                        "end": end,
                        "clock_ref": t.get("clock_ref"),
                        "source": t["source"],
                        "start_source": t["start_source"],
                        "end_source": t["end_source"],
                    }
                )
            output = sum(s["output"] for s in samples)
            duration = sum(s["end"] - s["start"] for s in samples)
            union_rate = None
            wall_window_rate = None
            union = None
            if samples and all(
                s["clock_ref"] == samples[0]["clock_ref"] and s["clock_ref"] for s in samples
            ):
                intervals = sorted((s["start"], s["end"]) for s in samples)
                begin, end = intervals[0]
                union = 0
                for a, b in intervals[1:]:
                    if a > end:
                        union += end - begin
                        begin = a
                    end = max(end, b)
                union += end - begin
                union_rate = output / union
                wall_window_rate = output / (
                    max(s["end"] for s in samples) - min(s["start"] for s in samples)
                )
            result.append(
                {
                    "kind": kind,
                    "status": status,
                    "used": len(samples),
                    "eligible": max(len(expected), len(eligible)),
                    "unknown": max(len(expected), len(eligible)) - len(samples),
                    "output_tokens": output if samples else None,
                    "duration_seconds": duration if samples else None,
                    "weighted_rate": output / duration if duration else None,
                    "parallel_union_rate": union_rate,
                    "union_duration_seconds": union,
                    "wall_window_rate": wall_window_rate,
                    "output_coverage": output / known_output
                    if output_complete and known_output
                    else None,
                    "output_definition": "total output includes reasoning when reported",
                    "formula": "sum(output_tokens)/sum(duration_seconds)",
                    "samples": samples,
                }
            )
    start, end = instant(task_window.get("start")), instant(task_window.get("end"))
    wall = end - start if None not in (start, end) and end >= start else None
    return {
        "metrics": result,
        "wall_clock_seconds": wall,
        "wall_clock_state": "complete"
        if task_window.get("complete_independent_pass") and task_window.get("end_source")
        else "elapsed_to_cutoff",
    }


def build_report(scope: dict, *, base: Path = Path(".")) -> dict:
    validate_scope(scope)
    issues = []
    receipts, cumulative, attempts, timings, compactions, sources, snapshots, native = _read_sources(
        scope, base, issues
    )
    canonical, ambiguous = _deduplicate(receipts, issues)
    native_units, native_comparisons = _account_dsh_native(native, canonical, issues)
    dsh_cumulative = [r for r in cumulative if r.get("source_mode") == "dsh_assistant_cumulative"]
    cumulative = [r for r in cumulative if r not in dsh_cumulative]
    units, observed = _account(canonical, cumulative, issues)
    units.extend(native_units)
    dsh_deltas, dsh_observed = _account([], dsh_cumulative, issues)
    observed.extend(dsh_observed)
    for delta in dsh_deltas:
        matching = [r for r in units if _session_key(r) == _session_key(delta)
                    and r.get("provider") == delta.get("provider")
                    and r.get("key_ref") == delta.get("key_ref")]
        ordinary = [r for r in matching if r.get("purpose") == "assistant"]
        native_comparisons.append({"runtime": "dsh",
            "runtime_session_id": delta.get("runtime_session_id"),
            "native_cumulative_delta": delta["usage"], "sources": delta["sources"],
            "provider_usage": summarize(ordinary), "additive": False,
            "selected_source": "bound_records" if matching else "partial_cumulative"})
        if not matching:
            _issue(issues, "dsh_provider_original_missing", delta["sources"][0])
            delta.update(source_mode="partial_dsh_native", purpose="assistant")
            units.append(delta)
    units, snapshot_comparisons = _reconcile_consumer_snapshots(units, snapshots, issues)
    task = []
    task_window = scope.get("task_window") or {}
    window_valid = (
        instant(task_window.get("start")) is not None
        and instant(task_window.get("end")) is not None
    )
    if not window_valid or not task_window.get("start_source"):
        _issue(issues, "task_window_incomplete")
    for r in units:
        if r.get("task_ref") != scope["task_ref"]:
            continue
        w = r.get("window")
        if not window_valid:
            task.append(r)
        elif w:
            if instant(w["start"]) >= instant(task_window["start"]) and instant(
                w["end"]
            ) <= instant(task_window["end"]):
                task.append(r)
            else:
                _issue(issues, "task_cumulative_boundary_unknown", r["sources"][0])
        elif instant(r.get("timestamp")) is None:
            _issue(issues, "task_timestamp_unknown", r["sources"][0])
        elif window_contains(task_window, r["timestamp"]):
            task.append(r)
    compaction_rows = [r for r in task if r.get("runtime") == "dsh"
                       and r.get("purpose") == "compaction"]
    compaction_keys = set()
    for c in compactions:
        matched = [
            r
            for r in canonical
            if c.get("response_id")
            and r.get("response_id") == c["response_id"]
            and r.get("thread_id") == c.get("thread_id")
        ]
        if len(matched) != 1:
            _issue(issues, "compaction_binding_unknown", c["source"])
            continue
        r = matched[0]
        key = (r.get("provider"), r.get("key_ref"), r["response_id"])
        if key not in compaction_keys:
            compaction_keys.add(key)
            if r.get("task_ref") == scope["task_ref"] and (
                not window_valid or window_contains(task_window, r.get("timestamp"))
            ):
                compaction_rows.append(r)
    billing, reconciliation = _billing(scope, canonical, units, attempts, issues)
    layers = []
    for declared in scope.get("layer_coverage", []):
        selector = {k: v for k, v in identity(declared).items() if v is not None}
        rows = [r for r in task if all(r.get(k) == v for k, v in selector.items())]
        state = declared.get("status", "unknown")
        invoked = any(
            a.get("task_ref") == scope["task_ref"]
            and all(a.get(k) == v for k, v in selector.items())
            for a in attempts
        )
        if state == "not_invoked" and (not declared.get("evidence_ref") or rows or invoked):
            state = "partial" if rows else "unknown"
        if state in ("observed", "complete"):
            state = (
                "unknown"
                if not rows
                else "partial"
                if any(r["usage"].get(field) is None for r in rows for field in REQUIRED)
                else "observed"
            )
        layers.append(
            {
                **selector,
                "status": state,
                "evidence_ref": declared.get("evidence_ref"),
                **summarize(rows),
            }
        )
    matched_requests = {(r.get("provider"), r.get("request_id")) for r in canonical
                        if r.get("request_id")}
    unknown_dsh_attempts = {
        (a.get("provider"), a.get("request_id")) for a in attempts
        if a.get("runtime") == "dsh" and (a.get("provider"), a.get("request_id")) not in matched_requests
    }
    for provider, request_id in sorted(unknown_dsh_attempts, key=str):
        _issue(issues, "dsh_attempt_usage_missing", request_id=request_id, provider=provider)
    summary = summarize(task)
    usage_complete = (
        bool(task)
        and not issues
        and not ambiguous
        and all(summary["field_coverage"][f]["unknown"] == 0 for f in REQUIRED)
    )
    usage_complete = usage_complete and scope.get("inventory_complete") is True
    usage_complete = usage_complete and all(
        layer["status"] in ("observed", "not_invoked") for layer in layers
    )
    unallocated = [r for r in units if not r.get("task_ref")]
    task_timings = [
        t
        for t in timings
        if any(
            r.get("task_ref") == scope["task_ref"]
            and r.get("provider") == t.get("provider")
            and r.get("key_ref") == t.get("key_ref")
            and (
                (t.get("response_id") and r.get("response_id") == t["response_id"])
                or (
                    t.get("kind") == "agent_turn"
                    and t.get("turn_id")
                    and r.get("turn_id") == t["turn_id"]
                    and r.get("thread_id") == t.get("thread_id")
                )
            )
            for r in canonical
        )
    ]
    timing = _timing(
        [r for r in canonical if r.get("task_ref") == scope["task_ref"]],
        task_timings,
        task,
        scope.get("task_window") or {},
    )
    if not usage_complete:
        for metric in timing["metrics"]:
            metric["output_coverage"] = None
    report = {
        "schema_version": "model-usage-report/v1",
        "metadata": {
            "task_ref": scope["task_ref"],
            "code_revision": scope.get("code_revision"),
            "config_refs": scope.get("config_refs", []),
        },
        "scope": {
            "sha256": hashlib.sha256(
                json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "inventory_complete": scope.get("inventory_complete", False),
            "task_window": {
                k: v
                for k, v in (scope.get("task_window") or {}).items()
                if k
                in (
                    "start",
                    "end",
                    "timezone",
                    "start_source",
                    "end_source",
                    "complete_independent_pass",
                )
            },
        },
        "sources": sources,
        "task_usage": {**summary, "groups": _groups(task)},
        "billing_window_usage": billing,
        "layers": layers,
        "compaction_subset": {**summarize(compaction_rows), "additive": False},
        "timing_metrics": timing,
        "cost_estimates": _costs(task, scope.get("price_versions", [])),
        "reconciliation": reconciliation,
        "limitations": issues,
        "billing_scope": {
            k: v
            for k, v in (scope.get("billing_scope") or {}).items()
            if k
            in (
                "provider",
                "account_ref",
                "key_ref",
                "model",
                "start",
                "end",
                "timezone",
                "time_basis",
                "definition_ref",
                "source_ref",
                "key_binding_evidence_ref",
            )
        },
        "usage_status": "complete" if usage_complete else "partial" if task else "unknown",
        "attribution_status": "partial"
        if unallocated
        or ambiguous
        or not usage_complete
        or any(not r.get("role") or not r.get("phase") for r in task)
        else "complete",
        "timing_status": "partial" if any(m["used"] for m in timing["metrics"]) else "unknown",
        "billing_status": reconciliation["status"],
        "unallocated": summarize(unallocated),
        "attempts": attempts,
        "dsh_unknown_attempts": len(unknown_dsh_attempts),
        "responses": canonical,
        "ambiguous_responses": ambiguous,
        "cost_units": units,
        "observed_thread_totals": observed,
        "consumer_snapshot_comparisons": snapshot_comparisons,
        "dsh_native_comparisons": native_comparisons,
        "usage_definitions": sorted(
            {r["usage_definition_ref"] for r in units if r.get("usage_definition_ref")}
        ),
    }
    costs_by_currency = defaultdict(list)
    for cost in report["cost_estimates"]:
        costs_by_currency[cost.get("currency")].append(cost)
    report["cost_summary"] = []
    for currency, costs in costs_by_currency.items():
        known = [Decimal(c["amount"]) for c in costs if c["amount"] is not None]
        report["cost_summary"].append(
            {
                "currency": currency,
                "known_estimate_subtotal": str(sum(known, Decimal(0))) if known else None,
                "known": len(known),
                "unknown": len(costs) - len(known),
            }
        )
    issue_groups = defaultdict(list)
    for issue in issues:
        issue_groups[issue["code"]].append(issue)
    report["limitation_summary"] = [
        {"code": code, "count": len(rows), "first_source": rows[0].get("source")}
        for code, rows in issue_groups.items()
    ]
    # Bindings contain source evidence/configuration, never raw bodies. Avoid
    # copying the input object or arbitrary fields into the report.
    for r in [*canonical, *ambiguous, *units, *observed]:
        r.pop("binding", None)
    return report


def render_markdown(report):
    def cell(value):
        return str(value if value is not None else "unknown").replace("|", "\\|").replace("\n", " ")

    def table(headers, rows):
        return [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows),
        ]

    lines = [
        f"# Model usage: {cell(report['metadata']['task_ref'])}",
        "",
        "Local numeric evidence; amounts are estimates, not a provider invoice.",
        "",
    ]
    lines += table(
        ["Usage", "Attribution", "Timing", "Billing"],
        [
            [
                report[k]
                for k in ("usage_status", "attribution_status", "timing_status", "billing_status")
            ]
        ],
    )
    lines += ["", "## Task usage", ""]
    lines += table(
        ["Field", "Known subtotal", "Known / unknown units"],
        [
            [
                field,
                report["task_usage"]["tokens"][field],
                f"{report['task_usage']['field_coverage'][field]['known']} / "
                f"{report['task_usage']['field_coverage'][field]['unknown']}",
            ]
            for field in FIELDS
        ],
    )
    lines += [
        "",
        f"Cache rate: {cell(report['task_usage']['tokens']['cache_rate'])}; "
        f"sample input: {cell(report['task_usage']['cache_rate_input_coverage'])}.",
        "",
        "## Groups and layers",
        "",
    ]
    lines += table(
        ["Identity", "Units", "Input", "Cached", "Output"],
        [
            [
                json.dumps(group["identity"], ensure_ascii=False, sort_keys=True),
                group["cost_units"],
                *(
                    group["tokens"][k]
                    for k in ("input_tokens", "cached_input_tokens", "output_tokens")
                ),
            ]
            for group in report["task_usage"]["groups"]
        ],
    )
    lines += [""] + table(
        ["Role / phase", "Status", "Input", "Output", "Evidence"],
        [
            [
                f"{layer.get('role')} / {layer.get('phase')}",
                layer["status"],
                layer["tokens"]["input_tokens"],
                layer["tokens"]["output_tokens"],
                layer["evidence_ref"],
            ]
            for layer in report["layers"]
        ],
    )
    if report.get("dsh_native_comparisons"):
        lines += ["", "## DSH native reconciliation (not additive)", ""]
        lines += table(
            ["Session", "Selected source", "Provider input", "Native input", "Input difference"],
            [[row["runtime_session_id"], row["selected_source"],
              row["provider_usage"]["tokens"]["input_tokens"],
              row.get("native_assistant_usage", {}).get("tokens", {}).get("input_tokens",
                  row.get("native_cumulative_delta", {}).get("input_tokens")),
              row.get("difference", {}).get("input_tokens")]
             for row in report["dsh_native_comparisons"]])
    dsh_rows = [row for row in report["responses"] if row.get("runtime") == "dsh"]
    if dsh_rows:
        lines += ["", "## DSH provider buckets / presence", ""]
        lines += table(["Response / request", "Session", "Raw buckets", "Present fields", "Definition"],
            [[row.get("response_id") or row.get("request_id"), row.get("runtime_session_id"),
              json.dumps(row.get("raw_usage", {}), sort_keys=True),
              json.dumps(row.get("present_fields", [])), row.get("usage_definition_ref")]
             for row in dsh_rows])
        lines += ["", f"DSH attempts without numeric receipt: {report['dsh_unknown_attempts']}", ""]
    if report.get("consumer_snapshot_comparisons"):
        lines += ["", "## Consumer snapshot reconciliation", ""]
        lines += table(
            ["Thread", "Selected source", "Snapshot input", "Bound input", "Input difference"],
            [[row["thread_id"], row["selected_source"], row["snapshot_usage"]["input_tokens"],
              row.get("native_usage", {}).get("input_tokens"),
              row.get("difference", {}).get("input_tokens")]
             for row in report["consumer_snapshot_comparisons"]],
        )
    lines += [
        "",
        "## Billing",
        "",
        f"Scope: {cell(json.dumps(report['billing_scope'], ensure_ascii=False, sort_keys=True))}",
        "",
    ]
    rec = report["reconciliation"]
    lines += table(
        ["Field", "Vendor", "Local matched", "Difference / raw difference"],
        [
            [
                field,
                row["vendor"],
                row["local_matched"],
                row.get("difference", row.get("raw_difference")),
            ]
            for field, row in rec.get("tokens", {}).items()
        ],
    )
    billing = report["billing_window_usage"]
    lines += [""] + table(
        ["Attribution", "Input", "Output"],
        [
            [name, value["tokens"]["input_tokens"], value["tokens"]["output_tokens"]]
            for name, value in billing.get("categories", {}).items()
        ],
    )
    lines += [
        "",
        f"Amount: {cell(json.dumps(rec.get('amount', {}), sort_keys=True))}",
        "",
        "## Compaction subset (not additive)",
        "",
        cell(json.dumps(report["compaction_subset"]["tokens"], sort_keys=True)),
        "",
        "## Timing",
        "",
    ]
    lines += table(
        [
            "Kind / status",
            "Used / eligible / unknown",
            "Output",
            "Seconds",
            "Weighted rate",
            "Union rate",
            "Output coverage",
        ],
        [
            [
                f"{m['kind']} / {m['status']}",
                f"{m['used']} / {m['eligible']} / {m['unknown']}",
                m["output_tokens"],
                m["duration_seconds"],
                m["weighted_rate"],
                m["parallel_union_rate"],
                m["output_coverage"],
            ]
            for m in report["timing_metrics"]["metrics"]
        ],
    )
    lines += [
        "",
        "Rates = sum(total output including reported reasoning) / sum(duration). "
        "Turn activity includes tools and waits. Endpoint sources and sample detail: report.json.",
        f"Wall clock: {cell(report['timing_metrics']['wall_clock_seconds'])} seconds "
        f"({report['timing_metrics']['wall_clock_state']}).",
        "",
        "## Local estimates",
        "",
    ]
    lines += table(
        ["Currency", "Known estimate subtotal", "Known / unknown units"],
        [
            [row["currency"], row["known_estimate_subtotal"], f"{row['known']} / {row['unknown']}"]
            for row in report["cost_summary"]
        ],
    )
    lines += ["", "## Frozen sources", ""]
    lines += table(
        ["Source", "Path", "Offset / length", "SHA256", "State"],
        [
            [
                source["id"],
                source["path"],
                f"{source['byte_offset']} / {source.get('byte_length')}",
                source.get("sha256"),
                source["status"],
            ]
            for source in report["sources"]
        ],
    )
    lines += ["", "## Limitations", ""]
    lines += table(
        ["Code", "Count", "First locator"],
        [
            [row["code"], row["count"], json.dumps(row["first_source"], sort_keys=True)]
            for row in report["limitation_summary"]
        ],
    )
    lines += [
        "",
        "Full per-response fields, missing coverage, attempts, price formulas and locators: report.json.",
    ]
    return "\n".join(lines) + "\n"


def write_report(scope_path: Path, output_dir: Path):
    scope_path = Path(scope_path)
    try:
        scope = json.loads(scope_path.read_text())
    except (OSError, ValueError) as exc:
        raise ScopeError("scope is unavailable or invalid JSON") from exc
    report = build_report(scope, base=scope_path.resolve().parent)
    output_dir = Path(output_dir)
    # Exclusive directory creation prevents overwriting any retained report.
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, content in (
        ("report.json", json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n"),
        ("report.md", render_markdown(report)),
    ):
        with (output_dir / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
        (output_dir / name).chmod(0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = write_report(args.scope, args.output_dir)
    except (ScopeError, FileExistsError) as exc:
        parser.exit(
            2,
            f"usage_report: {exc if isinstance(exc, ScopeError) else 'output directory exists'}\n",
        )
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("usage_status", "attribution_status", "timing_status", "billing_status")
            }
        )
    )


if __name__ == "__main__":
    main()
