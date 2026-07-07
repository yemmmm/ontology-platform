"""Phase 7 product command compilers.

Thin adapters that translate structured product API commands into the same
:class:`RdfGraphDelta` shape produced by direct semantic edits. The canonical
write service consumes the delta without knowing which surface produced it, so
product APIs and direct semantic APIs share one validation, audit, and revision
pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import Settings
from app.repositories.rdf_store import RdfGraphDelta
from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_export import SemanticNamespace, namespace_from_settings


class CommandCompilerError(RuntimeError):
    status_code = 400


class UnsupportedCommandKind(CommandCompilerError):
    pass


class InvalidCommandPayload(CommandCompilerError):
    pass


@dataclass(frozen=True)
class CompiledCommand:
    """Result of compiling a product command into a graph delta.

    ``object_kind`` and ``source_ids`` travel with the compiled command so the
    migration writer and audit log can record provenance without re-parsing the
    payload. ``target_graph_iris`` is the canonical set of graphs the delta
    touches, used for revision tracking and parity scoping.
    """

    command_kind: str
    delta: RdfGraphDelta
    object_kind: str
    source_ids: list[str]
    target_graph_iris: list[str]
    metadata: dict[str, Any]


Compiler = Callable[[dict[str, Any], SemanticNamespace, Settings], CompiledCommand]


def _required(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise InvalidCommandPayload(f"Missing required field: {key}")
    return payload[key]


def _iri_term(iri: str) -> str:
    return f"<{iri}>"


def _literal_term(value: Any) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean>'
    if isinstance(value, int):
        return f'"{int(value)}"^^<http://www.w3.org/2001/XMLSchema#integer>'
    if isinstance(value, float):
        return f'"{float(value)}"^^<http://www.w3.org/2001/XMLSchema#decimal>'
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _object_term(value: Any, *, is_iri: bool = False) -> str:
    if is_iri:
        return _iri_term(str(value))
    return _literal_term(value)


_XSD_PREFIX = "http://www.w3.org/2001/XMLSchema#"


def _datatype_iri(value: str) -> str:
    """Normalize a datatype value to a full IRI string (without angle brackets).

    Accepts ``xsd:string`` style prefixes or full IRIs.
    """
    if value.startswith("xsd:"):
        return f"{_XSD_PREFIX}{value[4:]}"
    return value


def _ontology_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("ontology", ontology_id))


def _data_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("data", ontology_id))


def _shapes_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("shapes", ontology_id))


def _shapes_custom_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return f"{_shapes_graph_iri(ns, ontology_id)}/custom"


def compile_create_class(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    class_id = payload.get("class_id") or str(uuid.uuid4())
    name = _required(payload, "name")
    description = payload.get("description")
    aliases: list[str] = payload.get("aliases", []) or []
    parent_class_ids: list[str] = payload.get("parent_class_ids", []) or []
    external_mappings: dict[str, Any] = payload.get("external_mappings", {}) or {}

    class_iri = str(ns.resource("class", class_id))
    ontology_iri = str(ns.resource("ontology", ontology_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{class_iri}>", "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         "<http://www.w3.org/2002/07/owl#Class>", graph_iri),
        (f"<{class_iri}>", f"<{op}id>", _literal_term(class_id), graph_iri),
        (f"<{class_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (f"<{class_iri}>", "<http://www.w3.org/2000/01/rdf-schema#label>",
         _literal_term(name), graph_iri),
    ]
    if description:
        insert_quads.append(
            (f"<{class_iri}>", "<http://www.w3.org/2000/01/rdf-schema#comment>",
             _literal_term(description), graph_iri)
        )
    for alias in aliases:
        insert_quads.append(
            (f"<{class_iri}>", "<http://www.w3.org/2004/02/skos/core#altLabel>",
             _literal_term(alias), graph_iri)
        )
    for parent_id in parent_class_ids:
        insert_quads.append(
            (f"<{class_iri}>", "<http://www.w3.org/2000/01/rdf-schema#subClassOf>",
             f"<{ns.resource('class', parent_id)}>", graph_iri)
        )
    for external_id, mapping in external_mappings.items():
        if not mapping:
            continue
        insert_quads.append(
            (f"<{class_iri}>", f"<{op}externalMapping>",
             _literal_term({"system": external_id, "mapping": mapping}), graph_iri)
        )
    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_class",
        delta=delta,
        object_kind="class",
        source_ids=[class_id],
        target_graph_iris=[graph_iri],
        metadata={"class_id": class_id, "ontology_id": ontology_id, "name": name},
    )


def compile_create_relation_type(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    relation_type_id = payload.get("relation_type_id") or str(uuid.uuid4())
    name = _required(payload, "name")
    source_class_id = _required(payload, "source_class_id")
    target_class_id = _required(payload, "target_class_id")
    description = payload.get("description")
    symmetric = bool(payload.get("symmetric", False))
    transitive = bool(payload.get("transitive", False))
    scope_policy = payload.get("scope_policy", "both")
    status = payload.get("status", "active")

    relation_iri = str(ns.resource("relation-type", relation_type_id))
    ontology_iri = str(ns.resource("ontology", ontology_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{relation_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         "<http://www.w3.org/2002/07/owl#ObjectProperty>", graph_iri),
        (f"<{relation_iri}>", f"<{op}id>", _literal_term(relation_type_id), graph_iri),
        (f"<{relation_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (f"<{relation_iri}>",
         "<http://www.w3.org/2000/01/rdf-schema#label>",
         _literal_term(name), graph_iri),
        (f"<{relation_iri}>",
         "<http://www.w3.org/2000/01/rdf-schema#domain>",
         f"<{ns.resource('class', source_class_id)}>", graph_iri),
        (f"<{relation_iri}>",
         "<http://www.w3.org/2000/01/rdf-schema#range>",
         f"<{ns.resource('class', target_class_id)}>", graph_iri),
        (f"<{relation_iri}>", f"<{op}sourceClassId>",
         _literal_term(source_class_id), graph_iri),
        (f"<{relation_iri}>", f"<{op}targetClassId>",
         _literal_term(target_class_id), graph_iri),
        (f"<{relation_iri}>", f"<{op}scopePolicy>", _literal_term(scope_policy), graph_iri),
        (f"<{relation_iri}>", f"<{op}status>", _literal_term(status), graph_iri),
    ]
    if description:
        insert_quads.append(
            (f"<{relation_iri}>",
             "<http://www.w3.org/2000/01/rdf-schema#comment>",
             _literal_term(description), graph_iri)
        )
    if symmetric:
        insert_quads.append(
            (f"<{relation_iri}>",
             "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
             "<http://www.w3.org/2002/07/owl#SymmetricProperty>", graph_iri)
        )
    if transitive:
        insert_quads.append(
            (f"<{relation_iri}>",
             "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
             "<http://www.w3.org/2002/07/owl#TransitiveProperty>", graph_iri)
        )
    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_relation_type",
        delta=delta,
        object_kind="relation_type",
        source_ids=[relation_type_id],
        target_graph_iris=[graph_iri],
        metadata={
            "relation_type_id": relation_type_id,
            "ontology_id": ontology_id,
            "name": name,
        },
    )


def compile_update_fact(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    old_object_value = _required(payload, "old_object_value")
    new_object_value = _required(payload, "new_object_value")
    old_object_is_iri = bool(payload.get("old_object_is_iri", False))
    new_object_is_iri = bool(payload.get("new_object_is_iri", False))
    graph_iri = payload.get("graph_iri") or _data_graph_iri(ns, ontology_id)

    subject = _iri_term(subject_iri)
    predicate = _iri_term(predicate_iri)
    old_object = _object_term(old_object_value, is_iri=old_object_is_iri)
    new_object = _object_term(new_object_value, is_iri=new_object_is_iri)
    delta = RdfGraphDelta(
        deletes=[(subject, predicate, old_object, graph_iri)],
        inserts=[(subject, predicate, new_object, graph_iri)],
    )
    fact_id = compute_fact_id(subject_iri, predicate_iri, old_object, graph_iri)
    return CompiledCommand(
        command_kind="update_fact",
        delta=delta,
        object_kind="fact",
        source_ids=[fact_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "fact_id": fact_id,
            "subject_iri": subject_iri,
            "predicate_iri": predicate_iri,
            "old_object_value": old_object_value,
            "new_object_value": new_object_value,
            "graph_iri": graph_iri,
        },
    )


def compile_delete_fact(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    object_value = _required(payload, "object_value")
    object_is_iri = bool(payload.get("object_is_iri", False))
    graph_iri = payload.get("graph_iri") or _data_graph_iri(ns, ontology_id)

    subject = _iri_term(subject_iri)
    predicate = _iri_term(predicate_iri)
    obj = _object_term(object_value, is_iri=object_is_iri)
    delta = RdfGraphDelta(deletes=[(subject, predicate, obj, graph_iri)])
    fact_id = compute_fact_id(subject_iri, predicate_iri, obj, graph_iri)
    return CompiledCommand(
        command_kind="delete_fact",
        delta=delta,
        object_kind="fact",
        source_ids=[fact_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "fact_id": fact_id,
            "subject_iri": subject_iri,
            "predicate_iri": predicate_iri,
            "object_value": object_value,
            "graph_iri": graph_iri,
        },
    )


def compile_create_property(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    class_id = _required(payload, "class_id")
    property_id = payload.get("property_id") or str(uuid.uuid4())
    name = _required(payload, "name")
    description = payload.get("description")
    datatype = payload.get("datatype")
    object_class_id = payload.get("object_class_id")
    if datatype is None and object_class_id is None:
        raise InvalidCommandPayload(
            "create_property requires either datatype (for DatatypeProperty) "
            "or object_class_id (for ObjectProperty)"
        )

    property_iri = str(ns.resource("property", property_id))
    class_iri = str(ns.resource("class", class_id))
    ontology_iri = str(ns.resource("ontology", ontology_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    is_object_property = object_class_id is not None

    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{property_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         "<http://www.w3.org/2002/07/owl#ObjectProperty>" if is_object_property
         else "<http://www.w3.org/2002/07/owl#DatatypeProperty>", graph_iri),
        (f"<{property_iri}>", f"<{op}id>", _literal_term(property_id), graph_iri),
        (f"<{property_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (f"<{property_iri}>", "<http://www.w3.org/2000/01/rdf-schema#label>",
         _literal_term(name), graph_iri),
        (f"<{property_iri}>", "<http://www.w3.org/2000/01/rdf-schema#domain>",
         f"<{class_iri}>", graph_iri),
    ]
    if description:
        insert_quads.append(
            (f"<{property_iri}>", "<http://www.w3.org/2000/01/rdf-schema#comment>",
             _literal_term(description), graph_iri)
        )
    if is_object_property:
        target_iri = str(ns.resource("class", object_class_id))
        insert_quads.append(
            (f"<{property_iri}>", "<http://www.w3.org/2000/01/rdf-schema#range>",
             f"<{target_iri}>", graph_iri)
        )
    else:
        insert_quads.append(
            (f"<{property_iri}>", "<http://www.w3.org/2000/01/rdf-schema#range>",
             f"<{_datatype_iri(datatype)}>", graph_iri)
        )

    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_property",
        delta=delta,
        object_kind="property",
        source_ids=[property_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "class_id": class_id,
            "property_id": property_id,
            "name": name,
            "is_object_property": is_object_property,
        },
    )


def compile_update_property(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "property_id" not in payload and "property_iri" not in payload:
        raise InvalidCommandPayload("update_property requires property_id or property_iri")
    property_id = payload.get("property_id")
    property_iri = payload.get("property_iri") or (
        str(ns.resource("property", property_id)) if property_id else None
    )
    if property_iri is None:
        raise InvalidCommandPayload("update_property requires property_id or property_iri")

    name = payload.get("name")
    description = payload.get("description")
    datatype = payload.get("datatype")
    object_class_id = payload.get("object_class_id")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    prop_term = f"<{property_iri}>"
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []

    if name is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri))
        inserts.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#label>", _literal_term(name), graph_iri))
    if description is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri))
        if description:
            inserts.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", _literal_term(description), graph_iri))
    if datatype is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", f"<{_datatype_iri(datatype)}>", graph_iri))
    if object_class_id is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append(
            (prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>",
             f"<{ns.resource('class', object_class_id)}>", graph_iri)
        )

    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [property_id] if property_id else [property_iri]
    return CompiledCommand(
        command_kind="update_property",
        delta=delta,
        object_kind="property",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "property_id": property_id,
            "property_iri": property_iri,
            "fields_updated": [
                k for k in ("name", "description", "datatype", "object_class_id")
                if payload.get(k) is not None
            ],
        },
    )


def compile_update_relation_type(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "relation_type_id" not in payload and "relation_type_iri" not in payload:
        raise InvalidCommandPayload(
            "update_relation_type requires relation_type_id or relation_type_iri"
        )
    relation_type_id = payload.get("relation_type_id")
    relation_type_iri = payload.get("relation_type_iri") or (
        str(ns.resource("relation-type", relation_type_id)) if relation_type_id else None
    )
    if relation_type_iri is None:
        raise InvalidCommandPayload(
            "update_relation_type requires relation_type_id or relation_type_iri"
        )

    name = payload.get("name")
    description = payload.get("description")
    source_class_id = payload.get("source_class_id")
    target_class_id = payload.get("target_class_id")
    inverse_name = payload.get("inverse_name")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    rel_term = f"<{relation_type_iri}>"
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []

    if name is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri))
        inserts.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#label>", _literal_term(name), graph_iri))
    if description is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri))
        if description:
            inserts.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", _literal_term(description), graph_iri))
    if source_class_id is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#domain>", "?o", graph_iri))
        inserts.append(
            (rel_term, "<http://www.w3.org/2000/01/rdf-schema#domain>",
             f"<{ns.resource('class', source_class_id)}>", graph_iri)
        )
    if target_class_id is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append(
            (rel_term, "<http://www.w3.org/2000/01/rdf-schema#range>",
             f"<{ns.resource('class', target_class_id)}>", graph_iri)
        )
    if inverse_name is not None:
        # Inverse name uses op:inverseName predicate.
        op = str(ns.vocab)
        deletes.append((rel_term, f"<{op}inverseName>", "?o", graph_iri))
        if inverse_name:
            inserts.append((rel_term, f"<{op}inverseName>", _literal_term(inverse_name), graph_iri))

    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [relation_type_id] if relation_type_id else [relation_type_iri]
    return CompiledCommand(
        command_kind="update_relation_type",
        delta=delta,
        object_kind="relation_type",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "relation_type_id": relation_type_id,
            "relation_type_iri": relation_type_iri,
            "fields_updated": [
                k for k in ("name", "description", "source_class_id", "target_class_id", "inverse_name")
                if payload.get(k) is not None
            ],
        },
    )


def _compile_shape_node(
    payload: dict[str, Any], ns: SemanticNamespace, ontology_id: str, shape_iri: str
) -> list[tuple[str, str, str, str]]:
    """Build insert quads for a sh:NodeShape with constraints. Target graph
    is the custom shapes sub-graph; caller is responsible for any deletes."""
    target_class_id = _required(payload, "target_class_id")
    constraints = payload.get("constraints") or []
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    class_iri = str(ns.resource("class", target_class_id))
    shape_term = f"<{shape_iri}>"
    quads: list[tuple[str, str, str, str]] = [
        (shape_term, "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         "<http://www.w3.org/ns/shacl#NodeShape>", graph_iri),
        (shape_term, "<http://www.w3.org/ns/shacl#targetClass>", f"<{class_iri}>", graph_iri),
    ]
    for constraint in constraints:
        path_id = _required(constraint, "path_id")
        property_term = "?b"  # placeholder, replaced below per constraint
        # Use a stable BNode-style label by index for readability of inspection;
        # the canonical-write service persists these as blank nodes.
        property_term = f"_:{shape_iri.split('/')[-1]}__{path_id}"
        quads.append((shape_term, "<http://www.w3.org/ns/shacl#property>", property_term, graph_iri))
        quads.append((property_term, "<http://www.w3.org/ns/shacl#path>",
                      f"<{ns.resource('property', path_id)}>", graph_iri))
        if "min_count" in constraint:
            quads.append((property_term, "<http://www.w3.org/ns/shacl#minCount>",
                          _literal_term(int(constraint["min_count"])), graph_iri))
        if "max_count" in constraint:
            quads.append((property_term, "<http://www.w3.org/ns/shacl#maxCount>",
                          _literal_term(int(constraint["max_count"])), graph_iri))
        if "datatype" in constraint:
            quads.append((property_term, "<http://www.w3.org/ns/shacl#datatype>",
                          f"<{_datatype_iri(constraint['datatype'])}>", graph_iri))
        if "pattern" in constraint:
            quads.append((property_term, "<http://www.w3.org/ns/shacl#pattern>",
                          _literal_term(constraint["pattern"]), graph_iri))
        if "description" in constraint:
            quads.append((property_term, "<http://www.w3.org/2000/01/rdf-schema#comment>",
                          _literal_term(constraint["description"]), graph_iri))
        if "enum_values" in constraint:
            for value in constraint["enum_values"]:
                quads.append((property_term, "<http://www.w3.org/ns/shacl#in>",
                              _literal_term(value), graph_iri))
    return quads


def compile_create_shape(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    shape_id = payload.get("shape_id") or str(uuid.uuid4())
    shape_iri = str(ns.resource("shape", shape_id))
    insert_quads = _compile_shape_node(payload, ns, ontology_id, shape_iri)
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_shape",
        delta=delta,
        object_kind="shape",
        source_ids=[shape_id],
        target_graph_iris=[graph_iri],
        metadata={"ontology_id": ontology_id, "shape_id": shape_id, "shape_iri": shape_iri},
    )


def compile_update_shape(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "shape_id" not in payload and "shape_iri" not in payload:
        raise InvalidCommandPayload("update_shape requires shape_id or shape_iri")
    shape_id = payload.get("shape_id")
    shape_iri = payload.get("shape_iri") or (
        str(ns.resource("shape", shape_id)) if shape_id else None
    )
    if shape_iri is None:
        raise InvalidCommandPayload("update_shape requires shape_id or shape_iri")
    insert_quads = _compile_shape_node(payload, ns, ontology_id, shape_iri)
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    shape_term = f"<{shape_iri}>"
    deletes = [(shape_term, "?p", "?o", graph_iri)]
    delta = RdfGraphDelta(inserts=insert_quads, deletes=deletes)
    source_ids = [shape_id] if shape_id else [shape_iri]
    return CompiledCommand(
        command_kind="update_shape",
        delta=delta,
        object_kind="shape",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={"ontology_id": ontology_id, "shape_id": shape_id, "shape_iri": shape_iri},
    )


def compile_delete_shape(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "shape_id" not in payload and "shape_iri" not in payload:
        raise InvalidCommandPayload("delete_shape requires shape_id or shape_iri")
    shape_id = payload.get("shape_id")
    shape_iri = payload.get("shape_iri") or (
        str(ns.resource("shape", shape_id)) if shape_id else None
    )
    if shape_iri is None:
        raise InvalidCommandPayload("delete_shape requires shape_id or shape_iri")
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    shape_term = f"<{shape_iri}>"
    deletes = [(shape_term, "?p", "?o", graph_iri)]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [shape_id] if shape_id else [shape_iri]
    return CompiledCommand(
        command_kind="delete_shape",
        delta=delta,
        object_kind="shape",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={"ontology_id": ontology_id, "shape_id": shape_id, "shape_iri": shape_iri},
    )


def compile_delete_relation_type(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "relation_type_id" not in payload and "relation_type_iri" not in payload:
        raise InvalidCommandPayload(
            "delete_relation_type requires relation_type_id or relation_type_iri"
        )
    relation_type_id = payload.get("relation_type_id")
    relation_type_iri = payload.get("relation_type_iri") or (
        str(ns.resource("relation-type", relation_type_id)) if relation_type_id else None
    )
    if relation_type_iri is None:
        raise InvalidCommandPayload(
            "delete_relation_type requires relation_type_id or relation_type_iri"
        )

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    rel_term = f"<{relation_type_iri}>"
    deletes = [(rel_term, "?p", "?o", graph_iri)]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [relation_type_id] if relation_type_id else [relation_type_iri]
    return CompiledCommand(
        command_kind="delete_relation_type",
        delta=delta,
        object_kind="relation_type",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "relation_type_id": relation_type_id,
            "relation_type_iri": relation_type_iri,
        },
    )


def compile_delete_property(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "property_id" not in payload and "property_iri" not in payload:
        raise InvalidCommandPayload("delete_property requires property_id or property_iri")
    property_id = payload.get("property_id")
    property_iri = payload.get("property_iri") or (
        str(ns.resource("property", property_id)) if property_id else None
    )
    if property_iri is None:
        raise InvalidCommandPayload("delete_property requires property_id or property_iri")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    prop_term = f"<{property_iri}>"
    deletes = [(prop_term, "?p", "?o", graph_iri)]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [property_id] if property_id else [property_iri]
    return CompiledCommand(
        command_kind="delete_property",
        delta=delta,
        object_kind="property",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={"ontology_id": ontology_id, "property_id": property_id, "property_iri": property_iri},
    )


def compile_delete_class(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "class_id" not in payload and "class_iri" not in payload:
        raise InvalidCommandPayload("delete_class requires class_id or class_iri")
    class_id = payload.get("class_id")
    class_iri = payload.get("class_iri") or (str(ns.resource("class", class_id)) if class_id else None)
    if class_iri is None:
        raise InvalidCommandPayload("delete_class requires class_id or class_iri")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    class_term = f"<{class_iri}>"
    op = str(ns.vocab)
    deletes = [(class_term, "?p", "?o", graph_iri)]
    inserts = [
        (class_term, f"<{op}deprecated>", '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>', graph_iri)
    ]
    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [class_id] if class_id else [class_iri]
    return CompiledCommand(
        command_kind="delete_class",
        delta=delta,
        object_kind="class",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={"ontology_id": ontology_id, "class_id": class_id, "class_iri": class_iri},
    )


def compile_update_class(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "class_id" not in payload and "class_iri" not in payload:
        raise InvalidCommandPayload("update_class requires class_id or class_iri")
    class_id = payload.get("class_id")
    class_iri = payload.get("class_iri") or (str(ns.resource("class", class_id)) if class_id else None)
    if class_iri is None:
        raise InvalidCommandPayload("update_class requires class_id or class_iri")
    name = payload.get("name")
    description = payload.get("description")
    aliases: list[str] | None = payload.get("aliases")
    parent_class_ids: list[str] | None = payload.get("parent_class_ids")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    class_term = f"<{class_iri}>"
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []

    if name is not None:
        deletes.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri))
        inserts.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#label>", _literal_term(name), graph_iri))
    if description is not None:
        deletes.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri))
        if description:
            inserts.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", _literal_term(description), graph_iri))
    if aliases is not None:
        deletes.append((class_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", "?o", graph_iri))
        for alias in aliases:
            inserts.append((class_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", _literal_term(alias), graph_iri))
    if parent_class_ids is not None:
        deletes.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#subClassOf>", "?o", graph_iri))
        for parent_id in parent_class_ids:
            inserts.append((class_term, "<http://www.w3.org/2000/01/rdf-schema#subClassOf>", f"<{ns.resource('class', parent_id)}>", graph_iri))

    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [class_id] if class_id else [class_iri]
    return CompiledCommand(
        command_kind="update_class",
        delta=delta,
        object_kind="class",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "class_id": class_id,
            "class_iri": class_iri,
            "fields_updated": [k for k in ("name", "description", "aliases", "parent_class_ids") if payload.get(k) is not None],
        },
    )


def compile_create_entity(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 — write a NamedIndividual into graph/data/{ontology_id}.

    Writes ``a owl:NamedIndividual``, ``a <class>``, ``rdfs:label``,
    ``skos:altLabel`` per alias, one triple per property.
    """
    ontology_id = _required(payload, "ontology_id")
    entity_id = payload.get("entity_id") or str(uuid.uuid4())
    class_iri_or_legacy_id = _required(payload, "class_iri_or_legacy_id")
    label = _required(payload, "label")
    aliases: list[str] = payload.get("aliases", []) or []
    properties: dict[str, Any] = payload.get("properties", {}) or {}

    # Resolve class IRI: if the caller passes a bare id, expand via the
    # namespace. If it already looks like an IRI (contains ":"), use verbatim.
    if isinstance(class_iri_or_legacy_id, str) and ":" in class_iri_or_legacy_id:
        class_iri = class_iri_or_legacy_id
    else:
        class_iri = str(ns.resource("class", class_iri_or_legacy_id))

    entity_iri = str(ns.resource("entity", entity_id))
    graph_iri = _data_graph_iri(ns, ontology_id)
    op = str(ns.vocab)

    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{entity_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         "<http://www.w3.org/2002/07/owl#NamedIndividual>", graph_iri),
        (f"<{entity_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         f"<{class_iri}>", graph_iri),
        (f"<{entity_iri}>", f"<{op}id>", _literal_term(entity_id), graph_iri),
        (f"<{entity_iri}>",
         "<http://www.w3.org/2000/01/rdf-schema#label>",
         _literal_term(label), graph_iri),
    ]
    for alias in aliases:
        insert_quads.append(
            (f"<{entity_iri}>",
             "<http://www.w3.org/2004/02/skos/core#altLabel>",
             _literal_term(alias), graph_iri)
        )
    for prop_iri, value in properties.items():
        if value is None:
            continue
        insert_quads.append(
            (f"<{entity_iri}>", f"<{prop_iri}>", _literal_term(value), graph_iri)
        )

    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_entity",
        delta=delta,
        object_kind="entity",
        source_ids=[entity_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "entity_id": entity_id,
            "entity_iri": entity_iri,
            "class_iri": class_iri,
            "label": label,
        },
    )


def compile_update_entity(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 — patch label / aliases / properties of an existing entity."""
    ontology_id = _required(payload, "ontology_id")
    if "entity_id" not in payload and "entity_iri" not in payload:
        raise InvalidCommandPayload("update_entity requires entity_id or entity_iri")
    entity_id = payload.get("entity_id")
    entity_iri = payload.get("entity_iri") or (
        str(ns.resource("entity", entity_id)) if entity_id else None
    )
    if entity_iri is None:
        raise InvalidCommandPayload("update_entity requires entity_id or entity_iri")

    label = payload.get("label")
    aliases: list[str] | None = payload.get("aliases")
    properties: dict[str, Any] | None = payload.get("properties")

    graph_iri = _data_graph_iri(ns, ontology_id)
    entity_term = f"<{entity_iri}>"
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []

    if label is not None:
        deletes.append((entity_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri))
        inserts.append((entity_term, "<http://www.w3.org/2000/01/rdf-schema#label>", _literal_term(label), graph_iri))
    if aliases is not None:
        deletes.append((entity_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", "?o", graph_iri))
        for alias in aliases:
            inserts.append((entity_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", _literal_term(alias), graph_iri))
    if properties is not None:
        for prop_iri, value in properties.items():
            deletes.append((entity_term, f"<{prop_iri}>", "?o", graph_iri))
            if value is None:
                continue
            inserts.append((entity_term, f"<{prop_iri}>", _literal_term(value), graph_iri))

    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [entity_id] if entity_id else [entity_iri]
    return CompiledCommand(
        command_kind="update_entity",
        delta=delta,
        object_kind="entity",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "entity_id": entity_id,
            "entity_iri": entity_iri,
            "fields_updated": [
                k for k in ("label", "aliases", "properties")
                if payload.get(k) is not None
            ],
        },
    )


def compile_delete_entity(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 — remove every triple whose subject or object is the entity.

    Cascades to relations: any triple where this entity appears as the object
    (e.g. ``<other> someRelation <entity>``) is also removed.
    """
    ontology_id = _required(payload, "ontology_id")
    if "entity_id" not in payload and "entity_iri" not in payload:
        raise InvalidCommandPayload("delete_entity requires entity_id or entity_iri")
    entity_id = payload.get("entity_id")
    entity_iri = payload.get("entity_iri") or (
        str(ns.resource("entity", entity_id)) if entity_id else None
    )
    if entity_iri is None:
        raise InvalidCommandPayload("delete_entity requires entity_id or entity_iri")

    graph_iri = _data_graph_iri(ns, ontology_id)
    entity_term = f"<{entity_iri}>"
    deletes = [
        (entity_term, "?p", "?o", graph_iri),
        ("?s", "?p", entity_term, graph_iri),
    ]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [entity_id] if entity_id else [entity_iri]
    return CompiledCommand(
        command_kind="delete_entity",
        delta=delta,
        object_kind="entity",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "entity_id": entity_id,
            "entity_iri": entity_iri,
        },
    )


def compile_create_relation(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 — write ``<source> <relation_type> <target>`` to the data graph.

    relation_type_iri is taken verbatim so callers can target arbitrary OWL
    ObjectProperties (defined on the ontology graph).
    """
    ontology_id = _required(payload, "ontology_id")
    source_iri = _required(payload, "source_entity_iri")
    relation_type_iri = _required(payload, "relation_type_iri")
    target_iri = _required(payload, "target_entity_iri")

    graph_iri = _data_graph_iri(ns, ontology_id)
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{source_iri}>", f"<{relation_type_iri}>", f"<{target_iri}>", graph_iri),
    ]

    delta = RdfGraphDelta(inserts=insert_quads)
    source_ids = [f"{source_iri}|{relation_type_iri}|{target_iri}"]
    return CompiledCommand(
        command_kind="create_relation",
        delta=delta,
        object_kind="relation",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "source_entity_iri": source_iri,
            "relation_type_iri": relation_type_iri,
            "target_entity_iri": target_iri,
        },
    )


def compile_delete_relation(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 — remove the specific ``(source, predicate, target)`` triple."""
    ontology_id = _required(payload, "ontology_id")
    source_iri = _required(payload, "source_entity_iri")
    relation_type_iri = _required(payload, "relation_type_iri")
    target_iri = _required(payload, "target_entity_iri")

    graph_iri = _data_graph_iri(ns, ontology_id)
    deletes = [
        (f"<{source_iri}>", f"<{relation_type_iri}>", f"<{target_iri}>", graph_iri),
    ]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [f"{source_iri}|{relation_type_iri}|{target_iri}"]
    return CompiledCommand(
        command_kind="delete_relation",
        delta=delta,
        object_kind="relation",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "source_entity_iri": source_iri,
            "relation_type_iri": relation_type_iri,
            "target_entity_iri": target_iri,
        },
    )


# Stage 2 §7.4 — Catalog mapping canonical-write kinds ----------------------------------


_TARGET_PREDICATES = {
    "class": "targetClass",
    "property": "targetProperty",
    "relation_type": "targetRelationType",
}


def _import_graph_for(ns: SemanticNamespace, source_id: str, run_id: str) -> str:
    """Build the graph/import/{source_id}/{run_id} IRI."""
    base = str(ns.graph_iri_prefix).rstrip("/")
    return f"{base}/import/{source_id}/{run_id}"


def compile_create_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §7.4 — write an ``op:SemanticMapping`` resource.

    Default target graph is ``graph/ontology/{ontology_id}``. When ``source_id``
    and ``run_id`` are supplied the mapping is written to
    ``graph/import/{source_id}/{run_id}`` and a ``prov:wasDerivedBy`` link is
    attached to record the import-run provenance.
    """
    ontology_id = _required(payload, "ontology_id")
    mapping_id = payload.get("mapping_id") or str(uuid.uuid4())
    external_field_iri = _required(payload, "external_field_iri")
    target_type = _required(payload, "target_type")
    if target_type not in _TARGET_PREDICATES:
        raise InvalidCommandPayload(
            "target_type must be one of: " + ", ".join(sorted(_TARGET_PREDICATES))
        )
    target_iri = _required(payload, "target_iri")
    join_key = _required(payload, "join_key")
    confidence = float(payload.get("confidence", 1.0))
    owner = payload.get("owner")
    source_id = payload.get("source_id")
    run_id = payload.get("run_id")
    import_run_iri = payload.get("import_run_iri")

    if (source_id is None) != (run_id is None):
        raise InvalidCommandPayload(
            "create_mapping requires both source_id and run_id, or neither"
        )

    mapping_iri = str(ns.resource("mapping", mapping_id))
    op = str(ns.vocab)
    if source_id and run_id:
        graph_iri = _import_graph_for(ns, source_id, run_id)
    else:
        graph_iri = _ontology_graph_iri(ns, ontology_id)

    target_predicate = _TARGET_PREDICATES[target_type]
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{mapping_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         f"<{op}SemanticMapping>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}id>", _literal_term(mapping_id), graph_iri),
        (f"<{mapping_iri}>", f"<{op}ontology>",
         f"<{ns.resource('ontology', ontology_id)}>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}externalField>",
         f"<{external_field_iri}>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}{target_predicate}>",
         f"<{target_iri}>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}targetType>",
         _literal_term(target_type), graph_iri),
        (f"<{mapping_iri}>", f"<{op}joinKey>",
         _literal_term(join_key), graph_iri),
        (f"<{mapping_iri}>", f"<{op}confidence>",
         _literal_term(confidence), graph_iri),
    ]
    if owner:
        insert_quads.append(
            (f"<{mapping_iri}>", f"<{op}owner>", _literal_term(owner), graph_iri)
        )
    if source_id and run_id:
        if import_run_iri:
            insert_quads.append(
                (f"<{mapping_iri}>",
                 "<http://www.w3.org/ns/prov#wasDerivedBy>",
                 f"<{import_run_iri}>", graph_iri)
            )
        insert_quads.append(
            (f"<{mapping_iri}>", f"<{op}sourceId>",
             _literal_term(source_id), graph_iri)
        )
        insert_quads.append(
            (f"<{mapping_iri}>", f"<{op}runId>",
             _literal_term(run_id), graph_iri)
        )

    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="create_mapping",
        delta=delta,
        object_kind="mapping",
        source_ids=[mapping_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "mapping_id": mapping_id,
            "mapping_iri": mapping_iri,
            "target_type": target_type,
            "target_iri": target_iri,
            "external_field_iri": external_field_iri,
            "graph_iri": graph_iri,
            "import_source": bool(source_id and run_id),
        },
    )


def compile_update_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §7.4 — patch join_key / confidence / owner on an existing mapping.

    Target graph resolves the same way as ``create_mapping``: ontology graph by
    default, import graph when ``source_id`` + ``run_id`` are present.
    """
    ontology_id = _required(payload, "ontology_id")
    if "mapping_id" not in payload and "mapping_iri" not in payload:
        raise InvalidCommandPayload("update_mapping requires mapping_id or mapping_iri")
    mapping_id = payload.get("mapping_id")
    mapping_iri = payload.get("mapping_iri") or (
        str(ns.resource("mapping", mapping_id)) if mapping_id else None
    )
    if mapping_iri is None:
        raise InvalidCommandPayload("update_mapping requires mapping_id or mapping_iri")

    source_id = payload.get("source_id")
    run_id = payload.get("run_id")
    if source_id and run_id:
        graph_iri = _import_graph_for(ns, source_id, run_id)
    else:
        graph_iri = _ontology_graph_iri(ns, ontology_id)

    join_key = payload.get("join_key")
    confidence = payload.get("confidence")
    owner = payload.get("owner")
    target_type = payload.get("target_type")
    target_iri = payload.get("target_iri")

    mapping_term = f"<{mapping_iri}>"
    op = str(ns.vocab)
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []

    if join_key is not None:
        deletes.append((mapping_term, f"<{op}joinKey>", "?o", graph_iri))
        inserts.append((mapping_term, f"<{op}joinKey>", _literal_term(join_key), graph_iri))
    if confidence is not None:
        deletes.append((mapping_term, f"<{op}confidence>", "?o", graph_iri))
        inserts.append((mapping_term, f"<{op}confidence>", _literal_term(float(confidence)), graph_iri))
    if owner is not None:
        deletes.append((mapping_term, f"<{op}owner>", "?o", graph_iri))
        if owner:
            inserts.append((mapping_term, f"<{op}owner>", _literal_term(owner), graph_iri))
    if target_type is not None and target_iri is not None:
        if target_type not in _TARGET_PREDICATES:
            raise InvalidCommandPayload(
                "target_type must be one of: " + ", ".join(sorted(_TARGET_PREDICATES))
            )
        target_predicate = _TARGET_PREDICATES[target_type]
        deletes.append((mapping_term, f"<{op}{target_predicate}>", "?o", graph_iri))
        inserts.append((mapping_term, f"<{op}{target_predicate}>", f"<{target_iri}>", graph_iri))
        deletes.append((mapping_term, f"<{op}targetType>", "?o", graph_iri))
        inserts.append((mapping_term, f"<{op}targetType>", _literal_term(target_type), graph_iri))

    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    source_ids = [mapping_id] if mapping_id else [mapping_iri]
    return CompiledCommand(
        command_kind="update_mapping",
        delta=delta,
        object_kind="mapping",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "mapping_id": mapping_id,
            "mapping_iri": mapping_iri,
            "graph_iri": graph_iri,
            "fields_updated": [
                k for k in ("join_key", "confidence", "owner", "target_type", "target_iri")
                if payload.get(k) is not None
            ],
        },
    )


def compile_delete_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §7.4 — remove every triple whose subject is the mapping IRI."""
    ontology_id = _required(payload, "ontology_id")
    if "mapping_id" not in payload and "mapping_iri" not in payload:
        raise InvalidCommandPayload("delete_mapping requires mapping_id or mapping_iri")
    mapping_id = payload.get("mapping_id")
    mapping_iri = payload.get("mapping_iri") or (
        str(ns.resource("mapping", mapping_id)) if mapping_id else None
    )
    if mapping_iri is None:
        raise InvalidCommandPayload("delete_mapping requires mapping_id or mapping_iri")

    source_id = payload.get("source_id")
    run_id = payload.get("run_id")
    if source_id and run_id:
        graph_iri = _import_graph_for(ns, source_id, run_id)
    else:
        graph_iri = _ontology_graph_iri(ns, ontology_id)

    mapping_term = f"<{mapping_iri}>"
    deletes = [(mapping_term, "?p", "?o", graph_iri)]
    delta = RdfGraphDelta(inserts=[], deletes=deletes)
    source_ids = [mapping_id] if mapping_id else [mapping_iri]
    return CompiledCommand(
        command_kind="delete_mapping",
        delta=delta,
        object_kind="mapping",
        source_ids=source_ids,
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "mapping_id": mapping_id,
            "mapping_iri": mapping_iri,
            "graph_iri": graph_iri,
        },
    )


# Stage 2 §6.4 — review_assertion canonical-write kind -----------------------------------


_VALID_REVIEW_DECISIONS = {"approved", "rejected", "needs_correction"}


def _object_term_for_review(value: Any) -> str:
    """Render an object term for RDF-star reification.

    A dict carrying an ``iri`` key produces an IRI term; everything else is
    stringified and rendered as a literal. The literal form matches the
    caller-supplied value verbatim (callers pre-format numbers / booleans
    as their string forms via the API layer; the canonical-write store
    interprets a bare quoted string as xsd:string).
    """
    if isinstance(value, dict) and "iri" in value and value["iri"]:
        return f"<{value['iri']}>"
    return _literal_term(value)


def _quoted_triple_term(subject_iri: str, predicate_iri: str, object_term: str) -> str:
    """Build an RDF-star ``<<s p o>>>`` term.

    The result has the shape ``<<<s> <p> o>>>`` for IRI objects and
    ``<<<s> <p> "literal">>>`` for literal objects — i.e. 3 leading
    angle brackets (``<<`` + ``<``) and 3 trailing angle brackets (``>`` +
    ``>>``). ``object_term`` is expected to already be in turtle object
    form (IRI angle-bracketed or literal-quoted), produced by
    ``_object_term_for_review``.
    """
    return f"<<<{subject_iri}> <{predicate_iri}> {object_term}>>"


def _reviewer_term(reviewer: str, ns: SemanticNamespace) -> str:
    """Render a reviewer term. Accepts ``user:<id>`` (preferred) or a bare
    IRI; ``user:`` form is expanded into the platform namespace."""
    if reviewer.startswith("http://") or reviewer.startswith("https://"):
        return f"<{reviewer}>"
    if ":" in reviewer and not reviewer.startswith("user:"):
        # Already namespaced (e.g. ``agent:foo``) — render verbatim as IRI
        # under the platform base IRI to keep it stable.
        return f"<{str(ns.base_iri).rstrip('/')}/{reviewer}>"
    # ``user:alice`` form
    identifier = reviewer.split(":", 1)[1] if ":" in reviewer else reviewer
    return f"<{ns.resource('user', identifier)}>"


def compile_review_assertion(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §6.4 — write an RDF-star reification recording a fact review.

    The compiled delta attaches ``op:auditStatus``, ``op:reviewReason``,
    ``op:reviewedBy``, ``op:reviewedAt`` to the quoted triple term, with
    an optional ``op:linkedFixProposal`` for rejections. Target graph is
    selected by ``assertion_kind``:

    - ``asserted`` / ``missing_evidence`` → ``graph/data/{ontology_id}``
    - ``inferred`` → ``result_graph_iri`` (caller-supplied reasoning-result)
    - ``rule_derived`` → ``result_graph_iri`` (caller-supplied rule-result)

    The ``fact_id`` carried in ``metadata`` is the SHA-256 over the
    canonical N-Triples form of the reviewed triple.
    """
    ontology_id = _required(payload, "ontology_id")
    assertion_kind = payload.get("assertion_kind", "asserted")
    if assertion_kind not in {"asserted", "inferred", "rule_derived", "missing_evidence"}:
        raise InvalidCommandPayload(
            "assertion_kind must be one of: asserted, inferred, rule_derived, "
            "missing_evidence"
        )
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    object_value = _required(payload, "object_value")
    decision = _required(payload, "decision")
    if decision not in _VALID_REVIEW_DECISIONS:
        raise InvalidCommandPayload(
            "decision must be one of: " + ", ".join(sorted(_VALID_REVIEW_DECISIONS))
        )
    reason = payload.get("reason") or ""
    reviewed_by = _required(payload, "reviewed_by")
    linked_fix_proposal_id = payload.get("linked_fix_proposal_id")
    if decision == "rejected" and not linked_fix_proposal_id:
        raise InvalidCommandPayload(
            "rejected review requires a linked_fix_proposal_id"
        )
    result_graph_iri = payload.get("result_graph_iri")

    # Select target graph by assertion_kind.
    if assertion_kind in {"asserted", "missing_evidence"}:
        graph_iri = _data_graph_iri(ns, ontology_id)
    elif assertion_kind == "inferred":
        if not result_graph_iri:
            raise InvalidCommandPayload(
                "inferred review requires result_graph_iri (reasoning-result graph)"
            )
        graph_iri = result_graph_iri
    else:  # rule_derived
        if not result_graph_iri:
            raise InvalidCommandPayload(
                "rule_derived review requires result_graph_iri (rule-result graph)"
            )
        graph_iri = result_graph_iri

    object_term = _object_term_for_review(object_value)
    quoted = _quoted_triple_term(subject_iri, predicate_iri, object_term)
    fact_id = compute_fact_id(subject_iri, predicate_iri, object_term, graph_iri)
    op = str(ns.vocab)

    from datetime import datetime, timezone

    reviewed_at = datetime.now(timezone.utc).isoformat()

    insert_quads: list[tuple[str, str, str, str]] = [
        (quoted, f"<{op}auditStatus>", _literal_term(decision), graph_iri),
        (quoted, f"<{op}reviewReason>", _literal_term(reason), graph_iri),
        (quoted, f"<{op}reviewedBy>", _reviewer_term(reviewed_by, ns), graph_iri),
        (
            quoted,
            f"<{op}reviewedAt>",
            _literal_term(reviewed_at),
            graph_iri,
        ),
        # fact_id links the reification back to the stable digest the
        # FactAuditPage uses to dedupe reviews across runs.
        (quoted, f"<{op}factId>", _literal_term(fact_id), graph_iri),
    ]
    if linked_fix_proposal_id:
        insert_quads.append(
            (
                quoted,
                f"<{op}linkedFixProposal>",
                f"<{ns.resource('fix-proposal', linked_fix_proposal_id)}>",
                graph_iri,
            )
        )

    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="review_assertion",
        delta=delta,
        object_kind="fact_review",
        source_ids=[fact_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "assertion_kind": assertion_kind,
            "decision": decision,
            "fact_id": fact_id,
            "subject_iri": subject_iri,
            "predicate_iri": predicate_iri,
            "object_value": object_value,
            "reviewed_by": reviewed_by,
            "reason": reason,
            "linked_fix_proposal_id": linked_fix_proposal_id,
            "graph_iri": graph_iri,
        },
    )


def compile_bind_fact_evidence(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Bind evidence text or chunk to a specific fact (identified by fact_id).

    Stores in Postgres only — does not write RDF. The fact_id is computed
    from (s, p, o, g) using canonical N-Triples; if the caller provides a
    fact_id it must match or the command is rejected.

    .. note::
        Must be applied via the POST /api/semantic/graph-sets/{gs}/fact-evidence
        REST endpoint, NOT via ``apply_compiled_command``. The compiler emits
        an empty RdfGraphDelta on purpose; applying it through the standard
        RDF-only executor will silently no-op the Postgres write.
    """
    ontology_id = _required(payload, "ontology_id")
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    object_value = _required(payload, "object_value")
    object_is_iri = bool(payload.get("object_is_iri", False))
    object_datatype = payload.get("object_datatype")
    object_lang = payload.get("object_lang")
    graph_iri = payload.get("graph_iri") or _data_graph_iri(ns, ontology_id)
    text = str(_required(payload, "text")).strip()
    if not text:
        raise InvalidCommandPayload("text must not be empty")

    object_term = canonical_object_term(
        object_value, is_iri=object_is_iri, datatype=object_datatype, lang=object_lang
    )
    fid = compute_fact_id(subject_iri, predicate_iri, object_term, graph_iri)

    provided_fid = payload.get("fact_id")
    if provided_fid is not None and provided_fid != fid:
        raise InvalidCommandPayload(
            f"fact_id mismatch: caller provided {provided_fid}, computed {fid}"
        )

    # No RDF writes — repository call is performed by the command executor
    # at apply time, not here. The delta is empty.
    delta = RdfGraphDelta(inserts=[], deletes=[])
    return CompiledCommand(
        command_kind="bind_fact_evidence",
        delta=delta,
        object_kind="fact_evidence",
        source_ids=[subject_iri, fid],
        target_graph_iris=[],  # no graph writes
        metadata={
            "ontology_id": ontology_id,
            "fact_id": fid,
            "subject_iri": subject_iri,
            "predicate_iri": predicate_iri,
            "object_value": object_term,
            "graph_iri": graph_iri,
            "chunk_id": payload.get("chunk_id"),
            "evidence_artifact_id": payload.get("evidence_artifact_id"),
            "document_filename": payload.get("document_filename"),
            "sequence": payload.get("sequence"),
            "char_start": payload.get("char_start"),
            "char_end": payload.get("char_end"),
            "text": text,
            "actor": payload.get("actor"),
            "reason": payload.get("reason"),
        },
    )


def compile_unbind_fact_evidence(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Delete a fact evidence binding from Postgres by binding_id.

    .. note::
        Must be applied via the DELETE
        /api/semantic/graph-sets/{gs}/fact-evidence/{binding_id} REST
        endpoint, NOT via ``apply_compiled_command``. The compiler emits an
        empty RdfGraphDelta on purpose; applying it through the standard
        RDF-only executor will silently no-op the Postgres write.
    """
    _required(payload, "ontology_id")
    binding_id = _required(payload, "binding_id")
    delta = RdfGraphDelta(inserts=[], deletes=[])
    return CompiledCommand(
        command_kind="unbind_fact_evidence",
        delta=delta,
        object_kind="fact_evidence",
        source_ids=[binding_id],
        target_graph_iris=[],
        metadata={"ontology_id": payload["ontology_id"], "binding_id": binding_id},
    )


_COMPILERS: dict[str, Compiler] = {
    "create_class": compile_create_class,
    "create_relation_type": compile_create_relation_type,
    "update_fact": compile_update_fact,
    "delete_fact": compile_delete_fact,
    "bind_fact_evidence": compile_bind_fact_evidence,
    "unbind_fact_evidence": compile_unbind_fact_evidence,
    "update_class": compile_update_class,
    "delete_class": compile_delete_class,
    "create_property": compile_create_property,
    "update_property": compile_update_property,
    "delete_property": compile_delete_property,
    "update_relation_type": compile_update_relation_type,
    "delete_relation_type": compile_delete_relation_type,
    "create_shape": compile_create_shape,
    "update_shape": compile_update_shape,
    "delete_shape": compile_delete_shape,
    "create_entity": compile_create_entity,
    "update_entity": compile_update_entity,
    "delete_entity": compile_delete_entity,
    "create_relation": compile_create_relation,
    "delete_relation": compile_delete_relation,
    "create_mapping": compile_create_mapping,
    "update_mapping": compile_update_mapping,
    "delete_mapping": compile_delete_mapping,
    "review_assertion": compile_review_assertion,
}


def supported_command_kinds() -> list[str]:
    return sorted(_COMPILERS)


def compile_command(
    command_kind: str,
    payload: dict[str, Any],
    settings: Settings,
) -> CompiledCommand:
    compiler = _COMPILERS.get(command_kind)
    if compiler is None:
        raise UnsupportedCommandKind(
            f"Unsupported product command kind: {command_kind}. "
            f"Supported: {', '.join(supported_command_kinds())}"
        )
    ns = namespace_from_settings(settings)
    return compiler(payload, ns, settings)
