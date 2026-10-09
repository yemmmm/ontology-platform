"""R4.3-008: read saved business annotations without inventing semantic content."""
from __future__ import annotations

import json
from typing import Any

DEFINITION_PREDICATES = {
    "semantic_definition": "semanticDefinition",
    "action_definition": "actionDefinition",
    "parameter_definition": "parameterDefinition",
}
DEFINITION_FIELDS = {
    "semantic_definition": (
        "semantic_role", "business_meaning", "applicability", "unknowns",
        "not_applicable", "conflicting_meanings",
    ),
    "action_definition": ("input_status", "output_status"),
    "parameter_definition": (
        "direction", "value_kind", "value_type", "required", "occurrence_condition",
        "cardinality", "unit", "enum_values", "missing_meaning", "result_kind",
    ),
}


def definition_text_fields(field: str, value: Any) -> list[tuple[str, str]]:
    """Project only contract fields; invalid JSON and unrecognized keys add no text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if not isinstance(value, dict):
        return []
    result = []
    for key in DEFINITION_FIELDS.get(field, ()):
        entries = value.get(key)
        entries = entries if isinstance(entries, list) else [entries]
        for entry in entries:
            if isinstance(entry, str) and entry.strip():
                result.append((f"{field}.{key}", entry))
            elif isinstance(entry, (int, float, bool)):
                result.append((f"{field}.{key}", json.dumps(entry)))
    return result
