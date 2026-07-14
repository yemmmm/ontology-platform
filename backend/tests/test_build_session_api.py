"""R-003 REST coverage for Project build sessions and Ontology leases."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.build_sessions import router
from app.api.deps import get_db_session
from app.core.config import Settings
from app.repositories.models import (
    EvidenceReferenceModel,
    OntologyLeaseModel,
    OntologyModel,
    ProjectBriefModel,
    ProjectModel,
)
from app.services.ontology_workspace import OntologyWorkspaceService


PROJECT_ID = "project-build-session"
OTHER_PROJECT_ID = "project-build-session-other"
ONTOLOGY_ID = "ontology-build-session"
SECOND_ONTOLOGY_ID = "ontology-build-session-second"
OTHER_ONTOLOGY_ID = "ontology-build-session-other"


def _settings() -> Settings:
    return Settings(
        semantic_graph_iri_prefix="https://internal.example/graphs/",
        build_session_lease_ttl_seconds=300,
    )


def _seed_scope(session: Session) -> None:
    session.add_all(
        [
            ProjectModel(
                id=PROJECT_ID,
                name="Build Session project",
                normalized_label="build session project",
            ),
            ProjectModel(
                id=OTHER_PROJECT_ID,
                name="Other Build Session project",
                normalized_label="other build session project",
            ),
        ]
    )
    session.flush()
    ontologies = [
        OntologyModel(
            id=ONTOLOGY_ID,
            project_id=PROJECT_ID,
            name="Primary ontology",
        ),
        OntologyModel(
            id=SECOND_ONTOLOGY_ID,
            project_id=PROJECT_ID,
            name="Second ontology",
        ),
        OntologyModel(
            id=OTHER_ONTOLOGY_ID,
            project_id=OTHER_PROJECT_ID,
            name="Foreign ontology",
        ),
    ]
    session.add_all(ontologies)
    session.flush()
    workspace_service = OntologyWorkspaceService(session, _settings())
    for ontology in ontologies:
        workspace_service.ensure(ontology)
    session.add_all(
        [
            ProjectBriefModel(
                id="brief-build-session",
                project_id=PROJECT_ID,
                content={"business_goal": "Recover external Agent work"},
                field_states={"business_goal": "confirmed"},
                field_sources={},
            ),
            EvidenceReferenceModel(
                id="evidence-build-session",
                project_id=PROJECT_ID,
                document_name="Requirements.md",
                normalized_document_name="Requirements.md",
                excerpt="Build Sessions are project-scoped.",
                excerpt_hash="e" * 64,
            ),
        ]
    )
    session.commit()


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.state.settings = _settings()
    app.include_router(router, prefix="/api")

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


@pytest.fixture()
def build_client(in_memory_session: Session) -> tuple[TestClient, Session]:
    _seed_scope(in_memory_session)
    return _client(in_memory_session), in_memory_session


def _create_session(
    client: TestClient,
    *,
    project_id: str = PROJECT_ID,
    client_session_id: str = "agent-run-001",
    previous_session_id: str | None = None,
    initial_checkpoint: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    payload: dict[str, Any] = {
        "client_session_id": client_session_id,
        "previous_session_id": previous_session_id,
    }
    if initial_checkpoint is not None:
        payload["initial_checkpoint"] = initial_checkpoint
    response = client.post(f"/api/projects/{project_id}/build-sessions", json=payload)
    body = response.json()
    return response, body.get("session", body)


def _error_code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _assert_no_internal_graph_or_token(value: Any) -> None:
    """Recursively prove ordinary recovery payloads do not expose internals."""
    forbidden_key_parts = ("graph_set", "graph_iri", "lease_token", "token_hash")
    if isinstance(value, dict):
        for key, child in value.items():
            assert not any(part in key.lower() for part in forbidden_key_parts), key
            _assert_no_internal_graph_or_token(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_internal_graph_or_token(child)
    elif isinstance(value, str):
        assert "https://internal.example/graphs/" not in value


def test_create_is_idempotent_and_rejects_payload_reuse(build_client) -> None:
    client, _session = build_client
    first, first_session = _create_session(client)
    retry, retry_session = _create_session(client)

    assert first.status_code == 201, first.text
    assert retry.status_code == 200, retry.text
    assert retry_session["id"] == first_session["id"]
    assert retry_session["revision"] == first_session["revision"] == 1

    changed, _ = _create_session(
        client,
        initial_checkpoint={
            "client_checkpoint_id": "unexpected-cp",
            "phase": "intake",
            "current_step": "This was not part of the original request",
            "blockers": [],
        },
    )
    assert changed.status_code == 409
    assert _error_code(changed) == "idempotency_conflict"


def test_checkpoint_retry_precedes_revision_check_and_resume_does_not_increment(
    build_client,
) -> None:
    client, _session = build_client
    _created, session = _create_session(client)
    session_id = session["id"]
    checkpoint = {
        "client_checkpoint_id": "cp-001",
        "expected_revision": 1,
        "phase": "modeling",
        "current_step": "Model the first ontology",
        "next_step": "Verify the model",
        "ontology_id": ONTOLOGY_ID,
        "summary": "Drafted the schema",
        "blockers": [],
        "failure": None,
    }

    first = client.post(
        f"/api/build-sessions/{session_id}/checkpoints", json=checkpoint
    )
    retry = client.post(
        f"/api/build-sessions/{session_id}/checkpoints", json=checkpoint
    )
    assert first.status_code == retry.status_code == 200
    assert retry.json()["checkpoint"]["id"] == first.json()["checkpoint"]["id"]
    assert first.json()["session"]["revision"] == 2

    stale = client.post(
        f"/api/build-sessions/{session_id}/checkpoints",
        json={
            **checkpoint,
            "client_checkpoint_id": "cp-002",
            "current_step": "A competing update",
        },
    )
    assert stale.status_code == 409
    assert _error_code(stale) == "session_revision_conflict"
    assert stale.json()["detail"]["current_revision"] == 2

    resume = client.post(
        f"/api/build-sessions/{session_id}:resume",
        json={"client_request_id": "resume-001", "expected_revision": 2},
    )
    resume_retry = client.post(
        f"/api/build-sessions/{session_id}:resume",
        json={"client_request_id": "resume-001", "expected_revision": 2},
    )
    assert resume.status_code == resume_retry.status_code == 200
    assert resume.json()["session"]["revision"] == 2
    assert resume_retry.json()["session"]["revision"] == 2
    assert resume.json()["latest_checkpoint"]["client_checkpoint_id"] == "cp-001"


def test_cross_project_resources_are_hidden(build_client) -> None:
    client, _session = build_client
    _created, local_session = _create_session(client)
    _other_created, foreign_session = _create_session(
        client,
        project_id=OTHER_PROJECT_ID,
        client_session_id="foreign-session",
    )

    checkpoint = client.post(
        f"/api/build-sessions/{local_session['id']}/checkpoints",
        json={
            "client_checkpoint_id": "cp-cross-project",
            "expected_revision": 1,
            "phase": "modeling",
            "current_step": "Attempt a foreign Ontology",
            "ontology_id": OTHER_ONTOLOGY_ID,
            "blockers": [],
        },
    )
    assert checkpoint.status_code == 404
    assert _error_code(checkpoint) == "ontology_not_found"

    previous, _ = _create_session(
        client,
        client_session_id="invalid-predecessor",
        previous_session_id=foreign_session["id"],
    )
    assert previous.status_code == 404
    assert _error_code(previous) == "build_session_not_found"


def test_lease_acquire_conflict_renew_release_and_expiry(build_client) -> None:
    client, db_session = build_client
    _created, first_session = _create_session(client, client_session_id="lease-owner")
    _created, second_session = _create_session(client, client_session_id="lease-contender")

    acquire = client.post(
        f"/api/build-sessions/{first_session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": "acquire-001",
            "expected_session_revision": 1,
            "rotate_token": False,
        },
    )
    assert acquire.status_code == 200, acquire.text
    lease = acquire.json()
    assert lease["lease_token"]
    assert lease["lease_revision"] == 1
    assert "graph_set_id" not in lease
    assert "graph_iri" not in lease

    conflict = client.post(
        f"/api/build-sessions/{second_session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": "acquire-002",
            "expected_session_revision": 1,
            "rotate_token": False,
        },
    )
    assert conflict.status_code == 409
    assert _error_code(conflict) == "ontology_lease_conflict"
    assert "lease_token" not in conflict.text

    renewed = client.post(
        f"/api/build-sessions/{first_session['id']}/ontology-leases/{ONTOLOGY_ID}:renew",
        json={
            "client_request_id": "renew-001",
            "lease_token": lease["lease_token"],
            "expected_lease_revision": 1,
        },
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["lease_revision"] == 2
    assert renewed.json()["lease_token"]

    released = client.post(
        f"/api/build-sessions/{first_session['id']}/ontology-leases/{ONTOLOGY_ID}:release",
        json={
            "client_request_id": "release-001",
            "lease_token": renewed.json()["lease_token"],
            "expected_lease_revision": 2,
        },
    )
    assert released.status_code == 200, released.text
    assert released.json()["released"] is True
    assert "lease_token" not in released.json()

    after_release = client.post(
        f"/api/build-sessions/{second_session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": "acquire-after-release",
            "expected_session_revision": 1,
            "rotate_token": False,
        },
    )
    assert after_release.status_code == 200, after_release.text

    row = db_session.get(OntologyLeaseModel, ONTOLOGY_ID)
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    reacquire = client.post(
        f"/api/build-sessions/{first_session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": "acquire-after-expiry",
            "expected_session_revision": 1,
            "rotate_token": False,
        },
    )
    assert reacquire.status_code == 200, reacquire.text
    assert reacquire.json()["lease_token"] != after_release.json()["lease_token"]
    assert reacquire.json()["lease_revision"] > after_release.json()["lease_revision"]


@pytest.mark.parametrize("terminal_action", ["complete", "cancel"])
def test_terminal_action_releases_all_leases_and_blocks_resume(
    build_client, terminal_action: str
) -> None:
    client, _session = build_client
    _created, session = _create_session(
        client, client_session_id=f"terminal-{terminal_action}"
    )
    session_id = session["id"]
    for index, ontology_id in enumerate((ONTOLOGY_ID, SECOND_ONTOLOGY_ID), start=1):
        acquired = client.post(
            f"/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire",
            json={
                "client_request_id": f"acquire-terminal-{index}",
                "expected_session_revision": 1,
                "rotate_token": False,
            },
        )
        assert acquired.status_code == 200, acquired.text

    if terminal_action == "complete":
        payload = {
            "client_request_id": "complete-001",
            "expected_revision": 1,
            "summary": "Completed the scoped modeling work",
            "unresolved_items": ["Publication was intentionally deferred"],
        }
    else:
        payload = {
            "client_request_id": "cancel-001",
            "expected_revision": 1,
            "reason": "User stopped the run",
        }
    terminal = client.post(
        f"/api/build-sessions/{session_id}:{terminal_action}", json=payload
    )
    assert terminal.status_code == 200, terminal.text
    assert terminal.json()["status"] == (
        "completed" if terminal_action == "complete" else "cancelled"
    )

    resume = client.post(
        f"/api/build-sessions/{session_id}:resume",
        json={
            "client_request_id": "resume-after-terminal",
            "expected_revision": terminal.json()["revision"],
        },
    )
    assert resume.status_code == 409
    assert _error_code(resume) == "session_terminal"

    _new_created, new_session = _create_session(
        client,
        client_session_id=f"after-{terminal_action}",
        previous_session_id=session_id,
    )
    acquired_again = client.post(
        f"/api/build-sessions/{new_session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": f"acquire-after-{terminal_action}",
            "expected_session_revision": 1,
            "rotate_token": False,
        },
    )
    assert acquired_again.status_code == 200, acquired_again.text


def test_build_context_is_project_wide_and_hides_graph_internals(build_client) -> None:
    client, _session = build_client
    _created, session = _create_session(
        client,
        initial_checkpoint={
            "client_checkpoint_id": "cp-context",
            "phase": "intake",
            "current_step": "Review the project as a whole",
            "ontology_id": ONTOLOGY_ID,
            "blockers": [],
        },
    )
    acquired = client.post(
        f"/api/build-sessions/{session['id']}/ontology-leases/{ONTOLOGY_ID}:acquire",
        json={
            "client_request_id": "context-lease",
            "expected_session_revision": session["revision"],
            "rotate_token": False,
        },
    )
    assert acquired.status_code == 200, acquired.text

    response = client.get(f"/api/projects/{PROJECT_ID}/build-context")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project"]["id"] == PROJECT_ID
    ontology_ids = {item["id"] for item in payload["platform_state"]["ontologies"]}
    assert ontology_ids == {ONTOLOGY_ID, SECOND_ONTOLOGY_ID}
    assert payload["platform_state"]["evidence_reference_count"] == 1
    assert payload["agent_state"]["active_sessions"]
    _assert_no_internal_graph_or_token(payload)

    detail = client.get(f"/api/build-sessions/{session['id']}")
    assert detail.status_code == 200, detail.text
    _assert_no_internal_graph_or_token(detail.json())


def test_build_context_recent_session_cursor_can_read_every_terminal_session(
    build_client,
) -> None:
    client, _session = build_client
    expected_ids: set[str] = set()
    for index in range(3):
        _created, session = _create_session(
            client, client_session_id=f"terminal-page-{index}"
        )
        expected_ids.add(session["id"])
        completed = client.post(
            f"/api/build-sessions/{session['id']}:complete",
            json={
                "client_request_id": f"complete-page-{index}",
                "expected_revision": 1,
                "summary": f"Completed page item {index}",
                "unresolved_items": [],
            },
        )
        assert completed.status_code == 200, completed.text

    seen_ids: set[str] = set()
    cursor = 0
    while True:
        response = client.get(
            f"/api/projects/{PROJECT_ID}/build-context",
            params={"recent_session_limit": 1, "recent_session_cursor": cursor},
        )
        assert response.status_code == 200, response.text
        agent_state = response.json()["agent_state"]
        page = agent_state["recent_sessions"]
        assert len(page) == 1
        assert page[0]["id"] not in seen_ids
        seen_ids.add(page[0]["id"])
        next_cursor = agent_state["recent_sessions_next_cursor"]
        if next_cursor is None:
            break
        assert next_cursor > cursor
        cursor = next_cursor

    assert seen_ids == expected_ids


def test_rest_returns_stable_error_codes_and_forbids_extra_fields(build_client) -> None:
    client, _session = build_client
    missing = client.get("/api/build-sessions/not-found")
    assert missing.status_code == 404
    assert _error_code(missing) == "build_session_not_found"

    _created, session = _create_session(client)
    invalid_checkpoint = client.post(
        f"/api/build-sessions/{session['id']}/checkpoints",
        json={
            "client_checkpoint_id": "invalid-phase",
            "expected_revision": 1,
            "phase": "done",
            "current_step": "Invalid phase",
            "blockers": [],
            "graph_set_id": "must-not-be-accepted",
        },
    )
    assert invalid_checkpoint.status_code == 422
    detail = invalid_checkpoint.json()["detail"]
    if isinstance(detail, dict):
        assert detail["code"] == "checkpoint_validation_failed"
    else:
        assert any(item["type"] in {"extra_forbidden", "literal_error"} for item in detail)
