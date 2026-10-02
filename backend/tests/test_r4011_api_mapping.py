"""Ordinary API mapping RDF/read contracts; no live business API invocation."""

from copy import deepcopy

from rdflib import URIRef

from app.services.semantic_access import SemanticAccessView
from modeling_team.tests.test_r4011_api_mapping_contract import (
    candidate,
    unified_candidate,
    unified_plan,
    commands,
)
from test_r4002_multiview_semantics import _materialize
from test_r3009_unified_semantic_graph import DATA_GRAPH, NS, _client, _seed_graph_set, _read_model


def objects(graph, source, predicate):
    return set(
        map(
            str,
            graph.objects(URIRef(NS + "entity/" + source), URIRef(NS + "property/" + predicate)),
        )
    )


def test_field_positions_contexts_identifiers_codes_and_variants_roundtrip(in_memory_session):
    value = candidate()
    _, store = _materialize(value)
    store.graphs = {str(g.identifier): g.serialize(format="trig") for g in store.dataset.graphs()}
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    for mapping, field, param, call in [
        ("map-call-original", "path-id", "original", "call-original"),
        ("map-call-replacement", "body-id", "replacement", "call-replacement"),
    ]:
        for p, target in [("forField", field), ("forParameter", param), ("inContext", call)]:
            assert objects(graph, mapping, p) == {NS + "entity/" + target}
    assert objects(graph, "items", "hasElement") == {NS + "entity/element"}
    assert objects(graph, "nested", "hasMember") == {NS + "entity/nested-id"}
    assert objects(graph, "conversion", "forField") == {NS + "entity/timestamp-ms"}
    assert objects(graph, "conversion", "viaProperty") == {NS + "entity/business-time"}
    assert objects(graph, "code-a", "denotesValue") == {NS + "entity/available"}
    assert objects(graph, "code-b", "denotesValue") == {NS + "entity/withdrawn"}
    assert objects(graph, "composite-id", "hasIdentifierMember") == {
        NS + "entity/identity-region",
        NS + "entity/identity-number",
    }
    assert objects(graph, "accepted", "followedByInterface") == {NS + "entity/query-b"}
    assert objects(graph, "binding", "forOperation") == {NS + "operation/reserve-operation"}
    assert not objects(graph, "query-a", "forAction")
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    entities = _read_model(client, "entity-list")["items"]
    query = next(row for row in entities if row["iri"] == NS + "entity/query-a")
    assert query["class_iris"] == []
    for row in value["items"]:
        if row["item_kind"] != "entity":
            continue
        read = client.get(
            "/api/semantic/resources/" + NS + "entity/" + row["item_id"],
            params={"graph_set_id": "gs-009"},
        )
        assert read.status_code == 200, read.text
        data = read.json()["properties"]
        assert data["semantic_definition"] == row["semantic"]["semantic_definition"]
        if "parameter_definition" in row["semantic"]:
            assert data["parameter_definition"] == row["semantic"]["parameter_definition"]
    exported = client.get("/api/semantic/graph-sets/gs-009/export")
    assert exported.status_code == 200
    assert "202 means accepted" in exported.text


def test_governed_api_fields_edges_export_and_filtered_paging(in_memory_session, monkeypatch):
    from app.api import semantic

    _, store = _materialize(candidate())
    store.graphs = {str(g.identifier): g.serialize(format="trig") for g in store.dataset.graphs()}
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    hidden = {NS + "entity/path-id", NS + "entity/lookup-rule", NS + "entity/map-call-original"}
    view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(hidden))
    monkeypatch.setattr(semantic, "_access_view", lambda *_a, **_kw: view)
    for iri in hidden:
        response = client.get("/api/semantic/resources/" + iri, params={"graph_set_id": "gs-009"})
        assert response.status_code == 404
    visible = _read_model(client, "entity-list")
    page = _read_model(client, "entity-list", limit=1)
    assert page["items"] == visible["items"][:1]
    assert page["paging"]["visible_count"] == len(visible["items"])
    for path in (
        "/api/semantic/statements",
        "/api/semantic/graph-sets/gs-009/read-models/entity-relations",
        "/api/semantic/graph-sets/gs-009/export",
    ):
        response = client.get(path, params={"graph_set_id": "gs-009"})
        assert response.status_code == 200
        assert all(iri not in response.text for iri in hidden)
        assert "Path ID locates original" not in response.text


def test_unified_materialization_matches_neutral_graph():
    value = unified_candidate()
    plan = unified_plan(value)
    keys = {i["item_id"] for i in value["items"]}
    neutral = candidate()
    neutral["items"] = [i for i in neutral["items"] if i["item_id"] in keys]
    expected, store = _materialize(neutral)
    assert commands(plan) == commands(expected)
    assert store.dataset.graph(URIRef(DATA_GRAPH))


def test_rename_and_binding_drift_preserve_identity_and_report_semantic_gap():
    value = candidate()
    before, store = _materialize(value)
    modified = deepcopy(value)
    next(i for i in modified["items"] if i["item_id"] == "path-id")["semantic"]["values"][
        "memberName"
    ] = "item_key"
    operation = next(i for i in modified["items"] if i["item_id"] == "reserve-operation")
    operation["semantic"]["tool_bindings"] = operation["semantic"]["tool_bindings"][:1]
    after, _ = _materialize(modified)
    # Both are legal ordinary graphs; a JSON-local binding key is not a governed RDF edge.
    first = {i["client_item_id"]: i["payload"] for i in commands(before)}
    second = {i["client_item_id"]: i["payload"] for i in commands(after)}
    assert first["path-id"]["entity_id"] == second["path-id"]["entity_id"]
    assert second["path-id"]["properties"]["memberName"] == "item_key"
    binding_id = second["binding"]["properties"]["bindingId"]
    assert binding_id not in {b["binding_id"] for b in second["reserve-operation"]["tool_bindings"]}
    assert second["binding"] == first["binding"]  # never automatically selects reserve-v1
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    assert objects(graph, "query-a-v2", "successorOf") == {NS + "entity/query-a"}
