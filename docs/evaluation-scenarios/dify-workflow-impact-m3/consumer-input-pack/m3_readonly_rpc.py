#!/usr/bin/env python3
"""Generic read-only M3 file-spool RPC client for the isolated consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Final


ID_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{7,63}$")
RECEIPT_KEYS: Final = {
    "run_tag",
    "request_id",
    "response_id",
    "canonical_request_sha256",
    "host_response_sha256",
    "status",
    "response_read_confirmed",
}
ALLOWED_GET_PATHS: Final = {
    "/openapi.json",
    "/api/health",
}
PROJECT_CONTEXT_RE: Final = re.compile(r"^/api/projects/[^/]+/build-context$")
ONTOLOGY_CONTEXT_RE: Final = re.compile(r"^/api/ontologies/[^/]+/modeling-context$")
READ_MODEL_RE: Final = re.compile(r"^/api/ontologies/[^/]+/semantic-read-models/.+$")


class RpcError(ValueError):
    """The consumer attempted an invalid or incomplete read-only RPC exchange."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_json(value: str, label: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise RpcError(f"{label} is not JSON") from error


def allowed_operation(method: str, path: str) -> bool:
    return (
        method == "GET"
        and (
            path in ALLOWED_GET_PATHS
            or PROJECT_CONTEXT_RE.fullmatch(path) is not None
            or ONTOLOGY_CONTEXT_RE.fullmatch(path) is not None
            or READ_MODEL_RE.fullmatch(path) is not None
        )
    ) or (
        method == "POST" and path == "/api/semantic/sparql:query"
    )


def normalized_headers(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        raise RpcError("headers must be a JSON string map")
    normalized = {key.lower(): item for key, item in value.items()}
    if len(normalized) != len(value) or set(normalized) - {"accept", "content-type"}:
        raise RpcError("headers contain a disallowed name")
    return normalized


def atomic_request_write(request_dir: Path, request_id: str, content: bytes) -> None:
    target = request_dir / f"{request_id}.json"
    if target.exists():
        raise RpcError("request ID already has a request file")
    temporary_dir = request_dir.parent / ".m3-readonly-rpc-tmp"
    temporary_dir.mkdir(mode=0o700, exist_ok=True)
    temporary = temporary_dir / f"{request_id}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, target)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise RpcError("could not atomically publish request") from error


def read_response(response_path: Path, request_id: str, timeout_seconds: float) -> tuple[bytes, dict[str, object]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            raw = response_path.read_bytes()
        except FileNotFoundError:
            time.sleep(0.05)
            continue
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RpcError("response is not UTF-8 JSON") from error
        if not isinstance(response, dict) or set(response) != {"id", "status", "headers", "body"}:
            raise RpcError("response keys do not match the RPC contract")
        if response.get("id") != request_id or not isinstance(response.get("status"), int):
            raise RpcError("response ID or status does not match the request")
        if not isinstance(response.get("headers"), dict):
            raise RpcError("response headers are not an object")
        return raw, response
    raise RpcError("timed out waiting for host response")


def append_receipt(receipt_path: Path, receipt: dict[str, object]) -> None:
    if set(receipt) != RECEIPT_KEYS:
        raise RpcError("receipt keys do not match the M3 receipt contract")
    line = canonical_json(receipt) + b"\n"
    descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def finalize_runtime_record(receipt_path: Path, runtime_path: Path, run_tag: str) -> str:
    try:
        raw_log = receipt_path.read_bytes()
    except OSError as error:
        raise RpcError("receipt log is unavailable for runtime finalization") from error
    receipts: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(raw_log.splitlines(), start=1):
        if not line:
            raise RpcError(f"receipt log has a blank line at {line_number}")
        try:
            receipt = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RpcError(f"receipt log has invalid JSON at {line_number}") from error
        request_id = receipt.get("request_id") if isinstance(receipt, dict) else None
        if (
            not isinstance(receipt, dict)
            or set(receipt) != RECEIPT_KEYS
            or line != canonical_json(receipt)
            or receipt.get("run_tag") != run_tag
            or not isinstance(request_id, str)
            or request_id in seen_ids
        ):
            raise RpcError(f"receipt log violates the M3 contract at {line_number}")
        seen_ids.add(request_id)
        receipts.append(receipt)
    record = {
        "run_tag": run_tag,
        "spool_receipt_log": {
            "path": receipt_path.name,
            "sha256": sha256_bytes(raw_log),
            "count": len(receipts),
        },
        "spool_receipts": receipts,
    }
    temporary = runtime_path.with_name(f".{runtime_path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    temporary.write_bytes(canonical_json(record))
    os.replace(temporary, runtime_path)
    return (
        f"M3_RECEIPT_SUMMARY run_tag={run_tag} receipt_count={len(receipts)} "
        f"receipt_log_sha256={record['spool_receipt_log']['sha256']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id")
    parser.add_argument("--method", choices=("GET", "POST"))
    parser.add_argument("--path")
    body = parser.add_mutually_exclusive_group()
    body.add_argument("--body-json")
    body.add_argument("--body-file", type=Path)
    parser.add_argument("--headers-json", default='{"accept":"application/json"}')
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--receipt-log", type=Path, default=Path("/mnt/spool-consumption-receipts.jsonl"))
    parser.add_argument("--runtime-record", type=Path, default=Path("/mnt/runtime-record.json"))
    parser.add_argument("--finalize-runtime-record", action="store_true")
    args = parser.parse_args()
    run_tag = os.environ.get("M3_RUN_TAG")
    if args.finalize_runtime_record:
        if args.id or args.method or args.path or args.body_json or args.body_file:
            raise SystemExit("runtime finalization does not accept an RPC operation")
        if not run_tag:
            raise SystemExit("M3 run tag must be supplied by the launcher")
        print(finalize_runtime_record(args.receipt_log, args.runtime_record, run_tag))
        return 0
    if not args.id or not args.method or not args.path:
        raise SystemExit("--id, --method and --path are required for an RPC operation")
    if not ID_RE.fullmatch(args.id):
        raise SystemExit("--id must match ^[a-z][a-z0-9_-]{7,63}$")
    if args.timeout_seconds <= 0 or not allowed_operation(args.method, args.path):
        raise SystemExit("operation is outside the read-only consumer contract")
    body_text = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body_json
    body_value = None if body_text is None else parse_json(body_text, "body")
    headers = normalized_headers(parse_json(args.headers_json, "headers"))
    request = {"id": args.id, "method": args.method, "path": args.path, "headers": headers, "body": body_value}
    request_bytes = canonical_json(request)
    request_dir_text = os.environ.get("M3_API_REQUEST_DIR")
    response_dir_text = os.environ.get("M3_API_RESPONSE_DIR")
    if not request_dir_text or not response_dir_text or not run_tag:
        raise SystemExit("M3 request/response directories and run tag must be supplied by the launcher")
    request_dir, response_dir = Path(request_dir_text), Path(response_dir_text)
    if not request_dir.is_dir() or not response_dir.is_dir():
        raise SystemExit("M3 request/response directories and run tag must be supplied by the launcher")
    atomic_request_write(request_dir, args.id, request_bytes)
    raw_response, response = read_response(response_dir / f"{args.id}.json", args.id, args.timeout_seconds)
    append_receipt(
        args.receipt_log,
        {
            "run_tag": run_tag,
            "request_id": args.id,
            "response_id": args.id,
            "canonical_request_sha256": sha256_bytes(request_bytes),
            "host_response_sha256": sha256_bytes(raw_response),
            "status": response["status"],
            "response_read_confirmed": True,
        },
    )
    print(canonical_json(response).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
