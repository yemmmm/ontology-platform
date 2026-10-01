"""R4.0-012: production routes do not expose even retained historical artifacts."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.routes import router as api_router
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
    app.include_router(api_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    return TestClient(app)


@pytest.fixture()
def evidence_client(in_memory_session: Session) -> tuple[TestClient, str, str, str]:
    project_id, artifact_id, chunk_id = _seed_evidence(in_memory_session)
    return _client(in_memory_session), project_id, artifact_id, chunk_id


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects/project-1/evidence-artifacts",
        "/api/projects/project-1/evidence-artifacts?limit=0",
        "/api/evidence-artifacts/art-1",
        "/api/evidence-artifacts/art-1/chunks",
        "/api/chunks/chk-2",
    ],
)
def test_historical_evidence_routes_are_unavailable(evidence_client, path):
    client, _, _, _ = evidence_client
    response = client.get(path)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}


def test_unavailable_routes_preserve_historical_rows(evidence_client, in_memory_session):
    client, _, _, _ = evidence_client
    assert client.get("/api/evidence-artifacts/art-1/chunks").status_code == 404
    assert in_memory_session.get(EvidenceArtifactModel, "art-1").filename == "acme-overview.pdf"
    assert in_memory_session.get(EvidenceChunkModel, "chk-2").text.startswith(" of widgets")


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/projects/project-1/evidence-references"),
        ("GET", "/api/projects/project-1/evidence-references"),
        ("POST", "/api/projects/project-1/evidence-references:resolve"),
        ("GET", "/api/evidence-references/historical-reference"),
        ("GET", "/api/evidence-references/historical-reference/associations"),
        ("GET", "/api/projects/project-1/evidence-associations"),
        ("POST", "/api/projects/project-1/evidence-associations"),
        ("POST", "/api/projects/project-1/evidence-associations:batch"),
    ],
)
def test_reference_and_association_routes_are_unavailable(evidence_client, method, path):
    client, _, _, _ = evidence_client
    response = client.request(method, path, json={})
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}
