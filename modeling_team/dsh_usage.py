"""DSH's exclusive input buckets and bounded, content-free Messages observation.

Definition evidence: pinned 687f282 llm/types.ts, llm-deepseek/translate.ts.
This adapter definition is not a claim of verified provider billing semantics.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .usage_capture import TOKEN_FIELDS

DSH_SEMANTICS = "dsh-exclusive-input/v1"
DSH_DEFINITION = "dsh:687f282:llm/types.ts+llm-deepseek/translate.ts"
MESSAGES_FIELDS = {
    "input_tokens": "input_tokens",
    "cached_input_tokens": "cache_read_input_tokens",
    "cache_write_tokens": "cache_creation_input_tokens",
    "output_tokens": "output_tokens",
    "reasoning_output_tokens": "reasoning_tokens",
}
NATIVE_FIELDS = dict(
    zip(
        TOKEN_FIELDS,
        ("inputTokens", "cacheReadTokens", "outputTokens", "reasoningTokens", "cacheWriteTokens"),
    )
)


PROJECTION_FIELDS = {**NATIVE_FIELDS, "input_tokens": "uncachedInputTokens"}


def safe_id(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[\w./:@+-]{1,256}", value, re.ASCII)
        else None
    )


def normalize_dsh_usage(raw, kind):
    mapping = (
        MESSAGES_FIELDS
        if kind == "messages"
        else PROJECTION_FIELDS
        if kind == "projection"
        else NATIVE_FIELDS
    )
    usage, invalid = {}, []
    for field, key in mapping.items():
        value = raw.get(key)
        if value is not None and (type(value) is not int or value < 0):
            invalid.append(field)
            value = None
        usage[field] = value
    buckets = [
        usage[field] for field in ("input_tokens", "cached_input_tokens", "cache_write_tokens")
    ]
    usage["input_tokens"] = sum(buckets) if None not in buckets else None
    reasoning, output = usage["reasoning_output_tokens"], usage["output_tokens"]
    if reasoning is not None and output is not None and reasoning > output:
        usage["reasoning_output_tokens"] = None
        invalid.append("reasoning_output_tokens")
    return usage, invalid


class MessagesUsageObserver:
    """Observe complete SSE frames, retaining only bounded identifiers and numbers."""

    def __init__(self, max_event_bytes=262144):
        self.max_event_bytes = max_event_bytes
        self.buffer = bytearray()
        self.lines, self.event_size = [], 0
        self.raw, self.present, self.invalid = {}, set(), set()
        self.issues = set()
        self.positions = {}
        self.event_index = 0
        self.response_id = self.model = None
        self.started = self.stopped = self.final_output = self.disabled = False

    def feed(self, chunk):
        if self.disabled:
            return
        # Split without ever retaining a complete large network chunk.
        for part in chunk.split(b"\n")[:-1]:
            self._line(part, complete=True)
            if self.disabled:
                return
        self._line(chunk.rsplit(b"\n", 1)[-1], complete=False)

    def _line(self, part, *, complete):
        if self.event_size + len(self.buffer) + len(part) > self.max_event_bytes:
            self.issues.add("event_too_large")
            self.buffer.clear()
            self.lines.clear()
            self.disabled = True
            return
        self.buffer.extend(part)
        if not complete:
            return
        line = bytes(self.buffer).removesuffix(b"\r")
        self.buffer.clear()
        self.event_size += len(line) + 1
        if line:
            if line.startswith(b"data:"):
                self.lines.append(line[5:].removeprefix(b" "))
        else:
            if self.lines:
                self._event(b"\n".join(self.lines))
            self.lines.clear()
            self.event_size = 0

    def _event(self, raw):
        self.event_index += 1
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError
            kind = value.get("type")
            if kind == "message_stop":
                self.stopped = True
                return
            if kind not in ("message_start", "message_delta"):
                if kind == "error":
                    self.issues.add("provider_stream_error")
                return
            if self.stopped:
                self.issues.add("usage_after_stop")
                return
            message = value.get("message") if kind == "message_start" else value
            if not isinstance(message, dict):
                raise ValueError
            if kind == "message_start":
                if self.started:
                    self.issues.add("duplicate_message_start")
                self.started = True
                response_id, model = safe_id(message.get("id")), safe_id(message.get("model"))
                if self.response_id and response_id != self.response_id:
                    self.issues.add("response_identity_conflict")
                else:
                    self.response_id = response_id
                self.model = model
            usage = message.get("usage", {})
            if not isinstance(usage, dict):
                raise ValueError
            for key in MESSAGES_FIELDS.values():
                if key not in usage:
                    continue
                self.present.add(key)
                number = usage[key]
                if kind == "message_delta" and key not in ("output_tokens", "reasoning_tokens"):
                    if key not in self.raw or self.raw[key] != number:
                        self.invalid.add(key)
                        self.issues.add("input_outside_start:" + key)
                    continue
                self.positions[key] = self.event_index
                if type(number) is not int or number < 0:
                    self.invalid.add(key)
                    self.issues.add("invalid_usage:" + key)
                elif key in self.raw and number < self.raw[key]:
                    self.invalid.add(key)
                    self.issues.add("usage_decreased:" + key)
                else:
                    self.raw[key] = number
                if key == "output_tokens" and kind == "message_delta":
                    self.final_output = True
        except (ValueError, UnicodeError, TypeError):
            self.issues.add("invalid_sse_event")

    def finish(self):
        if self.buffer or self.lines:
            self.issues.add("truncated_sse_event")
        if not self.started:
            self.issues.add("message_start_missing")
        if not self.stopped:
            self.issues.add("message_stop_missing")
        if not self.final_output:
            self.issues.add("final_output_missing")
        raw = {
            key: self.raw.get(key) if key not in self.invalid else None
            for key in MESSAGES_FIELDS.values()
        }
        if not self.final_output:
            raw["output_tokens"] = None
        complete = not self.issues and all(
            raw[key] is not None
            for key in (
                "input_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
                "output_tokens",
            )
        )
        return dict(
            raw_usage=raw,
            present_fields=sorted(self.present),
            usage_issues=sorted(self.issues),
            field_positions=self.positions,
            response_id=self.response_id,
            actual_model=self.model,
            usage_complete=complete,
            message_stop=self.stopped,
            usage_semantics=DSH_SEMANTICS,
            adapter_definition_ref=DSH_DEFINITION,
        )


def native_numeric_event(value, session_id=None):
    """Project durable/session.event records before any report can retain text."""
    process_instance = value.get("process_instance")
    frame = value.get("frame", value)
    if frame.get("method") == "session.event":
        params = frame.get("params") or {}
        session_id = params.get("sessionId")
        value = params.get("event") or {}
    kind = value.get("type")
    if kind not in (
        "assistant/message",
        "assistant/attempt",
        "llm/retry-started",
        "compaction/summary",
    ):
        return None
    data = value.get("data") or {}
    raw = data.get("usage")
    if raw is None:
        for part in data.get("stream", []):
            chunk = part.get("chunk", part)
            if chunk.get("type") == "usage":
                raw = chunk.get("usage")
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("invalid native usage")
    raw = {key: raw[key] for key in NATIVE_FIELDS.values() if key in (raw or {})}
    # Native translator defaults cannot establish provider field presence.
    usage, invalid = normalize_dsh_usage(raw, "native")
    timestamp = value.get("timestamp")
    if timestamp is None and type(value.get("time")) in (int, float):
        timestamp = datetime.fromtimestamp(value["time"] / 1000, timezone.utc).isoformat()
    return dict(
        runtime="dsh",
        runtime_session_id=session_id,
        timestamp=timestamp,
        process_instance=process_instance,
        native_type=kind,
        native_seq=value.get("seq"),
        native_turn=data.get("turn"),
        native_step=data.get("step"),
        raw_usage={
            key: number if type(number) is int and number >= 0 else None
            for key, number in raw.items()
        },
        usage=usage,
        invalid_fields=invalid,
        usage_semantics=DSH_SEMANTICS,
    )
