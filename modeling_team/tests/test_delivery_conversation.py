import hashlib
import json
import uuid

import pytest

from modeling_team.delivery_conversation import (
    ConversationError, ConversationLog, ConversationServer, project_history, read_events,
    request_socket,
)


def message(text="原始内容\n  第二行", **changes):
    return {"message_id": str(uuid.uuid4()), "kind": "message", "text": text,
            "sender": {"kind": "user", "reference": "u"},
            "submitted_by": {"kind": "host_agent", "reference": "h"},
            "entrypoint": "modeling_dev_loop", **changes}


def log(tmp_path):
    return ConversationLog(tmp_path / "conversation", project_id="p", delivery_session_id="s")


def test_receipt_retries_preserve_identity_payload_and_order(tmp_path):
    ledger = log(tmp_path)
    payload = message()
    first, created = ledger.receive(payload)
    assert created and first["received_seq"] == 2
    ledger.append("dispatch_started", message_id=payload["message_id"], dispatch_attempt_id="a")
    replay, created = ledger.receive(payload)
    assert not created and replay["dispatch"] == "unknown"
    assert replay["text"] == payload["text"]
    with pytest.raises(ConversationError, match="original payload"):
        ledger.receive({**payload, "text": "different"})
    ledger.receive(message())  # Equal text is a distinct deliberate submission.
    assert [e["event_seq"] for e in read_events(ledger.path)["events"]] == [1, 2, 3, 4]


def test_uuid_spellings_share_one_durable_identity_and_question_reference(tmp_path):
    ledger = log(tmp_path)
    payload = message()
    ledger.receive({**payload, "message_id": payload["message_id"].upper()})
    assert ledger.receive(payload)[1] is False
    assert ledger.receive({**payload, "message_id": uuid.UUID(payload["message_id"]).hex})[1] is False
    question = ledger.publish({"kind": "business_question", "text": "确认口径"})
    receipt, _ = ledger.receive(message(kind="answer", reply_to_message_id=question["message_id"].upper()))
    assert receipt["reply_to_message_id"] == question["message_id"]


def test_question_identity_and_resolution_require_explicit_delivery_output(tmp_path):
    ledger = log(tmp_path)
    with pytest.raises(ConversationError):
        ledger.receive(message(kind="answer", reply_to_message_id=str(uuid.uuid4())))
    question = ledger.publish({"kind": "business_question", "text": "退货如何计算？",
                               "question_delivery_id": "original-question"}, "native:call1")
    assert ledger.publish({"kind": "business_question", "text": "retry"}, "native:call1") == question
    ledger.receive(message(kind="answer", reply_to_message_id=question["message_id"]))
    assert len(ledger.snapshot()["pending_questions"]) == 1
    ledger.publish({"kind": "status", "text": "已确认", "resolved_question_ids": [question["message_id"]]})
    assert ledger.snapshot()["pending_questions"] == []


def test_new_history_does_not_import_or_change_old_files_and_resume_preserves_start(tmp_path):
    root = tmp_path / "conversation"
    root.mkdir()
    old = root / "public-messages.jsonl"
    old.write_text('{"text":"OLD_PRIVATE_SENTINEL"}\n')
    digest = hashlib.sha256(old.read_bytes()).hexdigest()
    ledger = log(tmp_path)
    started = ledger.snapshot()["history_started_at"]
    ledger.receive(message())
    restored = log(tmp_path)
    assert restored.snapshot()["history_started_at"] == started
    assert "OLD_PRIVATE_SENTINEL" not in restored.path.read_text()
    assert hashlib.sha256(old.read_bytes()).hexdigest() == digest
    with pytest.raises(ConversationError):
        ConversationLog(root, project_id="other", delivery_session_id="s")


def test_partial_tail_is_preserved_but_middle_corruption_cannot_be_fabricated(tmp_path):
    ledger = log(tmp_path)
    with ledger.path.open("ab") as handle:
        handle.write(b'{"incomplete":')
    assert read_events(ledger.path)["history_complete"] is False
    restored = log(tmp_path)
    assert next(restored.root.glob("incomplete-tail-*.bin")).read_bytes() == b'{"incomplete":'
    assert read_events(restored.path)["history_complete"] is True
    with restored.path.open("ab") as handle:
        handle.write(b'not-json\n')
    assert project_history(read_events(restored.path))["history_complete"] is False
    with pytest.raises(ConversationError, match="inspect the history"):
        log(tmp_path)


def test_real_socket_accepts_once_without_invoking_model_and_checks_binding(tmp_path):
    ledger = log(tmp_path)
    accepted = []
    server = ConversationServer(tmp_path, ledger, accepted.append,
                                lambda: {"native_available": True, "activity": "active"})
    server.start()
    request = {"project_id": "p", "delivery_session_id": "s", "action": "ping"}
    try:
        assert request_socket(server.path, request)["native_available"]
        payload = message()
        request.update(action="submit", message=payload)
        assert request_socket(server.path, request)["created"]
        assert not request_socket(server.path, request)["created"]
        assert accepted == [payload | {"reply_to_message_id": None, "source_reference": None}]
        with pytest.raises(ConversationError):
            request_socket(server.path, request | {"project_id": "other"})
    finally:
        server.close()
    assert not server.path.exists()
    assert read_events(ledger.path)["history_complete"]


@pytest.mark.parametrize("changes", [{"text": " "}, {"text": "x" * 65537},
    {"message_id": "wrong"}, {"kind": "answer"}, {"kind": "control", "action": "exec"},
    {"private_transcript": "CANARY"}])
def test_malformed_messages_are_recoverable_before_acceptance(tmp_path, changes):
    ledger = log(tmp_path)
    with pytest.raises(ConversationError):
        ledger.receive(message(**changes))
    assert len(ledger.events) == 1
    assert ledger.receive(message())[1]
