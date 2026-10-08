"""Production self-check mechanics over actual governed SPARQL query results."""

import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository, SparqlResult
from app.services.scoped_sparql_query import ScopedSparqlQueryService
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_query_scope import ResolvedOntologyScope, SemanticQueryScope
from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.protocol_mechanics import MODEL_CHECK_QUERY, inspect_model_associations


ROOT = Path(__file__).resolve().parents[2]
EX = "https://example.test/"
OP = Settings().semantic_base_iri.rstrip("/") + "/vocab/"
GRAPH = EX + "graph"


class Store:
    def __init__(self):
        self.dataset = Dataset()

    def query_sparql(self, query, **kwargs):
        result = json.loads(self.dataset.query(query).serialize(format="json"))
        return SparqlResult(result=result)


def scope(signature="sig-1", ontology_id="ontology-1", graph=GRAPH):
    return SemanticQueryScope(
        project_id="project-1", mode="ontologies", status="complete",
        ontologies=(ResolvedOntologyScope(
            ontology_id=ontology_id, ontology_name="Test",
            workspace_version="workspace-1", source_signature=signature,
            graph_iris=(graph,), graph_assertion_kinds={graph: "asserted"}, derived_state={},
        ),),
    )


def node(store, name, kind=OWL.NamedIndividual, graph=GRAPH):
    iri = URIRef(EX + name)
    store.dataset.graph(URIRef(graph)).add((iri, RDF.type, kind))
    store.dataset.graph(URIRef(graph)).add((iri, URIRef(OP + "id"), Literal(name)))
    return iri


def read(store, offset=0, limit=1000, selected=None, hidden=()):
    selected = selected or scope()
    service = ScopedSparqlQueryService(
        SimpleNamespace(resolve=lambda **kwargs: selected), store, Settings(),
        access_view=SemanticAccessView(
            requires_filtering=bool(hidden), _unauthorized_iris=frozenset(hidden),
            _member_ontology_ids={iri: "ontology-1" for iri in hidden},
        ),
    )
    request = {
        "project_id": "project-1", "scope_mode": "ontologies",
        "ontology_ids": [s.ontology_id for s in selected.ontologies],
        "query": MODEL_CHECK_QUERY.replace("{asserted_graphs}", " ".join(
            f"<{g}>" for s in selected.ontologies for g in s.graph_iris
        )) + f"\nOFFSET {offset}", "result_limit": limit,
    }
    try:
        response = {"ok": True, "data": service.query(**request)}
    except Exception:
        response = {"ok": False, "error": {"code": "scope_not_ready"}}
    return {"request": request, "response": response}


def inspect(pages, final, focus=None, ids=None):
    return inspect_model_associations(
        project_id="project-1", ontology_ids=ids or ["ontology-1"],
        read_pages=pages, final_read=final, semantic_base_iri=Settings().semantic_base_iri,
        focus_iris=focus,
    )


def test_actual_query_incoming_predicate_business_types_and_self_link():
    store = Store()
    a, b, predicate, orphan, parent, child = [node(store, n) for n in
                                            ("a", "b", "predicate", "orphan", "parent", "child")]
    g = store.dataset.graph(URIRef(GRAPH))
    g.add((a, predicate, b))
    g.add((child, RDF.type, parent))
    g.add((orphan, URIRef(EX + "self"), orphan))
    g.add((orphan, RDFS.label, Literal("https://example.test/a")))
    result = inspect([read(store)], read(store, limit=1))
    assert result["coverage"] == "complete"
    assert [item["resource_iri"] for item in result["candidates"]] == [str(orphan)]
    assert result["semantic_verdict"] == "not_evaluated"
    assert not result.get("pass") and not result.get("writes")
    assert result["connected_resource_iris"] == sorted(map(str, [a, b, predicate, parent, child]))


@pytest.mark.parametrize("reference", [
    {"target_iri": EX + "b"}, {"target_iris": [EX + "b"]},
    {"nested": [{"definition_ref": "b"}]},
])
def test_actual_formal_json_references(reference):
    store = Store()
    a, b = node(store, "a"), node(store, "b")
    store.dataset.graph(URIRef(GRAPH)).add(
        (a, URIRef(OP + "actionDefinition"), Literal(json.dumps(reference)))
    )
    result = inspect([read(store)], read(store, limit=1))
    assert result["candidates"] == []
    assert result["connected_resource_iris"] == [str(a), str(b)]


@pytest.mark.parametrize("predicate,payload", [
    (OP + "actionDefinition", {"description": EX + "b"}),
    (EX + "arbitraryJson", {"target_iri": EX + "b"}),
])
def test_arbitrary_literals_never_create_associations(predicate, payload):
    store = Store()
    a = node(store, "a")
    node(store, "b")
    store.dataset.graph(URIRef(GRAPH)).add((a, URIRef(predicate), Literal(json.dumps(payload))))
    assert len(inspect([read(store)], read(store, limit=1))["candidates"]) == 2


def test_missing_and_ambiguous_references_are_actionable_not_connections():
    store = Store()
    a = node(store, "a")
    b = node(store, "b")
    store.dataset.graph(URIRef(GRAPH)).add((b, URIRef(OP + "id"), Literal("a")))
    store.dataset.graph(URIRef(GRAPH)).add((a, URIRef(OP + "ruleDefinition"), Literal(
        json.dumps({"inputs": [{"definition_ref": "a"}, {"target_iri": EX + "missing"}]}))))
    result = inspect([read(store)], read(store, limit=1))
    assert len(result["unresolved_references"]) == 2
    assert len(result["candidates"]) == 2
    assert result["unresolved_references"][0]["field_path"].startswith("inputs[")


def test_over_500_resources_paging_repair_and_unchanged_side_scope():
    store = Store()
    # A business resource outside the old 500-node canvas still participates.
    for index in range(501):
        node(store, f"n{index:03}")
    g = store.dataset.graph(URIRef(GRAPH))
    g.add((URIRef(EX + "n500"), URIRef(EX + "uses"), URIRef(EX + "n000")))
    pages, offset = [], 0
    while True:
        page = read(store, offset=offset, limit=500)
        pages.append(page)
        data = page["response"]["data"]
        offset += len(data["result"]["results"]["bindings"])
        if not data["truncated"]:
            break
    final = read(store, limit=1)
    partial = inspect(pages[:1], final)
    assert partial["coverage"] == "partial"
    assert all(c["reason"] == "association_not_observed_in_partial_read" for c in partial["candidates"])
    result = inspect(pages, final)
    assert result["coverage"] == "complete"
    assert result["checked_count"] == 501
    assert EX + "n500" in result["connected_resource_iris"]
    # A semantic owner chooses a source-grounded correction; the helper cannot write it.
    g.add((URIRef(EX + "n001"), URIRef(EX + "uses"), URIRef(EX + "n000")))
    repaired = inspect([read(store, limit=2000)], read(store, limit=1))
    assert EX + "n001" not in {c["resource_iri"] for c in repaired["candidates"]}
    assert EX + "n002" in {c["resource_iri"] for c in repaired["candidates"]}
    assert repaired["semantic_verdict"] == "not_evaluated"


@pytest.mark.parametrize("mutation", ["drift", "scope", "failure", "wrong_query", "missing_page"])
def test_recoverable_feedback_never_claims_complete(mutation):
    store = Store()
    node(store, "a")
    pages, final = [read(store)], read(store, limit=1)
    if mutation == "drift":
        final = read(store, limit=1, selected=scope("sig-2"))
    elif mutation == "scope":
        pages[0]["response"]["data"]["scope"]["project_id"] = "other-project"
    elif mutation == "failure":
        pages[0]["response"] = {"ok": False, "error": {"code": "forbidden"}}
    elif mutation == "wrong_query":
        pages[0]["request"]["query"] = "SELECT ?subject WHERE { ?subject ?p ?o }"
    else:
        pages[0]["request"]["query"] = pages[0]["request"]["query"].replace("OFFSET 0", "OFFSET 20")
    result = inspect(pages, final)
    assert result["coverage"] == "partial" and result["issues"]
    assert result["candidates"] == []
    assert inspect([read(store)], read(store, limit=1))["coverage"] == "complete"


def test_cross_ontology_association_and_focus_do_not_expand_business_cleanup():
    store = Store()
    a = node(store, "a")
    other_graph = EX + "other-graph"
    b = node(store, "b", graph=other_graph)
    node(store, "old-independent", graph=other_graph)
    store.dataset.graph(URIRef(other_graph)).add((b, URIRef(EX + "uses"), a))
    selected = scope()
    selected = SemanticQueryScope(
        project_id=selected.project_id, mode=selected.mode, status=selected.status,
        ontologies=selected.ontologies + scope(ontology_id="ontology-2", graph=other_graph).ontologies,
    )
    result = inspect([read(store, selected=selected)], read(store, limit=1, selected=selected),
                     focus=[str(a)], ids=["ontology-1", "ontology-2"])
    assert result["checked_count"] == 1 and result["candidates"] == []
    assert result["connected_resource_iris"] == [str(a)]


def test_active_task_mounts_only_production_roles_and_advertises_actual_reader():
    config = load_multi_slice_team_configuration(
        ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml",
        ROOT / "modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml",
    )
    source = next(s for s in config.task.role_sources if s.path.name == "r4-0-024-model-check-contract.json")
    assert set(source.roles) == {"coordinator", "modeling", "protocol"}
    assert "semantic_sparql_query" in config.task.protocol_tools
    contract = json.loads(source.path.read_text())
    assert contract["scan"]["query"] == MODEL_CHECK_QUERY
    assert contract["semantic_verdict_owner"] == "modeling"
    for role in source.roles:
        text = (ROOT / f"modeling_team/agent-packages/{role}/instructions.md").read_text()
        assert "R4.0-024" in text and "terminal" in text.split("R4.0-024", 1)[1]


def test_native_facade_dispatches_read_only_tool_and_recovers_from_bad_input():
    path = ROOT / "modeling_team/protocol_retrieval_mcp.py"
    spec = importlib.util.spec_from_file_location("r4024_facade", path)
    facade = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(facade)
    finally:
        sys.path.pop(0)
    assert "inspect_model_associations" in {
        tool["name"] for tool in facade.handle({"method": "tools/list"})["result"]["tools"]
    }
    store = Store()
    node(store, "a")
    arguments = {
        "project_id": "project-1", "ontology_ids": ["ontology-1"],
        "read_pages": [read(store)], "final_read": read(store, limit=1),
        "semantic_base_iri": Settings().semantic_base_iri,
    }
    call = {"id": 1, "method": "tools/call", "params": {
        "name": "inspect_model_associations", "arguments": {},
    }}
    assert facade.handle(call)["error"]["code"] == -32602
    call["params"]["arguments"] = arguments
    result = facade.handle(call)["result"]["structuredContent"]
    assert result["coverage"] == "complete" and len(result["candidates"]) == 1


def test_real_governed_denial_does_not_leak_protected_nodes():
    store = Store()
    secret = node(store, "protected-resource")
    blocked = read(store, hidden=[str(secret)])
    assert blocked["response"]["ok"] is False
    result = inspect([blocked], blocked)
    assert result["coverage"] == "partial" and result["candidates"] == []
    assert str(secret) not in json.dumps(result)


def test_declared_predicate_use_with_literal_and_independent_components():
    store = Store()
    a, b, c, d = [node(store, name) for name in ("a", "b", "c", "d")]
    prop = node(store, "property", kind=OWL.DatatypeProperty)
    graph = store.dataset.graph(URIRef(GRAPH))
    graph.add((a, prop, Literal("a value")))
    graph.add((b, URIRef(EX + "uses"), c))
    result = inspect([read(store)], read(store, limit=1))
    assert [item["resource_iri"] for item in result["candidates"]] == [str(d)]
    assert str(prop) in result["connected_resource_iris"]


def test_generic_vocabulary_declarations_do_not_become_business_candidates():
    store = Store()
    node(store, "business")
    graph = store.dataset.graph(URIRef(GRAPH))
    graph.add((OWL.Thing, RDF.type, OWL.Class))
    graph.add((URIRef(OP + "id"), RDF.type, OWL.DatatypeProperty))
    result = inspect([read(store)], read(store, limit=1))
    assert result["checked_count"] == 1
    assert result["candidates"] == [{"resource_iri": EX + "business", "reason": "no_observed_association"}]


@pytest.mark.skipif(os.getenv("RUN_R4024_RDF_LIVE") != "1", reason="opt-in isolated live RDF dependency")
def test_live_oxigraph_scan_repair_and_cleanup():
    """Uses the real scoped service and engine, with an owned disposable graph.

    The resolver is a bounded test scope, not an authenticated production
    project. This proves engine/scan behavior, never semantic modeling PASS.
    """
    settings = Settings()
    store = RdfStoreRepository(settings.oxigraph_url)
    graph_iri = EX + "r4024-live-" + uuid4().hex
    fixture = Store()
    a = node(fixture, "a", graph=graph_iri)
    node(fixture, "b", graph=graph_iri)
    g = fixture.dataset.graph(URIRef(graph_iri))
    selected = scope(graph=graph_iri)

    def check():
        return inspect_model_associations(
            project_id="project-1", ontology_ids=["ontology-1"],
            read_pages=[read(store, selected=selected, limit=2),
                        read(store, selected=selected, offset=2, limit=2)],
            final_read=read(store, selected=selected, limit=1),
            semantic_base_iri=settings.semantic_base_iri,
        )

    try:
        store.put_named_graph(graph_iri, g.serialize(format="turtle"), "turtle")
        initial = check()
        assert initial["coverage"] == "complete" and len(initial["candidates"]) == 2
        g.add((a, URIRef(EX + "uses"), URIRef(EX + "b")))
        store.put_named_graph(graph_iri, g.serialize(format="turtle"), "turtle")
        # After repair there are five triples, requiring one more actual page.
        result = inspect_model_associations(
            project_id="project-1", ontology_ids=["ontology-1"],
            read_pages=[read(store, selected=selected, limit=2),
                        read(store, selected=selected, offset=2, limit=2),
                        read(store, selected=selected, offset=4, limit=2)],
            final_read=read(store, selected=selected, limit=1),
            semantic_base_iri=settings.semantic_base_iri,
        )
        assert result["coverage"] == "complete" and result["candidates"] == []
        assert result["semantic_verdict"] == "not_evaluated"
    finally:
        store.drop_named_graph(graph_iri)
        assert not store.graph_exists(graph_iri)
