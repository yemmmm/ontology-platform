"""Phase 7 product command compilers.

Thin adapters that translate structured product API commands into the same
:class:`RdfGraphDelta` shape produced by direct semantic edits. The canonical
write service consumes the delta without knowing which surface produced it, so
product APIs and direct semantic APIs share one validation, audit, and revision
pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, SKOS

from app.core.config import Settings
from app.repositories.rdf_store import RdfGraphDelta
from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_export import SemanticNamespace, namespace_from_settings
from app.services.operation_semantics import (
    OperationValidationError,
    canonical_operation_iri,
    operation_graph_iri,
    operation_quads,
    operation_vocabulary,
    validate_operation_payload,
)
from app.security.secrets import SecretDetected, scan_domain_payload
from app.services.semantic_lineage_identity import InvalidLineageStatement, canonical_iri


class CommandCompilerError(RuntimeError):
    status_code = 400


class UnsupportedCommandKind(CommandCompilerError):
    pass


class InvalidCommandPayload(CommandCompilerError):
    pass


class ClassMembershipConflict(CommandCompilerError):
    """R3.0-009: legacy scalar class and ``class_iris`` disagree.

    ``code`` is surfaced verbatim as the ModelingBatch finding code so the
    caller can locate and repair the membership expression; ``fields`` names
    the payload fields the finding points at (R3.0-009 §8).
    """

    code = "class_membership_conflict"
    fields: tuple[str, ...] = ()

    def __init__(self, message: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.fields = fields


class ShapeTargetConflict(CommandCompilerError):
    """R3.0-009: zero or several Shape target selectors were supplied.

    ``create_shape`` / ``update_shape`` accept exactly one non-empty target
    field; compound targets must be modelled as separate shapes. ``fields``
    names the payload fields the finding points at (R3.0-009 §8).
    """

    code = "shape_target_conflict"
    fields: tuple[str, ...] = ()

    def __init__(self, message: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.fields = fields


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


def _required_absolute_iri(payload: dict[str, Any], key: str) -> str:
    value = _required(payload, key)
    if not isinstance(value, str):
        raise InvalidCommandPayload(f"{key} must be an absolute RDF IRI")
    try:
        return canonical_iri(value)
    except InvalidLineageStatement as exc:
        raise InvalidCommandPayload(f"{key} must be an absolute RDF IRI") from exc


def _iri_term(iri: str) -> str:
    return f"<{iri}>"


def _property_iri(property_key: object, ns: SemanticNamespace) -> str:
    """Resolve a property payload key without emitting a relative RDF predicate."""
    if not isinstance(property_key, str) or not property_key:
        raise InvalidCommandPayload("properties keys must be non-empty strings")
    return property_key if ":" in property_key else str(ns.resource("property", property_key))


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
_XSD_BARE_LOCAL_NAMES = frozenset(
    {
        "anyURI",
        "base64Binary",
        "boolean",
        "byte",
        "date",
        "dateTime",
        "decimal",
        "double",
        "float",
        "hexBinary",
        "int",
        "integer",
        "long",
        "negativeInteger",
        "nonNegativeInteger",
        "nonPositiveInteger",
        "positiveInteger",
        "short",
        "string",
        "time",
        "unsignedByte",
        "unsignedInt",
        "unsignedLong",
        "unsignedShort",
    }
)


def _datatype_iri(value: str) -> str:
    """Normalize a datatype value to a full IRI string (without angle brackets).

    Accepts ``xsd:string`` style prefixes, recognized bare XML Schema local
    names, or full IRIs. Unknown bare values remain unchanged for compatibility.
    """
    if value.startswith("xsd:"):
        return f"{_XSD_PREFIX}{value[4:]}"
    if value in _XSD_BARE_LOCAL_NAMES:
        return f"{_XSD_PREFIX}{value}"
    return value


def _ontology_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("ontology", ontology_id))


def _data_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("data", ontology_id))


def _shapes_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return str(ns.graph("shapes", ontology_id))


def _shapes_custom_graph_iri(ns: SemanticNamespace, ontology_id: str) -> str:
    return f"{_shapes_graph_iri(ns, ontology_id)}/custom"


_NAMED_INDIVIDUAL_IRI = "http://www.w3.org/2002/07/owl#NamedIndividual"
_RDF_TYPE_IRI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _reject_named_individual_marker(
    relation_type_iri: str, target_iri: str, command_kind: str
) -> None:
    """The ``owl:NamedIndividual`` marker belongs to entity lifecycle commands."""
    if relation_type_iri == _RDF_TYPE_IRI and target_iri == _NAMED_INDIVIDUAL_IRI:
        raise InvalidCommandPayload(
            f"{command_kind} must not write or remove the owl:NamedIndividual marker; "
            "use create_entity / delete_entity for the entity marker"
        )


def _expand_class_iri(value: Any, ns: SemanticNamespace, *, field: str) -> str:
    """Expand one class reference to an absolute IRI (R3.0-009 §4.1)."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidCommandPayload(f"{field} must be a non-empty class id or absolute IRI")
    candidate = value.strip()
    if candidate == _NAMED_INDIVIDUAL_IRI or candidate == "owl:NamedIndividual":
        raise InvalidCommandPayload(
            f"{field} must name a business Class; owl:NamedIndividual is an entity marker"
        )
    if ":" in candidate:
        try:
            return canonical_iri(candidate)
        except InvalidLineageStatement as exc:
            raise InvalidCommandPayload(f"{field} must be an absolute RDF IRI") from exc
    return str(ns.resource("class", candidate))


def _normalized_class_iris(
    payload: dict[str, Any], ns: SemanticNamespace
) -> tuple[list[str], str | None]:
    """Normalize legacy scalar + ``class_iris`` into one deduplicated set.

    R3.0-009 §4.1/§6.2: both fields omitted, or an empty array alone, is the
    legal zero-member state.  A legacy scalar becomes the single member.
    When both are supplied the expanded scalar must be present in the array —
    otherwise the payload is a ``class_membership_conflict``.
    """
    legacy = payload.get("class_iri_or_legacy_id")
    array = payload.get("class_iris")
    if array is not None and not isinstance(array, list):
        raise InvalidCommandPayload("class_iris must be an array of class ids or absolute IRIs")
    legacy_iri: str | None = None
    if legacy is not None:
        legacy_iri = _expand_class_iri(legacy, ns, field="class_iri_or_legacy_id")
    members: list[str] = []
    if array is not None:
        for entry in array:
            members.append(_expand_class_iri(entry, ns, field="class_iris"))
    elif legacy_iri is not None:
        # Legacy scalar-only payload: the scalar becomes the single member.
        members.append(legacy_iri)
    if legacy_iri is not None and array is not None:
        # An empty array next to a non-empty scalar is the same conflict as a
        # mismatched membership list (R3.0-009 §6.2).
        if legacy_iri not in members:
            raise ClassMembershipConflict(
                "class_membership_conflict: class_iri_or_legacy_id "
                f"{legacy_iri} is absent from class_iris",
                fields=("class_iri_or_legacy_id", "class_iris"),
            )
    deduped = sorted(set(members))
    return deduped, legacy_iri


def _operation_error(exc: OperationValidationError) -> InvalidCommandPayload:
    error = InvalidCommandPayload(f"{exc.code}: {exc}")
    error.code = exc.code
    return error


def compile_create_operation(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    try:
        operation = validate_operation_payload(payload, settings=settings, create=True)
    except OperationValidationError as exc:
        raise _operation_error(exc) from exc
    delta = RdfGraphDelta(inserts=operation_quads(operation, settings, ontology_id))
    return CompiledCommand(
        command_kind="create_operation",
        delta=delta,
        object_kind="operation",
        source_ids=[operation["operation_id"]],
        target_graph_iris=[operation_graph_iri(settings, ontology_id)],
        metadata={
            "ontology_id": ontology_id,
            "operation_id": operation["operation_id"],
            "operation_iri": operation["operation_iri"],
        },
    )


def compile_update_operation(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    try:
        patch = validate_operation_payload(payload, settings=settings, partial=True)
    except OperationValidationError as exc:
        raise _operation_error(exc) from exc
    operation_id = patch.get("operation_id")
    operation_iri = patch.get("operation_iri")
    if operation_iri is None and operation_id:
        operation_iri = canonical_operation_iri(settings, operation_id)
    if operation_iri is None:
        raise InvalidCommandPayload("invalid_operation_payload: update_operation requires an ID")
    graph_iri = operation_graph_iri(settings, ontology_id)
    subject = f"<{operation_iri}>"
    vocab = operation_vocabulary(settings)
    scalar_predicates = {
        "name": str(RDFS.label),
        "description": str(RDFS.comment),
        "target_resource_type_iri": vocab["target_resource_type_iri"],
        "risk_level": vocab["risk_level"],
        "status": vocab["status"],
        "schema_version": vocab["schema_version"],
    }
    json_fields = {
        "parameters",
        "preconditions",
        "effects",
        "possible_failures",
        "idempotency",
        "tool_bindings",
        "credential_requirements",
    }
    aliases_predicate = str(SKOS.altLabel)
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []
    for field, predicate in scalar_predicates.items():
        if field not in patch:
            continue
        deletes.append((subject, f"<{predicate}>", "?o", graph_iri))
        value = patch[field]
        if value is None or value == "":
            continue
        obj = URIRef(value).n3() if field == "target_resource_type_iri" else Literal(value).n3()
        inserts.append((subject, f"<{predicate}>", obj, graph_iri))
    if "aliases" in patch:
        deletes.append((subject, f"<{aliases_predicate}>", "?o", graph_iri))
        inserts.extend(
            (subject, f"<{aliases_predicate}>", Literal(alias).n3(), graph_iri)
            for alias in patch["aliases"]
        )
    for field in json_fields:
        if field not in patch:
            continue
        deletes.append((subject, f"<{vocab[field]}>", "?o", graph_iri))
        encoded = json.dumps(
            patch[field], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        inserts.append(
            (
                subject,
                f"<{vocab[field]}>",
                Literal(
                    encoded, datatype=URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON")
                ).n3(),
                graph_iri,
            )
        )
    return CompiledCommand(
        command_kind="update_operation",
        delta=RdfGraphDelta(inserts=sorted(inserts), deletes=sorted(deletes)),
        object_kind="operation",
        source_ids=[operation_id or operation_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "operation_id": operation_id,
            "operation_iri": operation_iri,
        },
    )


def compile_delete_operation(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    try:
        identity = validate_operation_payload(payload, settings=settings, partial=True)
    except OperationValidationError as exc:
        raise _operation_error(exc) from exc
    operation_id = identity.get("operation_id")
    operation_iri = identity.get("operation_iri")
    if operation_iri is None and operation_id:
        operation_iri = canonical_operation_iri(settings, operation_id)
    if operation_iri is None:
        raise InvalidCommandPayload("invalid_operation_payload: delete_operation requires an ID")
    graph_iri = operation_graph_iri(settings, ontology_id)
    return CompiledCommand(
        command_kind="delete_operation",
        delta=RdfGraphDelta(deletes=[(f"<{operation_iri}>", "?p", "?o", graph_iri)]),
        object_kind="operation",
        source_ids=[operation_id or operation_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "operation_id": operation_id,
            "operation_iri": operation_iri,
        },
    )


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
        (
            f"<{class_iri}>",
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
            "<http://www.w3.org/2002/07/owl#Class>",
            graph_iri,
        ),
        (f"<{class_iri}>", f"<{op}id>", _literal_term(class_id), graph_iri),
        (f"<{class_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (
            f"<{class_iri}>",
            "<http://www.w3.org/2000/01/rdf-schema#label>",
            _literal_term(name),
            graph_iri,
        ),
    ]
    if description:
        insert_quads.append(
            (
                f"<{class_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#comment>",
                _literal_term(description),
                graph_iri,
            )
        )
    for alias in aliases:
        insert_quads.append(
            (
                f"<{class_iri}>",
                "<http://www.w3.org/2004/02/skos/core#altLabel>",
                _literal_term(alias),
                graph_iri,
            )
        )
    for parent_id in parent_class_ids:
        insert_quads.append(
            (
                f"<{class_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#subClassOf>",
                f"<{ns.resource('class', parent_id)}>",
                graph_iri,
            )
        )
    for external_id, mapping in external_mappings.items():
        if not mapping:
            continue
        insert_quads.append(
            (
                f"<{class_iri}>",
                f"<{op}externalMapping>",
                _literal_term({"system": external_id, "mapping": mapping}),
                graph_iri,
            )
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
    # R3.0-009 §4.3: source/target Class are optional. Absent constraints are
    # simply not written; supplied ones are still validated and projected.
    source_class_id = payload.get("source_class_id")
    target_class_id = payload.get("target_class_id")
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
        (
            f"<{relation_iri}>",
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
            "<http://www.w3.org/2002/07/owl#ObjectProperty>",
            graph_iri,
        ),
        (f"<{relation_iri}>", f"<{op}id>", _literal_term(relation_type_id), graph_iri),
        (f"<{relation_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (
            f"<{relation_iri}>",
            "<http://www.w3.org/2000/01/rdf-schema#label>",
            _literal_term(name),
            graph_iri,
        ),
    ]
    if source_class_id is not None:
        insert_quads.extend(
            [
                (
                    f"<{relation_iri}>",
                    "<http://www.w3.org/2000/01/rdf-schema#domain>",
                    f"<{ns.resource('class', source_class_id)}>",
                    graph_iri,
                ),
                (
                    f"<{relation_iri}>",
                    f"<{op}sourceClassId>",
                    _literal_term(source_class_id),
                    graph_iri,
                ),
            ]
        )
    if target_class_id is not None:
        insert_quads.extend(
            [
                (
                    f"<{relation_iri}>",
                    "<http://www.w3.org/2000/01/rdf-schema#range>",
                    f"<{ns.resource('class', target_class_id)}>",
                    graph_iri,
                ),
                (
                    f"<{relation_iri}>",
                    f"<{op}targetClassId>",
                    _literal_term(target_class_id),
                    graph_iri,
                ),
            ]
        )
    insert_quads.extend(
        [
            (f"<{relation_iri}>", f"<{op}scopePolicy>", _literal_term(scope_policy), graph_iri),
            (f"<{relation_iri}>", f"<{op}status>", _literal_term(status), graph_iri),
        ]
    )
    if description:
        insert_quads.append(
            (
                f"<{relation_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#comment>",
                _literal_term(description),
                graph_iri,
            )
        )
    if symmetric:
        insert_quads.append(
            (
                f"<{relation_iri}>",
                "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                "<http://www.w3.org/2002/07/owl#SymmetricProperty>",
                graph_iri,
            )
        )
    if transitive:
        insert_quads.append(
            (
                f"<{relation_iri}>",
                "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                "<http://www.w3.org/2002/07/owl#TransitiveProperty>",
                graph_iri,
            )
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
    # R3.0-009 §4.3: the domain Class is optional. A property created without
    # an approved domain stays discoverable and usable; when a domain is
    # supplied it is still validated and written verbatim.
    class_id = payload.get("class_id")
    property_id = payload.get("property_id") or str(uuid.uuid4())
    name = _required(payload, "name")
    description = payload.get("description")
    datatype = payload.get("datatype")
    object_class_id = payload.get("object_class_id")
    if datatype is not None and object_class_id is not None:
        raise InvalidCommandPayload(
            "create_property accepts either datatype (DatatypeProperty) or "
            "object_class_id (ObjectProperty), not both"
        )

    property_iri = str(ns.resource("property", property_id))
    ontology_iri = str(ns.resource("ontology", ontology_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    # A datatype value selects DatatypeProperty. Everything else — including
    # the constraint-free property — is an ObjectProperty whose Class range is
    # simply omitted (R3.0-009 §4.3).
    is_object_property = datatype is None

    insert_quads: list[tuple[str, str, str, str]] = [
        (
            f"<{property_iri}>",
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
            "<http://www.w3.org/2002/07/owl#ObjectProperty>"
            if is_object_property
            else "<http://www.w3.org/2002/07/owl#DatatypeProperty>",
            graph_iri,
        ),
        (f"<{property_iri}>", f"<{op}id>", _literal_term(property_id), graph_iri),
        (f"<{property_iri}>", f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (
            f"<{property_iri}>",
            "<http://www.w3.org/2000/01/rdf-schema#label>",
            _literal_term(name),
            graph_iri,
        ),
    ]
    if class_id is not None:
        insert_quads.append(
            (
                f"<{property_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#domain>",
                f"<{ns.resource('class', class_id)}>",
                graph_iri,
            )
        )
    if description:
        insert_quads.append(
            (
                f"<{property_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#comment>",
                _literal_term(description),
                graph_iri,
            )
        )
    if object_class_id is not None:
        target_iri = str(ns.resource("class", object_class_id))
        insert_quads.append(
            (
                f"<{property_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#range>",
                f"<{target_iri}>",
                graph_iri,
            )
        )
    elif datatype is not None:
        insert_quads.append(
            (
                f"<{property_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#range>",
                f"<{_datatype_iri(datatype)}>",
                graph_iri,
            )
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
        inserts.append(
            (
                prop_term,
                "<http://www.w3.org/2000/01/rdf-schema#label>",
                _literal_term(name),
                graph_iri,
            )
        )
    if description is not None:
        deletes.append(
            (prop_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri)
        )
        if description:
            inserts.append(
                (
                    prop_term,
                    "<http://www.w3.org/2000/01/rdf-schema#comment>",
                    _literal_term(description),
                    graph_iri,
                )
            )
    if datatype is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append(
            (
                prop_term,
                "<http://www.w3.org/2000/01/rdf-schema#range>",
                f"<{_datatype_iri(datatype)}>",
                graph_iri,
            )
        )
    if object_class_id is not None:
        deletes.append((prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append(
            (
                prop_term,
                "<http://www.w3.org/2000/01/rdf-schema#range>",
                f"<{ns.resource('class', object_class_id)}>",
                graph_iri,
            )
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
                k
                for k in ("name", "description", "datatype", "object_class_id")
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
        inserts.append(
            (
                rel_term,
                "<http://www.w3.org/2000/01/rdf-schema#label>",
                _literal_term(name),
                graph_iri,
            )
        )
    if description is not None:
        deletes.append(
            (rel_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri)
        )
        if description:
            inserts.append(
                (
                    rel_term,
                    "<http://www.w3.org/2000/01/rdf-schema#comment>",
                    _literal_term(description),
                    graph_iri,
                )
            )
    if source_class_id is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#domain>", "?o", graph_iri))
        inserts.append(
            (
                rel_term,
                "<http://www.w3.org/2000/01/rdf-schema#domain>",
                f"<{ns.resource('class', source_class_id)}>",
                graph_iri,
            )
        )
    if target_class_id is not None:
        deletes.append((rel_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "?o", graph_iri))
        inserts.append(
            (
                rel_term,
                "<http://www.w3.org/2000/01/rdf-schema#range>",
                f"<{ns.resource('class', target_class_id)}>",
                graph_iri,
            )
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
                k
                for k in (
                    "name",
                    "description",
                    "source_class_id",
                    "target_class_id",
                    "inverse_name",
                )
                if payload.get(k) is not None
            ],
        },
    )


_SHAPE_TARGET_FIELDS = (
    "target_class_id",
    "target_node_iri",
    "target_subjects_of_iri",
)


def _shape_target_quads(
    payload: dict[str, Any], ns: SemanticNamespace
) -> list[tuple[str, str, str]]:
    """Resolve the single R3.0-009 §6.1 Shape target selector.

    ``target_class_id`` (legacy), ``target_node_iri`` and
    ``target_subjects_of_iri`` are mutually exclusive and exactly one must be
    non-empty.  Returns ``(predicate, object)`` pairs to attach to the
    ``sh:NodeShape``.
    """
    target_class_id = payload.get("target_class_id")
    target_node_iri = payload.get("target_node_iri")
    target_subjects_of_iri = payload.get("target_subjects_of_iri")
    supplied = [
        (field, value)
        for field, value in (
            ("target_class_id", target_class_id),
            ("target_node_iri", target_node_iri),
            ("target_subjects_of_iri", target_subjects_of_iri),
        )
        if value is not None and value != ""
    ]
    if not supplied:
        raise ShapeTargetConflict(
            "shape_target_conflict: exactly one of target_class_id, "
            "target_node_iri or target_subjects_of_iri is required",
            fields=_SHAPE_TARGET_FIELDS,
        )
    if len(supplied) > 1:
        raise ShapeTargetConflict(
            "shape_target_conflict: combine "
            + ", ".join(field for field, _value in supplied)
            + " into separate shapes; one target per shape",
            fields=tuple(field for field, _value in supplied),
        )
    field, value = supplied[0]
    if field == "target_class_id":
        if not isinstance(value, str) or not value.strip():
            raise InvalidCommandPayload("target_class_id must be a non-empty class id")
        return [
            (
                "<http://www.w3.org/ns/shacl#targetClass>",
                f"<{ns.resource('class', value)}>",
            )
        ]
    # Node and subjects-of targets must be caller-supplied absolute IRIs; the
    # platform never guesses an IRI from a name (R3.0-009 §6.1).
    if not isinstance(value, str):
        raise InvalidCommandPayload(f"{field} must be an absolute RDF IRI")
    try:
        resolved = canonical_iri(value)
    except InvalidLineageStatement as exc:
        raise InvalidCommandPayload(f"{field} must be an absolute RDF IRI") from exc
    predicate = (
        "<http://www.w3.org/ns/shacl#targetNode>"
        if field == "target_node_iri"
        else "<http://www.w3.org/ns/shacl#targetSubjectsOf>"
    )
    return [(predicate, f"<{resolved}>")]


def _shape_path_iri(path_id: str, ns: SemanticNamespace) -> str:
    """Resolve a ``sh:path`` reference to the predicate it constrains.

    An absolute IRI is used verbatim — it must never be re-prefixed or
    percent-encoded (R3.0-009 §6.1); a bare local id resolves to the
    platform property resource, matching ``_property_iri``.
    """
    if not isinstance(path_id, str) or not path_id.strip():
        raise InvalidCommandPayload("constraints[].path_id must be a non-empty predicate id")
    candidate = path_id.strip()
    if ":" in candidate:
        try:
            return canonical_iri(candidate)
        except InvalidLineageStatement as exc:
            raise InvalidCommandPayload(
                "constraints[].path_id must be an absolute RDF IRI or a property id"
            ) from exc
    return str(ns.resource("property", candidate))


def _compile_shape_node(
    payload: dict[str, Any], ns: SemanticNamespace, ontology_id: str, shape_iri: str
) -> list[tuple[str, str, str, str]]:
    """Build insert quads for a sh:NodeShape with constraints. Target graph
    is the custom shapes sub-graph; caller is responsible for any deletes."""
    constraints = payload.get("constraints") or []
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    shape_term = f"<{shape_iri}>"
    quads: list[tuple[str, str, str, str]] = [
        (
            shape_term,
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
            "<http://www.w3.org/ns/shacl#NodeShape>",
            graph_iri,
        ),
    ]
    for target_predicate, target_object in _shape_target_quads(payload, ns):
        quads.append((shape_term, target_predicate, target_object, graph_iri))
    for index, constraint in enumerate(constraints):
        path_id = _required(constraint, "path_id")
        identity = json.dumps(
            {"constraint_index": index, "path_id": path_id, "shape_iri": shape_iri},
            sort_keys=True,
            separators=(",", ":"),
        )
        property_term = f"<{shape_iri}#property-{_shape_node_digest(identity)}>"
        quads.append(
            (shape_term, "<http://www.w3.org/ns/shacl#property>", property_term, graph_iri)
        )
        quads.append(
            (
                property_term,
                "<http://www.w3.org/ns/shacl#path>",
                _iri_term(_shape_path_iri(path_id, ns)),
                graph_iri,
            )
        )
        if "min_count" in constraint:
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/ns/shacl#minCount>",
                    _literal_term(int(constraint["min_count"])),
                    graph_iri,
                )
            )
        if "max_count" in constraint:
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/ns/shacl#maxCount>",
                    _literal_term(int(constraint["max_count"])),
                    graph_iri,
                )
            )
        if "datatype" in constraint:
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/ns/shacl#datatype>",
                    f"<{_datatype_iri(constraint['datatype'])}>",
                    graph_iri,
                )
            )
        if "pattern" in constraint:
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/ns/shacl#pattern>",
                    _literal_term(constraint["pattern"]),
                    graph_iri,
                )
            )
        if "description" in constraint:
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/2000/01/rdf-schema#comment>",
                    _literal_term(constraint["description"]),
                    graph_iri,
                )
            )
        if "enum_values" in constraint:
            enum_values = constraint["enum_values"]
            list_nodes = [
                f"<{shape_iri}#property-{_shape_node_digest(identity)}/list-{position}>"
                for position in range(len(enum_values))
            ]
            quads.append(
                (
                    property_term,
                    "<http://www.w3.org/ns/shacl#in>",
                    list_nodes[0] if list_nodes else "<http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>",
                    graph_iri,
                )
            )
            for position, value in enumerate(enum_values):
                next_node = (
                    list_nodes[position + 1]
                    if position + 1 < len(list_nodes)
                    else "<http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>"
                )
                quads.extend(
                    [
                        (
                            list_nodes[position],
                            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#first>",
                            _literal_term(value),
                            graph_iri,
                        ),
                        (
                            list_nodes[position],
                            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#rest>",
                            next_node,
                            graph_iri,
                        ),
                    ]
                )
    return quads


def _shape_node_digest(identity: str) -> str:
    """Stable digest naming one shape-owned constraint node (R3.0-009 §9.1).

    Constraint nodes are IRIs under the shape IRI rather than blank nodes so
    ``update_shape``/``delete_shape`` can address them in the store's wildcard
    deletes (D9) and guidance can reference the source shape.
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _shape_target_metadata(payload: dict[str, Any], ns: SemanticNamespace) -> dict[str, Any]:
    """Project the resolved shape target into command metadata for audit."""
    for field, predicate in (
        ("target_class_id", "targetClass"),
        ("target_node_iri", "targetNode"),
        ("target_subjects_of_iri", "targetSubjectsOf"),
    ):
        value = payload.get(field)
        if value in (None, ""):
            continue
        if field == "target_class_id":
            return {"target_kind": "class", "target_value": str(ns.resource("class", value))}
        return {"target_kind": field[len("target_"):-4], "target_value": str(value)}
    return {}


def compile_create_shape(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    shape_id = payload.get("shape_id") or str(uuid.uuid4())
    shape_iri = str(ns.resource("shape", shape_id))
    insert_quads = _compile_shape_node(payload, ns, ontology_id, shape_iri)
    graph_iri = _shapes_custom_graph_iri(ns, ontology_id)
    delta = RdfGraphDelta(inserts=insert_quads)
    metadata = {
        "ontology_id": ontology_id,
        "shape_id": shape_id,
        "shape_iri": shape_iri,
        **_shape_target_metadata(payload, ns),
    }
    return CompiledCommand(
        command_kind="create_shape",
        delta=delta,
        object_kind="shape",
        source_ids=[shape_id],
        target_graph_iris=[graph_iri],
        metadata=metadata,
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
        metadata={
            "ontology_id": ontology_id,
            "shape_id": shape_id,
            "shape_iri": shape_iri,
            # Full-definition replacement: the previous target selector is
            # deleted with the rest of the shape and never unioned (§6.1).
            **_shape_target_metadata(payload, ns),
        },
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
        metadata={
            "ontology_id": ontology_id,
            "property_id": property_id,
            "property_iri": property_iri,
        },
    )


def compile_delete_class(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    if "class_id" not in payload and "class_iri" not in payload:
        raise InvalidCommandPayload("delete_class requires class_id or class_iri")
    class_id = payload.get("class_id")
    class_iri = payload.get("class_iri") or (
        str(ns.resource("class", class_id)) if class_id else None
    )
    if class_iri is None:
        raise InvalidCommandPayload("delete_class requires class_id or class_iri")

    graph_iri = _ontology_graph_iri(ns, ontology_id)
    class_term = f"<{class_iri}>"
    op = str(ns.vocab)
    deletes = [(class_term, "?p", "?o", graph_iri)]
    inserts = [
        (
            class_term,
            f"<{op}deprecated>",
            '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>',
            graph_iri,
        )
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
    class_iri = payload.get("class_iri") or (
        str(ns.resource("class", class_id)) if class_id else None
    )
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
        deletes.append(
            (class_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri)
        )
        inserts.append(
            (
                class_term,
                "<http://www.w3.org/2000/01/rdf-schema#label>",
                _literal_term(name),
                graph_iri,
            )
        )
    if description is not None:
        deletes.append(
            (class_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", "?o", graph_iri)
        )
        if description:
            inserts.append(
                (
                    class_term,
                    "<http://www.w3.org/2000/01/rdf-schema#comment>",
                    _literal_term(description),
                    graph_iri,
                )
            )
    if aliases is not None:
        deletes.append(
            (class_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", "?o", graph_iri)
        )
        for alias in aliases:
            inserts.append(
                (
                    class_term,
                    "<http://www.w3.org/2004/02/skos/core#altLabel>",
                    _literal_term(alias),
                    graph_iri,
                )
            )
    if parent_class_ids is not None:
        deletes.append(
            (class_term, "<http://www.w3.org/2000/01/rdf-schema#subClassOf>", "?o", graph_iri)
        )
        for parent_id in parent_class_ids:
            inserts.append(
                (
                    class_term,
                    "<http://www.w3.org/2000/01/rdf-schema#subClassOf>",
                    f"<{ns.resource('class', parent_id)}>",
                    graph_iri,
                )
            )

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
            "fields_updated": [
                k
                for k in ("name", "description", "aliases", "parent_class_ids")
                if payload.get(k) is not None
            ],
        },
    )


def compile_create_entity(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Stage 2 §5.4 / R3.0-009 §4.1 — write a NamedIndividual into the data graph.

    Writes ``a owl:NamedIndividual``, one ``a <class>`` triple per explicit
    formal Class (zero members is legal), ``rdfs:label``, ``skos:altLabel``
    per alias, one triple per property.  No placeholder Class is invented
    when the caller omits the class entirely.
    """
    ontology_id = _required(payload, "ontology_id")
    entity_id = payload.get("entity_id") or str(uuid.uuid4())
    label = _required(payload, "label")
    aliases: list[str] = payload.get("aliases", []) or []
    properties: dict[str, Any] = payload.get("properties", {}) or {}

    class_iris, legacy_class_iri = _normalized_class_iris(payload, ns)

    entity_iri = str(ns.resource("entity", entity_id))
    graph_iri = _data_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    rdf_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"

    insert_quads: list[tuple[str, str, str, str]] = [
        (
            f"<{entity_iri}>",
            rdf_type,
            f"<{_NAMED_INDIVIDUAL_IRI}>",
            graph_iri,
        ),
    ]
    for class_iri in class_iris:
        insert_quads.append(
            (f"<{entity_iri}>", rdf_type, f"<{class_iri}>", graph_iri)
        )
    insert_quads.extend(
        [
            (f"<{entity_iri}>", f"<{op}id>", _literal_term(entity_id), graph_iri),
            (
                f"<{entity_iri}>",
                "<http://www.w3.org/2000/01/rdf-schema#label>",
                _literal_term(label),
                graph_iri,
            ),
        ]
    )
    for alias in aliases:
        insert_quads.append(
            (
                f"<{entity_iri}>",
                "<http://www.w3.org/2004/02/skos/core#altLabel>",
                _literal_term(alias),
                graph_iri,
            )
        )
    for property_key, value in properties.items():
        prop_iri = _property_iri(property_key, ns)
        if value is None:
            continue
        insert_quads.append((f"<{entity_iri}>", f"<{prop_iri}>", _literal_term(value), graph_iri))

    delta = RdfGraphDelta(inserts=insert_quads)
    metadata: dict[str, Any] = {
        "ontology_id": ontology_id,
        "entity_id": entity_id,
        "entity_iri": entity_iri,
        "class_iris": class_iris,
        "label": label,
    }
    # Legacy single-value projection: the first visible formal Class, or None
    # when the entity has zero members (R3.0-009 §6.2).
    metadata["class_iri"] = class_iris[0] if class_iris else None
    if legacy_class_iri is not None:
        metadata["class_iri_or_legacy_id"] = legacy_class_iri
    return CompiledCommand(
        command_kind="create_entity",
        delta=delta,
        object_kind="entity",
        source_ids=[entity_id],
        target_graph_iris=[graph_iri],
        metadata=metadata,
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
        deletes.append(
            (entity_term, "<http://www.w3.org/2000/01/rdf-schema#label>", "?o", graph_iri)
        )
        inserts.append(
            (
                entity_term,
                "<http://www.w3.org/2000/01/rdf-schema#label>",
                _literal_term(label),
                graph_iri,
            )
        )
    if aliases is not None:
        deletes.append(
            (entity_term, "<http://www.w3.org/2004/02/skos/core#altLabel>", "?o", graph_iri)
        )
        for alias in aliases:
            inserts.append(
                (
                    entity_term,
                    "<http://www.w3.org/2004/02/skos/core#altLabel>",
                    _literal_term(alias),
                    graph_iri,
                )
            )
    if properties is not None:
        for property_key, value in properties.items():
            prop_iri = _property_iri(property_key, ns)
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
                k for k in ("label", "aliases", "properties") if payload.get(k) is not None
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
    ObjectProperties (defined on the ontology graph).  R3.0-009 §4.3 keeps
    this as the formal membership path (``rdf:type``) but forbids the
    relation command from forging the internal ``owl:NamedIndividual`` marker.
    """
    ontology_id = _required(payload, "ontology_id")
    source_iri = _required_absolute_iri(payload, "source_entity_iri")
    relation_type_iri = _required_absolute_iri(payload, "relation_type_iri")
    target_iri = _required_absolute_iri(payload, "target_entity_iri")
    _reject_named_individual_marker(relation_type_iri, target_iri, "create_relation")

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
    source_iri = _required_absolute_iri(payload, "source_entity_iri")
    relation_type_iri = _required_absolute_iri(payload, "relation_type_iri")
    target_iri = _required_absolute_iri(payload, "target_entity_iri")
    _reject_named_individual_marker(relation_type_iri, target_iri, "delete_relation")

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
        raise InvalidCommandPayload("create_mapping requires both source_id and run_id, or neither")

    mapping_iri = str(ns.resource("mapping", mapping_id))
    op = str(ns.vocab)
    if source_id and run_id:
        graph_iri = _import_graph_for(ns, source_id, run_id)
    else:
        graph_iri = _ontology_graph_iri(ns, ontology_id)

    target_predicate = _TARGET_PREDICATES[target_type]
    insert_quads: list[tuple[str, str, str, str]] = [
        (
            f"<{mapping_iri}>",
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
            f"<{op}SemanticMapping>",
            graph_iri,
        ),
        (f"<{mapping_iri}>", f"<{op}id>", _literal_term(mapping_id), graph_iri),
        (
            f"<{mapping_iri}>",
            f"<{op}ontology>",
            f"<{ns.resource('ontology', ontology_id)}>",
            graph_iri,
        ),
        (f"<{mapping_iri}>", f"<{op}externalField>", f"<{external_field_iri}>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}{target_predicate}>", f"<{target_iri}>", graph_iri),
        (f"<{mapping_iri}>", f"<{op}targetType>", _literal_term(target_type), graph_iri),
        (f"<{mapping_iri}>", f"<{op}joinKey>", _literal_term(join_key), graph_iri),
        (f"<{mapping_iri}>", f"<{op}confidence>", _literal_term(confidence), graph_iri),
    ]
    if owner:
        insert_quads.append((f"<{mapping_iri}>", f"<{op}owner>", _literal_term(owner), graph_iri))
    if source_id and run_id:
        if import_run_iri:
            insert_quads.append(
                (
                    f"<{mapping_iri}>",
                    "<http://www.w3.org/ns/prov#wasDerivedBy>",
                    f"<{import_run_iri}>",
                    graph_iri,
                )
            )
        insert_quads.append(
            (f"<{mapping_iri}>", f"<{op}sourceId>", _literal_term(source_id), graph_iri)
        )
        insert_quads.append((f"<{mapping_iri}>", f"<{op}runId>", _literal_term(run_id), graph_iri))

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
        inserts.append(
            (mapping_term, f"<{op}confidence>", _literal_term(float(confidence)), graph_iri)
        )
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
                k
                for k in ("join_key", "confidence", "owner", "target_type", "target_iri")
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
            "assertion_kind must be one of: asserted, inferred, rule_derived, missing_evidence"
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
        raise InvalidCommandPayload("rejected review requires a linked_fix_proposal_id")
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


# ======================================================================
# R3.0-003 relational schema mapping commands (table / join / enum /
# metric). Pure-payload shape validation (G1/G4/G7) lives here; scope
# existence and cross-resource gates (G2/G3/G5/G6) run in the Modeling
# Batch validation on a merged view (see modeling_batches.py).
# ======================================================================

_RELATIONAL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)?$")
_DSN_SCHEME_PREFIX_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:")
_DSN_USERINFO_RE = re.compile(r"[A-Za-z0-9._%+-]+:[^@\s]+@[A-Za-z0-9.\-]+")
# Fields whose values are structural IRI references or update/delete
# locators. They are constrained by IRI shape validation (G1) plus scope
# existence validation (G2 create-side / G6 update-side), which already
# rejects DSN-shaped strings, so the DSN/URL rejection gate exempts them
# instead of re-scanning their content (design §3.3, review H-A).
_RELATIONAL_DSN_EXEMPT_FIELDS = frozenset(
    {
        "mapped_class_iri",
        "relation_type_iri",
        "property_iri",
        "time_field",
        "measure_property_iri",
        "field",
        "grain",
        "table_mapping_iri",
        "join_mapping_iri",
        "enum_meaning_iri",
        "metric_iri",
        # R3.0-008A: intra-ontology IRI reference constrained by G7-a/b, and
        # an absolute IRI always contains "://", which the DSN gate would
        # otherwise misread as an embedded URL.
        "semantic_value",
    }
)

_METRIC_AGGREGATIONS = frozenset({"sum", "avg", "count", "count_distinct", "min", "max"})
_METRIC_MEASURE_REQUIRED_AGGREGATIONS = frozenset({"sum", "avg", "min", "max", "count_distinct"})

_RDF_TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
_RDFS_LABEL = "<http://www.w3.org/2000/01/rdf-schema#label>"
_RDFS_COMMENT = "<http://www.w3.org/2000/01/rdf-schema#comment>"
_RDF_JSON_DATATYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON"


def _relational_string(
    payload: dict[str, Any], key: str, *, required: bool, allow_empty: bool = False
) -> str | None:
    if key not in payload or payload[key] is None:
        if required:
            raise InvalidCommandPayload(f"Missing required field: {key}")
        return None
    value = payload[key]
    if not isinstance(value, str):
        raise InvalidCommandPayload(f"{key} must be a string")
    if not value and not allow_empty:
        raise InvalidCommandPayload(f"{key} must not be empty")
    return value


def _relational_iri_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidCommandPayload(f"{label} must be an absolute RDF IRI")
    try:
        return canonical_iri(value)
    except InvalidLineageStatement as exc:
        raise InvalidCommandPayload(f"{label} must be an absolute RDF IRI") from exc


def _relational_iri_ref(payload: dict[str, Any], key: str) -> str:
    if key not in payload or payload[key] is None:
        raise InvalidCommandPayload(f"Missing required field: {key}")
    return _relational_iri_value(payload[key], key)


def _relational_identifier_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _RELATIONAL_IDENTIFIER_RE.fullmatch(value):
        raise InvalidCommandPayload(
            f"{label} must match {_RELATIONAL_IDENTIFIER_RE.pattern}"
        )
    return value


def _scan_relational_dsn_strings(
    node: Any, *, exempt: bool = False, label: str = "payload"
) -> None:
    """Field-scoped DSN/URL rejection gate (design §3.3, review H-2/H-A).

    Three deterministic rules on every non-exempt string value, including
    strings embedded in JSON payloads; fail-closed by design.
    """
    if isinstance(node, str):
        if exempt:
            return
        if "://" in node:
            raise InvalidCommandPayload(f"{label} must not contain a URL/DSN value")
        if _DSN_SCHEME_PREFIX_RE.match(node):
            raise InvalidCommandPayload(
                f"{label} must not contain a scheme-prefixed connection string"
            )
        if _DSN_USERINFO_RE.search(node):
            raise InvalidCommandPayload(
                f"{label} must not contain embedded credentials (user:pass@host)"
            )
        return
    if isinstance(node, dict):
        for key, child in node.items():
            _scan_relational_dsn_strings(
                child,
                exempt=exempt or key in _RELATIONAL_DSN_EXEMPT_FIELDS,
                label=f"{label}.{key}",
            )
        return
    if isinstance(node, (list, tuple)):
        for index, child in enumerate(node):
            _scan_relational_dsn_strings(child, exempt=exempt, label=f"{label}[{index}]")


def _validate_relational_payload(payload: dict[str, Any]) -> None:
    try:
        scan_domain_payload(payload)
    except SecretDetected as exc:
        raise InvalidCommandPayload(
            f"invalid_command_payload: payload rejected by secret scanning ({exc})"
        ) from exc
    _scan_relational_dsn_strings(payload)


def _relational_json_literal(value: Any) -> str:
    """Canonical JSON literal: ``json.dumps(payload, ensure_ascii=False)``.

    The repr path of ``_literal_term(dict)`` is forbidden here — it stores a
    Python repr that is not valid JSON and would silently defeat the
    authorization layer's JSON reference extraction helper.
    """
    encoded = json.dumps(value, ensure_ascii=False)
    return Literal(encoded, datatype=URIRef(_RDF_JSON_DATATYPE)).n3()


def _normalize_column_mappings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise InvalidCommandPayload("column_mappings must be a non-empty JSON array")
    normalized: list[dict[str, str]] = []
    for index, entry in enumerate(value):
        label = f"column_mappings[{index}]"
        if not isinstance(entry, dict):
            raise InvalidCommandPayload(f"{label} must be a JSON object")
        unknown = sorted(set(entry) - {"property_iri", "column", "role"})
        if unknown:
            raise InvalidCommandPayload(f"{label} has unknown field(s): {', '.join(unknown)}")
        missing = sorted({"property_iri", "column"} - set(entry))
        if missing:
            raise InvalidCommandPayload(f"{label} is missing field(s): {', '.join(missing)}")
        role = entry.get("role", "value")
        if role not in {"value", "business_key"}:
            raise InvalidCommandPayload(f"{label}.role must be 'value' or 'business_key'")
        normalized.append(
            {
                "property_iri": _relational_iri_value(entry["property_iri"], f"{label}.property_iri"),
                "column": _relational_identifier_value(entry["column"], f"{label}.column"),
                "role": role,
            }
        )
    if not any(item["role"] == "business_key" for item in normalized):
        raise InvalidCommandPayload(
            "column_mappings must declare at least one business_key column"
        )
    return normalized


def _normalize_join_path(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise InvalidCommandPayload(
            "join_path must be a non-empty JSON array of ordered steps"
        )
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(value):
        label = f"join_path[{index}]"
        if not isinstance(step, dict):
            raise InvalidCommandPayload(f"{label} must be a JSON object")
        if set(step) != {"from_table", "to_table", "from_columns", "to_columns"}:
            raise InvalidCommandPayload(
                f"{label} must have exactly from_table, to_table, from_columns, to_columns"
            )
        from_columns = step["from_columns"]
        to_columns = step["to_columns"]
        if not isinstance(from_columns, list) or not from_columns:
            raise InvalidCommandPayload(f"{label}.from_columns must be a non-empty array")
        if not isinstance(to_columns, list) or not to_columns:
            raise InvalidCommandPayload(f"{label}.to_columns must be a non-empty array")
        if len(from_columns) != len(to_columns):
            raise InvalidCommandPayload(
                f"{label}.from_columns and to_columns must have equal length"
            )
        steps.append(
            {
                "from_table": _relational_identifier_value(step["from_table"], f"{label}.from_table"),
                "to_table": _relational_identifier_value(step["to_table"], f"{label}.to_table"),
                "from_columns": [
                    _relational_identifier_value(column, f"{label}.from_columns[{position}]")
                    for position, column in enumerate(from_columns)
                ],
                "to_columns": [
                    _relational_identifier_value(column, f"{label}.to_columns[{position}]")
                    for position, column in enumerate(to_columns)
                ],
            }
        )
    for index in range(len(steps) - 1):
        if steps[index]["to_table"] != steps[index + 1]["from_table"]:
            raise InvalidCommandPayload(
                f"join_path steps {index} and {index + 1} are not adjacent: "
                f"{steps[index]['to_table']} != {steps[index + 1]['from_table']}"
            )
    return steps


def _normalize_metric_filters(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise InvalidCommandPayload("filters must be a JSON array")
    normalized: list[dict[str, str]] = []
    for index, entry in enumerate(value):
        label = f"filters[{index}]"
        if not isinstance(entry, dict):
            raise InvalidCommandPayload(f"{label} must be a JSON object")
        if set(entry) != {"field", "operator", "value"}:
            raise InvalidCommandPayload(f"{label} must have exactly field, operator, value")
        for field in ("operator", "value"):
            if not isinstance(entry[field], str) or not entry[field]:
                raise InvalidCommandPayload(f"{label}.{field} must be a non-empty string")
        normalized.append(
            {
                "field": _relational_iri_value(entry["field"], f"{label}.field"),
                "operator": entry["operator"],
                "value": entry["value"],
            }
        )
    return normalized


def _normalize_metric_grain(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise InvalidCommandPayload("grain must be a JSON array of property IRIs")
    return [
        _relational_iri_value(item, f"grain[{index}]") for index, item in enumerate(value)
    ]


def _relational_subject(
    payload: dict[str, Any], ns: SemanticNamespace, *, id_key: str, iri_key: str, kind: str
) -> tuple[str, str | None]:
    """Resolve an update/delete target: explicit ``*_iri`` or ``*_id`` derived."""
    iri = payload.get(iri_key)
    resource_id = payload.get(id_key)
    if iri is not None:
        return _relational_iri_value(iri, iri_key), None
    if resource_id is not None:
        if not isinstance(resource_id, str) or not resource_id:
            raise InvalidCommandPayload(f"{id_key} must be a non-empty string")
        return str(ns.resource(kind, resource_id)), resource_id
    raise InvalidCommandPayload(f"{id_key} or {iri_key} is required")


def _relational_common_quads(
    *,
    subject_iri: str,
    resource_id: str,
    ontology_id: str,
    payload: dict[str, Any],
    ns: SemanticNamespace,
    type_name: str,
    name: str,
    schema_source_required: bool,
) -> list[tuple[str, str, str, str]]:
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    ontology_iri = str(ns.resource("ontology", ontology_id))
    subject = f"<{subject_iri}>"
    quads: list[tuple[str, str, str, str]] = [
        (subject, _RDF_TYPE, f"<{op}{type_name}>", graph_iri),
        (subject, f"<{op}id>", _literal_term(resource_id), graph_iri),
        (subject, f"<{op}ontology>", f"<{ontology_iri}>", graph_iri),
        (subject, _RDFS_LABEL, _literal_term(name), graph_iri),
    ]
    description = payload.get("description")
    if description is not None:
        quads.append((subject, _RDFS_COMMENT, _literal_term(description), graph_iri))
    if "schema_source" in payload:
        schema_source = _relational_string(payload, "schema_source", required=False)
        if schema_source is not None:
            quads.append(
                (subject, f"<{op}schemaSource>", _literal_term(schema_source), graph_iri)
            )
    elif schema_source_required:
        raise InvalidCommandPayload("Missing required field: schema_source")
    if "semantic_version" in payload:
        semantic_version = _relational_string(payload, "semantic_version", required=False)
        if semantic_version is not None:
            quads.append(
                (subject, f"<{op}semanticVersion>", _literal_term(semantic_version), graph_iri)
            )
    return quads


def _relational_update_delta(
    payload: dict[str, Any],
    *,
    subject_iri: str,
    graph_iri: str,
    literal_fields: dict[str, str],
    iri_fields: dict[str, str],
    json_fields: dict[str, str],
) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str, str]]]:
    """Per-predicate delete+insert for update_* relational commands."""
    subject = f"<{subject_iri}>"
    deletes: list[tuple[str, str, str, str]] = []
    inserts: list[tuple[str, str, str, str]] = []
    for field, predicate in literal_fields.items():
        if field not in payload:
            continue
        deletes.append((subject, f"<{predicate}>", "?o", graph_iri))
        value = payload[field]
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise InvalidCommandPayload(f"{field} must be a string")
        inserts.append((subject, f"<{predicate}>", _literal_term(value), graph_iri))
    for field, predicate in iri_fields.items():
        if field not in payload:
            continue
        deletes.append((subject, f"<{predicate}>", "?o", graph_iri))
        if payload[field] is None or payload[field] == "":
            continue
        value = _relational_iri_value(payload[field], field)
        inserts.append((subject, f"<{predicate}>", f"<{value}>", graph_iri))
    for field, predicate in json_fields.items():
        if field not in payload:
            continue
        deletes.append((subject, f"<{predicate}>", "?o", graph_iri))
        value = payload[field]
        if value is None:
            continue
        inserts.append(
            (subject, f"<{predicate}>", _relational_json_literal(value), graph_iri)
        )
    return inserts, deletes


def compile_create_table_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    resource_id = payload.get("table_mapping_id") or str(uuid.uuid4())
    if not isinstance(resource_id, str) or not resource_id:
        raise InvalidCommandPayload("table_mapping_id must be a non-empty string")
    name = _relational_string(payload, "name", required=True) or ""
    mapped_class_iri = _relational_iri_ref(payload, "mapped_class_iri")
    table_name = _relational_identifier_value(payload.get("table_name"), "table_name")
    column_mappings = _normalize_column_mappings(payload.get("column_mappings"))
    subject_iri = str(ns.resource("table-mapping", resource_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    quads = _relational_common_quads(
        subject_iri=subject_iri,
        resource_id=resource_id,
        ontology_id=ontology_id,
        payload=payload,
        ns=ns,
        type_name="TableMapping",
        name=name,
        schema_source_required=True,
    )
    subject = f"<{subject_iri}>"
    quads.extend(
        [
            (subject, f"<{op}mappedClass>", f"<{mapped_class_iri}>", graph_iri),
            (subject, f"<{op}tableName>", _literal_term(table_name), graph_iri),
            (subject, f"<{op}columnMappings>", _relational_json_literal(column_mappings), graph_iri),
        ]
    )
    return CompiledCommand(
        command_kind="create_table_mapping",
        delta=RdfGraphDelta(inserts=sorted(quads)),
        object_kind="table_mapping",
        source_ids=[resource_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "table_mapping_id": resource_id,
            "table_mapping_iri": subject_iri,
            "table_name": table_name,
        },
    )


def compile_update_table_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    if "column_mappings" in payload:
        _normalize_column_mappings(payload["column_mappings"])
    if "table_name" in payload and payload["table_name"]:
        _relational_identifier_value(payload["table_name"], "table_name")
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="table_mapping_id", iri_key="table_mapping_iri", kind="table-mapping"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    inserts, deletes = _relational_update_delta(
        payload,
        subject_iri=subject_iri,
        graph_iri=graph_iri,
        literal_fields={
            "name": "http://www.w3.org/2000/01/rdf-schema#label",
            "description": "http://www.w3.org/2000/01/rdf-schema#comment",
            "table_name": f"{op}tableName",
            "schema_source": f"{op}schemaSource",
            "semantic_version": f"{op}semanticVersion",
        },
        iri_fields={},
        json_fields={"column_mappings": f"{op}columnMappings"},
    )
    return CompiledCommand(
        command_kind="update_table_mapping",
        delta=RdfGraphDelta(inserts=sorted(inserts), deletes=sorted(deletes)),
        object_kind="table_mapping",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "table_mapping_id": payload.get("table_mapping_id"),
            "table_mapping_iri": subject_iri,
        },
    )


def compile_delete_table_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="table_mapping_id", iri_key="table_mapping_iri", kind="table-mapping"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    return CompiledCommand(
        command_kind="delete_table_mapping",
        delta=RdfGraphDelta(deletes=[(f"<{subject_iri}>", "?p", "?o", graph_iri)]),
        object_kind="table_mapping",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "table_mapping_id": payload.get("table_mapping_id"),
            "table_mapping_iri": subject_iri,
        },
    )


def compile_create_join_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    resource_id = payload.get("join_mapping_id") or str(uuid.uuid4())
    if not isinstance(resource_id, str) or not resource_id:
        raise InvalidCommandPayload("join_mapping_id must be a non-empty string")
    name = _relational_string(payload, "name", required=True) or ""
    relation_type_iri = _relational_iri_ref(payload, "relation_type_iri")
    join_direction = _relational_string(payload, "join_direction", required=True) or ""
    if join_direction not in {"forward", "reverse"}:
        raise InvalidCommandPayload("join_direction must be 'forward' or 'reverse'")
    join_path = _normalize_join_path(payload.get("join_path"))
    subject_iri = str(ns.resource("join-mapping", resource_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    quads = _relational_common_quads(
        subject_iri=subject_iri,
        resource_id=resource_id,
        ontology_id=ontology_id,
        payload=payload,
        ns=ns,
        type_name="JoinMapping",
        name=name,
        schema_source_required=True,
    )
    subject = f"<{subject_iri}>"
    quads.extend(
        [
            (subject, f"<{op}mappedRelationType>", f"<{relation_type_iri}>", graph_iri),
            (subject, f"<{op}joinDirection>", _literal_term(join_direction), graph_iri),
            (subject, f"<{op}joinPath>", _relational_json_literal(join_path), graph_iri),
        ]
    )
    return CompiledCommand(
        command_kind="create_join_mapping",
        delta=RdfGraphDelta(inserts=sorted(quads)),
        object_kind="join_mapping",
        source_ids=[resource_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "join_mapping_id": resource_id,
            "join_mapping_iri": subject_iri,
            "join_path": join_path,
        },
    )


def compile_update_join_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    if "join_path" in payload and payload["join_path"] is not None:
        _normalize_join_path(payload["join_path"])
    if "join_direction" in payload and payload["join_direction"]:
        if payload["join_direction"] not in {"forward", "reverse"}:
            raise InvalidCommandPayload("join_direction must be 'forward' or 'reverse'")
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="join_mapping_id", iri_key="join_mapping_iri", kind="join-mapping"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    inserts, deletes = _relational_update_delta(
        payload,
        subject_iri=subject_iri,
        graph_iri=graph_iri,
        literal_fields={
            "name": "http://www.w3.org/2000/01/rdf-schema#label",
            "description": "http://www.w3.org/2000/01/rdf-schema#comment",
            "join_direction": f"{op}joinDirection",
            "schema_source": f"{op}schemaSource",
            "semantic_version": f"{op}semanticVersion",
        },
        iri_fields={},
        json_fields={"join_path": f"{op}joinPath"},
    )
    return CompiledCommand(
        command_kind="update_join_mapping",
        delta=RdfGraphDelta(inserts=sorted(inserts), deletes=sorted(deletes)),
        object_kind="join_mapping",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "join_mapping_id": payload.get("join_mapping_id"),
            "join_mapping_iri": subject_iri,
        },
    )


def compile_delete_join_mapping(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="join_mapping_id", iri_key="join_mapping_iri", kind="join-mapping"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    return CompiledCommand(
        command_kind="delete_join_mapping",
        delta=RdfGraphDelta(deletes=[(f"<{subject_iri}>", "?p", "?o", graph_iri)]),
        object_kind="join_mapping",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "join_mapping_id": payload.get("join_mapping_id"),
            "join_mapping_iri": subject_iri,
        },
    )


def compile_create_enum_meaning(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    resource_id = payload.get("enum_meaning_id") or str(uuid.uuid4())
    if not isinstance(resource_id, str) or not resource_id:
        raise InvalidCommandPayload("enum_meaning_id must be a non-empty string")
    name = _relational_string(payload, "name", required=True) or ""
    property_iri = _relational_iri_ref(payload, "property_iri")
    enum_value = _relational_string(payload, "enum_value", required=True)
    business_meaning = _relational_string(payload, "business_meaning", required=True)
    subject_iri = str(ns.resource("enum-meaning", resource_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    quads = _relational_common_quads(
        subject_iri=subject_iri,
        resource_id=resource_id,
        ontology_id=ontology_id,
        payload=payload,
        ns=ns,
        type_name="EnumValueMeaning",
        name=name,
        schema_source_required=True,
    )
    subject = f"<{subject_iri}>"
    quads.extend(
        [
            (subject, f"<{op}mappedProperty>", f"<{property_iri}>", graph_iri),
            (subject, f"<{op}enumValue>", _literal_term(enum_value), graph_iri),
            (subject, f"<{op}businessMeaning>", _literal_term(business_meaning), graph_iri),
        ]
    )
    # R3.0-008A L3 form: optional single op:semanticValue IRI reference to a
    # first-class business semantic node. Absent/empty stays L2; a non-string
    # or non-IRI shape is rejected here (G7-c single-value enforcement at the
    # command surface — multi-value lists never compile).
    semantic_value = payload.get("semantic_value")
    semantic_value_iri: str | None = None
    if semantic_value is not None and semantic_value != "":
        semantic_value_iri = _relational_iri_value(semantic_value, "semantic_value")
        quads.append((subject, f"<{op}semanticValue>", f"<{semantic_value_iri}>", graph_iri))
    return CompiledCommand(
        command_kind="create_enum_meaning",
        delta=RdfGraphDelta(inserts=sorted(quads)),
        object_kind="enum_meaning",
        source_ids=[resource_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "enum_meaning_id": resource_id,
            "enum_meaning_iri": subject_iri,
            "mapped_property_iri": property_iri,
            "enum_value": enum_value,
            "semantic_value_iri": semantic_value_iri,
        },
    )


def compile_update_enum_meaning(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="enum_meaning_id", iri_key="enum_meaning_iri", kind="enum-meaning"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    inserts, deletes = _relational_update_delta(
        payload,
        subject_iri=subject_iri,
        graph_iri=graph_iri,
        literal_fields={
            "name": "http://www.w3.org/2000/01/rdf-schema#label",
            "description": "http://www.w3.org/2000/01/rdf-schema#comment",
            "enum_value": f"{op}enumValue",
            "business_meaning": f"{op}businessMeaning",
            "schema_source": f"{op}schemaSource",
            "semantic_version": f"{op}semanticVersion",
        },
        iri_fields={"semantic_value": f"{op}semanticValue"},
        json_fields={},
    )
    # R3.0-008A: null/"" clears op:semanticValue (L3 -> L2 downgrade); a new
    # IRI replaces/adds it (L2 -> L3 upgrade), per-predicate delete-then-insert.
    update_semantic_value = payload.get("semantic_value")
    update_semantic_value_iri = (
        _relational_iri_value(update_semantic_value, "semantic_value")
        if update_semantic_value is not None and update_semantic_value != ""
        else None
    )
    return CompiledCommand(
        command_kind="update_enum_meaning",
        delta=RdfGraphDelta(inserts=sorted(inserts), deletes=sorted(deletes)),
        object_kind="enum_meaning",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "enum_meaning_id": payload.get("enum_meaning_id"),
            "enum_meaning_iri": subject_iri,
            "semantic_value_iri": update_semantic_value_iri,
        },
    )


def compile_delete_enum_meaning(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="enum_meaning_id", iri_key="enum_meaning_iri", kind="enum-meaning"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    return CompiledCommand(
        command_kind="delete_enum_meaning",
        delta=RdfGraphDelta(deletes=[(f"<{subject_iri}>", "?p", "?o", graph_iri)]),
        object_kind="enum_meaning",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "enum_meaning_id": payload.get("enum_meaning_id"),
            "enum_meaning_iri": subject_iri,
        },
    )


def _validate_metric_aggregation(payload: dict[str, Any]) -> None:
    aggregation = payload.get("aggregation")
    if aggregation is not None and aggregation not in _METRIC_AGGREGATIONS:
        raise InvalidCommandPayload(
            "aggregation must be one of: " + ", ".join(sorted(_METRIC_AGGREGATIONS))
        )
    if (
        aggregation in _METRIC_MEASURE_REQUIRED_AGGREGATIONS
        and not payload.get("measure_property_iri")
    ):
        raise InvalidCommandPayload(
            "measure_property_iri is required when aggregation is "
            f"{aggregation} (row-count 'count' is the only aggregation without one)"
        )


def compile_create_metric_definition(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    _validate_metric_aggregation(payload)
    if not payload.get("aggregation"):
        raise InvalidCommandPayload("Missing required field: aggregation")
    resource_id = payload.get("metric_id") or str(uuid.uuid4())
    if not isinstance(resource_id, str) or not resource_id:
        raise InvalidCommandPayload("metric_id must be a non-empty string")
    name = _relational_string(payload, "name", required=True) or ""
    grain = _normalize_metric_grain(payload.get("grain"))
    time_field = _relational_iri_ref(payload, "time_field")
    measure_property_iri = (
        _relational_iri_ref(payload, "measure_property_iri")
        if payload.get("measure_property_iri")
        else None
    )
    value_expression = _relational_string(payload, "value_expression", required=False)
    filters = _normalize_metric_filters(payload.get("filters"))
    null_value_rule = _relational_string(payload, "null_value_rule", required=True)
    denominator_rule = _relational_string(payload, "denominator_rule", required=True)
    aggregation = payload["aggregation"]
    subject_iri = str(ns.resource("metric", resource_id))
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    quads = _relational_common_quads(
        subject_iri=subject_iri,
        resource_id=resource_id,
        ontology_id=ontology_id,
        payload=payload,
        ns=ns,
        type_name="MetricDefinition",
        name=name,
        schema_source_required=True,
    )
    subject = f"<{subject_iri}>"
    quads.append((subject, f"<{op}metricGrain>", _relational_json_literal(grain), graph_iri))
    quads.append((subject, f"<{op}metricTimeField>", f"<{time_field}>", graph_iri))
    if measure_property_iri is not None:
        quads.append((subject, f"<{op}metricMeasure>", f"<{measure_property_iri}>", graph_iri))
    if value_expression is not None:
        quads.append((subject, f"<{op}valueExpression>", _literal_term(value_expression), graph_iri))
    quads.append((subject, f"<{op}metricFilters>", _relational_json_literal(filters), graph_iri))
    quads.append((subject, f"<{op}metricAggregation>", _literal_term(aggregation), graph_iri))
    quads.append((subject, f"<{op}nullValueRule>", _literal_term(null_value_rule), graph_iri))
    quads.append(
        (subject, f"<{op}denominatorRule>", _literal_term(denominator_rule), graph_iri)
    )
    return CompiledCommand(
        command_kind="create_metric_definition",
        delta=RdfGraphDelta(inserts=sorted(quads)),
        object_kind="metric",
        source_ids=[resource_id],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "metric_id": resource_id,
            "metric_iri": subject_iri,
        },
    )


def compile_update_metric_definition(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    _validate_metric_aggregation(payload)
    if "grain" in payload and payload["grain"] is not None:
        _normalize_metric_grain(payload["grain"])
    if "filters" in payload and payload["filters"] is not None:
        _normalize_metric_filters(payload["filters"])
    for field in ("null_value_rule", "denominator_rule"):
        if field in payload and (payload[field] is None or payload[field] == ""):
            raise InvalidCommandPayload(
                f"{field} must be explicit non-empty text (empty metric rules are not allowed)"
            )
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="metric_id", iri_key="metric_iri", kind="metric"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    op = str(ns.vocab)
    inserts, deletes = _relational_update_delta(
        payload,
        subject_iri=subject_iri,
        graph_iri=graph_iri,
        literal_fields={
            "name": "http://www.w3.org/2000/01/rdf-schema#label",
            "description": "http://www.w3.org/2000/01/rdf-schema#comment",
            "value_expression": f"{op}valueExpression",
            "aggregation": f"{op}metricAggregation",
            "null_value_rule": f"{op}nullValueRule",
            "denominator_rule": f"{op}denominatorRule",
            "schema_source": f"{op}schemaSource",
            "semantic_version": f"{op}semanticVersion",
        },
        iri_fields={
            "time_field": f"{op}metricTimeField",
            "measure_property_iri": f"{op}metricMeasure",
        },
        json_fields={
            "grain": f"{op}metricGrain",
            "filters": f"{op}metricFilters",
        },
    )
    return CompiledCommand(
        command_kind="update_metric_definition",
        delta=RdfGraphDelta(inserts=sorted(inserts), deletes=sorted(deletes)),
        object_kind="metric",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "metric_id": payload.get("metric_id"),
            "metric_iri": subject_iri,
        },
    )


def compile_delete_metric_definition(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    ontology_id = _required(payload, "ontology_id")
    _validate_relational_payload(payload)
    subject_iri, resource_id = _relational_subject(
        payload, ns, id_key="metric_id", iri_key="metric_iri", kind="metric"
    )
    graph_iri = _ontology_graph_iri(ns, ontology_id)
    return CompiledCommand(
        command_kind="delete_metric_definition",
        delta=RdfGraphDelta(deletes=[(f"<{subject_iri}>", "?p", "?o", graph_iri)]),
        object_kind="metric",
        source_ids=[resource_id or subject_iri],
        target_graph_iris=[graph_iri],
        metadata={
            "ontology_id": ontology_id,
            "metric_id": payload.get("metric_id"),
            "metric_iri": subject_iri,
        },
    )


_COMPILERS: dict[str, Compiler] = {
    "create_operation": compile_create_operation,
    "update_operation": compile_update_operation,
    "delete_operation": compile_delete_operation,
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
    "create_table_mapping": compile_create_table_mapping,
    "update_table_mapping": compile_update_table_mapping,
    "delete_table_mapping": compile_delete_table_mapping,
    "create_join_mapping": compile_create_join_mapping,
    "update_join_mapping": compile_update_join_mapping,
    "delete_join_mapping": compile_delete_join_mapping,
    "create_enum_meaning": compile_create_enum_meaning,
    "update_enum_meaning": compile_update_enum_meaning,
    "delete_enum_meaning": compile_delete_enum_meaning,
    "create_metric_definition": compile_create_metric_definition,
    "update_metric_definition": compile_update_metric_definition,
    "delete_metric_definition": compile_delete_metric_definition,
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
