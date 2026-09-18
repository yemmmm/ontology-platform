"""F-SEAL-004: a sealed source Project stays readable but not semantically queryable.

Shared test plan §9 (2026-09-19 post-delivery evidence) pins R3.0-017 delivery
contract point 5 with the pre-existing archived readiness semantics
(R3.0-004): after a fork commit the source Project's metadata and stored data
remain readable, governed semantic queries fail closed with 409
``scope_not_ready`` because every source Ontology is ``archived``, Ontologies
outside the snapshot scope get no fork copy and are equally not queryable, and
semantic querying continues in the new Project.

Readiness/query-scope judgements run through the real code paths
(``OntologyQueryReadinessEvaluator`` and ``SemanticQueryScopeResolver``); only
the RDF store is faked, and it raises if a sealed-source query ever reaches it.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from rdflib import Graph
from rdflib.compare import to_isomorphic
from sqlalchemy import select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.rdf_store import SparqlResult
from app.services.authorized_scope_discovery import AuthorizedScopeDiscoveryService
from app.services.checkpoint_data import CheckpointDataService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.scoped_sparql_query import ScopedSparqlQueryService
from app.services.semantic_query_scope import (
    SemanticQueryScopeNotReady,
    SemanticQueryScopeResolver,
)


class SealedStore:
    """Fake RDF store with the checkpoint-data contract of ``test_checkpoint_data``.

    ``query_sparql`` fails loudly: a query against a sealed source must be
    rejected by readiness evaluation before any RDF store access.
    """

    def __init__(self) -> None:
        self.graphs: dict[str, str] = {}
        self.query_calls = 0

    def graph_exists(self, iri: str) -> bool:
        return iri in self.graphs

    def export_named_graph(self, iri: str, format: str) -> str:
        return self.graphs[iri]

    def put_named_graph(self, iri: str, content: str, format: str) -> None:
        self.graphs[iri] = content

    def graph_content_hash(self, iri: str) -> str:
        return str(
            to_isomorphic(Graph().parse(data=self.graphs[iri], format="turtle")).graph_digest()
        )

    def drop_named_graph(self, iri: str) -> None:
        self.graphs.pop(iri, None)

    def query_sparql(self, query: str, timeout_seconds: float, limit: int) -> SparqlResult:
        self.query_calls += 1
        raise AssertionError("sealed source queries must be rejected before the RDF store")


class RecordingStore:
    """Minimal SPARQL-executing stand-in (pattern of ``test_scoped_sparql_query``)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, int]] = []

    def query_sparql(self, query: str, timeout_seconds: float, limit: int) -> SparqlResult:
        self.calls.append((query, timeout_seconds, limit))
        return SparqlResult(
            result={"head": {"vars": ["s"]}, "results": {"bindings": []}},
            result_format="application/sparql-results+json",
        )


@pytest.fixture
def sealed(in_memory_session):
    """Capture and fork a source Project that also holds an out-of-scope Ontology."""
    session = in_memory_session
    settings = Settings()
    session.add(m.ProjectModel(id="project", name="Source", normalized_label="Source"))
    session.flush()
    workspace_service = OntologyWorkspaceService(session, settings)
    graph_iris: dict[str, str] = {}
    for ontology_id, name in (("ontology", "Business"), ("extra", "OutOfScope")):
        ontology = m.OntologyModel(id=ontology_id, project_id="project", name=name)
        session.add(ontology)
        session.flush()
        workspace_service.ensure(ontology)
        graph_iris[ontology_id] = workspace_service.context(ontology_id)["members"][0]["graph_iri"]
    store = SealedStore()
    store.graphs[graph_iris["ontology"]] = (
        '<urn:business:Order> <urn:label> "Before checkpoint" .'
    )
    store.graphs[graph_iris["extra"]] = '<urn:business:Supplier> <urn:label> "Out of scope" .'
    session.commit()
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["ontology"])
    session.commit()
    fork = service.fork(snapshot, name="Fork", settings=settings)
    return {
        "session": session,
        "settings": settings,
        "store": store,
        "fork": fork,
        "graph_iris": graph_iris,
    }


def _resolver(session, settings) -> SemanticQueryScopeResolver:
    return SemanticQueryScopeResolver(session, settings)


def _sparql_service(session, store, settings) -> ScopedSparqlQueryService:
    return ScopedSparqlQueryService(_resolver(session, settings), store, settings)


def test_sealed_source_project_scope_query_is_not_ready(sealed):
    env = sealed
    service = _sparql_service(env["session"], env["store"], env["settings"])

    with pytest.raises(SemanticQueryScopeNotReady, match="Semantic query scope is not ready") as error:
        service.query(
            project_id="project",
            scope_mode="project",
            ontology_ids=None,
            query="SELECT * WHERE { ?s ?p ?o }",
        )

    assert error.value.status_code == 409
    assert error.value.code == "scope_not_ready"
    assert env["store"].query_calls == 0


def test_sealed_source_ontology_scope_query_is_not_ready(sealed):
    env = sealed
    service = _sparql_service(env["session"], env["store"], env["settings"])

    with pytest.raises(SemanticQueryScopeNotReady) as error:
        service.query(
            project_id="project",
            scope_mode="ontologies",
            ontology_ids=["ontology"],
            query="SELECT * WHERE { ?s ?p ?o }",
        )

    assert error.value.status_code == 409
    assert error.value.code == "scope_not_ready"
    assert env["store"].query_calls == 0
    with pytest.raises(SemanticQueryScopeNotReady, match="selected Ontology workspaces"):
        _resolver(env["session"], env["settings"]).resolve(
            project_id="project", scope_mode="ontologies", ontology_ids=["ontology"]
        )


def test_scope_discovery_reports_sealed_ontologies_as_not_queryable(sealed):
    env = sealed
    discovery = AuthorizedScopeDiscoveryService(env["session"], env["settings"]).discover(
        authorized_project_id="project"
    )
    project_items = [
        item for item in discovery["items"] if item["resource_type"] == "project"
    ]
    ontology_items = [
        item for item in discovery["items"] if item["resource_type"] == "ontology"
    ]

    assert len(project_items) == 1 and len(ontology_items) == 2
    assert project_items[0]["query_status"] == "unavailable"
    assert {
        item["ontology_id"]: item["reason"]
        for item in project_items[0]["excluded_ontologies"]
    } == {"ontology": "ontology_archived", "extra": "ontology_archived"}
    for item in ontology_items:
        assert item["status"] == "archived"
        assert item["queryable"] is False
        assert item["unavailable_reason"] == "ontology_archived"

    only_queryable = AuthorizedScopeDiscoveryService(
        env["session"], env["settings"]
    ).discover(authorized_project_id="project", queryable="true")
    assert only_queryable["items"] == []


def test_out_of_scope_ontology_is_sealed_without_fork_copy(sealed):
    env = sealed
    session, store, fork = env["session"], env["store"], env["fork"]
    mapping: dict[str, str] = fork["identity_mapping"]

    assert "extra" not in mapping
    new_ontology_ids = list(
        session.scalars(
            select(m.OntologyModel.id).where(
                m.OntologyModel.project_id == fork["project_id"]
            )
        )
    )
    assert new_ontology_ids == [mapping["ontology"]]
    for ontology_id in ("ontology", "extra"):
        assert session.get(m.OntologyModel, ontology_id).status == "archived"
    extra_iri = env["graph_iris"]["extra"]
    assert [
        iri for iri, content in store.graphs.items() if "Out of scope" in content
    ] == [extra_iri]

    with pytest.raises(SemanticQueryScopeNotReady) as error:
        _resolver(session, env["settings"]).resolve(
            project_id="project", scope_mode="ontologies", ontology_ids=["extra"]
        )
    assert error.value.status_code == 409
    assert error.value.code == "scope_not_ready"


def test_forked_project_continues_semantic_queries(sealed):
    env = sealed
    fork: dict[str, Any] = env["fork"]
    store = RecordingStore()
    service = ScopedSparqlQueryService(
        _resolver(env["session"], env["settings"]), store, env["settings"]
    )

    result = service.query(
        project_id=fork["project_id"],
        scope_mode="project",
        ontology_ids=None,
        query="SELECT * WHERE { ?s ?p ?o }",
    )

    assert result["scope"]["status"] == "complete"
    assert (
        result["scope"]["ontologies"][0]["ontology_id"]
        == fork["identity_mapping"]["ontology"]
    )
    assert store.calls and "FROM <" in store.calls[0][0]


def test_sealed_source_http_reads_and_semantic_query_not_ready(r008_client):
    env = r008_client
    client = env["client"]
    store = SealedStore()
    client.app.state.rdf_store = store
    admin_headers = {"Authorization": "Bearer " + env["org_key"]}
    read_headers = {"Authorization": "Bearer " + env["p1_read_key"]}
    project = env["ids"]["p1"]
    created = client.post(
        f"/api/projects/{project}/ontologies",
        headers=admin_headers,
        json={"name": "Snapshot ontology"},
    )
    assert created.status_code == 201, created.text
    ontology_id = created.json()["id"]
    capture = client.post(
        "/api/checkpoint-data/capture",
        headers=admin_headers,
        json={"project_id": project, "ontology_ids": [ontology_id]},
    )
    assert capture.status_code == 200, capture.text
    fork = client.post(
        "/api/checkpoint-data/fork",
        headers=admin_headers,
        json={
            "snapshot": capture.json(),
            "name": "Fork",
            "target_project_id": str(uuid4()),
        },
    )
    assert fork.status_code == 200, fork.text
    assert fork.json()["project_id"]

    # Project metadata stays readable while writes stay blocked (F-SEAL-002 control).
    assert client.get(f"/api/projects/{project}", headers=admin_headers).status_code == 200
    blocked = client.patch(
        f"/api/projects/{project}", headers=admin_headers, json={"name": "Rewrite"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "checkpoint_source_archived"

    # The seal gate skips endpoints whose required scope is "read", so the
    # governed semantic query reaches readiness evaluation and fails closed.
    denied = client.post(
        "/api/semantic/sparql:query",
        headers=read_headers,
        json={
            "project_id": project,
            "scope_mode": "project",
            "query": "SELECT * WHERE { ?s ?p ?o }",
        },
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["detail"]["code"] == "scope_not_ready"
    denied_ontology = client.post(
        "/api/semantic/sparql:query",
        headers=read_headers,
        json={
            "project_id": project,
            "scope_mode": "ontologies",
            "ontology_ids": [ontology_id],
            "query": "SELECT * WHERE { ?s ?p ?o }",
        },
    )
    assert denied_ontology.status_code == 409
    assert denied_ontology.json()["detail"]["code"] == "scope_not_ready"
    assert store.query_calls == 0

    # Governed semantic queries require "read" scope regardless of method, so
    # the archive gate exempts them and readiness answers for admin keys too.
    gated = client.post(
        "/api/semantic/sparql:query",
        headers=admin_headers,
        json={
            "project_id": project,
            "scope_mode": "project",
            "query": "SELECT * WHERE { ?s ?p ?o }",
        },
    )
    assert gated.status_code == 409
    assert gated.json()["detail"]["code"] == "scope_not_ready"

    discovered = client.get("/api/semantic/scopes:discover", headers=read_headers)
    assert discovered.status_code == 200, discovered.text
    items = discovered.json()["items"]
    project_items = [item for item in items if item["resource_type"] == "project"]
    ontology_items = [item for item in items if item["resource_type"] == "ontology"]
    assert len(project_items) == 1 and len(ontology_items) == 1
    assert project_items[0]["query_status"] == "unavailable"
    assert project_items[0]["excluded_ontologies"] == [
        {
            "ontology_id": ontology_id,
            "ontology_name": "Snapshot ontology",
            "reason": "ontology_archived",
        }
    ]
    assert ontology_items[0]["status"] == "archived"
    assert ontology_items[0]["queryable"] is False
    assert ontology_items[0]["unavailable_reason"] == "ontology_archived"
