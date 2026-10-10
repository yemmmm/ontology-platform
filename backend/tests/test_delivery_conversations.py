import json
import uuid

import pytest

from app.api.delivery_conversations import get_conversations_service
from app.services.delivery_conversations import DeliveryConversationsService, ConversationError, io


def setup(root, project="p", session="s"):
    directory = root / "workspaces/delivery-sessions" / session
    directory.mkdir(parents=True)
    (directory / "session.json").write_text(json.dumps({"session_id": session, "project_id": project,
        "supervisor_pid": 1, "state": "active", "credentials": "PRIVATE_SENTINEL"}))
    (directory / "private-transcript.json").write_text("PRIVATE_SENTINEL")
    log = io.ConversationLog(directory, project_id=project, delivery_session_id=session)
    return DeliveryConversationsService(root), log


def envelope(text="message", **changes):
    return {"message_id": str(uuid.uuid4()), "kind": "message", "text": text,
            "sender": {"kind": "user", "reference": "u"},
            "submitted_by": {"kind": "user", "reference": "u"}, "entrypoint": "web", **changes}


def test_offline_history_is_readable_without_pid_or_state_online_claim(tmp_path):
    service, log = setup(tmp_path)
    question = log.publish({"kind": "business_question", "text": "Question"})
    detail = service.detail("p", "s")
    assert detail["connection"] == "offline"  # PID 1 and persisted active are not proof.
    assert detail["pending_questions"][0]["message_id"] == question["message_id"]
    assert "PRIVATE_SENTINEL" not in json.dumps(detail)
    with pytest.raises(ConversationError) as error:
        service.submit("p", "s", envelope())
    assert error.value.code == "delivery_offline"
    assert len(log.events) == 2
    with pytest.raises(ConversationError):
        service.detail("other", "s")
    with pytest.raises(ConversationError):
        service.detail("p", "../s")


def test_retry_known_identity_is_read_only_offline_and_unknown_receipt_is_not_absence(tmp_path):
    service, log = setup(tmp_path)
    message = envelope()
    log.receive(message)
    log.append("dispatch_started", message_id=message["message_id"], dispatch_attempt_id="a")
    result = service.submit("p", "s", message)
    assert not result["created"] and result["message"]["dispatch"] == "unknown"
    with pytest.raises(ConversationError) as error:
        service.submit("p", "s", {**message, "text": "changed"})
    assert error.value.code == "message_identity_conflict"
    with log.path.open("ab") as handle:
        handle.write(b"bad\n")
    with pytest.raises(ConversationError) as error:
        service.receipt("p", "s", str(uuid.uuid4()))
    assert error.value.code == "message_receipt_unknown"


def test_pagination_and_corrupt_enumeration_do_not_claim_completeness(tmp_path):
    service, log = setup(tmp_path)
    for _ in range(5):
        log.receive(envelope())
    first = service.events("p", "s", 0, 2)
    assert first["next_after_seq"] == 2 and first["has_more"]
    last = service.events("p", "s", 2, 100)
    assert len(last["items"]) == 4 and not last["has_more"]
    other = tmp_path / "workspaces/delivery-sessions/broken"
    other.mkdir()
    (other / "session.json").write_text("bad")
    index = service.list("p")
    assert not index["enumeration_complete"]
    assert [x["delivery_session_id"] for x in index["items"]] == ["s"]


def test_http_read_scope_can_send_and_read_on_same_online_socket(tmp_path, r008_client):
    client = r008_client["client"]
    project = r008_client["ids"]["p1"]
    service, log = setup(tmp_path, project)
    accepted = []
    server = io.ConversationServer(tmp_path, log, accepted.append,
                                    lambda: {"native_available": True, "activity": "active"})
    server.start()
    client.app.dependency_overrides[get_conversations_service] = lambda: service
    headers = {"Authorization": "Bearer " + r008_client["p1_read_key"]}
    base = f"/api/projects/{project}/delivery-conversations"
    body = {"message_id": str(uuid.uuid4()), "kind": "control", "action": "pause", "text": "先暂停"}
    try:
        assert client.get(base, headers=headers).status_code == 200
        assert client.get(base + "/s", headers=headers).json()["connection"] == "online"
        response = client.post(base + "/s/messages", headers=headers, json=body)
        assert response.status_code == 202, response.text
        assert client.post(base + "/s/messages", headers=headers, json=body).status_code == 200
        assert len(accepted) == 1 and accepted[0]["action"] == "pause"
        assert accepted[0]["entrypoint"] == "web"
        assert client.get(base + "/s/events?limit=1", headers=headers).json()["has_more"]
        assert client.get(base + "/s/events?limit=201", headers=headers).status_code == 422
        assert client.post(base + "/s/messages", headers=headers,
                           json={**body, "sender": {"kind": "host_agent"}}).status_code == 422
        assert "PRIVATE_SENTINEL" not in client.get(base + "/s/events", headers=headers).text
        assert client.get(f"/api/projects/{r008_client['ids']['p2']}/delivery-conversations",
                          headers=headers).status_code == 403
    finally:
        server.close()
    assert client.get(base + "/s", headers=headers).json()["connection"] == "offline"
    assert client.post(base + "/s/messages", headers=headers, json=body).status_code == 200
