"""R3.0-009 unified semantic graph — mechanical acceptance tests.

Executes the design §8 order against real code paths:

* §4 command entry — zero/multi Class entities, legacy scalar compatibility,
  ``class_membership_conflict``, optional property domain, optional relation
  endpoints and the mutually exclusive Shape targets.
* §6/§9.3 read models — the SPARQL templates run against a real RDFLib
  Dataset, the entity-list aggregation keeps zero-class and multi-class
  entities, the class filter matches formal membership only and the
  class-shape templates project ``target_kind``/``target_value``.
* §6.1 shape chain — target extraction, multi-source guidance merge,
  ``shape_conflict`` through the HTTP surface and real pySHACL detection of
  ``sh:targetNode`` / ``sh:targetSubjectsOf`` violations.

Shared test plan coverage (mechanically verifiable parts): S01-S06, S15-S18,
B01/B10/B11/B13, F08/F15/F16, R01/R03/R04/R13.
"""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Dataset, Graph, URIRef
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router as semantic_router
from app.core.config import Settings
from app.repositories.models import SemanticGraphSetMemberModel, SemanticGraphSetModel
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import (
    ClassMembershipConflict,
    InvalidCommandPayload,
    ShapeTargetConflict,
    compile_command,
)
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_shape_guidance_reader import (
    entity_class_iris,
    entity_subject_predicates,
    extract_shape_guidance_for_targets,
)
from app.services.semantic_validation import SemanticValidationService

PREFIX = "http://ontology-platform.local/semantic/"
# Settings.semantic_base_iri default — compiler resource IRIs below must match it.
NS = PREFIX
GRAPH_PREFIX = f"{PREFIX}graph/"
ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-1"
DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-1"
CUSTOM_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/custom"
WORKSPACE_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1"
GENERATED_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/generated"
GRAPH_SET_ID = "gs-009"
ONTOLOGY_ID = "ont-1"

CLASS_ALPHA = f"{NS}class/Alpha"
CLASS_BETA = f"{NS}class/Beta"
CLASS_BARE = f"{NS}class/Bare"
PROPERTY_AGE = f"{NS}property/age"
PROPERTY_NOTE = f"{NS}property/note"
RELATION_RELATED = f"{NS}relation-related"
ENTITY_ZERO = f"{NS}entity/n0"
ENTITY_MULTI = f"{NS}entity/n1"
ENTITY_LEGACY = f"{NS}entity/n2"
ENTITY_BAD = f"{NS}entity/n9"

ONTOLOGY_TTL = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix op: <{PREFIX}vocab/> .
@prefix ex: <{NS}> .

<{CLASS_ALPHA}> a owl:Class ; rdfs:label "Alpha" ; op:id "alpha" .
<{CLASS_BETA}> a owl:Class ; rdfs:label "Beta" ; op:id "beta" .
<{CLASS_BARE}> a owl:Class ; rdfs:label "Bare" .
<{PROPERTY_AGE}> a owl:DatatypeProperty ; rdfs:label "age" ;
  rdfs:domain <{CLASS_ALPHA}> ; rdfs:range xsd:integer .
<{PROPERTY_NOTE}> a owl:DatatypeProperty ; rdfs:label "note" .
<{RELATION_RELATED}> a owl:ObjectProperty ; rdfs:label "related" .
"""

DATA_TTL = f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix op: <{PREFIX}vocab/> .
@prefix ex: <{NS}> .

<{ENTITY_ZERO}> a owl:NamedIndividual ; op:id "n0" ; rdfs:label "c-zero" ;
  <{PROPERTY_NOTE}> "zero note" .
<{ENTITY_MULTI}> a owl:NamedIndividual, <{CLASS_ALPHA}>, <{CLASS_BETA}> ;
  op:id "n1" ; rdfs:label "b-multi" ;
  <{PROPERTY_AGE}> 41 ; <{RELATION_RELATED}> <{ENTITY_ZERO}> .
<{ENTITY_LEGACY}> a owl:NamedIndividual, <{CLASS_BARE}> ;
  op:id "n2" ; rdfs:label "a-legacy" .
"""

CUSTOM_SHAPES_TTL = f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <{NS}> .

<{NS}shape/node-shape> a sh:NodeShape ;
  sh:targetNode <{ENTITY_ZERO}> ;
  sh:property [ sh:path <{PROPERTY_NOTE}> ; sh:minCount 1 ; sh:datatype xsd:string ] .

<{NS}shape/subjects-shape> a sh:NodeShape ;
  sh:targetSubjectsOf <{RELATION_RELATED}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:maxCount 2 ] .

<{NS}shape/class-shape> a sh:NodeShape ;
  sh:targetClass <{CLASS_ALPHA}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:minCount 1 ] .
"""


# ---------------------------------------------------------------------------
# Harness — a real RDFLib Dataset behind the read-model contract
# ---------------------------------------------------------------------------


class _DatasetStore:
    """Runs production templates and serves graphs as the real store would."""

    def __init__(
        self,
        *,
        data: str = DATA_TTL,
        custom_shapes: str = CUSTOM_SHAPES_TTL,
        ontology: str = ONTOLOGY_TTL,
    ) -> None:
        self.graphs: dict[str, str] = {
            ONTOLOGY_GRAPH: ontology,
            DATA_GRAPH: data,
            CUSTOM_SHAPES_GRAPH: custom_shapes,
        }
        self.dataset = Dataset()
        for graph_iri, content in self.graphs.items():
            if content.strip():
                self.dataset.graph(URIRef(graph_iri)).parse(data=content, format="turtle")

    def set_graph(self, graph_iri: str, content: str) -> None:
        self.graphs[graph_iri] = content
        self.dataset.graph(URIRef(graph_iri)).parse(data=content, format="turtle")

    def graph_exists(self, graph_iri: str) -> bool:
        return bool(self.graphs.get(graph_iri, "").strip())

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        return self.graphs.get(graph_iri, "")

    def query_read_model(
        self,
        query: str,
        graph_iris: list[str],
        timeout_seconds: float,
        limit: int,
    ) -> SimpleNamespace:
        assert timeout_seconds > 0
        assert limit > 0
        result = self.dataset.query(query)
        bindings = [{str(key): value for key, value in row.items()} for row in result.bindings]
        return SimpleNamespace(bindings=bindings)

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        return SimpleNamespace(result={"head": {"vars": []}, "results": {"bindings": []}})


def _seed_graph_set(
    session: Session, members: list[tuple[str, str]] | None = None
) -> None:
    graph_set = SemanticGraphSetModel(
        id=GRAPH_SET_ID,
        name="unified-semantic-graph",
        scope_type="ontology",
        scope_id=ONTOLOGY_ID,
        status="active",
        source_signature="r3009-v1",
    )
    for index, (graph_iri, role) in enumerate(
        members
        or [
            (ONTOLOGY_GRAPH, "asserted_ontology"),
            (DATA_GRAPH, "asserted_data"),
        ]
    ):
        graph_set.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{index}",
                graph_iri=graph_iri,
                role=role,
                required=True,
                sort_order=index,
            )
        )
    session.add(graph_set)
    session.commit()


def _client(store: _DatasetStore, session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(semantic_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings()
    return TestClient(app)


def _read_model(client: TestClient, model_name: str, **params: Any) -> dict[str, Any]:
    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/{model_name}",
        params={"include": "asserted", **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _items_by_iri(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["iri"]: item for item in body["items"]}


# ---------------------------------------------------------------------------
# §4.1/§6.2 — create_entity class membership
# ---------------------------------------------------------------------------


def _compile(command_kind: str, payload: dict[str, Any]) -> Any:
    return compile_command(
        command_kind, {"ontology_id": ONTOLOGY_ID, **payload}, Settings()
    )


def _type_objects(compiled: Any, subject_iri: str) -> list[str]:
    """Class membership IRIs written by one entity command (marker excluded)."""
    return [
        obj[1:-1]
        for subject, predicate, obj, _graph in compiled.delta.inserts
        if subject == f"<{subject_iri}>"
        and predicate == "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
        and "NamedIndividual" not in obj
    ]


def test_create_entity_writes_zero_multi_and_legacy_class_memberships() -> None:
    settings = Settings()

    zero = _compile("create_entity", {"entity_id": "n0", "label": "c-zero"})
    assert zero.metadata["class_iris"] == []
    assert zero.metadata["class_iri"] is None
    # No placeholder Class is invented; only the NamedIndividual marker is written.
    markers = [
        obj for _s, _p, obj, _g in zero.delta.inserts if "NamedIndividual" in obj
    ]
    assert markers == ["<http://www.w3.org/2002/07/owl#NamedIndividual>"]
    assert _type_objects(zero, ENTITY_ZERO) == []

    multi = _compile(
        "create_entity",
        {
            "entity_id": "n1",
            "label": "b-multi",
            "class_iris": [CLASS_BETA, CLASS_ALPHA, CLASS_BETA],
        },
    )
    assert multi.metadata["class_iris"] == sorted({CLASS_ALPHA, CLASS_BETA})
    assert _type_objects(multi, ENTITY_MULTI) == sorted({CLASS_ALPHA, CLASS_BETA})

    legacy = _compile(
        "create_entity",
        {"entity_id": "n2", "label": "a-legacy", "class_iri_or_legacy_id": "Alpha"},
    )
    assert legacy.metadata["class_iris"] == [CLASS_ALPHA]
    assert legacy.metadata["class_iri"] == CLASS_ALPHA
    assert legacy.metadata["class_iri_or_legacy_id"] == CLASS_ALPHA
    assert _type_objects(legacy, ENTITY_LEGACY) == [CLASS_ALPHA]
    assert settings.semantic_base_iri == NS


def test_create_entity_class_membership_conflict_paths() -> None:
    with pytest.raises(ClassMembershipConflict) as mismatch:
        _compile(
            "create_entity",
            {
                "entity_id": "n3",
                "label": "x",
                "class_iri_or_legacy_id": "Alpha",
                "class_iris": [CLASS_BETA],
            },
        )
    assert mismatch.value.code == "class_membership_conflict"
    assert mismatch.value.status_code == 400

    # An empty array next to a scalar is the same conflict, not a zero-class write.
    with pytest.raises(ClassMembershipConflict):
        _compile(
            "create_entity",
            {
                "entity_id": "n4",
                "label": "y",
                "class_iri_or_legacy_id": "Alpha",
                "class_iris": [],
            },
        )

    # Agreement between both spellings stays legal and stays one member.
    agreed = _compile(
        "create_entity",
        {
            "entity_id": "n5",
            "label": "z",
            "class_iri_or_legacy_id": "Alpha",
            "class_iris": [CLASS_ALPHA],
        },
    )
    assert agreed.metadata["class_iris"] == [CLASS_ALPHA]


def test_create_entity_rejects_blank_and_non_string_class_references() -> None:
    # B01: blank, whitespace and non-string class references are rejected with
    # the field named, and nothing is compiled.
    for field, value in (
        ("class_iris", [""]),
        ("class_iris", ["   "]),
        ("class_iris", [42]),
        ("class_iri_or_legacy_id", ""),
        ("class_iri_or_legacy_id", "   "),
        ("class_iri_or_legacy_id", 7),
    ):
        with pytest.raises(InvalidCommandPayload) as rejected:
            _compile(
                "create_entity", {"entity_id": "n8", "label": "v", field: value}
            )
        assert field in str(rejected.value)


def test_create_entity_rejects_named_individual_as_class() -> None:
    named_individual = "http://www.w3.org/2002/07/owl#NamedIndividual"
    for field, value in (
        ("class_iris", [named_individual]),
        ("class_iri_or_legacy_id", "owl:NamedIndividual"),
    ):
        with pytest.raises(InvalidCommandPayload) as rejected:
            _compile(
                "create_entity", {"entity_id": "n6", "label": "w", field: value}
            )
        assert "owl:NamedIndividual" in str(rejected.value)


def test_class_membership_write_back_uses_rdf_type_relation_commands() -> None:
    """R3.0-009 §4.3 / D12 — the only membership path for an existing entity.

    ``create_relation`` / ``delete_relation`` with the ``rdf:type`` predicate
    add and remove one formal Class member at a time; the entity marker stays
    reserved for the entity lifecycle commands.
    """
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    add = _compile(
        "create_relation",
        {
            "source_entity_iri": ENTITY_MULTI,
            "relation_type_iri": rdf_type,
            "target_entity_iri": CLASS_BETA,
        },
    )
    assert add.target_graph_iris == [DATA_GRAPH]
    assert add.delta.inserts == [
        (f"<{ENTITY_MULTI}>", f"<{rdf_type}>", f"<{CLASS_BETA}>", DATA_GRAPH)
    ]
    assert add.delta.deletes == []

    remove = _compile(
        "delete_relation",
        {
            "source_entity_iri": ENTITY_MULTI,
            "relation_type_iri": rdf_type,
            "target_entity_iri": CLASS_BETA,
        },
    )
    assert remove.delta.inserts == []
    assert remove.delta.deletes == [
        (f"<{ENTITY_MULTI}>", f"<{rdf_type}>", f"<{CLASS_BETA}>", DATA_GRAPH)
    ]

    # The owl:NamedIndividual marker is not reachable through relation commands.
    with pytest.raises(InvalidCommandPayload) as marker:
        _compile(
            "create_relation",
            {
                "source_entity_iri": ENTITY_MULTI,
                "relation_type_iri": rdf_type,
                "target_entity_iri": "http://www.w3.org/2002/07/owl#NamedIndividual",
            },
        )
    assert "owl:NamedIndividual" in str(marker.value)

    # update_entity still refuses class_iris: membership is not an entity patch.
    with pytest.raises(InvalidCommandPayload) as patch:
        ModelingCommandHandlerRegistry.validate_payload_shape(
            "update_entity",
            {"entity_iri": ENTITY_MULTI, "label": "kept", "class_iris": [CLASS_BETA]},
        )
    assert "class_iris" in str(patch.value)


# ---------------------------------------------------------------------------
# §4.4 — Shape target selection and payload whitelist
# ---------------------------------------------------------------------------


def test_shape_targets_compile_one_selector_per_shape() -> None:
    node = _compile(
        "create_shape",
        {
            "shape_id": "s-node",
            "target_node_iri": ENTITY_ZERO,
            "constraints": [{"path_id": "note", "min_count": 1}],
        },
    )
    assert node.target_graph_iris == [CUSTOM_SHAPES_GRAPH]
    assert node.metadata["target_kind"] == "node"
    assert node.metadata["target_value"] == ENTITY_ZERO
    assert (f"<{NS}shape/s-node>", "<http://www.w3.org/ns/shacl#targetNode>", f"<{ENTITY_ZERO}>", CUSTOM_SHAPES_GRAPH) in node.delta.inserts

    subjects = _compile(
        "update_shape",
        {"shape_id": "s-subj", "target_subjects_of_iri": RELATION_RELATED},
    )
    assert subjects.metadata["target_kind"] == "subjects_of"
    assert subjects.metadata["target_value"] == RELATION_RELATED
    assert (
        f"<{NS}shape/s-subj>",
        "<http://www.w3.org/ns/shacl#targetSubjectsOf>",
        f"<{RELATION_RELATED}>",
        CUSTOM_SHAPES_GRAPH,
    ) in subjects.delta.inserts
    # Full-definition replacement: the previous selector is deleted, never unioned.
    assert subjects.delta.deletes == [
        (f"<{NS}shape/s-subj>", "?p", "?o", CUSTOM_SHAPES_GRAPH)
    ]

    legacy = _compile(
        "create_shape", {"shape_id": "s-class", "target_class_id": "Alpha"}
    )
    assert legacy.metadata["target_kind"] == "class"
    assert legacy.metadata["target_value"] == CLASS_ALPHA


def test_shape_target_requires_exactly_one_selector() -> None:
    with pytest.raises(ShapeTargetConflict) as missing:
        _compile("create_shape", {"shape_id": "s0"})
    assert missing.value.code == "shape_target_conflict"

    with pytest.raises(ShapeTargetConflict) as both:
        _compile(
            "create_shape",
            {
                "shape_id": "s1",
                "target_node_iri": ENTITY_ZERO,
                "target_subjects_of_iri": RELATION_RELATED,
            },
        )
    assert both.value.code == "shape_target_conflict"

    with pytest.raises(ShapeTargetConflict):
        _compile(
            "update_shape",
            {"shape_id": "s2", "target_class_id": "Alpha", "target_node_iri": ENTITY_ZERO},
        )


def test_shape_target_rejects_blank_and_relative_iris() -> None:
    # F15: an empty string is "absent", not a target; a relative reference is
    # never silently expanded into an IRI.
    for payload in (
        {"shape_id": "s3", "target_node_iri": ""},
        {"shape_id": "s4", "target_subjects_of_iri": "   "},
        {"shape_id": "s5", "target_node_iri": "student-1"},
        {"shape_id": "s6", "target_subjects_of_iri": "ns/rel"},
    ):
        with pytest.raises((ShapeTargetConflict, InvalidCommandPayload)) as rejected:
            _compile("create_shape", payload)
        assert rejected.value.status_code == 400


def test_update_shape_replaces_class_target_with_node_target() -> None:
    # S18: switching the target deletes the previous selector with the whole
    # shape definition instead of unioning both selectors.
    switched = _compile(
        "update_shape",
        {"shape_id": "s-class", "target_node_iri": ENTITY_MULTI},
    )
    predicates = [predicate for _s, predicate, _o, _g in switched.delta.inserts]
    assert "<http://www.w3.org/ns/shacl#targetNode>" in predicates
    assert "<http://www.w3.org/ns/shacl#targetClass>" not in predicates
    assert switched.metadata["target_kind"] == "node"


def test_registry_accepts_009_fields_and_keeps_rejecting_unknowns() -> None:
    registry = ModelingCommandHandlerRegistry(Settings())

    prepared = registry.prepare(
        batch_id="batch-1",
        ontology_id=ONTOLOGY_ID,
        client_item_id="item-1",
        command_kind="create_shape",
        payload={
            "shape_id": "s-node",
            "target_node_iri": ENTITY_ZERO,
            "constraints": [{"path_id": "note", "min_count": 1, "datatype": "string"}],
        },
    )
    # Shape commands write the custom shapes sub-graph, the one graph the
    # shape endpoint reads back (R3.0-009 §6.1 / defect D1).
    assert prepared.compiled.target_graph_iris == [CUSTOM_SHAPES_GRAPH]
    assert {quad[3] for quad in prepared.compiled.delta.inserts} == {CUSTOM_SHAPES_GRAPH}
    assert prepared.compiled.metadata["target_kind"] == "node"

    entity = registry.prepare(
        batch_id="batch-1",
        ontology_id=ONTOLOGY_ID,
        client_item_id="item-2",
        command_kind="create_entity",
        payload={"entity_id": "n1", "label": "b-multi", "class_iris": [CLASS_ALPHA, CLASS_BETA]},
    )
    assert entity.compiled.metadata["class_iris"] == [CLASS_ALPHA, CLASS_BETA]
    assert entity.compiled.target_graph_iris == [DATA_GRAPH]

    unknown_shape = {
        "shape_id": "s-x",
        "target_node_iri": ENTITY_ZERO,
        "target_iri": ENTITY_ZERO,
    }
    with pytest.raises(InvalidCommandPayload) as unknown:
        registry.prepare(
            batch_id="batch-1",
            ontology_id=ONTOLOGY_ID,
            client_item_id="item-3",
            command_kind="create_shape",
            payload=unknown_shape,
        )
    assert "target_iri" in str(unknown.value)

    with pytest.raises(InvalidCommandPayload) as legacy_entity_field:
        registry.prepare(
            batch_id="batch-1",
            ontology_id=ONTOLOGY_ID,
            client_item_id="item-4",
            command_kind="create_entity",
            payload={"entity_id": "n7", "label": "q", "class_id": "Alpha"},
        )
    assert "class_id" in str(legacy_entity_field.value)

    with pytest.raises(ShapeTargetConflict) as combined:
        registry.prepare(
            batch_id="batch-1",
            ontology_id=ONTOLOGY_ID,
            client_item_id="item-5",
            command_kind="create_shape",
            payload={
                "shape_id": "s-y",
                "target_class_id": "Alpha",
                "target_subjects_of_iri": RELATION_RELATED,
            },
        )
    assert "shape_target_conflict" in str(combined.value)
    assert combined.value.code == "shape_target_conflict"
    assert combined.value.fields == ("target_class_id", "target_subjects_of_iri")


def test_property_and_relation_type_accept_optional_endpoints() -> None:
    free_property = _compile(
        "create_property", {"property_id": "note", "name": "note"}
    )
    domains = [
        obj for _s, p, obj, _g in free_property.delta.inserts if p.endswith("domain>")
    ]
    assert domains == []

    typed_property = _compile(
        "create_property",
        {"property_id": "age", "name": "age", "class_id": "Alpha", "datatype": "integer"},
    )
    assert (
        f"<{PROPERTY_AGE}>",
        "<http://www.w3.org/2000/01/rdf-schema#domain>",
        f"<{CLASS_ALPHA}>",
        ONTOLOGY_GRAPH,
    ) in typed_property.delta.inserts

    free_relation = _compile(
        "create_relation_type", {"relation_type_id": "related", "name": "related"}
    )
    endpoints = [
        (predicate, obj)
        for _s, predicate, obj, _g in free_relation.delta.inserts
        if predicate.endswith(("domain>", "range>"))
    ]
    assert endpoints == []

    bound_relation = _compile(
        "create_relation_type",
        {
            "relation_type_id": "related",
            "name": "related",
            "source_class_id": "Alpha",
            "target_class_id": "Beta",
        },
    )
    assert (
        f"<{NS}relation-type/related>",
        "<http://www.w3.org/2000/01/rdf-schema#domain>",
        f"<{CLASS_ALPHA}>",
        ONTOLOGY_GRAPH,
    ) in bound_relation.delta.inserts


# ---------------------------------------------------------------------------
# §6.2/§9.3 — read models over the real templates
# ---------------------------------------------------------------------------


def test_entity_list_aggregates_zero_multi_and_bare_class_entities(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(), in_memory_session)

    body = _read_model(client, "entity-list")
    rows = _items_by_iri(body)

    assert set(rows) == {ENTITY_ZERO, ENTITY_MULTI, ENTITY_LEGACY}
    assert [item["iri"] for item in body["items"]] == [
        ENTITY_LEGACY,
        ENTITY_MULTI,
        ENTITY_ZERO,
    ]

    zero = rows[ENTITY_ZERO]
    assert zero["class_iris"] == []
    assert zero["class_iri"] is None
    assert zero["semantic_id"] == "n0"
    assert zero["entity_iri"] == ENTITY_ZERO

    multi = rows[ENTITY_MULTI]
    assert multi["class_iris"] == [CLASS_ALPHA, CLASS_BETA]
    assert multi["class_iri"] == CLASS_ALPHA
    assert multi["class_label"] == "Alpha"
    assert multi["class_semantic_id"] == "alpha"
    assert "incomplete_class_identity_iris" not in multi

    bare = rows[ENTITY_LEGACY]
    assert bare["class_iris"] == [CLASS_BARE]
    assert bare["class_semantic_id"] is None
    assert bare["incomplete_class_identity_iris"] == [CLASS_BARE]


def test_entity_list_collects_classes_from_a_second_authorized_graph(
    in_memory_session,
) -> None:
    # B13: type edges may live in a different authorized graph than the
    # entity identity; the aggregate still carries the full visible set.
    second_data_graph = f"{GRAPH_PREFIX}data/ont-2"
    _seed_graph_set(
        in_memory_session,
        [
            (ONTOLOGY_GRAPH, "asserted_ontology"),
            (DATA_GRAPH, "asserted_data"),
            (second_data_graph, "asserted_data"),
        ],
    )
    store = _DatasetStore()
    store.set_graph(
        second_data_graph,
        f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <{NS}> .
<{ENTITY_MULTI}> a <{CLASS_BETA}> .
""",
    )
    client = _client(store, in_memory_session)

    body = _read_model(client, "entity-list")
    multi = _items_by_iri(body)[ENTITY_MULTI]
    assert multi["class_iris"] == [CLASS_ALPHA, CLASS_BETA]


def test_entity_search_returns_zero_class_entities_and_filters_by_membership(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(), in_memory_session)

    zero = _read_model(client, "entity-search", q="zero")
    assert [item["iri"] for item in zero["items"]] == [ENTITY_ZERO]
    assert zero["items"][0]["class_iris"] == []
    assert zero["items"][0]["class_iri"] is None
    assert zero["recall"]["match_status"] in {"candidate", "exact"}

    multi = _read_model(client, "entity-search", q="multi")
    assert [item["iri"] for item in multi["items"]] == [ENTITY_MULTI]
    assert multi["items"][0]["class_iris"] == [CLASS_ALPHA, CLASS_BETA]

    for class_iri, expected in (
        (CLASS_ALPHA, [ENTITY_MULTI]),
        (CLASS_BETA, [ENTITY_MULTI]),
        (CLASS_BARE, []),
    ):
        filtered = _read_model(client, "entity-search", q="multi", class_iri=class_iri)
        assert [item["iri"] for item in filtered["items"]] == expected, class_iri

    # A zero-class entity is never a formal member of any class filter.
    none_match = _read_model(
        client, "entity-search", q="zero", class_iri=CLASS_ALPHA
    )
    assert none_match["items"] == []


def test_property_list_anchors_on_declared_domain_only(in_memory_session) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(), in_memory_session)

    unfiltered = _read_model(client, "property-list")
    paths = {item["iri"] for item in unfiltered["items"]}
    assert {PROPERTY_AGE, PROPERTY_NOTE} <= paths

    alpha = _read_model(client, "property-list", class_iri=CLASS_ALPHA)
    assert [item["iri"] for item in alpha["items"]] == [PROPERTY_AGE]
    assert alpha["items"][0]["detail_fields"]["domain"] == CLASS_ALPHA

    # Beta declares no domain at all: nothing implicitly belongs to it.
    beta = _read_model(client, "property-list", class_iri=CLASS_BETA)
    assert beta["items"] == []


def test_class_shape_read_models_project_target_kind_and_value(
    in_memory_session,
) -> None:
    # The custom shapes graph is attached as a source graph so the template
    # reads real shape triples from the Dataset.
    _seed_graph_set(
        in_memory_session,
        [(CUSTOM_SHAPES_GRAPH, "asserted_ontology"), (DATA_GRAPH, "asserted_data")],
    )
    client = _client(_DatasetStore(), in_memory_session)

    body = _read_model(client, "class-shape-custom")
    rows = {(item["iri"], item["detail_fields"]["target_kind"]): item for item in body["items"]}

    node_row = rows[(f"{NS}shape/node-shape", "node")]
    assert node_row["detail_fields"]["target_value"] == ENTITY_ZERO
    subjects_row = rows[(f"{NS}shape/subjects-shape", "subjects_of")]
    assert subjects_row["detail_fields"]["target_value"] == RELATION_RELATED
    class_row = rows[(f"{NS}shape/class-shape", "class")]
    assert class_row["detail_fields"]["target_value"] == CLASS_ALPHA
    assert len(rows) == 3


def test_entity_list_hybrid_recall_keeps_canonical_rows(in_memory_session) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(), in_memory_session)

    body = _read_model(client, "entity-list", q="multi", search_mode="hybrid")
    assert body["recall"]["mode"] == "hybrid"
    items = [item for item in body["items"] if item["iri"] == ENTITY_MULTI]
    assert items, "expected the canonical entity row to survive recall fusion"
    assert items[0]["class_iris"] == [CLASS_ALPHA, CLASS_BETA]
    assert items[0]["match"]["candidate_level"] in {"exact", "lexical_candidate"}


# ---------------------------------------------------------------------------
# §6.1 — shape guidance chain
# ---------------------------------------------------------------------------


def test_extract_shape_guidance_for_targets_matches_all_three_targets() -> None:
    shapes = Graph()
    shapes.parse(data=CUSTOM_SHAPES_TTL, format="turtle")
    data = Graph()
    data.parse(data=DATA_TTL, format="turtle")

    assert entity_class_iris(data, ENTITY_MULTI) == [CLASS_ALPHA, CLASS_BETA]
    assert entity_class_iris(data, ENTITY_ZERO) == []
    assert PROPERTY_NOTE in entity_subject_predicates(data, ENTITY_ZERO)
    assert RELATION_RELATED in entity_subject_predicates(data, ENTITY_MULTI)

    guidance = extract_shape_guidance_for_targets(
        shapes,
        class_iris=[CLASS_ALPHA, CLASS_BETA],
        target_node_iri=ENTITY_MULTI,
        subject_predicates=entity_subject_predicates(data, ENTITY_MULTI),
    )
    assert set(guidance["shape_iris"]) == {
        f"{NS}shape/subjects-shape",
        f"{NS}shape/class-shape",
    }
    matched = {(target["kind"], target["value"]) for target in guidance["targets"]}
    assert ("class", CLASS_ALPHA) in matched
    assert ("subjects_of", RELATION_RELATED) in matched
    assert ("node", ENTITY_ZERO) not in matched

    # The node target only matches the entity it names.
    zero_guidance = extract_shape_guidance_for_targets(
        shapes,
        class_iris=[],
        target_node_iri=ENTITY_ZERO,
        subject_predicates=[PROPERTY_NOTE],
    )
    assert set(zero_guidance["shape_iris"]) == {f"{NS}shape/node-shape"}
    field = zero_guidance["fields"][0]
    assert field["path"] == PROPERTY_NOTE
    assert field["source_shape_iri"] == f"{NS}shape/node-shape"
    assert field["matched_targets"] == [{"kind": "node", "value": ENTITY_ZERO}]


def test_removed_shape_stops_matching_entity_guidance(in_memory_session) -> None:
    # S18: after the node-target shape is deleted from the custom shapes graph
    # it no longer matches the entity, while the other targets keep working.
    _seed_graph_set(in_memory_session)
    kept = f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <{NS}> .

<{NS}shape/subjects-shape> a sh:NodeShape ;
  sh:targetSubjectsOf <{RELATION_RELATED}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:maxCount 2 ] .
"""
    client = _client(_DatasetStore(custom_shapes=kept), in_memory_session)

    body = _read_model(client, "entity-shape", entity=ENTITY_MULTI)
    guidance = body["items"][0].get("guidance", body["items"][0])
    assert f"{NS}shape/node-shape" not in guidance["shape_iris"]
    # The subjects-of shape keeps matching; generated class shapes remain too.
    assert f"{NS}shape/subjects-shape" in guidance["shape_iris"]
    fields = {field["path"]: field for field in guidance["fields"]}
    assert fields[PROPERTY_AGE]["max_count"] == 2


def test_entity_shape_merges_generated_and_custom_without_dropping_constraints(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(), in_memory_session)

    body = _read_model(client, "entity-shape", entity=ENTITY_MULTI)
    payload = body["items"][0]
    guidance = payload.get("guidance", payload)

    assert guidance["entity_iri"] == ENTITY_MULTI
    assert guidance["class_iris"] == [CLASS_ALPHA, CLASS_BETA]
    assert guidance["shape_iris"], "expected matched shape provenance"

    fields = {field["path"]: field for field in guidance["fields"]}
    age = fields[PROPERTY_AGE]
    # Generated (datatype from range), class target (minCount) and subjects-of
    # target (maxCount) all survive the merge on one path.
    assert age["datatype"] == "http://www.w3.org/2001/XMLSchema#integer"
    assert age["min_count"] == 1
    assert age["max_count"] == 2
    # Sources are the two guidance origins (generated + custom), and every
    # still-effective constraint from both is preserved.
    assert age["sources"] == [
        f"generated:{ONTOLOGY_GRAPH}",
        f"custom:{CUSTOM_SHAPES_GRAPH}",
    ]
    assert age["provenance"] == "merged"


def test_entity_shape_conflict_surfaces_as_409_shape_conflict(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session)
    conflicting_shapes = CUSTOM_SHAPES_TTL + f"""

<{NS}shape/conflicting> a sh:NodeShape ;
  sh:targetNode <{ENTITY_MULTI}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:datatype xsd:string ] .
"""
    client = _client(
        _DatasetStore(custom_shapes=conflicting_shapes), in_memory_session
    )

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/entity-shape",
        params={"include": "asserted", "entity": ENTITY_MULTI},
    )
    assert response.status_code == 409, response.text
    assert "shape_conflict" in response.json()["detail"]


# ---------------------------------------------------------------------------
# §6.1 — real pySHACL validation over the new shape targets
# ---------------------------------------------------------------------------


def _validation_service(session: Session, store: _DatasetStore) -> SemanticValidationService:
    _seed_graph_set(session)
    return SemanticValidationService(
        session,
        store,
        Settings(),
        graph_set_service=SemanticGraphSetService(session, Settings()),
    )


def test_shacl_validation_accepts_conforming_new_targets(
    in_memory_session,
) -> None:
    result = _validation_service(in_memory_session, _DatasetStore()).run_validation(
        data_graph_iris=[DATA_GRAPH],
        shape_graph_iris=[CUSTOM_SHAPES_GRAPH],
        graph_set_id=GRAPH_SET_ID,
    )
    assert result["status"] == "succeeded"
    assert result["conforms"] is True
    assert result["summary"]["violations"] == 0


def test_shacl_validation_detects_target_node_violation(in_memory_session) -> None:
    # Drop the note triple the sh:targetNode shape requires; the subject keeps
    # a legal triple so the turtle still parses.
    missing_note = DATA_TTL.replace(
        f'  <{PROPERTY_NOTE}> "zero note" .', '  rdfs:comment "no note" .'
    )
    result = _validation_service(
        in_memory_session, _DatasetStore(data=missing_note)
    ).run_validation(
        data_graph_iris=[DATA_GRAPH],
        shape_graph_iris=[CUSTOM_SHAPES_GRAPH],
        graph_set_id=GRAPH_SET_ID,
    )
    assert result["conforms"] is False
    assert result["summary"]["violations"] >= 1


def test_shacl_validation_detects_target_subjects_of_violation(
    in_memory_session,
) -> None:
    three_ages = DATA_TTL.replace(
        f"  <{PROPERTY_AGE}> 41 ;", f"  <{PROPERTY_AGE}> 41, 42, 43 ;"
    )
    result = _validation_service(
        in_memory_session, _DatasetStore(data=three_ages)
    ).run_validation(
        data_graph_iris=[DATA_GRAPH],
        shape_graph_iris=[CUSTOM_SHAPES_GRAPH],
        graph_set_id=GRAPH_SET_ID,
    )
    assert result["conforms"] is False
    assert result["summary"]["violations"] >= 1


# ---------------------------------------------------------------------------
# Round 2 — D14 lazily materialized graphs read as empty projections, F08
# conflict detection across every still-effective shape of one source graph
# ---------------------------------------------------------------------------


def test_missing_data_graph_is_an_empty_entity_projection(in_memory_session) -> None:
    """D14: a graph set whose data graph was never materialized still answers
    with an empty guidance envelope instead of a store error."""
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(data=""), in_memory_session)

    body = _read_model(client, "entity-shape", entity=ENTITY_MULTI)
    guidance = body["items"][0].get("guidance", body["items"][0])

    assert guidance["entity_iri"] == ENTITY_MULTI
    assert guidance["fields"] == []
    assert guidance["class_iris"] == []
    assert DATA_GRAPH in guidance["missing_graph_iris"]
    # The custom shapes graph is materialized, so it is not reported missing.
    assert CUSTOM_SHAPES_GRAPH not in guidance["missing_graph_iris"]


def test_missing_ontology_graph_is_an_empty_class_projection(in_memory_session) -> None:
    """D14: a missing asserted ontology member graph degrades to an empty
    generated side instead of HTTP 500; the member itself is still listed."""
    _seed_graph_set(in_memory_session)
    client = _client(_DatasetStore(ontology=""), in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/entity-shape",
        params={"include": "asserted", "class_iri": CLASS_ALPHA},
    )
    assert response.status_code == 200, response.text
    body = response.json()["items"][0]
    guidance = body.get("guidance", body)
    # Only the custom shape survives; the generated side (from the missing
    # ontology graph) contributed nothing, so no range datatype is projected.
    fields = {field["path"]: field for field in guidance["fields"]}
    assert set(fields) == {PROPERTY_AGE}
    assert "datatype" not in fields[PROPERTY_AGE]
    assert fields[PROPERTY_AGE]["min_count"] == 1
    assert ONTOLOGY_GRAPH in guidance["missing_graph_iris"]


def test_class_guidance_conflicting_shapes_in_one_graph_raise_409(
    in_memory_session,
) -> None:
    """F08: two still-effective shapes of the same source graph that bind one
    path differently raise ``shape_conflict`` (S17/B13) — the reader must not
    collapse them into a last-writer-wins field before the merge."""
    _seed_graph_set(in_memory_session)
    conflicting = CUSTOM_SHAPES_TTL + f"""

<{NS}shape/alpha-age-string> a sh:NodeShape ;
  sh:targetClass <{CLASS_ALPHA}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:datatype xsd:string ] .
"""
    client = _client(_DatasetStore(custom_shapes=conflicting), in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/shapes/classes/{CLASS_ALPHA}"
    )
    assert response.status_code == 409, response.text
    assert "shape_conflict" in response.json()["detail"]


def test_class_guidance_read_model_surfaces_the_same_conflict(
    in_memory_session,
) -> None:
    """F08: the class branch of the entity-shape read model reports the same
    locatable conflict as the shape endpoint."""
    _seed_graph_set(in_memory_session)
    conflicting = CUSTOM_SHAPES_TTL + f"""

<{NS}shape/alpha-age-string> a sh:NodeShape ;
  sh:targetClass <{CLASS_ALPHA}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:datatype xsd:string ] .
"""
    client = _client(_DatasetStore(custom_shapes=conflicting), in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/read-models/entity-shape",
        params={"include": "asserted", "class_iri": CLASS_ALPHA},
    )
    assert response.status_code == 409, response.text
    assert "shape_conflict" in response.json()["detail"]


def test_class_guidance_keeps_compatible_constraints_from_both_shapes(
    in_memory_session,
) -> None:
    """F08 positive control: two shapes that do not clash contribute every
    constraint, and the class envelope keeps its legacy provenance."""
    _seed_graph_set(in_memory_session)
    compatible = CUSTOM_SHAPES_TTL + f"""

<{NS}shape/alpha-age-pattern> a sh:NodeShape ;
  sh:targetClass <{CLASS_ALPHA}> ;
  sh:property [ sh:path <{PROPERTY_AGE}> ; sh:pattern "^[0-9]+$" ] .
"""
    client = _client(_DatasetStore(custom_shapes=compatible), in_memory_session)

    response = client.get(
        f"/api/semantic/graph-sets/{GRAPH_SET_ID}/shapes/classes/{CLASS_ALPHA}"
    )
    assert response.status_code == 200, response.text
    fields = {
        field["path"]: field for field in response.json()["fields"]
    }
    age = fields[PROPERTY_AGE]
    assert age["min_count"] == 1
    assert age["pattern"] == "^[0-9]+$"
    assert f"custom:{CUSTOM_SHAPES_GRAPH}" in age["sources"]
    assert age["provenance"] in {"custom", "merged"}
