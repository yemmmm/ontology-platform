"""Read public conversation files and proxy to the existing local supervisor."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# Load only the stdlib wire/log module; importing modeling_team would also load
# its Runner and model dependencies into the HTTP application.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "delivery_conversation_io", REPOSITORY_ROOT / "modeling_team/delivery_conversation.py"
)
io = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(io)
ConversationError = io.ConversationError

MESSAGE_FIELDS = {
    "message_id", "kind", "text", "sender", "entrypoint", "submitted_by",
    "reply_to_message_id", "reply_to_message_ids", "resolved_question_ids",
    "source_reference", "action", "question_delivery_id", "received_seq", "recorded_at",
    "dispatch", "dispatch_reason", "control",
}
EVENT_FIELDS = {"schema_version", "event_seq", "event_type", "recorded_at", "project_id",
                "delivery_session_id", "message_id", "dispatch_attempt_id", "status", "reason",
                "action", "basis", "question_ids", "state", "message"}


def public_message(message: dict) -> dict:
    return {key: value for key, value in message.items() if key in MESSAGE_FIELDS}


def public_event(event: dict) -> dict:
    result = {key: value for key, value in event.items() if key in EVENT_FIELDS}
    if "message" in result:
        result["message"] = public_message(result["message"])
    return result


class DeliveryConversationsService:
    def __init__(self, repository_root: Path = REPOSITORY_ROOT):
        self.repository_root = Path(repository_root).resolve()
        self.root = self.repository_root / "workspaces/delivery-sessions"

    def _session(self, project_id: str, session_id: str) -> tuple[Path, dict]:
        io.validate_session_id(session_id)
        root = self.root / session_id
        try:
            if root.is_symlink() or not root.is_dir():
                raise ValueError("invalid session directory")
            record = json.loads((root / "session.json").read_text())
            if record.get("project_id") != project_id or record.get("session_id") != session_id:
                raise ValueError("binding mismatch")
        except (OSError, ValueError, AttributeError) as exc:
            raise ConversationError("conversation_not_found", "Select a conversation bound to this project", 404) from exc
        return root, record

    def _history(self, project_id: str, session_id: str) -> dict:
        root, _ = self._session(project_id, session_id)
        history = io.read_events(root / "conversation-events.jsonl")
        if history["events"] and (history["events"][0]["project_id"] != project_id
                                   or history["events"][0]["delivery_session_id"] != session_id):
            raise ConversationError("history_incomplete", "Conversation history binding needs verification", 503)
        return history

    def list(self, project_id: str) -> dict:
        items, issues = [], []
        if not self.root.exists():
            return {"items": [], "enumeration_complete": True, "read_errors": []}
        try:
            directories = sorted(self.root.iterdir())
        except OSError:
            return {"items": [], "enumeration_complete": False,
                    "read_errors": [{"code": "session_enumeration_unavailable"}]}
        for directory in directories:
            if directory.name.startswith(".") or not directory.is_dir():
                continue
            try:
                io.validate_session_id(directory.name)
                record = json.loads((directory / "session.json").read_text())
                if record.get("project_id") != project_id:
                    continue  # Unbound legacy sessions are not guessed or migrated by HTTP.
                history = self._history(project_id, directory.name)
                view = io.project_history(history)
                items.append({"delivery_session_id": directory.name,
                              "history_started_at": view["history_started_at"],
                              "last_updated_at": history["events"][-1]["recorded_at"] if history["events"] else None,
                              "history_complete": view["history_complete"]})
                if not view["history_complete"]:
                    issues.append({"delivery_session_id": directory.name, "code": view["read_error"]})
            except (OSError, ValueError, AttributeError, KeyError):
                issues.append({"delivery_session_id": directory.name, "code": "session_unavailable"})
        return {"items": items, "enumeration_complete": not issues, "read_errors": issues}

    def detail(self, project_id: str, session_id: str) -> dict:
        view = io.project_history(self._history(project_id, session_id))
        state = view["state"]
        result = {"delivery_session_id": session_id, "connection": "offline",
                  "activity": state.get("activity", "interrupted"),
                  "observed_at": state.get("observed_at"), "basis": state.get("basis"),
                  "delivery_result": state.get("delivery_result"),
                  "history_started_at": view["history_started_at"],
                  "pending_questions": [public_message(x) for x in view["pending_questions"]],
                  "latest_event_seq": view["latest_event_seq"],
                  "history_complete": view["history_complete"], "read_error": view["read_error"]}
        try:
            ping = io.request_socket(io.socket_path(self.repository_root, session_id), {
                "action": "ping", "project_id": project_id, "delivery_session_id": session_id,
            }, timeout=1)
            if ping["project_id"] != project_id or ping["delivery_session_id"] != session_id:
                raise ConversationError("delivery_status_unknown", "Endpoint identity not verified", 503)
            result.update(connection="online" if ping.get("native_available") else "offline",
                          activity=ping.get("activity", "interrupted"),
                          observed_at=ping["observed_at"], basis="supervisor_ping")
        except ConversationError as exc:
            if exc.code != "delivery_offline":
                result["connection"] = "unknown"
            result["connection_error"] = exc.code
        return result

    def events(self, project_id: str, session_id: str, after_seq: int, limit: int) -> dict:
        history = self._history(project_id, session_id)
        selected = [e for e in history["events"] if e["event_seq"] > after_seq][:limit]
        cursor = selected[-1]["event_seq"] if selected else after_seq
        return {"items": [public_event(e) for e in selected], "next_after_seq": cursor,
                "has_more": any(e["event_seq"] > cursor for e in history["events"]),
                "history_complete": history["history_complete"], "read_error": history["read_error"]}

    def receipt(self, project_id: str, session_id: str, message_id: str) -> dict:
        view = io.project_history(self._history(project_id, session_id))
        found = next((m for m in view["messages"] if m["message_id"] == message_id), None)
        if found:
            return public_message(found)
        if not view["history_complete"]:
            raise ConversationError("message_receipt_unknown", "History incomplete; acceptance cannot be ruled out", 503)
        raise ConversationError("message_not_found", "No received message with this ID", 404)

    def submit(self, project_id: str, session_id: str, message: dict) -> dict:
        message = io.validate_message(message)
        history = self._history(project_id, session_id)
        prior = next((e for e in history["events"] if e["event_type"] == "message_received"
                      and e["message_id"] == message["message_id"]), None)
        if prior:
            if prior["payload_digest"] != io.payload_digest(message):
                raise ConversationError("message_identity_conflict", "Keep the original message payload")
            return {"message": self.receipt(project_id, session_id, message["message_id"]), "created": False}
        if not history["history_complete"]:
            raise ConversationError("history_incomplete", "Verify history before accepting a new message", 503)
        status = self.detail(project_id, session_id)
        if status["connection"] != "online":
            raise ConversationError("delivery_offline" if status["connection"] == "offline" else "delivery_status_unknown",
                                    "Resume or verify the original Delivery before sending",
                                    409 if status["connection"] == "offline" else 503)
        result = io.request_socket(io.socket_path(self.repository_root, session_id), {
            "action": "submit", "project_id": project_id, "delivery_session_id": session_id,
            "message": message,
        })
        result["message"] = public_message(result["message"])
        return result
