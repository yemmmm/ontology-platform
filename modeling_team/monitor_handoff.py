"""File-owned foreground monitor handoff for the bounded P2 smoke path.

The monitor and the foreground CLI deliberately exchange one immutable JSON file per phase.
The monitor owns the handoff directory and acknowledgement files; the CLI only owns the
runner-to-monitor phase files.  There is no append/update operation that could make a stale
acknowledgement look current.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any

HANDOFF_ENV = "ONTOLOGY_P2_MONITOR_HANDOFF"
HANDOFF_CONTRACT_RELATIVE_PATH = Path("modeling_team/references/p2-monitor-handoff-contract.json")
HANDOFF_SCHEMA_VERSION = "p2-monitor-handoff/v1"
HANDOFF_ROOT_MODE = 0o700
HANDOFF_FILE_MODE = 0o600
NONCE_BYTES = 16
RUNNER_TO_MONITOR = "runner-to-monitor"
MONITOR_TO_RUNNER = "monitor-to-runner"
RUNNER_PHASES = frozenset({"prepared", "cleanup_pending", "failed"})
MONITOR_PHASES = frozenset({"extraction_complete", "extraction_failed"})
PHASE_DEADLINES_SECONDS = {
    "prepared": 30.0,
    "foreground_run": 120.0,
    "extraction_complete": 30.0,
}
_SAFE_RUN_ID = __import__("re").compile(r"^[a-z0-9][a-z0-9-]{2,80}$")


def _contract_fields() -> dict[str, Any]:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "environment": HANDOFF_ENV,
        "runner_phases": ["prepared", "cleanup_pending", "failed"],
        "monitor_phases": ["extraction_complete", "extraction_failed"],
        "phase_deadlines_seconds": PHASE_DEADLINES_SECONDS,
        "handoff_root_mode": HANDOFF_ROOT_MODE,
        "handoff_file_mode": HANDOFF_FILE_MODE,
        "nonce_bytes": NONCE_BYTES,
        "runner_to_monitor_directory": RUNNER_TO_MONITOR,
        "monitor_to_runner_directory": MONITOR_TO_RUNNER,
        "environment_payload": "handoff-root-directory",
    }


def load_handoff_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("P2 monitor handoff contract is unreadable") from exc
    expected = _contract_fields()
    if value != expected:
        raise ValueError("P2 monitor handoff contract drifted")
    return value


def canonical_run_root(repository: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("P2 monitor handoff run ID is unsafe")
    repo = repository.resolve()
    root = repo / "workspaces" / "modeling-runs" / run_id
    if root.resolve(strict=False) != root:
        raise ValueError("P2 monitor handoff run root escapes canonical repository path")
    for parent in (repo, repo / "workspaces", repo / "workspaces" / "modeling-runs"):
        if parent.is_symlink():
            raise ValueError("P2 monitor handoff run root has a symlinked parent")
    return root


def _assert_mode(path: Path, expected_mode: int, *, directory: bool) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ValueError("P2 monitor handoff path is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("P2 monitor handoff refuses symlink paths")
    if (directory and not stat.S_ISDIR(metadata.st_mode)) or (
        not directory and not stat.S_ISREG(metadata.st_mode)
    ):
        raise ValueError("P2 monitor handoff path has the wrong type")
    if stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise ValueError("P2 monitor handoff path has the wrong mode")


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("P2 monitor handoff phase is immutable and already exists")
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, HANDOFF_FILE_MODE)
    except FileExistsError as exc:
        raise ValueError("P2 monitor handoff phase is immutable and already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    os.chmod(path, HANDOFF_FILE_MODE)
    _fsync_parent(path.parent)


def _metadata(root: Path) -> dict[str, Any]:
    _assert_mode(root, HANDOFF_ROOT_MODE, directory=True)
    metadata_path = root / "metadata.json"
    _assert_mode(metadata_path, HANDOFF_FILE_MODE, directory=False)
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("P2 monitor handoff metadata is unreadable") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "nonce", "run_id", "expected_run_root", "created_at_ns"
    }:
        raise ValueError("P2 monitor handoff metadata fields drifted")
    if value.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise ValueError("P2 monitor handoff metadata schema drifted")
    if (
        not isinstance(value.get("nonce"), str)
        or len(value["nonce"]) != NONCE_BYTES * 2
        or not isinstance(value.get("run_id"), str)
        or not isinstance(value.get("expected_run_root"), str)
        or not isinstance(value.get("created_at_ns"), int)
        or isinstance(value.get("created_at_ns"), bool)
    ):
        raise ValueError("P2 monitor handoff metadata is invalid")
    return value


def create_handoff_root(repository: Path, target_root: Path) -> tuple[Path, dict[str, Any]]:
    """Create the fresh sibling directory without touching the target CLI run root."""
    repo = repository.resolve()
    expected = canonical_run_root(repo, target_root.name)
    if target_root.resolve(strict=False) != expected or target_root.exists() or target_root.is_symlink():
        raise ValueError("P2 monitor target run root must be a fresh canonical directory")
    nonce = secrets.token_hex(NONCE_BYTES)
    handoff_root = expected.parent / f".{expected.name}.monitor-{nonce}"
    if handoff_root.exists() or handoff_root.is_symlink():
        raise ValueError("P2 monitor handoff root already exists")
    handoff_root.mkdir(mode=HANDOFF_ROOT_MODE, parents=False, exist_ok=False)
    os.chmod(handoff_root, HANDOFF_ROOT_MODE)
    for name in (RUNNER_TO_MONITOR, MONITOR_TO_RUNNER):
        directory = handoff_root / name
        directory.mkdir(mode=HANDOFF_ROOT_MODE, exist_ok=False)
        os.chmod(directory, HANDOFF_ROOT_MODE)
    _fsync_parent(handoff_root.parent)
    metadata = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "nonce": nonce,
        "run_id": expected.name,
        "expected_run_root": str(expected),
        "created_at_ns": time.time_ns(),
    }
    _write_exclusive(handoff_root / "metadata.json", metadata)
    return handoff_root, metadata


def _phase_payload(root: Path, owner: str, phase: str, **payload: Any) -> dict[str, Any]:
    metadata = _metadata(root)
    if owner == "runner":
        phases = RUNNER_PHASES
    elif owner == "foreground_monitor":
        phases = MONITOR_PHASES
    else:
        raise ValueError("P2 monitor handoff owner is invalid")
    if phase not in phases:
        raise ValueError("P2 monitor handoff phase is invalid")
    base_fields = {
        "schema_version",
        "owner",
        "phase",
        "nonce",
        "run_id",
        "expected_run_root",
        "run_root",
        "recorded_at_ns",
    }
    extra_allowed: set[str] = set()
    if owner == "foreground_monitor" and phase == "extraction_complete":
        extra_allowed.update({"output_digest", "output_length"})
    if owner == "foreground_monitor" and phase == "extraction_failed":
        extra_allowed.add("error_type")
    if set(payload) - (base_fields | extra_allowed):
        raise ValueError("P2 monitor handoff payload fields drifted")
    reported_root = Path(payload.pop("run_root", metadata["expected_run_root"])).resolve(strict=False)
    expected_root = Path(metadata["expected_run_root"]).resolve(strict=False)
    if reported_root != expected_root:
        raise ValueError("P2 monitor handoff run root does not match the prepared target")
    value = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "owner": owner,
        "phase": phase,
        "nonce": metadata["nonce"],
        "run_id": metadata["run_id"],
        "expected_run_root": metadata["expected_run_root"],
        "run_root": str(reported_root),
        "recorded_at_ns": time.time_ns(),
        **payload,
    }
    return value


def write_runner_phase(root: Path, phase: str, *, run_root: Path | None = None, **payload: Any) -> Path:
    value = _phase_payload(root, "runner", phase, run_root=run_root or Path(_metadata(root)["expected_run_root"]), **payload)
    path = root / RUNNER_TO_MONITOR / f"{phase}.json"
    _write_exclusive(path, value)
    return path


def write_monitor_phase(root: Path, phase: str, *, run_root: Path | None = None, **payload: Any) -> Path:
    value = _phase_payload(
        root, "foreground_monitor", phase, run_root=run_root or Path(_metadata(root)["expected_run_root"]), **payload
    )
    path = root / MONITOR_TO_RUNNER / f"{phase}.json"
    _write_exclusive(path, value)
    return path


def read_phase(root: Path, owner: str, phase: str) -> dict[str, Any] | None:
    directory = RUNNER_TO_MONITOR if owner == "runner" else MONITOR_TO_RUNNER
    phases = RUNNER_PHASES if owner == "runner" else MONITOR_PHASES
    if phase not in phases:
        raise ValueError("P2 monitor handoff phase is invalid")
    path = root / directory / f"{phase}.json"
    if not path.exists():
        return None
    _assert_mode(path, HANDOFF_FILE_MODE, directory=False)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("P2 monitor handoff phase is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("P2 monitor handoff phase is invalid")
    metadata = _metadata(root)
    expected_fields = {
        "schema_version",
        "owner",
        "phase",
        "nonce",
        "run_id",
        "expected_run_root",
        "run_root",
        "recorded_at_ns",
    }
    if owner == "foreground_monitor" and phase == "extraction_complete":
        expected_fields.update({"output_digest", "output_length"})
    if owner == "foreground_monitor" and phase == "extraction_failed":
        expected_fields.add("error_type")
    if set(value) != expected_fields:
        raise ValueError("P2 monitor handoff phase fields drifted")
    if (
        value.get("schema_version") != HANDOFF_SCHEMA_VERSION
        or value.get("owner") != owner
        or value.get("phase") != phase
        or value.get("nonce") != metadata["nonce"]
        or value.get("run_id") != metadata["run_id"]
        or value.get("expected_run_root") != metadata["expected_run_root"]
        or value.get("run_root") != metadata["expected_run_root"]
    ):
        raise ValueError("P2 monitor handoff phase does not match current run")
    if (
        not isinstance(value.get("recorded_at_ns"), int)
        or isinstance(value.get("recorded_at_ns"), bool)
        or value["recorded_at_ns"] <= 0
    ):
        raise ValueError("P2 monitor handoff phase timestamp is invalid")
    if phase == "extraction_complete" and (
        not isinstance(value.get("output_digest"), str)
        or len(value["output_digest"]) != 64
        or not isinstance(value.get("output_length"), int)
        or isinstance(value["output_length"], bool)
        or value["output_length"] < 1
    ):
        raise ValueError("P2 monitor extraction acknowledgement is invalid")
    if phase == "extraction_failed" and (
        not isinstance(value.get("error_type"), str) or not value["error_type"]
    ):
        raise ValueError("P2 monitor extraction failure is invalid")
    return value


def wait_for_phase(root: Path, owner: str, phase: str, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read_phase(root, owner, phase)
        if value is not None:
            return value
        time.sleep(0.05)
    return None


def output_digest(path: Path) -> tuple[str, int]:
    import hashlib

    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


def validate_target_run_root(repository: Path, run_root: Path, run_id: str) -> Path:
    expected = canonical_run_root(repository, run_id)
    actual = run_root.resolve(strict=False)
    if actual != expected:
        raise ValueError("P2 monitor target run root is not the canonical run path")
    return expected
