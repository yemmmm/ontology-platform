"""Focused R4.0-010 contracts for the pure RDF mapping validator."""

from __future__ import annotations

import json

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import OWL

from app.services.semantic_mapping_integrity import validate_mapping_graph


BASE = "http://op.local/ns/"
OP = BASE + "vocab/"


def _term(value: str) -> URIRef:
    return URIRef(value)


def _add_table(
    graph: Graph,
    iri: str,
    table_name: str,
    columns: list[dict[str, str]],
    target: str,
) -> None:
    graph.add((_term(iri), RDF.type, _term(OP + "TableMapping")))
    graph.add((_term(iri), _term(OP + "mappedClass"), _term(target)))
    graph.add((_term(target), RDF.type, OWL.Class))
    graph.add((_term(iri), _term(OP + "tableName"), Literal(table_name)))
    graph.add(
        (
            _term(iri),
            _term(OP + "columnMappings"),
            Literal(json.dumps(columns, ensure_ascii=False)),
        )
    )


def _add_property(graph: Graph, iri: str) -> None:
    graph.add((_term(iri), RDF.type, OWL.DatatypeProperty))


def _add_relation(graph: Graph, iri: str) -> None:
    graph.add((_term(iri), RDF.type, OWL.ObjectProperty))


def _codes(findings: list[dict]) -> list[str]:
    return [finding["code"] for finding in findings]


def test_table_definition_allows_technical_columns_and_uses_iri_paths() -> None:
    final = Graph()
    table = BASE + "table-mapping/orders"
    definition = BASE + "definition/order"
    prop = BASE + "property/order-id"
    _add_table(
        final,
        table,
        "service.orders",
        [
            {"column": "tenant_id", "role": "value"},
            {"column": "order_id", "property_iri": prop, "role": "value"},
        ],
        definition,
    )
    _add_property(final, prop)
    final.add((_term(definition), RDF.type, _term(OP + "BusinessDefinition")))
    final.add(
        (
            _term(table),
            _term(OP + "mappingDefinition"),
            Literal(
                json.dumps(
                    {
                        "source_key": "orders-db",
                        "record_key_columns": ["tenant_id", "order_id"],
                        "object_key_columns": None,
                    }
                )
            ),
        )
    )

    assert validate_mapping_graph(final) == []

    final.add(
        (
            _term(table),
            _term(OP + "mappedClass"),
            _term(BASE + "class/also-order"),
        )
    )
    final.add((_term(BASE + "class/also-order"), RDF.type, OWL.Class))
    findings = validate_mapping_graph(final)
    target_finding = next(
        finding
        for finding in findings
        if finding["code"] == "invalid_resource_reference"
        and "exactly one" in finding["message"]
    )
    assert target_finding["path"] == ["mapped_class_iri"]


def test_referenced_join_checks_columns_and_mapping_role_adjacency() -> None:
    final = Graph()
    left = BASE + "table-mapping/left"
    right = BASE + "table-mapping/right"
    prop = BASE + "property/id"
    relation = BASE + "relation-type/joins"
    join = BASE + "join-mapping/orders"
    _add_table(final, left, "service.orders", [{"column": "id", "property_iri": prop}], BASE + "class/order")
    _add_table(final, right, "service.lines", [{"column": "order_id", "property_iri": prop}], BASE + "class/line")
    _add_property(final, prop)
    _add_relation(final, relation)
    final.add((_term(join), RDF.type, _term(OP + "JoinMapping")))
    final.add((_term(join), _term(OP + "mappedRelationType"), _term(relation)))
    final.add(
        (
            _term(join),
            _term(OP + "joinPath"),
            Literal(
                json.dumps(
                    [
                        {
                            "from_mapping_iri": left,
                            "to_mapping_iri": right,
                            "from_role": "order",
                            "to_role": "line",
                            "from_columns": ["id"],
                            "to_columns": ["order_id"],
                        }
                    ]
                )
            ),
        )
    )

    assert validate_mapping_graph(final) == []
    final.remove((_term(join), _term(OP + "joinPath"), next(final.objects(_term(join), _term(OP + "joinPath")))))
    final.add(
        (
            _term(join),
            _term(OP + "joinPath"),
            Literal(
                json.dumps(
                    [
                        {
                            "from_mapping_iri": left,
                            "to_mapping_iri": right,
                            "from_role": "order",
                            "to_role": "line",
                            "from_columns": ["id"],
                            "to_columns": ["missing"],
                        }
                    ]
                )
            ),
        )
    )
    finding = next(
        finding
        for finding in validate_mapping_graph(final)
        if finding["code"] == "join_path_not_mapped"
    )
    assert finding["path"] == ["join_path", 0, "to_columns", 0]


def test_scoped_enum_uniqueness_and_semantic_value_deletion_are_checked() -> None:
    final = Graph()
    table = BASE + "table-mapping/orders"
    prop = BASE + "property/status"
    _add_table(final, table, "service.orders", [{"column": "status", "property_iri": prop}], BASE + "class/order")
    _add_property(final, prop)
    for identifier in ("open-1", "open-2"):
        subject = _term(BASE + "enum-meaning/" + identifier)
        final.add((subject, RDF.type, _term(OP + "EnumValueMeaning")))
        final.add((subject, _term(OP + "mappedProperty"), _term(prop)))
        final.add((subject, _term(OP + "enumValue"), Literal("OPEN")))
        final.add((subject, _term(OP + "tableMapping"), _term(table)))
        final.add((subject, _term(OP + "columnName"), Literal("status")))
    findings = validate_mapping_graph(final)
    assert _codes(findings).count("resource_already_exists") == 2

    original = Graph()
    for triple in final:
        original.add(triple)
    enum = _term(BASE + "enum-meaning/open-1")
    target = _term(BASE + "entity/status-open")
    final.add((enum, _term(OP + "semanticValue"), target))
    original.add((target, RDF.type, OWL.NamedIndividual))
    dangling = validate_mapping_graph(final, original_graph=original)
    assert any(finding["code"] == "semantic_value_dangling" for finding in dangling)


def test_multiple_semantic_values_remain_a_structural_error() -> None:
    final = Graph()
    table = BASE + "table-mapping/orders"
    prop = BASE + "property/status"
    enum = BASE + "enum-meaning/status-open"
    _add_table(final, table, "service.orders", [{"column": "status", "property_iri": prop}], BASE + "class/order")
    _add_property(final, prop)
    final.add((_term(enum), RDF.type, _term(OP + "EnumValueMeaning")))
    final.add((_term(enum), _term(OP + "mappedProperty"), _term(prop)))
    final.add((_term(enum), _term(OP + "enumValue"), Literal("OPEN")))
    final.add((_term(enum), _term(OP + "semanticValue"), _term(BASE + "entity/open")))
    final.add((_term(enum), _term(OP + "semanticValue"), _term(BASE + "entity/other")))
    findings = validate_mapping_graph(final)
    assert any(
        finding["code"] == "invalid_resource_reference"
        and finding["path"] == ["semantic_value"]
        and "at most one" in finding["message"]
        for finding in findings
    )


def test_metric_context_roles_and_join_step_indexes_are_closed() -> None:
    final = Graph()
    table = BASE + "table-mapping/orders"
    prop = BASE + "property/id"
    join = BASE + "join-mapping/self"
    relation = BASE + "relation-type/self"
    metric = BASE + "metric/orders"
    _add_table(final, table, "service.orders", [{"column": "id", "property_iri": prop}], BASE + "class/order")
    _add_property(final, prop)
    _add_relation(final, relation)
    final.add((_term(join), RDF.type, _term(OP + "JoinMapping")))
    final.add((_term(join), _term(OP + "mappedRelationType"), _term(relation)))
    final.add(
        (
            _term(join),
            _term(OP + "joinPath"),
            Literal(
                json.dumps(
                    [
                        {
                            "from_mapping_iri": table,
                            "to_mapping_iri": table,
                            "from_role": "base",
                            "to_role": "detail",
                            "from_columns": ["id"],
                            "to_columns": ["id"],
                        }
                    ]
                )
            ),
        )
    )
    final.add((_term(metric), RDF.type, _term(OP + "MetricDefinition")))
    final.add(
        (
            _term(metric),
            _term(OP + "mappingDefinition"),
            Literal(
                json.dumps(
                    {
                        "contexts": [
                            {
                                "context_key": "orders",
                                "base_mapping_iri": table,
                                "base_role": "base",
                                "join_mapping_iris": [join],
                                "property_bindings": [
                                    {
                                        "property_iri": prop,
                                        "table_mapping_iri": table,
                                        "role": "unknown-role",
                                        "column": "id",
                                    }
                                ],
                            }
                        ]
                    }
                )
            ),
        )
    )
    final.add(
        (
            _term(join),
            _term(OP + "mappingDefinition"),
            Literal(json.dumps({"step_semantics": [{"step_index": 1}]})),
        )
    )
    findings = validate_mapping_graph(final)
    assert any(
        finding["path"]
        == ["mapping_definition", "contexts", 0, "property_bindings", 0, "role"]
        for finding in findings
    )
    assert any(
        finding["path"] == ["mapping_definition", "step_semantics", 0, "step_index"]
        for finding in findings
    )
