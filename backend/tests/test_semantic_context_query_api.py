from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.deps import (
    get_context_cursor_codec,
    get_db_session,
    get_rdf_store,
    get_settings,
)
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import RdfStoreUnavailable, SparqlQueryTimeout, SparqlResult
from app.services.semantic_context_query import SemanticContextQueryService
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


def test_context_query_rest_keeps_bilingual_asserted_label_exactness(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://context-rest.test/graphs")
    _ready_scope(in_memory_session, settings)
    graph = "https://context-rest.test/graphs/ontology/o"

    class BilingualStore:
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={
                    "head": {"vars": []},
                    "results": {
                        "bindings": [
                            {
                                "graph": {"type": "uri", "value": graph},
                                "subject": {
                                    "type": "uri",
                                    "value": "https://example.test/CustomerSupportWorkflow",
                                },
                                "predicate": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/2000/01/rdf-schema#label",
                                },
                                "object": {
                                    "type": "literal",
                                    "value": "客户支持工作流",
                                    "xml:lang": "zh",
                                },
                                "subjectLabel": {
                                    "type": "literal",
                                    "value": "Customer Support Workflow",
                                    "xml:lang": "en",
                                },
                                "subjectTypes": {
                                    "type": "literal",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                                "matchedField": {"type": "literal", "value": "label"},
                                "matchedValue": {
                                    "type": "literal",
                                    "value": "客户支持工作流",
                                },
                            }
                        ]
                    },
                },
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall",
        lambda *_args, **_kwargs: {
            "candidates": [],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    response = _client(in_memory_session, settings, BilingualStore).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "客户支持工作流",
            "resource_types": ["concept"],
            "depth": 0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recall"]["match_status"] == "exact"
    assert body["primary_matches"][0]["label"] == "客户支持工作流"
    assert body["primary_matches"][0]["match"]["reasons"] == ["exact_label"]


def test_context_query_rest_strips_unknown_shape_lineage_marker(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://context-rest.test/graphs")
    _ready_scope(in_memory_session, settings)
    graph = "https://context-rest.test/graphs/ontology/o"

    class CandidateStore(ApiStore):
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={
                    "head": {"vars": []},
                    "results": {
                        "bindings": [
                            {
                                "graph": {"type": "uri", "value": graph},
                                "subject": {
                                    "type": "uri",
                                    "value": "https://example.test/Workflow",
                                },
                                "predicate": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                                },
                                "object": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                                "subjectLabel": {
                                    "type": "literal",
                                    "value": "Workflow",
                                },
                                "subjectTypes": {
                                    "type": "literal",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                            }
                        ]
                    },
                },
                result_format="application/sparql-results+json",
            )

    def invalid_shape_items(self, primary, scope, *, limit):  # noqa: ARG001
        return [
            {
                "id": "shape-hash",
                "kind": "fact",
                "ontology_id": "o",
                "iri": None,
                "label": "custom property",
                "aliases": [],
                "description": None,
                "data": {
                    "target_class": "https://example.test/Workflow",
                    "constraint": {"path": "relative/property", "provenance": "custom"},
                },
                "distance": 1,
                "assertion_kind": "asserted",
                "match": {
                    "score": 275,
                    "matched_terms": [],
                    "matched_fields": ["constraint"],
                    "reasons": ["shape_constraint"],
                },
                "_lineage_target": {
                    "target_type": "synthetic",
                    "target_id": "shape-hash",
                },
            }
        ][:limit]

    monkeypatch.setattr(SemanticContextQueryService, "_shape_constraint_items", invalid_shape_items)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    response = _client(in_memory_session, settings, CandidateStore).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "workflow",
            "resource_types": ["concept", "fact"],
            "depth": 1,
            "context_limit": 1,
        },
    )

    assert response.status_code == 200, response.text
    related = response.json()["related_context"]
    assert len(related) == 1
    shape_item = related[0]
    assert "_lineage_target" not in shape_item
    assert "target_kind" not in shape_item
    assert shape_item["lineage"] == {"status": "missing"}
    assert "synthetic" not in str(shape_item["lineage"])


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


# ---------------------------------------------------------------------------
# R1.2-004 API-level multi-expression Context Query validation and parity.
# ---------------------------------------------------------------------------


def test_context_query_rest_accepts_canonical_queries(in_memory_session, monkeypatch):
    settings = Settings()
    _ready_scope(in_memory_session, settings)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[], []],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    response = _client(in_memory_session, settings).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "queries": ["one", "two"],
            "depth": 0,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"]["queries"] == ["one", "two"]
    assert body["query"]["normalized_queries"] == ["one", "two"]
    assert body["matches_page"]["returned"] == 0
    assert body["context_page"]["returned"] == 0


def test_context_query_rest_rejects_both_query_and_queries(in_memory_session):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "query": "x",
            "queries": ["x"],
        },
    )
    assert response.status_code == 422


def test_context_query_rest_rejects_neither_query_nor_queries(in_memory_session):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
        },
    )
    assert response.status_code == 422


def test_context_query_rest_rejects_too_many_queries(in_memory_session):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "queries": [f"q{index}" for index in range(9)],
        },
    )
    assert response.status_code == 422


def test_context_query_rest_rejects_both_cursors(in_memory_session):
    response = _client(in_memory_session, Settings()).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "queries": ["x"],
            "match_cursor": "abc",
            "context_cursor": "def",
        },
    )
    assert response.status_code == 422


def test_context_query_rest_rejects_invalid_context_cursor(in_memory_session, monkeypatch):
    settings = Settings()
    _ready_scope(in_memory_session, settings)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    response = _client(in_memory_session, settings).post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o"],
            "queries": ["x"],
            "depth": 0,
            "context_cursor": "tampered.payload",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_context_cursor"


def test_context_query_rest_reuses_default_ephemeral_cursor_across_requests(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_context_query_cursor_signing_secret="")
    _ready_scope(in_memory_session, settings)
    graph = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/o"
    rows = [
        {
            "graph": {"type": "uri", "value": graph},
            "subject": {
                "type": "uri",
                "value": f"https://example.test/Workflow{index}",
            },
            "predicate": {
                "type": "uri",
                "value": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            },
            "object": {
                "type": "uri",
                "value": "http://www.w3.org/2002/07/owl#Class",
            },
            "subjectLabel": {"type": "literal", "value": f"Workflow {index}"},
            "subjectTypes": {
                "type": "literal",
                "value": "http://www.w3.org/2002/07/owl#Class",
            },
        }
        for index in range(3)
    ]

    class CandidateStore(ApiStore):
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={
                    "head": {"vars": []},
                    "results": {"bindings": rows},
                },
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    client = _client(in_memory_session, settings, CandidateStore)
    request = {
        "project_id": "p",
        "scope_mode": "ontologies",
        "ontology_ids": ["o"],
        "query": "workflow",
        "resource_types": ["concept"],
        "depth": 0,
        "limit": 1,
        "context_limit": 0,
    }

    first = client.post("/api/semantic/context:query", json=request)
    assert first.status_code == 200, first.text
    first_body = first.json()
    first_cursor = first_body["matches_page"]["next_match_cursor"]
    assert first_cursor

    second_request = {**request, "match_cursor": first_cursor}
    second = client.post("/api/semantic/context:query", json=second_request)
    assert second.status_code == 200, second.text
    second_body = second.json()
    first_ids = {item["iri"] for item in first_body["primary_matches"]}
    second_ids = {item["iri"] for item in second_body["primary_matches"]}
    assert first_ids.isdisjoint(second_ids)
    assert second_body["matches_page"]["returned"] == 1


def _request_for_app(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "scheme": "http",
            "headers": [],
            "client": ("testclient", 1),
            "server": ("testserver", 80),
            "root_path": "",
            "app": app,
        }
    )


def test_context_cursor_codec_isolated_per_app_and_concurrent_initialization():
    settings = Settings(semantic_context_query_cursor_signing_secret="")
    app_a = FastAPI()
    app_b = FastAPI()

    with ThreadPoolExecutor(max_workers=8) as executor:
        codecs_a = list(
            executor.map(
                lambda _index: get_context_cursor_codec(_request_for_app(app_a), settings),
                range(16),
            )
        )
    codec_a = codecs_a[0]
    assert all(codec is codec_a for codec in codecs_a)
    assert get_context_cursor_codec(_request_for_app(app_a), settings) is codec_a

    codec_b = get_context_cursor_codec(_request_for_app(app_b), settings)
    assert codec_b is not codec_a
    assert codec_b._signing_key() != codec_a._signing_key()
