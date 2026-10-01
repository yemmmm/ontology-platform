"""Stored business rule declarations; never evaluate or execute their scripts."""

from typing import Any


def validate_rule_annotation(value: Any) -> None:
    """Validate local metadata only; references remain ordinary governed edges.

    Omission carries no information, null clears the annotation. Partial
    declarations are legal and do not establish an executable business rule.
    """
    if value is None:
        return
    if not isinstance(value, dict) or not value:
        raise ValueError("rule_definition must be a non-empty object or null")
    enums = {
        "kind": {"judgment_constraint", "derivation"},
        "input_status": {"defined", "none", "unknown"},
        "output_status": {"defined", "none", "unknown"},
    }
    text_fields = {
        "script_language", "script_version", "script_source", "execution_environment",
        "missing_policy", "change_note",
    }
    extra = set(value) - (set(enums) | text_fields)
    if extra:
        raise ValueError(f"rule_definition contains unsupported fields: {', '.join(sorted(extra))}")
    for key, entry in value.items():
        if key in enums:
            valid = isinstance(entry, str) and entry in enums[key]
        else:
            valid = entry is None or isinstance(entry, str) and bool(entry.strip())
        if not valid:
            raise ValueError(f"rule_definition.{key} has an invalid value")
