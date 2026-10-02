"""R4.0-008 functional contracts over actual SPARQL and declared business data."""

from __future__ import annotations

import json

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDFS, XSD

from app.core.config import Settings
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_context_cursor import ContextCursorCodec
from app.services.semantic_context_query import (
    SemanticContextCursorMismatch,
    SemanticContextQueryError,
    SemanticContextQueryService,
    SemanticContextSnapshotChanged,
)
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_query_scope import SemanticQueryScopeResolver
from test_semantic_context_query import DatasetStore, _principal, _ready_ontology


class NoShapes:
    def read_merged_guidance(self, *args):
        return {"fields": []}


@pytest.fixture
def context(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    dataset = Dataset()
    graph = dataset.graph(URIRef("https://graphs.test/ontology/ontology-1"))
    codec = ContextCursorCodec(secret="r4008-test", stable_secret=True, lifetime_seconds=3600)
    service = SemanticContextQueryService(
        in_memory_session,
        DatasetStore(dataset),
        SemanticQueryScopeResolver(in_memory_session, settings),
        shape_endpoint=NoShapes(),
        cursor_codec=codec,
    )
    vocab = str(namespace_from_settings(settings).vocab)

    def declare(name, role=None, label=None, **definitions):
        iri = URIRef("https://business.test/" + name)
        graph.add((iri, RDFS.label, Literal(label or name)))
        if role:
            definitions["semanticDefinition"] = {
                "semantic_role": role,
                "business_meaning": f"meaning of {name}",
                "unknowns": ["unconfirmed"],
                "not_applicable": ["execution"],
                "conflicting_meanings": [],
            }
        for predicate, value in definitions.items():
            graph.add((iri, URIRef(vocab + predicate), Literal(json.dumps(value))))
        return iri

    def query(queries, **kwargs):
        return service.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=queries,
            search_mode="lexical",
            principal=_principal(),
            **kwargs,
        )

    return service, graph, declare, query, vocab


def identity(item):
    return item["ontology_id"], item["kind"], item["id"]


def drain(query, queries, **kwargs):
    result = query(queries, **kwargs)
    primary = result["primary_matches"]
    rows = list(result["related_context"])
    while cursor := result["context_page"]["next_context_cursor"]:
        result = query(queries, **kwargs, context_cursor=cursor)
        assert result["primary_matches"] == primary
        rows.extend(result["related_context"])
    return rows, result


def test_roles_are_explicit_case_sensitive_primary_only(context):
    service, graph, declare, query, vocab = context
    action = declare("perform", "Action", actionDefinition={"purpose": "perform task"})
    rule = declare("policy", "Rule", ruleDefinition={"rule_category": "constraint"})
    parameter = declare("argument", "Parameter", parameterDefinition={"direction": "input"})
    graph.add((action, URIRef("https://business.test/constrainedBy"), rule))
    graph.add((action, URIRef("https://business.test/hasParameter"), parameter))
    result = query([str(action)], semantic_roles=[" Action ", "Action"], depth=1)
    assert result["query"]["semantic_roles"] == ["Action"]
    assert result["primary_matches"][0]["data"]["semantic_definition"]["unknowns"] == [
        "unconfirmed"
    ]
    related = {
        row["iri"]: row for row in result["related_context"] if row.get("target_kind") == "resource"
    }
    assert related[str(rule)]["data"]["rule_definition"]["rule_category"] == "constraint"
    assert related[str(parameter)]["data"]["parameter_definition"]["direction"] == "input"
    assert query([str(action)], semantic_roles=["action"])["result_status"] == "no_match"
    assert query(["perform"], semantic_roles=["unknown"])["result_status"] == "no_match"
    assert (
        query(["constrainedBy"], resource_types=["relation"], semantic_roles=["Action"])[
            "primary_matches"
        ]
        == []
    )


@pytest.mark.parametrize("roles", [[], [""], ["   "], [1], "Action"])
def test_invalid_role_filters(context, roles):
    with pytest.raises(SemanticContextQueryError, match="semantic_roles"):
        context[3](["example"], semantic_roles=roles)


def test_shared_action_keeps_distinct_calls_bindings_and_typed_facts(context):
    _, graph, declare, query, _ = context
    flow = declare("flow", "Process")
    action = declare("close", "Action")
    call_a = declare("call-a", "Invocation", label="same call")
    call_b = declare("call-b", "Invocation", label="same call")
    for call, source in [(call_a, "original"), (call_b, "repair")]:
        binding = declare("binding-" + source, "Binding", label="same binding")
        graph.add((flow, URIRef("https://business.test/contains"), call))
        graph.add((call, URIRef("https://business.test/invokes"), action))
        graph.add((call, URIRef("https://business.test/binding"), binding))
        graph.add((binding, URIRef("https://business.test/source"), Literal(source, lang="en")))
    full, _ = drain(query, [str(flow)], depth=3, context_limit=3)
    compact, _ = drain(query, [str(flow)], depth=3, context_limit=30, context_detail="compact")
    assert {identity(row) for row in full} == {identity(row) for row in compact}
    assert len(full) == len({identity(row) for row in full})
    resources = [row for row in full if row.get("target_kind") == "resource"]
    assert sum(row["iri"] == str(action) for row in resources) == 1
    assert {str(call_a), str(call_b)} <= {row["iri"] for row in resources}
    facts = [
        row for row in compact if row["data"].get("predicate") == "https://business.test/source"
    ]
    assert {row["data"]["object"] for row in facts} == {"original", "repair"}
    assert all(row["data"]["object_language"] == "en" for row in facts)
    assert all(row["data"]["subject"] for row in facts)


def test_compact_scripts_no_raw_literal_bypass_and_full_anchor_supplement(context):
    _, graph, declare, query, vocab = context
    action = declare("dispatch", "Action")
    definition = {
        "script_source": "return input.amount > 10",
        "script_language": "javascript",
        "version": "v1",
        "unknowns": ["currency"],
        "conflicting_meanings": ["threshold"],
    }
    rule = declare("threshold", "Rule", ruleDefinition=definition)
    graph.add((action, URIRef("https://business.test/policy"), rule))
    full = query([str(action)], depth=1)
    compact = query([str(action)], depth=1, context_detail="compact")
    assert {identity(row) for row in full["related_context"]} == {
        identity(row) for row in compact["related_context"]
    }
    # At depth two the raw annotation fact is explicitly included and stripped.
    compact = query([str(action)], depth=2, context_detail="compact")
    assert "return input.amount" not in json.dumps(compact)
    resource = next(row for row in compact["related_context"] if row["iri"] == str(rule))
    assert resource["projection"]["omitted_fields"] == ["data.rule_definition.script_source"]
    assert resource["data"]["rule_definition"]["unknowns"] == ["currency"]
    raw = next(
        row
        for row in compact["related_context"]
        if row["data"].get("predicate") == vocab + "ruleDefinition"
    )
    assert "object" not in raw["data"]
    assert raw["projection"]["omitted_fields"] == ["data.object"]
    supplement = query([str(rule)], context_detail="compact", depth=0)
    assert supplement["primary_matches"][0]["data"]["rule_definition"] == definition


def test_hidden_bridge_and_nested_script_references_cannot_disclose_or_traverse(context):
    service, graph, declare, query, vocab = context
    start = declare("start", "Process")
    hidden = declare("hidden", "Binding")
    public = declare("public", "Object")
    script = declare("script", "Rule", ruleDefinition={"script_source": "x", "refs": [str(hidden)]})
    graph.add((start, URIRef("https://business.test/next"), hidden))
    graph.add((hidden, URIRef("https://business.test/next"), public))
    graph.add((start, URIRef("https://business.test/next"), script))
    graph.add((public, URIRef("https://business.test/value"), Literal("secret through bridge")))
    service.access_view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({str(hidden)})
    )
    result = query([str(start)], depth=3, context_detail="compact")
    rendered = json.dumps(result)
    assert str(hidden) not in rendered
    assert str(script) not in rendered
    assert str(public) not in rendered
    assert "secret through bridge" not in rendered
    assert result["context_page"]["expansion"]["status"] == "complete"
    assert query([str(hidden)]) == query(["https://business.test/absent"]) | {
        "query": query([str(hidden)])["query"]
    }


def test_fact_output_traverses_relation_without_returning_it(context):
    _, graph, declare, query, _ = context
    root = declare("root", "Process")
    mid = declare("mid", "Object")
    graph.add((root, URIRef("https://business.test/next"), mid))
    graph.add((mid, URIRef("https://business.test/amount"), Literal(42, datatype=XSD.integer)))
    # Lexical fact root is a statement: use its subject, never its predicate,
    # as the graph expansion anchor.
    graph.add((root, URIRef("https://business.test/marker"), Literal("uniqueRootMarker")))
    result = query(["uniqueRootMarker"], depth=2, resource_types=["fact"])
    assert result["primary_matches"][0]["data"]["subject"] == str(root)
    assert any(row["data"].get("object") == "42" for row in result["related_context"])
    assert all(row["kind"] == "fact" for row in result["related_context"])


def test_context_only_cursor_restores_second_match_page_and_next_match(context):
    _, graph, declare, query, _ = context
    for index in range(3):
        root = declare(f"root-{index}", "Action", label="shared")
        for fact in range(6):
            graph.add(
                (
                    root,
                    URIRef(f"https://business.test/fact-{fact}"),
                    Literal(f"value-{index}-{fact}"),
                )
            )
    opts = dict(semantic_roles=["Action"], limit=1, context_limit=2)
    first = query(["shared"], **opts)
    second = query(["shared"], **opts, match_cursor=first["matches_page"]["next_match_cursor"])
    rows = list(second["related_context"])
    result = second
    while token := result["context_page"]["next_context_cursor"]:
        result = query(["shared"], **opts, context_cursor=token)
        assert result["primary_matches"] == second["primary_matches"]
        rows.extend(result["related_context"])
    assert len(rows) == len({identity(row) for row in rows})
    assert {row["data"].get("object") for row in rows} >= {f"value-1-{fact}" for fact in range(6)}
    third = query(["shared"], **opts, match_cursor=result["matches_page"]["next_match_cursor"])
    assert third["primary_matches"][0]["iri"].endswith("root-2")


def test_budget_partial_is_distinct_from_terminal_page_and_hidden_rows(context, monkeypatch):
    import app.services.semantic_context_query as module

    service, graph, declare, query, _ = context
    root = declare("root", "Action")
    graph.add((root, URIRef("https://business.test/value"), Literal("one")))
    # One statement and one root description fill the budget exactly.
    monkeypatch.setattr(module, "CONTEXT_EXPANSION_BUDGET", 3)
    complete = query([str(root)], depth=1)
    assert complete["context_page"]["expansion"]["status"] == "complete"
    graph.add((root, URIRef("https://business.test/value-2"), Literal("two")))
    partial = query([str(root)], depth=1)
    assert partial["context_page"]["expansion"] == {
        "status": "partial",
        "reason": "expansion_budget_reached",
    }
    assert partial["context_page"]["next_context_cursor"] is None
    assert partial["truncated"] is False
    assert "context_expansion_incomplete" in {w["code"] for w in partial["warnings"]}
    for hidden_index in range(10):
        hidden = declare(f"hidden-{hidden_index}")
        graph.add((root, URIRef("https://business.test/edge"), hidden))
    service.access_view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset(
            f"https://business.test/hidden-{index}" for index in range(10)
        ),
    )
    assert query([str(root)], depth=1) == partial
    assert query([str(root)], depth=0)["context_page"]["expansion"]["status"] == "not_requested"
    assert (
        query([str(root)], context_limit=0)["context_page"]["expansion"]["status"]
        == "not_requested"
    )


def test_cursors_bind_roles_and_visible_protection_membership(context):
    service, graph, declare, query, _ = context
    root = declare("root", "Action")
    child = declare("child", "Object")
    graph.add((root, URIRef("https://business.test/edge"), child))
    result = query([str(root)], context_limit=1, semantic_roles=["Action"])
    token = result["context_page"]["next_context_cursor"]
    with pytest.raises(SemanticContextCursorMismatch):
        query([str(root)], context_limit=1, semantic_roles=["Object"], context_cursor=token)
    service.access_view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({str(child)})
    )
    with pytest.raises(SemanticContextSnapshotChanged):
        query([str(root)], context_limit=1, semantic_roles=["Action"], context_cursor=token)


def test_hidden_membership_changes_do_not_invalidate_visible_cursor(context):
    service, graph, declare, query, _ = context
    root = declare("root", "Action")
    for i in range(4):
        graph.add((root, URIRef(f"https://business.test/f-{i}"), Literal(i)))
    result = query([str(root)], context_limit=1)
    token = result["context_page"]["next_context_cursor"]
    service.access_view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({"https://business.test/unrelated"})
    )
    resumed = query([str(root)], context_limit=1, context_cursor=token)
    assert resumed["primary_matches"] == result["primary_matches"]


def test_lexical_raw_chunks_filter_and_dedupe_before_candidate_window(context, monkeypatch):
    import app.services.semantic_context_query as module

    service, graph, declare, query, _ = context
    monkeypatch.setattr(module, "RDF_READ_CHUNK_SIZE", 3)
    for i in range(20):
        declare(f"irrelevant-{i}", "Object", label="needle")
    expected = declare("wanted", "Action", label="needle")
    result = query(["needle"], semantic_roles=["Action"], depth=0, limit=1)
    assert [item["iri"] for item in result["primary_matches"]] == [str(expected)]
    assert result["recall"]["completeness"] == "complete"
    assert "candidate_window_incomplete" not in {w["code"] for w in result["warnings"]}
    service.access_view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset(f"https://business.test/irrelevant-{i}" for i in range(20)),
    )
    assert query(["needle"], semantic_roles=["Action"], depth=0, limit=1) == result


def test_annotation_ambiguity_and_invalid_json_remain_unconfirmed(context):
    _, graph, declare, query, vocab = context
    root = declare("root", "Action")
    graph.add((root, URIRef(vocab + "ruleDefinition"), Literal("broken JSON")))
    graph.add((root, URIRef(vocab + "parameterDefinition"), Literal('{"direction":"in"}')))
    graph.add((root, URIRef(vocab + "parameterDefinition"), Literal('{"direction":"out"}')))
    result = query([str(root)])
    data = result["primary_matches"][0]["data"]
    assert "rule_definition" not in data
    assert "parameter_definition" not in data
    assert {d["code"] for d in data["annotation_read_diagnostics"]} == {
        "invalid_annotation",
        "ambiguous_annotation",
    }
    assert any(row["data"].get("object") == "broken JSON" for row in result["related_context"])


def test_lexical_qualified_window_marks_only_an_extra_visible_identity(context, monkeypatch):
    import app.services.semantic_context_query as module

    service, graph, declare, query, _ = context
    monkeypatch.setattr(module, "RDF_READ_CHUNK_SIZE", 2)
    for i in range(4):
        declare(f"a-{i}", "Action", label="needle")
    query(["needle"], semantic_roles=["Action"], depth=0)
    scope = service.scope_resolver.resolve(
        project_id="project-1", scope_mode="ontologies", ontology_ids=["ontology-1"]
    )
    service._candidate_window_incomplete = False
    items = service._qualified_lexical_candidates(
        scope, "needle", ["needle"], 3, {"instance"}, {"asserted"}
    )
    assert len(items) == 3
    assert service._candidate_window_incomplete is True
    service._candidate_window_incomplete = False
    service.access_view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({"https://business.test/a-3"})
    )
    items = service._qualified_lexical_candidates(
        scope, "needle", ["needle"], 3, {"instance"}, {"asserted"}
    )
    assert len(items) == 3
    assert service._candidate_window_incomplete is False


def test_cross_ontology_visible_definition_and_hidden_definition_bridge(context, in_memory_session):
    service, graph, declare, _, vocab = context
    settings = service.settings
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-2")
    other = service.rdf_store.dataset.graph(URIRef("https://graphs.test/ontology/ontology-2"))
    root = declare("start", "Process")
    target = URIRef("https://business.test/foreign")
    other.add((target, RDFS.label, Literal("foreign model")))
    other.add(
        (
            target,
            URIRef(vocab + "semanticDefinition"),
            Literal('{"semantic_role":"Object","unknowns":["owner"]}'),
        )
    )
    graph.add((root, URIRef("https://business.test/next"), target))
    other.add((target, URIRef("https://business.test/note"), Literal("foreign fact")))
    opts = dict(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1", "ontology-2"],
        queries=[str(root)],
        search_mode="lexical",
        depth=2,
        principal=_principal(),
    )
    result = service.query_multi(**opts)
    resource = next(row for row in result["related_context"] if row["iri"] == str(target))
    assert resource["ontology_id"] == "ontology-2"
    assert resource["data"]["semantic_definition"]["unknowns"] == ["owner"]
    assert any(row["data"].get("object") == "foreign fact" for row in result["related_context"])
    # Hide by a reference in the target's definition in its actual Ontology.
    secret = "https://business.test/secret"
    other.add(
        (target, URIRef(vocab + "ruleDefinition"), Literal(json.dumps({"reference": secret})))
    )
    service.access_view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({secret})
    )
    hidden = service.query_multi(**opts)
    assert str(target) not in json.dumps(hidden)
    assert "foreign fact" not in json.dumps(hidden)


def test_statement_anchor_does_not_expand_every_user_of_its_predicate(context):
    _, graph, declare, query, _ = context
    one, two = declare("one"), declare("two")
    predicate = URIRef("https://business.test/value")
    graph.add((one, predicate, Literal("unique-needle")))
    graph.add((two, predicate, Literal("unrelated-needle")))
    result = query(["unique-needle"], resource_types=["fact"], depth=2)
    assert all(row["data"].get("subject") != str(two) for row in result["related_context"])


def test_cycle_and_overlapping_roots_keep_shortest_root_paths(context):
    _, graph, declare, query, _ = context
    first, second = (
        declare("first", "Action", label="common"),
        declare("second", "Action", label="common"),
    )
    shared = declare("shared", "Object")
    for root in [first, second]:
        graph.add((root, URIRef("https://business.test/next"), shared))
    graph.add((shared, URIRef("https://business.test/next"), first))
    result = query(["common"], semantic_roles=["Action"], depth=3)
    shared_row = next(row for row in result["related_context"] if row["iri"] == str(shared))
    assert shared_row["root_paths"] == [
        {"root_match_id": str(first), "graph_distance": 1},
        {"root_match_id": str(second), "graph_distance": 1},
    ]
    assert len(result["related_context"]) == len(
        {identity(row) for row in result["related_context"]}
    )


def test_rdf_dependency_failure_is_not_a_complete_empty_result(context):
    from app.repositories.rdf_store import SparqlQueryTimeout

    service, graph, declare, query, _ = context

    def unavailable(*args, **kwargs):
        raise SparqlQueryTimeout("fixture timed out")

    service.rdf_store.query_sparql = unavailable
    with pytest.raises(SparqlQueryTimeout):
        query(["example"])


def test_rest_role_filter_and_expansion_contract(context, in_memory_session):
    from test_semantic_context_query_api import _client

    service, _, declare, _, _ = context
    declare("action", "Action", label="shared")
    declare("object", "Object", label="shared")
    client = _client(in_memory_session, service.settings, store=lambda: service.rdf_store)
    body = {
        "project_id": "project-1",
        "scope_mode": "ontologies",
        "ontology_ids": ["ontology-1"],
        "queries": ["shared"],
        "search_mode": "lexical",
        "semantic_roles": [" Action ", "Action"],
        "depth": 0,
    }
    response = client.post("/api/semantic/context:query", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["semantic_roles"] == ["Action"]
    assert data["query"]["result_scope"] == "authorized_query_scope"
    assert len(data["primary_matches"]) == 1
    assert data["context_page"]["expansion"]["status"] == "not_requested"
    for roles in [[], [""], [" "]]:
        response = client.post(
            "/api/semantic/context:query", json={**body, "semantic_roles": roles}
        )
        assert response.status_code == 422


def test_generic_related_mapping_metric_and_operation_projection(context):
    from rdflib.namespace import RDF
    from rdflib.util import from_n3
    from app.services.operation_semantics import operation_quads, validate_operation_payload
    from test_operation_semantics import _operation

    service, graph, declare, query, vocab = context
    book = declare("Book", "Object")
    mapping = declare("catalog-mapping", "Mapping")
    metric = declare("loan-metric", "Metric")
    graph.add((mapping, RDF.type, URIRef(vocab + "TableMapping")))
    graph.add((mapping, URIRef(vocab + "mappedClass"), book))
    graph.add((mapping, URIRef(vocab + "tableName"), Literal("library_catalog")))
    graph.add((metric, RDF.type, URIRef(vocab + "MetricDefinition")))
    graph.add((metric, URIRef(vocab + "metricMeasure"), book))
    graph.add((metric, URIRef(vocab + "metricGrain"), Literal(json.dumps([str(book)]))))
    graph.add((metric, URIRef(vocab + "metricAggregation"), Literal("count")))
    operation = validate_operation_payload(
        _operation(
            operation_id="borrow-book",
            name="Borrow a book",
            description="External lending capability",
            aliases=[],
            target_resource_type_iri=str(book),
        ),
        settings=service.settings,
    )
    for subject, predicate, object_, graph_iri in operation_quads(
        operation, service.settings, "ontology-1"
    ):
        service.rdf_store.dataset.graph(URIRef(graph_iri)).add(
            (from_n3(subject), from_n3(predicate), from_n3(object_))
        )
    operation_iri = URIRef(operation["operation_iri"])
    graph.add((book, URIRef("https://business.test/capability"), operation_iri))
    result = query([str(book)], depth=1, context_detail="compact")
    resources = {
        row["iri"]: row for row in result["related_context"] if row.get("target_kind") == "resource"
    }
    assert resources[str(mapping)]["data"]["table_name"] == "library_catalog"
    assert resources[str(metric)]["data"]["grain"] == [str(book)]
    assert resources[str(operation_iri)]["data"]["target_resource_type_iri"] == str(book)
    assert resources[str(operation_iri)]["data"]["tool_bindings"] == operation["tool_bindings"]
    assert not any(
        row["data"].get("subject") == str(operation_iri) for row in result["related_context"]
    )


def test_r4010_nested_mapping_references_are_directional_derived_edges(context):
    service, graph, declare, query, vocab = context
    from rdflib.namespace import OWL, RDF

    mapping = declare(
        "work-order-mapping",
        "Mapping",
        mappingDefinition={
            "source_key": "ops",
            "field_meanings": [{
                "column": "status_code",
                "conversion_rule_iri": "https://business.test/rule/status-code",
            }],
        },
    )
    graph.add((mapping, RDF.type, URIRef(vocab + "TableMapping")))
    graph.add(
        (
            mapping,
            URIRef(vocab + "columnMappings"),
            Literal(json.dumps([{
                "column": "status_code",
                "property_iri": "https://business.test/property/status",
            }])),
        )
    )
    target = declare("status", "Property", label="Status")
    graph.add((target, RDF.type, OWL.DatatypeProperty))

    result = query([str(mapping)], depth=1)
    derived = [
        row for row in result["related_context"]
        if row["data"].get("derived_reference")
    ]

    assert derived
    edge = next(
        row for row in derived
        if row["data"]["target_iri"] == "https://business.test/rule/status-code"
    )
    assert edge["target_kind"] == "derived_reference"
    assert edge["origin"] == "derived_reference"
    assert edge["data"]["source_iri"] == str(mapping)
    assert edge["data"]["predicate"] == vocab + "mappingDefinition"
    assert edge["data"]["source_path"] == (
        "data.mapping_definition.field_meanings[0].conversion_rule_iri"
    )
    assert edge["data"]["field_path"] == edge["data"]["source_path"]
    assert "subject" not in edge["data"] and "object" not in edge["data"]

    compact = query([str(mapping)], depth=1, context_detail="compact")
    compact_edge = next(
        row for row in compact["related_context"]
        if row["data"].get("derived_reference")
        and row["data"].get("target_iri") == "https://business.test/rule/status-code"
    )
    assert compact_edge["id"] == edge["id"]
    assert compact_edge["data"]["source_path"] == edge["data"]["source_path"]


def test_equal_annotation_text_in_distinct_rdf_terms_is_ambiguous(context):
    _, graph, declare, query, vocab = context
    root = declare("root", "Action")
    value = '{"script_source":"return true"}'
    graph.add((root, URIRef(vocab + "ruleDefinition"), Literal(value, lang="en")))
    graph.add((root, URIRef(vocab + "ruleDefinition"), Literal(value, lang="zh")))
    result = query([str(root)], context_detail="compact")
    data = result["primary_matches"][0]["data"]
    assert "rule_definition" not in data
    assert {"field": "rule_definition", "code": "ambiguous_annotation"} in data[
        "annotation_read_diagnostics"
    ]
    statements = [
        row
        for row in result["related_context"]
        if row["data"].get("predicate") == vocab + "ruleDefinition"
    ]
    assert len(statements) == 2
    assert len({row["id"] for row in statements}) == 2
    assert all(row["projection"]["omitted_fields"] == ["data.object"] for row in statements)
