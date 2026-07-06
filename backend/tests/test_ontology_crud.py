"""Tests for the Stage 3 B2 ontologies router."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ontologies import router as ontologies_router


def test_list_ontology_versions_returns_empty_placeholder() -> None:
    """Stage 3 B2: /ontologies/{id}/versions returns [] until Stage 4
    replaces it with the graph-set history view."""
    app = FastAPI()
    app.include_router(ontologies_router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/ontologies/any-id/versions")
    assert response.status_code == 200
    assert response.json() == []
