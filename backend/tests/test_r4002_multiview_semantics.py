"""R4.0-002 developer contracts: neutral translation, real RDF and governed readback."""

import pytest
from rdflib import Dataset, URIRef

from app.core.config import Settings
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
from modeling_team.protocol_mechanics import translate_candidate_to_batches
from test_r3009_unified_semantic_graph import (
    _DatasetStore,
    _client,
    _read_model,
    _seed_graph_set,
    ONTOLOGY_ID,
    NS,
)


def _item(identifier, kind, semantic):
    return {"item_id": identifier, "item_kind": kind, "semantic": semantic}


def candidate():
    def definition(role, meaning, scope):
        return {"semantic_role": role, "business_meaning": meaning, "applicability": scope}

    items = [
        _item(
            "class-a",
            "class",
            {
                "class_id": "Shared",
                "label": "工单",
                "semantic_definition": definition("object", "共享工单定义", "服务业务"),
            },
        ),
        _item(
            "class-b",
            "class",
            {
                "class_id": "Special",
                "superclass": "Shared",
                "semantic_definition": definition("object", "工单的正式子类", "集合包含已确认"),
            },
        ),
        _item(
            "p-participates",
            "predicate",
            {
                "predicate": "participates",
                "predicate_kind": "relation",
                "semantic_definition": definition("relationship", "从角色指向参与内容", "业务参与"),
            },
        ),
        _item("p-context", "predicate", {"predicate": "inContext", "predicate_kind": "relation"}),
        _item(
            "p-definition",
            "predicate",
            {"predicate": "usesDefinition", "predicate_kind": "relation"},
        ),
        _item(
            "p-predicate", "predicate", {"predicate": "usesPredicate", "predicate_kind": "relation"}
        ),
        _item(
            "p-source", "predicate", {"predicate": "relationSource", "predicate_kind": "relation"}
        ),
        _item(
            "p-target", "predicate", {"predicate": "relationTarget", "predicate_kind": "relation"}
        ),
        _item(
            "role",
            "entity",
            {
                "entity_id": "reviewer",
                "aliases": ["审查人"],
                "values": {"label": "审核员"},
                "semantic_definition": definition("business_role", "负责审核业务内容", "售后"),
            },
        ),
        _item(
            "context-one",
            "entity",
            {
                "entity_id": "context-one",
                "values": {"label": "售后上下文"},
                "semantic_definition": definition("context", "售后用途", "售后流程"),
            },
        ),
        _item(
            "context-two", "entity", {"entity_id": "context-two", "values": {"label": "制造上下文"}}
        ),
        _item(
            "object-one",
            "entity",
            {
                "entity_id": "definition-one",
                "classes": ["Shared", "Special"],
                "values": {"label": "单据"},
                "semantic_definition": definition("object", "服务单据定义", "售后"),
            },
        ),
        _item(
            "object-two",
            "entity",
            {
                "entity_id": "definition-two",
                "values": {"label": "单据"},
                "semantic_definition": definition("object", "制造单据定义", "制造"),
            },
        ),
        _item(
            "local",
            "entity",
            {
                "entity_id": "local",
                "values": {"label": "售后审核职责"},
                "semantic_definition": {
                    **definition("local_usage", "售后审核须人工复核", "仅售后上下文"),
                    "unknowns": ["时限待确认"],
                    "not_applicable": ["制造审批"],
                    "conflicting_meanings": ["两个时限口径待确认"],
                },
            },
        ),
    ]
    links = [
        ("context-one", "usesDefinition", {"definition_ref": "class-a"}),
        ("context-two", "usesDefinition", {"definition_ref": "class-a"}),
        ("reviewer", "participates", "definition-one"),
        ("local", "inContext", "context-one"),
        ("local", "relationSource", "reviewer"),
        ("local", "relationTarget", "definition-one"),
        ("local", "usesPredicate", {"definition_ref": "p-participates"}),
    ]
    items.extend(
        _item(f"r-{i}", "relation", {"subject": s, "predicate": p, "object": o})
        for i, (s, p, o) in enumerate(links)
    )
    return {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": "r4002-v1",
        "scope": "approved-project",
        "constraints": [],
        "items": items,
    }


def _materialize(candidate_value):
    plan = translate_candidate_to_batches(candidate_value)
    assert not plan["conflicts"]
    store = _DatasetStore()
    store.dataset = Dataset()
    store.graphs = {}
    handler = ModelingCommandHandlerRegistry(Settings())
    for batch in plan["batches"]:
        for item in batch["items"]:
            prepared = handler.prepare(
                batch_id=batch["client_batch_id"],
                ontology_id=ONTOLOGY_ID,
                client_item_id=item["client_item_id"],
                command_kind=item["command_kind"],
                payload=item["payload"],
            )
            for s, p, o, g in prepared.compiled.delta.inserts:
                store.dataset.graph(URIRef(g)).parse(data=f"{s} {p} {o} .", format="turtle")
                store.graphs[g] = "nonempty"
    return plan, store


def test_shared_identity_local_meaning_roles_and_unknowns_roundtrip(in_memory_session):
    session = in_memory_session
    plan, store = _materialize(candidate())
    _seed_graph_set(session)
    client = _client(store, session)
    entities = {x["iri"]: x for x in _read_model(client, "entity-list")["items"]}
    assert len(entities) == 6
    assert entities[f"{NS}entity/reviewer"]["class_iris"] == []
    assert len(entities[f"{NS}entity/definition-one"]["class_iris"]) == 2
    local = entities[f"{NS}entity/local"]["detail_fields"]["semantic_definition"]
    assert local["unknowns"] == ["时限待确认"]
    assert local["not_applicable"] == ["制造审批"]
    assert local["conflicting_meanings"] == ["两个时限口径待确认"]
    assert "detail_fields" not in entities[f"{NS}entity/context-two"]
    assert (
        entities[f"{NS}entity/reviewer"]["detail_fields"]["semantic_definition"]["semantic_role"]
        == "business_role"
    )
    classes = {x["iri"]: x for x in _read_model(client, "class-detail")["items"]}
    assert (
        classes[f"{NS}class/Shared"]["detail_fields"]["semantic_definition"]["business_meaning"]
        == "共享工单定义"
    )
    assert (
        entities[f"{NS}entity/definition-one"]["detail_fields"]["semantic_definition"]
        != entities[f"{NS}entity/definition-two"]["detail_fields"]["semantic_definition"]
    )
    props = {x["iri"]: x for x in _read_model(client, "property-list")["items"]}
    assert (
        props[f"{NS}property/participates"]["detail_fields"]["semantic_definition"][
            "business_meaning"
        ]
        == "从角色指向参与内容"
    )
    triples = list(
        store.dataset.quads(
            (None, URIRef(f"{NS}property/usesDefinition"), URIRef(f"{NS}class/Shared"), None)
        )
    )
    assert len(triples) == 2
    assert (
        len(
            [
                i
                for b in plan["batches"]
                for i in b["items"]
                if i["payload"].get("class_id") == "Shared"
            ]
        )
        == 1
    )
    for model in ("entity-detail", "ontology-schema-summary", "relation-type-list"):
        assert any(
            "semantic_definition" in item.get("detail_fields", {})
            for item in _read_model(client, model)["items"]
        )
    for iri in (f"{NS}class/Shared", f"{NS}entity/reviewer", f"{NS}property/participates"):
        response = client.get(f"/api/semantic/resources/{iri}", params={"graph_set_id": "gs-009"})
        assert response.status_code == 200, response.text
        assert "semantic_definition" in response.json()["properties"]


def test_definition_patch_clear_and_invalid_values():
    for payload in ({"unknowns": "missing"}, {"semantic_role": ""}, {"unknown_field": "x"}):
        with pytest.raises(InvalidCommandPayload):
            compile_command(
                "create_entity",
                {
                    "ontology_id": ONTOLOGY_ID,
                    "entity_id": "x",
                    "label": "x",
                    "semantic_definition": payload,
                },
                Settings(),
            )
    compiled = compile_command(
        "update_entity",
        {"ontology_id": ONTOLOGY_ID, "entity_id": "x", "semantic_definition": None},
        Settings(),
    )
    assert any("semanticDefinition" in p for _, p, _, _ in compiled.delta.deletes)
    assert not compiled.delta.inserts


def test_duplicate_identity_and_unknown_reference_return_repairable_feedback():
    value = candidate()
    value["items"].append(
        _item("dup", "entity", {"entity_id": "reviewer", "values": {"label": "different"}})
    )
    result = translate_candidate_to_batches(value)
    assert result["conflicts"][0]["code"] == "duplicate_semantic_identity"
    assert result["conflicts"][0]["item_id"] == "dup"
    value = candidate()
    value["items"][-1]["semantic"]["object"] = {"definition_ref": "missing"}
    plan = translate_candidate_to_batches(value)
    assert plan["conflicts"][0]["code"] == "unbound_definition_reference"


def test_exact_resource_read_binds_identity_before_listing_limit(in_memory_session):
    from rdflib import Literal
    from rdflib.namespace import OWL, RDF, RDFS
    from test_r3009_unified_semantic_graph import DATA_GRAPH, ONTOLOGY_GRAPH

    _, store = _materialize(candidate())
    # More than either 200-schema or 500-entity first-page defaults.
    for kind, rdf_type, graph in (
        ("entity", OWL.NamedIndividual, DATA_GRAPH),
        ("class", OWL.Class, ONTOLOGY_GRAPH),
        ("property", OWL.ObjectProperty, ONTOLOGY_GRAPH),
    ):
        for index in range(550):
            subject = URIRef(f"{NS}{kind}/filler-{index:04}")
            store.dataset.graph(URIRef(graph)).add((subject, RDF.type, rdf_type))
            store.dataset.graph(URIRef(graph)).add((subject, RDFS.label, Literal(str(index))))
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    for kind, model in (
        ("entity", "entity-detail"),
        ("class", "class-detail"),
        ("property", "property-list"),
    ):
        iri = f"{NS}{kind}/filler-0549"
        body = _read_model(client, model, entity=iri)
        assert [item["iri"] for item in body["items"]] == [iri]
        response = client.get(f"/api/semantic/resources/{iri}", params={"graph_set_id": "gs-009"})
        assert response.status_code == 200, response.text
        assert response.json()["iri"] == iri
