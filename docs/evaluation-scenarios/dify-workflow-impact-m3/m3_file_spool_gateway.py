#!/usr/bin/env python3
"""Fail-closed host-side file-spool RPC gateway for an isolated M3 Agent."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import signal
import stat
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Final
from urllib.parse import unquote, urlsplit


MAX_REQUEST_BYTES: Final = 1024 * 1024
MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
ID_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{7,63}$")
REQUEST_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{7,63}\.json$")
ALLOWED_METHODS: Final = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SAFE_REQUEST_HEADERS: Final = {"accept", "content-type"}
SAFE_RESPONSE_HEADERS: Final = {"content-type"}


class PolicyError(ValueError):
    """A malformed or unauthorized Agent request that must not reach the backend."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_allowed_path(value: str) -> bool:
    parts = urlsplit(value)
    decoded_parts = unquote(parts.path).split("/")
    return (
        value.startswith("/")
        and not parts.scheme
        and not parts.netloc
        and not parts.fragment
        and ".." not in decoded_parts
        and (parts.path == "/openapi.json" or parts.path.startswith("/api/"))
    )


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("duplicate JSON key")
        result[key] = value
    return result


def secure_regular_read(path: Path, size_limit: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as error:
        raise PolicyError("request is not a no-follow readable file") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PolicyError("request is not one regular unlinked-safe file")
        if info.st_size > size_limit:
            raise PolicyError("request exceeds the byte limit")
        value = os.read(descriptor, size_limit + 1)
        if len(value) > size_limit:
            raise PolicyError("request exceeds the byte limit")
        return value
    finally:
        os.close(descriptor)


def exclusive_write(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_response_atomically(directory: Path, name: str, content: bytes) -> None:
    target = directory / name
    try:
        existing = os.lstat(target)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        raise PolicyError("host response path already exists")
    temporary = directory / f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    exclusive_write(temporary, content)
    try:
        os.link(temporary, target, follow_symlinks=False)
    except FileExistsError as error:
        raise PolicyError("host response path was created concurrently") from error
    finally:
        temporary.unlink(missing_ok=True)


def parse_request(raw: bytes, filename: str) -> tuple[dict[str, object], bytes]:
    if not REQUEST_NAME_RE.fullmatch(filename):
        raise PolicyError("request filename is not a strict ID.json")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError("request is not strict UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != {"id", "method", "path", "headers", "body"}:
        raise PolicyError("request keys do not match the RPC contract")
    request_id, method, path, headers = value["id"], value["method"], value["path"], value["headers"]
    if not isinstance(request_id, str) or not ID_RE.fullmatch(request_id) or filename != f"{request_id}.json":
        raise PolicyError("request ID does not match its strict filename")
    if not isinstance(method, str) or method not in ALLOWED_METHODS:
        raise PolicyError("request method is not allowlisted")
    if not isinstance(path, str) or not is_allowed_path(path):
        raise PolicyError("request path is not allowlisted")
    if not isinstance(headers, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in headers.items()):
        raise PolicyError("request headers must be a string map")
    normalized = {key.lower(): item for key, item in headers.items()}
    if len(normalized) != len(headers) or set(normalized) - SAFE_REQUEST_HEADERS or "authorization" in normalized:
        raise PolicyError("request headers violate the allowlist")
    canonical = canonical_json(
        {"id": request_id, "method": method, "path": path, "headers": normalized, "body": value["body"]}
    )
    return json.loads(canonical), canonical


class FileSpoolGateway:
    """Consumes one Agent-writable request directory and owns all responses."""

    def __init__(
        self,
        *,
        requests: Path,
        responses: Path,
        archive: Path,
        audit_path: Path,
        api_key: str,
        upstream: Callable[[dict[str, object]], tuple[int, dict[str, str], object]] | None = None,
        request_allowed: Callable[[dict[str, object]], bool] | None = None,
    ) -> None:
        self.requests, self.responses, self.archive = requests, responses, archive
        self.audit_path, self.api_key = audit_path, api_key
        self.upstream = upstream or self._http_upstream
        self.request_allowed = request_allowed or (lambda _request: True)
        self.handled_ids: set[str] = set()
        self.completed_files: dict[str, tuple[int, int]] = {}
        self.rejected_names: set[str] = set()
        self.audit_lock = threading.Lock()
        for directory in (responses, archive):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = os.lstat(directory)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise PolicyError("host-owned directory is unsafe")

    def audit(self, **entry: object) -> None:
        safe = {"at": utc_now(), **entry}
        with self.audit_lock, self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe, ensure_ascii=False, sort_keys=True) + "\n")

    def process_once(self) -> int:
        processed = 0
        with os.scandir(self.requests) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.name in self.rejected_names:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    # Agent atomic request writes may remove a temporary entry after scandir().
                    continue
                file_identity = (info.st_dev, info.st_ino)
                if self.completed_files.get(entry.name) == file_identity:
                    continue
                if not entry.is_file(follow_symlinks=False) or entry.is_symlink():
                    self.rejected_names.add(entry.name)
                    self.audit(policy="rejected", reason="non_regular_request", filename=entry.name)
                    continue
                self._process(Path(entry.path), entry.name, file_identity)
                processed += 1
        return processed

    def _process(self, request_path: Path, filename: str, file_identity: tuple[int, int]) -> None:
        request_id: str | None = None
        try:
            raw = secure_regular_read(request_path, MAX_REQUEST_BYTES)
            request, request_bytes = parse_request(raw, filename)
            request_id = str(request["id"])
            if not self.request_allowed(request):
                raise PolicyError("request violates gateway operation policy")
            if request_id in self.handled_ids:
                raise PolicyError("duplicate request ID")
            response_path = self.responses / filename
            if response_path.exists() or response_path.is_symlink():
                raise PolicyError("host response was precreated")
            archive_path = self.archive / filename
            exclusive_write(archive_path, request_bytes)
            self.handled_ids.add(request_id)
            status, headers, body = self.upstream(request)
            safe_headers = {key.lower(): value for key, value in headers.items() if key.lower() in SAFE_RESPONSE_HEADERS}
            response_bytes = canonical_json(
                {"id": request_id, "status": status, "headers": safe_headers, "body": body}
            )
            if len(response_bytes) > MAX_RESPONSE_BYTES:
                raise PolicyError("upstream response exceeds the byte limit")
            write_response_atomically(self.responses, filename, response_bytes)
            self.completed_files[filename] = file_identity
            self.audit(
                policy="forwarded",
                request_id=request_id,
                method=request["method"],
                path=request["path"],
                status=status,
                request_sha256=sha256_bytes(request_bytes),
                response_sha256=sha256_bytes(response_bytes),
            )
        except PolicyError as error:
            self.rejected_names.add(filename)
            self.audit(policy="rejected", reason=str(error), filename=filename, request_id=request_id)

    def _http_upstream(self, request: dict[str, object]) -> tuple[int, dict[str, str], object]:
        headers = dict(request["headers"])
        headers["Authorization"] = f"Bearer {self.api_key}"
        body_value = request["body"]
        body = None if body_value is None else canonical_json(body_value)
        if body is not None:
            headers.setdefault("content-type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", 8012, timeout=30)
        connection.request(str(request["method"]), str(request["path"]), body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise PolicyError("upstream response exceeds the byte limit")
        try:
            body_value = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            body_value = {"non_json_response": raw.decode("utf-8", errors="replace")}
        return response.status, dict(response.getheaders()), body_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    api_key = os.environ.get("M3_API_KEY")
    if not api_key:
        raise SystemExit("M3_API_KEY must exist only in the host gateway environment")
    gateway = FileSpoolGateway(
        requests=args.requests,
        responses=args.responses,
        archive=args.archive,
        audit_path=args.audit,
        api_key=api_key,
    )
    stop = False

    def request_stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop:
        gateway.process_once()
        time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
