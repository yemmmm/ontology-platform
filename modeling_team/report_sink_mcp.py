"""Child-local MCP write-only Examiner report sink bridge.

The child may submit exactly six semantic fields.  Runner-owned task, ticket,
session, source, and model-state bindings are deliberately not present in the
published schema and are added only by the Host callback behind the private
socket.  The same shape check is repeated here so a model cannot bypass it by
writing directly to the Unix socket.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Mapping


SEMANTIC_FIELDS = [
    "answerability",
    "conclusion",
    "evidence",
    "coverage",
    "gaps",
    "evidence_refs",
]
PLATFORM_LOCATOR_FIELDS = [
    "ref_id",
    "tool",
    "request_digest",
    "response_digest",
    "artifact_path",
    "page",
]
PAGE_FIELDS = ["ordinal", "input_cursor", "output_cursor", "has_more", "sequence_complete"]


def report_schema(kind: str) -> dict[str, Any]:
    """Return the strict, non-secret input schema for one Examiner kind."""

    if kind == "acceptance":
        fields = ["status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"]
        return {
            "type": "object",
            "required": fields,
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
                "answer": {"type": "string", "minLength": 1},
                "evidence_ref_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "current": {"type": "boolean"},
                "usable": {"type": "boolean"},
                "failure_layer": {"type": ["string", "null"]},
                "blocked_reason": {"type": ["string", "null"]},
            },
            "description": "Strict fresh Acceptance typed verdict payload.",
        }
    if kind not in {"source", "platform"}:
        raise ValueError("invalid Examiner kind")
    if kind == "source":
        evidence_ref = {
            "type": "object",
            "required": ["location"],
            "additionalProperties": False,
            "properties": {
                "location": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Approved-source location only; the Host supplies ref_id and digests.",
                }
            },
        }
    else:
        evidence_ref = {
            "type": "object",
            "required": PLATFORM_LOCATOR_FIELDS,
            "additionalProperties": False,
            "properties": {
                "ref_id": {"type": "string", "minLength": 1},
                "tool": {"type": "string", "minLength": 1},
                "request_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "response_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "artifact_path": {"type": "string", "minLength": 1},
                "page": {
                    "type": "object",
                    "required": PAGE_FIELDS,
                    "additionalProperties": False,
                    "properties": {
                        "ordinal": {"type": "integer", "minimum": 0},
                        "input_cursor": {"type": ["string", "null"]},
                        "output_cursor": {"type": ["string", "null"]},
                        "has_more": {"type": "boolean"},
                        "sequence_complete": {"type": "boolean"},
                    },
                },
            },
        }
    return {
        "type": "object",
        "required": SEMANTIC_FIELDS,
        "additionalProperties": False,
        "properties": {
            "answerability": {
                "type": "string",
                "enum": ["answerable", "insufficient-evidence", "unavailable"],
            },
            "conclusion": {"type": "string", "minLength": 1},
            "evidence": {"type": "array"},
            "coverage": {
                "type": "object",
                "required": ["queries_or_sections", "complete"],
                "additionalProperties": False,
                "properties": {
                    "queries_or_sections": {"type": "array", "items": {"type": "string"}},
                    "complete": {"type": "boolean"},
                },
            },
            "gaps": {"type": "array"},
            "evidence_refs": {"type": "array", "minItems": 1, "items": evidence_ref},
        },
        "description": (
            f"Strict {kind} Examiner semantic payload. Submit no Runner bindings, "
            "ticket/session fields, model_state, source_bundle_digest, or report_digest."
        ),
    }


def _validate_payload(value: Any, *, kind: str) -> dict[str, Any]:
    if kind == "acceptance":
        expected = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("acceptance verdict fields drift")
        if value["status"] not in {"PASS", "FAIL", "BLOCKED"} or not isinstance(value["answer"], str) or not value["answer"]:
            raise ValueError("acceptance verdict is invalid")
        if not isinstance(value["evidence_ref_ids"], list) or any(not isinstance(item, str) or not item for item in value["evidence_ref_ids"]):
            raise ValueError("acceptance verdict evidence refs are invalid")
        if not isinstance(value["current"], bool) or not isinstance(value["usable"], bool):
            raise ValueError("acceptance verdict flags are invalid")
        return dict(value)
    if not isinstance(value, Mapping) or set(value) != set(SEMANTIC_FIELDS):
        raise ValueError("report payload fields drift")
    if value["answerability"] not in {"answerable", "insufficient-evidence", "unavailable"}:
        raise ValueError("report answerability is invalid")
    if not isinstance(value["conclusion"], str) or not value["conclusion"]:
        raise ValueError("report conclusion is invalid")
    if not isinstance(value["evidence"], list) or not isinstance(value["gaps"], list):
        raise ValueError("report evidence/gaps are invalid")
    coverage = value["coverage"]
    if (
        not isinstance(coverage, Mapping)
        or set(coverage) != {"queries_or_sections", "complete"}
        or not isinstance(coverage["queries_or_sections"], list)
        or not isinstance(coverage["complete"], bool)
    ):
        raise ValueError("report coverage is invalid")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("report evidence_refs are invalid")
    for ref in refs:
        if not isinstance(ref, Mapping):
            raise ValueError("report evidence locator is invalid")
        if kind == "source":
            if set(ref) != {"location"} or not isinstance(ref["location"], str) or not ref["location"]:
                raise ValueError("source evidence locator is invalid")
            path = ref["location"].split("#", 1)[0]
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("source evidence locator path is invalid")
        else:
            if set(ref) != set(PLATFORM_LOCATOR_FIELDS):
                raise ValueError("platform evidence locator fields drift")
            if not isinstance(ref["ref_id"], str) or not ref["ref_id"]:
                raise ValueError("platform evidence locator ref_id is invalid")
            if not isinstance(ref["tool"], str) or not ref["tool"]:
                raise ValueError("platform evidence locator tool is invalid")
            for field in ("request_digest", "response_digest"):
                digest = ref[field]
                if not isinstance(digest, str) or len(digest) != 64 or any(
                    char not in "0123456789abcdef" for char in digest
                ):
                    raise ValueError(f"platform evidence locator {field} is invalid")
            path = ref["artifact_path"]
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("platform evidence locator path is invalid")
            page = ref["page"]
            if not isinstance(page, Mapping) or set(page) != set(PAGE_FIELDS):
                raise ValueError("platform evidence locator page is invalid")
            if not isinstance(page["ordinal"], int) or page["ordinal"] < 0:
                raise ValueError("platform evidence locator page ordinal is invalid")
            if not isinstance(page["input_cursor"], (str, type(None))) or not isinstance(
                page["output_cursor"], (str, type(None))
            ):
                raise ValueError("platform evidence locator page cursors are invalid")
            if not isinstance(page["has_more"], bool) or not isinstance(
                page["sequence_complete"], bool
            ):
                raise ValueError("platform evidence locator page flags are invalid")
            if page["has_more"] and page["sequence_complete"]:
                raise ValueError("platform evidence locator page is incomplete and complete")
    return dict(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--kind", choices=("source", "platform", "acceptance"), required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()
    try:
        token = open(args.token_file, encoding="utf-8").read().strip()
    except OSError:
        return 2
    for line in sys.stdin:
        request: Any = None
        try:
            request = json.loads(line)
            request_id = request.get("id") if isinstance(request, dict) else None
            method = request.get("method") if isinstance(request, dict) else None
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "examiner_report", "version": "1"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "submit_examiner_report",
                            "description": f"submit one strict {args.kind} semantic report",
                            "inputSchema": report_schema(args.kind),
                        }
                    ]
                }
            elif method == "tools/call":
                params = request.get("params", {})
                if not isinstance(params, Mapping) or params.get("name") != "submit_examiner_report":
                    raise RuntimeError("report-tool-denied")
                arguments = _validate_payload(params.get("arguments"), kind=args.kind)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(5)
                    client.connect(args.socket)
                    client.sendall(
                        (_json({"token": token, "report": arguments})).encode("utf-8")
                    )
                    response = json.loads(client.recv(65536).decode("utf-8"))
                if not response.get("ok"):
                    raise RuntimeError(str(response.get("code", "report-rejected")))
                result = {"content": [{"type": "text", "text": "report-submitted"}], "isError": False}
            else:
                raise RuntimeError("report-method-denied")
            print(_json({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
        except Exception as exc:
            request_id = request.get("id") if isinstance(request, dict) else None
            print(
                _json(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": str(exc)},
                    }
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
