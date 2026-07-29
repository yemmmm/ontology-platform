#!/usr/bin/env python3
"""Publish one generic API spool candidate without exposing spool mechanics to the Agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
EXACT_KEYS = {"id", "method", "path", "headers", "body"}
MAX_BYTES = 1024 * 1024


class SpoolError(ValueError):
    """The Agent candidate cannot safely enter the Host-owned spool."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SpoolError("duplicate JSON key")
        result[key] = value
    return result


def strip_one_final_line_ending(raw: bytes) -> bytes:
    if raw.endswith(b"\r\n"):
        return raw[:-2]
    if raw.endswith(b"\n"):
        return raw[:-1]
    return raw


def read_regular(path: Path, *, limit: int = MAX_BYTES) -> bytes:
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > limit:
        raise SpoolError("candidate or response is not a safe regular file")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise SpoolError("candidate or response exceeds byte limit")
    return raw


def parse_candidate(raw: bytes) -> tuple[dict[str, object], bytes]:
    try:
        value = json.loads(
            strip_one_final_line_ending(raw).decode("utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpoolError("candidate is not strict UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != EXACT_KEYS:
        raise SpoolError("candidate keys do not match the generic API envelope")
    request_id, method, path, headers = (
        value["id"],
        value["method"],
        value["path"],
        value["headers"],
    )
    if not isinstance(request_id, str) or not ID_RE.fullmatch(request_id):
        raise SpoolError("candidate ID is invalid")
    if not isinstance(method, str) or not isinstance(path, str):
        raise SpoolError("candidate method and path must be strings")
    if not isinstance(headers, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in headers.items()
    ):
        raise SpoolError("candidate headers must be a string map")
    normalized = {key.lower(): item for key, item in headers.items()}
    if len(normalized) != len(headers) or "authorization" in normalized:
        raise SpoolError("candidate must not carry Authorization")
    canonical = canonical_json(
        {"id": request_id, "method": method, "path": path, "headers": normalized, "body": value["body"]}
    )
    return json.loads(canonical), canonical


def atomic_publish(directory: Path, filename: str, content: bytes) -> Path:
    target = directory / filename
    if target.exists() or target.is_symlink():
        raise SpoolError("matching request already exists")
    temporary = directory / f".{filename}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(temporary, target, follow_symlinks=False)
    except FileExistsError as error:
        raise SpoolError("matching request was created concurrently") from error
    finally:
        temporary.unlink(missing_ok=True)
    os.chmod(target, 0o400)
    return target


def wait_response(path: Path, request_id: str, timeout_seconds: float) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists() or path.is_symlink():
            raw = read_regular(path)
            try:
                response = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SpoolError("matching response is not strict UTF-8 JSON") from error
            if not isinstance(response, dict) or response.get("id") != request_id:
                raise SpoolError("matching response ID differs from request ID")
            return raw
        time.sleep(0.05)
    raise SpoolError("matching response did not arrive before timeout")


def run(candidate: Path, requests: Path, responses: Path, timeout_seconds: float) -> bytes:
    if timeout_seconds <= 0:
        raise SpoolError("timeout must be positive")
    raw = read_regular(candidate)
    request, canonical = parse_candidate(raw)
    filename = f"{request['id']}.json"
    response_path = responses / filename
    if response_path.exists() or response_path.is_symlink():
        raise SpoolError("matching response already exists")
    atomic_publish(requests, filename, canonical)
    return wait_response(response_path, str(request["id"]), timeout_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    requests_value = os.environ.get("M4_API_REQUEST_DIR")
    responses_value = os.environ.get("M4_API_RESPONSE_DIR")
    if not requests_value or not responses_value:
        raise SpoolError("M4 API spool directories are unavailable")
    response = run(args.candidate, Path(requests_value), Path(responses_value), args.timeout_seconds)
    sys.stdout.buffer.write(response + (b"" if response.endswith(b"\n") else b"\n"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpoolError as error:
        print(f"m4-api-spool: {error}", file=sys.stderr)
        raise SystemExit(2)
