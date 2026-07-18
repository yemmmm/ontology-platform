"""R-007 Operation vocabulary, codec, and non-bypassable platform invariants."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote, urlparse

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.util import from_n3

from app.core.config import Settings
from app.repositories.rdf_store import RdfFormat, RdfGraphDelta, RdfStoreRepository
from app.services.semantic_export import namespace_from_settings


OPERATION_SCHEMA_VERSION = "operation-v1"
JSON_DATATYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON")
MAX_COLLECTION_ITEMS = 100
MAX_STRING_LENGTH = 4000
MAX_OPERATION_BYTES = 128_000
MAX_JSON_DEPTH = 12

_SECRET_KEYS = {
    "apikey",
    "authorization",
    "credentialid",
    "credentialref",
    "credentialreferenceid",
    "headervalue",
    "password",
    "secret",
    "token",
    "accesstoken",
    "refreshtoken",
}
_VALUE_TYPES = {"string", "integer", "number", "boolean", "object", "array", "iri"}
_RISK_LEVELS = {"low", "medium", "high", "critical"}
_IDEMPOTENCY_KINDS = {"idempotent", "conditional", "non_idempotent", "unknown"}
_BINDING_KINDS = {"http_api", "mcp_tool"}
_STATUSES = {"active", "inactive"}
_CONSTRAINT_FIELDS = {
    "min_value",
    "max_value",
    "min_length",
    "max_length",
    "pattern",
    "format",
}


class OperationValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def operation_vocabulary(settings: Settings) -> dict[str, str]:
    vocab = str(namespace_from_settings(settings).vocab)
    return {
        "type": f"{vocab}Operation",
        "id": f"{vocab}id",
        "ontology": f"{vocab}ontology",
        "target_resource_type_iri": f"{vocab}targetResourceType",
        "parameters": f"{vocab}parameters",
        "preconditions": f"{vocab}preconditions",
        "effects": f"{vocab}effects",
        "possible_failures": f"{vocab}possibleFailures",
        "idempotency": f"{vocab}idempotency",
        "risk_level": f"{vocab}riskLevel",
        "tool_bindings": f"{vocab}toolBindings",
        "credential_requirements": f"{vocab}credentialRequirements",
        "status": f"{vocab}status",
        "schema_version": f"{vocab}schemaVersion",
    }


def operation_predicates(settings: Settings) -> set[str]:
    values = operation_vocabulary(settings)
    return {value for key, value in values.items() if key != "type"}


def operation_json_predicates(settings: Settings) -> set[str]:
    values = operation_vocabulary(settings)
    return {
        values[key]
        for key in (
            "parameters",
            "preconditions",
            "effects",
            "possible_failures",
            "idempotency",
            "tool_bindings",
            "credential_requirements",
        )
    }


def canonical_operation_iri(settings: Settings, operation_id: str) -> str:
    return str(namespace_from_settings(settings).resource("operation", operation_id))


def operation_graph_iri(settings: Settings, ontology_id: str) -> str:
    return str(namespace_from_settings(settings).graph("ontology", ontology_id))


def scan_operation_secret_keys(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
            if normalized in _SECRET_KEYS or scan_operation_secret_keys(nested):
                return True
    elif isinstance(value, list):
        return any(scan_operation_secret_keys(item) for item in value)
    return False


def reject_operation_secrets(value: Any) -> None:
    if scan_operation_secret_keys(value):
        raise OperationValidationError(
            "operation_secret_forbidden",
            "Operation payload contains a forbidden credential instance or secret-bearing field",
        )


def validate_operation_payload(
    payload: dict[str, Any],
    *,
    settings: Settings,
    create: bool = False,
    partial: bool = False,
) -> dict[str, Any]:
    reject_operation_secrets(payload)
    _check_capacity(payload)
    result = dict(payload)
    if create and "operation_iri" in result:
        raise OperationValidationError(
            "invalid_operation_payload", "create_operation does not accept operation_iri"
        )
    operation_id = result.get("operation_id")
    operation_iri = result.get("operation_iri")
    if not partial or operation_id is not None or operation_iri is not None:
        if not operation_id and not operation_iri:
            raise OperationValidationError(
                "invalid_operation_payload", "Operation requires operation_id"
            )
        if operation_id is not None:
            _string(operation_id, "operation_id", required=True, maximum=255)
            canonical = canonical_operation_iri(settings, operation_id)
            if operation_iri is not None and operation_iri != canonical:
                raise OperationValidationError(
                    "invalid_operation_payload",
                    "operation_id and operation_iri do not identify the same canonical Operation",
                )
            result["operation_iri"] = canonical

    status = result.get("status", "active" if not partial else None)
    if status is not None and status not in _STATUSES:
        raise OperationValidationError("invalid_operation_payload", "Unsupported Operation status")
    if not partial:
        result.setdefault("aliases", [])
        result.setdefault("description", None)
        result.setdefault("parameters", [])
        result.setdefault("preconditions", [])
        result.setdefault("effects", [])
        result.setdefault("possible_failures", [])
        result.setdefault("credential_requirements", [])
        result.setdefault("status", "active")
        result.setdefault("schema_version", OPERATION_SCHEMA_VERSION)

    if "schema_version" in result and result["schema_version"] != OPERATION_SCHEMA_VERSION:
        raise OperationValidationError(
            "unsupported_operation_schema_version", "Unsupported Operation schema_version"
        )
    if not partial and result["status"] == "active":
        required = {
            "name",
            "target_resource_type_iri",
            "idempotency",
            "risk_level",
            "tool_bindings",
        }
        missing = sorted(field for field in required if field not in result)
        if missing:
            raise OperationValidationError(
                "invalid_operation_payload",
                f"Operation is missing required field(s): {', '.join(missing)}",
            )

    if "name" in result:
        _string(result["name"], "name", required=True)
    if "description" in result and result["description"] is not None:
        _string(result["description"], "description")
    if "aliases" in result:
        result["aliases"] = _string_list(result["aliases"], "aliases")
    if "target_resource_type_iri" in result:
        _iri(result["target_resource_type_iri"], "target_resource_type_iri")
    if "risk_level" in result and result["risk_level"] not in _RISK_LEVELS:
        raise OperationValidationError("invalid_operation_payload", "Unsupported risk_level")
    if "idempotency" in result:
        result["idempotency"] = _validate_idempotency(result["idempotency"])
    if "parameters" in result:
        result["parameters"] = _validate_parameters(result["parameters"])
    for field in ("preconditions", "effects"):
        if field in result:
            result[field] = _validate_named_declarations(result[field], field)
    if "possible_failures" in result:
        result["possible_failures"] = _validate_failures(result["possible_failures"])
    if "tool_bindings" in result:
        result["tool_bindings"] = _validate_bindings(result["tool_bindings"])
        if status == "active" and not result["tool_bindings"]:
            raise OperationValidationError(
                "invalid_operation_payload", "Active Operation requires at least one tool binding"
            )
    if "credential_requirements" in result:
        result["credential_requirements"] = _validate_credentials(result["credential_requirements"])
    return result


def operation_quads(
    operation: dict[str, Any], settings: Settings, ontology_id: str
) -> list[tuple[str, str, str, str]]:
    operation = validate_operation_payload(operation, settings=settings)
    vocab = operation_vocabulary(settings)
    graph_iri = operation_graph_iri(settings, ontology_id)
    subject = URIRef(operation["operation_iri"]).n3()
    ontology_iri = namespace_from_settings(settings).resource("ontology", ontology_id).n3()
    quads = [
        (subject, RDF.type.n3(), URIRef(vocab["type"]).n3(), graph_iri),
        (subject, URIRef(vocab["id"]).n3(), Literal(operation["operation_id"]).n3(), graph_iri),
        (subject, URIRef(vocab["ontology"]).n3(), ontology_iri, graph_iri),
    ]
    scalar_terms = {
        "name": RDFS.label,
        "description": RDFS.comment,
        "target_resource_type_iri": URIRef(vocab["target_resource_type_iri"]),
        "risk_level": URIRef(vocab["risk_level"]),
        "status": URIRef(vocab["status"]),
        "schema_version": URIRef(vocab["schema_version"]),
    }
    for field, predicate in scalar_terms.items():
        value = operation.get(field)
        if value is None or value == "":
            continue
        obj = URIRef(value) if field == "target_resource_type_iri" else Literal(value)
        quads.append((subject, predicate.n3(), obj.n3(), graph_iri))
    for alias in operation.get("aliases", []):
        quads.append((subject, SKOS.altLabel.n3(), Literal(alias).n3(), graph_iri))
    for field in (
        "parameters",
        "preconditions",
        "effects",
        "possible_failures",
        "idempotency",
        "tool_bindings",
        "credential_requirements",
    ):
        value = operation[field]
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        quads.append(
            (
                subject,
                URIRef(vocab[field]).n3(),
                Literal(encoded, datatype=JSON_DATATYPE).n3(),
                graph_iri,
            )
        )
    return sorted(quads)


def decode_operations(graph: Graph, settings: Settings) -> list[dict[str, Any]]:
    vocab = operation_vocabulary(settings)
    operation_type = URIRef(vocab["type"])
    subjects = set(graph.subjects(RDF.type, operation_type))
    operation_iri_prefix = f"{namespace_from_settings(settings).base_iri.rstrip('/')}/operation/"
    predicates = {
        URIRef(value)
        for key, value in vocab.items()
        if key not in {"type", "id", "ontology", "status"}
    }
    subjects.update(
        subject
        for subject, predicate, _obj in graph
        if predicate in predicates or str(subject).startswith(operation_iri_prefix)
    )
    result = []
    for subject in sorted(subjects, key=str):
        if (subject, RDF.type, operation_type) not in graph:
            raise OperationValidationError(
                "invalid_operation_payload",
                "Operation vocabulary subject is missing rdf:type Operation",
            )
        allowed_predicates = {RDF.type, RDFS.label, RDFS.comment, SKOS.altLabel}
        allowed_predicates.update(URIRef(value) for key, value in vocab.items() if key != "type")
        for predicate in graph.predicates(subject):
            if predicate in allowed_predicates:
                continue
            key = re.split(r"[/#:]", str(predicate).rstrip("/#:"))[-1]
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            if normalized in _SECRET_KEYS:
                raise OperationValidationError(
                    "operation_secret_forbidden",
                    "Operation RDF contains a forbidden secret-bearing predicate",
                )
            raise OperationValidationError(
                "invalid_operation_payload", "Operation RDF contains an unsupported predicate"
            )
        data: dict[str, Any] = {
            "operation_iri": str(subject),
            "aliases": sorted(str(value) for value in graph.objects(subject, SKOS.altLabel)),
        }
        singleton = {
            "operation_id": URIRef(vocab["id"]),
            "ontology_iri": URIRef(vocab["ontology"]),
            "name": RDFS.label,
            "description": RDFS.comment,
            "target_resource_type_iri": URIRef(vocab["target_resource_type_iri"]),
            "risk_level": URIRef(vocab["risk_level"]),
            "status": URIRef(vocab["status"]),
            "schema_version": URIRef(vocab["schema_version"]),
        }
        for field, predicate in singleton.items():
            values = list(graph.objects(subject, predicate))
            if len(values) > 1:
                raise OperationValidationError(
                    "invalid_operation_payload", f"Operation field {field} must be single-valued"
                )
            if values:
                data[field] = str(values[0])
        for field in (
            "parameters",
            "preconditions",
            "effects",
            "possible_failures",
            "idempotency",
            "tool_bindings",
            "credential_requirements",
        ):
            values = list(graph.objects(subject, URIRef(vocab[field])))
            if len(values) != 1:
                raise OperationValidationError(
                    "invalid_operation_payload", f"Operation field {field} must occur exactly once"
                )
            try:
                data[field] = json.loads(str(values[0]))
            except (TypeError, json.JSONDecodeError) as exc:
                raise OperationValidationError(
                    "invalid_operation_payload", f"Operation field {field} is not valid JSON"
                ) from exc
        data.pop("ontology_iri", None)
        operation = validate_operation_payload(data, settings=settings)
        target = URIRef(operation["target_resource_type_iri"])
        if (target, RDF.type, OWL.Class) not in graph and (
            target,
            RDF.type,
            RDFS.Class,
        ) not in graph:
            raise OperationValidationError(
                "operation_target_not_found",
                "Operation target resource type is not a Class in the same Ontology graph",
            )
        result.append(operation)
    ids = [item["operation_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise OperationValidationError(
            "invalid_operation_payload", "Operation ID must be unique within an Ontology"
        )
    return result


def validate_operation_delta(
    rdf_store: RdfStoreRepository,
    delta: RdfGraphDelta,
    settings: Settings,
) -> None:
    relevant_graphs = set(delta.affected_graph_iris())
    if not relevant_graphs:
        return
    vocab = operation_vocabulary(settings)
    operation_terms = {
        f"<{value}>" for key, value in vocab.items() if key not in {"type", "id", "ontology"}
    }
    may_touch = any(
        predicate in operation_terms or obj == f"<{vocab['type']}>"
        for _subject, predicate, obj, _graph in (*delta.inserts, *delta.deletes)
    )
    if not may_touch:
        may_touch = any(
            subject.startswith(f"<{settings.semantic_base_iri.rstrip('/')}/operation/")
            for subject, _predicate, _obj, _graph in (*delta.inserts, *delta.deletes)
        )
    if not may_touch:
        return
    for graph_iri in sorted(relevant_graphs):
        graph = Graph()
        graph_exists = not hasattr(rdf_store, "graph_exists") or rdf_store.graph_exists(graph_iri)
        content = rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value) if graph_exists else ""
        if content and content.strip():
            graph.parse(data=content, format=RdfFormat.TURTLE.value)
        if graph_iri in delta.clear_graphs or graph_iri in delta.drop_graphs:
            graph = Graph()
        for subject, predicate, obj, quad_graph in delta.deletes:
            if quad_graph != graph_iri:
                continue
            graph.remove(tuple(_term_or_none(value) for value in (subject, predicate, obj)))
        for subject, predicate, obj, quad_graph in delta.inserts:
            if quad_graph == graph_iri:
                graph.add(tuple(_term(value) for value in (subject, predicate, obj)))
        decode_operations(graph, settings)


def ontology_id_from_graph_iri(settings: Settings, graph_iri: str) -> str | None:
    prefix = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/"
    return unquote(graph_iri[len(prefix) :]) if graph_iri.startswith(prefix) else None


def _term(value: str):
    term = from_n3(value)
    if term is None:
        raise OperationValidationError("invalid_operation_payload", "Invalid RDF term")
    return term


def _term_or_none(value: str):
    return None if value.startswith("?") else _term(value)


def _check_capacity(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise OperationValidationError("invalid_operation_payload", "Operation JSON is too deep")
    if depth == 0:
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if size > MAX_OPERATION_BYTES:
            raise OperationValidationError(
                "invalid_operation_payload", "Operation payload is too large"
            )
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        raise OperationValidationError("invalid_operation_payload", "Operation string is too long")
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise OperationValidationError(
                "invalid_operation_payload", "Operation collection is too large"
            )
        for item in value:
            _check_capacity(item, depth + 1)
    elif isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise OperationValidationError(
                "invalid_operation_payload", "Operation object is too large"
            )
        for key, item in value.items():
            _check_capacity(str(key), depth + 1)
            _check_capacity(item, depth + 1)


def _string(
    value: Any, field: str, *, required: bool = False, maximum: int = MAX_STRING_LENGTH
) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        raise OperationValidationError("invalid_operation_payload", f"Invalid Operation {field}")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_COLLECTION_ITEMS:
        raise OperationValidationError("invalid_operation_payload", f"Invalid Operation {field}")
    result = [_string(item, field, required=True) for item in value]
    if len(result) != len(set(result)):
        raise OperationValidationError("invalid_operation_payload", f"Duplicate value in {field}")
    return result


def _iri(value: Any, field: str) -> str:
    value = _string(value, field, required=True)
    parsed = urlparse(value)
    if not parsed.scheme:
        raise OperationValidationError("invalid_operation_payload", f"Invalid IRI in {field}")
    return value


def _dict(value: Any, field: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed:
        raise OperationValidationError("invalid_operation_payload", f"Invalid fields in {field}")
    return dict(value)


def _items(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > MAX_COLLECTION_ITEMS:
        raise OperationValidationError("invalid_operation_payload", f"Invalid Operation {field}")
    return value


def _unique(values: list[dict[str, Any]], key: str, field: str) -> None:
    keys = [item[key] for item in values]
    if len(keys) != len(set(keys)):
        raise OperationValidationError("invalid_operation_payload", f"Duplicate {key} in {field}")


def _validate_idempotency(value: Any) -> dict[str, Any]:
    item = _dict(value, "idempotency", {"kind", "description"})
    if item.get("kind") not in _IDEMPOTENCY_KINDS:
        raise OperationValidationError("invalid_operation_payload", "Unsupported idempotency kind")
    if item.get("description") is not None:
        _string(item["description"], "idempotency.description")
    return item


def _validate_parameters(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _items(value, "parameters"):
        item = _dict(
            raw,
            "parameter",
            {
                "name",
                "description",
                "required",
                "value_type",
                "enum_values",
                "default_value",
                "constraints",
            },
        )
        _string(item.get("name"), "parameter.name", required=True)
        if item.get("description") is not None:
            _string(item["description"], "parameter.description")
        if (
            not isinstance(item.get("required", False), bool)
            or item.get("value_type") not in _VALUE_TYPES
        ):
            raise OperationValidationError("invalid_operation_payload", "Invalid parameter type")
        item.setdefault("required", False)
        item.setdefault("enum_values", [])
        item.setdefault("default_value", None)
        item.setdefault("constraints", {})
        if (
            not isinstance(item["enum_values"], list)
            or len(item["enum_values"]) > MAX_COLLECTION_ITEMS
        ):
            raise OperationValidationError(
                "invalid_operation_payload", "Invalid parameter enum_values"
            )
        constraints = _dict(item["constraints"], "parameter.constraints", _CONSTRAINT_FIELDS)
        _validate_parameter_values(item, constraints)
        item["constraints"] = constraints
        result.append(item)
    _unique(result, "name", "parameters")
    return result


def _validate_parameter_values(item: dict[str, Any], constraints: dict[str, Any]) -> None:
    value_type = item["value_type"]
    validator = {
        "string": lambda value: isinstance(value, str),
        "iri": lambda value: isinstance(value, str) and bool(urlparse(value).scheme),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
    }[value_type]
    values = list(item["enum_values"])
    if item["default_value"] is not None:
        values.append(item["default_value"])
    if any(not validator(value) for value in values):
        raise OperationValidationError(
            "invalid_operation_payload", "Parameter values do not match value_type"
        )
    if (
        item["enum_values"]
        and item["default_value"] is not None
        and item["default_value"] not in item["enum_values"]
    ):
        raise OperationValidationError(
            "invalid_operation_payload", "Parameter default is not in enum_values"
        )
    numeric = {"min_value", "max_value"}
    lengths = {"min_length", "max_length"}
    if set(constraints) & numeric and value_type not in {"integer", "number"}:
        raise OperationValidationError(
            "invalid_operation_payload", "Numeric constraint requires numeric value_type"
        )
    if set(constraints) & lengths and value_type not in {"string", "array"}:
        raise OperationValidationError(
            "invalid_operation_payload", "Length constraint requires string or array"
        )
    if ("pattern" in constraints or "format" in constraints) and value_type not in {
        "string",
        "iri",
    }:
        raise OperationValidationError(
            "invalid_operation_payload", "Text constraint requires string or iri"
        )
    for key in numeric:
        if key in constraints and (
            not isinstance(constraints[key], (int, float)) or isinstance(constraints[key], bool)
        ):
            raise OperationValidationError("invalid_operation_payload", f"Invalid {key}")
    for key in lengths:
        if key in constraints and (not isinstance(constraints[key], int) or constraints[key] < 0):
            raise OperationValidationError("invalid_operation_payload", f"Invalid {key}")
    if constraints.get("min_value", float("-inf")) > constraints.get("max_value", float("inf")):
        raise OperationValidationError("invalid_operation_payload", "min_value exceeds max_value")
    if constraints.get("min_length", 0) > constraints.get("max_length", MAX_STRING_LENGTH):
        raise OperationValidationError("invalid_operation_payload", "min_length exceeds max_length")
    if "pattern" in constraints:
        try:
            re.compile(_string(constraints["pattern"], "pattern"))
        except re.error as exc:
            raise OperationValidationError(
                "invalid_operation_payload", "Invalid parameter pattern"
            ) from exc


def _validate_named_declarations(value: Any, field: str) -> list[dict[str, Any]]:
    result = []
    for raw in _items(value, field):
        item = _dict(raw, field, {"name", "description"})
        _string(item.get("name"), f"{field}.name", required=True)
        _string(item.get("description"), f"{field}.description", required=True)
        result.append(item)
    _unique(result, "name", field)
    return result


def _validate_failures(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _items(value, "possible_failures"):
        item = _dict(raw, "possible_failure", {"code", "description", "retryable"})
        _string(item.get("code"), "failure.code", required=True)
        _string(item.get("description"), "failure.description", required=True)
        if not isinstance(item.get("retryable", False), bool):
            raise OperationValidationError("invalid_operation_payload", "Invalid failure.retryable")
        item.setdefault("retryable", False)
        result.append(item)
    _unique(result, "code", "possible_failures")
    return result


def _validate_bindings(value: Any) -> list[dict[str, Any]]:
    allowed = {
        "binding_id",
        "kind",
        "system",
        "operation_identifier",
        "version",
        "documentation_source",
        "documentation_version",
    }
    result = []
    for raw in _items(value, "tool_bindings"):
        item = _dict(raw, "tool_binding", allowed)
        for field in ("binding_id", "system", "operation_identifier"):
            _string(item.get(field), f"tool_binding.{field}", required=True)
        if item.get("kind") not in _BINDING_KINDS:
            raise OperationValidationError(
                "invalid_operation_payload", "Unsupported tool binding kind"
            )
        for field in ("version", "documentation_source", "documentation_version"):
            if item.get(field) is not None:
                _string(item[field], f"tool_binding.{field}")
        result.append(item)
    _unique(result, "binding_id", "tool_bindings")
    return result


def _validate_credentials(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _items(value, "credential_requirements"):
        item = _dict(
            raw, "credential_requirement", {"name", "reference_type", "description", "required"}
        )
        _string(item.get("name"), "credential_requirement.name", required=True)
        reference_type = _string(
            item.get("reference_type"), "credential_requirement.reference_type", required=True
        )
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", reference_type):
            raise OperationValidationError(
                "invalid_operation_payload", "Invalid credential reference_type"
            )
        if item.get("description") is not None:
            _string(item["description"], "credential_requirement.description")
        if not isinstance(item.get("required", False), bool):
            raise OperationValidationError(
                "invalid_operation_payload", "Invalid credential requirement"
            )
        item.setdefault("required", False)
        result.append(item)
    _unique(result, "name", "credential_requirements")
    return result
