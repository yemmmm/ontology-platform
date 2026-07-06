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


def compile_submit_assertion(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    fact_claim_id = payload.get("fact_claim_id") or str(uuid.uuid4())
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    value = _required(payload, "value")
    confidence = float(payload.get("confidence", 1.0))
    audit_status = payload.get("audit_status", "system_accepted")
    evidence_status = payload.get("evidence_status", "evidence_bound")
    evidence_ids: list[str] = payload.get("evidence_ids", []) or []

    fact_iri = str(ns.resource("fact-claim", fact_claim_id))
    graph_iri = _data_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{fact_iri}>",
         "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
         f"<{op}FactClaim>", graph_iri),
        (f"<{fact_iri}>", f"<{op}id>", _literal_term(fact_claim_id), graph_iri),
        (f"<{fact_iri}>", f"<{op}subject>", f"<{subject_iri}>", graph_iri),
        (f"<{fact_iri}>", f"<{op}predicate>", f"<{predicate_iri}>", graph_iri),
        (f"<{fact_iri}>", f"<{op}value>", _literal_term(value), graph_iri),
        (f"<{fact_iri}>", f"<{op}confidence>", _literal_term(confidence), graph_iri),
        (f"<{fact_iri}>", f"<{op}auditStatus>", _literal_term(audit_status), graph_iri),
        (f"<{fact_iri}>", f"<{op}evidenceStatus>", _literal_term(evidence_status), graph_iri),
    ]
    for evidence_id in evidence_ids:
        insert_quads.append(
            (f"<{fact_iri}>", f"<{op}evidence>",
             f"<{ns.resource('evidence', evidence_id)}>", graph_iri)
        )
    delta = RdfGraphDelta(inserts=insert_quads)
    return CompiledCommand(
        command_kind="submit_assertion",
        delta=delta,
        object_kind="fact_claim",
        source_ids=[fact_claim_id],
        target_graph_iris=[graph_iri],
        metadata={
            "fact_claim_id": fact_claim_id,
            "ontology_id": ontology_id,
            "evidence_status": evidence_status,
            "missing_evidence": evidence_status == "missing_evidence",
        },
    )


def compile_update_evidence_status(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    fact_claim_id = _required(payload, "fact_claim_id")
    new_status = _required(payload, "evidence_status")
    if new_status not in {"evidence_bound", "missing_evidence"}:
        raise InvalidCommandPayload(
            "evidence_status must be 'evidence_bound' or 'missing_evidence'"
        )
    fact_iri = str(ns.resource("fact-claim", fact_claim_id))
    graph_iri = _data_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    deletes = [
        (f"<{fact_iri}>", f"<{op}evidenceStatus>", "?o", graph_iri),
    ]
    inserts = [
        (f"<{fact_iri}>", f"<{op}evidenceStatus>", _literal_term(new_status), graph_iri),
    ]
    delta = RdfGraphDelta(inserts=inserts, deletes=deletes)
    return CompiledCommand(
        command_kind="update_evidence_status",
        delta=delta,
        object_kind="fact_claim",
        source_ids=[fact_claim_id],
        target_graph_iris=[graph_iri],
        metadata={
            "fact_claim_id": fact_claim_id,
            "ontology_id": ontology_id,
            "new_status": new_status,
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
    ``skos:altLabel`` per alias, one triple per property, and an
    ``op:evidenceStatus "missing_evidence"`` marker per ADR 0004 §301-303.
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
    # Default evidence_status marker.
    insert_quads.append(
        (f"<{entity_iri}>", f"<{op}evidenceStatus>",
         _literal_term("missing_evidence"), graph_iri)
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
    ObjectProperties (defined on the ontology graph). The triple is decorated
    with ``op:evidenceStatus "missing_evidence"`` on the subject entity to
    flag the new assertion for review.
    """
    ontology_id = _required(payload, "ontology_id")
    source_iri = _required(payload, "source_entity_iri")
    relation_type_iri = _required(payload, "relation_type_iri")
    target_iri = _required(payload, "target_entity_iri")

    graph_iri = _data_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    insert_quads: list[tuple[str, str, str, str]] = [
        (f"<{source_iri}>", f"<{relation_type_iri}>", f"<{target_iri}>", graph_iri),
    ]
    # Track the new relation as missing-evidence on the subject entity so the
    # FactAuditPage missing-evidence tab surfaces it for review.
    insert_quads.append(
        (f"<{source_iri}>", f"<{op}evidenceStatus>",
         _literal_term("missing_evidence"), graph_iri)
    )

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


_COMPILERS: dict[str, Compiler] = {
    "create_class": compile_create_class,
    "create_relation_type": compile_create_relation_type,
    "submit_assertion": compile_submit_assertion,
    "update_evidence_status": compile_update_evidence_status,
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
