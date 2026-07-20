"""Regression coverage for OWL/RDFS class compatibility in supported read models."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Dataset, URIRef
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.modeling_batches import router as modeling_batches_router
from app.api.semantic import router as semantic_router
from app.core.config import Settings
from app.repositories.models import SemanticGraphSetMemberModel, SemanticGraphSetModel
from app.services.ontology_workspace import OntologyWorkspaceService


GRAPH_IRI = "http://op.local/semantic/graph/ontology/class-types"
OUT_OF_SCOPE_GRAPH_IRI = "http://op.local/semantic/graph/ontology/out-of-scope"
GRAPH_SET_ID = "gs-class-types"
ONTOLOGY_ID = "ont-class-types"


class _DatasetStore:
    """Execute the production SPARQL template against a real RDFLib dataset."""

    def __init__(self) -> None:
        self.dataset = Dataset()
        self.dataset.graph(URIRef(GRAPH_IRI)).parse(
            data="""
                @prefix ex: <http://example.test/> .
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

                ex:OwlOnly a owl:Class ; rdfs:label "OWL only" .
                ex:RdfsOnly a rdfs:Class ; rdfs:label "RDFS only" .
                ex:DualTyped a owl:Class, rdfs:Class ; rdfs:label "Dual typed" .
            """,
            format="turtle",
        )
        self.dataset.graph(URIRef(OUT_OF_SCOPE_GRAPH_IRI)).parse(
            data="""
                @prefix ex: <http://outside.example.test/> .
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

                ex:OwlOnly a owl:Class ; rdfs:label "Outside OWL" .
                ex:RdfsOnly a rdfs:Class ; rdfs:label "Outside RDFS" .
                ex:DualTyped a owl:Class, rdfs:Class ; rdfs:label "Outside dual" .
            """,
            format="turtle",
        )

    def query_read_model(
        self,
        query: str,
        graph_iris: list[str],
        timeout_seconds: float,
        limit: int,
    ) -> SimpleNamespace:
        assert graph_iris == [GRAPH_IRI]
        assert timeout_seconds > 0
        assert limit > 0
        result = self.dataset.query(query)
        bindings = [{str(key): value for key, value in row.items()} for row in result.bindings]
        return SimpleNamespace(bindings=bindings)


def _seed_graph_set(session: Session) -> None:
    graph_set = SemanticGraphSetModel(
        id=GRAPH_SET_ID,
        name="class-type-regression",
        scope_type="ontology",
        scope_id=ONTOLOGY_ID,
        status="active",
        source_signature="class-type-regression-v1",
    )
    graph_set.members.append(
        SemanticGraphSetMemberModel(
            id="member-class-types",
            graph_iri=GRAPH_IRI,
            role="asserted_ontology",
            required=True,
            sort_order=0,
        )
    )
    session.add(graph_set)
    session.commit()


def _client(
    session: Session,
    store: _DatasetStore,
    monkeypatch,
) -> TestClient:
    app = FastAPI()
    app.include_router(semantic_router, prefix="/api")
    app.include_router(modeling_batches_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(semantic_read_mode="canonical")
    monkeypatch.setattr(
        OntologyWorkspaceService,
        "context",
        lambda _self, ontology_id: {
            "state": "ready",
            "ontology_id": ontology_id,
            "default_graph_set_id": GRAPH_SET_ID,
        },
    )
    return TestClient(app)


def _assert_three_unique_classes(response) -> None:
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 3
    assert len({item["iri"] for item in items}) == 3
    assert {item["label"] for item in items} == {"OWL only", "RDFS only", "Dual typed"}
    assert {item["source_graph_iri"] for item in items} == {GRAPH_IRI}


def test_class_read_models_support_owl_rdfs_and_dual_types_once(
    in_memory_session: Session,
    monkeypatch,
) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(in_memory_session, _DatasetStore(), monkeypatch)

    _assert_three_unique_classes(
        client.get(f"/api/ontologies/{ONTOLOGY_ID}/semantic-read-models/classes")
    )
    _assert_three_unique_classes(
        client.get(f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/class-detail")
    )
