"""Tests for /api/semantic/graph-sets/{gs}/fact-evidence endpoints.

The new endpoints write evidence to Postgres via FactEvidenceBindingRepository,
bypassing the RDF store. graph_set_id appears in the URL for resource shape
only — the fact is identified by the computed fact_id, so tests pass an
arbitrary graph_set_id.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.api.deps import get_db_session, get_settings
from app.api.fact_evidence import router as fact_evidence_router
from app.core.config import Settings
from app.repositories.models import (
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    OntologyModel,
    ProjectModel,
    SemanticGraphSetModel,
)

GRAPH_SET_ID = "gs-test-1"


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(fact_evidence_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings()
    return TestClient(app)


def test_post_fact_evidence_creates_binding(in_memory_session: Session) -> None:
    client = _client(in_memory_session)
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "evidence snippet",
        "actor": "user:alice",
    }
    resp = client.post(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence", json=payload
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fact_id"]
    assert body["text"] == "evidence snippet"
    assert body["id"]
    assert body["subject_iri"] == "http://example/s"


def test_post_fact_evidence_rejects_fact_id_mismatch(in_memory_session: Session) -> None:
    client = _client(in_memory_session)
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "fact_id": "0" * 64,
        "text": "t",
    }
    resp = client.post(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence", json=payload
    )
    assert resp.status_code == 400


def test_post_fact_evidence_creates_lightweight_reference_and_association(
    in_memory_session: Session,
) -> None:
    in_memory_session.add_all(
        [
            ProjectModel(id="project-1", name="Project", normalized_label="project"),
            OntologyModel(id="ont-1", project_id="project-1", name="Ontology"),
            SemanticGraphSetModel(
                id=GRAPH_SET_ID,
                name="Default",
                scope_type="ontology",
                scope_id="ont-1",
                status="active",
                is_default=True,
                source_signature="test",
            ),
        ]
    )
    in_memory_session.commit()
    client = _client(in_memory_session)
    response = client.post(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence",
        json={
            "ontology_id": "ont-1",
            "subject_iri": "http://example/s",
            "predicate_iri": "http://example/p",
            "object_value": "42",
            "graph_iri": "http://example/g",
            "document_filename": "API Guide",
            "text": "The value is 42.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence_reference_id"]
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 1
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 1


def test_delete_fact_evidence(in_memory_session: Session) -> None:
    client = _client(in_memory_session)
    create = client.post(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence",
        json={
            "ontology_id": "ont-1",
            "subject_iri": "http://example/s",
            "predicate_iri": "http://example/p",
            "object_value": "42",
            "object_is_iri": False,
            "graph_iri": "http://example/g",
            "text": "t",
        },
    )
    assert create.status_code == 200, create.text
    binding_id = create.json()["id"]
    resp = client.delete(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence/{binding_id}"
    )
    assert resp.status_code == 204


def test_delete_fact_evidence_404_for_missing(in_memory_session: Session) -> None:
    client = _client(in_memory_session)
    resp = client.delete(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/fact-evidence/nonexistent"
    )
    assert resp.status_code == 404
