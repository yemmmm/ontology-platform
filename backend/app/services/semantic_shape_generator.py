"""Generate SHACL shapes from an asserted OWL ontology graph.

Stage 2 §3.4 specifies a derived ``graph/shapes/{ontology_id}/generated``
sub-graph produced from ``graph/ontology/{id}``. This module owns the pure
OWL → SHACL translation; the I/O wrapper that loads and persists graphs
lives elsewhere.
"""

from __future__ import annotations

from rdflib import BNode, Graph
from rdflib.namespace import OWL, RDF, RDFS, SH


def generate_shapes(ontology_graph: Graph) -> Graph:
    """Produce a SHACL shapes graph from an OWL ontology graph.

    Each ``owl:Class`` in the source produces one ``sh:NodeShape`` whose
    ``sh:targetClass`` is the class IRI. Each ``owl:DatatypeProperty`` whose
    ``rdfs:domain`` is the class produces a nested ``sh:PropertyShape`` with
    ``sh:path`` and ``sh:datatype`` drawn from the property's ``rdfs:range``.
    ``owl:ObjectProperty`` with a class range produces a ``sh:PropertyShape``
    with ``sh:class`` instead of ``sh:datatype``.
    """
    shapes = Graph()
    for class_iri in ontology_graph.subjects(predicate=RDF.type, object=OWL.Class):
        shape = BNode()
        shapes.add((shape, RDF.type, SH.NodeShape))
        shapes.add((shape, SH.targetClass, class_iri))
        for property_iri in ontology_graph.subjects(predicate=RDFS.domain, object=class_iri):
            is_datatype = (property_iri, RDF.type, OWL.DatatypeProperty) in ontology_graph
            is_object = (property_iri, RDF.type, OWL.ObjectProperty) in ontology_graph
            if not (is_datatype or is_object):
                continue
            property_shape = BNode()
            shapes.add((shape, SH.property, property_shape))
            shapes.add((property_shape, SH.path, property_iri))
            range_value = ontology_graph.value(property_iri, RDFS.range)
            if range_value is None:
                continue
            if is_datatype:
                shapes.add((property_shape, SH.datatype, range_value))
            else:
                shapes.add((property_shape, SH["class"], range_value))
    return shapes
