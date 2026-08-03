"""Deterministic, non-semantic R2.3-003 scope-handoff publisher."""

from __future__ import annotations

import json
import os
import fcntl
import hashlib
from pathlib import Path
from typing import Any
from types import SimpleNamespace

from .contracts import TeamConfigurationError
from .platform_scope import PlatformScope, PlatformScopeError


HANDOFF_FIELDS = ("run_id", "project_id", "ontology_id", "workspace_version", "scope_disposition")
_REQUIRED_ROLES = {"coordinator", "modeling", "protocol"}


def publish_scope_handoff(scope: Any, run: Any, phase_a_verdict: str, destination: Path) -> Path:
    """Publish exactly once after a Phase A PASS and a fresh scope recheck."""
    if phase_a_verdict != "PHASE_A_PASS":
        raise TeamConfigurationError("scope handoff requires independent PHASE_A_PASS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt = destination.parent / ".r2-3-002-handoff-publications.jsonl"
    lock_path = destination.parent / ".r2-3-002-handoff-publications.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            records = _receipt_records(receipt)
            if destination.exists() or any(record.get("run_id") == run.run_id for record in records):
                raise TeamConfigurationError("scope handoff is immutable and already published")
            terminal = scope.recheck_retained_producer()
            if terminal.get("scope_disposition") != "retained-pending-acceptance":
                raise TeamConfigurationError("producer scope is not pending acceptance")
            results = getattr(run, "terminal_results", None)
            required = {"coordinator", "modeling", "protocol"}
            if (
                not isinstance(results, dict)
                or set(results) != required
                or any(not isinstance(value, dict) or value.get("status") != "completed" for value in results.values())
            ):
                raise TeamConfigurationError("all producer Agents must be completed")
            payload = {
                "run_id": run.run_id,
                "project_id": terminal["project_id"],
                "ontology_id": terminal["ontology_id"],
                "workspace_version": terminal["workspace_version"],
                "scope_disposition": "retained",
            }
            if not isinstance(payload["workspace_version"], str) or not payload["workspace_version"]:
                raise TeamConfigurationError("scope handoff requires a non-empty workspace version")
            payload_hash = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            _append_receipt(receipt, {"run_id": run.run_id, "payload_sha256": payload_hash})
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o444)
            os.replace(temporary, destination)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return destination


def publish_offline_scope_handoff(
    *,
    run_root: Path,
    expected_run_id: str,
    base_url: str,
    phase_a_verdict_artifact: Path,
    destination: Path,
    bootstrap_admin: Any,
    revoke_admin: Any,
    request: Any | None = None,
) -> Path:
    """Recheck retained producer state after the original Runtime has stopped.

    This deliberately only validates persisted mechanical evidence and current platform state;
    it does not inspect model content or calculate a semantic verdict.
    """
    verdict = _phase_a_verdict(phase_a_verdict_artifact)
    if verdict != "PHASE_A_PASS":
        raise TeamConfigurationError("scope handoff requires independent PHASE_A_PASS")
    state = _run_state(run_root)
    retained = _retained_handoff_evidence(run_root)
    run_id = retained.get("run_id")
    statuses = retained.get("terminal_statuses")
    scope_data = retained.get("scope")
    state_scope = _state_scope(state)
    state_statuses = _terminal_statuses(state.get("terminal_results"))
    if state.get("state") != "CLEANED" or state.get("run_id") != run_id or run_id != expected_run_id:
        raise TeamConfigurationError("offline handoff requires immutable cleaned run state")
    if not isinstance(run_id, str) or not isinstance(scope_data, dict):
        raise TeamConfigurationError("offline handoff requires immutable retained scope evidence")
    required_scope = ("project_id", "ontology_id", "workspace_version", "completed_session_id")
    scope_keys = {"owned", "project_id", "ontology_id", "workspace_version", "completed_session_id", "scope_disposition"}
    if set(retained) != {"run_id", "terminal_statuses", "scope"} or set(scope_data) != scope_keys:
        raise TeamConfigurationError("offline handoff retained evidence has unexpected fields")
    if (
        scope_data.get("scope_disposition") != "retained-pending-acceptance"
        or scope_data.get("owned") is not True
        or any(not isinstance(scope_data.get(field), str) or not scope_data[field] for field in required_scope)
    ):
        raise TeamConfigurationError("offline handoff producer state is not retained pending acceptance")
    if statuses != {role: "completed" for role in sorted(_REQUIRED_ROLES)}:
        raise TeamConfigurationError("retained handoff evidence requires exactly three completed Agent statuses")
    if state_statuses != statuses:
        raise TeamConfigurationError("offline handoff terminal statuses drifted from retained evidence")
    if any(state_scope.get(key) != scope_data.get(key) for key in scope_keys):
        raise TeamConfigurationError("offline handoff scope drifted from retained evidence")
    run = SimpleNamespace(
        run_id=run_id,
        terminal_results={role: {"status": status} for role, status in statuses.items()},
    )
    scope = PlatformScope(base_url, run_id, bootstrap_admin, revoke_admin, request)
    scope.owned = True
    scope.project_id = scope_data["project_id"]
    scope.ontology_id = scope_data["ontology_id"]
    scope.scope_disposition = scope_data["scope_disposition"]
    scope.final_workspace_version = scope_data["workspace_version"]
    scope.completed_session_id = scope_data["completed_session_id"]
    scope.terminal_results = run.terminal_results
    try:
        current = scope.recheck_retained_producer()
    except PlatformScopeError as exc:
        raise TeamConfigurationError(f"offline handoff scope recheck failed: {exc}") from exc
    expected = {
        "project_id": scope_data["project_id"],
        "ontology_id": scope_data["ontology_id"],
        "workspace_version": scope_data["workspace_version"],
    }
    if {key: current.get(key) for key in expected} != expected:
        raise TeamConfigurationError("offline handoff scope drifted from immutable run state")
    return publish_scope_handoff(scope, run, verdict, destination)


def _phase_a_verdict(path: Path) -> str:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("Phase A verdict artifact is unreadable") from exc
    if not isinstance(artifact, dict) or set(artifact) != {"verdict"} or not isinstance(artifact["verdict"], str):
        raise TeamConfigurationError("Phase A verdict artifact is invalid")
    return artifact["verdict"]


def _run_state(run_root: Path) -> dict[str, Any]:
    try:
        state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("offline handoff run state is unreadable") from exc
    if not isinstance(state, dict):
        raise TeamConfigurationError("offline handoff run state is invalid")
    return state


def _retained_handoff_evidence(run_root: Path) -> dict[str, Any]:
    path = run_root / "evidence" / "retained-handoff-input.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("offline handoff retained evidence is unreadable") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError("offline handoff retained evidence is invalid")
    return value


def _state_scope(state: dict[str, Any]) -> dict[str, Any]:
    cleanup = state.get("cleanup")
    scope = cleanup.get("scope") if isinstance(cleanup, dict) else None
    if not isinstance(scope, dict):
        raise TeamConfigurationError("offline handoff cleaned state has no scope evidence")
    return scope


def _terminal_statuses(results: Any) -> dict[str, str]:
    if (
        not isinstance(results, dict)
        or set(results) != _REQUIRED_ROLES
        or any(not isinstance(value, dict) or not isinstance(value.get("status"), str) for value in results.values())
    ):
        raise TeamConfigurationError("offline handoff cleaned state has invalid Agent terminal statuses")
    return {role: results[role]["status"] for role in sorted(_REQUIRED_ROLES)}


def _receipt_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TeamConfigurationError("scope handoff receipt is corrupt") from exc
        if not isinstance(value, dict) or not isinstance(value.get("run_id"), str):
            raise TeamConfigurationError("scope handoff receipt is invalid")
        records.append(value)
    return records


def _append_receipt(path: Path, value: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
