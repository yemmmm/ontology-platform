"""Non-inference local clients for the existing Delivery conversation owner."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from .delivery_conversation import (ConversationError, payload_digest, project_history,
                                    read_events, request_socket, socket_path, validate_message,
                                    validate_session_id)


def execute(args, repository_root: Path) -> dict:
    session_id = validate_session_id(args.session_id)
    root = repository_root / "workspaces/delivery-sessions" / session_id
    if root.is_symlink() or not root.is_dir():
        raise ConversationError("conversation_not_found", "Delivery session not found", 404)
    binding = json.loads((root / "session.json").read_text())
    if binding.get("project_id") != args.project_id:
        raise ConversationError("conversation_not_found", "Delivery project binding differs", 404)
    history = read_events(root / "conversation-events.jsonl")
    projected = project_history(history)
    wire_binding = {"project_id": args.project_id, "delivery_session_id": session_id}
    if args.conversation_action == "history":
        return projected
    if args.conversation_action == "status":
        try:
            online = request_socket(socket_path(repository_root, session_id), {"action": "ping", **wire_binding})
        except ConversationError as exc:
            online = {"connection": "offline", "reason": exc.code}
        return {**online, "state": projected["state"], "history_complete": history["history_complete"]}
    if bool(args.text is not None) == bool(args.message_file is not None):
        raise ConversationError("invalid_message", "Supply either --text or --message-file", 422)
    actor = {"kind": args.sender_kind, "reference": args.sender_reference}
    submitted = {"kind": "host_agent", "reference": args.submitted_by}
    message = {"message_id": args.message_id or str(uuid.uuid4()), "kind": args.kind,
               "text": args.text if args.text is not None else args.message_file.read_text(),
               "sender": actor, "submitted_by": submitted, "entrypoint": "cli",
               "source_reference": args.source_reference,
               "reply_to_message_id": args.reply_to_message_id}
    if args.control_action:
        message["action"] = args.control_action
    message = validate_message(message)
    previous = next((e for e in history["events"] if e.get("event_type") == "message_received"
                     and e.get("message_id") == message["message_id"]), None)
    if previous:
        if previous["payload_digest"] != payload_digest(message):
            raise ConversationError("message_identity_conflict", "Keep original message payload", 409)
        return {"message_id": message["message_id"], "receipt": next(
            m for m in projected["messages"] if m["message_id"] == message["message_id"]), "duplicate": True}
    try:
        return request_socket(socket_path(repository_root, session_id), {"action": "submit", "message": message, **wire_binding})
    except ConversationError as exc:
        return {"message_id": message["message_id"], "status": "offline" if exc.code == "delivery_offline" else "unknown",
                "error": exc.code, "next_action": "read history; retry only with this original ID and payload"}
