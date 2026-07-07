"""Stage 4 §5.1 evidence-artifacts REST surface coverage.

Seeds an in-memory SQLite session with one ``EvidenceArtifactModel`` row and
two ``EvidenceChunkModel`` rows ordered by ``sequence``, then exercises the
four routes mounted under ``backend/app/api/evidence.py``:

* ``GET /api/projects/{project_id}/evidence-artifacts``
* ``GET /api/evidence-artifacts/{artifact_id}``
* ``GET /api/evidence-artifacts/{artifact_id}/chunks``
* ``GET /api/chunks/{chunk_id}``

The handler imports use the project-wide ``get_db_session`` dependency, so we
mount the router onto a minimal FastAPI app and override the session with the
seeded in-memory fixture (mirrors the pattern in
``tests/conftest_stage3.py:client_for``).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.evidence import router as evidence_router
from app.repositories.models import (
    EvidenceArtifactModel,
    EvidenceChunkModel,
    ProjectModel,
)


def _seed_evidence(session: Session) -> tuple[str, str, str]:
    """Insert one artifact (``project-1``) and two chunks; return
    ``(project_id, artifact_id, second_chunk_id)``."""
    artifact_id = "art-1"
    chunk_a_id = "chk-1"
    chunk_b_id = "chk-2"
    created = datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc)
    # Pre-create the two project rows the artifacts reference so the SQLite
    # foreign-key constraint (enabled in conftest.in_memory_session) passes.
    session.add(
        ProjectModel(
            id="project-1",
            name="Project One",
            normalized_label="project one",
            description="stage4 evidence fixture",
            created_at=created,
            updated_at=created,
        )
    )
    session.add(
        ProjectModel(
            id="project-other",
            name="Project Other",
            normalized_label="project other",
            description="stage4 evidence fixture (other)",
            created_at=created,
            updated_at=created,
        )
    )
    session.flush()
    session.add(
        EvidenceArtifactModel(
            id=artifact_id,
            project_id="project-1",
            filename="acme-overview.pdf",
            media_type="application/pdf",
            size_bytes=1024,
            content_hash="sha256:abcdef",
            content=b"%PDF-1.4 binary payload",
            parse_status="parsed",
            parse_error=None,
            parser_version="v1",
            parse_count=1,
            parse_revision=1,
            created_at=created,
            updated_at=created,
        )
    )
    # A second artifact under a different project so the listing filter
    # can prove it only returns rows for the requested project.
    session.add(
        EvidenceArtifactModel(
            id="art-other",
            project_id="project-other",
            filename="other.pdf",
            media_type="application/pdf",
            size_bytes=512,
            content_hash="sha256:other",
            content=b"%PDF-1.4 other",
            parse_status="pending",
            parser_version="v1",
            parse_count=0,
            parse_revision=1,
            created_at=created,
            updated_at=created,
        )
    )
    session.add(
        EvidenceChunkModel(
            id=chunk_a_id,
            document_id=artifact_id,
            sequence=0,
            parse_revision=1,
            page_number=1,
            char_start=0,
            char_end=20,
            text="Acme is a manufacturer",
            content_hash="sha256:chunk-a",
            created_at=created,
        )
    )
    session.add(
        EvidenceChunkModel(
            id=chunk_b_id,
            document_id=artifact_id,
            sequence=1,
            parse_revision=1,
            page_number=1,
            char_start=20,
            char_end=48,
            text=" of widgets based in Acme City.",
            content_hash="sha256:chunk-b",
            created_at=created,
        )
    )
    session.commit()
    return "project-1", artifact_id, chunk_b_id


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(evidence_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    return TestClient(app)


@pytest.fixture()
def evidence_client(in_memory_session: Session) -> tuple[TestClient, str, str, str]:
    project_id, artifact_id, chunk_id = _seed_evidence(in_memory_session)
    return _client(in_memory_session), project_id, artifact_id, chunk_id


def test_list_evidence_artifacts_filters_by_project(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, project_id, artifact_id, _ = evidence_client
    response = client.get(f"/api/projects/{project_id}/evidence-artifacts")
    assert response.status_code == 200, response.text
    payload = response.json()
    # Default page size is 50; we seeded two artifacts total but only one
    # belongs to ``project-1``.
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == artifact_id
    assert item["project_id"] == project_id
    assert item["filename"] == "acme-overview.pdf"
    # Metadata-only response: content bytes must not be carried.
    assert "content" not in item


def test_list_evidence_artifacts_respects_limit(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, project_id, _, _ = evidence_client
    response = client.get(
        f"/api/projects/{project_id}/evidence-artifacts", params={"limit": 0}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1  # total still counts the underlying rows
    assert payload["items"] == []


def test_get_single_artifact_metadata(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, _, artifact_id, _ = evidence_client
    response = client.get(f"/api/evidence-artifacts/{artifact_id}")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["id"] == artifact_id
    assert item["filename"] == "acme-overview.pdf"
    assert item["size_bytes"] == 1024
    assert item["parse_status"] == "parsed"
    # Content bytes never leave this route.
    assert "content" not in item


def test_get_single_artifact_returns_404_for_unknown_id(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, _, _, _ = evidence_client
    response = client.get("/api/evidence-artifacts/does-not-exist")
    assert response.status_code == 404


def test_list_chunks_ordered_by_sequence(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, _, artifact_id, _ = evidence_client
    response = client.get(f"/api/evidence-artifacts/{artifact_id}/chunks")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    sequences = [item["sequence"] for item in payload["items"]]
    assert sequences == [0, 1]
    first = payload["items"][0]
    assert first["document_id"] == artifact_id
    assert first["text"] == "Acme is a manufacturer"
    # Char offsets are projected so the drawer can render highlights.
    assert first["char_start"] == 0
    assert first["char_end"] == 20


def test_get_single_chunk_truncates_text_preview(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, _, _, chunk_id = evidence_client
    response = client.get(f"/api/chunks/{chunk_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == chunk_id
    assert payload["text"] == " of widgets based in Acme City."
    # Preview is capped at 500 chars by the spec.
    assert "text_preview" in payload
    assert payload["text_preview"] == " of widgets based in Acme City."


def test_get_single_chunk_returns_404_for_unknown_id(
    evidence_client: tuple[TestClient, str, str, str],
):
    client, _, _, _ = evidence_client
    response = client.get("/api/chunks/no-such-chunk")
    assert response.status_code == 404
