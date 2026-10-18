"""Public Delivery messages and local transport; no model/runtime dependencies."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
MAX_MESSAGE_BYTES = 65536
MAX_WIRE_BYTES = 262144
PUBLIC_KINDS = {"status", "business_question", "decision_request", "final"}
CONTROL_ACTIONS = {"pause", "resume", "cancel", "revoke_budget", "stop"}


def now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status

    def envelope(self) -> dict:
        return {"code": self.code, "message": str(self)}


def validate_session_id(value: str) -> str:
    if not isinstance(value, str) or not SESSION_ID.fullmatch(value):
        raise ConversationError("conversation_not_found", "Select an existing conversation", 404)
    return value


def validate_message(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ConversationError("invalid_message", "Message must be an object", 422)
    fields = {"message_id", "kind", "text", "sender", "entrypoint", "submitted_by",
              "reply_to_message_id", "source_reference", "action"}
    try:
        if set(value) - fields:
            raise ValueError("Unsupported message fields")
        message_id = str(uuid.UUID(value["message_id"]))
        if value["kind"] not in {"message", "answer", "control"}:
            raise ValueError("Unsupported message kind")
        text = value["text"]
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_MESSAGE_BYTES:
            raise ValueError("Supply non-empty text of at most 64 KiB")
        for key in ("sender", "submitted_by"):
            actor = value[key]
            if (not isinstance(actor, dict) or set(actor) != {"kind", "reference"}
                    or actor["kind"] not in {"user", "host_agent", "test_answerer"}
                    or not isinstance(actor["reference"], str) or not actor["reference"]):
                raise ValueError("Supply the actual message source and submitter")
        if value["entrypoint"] not in {"web", "cli", "stdin", "modeling_dev_loop"}:
            raise ValueError("Unsupported entrypoint")
        if value["kind"] == "control":
            if value.get("action") not in CONTROL_ACTIONS:
                raise ValueError("Unsupported control action")
        elif "action" in value:
            raise ValueError("Only control messages have actions")
        if value["kind"] == "answer" and not value.get("reply_to_message_id"):
            raise ValueError("An answer must reference an actual Delivery question")
        for key in ("source_reference", "reply_to_message_id"):
            if value.get(key) is not None and not isinstance(value[key], str):
                raise ValueError("References must be strings")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ConversationError("invalid_message", str(exc), 422) from exc
    reply_to = value.get("reply_to_message_id")
    if reply_to:
        try:
            reply_to = str(uuid.UUID(reply_to))
        except ValueError:
            pass  # Legacy question identities are compared verbatim.
    return {**value, "message_id": message_id, "reply_to_message_id": reply_to,
            "source_reference": value.get("source_reference")}


def payload_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_events(path: Path) -> dict:
    """Read complete committed lines, preserving an explicit incomplete boundary."""
    events = []
    complete, issue = True, None
    try:
        with path.open("rb") as handle:
            for line in handle:
                if not line.endswith(b"\n"):
                    complete, issue = False, "incomplete_tail"
                    break
                try:
                    event = json.loads(line)
                    if (not isinstance(event, dict)
                            or event.get("event_seq") != len(events) + 1
                            or event.get("schema_version") != 1):
                        raise ValueError("invalid event sequence")
                    if events and any(event.get(k) != events[0].get(k)
                                      for k in ("project_id", "delivery_session_id")):
                        raise ValueError("event binding mismatch")
                    events.append(event)
                except (ValueError, UnicodeError):
                    complete, issue = False, "corrupt_event"
                    break
    except FileNotFoundError:
        complete, issue = False, "history_not_started"
    except OSError:
        complete, issue = False, "history_unavailable"
    return {"events": events, "history_complete": complete, "read_error": issue}


def project_history(value: dict) -> dict:
    messages: dict[str, dict] = {}
    resolved: set[str] = set()
    state: dict = {}
    started = None
    for event in value["events"]:
        kind = event["event_type"]
        identity = event.get("message_id")
        if kind == "history_started":
            started = event["recorded_at"]
        elif kind == "message_received":
            messages[identity] = {**event["message"], "received_seq": event["event_seq"],
                                  "recorded_at": event["recorded_at"], "dispatch": "pending"}
        elif kind == "delivery_message":
            messages[identity] = {**event["message"], "message_id": identity,
                                  "received_seq": event["event_seq"],
                                  "recorded_at": event["recorded_at"], "dispatch": "published"}
        elif kind in {"dispatch_started", "dispatch_result", "control_result"} and identity in messages:
            message = messages[identity]
            if kind == "dispatch_started":
                message["dispatch"] = "unknown"
            elif kind == "dispatch_result":
                message["dispatch"] = event["status"]
                message["dispatch_reason"] = event.get("reason")
                if event.get("native_receipt"):
                    message["native_receipt"] = event["native_receipt"]
            else:
                message["control"] = {key: event.get(key) for key in ("action", "status", "basis")}
        elif kind == "native_consumption" and identity in messages:
            messages[identity]["native_receipt"] = event["native_receipt"]
        elif kind == "question_resolved":
            resolved.update(event["question_ids"])
        elif kind == "session_state":
            state = event["state"]
    return {"messages": list(messages.values()), "pending_questions": [
        item for item in messages.values()
        if item["kind"] in {"business_question", "decision_request"}
        and item["message_id"] not in resolved], "history_started_at": started,
        "state": state, "latest_event_seq": len(value["events"]),
        "history_complete": value["history_complete"], "read_error": value["read_error"]}


class ConversationLog:
    def __init__(self, root: Path, *, project_id: str, delivery_session_id: str):
        self.root = Path(root)
        self.project_id = project_id
        self.session_id = validate_session_id(delivery_session_id)
        self.path = self.root / "conversation-events.jsonl"
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        previous = read_events(self.path)
        if previous["read_error"] == "incomplete_tail":
            raw = self.path.read_bytes()
            split = raw.rfind(b"\n") + 1
            (self.root / f"incomplete-tail-{uuid.uuid4().hex}.bin").write_bytes(raw[split:])
            with self.path.open("r+b") as handle:
                handle.truncate(split)
                handle.flush()
                os.fsync(handle.fileno())
            previous = read_events(self.path)
            recovered = True
        else:
            recovered = False
        if previous["read_error"] not in {None, "history_not_started"}:
            raise ConversationError("history_incomplete", "Preserve and inspect the history before writing")
        self.events = previous["events"]
        if self.events:
            first = self.events[0]
            if (first.get("event_type") != "history_started" or first["project_id"] != project_id
                    or first["delivery_session_id"] != self.session_id):
                raise ConversationError("conversation_binding_mismatch", "Keep the original project binding")
        else:
            self.append("history_started")
        if recovered:
            self.append("history_tail_recovered")

    def append(self, event_type: str, **fields) -> dict:
        with self.lock:
            if getattr(self, "write_uncertain", False):
                raise ConversationError("history_incomplete", "Resume the original Host after preserving the incomplete tail", 503)
            event = {"schema_version": 1, "event_seq": len(self.events) + 1,
                     "event_type": event_type, "recorded_at": now(),
                     "project_id": self.project_id, "delivery_session_id": self.session_id, **fields}
            try:
                with self.path.open("ab") as handle:
                    handle.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                # A failed fsync may follow a complete write. Reload the committed prefix so
                # receipt checks and later appends cannot reuse an already-written sequence.
                observed = read_events(self.path)
                self.events = observed["events"]
                self.write_uncertain = not observed["history_complete"]
                raise ConversationError("conversation_write_failed", "Message recording failed; check receipt", 503) from exc
            self.events.append(event)
            return event

    def snapshot(self) -> dict:
        with self.lock:
            return project_history({"events": list(self.events), "history_complete": True, "read_error": None})

    def receipt(self, message_id: str) -> dict | None:
        return next((x for x in self.snapshot()["messages"] if x["message_id"] == message_id), None)

    def receive(self, message: dict) -> tuple[dict, bool]:
        message = validate_message(message)
        with self.lock:
            old = next((e for e in self.events if e["event_type"] == "message_received"
                        and e["message_id"] == message["message_id"]), None)
            digest = payload_digest(message)
            if old:
                if old["payload_digest"] != digest:
                    raise ConversationError("message_identity_conflict", "Keep the original payload for this message ID")
                return self.receipt(message["message_id"]), False
            question_id = message.get("reply_to_message_id")
            if question_id:
                question = self.receipt(question_id)
                if not question or question["kind"] not in {"business_question", "decision_request"}:
                    raise ConversationError("invalid_question_reference", "Select an actual question in this conversation", 422)
            self.append("message_received", message_id=message["message_id"],
                        message=message, payload_digest=digest)
            return self.receipt(message["message_id"]), True

    def publish(self, message: dict, call_identity: str | None = None) -> dict:
        with self.lock:
            if call_identity:
                old = next((e for e in self.events if e["event_type"] == "delivery_message"
                            and e.get("call_identity") == call_identity), None)
                if old:
                    return self.receipt(old["message_id"])
            if message.get("kind") not in PUBLIC_KINDS:
                raise ConversationError("invalid_message", "Only explicit public Delivery messages can be published", 422)
            references = message.get("reply_to_message_ids", [])
            resolved = message.get("resolved_question_ids", [])
            for identity in [*references, *resolved]:
                original = self.receipt(identity)
                if not original or (identity in resolved and original["kind"] not in {"business_question", "decision_request"}):
                    raise ConversationError("invalid_question_reference", "Use actual conversation message IDs", 422)
            identity = str(uuid.uuid4())
            self.append("delivery_message", message_id=identity, call_identity=call_identity,
                        message={**message, "sender": {"kind": "delivery", "reference": self.session_id},
                                 "entrypoint": "delivery", "reply_to_message_ids": references})
            if resolved:
                self.append("question_resolved", message_id=identity, question_ids=resolved)
            return self.receipt(identity)


def socket_path(repository_root: Path, session_id: str) -> Path:
    identity = hashlib.sha256(f"{repository_root.resolve()}:{validate_session_id(session_id)}".encode()).hexdigest()[:32]
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    directory = base / f"ontology-delivery-{os.getuid()}"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    return directory / f"{identity}.sock"


def request_socket(path: Path, request: dict, timeout: float = 3) -> dict:
    raw = (json.dumps(request, ensure_ascii=False) + "\n").encode()
    if len(raw) > MAX_WIRE_BYTES:
        raise ConversationError("invalid_message", "Message envelope too large", 422)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall(raw)
            chunks = b""
            while b"\n" not in chunks:
                part = client.recv(65536)
                if not part or len(chunks) + len(part) > MAX_WIRE_BYTES:
                    raise ConversationError("message_receipt_unknown", "Check the original message ID receipt", 503)
                chunks += part
            response = json.loads(chunks.split(b"\n", 1)[0])
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise ConversationError("delivery_offline", "Resume through the original Host entry before sending") from exc
    except (OSError, ValueError) as exc:
        raise ConversationError("delivery_status_unknown", "Connection not verified; check the original message receipt", 503) from exc
    if not response.get("ok"):
        error = response.get("error", {})
        raise ConversationError(error.get("code", "delivery_status_unknown"), error.get("message", "Request not verified"), response.get("status", 503))
    return response["data"]


class ConversationServer:
    """The existing supervisor owns this socket; the receiver never calls native RPC."""
    def __init__(self, repository_root: Path, log: ConversationLog,
                 enqueue: Callable[[dict], None], status: Callable[[], dict]):
        self.log, self.enqueue, self.status = log, enqueue, status
        self.path = socket_path(repository_root, log.session_id)
        self.instance_id = uuid.uuid4().hex
        self.closed = threading.Event()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.path.unlink(missing_ok=True)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.socket.listen(16)
        self.socket.settimeout(0.2)
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.thread.start()

    def _respond(self, request: dict) -> dict:
        if (request.get("project_id") != self.log.project_id
                or request.get("delivery_session_id") != self.log.session_id):
            raise ConversationError("conversation_binding_mismatch", "Select the bound project and session")
        if request.get("action") == "ping":
            return {"project_id": self.log.project_id, "delivery_session_id": self.log.session_id,
                    "supervisor_instance_id": self.instance_id, "observed_at": now(), **self.status()}
        if request.get("action") != "submit":
            raise ConversationError("invalid_message", "Only ping and submit are supported", 422)
        message = validate_message(request.get("message"))
        # Returning an existing receipt is read-only even while stopping.
        old = self.log.receipt(message["message_id"])
        if not old and self.status().get("activity") in {"stopping", "stopped"}:
            raise ConversationError("delivery_offline", "The conversation is stopping")
        receipt, created = self.log.receive(message)
        if created:
            self.enqueue(message)
        return {"message": receipt, "created": created}

    def _serve(self):
        while not self.closed.is_set():
            try:
                client, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                client.settimeout(2)
                try:
                    raw = b""
                    while b"\n" not in raw:
                        part = client.recv(65536)
                        if not part or len(raw) + len(part) > MAX_WIRE_BYTES:
                            raise ConversationError("invalid_message", "Incomplete or oversized envelope", 422)
                        raw += part
                    response = {"ok": True, "data": self._respond(json.loads(raw.split(b"\n", 1)[0]))}
                except ConversationError as exc:
                    response = {"ok": False, "error": exc.envelope(), "status": exc.status}
                except (OSError, ValueError, TypeError, AttributeError):
                    response = {"ok": False, "error": {"code": "invalid_message", "message": "Invalid request"}, "status": 422}
                try:
                    client.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode())
                except OSError:
                    pass  # Acceptance is durable; the caller must check its stable ID.

    def close(self):
        self.closed.set()
        self.socket.close()
        self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)
