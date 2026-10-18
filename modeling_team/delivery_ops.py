"""Narrow host-side Delivery operations for R4.0-023.

This module owns only the Delivery-specific process boundary.  Evaluation and
repair are explicit subprocesses with private records and logs; they are not a
general job queue and they never decide semantic results.  Platform
reconciliation uses the existing cursor-paginated readback implementation and
never exposes an apply or delete operation.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .checkpoint_recovery import (
    CompletedOperation,
    PlatformReadback,
    http_readback,
    origin_chain_roots,
    read_write_tail,
    reconcile_write_tail,
)
from .checkpoints import CheckpointError
from .competency_questions import CQContractError, reload_frozen_pool
from .host_ops import (
    DEFAULT_PLATFORM_BASE_URL,
    HOST_CREDENTIAL_ENV,
    HostOpError,
    default_repository_root,
    resolve_repo_path,
    resolve_run_root,
)


DELIVERY_DIRECTORY = ".delivery-ops"
DELIVERY_RECORD_SCHEMA = "modeling-team-delivery-operation/v1"
EVALUATION_SCHEMA = "modeling-team-delivery-evaluation/v1"
REPAIR_SCHEMA = "modeling-team-delivery-repair/v1"
OPERATION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})
SERVICE_TIERS = frozenset({"unset", "fast", "default"})
EVALUATION_MODES = frozenset({"cq-acceptance", "public-feedback"})
REPORT_VERDICTS = frozenset(
    {"pass", "model-recall-insufficient", "question-answer-review", "platform-runtime-incomplete"}
)
LOG_TAIL_BYTES = 4096
DEFAULT_EVALUATION_MODEL_PROFILE = "openai-luna-medium"
REPAIR_PUBLIC_CODE_ROOTS = ("modeling_team", "backend/app", "backend/.venv")
REPAIR_PRIVATE_PATH_PARTS = frozenset(
    {".git", ".codex", ".claude", ".delivery-ops", "workspaces"}
)
REPAIR_PRIVATE_PATH_PREFIXES = ("docs/delivery", "docs/evaluation")
REPAIR_DIFF_MAX_BYTES = 512 * 1024
REPAIR_TASK_METADATA_SCAN_LINES = 32
REPAIR_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)

_RECORD_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(repository_root: Path | None) -> Path:
    return (Path(repository_root) if repository_root is not None else default_repository_root()).resolve()


def _delivery_dir(repository_root: Path | None, *, create: bool = False) -> Path:
    root = _root(repository_root)
    path = root / DELIVERY_DIRECTORY
    if create:
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise HostOpError(
                "delivery_record_failed",
                f"could not create the private Delivery directory: {exc.strerror or exc}",
                obj=DELIVERY_DIRECTORY,
                retryable=False,
                next_action="check the repository checkout permissions",
            ) from exc
    return path


def _validate_operation_id(value: Any) -> str:
    if not isinstance(value, str) or not OPERATION_ID_PATTERN.fullmatch(value):
        raise HostOpError(
            "delivery_operation_id_invalid",
            "operation_id must be one safe path component of at most 128 characters",
            obj="operation_id",
            retryable=True,
            next_action="choose a new explicit Delivery operation id",
        )
    return value


def _nonempty(value: Any, field: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value or len(value) > max_length:
        raise HostOpError(
            "delivery_argument_invalid",
            f"{field} must be a non-empty string of at most {max_length} characters",
            obj=field,
            retryable=True,
            next_action=f"provide a valid {field}",
        )
    return value


def _safe_ref(value: Any, field: str) -> str:
    value = _nonempty(value, field, max_length=256)
    if not REFERENCE_PATTERN.fullmatch(value):
        raise HostOpError(
            "delivery_argument_invalid",
            f"{field} must be a single safe identifier/reference",
            obj=field,
            retryable=True,
            next_action=f"provide the recorded {field} without path separators",
        )
    return value


def _validate_base_url(value: str | None) -> str:
    value = DEFAULT_PLATFORM_BASE_URL if value is None else _nonempty(value, "base_url", max_length=2048)
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HostOpError(
            "delivery_argument_invalid",
            "base_url must be an http(s) URL",
            obj="base_url",
            retryable=True,
            next_action="provide the existing platform readback URL",
        )
    return value


def _record_path(operation_id: str, repository_root: Path | None) -> Path:
    return _delivery_dir(repository_root) / f"{_validate_operation_id(operation_id)}.json"


def _log_paths(operation_id: str, repository_root: Path | None) -> tuple[Path, Path]:
    directory = _delivery_dir(repository_root)
    return directory / f"{operation_id}.out.log", directory / f"{operation_id}.err.log"


def _log_tail(path: Path, *, limit: int = LOG_TAIL_BYTES) -> dict[str, Any]:
    """Read a bounded tail from a Delivery-owned log without following symlinks."""

    if path.is_symlink() or not path.is_file():
        return {"available": False, "text": "", "truncated": False}
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - limit)
            handle.seek(start)
            payload = handle.read(limit)
    except OSError:
        return {"available": False, "text": "", "truncated": False}
    return {
        "available": True,
        "text": _redact_log_text(payload.decode("utf-8", errors="replace")),
        "truncated": start > 0,
    }


def _redact_log_text(text: str) -> str:
    """Keep common host/provider credentials out of the Delivery-visible tail."""

    redacted = text
    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        upper = name.upper()
        if not (
            upper.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
            or upper in {
                "DEEPSEEK_API_KEY", "ONTOLOGY_PLATFORM_ADMIN_API_KEY",
                "R3011_ACCEPTANCE_PLATFORM_READ_KEY",
            }
        ):
            continue
        redacted = redacted.replace(value, "[REDACTED_SECRET]")
    redacted = re.sub(
        r"(?i)([\"']?(?:plaintext_key|authorization)[\"']?\s*[:=]\s*[\"']?)"
        r"(?:(?:Bearer|Basic)[ \t]+)?[^\"'\s,}]+",
        r"\1[REDACTED_SECRET]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\bBearer[ \t]+[^\"'\s,}]+", "Bearer [REDACTED_SECRET]", redacted,
    )
    return redacted


def _record_owned_path(root: Path, relative: Any) -> Path | None:
    """Resolve a recorded relative artifact only when it stays under root."""

    if not isinstance(relative, str) or not relative:
        return None
    candidate = root / relative
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _repair_artifact_path(record: Mapping[str, Any], root: Path) -> Path:
    relative = record.get("result_artifact_path")
    if isinstance(relative, str) and relative:
        owned = _record_owned_path(root, relative)
        if owned is not None:
            return owned
    return _delivery_dir(root) / f"{record['operation_id']}.repair-result.json"


def _repair_diff_path(record: Mapping[str, Any], root: Path) -> Path:
    relative = record.get("repair_diff_path")
    if isinstance(relative, str) and relative:
        owned = _record_owned_path(root, relative)
        if owned is not None:
            return owned
    return _delivery_dir(root) / f"{record['operation_id']}.repair-result.patch"


def _repair_path_is_private(relative: Path) -> bool:
    value = relative.as_posix()
    return bool(
        any(part in REPAIR_PRIVATE_PATH_PARTS for part in relative.parts)
        or any(value == prefix or value.startswith(prefix + "/") for prefix in REPAIR_PRIVATE_PATH_PREFIXES)
    )


def _repair_metadata_error(code: str, detail: str, *, obj: str, next_action: str) -> HostOpError:
    return HostOpError(
        code,
        detail,
        obj=obj,
        retryable=True,
        next_action=next_action,
    )


def _read_repair_task_metadata(task_path: Path, authorization_reference: str) -> dict[str, Any]:
    """Read the small public scope manifest embedded by ``prepare_repair_task``.

    The task body remains stdin-only.  Only the first bounded lines are parsed
    for the existing JSON manifest; arbitrary task prose cannot grant a mount.
    """

    try:
        lines = task_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise _repair_metadata_error(
            "repair_task_invalid",
            f"repair_task_file is not readable as UTF-8: {exc}",
            obj="repair_task_file",
            next_action="regenerate the explicit repair task and retry with a new operation id",
        ) from exc
    metadata: dict[str, Any] | None = None
    for line in lines[:REPAIR_TASK_METADATA_SCAN_LINES]:
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "owned_paths" in candidate:
            metadata = candidate
            break
    if metadata is None:
        raise _repair_metadata_error(
            "repair_scope_missing",
            "repair task has no bounded owned_paths/source_references manifest",
            obj="repair_task_file",
            next_action="prepare the task through the Delivery repair scope helper",
        )
    if metadata.get("authorization_reference") != authorization_reference:
        raise _repair_metadata_error(
            "repair_authorization_mismatch",
            "repair task authorization_reference does not match the requested authorization",
            obj="authorization_reference",
            next_action="use the task produced under the active Delivery authorization",
        )
    source_references = metadata.get("source_references")
    owned_paths = metadata.get("owned_paths")
    if (
        not isinstance(source_references, list)
        or not source_references
        or any(not isinstance(value, str) or not value.strip() for value in source_references)
        or not isinstance(owned_paths, list)
        or not owned_paths
        or any(not isinstance(value, str) or not value.strip() for value in owned_paths)
    ):
        raise _repair_metadata_error(
            "repair_scope_invalid",
            "repair task must list non-empty source_references and owned_paths",
            obj="repair_task_file",
            next_action="regenerate the task with the exact public refs and owned files",
        )
    if len(set(source_references)) != len(source_references) or len(set(owned_paths)) != len(owned_paths):
        raise _repair_metadata_error(
            "repair_scope_invalid",
            "repair task source_references and owned_paths must be unique",
            obj="repair_task_file",
            next_action="remove duplicate repair scope entries",
        )
    return {
        "source_references": list(source_references),
        "owned_paths": list(owned_paths),
    }


def _validate_repair_scope(
    root: Path, metadata: Mapping[str, Any]
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """Resolve exact public refs and owned regular files for the namespace."""

    source_files: list[tuple[Path, str]] = []
    owned_files: list[tuple[Path, str]] = []
    for field, target in (("source_references", source_files), ("owned_paths", owned_files)):
        values = metadata.get(field)
        if not isinstance(values, list):
            raise _repair_metadata_error(
                "repair_scope_invalid",
                f"repair task {field} is not a list",
                obj=field,
                next_action="regenerate the task with explicit repository paths",
            )
        for value in values:
            try:
                path = resolve_repo_path(value, field=field, repository_root=root)
            except HostOpError as exc:
                raise _repair_metadata_error(
                    "repair_scope_invalid",
                    f"repair task {field} contains a path outside this checkout",
                    obj=field,
                    next_action="use only exact public or owned paths inside repository_root",
                ) from exc
            relative = path.relative_to(root)
            if _repair_path_is_private(relative):
                raise _repair_metadata_error(
                    "repair_scope_private",
                    f"repair task {field} points at a private Host path: {relative.as_posix()}",
                    obj=field,
                    next_action="remove workspaces, Delivery/evaluation, auth and git paths from the repair scope",
                )
            try:
                metadata_value = os.lstat(path)
            except OSError as exc:
                raise _repair_metadata_error(
                    "repair_scope_invalid",
                    f"repair task {field} path is unavailable: {relative.as_posix()}",
                    obj=field,
                    next_action="use an existing non-symlink regular file",
                ) from exc
            if not path.is_file() or path.is_symlink() or not os.path.isfile(path):
                raise _repair_metadata_error(
                    "repair_scope_invalid",
                    f"repair task {field} must name a non-symlink regular file: {relative.as_posix()}",
                    obj=field,
                    next_action="narrow the repair scope to individual files",
                )
            if metadata_value.st_uid != os.getuid():
                raise _repair_metadata_error(
                    "repair_scope_invalid",
                    f"repair task {field} path is not owned by this host user: {relative.as_posix()}",
                    obj=field,
                    next_action="use a file in the current checkout owned by the Delivery host",
                )
            if metadata_value.st_nlink != 1:
                raise _repair_metadata_error(
                    "repair_scope_invalid",
                    f"repair task {field} path has multiple hard links: {relative.as_posix()}",
                    obj=field,
                    next_action="use an ordinary checkout file without hard-link aliases",
                )
            target.append((path, relative.as_posix()))
    return source_files, owned_files


def _repair_stage(root: Path, operation_id: str) -> tuple[Path, Path, Path]:
    stage = _delivery_dir(root, create=True) / f"{operation_id}.repair"
    if stage.exists() or stage.is_symlink():
        raise HostOpError(
            "delivery_operation_exists",
            f"repair staging directory for {operation_id!r} already exists",
            obj="operation_id",
            retryable=False,
            next_action="use a new explicit Delivery operation id",
        )
    stage.mkdir(mode=0o700)
    home = stage / "codex-home"
    baseline = stage / "baseline"
    home.mkdir(mode=0o700)
    baseline.mkdir(mode=0o700)
    return stage, home, baseline


def _snapshot_repair_files(root: Path, baseline_root: Path, owned_files: list[tuple[Path, str]]) -> None:
    for source, relative in owned_files:
        destination = baseline_root / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o600)


def _read_repair_bytes(path: Path) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def _write_repair_diff_artifact(record: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Write a bounded diff for only the explicitly owned files."""

    relative_values = record.get("repair_owned_paths")
    baseline_value = record.get("repair_baseline_path")
    if not isinstance(relative_values, list) or not isinstance(baseline_value, str):
        return {"available": False, "changed_paths": [], "binary_paths": []}
    baseline_root = _record_owned_path(root, baseline_value)
    patch_path = _repair_diff_path(record, root)
    if baseline_root is None:
        return {"available": False, "changed_paths": [], "binary_paths": []}
    chunks: list[str] = []
    changed: list[str] = []
    binary: list[str] = []
    for value in relative_values:
        if not isinstance(value, str):
            continue
        relative = Path(value)
        before = _read_repair_bytes(baseline_root / relative)
        after = _read_repair_bytes(root / relative)
        if before == after:
            continue
        changed.append(value)
        if before is None or after is None or b"\0" in (before or b"") or b"\0" in (after or b""):
            binary.append(value)
            continue
        try:
            before_text = (before or b"").decode("utf-8").splitlines(keepends=True)
            after_text = (after or b"").decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            binary.append(value)
            continue
        chunks.extend(
            difflib.unified_diff(
                before_text,
                after_text,
                fromfile=f"a/{value}",
                tofile=f"b/{value}",
            )
        )
    payload = "".join(chunks).encode("utf-8")
    truncated = len(payload) > REPAIR_DIFF_MAX_BYTES
    payload = payload[:REPAIR_DIFF_MAX_BYTES]
    try:
        patch_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = patch_path.with_name(f".{patch_path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
        temporary.write_bytes(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, patch_path)
    except OSError:
        return {"available": False, "changed_paths": changed, "binary_paths": binary}
    return {
        "available": True,
        "path": _safe_relative(patch_path, root),
        "changed_paths": changed,
        "binary_paths": binary,
        "truncated": truncated,
        "bytes": len(payload),
    }


def _repair_evidence(record: Mapping[str, Any], repository_root: Path | None) -> dict[str, Any]:
    """Project bounded repair evidence and locators, never effectiveness."""

    root = _root(repository_root)
    logs = record.get("log_paths")
    logs = logs if isinstance(logs, Mapping) else {}
    stdout_path = _record_owned_path(root, logs.get("stdout"))
    stderr_path = _record_owned_path(root, logs.get("stderr"))
    stdout_tail = _log_tail(stdout_path) if stdout_path is not None else {
        "available": False,
        "text": "",
        "truncated": False,
    }
    stderr_tail = _log_tail(stderr_path) if stderr_path is not None else {
        "available": False,
        "text": "",
        "truncated": False,
    }
    artifact_path = _repair_artifact_path(record, root)
    diff_path = _repair_diff_path(record, root)
    try:
        artifact_relative = _safe_relative(artifact_path, root)
        diff_relative = _safe_relative(diff_path, root)
    except OSError:
        artifact_relative = str(artifact_path)
        diff_relative = str(diff_path)
    return {
        "log_tails": {"stdout": stdout_tail, "stderr": stderr_tail},
        # Flat aliases keep the result easy to consume by a Delivery session
        # while the nested representation remains extensible.
        "stdout_tail": stdout_tail["text"],
        "stderr_tail": stderr_tail["text"],
        "artifact_locators": {
            "operation_record": record.get("record_path"),
            "repair_task_file": record.get("request", {}).get("repair_task_file"),
            "stdout_log": logs.get("stdout"),
            "stderr_log": logs.get("stderr"),
            "repair_result": artifact_relative,
            "repair_diff": diff_relative,
        },
        "repair_result_artifact": {
            "path": artifact_relative,
            "available": artifact_path.is_file() and not artifact_path.is_symlink(),
        },
        "repair_diff_artifact": {
            "path": diff_relative,
            "available": diff_path.is_file() and not diff_path.is_symlink(),
        },
    }


def _write_repair_result_artifact(record_path: Path, record: Mapping[str, Any]) -> None:
    """Persist a bounded, explicit repair outcome artifact after process exit."""

    try:
        root = record_path.parent.parent
        artifact_path = _repair_artifact_path(record, root)
        diff = _write_repair_diff_artifact(record, root)
        evidence = _repair_evidence(record, root)
        payload = {
            "schema": "modeling-team-delivery-repair-result/v1",
            "operation_id": record.get("operation_id"),
            "status": record.get("status"),
            "exit_code": record.get("exit_code"),
            "started_at": record.get("started_at"),
            "ended_at": record.get("ended_at"),
            "request": record.get("request"),
            "effect_verified": False,
            "verification_required": True,
            "diff": diff,
            "evidence": evidence,
        }
        _write_record(artifact_path, payload)
        stage = _record_owned_path(root, record.get("repair_stage_path"))
        if stage is not None and stage != root and stage.name.endswith(".repair"):
            shutil.rmtree(stage, ignore_errors=True)
    except (OSError, TypeError, ValueError):
        # A missing result artifact is surfaced by get_repair_status; never
        # turn it into an effectiveness claim or hide the process exit.
        return


def _write_record(path: Path, payload: Mapping[str, Any], *, exclusive: bool = False) -> None:
    encoded = (json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    with _RECORD_LOCK:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if exclusive and path.exists():
                raise FileExistsError(path)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _read_record(operation_id: str, repository_root: Path | None) -> dict[str, Any]:
    path = _record_path(operation_id, repository_root)
    if path.is_symlink() or not path.is_file():
        raise HostOpError(
            "delivery_operation_not_found",
            f"no Delivery operation record exists for {operation_id!r}",
            obj="operation_id",
            retryable=False,
            next_action="use the operation_id returned by the matching start tool",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostOpError(
            "delivery_record_invalid",
            f"the Delivery operation record is unreadable: {exc}",
            obj="operation_id",
            retryable=False,
            next_action="retain the record and inspect its log evidence manually",
        ) from exc
    if not isinstance(value, dict) or value.get("schema") != DELIVERY_RECORD_SCHEMA:
        raise HostOpError(
            "delivery_record_invalid",
            "the Delivery operation record has an unsupported schema",
            obj="operation_id",
            retryable=False,
            next_action="use a fresh operation id after preserving the invalid record",
        )
    return value


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _validate_service_tier(value: str) -> str:
    if value not in SERVICE_TIERS:
        raise HostOpError(
            "delivery_argument_invalid",
            "service_tier must be 'unset', 'fast', or 'default'",
            obj="service_tier",
            retryable=True,
            next_action="pass the selected child service tier",
        )
    return value


def _child_env(service_tier: str) -> dict[str, str]:
    _validate_service_tier(service_tier)
    env = dict(os.environ)
    if service_tier == "fast":
        env["MODELING_TEAM_CODEX_SERVICE_TIER"] = "fast"
    elif service_tier == "default":
        env.pop("MODELING_TEAM_CODEX_SERVICE_TIER", None)
    return env


def _default_launcher(
    argv: list[str], *, cwd: Path, env: dict[str, str], stdin: Any, stdout: Any, stderr: Any
) -> subprocess.Popen[Any]:
    return subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )


def _spawn_reaper(process: Any, record_path: Path) -> None:
    def reap() -> None:
        try:
            return_code = process.wait()
        except Exception as exc:  # noqa: BLE001 - retain the observation for status
            return_code = None
            error = f"process wait failed: {exc}"
        else:
            error = None
        try:
            with _RECORD_LOCK:
                value = json.loads(record_path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    return
                stopped = bool(value.get("stop_requested_at"))
                value.update(
                    {
                        "status": "stopped" if stopped else "exited",
                        "exit_code": return_code,
                        "ended_at": _utc_now(),
                        "wait_error": error,
                    }
                )
                _write_record(record_path, value)
                if value.get("kind") == "repair":
                    _write_repair_result_artifact(record_path, value)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # The operation record itself remains the source of truth; a
            # missing reaper update is surfaced by the status call.
            return

    threading.Thread(target=reap, name="delivery-op-reaper", daemon=True).start()


def _launch_operation(
    *,
    operation_id: str,
    kind: str,
    argv: list[str],
    repository_root: Path | None,
    request: dict[str, Any],
    service_tier: str,
    stdin: Any = subprocess.DEVNULL,
    stdin_close: Any = None,
    launcher: Callable[..., Any] | None = None,
    launch_cwd: Path | None = None,
    launch_env: dict[str, str] | None = None,
    record_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = _root(repository_root)
    operation_id = _validate_operation_id(operation_id)
    directory = _delivery_dir(repository_root, create=True)
    record_path = directory / f"{operation_id}.json"
    if record_path.exists() or record_path.is_symlink():
        raise HostOpError(
            "delivery_operation_exists",
            f"Delivery operation {operation_id!r} already has a retained record",
            obj="operation_id",
            retryable=False,
            next_action="query the existing operation; use a new id for a retry",
        )
    stdout_path, stderr_path = _log_paths(operation_id, repository_root)
    started_at = _utc_now()
    record: dict[str, Any] = {
        "schema": DELIVERY_RECORD_SCHEMA,
        "operation_schema": EVALUATION_SCHEMA if kind == "evaluation" else REPAIR_SCHEMA,
        "operation_id": operation_id,
        "kind": kind,
        "argv": list(argv),
        "request": dict(request),
        "service_tier": service_tier,
        "status": "starting",
        "pid": None,
        "started_at": started_at,
        "ended_at": None,
        "exit_code": None,
        "log_paths": {
            "stdout": _safe_relative(stdout_path, root),
            "stderr": _safe_relative(stderr_path, root),
        },
        "record_path": _safe_relative(record_path, root),
    }
    if kind == "repair":
        record["result_artifact_path"] = _safe_relative(
            directory / f"{operation_id}.repair-result.json", root
        )
    if record_extra:
        record.update(dict(record_extra))
    if kind == "evaluation":
        run_root_value = request.get("run_root")
        mode_value = request.get("mode")
        if isinstance(run_root_value, str) and mode_value in EVALUATION_MODES:
            record["initial_reports"] = _report_snapshot(Path(run_root_value), str(mode_value))
    _write_record(record_path, record, exclusive=True)
    launch = _default_launcher if launcher is None else launcher
    out_handle = stdout_path.open("ab")
    err_handle = stderr_path.open("ab")
    try:
        process = launch(
            list(argv),
            cwd=root if launch_cwd is None else launch_cwd,
            env=_child_env(service_tier) if launch_env is None else dict(launch_env),
            stdin=stdin,
            stdout=out_handle,
            stderr=err_handle,
        )
    except Exception as exc:  # noqa: BLE001 - retain every launch failure
        record.update({"status": "launch_failed", "ended_at": _utc_now(), "error": str(exc)})
        _write_record(record_path, record)
        raise HostOpError(
            "delivery_launch_failed",
            f"the {kind} process could not be started: {exc}",
            obj="operation_id",
            retryable=False,
            next_action="inspect the retained Delivery stderr log; no retry was issued",
            passthrough={"record_path": record["record_path"], "log_paths": record["log_paths"]},
        ) from exc
    finally:
        out_handle.close()
        err_handle.close()
        if stdin_close is not None:
            stdin_close.close()
    pid = getattr(process, "pid", None)
    record.update({"status": "running", "pid": pid, "launched_at": _utc_now()})
    _write_record(record_path, record)
    _spawn_reaper(process, record_path)
    return {
        "operation_id": operation_id,
        "kind": kind,
        "status": "running",
        "pid": pid,
        "record_path": record["record_path"],
        "log_paths": record["log_paths"],
        "argv": list(argv),
        "request": dict(request),
        "note": "process launch is not evaluation/repair success; query the status tool",
    }


def _validate_timeout(value: float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise HostOpError(
            "delivery_argument_invalid",
            "session_timeout must be a positive number of seconds",
            obj="session_timeout",
            retryable=True,
            next_action="pass a positive CLI-supported session timeout",
        )
    return float(value)


def _report_snapshot(run_root: Path, mode: str) -> dict[str, dict[str, Any]]:
    candidates: list[Path] = []
    if mode == "cq-acceptance":
        for base in (
            run_root / "acceptance-v3" / "reports",
            run_root / "acceptance-v3" / "public-regression",
        ):
            if base.is_dir() and not base.is_symlink():
                candidates.extend(
                    path
                    for path in base.glob("**/batch-report.json")
                    if path.is_file() and not path.is_symlink()
                )
    elif mode == "public-feedback":
        base = run_root / "early-feedback"
        if base.is_dir() and not base.is_symlink():
            candidates.extend(
                path
                for path in base.glob("*/feedback.json")
                if path.is_file() and not path.is_symlink()
            )
    snapshot: dict[str, dict[str, Any]] = {}
    for path in candidates:
        try:
            raw = path.read_bytes()
            stat_result = path.stat()
        except OSError:
            continue
        snapshot[path.as_posix()] = {
            "digest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
        }
    return snapshot


def _new_reports(record: Mapping[str, Any]) -> list[tuple[Path, dict[str, Any], bool]]:
    run_root_value = record.get("request", {}).get("run_root")
    if not isinstance(run_root_value, str):
        return []
    run_root = Path(run_root_value)
    mode = str(record.get("request", {}).get("mode") or "")
    before = record.get("initial_reports")
    before = before if isinstance(before, Mapping) else {}
    current = _report_snapshot(run_root, mode)
    output: list[tuple[Path, dict[str, Any], bool]] = []
    for value, metadata in current.items():
        prior = before.get(value)
        # A report that existed before this operation is never eligible for
        # binding, even if its bytes changed.  The existing CLI publishes
        # reports immutably; treating a rewritten old path as this invocation's
        # success would make an unknown/late process look accepted.
        if not isinstance(prior, Mapping):
            output.append((Path(value), metadata, False))
    return output


def _load_report(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _load_frozen_snapshot(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read one Runner-owned frozen snapshot and verify its content digest."""

    if path.is_symlink() or not path.is_file():
        return None, None
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        return reload_frozen_pool(stored), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CQContractError, TypeError, ValueError) as exc:
        return None, str(exc)


def _published_freeze_digest(run_root: Path, freeze_id: str) -> str | None:
    """Read the same-run handoff digest when it names this batch identity."""

    path = run_root / "acceptance-v3" / "production-handoff.json"
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping) or value.get("freeze_id") != freeze_id:
        return None
    digest = value.get("freeze_digest")
    return digest if isinstance(digest, str) and digest else None


def _resolve_cq_freeze_snapshot(
    run_root: Path, freeze_id: str
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Resolve a CQ batch identity to the CLI's immutable snapshot stem.

    The Delivery request and handoff use the frozen batch id, while the CLI
    reads a file by its snapshot stem.  An explicit stem remains preferred for
    compatibility.  A batch id is translated only when exactly one valid
    snapshot in this run matches it; a same-run handoff digest may select one
    candidate deterministically.  Missing snapshots retain the old CLI
    failure path, while ambiguity is rejected instead of guessed.
    """

    frozen = run_root / "competency-questions" / "frozen"
    direct = frozen / f"{freeze_id}.json"
    if direct.is_file() and not direct.is_symlink():
        snapshot, error = _load_frozen_snapshot(direct)
        return freeze_id, snapshot, error

    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(frozen.glob("*.json")):
        if path.is_symlink() or not path.is_file() or not REFERENCE_PATTERN.fullmatch(path.stem):
            continue
        snapshot, _error = _load_frozen_snapshot(path)
        if snapshot is not None and snapshot.get("batch_id") == freeze_id:
            candidates.append((path, snapshot))
    if not candidates:
        return freeze_id, None, None

    expected_digest = _published_freeze_digest(run_root, freeze_id)
    if expected_digest is not None:
        candidates = [
            (path, snapshot)
            for path, snapshot in candidates
            if snapshot.get("snapshot_digest") == expected_digest
        ]
        if not candidates:
            raise HostOpError(
                "evaluation_argument_invalid",
                f"freeze_id {freeze_id!r} does not match the published freeze digest",
                obj="freeze_id",
                retryable=False,
                next_action="use the immutable freeze identity from the same run",
            )
    if len(candidates) != 1:
        raise HostOpError(
            "evaluation_argument_invalid",
            f"freeze_id {freeze_id!r} matches multiple frozen snapshots",
            obj="freeze_id",
            retryable=True,
            next_action="use the frozen snapshot stem or an unambiguous batch identity",
        )
    path, snapshot = candidates[0]
    return path.stem, snapshot, None


def _freeze_expectation(
    run_root: Path,
    freeze_id: str,
    *,
    question_visibility: str | None,
    resolve_batch_id: bool = False,
) -> dict[str, Any]:
    """Read the CLI's immutable freeze identity for report attribution.

    A missing freeze is left to the real CLI to reject, but a report produced
    without a readable freeze is never allowed to claim a stronger binding
    than the explicit ``freeze_id`` argument.  When the file exists, its
    digest, batch id and visibility-selected question ids become mandatory
    report fields.
    """

    expectation: dict[str, Any] = {
        "batch_id": freeze_id,
        "freeze_digest": None,
        "question_ids": None,
    }
    if resolve_batch_id:
        _cli_freeze_id, freeze, snapshot_error = _resolve_cq_freeze_snapshot(run_root, freeze_id)
    else:
        path = run_root / "competency-questions" / "frozen" / f"{freeze_id}.json"
        freeze, snapshot_error = _load_frozen_snapshot(path)
    if snapshot_error is not None:
        expectation["freeze_snapshot_error"] = snapshot_error
    if freeze is None:
        return expectation
    expectation["batch_id"] = freeze["batch_id"]
    expectation["freeze_digest"] = freeze["snapshot_digest"]
    if question_visibility in {"hidden", "public"}:
        by_id = {
            str(question["question_id"]): question
            for question in freeze["questions"]
            if isinstance(question, Mapping)
        }
        expectation["question_ids"] = [
            question_id
            for question_id in freeze["ordering"]
            if by_id.get(str(question_id), {}).get("visibility") == question_visibility
        ]
    return expectation


def _profile_digest(repository_root: Path, profile_id: str | None) -> str | None:
    if not profile_id:
        return None
    try:
        from .model_routing import load_team_model_profile

        return load_team_model_profile(repository_root, profile_id).digest
    except Exception:  # noqa: BLE001 - absence is reported as unverifiable metadata
        return None


def _run_profile_digest(run_root: Path, profile_id: str | None) -> str | None:
    """Recover the frozen profile digest when the checkout profile is absent.

    A retained run baseline is an existing host contract, not a new source of
    model identity.  The fallback keeps report binding strict for injected
    checkout roots used by Delivery tests and for archived run roots.
    """

    path = run_root / "baseline-manifest.json"
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    profile = value.get("team_model_profile") if isinstance(value, Mapping) else None
    if not isinstance(profile, Mapping):
        return None
    if profile_id is not None and profile.get("profile_id") not in {None, profile_id}:
        return None
    digest = profile.get("sha256")
    return digest if isinstance(digest, str) and digest else None


def _evaluation_request(
    *,
    run_root: Path,
    mode: str,
    freeze_id: str,
    question_visibility: str | None,
    checkpoint_id: str | None,
    question_ids: list[str],
    model_profile: str | None,
    repository_root: Path | None,
    runtime: str = "codex",
) -> dict[str, Any]:
    freeze = _freeze_expectation(
        run_root,
        freeze_id,
        question_visibility=question_visibility if mode == "cq-acceptance" else None,
        resolve_batch_id=mode == "cq-acceptance",
    )
    if mode == "public-feedback":
        freeze["question_ids"] = list(question_ids)
    expected_model_profile = model_profile or DEFAULT_EVALUATION_MODEL_PROFILE
    model_profile_digest = _profile_digest(_root(repository_root), expected_model_profile)
    if model_profile_digest is None:
        model_profile_digest = _run_profile_digest(run_root, expected_model_profile)
    return {
        "run_id": None,
        "run_root": str(run_root),
        "mode": mode,
        "freeze_id": freeze_id,
        "checkpoint_id": checkpoint_id,
        "question_ids": list(question_ids),
        "question_visibility": question_visibility,
        "model_profile": model_profile,
        "runtime": runtime,
        "report_expectations": {
            **freeze,
            "checkpoint_id": checkpoint_id,
            "question_visibility": question_visibility,
            "runtime": runtime,
            "model_profile": expected_model_profile,
            "model_profile_digest": model_profile_digest,
        },
    }


def _report_model_profile(report: Mapping[str, Any]) -> tuple[str | None, str | None]:
    model_id = report.get("model_profile") or report.get("model_profile_id")
    digest = report.get("effective_model_profile_digest") or report.get("model_profile_digest")
    sessions = report.get("sessions")
    if isinstance(sessions, Mapping):
        model_id = model_id or sessions.get("model_profile") or sessions.get("model_profile_id")
        digest = digest or sessions.get("effective_model_profile_digest") or sessions.get(
            "model_profile_digest"
        )
    return (
        model_id if isinstance(model_id, str) else None,
        digest if isinstance(digest, str) else None,
    )


def _report_binding_errors(record: Mapping[str, Any], report: Mapping[str, Any]) -> list[str]:
    request = record.get("request")
    request = request if isinstance(request, Mapping) else {}
    mode = request.get("mode")
    expected = request.get("report_expectations")
    expected = expected if isinstance(expected, Mapping) else {}
    errors: list[str] = []
    expected_runtime = expected.get("runtime", request.get("runtime", "codex"))
    observed_runtime = report.get("runtime")
    if observed_runtime is None and expected_runtime == "codex":
        observed_runtime = "codex"  # Historical Codex evidence remains readable.
    if observed_runtime != expected_runtime:
        errors.append("runtime_mismatch")

    if expected.get("freeze_snapshot_error"):
        errors.append("freeze_snapshot_unreadable")
    if mode == "cq-acceptance":
        # The CQ carrier always publishes the source run id.  A matching
        # batch/freeze by itself is insufficient: a report from another run
        # must never be attributed to this operation.
        if report.get("run_id") != request.get("run_id"):
            errors.append("run_id_mismatch")
        observed_batch = report.get("batch_id")
        if observed_batch != expected.get("batch_id"):
            errors.append(
                f"batch_id_mismatch(expected={expected.get('batch_id')!r}, observed={observed_batch!r})"
            )
        expected_digest = expected.get("freeze_digest")
        if expected_digest is not None and report.get("freeze_digest") != expected_digest:
            errors.append("freeze_digest_mismatch")
        selection = report.get("question_selection")
        if isinstance(selection, Mapping):
            observed_visibility = selection.get("visibility")
            observed_selection_ids = selection.get("question_ids")
        else:
            observed_visibility = "hidden"
            observed_selection_ids = None
        if observed_visibility != expected.get("question_visibility"):
            errors.append("question_visibility_mismatch")
        expected_ids = expected.get("question_ids")
        executed = report.get("executed_question_ids")
        unexecuted = report.get("unexecuted_question_ids")
        if not isinstance(executed, list) or (
            expected.get("question_ids") is not None and not isinstance(unexecuted, list)
        ):
            errors.append("question_ids_missing")
        else:
            actual_ids = executed + (unexecuted if isinstance(unexecuted, list) else [])
            if any(not isinstance(item, str) for item in actual_ids) or len(set(actual_ids)) != len(actual_ids):
                errors.append("question_ids_invalid")
            elif isinstance(expected_ids, list) and set(actual_ids) != set(expected_ids):
                errors.append("question_ids_mismatch")
        if expected.get("question_visibility") == "public":
            if not isinstance(observed_selection_ids, list) or set(observed_selection_ids) != set(expected_ids or []):
                errors.append("question_selection_mismatch")
    elif mode == "public-feedback":
        if report.get("run_id") != request.get("run_id"):
            errors.append("run_id_mismatch")
        if report.get("freeze_id") != request.get("freeze_id"):
            errors.append("freeze_id_mismatch")
        if report.get("checkpoint_id") != expected.get("checkpoint_id"):
            errors.append("checkpoint_id_mismatch")
        observed_ids = report.get("question_ids")
        expected_ids = expected.get("question_ids")
        if not isinstance(observed_ids, list) or observed_ids != expected_ids:
            errors.append("question_ids_mismatch")
        expected_digest = expected.get("freeze_digest")
        if expected_digest is not None and report.get("freeze_digest") != expected_digest:
            errors.append("freeze_digest_mismatch")
    else:
        errors.append("evaluation_mode_missing")

    expected_model = expected.get("model_profile")
    expected_model_digest = expected.get("model_profile_digest")
    observed_model, observed_digest = _report_model_profile(report)
    if expected_model is not None:
        if observed_model is None:
            # public-feedback's real record carries the effective profile
            # digest but no profile id; the digest is the binding there.
            if not (
                mode == "public-feedback"
                and expected_model_digest is not None
                and observed_digest == expected_model_digest
            ):
                errors.append("model_profile_missing")
        elif observed_model != expected_model:
            errors.append("model_profile_mismatch")
    # The current CQ CLI records the profile id but does not publish a profile
    # digest in its batch report.  If a report carries a digest (as public
    # feedback does, or as a future CQ report may), it is still authoritative
    # and must agree; a same-named profile cannot launder a wrong digest.
    if expected_model_digest is not None and observed_digest is not None and observed_digest != expected_model_digest:
        errors.append("model_profile_digest_mismatch")
    if mode == "public-feedback" and expected_model_digest is not None and observed_digest is None:
        errors.append("model_profile_digest_missing")
    return errors


def _report_summary(mode: str, report: Mapping[str, Any]) -> dict[str, Any]:
    if mode == "cq-acceptance":
        executed = report.get("executed_question_ids")
        verdicts = report.get("verdicts")
        executed_ids = list(executed) if isinstance(executed, list) else []
        verdict_list = list(verdicts) if isinstance(verdicts, list) else []
        valid = sum(
            1
            for item in verdict_list
            if isinstance(item, Mapping) and item.get("verdict") in REPORT_VERDICTS
        )
        return {
            "status": report.get("status"),
            "full_pass": report.get("full_pass"),
            "executed_question_ids": executed_ids,
            "executed_question_count": len(executed_ids),
            "verdict_count": len(verdict_list),
            "valid_verdict_count": valid,
            "freeze_id": report.get("batch_id"),
            "freeze_digest": report.get("freeze_digest"),
        }
    reports = report.get("reports")
    report_list = list(reports) if isinstance(reports, list) else []
    valid = sum(
        1
        for item in report_list
        if isinstance(item, Mapping) and item.get("status") == "completed" and not item.get("explicit_unknown")
    )
    return {
        "status": report.get("status"),
        "formal_acceptance": report.get("formal_acceptance"),
        "question_ids": list(report.get("question_ids") or []),
        "report_count": len(report_list),
        "valid_report_count": valid,
        "freeze_id": report.get("freeze_id"),
        "freeze_digest": report.get("freeze_digest"),
    }


def _request_report_visibility(record: Mapping[str, Any]) -> str | None:
    """The question visibility this operation's cq-acceptance request bound."""

    request = record.get("request")
    request = request if isinstance(request, Mapping) else {}
    if request.get("mode") != "cq-acceptance":
        return None
    expected = request.get("report_expectations")
    expected = expected if isinstance(expected, Mapping) else {}
    visibility = expected.get("question_visibility")
    return visibility if visibility in {"hidden", "public"} else None


def _report_visibility(report: Mapping[str, Any]) -> str:
    """A report's own visibility claim (legacy reports default to hidden)."""

    selection = report.get("question_selection")
    if isinstance(selection, Mapping):
        visibility = selection.get("visibility")
        if visibility in {"hidden", "public"}:
            return str(visibility)
    return "hidden"


def _eligible_report_candidates(
    record: Mapping[str, Any],
) -> tuple[list[tuple[Path, dict[str, Any], bool]], list[dict[str, Any]]]:
    """Split new reports into this-operation candidates and out-of-scope ones.

    A cq-acceptance operation binds only a report published for its own
    requested question visibility; a readable report whose visibility differs
    (for example a public regression report published while this operation
    runs the hidden set) belongs to another operation and is never selected or
    attributed here.  Unreadable reports cannot be classified and stay
    candidates, preserving the refuse-to-guess ambiguity contract, and a
    same-visibility report with a foreign run/freeze identity is still bound
    and then rejected by ``_report_binding_errors``.
    """

    expected_visibility = _request_report_visibility(record)
    candidates: list[tuple[Path, dict[str, Any], bool]] = []
    excluded: list[dict[str, Any]] = []
    for path, metadata, preexisted in _new_reports(record):
        report = _load_report(path)
        if (
            expected_visibility is not None
            and report is not None
            and _report_visibility(report) != expected_visibility
        ):
            excluded.append(
                {
                    "path": path.as_posix(),
                    "digest": metadata.get("digest"),
                    "visibility": _report_visibility(report),
                }
            )
            continue
        candidates.append((path, metadata, preexisted))
    return candidates, excluded


def _bind_report(
    record: dict[str, Any],
    candidates: list[tuple[Path, dict[str, Any], bool]] | None = None,
) -> dict[str, Any] | None:
    if candidates is None:
        candidates, _excluded = _eligible_report_candidates(record)
    if not candidates:
        return None
    # The CLI writes one authoritative report per invocation.  If a malformed
    # or concurrent process leaves multiple new files, refuse to guess which
    # one belongs to this operation.
    if len(candidates) != 1:
        return None
    candidates = sorted(candidates, key=lambda item: item[0].as_posix())
    path, metadata, preexisted = candidates[0]
    report = _load_report(path)
    run_root = Path(str(record["request"]["run_root"]))
    repository_root = run_root.parents[2] if len(run_root.parents) >= 3 else run_root.parent
    binding = {
        "path": _safe_relative(path, repository_root),
        "absolute_path": path.as_posix(),
        "digest": metadata["digest"],
        "observed_at": _utc_now(),
        "preexisted": preexisted,
        "readable": report is not None,
        "candidate_count": len(candidates),
    }
    if report is not None:
        validation_errors = _report_binding_errors(record, report)
        binding["valid"] = not validation_errors
        binding["validation_errors"] = validation_errors
        summary = _report_summary(str(record["request"]["mode"]), report)
        if validation_errors:
            # Keep the reported value as evidence, but never project an
            # unbound report's PASS as the Delivery operation's outcome.
            if "full_pass" in summary:
                summary["reported_full_pass"] = summary.get("full_pass")
                summary["full_pass"] = None
            if "formal_acceptance" in summary:
                summary["reported_formal_acceptance"] = summary.get("formal_acceptance")
                summary["formal_acceptance"] = None
        binding["summary"] = summary
    else:
        binding["valid"] = False
        binding["validation_errors"] = ["report_unreadable"]
    return binding


def _refresh_evaluation_record(record: dict[str, Any]) -> dict[str, Any]:
    binding = record.get("report_binding")
    if not isinstance(binding, Mapping):
        candidates, excluded = _eligible_report_candidates(record)
        if excluded:
            # Retained host-side evidence that a foreign-visibility report was
            # published in this window; it is never this operation's report.
            record["excluded_report_candidates"] = excluded
        bound = _bind_report(record, candidates) if len(candidates) == 1 else None
        if bound is not None:
            record["report_binding"] = bound
            record["report_status"] = (
                "new_report_bound" if bound.get("valid") is True else "new_report_rejected"
            )
        elif len(candidates) > 1:
            record["report_status"] = "ambiguous_new_reports"
            record["report_candidates"] = [
                {
                    "path": path.as_posix(),
                    "digest": metadata.get("digest"),
                }
                for path, metadata, _preexisted in candidates
            ]
    return record


def validate_evaluation_runtime(runtime, model_profile, service_tier, *, mode, repository_root):
    from .model_routing import load_team_model_profile, TeamModelProfileError
    from .runtimes.acceptance import validate_acceptance_profile

    try:
        if runtime not in {"codex", "dsh"}:
            raise TeamModelProfileError("runtime must be codex or dsh")
        if runtime == "dsh":
            if not model_profile:
                raise TeamModelProfileError("acceptance-model-binding-missing: explicit DSH model_profile required")
            profile = load_team_model_profile(_root(repository_root), model_profile)
            validate_acceptance_profile(runtime, profile, judge=mode != "public-feedback", service_tier=service_tier)
    except TeamModelProfileError as exc:
        raise HostOpError("evaluation_runtime_invalid", str(exc), obj="runtime/model_profile/service_tier",
            retryable=True, next_action="correct the explicit acceptance runtime and role bindings") from exc


def start_evaluation(
    *,
    run_id: str,
    operation_id: str,
    mode: str,
    freeze_id: str,
    model_handoff: str | None = None,
    checkpoint_id: str | None = None,
    question_ids: list[str] | None = None,
    question_visibility: str | None = None,
    model_profile: str | None = None,
    runtime: str = "codex",
    session_timeout: float | int | None = None,
    service_tier: str = "unset",
    repository_root: Path | None = None,
    launcher: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Launch the existing ``cq-acceptance`` or ``public-feedback`` CLI."""

    operation_id = _validate_operation_id(operation_id)
    if mode not in EVALUATION_MODES:
        raise HostOpError(
            "evaluation_mode_invalid",
            "mode must be 'cq-acceptance' or 'public-feedback'",
            obj="mode",
            retryable=True,
            next_action="choose one of the two existing evaluation CLI entry points",
        )
    _safe_ref(run_id, "run_id")
    freeze_id = _safe_ref(freeze_id, "freeze_id")
    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    timeout = _validate_timeout(session_timeout)
    _validate_service_tier(service_tier)
    validate_evaluation_runtime(runtime, model_profile, service_tier, mode=mode, repository_root=repository_root)
    if model_profile is not None:
        model_profile = _safe_ref(model_profile, "model_profile")
    if question_visibility is None and mode == "cq-acceptance":
        question_visibility = "hidden"
    if mode == "cq-acceptance":
        if question_visibility not in {"hidden", "public"}:
            raise HostOpError(
                "evaluation_argument_invalid",
                "cq-acceptance question_visibility must be 'hidden' or 'public'",
                obj="question_visibility",
                retryable=True,
                next_action="pass a CLI-supported CQ visibility",
            )
        if checkpoint_id is not None or question_ids is not None:
            raise HostOpError(
                "evaluation_argument_invalid",
                "checkpoint_id and question_ids belong to public-feedback only",
                obj="mode",
                retryable=True,
                next_action="remove public-feedback-only arguments",
            )
        handoff_path = resolve_repo_path(
            model_handoff, field="model_handoff", repository_root=repository_root
        ) if model_handoff is not None else None
        if handoff_path is None or not handoff_path.is_file() or handoff_path.is_symlink():
            raise HostOpError(
                "evaluation_argument_invalid",
                "cq-acceptance requires an existing non-symlink model_handoff file",
                obj="model_handoff",
                retryable=True,
                next_action="pass the current Runner-published handoff file",
            )
        model_handoff_value = handoff_path
    else:
        if question_visibility is not None:
            raise HostOpError(
                "evaluation_argument_invalid",
                "public-feedback has no question_visibility CLI argument",
                obj="question_visibility",
                retryable=True,
                next_action="omit question_visibility for public-feedback",
            )
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            raise HostOpError(
                "evaluation_argument_invalid",
                "public-feedback requires checkpoint_id",
                obj="checkpoint_id",
                retryable=True,
                next_action="pass the explicit checkpoint id",
            )
        checkpoint_id = _safe_ref(checkpoint_id, "checkpoint_id")
        if not isinstance(question_ids, list) or not question_ids or any(
            not isinstance(item, str) or not item.strip() or "/" in item or "\\" in item
            for item in question_ids
        ) or len(set(question_ids)) != len(question_ids):
            raise HostOpError(
                "evaluation_argument_invalid",
                "public-feedback requires a non-empty unique question_ids list",
                obj="question_ids",
                retryable=True,
                next_action="pass the approved public question ids exactly once",
            )
        if model_handoff is not None:
            raise HostOpError(
                "evaluation_argument_invalid",
                "model_handoff belongs to cq-acceptance only",
                obj="model_handoff",
                retryable=True,
                next_action="remove model_handoff for public-feedback",
            )
        model_handoff_value = None
    cli_freeze_id = freeze_id
    if mode == "cq-acceptance":
        cli_freeze_id, _freeze, _snapshot_error = _resolve_cq_freeze_snapshot(run_root, freeze_id)
    argv = [
        sys.executable,
        "-m",
        "modeling_team",
        mode,
        "--run-root",
        str(run_root),
        "--freeze-id",
        cli_freeze_id,
    ]
    if mode == "cq-acceptance":
        argv.extend(["--model-handoff", str(model_handoff_value), "--question-visibility", str(question_visibility)])
    else:
        argv.extend(["--checkpoint-id", str(checkpoint_id)])
        for question_id in question_ids or []:
            argv.extend(["--question-id", question_id])
    argv.extend(["--runtime", runtime])
    if model_profile is not None:
        argv.extend(["--model-profile", model_profile])
    if timeout is not None:
        argv.extend(["--session-timeout", str(timeout)])
    if mode == "cq-acceptance":
        argv.extend(["--owner-root", str(_delivery_dir(repository_root) / (operation_id + ".owner"))])
    request = _evaluation_request(
        run_root=run_root,
        mode=mode,
        freeze_id=freeze_id,
        question_visibility=question_visibility,
        checkpoint_id=checkpoint_id,
        question_ids=list(question_ids or []),
        model_profile=model_profile,
        runtime=runtime,
        repository_root=repository_root,
    )
    request.update(
        {
            "run_id": run_id,
            "model_handoff": str(model_handoff_value) if model_handoff_value is not None else None,
            "session_timeout": timeout,
        }
    )
    result = _launch_operation(
        operation_id=operation_id,
        kind="evaluation",
        argv=argv,
        repository_root=repository_root,
        request=request,
        service_tier=service_tier,
        launcher=launcher,
        launch_env=_child_env("default" if runtime == "dsh" else service_tier),
    )
    record = _read_record(operation_id, repository_root)
    result["initial_report_count"] = len(record.get("initial_reports") or {})
    return result


def get_evaluation_status(
    *, operation_id: str, repository_root: Path | None = None
) -> dict[str, Any]:
    """Observe one evaluation, its bounded log tails and its report binding."""

    record_path = _record_path(operation_id, repository_root)
    with _RECORD_LOCK:
        record = _read_record(operation_id, repository_root)
        if record.get("kind") != "evaluation":
            raise HostOpError(
                "delivery_operation_kind_mismatch",
                f"operation {operation_id!r} is not an evaluation operation",
                obj="operation_id",
                retryable=False,
                next_action="use get_repair_status for repair operations",
            )
        record = _refresh_evaluation_record(record)
        # The existing CLIs publish their report after the worker/session has
        # finished and may briefly leave the reaper/status update ahead of the
        # atomic report rename.  A status read remains read-only, but a small
        # bounded observation window avoids returning ``no_new_report`` for a
        # report that is already being published by this operation.  The
        # pre-launch snapshot is still the only basis for eligibility, so an
        # older rewritten report can never become a new success.
        if record.get("report_binding") is None and record.get("status") in {
            "starting",
            "running",
            "exited",
        }:
            deadline = time.monotonic() + 0.15
            while time.monotonic() < deadline:
                time.sleep(0.01)
                record = _refresh_evaluation_record(record)
                if record.get("report_binding") is not None or record.get("report_status") == "ambiguous_new_reports":
                    break
        _write_record(record_path, record)
    binding = record.get("report_binding")
    report_status = record.get("report_status")
    if report_status not in {
        "new_report_bound",
        "new_report_rejected",
        "ambiguous_new_reports",
    }:
        report_status = "no_new_report"
    owner_path = _delivery_dir(repository_root) / (operation_id + ".owner") / "state.json"
    try:
        owner = json.loads(owner_path.read_text())
        if owner.get("owner_pid") != record.get("pid"):
            owner = None
    except (OSError, ValueError):
        owner = None
    stdout_path, stderr_path = _log_paths(operation_id, repository_root)
    log_tails = {"stdout": _log_tail(stdout_path), "stderr": _log_tail(stderr_path)}
    return {
        "operation_id": operation_id,
        "kind": "evaluation",
        "run_id": record["request"].get("run_id"),
        "mode": record["request"].get("mode"),
        "status": record.get("status"),
        "pid": record.get("pid"),
        "exit_code": record.get("exit_code"),
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "request_binding": record.get("request"),
        "report_status": report_status,
        "report_binding": binding,
        "work_state": "completed" if owner and owner.get("task_closed") else "working",
        "lifecycle": owner.get("lifecycle") if owner else "unknown",
        "retained_members": owner.get("retained_members", []) if owner else [],
        "current_role": owner.get("current") if owner else None,
        "control_receipts": owner.get("receipts", {}) if owner else {},
        "consult_replies": owner.get("consult_replies", []) if owner else [],
        "logs": record.get("log_paths"),
        "log_tails": log_tails,
        "stdout_tail": log_tails["stdout"]["text"],
        "stderr_tail": log_tails["stderr"]["text"],
        "record_path": record.get("record_path"),
        "note": "a process exit and a new report do not by themselves prove semantic acceptance",
    }


def _repair_child_env(service_tier: str) -> dict[str, str]:
    """Environment visible to the bwrap process before its clearenv boundary."""

    _validate_service_tier(service_tier)
    values = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    for key in REPAIR_PROXY_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            values[key] = value
    if service_tier == "fast":
        values["MODELING_TEAM_CODEX_SERVICE_TIER"] = "fast"
    return values


def _repair_namespace_command(
    *,
    root: Path,
    codex_binary: Path,
    companion: Path | None,
    home: Path,
    source_files: list[tuple[Path, str]],
    owned_files: list[tuple[Path, str]],
    model: str,
    effort: str,
    service_tier: str,
) -> list[str]:
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise HostOpError(
            "repair_isolation_unavailable",
            "bubblewrap is required for an isolated Codex repair",
            obj="executor",
            retryable=True,
            next_action="enable the existing Host bubblewrap runtime; no repair process was started",
        )
    command = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--clearenv",
    ]
    for system_path in (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ld.so.cache",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/nsswitch.conf",
        "/etc/ssl/certs",
    ):
        if Path(system_path).exists():
            command.extend(["--ro-bind", system_path, system_path])
    command.extend(
        [
            "--dir",
            "/agent",
            "--dir",
            "/agent/bin",
            "--bind",
            str(home),
            "/agent/home",
            "--ro-bind",
            str(codex_binary),
            "/agent/bin/codex",
            "--dir",
            "/workspace",
        ]
    )
    if companion is not None:
        command.extend(["--ro-bind", str(companion), "/agent/bin/codex-code-mode-host"])

    mounted_code_roots: list[str] = []
    for relative_root in REPAIR_PUBLIC_CODE_ROOTS:
        source = root / relative_root
        if source.is_symlink() or not source.exists():
            continue
        destination = f"/workspace/{relative_root}"
        command.extend(["--ro-bind", str(source), destination])
        mounted_code_roots.append(relative_root)

    def add_parent_dirs(relative: str) -> None:
        parts = Path(relative).parts
        for index in range(1, len(parts)):
            parent = Path(*parts[:index]).as_posix()
            if any(parent == root_name or parent.startswith(root_name + "/") for root_name in mounted_code_roots):
                continue
            command.extend(["--dir", f"/workspace/{parent}"])

    # Each public reference is mounted as its own file.  No parent docs/source
    # directory is exposed just because one file was cited.
    for source, relative in source_files:
        add_parent_dirs(relative)
        command.extend(["--ro-bind", str(source), f"/workspace/{relative}"])
    # RW binds come last so an explicitly owned source file overrides the
    # matching public RO code bind without exposing its siblings.
    for source, relative in owned_files:
        add_parent_dirs(relative)
        command.extend(["--bind", str(source), f"/workspace/{relative}"])

    env_values = {
        "CODEX_HOME": "/agent/home",
        "HOME": "/agent/home",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    for key in REPAIR_PROXY_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            env_values[key] = value
    if service_tier == "fast":
        env_values["MODELING_TEAM_CODEX_SERVICE_TIER"] = "fast"
    for key, value in env_values.items():
        command.extend(["--setenv", key, value])
    command.extend(
        [
            "--chdir",
            "/workspace",
            "--",
            "/agent/bin/codex",
            "--ask-for-approval",
            "never",
            "exec",
            # /workspace is a scoped file view; Host .git stays outside it.
            "--skip-git-repo-check",
            "--json",
            "--sandbox",
            "workspace-write",
            "--model",
            model,
            "-c",
            f"model_reasoning_effort={effort}",
            "-",
        ]
    )
    return command


def _prepare_codex_repair_auth(home: Path) -> None:
    try:
        from .model_routing import codex_auth_cache_path, preflight_codex_subscription_auth

        preflight_codex_subscription_auth()
        source = codex_auth_cache_path()
        destination = home / "auth.json"
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o600)
    except Exception as exc:  # noqa: BLE001 - provider auth details stay private
        raise HostOpError(
            "repair_isolation_unavailable",
            "Codex subscription auth could not be staged into the private repair HOME",
            obj="executor",
            retryable=True,
            next_action="restore the existing private Codex subscription auth; no repair process was started",
        ) from exc


def start_repair(
    *,
    operation_id: str,
    repair_task_file: str,
    executor: str,
    model: str,
    effort: str,
    authorization_reference: str,
    issue_id: str | None = None,
    service_tier: str = "unset",
    repository_root: Path | None = None,
    launcher: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Launch one explicitly authorized, namespace-isolated repair task.

    The first supported isolated executor is Codex.  Claude remains a typed
    unavailable path until its runtime and authentication can be proven to
    obey the same boundary; it is never silently downgraded to a host-cwd
    launch.
    """

    operation_id = _validate_operation_id(operation_id)
    if executor not in {"codex", "claude"}:
        raise HostOpError(
            "repair_executor_invalid",
            "executor must be 'codex' or 'claude'",
            obj="executor",
            retryable=True,
            next_action="choose the explicitly authorized repair executor",
        )
    model = _nonempty(model, "model", max_length=256)
    if effort not in EFFORTS or (executor == "claude" and effort == "none"):
        raise HostOpError(
            "repair_effort_invalid",
            "effort must be a supported model effort (Claude excludes 'none')",
            obj="effort",
            retryable=True,
            next_action="pass the selected executor's supported effort",
        )
    authorization_reference = _nonempty(authorization_reference, "authorization_reference")
    if issue_id is not None:
        issue_id = _safe_ref(issue_id, "issue_id")
    _validate_service_tier(service_tier)
    if executor == "claude":
        raise HostOpError(
            "repair_isolation_unavailable",
            "Claude repair isolation and independent authentication are not proven on this Host",
            obj="executor",
            retryable=True,
            next_action="select the supported isolated Codex executor or provide a separately proven Claude sandbox",
        )
    task_path = resolve_repo_path(
        repair_task_file, field="repair_task_file", repository_root=repository_root
    )
    if task_path.is_symlink() or not task_path.is_file():
        raise HostOpError(
            "repair_task_invalid",
            "repair_task_file must be an existing non-symlink regular file",
            obj="repair_task_file",
            retryable=True,
            next_action="write the explicit repair-task file inside this checkout",
        )
    try:
        task_digest = f"sha256:{hashlib.sha256(task_path.read_bytes()).hexdigest()}"
    except OSError as exc:
        raise HostOpError(
            "repair_task_invalid",
            f"repair_task_file could not be read: {exc.strerror or exc}",
            obj="repair_task_file",
            retryable=True,
            next_action="check the task file and retry with a new operation id",
        ) from exc
    root = _root(repository_root)
    metadata = _read_repair_task_metadata(task_path, authorization_reference)
    source_files, owned_files = _validate_repair_scope(root, metadata)
    executable = shutil.which("codex")
    if executable is None:
        raise HostOpError(
            "repair_isolation_unavailable",
            "the Codex executable is not available for an isolated repair",
            obj="executor",
            retryable=True,
            next_action="install/enable the existing local Codex runtime; no repair process was started",
        )
    codex_binary = Path(executable).resolve()
    try:
        codex_metadata = os.lstat(codex_binary)
    except OSError as exc:
        raise HostOpError(
            "repair_isolation_unavailable",
            "the resolved Codex executable cannot be inspected",
            obj="executor",
            retryable=True,
            next_action="restore the existing local Codex runtime; no repair process was started",
        ) from exc
    if not codex_binary.is_file() or not os.access(codex_binary, os.X_OK) or codex_metadata.st_uid != os.getuid():
        raise HostOpError(
            "repair_isolation_unavailable",
            "the resolved Codex executable is not a regular executable owned by this Host user",
            obj="executor",
            retryable=True,
            next_action="restore the existing local Codex runtime; no repair process was started",
        )
    companion = codex_binary.parent / "codex-code-mode-host"
    if companion.is_symlink() or not companion.is_file() or not os.access(companion, os.X_OK):
        companion = None

    stage, home, baseline = _repair_stage(root, operation_id)
    try:
        _snapshot_repair_files(root, baseline, owned_files)
        if launcher is None:
            _prepare_codex_repair_auth(home)
        argv = _repair_namespace_command(
            root=root,
            codex_binary=codex_binary,
            companion=companion,
            home=home,
            source_files=source_files,
            owned_files=owned_files,
            model=model,
            effort=effort,
            service_tier=service_tier,
        )
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    request = {
        "repair_task_file": _safe_relative(task_path, root),
        "repair_task_digest": task_digest,
        "executor": executor,
        "model": model,
        "effort": effort,
        "authorization_reference": authorization_reference,
        "issue_id": issue_id,
        "source_references": [relative for _path, relative in source_files],
        "owned_paths": [relative for _path, relative in owned_files],
        "isolation": "bwrap-codex-v1",
    }
    directory = _delivery_dir(root)
    record_extra = {
        "repair_owned_paths": [relative for _path, relative in owned_files],
        "repair_baseline_path": _safe_relative(baseline, root),
        "repair_diff_path": _safe_relative(directory / f"{operation_id}.repair-result.patch", root),
        "repair_stage_path": _safe_relative(stage, root),
    }
    with task_path.open("rb") as task_handle:
        try:
            result = _launch_operation(
                operation_id=operation_id,
                kind="repair",
                argv=argv,
                repository_root=repository_root,
                request=request,
                service_tier=service_tier,
                stdin=task_handle,
                stdin_close=None,
                launcher=launcher,
                launch_cwd=stage,
                launch_env=_repair_child_env(service_tier),
                record_extra=record_extra,
            )
        except Exception:
            # A failed launch leaves the operation record/logs as evidence but
            # must not leave staged credentials or a writable repair staging
            # tree behind.
            shutil.rmtree(stage, ignore_errors=True)
            raise
    result.update(
        {
            "repair_task_file": request["repair_task_file"],
            "repair_task_digest": task_digest,
            "executor": executor,
            "model": model,
            "effort": effort,
            "isolation": "bwrap-codex-v1",
            "owned_paths": request["owned_paths"],
        }
    )
    return result


def get_repair_status(
    *, operation_id: str, repository_root: Path | None = None
) -> dict[str, Any]:
    """Observe repair process/log evidence without claiming code effectiveness."""

    record = _read_record(operation_id, repository_root)
    if record.get("kind") != "repair":
        raise HostOpError(
            "delivery_operation_kind_mismatch",
            f"operation {operation_id!r} is not a repair operation",
            obj="operation_id",
            retryable=False,
            next_action="use get_evaluation_status for evaluation operations",
        )
    exit_code = record.get("exit_code")
    current_status = record.get("status")
    outcome = (
        "running"
        if current_status in {"starting", "running", "stop_requested"}
        else "stopped"
        if current_status == "stopped"
        else "completed"
        if exit_code == 0
        else "failed"
    )
    if current_status not in {"starting", "running", "stop_requested"}:
        artifact_path = _repair_artifact_path(record, _root(repository_root))
        if not artifact_path.is_file() or artifact_path.is_symlink():
            _write_repair_result_artifact(_record_path(operation_id, repository_root), record)
    evidence = _repair_evidence(record, repository_root)
    return {
        "operation_id": operation_id,
        "kind": "repair",
        "status": record.get("status"),
        "outcome": outcome,
        "pid": record.get("pid"),
        "exit_code": exit_code,
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "request_binding": record.get("request"),
        "logs": record.get("log_paths"),
        "record_path": record.get("record_path"),
        **evidence,
        "effect_verified": False,
        "verification": {
            "required": True,
            "note": "executor exit/text is not proof that the repair is effective; inspect diff, tests, and runtime separately",
        },
    }


def _proc_command(pid: int) -> list[str] | None:
    path = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    values = [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]
    return values or None


def _recorded_process_commands(argv: list[Any]) -> tuple[list[str], ...]:
    """Accept the bwrap command or its exact post-``--`` exec argv."""

    candidates: list[list[str]] = [list(argv)]
    if "--" in argv:
        separator = argv.index("--")
        child = argv[separator + 1 :]
        if child:
            candidates.append(child)
    return tuple(candidates)


def relay_evaluation_message(*, operation_id: str, action: str, text: str,
                             request_id: str | None = None,
                             repository_root: Path | None = None) -> dict[str, Any]:
    """Relay sourced controls to the operation's original owner/current role."""
    import uuid
    from .host_ops import _write_fifo_line
    operation_id = _validate_operation_id(operation_id)
    record = _read_record(operation_id, repository_root)
    if record.get("kind") != "evaluation" or action not in {"consult", "pause", "resume", "stop"}:
        raise HostOpError("evaluation_control_invalid", "select a cooperative evaluation action", obj="action",
                          retryable=True, next_action="use consult, pause, resume, or stop on an evaluation")
    text = _nonempty(text, "text", max_length=32_000)
    request_id = _validate_operation_id(request_id or str(uuid.uuid4()))
    owner_root = _delivery_dir(repository_root) / (operation_id + ".owner")
    try:
        owner = json.loads((owner_root / "state.json").read_text())
    except (OSError, ValueError):
        raise HostOpError("evaluation_owner_unavailable", "original owner is not online", obj=operation_id,
                          retryable=True, next_action="query evaluation status; no new owner is started")
    if owner.get("owner_pid") != record.get("pid"):
        raise HostOpError("evaluation_owner_mismatch", "owner identity differs", obj=operation_id,
                          retryable=False, next_action="preserve the operation evidence")
    message = {"request_id": request_id, "action": action, "text": text}
    ledger = owner_root / ("request-" + request_id + ".json")
    if ledger.exists():
        previous = json.loads(ledger.read_text())
        if previous["message"] != message:
            raise HostOpError("request_identity_conflict", "keep the original request payload", obj=request_id,
                              retryable=False, next_action="use a new ID for a new message")
        return {"request_id": request_id, **owner.get("receipts", {}).get(request_id, {"status": previous["status"]})}
    _write_record(ledger, {"message": message, "status": "unknown"}, exclusive=True)
    _write_fifo_line(owner_root / "input.fifo", (json.dumps(message, ensure_ascii=False) + "\n").encode())
    _write_record(ledger, {"message": message, "status": "submitted"})
    return {"request_id": request_id, "status": "submitted", "next_action": "get_evaluation_status"}


def stop_delivery_operation(
    *, operation_id: str, reason: str, repository_root: Path | None = None
) -> dict[str, Any]:
    """Stop one owned evaluation/repair process after command verification.

    The operation record and logs remain intact.  The PID and process group
    are checked against the recorded argv before a signal is sent, so an
    unrelated process cannot be stopped through a stale or forged id.
    """

    operation_id = _validate_operation_id(operation_id)
    reason = _nonempty(reason, "reason", max_length=2048)
    owner_root = _delivery_dir(repository_root) / (operation_id + ".owner")
    if (owner_root / "input.fifo").exists():
        result = relay_evaluation_message(operation_id=operation_id, action="stop", text=reason,
                                          repository_root=repository_root)
        return {"operation_id": operation_id, "stop_status": "requested", "evidence_retained": True, **result}
    record_path = _record_path(operation_id, repository_root)
    with _RECORD_LOCK:
        record = _read_record(operation_id, repository_root)
        kind = record.get("kind")
        if kind not in {"evaluation", "repair"}:
            raise HostOpError(
                "delivery_operation_kind_mismatch",
                f"operation {operation_id!r} is outside the evaluation/repair stop boundary",
                obj="operation_id",
                retryable=False,
                next_action="stop only an evaluation or repair operation",
            )
        status = record.get("status")
        if status in {"exited", "stopped", "launch_failed"}:
            return {
                "operation_id": operation_id,
                "kind": kind,
                "status": status,
                "stop_status": "already_finished",
                "reason": reason,
                "pid": record.get("pid"),
                "exit_code": record.get("exit_code"),
                "record_path": record.get("record_path"),
                "logs": record.get("log_paths"),
                "evidence_retained": True,
            }
        pid = record.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise HostOpError(
                "delivery_stop_refused",
                "the operation has no verifiable live process pid",
                obj="operation_id",
                retryable=False,
                next_action="query the operation status; retain its record and logs",
            )
        expected_argv = record.get("argv")
        observed_argv = _proc_command(pid)
        if (
            not isinstance(expected_argv, list)
            or not expected_argv
            or observed_argv is None
            or observed_argv not in _recorded_process_commands(expected_argv)
        ):
            raise HostOpError(
                "delivery_stop_refused",
                "the recorded pid command does not match the owned Delivery argv",
                obj="operation_id",
                retryable=False,
                next_action="retain the operation evidence and inspect the process manually",
                passthrough={"pid": pid},
            )
        try:
            process_group = os.getpgid(pid)
        except OSError as exc:
            raise HostOpError(
                "delivery_stop_refused",
                f"could not verify the owned process group: {exc}",
                obj="operation_id",
                retryable=False,
                next_action="retain the operation evidence and inspect the process manually",
            ) from exc
        if process_group != pid:
            raise HostOpError(
                "delivery_stop_refused",
                "the owned process is not the leader of its private process group",
                obj="operation_id",
                retryable=False,
                next_action="retain the operation evidence; no shared process group was signalled",
                passthrough={"pid": pid, "process_group": process_group},
            )
        try:
            os.killpg(process_group, signal.SIGTERM)
        except OSError as exc:
            raise HostOpError(
                "delivery_stop_failed",
                f"could not stop the owned Delivery process: {exc}",
                obj="operation_id",
                retryable=False,
                next_action="inspect the retained logs and process evidence",
            ) from exc
        record.update(
            {
                "status": "stop_requested",
                "stop_requested_at": _utc_now(),
                "stop_reason": reason,
                "stop_signal": "SIGTERM",
                "process_group": process_group,
            }
        )
        _write_record(record_path, record)

    # Give the child a short bounded grace period, then terminate the same
    # verified group.  The reaper owns the final exit/status evidence.
    deadline = time.monotonic() + 0.75
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        except PermissionError:
            break
        time.sleep(0.025)
    else:
        try:
            os.killpg(process_group, signal.SIGKILL)
            with _RECORD_LOCK:
                record = _read_record(operation_id, repository_root)
                record["stop_signal"] = "SIGKILL"
                _write_record(record_path, record)
        except OSError:
            # The reaper/status path retains the verified stop request even if
            # the short escalation raced with natural process exit.
            pass

    record = _read_record(operation_id, repository_root)
    return {
        "operation_id": operation_id,
        "kind": kind,
        "status": record.get("status"),
        "stop_status": "requested",
        "reason": reason,
        "pid": pid,
        "process_group": process_group,
        "record_path": record.get("record_path"),
        "logs": record.get("log_paths"),
        "evidence_retained": True,
    }


def _require_readback_credential() -> str:
    value = os.environ.get(HOST_CREDENTIAL_ENV)
    if not value:
        raise HostOpError(
            "host_credential_missing",
            f"the host environment does not set {HOST_CREDENTIAL_ENV}",
            obj="platform_readback",
            retryable=True,
            next_action="inject the existing host read credential; no platform mutation is attempted",
        )
    return value


def _readback_or_default(
    base_url: str | None, readback: PlatformReadback | None
) -> PlatformReadback:
    if readback is not None:
        return readback
    return http_readback(_validate_base_url(base_url), _require_readback_credential())


def _as_host_readback_error(exc: CheckpointError) -> HostOpError:
    return HostOpError(
        exc.reason_code,
        exc.detail,
        obj=exc.object,
        retryable=exc.retryable,
        next_action=exc.retry,
        passthrough={"phase": exc.phase} if exc.phase is not None else None,
    )


def _scope_validate_ids(
    *, project_id: str | None = None, ontology_id: str | None = None, ontology_ids: list[str] | None = None
) -> tuple[str | None, str | None, list[str]]:
    if project_id is not None:
        project_id = _safe_ref(project_id, "project_id")
    if ontology_id is not None:
        ontology_id = _safe_ref(ontology_id, "ontology_id")
    values = ontology_ids if ontology_ids is not None else ([ontology_id] if ontology_id else [])
    if not values or any(not isinstance(value, str) or not value.strip() for value in values):
        raise HostOpError(
            "platform_scope_invalid",
            "an explicit non-empty ontology scope is required for platform readback",
            obj="ontology_ids",
            retryable=True,
            next_action="pass the exact Ontology ids from the run scope binding",
        )
    cleaned = [_safe_ref(value, "ontology_id") for value in values]
    if len(set(cleaned)) != len(cleaned):
        raise HostOpError(
            "platform_scope_invalid",
            "ontology_ids must not contain duplicates",
            obj="ontology_ids",
            retryable=True,
            next_action="pass each exact Ontology id once",
        )
    return project_id, ontology_id, cleaned


def _raise_scope_mismatch(field: str, expected: str, observed: Any) -> None:
    raise HostOpError(
        "platform_scope_mismatch",
        f"platform readback {field} {observed!r} does not match the bound scope {expected!r}",
        obj=field,
        retryable=False,
        next_action="retain the readback and reconcile the exact run/project/Ontology binding",
    )


def _assert_record_scope(
    record_type: str,
    value: Any,
    *,
    project_id: str | None,
    ontology_id: str,
) -> None:
    """Check the response identity before returning private platform facts."""

    if record_type == "batch":
        if not isinstance(value, Mapping):
            return
        if project_id is not None and value.get("project_id") != project_id:
            _raise_scope_mismatch("project_id", project_id, value.get("project_id"))
        if value.get("ontology_id") != ontology_id:
            _raise_scope_mismatch("ontology_id", ontology_id, value.get("ontology_id"))
        return
    if record_type == "session":
        if not isinstance(value, Mapping):
            return
        session = value.get("session")
        session = session if isinstance(session, Mapping) else value
        if project_id is not None and session.get("project_id") != project_id:
            _raise_scope_mismatch("project_id", project_id, session.get("project_id"))
        involved = value.get("involved_ontology_ids")
        if not isinstance(involved, list) or ontology_id not in involved:
            _raise_scope_mismatch("ontology_id", ontology_id, involved)
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping) and item.get("ontology_id") not in (None, ontology_id):
                _raise_scope_mismatch("ontology_id", ontology_id, item.get("ontology_id"))


def _json_safe_reconciliation(value: Any) -> Any:
    """Project recovery dataclasses/tuple keys into the MCP JSON contract."""

    if isinstance(value, CompletedOperation):
        return _json_safe_reconciliation(value.index_entry())
    if isinstance(value, Mapping):
        return {
            (key if isinstance(key, (str, int, float, bool)) or key is None else str(key)):
            _json_safe_reconciliation(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe_reconciliation(item) for item in value]
    return value


def read_platform_record(
    *,
    record_type: str,
    record_id: str,
    project_id: str | None = None,
    ontology_id: str | None = None,
    base_url: str | None = None,
    repository_root: Path | None = None,
    readback: PlatformReadback | None = None,
) -> dict[str, Any]:
    """Read one existing platform record through the scoped readback client.

    ``batch`` includes the platform's Attempts, item results and resource
    outputs; ``session`` reads the Build Session detail; ``ontology_batches``
    enumerates only the exact Ontology scope.  The returned capability marker
    makes the absence of apply/delete authority explicit to callers.
    """

    if record_type not in {"batch", "session", "ontology_batches"}:
        raise HostOpError(
            "platform_record_type_invalid",
            "record_type must be 'batch', 'session', or 'ontology_batches'",
            obj="record_type",
            retryable=True,
            next_action="choose one of the existing readback record types",
        )
    record_id = _safe_ref(record_id, "record_id")
    if record_type == "ontology_batches" and ontology_id is None:
        ontology_id = record_id
    elif record_type == "ontology_batches" and ontology_id != record_id:
        _raise_scope_mismatch("ontology_id", str(ontology_id), record_id)
    if record_type != "ontology_batches" and ontology_id is None:
        raise HostOpError(
            "platform_scope_invalid",
            "batch/session readback requires the exact ontology_id scope",
            obj="ontology_id",
            retryable=True,
            next_action="pass the Ontology id bound to the run",
        )
    project_id, ontology_id, _ = _scope_validate_ids(
        project_id=project_id,
        ontology_id=ontology_id,
        ontology_ids=[ontology_id] if ontology_id is not None else None,
    )
    client = _readback_or_default(base_url, readback)
    try:
        if record_type == "batch":
            value = client.get_batch(record_id)
            if value.get("batch_id") not in (None, record_id):
                raise HostOpError(
                    "platform_scope_mismatch",
                    "platform batch detail returned a different batch identity",
                    obj="record_id",
                    retryable=False,
                    next_action="retain the readback and reconcile the exact operation identity",
                )
        elif record_type == "session":
            value = client.get_session(record_id)
        else:
            value = client.list_ontology_batches(record_id)
    except CheckpointError as exc:
        raise _as_host_readback_error(exc) from exc
    except OSError as exc:
        raise HostOpError(
            "platform_readback_unreachable",
            f"platform readback for {record_id!r} failed: {exc}",
            obj=record_id,
            retryable=True,
            next_action="check the existing read-only platform endpoint and retry; no mutation was attempted",
        ) from exc
    _assert_record_scope(
        record_type,
        value,
        project_id=project_id,
        ontology_id=str(ontology_id),
    )
    return {
        "record_type": record_type,
        "record_id": record_id,
        "scope": {"project_id": project_id, "ontology_id": ontology_id},
        "record": value,
        "readback_only": True,
        "mutation_capabilities": {"apply": False, "delete": False},
        "readback_counters": {
            "sessions_read": client.sessions_read,
            "batches_read": client.batches_read,
            "pages_read": client.pages_read,
        },
    }


def reconcile_write_state(
    *,
    run_id: str,
    project_id: str,
    ontology_ids: list[str],
    base_url: str | None = None,
    repository_root: Path | None = None,
    readback: PlatformReadback | None = None,
) -> dict[str, Any]:
    """Reconcile the run's complete write tail against live readback.

    This is deliberately a read-only projection of the existing recovery
    function.  It does not submit, apply, delete, settle, or retry anything.
    """

    _safe_ref(run_id, "run_id")
    project_id, _ontology_id, ontology_ids = _scope_validate_ids(
        project_id=project_id, ontology_ids=ontology_ids
    )
    run_root, runs_root = resolve_run_root(run_id, repository_root=repository_root)
    chain = origin_chain_roots(run_root, runs_root)
    tail = read_write_tail(chain)
    client = _readback_or_default(base_url, readback)
    try:
        result = reconcile_write_tail(chain, tail, client, ontology_ids=ontology_ids)
    except CheckpointError as exc:
        raise _as_host_readback_error(exc) from exc
    except OSError as exc:
        raise HostOpError(
            "platform_readback_unreachable",
            f"platform reconciliation readback failed: {exc}",
            obj="platform_readback",
            retryable=True,
            next_action="check the existing read-only platform endpoint and retry; no mutation was attempted",
        ) from exc
    return {
        "run_id": run_id,
        "project_id": project_id,
        "chain_run_ids": [path.name for path in chain],
        "write_tail": tail,
        "reconciliation": _json_safe_reconciliation(result),
        "readback_only": True,
        "mutation_capabilities": {"apply": False, "delete": False},
        "note": "readback proves current platform facts; it does not mutate the run or replay an unknown request",
    }


__all__ = [
    "DELIVERY_DIRECTORY",
    "DELIVERY_RECORD_SCHEMA",
    "get_evaluation_status",
    "get_repair_status",
    "read_platform_record",
    "reconcile_write_state",
    "stop_delivery_operation",
    "start_evaluation",
    "start_repair",
]
