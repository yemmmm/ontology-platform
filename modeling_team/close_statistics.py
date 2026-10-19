"""R4.3-036: numeric activity capture and offline, owner-driven close reports.

Only explicitly registered members/sources are read. Capture/report failures are
advisory and must never change tool execution, stop receipts or resource cleanup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .usage_capture import identity, utc_now

LOG = logging.getLogger(__name__)
SCHEMA = "team-close-statistics/v1"
CAPTURE_DIRECTORY = "evidence/close-statistics-capture"
_WRITE_LOCK = threading.Lock()
EVENTS = {
    "launch",
    "bind",
    "exit",
    "llm_start",
    "llm_end",
    "tool_start",
    "tool_end",
    "tool_request",
    "tool_rejected",
    "pause_start",
    "pause_end",
    "wait_start",
    "wait_end",
    "capture_gap",
}
STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "unfinished",
    "unknown",
    "rejected",
    "startup_failed",
    "transport_error",
    "http_error",
    "stream_error",
    "client_disconnected",
}


@lru_cache(maxsize=1)
def clock_ref():
    # Both CPython CLOCK_MONOTONIC and Linux Node uv_hrtime use this kernel
    # clock. boot identity also prevents unions across reboots/machines.
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return "linux-monotonic:" + boot
    except OSError:
        return "process-monotonic:" + uuid.uuid4().hex


def clock_stamp():
    return {"clock_ref": clock_ref(), "monotonic_ns": time.monotonic_ns()}


def safe_activity(event):
    if event.get("event") not in EVENTS:
        return None
    value = {"schema_version": "agent-activity/v1", **identity(event), "event": event["event"]}
    for field in (
        "call_id",
        "root_call_id",
        "logical_call_id",
        "tool_name",
        "clock_ref",
        "recorded_at",
        "purpose",
    ):
        item = event.get(field)
        if isinstance(item, str) and len(item) <= 512 and not any(ord(c) < 32 for c in item):
            value[field] = item
    for field in ("monotonic_ns", "returncode"):
        item = event.get(field)
        if type(item) is int and (field == "returncode" or item >= 0):
            value[field] = item
    if event.get("status") in STATUSES:
        value["status"] = event["status"]
    return value


def _append(path, value):
    try:
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "a") as stream:
                stream.write(json.dumps(value, sort_keys=True) + "\n")
        return True
    except Exception:
        LOG.warning("close_statistics_capture_incomplete")
        return False


class ActivityRecorder:
    """One actual launch instance, registered before attempting process creation."""

    def __init__(self, root, context, *, usage_sources=(), fresh_session=False):
        self.root = Path(root).resolve()
        self.context = {**identity(context)}
        self.context.setdefault("process_instance", uuid.uuid4().hex)
        self.context.setdefault("runtime_session_id", None)
        self.started_at = utc_now()
        self.exited = False
        self._exit_lock = threading.Lock()
        self.path = self.root / CAPTURE_DIRECTORY / "activity.jsonl"
        _append(
            self.root / CAPTURE_DIRECTORY / "statistics-members.jsonl",
            {
                **self.context,
                "started_at": self.started_at,
                "fresh_session": fresh_session,
                "activity_path": str(self.path),
                "usage_sources": [
                    {
                        "path": str(Path(s["path"]).resolve()),
                        "kind": s["kind"],
                        "shared": s.get("shared", False),
                    }
                    | (
                        {"capture_session_id": s["capture_session_id"]}
                        if s.get("capture_session_id")
                        else {}
                    )
                    for s in usage_sources
                ],
            },
        )
        self.emit("launch")

    def emit(self, event, **fields):
        value = safe_activity(
            {**self.context, **clock_stamp(), "recorded_at": utc_now(), **fields, "event": event}
        )
        if value:
            _append(self.path, value)

    def bind(self, native_session_id):
        self.context["runtime_session_id"] = native_session_id
        if self.context.get("runtime") == "codex":
            self.context["thread_id"] = native_session_id
        self.emit("bind")

    def exit(self, returncode, *, startup_failed=False, time_known=True):
        with self._exit_lock:
            if not self.exited and (returncode is not None or startup_failed):
                self.emit(
                    "exit",
                    returncode=returncode,
                    **({"monotonic_ns": None} if not time_known else {}),
                    status="startup_failed"
                    if startup_failed
                    else "completed"
                    if returncode == 0
                    else "failed",
                )
                self.exited = True

    def execute_tool(self, call_id, name, callback):
        self.emit("tool_start", call_id=str(call_id), tool_name=name)
        status = "failed"
        try:
            result = callback()
            status = (
                "failed"
                if isinstance(result, dict)
                and (
                    result.get("ok") is False
                    or result.get("isError") is True
                    or result.get("error")
                )
                else "completed"
            )
            return result
        finally:
            self.emit("tool_end", call_id=str(call_id), tool_name=name, status=status)

    @contextmanager
    def tool(self, call_id, name, *, root_call_id=None):
        self.emit("tool_start", call_id=str(call_id), tool_name=name, root_call_id=root_call_id)
        status = "failed"
        try:
            yield
            status = "completed"
        except BaseException:
            raise
        finally:
            self.emit(
                "tool_end",
                call_id=str(call_id),
                tool_name=name,
                root_call_id=root_call_id,
                status=status,
            )


def register_statistics_link(root, linked_root, evidence_ref):
    if Path(root).resolve() != Path(linked_root).resolve():
        _append(
            Path(root) / CAPTURE_DIRECTORY / "statistics-links.jsonl",
            {"root": str(Path(linked_root).resolve()), "evidence_ref": evidence_ref},
        )


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _union(intervals):
    if not intervals:
        return None
    if len({r[0] for r in intervals}) != 1:
        return None
    total, left, right = 0, None, None
    for _, start, end in sorted(intervals, key=lambda r: r[1]):
        if left is None:
            left, right = start, end
        elif start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return (total + right - left) / 1e9


def _key(row):
    return row.get("runtime"), row.get("process_instance"), row.get("agent_id")


def _interval(start, end, limits):
    if not start or not end:
        return None
    a, b = start.get("monotonic_ns"), end.get("monotonic_ns")
    if not _number(a) or not _number(b):
        limits.add("monotonic_boundary_missing")
    elif not start.get("clock_ref") or start.get("clock_ref") != end.get("clock_ref"):
        limits.add("clock_incomparable")
    elif b < a:
        limits.add("clock_reversed")
    else:
        return start["clock_ref"], a, b
    return None


def _calls(rows, prefix, cutoff, limits):
    calls = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["event"].startswith(prefix + "_") and row.get("call_id"):
            calls[row["call_id"]][row["event"].split("_", 1)[1]].append(row)
    intervals, details = [], []
    counts = dict(
        requests=0,
        executed=0,
        completed=0,
        failed=0,
        cancelled=0,
        unfinished=0,
        rejected=0,
        unknown=0,
        unfinished_elapsed_seconds=None,
    )
    for call_id, parts in calls.items():
        all_rows = [row for values in parts.values() for row in values]
        if prefix == "tool" and any(r.get("root_call_id") not in (None, call_id) for r in all_rows):
            continue
        counts["requests"] += 1
        starts, ends = parts.get("start", []), parts.get("end", [])

        # Copies are harmless; different observations for one endpoint are a gap.
        def unique(values):
            distinct = {
                (r.get("clock_ref"), r.get("monotonic_ns"), r.get("status")) for r in values
            }
            if len(distinct) > 1:
                limits.add("activity_endpoint_conflict")
                return None
            return values[0] if values else None

        start, end = unique(starts), unique(ends)
        status = end.get("status", "unknown") if end else "unfinished" if start else "unknown"
        if parts.get("rejected") and not starts:
            counts["rejected"] += 1
            continue
        if starts:
            counts["executed"] += 1
        span = _interval(start, end, limits)
        if span:
            intervals.append(span)
        elif not start or not end:
            limits.add("activity_boundary_missing")
        if status in {"completed", "failed", "cancelled", "unfinished"}:
            counts[status] += 1
        elif status in {"transport_error", "http_error", "stream_error"}:
            counts["failed"] += 1
        elif status == "client_disconnected":
            counts["cancelled"] += 1
        else:
            counts["unknown"] += 1
        lower_bound = _interval(start, cutoff, limits) if start and not ends else None
        if lower_bound:
            counts["unfinished_elapsed_seconds"] = (counts["unfinished_elapsed_seconds"] or 0) + (
                lower_bound[2] - lower_bound[1]
            ) / 1e9
        details.append(
            {
                "call_id": call_id,
                "tool_name": next(
                    (r.get("tool_name") for r in all_rows if r.get("tool_name")), None
                ),
                "status": status,
                "seconds": (span[2] - span[1]) / 1e9 if span else None,
                "sources": [r["source"] for r in all_rows if r.get("source")],
            }
        )
    return counts, intervals, details


def aggregate_activity(config, usage, events):
    """Numeric close view using the existing 019/034 cost units unchanged."""
    from .usage_report import summarize

    limits = set(config.get("limitations", []))
    members, all_intervals, member_units = [], [], {}
    cutoff = config.get("cutoff_clock") or {}
    units = usage.get("cost_units", [])
    # Provider attempts do not need a response_id or a usage value to be timed.
    activity = list(events)
    for attempt in usage.get("attempts", []):
        if attempt.get("event") not in {"attempt_start", "attempt_end"}:
            continue
        end = attempt["event"] == "attempt_end"
        activity.append(
            {
                **identity(attempt),
                "event": "llm_end" if end else "llm_start",
                "clock_ref": attempt.get("clock_ref"),
                "monotonic_ns": attempt.get("monotonic_end_ns" if end else "monotonic_start_ns"),
                "call_id": ":".join(
                    str(attempt.get(k)) for k in ("proxy_session_id", "request_id", "attempt_index")
                ),
                "logical_call_id": ":".join(
                    str(attempt.get(k)) for k in ("proxy_session_id", "request_id")
                ),
                "purpose": attempt.get("purpose"),
                "status": attempt.get("status"),
                "source": attempt.get("source"),
            }
        )
    # Resolve agent_id only by a unique registered process/session, never by time.
    for row in activity:
        matches = [
            m
            for m in config.get("members", [])
            if m.get("runtime") == row.get("runtime")
            and m.get("process_instance") == row.get("process_instance")
            and row.get("process_instance")
            and (not row.get("agent_id") or m.get("agent_id") == row["agent_id"])
        ]
        if len(matches) == 1:
            row.setdefault("agent_id", matches[0].get("agent_id"))
    used_units = set()
    for declared in config.get("members", []):
        member = identity(declared)
        rows = [r for r in activity if _key(r) == _key(member)]
        bound = {r["runtime_session_id"] for r in rows if r.get("runtime_session_id")}
        if len(bound) == 1:
            member["runtime_session_id"] = bound.pop()
        member_limits = set()
        starts, exits = (
            [r for r in rows if r["event"] == "launch"],
            [r for r in rows if r["event"] == "exit"],
        )
        start, end = (starts[0] if starts else None), (exits[-1] if exits else None)
        lifecycle_conflict = any(
            len(
                {
                    (
                        r.get("clock_ref"),
                        r.get("monotonic_ns"),
                        r.get("status"),
                        r.get("returncode"),
                    )
                    for r in values
                }
            )
            > 1
            for values in (starts, exits)
        )
        if lifecycle_conflict:
            member_limits.add("lifecycle_endpoint_conflict")
        life = _interval(start, end, member_limits) if not lifecycle_conflict else None
        elapsed = _interval(start, cutoff, member_limits) if not end else None
        if not start:
            member_limits.add("launch_boundary_missing")
        if not end:
            member_limits.add("exit_unconfirmed")
        if any(r["event"] == "capture_gap" for r in rows):
            member_limits.add("activity_capture_incomplete")
        llm, requests, llm_details = _calls(rows, "llm", cutoff, member_limits)
        llm["logical_requests"] = len(
            {r.get("logical_call_id", r.get("call_id")) for r in rows if r["event"] == "llm_start"}
        )
        llm["compaction_requests"] = len(
            {
                r.get("logical_call_id", r.get("call_id"))
                for r in rows
                if r["event"] == "llm_start" and r.get("purpose") == "compaction"
            }
        )
        tools, execution, details = _calls(rows, "tool", cutoff, member_limits)
        spans = requests + execution
        active = _union(spans)
        if spans and active is None:
            member_limits.add("clock_incomparable")
        selected = []
        for index, unit in enumerate(units):
            if unit.get("runtime", "codex") != member.get("runtime"):
                continue
            session = unit.get("runtime_session_id") or unit.get("thread_id")
            if not session or session != member.get("runtime_session_id"):
                continue
            if unit.get("process_instance") and unit["process_instance"] != member.get(
                "process_instance"
            ):
                continue
            candidates = [
                m
                for m in config.get("members", [])
                if m.get("runtime") == member.get("runtime")
                and m.get("runtime_session_id") == session
            ]
            if not unit.get("process_instance") and len(candidates) != 1:
                member_limits.add("session_usage_instance_unallocated")
                continue
            if index not in used_units:
                selected.append(unit)
                used_units.add(index)
        totals = summarize(selected)
        for field in (
            "actual_model",
            "provider",
            "requested_model",
            "requested_effort",
            "effective_effort",
            "phase",
        ):
            observed = {u[field] for u in selected if u.get(field) is not None}
            if not member.get(field) and len(observed) == 1:
                member[field] = observed.pop()
        member_units[_key(member)] = selected
        if not selected:
            member_limits.add("token_usage_unknown")
        if member.get("runtime") == "codex":
            # Subscription internal requests and native tools lack a universal
            # precise boundary; even a known observed subtotal stays partial.
            member_limits.add("codex_internal_activity_unobservable")
        if not llm["requests"]:
            member_limits.add("llm_activity_unknown")
            llm["compaction_requests"] = None
        if not tools["requests"]:
            member_limits.add("tool_activity_unknown")
        llm["counts_basis"] = tools["counts_basis"] = "observed_records_only"
        llm["coverage_status"] = "partial" if llm["requests"] else "unknown"
        tools["coverage_status"] = "partial" if tools["requests"] else "unknown"
        waiting = {}
        for kind in ("pause", "wait"):
            _, intervals, _ = _calls(rows, kind, cutoff, member_limits)
            waiting[kind + "_seconds"] = _union(intervals)
        top = defaultdict(list)
        for detail in details:
            if detail["seconds"] is not None:
                top[detail["tool_name"]].append(detail["seconds"])
        member.update(
            usage=totals,
            lifecycle_seconds=(life[2] - life[1]) / 1e9 if life else None,
            scope_member=declared.get("scope_member", True),
            elapsed_to_cutoff_seconds=(elapsed[2] - elapsed[1]) / 1e9 if elapsed else None,
            llm_request_seconds=sum((b - a) / 1e9 for _, a, b in requests) if requests else None,
            tool_execution_seconds=sum((b - a) / 1e9 for _, a, b in execution)
            if execution
            else None,
            active_seconds=active,
            llm=llm,
            tools=tools,
            llm_attempts=llm_details,
            tool_calls=details,
            lifecycle_sources=[r["source"] for r in [*starts, *exits] if r.get("source")],
            **waiting,
            closure_status="closed" if end else "closing",
            exit_status=end.get("status") if end and not lifecycle_conflict else None,
            exit_returncode=end.get("returncode") if end and not lifecycle_conflict else None,
            tool_top_5=[
                {"tool_name": name, "seconds": sum(values), "samples": len(values)}
                for name, values in sorted(top.items(), key=lambda kv: -sum(kv[1]))[:5]
            ],
            limitations=sorted(member_limits),
        )
        member["other_or_uncovered_seconds"] = (
            max(0, member["lifecycle_seconds"] - active) if life and active is not None else None
        )
        member["activity_coverage"] = "partial" if member_limits else "observed"
        member["active_observed_subtotal_seconds"] = active
        if member["scope_member"]:
            all_intervals.extend(spans)
            limits.update(member_limits)
        members.append(member)
    task_context_members = [m for m in members if not m["scope_member"]]
    members = [m for m in members if m["scope_member"]]
    if any(
        m.get("role") == "delivery" and m["closure_status"] != "closed"
        for m in task_context_members
    ):
        limits.add("delivery_still_running")
    unallocated_activity = [
        r
        for r in activity
        if not any(_key(r) == _key(m) for m in [*members, *task_context_members])
    ]
    unallocated_counts, unallocated_intervals, _ = _calls(
        unallocated_activity, "llm", cutoff, limits
    )
    if usage.get("limitations"):
        limits.add("numeric_usage_partial")
    limits.add("host_auxiliary_usage_unknown")
    if not members:
        limits.add("member_inventory_unavailable")
    scoped_units = [
        u
        for u in units
        if any(
            u.get("runtime", "codex") == m.get("runtime")
            and (u.get("runtime_session_id") or u.get("thread_id")) == m.get("runtime_session_id")
            for m in members
        )
    ]
    task_usage = summarize(scoped_units)
    summary = dict(task_usage["tokens"])
    if (
        len(
            {
                (
                    u.get("provider"),
                    u.get("actual_model") or u.get("requested_model"),
                    u.get("usage_definition_ref"),
                )
                for u in scoped_units
            }
        )
        > 1
    ):
        summary["cache_rate"] = None
        limits.add("cache_rate_requires_model_provider_groups")
    for field in (
        "lifecycle_seconds",
        "llm_request_seconds",
        "tool_execution_seconds",
        "active_seconds",
    ):
        values = [m[field] for m in members if m[field] is not None]
        summary[field] = sum(values) if values else None
    # summary.active_seconds is cumulative Agent time, separately from Team union.
    denominator = sum(u["usage"].get("input_tokens") or 0 for u in scoped_units) + sum(
        u["usage"].get("output_tokens") or 0 for u in scoped_units
    )
    for member in members:
        known = [member["usage"]["tokens"].get(k) for k in ("input_tokens", "output_tokens")]
        member["known_token_share"] = (
            sum(v for v in known if v is not None) / denominator
            if denominator and any(v is not None for v in known)
            else None
        )
        member["known_token_share_denominator"] = denominator or None
    groups = []
    buckets = defaultdict(list)
    for m in members:
        buckets[
            tuple(
                m.get(k)
                for k in (
                    "runtime",
                    "provider",
                    "requested_model",
                    "actual_model",
                    "requested_effort",
                    "effective_effort",
                    "role",
                )
            )
        ].append(m)
    for group, values in buckets.items():
        selected = [u for m in values for u in member_units[_key(m)]]
        groups.append(
            {
                **dict(
                    zip(
                        (
                            "runtime",
                            "provider",
                            "requested_model",
                            "actual_model",
                            "requested_effort",
                            "effective_effort",
                            "role",
                        ),
                        group,
                    )
                ),
                **summarize(selected),
                "members": len(values),
            }
        )
        for field in (
            "lifecycle_seconds",
            "llm_request_seconds",
            "tool_execution_seconds",
            "active_seconds",
        ):
            known = [m[field] for m in values if m[field] is not None]
            groups[-1][field] = sum(known) if known else None
        groups[-1]["time_basis"] = "cumulative_observed_agent_seconds"
    sessions = []
    for session in sorted(
        {
            (
                m.get("runtime"),
                m.get("runtime_session_id"),
                m.get("process_instance") if not m.get("runtime_session_id") else None,
            )
            for m in members
        },
        key=str,
    ):
        values = [
            m
            for m in members
            if (
                m.get("runtime"),
                m.get("runtime_session_id"),
                m.get("process_instance") if not m.get("runtime_session_id") else None,
            )
            == session
        ]
        sessions.append(
            {
                "runtime": session[0],
                "runtime_session_id": session[1],
                "unbound_process_instance": session[2],
                "instances": len(values),
                "lifecycle_seconds": sum(
                    m["lifecycle_seconds"] for m in values if m["lifecycle_seconds"] is not None
                )
                if any(m["lifecycle_seconds"] is not None for m in values)
                else None,
            }
        )
        sessions[-1]["lifecycle_observed_subtotal_seconds"] = sessions[-1]["lifecycle_seconds"]
        if any(m["lifecycle_seconds"] is None for m in values):
            sessions[-1]["lifecycle_seconds"] = None
        lifecycle_rows = [
            r
            for r in activity
            if (r.get("runtime"), r.get("runtime_session_id")) == session
            or any(_key(r) == _key(m) for m in values)
        ]
        launches = [r for r in lifecycle_rows if r["event"] == "launch"]
        exits = [r for r in lifecycle_rows if r["event"] == "exit"]
        if launches and exits and len({r.get("clock_ref") for r in [*launches, *exits]}) == 1:
            a = min(
                (r for r in launches if _number(r.get("monotonic_ns"))),
                key=lambda r: r["monotonic_ns"],
                default=None,
            )
            b = max(
                (r for r in exits if _number(r.get("monotonic_ns"))),
                key=lambda r: r["monotonic_ns"],
                default=None,
            )
            span = _interval(a, b, limits)
            sessions[-1]["launch_to_last_exit_span_seconds"] = (
                (span[2] - span[1]) / 1e9 if span else None
            )
            sessions[-1]["offline_gap_seconds"] = (
                max(0, (span[2] - span[1]) / 1e9 - sessions[-1]["lifecycle_seconds"])
                if span and all(m["lifecycle_seconds"] is not None for m in values)
                else None
            )
    wall = config.get("wall_clock_seconds")
    if wall is None:
        launches = [
            r
            for r in activity
            if r["event"] == "launch" and any(_key(r) == _key(m) for m in members)
        ]
        if launches and all(
            r.get("clock_ref") == cutoff.get("clock_ref") and _number(r.get("monotonic_ns"))
            for r in launches
        ):
            first = min(launches, key=lambda r: r["monotonic_ns"])
            span = _interval(first, cutoff, limits)
            wall = (span[2] - span[1]) / 1e9 if span else None
    closure = (
        "closed"
        if members and all(m["closure_status"] == "closed" for m in members)
        else "incomplete"
        if config.get("cleanup_complete") is False
        else "closing"
        if members
        else "unknown"
    )
    if "member_registration_missing" in limits:
        closure = "unknown"
    if config.get("cleanup_complete") is False:
        closure = "incomplete"
        limits.add("cleanup_incomplete")
    return {
        "schema_version": SCHEMA,
        "view": config.get("view"),
        "closure_status": closure,
        "coverage_status": "partial" if members else "unknown",
        "cutoff_at": config.get("cutoff_at"),
        "summary": summary,
        "summary_time_basis": "cumulative_agent_seconds",
        "team_active_seconds": _union(all_intervals),
        "members": members,
        "groups": groups,
        "task_cutoff_members": task_context_members,
        "sessions": sessions,
        "token_field_coverage": task_usage["field_coverage"],
        "cache_rate_input_coverage": task_usage["cache_rate_input_coverage"],
        "compaction_subset": usage.get("compaction_subset"),
        "cost_summary": usage.get("cost_summary"),
        "estimated_amount": None if not usage.get("cost_summary") else usage["cost_summary"],
        "unallocated_usage": summarize(
            [u for index, u in enumerate(units) if index not in used_units]
        ),
        "unallocated_llm_activity": {
            "counts": unallocated_counts,
            "llm_request_seconds": sum((b - a) / 1e9 for _, a, b in unallocated_intervals)
            if unallocated_intervals
            else None,
            "attribution_status": "unknown",
            "additive_to_agent_time": False,
        },
        "wall_clock_seconds": wall,
        "wall_clock_basis": config.get("wall_clock_basis", "first_registered_launch_to_cutoff"),
        "limitations": sorted(limits),
    }


def render_close_markdown(value):
    def cell(item):
        return "unknown" if item is None else str(item).replace("|", "\\|").replace("\n", " ")

    lines = [
        "",
        "## Team close statistics",
        "",
        f"View: {cell(value['view'])}; closure: {value['closure_status']}; coverage: {value['coverage_status']}.",
        "",
        "| Agent / instance | Runtime / role | Input | Output | LLM seconds | Tool seconds | Active seconds | Lifecycle seconds |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in value["members"]:
        lines.append(
            "| "
            + " | ".join(
                cell(x)
                for x in [
                    f"{m.get('agent_id')} / {m.get('process_instance')}",
                    f"{m.get('runtime')} / {m.get('role')}",
                    m["usage"]["tokens"]["input_tokens"],
                    m["usage"]["tokens"]["output_tokens"],
                    m["llm_request_seconds"],
                    m["tool_execution_seconds"],
                    m["active_seconds"],
                    m["lifecycle_seconds"],
                ]
            )
            + " |"
        )
    lines += [
        "",
        "Totals (known subtotals; cumulative Agent seconds): "
        + cell(json.dumps(value["summary"], sort_keys=True)),
        "",
        "Team observed activity union: " + cell(value["team_active_seconds"]),
        "",
        "LLM time includes transport/queue/streaming; tools include internal waits. Other/uncovered time is not inferred idle time.",
        "",
        "Limitations: " + ", ".join(value["limitations"]),
        "",
    ]
    return "\n".join(lines)


def _json_lines(path):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return []
    result = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise ValueError("registry_truncated")
        result.append(json.loads(line))
    return result


def _inventory(root, *, follow_links=True, limitations=None):
    pending, roots, members = [Path(root).resolve()], set(), []
    while pending:
        current = pending.pop()
        if current in roots:
            continue
        roots.add(current)
        registered = _json_lines(current / CAPTURE_DIRECTORY / "statistics-members.jsonl")
        links = (
            _json_lines(current / CAPTURE_DIRECTORY / "statistics-links.jsonl")
            if follow_links
            else []
        )
        if not registered and not links and limitations is not None:
            limitations.add("member_registration_missing")
        members.extend(registered)
        if follow_links:
            pending.extend(Path(row["root"]) for row in links if row.get("evidence_ref"))
    return members


def read_close_statistics(root):
    """Queries only read the published pointer; never parse logs or start work."""
    try:
        return json.loads((Path(root) / "evidence/close-statistics.json").read_text())
    except (OSError, ValueError):
        return {
            "schema_version": SCHEMA,
            "closure_status": "unknown",
            "report_status": "unavailable",
            "coverage_status": "unknown",
            "limitations": ["close_statistics_not_published"],
        }


def _pointer(root, value):
    path = Path(root) / "evidence/close-statistics.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(".statistics-" + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, sort_keys=True))
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_close_statistics(
    root, *, view, task_ref, cleanup_complete=None, wall_clock_seconds=None
):
    """Called by the original owner after exit/flush and outside control locks."""
    from .usage_report import build_report, render_markdown

    root = Path(root).resolve()
    temporary = None
    previous = read_close_statistics(root)
    try:
        inventory_limits = set()
        members = _inventory(root, limitations=inventory_limits)
        wall_basis = "first_registered_launch_to_cutoff"
        if view == "run_close":
            # The original Host launch ledger is the explicit task/Delivery
            # binding. Read that session's own members only, avoiding task→run cycles.
            try:
                supervisor = json.loads((root / "control/host-supervisor.json").read_text())
            except (OSError, ValueError):
                supervisor = {}
            if supervisor.get("session_ref"):
                session_root = Path(supervisor["session_ref"]).parent
                context_limits = set()
                context_members = _inventory(
                    session_root, follow_links=True, limitations=context_limits
                )
                try:
                    session = json.loads(Path(supervisor["session_ref"]).read_text())
                except (OSError, ValueError):
                    session = {}
                # Actual bindings come from this specific session's ledger.
                # No global workspace enumeration or time-based attribution.
                from .host_ops import HostOpError, resolve_run_root

                for run_id in session.get("run_ids", []):
                    try:
                        linked_root, _ = resolve_run_root(run_id, repository_root=root.parents[2])
                        context_members.extend(_inventory(linked_root, limitations=context_limits))
                    except HostOpError:
                        context_limits.add("member_registration_missing")
                for operation_id in session.get("operation_ids", []):
                    context_members.extend(
                        _inventory(
                            root.parents[2] / ".delivery-ops" / (operation_id + ".owner"),
                            limitations=context_limits,
                        )
                    )
                if context_limits:
                    inventory_limits.add("task_context_registration_missing")
                seen = {_key(m) for m in members}
                for member in context_members:
                    if _key(member) not in seen:
                        seen.add(_key(member))
                        members.append({**member, "scope_member": False})
            if supervisor.get("started_at"):
                try:
                    wall_clock_seconds = max(
                        0,
                        datetime.now(timezone.utc).timestamp()
                        - datetime.fromisoformat(
                            supervisor["started_at"].replace("Z", "+00:00")
                        ).timestamp(),
                    )
                    wall_basis = "original_host_launch_to_close"
                except (ValueError, TypeError):
                    pass
        specs, bindings, frozen = {}, [], {}
        # Freeze exactly the registered prefix; copies make later offline replay
        # independent of mutable runtime files or removed private homes.
        for member in members:
            for source in [
                {"path": member["activity_path"], "kind": "activity"},
                *member.get("usage_sources", []),
            ]:
                path = Path(source["path"])
                sid = hashlib.sha256(
                    (str(path) + source["kind"] + source.get("capture_session_id", "")).encode()
                ).hexdigest()[:24]
                if sid not in specs:
                    try:
                        raw = path.read_bytes()
                    except FileNotFoundError:
                        raw = None
                    frozen[sid] = raw
                    specs[sid] = {
                        "id": sid,
                        "path": "sources/" + sid + ".jsonl",
                        "kind": source["kind"],
                        "byte_length": len(raw) if raw is not None else 0,
                        "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
                        "original_path": str(path),
                    }
                    if source.get("capture_session_id"):
                        specs[sid]["capture_session_id"] = source["capture_session_id"]
                binding = {
                    **({} if source.get("shared") else identity(member)),
                    "source_id": sid,
                    "evidence_ref": str(path) if source.get("shared") else member["activity_path"],
                }
                if source.get("capture_session_id"):
                    binding["session_id"] = source["capture_session_id"]
                # bind events carry the actual native identity; no planned ID is
                # treated as an established session on a failed launch.
                activity_sid = hashlib.sha256(
                    (member["activity_path"] + "activity").encode()
                ).hexdigest()[:24]
                activity_raw = frozen[activity_sid] or b""
                for line in activity_raw.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if _key(event) == _key(member) and event.get("event") == "bind":
                        if not source.get("shared"):
                            binding.update(identity(event))
                        member.update(identity(event))
                if binding not in bindings:
                    bindings.append(binding)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "sources": list(specs.values()),
                    "bindings": bindings,
                    "view": view,
                    "cleanup_complete": cleanup_complete,
                    "calculator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "scope_membership": [
                        {**identity(m), "scope_member": m.get("scope_member", True)}
                        for m in members
                    ],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if (
            previous.get("snapshot_sha256") == fingerprint
            and previous.get("report_status") == "ready"
        ):
            return previous
        cutoff_at, cutoff = utc_now(), clock_stamp()
        for binding in bindings:
            member = next((m for m in members if _key(m) == _key(binding)), {})
            if (
                binding.get("runtime") == "codex"
                and binding.get("thread_id")
                and member.get("fresh_session")
            ):
                binding["cumulative_segment"] = {
                    "id": binding["thread_id"],
                    "evidence_ref": member["activity_path"],
                    "fresh_zero_baseline": True,
                    "start": member["started_at"],
                    "end": cutoff_at,
                }
            binding["task_ref"] = task_ref
        start = min((m["started_at"] for m in members), default=cutoff_at)
        scope = {
            "schema_version": "model-usage-scope/v1",
            "task_ref": task_ref,
            "config_refs": [
                {
                    "kind": "registered_member_bindings",
                    "sha256": hashlib.sha256(
                        json.dumps([identity(m) for m in members], sort_keys=True).encode()
                    ).hexdigest(),
                }
            ],
            "inventory_complete": False,
            "sources": list(specs.values()),
            "bindings": bindings,
            "task_window": {
                "start": start,
                "end": (datetime.fromisoformat(cutoff_at) + timedelta(microseconds=1)).isoformat(),
                "start_source": "registered_runtime_launch",
                "end_source": "owner_close_cutoff",
            },
            "close_statistics": {
                "view": view,
                "cutoff_at": cutoff_at,
                "cutoff_clock": cutoff,
                "limitations": sorted(inventory_limits),
                "members": [
                    {**identity(m), "scope_member": m.get("scope_member", True)} for m in members
                ],
                "cleanup_complete": cleanup_complete,
                "wall_clock_seconds": wall_clock_seconds,
                "wall_clock_basis": wall_basis,
            },
        }
        parent = root / "evidence/close-statistics"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
        (temporary / "sources").mkdir(mode=0o700)
        for sid, raw in frozen.items():
            if raw is not None:
                path = temporary / specs[sid]["path"]
                path.write_bytes(raw)
                path.chmod(0o600)
        (temporary / "scope.json").write_text(json.dumps(scope, sort_keys=True, indent=2))
        report = build_report(scope, base=temporary)
        (temporary / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2))
        (temporary / "report.md").write_text(render_markdown(report))
        for name in ("scope.json", "report.json", "report.md"):
            (temporary / name).chmod(0o600)
        target = parent / ("report-" + fingerprint[:24])
        if target.exists():
            # A prior publication may have completed before its pointer write.
            retained = json.loads((target / "report.json").read_text())
            report = retained
            shutil.rmtree(temporary)
        else:
            temporary.rename(target)
        temporary = None
        close = report["close_statistics"]
        value = {
            k: close[k]
            for k in (
                "schema_version",
                "view",
                "closure_status",
                "coverage_status",
                "cutoff_at",
                "summary",
                "limitations",
            )
        }
        value.update(
            report_status="ready",
            report_ref=str((target / "report.json").relative_to(root)),
            markdown_ref=str((target / "report.md").relative_to(root)),
            scope_ref=str((target / "scope.json").relative_to(root)),
            snapshot_sha256=fingerprint,
        )
        prior_ref = previous.get("report_ref") or previous.get("previous_report_ref")
        if prior_ref:
            value["previous_report_ref"] = prior_ref
        _pointer(root, value)
        return value
    except Exception:
        LOG.warning("close_statistics_report_unavailable")
        value = {
            "schema_version": SCHEMA,
            "view": view,
            "closure_status": "incomplete" if cleanup_complete is False else "unknown",
            "report_status": "unavailable",
            "coverage_status": "unknown",
            "limitations": ["close_statistics_generation_failed"],
        }
        prior_ref = previous.get("report_ref") or previous.get("previous_report_ref")
        if prior_ref:
            value["previous_report_ref"] = prior_ref
        try:
            _pointer(root, value)
        except Exception:
            pass
        return value
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
