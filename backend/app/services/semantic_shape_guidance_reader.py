"""Extract per-class ShaclFormGuidance from a shapes graph.

Stage 2 §3.4.2: the shape endpoint reads generated and custom shape
graphs and turns each into a ``ShaclFormGuidance`` dict before merging.
This module owns that translation; the merge lives in
:mod:`app.services.semantic_shape_merge`.

R3.0-009 §6.1 adds ``extract_shape_guidance_for_targets``, which selects
shapes by any of the three supported targets (``sh:targetClass``,
``sh:targetNode``, ``sh:targetSubjectsOf``) so an entity's guidance can be
assembled from its full formal class set, its node target shapes and the
subjects-of shapes of the predicates it actually uses.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SH

OWL = Namespace("http://www.w3.org/2002/07/owl#")
NAMED_INDIVIDUAL = OWL.NamedIndividual


def extract_shape_guidance_for_class(
    shapes_graph: Graph, class_iri: URIRef | str
) -> dict[str, Any]:
    """Build a ``ShaclFormGuidance`` dict for one class from a shapes graph.

    Selects every ``sh:NodeShape`` whose ``sh:targetClass`` equals
    ``class_iri`` and projects its ``sh:property`` constraints into the
    flat field list the frontend ``ShaclFormRenderer`` expects.

    Every field carries the ``source_shape_iri`` it came from, and constraints
    from different shapes are kept as separate entries (F08): collapsing them
    here would hide a still-effective constraint before the merge could report
    the conflict. Only one shape restating its own constraint is folded.
    """
    class_value = URIRef(class_iri) if isinstance(class_iri, str) else class_iri
    fields: list[dict[str, Any]] = []
    fields_by_path_shape: dict[tuple[str, str], dict[str, Any]] = {}

    for shape in shapes_graph.subjects(predicate=RDF.type, object=SH.NodeShape):
        if (shape, SH.targetClass, class_value) not in shapes_graph:
            continue
        for property_shape in shapes_graph.objects(shape, SH.property):
            field = _field_from_property_shape(shapes_graph, property_shape)
            if field is None:
                continue
            path = field.get("path")
            field["source_shape_iri"] = str(shape)
            key = (str(path), str(shape))
            existing = fields_by_path_shape.get(key)
            if existing is not None:
                # One shape restating a constraint: fill in keys it lacks.
                for key_name, value in field.items():
                    existing.setdefault(key_name, value)
                continue
            fields_by_path_shape[key] = field
            fields.append(field)

    return {
        "target_class": str(class_value),
        "fields": fields,
    }


def extract_shape_guidance_for_targets(
    shapes_graph: Graph,
    *,
    class_iris: Iterable[str] = (),
    target_node_iri: str | None = None,
    subject_predicates: Iterable[str] = (),
) -> dict[str, Any]:
    """Project every NodeShape that applies to one entity (R3.0-009 §6.1).

    A shape applies when any of its targets matches the entity:

    - ``sh:targetClass`` in ``class_iris`` (the entity's full formal class set,
      ``owl:NamedIndividual`` excluded),
    - ``sh:targetNode`` equal to ``target_node_iri``,
    - ``sh:targetSubjectsOf`` naming one of the ``subject_predicates`` the
      entity actually uses as a subject.

    Each projected field records its source shape IRI and the matched targets
    so callers keep provenance and the merge step can detect conflicts instead
    of silently keeping the last constraint.
    """
    wanted_classes = {str(value) for value in class_iris if value}
    wanted_predicates = {str(value) for value in subject_predicates if value}
    fields: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    shape_iris: list[str] = []

    for shape in shapes_graph.subjects(predicate=RDF.type, object=SH.NodeShape):
        matched: list[dict[str, str]] = []
        for class_value in shapes_graph.objects(shape, SH.targetClass):
            if str(class_value) in wanted_classes:
                matched.append({"kind": "class", "value": str(class_value)})
        if target_node_iri:
            for node_value in shapes_graph.objects(shape, SH.targetNode):
                if str(node_value) == target_node_iri:
                    matched.append({"kind": "node", "value": str(node_value)})
        for predicate_value in shapes_graph.objects(shape, SH.targetSubjectsOf):
            if str(predicate_value) in wanted_predicates:
                matched.append(
                    {"kind": "subjects_of", "value": str(predicate_value)}
                )
        if not matched:
            continue
        shape_iris.append(str(shape))
        targets.extend(matched)
        for property_shape in shapes_graph.objects(shape, SH.property):
            field = _field_from_property_shape(shapes_graph, property_shape)
            if field is None:
                continue
            field["source_shape_iri"] = str(shape)
            field["matched_targets"] = [dict(item) for item in matched]
            fields.append(field)

    return {
        "fields": fields,
        "targets": targets,
        "shape_iris": shape_iris,
    }


def entity_class_iris(graph: Graph, entity_iri: str) -> list[str]:
    """Return the entity's visible formal class set from a data graph.

    ``owl:NamedIndividual`` and every ``owl:``-namespaced type are excluded, so
    the marker never doubles as a business class (R3.0-009 §6.2).
    """
    subject = URIRef(entity_iri)
    classes = {
        str(class_value)
        for class_value in graph.objects(subject, RDF.type)
        if not str(class_value).startswith(str(OWL))
    }
    return sorted(classes)


def entity_subject_predicates(graph: Graph, entity_iri: str) -> list[str]:
    """Return the predicates the entity actually uses as a subject.

    Platform-owned identity and description predicates are excluded: they are
    not business classification/relation predicates and must not select
    ``sh:targetSubjectsOf`` shapes.
    """
    subject = URIRef(entity_iri)
    excluded = {
        str(RDF.type),
        str(RDFS.label),
        URIRef("http://www.w3.org/2004/02/skos/core#altLabel"),
        URIRef("http://www.w3.org/2000/01/rdf-schema#comment"),
    }
    predicates = {
        str(predicate)
        for predicate in graph.predicates(subject, None)
        if str(predicate) not in excluded
    }
    return sorted(predicates)



def _field_from_property_shape(
    shapes_graph: Graph, property_shape
) -> dict[str, Any] | None:
    path = shapes_graph.value(property_shape, SH.path)
    if path is None:
        return None
    field: dict[str, Any] = {"path": str(path)}
    name = shapes_graph.value(property_shape, SH.name)
    if name is None:
        # Local-name fallback: take the last path segment of the IRI.
        field["name"] = str(path).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    else:
        field["name"] = str(name)
    label = shapes_graph.value(property_shape, SH.description) or shapes_graph.value(
        property_shape, RDFS.label
    )
    if label is not None:
        field["label"] = str(label)
    datatype = shapes_graph.value(property_shape, SH.datatype)
    if datatype is not None:
        field["datatype"] = str(datatype)
    class_value = shapes_graph.value(property_shape, SH["class"])
    if class_value is not None:
        field["class_iri"] = str(class_value)
    min_count = shapes_graph.value(property_shape, SH.minCount)
    if min_count is not None:
        field["min_count"] = int(min_count)
        field["required"] = int(min_count) > 0
    max_count = shapes_graph.value(property_shape, SH.maxCount)
    if max_count is not None:
        field["max_count"] = int(max_count)
    pattern = shapes_graph.value(property_shape, SH.pattern)
    if pattern is not None:
        field["pattern"] = str(pattern)
    description = shapes_graph.value(property_shape, RDFS.comment)
    if description is not None:
        field["description"] = str(description)
    in_node = shapes_graph.value(property_shape, SH["in"])
    if in_node is not None:
        from rdflib.collection import Collection

        values = [str(v) for v in Collection(shapes_graph, in_node)]
        field["enumeration"] = values
    return field
