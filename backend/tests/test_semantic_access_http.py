"""HTTP-level access-view regressions (R3.0-004, repair round 1).

Exercises the real route + authentication middleware stack (bearer key ->
AuthPrincipal -> SemanticAccessResolver) instead of service-level fakes.
Catches defects where the view is resolved wrongly or not applied on the
live HTTP path (D1: SPARQL whole-request rejection).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_rdf_store, get_settings
from app.core.config import Settings
from app.main import create_app
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticProtectionSetMemberModel,
    SemanticProtectionSetModel,
)
from app.repositories.rdf_store import SparqlResult
from app.security.auth import create_api_key
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_query import SemanticContextQueryService
from fastapi.testclient import TestClient

COST_IRI = "https://r304.test/SparePartStandardCost"
PUBLIC_IRI = "https://r304.test/PublicResource"
NAME_PREDICATE = "https://r304.test/name"


def _uri(value: str) -> dict:
    return {"value": value, "type": "uri"}


def _literal(value: str) -> dict:
    return {"value": value, "type": "literal"}


class AccessStore:
    """Query-aware fake RDF store serving protected + public content."""

    def __init__(self, data_graph: str) -> None:
        self.data_graph = data_graph

    def _select(self, bindings: list[dict]) -> SparqlResult:
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": bindings}},
            result_format="application/sparql-results+json",
        )

    def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
        if "template: entity-detail" in query or "template: entity-list" in query:
            return self._select(
                [
                    {
                        "entity": _uri(COST_IRI),
                        "label": _literal("cost"),
                        "graph": _uri(self.data_graph),
                    },
                    {
                        "entity": _uri(PUBLIC_IRI),
                        "label": _literal("public"),
                        "graph": _uri(self.data_graph),
                    },
                ]
            )
        if "template: statement-list" in query:
            return self._select(
                [
                    {
                        "subject": _uri(PUBLIC_IRI),
                        "predicate": _uri(NAME_PREDICATE),
                        "object": _literal("public name"),
                        "graph": _uri(self.data_graph),
                    },
                    {
                        "subject": _uri(COST_IRI),
                        "predicate": _uri(NAME_PREDICATE),
                        "object": _literal("cost value"),
                        "graph": _uri(self.data_graph),
                    },
                    {
                        "subject": _uri(PUBLIC_IRI),
                        "predicate": _uri("https://r304.test/relates-to"),
                        "object": _uri(COST_IRI),
                        "graph": _uri(self.data_graph),
                    },
                ]
            )
        # direct SPARQL: only the O_a data graph mentions the protected IRI
        if self.data_graph in query:
            return self._select([{"s": _uri(COST_IRI), "p": _uri(NAME_PREDICATE)}])
        return self._select([])

    def query_sparql_scoped(self, query, timeout_seconds, limit, graph_iris):  # noqa: ARG002
        return self.query_sparql(query, timeout_seconds, limit)

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):  # noqa: ARG002
        return self.query_sparql(query, timeout_seconds, limit)

    def get_graph(self, graph_iri, format):  # noqa: ARG002
        if graph_iri == self.data_graph:
            return (
                f"<{self.data_graph}> {{\n"
                f"  <{COST_IRI}> <{NAME_PREDICATE}> \"cost\" .\n"
                f"  <{PUBLIC_IRI}> <{NAME_PREDICATE}> \"public\" .\n"
                "}\n"
            )
        return ""

    def graph_exists(self, graph_iri):
        return graph_iri == self.data_graph

    def graph_content_hash(self, graph_iri):  # noqa: ARG002
        return None


@pytest.fixture()
def http_env(in_memory_session):
    settings = Settings()
    session = in_memory_session
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology_a = OntologyModel(id="o-a", project_id="p", name="O_a")
    ontology_c = OntologyModel(id="o-c", project_id="p", name="O_c")
    session.add_all([ontology_a, ontology_c])
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology_a)
    OntologyWorkspaceService(session, settings).ensure(ontology_c)
    graph_set_a = OntologyWorkspaceService(session, settings).context(ontology_a.id)[
        "default_graph_set_id"
    ]
    data_graph = next(
        member["graph_iri"]
        for member in OntologyWorkspaceService(session, settings)
        .context(ontology_a.id)["members"]
        if member["role"] == "asserted_data"
    )
    protection_set = SemanticProtectionSetModel(
        id="ps", project_id="p", name="cost-visibility", allowed_grants=["cost-visibility"]
    )
    session.add(protection_set)
    session.flush()
    session.add(
        SemanticProtectionSetMemberModel(
            protection_set_id="ps", resource_iri=COST_IRI, ontology_id="o-a"
        )
    )
    _operator_record, operator_key = create_api_key(
        session, name="operator", project_id="p", scopes=["read"]
    )
    _manager_record, manager_key = create_api_key(
        session,
        name="manager",
        project_id="p",
        scopes=["read"],
        semantic_grants=["cost-visibility"],
    )
    session.commit()

    app = create_app()
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, autocommit=False)
    app.state.session_factory = factory
    app.state.session_secret = "test-secret-that-is-stable"
    app.dependency_overrides[get_rdf_store] = lambda: AccessStore(data_graph)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        yield {
            "client": client,
            "operator": {"Authorization": f"Bearer {operator_key}"},
            "manager": {"Authorization": f"Bearer {manager_key}"},
            "graph_set_a": graph_set_a,
        }


def _sparql_body(ontology_id: str) -> dict:
    return {
        "project_id": "p",
        "scope_mode": "ontologies",
        "ontology_ids": [ontology_id],
        "query": "SELECT * WHERE { ?s ?p ?o }",
    }


def test_sparql_rejects_scope_with_unauthorized_member_for_grantless_key(http_env):
    """D1 regression: operator querying O_a (contains the unauthorized
    protected member) must get 409 scope_not_ready and no protected content."""
    response = http_env["client"].post(
        "/api/semantic/sparql:query",
        json=_sparql_body("o-a"),
        headers=http_env["operator"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "scope_not_ready"
    assert COST_IRI not in response.text


def test_sparql_allows_manager_and_clean_scope(http_env):
    client = http_env["client"]

    manager = client.post(
        "/api/semantic/sparql:query",
        json=_sparql_body("o-a"),
        headers=http_env["manager"],
    )
    assert manager.status_code == 200, manager.text
    assert COST_IRI in manager.text

    clean = client.post(
        "/api/semantic/sparql:query",
        json=_sparql_body("o-c"),
        headers=http_env["operator"],
    )
    assert clean.status_code == 200, clean.text
    assert COST_IRI not in clean.text


def test_resource_route_returns_not_found_for_protected_member(http_env):
    client = http_env["client"]
    graph_set = http_env["graph_set_a"]

    denied = client.get(
        f"/api/semantic/resources/{COST_IRI}",
        params={"graph_set_id": graph_set},
        headers=http_env["operator"],
    )
    assert denied.status_code == 404
    assert denied.json()["detail"] == f"Resource not found: {COST_IRI}"

    allowed = client.get(
        f"/api/semantic/resources/{PUBLIC_IRI}",
        params={"graph_set_id": graph_set},
        headers=http_env["operator"],
    )
    assert allowed.status_code == 200
    assert allowed.json()["iri"] == PUBLIC_IRI

    manager = client.get(
        f"/api/semantic/resources/{COST_IRI}",
        params={"graph_set_id": graph_set},
        headers=http_env["manager"],
    )
    assert manager.status_code == 200
    assert manager.json()["iri"] == COST_IRI


def test_statements_route_filters_rows_before_pagination(http_env):
    client = http_env["client"]
    response = client.get(
        "/api/semantic/statements",
        params={"graph_set_id": http_env["graph_set_a"]},
        headers=http_env["operator"],
    )
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert COST_IRI not in response.text
    assert len(envelope["items"]) == 1

    manager = client.get(
        "/api/semantic/statements",
        params={"graph_set_id": http_env["graph_set_a"]},
        headers=http_env["manager"],
    )
    assert manager.status_code == 200
    assert len(manager.json()["items"]) == 3


def test_read_model_route_filters_protected_rows(http_env):
    client = http_env["client"]
    response = client.get(
        f"/api/semantic/graph-sets/{http_env['graph_set_a']}/read-models/entity-list",
        headers=http_env["operator"],
    )
    assert response.status_code == 200, response.text
    assert COST_IRI not in response.text
    assert PUBLIC_IRI in response.text


def test_export_graph_set_route_omits_protected_quads(http_env):
    client = http_env["client"]
    response = client.get(
        f"/api/semantic/graph-sets/{http_env['graph_set_a']}/export",
        params={"format": "trig"},
        headers=http_env["operator"],
    )
    assert response.status_code == 200, response.text
    assert "SparePartStandardCost" not in response.text
    assert "PublicResource" in response.text

    manager = client.get(
        f"/api/semantic/graph-sets/{http_env['graph_set_a']}/export",
        params={"format": "trig"},
        headers=http_env["manager"],
    )
    assert manager.status_code == 200
    assert "SparePartStandardCost" in manager.text


def test_context_query_route_filters_protected_candidates(http_env, monkeypatch):
    def candidates(self, _rows, scope, _text, _terms):  # noqa: ARG001
        base = {
            "kind": "instance",
            "target_kind": "resource",
            "ontology_id": "o-a",
            "aliases": [],
            "description": None,
            "data": {},
            "distance": 0,
            "assertion_kind": "asserted",
        }
        return [
            {
                **base,
                "id": PUBLIC_IRI,
                "iri": PUBLIC_IRI,
                "label": "public",
                "match": {"score": 900, "matched_terms": ["topic"], "matched_fields": ["label"], "reasons": ["exact_label"]},
            },
            {
                **base,
                "id": COST_IRI,
                "iri": COST_IRI,
                "label": "cost",
                "match": {"score": 800, "matched_terms": ["topic"], "matched_fields": ["label"], "reasons": ["label_contains"]},
            },
        ]

    monkeypatch.setattr(SemanticContextQueryService, "_rdf_candidates", candidates)
    monkeypatch.setattr(SemanticContextQueryService, "_lexical_candidate_rows", lambda *args: [])
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    client = http_env["client"]
    response = client.post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o-a"],
            "query": "topic",
        },
        headers=http_env["operator"],
    )
    assert response.status_code == 200, response.text
    assert COST_IRI not in response.text
    assert PUBLIC_IRI in response.text
    assert all(
        "visibility" not in str(w.get("code", "")) for w in response.json().get("warnings", [])
    )

    manager = client.post(
        "/api/semantic/context:query",
        json={
            "project_id": "p",
            "scope_mode": "ontologies",
            "ontology_ids": ["o-a"],
            "query": "topic",
        },
        headers=http_env["manager"],
    )
    assert manager.status_code == 200
    assert COST_IRI in manager.text
