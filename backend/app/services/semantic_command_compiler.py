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
