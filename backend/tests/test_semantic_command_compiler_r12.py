"""Focused compiler regressions for the M4 Round-12 Turtle serialization repair."""

from __future__ import annotations

import re

from app.core.config import Settings
from app.services import semantic_command_compiler as compiler
from app.services.semantic_command_compiler import compile_command


def _settings() -> Settings:
    return Settings(
        semantic_base_iri="http://op.local/ns/",
        semantic_graph_iri_prefix="http://op.local/graph/",
    )


def test_shape_constraint_blank_nodes_are_valid_deterministic_and_distinct_for_urn_ids() -> None:
    payload = {
        "ontology_id": "ont-1",
        "target_class_id": "urn:m4:Workflow",
        "shape_id": "urn:m4:WorkflowShape",
        "constraints": [
            {"path_id": "urn:m4:workflowKey", "datatype": "string"},
            {"path_id": "urn:m4:workflowKey", "datatype": "string"},
        ],
    }

    first = compile_command("create_shape", payload, _settings())
    second = compile_command("create_shape", payload, _settings())
    shape_iri = first.metadata["shape_iri"]
    assert isinstance(shape_iri, str)
    shape_term = f"<{shape_iri}>"
    property_terms = [
        quad[2]
        for quad in first.delta.inserts
        if quad[0] == shape_term and quad[1] == "<http://www.w3.org/ns/shacl#property>"
    ]

    assert property_terms == [
        quad[2]
        for quad in second.delta.inserts
        if quad[0] == shape_term and quad[1] == "<http://www.w3.org/ns/shacl#property>"
    ]
    assert len(property_terms) == len(set(property_terms)) == 2
    assert all(re.fullmatch(r"_:[A-Za-z][A-Za-z0-9_]*", term) for term in property_terms)
    assert (
        property_terms[0],
        "<http://www.w3.org/ns/shacl#datatype>",
        "<http://www.w3.org/2001/XMLSchema#string>",
        "http://op.local/graph/shapes/ont-1/custom",
    ) in first.delta.inserts


def test_datatype_iri_normalizes_only_recognized_bare_xsd_names() -> None:
    assert compiler._datatype_iri("string") == "http://www.w3.org/2001/XMLSchema#string"
    assert compiler._datatype_iri("xsd:string") == "http://www.w3.org/2001/XMLSchema#string"
    absolute = "https://example.test/custom-datatype"
    assert compiler._datatype_iri(absolute) == absolute
    assert compiler._datatype_iri("customDatatype") == "customDatatype"


def test_enum_values_compile_to_distinct_deterministic_rdf_lists() -> None:
    payload = {
        "ontology_id": "ont-1",
        "target_class_id": "urn:m4:Workflow",
        "shape_id": "urn:m4:WorkflowShape",
        "constraints": [
            {"enum_values": ["draft", "published"], "path_id": "urn:m4:status"},
            {"enum_values": ["low", "high"], "path_id": "urn:m4:priority"},
        ],
    }

    first = compile_command("create_shape", payload, _settings())
    second = compile_command("create_shape", payload, _settings())
    graph_iri = "http://op.local/graph/shapes/ont-1/custom"
    in_predicate = "<http://www.w3.org/ns/shacl#in>"
    first_predicate = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#first>"
    rest_predicate = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#rest>"
    nil = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>"
    in_quads = [quad for quad in first.delta.inserts if quad[1] == in_predicate]

    assert in_quads == [quad for quad in second.delta.inserts if quad[1] == in_predicate]
    assert len(in_quads) == 2
    heads = [quad[2] for quad in in_quads]
    assert len(heads) == len(set(heads)) == 2
    assert all(re.fullmatch(r"_:[A-Za-z][A-Za-z0-9_]*", head) for head in heads)
    list_nodes: set[str] = set()
    values_by_head: dict[str, list[str]] = {}
    for head in heads:
        node = head
        values: list[str] = []
        while node != nil:
            list_nodes.add(node)
            first_quad = next(
                quad for quad in first.delta.inserts if quad[0] == node and quad[1] == first_predicate
            )
            rest_quad = next(quad for quad in first.delta.inserts if quad[0] == node and quad[1] == rest_predicate)
            assert first_quad[3] == rest_quad[3] == graph_iri
            values.append(first_quad[2])
            node = rest_quad[2]
        values_by_head[head] = values
    assert len(list_nodes) == 4
    assert sorted(values_by_head.values()) == [['"draft"', '"published"'], ['"low"', '"high"']]
