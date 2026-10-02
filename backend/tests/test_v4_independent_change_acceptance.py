"""Independent bounded change checks; no provider or customer run is involved."""

import json

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from app.services.semantic_export import namespace_from_settings
from test_r4008_context_query import drain
from test_relational_mapping_application import item, submit

pytest_plugins = ["test_r4008_context_query", "test_relational_mapping_application"]


def _entity(key, role, meaning, **annotations):
    return item(
        key,
        "create_entity",
        entity_id=key,
        label=key,
        semantic_definition={"semantic_role": role, "business_meaning": meaning},
        **annotations,
    )


def _edge(fixture, key, source, target, kind="create_relation"):
    return item(
        key,
        kind,
        source_entity_iri=fixture["base"] + "entity/" + source,
        relation_type_iri=fixture["base"] + "relation-type/related",
        target_entity_iri=fixture["base"] + "entity/" + target,
    )


def _data(fixture, ontology):
    graph = namespace_from_settings(fixture["settings"]).graph("data", ontology)
    return Graph().parse(data=fixture["store"].get_graph(str(graph), "turtle"), format="turtle")


def _targets(fixture, graph, source):
    return set(
        map(
            str,
            graph.objects(
                URIRef(fixture["base"] + "entity/" + source),
                URIRef(fixture["base"] + "relation-type/related"),
            ),
        )
    )


def test_new_contract_switch_failure_keeps_old_definition_and_unswitched_reference(
    mapping_application,
):
    """A failed second Ontology switch must not erase its still valid old target."""
    f = mapping_application
    a, b, _ = f["ontologies"]
    old = _entity("old-action", "action", "Original contract without mandatory reason")
    assert (
        submit(
            f,
            a,
            [
                old,
                _entity("call-a", "invocation", "First usage"),
                _edge(f, "old-a", "call-a", "old-action"),
            ],
        )["attempt_status"]
        == "applied"
    )
    assert (
        submit(
            f,
            b,
            [
                _entity("call-b", "invocation", "Second usage cannot change yet"),
                _edge(f, "old-b", "call-b", "old-action"),
            ],
        )["attempt_status"]
        == "applied"
    )
    original = _data(f, a)
    old_iri = URIRef(f["base"] + "entity/old-action")
    old_definition = set(original.triples((old_iri, None, None)))
    new = [
        _entity("new-action", "action", "New contract requires reason"),
        _entity(
            "reason",
            "parameter",
            "Mandatory reason for new contract",
            parameter_definition={
                "direction": "input",
                "value_kind": "value",
                "value_type": "string",
                "cardinality": "single",
                "required": True,
            },
        ),
        _edge(f, "new-parameter", "new-action", "reason"),
    ]
    created = submit(f, a, new)
    assert created["attempt_status"] == "applied", created
    new_graph = _data(f, a)
    reason_iri = URIRef(f["base"] + "entity/reason")
    parameter_predicate = URIRef(
        str(namespace_from_settings(f["settings"]).vocab) + "parameterDefinition"
    )
    assert json.loads(str(next(new_graph.objects(reason_iri, parameter_predicate))))["required"]
    assert _targets(f, new_graph, "new-action") == {str(reason_iri)}
    assert _targets(f, new_graph, "old-action") == set()
    assert _targets(f, _data(f, b), "call-b") == {str(old_iri)}
    first = submit(
        f,
        a,
        [
            _edge(f, "remove-old-a", "call-a", "old-action", "delete_relation"),
            _edge(f, "new-a", "call-a", "new-action"),
        ],
    )
    assert first["attempt_status"] == "applied", json.dumps(first, default=str)
    # Deterministic pre-write failure; no uncertain write is created or inspected.
    # Plain RDF object IRIs need not have a prior local declaration. Use the
    # established absolute-IRI contract rather than assuming a missing-node gate.
    invalid_switch = _edge(f, "bad-new-b", "call-b", "new-action")
    invalid_switch["payload"]["target_entity_iri"] = "relative-new-action"
    failed = submit(
        f,
        b,
        [
            _edge(f, "remove-old-b", "call-b", "old-action", "delete_relation"),
            invalid_switch,
        ],
    )
    assert failed["attempt_status"] == "validation_failed", failed
    assert failed["attempt_id"] != first["attempt_id"]
    assert any(
        finding["code"] == "invalid_command_payload"
        and "target_entity_iri must be an absolute RDF IRI" in finding["message"]
        for finding in failed["findings"]
    ), failed
    assert _targets(f, _data(f, b), "call-b") == {str(old_iri)}
    assert _targets(f, _data(f, a), "call-a") == {f["base"] + "entity/new-action"}
    assert set(_data(f, a).triples((old_iri, None, None))) == old_definition
    # The fixture's existing BuildSession and lease are reused after repair.
    build_before = f["bindings"][b]
    repaired = submit(
        f,
        b,
        [
            _edge(f, "remove-old-b", "call-b", "old-action", "delete_relation"),
            _edge(f, "new-b", "call-b", "new-action"),
        ],
    )
    assert repaired["attempt_status"] == "applied", repaired
    assert f["bindings"][b] == build_before
    assert _targets(f, _data(f, b), "call-b") == {f["base"] + "entity/new-action"}
    assert set(_data(f, a).triples((old_iri, None, None))) == old_definition


def test_indirect_review_query_reaches_both_flows_and_exposes_removed_binding(context):
    """Explicit dependency chains can be inspected; this is not an automatic reviewer."""
    _, graph, declare, query, _ = context
    parameter = declare("mandatory-parameter", "parameter")
    action = declare("shared-action", "action")
    has_parameter = URIRef("https://review.test/hasParameter")
    invokes = URIRef("https://review.test/invokes")
    contains = URIRef("https://review.test/contains")
    binds = URIRef("https://review.test/bindsParameter")
    for predicate in (has_parameter, invokes, contains, binds):
        graph.add((predicate, RDFS.label, Literal(str(predicate).rsplit("/", 1)[-1])))
    graph.add((action, has_parameter, parameter))
    for index in (1, 2):
        call = declare(f"usage-{index}", "invocation")
        flow = declare(f"flow-{index}", "process")
        graph.add((call, invokes, action))
        graph.add((flow, contains, call))
        graph.add((call, binds, parameter))
    rows, result = drain(query, [str(parameter)], depth=3, context_limit=2)
    assert result["context_page"]["expansion"]["status"] == "complete"
    resources = {row["iri"] for row in rows if row.get("target_kind") == "resource"}
    assert {"https://business.test/flow-1", "https://business.test/flow-2"} <= resources
    expected = {(f"https://business.test/usage-{i}", str(binds), str(parameter)) for i in (1, 2)}

    def bindings(rows):
        return {
            (r["data"].get("subject"), r["data"].get("predicate"), r["data"].get("object"))
            for r in rows
            if r.get("target_kind") == "statement"
        }

    assert expected <= bindings(rows)
    graph.remove((URIRef("https://business.test/usage-2"), binds, parameter))
    after, _ = drain(query, [str(parameter)], depth=3, context_limit=20)
    # Independent fixture oracle detects a missing binding even though the flow remains reachable.
    assert expected - bindings(after) == {
        ("https://business.test/usage-2", str(binds), str(parameter))
    }
    assert "https://business.test/flow-2" in {
        r["iri"] for r in after if r.get("target_kind") == "resource"
    }
    bounded = query([str(parameter)], depth=1, context_limit=1)
    assert bounded["context_page"]["next_context_cursor"]
    assert bounded["truncated"]
    assert "compatible" not in json.dumps(bounded).lower()
