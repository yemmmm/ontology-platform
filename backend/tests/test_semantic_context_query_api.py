from __future__ import annotations

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import RdfStoreUnavailable, SparqlQueryTimeout, SparqlResult
from app.services.ontology_workspace import OntologyWorkspaceService


class ApiStore:
    def query_sparql(self, query, timeout_seconds, limit):
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}},
            result_format="application/sparql-results+json",
        )

    def query_sparql_scoped(self, query, timeout_seconds, limit, graph_iris):
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}},
            result_format="application/sparql-results+json",
        )


def _client(session: Session, settings: Settings, store=ApiStore) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _ready_scope(session: Session, settings: Settings) -> None:
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()


def test_context_query_rest_returns_no_match_and_public_scope(in_memory_session):
    settings = Settings()
    _ready_scope(in_memory_session, settings)

    response = _client(in_memory_session, settings).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "not found",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result_status"] == "no_match"
    assert body["scope"]["ontologies"][0]["ontology_id"] == "o"
    assert "graph_set" not in str(body)
    assert "graph_iri" not in str(body)


def test_context_query_rest_rejects_internal_scope_fields(in_memory_session):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "project",
            "ontology_ids": [],
            "query": "workflow",
            "graph_set_id": "internal",
            "graph_iri": "https://secret.test/graph",
        },
    )

    assert response.status_code == 422
    request_schema = _client(in_memory_session, Settings()).get("/openapi.json").json()[
        "components"
    ]["schemas"]["SemanticContextQueryRequest"]
    assert "graph_set_id" not in str(request_schema)
    assert "graph_iri" not in str(request_schema)


def test_scoped_sparql_rest_returns_standard_result_and_scope(in_memory_session):
    settings = Settings()
    _ready_scope(in_memory_session, settings)

    response = _client(in_memory_session, settings).post(
        "/api/semantic/sparql:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "ASK { ?s ?p ?o }",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "ask"
    assert body["scope"]["ontologies"][0]["ontology_id"] == "o"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (SparqlQueryTimeout("timed out"), 504, "query_timeout"),
        (RdfStoreUnavailable("offline"), 502, "query_unavailable"),
    ],
)
def test_semantic_query_rest_preserves_runtime_error_codes(
    in_memory_session, error, status_code, code
):
    settings = Settings()
    _ready_scope(in_memory_session, settings)

    class FailingStore:
        def query_sparql(self, query, timeout_seconds, limit):
            raise error

    response = _client(in_memory_session, settings, FailingStore).post(
        "/api/semantic/sparql:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "ASK { ?s ?p ?o }",
        },
    )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize(
    "field_value",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": 121},
        {"result_limit": 0},
        {"result_limit": 10001},
    ],
)
def test_scoped_sparql_rest_rejects_invalid_query_bounds(
    in_memory_session, field_value
):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/sparql:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "ASK { ?s ?p ?o }",
            **field_value,
        },
    )

    assert response.status_code == 422
