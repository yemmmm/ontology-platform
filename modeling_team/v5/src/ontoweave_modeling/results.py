"""Validate a returned JSON object without repairing or inventing its content."""

from __future__ import annotations

import json
import re

from jsonschema import ValidationError, validate

MATERIAL_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "propositions": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "source_refs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["propositions", "unknowns", "source_refs"],
}


class ResultContractError(ValueError):
    """A recoverable result-format error; the original response remains evidence."""


def decode_json_result(message: str, schema: dict) -> dict:
    """Accept bare JSON or one explicit JSON block, then validate the given schema."""
    try:
        result = json.loads(message)
    except json.JSONDecodeError:
        blocks = re.findall(r"^```json\s*\n(.*?)^```\s*$", message, flags=re.MULTILINE | re.DOTALL)
        if len(blocks) != 1:
            raise ResultContractError("result_json_missing_or_ambiguous") from None
        try:
            result = json.loads(blocks[0])
        except json.JSONDecodeError:
            raise ResultContractError("result_json_invalid") from None
    try:
        validate(instance=result, schema=schema)
    except ValidationError as exc:
        path = "/".join(str(part) for part in exc.absolute_path)
        raise ResultContractError(f"result_schema_invalid: {path}") from None
    return result
