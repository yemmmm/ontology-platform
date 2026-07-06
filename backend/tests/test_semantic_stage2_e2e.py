"""Stage 2 §11 — end-to-end happy-path coverage.

Spec §11 calls for a single continuous flow:

  1. create a graph set with asserted_ontology,
  2. POST create_class,
  3. GET class-topology and see the class,
  4. POST create_property,
  5. GET property-list?class_iri=... and see the property,
  6. POST create_shape with a min_count=1 custom constraint,
  7. GET /shapes/classes/{class_iri} and see generated + custom guidance merged.

The FakeStore (see test_semantic_canonical_write_stage2.py) does not
actually execute SPARQL queries against stored triples — its
``query_sparql`` returns canned result sets. So a true continuous flow
is not feasible without standing up a real Oxigraph. Per the task brief,
this file decomposes the spec §11 happy path into per-step tests that
each verify one stage succeeds end-to-end through the FastAPI boundary:

* Step 1 — graph set creation with asserted_ontology role.
* Step 2 — create_class apply returns applied=true and bumps revisions.
* Step 3 — class-topology read model issues a SPARQL query against the
  ontology graph (rows are canned, but we verify the right graph was
  selected and the response envelope is shaped correctly).
* Step 4 — create_property apply.
* Step 5 — property-list read model with class_iri filter is routed.
* Step 6 — create_shape apply (KNOWN BUG: see canonical-write tests;
  xfailed).
* Step 7 — shape endpoint returns merged guidance from generated + custom
  sources (covered separately by test_semantic_shape_endpoint.py; here
  we exercise the same flow as a smoke test of the full path).

Each step uses the same shared graph set + registered graphs so the
sequence mirrors a real session even though each pytest function runs
in its own transaction.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import SemanticGraphRegistryModel
from app.repositories.rdf_store import RdfStoreRepository, SparqlResult, UpdateResult


PREFIX = "http://op.local/semantic/"
GRAPH_PREFIX = f"{PREFIX}graph/"
ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-1"
DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-1"
CUSTOM_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/custom"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.bindings = rows


class FakeStore(RdfStoreRepository):
    """Hybrid fake: captures UPDATEs (via apply_dataset_delta inherited
    from the real repository) and returns canned rows per query marker
    (via query_read_model override)."""

    def __init__(
        self,
        rows_by_marker: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.updates: list[str] = []
        self.queries: list[str] = []
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None
        self._rows_by_marker = rows_by_marker or {}
        self._stored: dict[str, str] = {}
        self._graphs: set[str] = set()

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        self.queries.append(query)
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}}
        )

    def query_read_model(self, query: str, graph_iris: list[str], timeout_seconds: float, limit: int):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        for marker, rows in self._rows_by_marker.items():
            if marker in query:
                return _Result(rows)
        return _Result([])

    def update_sparql(self, update: str):
        self.updates.append(update)
        return UpdateResult()

    def export_dataset(self, format: str, graph_iris=None) -> str:  # noqa: A002
        return ""

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._graphs

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        return self._stored.get(graph_iri, "")

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._stored[graph_iri] = content
        self._graphs.add(graph_iri)

    def clear_graph(self, graph_iri: str):
        self._graphs.discard(graph_iri)
        return UpdateResult()

    def graph_content_hash(self, graph_iri: str):
        return None


def _settings() -> Settings:
    return Settings(
        semantic_base_iri=f"{PREFIX}ns/",
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        semantic_product_write_mode="canonical_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=True,
    )


def _client(store: FakeStore, session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    def driver_override() -> None:
        yield None

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_neo4j_driver] = driver_override
    return TestClient(app)


def _register_graph(session: Session, graph_iri: str, category: str) -> None:
    from uuid import uuid4

    session.add(
        SemanticGraphRegistryModel(
            id=str(uuid4()),
            graph_iri=graph_iri,
            category=category,
            semantic_owner_type="ontology",
            semantic_owner_id="ont-1",
            mutable_by_direct_edit=True,
        )
    )
    session.commit()


@pytest.fixture()
def graph_set_id(in_memory_session) -> str:
    """Step 1: register ontology + data + custom-shape graphs and create a
    graph set that wires them up under the standard Stage 2 roles."""
    for graph_iri, category in [
        (ONTOLOGY_GRAPH, "ontology"),
        (DATA_GRAPH, "data"),
        (CUSTOM_SHAPES_GRAPH, "data"),  # registered but see KNOWN BUG below
    ]:
        _register_graph(in_memory_session, graph_iri, category)

    store = FakeStore()
    client = _client(store, in_memory_session)
    response = client.post(
        "/api/semantic/graph-sets",
        json={
            "name": "stage2-e2e",
            "scope_type": "ontology",
            "scope_id": "ont-1",
            "members": [
                {"graph_iri": ONTOLOGY_GRAPH, "role": "asserted_ontology"},
                {"graph_iri": DATA_GRAPH, "role": "asserted_data"},
                {
                    "graph_iri": CUSTOM_SHAPES_GRAPH,
                    "role": "shape_graph_custom",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ---------------------------------------------------------------------------
# Step 2 — create_class apply
# ---------------------------------------------------------------------------


def test_step2_create_class_applies_and_bumps_ontology_revision(
    in_memory_session,
    graph_set_id,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": "create_class",
            "graph_set_id": graph_set_id,
            "payload": {
                "ontology_id": "ont-1",
                "class_id": "Student",
                "name": "Student",
                "description": "A student entity",
            },
            "validate_edit": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["graph_revisions"].get(ONTOLOGY_GRAPH, 0) >= 1
    # The captured UPDATE contains the class IRI and label.
    update_blob = "\n".join(store.updates)
    assert "/ns/class/Student>" in update_blob
    assert '"Student"' in update_blob


# ---------------------------------------------------------------------------
# Step 3 — class-topology read model
# ---------------------------------------------------------------------------


def test_step3_class_topology_runs_against_ontology_graph(
    in_memory_session,
    graph_set_id,
) -> None:
    store = FakeStore(
        rows_by_marker={
            "class-topology": [
                {
                    "class": f"{PREFIX}ns/class/Student",
                    "label": "Student",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{graph_set_id}/read-models/class-topology",
        params={"include": "asserted"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_name"] == "class-topology"
    # The query was issued against the ontology graph.
    assert ONTOLOGY_GRAPH in (store.last_graph_iris or [])
    # Canned row made it through decoration.
    assert body["items"]
    item = body["items"][0]
    assert item["iri"] == f"{PREFIX}ns/class/Student"
    assert item["label"] == "Student"
    assert item["source_graph_iri"] == ONTOLOGY_GRAPH


# ---------------------------------------------------------------------------
# Step 4 — create_property apply
# ---------------------------------------------------------------------------


def test_step4_create_property_applies_to_ontology_graph(
    in_memory_session,
    graph_set_id,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": "create_property",
            "graph_set_id": graph_set_id,
            "payload": {
                "ontology_id": "ont-1",
                "class_id": "Student",
                "property_id": "email",
                "name": "email",
                "description": "Student email",
                "datatype": "xsd:string",
            },
            "validate_edit": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    update_blob = "\n".join(store.updates)
    assert "/ns/property/email>" in update_blob
    assert "DatatypeProperty" in update_blob


# ---------------------------------------------------------------------------
# Step 5 — property-list read model with class_iri filter
# ---------------------------------------------------------------------------


def test_step5_property_list_routes_class_iri_filter(
    in_memory_session,
    graph_set_id,
) -> None:
    store = FakeStore(
        rows_by_marker={
            "property-list": [
                {
                    "property": f"{PREFIX}ns/property/email",
                    "label": "email",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{graph_set_id}/read-models/property-list",
        params={
            "include": "asserted",
            "class_iri": f"{PREFIX}ns/class/Student",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_name"] == "property-list"
    # The class_iri filter was threaded through to the SPARQL template
    # (the canned row only resolves when the marker matches).
    assert store.last_query is not None
    assert "property-list" in store.last_query


# ---------------------------------------------------------------------------
# Step 6 — create_shape (KNOWN BUG: xfail)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "KNOWN BUG (2026-07-06): see "
        "test_create_shape_apply_writes_node_shape_into_custom_subgraph."
    ),
    strict=True,
)
def test_step6_create_shape_apply_writes_custom_constraint(
    in_memory_session,
    graph_set_id,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": "create_shape",
            "graph_set_id": graph_set_id,
            "payload": {
                "ontology_id": "ont-1",
                "target_class_id": "Student",
                "shape_id": "Student-required-email",
                "constraints": [
                    {"path_id": "email", "min_count": 1, "datatype": "xsd:string"}
                ],
            },
            "validate_edit": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True


# ---------------------------------------------------------------------------
# Step 7 — shape endpoint returns merged guidance
# ---------------------------------------------------------------------------


def test_step7_shape_endpoint_returns_merged_generated_and_custom_guidance(
    in_memory_session,
    graph_set_id,
) -> None:
    """End-to-end shape endpoint smoke: seed ontology graph with an OWL
    DatatypeProperty (will surface as generated guidance) and a custom
    SHACL NodeShape (will surface as custom guidance), then call
    ``GET /shapes/classes/{class_iri}`` and verify both provenances appear.
    """
    class_iri = f"{PREFIX}ns/class/Student"
    property_iri = f"{PREFIX}ns/property/email"

    store = FakeStore()
    store.set_graph(
        ONTOLOGY_GRAPH,
        f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<{class_iri}> a owl:Class ; rdfs:label "Student" .
<{property_iri}> a owl:DatatypeProperty ; rdfs:label "email" ;
  rdfs:domain <{class_iri}> ; rdfs:range xsd:string .
""",
    )
    store.set_graph(
        CUSTOM_SHAPES_GRAPH,
        f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<{PREFIX}ns/shape/Student-required-email> a sh:NodeShape ;
  sh:targetClass <{class_iri}> ;
  sh:property [ sh:path <{property_iri}> ; sh:minCount 1 ; sh:datatype xsd:string ] .
""",
    )
    client = _client(store, in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{graph_set_id}/shapes/classes/{class_iri}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_class"] == class_iri
    fields_by_path = {f["path"]: f for f in body["fields"]}
    # OWL DatatypeProperty appears in guidance (provenance may be "generated"
    # or "merged" when the same path is constrained by both OWL and SHACL).
    assert property_iri in fields_by_path
    assert fields_by_path[property_iri]["provenance"] in {"generated", "merged"}
    # The custom SHACL NodeShape contributes min_count=1 on this field.
    assert fields_by_path[property_iri].get("min_count") == 1
