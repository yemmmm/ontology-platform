from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Dataset, Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS

from app.api.deps import get_db_session, get_neo4j_driver, get_settings
from app.api.import_export import router
from app.core.config import Settings
from app.repositories.models import FactClaimModel
from app.services import semantic_export


SETTINGS = Settings(_env_file=None)
NS = semantic_export.namespace_from_settings(SETTINGS)
OP = NS.vocab


def _export_payload() -> dict:
    return {
        "ontology": {
            "id": "ont-1",
            "project_id": "proj-1",
            "current_version_id": "ver-1",
            "name": "Company",
            "description": "Company ontology",
            "status": "draft",
            "external_mappings": {"schema": "https://schema.org/Organization"},
            "created_at": None,
            "updated_at": None,
        },
        "classes": [
            {
                "id": "class-person",
                "ontology_id": "ont-1",
                "name": "Person",
                "normalized_label": "Person",
                "description": None,
                "aliases": ["Human"],
                "parent_class_ids": [],
                "external_mappings": {},
                "created_at": None,
                "updated_at": None,
                "properties": [
                    {
                        "id": "prop-status",
                        "class_id": "class-person",
                        "name": "status",
                        "type": "enum",
                        "description": None,
                        "required": True,
                        "multi_valued": False,
                        "enum_values": ["active", "inactive"],
                        "constraints": {},
                        "external_mappings": {},
                        "created_at": None,
                        "updated_at": None,
                    },
                    {
                        "id": "prop-age",
                        "class_id": "class-person",
                        "name": "age",
                        "type": "number",
                        "description": None,
                        "required": False,
                        "multi_valued": False,
                        "enum_values": [],
                        "constraints": {},
                        "external_mappings": {},
                        "created_at": None,
                        "updated_at": None,
                    },
                ],
            },
            {
                "id": "class-manager",
                "ontology_id": "ont-1",
                "name": "Manager",
                "normalized_label": "Manager",
                "description": None,
                "aliases": [],
                "parent_class_ids": ["class-person"],
                "external_mappings": {},
                "created_at": None,
                "updated_at": None,
                "properties": [],
            },
        ],
        "relation_types": [
            {
                "id": "rel-manages",
                "ontology_id": "ont-1",
                "name": "manages",
                "description": None,
                "aliases": ["supervises"],
                "parent_relation_type_id": None,
                "source_class_id": "class-manager",
                "target_class_id": "class-person",
                "inverse_name": None,
                "normalized_type": "MANAGES",
                "scope_policy": "entity_only",
                "symmetric": False,
                "transitive": True,
                "status": "active",
                "valid_from": None,
                "valid_to": None,
                "external_mappings": {},
                "created_at": None,
                "updated_at": None,
            }
        ],
        "entities": [
            {
                "id": "alice",
                "project_id": "proj-1",
                "ontology_id": "ont-1",
                "ontology_version_id": "ver-1",
                "class_id": "class-manager",
                "class_label": "Manager",
                "name": "Alice",
                "aliases": ["A"],
                "properties": {},
            },
            {
                "id": "bob",
                "project_id": "proj-1",
                "ontology_id": "ont-1",
                "ontology_version_id": "ver-1",
                "class_id": "class-person",
                "class_label": "Person",
                "name": "Bob",
                "aliases": [],
                "properties": {"status": "active", "age": 42},
            },
        ],
        "relations": [
            {
                "id": "relation-1",
                "project_id": "proj-1",
                "ontology_id": "ont-1",
                "ontology_version_id": "ver-1",
                "relation_type_id": "rel-manages",
                "relation_type": "MANAGES",
                "source_entity_id": "alice",
                "target_entity_id": "bob",
                "properties": {},
                "scope": "instance",
                "status": "active",
                "valid_from": None,
                "valid_to": None,
            }
        ],
    }


def _claim(**overrides) -> FactClaimModel:
    values = {
        "id": "claim-1",
        "claim_key": "entity_attribute:bob:age:hash",
        "project_id": "proj-1",
        "ontology_id": "ont-1",
        "ontology_version_id": "ver-1",
        "claim_type": "direct",
        "layer": "entity_attribute",
        "subject": {"entity_id": "bob"},
        "predicate": "age",
        "value": 42,
        "anchor": {"type": "entity", "target_id": "bob"},
        "graph_path": [],
        "evidence_ids": [],
        "generation_reason": "entity_property",
        "confidence": 1.0,
        "audit_status": "pending",
    }
    values.update(overrides)
    return FactClaimModel(**values)


def _graph_from_trig(content: str) -> Graph:
    dataset = Dataset()
    dataset.parse(data=content, format="trig")
    graph = Graph()
    for subject, predicate, object_, _ in dataset.quads((None, None, None, None)):
        graph.add((subject, predicate, object_))
    return graph


def test_semantic_namespace_manifest_is_stable() -> None:
    manifest = semantic_export.semantic_iri_manifest(SETTINGS, "ont-1")
    context = semantic_export.jsonld_context(SETTINGS)

    assert manifest["class"] == "http://ontology-platform.local/semantic/class/{class_id}"
    assert manifest["ontology_graph"].endswith("/graph/ontology/ont-1")
    assert context["owl"] == str(OWL)
    assert context["evidenceStatus"].endswith("/vocab/evidenceStatus")


def test_semantic_export_preserves_schema_data_and_missing_evidence_status() -> None:
    dataset = semantic_export.build_ontology_dataset(_export_payload(), NS, [_claim()], [])
    content = dataset.serialize(format="trig")
    graph = _graph_from_trig(content)

    person = NS.resource("class", "class-person")
    manager = NS.resource("class", "class-manager")
    bob = NS.resource("entity", "bob")
    claim = NS.resource("fact-claim", "claim-1")

    assert (person, RDF.type, OWL.Class) in graph
    assert (person, SKOS.altLabel, Literal("Human")) in graph
    assert (manager, RDFS.subClassOf, person) in graph
    assert (NS.resource("relation-type", "rel-manages"), RDF.type, OWL.TransitiveProperty) in graph
    assert (bob, NS.resource("property", "prop-status"), Literal("active")) in graph
    assert (claim, OP.evidenceStatus, Literal("missing_evidence")) in graph
    assert (claim, OP.missingEvidence, Literal(True)) in graph


def test_shacl_shapes_express_required_enum_and_relation_constraints() -> None:
    graph = semantic_export.build_shacl_shapes(_export_payload(), NS)
    person_shape = NS.resource("shape", "class-person-node")
    manager_shape = NS.resource("shape", "class-manager-node")

    assert (person_shape, RDF.type, SH.NodeShape) in graph
    assert (person_shape, SH.targetClass, NS.resource("class", "class-person")) in graph
    assert any(
        (shape, SH.path, NS.resource("property", "prop-status")) in graph
        and (shape, SH.minCount, Literal(1)) in graph
        for shape in graph.objects(person_shape, SH.property)
    )
    assert any(
        (shape, SH.path, NS.resource("relation-type", "rel-manages")) in graph
        and (shape, SH["class"], NS.resource("class", "class-person")) in graph
        for shape in graph.objects(manager_shape, SH.property)
    )


def test_semantic_export_round_trips_to_compact_projection() -> None:
    dataset = semantic_export.build_ontology_dataset(_export_payload(), NS, [_claim()], [])
    content = dataset.serialize(format="trig")

    projection = semantic_export.compact_projection_from_semantic_export(content, "trig")

    assert projection["classes"] == [
        {"id": "class-manager", "name": "Manager", "aliases": [], "parent_class_ids": ["class-person"]},
        {"id": "class-person", "name": "Person", "aliases": ["Human"], "parent_class_ids": []},
    ]
    assert projection["entities"] == [
        {"id": "alice", "name": "Alice", "class_id": "class-manager", "aliases": ["A"]},
        {"id": "bob", "name": "Bob", "class_id": "class-person", "aliases": []},
    ]
    assert projection["relations"][0]["relation_type_id"] == "rel-manages"
    assert projection["fact_claims"][0]["evidence_status"] == "missing_evidence"


def test_semantic_export_api_returns_rdf_media_type() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
    app.dependency_overrides[get_neo4j_driver] = lambda: SimpleNamespace()
    app.dependency_overrides[get_settings] = lambda: SETTINGS

    with (
        patch.object(semantic_export, "export_ontology_semantic", return_value="@prefix op: <x:> ."),
        patch.object(semantic_export, "export_ontology_shapes", return_value="@prefix sh: <x:> ."),
    ):
        client = TestClient(app)
        export_response = client.get("/api/ontologies/ont-1/semantic-export?format=turtle")
        shapes_response = client.get("/api/ontologies/ont-1/semantic-shapes?format=json-ld")

    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/turtle")
    assert shapes_response.status_code == 200
    assert shapes_response.headers["content-type"].startswith("application/ld+json")


def test_semantic_projection_parse_api() -> None:
    dataset = semantic_export.build_ontology_dataset(_export_payload(), NS, [_claim()], [])
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/semantic/projections:parse",
        json={"format": "trig", "content": dataset.serialize(format="trig")},
    )

    assert response.status_code == 200
    assert response.json()["fact_claims"][0]["evidence_status"] == "missing_evidence"
