"""R4.0-012 removes fact binding and missing-evidence dedicated REST routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "POST",
            "/api/semantic/ontologies/gs/fact-evidence",
            {
                "ontology_id": "o",
                "subject_iri": "urn:entity",
                "predicate_iri": "urn:name",
                "text": "source",
            },
        ),
        ("POST", "/api/semantic/ontologies/gs/fact-evidence", {}),
        ("DELETE", "/api/semantic/ontologies/gs/fact-evidence/historical-binding", None),
        ("GET", "/api/semantic/ontologies/gs/missing-evidence-facts", None),
        ("GET", "/api/semantic/ontologies/gs/missing-evidence-facts?limit=0", None),
    ],
)
def test_fact_evidence_routes_are_unavailable(method, path, payload):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    response = TestClient(app).request(method, path, json=payload)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}
    assert not any(
        "fact-evidence" in path or "missing-evidence-facts" in path
        for path in app.openapi()["paths"]
    )
