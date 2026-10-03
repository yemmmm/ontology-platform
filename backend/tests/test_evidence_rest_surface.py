"""R4.0-012 keeps dedicated evidence routes out of the production registry."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router as api_router


@pytest.fixture()
def evidence_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    return TestClient(app)


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
    client = evidence_client
    response = client.get(path)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}


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
    client = evidence_client
    response = client.request(method, path, json={})
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}
