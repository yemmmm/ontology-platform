"""Private R4.3-029 Delivery-to-Host journal hand-off.
Only bounded request/result metadata is journaled; Host result bodies stay in
the session-private host-results directory.
"""

from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from .host_ops import HostOpError

SESSION_EVENTS_FILENAME = "session-events.jsonl"
SESSION_EVENTS_LOCK_FILENAME = "session-events.jsonl.lock"
HOST_RESULTS_DIRECTORY = "host-results"
HOST_ACTION_REQUEST_EVENT = "host_action_request"
HOST_ACTION_RESULT_EVENT = "host_action_result"
HOST_ACTION_SCHEMA = "r4.3-029-host-action/v1"
HOST_RESULT_SOURCE = "host_agent"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_KINDS, _STATUSES = {"cq_review", "platform_repair"}, {"completed", "blocked", "failed"}
_BINDING_KEYS = {
    "id",
    "type",
    "status",
    "kind",
    "review_id",
    "question_id",
    "question_ids",
    "content_version",
    "content_digest",
    "digest",
    "review_snapshot_ref",
    "snapshot_ref",
    "phase",
    "recorded_at",
    "source_ref",
    "path",
    "byte_offset",
    "byte_length",
    "issue_id",
    "reporter_id",
    "control_epoch",
    "issue_epoch",
    "request_id",
    "run_id",
    "version",
    "state",
    "action",
    "reason_code",
    "session_id",
    "material_id",
    "visibility",
}
_META_KEYS = {
    "expected_behavior",
    "actual_behavior",
    "blocked_step",
    "checked",
    "hypotheses",
    "write_state",
    "expected",
    "actual",
    "limitations",
    "stage",
    "report_ref",
    "operation_ref",
    "current_write_state",
    "evidence_references",
}
_PRIVATE_PATH_MARKERS = (
    "competency-questions/private",
    "competency-questions/reviews",
    "competency-questions/frozen",
    "acceptance-v3/reports",
    "/evidence/cq-",
    "evidence/cq-",
)
_RUN_PATH_PREFIXES = ("evidence/", "control/", "manifest-snapshots/", "early-feedback/")
_RUN_PATH_FILES = {
    "state.json",
    "baseline-manifest.json",
    "task.snapshot.yaml",
    "profile.snapshot.yaml",
    "model-handoff.json",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fail(
    code: str,
    reason: str,
    *,
    obj: str | None = None,
    retryable: bool = True,
    next_action: str | None = None,
    **extra: Any,
) -> HostOpError:
    return HostOpError(
        code, reason, obj=obj, retryable=retryable, next_action=next_action, passthrough=extra
    )


def _root(value: Path | str, *, create: bool) -> Path:
    path = Path(value).expanduser()
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = path.resolve(strict=False)
    except OSError as exc:
        raise _fail(
            "host_journal_unavailable",
            str(exc),
            obj=str(path),
            next_action="restore the private session directory and retry",
        ) from exc
    if not path.is_dir():
        raise _fail(
            "host_journal_unavailable",
            "private session root is not a directory",
            obj=str(path),
            next_action="restore the private session directory and retry",
        )
    return path


def _id(value: Any, name: str, *, session: bool = False) -> str:
    pattern = _SESSION_ID if session else _ID
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _fail(
            "host_action_identity_invalid",
            f"invalid {name}",
            obj=name,
            retryable=False,
            next_action=f"provide a valid {name}",
        )
    return value


def _encode(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _fail(
            "host_journal_value_invalid",
            str(exc),
            retryable=False,
            next_action="use JSON-compatible metadata",
        ) from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_encode(value)[:-1]).hexdigest()


@contextlib.contextmanager
def _lock(root: Path, *, exclusive: bool) -> Iterator[None]:
    path = root / SESSION_EVENTS_LOCK_FILENAME
    try:
        handle = os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+b")
    except OSError as exc:
        raise _fail(
            "host_journal_lock_unavailable",
            str(exc),
            obj=str(path),
            next_action="restore the private journal lock and retry",
        ) from exc
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    except OSError as exc:
        raise _fail(
            "host_journal_lock_failed",
            str(exc),
            obj=str(path),
            next_action="retry after the private session lock is available",
        ) from exc
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _append_locked(root: Path, line: bytes) -> tuple[int, int]:
    path = root / SESSION_EVENTS_FILENAME
    try:
        with path.open("ab") as handle:
            handle.seek(0, os.SEEK_END)
            offset = handle.tell()
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise _fail(
            "host_journal_write_failed",
            str(exc),
            obj=str(path),
            next_action="inspect the journal tail before retrying",
        ) from exc
    return offset, len(line)


def append_session_event(session_root: Path | str, value: Mapping[str, Any]) -> tuple[int, int]:
    if not isinstance(value, Mapping):
        raise _fail(
            "host_journal_value_invalid",
            "session event must be an object",
            retryable=False,
            next_action="append a mapping event",
        )
    root = _root(session_root, create=True)
    with _lock(root, exclusive=True):
        return _append_locked(root, _encode(value))


def read_session_journal(session_root: Path | str) -> bytes:
    root = _root(session_root, create=False)
    with _lock(root, exclusive=False):
        try:
            return (root / SESSION_EVENTS_FILENAME).read_bytes()
        except FileNotFoundError:
            return b""
        except OSError as exc:
            raise _fail(
                "host_journal_unavailable",
                str(exc),
                obj=str(root / SESSION_EVENTS_FILENAME),
                next_action="restore the private journal and retry",
            ) from exc


@dataclass
class _HostJournalCursor:
    signature: tuple[int, ...] | None = None
    offset: int = 0
    events: list[tuple[dict[str, Any], int, int]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)


@lru_cache(maxsize=32)
def _host_journal_cursor(root: Path) -> _HostJournalCursor:
    return _HostJournalCursor()


def _read_locked(root: Path) -> tuple[list[tuple[dict[str, Any], int, int]], list[str]]:
    """Read new journal rows under the file lock, retaining only Host actions.

    The journal is append-only. Replacement, truncation or an in-place edit at
    the same size rebuilds the projection; recovery in another process starts
    from the original file. A partial tail is retried, never cached as consumed.
    """
    cursor = _host_journal_cursor(root)
    with cursor.lock:
        try:
            with (root / SESSION_EVENTS_FILENAME).open("rb") as handle:
                stat = os.fstat(handle.fileno())
                signature = (stat.st_dev, stat.st_ino, stat.st_size,
                             stat.st_mtime_ns, stat.st_ctime_ns)
                previous = cursor.signature
                if previous and (signature[:2] != previous[:2]
                                 or signature[2] < previous[2]
                                 or signature[2] == previous[2] and signature != previous):
                    cursor.offset, cursor.events, cursor.limitations = 0, [], []
                if signature != previous:
                    handle.seek(cursor.offset)
                    for line in handle:
                        if not line.endswith(b"\n"):
                            break
                        length = len(line)
                        try:
                            value = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            cursor.limitations.append(f"corrupt_event:{cursor.offset}")
                        else:
                            if not isinstance(value, dict):
                                cursor.limitations.append(f"non_object_event:{cursor.offset}")
                            elif _kind(value) in {HOST_ACTION_REQUEST_EVENT, HOST_ACTION_RESULT_EVENT}:
                                cursor.events.append((value, cursor.offset, length))
                        cursor.offset += length
                    cursor.signature = signature
        except FileNotFoundError:
            cursor.signature, cursor.offset = None, 0
            cursor.events, cursor.limitations = [], []
            return [], ["history_not_started"]
        except OSError as exc:
            return [], [f"history_unavailable:{exc}"]
        limitations = list(cursor.limitations)
        if cursor.offset < signature[2]:
            limitations.append(f"incomplete_tail:{cursor.offset}")
        return deepcopy(cursor.events), limitations


def _kind(event: Mapping[str, Any]) -> str | None:
    value = event.get("event") or event.get("event_type")
    return value if isinstance(value, str) else None


def _journal_ref(root: Path, offset: int, length: int) -> dict[str, Any]:
    return {
        "path": str(root / SESSION_EVENTS_FILENAME),
        "byte_offset": offset,
        "byte_length": length,
    }


def _binding(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(
            "host_action_binding_invalid",
            f"{name} must be an object",
            obj=name,
            next_action=f"refresh the current {name} binding and retry",
        )
    result = {key: value[key] for key in _BINDING_KEYS if key in value}
    if not result:
        raise _fail(
            "host_action_binding_invalid",
            f"{name} has no binding metadata",
            obj=name,
            next_action=f"refresh the current {name} binding and retry",
        )
    try:
        _encode(result)
    except HostOpError as exc:
        raise _fail(
            "host_action_binding_invalid",
            str(exc),
            obj=name,
            retryable=False,
            next_action="use JSON-compatible binding metadata",
        ) from exc
    return result


def _private_path(value: str | None, item: Mapping[str, Any]) -> bool:
    source = item.get("source_ref")
    if item.get("visibility") in {"private", "hidden"} or (
        isinstance(source, Mapping) and source.get("visibility") in {"private", "hidden"}
    ):
        return True
    if not isinstance(value, str):
        return False
    return any(marker in value.replace("\\", "/").lower() for marker in _PRIVATE_PATH_MARKERS)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _evidence(value: Any, root: Path, session_id: str, run_ids: set[str]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _fail(
            "host_action_evidence_invalid",
            "evidence_references must be a list",
            obj="evidence_references",
            retryable=False,
            next_action="provide approved session/run references",
        )
    session_root = root.resolve(strict=False)
    repo_root = root.parents[2] if len(root.parents) > 2 else root
    run_base = (repo_root / "workspaces" / "modeling-runs").resolve(strict=False)
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise _fail(
                "host_action_evidence_forbidden",
                "evidence reference must be metadata",
                obj="evidence_references",
                next_action="use approved technical/public evidence",
            )
        ref = _binding(item, "evidence_reference")
        if item.get("session_id") not in (None, session_id):
            raise _fail(
                "host_action_evidence_unbound",
                "evidence belongs to another session",
                obj="evidence_references",
                next_action="use current session evidence",
            )
        run_id = item.get("run_id")
        if run_id is not None and run_id not in run_ids:
            raise _fail(
                "host_action_evidence_unbound",
                "evidence belongs to another run",
                obj="evidence_references",
                next_action="use a current Delivery run",
            )
        source = item.get("source_ref")
        path_value = item.get("path") or (
            source.get("path") if isinstance(source, Mapping) else None
        )
        if _private_path(path_value, item):
            raise _fail(
                "host_action_evidence_forbidden",
                "private CQ material is not repair evidence",
                obj="evidence_references",
                next_action="use approved technical/public evidence",
            )
        if not isinstance(path_value, str):
            if not item.get("material_id"):
                raise _fail(
                    "host_action_evidence_invalid",
                    "evidence needs a path or material_id",
                    obj="evidence_references",
                    next_action="include the actual reference",
                )
        else:
            if not path_value.strip() or "\x00" in path_value:
                raise _fail(
                    "host_action_evidence_invalid",
                    "evidence path is invalid",
                    obj="evidence_references",
                    next_action="include the actual reference",
                )
            path = Path(path_value).expanduser()
            candidates = [path if path.is_absolute() else root / path]
            run_root = (run_base / run_id).resolve(strict=False) if run_id else None
            if run_root is not None and not path.is_absolute():
                candidates.append(run_root / path)
            bound = False
            for candidate in candidates:
                resolved = candidate.resolve(strict=False)
                if _inside(resolved, session_root):
                    bound = True
                elif run_root is not None and _inside(resolved, run_root):
                    relative = resolved.relative_to(run_root).as_posix()
                    bound = relative in _RUN_PATH_FILES or relative.startswith(_RUN_PATH_PREFIXES)
                if bound:
                    break
            if not bound:
                raise _fail(
                    "host_action_evidence_unbound",
                    "evidence is outside current session/run",
                    obj="evidence_references",
                    next_action="use bound technical/public evidence",
                )
        result.append(ref)
    return result


def _safe_arguments(
    arguments: Mapping[str, Any], *, kind: str, root: Path, session_id: str, run_ids: set[str]
) -> dict[str, Any]:
    allowed = {
        "request_id",
        "run_id",
        "kind",
        "authorization",
        "authorization_reference",
        "bindings",
    } | _META_KEYS
    unknown = set(arguments) - allowed
    if unknown:
        raise _fail(
            "host_action_arguments_invalid",
            "unsupported fields: " + ", ".join(sorted(map(str, unknown))),
            retryable=False,
            next_action="send references and bounded diagnostics only",
        )
    raw = arguments.get("bindings")
    if kind == "cq_review":
        binding = _binding(raw, "bindings")
        if not any(binding.get(key) for key in ("review_id", "question_id", "question_ids", "id")):
            raise _fail(
                "host_action_pending_unbound",
                "CQ request has no pending review identity",
                obj="bindings",
                next_action="use the actual cq_review pending binding",
            )
    elif raw:
        binding = _binding(raw, "bindings")
        if binding.get("issue_id") is None:
            raise _fail(
                "host_action_issue_unbound",
                "issue binding must include issue_id",
                obj="bindings",
                next_action="use the actual pending issue binding",
            )
    else:
        binding = {}
    result = {"bindings": binding}
    for key in _META_KEYS:
        if key not in arguments:
            continue
        if key == "evidence_references":
            result[key] = _evidence(arguments[key], root, session_id, run_ids)
            continue
        try:
            json.dumps(arguments[key], ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise _fail(
                "host_action_arguments_invalid",
                str(exc),
                obj=key,
                retryable=False,
                next_action="use JSON-compatible diagnostics",
            ) from exc
        result[key] = arguments[key]
    return result


def request_host_action(
    session_root: Path | str,
    session_id: str,
    run_ids: Sequence[str] | set[str] | str,
    authorization: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    session_id = _id(session_id, "session_id", session=True)
    try:
        run_set = {run_ids} if isinstance(run_ids, str) else set(run_ids)
    except TypeError as exc:
        raise _fail(
            "host_action_run_binding_invalid",
            "run_ids must contain current run IDs",
            obj="run_ids",
            retryable=False,
            next_action="refresh the Delivery run IDs",
        ) from exc
    if any(not isinstance(item, str) or not item for item in run_set):
        raise _fail(
            "host_action_run_binding_invalid",
            "run_ids must contain current run IDs",
            obj="run_ids",
            retryable=False,
            next_action="refresh the Delivery run IDs",
        )
    if not isinstance(authorization, str) or not authorization.strip() or "\x00" in authorization:
        raise _fail(
            "host_action_reference_invalid",
            "invalid authorization_reference",
            obj="authorization_reference",
            retryable=False,
            next_action="provide the actual authorization_reference",
        )
    if not isinstance(arguments, Mapping):
        raise _fail(
            "host_action_arguments_invalid",
            "arguments must be an object",
            retryable=False,
            next_action="provide the host action object",
        )
    request_id, kind, run_id = (
        arguments.get("request_id"),
        arguments.get("kind"),
        arguments.get("run_id"),
    )
    request_id = _id(request_id, "request_id")
    if kind not in _KINDS:
        raise _fail(
            "host_action_kind_invalid",
            "kind must be cq_review or platform_repair",
            obj="kind",
            retryable=False,
            next_action="choose a supported host action kind",
        )
    if not isinstance(run_id, str) or run_id not in run_set:
        raise _fail(
            "host_action_run_unbound",
            "request is outside this Delivery session",
            obj="run_id",
            next_action="use a current Delivery run",
        )
    supplied = arguments.get("authorization_reference", arguments.get("authorization"))
    if supplied is not None and supplied != authorization:
        raise _fail(
            "host_action_authorization_mismatch",
            "authorization differs from Delivery",
            obj="authorization_reference",
            retryable=False,
            next_action="use the current Delivery authorization",
        )
    root = _root(session_root, create=True)
    safe = _safe_arguments(arguments, kind=kind, root=root, session_id=session_id, run_ids=run_set)
    payload = {
        "session_id": session_id,
        "run_id": run_id,
        "kind": kind,
        "authorization_reference": authorization,
        "request_id": request_id,
        "arguments": safe,
    }
    digest = _digest(payload)
    event = {
        "event": HOST_ACTION_REQUEST_EVENT,
        "schema_version": HOST_ACTION_SCHEMA,
        "recorded_at": _now(),
        **payload,
        "bindings": safe["bindings"],
        **safe,
        "content_digest": digest,
        "request_digest": digest,
    }
    with _lock(root, exclusive=True):
        events, limitations = _read_locked(root)
        if any(item.startswith("incomplete_tail") for item in limitations):
            raise _fail(
                "host_journal_incomplete",
                "private journal has an incomplete tail",
                obj=str(root / SESSION_EVENTS_FILENAME),
                next_action="preserve and repair the journal tail before retrying",
            )
        existing = next(
            (
                (event, offset, length)
                for event, offset, length in events
                if _kind(event) == HOST_ACTION_REQUEST_EVENT
                and event.get("request_id") == request_id
            ),
            None,
        )
        if existing is not None:
            old, offset, length = existing
            if old.get("content_digest") == digest or old.get("request_digest") == digest:
                return {**old, "journal_ref": _journal_ref(root, offset, length)}
            raise _fail(
                "host_action_request_id_conflict",
                "request_id already has different content",
                obj="request_id",
                next_action="inspect the original and use a new request_id",
                recorded_content_digest=old.get("content_digest"),
                submitted_content_digest=digest,
            )
        offset, length = _append_locked(root, _encode(event))
    return {**event, "journal_ref": _journal_ref(root, offset, length)}


def _result_file(root: Path, value: Path | str) -> tuple[Path, str]:
    directory = root / HOST_RESULTS_DIRECTORY
    if directory.is_symlink() or not directory.is_dir():
        raise _fail(
            "host_result_unavailable",
            "private host-results directory is unavailable",
            obj=str(directory),
            next_action="restore session/host-results and retry",
        )
    if not isinstance(value, (str, Path)):
        raise _fail(
            "host_result_unavailable",
            "result_path is invalid",
            obj="result_path",
            next_action="use an actual file under session/host-results",
        )
    candidate = Path(value).expanduser()
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved, allowed = candidate.resolve(strict=False), directory.resolve(strict=False)
        resolved.relative_to(allowed)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail(
            "host_result_path_escape",
            "result_path is outside private host-results",
            obj=str(value),
            next_action="use an actual file under session/host-results",
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise _fail(
            "host_result_unavailable",
            "result original is missing or not a regular file",
            obj=str(value),
            next_action="restore the current result original and retry",
        )
    return resolved, resolved.relative_to(root).as_posix()


def _result_meta(path: Path, relative: str) -> dict[str, Any]:
    try:
        before, raw, after = path.stat(), path.read_bytes(), path.stat()
    except OSError as exc:
        raise _fail(
            "host_result_unreadable",
            str(exc),
            obj=relative,
            next_action="restore the result original and retry",
        ) from exc
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise _fail(
            "host_result_changed",
            "result original changed while being read",
            obj=relative,
            next_action="write a stable result original and retry",
        )
    return {
        "path": relative,
        "content_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
        "mtime_ns": after.st_mtime_ns,
    }


def record_host_action_result(
    session_root: Path | str, request_id: str, status: str, result_path: Path | str
) -> dict[str, Any]:
    request_id = _id(request_id, "request_id")
    if status not in _STATUSES:
        raise _fail(
            "host_result_status_invalid",
            "status must be completed, blocked or failed",
            obj="status",
            retryable=False,
            next_action="choose a supported status",
        )
    root = _root(session_root, create=False)
    with _lock(root, exclusive=True):
        events, limitations = _read_locked(root)
        if any(item.startswith("incomplete_tail") for item in limitations):
            raise _fail(
                "host_journal_incomplete",
                "private journal has an incomplete tail",
                obj=str(root / SESSION_EVENTS_FILENAME),
                next_action="repair the journal tail",
            )
        request = next(
            (
                (event, offset, length)
                for event, offset, length in events
                if _kind(event) == HOST_ACTION_REQUEST_EVENT
                and event.get("request_id") == request_id
            ),
            None,
        )
        if request is None:
            raise _fail(
                "host_action_request_unknown",
                "request_id is not in this session journal",
                obj="request_id",
                next_action="refresh and use the current host request",
            )
        request_event, _, _ = request
        path, relative = _result_file(root, result_path)
        result_ref = _result_meta(path, relative)
        old = next(
            (
                (event, offset, length)
                for event, offset, length in events
                if _kind(event) == HOST_ACTION_RESULT_EVENT
                and event.get("request_id") == request_id
            ),
            None,
        )
        if old is not None:
            old_event, offset, length = old
            old_ref = old_event.get("result_ref") or {}
            if (
                old_event.get("status") == status
                and old_ref.get("path") == result_ref["path"]
                and old_ref.get("content_digest") == result_ref["content_digest"]
            ):
                return {**old_event, "journal_ref": _journal_ref(root, offset, length)}
            raise _fail(
                "host_action_result_conflict",
                "request_id already has a different result",
                obj="request_id",
                next_action="inspect the recorded result or issue a new request",
                recorded_result=old_ref,
                submitted_result=result_ref,
            )
        event = {
            "event": HOST_ACTION_RESULT_EVENT,
            "schema_version": HOST_ACTION_SCHEMA,
            "recorded_at": datetime.now(UTC).isoformat(),
            "session_id": request_event.get("session_id"),
            "run_id": request_event.get("run_id"),
            "request_id": request_id,
            "kind": request_event.get("kind"),
            "authorization_reference": request_event.get("authorization_reference"),
            "source": HOST_RESULT_SOURCE,
            "status": status,
            "result_ref": result_ref,
            "result_digest": result_ref["content_digest"],
        }
        offset, length = _append_locked(root, _encode(event))
    return {**event, "journal_ref": _journal_ref(root, offset, length)}


append_host_action_result = record_host_action_result


def host_action_state(session_root: Path | str) -> dict[str, Any]:
    root = _root(session_root, create=False)
    with _lock(root, exclusive=False):
        events, limitations = _read_locked(root)
    requests: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    for event, offset, length in events:
        kind, request_id = _kind(event), event.get("request_id")
        if not isinstance(request_id, str) or kind not in {
            HOST_ACTION_REQUEST_EVENT,
            HOST_ACTION_RESULT_EVENT,
        }:
            continue
        if kind == HOST_ACTION_REQUEST_EVENT:
            if request_id in requests and requests[request_id].get("content_digest") != event.get(
                "content_digest"
            ):
                limitations.append(f"request_conflict:{request_id}")
            else:
                requests.setdefault(
                    request_id, {**event, "journal_ref": _journal_ref(root, offset, length)}
                )
            continue
        request = requests.get(request_id)
        if request is None:
            limitations.append(f"orphan_result:{request_id}")
            continue
        if (event.get("session_id"), event.get("run_id")) != (
            request.get("session_id"),
            request.get("run_id"),
        ):
            limitations.append(f"result_binding_mismatch:{request_id}")
            continue
        if event.get("source") != HOST_RESULT_SOURCE:
            limitations.append(f"result_source_invalid:{request_id}")
            continue
        results[request_id] = {**event, "journal_ref": _journal_ref(root, offset, length)}
    pending = [item for key, item in requests.items() if key not in results]
    unresolved = [item for item in results.values() if item.get("status") in {"blocked", "failed"}]
    completed = [item for item in results.values() if item.get("status") == "completed"]
    incomplete = ("incomplete_tail", "history_unavailable", "corrupt_event")
    return {
        "schema_version": HOST_ACTION_SCHEMA,
        "requests": requests,
        "results": results,
        "pending": pending,
        "unresolved": unresolved,
        "completed": completed,
        "history_complete": not any(item.startswith(incomplete) for item in limitations),
        "limitations": sorted(set(limitations)),
    }


read_host_action_state = host_action_state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one private Host action result")
    parser.add_argument("--session-root", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(_STATUSES))
    parser.add_argument("--result-path", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = record_host_action_result(
            args.session_root, args.request_id, args.status, args.result_path
        )
    except HostOpError as exc:
        print(json.dumps({"ok": False, "error": exc.as_envelope()}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "data": value}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
