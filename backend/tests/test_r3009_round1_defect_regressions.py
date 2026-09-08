"""R3.0-009 Round 1 defect regressions (D1, D3, D9, D10).

Each test pins one defect from the shared test plan §8.4 on a real code path:

* D1 — Shape commands and the shape/guidance readers use the same named graph
  (``…/graph/shapes/{ontology}/custom``) and an unreadable graph is never read
  as "no guidance".
* D3 — an absolute ``constraints[].path_id`` is written verbatim as ``sh:path``.
* D9 — ``update_shape`` / ``delete_shape`` remove the ``sh:property`` subtrees
  they own (no orphan constraint nodes).
* D10 — generated shapes carry a stable IRI in the guidance projection.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import SH
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router as semantic_router
from app.core.config import Settings
from app.repositories.models import SemanticGraphRegistryModel, SemanticGraphSetModel
from app.repositories.rdf_store import (
    RdfFormat,
    RdfStoreRepository,
    SparqlResult,
    UpdateResult,
)
from app.services.semantic_command_compiler import compile_command
from app.services.semantic_shape_generator import generate_shapes

PREFIX = "http://ontology-platform.local/semantic/"
GRAPH_PREFIX = f"{PREFIX}graph/"
ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-1"
DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-1"
CUSTOM_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/custom"
GENERATED_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/generated"
GRAPH_SET_ID = "gs-round1"
ONTOLOGY_ID = "ont-1"

CLASS_ALPHA = f"{PREFIX}class/Alpha"
PROPERTY_AGE = f"{PREFIX}property/age"
ENTITY_MULTI = f"{PREFIX}entity/n1"

ONTOLOGY_TTL = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <{PREFIX}> .

<{CLASS_ALPHA}> a owl:Class ; rdfs:label "Alpha" .
<{PROPERTY_AGE}> a owl:DatatypeProperty ; rdfs:label "age" ;
  rdfs:domain <{CLASS_ALPHA}> ; rdfs:range xsd:integer .
"""

DATA_TTL = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <{PREFIX}> .

<{ENTITY_MULTI}> a owl:NamedIndividual, <{CLASS_ALPHA}> ;
  rdfs:label "b-multi" ; <{PROPERTY_AGE}> 41 .
"""


class DatasetBackedStore(RdfStoreRepository):
    """Real production delta/read primitives over one in-memory rdflib Dataset.

    ``apply_dataset_delta`` is inherited from the production repository, so the
    store behaves like Oxigraph for writes; only the transport primitives are
    backed by rdflib.
    """

    def __init__(self, graphs: dict[str, str] | None = None) -> None:
        self.dataset = Dataset()
        for graph_iri, content in (graphs or {}).items():
            if content.strip():
                self.dataset.graph(URIRef(graph_iri)).parse(data=content, format="turtle")
        self.updates: list[str] = []
        self.unreadable: set[str] = set()

    def update_sparql(self, update: str):
        self.updates.append(update)
        self.dataset.update(update)
        return UpdateResult()

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        return SparqlResult(result={"head": {"vars": []}, "results": {"bindings": []}})

    def query_read_model(  # noqa: A002
        self, query: str, graph_iris: list[str], timeout_seconds: float, limit: int
    ):
        result = self.dataset.query(query)
        bindings = [{str(key): value for key, value in row.items()} for row in result.bindings]
        return SparqlResult(result={"head": {"vars": []}, "results": {"bindings": bindings}})

    def graph_exists(self, graph_iri: str) -> bool:
        return bool(self.graph(graph_iri))

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        if graph_iri in self.unreadable:
            raise RuntimeError(f"simulated unreadable graph: {graph_iri}")
        return self.graph(graph_iri)

    def set_graph(self, graph_iri: str, content: str) -> None:
        target = self.dataset.graph(URIRef(graph_iri))
        for triple in list(target):
            target.remove(triple)
        target.parse(data=content, format="turtle")

    def clear_graph(self, graph_iri: str):
        self.dataset.remove_graph(URIRef(graph_iri))
        return UpdateResult()

    def export_dataset(self, format: str, graph_iris=None) -> str:  # noqa: A002
        return "".join(self.graph(iri) for iri in self.graph_names())

    def graph_content_hash(self, graph_iri: str):
        return None

    # -- helpers ---------------------------------------------------------
    def graph(self, graph_iri: str) -> str:
        named = self.dataset.graph(URIRef(graph_iri))
        if len(named) == 0:
            return ""
        return named.serialize(format=RdfFormat.TURTLE.value)

    def graph_names(self) -> list[str]:
        return [str(context.identifier) for context in self.dataset.contexts()]

    def named_graph(self, graph_iri: str) -> Graph:
        return self.dataset.graph(URIRef(graph_iri))


def _settings() -> Settings:
    return Settings(
        semantic_base_iri=PREFIX,
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        semantic_product_write_mode="canonical_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=True,
    )


def _client(store: DatasetBackedStore, session: Session, *, quiet: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(semantic_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = _settings
    return TestClient(app, raise_server_exceptions=not quiet)


def _register_graphs(session: Session) -> None:
    from uuid import uuid4

    for graph_iri, category in (
        (ONTOLOGY_GRAPH, "ontology"),
        (DATA_GRAPH, "data"),
        (CUSTOM_SHAPES_GRAPH, "shapes"),
    ):
        session.add(
            SemanticGraphRegistryModel(
                id=str(uuid4()),
                graph_iri=graph_iri,
                category=category,
                semantic_owner_type="ontology",
                semantic_owner_id=ONTOLOGY_ID,
                mutable_by_direct_edit=True,
            )
        )
    session.commit()


def _seed_graph_set(session: Session) -> None:
    graph_set = SemanticGraphSetModel(
        id=GRAPH_SET_ID,
        name="round1-defects",
        scope_type="ontology",
        scope_id=ONTOLOGY_ID,
        status="active",
        source_signature="round1-v1",
    )
    for index, (graph_iri, role) in enumerate(
        (
            (ONTOLOGY_GRAPH, "asserted_ontology"),
            (DATA_GRAPH, "asserted_data"),
            (CUSTOM_SHAPES_GRAPH, "shape_graph_custom"),
        )
    ):
        graph_set.members.append(_member(index, graph_iri, role))
    session.add(graph_set)
    session.commit()


def _member(index: int, graph_iri: str, role: str):
    from app.repositories.models import SemanticGraphSetMemberModel

    return SemanticGraphSetMemberModel(
        id=f"m-{index}",
        graph_iri=graph_iri,
        role=role,
        required=True,
        sort_order=index,
    )


def _apply(client: TestClient, command_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": command_kind,
            "graph_set_id": GRAPH_SET_ID,
            "payload": {"ontology_id": ONTOLOGY_ID, **payload},
            "validate_edit": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# D1 — one shapes graph for writes and reads
# ---------------------------------------------------------------------------


def test_d1_applied_shape_is_projected_by_entity_and_class_guidance(in_memory_session) -> None:
    """The custom sub-graph a Shape command writes is the graph the shape
    endpoint and the entity-shape read model read (§6.1, S08/S17)."""
    store = DatasetBackedStore({ONTOLOGY_GRAPH: ONTOLOGY_TTL, DATA_GRAPH: DATA_TTL})
    _register_graphs(in_memory_session)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)

    applied = _apply(
        client,
        "create_shape",
        {
            "shape_id": "alpha-age",
            "target_class_id": "Alpha",
            "constraints": [{"path_id": "age", "min_count": 1}],
        },
    )
    assert applied["applied"] is True
    shape_graph = store.named_graph(CUSTOM_SHAPES_GRAPH)
    assert (None, SH.targetClass, URIRef(CLASS_ALPHA)) in shape_graph, (
        f"shape must land in {CUSTOM_SHAPES_GRAPH}: {shape_graph.serialize()}"
    )
    # The parent shapes graph stays out of the shape write path.
    assert len(store.named_graph(f"{GRAPH_PREFIX}shapes/{ONTOLOGY_ID}")) == 0

    entity_response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/entity-shape",
        params={"include": "asserted", "entity": ENTITY_MULTI},
    )
    assert entity_response.status_code == 200, entity_response.text
    payload = entity_response.json()["items"][0]
    guidance = payload.get("guidance", payload)
    fields = {field["path"]: field for field in guidance["fields"]}
    assert fields[PROPERTY_AGE]["min_count"] == 1
    assert f"custom:{CUSTOM_SHAPES_GRAPH}" in fields[PROPERTY_AGE]["sources"]

    class_response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/shapes/classes/{CLASS_ALPHA}"
    )
    assert class_response.status_code == 200, class_response.text
    class_fields = {field["path"]: field for field in class_response.json()["fields"]}
    assert class_fields[PROPERTY_AGE]["min_count"] == 1


def test_d1_unreadable_shape_graph_is_not_read_as_empty(in_memory_session) -> None:
    """A broken store read surfaces instead of silently empty guidance."""
    store = DatasetBackedStore(
        {
            ONTOLOGY_GRAPH: ONTOLOGY_TTL,
            DATA_GRAPH: DATA_TTL,
            CUSTOM_SHAPES_GRAPH: f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <{PREFIX}> .
<exshape/broken> a sh:NodeShape ; sh:targetClass <{CLASS_ALPHA}> .
""",
        }
    )
    store.unreadable.add(CUSTOM_SHAPES_GRAPH)
    _register_graphs(in_memory_session)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session, quiet=True)

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/entity-shape",
        params={"include": "asserted", "entity": ENTITY_MULTI},
    )

    assert response.status_code >= 400, response.text


# ---------------------------------------------------------------------------
# D3 — absolute path ids stay verbatim
# ---------------------------------------------------------------------------


def test_d3_absolute_path_id_is_used_verbatim() -> None:
    compiled = compile_command(
        "create_shape",
        {
            "ontology_id": ONTOLOGY_ID,
            "shape_id": "alpha-age",
            "target_class_id": "Alpha",
            "constraints": [{"path_id": PROPERTY_AGE, "min_count": 1}],
        },
        _settings(),
    )
    path_objects = [
        obj
        for subject, predicate, obj, _graph in compiled.delta.inserts
        if predicate == f"<{SH.path}>"
    ]
    assert path_objects == [f"<{PROPERTY_AGE}>"]
    assert not any("%" in term for quad in compiled.delta.inserts for term in quad)

    # A bare local id keeps expanding through the namespace.
    relative = compile_command(
        "create_shape",
        {
            "ontology_id": ONTOLOGY_ID,
            "shape_id": "alpha-age-relative",
            "target_class_id": "Alpha",
            "constraints": [{"path_id": "age", "min_count": 1}],
        },
        _settings(),
    )
    assert [obj for _s, p, obj, _g in relative.delta.inserts if p == f"<{SH.path}>"] == [
        f"<{PROPERTY_AGE}>"
    ]


# ---------------------------------------------------------------------------
# D9 — no orphan sh:property subtrees
# ---------------------------------------------------------------------------


def _seed_platform_shape(client: TestClient, constraints: list[dict[str, Any]]) -> None:
    applied = _apply(
        client,
        "create_shape",
        {
            "shape_id": "alpha-age",
            "target_class_id": "Alpha",
            "constraints": constraints,
        },
    )
    assert applied["applied"] is True


def test_d9_shape_deletes_cascade_to_property_subtree(in_memory_session) -> None:
    store = DatasetBackedStore({ONTOLOGY_GRAPH: ONTOLOGY_TTL, DATA_GRAPH: DATA_TTL})
    _register_graphs(in_memory_session)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    _seed_platform_shape(
        client,
        [
            {"path_id": "age", "min_count": 1, "datatype": "integer"},
            {"path_id": "status", "enum_values": ["a", "b"]},
        ],
    )
    shape_graph = store.named_graph(CUSTOM_SHAPES_GRAPH)
    assert list(shape_graph.subjects(SH.path, None)), "expected constraint nodes"
    assert list(shape_graph.subjects(SH["in"], None)), "expected the sh:in list nodes"

    _apply(client, "delete_shape", {"shape_id": "alpha-age"})

    remaining = store.named_graph(CUSTOM_SHAPES_GRAPH)
    assert len(remaining) == 0, remaining.serialize()
    assert list(remaining.subjects(SH.path, None)) == []
    assert list(remaining.subjects(URIRef(f"{SH}first"), None)) == []


def test_d9_update_shape_leaves_no_stale_constraints(in_memory_session) -> None:
    store = DatasetBackedStore({ONTOLOGY_GRAPH: ONTOLOGY_TTL, DATA_GRAPH: DATA_TTL})
    _register_graphs(in_memory_session)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    _seed_platform_shape(
        client,
        [
            {"path_id": "age", "min_count": 1, "datatype": "integer"},
            {"path_id": "status", "enum_values": ["a", "b"]},
        ],
    )

    _apply(
        client,
        "update_shape",
        {
            "shape_id": "alpha-age",
            "target_class_id": "Alpha",
            "constraints": [{"path_id": "age", "max_count": 4}],
        },
    )

    graph = store.named_graph(CUSTOM_SHAPES_GRAPH)
    assert (None, SH.maxCount, None) in graph
    assert (None, SH["in"], None) not in graph, "old sh:in list must be cascaded away"
    assert (None, SH.datatype, None) not in graph, "replaced constraint must not survive"
    paths = list(graph.objects(None, SH.path))
    assert paths == [URIRef(PROPERTY_AGE)]


# ---------------------------------------------------------------------------
# D10 — generated shapes carry stable IRIs
# ---------------------------------------------------------------------------


def test_d10_generated_shape_iris_are_stable_and_referenceable() -> None:
    ontology = Graph()
    ontology.parse(data=ONTOLOGY_TTL, format="turtle")

    shapes = generate_shapes(ontology, base_iri=GENERATED_SHAPES_GRAPH)

    node_shapes = sorted(str(node) for node in shapes.subjects(SH.targetClass, None))
    assert node_shapes == [f"{GENERATED_SHAPES_GRAPH}#Alpha"]
    property_shapes = list(shapes.objects(None, SH.property))
    assert property_shapes and all(isinstance(node, URIRef) for node in property_shapes)
    assert str(property_shapes[0]).startswith(f"{GENERATED_SHAPES_GRAPH}#Alpha/")
