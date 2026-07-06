"""Tests for the OWL → SHACL shape generator (Stage 2 §3.4).

The generator reads an asserted OWL ontology graph and produces a derived
SHACL shapes graph. It is a pure function over rdflib graphs so the tests
exercise the generation logic directly without Oxigraph I/O.
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD

from app.services.semantic_shape_generator import generate_shapes


def _ontology_graph() -> Graph:
    graph = Graph()
    return graph


def test_single_owl_class_produces_one_node_shape_targeting_it():
    ontology = _ontology_graph()
    student = URIRef("http://example.org/ns/class/Student")
    ontology.add((student, RDF.type, OWL.Class))
    ontology.add((student, RDFS.label, Literal("Student")))

    shapes = generate_shapes(ontology)

    node_shapes = list(shapes.subjects(predicate=RDF.type, object=SH.NodeShape))
    assert len(node_shapes) == 1
    shape = node_shapes[0]
    targets = list(shapes.objects(shape, SH.targetClass))
    assert targets == [student]


def test_datatype_property_with_domain_and_range_produces_property_shape():
    ontology = _ontology_graph()
    student = URIRef("http://example.org/ns/class/Student")
    name = URIRef("http://example.org/ns/property/name")
    ontology.add((student, RDF.type, OWL.Class))
    ontology.add((name, RDF.type, OWL.DatatypeProperty))
    ontology.add((name, RDFS.domain, student))
    ontology.add((name, RDFS.range, XSD.string))

    shapes = generate_shapes(ontology)

    node_shapes = list(shapes.subjects(predicate=RDF.type, object=SH.NodeShape))
    assert len(node_shapes) == 1
    shape = node_shapes[0]
    property_shapes = list(shapes.objects(shape, SH.property))
    assert len(property_shapes) == 1
    ps = property_shapes[0]
    assert list(shapes.objects(ps, SH.path)) == [name]
    assert list(shapes.objects(ps, SH.datatype)) == [XSD.string]


def test_object_property_with_class_range_uses_sh_class_not_datatype():
    ontology = _ontology_graph()
    student = URIRef("http://example.org/ns/class/Student")
    course = URIRef("http://example.org/ns/class/Course")
    enrolled_in = URIRef("http://example.org/ns/property/enrolledIn")
    ontology.add((student, RDF.type, OWL.Class))
    ontology.add((course, RDF.type, OWL.Class))
    ontology.add((enrolled_in, RDF.type, OWL.ObjectProperty))
    ontology.add((enrolled_in, RDFS.domain, student))
    ontology.add((enrolled_in, RDFS.range, course))

    shapes = generate_shapes(ontology)

    student_shape = next(
        s for s in shapes.subjects(predicate=RDF.type, object=SH.NodeShape)
        if shapes.value(s, SH.targetClass) == student
    )
    property_shapes = list(shapes.objects(student_shape, SH.property))
    assert len(property_shapes) == 1
    ps = property_shapes[0]
    assert list(shapes.objects(ps, SH.path)) == [enrolled_in]
    assert list(shapes.objects(ps, SH["class"])) == [course]
    assert list(shapes.objects(ps, SH.datatype)) == []
