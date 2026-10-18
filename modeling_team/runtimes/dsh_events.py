"""Fold original DSH facts without treating enqueue/idle/text as business completion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DispatchProjection:
    session_id: str
    events: dict[int, dict] = field(default_factory=dict)
    messages: dict[str, dict] = field(default_factory=dict)
    inbox: dict[str, list[str]] = field(default_factory=lambda: {"next-turn": [], "next-step": []})
    next_seq: int = 0
    activity: int | None = None
    gap: bool = False
    conflict: bool = False

    def append(self, event: dict) -> bool:
        seq = event["seq"]
        if seq in self.events:
            if self.events[seq] != event:
                self.conflict = True
            return False
        self.events[seq] = event
        while self.next_seq in self.events:
            value = self.events[self.next_seq]
            self._fold(value)
            self.next_seq += 1
        self.gap = any(seq >= self.next_seq for seq in self.events)
        return True

    def _fold(self, event: dict) -> None:
        kind, data, seq = event["type"], event["data"], event["seq"]
        if kind == "turn/start":
            self.activity = seq
        elif kind == "agent/inbox/spliced":
            pending = self.inbox[data["target"]]
            start = data["start"]
            removed = pending[start : start + data.get("removedCount", 0)]
            inserted = [message["id"] for message in data["inserted"]]
            pending[start : start + data.get("removedCount", 0)] = inserted
            for identity in inserted:
                self.messages[identity] = {
                    "message_id": identity,
                    "state": "queued",
                    "queued_seq": seq,
                }
            for identity in removed:
                if identity in inserted:
                    continue
                record = self.messages[identity]
                if data.get("outcome") == "canceled":
                    record.update(state="canceled", removed_seq=seq)
                elif self.activity is not None:
                    record.update(state="claimed", claimed_seq=seq, turn_start_seq=self.activity)
                else:
                    record.update(state="unknown", removed_seq=seq)
        elif kind == "turn/end":
            for record in self.messages.values():
                if record["state"] == "claimed" and record.get("turn_start_seq") == self.activity:
                    record.update(state="settled", turn_end_seq=seq, reason=data["reason"])
            self.activity = None

    def status(self, message_id: str) -> dict[str, Any]:
        record = dict(self.messages.get(message_id, {"message_id": message_id, "state": "unknown"}))
        if self.gap or self.conflict:
            record.update(
                state="unknown",
                reason="event-sequence-conflict" if self.conflict else "event-sequence-gap",
            )
        return record
