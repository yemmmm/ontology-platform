"""R4.0-003 annotations on ordinary semantic entities, never business execution.

Resource references belong in ordinary graph relations so the existing access
view can filter both endpoints. These annotations contain only local metadata.
"""

from __future__ import annotations

from typing import Any


def validate_action_annotation(field: str, value: Any) -> None:
    """Validate a complete replacement; null clears, omission is no information."""
    if value is None:
        return
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} must be a non-empty object or null")
    if field == "action_definition":
        allowed = {"input_status", "output_status"}
        enums = {key: {"defined", "none", "unknown"} for key in allowed}
        text_fields: set[str] = set()
    else:
        allowed = {
            "direction", "value_kind", "value_type", "required", "occurrence_condition",
            "cardinality", "unit", "enum_values", "missing_meaning", "result_kind",
        }
        enums = {
            "direction": {"input", "output", "unknown"},
            "value_kind": {"object_reference", "value", "unknown"},
            "cardinality": {"single", "collection", "unknown"},
            "result_kind": {"updated_input", "new_object", "computed_value", "unknown"},
        }
        text_fields = {"value_type", "occurrence_condition", "unit", "missing_meaning"}
    extra = set(value) - allowed
    if extra:
        raise ValueError(f"{field} contains unsupported fields: {', '.join(sorted(extra))}")
    for key, entry in value.items():
        if key in enums:
            valid = isinstance(entry, str) and entry in enums[key]
        elif key in text_fields:
            valid = entry is None or isinstance(entry, str) and bool(entry.strip())
        elif key == "required":
            valid = entry is None or isinstance(entry, bool)
        else:  # enum_values: explicit unknown or a confirmed scalar value list
            valid = entry is None or isinstance(entry, list) and all(
                isinstance(item, (str, int, float, bool)) or item is None for item in entry
            )
        if not valid:
            raise ValueError(f"{field}.{key} has an invalid value")
