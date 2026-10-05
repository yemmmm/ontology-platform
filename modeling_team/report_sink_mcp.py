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

# v3 batch branch (R3.0-011): selected by report schema, never by a new kind.
# The child-side check repeats only the per-question field shape so a model
# cannot bypass it by writing to the socket directly; batch identity, question
# order, and completeness stay Host-side (the sink's batch contract).
CQ_BATCH_REPORT_SCHEMA = "r3-0-011-acceptance-batch-report/v1"
CQ_EXAMINER_STATUSES = ("completed", "unanswered", "runtime-incomplete")
# Exact projection of competency_questions.CQ_VERDICT_STATES: this bridge runs
# standalone in the child namespace and cannot import the host package.  A
# non-pass verdict names why the answer was insufficient; there is no bare
# "fail" state in the canonical contract.
CQ_VERDICT_STATES = (
    "pass",
    "model-recall-insufficient",
    "question-answer-review",
    "platform-runtime-incomplete",
)
CQ_FAILURE_LAYERS = (
    "modeling-quality",
    "platform-contract",
    "collaboration/routing",
    "runtime/infrastructure",
)
# Judge verdicts whose canonical ``failure_layer`` is empty.  The wire accepts
# an omitted ``failure_layer`` for exactly these verdicts (and for every
# Platform Examiner status, where ``None`` is always legal) and normalizes it
# to ``None``; every other state still has to name one of ``CQ_FAILURE_LAYERS``.
# 2026-10-05 public judge report-contract failure: across 49 submissions the
# then-only advertised empty spelling (literal JSON null in a required
# property) never appeared -- the key was dropped or the string "None" was
# sent -- so the session ended on an unsubmitted empty spelling, not on the
# verdict.
CQ_EMPTY_LAYER_VERDICTS = ("pass", "question-answer-review")
BATCH_EXAMINER_FIELDS = [
    "schema_version",
    "batch_id",
    "question_id",
    "question_content_version",
    "answer",
    "evidence_refs",
    "explicit_unknown",
    "status",
    "failure_layer",
    "reason",
]
BATCH_VERDICT_FIELDS = [
    "schema_version",
    "batch_id",
    "question_id",
    "verdict",
    "failure_layer",
    "conflicting_evidence",
    "note",
]


def _validate_batch_payload(
    value: Any, *, kind: str, batch_id: str, question_ids: list[str], role: str
) -> dict[str, Any]:
    """Validate one v3 per-question report entry (platform or judge spelling)."""

    if kind not in {"platform", "acceptance"}:
        raise ValueError("v3 batch report sink kind is invalid")
    # ``role`` is the session role spelling; ``kind`` is the sink kind spelling.
    expected_platform = role == "platform-examiner"
    if (kind == "platform") is not expected_platform:
        raise ValueError("v3 batch report role does not match the sink kind")
    fields = BATCH_EXAMINER_FIELDS if expected_platform else BATCH_VERDICT_FIELDS
    if not isinstance(value, Mapping):
        raise ValueError("v3 batch report fields drift")
    # The wire accepts an omitted ``failure_layer`` only where the canonical
    # value is empty (judge pass/question-answer-review, any examiner status)
    # and normalizes it to ``None``: the Host-side verdict semantics stay the
    # sole enforcement of which state may carry an empty layer.
    layer_optional = expected_platform or value.get("verdict") in CQ_EMPTY_LAYER_VERDICTS
    optional_fields = set(fields) - {"failure_layer"} if layer_optional else set(fields)
    if set(value) not in (set(fields), optional_fields):
        missing = set(fields) - set(value)
        if missing == {"failure_layer"}:
            raise ValueError(
                "v3 batch report failure_layer is required for verdict "
                f"{value.get('verdict')!r}: set it to one of {list(CQ_FAILURE_LAYERS)}"
            )
        raise ValueError("v3 batch report fields drift")
    if "failure_layer" not in value:
        value = {**value, "failure_layer": None}
    if value["schema_version"] != CQ_BATCH_REPORT_SCHEMA:
        raise ValueError("v3 batch report schema is invalid")
    if not isinstance(value["batch_id"], str) or not value["batch_id"]:
        raise ValueError("v3 batch report batch_id is invalid")
    if value["batch_id"] != batch_id:
        raise ValueError("v3 batch report is bound to another batch")
    question_id = value["question_id"]
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("v3 batch report question_id is invalid")
    if question_ids and question_id not in question_ids:
        raise ValueError("v3 batch report question is not in the frozen batch")
    if expected_platform:
        version = value["question_content_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("v3 batch report question_content_version is invalid")
        if not isinstance(value["answer"], str) or not value["answer"]:
            raise ValueError("v3 batch report answer is invalid")
        refs = value["evidence_refs"]
        if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
            raise ValueError("v3 batch report evidence_refs are invalid")
        if not isinstance(value["explicit_unknown"], list):
            raise ValueError("v3 batch report explicit_unknown is invalid")
        if value["status"] not in CQ_EXAMINER_STATUSES:
            raise ValueError("v3 batch report status is invalid")
    else:
        if value["verdict"] not in CQ_VERDICT_STATES:
            raise ValueError("v3 batch report verdict is invalid")
        if not isinstance(value["conflicting_evidence"], list):
            raise ValueError("v3 batch report conflicting_evidence is invalid")
        if not isinstance(value["note"], str) or not value["note"]:
            raise ValueError("v3 batch report note is invalid")
    layer = value["failure_layer"]
    if layer is not None and layer not in CQ_FAILURE_LAYERS:
        raise ValueError(
            "v3 batch report failure_layer is invalid: use JSON null or omit "
            "the field when the layer is empty (pass/question-answer-review), "
            f"never a string such as {layer!r}; otherwise one of "
            f"{list(CQ_FAILURE_LAYERS)}"
        )
    return dict(value)


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
                # Digest transcription is verified and canonicalized Host-side
                # against the proxy receipt; a hand-copied typo must not end
                # the round here (R2.3-009 examiner diagnosis, 2026-08-21).
                "request_digest": {"type": "string", "minLength": 1},
                "response_digest": {"type": "string", "minLength": 1},
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
                # Non-empty only: the Host sink matches the locator to the
                # proxy receipt and stamps the canonical digests, so a single
                # transcribed character must not reject the whole report.
                if not isinstance(digest, str) or not digest:
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


def _v3_batch_report_schema(*, platform: bool) -> dict[str, Any]:
    """Advertised schema for the selected v3 batch branch (``--schema``).

    ``tools/list`` must describe the branch the sink actually validates, so a
    child that lists tools before submitting sees the same per-question field
    set the Host enforces.  Batch identity, question order and completeness stay
    Host-side and are therefore not part of the per-call schema.
    """

    def _text(name: str) -> dict[str, Any]:
        return {"type": "string", "minLength": 1}

    properties: dict[str, Any] = {
        "schema_version": {"type": "string", "const": CQ_BATCH_REPORT_SCHEMA},
        "batch_id": _text("batch_id"),
        "question_id": _text("question_id"),
        "failure_layer": {
            "type": ["string", "null"],
            "enum": [*CQ_FAILURE_LAYERS, None],
            "description": (
                "Failure layer, or an empty layer as the JSON null value or an "
                "omitted field (judge: only verdict pass and question-answer-review "
                "may be empty; model-recall-insufficient and "
                "platform-runtime-incomplete name one of the enum layers). "
                "Never send a string such as \"None\" or \"\"."
            ),
        },
    }
    # ``failure_layer`` stays deliberately out of ``required``: the omitted
    # spelling keeps an empty layer submittable on tool paths where the
    # explicit null spelling did not arrive (2026-10-05: no literal null in
    # the observed 49 submissions); the sink canonicalizes an omitted empty
    # layer to ``None``.
    required = ["schema_version", "batch_id", "question_id"]
    if platform:
        properties.update(
            {
                "question_content_version": {"type": "integer", "minimum": 1},
                "answer": {"type": "string", "minLength": 1},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "explicit_unknown": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": list(CQ_EXAMINER_STATUSES)},
                "reason": _text("reason"),
            }
        )
        required += [
            "question_content_version",
            "answer",
            "evidence_refs",
            "explicit_unknown",
            "status",
            "reason",
        ]
    else:
        properties.update(
            {
                "verdict": {"type": "string", "enum": list(CQ_VERDICT_STATES)},
                "conflicting_evidence": {"type": "array", "items": {"type": "string"}},
                "note": {"type": "string", "minLength": 1},
            }
        )
        required += ["verdict", "conflicting_evidence", "note"]
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
        "description": (
            "Strict R3.0-011 v3 per-question Platform Examiner batch report "
            "(one call per question, packet order)."
            if platform
            else "Strict R3.0-011 v3 per-question Acceptance judge verdict (one call per question)."
        ),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--kind", choices=("source", "platform", "acceptance"), required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument(
        "--schema",
        choices=(CQ_BATCH_REPORT_SCHEMA,),
        default=None,
        help="select the v3 batch report branch (platform/acceptance only)",
    )
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--role", choices=("platform-examiner", "acceptance"), default=None)
    parser.add_argument(
        "--question-ids",
        default="",
        help="comma-separated frozen batch question order (advisory, Host-enforced)",
    )
    args = parser.parse_args()
    if args.schema is not None and args.role is None:
        parser.error("--schema requires --role")
    try:
        token = open(args.token_file, encoding="utf-8").read().strip()
    except OSError:
        return 2
    question_ids = [item for item in args.question_ids.split(",") if item]
    v3_batch = args.schema is not None
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
                if v3_batch:
                    advertised = _v3_batch_report_schema(
                        platform=args.role == "platform-examiner"
                    )
                else:
                    advertised = report_schema(args.kind)
                result = {
                    "tools": [
                        {
                            "name": "submit_examiner_report",
                            "description": f"submit one strict {args.kind} semantic report",
                            "inputSchema": advertised,
                        }
                    ]
                }
            elif method == "tools/call":
                params = request.get("params", {})
                if not isinstance(params, Mapping) or params.get("name") != "submit_examiner_report":
                    raise RuntimeError("report-tool-denied")
                if args.schema is not None:
                    arguments = _validate_batch_payload(
                        params.get("arguments"),
                        kind=args.kind,
                        batch_id=args.batch_id,
                        question_ids=question_ids,
                        role=args.role,
                    )
                else:
                    arguments = _validate_payload(params.get("arguments"), kind=args.kind)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(5)
                    client.connect(args.socket)
                    client.sendall(
                        (_json({"token": token, "report": arguments})).encode("utf-8")
                    )
                    response = json.loads(client.recv(65536).decode("utf-8"))
                if not response.get("ok"):
                    code = str(response.get("code", "report-rejected"))
                    detail = str(response.get("detail", ""))
                    remaining = response.get("attempts_remaining")
                    message = f"report rejected: {code}"
                    if detail:
                        message += f"; {detail}"
                    if isinstance(remaining, int):
                        message += f"; attempts_remaining={remaining}"
                    raise RuntimeError(message)
                result = {"content": [{"type": "text", "text": "report-submitted"}], "isError": False}
            else:
                raise RuntimeError("report-method-denied")
            print(_json({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
        except Exception as exc:
            request_id = request.get("id") if isinstance(request, dict) else None
            # Codex surfaces JSON-RPC tool errors as the generic "user rejected
            # MCP tool call" and drops the detail.  Return an MCP tool result
            # with ``isError`` so the child can read the exact rejection reason
            # and repair the payload in its next inference.
            if method == "tools/call":
                print(
                    _json(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [{"type": "text", "text": str(exc)}],
                                "isError": True,
                            },
                        }
                    ),
                    flush=True,
                )
            else:
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
