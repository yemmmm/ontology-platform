"""Program-owned Delivery review windows; no model calls or business judgments."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import json


def _has_control(value):
    if isinstance(value, dict):
        if set(value).intersection({
            "write_state", "mutation_state", "control_epoch", "authorization_reference",
            "review_id", "report_binding", "freeze_id", "pending_actions",
        }):
            return True
        if any(value.get(key) in {"unknown", "blocked", "interrupted"}
               for key in ("status", "state", "outcome") if isinstance(value.get(key), str)):
            return True
        return any(_has_control(item) for item in value.values())
    return isinstance(value, list) and any(_has_control(item) for item in value)


def routine_event(event):
    """Only protocol facts classify events; unfamiliar anomalies stay immediate."""
    if not isinstance(event, dict) or event.get("corrupt") or event.get("truncated"):
        return False
    data, source = event.get("data"), event.get("source", "")
    if not isinstance(data, dict) or not isinstance(source, str) or _has_control(data):
        return False
    if source.startswith(("cq-", "outer-", "terminal-", "settled", "control")):
        return False
    if data.get("category") in {"terminal_report_accepted", "runtime_input_pending"}:
        return False
    if source == "dsh-wire.jsonl":
        frame = data.get("frame")
        params = frame.get("params") if isinstance(frame, dict) else None
        native = params.get("event") if isinstance(params, dict) else None
        if isinstance(native, dict) and native.get("type") == "tool/result":
            # Parameter/tool feedback is recoverable by the calling role. Native
            # activity failures and unknown writes still use the immediate path.
            payload = native.get("data", {})
            message = payload.get("message", {}) if isinstance(payload, dict) else {}
            if isinstance(message, dict):
                retryable = False
                for block in message.get("content") or []:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        try:
                            result = json.loads(block["text"])
                            if _has_control(result):
                                return False
                            error = result.get("error") if isinstance(result, dict) else None
                            retryable = retryable or isinstance(result, dict) and (
                                result.get("retryable") is True or isinstance(error, dict)
                                and error.get("retryable") is True)
                        except ValueError:
                            pass
                return retryable
        return False
    if source in {"app-server-events.jsonl", "provider-attempts.jsonl", "dsh-provider.jsonl",
                  "dsh-handoff.jsonl", "dsh-dispatch.jsonl", "auth-barrier.jsonl"}:
        return False  # known normal envelopes are already filtered by their protocol
    if source == "deliveries.jsonl" and data.get("event") == "delivery-deferred":
        return False
    if source in {"capability-calls.jsonl", "dynamic-tool-calls.jsonl"}:
        if data.get("operation", data.get("tool")) in {
            "modeling_apply_batch", "apply_modeling_batch", "apply_atomic", "protocol_apply_batch",
        }:
            return False  # transport success alone cannot settle a write
        error = data.get("error")
        if data.get("ok") is False or error:
            return data.get("retryable") is True or (
                isinstance(error, dict) and error.get("retryable") is True)
        return True
    if source == "staged-decisions.jsonl":
        return not any(data.get(key) for key in ("error", "diagnostic", "error_type"))
    if source == "team-transport-events.jsonl":
        return data.get("status") in {"queued", "delivered", "accepted"} and not data.get("error")
    # Unknown ordinary records do not all become alarms. A previously unseen
    # diagnostic shape, failed native activity or explicit blocker does.
    def anomaly(value):
        if isinstance(value, list):
            return any(anomaly(item) for item in value)
        if not isinstance(value, dict):
            return False
        return (any(value.get(key) for key in (
            "error", "error_type", "diagnostic", "provider_error", "code", "warning"))
            or value.get("ok") is False
            or any(isinstance(value.get(key), str) and value[key] in {
                "failed", "error", "warning", "blocked", "rejected", "cancelled",
                "pending", "incomplete", "forbidden"}
                for key in ("event", "type", "status", "state", "outcome"))
            or any(anomaly(item) for item in value.values()))
    return not anomaly(data)


class StatusReview:
    def __init__(self, interval, current_time, state=None):
        self.interval = interval
        self.seq = 0
        self.confirmed_seq = 0
        self.next_due_at = (current_time + timedelta(seconds=interval)).isoformat()
        self.next_review_at = None
        self.defer_facts = None
        self.facts = None
        self.sources = {}
        self.confirmed_sources = {}
        self.records = []
        self.seen = {}
        self.inflight = {}
        self.receptions = {}
        self.native_calls = {}
        self.fact_states = {}
        self.runtime = {}
        if state:
            for key, value in state.items():
                if key != "interval":
                    setattr(self, key, deepcopy(value))

    def state(self):
        return {key: deepcopy(getattr(self, key)) for key in (
            "seq", "confirmed_seq", "next_due_at", "next_review_at", "defer_facts",
            "facts", "sources", "confirmed_sources", "seen", "inflight", "runtime", "receptions", "native_calls", "fact_states")}

    def received(self, input_id, window, length, intervals):
        self.receptions.setdefault(input_id, {"window": deepcopy(window), "length": length, "offset": 0})
        self.inflight.setdefault(input_id, []).extend(intervals)

    def complete_reception(self, input_id):
        record = self.receptions[input_id]
        end = record["offset"]
        for start, stop in sorted(self.inflight.pop(input_id, [])):
            if start <= end:
                end = max(end, stop)
        record["offset"] = end
        if end == record["length"]:
            del self.receptions[input_id]
            return record["window"]
        return None

    def due(self, current_time):
        followup = self.next_review_at and current_time >= datetime.fromisoformat(self.next_review_at)
        if followup:
            return "followup_due"
        if current_time < datetime.fromisoformat(self.next_due_at):
            return None
        if self.next_review_at and self.facts == self.defer_facts:
            return None
        return "periodic_review"

    def scheduled(self, current_time):
        self.next_due_at = (current_time + timedelta(seconds=self.interval)).isoformat()
        # An expired followup is a single review, not an every-observation alarm.
        if self.next_review_at and current_time >= datetime.fromisoformat(self.next_review_at):
            self.next_review_at = None

    def defer(self, value):
        if value is not None:
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("next_review_at must be an ISO timestamp with timezone") from exc
            value = stamp.isoformat()
        self.next_review_at = value
        self.defer_facts = self.facts

    def record(self, changes, events, activities, sources, facts, current_time):
        """Keep counts and exact source positions, never another full event history."""
        groups = {}
        limitations = []
        for order, (run_id, event) in enumerate(events):
            if not isinstance(event, dict):
                limitations.append({"code": "event_shape_unknown", "run_id": run_id})
                continue
            source = event.get("source")
            position = event.get("byte_offset")
            if event.get("corrupt") or event.get("truncated"):
                limitations.append({"code": "event_source_incomplete", "run_id": run_id,
                                    "source": source, "byte_offset": position})
            # Only stable original positions deduplicate. Missing positions are
            # disclosed as unknown instead of inventing a source sequence.
            if isinstance(source, str) and type(position) is int:
                stream = run_id + ":" + source
                positions = self.seen.setdefault(stream, [])
                if position in positions:
                    continue
                positions.append(position)
            else:
                limitations.append({"code": "event_position_unknown", "run_id": run_id,
                                    "source": source, "next_action": "inspect the original event source and reconcile its unread range"})
            data = event.get("data")
            if not isinstance(data, dict):
                data = {}
            if source == "dsh-wire.jsonl":
                frame = data.get("frame")
                params = frame.get("params") if isinstance(frame, dict) else None
                native = params.get("event") if isinstance(params, dict) else None
                payload = native.get("data") if isinstance(native, dict) else None
                if isinstance(payload, dict):
                    message = payload.get("message")
                    call_id = payload.get("callId") if native.get("type") == "tool/call" else (
                        message.get("toolCallId") if isinstance(message, dict) else None)
                    key = json.dumps([run_id, data.get("agent_id"), data.get("session_id"),
                                      data.get("process_instance"), call_id])
                    if native.get("type") == "tool/call" and call_id:
                        self.native_calls[key] = payload.get("name", "unknown")
                        data = {**data, "operation": payload.get("name", "unknown")}
                    elif native.get("type") == "tool/result" and isinstance(message, dict):
                        data = {**data, "operation": self.native_calls.pop(key, "unknown"),
                                "ok": not message.get("isError", False),
                                "status": "failed" if message.get("isError") else "completed"}
                        for block in message.get("content") or []:
                            if not isinstance(block, dict) or not isinstance(block.get("text"), str):
                                continue
                            try:
                                value = json.loads(block["text"])
                            except ValueError:
                                continue
                            if isinstance(value, dict) and (value.get("ok") is False or value.get("error")):
                                data.update(ok=False, status="failed", error=value.get("error"))
            actor = data.get("agent_id", data.get("agent", data.get("role", "unknown")))
            operation = data.get("operation", data.get("tool", data.get("method", data.get("event", "unknown"))))
            error = data.get("error")
            code = error.get("code") if isinstance(error, dict) else data.get("code")
            status = data.get("status", data.get("outcome", "failed" if error or data.get("ok") is False else "observed"))
            key = json.dumps([run_id, actor, operation, code, status], sort_keys=True)
            fact_key = json.dumps([run_id, actor, operation])
            if source == "work-board-events.jsonl" and type(data.get("record_seq")) is int:
                self.fact_states["work_board:" + run_id] = data["record_seq"]
            elif error or data.get("ok") is False or code or status in {
                "failed", "error", "blocked", "unknown", "pending", "incomplete", "forbidden"}:
                self.fact_states[fact_key] = {"status": status, "code": code, "ok": data.get("ok")}
            elif fact_key in self.fact_states and data.get("ok") is True:
                self.fact_states[fact_key] = {"status": status, "ok": True}
            ref = {key: event[key] for key in ("source", "byte_offset", "line_no", "recorded_at") if key in event}
            row = groups.setdefault(key, {"run_id": run_id, "actor": actor,
                "operation": operation, "code": code, "status": status, "count": 0,
                "first": ref, "latest": ref})
            row["count"] += 1
            row["latest"] = ref
            row["latest_order"] = [self.seq + 1, order]
            row["failed"] = bool(error or data.get("ok") is False or status in {"failed", "error", "rejected"})
        self.facts = json.dumps([facts, self.fact_states], sort_keys=True)
        self.runtime = deepcopy(activities)
        self.sources.update(deepcopy(sources))
        if not changes and not groups and self.seq:
            return None
        self.seq += 1
        record = {"event": "delivery_review_observation", "seq": self.seq,
            "recorded_at": current_time.isoformat(), "changes": changes,
            "activity": list(groups.values()), "runtime": deepcopy(activities),
            "limitations": limitations}
        self.records.append(record)
        return record

    def summary(self):
        records = [row for row in self.records if self.confirmed_seq < row["seq"] <= self.seq]
        groups, fields, operations = {}, Counter(), {}
        for record in records:
            for change in record["changes"]:
                fields[tuple(change["path"])] += 1
            for row in record["activity"]:
                operation_key = json.dumps([row.get(k) for k in ("run_id", "actor", "operation")])
                operation = operations.setdefault(operation_key, {key: row[key] for key in
                    ("run_id", "actor", "operation")})
                operation["failure_count"] = operation.get("failure_count", 0) + (
                    row["count"] if row.get("failed") else 0)
                if row.get("latest_order", [0, 0]) >= operation.get("latest_order", [0, 0]):
                    operation.update(latest_order=row.get("latest_order"), latest_result={
                        key: row[key] for key in ("status", "code", "latest")})
                key = json.dumps([row.get(k) for k in ("run_id", "actor", "operation", "code", "status")])
                if key not in groups:
                    groups[key] = deepcopy(row)
                else:
                    groups[key]["count"] += row["count"]
                    groups[key]["latest"] = row["latest"]
        limitations = [item for row in records for item in row.get("limitations", [])]
        return {"window": {"after_seq": self.confirmed_seq, "through_seq": self.seq,
                    "complete": not limitations,
                    "after_sources": deepcopy(self.confirmed_sources), "through_sources": deepcopy(self.sources)},
                "changed_fields": [{"path": list(path), "count": count} for path, count in fields.items()],
                "activity": list(groups.values()),
                "retries": [row for row in operations.values() if row["failure_count"]],
                "runtime": deepcopy(self.runtime),
                "coverage": {"observations": len(records), "source_complete": False,
                    "complete": not limitations, "limitations": limitations,
                    "note": "overview only; original events and card versions remain separately readable"}}

    def confirm(self, window):
        if window["through_seq"] < self.confirmed_seq:
            return
        self.confirmed_seq = window["through_seq"]
        self.confirmed_sources = deepcopy(window["through_sources"])
        self.records = [row for row in self.records if row["seq"] > self.confirmed_seq]
