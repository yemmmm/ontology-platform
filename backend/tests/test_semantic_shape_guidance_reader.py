"""Tests for extracting per-class ShaclFormGuidance from a shapes graph.

Stage 2 §3.4.2: the shape endpoint reads generated + custom shape graphs
and turns each into a ``ShaclFormGuidance`` dict before merging. This
module tests the extraction logic in isolation, without Oxigraph I/O.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SH, XSD

from app.services.semantic_shape_guidance_reader import extract_shape_guidance_for_class


def _shapes_graph_with_one_node_shape_for_student() -> Graph:
    graph = Graph()
    student = URIRef("http://example.org/Student")
    name = URIRef("http://example.org/name")
    shape = BNode()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, student))
    property_shape = BNode()
    graph.add((shape, SH.property, property_shape))
    graph.add((property_shape, SH.path, name))
    graph.add((property_shape, SH.datatype, XSD.string))
    graph.add((property_shape, SH.minCount, Literal(1)))
    return graph


def test_extract_returns_target_class_and_label():
    graph = _shapes_graph_with_one_node_shape_for_student()
    student = URIRef("http://example.org/Student")

    guidance = extract_shape_guidance_for_class(graph, student)

    assert guidance["target_class"] == str(student)


def test_extract_returns_one_field_per_property_shape():
    graph = _shapes_graph_with_one_node_shape_for_student()
    student = URIRef("http://example.org/Student")
    name = URIRef("http://example.org/name")

    guidance = extract_shape_guidance_for_class(graph, student)

    assert len(guidance["fields"]) == 1
    field = guidance["fields"][0]
    assert field["path"] == str(name)
    assert field["datatype"] == str(XSD.string)
    assert field["min_count"] == 1


def test_extract_returns_empty_fields_when_no_node_shape_targets_class():
    graph = Graph()
    student = URIRef("http://example.org/Student")

    guidance = extract_shape_guidance_for_class(graph, student)

    assert guidance["fields"] == []


def test_extract_carries_max_count_pattern_and_description():
    graph = Graph()
    student = URIRef("http://example.org/Student")
    email = URIRef("http://example.org/email")
    shape = BNode()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, student))
    property_shape = BNode()
    graph.add((shape, SH.property, property_shape))
    graph.add((property_shape, SH.path, email))
    graph.add((property_shape, SH.maxCount, Literal(1)))
    graph.add((property_shape, SH.pattern, Literal("^[^@]+@[^@]+$")))
    graph.add((property_shape, RDFS.comment, Literal("Email constraint")))

    guidance = extract_shape_guidance_for_class(graph, student)

    field = guidance["fields"][0]
    assert field["max_count"] == 1
    assert field["pattern"] == "^[^@]+@[^@]+$"
    assert field["description"] == "Email constraint"


def test_extract_enumeration_translates_to_enumeration_field():
    from rdflib.collection import Collection

    graph = Graph()
    student = URIRef("http://example.org/Student")
    status = URIRef("http://example.org/status")
    shape = BNode()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, student))
    property_shape = BNode()
    graph.add((shape, SH.property, property_shape))
    graph.add((property_shape, SH.path, status))
    collection_node = BNode()
    Collection(graph, collection_node, [Literal("active"), Literal("inactive")])
    graph.add((property_shape, SH["in"], collection_node))

    guidance = extract_shape_guidance_for_class(graph, student)

    field = guidance["fields"][0]
    assert field["enumeration"] == ["active", "inactive"]
