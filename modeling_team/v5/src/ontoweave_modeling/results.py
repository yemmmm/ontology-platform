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

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.details = details


def decode_json_result(message: str, schema: dict) -> dict:
    """Read the unique schema-matching JSON value, retaining Agent text unchanged."""
    try:
        result = json.loads(message)
    except json.JSONDecodeError:
        decoder, position, matches, parsed = json.JSONDecoder(), 0, [], []
        first_error = None
        schema_errors = []
        while start := re.search(r"[\{\[]", message[position:]):
            position += start.start()
            try:
                candidate, end = decoder.raw_decode(message, position)
            except json.JSONDecodeError as error:
                if first_error is None:
                    first_error = {
                        "message": error.msg,
                        "line": error.lineno,
                        "column": error.colno,
                        "position": error.pos,
                    }
                position += 1
                continue
            position = end
            parsed.append(candidate)
            try:
                validate(instance=candidate, schema=schema)
            except ValidationError as error:
                if len(schema_errors) < 3:
                    path = "/".join(str(part) for part in error.absolute_path)
                    schema_errors.append(
                        {"path": "/" + path if path else "$", "message": error.message[:600]}
                    )
                continue
            if candidate not in matches:
                matches.append(candidate)
        if not matches and len(parsed) == 1:
            result = parsed[0]
        elif len(matches) != 1:
            details = (
                {"json_error": first_error} if first_error else {"matching_objects": len(matches)}
            )
            if not matches and schema_errors:
                details["schema_errors"] = schema_errors
            raise ResultContractError("result_json_missing_or_ambiguous", **details) from None
        else:
            result = matches[0]
    try:
        validate(instance=result, schema=schema)
    except ValidationError as exc:
        path = "/".join(str(part) for part in exc.absolute_path)
        raise ResultContractError(
            f"result_schema_invalid: {path or '$'}: {exc.message[:600]}"
        ) from None
    return result


def validate_evaluation_binding(report: dict, *, case_count: int, target_revision: int) -> None:
    """Check frozen coverage and identity; leave semantic judgments to the evaluator."""
    if report.get("target_revision") != target_revision:
        raise ResultContractError("evaluation_target_revision_mismatch")
    indices = [case["index"] for case in report["cases"]]
    if case_count <= 0 or sorted(indices) != list(range(1, case_count + 1)):
        raise ResultContractError("evaluation_case_coverage_mismatch")
    if report["verdict"] == "PASS" and not all(case["passed"] for case in report["cases"]):
        raise ResultContractError("evaluation_verdict_inconsistent")
