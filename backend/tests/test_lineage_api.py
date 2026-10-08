"""R4.0-012 removes the REST lineage route without a history-only replacement."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


@pytest.mark.parametrize(
    "params",
    [
        {"target_type": "statement", "target_id": "historical-statement"},
        {"target_type": "resource", "target_id": "https://example.test/Entity"},
        {"target_type": "statement", "target_id": "historical-statement", "include_history": True},
        {"target_type": "statement", "target_id": "historical-statement", "max_depth": 6},
        {"ontology_id": "forged", "graph_iri": "https://forged.test/g"},
    ],
)
def test_lineage_route_is_unavailable(params):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    response = TestClient(app).get("/api/ontologies/o/lineage", params=params)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert "/api/ontologies/{ontology_id}/lineage" not in app.openapi()["paths"]
