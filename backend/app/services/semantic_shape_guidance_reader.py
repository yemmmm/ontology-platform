"""Extract per-class ShaclFormGuidance from a shapes graph.

Stage 2 §3.4.2: the shape endpoint reads generated and custom shape
graphs and turns each into a ``ShaclFormGuidance`` dict before merging.
This module owns that translation; the merge lives in
:mod:`app.services.semantic_shape_merge`.
"""

from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, SH


def extract_shape_guidance_for_class(
    shapes_graph: Graph, class_iri: URIRef | str
) -> dict[str, Any]:
    """Build a ``ShaclFormGuidance`` dict for one class from a shapes graph.

    Selects every ``sh:NodeShape`` whose ``sh:targetClass`` equals
    ``class_iri`` and projects its ``sh:property`` constraints into the
    flat field list the frontend ``ShaclFormRenderer`` expects.
    """
    class_value = URIRef(class_iri) if isinstance(class_iri, str) else class_iri
    fields: list[dict[str, Any]] = []
    field_paths: set[str] = set()

    for shape in shapes_graph.subjects(predicate=RDF.type, object=SH.NodeShape):
        if (shape, SH.targetClass, class_value) not in shapes_graph:
            continue
        for property_shape in shapes_graph.objects(shape, SH.property):
            field = _field_from_property_shape(shapes_graph, property_shape)
            if field is None:
                continue
            path = field.get("path")
            if path is not None and path in field_paths:
                # Merge duplicates: later constraint wins for shared keys,
                # earlier keys persist for non-overlapping ones.
                existing = next(f for f in fields if f.get("path") == path)
                for key, value in field.items():
                    existing.setdefault(key, value)
                continue
            if path is not None:
                field_paths.add(path)
            fields.append(field)

    return {
        "target_class": str(class_value),
        "fields": fields,
    }


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
