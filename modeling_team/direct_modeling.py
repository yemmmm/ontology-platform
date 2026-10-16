"""Pure deterministic compiler for R4.3-025 direct model changes.

The compiler consumes the closed direct-change request, one immutable unified
candidate snapshot, and trusted bindings prepared by the Runner.  It does not
read a candidate path, call a platform endpoint, allocate a Session/lease, or
invent a resource identity.  Its output is a JSON-serialisable plan and a
source map for :mod:`modeling_team.direct_execution`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .staged_decisions import validate_unified_candidate


# Reuse the current command field shapes rather than maintaining another
# list of enum/type constraints beside the platform-facing reference.
_BATCH_CONTRACT = json.loads((Path(__file__).parent / "references/modeling-batch-item-contract.json").read_text())
_SEMANTIC_DEFINITION_FIELDS = tuple(json.loads(
    (Path(__file__).parent / "references/platform-neutral-candidate-authoring.json").read_text()
)["multiview_semantic_definition"]["fields"])


REQUEST_SCHEMA = "r4-3-025-model-changes/v1"
PLAN_SCHEMA = "r4-3-025-model-change-plan/v1"

_REQUEST_FIELDS = frozenset({"schema_version", "candidate_ref", "changes"})
_CHANGE_FIELDS = frozenset(
    {"change_id", "action", "resource_kind", "item_id", "target_ref", "fields"}
)
_ACTIONS = frozenset({"create", "update", "delete", "set_fact", "delete_fact"})
_RESOURCE_KINDS = frozenset(
    {
        "entity",
        "property",
        "class",
        "relation_type",
        "operation",
        "relation",
        "fact",
        "mapping",
        "table_mapping",
        "join_mapping",
        "enum_meaning",
        "metric_definition",
    }
)
_CANDIDATE_KINDS = frozenset(
    {
        "entity",
        "property",
        "relation",
        "table_mapping",
        "join_mapping",
        "enum_meaning",
        "metric_definition",
    }
)

_COMMANDS: dict[str, dict[str, str]] = {
    "entity": {
        "create": "create_entity",
        "update": "update_entity",
        "delete": "delete_entity",
    },
    "property": {
        "create": "create_property",
        "update": "update_property",
        "delete": "delete_property",
    },
    "class": {
        "create": "create_class",
        "update": "update_class",
        "delete": "delete_class",
    },
    "relation_type": {
        "create": "create_relation_type",
        "update": "update_relation_type",
        "delete": "delete_relation_type",
    },
    "operation": {
        "create": "create_operation",
        "update": "update_operation",
        "delete": "delete_operation",
    },
    "mapping": {
        "create": "create_mapping",
        "update": "update_mapping",
        "delete": "delete_mapping",
    },
    "table_mapping": {
        "create": "create_table_mapping",
        "update": "update_table_mapping",
        "delete": "delete_table_mapping",
    },
    "join_mapping": {
        "create": "create_join_mapping",
        "update": "update_join_mapping",
        "delete": "delete_join_mapping",
    },
    "enum_meaning": {
        "create": "create_enum_meaning",
        "update": "update_enum_meaning",
        "delete": "delete_enum_meaning",
    },
    "metric_definition": {
        "create": "create_metric_definition",
        "update": "update_metric_definition",
        "delete": "delete_metric_definition",
    },
}

# These are the semantic fields accepted by the existing Modeling handlers.
# Resource IDs/IRIs used only to address an existing target are deliberately
# absent from the public ``fields`` path and are inserted from a trusted
# target binding below.
_COMMAND_FIELDS: dict[str, frozenset[str]] = {
    "create_entity": frozenset(
        {
            "class_iri_or_legacy_id",
            "class_iris",
            "label",
            "aliases",
            "properties",
            "semantic_definition",
            "action_definition",
            "parameter_definition",
        }
    ),
    "update_entity": frozenset(
        {
            "label",
            "aliases",
            "properties",
            "semantic_definition",
            "action_definition",
            "parameter_definition",
            "entity_iri",
        }
    ),
    "delete_entity": frozenset({"entity_iri"}),
    "create_property": frozenset(
        {
            "name",
            "description",
            "predicate_kind",
            "class_id",
            "datatype",
            "object_class_id",
            "semantic_definition",
        }
    ),
    "update_property": frozenset(
        {"name", "description", "predicate_kind", "datatype", "object_class_id", "semantic_definition", "property_iri"}
    ),
    "delete_property": frozenset({"property_iri"}),
    "create_class": frozenset(
        {"name", "description", "aliases", "parent_class_ids", "external_mappings", "semantic_definition"}
    ),
    "update_class": frozenset(
        {"name", "description", "aliases", "parent_class_ids", "semantic_definition", "class_iri"}
    ),
    "delete_class": frozenset({"class_iri"}),
    "create_relation_type": frozenset(
        {
            "name",
            "source_class_id",
            "target_class_id",
            "description",
            "symmetric",
            "transitive",
            "scope_policy",
            "status",
            "semantic_definition",
        }
    ),
    "update_relation_type": frozenset(
        {
            "name",
            "description",
            "source_class_id",
            "target_class_id",
            "inverse_name",
            "semantic_definition",
            "relation_type_iri",
        }
    ),
    "delete_relation_type": frozenset({"relation_type_iri"}),
    "create_operation": frozenset(
        {
            "name",
            "description",
            "aliases",
            "target_resource_type_iri",
            "parameters",
            "preconditions",
            "effects",
            "possible_failures",
            "idempotency",
            "risk_level",
            "tool_bindings",
            "credential_requirements",
            "status",
            "schema_version",
        }
    ),
    "update_operation": frozenset(
        {
            "name",
            "description",
            "aliases",
            "target_resource_type_iri",
            "parameters",
            "preconditions",
            "effects",
            "possible_failures",
            "idempotency",
            "risk_level",
            "tool_bindings",
            "credential_requirements",
            "status",
            "schema_version",
            "operation_iri",
        }
    ),
    "delete_operation": frozenset({"operation_iri"}),
    "create_relation": frozenset(
        {"source_entity_iri", "relation_type_iri", "target_entity_iri"}
    ),
    "delete_relation": frozenset(
        {"source_entity_iri", "relation_type_iri", "target_entity_iri"}
    ),
    "update_fact": frozenset(
        {
            "subject_iri",
            "predicate_iri",
            "old_object_value",
            "new_object_value",
            "old_object_is_iri",
            "new_object_is_iri",
        }
    ),
    "delete_fact": frozenset(
        {"subject_iri", "predicate_iri", "object_value", "object_is_iri"}
    ),
    "create_mapping": frozenset(
        {
            "external_field_iri",
            "target_type",
            "target_iri",
            "join_key",
            "confidence",
            "owner",
            "import_run_iri",
        }
    ),
    "update_mapping": frozenset(
        {"join_key", "confidence", "owner", "target_type", "target_iri", "mapping_iri"}
    ),
    "delete_mapping": frozenset({"mapping_iri"}),
    "create_table_mapping": frozenset(
        {
            "name",
            "description",
            "mapped_class_iri",
            "mapped_definition_iri",
            "table_name",
            "column_mappings",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
        }
    ),
    "update_table_mapping": frozenset(
        {
            "name",
            "description",
            "table_name",
            "column_mappings",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
            "table_mapping_iri",
        }
    ),
    "delete_table_mapping": frozenset({"table_mapping_iri"}),
    "create_join_mapping": frozenset(
        {
            "name",
            "description",
            "relation_type_iri",
            "join_direction",
            "join_path",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
        }
    ),
    "update_join_mapping": frozenset(
        {
            "name",
            "description",
            "join_direction",
            "join_path",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
            "join_mapping_iri",
        }
    ),
    "delete_join_mapping": frozenset({"join_mapping_iri"}),
    "create_enum_meaning": frozenset(
        {
            "name",
            "description",
            "property_iri",
            "enum_value",
            "business_meaning",
            "table_mapping_iri",
            "column",
            "semantic_value",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
        }
    ),
    "update_enum_meaning": frozenset(
        {
            "name",
            "description",
            "enum_value",
            "business_meaning",
            "table_mapping_iri",
            "column",
            "semantic_value",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
            "enum_meaning_iri",
        }
    ),
    "delete_enum_meaning": frozenset({"enum_meaning_iri"}),
    "create_metric_definition": frozenset(
        {
            "name",
            "description",
            "grain",
            "time_field",
            "measure_property_iri",
            "value_expression",
            "filters",
            "aggregation",
            "null_value_rule",
            "denominator_rule",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
        }
    ),
    "update_metric_definition": frozenset(
        {
            "name",
            "description",
            "grain",
            "time_field",
            "measure_property_iri",
            "value_expression",
            "filters",
            "aggregation",
            "null_value_rule",
            "denominator_rule",
            "mapping_definition",
            "schema_source",
            "semantic_version",
            "semantic_definition",
            "metric_iri",
        }
    ),
    "delete_metric_definition": frozenset({"metric_iri"}),
}

_IDENTITY_FIELDS = {
    "entity": "entity_iri",
    "property": "property_iri",
    "class": "class_iri",
    "relation_type": "relation_type_iri",
    "operation": "operation_iri",
    "mapping": "mapping_iri",
    "table_mapping": "table_mapping_iri",
    "join_mapping": "join_mapping_iri",
    "enum_meaning": "enum_meaning_iri",
    "metric_definition": "metric_iri",
}
_TECHNICAL_FIELDS = frozenset(
    {
        "entity_id",
        "property_id",
        "relation_type_id",
        "operation_id",
        "mapping_id",
        "table_mapping_id",
        "join_mapping_id",
        "enum_meaning_id",
        "metric_id",
        "entity_iri",
        "property_iri",
        "class_iri",
        "relation_type_iri",
        "operation_iri",
        "mapping_iri",
        "table_mapping_iri",
        "join_mapping_iri",
        "enum_meaning_iri",
        "metric_iri",
        "ontology_id",
        "source_id",
        "run_id",
    }
)
_CREATE_REQUIRED = {
    "create_entity": ("label",),
    "create_property": ("name",),
    "create_class": ("name",),
    "create_relation_type": ("name", "source_class_id", "target_class_id"),
    "create_operation": ("name",),
    "create_mapping": ("external_field_iri", "target_type", "target_iri"),
    "create_table_mapping": ("name", "table_name", "column_mappings", "schema_source"),
    "create_join_mapping": (
        "name",
        "relation_type_iri",
        "join_direction",
        "join_path",
        "schema_source",
    ),
    "create_enum_meaning": (
        "name",
        "property_iri",
        "enum_value",
        "business_meaning",
        "schema_source",
    ),
    "create_metric_definition": (
        "name",
        "grain",
        "time_field",
        "filters",
        "aggregation",
        "null_value_rule",
        "denominator_rule",
        "schema_source",
    ),
}

_MAPPING_ALIASES: dict[str, dict[str, str]] = {
    "table_mapping": {
        "mapped_class": "mapped_class_iri",
        "mapped_class_ref": "mapped_class_iri",
        "mapped_definition": "mapped_definition_iri",
        "mapped_definition_ref": "mapped_definition_iri",
    },
    "join_mapping": {
        "relation_type": "relation_type_iri",
        "relation_type_ref": "relation_type_iri",
    },
    "enum_meaning": {
        "property_ref": "property_iri",
        "table_mapping_ref": "table_mapping_iri",
        "semantic_value_ref": "semantic_value",
    },
    "metric_definition": {
        "time_field_ref": "time_field",
        "measure_property_ref": "measure_property_iri",
    },
}

# Mapping references are deliberately enumerated by the current Batch
# contract.  A key named ``value`` (or an arbitrary nested business object)
# does not acquire reference semantics merely because one of its members is
# called ``definition_ref`` or contains an IRI-shaped string.
_MAPPING_REFERENCE_FIELDS = frozenset(
    {
        "external_field_iri",
        "target_iri",
        "import_run_iri",
        "mapped_class_iri",
        "mapped_definition_iri",
        "relation_type_iri",
        "property_iri",
        "table_mapping_iri",
        "semantic_value",
        "time_field",
        "measure_property_iri",
        "from_mapping_iri",
        "to_mapping_iri",
        "conversion_rule_iri",
        "condition_rule_iri",
        "base_mapping_iri",
        "join_mapping_iris",
        "conversion_rule_iris",
        "target_resource_type_iri",
    }
)

_GENERIC_REFERENCE_FIELDS: dict[str, frozenset[str]] = {
    "create_class": frozenset({"parent_class_ids"}),
    "update_class": frozenset({"parent_class_ids"}),
    "create_relation_type": frozenset({"source_class_id", "target_class_id"}),
    "update_relation_type": frozenset({"source_class_id", "target_class_id"}),
}


_MAPPING_REFERENCE_CONTAINERS = frozenset(
    {
        "column_mappings",
        "join_path",
        "filters",
        "mapping_definition",
        "identifiers",
        "field_meanings",
        "step_semantics",
        "contexts",
        "property_bindings",
        "counted_identity",
    }
)


class ModelChangeCompilationError(ValueError):
    """Static direct-modeling gaps, with locations in the original request."""

    def __init__(self, errors: Sequence[Mapping[str, Any]]) -> None:
        self.errors = [deepcopy(dict(error)) for error in errors]
        super().__init__(json.dumps(self.errors, ensure_ascii=False, sort_keys=True))


@dataclass
class _Build:
    command_kind: str
    payload: dict[str, Any]
    dependencies: set[str] = field(default_factory=set)
    field_map: dict[str, list[str]] = field(default_factory=dict)
    reference_slots: dict[str, dict[str, str]] = field(default_factory=dict)
    deferred_property_keys: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _Context:
    candidate: dict[str, Any] | None
    items: dict[str, dict[str, Any]]
    item_indices: dict[str, int]
    changes: list[dict[str, Any]]
    change_indices: dict[str, int]
    ontology_by_item: Mapping[str, str]
    resolve_binding: Callable[[Mapping[str, str]], Mapping[str, Any] | None]
    bindings: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def item_path(self, item_id: str | None, suffix: str = "") -> str | None:
        if item_id is None:
            return None
        index = self.item_indices.get(item_id)
        if index is None:
            return f"/items/?{_pointer_suffix(suffix)}"
        return f"/items/{index}{_pointer_suffix(suffix)}"

    def error(
        self,
        code: str,
        message: str,
        *,
        change: Mapping[str, Any] | None = None,
        change_index: int | None = None,
        item_id: str | None = None,
        field: str | None = None,
        candidate_path: str | None = None,
    ) -> None:
        if change_index is None and change is not None:
            change_index = self.change_indices.get(str(change.get("change_id")))
        change_id = str(change.get("change_id")) if change and change.get("change_id") else None
        resolved_item = item_id or (str(change["item_id"]) if change and change.get("item_id") else None)
        path = f"/changes/{change_index}" if change_index is not None else "/changes"
        if field:
            path += _pointer_suffix(f".{field}")
        self.errors.append(
            {
                "code": code,
                "change_id": change_id,
                "item_id": resolved_item,
                "field": field,
                "path": path,
                "candidate_path": candidate_path,
                "message": message,
                "retryable": True,
            }
        )


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _absolute_iri(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        return False
    parsed = urlparse(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _candidate_ref_valid(value: Any) -> bool:
    return _is_nonempty(value) and "://" not in value and not value.startswith("/")


def _material_ref_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"artifact_ref", "path"}:
        return False
    artifact = value.get("artifact_ref")
    path = value.get("path")
    return (
        _is_nonempty(artifact)
        and _candidate_ref_valid(artifact)
        and isinstance(path, str)
        and path.startswith("/")
        and "\x00" not in path
    )


def _pointer_suffix(suffix: str) -> str:
    text = suffix.lstrip(".")
    if not text:
        return ""
    segments: list[str] = []
    for segment in text.split("."):
        match = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", segment)
        if match is None:
            segments.append(segment)
            continue
        segments.append(match.group(1))
        if match.group(2) is not None:
            segments.append(match.group(2))
    return "".join(
        f"/{segment.replace('~', '~0').replace('/', '~1')}" for segment in segments
    )


def _canonical_ref(value: Mapping[str, str]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_pointer(ctx: _Context, item_id: str | None, suffix: str = "") -> str:
    tail = _pointer_suffix(suffix)
    if item_id is None:
        return "/changes/fields" + tail
    index = ctx.item_indices.get(item_id)
    if index is None:
        return "/items/?"
    return f"/items/{index}" + tail


def _candidate_input_path(
    ctx: _Context, change: Mapping[str, Any], path: str
) -> str | None:
    """Translate a builder input path to the selected candidate pointer."""

    item_id = change.get("item_id")
    if item_id is None or not isinstance(path, str):
        return None
    if path == "value":
        suffix = ".value"
    elif path.startswith("value."):
        suffix = f".{path}"
    else:
        return None
    return ctx.item_path(str(item_id), suffix)


def _pointer_path(path: str) -> str:
    """Turn a dotted compiler path into a JSON Pointer path."""

    segments = [segment for segment in path.split(".") if segment]
    return "".join(
        f"/{str(segment).replace('~', '~0').replace('/', '~1')}" for segment in segments
    )


def _join_pointer(base: str, segment: Any) -> str:
    """Append one JSON Pointer segment to a payload pointer."""

    return f"{base.rstrip('/')}/{str(segment).replace('~', '~0').replace('/', '~1')}"


def _source_pointer(ctx: _Context, change: Mapping[str, Any], path: str) -> str:
    """Map a builder path to the exact request/candidate JSON Pointer."""

    item_id = change.get("item_id")
    if item_id is not None and path.startswith("value"):
        return ctx.item_path(str(item_id), f".{path}") or path
    if path.startswith("fields"):
        suffix = path[len("fields") :]
        return f"/changes/fields{_pointer_suffix(suffix)}"
    return path


def _item_ref_slot(value: Any) -> dict[str, str] | None:
    if not _item_ref(value):
        return None
    reference = value["item_ref"]
    return {
        "depends_on": str(reference["client_item_id"]),
        "output": str(reference["output"]),
    }


def _field_marker(key: str) -> str:
    return f"/changes/fields{_pointer_path(key)}"


def _input_field(item: Mapping[str, Any] | None, suffix: str) -> str:
    """Return the request-side field path for candidate or fields input."""

    return f"{'value' if item is not None else 'fields'}.{suffix}"


def _field_map(ctx: _Context, item_id: str | None, suffix: str, payload_path: str) -> dict[str, list[str]]:
    return {
        f"/payload{_pointer_path(payload_path)}": [_candidate_pointer(ctx, item_id, suffix)]
    }


def _semantic_field_map(
    ctx: _Context,
    item_id: str | None,
    item: Mapping[str, Any] | None,
    raw: Any,
) -> dict[str, list[str]]:
    """Map generated semantic annotations to every selected source field."""

    pointers: list[str] = []
    if item is not None:
        if item.get("semantic_definition") is not None:
            pointers.append(_candidate_pointer(ctx, item_id, ".semantic_definition"))
        if _is_nonempty(item.get("business_meaning")):
            pointers.append(_candidate_pointer(ctx, item_id, ".business_meaning"))
        if item.get("unknowns"):
            pointers.append(_candidate_pointer(ctx, item_id, ".unknowns"))
        value = item.get("value")
        if isinstance(value, Mapping) and value.get("semantic_definition") is not None:
            pointers.append(_candidate_pointer(ctx, item_id, ".value.semantic_definition"))
    elif isinstance(raw, Mapping) and raw.get("semantic_definition") is not None:
        pointers.append(_field_marker("semantic_definition"))
    return {"/payload/semantic_definition": pointers} if pointers else {}


def _normalize_mapping_aliases(
    raw: Any,
    resource_kind: str,
    ctx: _Context,
    change: Mapping[str, Any],
) -> tuple[Any, dict[str, str]]:
    """Normalize only the explicitly documented neutral mapping aliases."""

    if not isinstance(raw, Mapping):
        return raw, {}
    value = deepcopy(dict(raw))
    source_keys: dict[str, str] = {}
    for alias, canonical in _MAPPING_ALIASES.get(resource_kind, {}).items():
        if alias not in value:
            continue
        if canonical in value and value[canonical] != value[alias]:
            ctx.error(
                "mapping_identity_conflict",
                f"mapping fields {alias} and {canonical} disagree",
                change=change,
                field=f"{('value' if change.get('item_id') is not None else 'fields')}.{alias}",
                candidate_path=(
                    ctx.item_path(str(change["item_id"]), f".value.{alias}")
                    if change.get("item_id") is not None
                    else None
                ),
            )
        elif canonical not in value:
            value[canonical] = value[alias]
            source_keys[canonical] = alias
        value.pop(alias, None)
    return value, source_keys


def _merge_field_maps(*maps: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mapping in maps:
        for key, values in mapping.items():
            target = result.setdefault(str(key), [])
            for value in values:
                if value not in target:
                    target.append(str(value))
    return result


def _normalize_field_map(
    field_map: Mapping[str, Sequence[str]], ctx: _Context, change: Mapping[str, Any]
) -> dict[str, list[str]]:
    """Resolve request-level pointers for a fields-only change.

    Builders intentionally use short ``/changes/fields`` and ``/target_ref``
    markers so their semantic rules stay independent of request ordering.  At
    the compile boundary those markers become pointers into this exact change.
    Candidate item pointers are already absolute and pass through unchanged.
    """

    change_index = ctx.change_indices.get(str(change["change_id"]))
    if change_index is None:
        return {key: list(values) for key, values in field_map.items()}
    prefix = f"/changes/{change_index}"
    result: dict[str, list[str]] = {}
    for key, values in field_map.items():
        normalized: list[str] = []
        for value in values:
            if value == "/target_ref":
                pointer = f"{prefix}/target_ref"
            elif value.startswith("/changes/"):
                pointer = f"{prefix}{value[len('/changes'):]}"
            else:
                pointer = value
            if pointer not in normalized:
                normalized.append(pointer)
        result[str(key)] = normalized
    return result


def _candidate_issue(issue: Any) -> dict[str, Any]:
    return {
        "code": getattr(issue, "reason_code", None) or "unified_schema_mismatch",
        "change_id": None,
        "item_id": None,
        "field": None,
        "path": "/candidate",
        "candidate_path": "/candidate",
        "message": getattr(issue, "message", None) or str(issue),
        "retryable": True,
    }


def _item_ref(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"item_ref"}:
        return False
    ref = value["item_ref"]
    return (
        isinstance(ref, Mapping)
        and set(ref) == {"client_item_id", "output"}
        and _is_nonempty(ref.get("client_item_id"))
        and ref.get("output") in {"resource_id", "resource_iri"}
    )


def _change_client_id(change: Mapping[str, Any]) -> str:
    return str(change.get("item_id") or change["change_id"])


def _ontology(ctx: _Context, change: Mapping[str, Any]) -> str | None:
    change_id = str(change["change_id"])
    item_id = change.get("item_id")
    value = ctx.ontology_by_item.get(change_id)
    if value is None and isinstance(item_id, str):
        value = ctx.ontology_by_item.get(item_id)
    return str(value) if _is_nonempty(value) else None


def _target_binding(
    ctx: _Context, change: Mapping[str, Any], *, required: bool = True
) -> Mapping[str, Any] | None:
    ref = change.get("target_ref")
    if ref is None:
        if required:
            ctx.error("target_ref_required", "this action requires a verified target_ref", change=change, field="target_ref")
        return None
    if not _material_ref_valid(ref):
        ctx.error("target_ref_invalid", "target_ref must be exactly {artifact_ref, path} with a run-relative artifact and JSON Pointer", change=change, field="target_ref")
        return None
    key = _canonical_ref(ref)
    if key in ctx.bindings:
        return ctx.bindings[key]
    try:
        binding = ctx.resolve_binding(ref)
    except Exception as exc:  # trusted adapter boundary; expose no path contents
        ctx.error("binding_lookup_failed", f"verified target binding could not be loaded: {exc}", change=change, field="target_ref")
        return None
    if not isinstance(binding, Mapping):
        ctx.error("binding_not_found", "target_ref has no verified resource binding", change=change, field="target_ref")
        return None
    value = deepcopy(dict(binding))
    expected_kind = change.get("resource_kind")
    if isinstance(expected_kind, str) and not _check_binding_kind(
        value, {expected_kind}, ctx, change, "target_ref"
    ):
        return None
    expected_ontology = _ontology(ctx, change)
    actual_ontology = value.get("ontology_id")
    if expected_ontology is not None and actual_ontology != expected_ontology:
        code = "binding_scope_missing" if actual_ontology is None else "binding_scope_mismatch"
        ctx.error(
            code,
            "verified target binding must belong to the selected ontology scope",
            change=change,
            field="target_ref",
        )
        return None
    ctx.bindings[key] = value
    return value


def _binding_iri(
    binding: Mapping[str, Any] | None, ctx: _Context, change: Mapping[str, Any], field: str
) -> str | None:
    iri = binding.get("resource_iri") if isinstance(binding, Mapping) else None
    if not _absolute_iri(iri):
        ctx.error("binding_identity_missing", f"verified binding must expose an absolute resource_iri for {field}", change=change, field="target_ref")
        return None
    return str(iri)


def _binding_value(
    binding: Mapping[str, Any] | None,
    output: str,
    ctx: _Context,
    change: Mapping[str, Any],
    field: str,
) -> Any:
    if output == "resource_iri":
        return _binding_iri(binding, ctx, change, field)
    if output == "resource_id":
        resource_id = binding.get("resource_id") if isinstance(binding, Mapping) else None
        if not _is_nonempty(resource_id):
            ctx.error(
                "binding_identity_missing",
                f"verified binding must expose a resource_id for {field}",
                change=change,
                field="target_ref" if field == "target_ref" else field,
            )
            return None
        return str(resource_id)
    ctx.error(
        "binding_output_invalid",
        "binding output must be resource_id or resource_iri",
        change=change,
        field=field,
    )
    return None


def _reference_output_for_key(key: str) -> str:
    if key.endswith("_id") or key.endswith("_ids"):
        return "resource_id"
    return "resource_iri"


def _check_binding_kind(
    binding: Mapping[str, Any],
    expected_kinds: set[str] | None,
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
) -> bool:
    if not expected_kinds:
        return True
    actual = binding.get("resource_kind")
    if actual not in expected_kinds:
        expected = ", ".join(sorted(expected_kinds))
        code = "binding_kind_missing" if actual is None else "binding_kind_mismatch"
        ctx.error(
            code,
            f"verified binding resource_kind must be one of {expected}",
            change=change,
            field=path,
        )
        return False
    return True


def _resolve_existing_ref(
    value: Mapping[str, Any],
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
    *,
    expected_kinds: set[str] | None = None,
    output: str = "resource_iri",
) -> tuple[Any, set[str]]:
    ref = value.get("existing_resource_ref")
    if not _material_ref_valid(ref):
        ctx.error("existing_resource_ref_invalid", "existing_resource_ref must be exactly {artifact_ref, path}", change=change, field=path, candidate_path=_candidate_input_path(ctx, change, path))
        return None, set()
    key = _canonical_ref(ref)
    if key in ctx.bindings:
        binding = ctx.bindings[key]
    else:
        try:
            binding = ctx.resolve_binding(ref)
        except Exception as exc:  # trusted adapter boundary
            ctx.error("binding_lookup_failed", f"verified resource reference could not be loaded: {exc}", change=change, field=path, candidate_path=_candidate_input_path(ctx, change, path))
            return None, set()
        if not isinstance(binding, Mapping):
            ctx.error("binding_not_found", "existing_resource_ref has no verified resource binding", change=change, field=path, candidate_path=_candidate_input_path(ctx, change, path))
            return None, set()
        binding = deepcopy(dict(binding))
        ctx.bindings[key] = binding
    if not _check_binding_kind(binding, expected_kinds, ctx, change, path):
        return None, set()
    resolved = _binding_value(binding, output, ctx, change, path)
    return resolved, set()


def _resolve_definition(
    ref_id: str,
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
    *,
    expected_kinds: set[str] | None = None,
    output: str = "resource_iri",
) -> tuple[Any, set[str]]:
    selected = [entry for entry in ctx.changes if entry.get("item_id") == ref_id]
    if not selected:
        ctx.error("unbound_definition_ref", f"definition_ref {ref_id!r} is not selected for this submission", change=change, field=path, candidate_path=ctx.item_path(ref_id))
        return None, set()
    if len(selected) != 1:
        ctx.error("ambiguous_definition_ref", f"definition_ref {ref_id!r} has more than one selected change", change=change, field=path, candidate_path=ctx.item_path(ref_id))
        return None, set()
    target = selected[0]
    if expected_kinds and target.get("resource_kind", target.get("item_kind")) not in expected_kinds:
        expected = ", ".join(sorted(expected_kinds))
        ctx.error(
            "definition_kind_mismatch",
            f"definition_ref {ref_id!r} must select one of {expected}",
            change=change,
            field=path,
            candidate_path=ctx.item_path(ref_id),
        )
        return None, set()
    action = target["action"]
    if action == "create":
        return {"item_ref": {"client_item_id": _change_client_id(target), "output": output}}, {str(target["change_id"])}
    if action in {"update", "delete"}:
        binding = _target_binding(ctx, target)
        if isinstance(binding, Mapping) and not _check_binding_kind(
            binding, expected_kinds, ctx, change, path
        ):
            return None, set()
        resolved = _binding_value(binding, output, ctx, target, path)
        return resolved, set()
    ctx.error("invalid_definition_target", f"definition_ref {ref_id!r} does not identify a resource-producing change", change=change, field=path, candidate_path=ctx.item_path(ref_id))
    return None, set()


def _resolve_ref_value(
    value: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
    *,
    resolve_reference: bool = True,
    require_wrapper: bool = False,
    expected_kinds: set[str] | None = None,
    output: str = "resource_iri",
) -> tuple[Any, set[str]]:
    # Some fields carry arbitrary JSON literals.  Their contents can happen
    # to use the same key names as the neutral reference wrappers, but the
    # contract only gives reference meaning to declared reference slots.
    if not resolve_reference:
        return deepcopy(value), set()
    if isinstance(value, Mapping) and set(value) == {"definition_ref"}:
        ref_id = value.get("definition_ref")
        if not _is_nonempty(ref_id):
            ctx.error("definition_ref_invalid", "definition_ref must be a nonempty candidate item_id", change=change, field=path, candidate_path=_candidate_input_path(ctx, change, path))
            return None, set()
        return _resolve_definition(
            str(ref_id),
            ctx,
            change,
            path,
            expected_kinds=expected_kinds,
            output=output,
        )
    if isinstance(value, Mapping) and set(value) == {"existing_resource_ref"}:
        return _resolve_existing_ref(
            value,
            ctx,
            change,
            path,
            expected_kinds=expected_kinds,
            output=output,
        )
    if require_wrapper:
        ctx.error(
            "reference_wrapper_required",
            "a declared reference slot must use definition_ref or existing_resource_ref",
            change=change,
            field=path,
            candidate_path=_candidate_input_path(ctx, change, path),
        )
        return None, set()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        dependencies: set[str] = set()
        for key, child in value.items():
            resolved, found = _resolve_ref_value(
                child,
                ctx,
                change,
                f"{path}.{key}",
                output=_reference_output_for_key(str(key)),
            )
            result[str(key)] = resolved
            dependencies.update(found)
        return result, dependencies
    if isinstance(value, list):
        result: list[Any] = []
        dependencies: set[str] = set()
        for index, child in enumerate(value):
            resolved, found = _resolve_ref_value(
                child,
                ctx,
                change,
                f"{path}[{index}]",
                output=output,
            )
            result.append(resolved)
            dependencies.update(found)
        return result, dependencies
    return deepcopy(value), set()


def _semantic_annotation(
    item: Mapping[str, Any] | None,
    value_semantic: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    *,
    supported: bool,
) -> dict[str, Any] | None:
    definitions = [(value_semantic, "fields.semantic_definition" if item is None else "value.semantic_definition")]
    if item is not None:
        definitions.append((item.get("semantic_definition"), "candidate.semantic_definition"))
    for definition, field_path in definitions:
        if isinstance(definition, Mapping):
            for key in sorted(set(definition) - set(_SEMANTIC_DEFINITION_FIELDS)):
                ctx.error(
                    "unsupported_semantic_field",
                    f"unsupported semantic_definition field {key}; supported: {', '.join(_SEMANTIC_DEFINITION_FIELDS)}",
                    change=change, field=f"{field_path}.{key}",
                )
    if item is None:
        if value_semantic is None:
            return None
        if not isinstance(value_semantic, Mapping):
            ctx.error("invalid_semantic_definition", "semantic_definition must be an object", change=change, field="fields.semantic_definition")
            return None
        result = deepcopy(dict(value_semantic))
        if not supported and result:
            ctx.error("semantic_definition_not_supported", "the selected command has no semantic_definition field", change=change, field="fields.semantic_definition")
            return None
        return result or None
    item_id = str(item["item_id"])
    item_semantic = item.get("semantic_definition")
    if item_semantic is not None and not isinstance(item_semantic, Mapping):
        ctx.error("invalid_semantic_definition", "candidate semantic_definition must be an object", change=change, item_id=item_id, field="candidate.semantic_definition", candidate_path=ctx.item_path(item_id, ".semantic_definition"))
        return None
    if value_semantic is not None and not isinstance(value_semantic, Mapping):
        ctx.error("invalid_semantic_definition", "candidate value semantic_definition must be an object", change=change, item_id=item_id, field="value.semantic_definition", candidate_path=ctx.item_path(item_id, ".value.semantic_definition"))
        return None
    result = deepcopy(dict(value_semantic or {}))
    for key, value in dict(item_semantic or {}).items():
        if key in result and result[key] != value:
            ctx.error("semantic_content_conflict", f"semantic_definition.{key} differs between item and value", change=change, item_id=item_id, field=f"candidate.semantic_definition.{key}", candidate_path=ctx.item_path(item_id, f".semantic_definition.{key}"))
        else:
            result[key] = deepcopy(value)
    meaning = item.get("business_meaning")
    unknowns = item.get("unknowns")
    if not isinstance(unknowns, list) or any(not isinstance(value, str) for value in unknowns):
        ctx.error("invalid_unknowns", "candidate unknowns must be a string list", change=change, item_id=item_id, field="candidate.unknowns", candidate_path=ctx.item_path(item_id, ".unknowns"))
    if meaning is not None and not isinstance(meaning, str):
        ctx.error("invalid_business_meaning", "candidate business_meaning must be a string", change=change, item_id=item_id, field="candidate.business_meaning", candidate_path=ctx.item_path(item_id, ".business_meaning"))
    if _is_nonempty(meaning):
        if "business_meaning" in result and result["business_meaning"] != meaning:
            ctx.error("semantic_content_conflict", "business_meaning differs from semantic_definition", change=change, item_id=item_id, field="candidate.business_meaning", candidate_path=ctx.item_path(item_id, ".business_meaning"))
        else:
            result.setdefault("business_meaning", meaning)
    if isinstance(unknowns, list) and unknowns:
        merged: list[str] = []
        for values in (result.get("unknowns", []), unknowns):
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value not in merged:
                        merged.append(value)
        result["unknowns"] = merged
    if result and not supported:
        ctx.error("semantic_definition_not_supported", "the selected command has no semantic_definition field; preserve this meaning in an explicit modeled resource", change=change, item_id=item_id, field="candidate.semantic_definition", candidate_path=ctx.item_path(item_id, ".semantic_definition"))
        return None
    return result or None


def _validate_public_fields(
    value: Any,
    command_kind: str,
    ctx: _Context,
    change: Mapping[str, Any],
    *,
    path: str,
) -> dict[str, Any] | None:
    item_id = str(change["item_id"]) if change.get("item_id") is not None else None
    candidate_path = ctx.item_path(item_id, f".{path}") if item_id and path == "value" else None
    if not isinstance(value, Mapping):
        ctx.error(
            "fields_object_required",
            "semantic fields must be an object",
            change=change,
            field=path,
            candidate_path=candidate_path,
        )
        return None
    result = deepcopy(dict(value))
    allowed = _COMMAND_FIELDS[command_kind]
    unknown = sorted(set(result) - allowed)
    if unknown:
        import_fields = sorted(set(unknown) & {"source_id", "run_id"})
        regular_fields = [key for key in unknown if key not in import_fields]
        if import_fields:
            ctx.error(
                "unsupported_batch_variant",
                f"source_id/run_id import mapping fields are not accepted: {', '.join(import_fields)}",
                change=change,
                field=path,
                candidate_path=candidate_path,
            )
        if regular_fields:
            ctx.error(
                "unsupported_change_field",
                f"fields contain unsupported field(s): {', '.join(regular_fields)}; supported for {command_kind}: {', '.join(sorted(allowed))}",
                change=change,
                field=path,
                candidate_path=candidate_path,
            )
        for key in unknown:
            result.pop(key, None)
    # An IRI field may reference a different business resource (for example
    # join_mapping.relation_type_iri); only this command's own identity is
    # technical. Referenced resources are resolved from their wrappers below.
    identity = _IDENTITY_FIELDS.get(command_kind.split("_", 1)[1])
    forbidden = (_TECHNICAL_FIELDS - set(_IDENTITY_FIELDS.values())) | {identity}
    technical = sorted(set(result) & forbidden)
    if technical:
        ctx.error(
            "technical_field_forbidden",
            f"fields cannot carry target/resource identity: {', '.join(technical)}",
            change=change,
            field=path,
            candidate_path=candidate_path,
        )
        for key in technical:
            result.pop(key, None)
    if command_kind.startswith("create_"):
        definitions = _BATCH_CONTRACT["create_payloads"].get(command_kind, {}).get("fields", {})
        kinds = {"string": str, "object": Mapping, "array": list, "boolean": bool,
                 "integer": int, "number": (int, float), "null": type(None)}
        for key, field_value in result.items():
            shape = definitions.get(key, {})
            if key == "properties" and command_kind == "create_entity":
                continue  # The approved neutral [{property_ref, value}] adapter.
            if isinstance(field_value, Mapping) and set(field_value) in ({"definition_ref"}, {"existing_resource_ref"}):
                continue  # The declared slot resolver validates identity/kind.
            expected = shape.get("type", [])
            expected = [expected] if isinstance(expected, str) else expected
            valid_type = not expected or any(
                kind in kinds and isinstance(field_value, kinds[kind])
                and not (kind in {"integer", "number"} and isinstance(field_value, bool))
                for kind in expected
            )
            if (not valid_type or ("enum" in shape and field_value not in shape["enum"])
                    or (isinstance(field_value, str) and len(field_value) < shape.get("min_length", 0))
                    or (isinstance(field_value, list) and len(field_value) < shape.get("min_items", 0))):
                ctx.error("invalid_field", f"{key} does not match the existing command field contract",
                          change=change, field=f"{path}.{key}", candidate_path=_candidate_input_path(ctx, change, f"{path}.{key}"))
    return result


def _mapping_reference_field(key: str, context: str, schema: str | None = None) -> bool:
    if context == "root":
        return (
            key in _MAPPING_REFERENCE_FIELDS
            or key == "grain"
            or key in _GENERIC_REFERENCE_FIELDS.get(schema or "", ())
        )
    if context == "column_mappings":
        return key == "property_iri"
    if context == "join_path":
        return key in {"from_mapping_iri", "to_mapping_iri"}
    if context == "filters":
        return key == "field"
    if context == "mapping_definition":
        return key in _MAPPING_REFERENCE_FIELDS
    if context == "identifiers" or context == "property_bindings":
        return key in {"property_iri", "table_mapping_iri"}
    if context == "field_meanings":
        return key == "conversion_rule_iri"
    if context == "step_semantics":
        return key == "condition_rule_iri"
    if context == "contexts":
        return key in {
            "base_mapping_iri",
            "join_mapping_iris",
            "conversion_rule_iris",
        }
    if context == "counted_identity":
        return key == "table_mapping_iri"
    return False


def _mapping_child_context(context: str, key: str) -> str | None:
    if context == "root" and key in _MAPPING_REFERENCE_CONTAINERS:
        return key
    if context == "mapping_definition" and key in _MAPPING_REFERENCE_CONTAINERS:
        return key
    if context == "contexts" and key in {"property_bindings", "counted_identity"}:
        return key
    return None


def _resolve_declared_mapping_value(
    value: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    source_path: str,
    payload_path: str,
    key: str,
) -> tuple[Any, set[str], dict[str, dict[str, str]], dict[str, list[str]]]:
    """Resolve one declared mapping reference slot and record its provenance."""

    dependencies: set[str] = set()
    reference_slots: dict[str, dict[str, str]] = {}
    field_map: dict[str, list[str]] = {}
    output = _reference_output_for_key(key)

    def resolve_one(child: Any, child_source: str, child_payload: str) -> Any:
        nonlocal dependencies
        resolved, found = _resolve_ref_value(
            child,
            ctx,
            change,
            child_source,
            require_wrapper=True,
            output=output,
        )
        dependencies.update(found)
        field_map[child_payload] = [_source_pointer(ctx, change, child_source)]
        slot = _item_ref_slot(resolved)
        if slot is not None:
            reference_slots[child_payload] = slot
        return resolved

    if isinstance(value, list):
        resolved_list = [
            resolve_one(
                child,
                f"{source_path}[{index}]",
                _join_pointer(payload_path, index),
            )
            for index, child in enumerate(value)
        ]
        return resolved_list, dependencies, reference_slots, field_map
    if value is None:
        field_map[payload_path] = [_source_pointer(ctx, change, source_path)]
        return None, dependencies, reference_slots, field_map
    resolved = resolve_one(value, source_path, payload_path)
    return resolved, dependencies, reference_slots, field_map


def _resolve_mapping_tree(
    value: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    source_path: str,
    payload_path: str,
    context: str,
    schema: str | None = None,
    source_aliases: Mapping[str, str] | None = None,
) -> tuple[Any, set[str], dict[str, dict[str, str]], dict[str, list[str]]]:
    if isinstance(value, list):
        resolved: list[Any] = []
        dependencies: set[str] = set()
        reference_slots: dict[str, dict[str, str]] = {}
        field_map: dict[str, list[str]] = {}
        for index, child in enumerate(value):
            child_value, found, slots, mapping = _resolve_mapping_tree(
                child,
                ctx,
                change,
                f"{source_path}[{index}]",
                _join_pointer(payload_path, index),
                context,
                schema,
                source_aliases,
            )
            resolved.append(child_value)
            dependencies.update(found)
            reference_slots.update(slots)
            field_map.update(mapping)
        return resolved, dependencies, reference_slots, field_map
    if not isinstance(value, Mapping):
        return deepcopy(value), set(), {}, {}

    resolved_object: dict[str, Any] = {}
    dependencies: set[str] = set()
    reference_slots: dict[str, dict[str, str]] = {}
    field_map: dict[str, list[str]] = {}
    for key, child in value.items():
        key_text = str(key)
        source_key = (
            source_aliases.get(key_text, key_text)
            if context == "root" and isinstance(source_aliases, Mapping)
            else key_text
        )
        child_source = f"{source_path}.{source_key}"
        child_payload = _join_pointer(payload_path, key_text)
        if _mapping_reference_field(key_text, context, schema):
            child_value, found, slots, mapping = _resolve_declared_mapping_value(
                child,
                ctx,
                change,
                child_source,
                child_payload,
                key_text,
            )
        else:
            child_context = _mapping_child_context(context, key_text)
            if child_context is None:
                child_value, found, slots, mapping = deepcopy(child), set(), {}, {}
            else:
                child_value, found, slots, mapping = _resolve_mapping_tree(
                    child,
                    ctx,
                    change,
                    child_source,
                    child_payload,
                    child_context,
                    schema,
                    source_aliases,
                )
        resolved_object[key_text] = child_value
        dependencies.update(found)
        reference_slots.update(slots)
        field_map.update(mapping)
    return resolved_object, dependencies, reference_slots, field_map


def _resolve_field_values(
    value: dict[str, Any],
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
    *,
    schema: str,
    source_aliases: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], set[str], dict[str, dict[str, str]], dict[str, list[str]]]:
    """Resolve only declared mapping slots; preserve all other JSON values."""

    resolved, dependencies, reference_slots, field_map = _resolve_mapping_tree(
        value, ctx, change, path, "/payload", "root", schema, source_aliases
    )
    # ``schema`` is intentionally accepted at this narrow boundary so callers
    # document which current command contract is being traversed.  The
    # declaration table above is shared by the four mapping command kinds;
    # arbitrary command JSON never enters this resolver.
    _ = schema
    return dict(resolved), dependencies, reference_slots, field_map


def _annotation_from_value(
    value: dict[str, Any], item: Mapping[str, Any] | None, ctx: _Context, change: Mapping[str, Any], *, supported: bool
) -> dict[str, Any] | None:
    semantic = value.pop("semantic_definition", None)
    return _semantic_annotation(item, semantic, ctx, change, supported=supported)


def _class_ref(
    value: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    path: str,
    *,
    output: str = "resource_iri",
) -> tuple[Any, set[str]]:
    if not isinstance(value, Mapping) or set(value) not in ({"definition_ref"}, {"existing_resource_ref"}):
        ctx.error("class_reference_required", "class membership must use definition_ref or existing_resource_ref", change=change, field=path)
        return None, set()
    return _resolve_ref_value(
        value, ctx, change, path, expected_kinds={"class"}, output=output
    )


def _entity_build(
    item: Mapping[str, Any] | None,
    fields: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    action: str,
) -> _Build | None:
    command = _COMMANDS["entity"][action]
    raw = item.get("value") if item is not None else fields
    value = _validate_public_fields(raw, command, ctx, change, path="value" if item else "fields")
    if value is None:
        return None
    dependencies: set[str] = set()
    mapping: dict[str, list[str]] = {}
    reference_slots: dict[str, dict[str, str]] = {}
    deferred_property_keys: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    item_id = str(item["item_id"]) if item is not None else None
    label_seen = False
    if "label" in value:
        label_seen = True
        label = value.pop("label")
        if not _is_nonempty(label) and not (action == "update" and label is None):
            ctx.error(
                "invalid_field",
                "entity label must be a nonempty string",
                change=change,
                item_id=item_id,
                field=_input_field(item, "label"),
                candidate_path=ctx.item_path(item_id, ".value.label") if item_id else None,
            )
        else:
            payload["label"] = deepcopy(label)
            mapping = _merge_field_maps(
                mapping,
                _field_map(ctx, item_id, ".value.label" if item else ".label", "label"),
            )
    if "aliases" in value:
        payload["aliases"] = deepcopy(value.pop("aliases"))
        mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.aliases" if item else ".aliases", "aliases"))
    if "class_iri_or_legacy_id" in value:
        resolved, found = _class_ref(
            value.pop("class_iri_or_legacy_id"),
            ctx,
            change,
            "value.class_iri_or_legacy_id",
        )
        payload["class_iri_or_legacy_id"] = resolved
        dependencies.update(found)
        slot = _item_ref_slot(resolved)
        if slot is not None:
            reference_slots["/payload/class_iri_or_legacy_id"] = slot
        mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.class_iri_or_legacy_id" if item else ".class_iri_or_legacy_id", "class_iri_or_legacy_id"))
    if "class_iris" in value:
        classes = value.pop("class_iris")
        if not isinstance(classes, list):
            ctx.error("invalid_class_membership", "class_iris must be an array of explicit references", change=change, item_id=item_id, field=_input_field(item, "class_iris"))
        else:
            resolved_classes: list[Any] = []
            for index, entry in enumerate(classes):
                resolved, found = _class_ref(
                    entry, ctx, change, f"value.class_iris[{index}]"
                )
                resolved_classes.append(resolved)
                dependencies.update(found)
                slot = _item_ref_slot(resolved)
                if slot is not None:
                    reference_slots[_join_pointer("/payload/class_iris", index)] = slot
            payload["class_iris"] = resolved_classes
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.class_iris" if item else ".class_iris", "class_iris"))
    if "properties" in value:
        properties = value.pop("properties")
        if action == "update" and properties is None:
            payload["properties"] = None
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.properties" if item else ".properties", "properties"))
        elif not isinstance(properties, list):
            ctx.error("invalid_entity_properties", "entity properties must use [{property_ref, value}] entries", change=change, item_id=item_id, field=_input_field(item, "properties"))
        else:
            normalized: dict[str, Any] = {}
            property_field_map: dict[str, list[str]] = {}
            input_prefix = "value" if item is not None else "fields"
            for index, entry in enumerate(properties):
                if not isinstance(entry, Mapping) or set(entry) != {"property_ref", "value"}:
                    ctx.error("invalid_entity_property", "each entity property entry requires only property_ref and value", change=change, item_id=item_id, field=_input_field(item, f"properties[{index}]"))
                    continue
                property_ref = entry["property_ref"]
                if not isinstance(property_ref, Mapping) or set(property_ref) not in ({"definition_ref"}, {"existing_resource_ref"}):
                    ctx.error("property_reference_required", "entity property_ref must be definition_ref or existing_resource_ref", change=change, item_id=item_id, field=_input_field(item, f"properties[{index}].property_ref"))
                    continue
                property_value, found = _resolve_ref_value(
                    property_ref,
                    ctx,
                    change,
                    f"value.properties[{index}].property_ref",
                    expected_kinds={"property"},
                )
                dependencies.update(found)
                resolved_value, found = _resolve_ref_value(
                    entry["value"],
                    ctx,
                    change,
                    f"value.properties[{index}].value",
                    resolve_reference=False,
                )
                dependencies.update(found)
                property_source = f"{input_prefix}.properties[{index}].property_ref"
                value_source = f"{input_prefix}.properties[{index}].value"
                property_source_pointer = _source_pointer(ctx, change, property_source)
                value_source_pointer = _source_pointer(ctx, change, value_source)
                if _item_ref(property_value):
                    # The property resource may be created in this same
                    # submission.  Keep the key neutral until Runner has the
                    # actual resource_iri; never derive an IRI from an item id.
                    deferred_property_keys.append(
                        {
                            "payload_path": "/payload/properties",
                            "property_ref": deepcopy(property_value),
                            "value": deepcopy(resolved_value),
                            "property_ref_source": property_source_pointer,
                            "value_source": value_source_pointer,
                        }
                    )
                    continue
                if not _absolute_iri(property_value):
                    ctx.error("unsupported_reference_slot", "entity property keys require an existing property IRI; a property created in this submission must be bound before this entity", change=change, item_id=item_id, field=_input_field(item, f"properties[{index}].property_ref"), candidate_path=ctx.item_path(item_id, f".value.properties[{index}].property_ref") if item_id else None)
                    continue
                if property_value in normalized:
                    ctx.error("duplicate_entity_property", "entity contains the same property more than once", change=change, item_id=item_id, field=_input_field(item, f"properties[{index}].property_ref"))
                    continue
                normalized[str(property_value)] = resolved_value
                property_field_map[_join_pointer("/payload/properties", property_value)] = [
                    property_source_pointer,
                    value_source_pointer,
                ]
            payload["properties"] = normalized
            mapping = _merge_field_maps(
                mapping,
                _field_map(ctx, item_id, ".value.properties" if item else ".properties", "properties"),
                property_field_map,
            )
    for key in ("action_definition", "parameter_definition"):
        if key in value:
            payload[key] = deepcopy(value.pop(key))
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, f".value.{key}" if item else f".{key}", key))
    annotation = _annotation_from_value(value, item, ctx, change, supported=True)
    if annotation is not None:
        payload["semantic_definition"] = annotation
        mapping = _merge_field_maps(mapping, _semantic_field_map(ctx, item_id, item, raw))
    if value:
        ctx.error("unsupported_value_field", f"entity value contains unsupported field(s): {', '.join(sorted(value))}", change=change, item_id=item_id, field="value" if item is not None else "fields")
    if action == "create" and not label_seen:
        ctx.error("missing_field", "entity creation requires label", change=change, item_id=item_id, field=_input_field(item, "label"), candidate_path=ctx.item_path(item_id, ".value.label") if item_id else None)
    return _Build(
        command,
        payload,
        dependencies,
        mapping,
        reference_slots,
        deferred_property_keys,
    )


def _property_build(
    item: Mapping[str, Any] | None,
    fields: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    action: str,
) -> _Build | None:
    command = _COMMANDS["property"][action]
    raw = item.get("value") if item is not None else fields
    value = _validate_public_fields(raw, command, ctx, change, path="value" if item else "fields")
    if value is None:
        return None
    item_id = str(item["item_id"]) if item is not None else None
    payload: dict[str, Any] = {}
    dependencies: set[str] = set()
    mapping: dict[str, list[str]] = {}
    reference_slots: dict[str, dict[str, str]] = {}
    name = value.pop("name", None)
    if name is not None:
        if not _is_nonempty(name):
            ctx.error("invalid_field", "property name must be nonempty", change=change, item_id=item_id, field=_input_field(item, "name"))
        else:
            payload["name"] = name
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.name" if item else ".name", "name"))
    if "description" in value:
        payload["description"] = deepcopy(value.pop("description"))
        mapping = _merge_field_maps(
            mapping,
            _field_map(ctx, item_id, ".value.description" if item else ".description", "description"),
        )
    kind = value.pop("predicate_kind", None)
    if (action == "create" or kind is not None) and (
            not _is_nonempty(kind) or str(kind).lower() not in {"fact", "relation"}):
        ctx.error("predicate_kind_required", "property requires explicit predicate_kind=fact or predicate_kind=relation", change=change, item_id=item_id, field=_input_field(item, "predicate_kind"), candidate_path=ctx.item_path(item_id, ".value.predicate_kind") if item_id else None)
    kind = str(kind).lower() if kind is not None else ""
    datatype = value.pop("datatype", None)
    object_class = value.pop("object_class_id", None)
    if action == "update" and not kind:
        # A description/name patch does not choose a new predicate kind.
        # Existing update handlers accept independent nullable range patches.
        if "datatype" in raw:
            payload["datatype"] = datatype
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.datatype" if item else ".datatype", "datatype"))
        if "object_class_id" in raw:
            resolved, found = _class_ref(object_class, ctx, change, "value.object_class_id", output="resource_id") if object_class is not None else (None, set())
            payload["object_class_id"] = resolved
            dependencies.update(found)
            slot = _item_ref_slot(resolved)
            if slot is not None:
                reference_slots["/payload/object_class_id"] = slot
            mapping = _merge_field_maps(mapping, _field_map(ctx, item_id, ".value.object_class_id" if item else ".object_class_id", "object_class_id"))
    if kind == "fact":
        if object_class is not None:
            ctx.error("property_type_conflict", "fact property cannot declare object_class_id", change=change, item_id=item_id, field=_input_field(item, "object_class_id"))
        if not _is_nonempty(datatype):
            ctx.error("missing_datatype", "fact property requires an explicit datatype", change=change, item_id=item_id, field=_input_field(item, "datatype"), candidate_path=ctx.item_path(item_id, ".value.datatype") if item_id else None)
        else:
            payload["datatype"] = datatype
            mapping = _merge_field_maps(
                mapping,
                _field_map(ctx, item_id, ".value.datatype" if item else ".datatype", "datatype"),
            )
    elif kind == "relation":
        if datatype is not None:
            ctx.error("property_type_conflict", "relation property cannot declare datatype", change=change, item_id=item_id, field=_input_field(item, "datatype"))
        if object_class is not None:
            resolved, found = _class_ref(
                object_class,
                ctx,
                change,
                "value.object_class_id",
                output="resource_id",
            )
            payload["object_class_id"] = resolved
            dependencies.update(found)
            slot = _item_ref_slot(resolved)
            if slot is not None:
                reference_slots["/payload/object_class_id"] = slot
            mapping = _merge_field_maps(
                mapping,
                _field_map(
                    ctx,
                    item_id,
                    ".value.object_class_id" if item else ".object_class_id",
                    "object_class_id",
                ),
            )
    domain = value.pop("class_id", None)
    if domain is not None:
        resolved, found = _class_ref(
            domain, ctx, change, "value.class_id", output="resource_id"
        )
        payload["class_id"] = resolved
        dependencies.update(found)
        slot = _item_ref_slot(resolved)
        if slot is not None:
            reference_slots["/payload/class_id"] = slot
        mapping = _merge_field_maps(
            mapping,
            _field_map(ctx, item_id, ".value.class_id" if item else ".class_id", "class_id"),
        )
    annotation = _annotation_from_value(value, item, ctx, change, supported=True)
    if annotation is not None:
        payload["semantic_definition"] = annotation
        mapping = _merge_field_maps(mapping, _semantic_field_map(ctx, item_id, item, raw))
    if value:
        ctx.error("unsupported_value_field", f"property value contains unsupported field(s): {', '.join(sorted(value))}", change=change, item_id=item_id, field="value" if item is not None else "fields")
    if action == "create" and "name" not in payload:
        ctx.error("missing_field", "property creation requires name", change=change, item_id=item_id, field=_input_field(item, "name"), candidate_path=ctx.item_path(item_id, ".value.name") if item_id else None)
    return _Build(command, payload, dependencies, mapping, reference_slots)


def _endpoint(
    value: Any, ctx: _Context, change: Mapping[str, Any], path: str
) -> tuple[Any, set[str]]:
    if isinstance(value, str) and value in ctx.items:
        return _resolve_definition(
            value, ctx, change, path, expected_kinds={"entity"}, output="resource_iri"
        )
    if isinstance(value, Mapping) and set(value) in ({"definition_ref"}, {"existing_resource_ref"}):
        return _resolve_ref_value(
            value,
            ctx,
            change,
            path,
            expected_kinds={"entity"},
            output="resource_iri",
        )
    ctx.error("relation_endpoint_reference_required", "relation endpoint must name a candidate item or existing_resource_ref", change=change, field=path)
    return None, set()


def _predicate(
    value: Any, ctx: _Context, change: Mapping[str, Any], path: str
) -> tuple[Any, set[str]]:
    if not isinstance(value, Mapping) or set(value) not in ({"definition_ref"}, {"existing_resource_ref"}):
        ctx.error("predicate_reference_required", "relation predicate must use definition_ref or existing_resource_ref", change=change, field=path)
        return None, set()
    return _resolve_ref_value(
        value,
        ctx,
        change,
        path,
        expected_kinds={"property"},
        output="resource_iri",
    )


def _relation_build(
    item: Mapping[str, Any] | None,
    fields: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    action: str,
) -> _Build | None:
    item_id = str(item["item_id"]) if item is not None else None
    if action == "update":
        ctx.error("unsupported_operation", "relation changes use explicit delete and create; relation update is unavailable", change=change, item_id=item_id, field="action")
        return None
    if action == "delete":
        binding = _target_binding(ctx, change)
        if not isinstance(binding, Mapping):
            return None
        keys = ("source_entity_iri", "relation_type_iri", "target_entity_iri")
        payload = {key: binding.get(key) for key in keys}
        if any(not _absolute_iri(value) for value in payload.values()):
            ctx.error("relation_binding_incomplete", "relation target binding must include source_entity_iri, relation_type_iri and target_entity_iri", change=change, field="target_ref")
            return None
        return _Build("delete_relation", payload, set(), {f"/payload/{key}": ["/target_ref"] for key in keys})
    raw = item.get("value") if item is not None else fields
    if not isinstance(raw, Mapping):
        ctx.error("fields_object_required", "relation create fields must be an object", change=change, item_id=item_id, field="value")
        return None
    value = deepcopy(dict(raw))
    allowed = {"predicate"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        ctx.error("unsupported_value_field", f"relation value contains unsupported field(s): {', '.join(unknown)}", change=change, item_id=item_id, field="value")
        for key in unknown:
            value.pop(key, None)
    endpoint_data = item.get("relation_endpoints") if item is not None else value.pop("relation_endpoints", None)
    if not isinstance(endpoint_data, Mapping) or set(endpoint_data) != {"from_item_id", "to_item_id"}:
        ctx.error("missing_relation_endpoints", "relation requires explicit relation_endpoints.from_item_id and to_item_id", change=change, item_id=item_id, field="relation_endpoints", candidate_path=ctx.item_path(item_id, ".relation_endpoints") if item_id else None)
        return None
    source, dependencies = _endpoint(endpoint_data["from_item_id"], ctx, change, "relation_endpoints.from_item_id")
    target, found = _endpoint(endpoint_data["to_item_id"], ctx, change, "relation_endpoints.to_item_id")
    dependencies.update(found)
    predicate_value, found = _predicate(value.pop("predicate", None), ctx, change, "value.predicate")
    dependencies.update(found)
    if not all(_absolute_iri(value) or _item_ref(value) for value in (source, predicate_value, target)):
        return None
    if item is not None:
        item_value = item.get("value")
        if item.get("semantic_definition") is not None:
            ctx.error(
                "semantic_definition_not_supported",
                "relation has no semantic_definition command field",
                change=change,
                item_id=item_id,
                field="candidate.semantic_definition",
                candidate_path=ctx.item_path(item_id, ".semantic_definition"),
            )
        if isinstance(item_value, Mapping) and item_value.get("semantic_definition") is not None:
            ctx.error(
                "semantic_definition_not_supported",
                "relation has no semantic_definition command field",
                change=change,
                item_id=item_id,
                field="value.semantic_definition",
                candidate_path=ctx.item_path(item_id, ".value.semantic_definition"),
            )
    mapping = _merge_field_maps(
        _field_map(ctx, item_id, ".relation_endpoints.from_item_id" if item else ".relation_endpoints.from_item_id", "source_entity_iri"),
        _field_map(ctx, item_id, ".value.predicate" if item else ".predicate", "relation_type_iri"),
        _field_map(ctx, item_id, ".relation_endpoints.to_item_id" if item else ".relation_endpoints.to_item_id", "target_entity_iri"),
    )
    reference_slots = {}
    for payload_key, resolved in (
        ("source_entity_iri", source),
        ("relation_type_iri", predicate_value),
        ("target_entity_iri", target),
    ):
        slot = _item_ref_slot(resolved)
        if slot is not None:
            reference_slots[f"/payload/{payload_key}"] = slot
    return _Build(
        "create_relation",
        {"source_entity_iri": source, "relation_type_iri": predicate_value, "target_entity_iri": target},
        dependencies,
        mapping,
        reference_slots,
    )


def _mapping_build(
    item: Mapping[str, Any] | None,
    fields: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    action: str,
    resource_kind: str,
) -> _Build | None:
    command = _COMMANDS[resource_kind][action]
    raw = item.get("value") if item is not None else fields
    raw, alias_sources = _normalize_mapping_aliases(raw, resource_kind, ctx, change)
    value = _validate_public_fields(raw, command, ctx, change, path="value" if item else "fields")
    if value is None:
        return None
    item_id = str(item["item_id"]) if item is not None else None
    annotation = _annotation_from_value(value, item, ctx, change, supported=True)
    resolved, dependencies, reference_slots, nested_field_map = _resolve_field_values(
        value,
        ctx,
        change,
        "value" if item else "fields",
        schema=resource_kind,
        source_aliases=alias_sources,
    )
    mapping = {
        f"/payload{_pointer_path(key)}": [
            _candidate_pointer(
                ctx,
                item_id,
                f".value.{alias_sources.get(key, key)}" if item else f".{alias_sources.get(key, key)}",
            )
        ]
        for key in resolved
    }
    mapping = _merge_field_maps(
        mapping,
        {
            pointer: sources
            for pointer, sources in nested_field_map.items()
            if pointer.count("/") > 2
        },
    )
    if annotation is not None:
        resolved["semantic_definition"] = annotation
        mapping = _merge_field_maps(mapping, _semantic_field_map(ctx, item_id, item, raw))
    if "source_id" in resolved or "run_id" in resolved:
        ctx.error("unsupported_batch_variant", "source_id/run_id import mapping fields are not accepted", change=change, item_id=item_id, field="value")
        resolved.pop("source_id", None)
        resolved.pop("run_id", None)
    if action == "create":
        for required in _CREATE_REQUIRED.get(command, ()):
            if required not in resolved or (resolved[required] is None and required != "schema_source"):
                ctx.error("missing_field", f"{resource_kind} creation requires {required}", change=change, item_id=item_id, field=_input_field(item, required), candidate_path=ctx.item_path(item_id, f".value.{required}") if item_id else None)
        if command == "create_table_mapping":
            targets = {bool(resolved.get("mapped_class_iri")), bool(resolved.get("mapped_definition_iri"))}
            if targets != {True, False}:
                ctx.error("mapping_target_required", "table_mapping requires exactly one mapped_class_iri or mapped_definition_iri", change=change, item_id=item_id, field=_input_field(item, "mapped_class_iri"), candidate_path=ctx.item_path(item_id, ".value.mapped_class_iri") if item_id else None)
    return _Build(command, resolved, dependencies, mapping, reference_slots)


def _generic_build(
    fields: Any,
    ctx: _Context,
    change: Mapping[str, Any],
    action: str,
    resource_kind: str,
) -> _Build | None:
    command = _COMMANDS[resource_kind][action]
    value = _validate_public_fields(fields, command, ctx, change, path="fields")
    if value is None:
        return None
    annotation = _annotation_from_value(value, None, ctx, change, supported="semantic_definition" in _COMMAND_FIELDS[command])
    resolved, dependencies, reference_slots, nested_field_map = _resolve_field_values(
        value, ctx, change, "fields", schema=command
    )
    mapping = _semantic_field_map(ctx, None, None, fields) if annotation is not None else {}
    if annotation is not None:
        resolved["semantic_definition"] = annotation
    if action == "create":
        for required in _CREATE_REQUIRED.get(command, ()):
            if required not in resolved or resolved[required] is None:
                ctx.error("missing_field", f"{resource_kind} creation requires {required}", change=change, field=f"fields.{required}")
    return _Build(
        command,
        resolved,
        dependencies,
        _merge_field_maps(
            {f"/payload{_pointer_path(key)}": [_field_marker(key)] for key in resolved},
            {
                pointer: sources
                for pointer, sources in nested_field_map.items()
                if pointer.count("/") > 2
            },
            mapping,
        ),
        reference_slots,
    )


def _target_identity(
    build: _Build, resource_kind: str, binding: Mapping[str, Any] | None, ctx: _Context, change: Mapping[str, Any]
) -> None:
    identity = _IDENTITY_FIELDS.get(resource_kind)
    if identity is None or build.command_kind in {"delete_relation", "update_fact", "delete_fact"}:
        return
    iri = _binding_iri(binding, ctx, change, identity)
    if iri is not None:
        build.payload[identity] = iri
        build.field_map.setdefault(f"/payload/{identity}", []).append("/target_ref")


def _fact_build(
    fields: Any, ctx: _Context, change: Mapping[str, Any], action: str
) -> _Build | None:
    binding = _target_binding(ctx, change)
    if not isinstance(binding, Mapping):
        return None
    if action == "set_fact":
        value = _validate_public_fields(fields, "update_fact", ctx, change, path="fields")
        if value is None:
            return None
        unknown = sorted(set(value) - {"new_object_value", "new_object_is_iri"})
        if unknown:
            ctx.error("fact_fields_invalid", f"set_fact fields only allow new_object_value and new_object_is_iri: {', '.join(unknown)}", change=change, field="fields")
            for key in unknown:
                value.pop(key, None)
        payload = {
            "subject_iri": binding.get("subject_iri"),
            "predicate_iri": binding.get("predicate_iri"),
            "old_object_value": binding.get("old_object_value", binding.get("object_value")),
            "old_object_is_iri": binding.get("old_object_is_iri", binding.get("object_is_iri")),
        }
        if not (
            "old_object_value" in binding
            or "object_value" in binding
        ) or not ("old_object_is_iri" in binding or "object_is_iri" in binding):
            ctx.error(
                "fact_binding_incomplete",
                "fact target binding must include the existing object value and IRI flag",
                change=change,
                field="target_ref",
            )
        if not _absolute_iri(payload["subject_iri"]) or not _absolute_iri(payload["predicate_iri"]):
            ctx.error("fact_binding_incomplete", "fact target binding must include absolute subject_iri and predicate_iri", change=change, field="target_ref")
        if "new_object_value" not in value or "new_object_is_iri" not in value:
            ctx.error("fact_fields_required", "set_fact requires new_object_value and new_object_is_iri", change=change, field="fields")
        elif not isinstance(value["new_object_is_iri"], bool):
            ctx.error("fact_fields_invalid", "new_object_is_iri must be boolean", change=change, field="fields.new_object_is_iri")
        dependencies: set[str] = set()
        new_value, found = _resolve_ref_value(
            value.get("new_object_value"),
            ctx,
            change,
            "fields.new_object_value",
            resolve_reference=value.get("new_object_is_iri") is True,
            require_wrapper=value.get("new_object_is_iri") is True,
        )
        dependencies.update(found)
        if value.get("new_object_is_iri") and not (_absolute_iri(new_value) or _item_ref(new_value)):
            ctx.error("fact_iri_binding_required", "new_object_value must use a verified existing_resource_ref or same-submission definition_ref when new_object_is_iri is true", change=change, field="fields.new_object_value")
        payload["new_object_value"] = new_value
        payload["new_object_is_iri"] = value.get("new_object_is_iri")
        reference_slots = {}
        slot = _item_ref_slot(new_value)
        if slot is not None:
            reference_slots["/payload/new_object_value"] = slot
        return _Build("update_fact", payload, dependencies, {f"/payload/{key}": ["/target_ref"] for key in ("subject_iri", "predicate_iri", "old_object_value", "old_object_is_iri")} | {"/payload/new_object_value": ["/changes/fields/new_object_value"], "/payload/new_object_is_iri": ["/changes/fields/new_object_is_iri"]}, reference_slots)
    if fields is not None:
        ctx.error("delete_fact_fields_forbidden", "delete_fact uses only target_ref; fields must be null", change=change, field="fields")
        return None
    payload = {
        "subject_iri": binding.get("subject_iri"),
        "predicate_iri": binding.get("predicate_iri"),
        "object_value": binding.get("object_value", binding.get("old_object_value")),
        "object_is_iri": binding.get("object_is_iri", binding.get("old_object_is_iri")),
    }
    if not _absolute_iri(payload["subject_iri"]) or not _absolute_iri(payload["predicate_iri"]):
        ctx.error("fact_binding_incomplete", "fact target binding must include absolute subject_iri and predicate_iri", change=change, field="target_ref")
    if not ("object_value" in binding or "old_object_value" in binding) or not (
        "object_is_iri" in binding or "old_object_is_iri" in binding
    ):
        ctx.error("fact_binding_incomplete", "fact target binding must include object_value and object_is_iri", change=change, field="target_ref")
    return _Build("delete_fact", payload, set(), {f"/payload/{key}": ["/target_ref"] for key in payload})


def _delete_build(
    resource_kind: str, ctx: _Context, change: Mapping[str, Any]
) -> _Build | None:
    command = _COMMANDS.get(resource_kind, {}).get("delete")
    if command is None:
        ctx.error("unsupported_operation", f"delete is not supported for {resource_kind}", change=change, field="action")
        return None
    binding = _target_binding(ctx, change)
    if not isinstance(binding, Mapping):
        return None
    build = _Build(command, {})
    if resource_kind == "entity":
        receipt = binding.get("impact_receipt")
        if not isinstance(receipt, Mapping):
            ctx.error(
                "delete_impact_receipt_required",
                "entity deletion requires the Runner's complete tool-owned impact receipt",
                change=change,
                field="target_ref",
            )
            return None
        digest = receipt.get("receipt_digest")
        if not _is_nonempty(digest):
            ctx.error(
                "delete_impact_receipt_invalid",
                "entity deletion impact receipt must expose receipt_digest",
                change=change,
                field="target_ref",
            )
            return None
        build.payload["impact_receipt"] = deepcopy(dict(receipt))
        build.payload["impact_receipt_digest"] = str(digest)
        build.field_map["/payload/impact_receipt"] = ["/target_ref"]
        build.field_map["/payload/impact_receipt_digest"] = ["/target_ref"]
    _target_identity(build, resource_kind, binding, ctx, change)
    return build


def _validate_request(
    request: Any,
    candidate: Any,
    ontology_by_item: Any,
    resolve_binding: Any,
    result: dict[str, Any],
) -> _Context | None:
    errors = result["errors"]
    if not isinstance(request, Mapping) or set(request) != _REQUEST_FIELDS:
        errors.append({"code": "request_schema_mismatch", "change_id": None, "item_id": None, "field": None, "path": "/request", "candidate_path": None, "message": "request must contain exactly schema_version, candidate_ref and changes", "retryable": True})
        return None
    if request.get("schema_version") != REQUEST_SCHEMA:
        errors.append({"code": "request_schema_mismatch", "change_id": None, "item_id": None, "field": "schema_version", "path": "/request/schema_version", "candidate_path": None, "message": f"schema_version must be {REQUEST_SCHEMA}", "retryable": True})
    candidate_ref = request.get("candidate_ref")
    if candidate_ref is not None and not _candidate_ref_valid(candidate_ref):
        errors.append({"code": "candidate_ref_invalid", "change_id": None, "item_id": None, "field": "candidate_ref", "path": "/request/candidate_ref", "candidate_path": None, "message": "candidate_ref must be a run-relative reference or null", "retryable": True})
    if not isinstance(ontology_by_item, Mapping) or not callable(resolve_binding):
        errors.append({"code": "trusted_context_invalid", "change_id": None, "item_id": None, "field": None, "path": "/trusted_context", "candidate_path": None, "message": "ontology_by_item must be an object and resolve_binding must be callable", "retryable": True})
        return None
    if candidate_ref is not None and not isinstance(candidate, Mapping):
        errors.append({"code": "candidate_snapshot_required", "change_id": None, "item_id": None, "field": "candidate_ref", "path": "/request/candidate_ref", "candidate_path": None, "message": "candidate_ref requires the already loaded immutable candidate snapshot", "retryable": True})
        return None
    candidate_copy: dict[str, Any] | None = _json_copy(dict(candidate)) if isinstance(candidate, Mapping) else None
    if candidate_copy is not None:
        candidate_issues = tuple(validate_unified_candidate(candidate_copy))
        if candidate_issues:
            errors.extend(_candidate_issue(issue) for issue in candidate_issues)
            return None
    raw_changes = request.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        errors.append({"code": "changes_required", "change_id": None, "item_id": None, "field": "changes", "path": "/request/changes", "candidate_path": None, "message": "changes must be a non-empty array", "retryable": True})
        return None
    items = {str(item["item_id"]): dict(item) for item in (candidate_copy or {}).get("items", [])}
    indices = {str(item["item_id"]): index for index, item in enumerate((candidate_copy or {}).get("items", []))}
    ctx = _Context(candidate_copy, items, indices, [], {}, ontology_by_item, resolve_binding)
    seen: set[str] = set()
    for index, raw in enumerate(raw_changes):
        if not isinstance(raw, Mapping) or set(raw) != _CHANGE_FIELDS:
            errors.append({"code": "change_schema_mismatch", "change_id": None, "item_id": None, "field": None, "path": f"/request/changes/{index}", "candidate_path": None, "message": "each change must contain exactly change_id, action, resource_kind, item_id, target_ref and fields; " + (f"missing={sorted(_CHANGE_FIELDS - set(raw))}; unexpected={sorted(set(raw) - _CHANGE_FIELDS)}" if isinstance(raw, Mapping) else "expected an object"), "retryable": True})
            continue
        change = deepcopy(dict(raw))
        change_id = change.get("change_id")
        if not _is_nonempty(change_id) or change_id in seen:
            ctx.error("change_id_invalid", "change_id must be unique and nonempty", change=change, change_index=index, field="change_id")
            continue
        seen.add(str(change_id))
        ctx.changes.append(change)
        ctx.change_indices[str(change_id)] = index
        action = change.get("action")
        resource_kind = change.get("resource_kind")
        item_id = change.get("item_id")
        target_ref = change.get("target_ref")
        fields = change.get("fields")
        if action not in _ACTIONS:
            ctx.error("action_invalid", "action must be create, update, delete, set_fact or delete_fact", change=change, field="action")
        if resource_kind not in _RESOURCE_KINDS:
            ctx.error("resource_kind_invalid", "resource_kind is outside the approved change matrix", change=change, field="resource_kind")
        if item_id is not None and not _is_nonempty(item_id):
            ctx.error("item_id_invalid", "item_id must be a nonempty string or null", change=change, field="item_id")
        if target_ref is not None and not _material_ref_valid(target_ref):
            ctx.error("target_ref_invalid", "target_ref must be exactly {artifact_ref, path} or null", change=change, field="target_ref")
        if fields is not None and not isinstance(fields, Mapping):
            ctx.error("fields_invalid", "fields must be an object or null", change=change, field="fields")
        if resource_kind == "fact" and action not in {"set_fact", "delete_fact"}:
            ctx.error("fact_action_invalid", "fact uses set_fact or delete_fact", change=change, field="action")
        if action in {"set_fact", "delete_fact"} and resource_kind != "fact":
            ctx.error("fact_action_invalid", "set_fact/delete_fact require resource_kind=fact", change=change, field="resource_kind")
        if action in {"update", "delete", "set_fact", "delete_fact"} and target_ref is None:
            ctx.error("target_ref_required", "this action requires target_ref", change=change, field="target_ref")
        if action == "create" and target_ref is not None:
            ctx.error("target_ref_forbidden", "create does not accept target_ref", change=change, field="target_ref")
        if action == "delete" and fields is not None:
            ctx.error("delete_fields_forbidden", "delete accepts fields=null only", change=change, field="fields")
        if action == "delete_fact" and fields is not None:
            ctx.error("delete_fact_fields_forbidden", "delete_fact accepts fields=null only", change=change, field="fields")
        if action == "set_fact" and not isinstance(fields, Mapping):
            ctx.error("fact_fields_required", "set_fact requires fields", change=change, field="fields")
        if action == "set_fact" and item_id is not None:
            ctx.error("fact_item_forbidden", "fact changes address the fact through target_ref and do not use item_id", change=change, field="item_id")
        if action == "delete_fact" and item_id is not None:
            ctx.error("fact_item_forbidden", "fact changes address the fact through target_ref and do not use item_id", change=change, field="item_id")
        if item_id is not None:
            if item_id not in items:
                ctx.error("candidate_item_not_found", "item_id is not present in the immutable candidate", change=change, field="item_id")
            elif resource_kind != items[item_id].get("item_kind"):
                ctx.error("resource_kind_mismatch", "resource_kind must equal the selected candidate item_kind", change=change, field="resource_kind", candidate_path=ctx.item_path(str(item_id), ".item_kind"))
            if candidate_ref is None:
                ctx.error("candidate_ref_required", "item_id requires a non-null candidate_ref", change=change, field="item_id")
        uses_item = item_id is not None
        uses_fields = fields is not None
        if action == "create":
            if resource_kind in _CANDIDATE_KINDS and not uses_item:
                ctx.error("candidate_item_required", "current unified candidate creates must select item_id", change=change, field="item_id")
            elif resource_kind not in _CANDIDATE_KINDS and uses_item:
                ctx.error("item_id_not_supported", "this resource kind is provided through fields, not a unified candidate item", change=change, field="item_id")
            elif uses_item == uses_fields:
                ctx.error("change_source_ambiguous", "create selects exactly one of item_id or fields", change=change, field="item_id")
        elif action == "update":
            if uses_item == uses_fields:
                ctx.error("change_source_ambiguous", "update selects exactly one of item_id or fields", change=change, field="item_id")
        elif action == "delete" and resource_kind in _CANDIDATE_KINDS and item_id is None:
            # A delete may use only a target_ref for a resource whose candidate
            # item is absent; it must still carry its explicit resource_kind.
            pass
        if action == "update" and resource_kind == "relation":
            ctx.error("unsupported_operation", "relation has no update command", change=change, field="action")
        if action in {"set_fact", "delete_fact"} and item_id is not None:
            ctx.error("fact_item_forbidden", "fact changes cannot select a candidate item", change=change, field="item_id")
    if errors:
        return ctx
    return ctx


def _topological_order(
    nodes: list[dict[str, Any]], ctx: _Context
) -> list[dict[str, Any]]:
    by_id = {str(node["change"]["change_id"]): node for node in nodes}
    position = {key: index for index, key in enumerate(by_id)}
    incoming = {key: set(node["build"].dependencies) & set(by_id) for key, node in by_id.items()}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for key, dependencies in incoming.items():
        for dependency in dependencies:
            outgoing[dependency].add(key)
    ready = sorted([key for key, dependencies in incoming.items() if not dependencies], key=position.get)
    ordered: list[dict[str, Any]] = []
    while ready:
        key = ready.pop(0)
        ordered.append(by_id[key])
        for target in sorted(outgoing.get(key, ()), key=position.get):
            incoming[target].discard(key)
            if not incoming[target]:
                ready.append(target)
        ready.sort(key=position.get)
    if len(ordered) != len(nodes):
        for key, dependencies in incoming.items():
            if dependencies:
                ctx.error("unresolvable_dependency", "selected changes contain a dependency cycle", change=by_id[key]["change"], field="item_id", candidate_path=ctx.item_path(str(by_id[key]["change"].get("item_id"))) if by_id[key]["change"].get("item_id") else None)
    return ordered


def _compile_one(change: Mapping[str, Any], ctx: _Context) -> _Build | None:
    action = str(change["action"])
    resource_kind = str(change["resource_kind"])
    item = ctx.items.get(str(change["item_id"])) if change.get("item_id") is not None else None
    if action == "set_fact":
        return _fact_build(change.get("fields"), ctx, change, action)
    if action == "delete_fact":
        return _fact_build(None, ctx, change, action)
    if action == "delete":
        if resource_kind == "relation":
            return _relation_build(item, None, ctx, change, action)
        return _delete_build(resource_kind, ctx, change)
    if resource_kind == "entity":
        build = _entity_build(item, change.get("fields"), ctx, change, action)
    elif resource_kind == "property":
        build = _property_build(item, change.get("fields"), ctx, change, action)
    elif resource_kind == "relation":
        build = _relation_build(item, change.get("fields"), ctx, change, action)
    elif resource_kind in {"table_mapping", "join_mapping", "enum_meaning", "metric_definition", "mapping"}:
        build = _mapping_build(item, change.get("fields"), ctx, change, action, resource_kind)
    else:
        build = _generic_build(change.get("fields"), ctx, change, action, resource_kind)
    if build is not None and action == "update":
        _target_identity(build, resource_kind, _target_binding(ctx, change), ctx, change)
    return build


def _source_entry(
    request: Mapping[str, Any], ctx: _Context, change: Mapping[str, Any]
) -> dict[str, Any]:
    item_id = change.get("item_id")
    candidate_path = ctx.item_path(str(item_id)) if item_id is not None else None
    return {
        "change_id": str(change["change_id"]),
        "item_id": item_id,
        "resource_kind": change["resource_kind"],
        "action": change["action"],
        "artifact_ref": request.get("candidate_ref") if item_id is not None else None,
        "candidate_path": candidate_path,
        "json_pointer": candidate_path or f"/changes/{ctx.change_indices.get(str(change['change_id']), '?')}",
        "target_ref": deepcopy(change.get("target_ref")),
        "commands": [],
        "field_map": {},
        "reference_slots": {},
        "deferred_property_keys": [],
    }


def _compile_plan(
    request: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None,
    ontology_by_item: Mapping[str, str],
    resolve_binding: Callable[[Mapping[str, str]], Mapping[str, Any] | None],
    batch_max_items: int,
) -> dict[str, Any]:
    """Build the internal result before the public tuple/error boundary."""

    result: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "status": "rejected",
        "candidate": None,
        "batches": [],
        "source_map": {},
        "cross_batch_dependencies": [],
        "errors": [],
        "pending_changes": [],
    }
    if type(batch_max_items) is not int or batch_max_items < 1:
        result["errors"].append({"code": "invalid_batch_capacity", "change_id": None, "item_id": None, "field": "batch_max_items", "path": "/batch_max_items", "candidate_path": None, "message": "batch_max_items must be a positive integer", "retryable": True})
        return result
    ctx = _validate_request(request, candidate, ontology_by_item, resolve_binding, result)
    if ctx is None:
        return result
    result["candidate"] = {
        "schema_version": ctx.candidate.get("schema_version") if ctx.candidate else None,
        "candidate_id": ctx.candidate.get("candidate_id") if ctx.candidate else None,
        "revision": ctx.candidate.get("revision") if ctx.candidate else None,
        "candidate_ref": request.get("candidate_ref"),
    }
    # Keep one mutable entry per change while compiling.  The public source map
    # is keyed by both batch index and client item id after deterministic
    # batching; a candidate item can intentionally occur in more than one
    # command/batch.
    source_entries = {
        str(change["change_id"]): _source_entry(request, ctx, change)
        for change in ctx.changes
    }
    if ctx.errors:
        result["errors"] = ctx.errors
        result["pending_changes"] = [{"change_id": str(change["change_id"]), "item_id": change.get("item_id"), "reason": "request_rejected"} for change in ctx.changes]
        return result
    nodes: list[dict[str, Any]] = []
    for change in ctx.changes:
        ontology_id = _ontology(ctx, change)
        if ontology_id is None:
            ctx.error("scope_binding_required", "change has no trusted ontology mapping", change=change, field="item_id" if change.get("item_id") else "change_id", candidate_path=ctx.item_path(str(change.get("item_id"))) if change.get("item_id") else None)
            continue
        build = _compile_one(change, ctx)
        if build is not None:
            build.field_map = _normalize_field_map(build.field_map, ctx, change)
        if build is not None and not ctx.errors:
            nodes.append({"change": change, "build": build, "ontology_id": ontology_id})
            source = source_entries[str(change["change_id"])]
            source["field_map"] = deepcopy(build.field_map)
            source["reference_slots"] = deepcopy(build.reference_slots)
            source["deferred_property_keys"] = deepcopy(build.deferred_property_keys)
    if ctx.errors:
        result["errors"] = ctx.errors
        result["pending_changes"] = [{"change_id": str(change["change_id"]), "item_id": change.get("item_id"), "reason": "compile_rejected"} for change in ctx.changes]
        return result
    ordered = _topological_order(nodes, ctx)
    if ctx.errors:
        result["errors"] = ctx.errors
        result["pending_changes"] = [{"change_id": str(change["change_id"]), "item_id": change.get("item_id"), "reason": "dependency_rejected"} for change in ctx.changes]
        return result
    batches: list[dict[str, Any]] = []
    node_batch: dict[str, int] = {}
    node_client: dict[str, str] = {str(node["change"]["change_id"]): _change_client_id(node["change"]) for node in nodes}
    for node in ordered:
        change = node["change"]
        build = node["build"]
        change_id = str(change["change_id"])
        client_id = _change_client_id(change)
        ontology_id = node["ontology_id"]
        dependencies = set(build.dependencies)
        batch_index: int | None = None
        if batches:
            current = batches[-1]
            current_ids = {str(item["client_item_id"]) for item in current["items"]}
            deferred_dependency_same_batch = bool(build.deferred_property_keys) and any(
                dependency in node_batch and node_batch[dependency] == len(batches) - 1
                for dependency in dependencies
            )
            if (
                current["ontology_id"] == ontology_id
                and len(current["items"]) < batch_max_items
                and client_id not in current_ids
                and not deferred_dependency_same_batch
            ):
                batch_index = len(batches) - 1
        if batch_index is None:
            batch_index = len(batches)
            batches.append({"ontology_id": ontology_id, "items": []})
        same_batch_dependencies = sorted(
            node_client[dependency]
            for dependency in dependencies
            if dependency in node_batch and node_batch[dependency] == batch_index
        )
        cross_dependencies = sorted(
            dependency
            for dependency in dependencies
            if dependency in node_batch and node_batch[dependency] != batch_index
        )
        item = {
            "client_item_id": client_id,
            "change_id": change_id,
            "resource_kind": change["resource_kind"],
            "command_kind": build.command_kind,
            "payload": deepcopy(build.payload),
            "depends_on": same_batch_dependencies,
            "rationale": None,
            "competency_question_ids": [],
        }
        item_index = len(batches[batch_index]["items"])
        batches[batch_index]["items"].append(item)
        node_batch[change_id] = batch_index
        source = source_entries[change_id]
        command_map = {
            "batch_index": batch_index,
            "item_index": item_index,
            "client_item_id": client_id,
            "change_id": change_id,
            "command_kind": build.command_kind,
            "field_map": deepcopy(build.field_map),
            "reference_slots": deepcopy(build.reference_slots),
            "deferred_property_keys": deepcopy(build.deferred_property_keys),
        }
        source["commands"].append(command_map)
        source["batch_index"] = batch_index
        source["item_index"] = item_index
        source.setdefault("cross_batch_dependencies", [])
        for dependency in cross_dependencies:
            edge = {
                "batch_index": batch_index,
                "client_item_id": client_id,
                "depends_on": node_client[dependency],
                "depends_on_batch": node_batch[dependency],
            }
            result["cross_batch_dependencies"].append(edge)
            source["cross_batch_dependencies"].append(edge)
    source_map: dict[str, dict[str, Any]] = {}
    for entry in source_entries.values():
        batch_index = entry.get("batch_index")
        client_id = entry.get("item_id") or entry.get("change_id")
        if not isinstance(batch_index, int) or not _is_nonempty(client_id):
            continue
        # JSON object keys cannot be tuples.  The nested representation is the
        # JSON-safe form of the D9 ``(batch_index, client_item_id)`` key.
        source_map.setdefault(str(batch_index), {})[str(client_id)] = entry
    result["source_map"] = source_map
    result["batches"] = batches
    result["status"] = "ok"
    return result


def model_change_item_schema() -> dict[str, Any]:
    """Advertise the existing compiler input; the compiler remains its validator."""
    any_value = {"type": ["string", "integer", "number", "boolean", "array", "object", "null"]}
    keys = set().union(*_COMMAND_FIELDS.values()) | {"new_object_value", "new_object_is_iri"}
    fields = {key: deepcopy(any_value) for key in sorted(keys)}
    fields["semantic_definition"] = {
        "type": ["object", "null"], "additionalProperties": False,
        "properties": {
            key: ({"type": "array", "items": {"type": "string", "minLength": 1}}
                  if key in {"unknowns", "not_applicable", "conflicting_meanings"}
                  else {"type": "string", "minLength": 1})
            for key in _SEMANTIC_DEFINITION_FIELDS
        },
    }
    reference = {
        "type": ["object", "null"], "required": ["artifact_ref", "path"],
        "additionalProperties": False,
        "properties": {key: {"type": "string", "minLength": 1} for key in ["artifact_ref", "path"]},
        "description": "Copy an actual governed read/applied receipt reference; never guess its pointer.",
    }
    return {
        "type": "object", "additionalProperties": False,
        "required": sorted(_CHANGE_FIELDS),
        "properties": {
            "change_id": {"type": "string", "minLength": 1},
            "action": {"type": "string", "enum": sorted(_ACTIONS)},
            "resource_kind": {"type": "string", "enum": sorted(_RESOURCE_KINDS)},
            "item_id": {"type": ["string", "null"],
                        "description": "Candidate item_id, or null for fields-only changes. Not a platform ID."},
            "target_ref": reference,
            "fields": {
                "type": ["object", "null"], "properties": fields, "additionalProperties": False,
                "description": "Semantic fields only; supported keys depend on resource_kind/action. "
                    "Candidate selection uses fields=null; fields-only uses item_id=null. "
                    "Create uses target_ref=null; update/delete require an actual target_ref. "
                    "A concept definition uses class, name and semantic_definition; relation_type "
                    "uses name, source_class_id and target_class_id wrapping actual existing_resource_ref. "
                    "Keep change_id/action/resource_kind/item_id/target_ref outside fields.",
            },
        },
    }


def compile_model_changes(
    request: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None,
    ontology_by_item: Mapping[str, str],
    resolve_binding: Callable[[Mapping[str, str]], Mapping[str, Any] | None],
    batch_max_items: int = 100,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compile a request into ``(batches, source_map)``.

    ``ontology_by_item`` is the trusted scope projection.  Candidate changes
    use their ``item_id`` key; fields-only changes use their ``change_id`` key.
    ``resolve_binding`` is a verified Runner lookup for an exact
    ``{artifact_ref, path}``; the compiler never reads the referenced artifact.
    Repairable static gaps are raised as :class:`ModelChangeCompilationError`
    with the original request/candidate pointers in ``error.errors``.
    """

    result = _compile_plan(
        request,
        candidate=candidate,
        ontology_by_item=ontology_by_item,
        resolve_binding=resolve_binding,
        batch_max_items=batch_max_items,
    )
    if result["errors"]:
        raise ModelChangeCompilationError(result["errors"])
    return result["batches"], result["source_map"]

__all__ = [
    "REQUEST_SCHEMA",
    "PLAN_SCHEMA",
    "ModelChangeCompilationError",
    "compile_model_changes",
]
