#!/usr/bin/env python3
"""Host-only generic API file-spool gateway used by M4; no credential reaches the Agent."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import hashlib
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final
from urllib.parse import unquote, urlsplit

from m4_clarification_responder import canonical_json, secure_regular_read, sha256_bytes, utc_now
from m4_transport import strip_one_final_line_ending


MAX_REQUEST_BYTES: Final = 1024 * 1024
MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
ID_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REQUEST_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}\.json$")
ALLOWED_METHODS: Final = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SAFE_REQUEST_HEADERS: Final = {"accept", "content-type"}
SAFE_RESPONSE_HEADERS: Final = {"content-type"}


class PolicyError(ValueError):
    """An API spool request is not safe to forward."""


@dataclass(frozen=True)
class ConsumerScope:
    project_id: str
    ontology_id: str
    graph_set_id: str


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("duplicate JSON key")
        result[key] = value
    return result


def _allowed_path(value: str) -> bool:
    parts = urlsplit(value)
    return (
        value.startswith("/")
        and not parts.scheme
        and not parts.netloc
        and not parts.fragment
        and ".." not in unquote(parts.path).split("/")
        and (parts.path == "/openapi.json" or parts.path.startswith("/api/"))
    )


def _consumer_scope_path_allowed(value: str, scope: ConsumerScope) -> bool:
    """Allow only scope-bound, read-only consumer paths; never discovery endpoints."""
    path = urlsplit(value).path
    exact = {
        f"/api/projects/{scope.project_id}",
        f"/api/projects/{scope.project_id}/ontologies",
        f"/api/ontologies/{scope.ontology_id}",
        f"/api/ontologies/{scope.ontology_id}/workspace-context",
        f"/api/ontologies/{scope.ontology_id}/modeling-context",
        f"/api/semantic/graph-sets/{scope.graph_set_id}",
    }
    read_model_prefixes = (
        f"/api/ontologies/{scope.ontology_id}/semantic-read-models/",
        f"/api/semantic/graph-sets/{scope.graph_set_id}/read-models/",
    )
    return path in exact or any(path.startswith(prefix) for prefix in read_model_prefixes)


def parse_request(raw: bytes, filename: str) -> tuple[dict[str, object], bytes]:
    if not REQUEST_NAME_RE.fullmatch(filename):
        raise PolicyError("request filename is not strict ID.json")
    try:
        request = json.loads(strip_one_final_line_ending(raw).decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError("request is not strict UTF-8 JSON") from error
    if not isinstance(request, dict) or set(request) != {"id", "method", "path", "headers", "body"}:
        raise PolicyError("request keys do not match API contract")
    request_id, method, path, headers = request["id"], request["method"], request["path"], request["headers"]
    if not isinstance(request_id, str) or not ID_RE.fullmatch(request_id) or filename != f"{request_id}.json":
        raise PolicyError("request ID does not match strict filename")
    if not isinstance(method, str) or method not in ALLOWED_METHODS:
        raise PolicyError("request method is not allowlisted")
    if not isinstance(path, str) or not _allowed_path(path):
        raise PolicyError("request path is not allowlisted")
    if not isinstance(headers, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()):
        raise PolicyError("request headers must be a string map")
    normalized = {key.lower(): value for key, value in headers.items()}
    if len(normalized) != len(headers) or set(normalized) - SAFE_REQUEST_HEADERS:
        raise PolicyError("request headers violate allowlist")
    canonical = canonical_json({"id": request_id, "method": method, "path": path, "headers": normalized, "body": request["body"]})
    if strip_one_final_line_ending(raw) != canonical:
        raise PolicyError("request is not canonical JSON")
    return json.loads(canonical), canonical


def _write_response(directory: Path, filename: str, content: bytes) -> None:
    target = directory / filename
    if target.exists() or target.is_symlink():
        raise PolicyError("host response path already exists")
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
        raise PolicyError("host response path was created concurrently") from error
    finally:
        temporary.unlink(missing_ok=True)
    os.chmod(target, 0o400)


def audit_request_summary(request: dict[str, object]) -> dict[str, object]:
    """Keep only revision/id predicates needed by the host final audit, never a request body."""
    body = request.get("body")
    if not isinstance(body, dict):
        return {}
    path = str(request["path"])
    if path.endswith("/modeling-batches"):
        items = body.get("items")
        command_kinds = [
            item.get("command_kind")
            for item in items
            if isinstance(item, dict) and isinstance(item.get("command_kind"), str)
        ] if isinstance(items, list) else []
        item_summaries = [
            {
                "canonical_item_sha256": hashlib.sha256(canonical_json(item)).hexdigest(),
                "client_item_id": item.get("client_item_id"),
                "command_kind": item.get("command_kind"),
                "depends_on": item.get("depends_on", []),
            }
            for item in items
            if isinstance(item, dict)
        ] if isinstance(items, list) else []
        return {
            "client_batch_id": body.get("client_batch_id"),
            "command_kinds": command_kinds,
            "contains_create_shape": "create_shape" in command_kinds,
            "expected_workspace_version": body.get("expected_workspace_version"),
            "idempotency_key_sha256": hashlib.sha256(
                str(body.get("idempotency_key", "")).encode("utf-8")
            ).hexdigest(),
            "item_summaries": item_summaries,
            "items_sha256": hashlib.sha256(canonical_json(items)).hexdigest(),
            "mode": body.get("mode"),
            "ontology_id": body.get("ontology_id"),
        }
    if path == "/api/semantic/sparql:query":
        return {
            "ontology_ids": body.get("ontology_ids"),
            "project_id": body.get("project_id"),
            "scope_mode": body.get("scope_mode"),
        }
    if path.endswith("/checkpoints"):
        return {
            key: body[key]
            for key in ("client_checkpoint_id", "expected_revision")
            if key in body
        }
    if path.endswith(":complete"):
        return {
            key: body[key]
            for key in ("client_request_id", "expected_revision")
            if key in body
        }
    return {}


class ApiFileSpoolGateway:
    """Consumes one Agent-writable request directory and owns all safe API responses."""

    def __init__(
        self,
        *,
        requests: Path,
        responses: Path,
        audit_path: Path,
        api_key: str,
        backend_port: int = 8012,
        read_only: bool = False,
        consumer_scope: ConsumerScope | None = None,
        upstream: Callable[[dict[str, object]], tuple[int, dict[str, str], object]] | None = None,
    ) -> None:
        self.requests, self.responses, self.audit_path, self.api_key = requests, responses, audit_path, api_key
        self.backend_port, self.read_only = backend_port, read_only
        self.consumer_scope = consumer_scope
        if self.read_only and self.consumer_scope is None:
            raise PolicyError("read-only gateway requires a verified consumer scope")
        self.upstream = upstream or self._http_upstream
        self.handled_ids: set[str] = set()
        self.completed_files: dict[str, tuple[int, int, int]] = {}
        self.rejected_names: set[str] = set()
        for directory in (requests, responses):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = os.lstat(directory)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise PolicyError("API spool directory is unsafe")
        audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def audit(self, **entry: object) -> None:
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": utc_now(), **entry}, sort_keys=True) + "\n")

    def process_once(self) -> int:
        processed = 0
        with os.scandir(self.requests) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.name.startswith(".") or entry.name in self.rejected_names:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    if self.completed_files.get(entry.name) == (info.st_dev, info.st_ino, info.st_ctime_ns):
                        continue
                    if not entry.is_file(follow_symlinks=False) or entry.is_symlink():
                        raise PolicyError("request is not a regular non-symlink file")
                    raw = secure_regular_read(Path(entry.path), MAX_REQUEST_BYTES)
                    request, canonical = parse_request(raw, entry.name)
                    if self.read_only and (request["method"] != "GET" or request["body"] is not None):
                        raise PolicyError("read-only gateway accepts only bodyless GET")
                    if self.read_only and not _consumer_scope_path_allowed(
                        str(request["path"]), self.consumer_scope
                    ):
                        raise PolicyError("read-only gateway path is outside verified consumer scope")
                    request_id = str(request["id"])
                    if request_id in self.handled_ids:
                        raise PolicyError("duplicate request ID")
                    response_path = self.responses / entry.name
                    if response_path.exists() or response_path.is_symlink():
                        raise PolicyError("host response path was precreated")
                    status, headers, body = self.upstream(request)
                    safe_headers = {key.lower(): value for key, value in headers.items() if key.lower() in SAFE_RESPONSE_HEADERS}
                    response = canonical_json({"id": request_id, "status": status, "headers": safe_headers, "body": body})
                    if len(response) > MAX_RESPONSE_BYTES:
                        raise PolicyError("upstream response exceeds byte limit")
                    _write_response(self.responses, entry.name, response)
                    self.handled_ids.add(request_id)
                    self.completed_files[entry.name] = (info.st_dev, info.st_ino, info.st_ctime_ns)
                    self.audit(
                        policy="forwarded",
                        request_id=request_id,
                        method=request["method"],
                        path=request["path"],
                        raw_request_sha256=sha256_bytes(raw),
                        canonical_request_sha256=sha256_bytes(canonical),
                        request_summary=audit_request_summary(request),
                        response_sha256=sha256_bytes(response),
                        response_filename=entry.name,
                        status=status,
                    )
                    processed += 1
                except PolicyError as error:
                    self.rejected_names.add(entry.name)
                    self.audit(policy="rejected", filename=entry.name, reason=str(error))
        return processed

    def _http_upstream(self, request: dict[str, object]) -> tuple[int, dict[str, str], object]:
        headers = dict(request["headers"])
        headers["Authorization"] = f"Bearer {self.api_key}"
        body_value = request["body"]
        body = None if body_value is None else canonical_json(body_value)
        if body is not None:
            headers.setdefault("content-type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.backend_port, timeout=30)
        connection.request(str(request["method"]), str(request["path"]), body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise PolicyError("upstream response exceeds byte limit")
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {"non_json_response": raw.decode("utf-8", errors="replace")}
        return response.status, dict(response.getheaders()), parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    api_key_source = parser.add_mutually_exclusive_group(required=True)
    api_key_source.add_argument("--api-key")
    api_key_source.add_argument("--api-key-env")
    parser.add_argument("--backend-port", type=int, default=8012)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--consumer-project-id")
    parser.add_argument("--consumer-ontology-id")
    parser.add_argument("--consumer-graph-set-id")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    args = parser.parse_args()
    api_key = args.api_key or os.environ.get(args.api_key_env, "")
    if not api_key:
        raise PolicyError("host API key is empty")
    consumer_scope = None
    scope_values = (
        args.consumer_project_id,
        args.consumer_ontology_id,
        args.consumer_graph_set_id,
    )
    if args.read_only:
        if not all(isinstance(value, str) and value for value in scope_values):
            raise PolicyError("read-only gateway requires all consumer scope IDs")
        consumer_scope = ConsumerScope(*scope_values)
    elif any(value is not None for value in scope_values):
        raise PolicyError("consumer scope IDs require --read-only")
    gateway = ApiFileSpoolGateway(
        requests=args.requests,
        responses=args.responses,
        audit_path=args.audit,
        api_key=api_key,
        backend_port=args.backend_port,
        read_only=args.read_only,
        consumer_scope=consumer_scope,
    )
    if args.poll_seconds <= 0:
        raise PolicyError("poll seconds must be positive")
    if args.watch:
        while True:
            gateway.process_once()
            time.sleep(args.poll_seconds)
    else:
        gateway.process_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
