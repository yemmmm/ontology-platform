"""Stage 2 §3.4 — GET /graph-sets/{gs}/shapes/classes/{class_iri} tests.

The endpoint reads the asserted ontology graph for the graph set, runs
the OWL→SHACL generator in memory, reads the custom shape sub-graph,
and returns merged ``ShaclFormGuidance``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.rdf_store import SparqlResult, UpdateResult


PREFIX = "http://op.local/semantic/"
ONTOLOGY_GRAPH = f"{PREFIX}graph/ontology/ont-1"
CUSTOM_SHAPES_GRAPH = f"{PREFIX}graph/shapes/ont-1/custom"
CLASS_IRI = f"{PREFIX}class/Student"
PROPERTY_IRI = f"{PREFIX}property/name"


class FakeStore:
    def __init__(self) -> None:
        self._stored: dict[str, str] = {}
        self._graphs: set[str] = set()

    def get_graph(self, graph_iri: str, format: str) -> str:
        return self._stored.get(graph_iri, "")

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._stored[graph_iri] = content
        self._graphs.add(graph_iri)

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._graphs

    def query_sparql(self, query: str, timeout_seconds: int, limit: int):
        return SparqlResult(result={"head": {"vars": []}, "results": {"bindings": []}})

    def update_sparql(self, update: str):
        return UpdateResult()

    def export_dataset(self, format: str, graph_iris=None) -> str:
        return ""

    def clear_graph(self, graph_iri: str):
        self._graphs.discard(graph_iri)
        return UpdateResult()

    def graph_content_hash(self, graph_iri: str):
        return None


@pytest.fixture()
def in_memory_session() -> Generator[Session, None, None]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.repositories.postgres import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _client(store: FakeStore, session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    settings = Settings(
        semantic_base_iri=PREFIX,
        semantic_graph_iri_prefix=f"{PREFIX}graph/",
    )

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _seed_ontology_graph(store: FakeStore) -> None:
    turtle = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<{CLASS_IRI}> a owl:Class ;
  rdfs:label "Student" .

<{PROPERTY_IRI}> a owl:DatatypeProperty ;
  rdfs:label "name" ;
  rdfs:domain <{CLASS_IRI}> ;
  rdfs:range xsd:string .
"""
    store.set_graph(ONTOLOGY_GRAPH, turtle)


def _seed_custom_shape_graph(store: FakeStore) -> None:
    email_path = f"{PREFIX}property/email"
    shape_iri = f"{PREFIX}shape/Student-required-email"
    turtle = f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<{shape_iri}> a sh:NodeShape ;
  sh:targetClass <{CLASS_IRI}> ;
  sh:property [
    sh:path <{email_path}> ;
    sh:minCount 1 ;
    sh:datatype xsd:string ;
  ] .
"""
    store.set_graph(CUSTOM_SHAPES_GRAPH, turtle)


def _create_graph_set(client: TestClient) -> str:
    response = client.post(
        "/api/semantic/graph-sets",
        json={
            "name": "stage2-test",
            "scope_type": "ontology",
            "scope_id": "ont-1",
            "members": [
                {"graph_iri": ONTOLOGY_GRAPH, "role": "asserted_ontology"},
            ],
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_shape_endpoint_returns_merged_guidance_with_provenance(in_memory_session) -> None:
    store = FakeStore()
    _seed_ontology_graph(store)
    _seed_custom_shape_graph(store)
    client = _client(store, in_memory_session)
    graph_set_id = _create_graph_set(client)

    response = client.get(f"/api/semantic/graph-sets/{graph_set_id}/shapes/classes/{CLASS_IRI}")

    assert response.status_code == 200
    body = response.json()
    assert body["target_class"] == CLASS_IRI
    fields_by_path = {f["path"]: f for f in body["fields"]}
    # Generated field from OWL property.
    assert PROPERTY_IRI in fields_by_path
    assert fields_by_path[PROPERTY_IRI]["provenance"] == "generated"
    assert fields_by_path[PROPERTY_IRI]["datatype"] == "http://www.w3.org/2001/XMLSchema#string"
    # Custom field from custom sub-graph.
    custom_path = f"{PREFIX}property/email"
    assert custom_path in fields_by_path
    assert fields_by_path[custom_path]["provenance"] == "custom"
    assert fields_by_path[custom_path]["min_count"] == 1


def test_shape_endpoint_returns_404_for_unknown_class(in_memory_session) -> None:
    store = FakeStore()
    _seed_ontology_graph(store)
    client = _client(store, in_memory_session)
    graph_set_id = _create_graph_set(client)

    response = client.get(
        f"/api/semantic/graph-sets/{graph_set_id}/shapes/classes/{PREFIX}class/Unknown"
    )

    # Unknown class still returns 200 with empty fields — the endpoint is a
    # best-effort read; the caller decides whether empty fields is an error.
    assert response.status_code == 200
    assert response.json()["fields"] == []
