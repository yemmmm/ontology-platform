"""Independent, task-scoped stdio MCP overlay for the Round71 P2a driver."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

try:
    from .p2a_batch_plan import (
        P2ABatchPlanError,
        P2A_TASK_ID,
        build_p2a_batch_plan,
        validate_overlay_contract,
        verify_p2a_dry_run_evidence_projection,
    )
except ImportError:  # pragma: no cover - exercised by the private /opt MCP mount
    from p2a_batch_plan import (  # type: ignore[no-redef]
        P2ABatchPlanError,
        P2A_TASK_ID,
        build_p2a_batch_plan,
        validate_overlay_contract,
        verify_p2a_dry_run_evidence_projection,
    )


SERVER_NAME = "p2a_protocol_overlay"
BUILD_TOOL = "build_p2a_batch_plan"
VERIFY_TOOL = "verify_p2a_dry_run_evidence_projection"
CONTRACT_PATH = Path("/opt/p2a-overlay-contract.json")
RUN_ID_ENV = "P2A_RUNTIME_RUN_ID"
TASK_ID_ENV = "P2A_RUNTIME_TASK_ID"
CONTRACT_DIGEST_ENV = "P2A_OVERLAY_CONTRACT_DIGEST"


class P2AOverlayError(RuntimeError):
    """The P2a-only overlay runtime authorization is unavailable or drifted."""


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _read_immutable(path: Path, name: str, expected_mode: int = 0o444) -> bytes:
    descriptor = -1
    try:
        flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise P2AOverlayError(f"{name} metadata is invalid")
        payload = bytearray()
        while chunk := os.read(descriptor, 65536):
            payload.extend(chunk)
        return bytes(payload)
    except P2AOverlayError:
        raise
    except OSError as exc:
        raise P2AOverlayError(f"{name} is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _authorized_context() -> tuple[str, dict[str, Any]]:
    run_id = os.environ.get(RUN_ID_ENV)
    task_id = os.environ.get(TASK_ID_ENV)
    expected_digest = os.environ.get(CONTRACT_DIGEST_ENV)
    if not run_id or task_id != P2A_TASK_ID or not expected_digest:
        raise P2AOverlayError("P2a overlay Host context is unavailable")
    raw = _read_immutable(CONTRACT_PATH, "P2a overlay contract")
    try:
        contract = json.loads(raw.decode("utf-8"))
        contract = validate_overlay_contract(
            contract,
            expected_run_id=run_id,
            expected_task_id=task_id,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, P2ABatchPlanError, TypeError) as exc:
        raise P2AOverlayError("P2a overlay contract is invalid") from exc
    if contract["contract_digest"] != expected_digest:
        raise P2AOverlayError("P2a overlay contract digest drifts from Host context")
    for asset in contract["assets"]:
        payload = _read_immutable(
            Path(asset["mount_path"]),
            "P2a overlay asset",
            int(asset["mode"], 8),
        )
        if hashlib.sha256(payload).hexdigest() != asset["sha256"]:
            raise P2AOverlayError("P2a overlay asset digest drifts")
    return run_id, contract


def _object_schema(description: str) -> dict[str, Any]:
    return {"type": "object", "description": description}


def _build_tool() -> dict[str, Any]:
    return {
        "name": BUILD_TOOL,
        "description": (
            "Compile the frozen P2a candidate, candidate-item Evidence map, and exact candidate "
            "receipt into the only authorized four-item Batch plan."
        ),
        "inputSchema": {
            "type": "object",
            "required": [
                "candidate",
                "candidate_item_evidence_map",
                "candidate_receipt",
            ],
            "additionalProperties": False,
            "properties": {
                "candidate": _object_schema("Complete frozen v2 candidate."),
                "candidate_item_evidence_map": _object_schema(
                    "Run-bound candidate item Evidence map."
                ),
                "candidate_receipt": _object_schema("Exact candidate receipt."),
            },
        },
    }


def _verify_tool() -> dict[str, Any]:
    return {
        "name": VERIFY_TOOL,
        "description": (
            "Verify the formal dry-run receipt and two authorized detail reads, project each "
            "4-field public Evidence row to the canonical 3-field proof row, enforce a global "
            "identity/dedupe bijection, and optionally bind post-apply Evidence IDs."
        ),
        "inputSchema": {
            "type": "object",
            "required": [
                "candidate",
                "candidate_item_evidence_map",
                "dry_run_receipt",
                "detail_read_1",
                "detail_read_2",
            ],
            "additionalProperties": False,
            "properties": {
                "candidate": _object_schema("Complete frozen v2 candidate."),
                "candidate_item_evidence_map": _object_schema(
                    "Run-bound candidate item Evidence map."
                ),
                "dry_run_receipt": _object_schema("Formal dry-run submit receipt."),
                "detail_read_1": _object_schema("First authorized Batch detail read."),
                "detail_read_2": _object_schema("Second authorized Batch detail read."),
                "postapply_evidence_bindings": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
    }


def _structured(request_id: Any, value: dict[str, Any]) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(value, ensure_ascii=False, sort_keys=True),
                }
            ],
            "structuredContent": value,
        },
    )


def handle(request: object) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _error(None, -32600, "invalid request")
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if method == "notifications/initialized":
        return None
    try:
        run_id, _contract = _authorized_context()
    except P2AOverlayError as exc:
        return _error(request_id, -32020, f"P2a overlay authorization failed: {exc}")
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "1"},
            },
        )
    if method == "tools/list":
        return _result(request_id, {"tools": [_build_tool(), _verify_tool()]})
    if method != "tools/call" or not isinstance(params, dict):
        return _error(request_id, -32601, "method or tool is unavailable")
    arguments = params.get("arguments")
    tool_name = params.get("name")
    if tool_name == BUILD_TOOL:
        expected = {"candidate", "candidate_item_evidence_map", "candidate_receipt"}
        if not isinstance(arguments, dict) or set(arguments) != expected:
            return _error(request_id, -32602, "P2a plan arguments drift")
        try:
            value = build_p2a_batch_plan(
                arguments["candidate"],
                arguments["candidate_item_evidence_map"],
                arguments["candidate_receipt"],
                expected_run_id=run_id,
            )
        except (P2ABatchPlanError, TypeError, ValueError) as exc:
            return _error(request_id, -32021, f"P2a Batch planning failed: {exc}")
        return _structured(request_id, value)
    if tool_name == VERIFY_TOOL:
        required = {
            "candidate",
            "candidate_item_evidence_map",
            "dry_run_receipt",
            "detail_read_1",
            "detail_read_2",
        }
        allowed = required | {"postapply_evidence_bindings"}
        if not isinstance(arguments, dict) or not required.issubset(arguments) or not set(
            arguments
        ).issubset(allowed):
            return _error(request_id, -32602, "P2a projection arguments drift")
        try:
            value = verify_p2a_dry_run_evidence_projection(
                arguments["candidate"],
                arguments["candidate_item_evidence_map"],
                arguments["dry_run_receipt"],
                arguments["detail_read_1"],
                arguments["detail_read_2"],
                expected_run_id=run_id,
                postapply_evidence_bindings=arguments.get("postapply_evidence_bindings"),
            )
        except (P2ABatchPlanError, TypeError, ValueError) as exc:
            return _error(request_id, -32022, f"P2a projection verification failed: {exc}")
        return _structured(request_id, value)
    return _error(request_id, -32601, "method or tool is unavailable")


def main() -> int:
    for line in sys.stdin:
        try:
            response = handle(json.loads(line))
        except json.JSONDecodeError:
            response = _error(None, -32700, "parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
