#!/usr/bin/env python3
"""Fail-closed L3 launcher for the bounded, isolated C -> B -> A experiment.

This is scenario infrastructure only.  It publishes deterministic protocol mechanics but
never creates, repairs, ranks, or reorders semantic Modeling Items.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, request
from uuid import uuid4


SCENARIO_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCENARIO_ROOT.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
REASONER_SCRIPT = BACKEND_ROOT / "scripts" / "dev_owl_reasoner.py"
AGENT_INPUT = SCENARIO_ROOT / "agent-input"
MANIFEST = AGENT_INPUT / "manifest.json"
RUNTIME_ROOT = SCENARIO_ROOT / "runtime" / "runs"
GLOBAL_LEDGER = SCENARIO_ROOT / "runtime" / "attempt-ledger.jsonl"
CLASSIFICATION_LEDGER = SCENARIO_ROOT / "runtime" / "historical-classification-ledger.jsonl"
GLOBAL_LOCK = SCENARIO_ROOT / "runtime" / "attempt-ledger.lock"
SCENARIO_STATE = SCENARIO_ROOT / "runtime" / "state.json"
EXECUTION_POLICY = SCENARIO_ROOT / "execution-policy.json"
ANSWER_CONTRACT = SCENARIO_ROOT / "tester-only" / "answer-contract.json"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
HOST_KEY_MARKERS = ("ONTOLOGY_MCP_API_KEY", "sk_admin_", "bootstrap-admin")
CODEX_BINARY = Path(os.environ.get("L3_CODEX_BINARY", "/home/yangxiang/.local/bin/codex"))
HOST_CODEX_AUTH = Path(os.environ.get("L3_HOST_CODEX_AUTH", "/home/yangxiang/.codex/auth.json"))
HISTORICAL_RUN_IDS = ("l3-real-20260730g", "l3-real-20260730h", "l3-real-20260730i")
RECOVERY_RUN_ID = "l3-real-20260730j"
RECOVERY_WAIT_RUN_ID = "l3-real-20260730k"
DUPLICATE_GATE_HALT_REASON = "20-minute first-modeling gate missed before child delegation"
PROTOCOL_TOOLS = (
    "check_platform_health",
    "get_modeling_context",
    "create_build_session",
    "get_build_session",
    "acquire_ontology_lease",
    "submit_modeling_batch",
    "get_modeling_batch",
    "get_ontology_read_model",
    "save_build_checkpoint",
    "complete_build_session",
    "cancel_build_session",
)
FIRST_RESPONSE_SECONDS = 60
TERMINAL_TIMEOUT_SECONDS = 300
PROTOCOL_TERMINAL_TIMEOUT_SECONDS = 900


class L3Error(RuntimeError):
    """A fail-closed scenario contract condition."""


def read_execution_policy() -> dict[str, Any]:
    required = {
        "policy_version",
        "live_execution_authorized",
        "state",
        "outcome",
        "category",
        "starts_consumed",
        "max_starts",
        "recovery_preparation_started_at",
        "run_ids",
        "user_authorization",
        "recovery_requirements",
    }
    try:
        policy = json.loads(EXECUTION_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("committed L3 execution policy is unavailable") from exc
    if not isinstance(policy, dict) or set(policy) != required or policy.get("policy_version") != 2:
        raise L3Error("committed L3 execution policy fields drift")
    if (
        not isinstance(policy.get("live_execution_authorized"), bool)
        or not isinstance(policy.get("starts_consumed"), int)
        or not isinstance(policy.get("max_starts"), int)
        or policy["starts_consumed"] < 0
        or policy["max_starts"] < policy["starts_consumed"]
    ):
        raise L3Error("committed L3 execution policy types drift")
    run_ids = policy.get("run_ids")
    recovery = policy.get("recovery_requirements")
    authorization = policy.get("user_authorization")
    preparation_started_at = policy.get("recovery_preparation_started_at")
    if (
        not isinstance(run_ids, list)
        or not all(isinstance(value, str) for value in run_ids)
        or not isinstance(recovery, list)
        or not all(isinstance(value, str) for value in recovery)
        or not isinstance(authorization, dict)
        or set(authorization) != {"authorized_at", "additional_starts"}
        or not isinstance(authorization.get("authorized_at"), str)
        or not isinstance(authorization.get("additional_starts"), int)
        or authorization["additional_starts"] != policy["max_starts"] - policy["starts_consumed"]
        or not isinstance(preparation_started_at, str)
    ):
        raise L3Error("committed L3 execution policy lists drift")
    try:
        preparation_time = datetime.fromisoformat(preparation_started_at)
    except ValueError as exc:
        raise L3Error("committed recovery preparation timestamp is invalid") from exc
    if preparation_time.tzinfo is None:
        raise L3Error("committed recovery preparation timestamp must include a timezone")
    if not policy["live_execution_authorized"] and (policy.get("state"), policy.get("outcome")) != ("PAUSED", "NOT_PASSED"):
        raise L3Error("disabled L3 execution policy must remain PAUSED/NOT_PASSED")
    if policy["live_execution_authorized"] and (policy.get("state"), policy.get("outcome"), policy.get("category")) != ("READY", "PENDING", "pending"):
        raise L3Error("enabled L3 execution policy must remain READY/PENDING/pending")
    return policy


def recovery_preparation_started_at(policy: dict[str, Any] | None = None) -> datetime:
    policy = policy or read_execution_policy()
    return datetime.fromisoformat(policy["recovery_preparation_started_at"])


def first_modeling_deadline(policy: dict[str, Any] | None = None) -> datetime:
    return recovery_preparation_started_at(policy) + timedelta(minutes=20)


def require_live_execution_authorized() -> dict[str, Any]:
    policy = read_execution_policy()
    if not policy["live_execution_authorized"]:
        raise L3Error("live L3 execution is disabled by committed execution-policy.json")
    return policy


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise L3Error("run_id must be lowercase alphanumeric with hyphens")
    return RUNTIME_ROOT / run_id


def safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise L3Error("manifest path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise L3Error("manifest path is unsafe")
    return path


def read_manifest() -> dict[str, Any]:
    try:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("L3 input manifest is invalid") from exc
    if set(value) != {"manifest_version", "files"} or value.get("manifest_version") != 1:
        raise L3Error("L3 input manifest fields drift")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise L3Error("L3 manifest has no staged files")
    declared: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise L3Error("L3 manifest item fields drift")
        relative = safe_relative(item["path"])
        digest = item["sha256"]
        if relative.as_posix() in declared or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise L3Error("L3 manifest has duplicate or invalid hash")
        declared.add(relative.as_posix())
        path = AGENT_INPUT / relative
        if path.is_symlink() or not path.is_file() or sha256_path(path) != digest:
            raise L3Error(f"L3 staged input hash drift: {relative}")
    actual = {p.relative_to(AGENT_INPUT).as_posix() for p in AGENT_INPUT.rglob("*") if p.is_file() and p != MANIFEST}
    if actual != declared:
        raise L3Error("L3 staged input set differs from manifest")
    return value


def atomic_json(path: Path, value: object, *, mode: int = 0o400) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError as exc:
        Path(temporary).unlink(missing_ok=True)
        raise L3Error(f"atomic publication failed: {path.name}") from exc


def stage_input(manifest: dict[str, Any], destination: Path) -> dict[str, Any]:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for item in manifest["files"]:
        relative = safe_relative(item["path"])
        target = destination / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(AGENT_INPUT / relative, target)
        os.chmod(target, 0o444)
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    expected = {item["path"] for item in manifest["files"]}
    if actual != expected:
        raise L3Error("staged namespace membership drift")
    return {"manifest_sha256": sha256_path(MANIFEST), "files": sorted(actual)}


def _stage_named_files(manifest: dict[str, Any], destination: Path, names: set[str]) -> list[str]:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    declared = {item["path"] for item in manifest["files"]}
    if not names.issubset(declared):
        raise L3Error("role staging requests undeclared input")
    for name in sorted(names):
        target = destination / safe_relative(name)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(AGENT_INPUT / safe_relative(name), target)
        os.chmod(target, 0o444)
    return sorted(names)


def protocol_mechanics_contract(run_id: str) -> dict[str, Any]:
    """A declarative, semantic-free mechanics contract for the Protocol Agent only."""
    return {
        "contract_version": 1,
        "run_id": run_id,
        "owner": "protocol_only_deterministic_helper",
        "owns": [
            "stable_ids",
            "canonical_json_and_hashes",
            "atomic_publication",
            "public_request_schema_validation",
            "immutable_batch_freeze_and_replay",
            "workspace_revision_and_lease_state",
            "lease_renewal_and_checkpoint_bodies",
            "response_parsing",
            "cross_batch_platform_identity_binding",
        ],
        "forbidden": ["modeling_item_synthesis", "item_reordering", "semantic_repair", "query_authoring"],
    }


def credential_lifecycle_contract() -> dict[str, Any]:
    return {
        "no_key_probe_required": True,
        "temporary_key": {
            "scope": "model",
            "project_scoped": True,
            "injected_only_after_no_key_rejection": True,
            "never_written_to_evidence": True,
            "revoked_before_project_deletion": True,
        },
        "host_admin": {"ephemeral": True, "never_mounted": True, "revoked_after_cleanup": True},
    }


def stage_role_packs(manifest: dict[str, Any], run_root: Path, run_id: str) -> dict[str, Any]:
    coordinator_files = {item["path"] for item in manifest["files"]} - {"public-protocol.md"}
    coordinator = run_root / "coordinator-input"
    protocol = run_root / "protocol-input"
    coordinator_receipt = _stage_named_files(manifest, coordinator, coordinator_files)
    protocol.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ("public-protocol.md",):
        target = protocol / name
        shutil.copyfile(AGENT_INPUT / name, target)
        os.chmod(target, 0o444)
    atomic_json(protocol / "mechanics-contract.json", protocol_mechanics_contract(run_id), mode=0o444)
    atomic_json(protocol / "credential-lifecycle.json", credential_lifecycle_contract(), mode=0o444)
    return {
        "coordinator_files": coordinator_receipt,
        "protocol_files": sorted(path.name for path in protocol.iterdir()),
        "coordinator_excludes_public_protocol": not (coordinator / "public-protocol.md").exists(),
    }


def stage_protocol_handoff(
    protocol_input: Path,
    candidate: dict[str, Any],
    dispatch: dict[str, Any],
    scope: dict[str, str],
) -> dict[str, str]:
    """Stage opaque coordinator output; this function never creates Items or keys."""
    if not isinstance(candidate, dict) or not isinstance(dispatch, dict):
        raise L3Error("Protocol handoff requires coordinator-authored candidate and dispatch")
    if set(scope) != {"project_id", "ontology_id"} or not all(isinstance(value, str) for value in scope.values()):
        raise L3Error("Protocol handoff scope is invalid")
    for name, value in (("approved-candidate.json", candidate), ("protocol-dispatch.json", dispatch), ("protocol-scope.json", scope)):
        atomic_json(protocol_input / name, value, mode=0o444)
    return {"candidate_sha256": hashlib.sha256(canonical_json(candidate)).hexdigest(), "scope": "owned"}


def stage_credential_proof(protocol_input: Path) -> None:
    """Publish only the launcher-owned ordering proof; never publish credential material."""
    atomic_json(
        protocol_input / "credential-proof.json",
        {
            "no_key_probe": "rejected_before_temporary_key_creation",
            "protocol_launch": "after_project_scoped_model_key_injection",
            "contains_credential_material": False,
        },
        mode=0o444,
    )


class ProtocolMechanics:
    """Deterministic, protocol-only mechanics; semantic contents remain opaque."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def stable_id(self, purpose: str, ordinal: int) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,48}", purpose) or ordinal < 0:
            raise L3Error("invalid deterministic identifier input")
        return str(uuid4()) if False else hashlib.sha256(f"{self.run_id}:{purpose}:{ordinal}".encode()).hexdigest()[:32]

    def request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z_]{3,64}", operation) or not isinstance(payload, dict):
            raise L3Error("public request schema is invalid")
        # The helper validates envelopes only: it does not inspect or supply Item semantics.
        return {"request_id": self.stable_id(operation, 0), "operation": operation, "payload": payload, "sha256": hashlib.sha256(canonical_json(payload)).hexdigest()}

    def freeze_batch(self, items: list[dict[str, Any]], client_batch_id: str) -> dict[str, Any]:
        if not isinstance(items, list) or not items or not isinstance(client_batch_id, str):
            raise L3Error("Batch envelope is invalid")
        if any(not isinstance(item, dict) for item in items):
            raise L3Error("Batch Items must be supplied by the Protocol Agent")
        return {"client_batch_id": client_batch_id, "items_sha256": hashlib.sha256(canonical_json(items)).hexdigest(), "items": items}

    def replay(self, frozen: dict[str, Any], items: list[dict[str, Any]], client_batch_id: str) -> None:
        if frozen.get("client_batch_id") != client_batch_id or frozen.get("items_sha256") != hashlib.sha256(canonical_json(items)).hexdigest():
            raise L3Error("immutable Batch replay drift")

    def lease_renewal(self, lease_token: str, revision: int) -> dict[str, Any]:
        if not lease_token or revision < 0:
            raise L3Error("lease renewal state is invalid")
        return {"lease_token": lease_token, "expected_revision": revision}

    def checkpoint(self, build_session_id: str, revision: int, body: dict[str, Any]) -> dict[str, Any]:
        if not build_session_id or revision < 0 or not isinstance(body, dict):
            raise L3Error("checkpoint state is invalid")
        return {"build_session_id": build_session_id, "expected_revision": revision, "body": body}

    def receipt(self, value: object, required: set[str]) -> dict[str, Any]:
        if not isinstance(value, dict) or not required.issubset(value):
            raise L3Error("platform response schema drift")
        return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise L3Error("attempt ledger is not valid JSONL") from exc
        if not isinstance(value, dict):
            raise L3Error("attempt ledger event is invalid")
        events.append(value)
    return events


def _append_locked(stream, event: dict[str, Any]) -> None:
    stream.write(canonical_json(event).decode() + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _reconcile_historical_starts(stream, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {event.get("run_id") for event in events}
    for attempt in sorted(RUNTIME_ROOT.glob("*/attempts.jsonl")):
        for event in _read_jsonl(attempt):
            run_id = event.get("run_id")
            if event.get("event") == "modeling_started" and isinstance(run_id, str) and run_id not in existing:
                restored = {
                    "event": "historical_coordinator_started",
                    "run_id": run_id,
                    "started_at": event.get("first_modeling_started_at"),
                    "reason": "pre-global-ledger historical attempt preserved",
                }
                _append_locked(stream, restored)
                events.append(restored)
                existing.add(run_id)
    return events


def _jsonl_items(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error(f"invalid raw {label} JSONL: {path.name}") from exc
    if not all(isinstance(value, dict) for value in values):
        raise L3Error(f"invalid raw {label} JSONL item")
    return values


def _exact_agent_message_marker(path: Path, marker: str) -> bool:
    """Match only a terminal Agent message, never prompt or command-output text."""
    return any(
        isinstance((item := value.get("item")), dict)
        and item.get("type") in {None, "agent_message"}
        and isinstance(item.get("text"), str)
        and item["text"].strip() == marker
        for value in _jsonl_items(path, "agent transcript")
    )


def _outer_thread_id(transcript: Path) -> str:
    ids = {
        value["thread_id"]
        for value in _jsonl_items(transcript, "coordinator transcript")
        if value.get("type") == "thread.started" and isinstance(value.get("thread_id"), str)
    }
    if len(ids) != 1:
        raise L3Error("outer coordinator transcript lacks exactly one thread.started identity")
    return ids.pop()


def _session_meta(path: Path) -> dict[str, Any]:
    metas = [
        value["payload"]
        for value in _jsonl_items(path, "session rollout")
        if value.get("type") == "session_meta" and isinstance(value.get("payload"), dict)
    ]
    if len(metas) != 1 or not isinstance(metas[0].get("id"), str):
        raise L3Error(f"raw session rollout lacks exactly one session_meta: {path.name}")
    return metas[0]


def _find_session_rollout(sessions: Path, thread_id: str) -> Path:
    candidates = [path for path in sessions.rglob("*.jsonl") if _session_meta(path).get("id") == thread_id]
    if len(candidates) != 1:
        raise L3Error(f"raw child rollout is missing or ambiguous: {thread_id}")
    return candidates[0]


def raw_verified_modeling_child(run_root: Path) -> dict[str, Any]:
    """Prove delegation from raw coordinator and child rollouts, never CLI summary alone."""
    transcript = run_root / "audit" / "coordinator.jsonl"
    coordinator_id = _outer_thread_id(transcript)
    sessions = run_root / "coordinator-home" / "sessions"
    if not sessions.is_dir():
        raise L3Error("raw coordinator rollout directory is missing")
    coordinator_rollout = _find_session_rollout(sessions, coordinator_id)
    eligible: list[str] = []
    for value in _jsonl_items(coordinator_rollout, "coordinator rollout"):
        payload = value.get("payload", {})
        if not (
            value.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "function_call"
            and payload.get("name") == "spawn_agent"
            and isinstance(payload.get("call_id"), str)
        ):
            continue
        try:
            arguments = json.loads(str(payload.get("arguments", "")))
        except json.JSONDecodeError as exc:
            raise L3Error("raw coordinator spawn arguments are invalid") from exc
        if not isinstance(arguments, dict):
            raise L3Error("raw coordinator spawn arguments are invalid")
        if arguments.get("agent_type") == "modeling_agent" and arguments.get("fork_turns") == "none":
            eligible.append(payload["call_id"])
    if len(eligible) != 1:
        raise L3Error("raw coordinator lacks exactly one agent_type=modeling_agent fork_turns=none spawn")
    child_ids = {
        payload["agent_thread_id"]
        for value in _jsonl_items(coordinator_rollout, "coordinator rollout")
        if value.get("type") == "event_msg"
        and isinstance((payload := value.get("payload")), dict)
        and payload.get("type") == "sub_agent_activity"
        and payload.get("event_id") == eligible[0]
        and isinstance(payload.get("agent_thread_id"), str)
    }
    if len(child_ids) != 1:
        raise L3Error("raw coordinator spawn lacks exactly one linked sub_agent_activity child")
    child_id = child_ids.pop()
    child_rollout = _find_session_rollout(sessions, child_id)
    child_meta = _session_meta(child_rollout)
    spawn = child_meta.get("source", {}).get("subagent", {}).get("thread_spawn", {}) if isinstance(child_meta.get("source"), dict) else {}
    if (
        child_meta.get("parent_thread_id") != coordinator_id
        or child_meta.get("agent_role") != "modeling_agent"
        or not isinstance(spawn, dict)
        or spawn.get("parent_thread_id") != coordinator_id
        or spawn.get("agent_role") != "modeling_agent"
    ):
        raise L3Error("raw child session lacks matching Modeling Agent parent/role proof")
    return {
        "coordinator_thread_id": coordinator_id,
        "modeling_agent_thread_id": child_id,
        "coordinator_rollout": coordinator_rollout.relative_to(run_root).as_posix(),
        "coordinator_rollout_sha256": sha256_path(coordinator_rollout),
        "child_rollout": child_rollout.relative_to(run_root).as_posix(),
        "child_rollout_sha256": sha256_path(child_rollout),
    }


def _historical_evidence(run_id: str) -> dict[str, Any]:
    root = RUNTIME_ROOT / run_id / "audit"
    state_path = root / "state.json"
    transcript_path = root / "coordinator.jsonl"
    if not state_path.is_file() or not transcript_path.is_file():
        raise L3Error(f"historical run {run_id} lacks raw state/transcript evidence")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error(f"historical run {run_id} state is invalid") from exc
    if not isinstance(state, dict) or state.get("run_id") != run_id:
        raise L3Error(f"historical run {run_id} state identity drift")
    if state.get("state") != "INCONCLUSIVE" or state.get("category") != "runtime/infrastructure":
        raise L3Error(f"historical run {run_id} original classification drift")
    try:
        raw_child_audit: dict[str, Any] = raw_verified_modeling_child(RUNTIME_ROOT / run_id)
    except L3Error as exc:
        if run_id != "l3-real-20260730g" or "agent_type=modeling_agent" not in str(exc):
            raise
        raw_child_audit = {"verification": "rejected", "reason": str(exc)}
    return {
        "state_path": f"runtime/{state_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
        "state_sha256": sha256_path(state_path),
        "transcript_path": f"runtime/{transcript_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
        "transcript_sha256": sha256_path(transcript_path),
        "raw_child_audit": raw_child_audit,
    }


def _classification_correction(run_id: str) -> dict[str, Any]:
    if run_id == "l3-real-20260730g":
        authoritative = {"state": "PAUSED", "outcome": "NOT_PASSED", "category": "collaboration/routing"}
        reason = "child role not configured: linked child omitted agent_type=modeling_agent"
    else:
        authoritative = {"state": "SUPERSEDED", "outcome": "NOT_APPLICABLE", "category": "acceptance-harness"}
        reason = "raw parent/role/fork evidence passes; false no-child harness classification superseded"
    return {
        "event": "historical_classification_correction",
        "correction_id": f"l3-child-identity-correction-v2:{run_id}",
        "run_id": run_id,
        "original": {"state": "INCONCLUSIVE", "category": "runtime/infrastructure"},
        "authoritative": authoritative,
        "reason": reason,
        "evidence": _historical_evidence(run_id),
    }


def _recovery_terminal_correction() -> dict[str, Any] | None:
    root = RUNTIME_ROOT / RECOVERY_RUN_ID
    state_path, transcript_path = root / "audit" / "state.json", root / "audit" / "coordinator-resume-1.jsonl"
    if not root.exists():
        return None
    if not state_path.is_file() or not transcript_path.is_file():
        raise L3Error("recovery terminal correction lacks retained raw evidence")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error("recovery terminal state is invalid") from exc
    terminal = state.get("terminal_outcome") if isinstance(state, dict) else None
    pending = root / "team-work" / "pending-question.json"
    try:
        exact_wait_marker = _exact_agent_message_marker(transcript_path, "L3_WAITING_FOR_ANSWER")
    except L3Error as exc:
        raise L3Error("recovery terminal raw role-contract evidence drift") from exc
    if (
        not isinstance(state, dict)
        or state.get("run_id") != RECOVERY_RUN_ID
        or state.get("state") != "PAUSED"
        or state.get("category") != "platform-contract"
        or not isinstance(terminal, dict)
        or terminal.get("category") != "platform-contract"
        or not exact_wait_marker
        or pending.exists()
    ):
        raise L3Error("recovery terminal raw role-contract evidence drift")
    return {
        "event": "terminal_classification_correction",
        "correction_id": f"l3-wait-marker-correction-v1:{RECOVERY_RUN_ID}",
        "run_id": RECOVERY_RUN_ID,
        "original": {"state": "PAUSED", "outcome": "NOT_PASSED", "category": "platform-contract"},
        "authoritative": {"state": "PAUSED", "outcome": "NOT_PASSED", "category": "collaboration/routing"},
        "reason": "coordinator emitted L3_WAITING_FOR_ANSWER without atomically publishing pending-question.json",
        "evidence": {
            "state_path": f"runtime/{state_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "state_sha256": sha256_path(state_path),
            "transcript_path": f"runtime/{transcript_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "transcript_sha256": sha256_path(transcript_path),
            "pending_question_absent": True,
        },
    }


def _event_sha256(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event)).hexdigest()


def _recovery_pending_snapshot_path(root: Path) -> Path:
    return root / "audit" / "pending-question-before-release.json"


def _recovery_final_state_path(root: Path) -> Path:
    return root / "audit" / "recovery-final-state.json"


def _read_recovery_final_state(
    root: Path,
    coordinator_thread_id: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    path = _recovery_final_state_path(root)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error("recovery final state evidence drift") from exc
    coordinator = state.get("coordinator") if isinstance(state, dict) else None
    scope = state.get("scope") if isinstance(state, dict) else None
    cleanup = state.get("cleanup") if isinstance(state, dict) else None
    credentials = cleanup.get("protocol_credentials") if isinstance(cleanup, dict) else None
    required_audits = {
        "protocol_result": root / "audit" / "protocol-result.json",
        "protocol_rollout_audit": root / "audit" / "protocol-rollout-audit.json",
        "platform_fact_audit": root / "audit" / "platform-fact-audit.json",
    }
    if (
        not isinstance(state, dict)
        or state.get("run_id") != RECOVERY_WAIT_RUN_ID
        or state.get("state") != "PASS"
        or state.get("outcome") != "PASSED"
        or state.get("category") != "passed"
        or not isinstance(coordinator, dict)
        or coordinator.get("coordinator_thread_id") != coordinator_thread_id
        or not isinstance(scope, dict)
        or not all(isinstance(scope.get(key), str) for key in ("project_id", "ontology_id"))
        or not isinstance(state.get("protocol_rollout_audit"), dict)
        or not isinstance(state.get("platform_fact_audit"), dict)
        or not isinstance(cleanup, dict)
        or not all(
            cleanup.get(key) is True
            for key in ("model_key_revoked", "project_deleted", "host_admin_revoked", "isolated_runtime_exited")
        )
        or not isinstance(credentials, dict)
        or credentials.get("protocol_home_removed") is not True
        or credentials.get("secret_found_after_cleanup") is not False
        or not all(path.is_file() for path in required_audits.values())
    ):
        raise L3Error("recovery final state evidence drift")
    evidence = {
        "final_state_path": f"runtime/{path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
        "final_state_sha256": sha256_path(path),
        **{
            f"{name}_path": f"runtime/{audit_path.relative_to(RUNTIME_ROOT.parent).as_posix()}"
            for name, audit_path in required_audits.items()
        },
        **{
            f"{name}_sha256": sha256_path(audit_path)
            for name, audit_path in required_audits.items()
        },
    }
    return state, evidence


def _recovery_cycle_path(root: Path, index: int) -> Path:
    return root / "audit" / f"recovery-cycle-{index}.json"


def _recovery_resume_origin(root: Path, coordinator_thread_id: str, index: int) -> Path:
    path = root / "audit" / ("coordinator.jsonl" if index == 1 else f"coordinator-resume-{index}.jsonl")
    if (
        not path.is_file()
        or _outer_thread_id(path) != coordinator_thread_id
        or not _exact_agent_message_marker(path, "L3_WAITING_FOR_ANSWER")
    ):
        raise L3Error("recovery cycle originating resume evidence drift")
    return path


def _recovery_corrections(corrections: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    versions: dict[int, dict[str, Any]] = {}
    for value in corrections:
        correction_id = value.get("correction_id")
        if (
            value.get("event") != "recovery_state_correction"
            or value.get("run_id") != RECOVERY_WAIT_RUN_ID
            or not isinstance(correction_id, str)
        ):
            continue
        match = re.fullmatch(
            rf"l3-duplicate-first-modeling-gate-correction-v(\d+):{re.escape(RECOVERY_WAIT_RUN_ID)}",
            correction_id,
        )
        if not match or int(match.group(1)) in versions:
            raise L3Error("multiple authoritative recovery state corrections exist")
        versions[int(match.group(1))] = value
    for revision in range(5, max(versions, default=4) + 1):
        if revision not in versions:
            raise L3Error("recovery correction revision ordering drift")
        value, previous = versions[revision], versions[revision - 1]
        if (
            value.get("previous_correction_id") != previous.get("correction_id")
            or value.get("previous_correction_sha256") != _event_sha256(previous)
            or not isinstance(value.get("transition_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["transition_sha256"])
            or not isinstance(value.get("cycle_count"), int)
            or value["cycle_count"] < 1
            or not isinstance(value.get("cycle_head_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["cycle_head_sha256"])
        ):
            raise L3Error("recovery correction revision chain drift")
    return versions


def _recovery_cycle_records(
    root: Path,
    coordinator_thread_id: str,
    corrections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    contract = json.loads(ANSWER_CONTRACT.read_text(encoding="utf-8"))
    answers = {
        entry["id"]: {
            "answer_id": entry["id"],
            "answer": entry["answer"],
            "sha256": hashlib.sha256(entry["answer"].encode()).hexdigest(),
        }
        for entry in contract.get("answers", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("answer"), str)
    }
    correction_hashes = (
        {_event_sha256(value) for value in _recovery_corrections(corrections).values()}
        if corrections is not None
        else None
    )
    for path in sorted(root.glob("audit/recovery-cycle-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise L3Error("recovery cycle evidence drift") from exc
        required = {"cycle_index", "coordinator_thread_id", "pending_question", "pending_question_sha256", "answer", "originating_resume_transcript", "originating_resume_transcript_sha256", "prior_cycle_sha256", "prior_revision_sha256"}
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("coordinator_thread_id") != coordinator_thread_id
            or not _valid_grounded_question(value.get("pending_question"))
            or value.get("pending_question_sha256")
            != hashlib.sha256(canonical_json(value["pending_question"])).hexdigest()
            or not isinstance(value.get("answer"), dict)
            or answers.get(value["answer"].get("answer_id")) != value["answer"]
        ):
            raise L3Error("recovery cycle evidence drift")
        records.append(value)
    if [record.get("cycle_index") for record in records] != list(range(1, len(records) + 1)):
        raise L3Error("recovery cycle ordering drift")
    for index, record in enumerate(records):
        expected_origin = _recovery_resume_origin(root, coordinator_thread_id, index + 1)
        expected_origin_path = f"runtime/{expected_origin.relative_to(RUNTIME_ROOT.parent).as_posix()}"
        if (
            record["prior_cycle_sha256"] != (None if index == 0 else _event_sha256(records[index - 1]))
            or record["originating_resume_transcript"] != expected_origin_path
            or record["originating_resume_transcript_sha256"] != sha256_path(expected_origin)
            or (
                record["prior_revision_sha256"] is not None
                and (
                    not isinstance(record["prior_revision_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", record["prior_revision_sha256"])
                    or (
                        correction_hashes is not None
                        and record["prior_revision_sha256"] not in correction_hashes
                    )
                )
            )
        ):
            raise L3Error("recovery cycle prior-link drift")
    return records


def _recovery_transition(
    root: Path,
    coordinator_thread_id: str,
    records: list[dict[str, Any]],
    pending: Path,
    released: Path,
) -> dict[str, Any]:
    pending_evidence: dict[str, Any] | None = None
    if pending.exists():
        try:
            question = json.loads(pending.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise L3Error("recovery waiting raw role-contract evidence drift") from exc
        if not _valid_grounded_question(question):
            raise L3Error("recovery waiting raw role-contract evidence drift")
        origin = _recovery_resume_origin(root, coordinator_thread_id, len(records) + 1)
        pending_evidence = {
            "question_sha256": hashlib.sha256(canonical_json(question)).hexdigest(),
            "file_sha256": sha256_path(pending),
            "origin_transcript": f"runtime/{origin.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "origin_transcript_sha256": sha256_path(origin),
        }
    released_evidence = _released_answer_is_exact(root / "team-work", allow_pending=True) if released.exists() else None
    transition = {
        "cycle_count": len(records),
        "cycle_head_sha256": _event_sha256(records[-1]) if records else None,
        "pending": pending_evidence,
        "released_answer": released_evidence,
        "next_resume_index": len(list((root / "audit").glob("coordinator-resume-*.jsonl"))) + 1,
    }
    return {**transition, "transition_sha256": hashlib.sha256(canonical_json(transition)).hexdigest()}


def _valid_grounded_question(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"question", "sources", "affected_conclusion"}
        and isinstance(value.get("question"), str)
        and isinstance(value.get("affected_conclusion"), str)
        and isinstance(value.get("sources"), list)
        and bool(value["sources"])
        and all(isinstance(source, str) for source in value["sources"])
    )


def _read_recovery_pending_snapshot(
    root: Path,
    coordinator_thread_id: str,
    pending: Path | None,
) -> dict[str, Any] | None:
    snapshot_path = _recovery_pending_snapshot_path(root)
    if not snapshot_path.exists():
        return None
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error("recovery pending snapshot evidence drift") from exc
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"snapshot_version", "coordinator_thread_id", "pending_question", "pending_question_sha256"}
        or snapshot.get("snapshot_version") != 1
        or snapshot.get("coordinator_thread_id") != coordinator_thread_id
        or not _valid_grounded_question(snapshot.get("pending_question"))
        or not isinstance(snapshot.get("pending_question_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["pending_question_sha256"])
    ):
        raise L3Error("recovery pending snapshot evidence drift")
    if pending is not None:
        try:
            question = json.loads(pending.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise L3Error("recovery waiting raw role-contract evidence drift") from exc
        if question != snapshot["pending_question"] or sha256_path(pending) != snapshot["pending_question_sha256"]:
            raise L3Error("recovery pending snapshot evidence drift")
    return snapshot


def _recovery_wait_correction(
    events: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Preserve k's raw failure while correcting only its duplicate first-modeling gate."""
    root = RUNTIME_ROOT / RECOVERY_WAIT_RUN_ID
    state_path, transcript_path = root / "audit" / "state.json", root / "audit" / "coordinator.jsonl"
    pending = root / "team-work" / "pending-question.json"
    if not root.exists():
        return None
    if not state_path.is_file() or not transcript_path.is_file():
        raise L3Error("recovery waiting correction lacks retained raw evidence")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error("recovery waiting raw role-contract evidence drift") from exc
    terminal = state.get("terminal_outcome") if isinstance(state, dict) else None
    coordinator = state.get("coordinator") if isinstance(state, dict) else None
    child = raw_verified_modeling_child(root)
    if (
        not isinstance(state, dict)
        or state.get("run_id") != RECOVERY_WAIT_RUN_ID
        or state.get("state") != "PAUSED"
        or state.get("outcome") != "NOT_PASSED"
        or state.get("category") != "runtime/infrastructure"
        or state.get("error") != "20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED"
        or not isinstance(terminal, dict)
        or terminal.get("category") != "runtime/infrastructure"
        or not isinstance(coordinator, dict)
        or coordinator.get("coordinator_thread_id") != child["coordinator_thread_id"]
        or coordinator.get("modeling_agent_thread_id") != child["modeling_agent_thread_id"]
        or not _exact_agent_message_marker(transcript_path, "L3_WAITING_FOR_ANSWER")
    ):
        raise L3Error("recovery waiting raw role-contract evidence drift")
    candidate_path = root / "team-work" / "approved-candidate.json"
    dispatch_path = root / "team-work" / "protocol-dispatch.json"
    if candidate_path.exists() != dispatch_path.exists():
        raise L3Error("recovery coordinator dispatch evidence is incomplete")
    dispatched = candidate_path.exists()
    dispatch_resume: Path | None = None
    if dispatched:
        _candidate_and_dispatch(root / "team-work")
        resumes = sorted((root / "audit").glob("coordinator-resume-*.jsonl"))
        if not resumes:
            raise L3Error("recovery coordinator dispatch lacks a resume transcript")
        dispatch_resume = resumes[-1]
        if (
            _outer_thread_id(dispatch_resume) != child["coordinator_thread_id"]
            or not _exact_agent_message_marker(dispatch_resume, "L3_COORDINATOR_DISPATCHED")
        ):
            raise L3Error("recovery coordinator dispatch marker evidence drift")
    final_state = _read_recovery_final_state(root, child["coordinator_thread_id"])
    released = root / "team-work" / "released-answer.json"
    snapshot = _read_recovery_pending_snapshot(
        root,
        child["coordinator_thread_id"],
        pending if pending.exists() and not released.exists() else None,
    )
    current_cycle: dict[str, Any] = {}
    versions = _recovery_corrections(corrections)
    completed_cycles = _recovery_cycle_records(root, child["coordinator_thread_id"], corrections)
    if pending.exists():
        try:
            question = json.loads(pending.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise L3Error("recovery waiting raw role-contract evidence drift") from exc
        if not _valid_grounded_question(question):
            raise L3Error("recovery waiting raw role-contract evidence drift")
        if released.exists():
            if snapshot is None:
                raise L3Error("recovery waiting requires a prior cycle snapshot")
            _released_answer_is_exact(root / "team-work", allow_pending=True)
            completed = len(completed_cycles) if completed_cycles else 1
            cycle_index = completed + 1
            origin = _recovery_resume_origin(root, child["coordinator_thread_id"], cycle_index)
            current_cycle = {"cycle_index": cycle_index, "pending_question_sha256": sha256_path(pending), "originating_resume_transcript": f"runtime/{origin.relative_to(RUNTIME_ROOT.parent).as_posix()}", "originating_resume_transcript_sha256": sha256_path(origin)}
    elif snapshot is None:
        raise L3Error("recovery waiting requires a pending snapshot after answer release")
    else:
        _released_answer_is_exact(root / "team-work")
    halts = [event for event in events if event.get("event") == "preparation_halted" and event.get("reason") == DUPLICATE_GATE_HALT_REASON]
    terminals = [
        event
        for event in events
        if event.get("event") == "terminal_outcome"
        and event.get("run_id") == RECOVERY_WAIT_RUN_ID
        and event.get("category") == "runtime/infrastructure"
        and event.get("outcome") == "NOT_PASSED"
    ]
    if len(halts) != 1 or len(terminals) != 1:
        raise L3Error("recovery waiting duplicated-gate ledger evidence drift")
    resume_transcript = root / "audit" / "coordinator-resume-1.jsonl"
    resume_stderr = root / "audit" / "coordinator-resume-1.stderr.log"
    revision = (
        2 * len(completed_cycles) + 3
        if final_state
        else
        2 * len(completed_cycles) + 2
        if dispatched
        else
        2 * current_cycle["cycle_index"]
        if current_cycle
        else 2 * len(completed_cycles) + 1
        if len(completed_cycles) > 1
        else 2
        if snapshot
        else 1
    )
    resume_evidence: dict[str, Any] = {}
    if resume_transcript.exists() or resume_stderr.exists():
        prior_id = f"l3-duplicate-first-modeling-gate-correction-v2:{RECOVERY_WAIT_RUN_ID}"
        prior = [value for value in corrections if value.get("correction_id") == prior_id]
        if len(prior) != 1 or snapshot is None or not resume_transcript.is_file() or not resume_stderr.is_file():
            raise L3Error("recovery resume harness evidence lacks one snapshot-bound prior correction")
        transcript = resume_transcript.read_text(encoding="utf-8", errors="replace")
        stderr = resume_stderr.read_text(encoding="utf-8", errors="replace")
        coordinator_id = child["coordinator_thread_id"]
        try:
            resumed_thread_id = _outer_thread_id(resume_transcript)
        except L3Error as exc:
            raise L3Error("recovery resume harness evidence drift") from exc
        if (
            resumed_thread_id != coordinator_id
            or "resumed session is read-only" not in transcript
            or "read-only sandbox" not in stderr
        ):
            raise L3Error("recovery resume harness evidence drift")
        revision = max(revision, 3)
        resume_evidence = {
            "released_answer_path": f"runtime/{released.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "released_answer_sha256": sha256_path(released),
            "resume_transcript_path": f"runtime/{resume_transcript.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "resume_transcript_sha256": sha256_path(resume_transcript),
            "resume_stderr_path": f"runtime/{resume_stderr.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "resume_stderr_sha256": sha256_path(resume_stderr),
            "prior_correction_id": prior_id,
            "prior_correction_sha256": _event_sha256(prior[0]),
        }
    correction = {
        "event": "recovery_state_correction",
        "correction_id": f"l3-duplicate-first-modeling-gate-correction-v{revision}:{RECOVERY_WAIT_RUN_ID}",
        "run_id": RECOVERY_WAIT_RUN_ID,
        "original": {"state": "PAUSED", "outcome": "NOT_PASSED", "category": "runtime/infrastructure"},
        "authoritative": {
            "state": "PASS" if final_state else "READY_FOR_PROTOCOL" if dispatched else "WAITING_FOR_ANSWER",
            "outcome": "PASSED" if final_state else "PENDING",
            "category": "passed" if final_state else "pending",
            "modeling_started": {
                "coordinator_thread_id": child["coordinator_thread_id"],
                "modeling_agent_thread_id": child["modeling_agent_thread_id"],
            },
        },
        "reason": (
            "same recovered run completed Protocol application, governed checks, and cleanup"
            if final_state
            else "same coordinator published the validated candidate and protocol dispatch"
            if dispatched
            else "valid child modeling and pending question completed before the duplicated post-child deadline check"
        ),
        "supersedes": {
            "preparation_halted": halts[0],
            "preparation_halted_sha256": _event_sha256(halts[0]),
            "terminal_outcome": terminals[0],
            "terminal_outcome_sha256": _event_sha256(terminals[0]),
        },
        "evidence": {
            "state_path": f"runtime/{state_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "state_sha256": sha256_path(state_path),
            "transcript_path": f"runtime/{transcript_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
            "transcript_sha256": sha256_path(transcript_path),
            "coordinator_rollout": child["coordinator_rollout"],
            "coordinator_rollout_sha256": child["coordinator_rollout_sha256"],
            "child_rollout": child["child_rollout"],
            "child_rollout_sha256": child["child_rollout_sha256"],
            **(
                {
                    "pending_snapshot_path": f"runtime/{_recovery_pending_snapshot_path(root).relative_to(RUNTIME_ROOT.parent).as_posix()}",
                    "pending_snapshot_sha256": sha256_path(_recovery_pending_snapshot_path(root)),
                    "pending_question_sha256": snapshot["pending_question_sha256"],
                    "snapshot_coordinator_thread_id": snapshot["coordinator_thread_id"],
                }
                if snapshot
                else {
                    "pending_question_path": f"runtime/{pending.relative_to(RUNTIME_ROOT.parent).as_posix()}",
                    "pending_question_sha256": sha256_path(pending),
                }
            ),
            **resume_evidence,
            **({"current_cycle": current_cycle} if current_cycle else {}),
            **(
                {
                    "dispatch_candidate_path": f"runtime/{candidate_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
                    "dispatch_candidate_sha256": sha256_path(candidate_path),
                    "protocol_dispatch_path": f"runtime/{dispatch_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
                    "protocol_dispatch_sha256": sha256_path(dispatch_path),
                    "dispatch_resume_path": f"runtime/{dispatch_resume.relative_to(RUNTIME_ROOT.parent).as_posix()}",
                    "dispatch_resume_sha256": sha256_path(dispatch_resume),
                }
                if dispatched and dispatch_resume is not None
                else {}
            ),
            **(final_state[1] if final_state else {}),
        },
    }
    if resume_evidence:
        correction["harness_failure"] = {
            "category": "runtime/infrastructure",
            "reason": "resume adapter omitted workspace-write and cwd before exec resume",
        }
    if revision >= 5:
        previous = versions.get(revision - 1)
        if previous is None:
            raise L3Error("recovery correction revision chain drift")
        transition = _recovery_transition(
            root,
            child["coordinator_thread_id"],
            completed_cycles,
            pending,
            released,
        )
        correction.update(
            {
                "previous_correction_id": previous["correction_id"],
                "previous_correction_sha256": _event_sha256(previous),
                "transition_sha256": transition["transition_sha256"],
                "cycle_count": transition["cycle_count"],
                "cycle_head_sha256": transition["cycle_head_sha256"],
            }
        )
        correction["evidence"]["transition"] = transition
    return correction


def _reconcile_historical_classifications(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    CLASSIFICATION_LEDGER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with CLASSIFICATION_LEDGER.open("a+", encoding="utf-8") as stream:
        stream.seek(0)
        corrections = _read_jsonl(CLASSIFICATION_LEDGER)
        present = [run_id for run_id in HISTORICAL_RUN_IDS if (RUNTIME_ROOT / run_id).exists()]
        if present and set(present) != set(HISTORICAL_RUN_IDS):
            raise L3Error("historical classification coverage is incomplete")
        existing = {value.get("correction_id"): value for value in corrections}
        if present:
            for run_id in HISTORICAL_RUN_IDS:
                correction = _classification_correction(run_id)
                previous = existing.get(correction["correction_id"])
                if previous is None:
                    _append_locked(stream, correction)
                    corrections.append(correction)
                    existing[correction["correction_id"]] = correction
                elif previous != correction:
                    raise L3Error(f"historical classification evidence hash drift: {run_id}")
        correction = _recovery_terminal_correction()
        if correction:
            previous = existing.get(correction["correction_id"])
            if previous is None:
                _append_locked(stream, correction)
                corrections.append(correction)
            elif previous != correction:
                raise L3Error("recovery terminal classification evidence hash drift")
        correction = _recovery_wait_correction(events, corrections)
        if correction:
            previous = existing.get(correction["correction_id"])
            if previous is None:
                _append_locked(stream, correction)
                corrections.append(correction)
            elif previous != correction:
                raise L3Error("recovery waiting classification evidence hash drift")
        return corrections


def _with_global_ledger(callback):
    GLOBAL_LOCK.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with GLOBAL_LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            GLOBAL_LEDGER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with GLOBAL_LEDGER.open("a+", encoding="utf-8") as stream:
                stream.seek(0)
                events = _reconcile_historical_starts(stream, _read_jsonl(GLOBAL_LEDGER))
                classifications = _reconcile_historical_classifications(events)
                return callback(stream, events, classifications)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _team_start_count(events: list[dict[str, Any]]) -> int:
    return sum(event.get("event") in {"historical_coordinator_started", "coordinator_started"} for event in events)


def _historical_start_count(events: list[dict[str, Any]]) -> int:
    return sum(event.get("event") == "historical_coordinator_started" for event in events)


def _terminal_modeling_quality(events: list[dict[str, Any]]) -> bool:
    return any(event.get("event") == "terminal_outcome" and event.get("category") == "modeling-quality" for event in events)


def _authoritative_terminal_category(run_id: object, events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> str | None:
    if not isinstance(run_id, str):
        return None
    corrections = [
        value
        for value in classifications
        if value.get("event") == "terminal_classification_correction" and value.get("run_id") == run_id
    ]
    if len(corrections) > 1:
        raise L3Error("multiple authoritative terminal corrections exist")
    if corrections:
        authoritative = corrections[0].get("authoritative")
        if not isinstance(authoritative, dict) or not isinstance(authoritative.get("category"), str):
            raise L3Error("authoritative terminal correction is invalid")
        return authoritative["category"]
    matches = [event.get("category") for event in events if event.get("event") == "terminal_outcome" and event.get("run_id") == run_id]
    return matches[0] if len(matches) == 1 and isinstance(matches[0], str) else None


def _authoritative_recovery_state(run_id: object, classifications: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(run_id, str):
        return None
    corrections = [
        value
        for value in classifications
        if value.get("event") == "recovery_state_correction" and value.get("run_id") == run_id
    ]
    if not corrections:
        return None
    versions = _recovery_corrections(corrections)
    selected = versions[max(versions)]
    authoritative = selected.get("authoritative")
    valid_terminal = (
        authoritative.get("state") == "PASS"
        and authoritative.get("outcome") == "PASSED"
        and authoritative.get("category") == "passed"
    ) if isinstance(authoritative, dict) else False
    valid_pending = (
        authoritative.get("state") in {"WAITING_FOR_ANSWER", "READY_FOR_PROTOCOL"}
        and authoritative.get("outcome") == "PENDING"
        and authoritative.get("category") == "pending"
    ) if isinstance(authoritative, dict) else False
    if (
        not isinstance(authoritative, dict)
        or not (valid_pending or valid_terminal)
        or not isinstance(authoritative.get("modeling_started"), dict)
    ):
        raise L3Error("authoritative recovery state correction is invalid")
    return authoritative


def _has_active_preparation_halt(events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> bool:
    superseded = {
        value.get("supersedes", {}).get("preparation_halted_sha256")
        for value in classifications
        if value.get("event") == "recovery_state_correction" and isinstance(value.get("supersedes"), dict)
    }
    return any(
        event.get("event") == "preparation_halted" and _event_sha256(event) not in superseded
        for event in events
    )


def _start_five_is_repairable(events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> bool:
    fresh_starts = [event for event in events if event.get("event") == "coordinator_started"]
    if len(fresh_starts) != 1:
        return False
    fourth_run_id = fresh_starts[0].get("run_id")
    return _authoritative_terminal_category(fourth_run_id, events, classifications) in {
        "runtime/infrastructure",
        "platform-contract",
        "collaboration/routing",
    }


def _has_valid_first_modeling(events: list[dict[str, Any]], policy: dict[str, Any]) -> bool:
    expected_preparation = recovery_preparation_started_at(policy)
    deadline = first_modeling_deadline(policy)
    coordinator_runs = {event.get("run_id") for event in events if event.get("event") == "coordinator_started"}
    for event in events:
        if (
            event.get("event") != "modeling_started"
            or event.get("run_id") not in coordinator_runs
            or not isinstance(event.get("coordinator_thread_id"), str)
            or not isinstance(event.get("modeling_agent_thread_id"), str)
            or not isinstance(event.get("first_modeling_started_at"), str)
            or event.get("preparation_started_at") != expected_preparation.isoformat()
        ):
            continue
        try:
            started = datetime.fromisoformat(event["first_modeling_started_at"])
        except ValueError:
            continue
        if started.tzinfo is not None and expected_preparation <= started <= deadline:
            return True
    return False


def reserve_coordinator_start(run_id: str, at: datetime | None = None) -> dict[str, Any]:
    """Reserve one globally budgeted fresh coordinator start before any live resource exists."""
    policy = require_live_execution_authorized()
    preparation_started_at = recovery_preparation_started_at(policy)
    deadline = first_modeling_deadline(policy)
    at = at or datetime.now(deadline.tzinfo)

    def reserve(stream, events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> dict[str, Any]:
        if _has_active_preparation_halt(events, classifications):
            raise L3Error("L3 is paused after the first-modeling deadline")
        if _historical_start_count(events) != policy["starts_consumed"]:
            raise L3Error("global historical start ledger does not match committed execution policy")
        if _terminal_modeling_quality(events):
            raise L3Error("L3 completed-model modeling-quality failure prohibits another start")
        if _team_start_count(events) >= policy["max_starts"]:
            raise L3Error("L3 global coordinator start limit reached; state is PAUSED/NOT_PASSED")
        if (
            policy["starts_consumed"] == 3
            and _team_start_count(events) == policy["max_starts"] - 1
            and not _start_five_is_repairable(events, classifications)
        ):
            raise L3Error("L3 start 5 requires a repairable terminal outcome from start 4")
        if at > deadline and not _has_valid_first_modeling(events, policy):
            halt = {"event": "preparation_halted", "at": at.isoformat(), "reason": "20-minute first-modeling gate missed"}
            _append_locked(stream, halt)
            raise L3Error("20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED")
        event = {"event": "coordinator_started", "run_id": run_id, "started_at": at.isoformat(), "preparation_started_at": preparation_started_at.isoformat()}
        _append_locked(stream, event)
        return event

    return _with_global_ledger(reserve)


def record_terminal_outcome(run_id: str, category: str, outcome: str = "NOT_PASSED") -> dict[str, Any]:
    """Retain terminal classification so a semantic failure closes the remaining start budget."""
    if category not in {"runtime/infrastructure", "platform-contract", "collaboration/routing", "modeling-quality"}:
        raise L3Error("terminal category is invalid")
    if outcome != "NOT_PASSED":
        raise L3Error("terminal outcome is invalid")

    def record(stream, events: list[dict[str, Any]], _classifications: list[dict[str, Any]]) -> dict[str, Any]:
        if not any(event.get("event") == "coordinator_started" and event.get("run_id") == run_id for event in events):
            raise L3Error("terminal outcome lacks an owned coordinator start")
        if any(event.get("event") == "terminal_outcome" and event.get("run_id") == run_id for event in events):
            raise L3Error("terminal outcome is already recorded")
        event = {"event": "terminal_outcome", "run_id": run_id, "category": category, "outcome": outcome, "at": now()}
        _append_locked(stream, event)
        return event

    return _with_global_ledger(record)


def record_modeling_delegation(
    run_id: str,
    coordinator_thread_id: str,
    modeling_agent_thread_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Record the first real modeling time only after a verifiable child identity exists."""
    policy = read_execution_policy()
    preparation_started_at = recovery_preparation_started_at(policy)
    deadline = first_modeling_deadline(policy)
    at = at or datetime.now(deadline.tzinfo)
    if not coordinator_thread_id or not modeling_agent_thread_id:
        raise L3Error("modeling delegation lacks authoritative child Session identity")

    def record(stream, events: list[dict[str, Any]], _classifications: list[dict[str, Any]]) -> dict[str, Any]:
        if at > deadline and not _has_valid_first_modeling(events, policy):
            _append_locked(stream, {"event": "preparation_halted", "at": at.isoformat(), "reason": "20-minute first-modeling gate missed before child delegation"})
            raise L3Error("20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED")
        if not any(event.get("event") == "coordinator_started" and event.get("run_id") == run_id for event in events):
            raise L3Error("modeling delegation lacks an owned coordinator start")
        if any(event.get("event") == "modeling_started" and event.get("run_id") == run_id for event in events):
            raise L3Error("first modeling delegation is already recorded")
        event = {"event": "modeling_started", "run_id": run_id, "coordinator_thread_id": coordinator_thread_id, "modeling_agent_thread_id": modeling_agent_thread_id, "first_modeling_started_at": at.isoformat(), "preparation_started_at": preparation_started_at.isoformat()}
        _append_locked(stream, event)
        return event

    return _with_global_ledger(record)


def local_scenario_status() -> dict[str, Any]:
    """Read local ignored evidence only when it exists; it cannot authorize execution."""
    def status(_stream, events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> dict[str, Any]:
        halted = _has_active_preparation_halt(events, classifications)
        starts = _team_start_count(events)
        historical_starts = _historical_start_count(events)
        semantic_terminal = _terminal_modeling_quality(events)
        ledger_path = f"runtime/{CLASSIFICATION_LEDGER.relative_to(RUNTIME_ROOT.parent).as_posix()}"
        current_corrections = [value for value in classifications if str(value.get("correction_id", "")).startswith("l3-child-identity-correction-v2:")]
        recovery_wait = _authoritative_recovery_state(RECOVERY_WAIT_RUN_ID, classifications)
        if recovery_wait:
            return {"state": recovery_wait["state"], "outcome": recovery_wait["outcome"], "category": recovery_wait["category"], "team_starts": starts, "historical_starts": historical_starts, "halted": halted, "classification_ledger": ledger_path, "classification_count": len(current_corrections), "terminal_correction_count": 1, "recovery_correction_count": 1}
        recovery_category = _authoritative_terminal_category(RECOVERY_RUN_ID, events, classifications)
        if recovery_category:
            return {"state": "PAUSED", "outcome": "NOT_PASSED", "category": recovery_category, "team_starts": starts, "historical_starts": historical_starts, "halted": halted, "classification_ledger": ledger_path, "classification_count": len(current_corrections), "terminal_correction_count": 1}
        if halted or semantic_terminal or starts >= read_execution_policy()["max_starts"]:
            category = "modeling-quality" if semantic_terminal else "pending"
            return {"state": "PAUSED", "outcome": "NOT_PASSED", "category": category, "team_starts": starts, "historical_starts": historical_starts, "halted": halted, "classification_ledger": ledger_path, "classification_count": len(current_corrections)}
        return {"state": "READY", "outcome": "PENDING", "category": "pending", "team_starts": starts, "historical_starts": historical_starts, "halted": False, "classification_ledger": ledger_path, "classification_count": len(current_corrections)}

    state = _with_global_ledger(status)
    atomic_json(SCENARIO_STATE, {**state, "updated_at": now()})
    return state


def scenario_status() -> dict[str, Any]:
    """Report the committed policy and, when present, fail closed on local-evidence drift."""
    policy = read_execution_policy()
    local_paths = (RUNTIME_ROOT.exists(), GLOBAL_LEDGER.exists(), CLASSIFICATION_LEDGER.exists())
    if not any(local_paths):
        return {"policy": policy, "local_ledger": {"available": False, "agreement": "unavailable"}}
    local = local_scenario_status()
    agreement = (
        local["historical_starts"] == policy["starts_consumed"]
        and policy["starts_consumed"] <= local["team_starts"] <= policy["max_starts"]
        and set(policy["run_ids"]) == set(HISTORICAL_RUN_IDS)
        and local["classification_count"] == len(policy["run_ids"])
    )
    if not agreement:
        raise L3Error("committed execution policy and local L3 ledger disagree")
    return {"policy": policy, "local_ledger": {"available": True, "agreement": "confirmed", **local}}


def record_question(work: Path, question: dict[str, Any]) -> dict[str, Any]:
    required = {"question", "sources", "affected_conclusion"}
    pending = work / "pending-question.json"
    if pending.exists() or not isinstance(question, dict) or set(question) != required or not isinstance(question["sources"], list) or not question["sources"]:
        raise L3Error("one grounded pending question is required")
    atomic_json(pending, question)
    return question


def _snapshot_recovery_pending_question(work: Path, answer: dict[str, Any] | None = None) -> None:
    """Freeze k's grounded question before normal answer release deletes the mutable file."""
    root = work.parent
    if root.name != RECOVERY_WAIT_RUN_ID:
        return
    pending = work / "pending-question.json"
    raw_state = _read_run_state(root)
    coordinator = raw_state.get("coordinator")
    child = raw_verified_modeling_child(root)
    try:
        question = json.loads(pending.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise L3Error("recovery pending snapshot requires a grounded pending question") from exc
    if (
        not isinstance(coordinator, dict)
        or coordinator.get("coordinator_thread_id") != child["coordinator_thread_id"]
        or not _valid_grounded_question(question)
    ):
        raise L3Error("recovery pending snapshot coordinator/question evidence drift")
    snapshot = {
        "snapshot_version": 1,
        "coordinator_thread_id": child["coordinator_thread_id"],
        "pending_question": question,
        "pending_question_sha256": sha256_path(pending),
    }
    snapshot_path = _recovery_pending_snapshot_path(root)
    if snapshot_path.exists():
        existing = _read_recovery_pending_snapshot(
            root,
            child["coordinator_thread_id"],
            pending if not (work / "released-answer.json").exists() else None,
        )
        if existing != snapshot and not (work / "released-answer.json").exists():
            raise L3Error("recovery pending snapshot evidence drift")
    else:
        atomic_json(snapshot_path, snapshot)
    if answer is None:
        return
    revisions = [
        value
        for value in _read_jsonl(CLASSIFICATION_LEDGER)
        if value.get("event") == "recovery_state_correction"
        and value.get("run_id") == RECOVERY_WAIT_RUN_ID
    ]
    records = _recovery_cycle_records(root, child["coordinator_thread_id"], revisions)
    released = work / "released-answer.json"
    if released.exists() and not records:
        prior_answer = _released_answer_is_exact(work, allow_pending=True)
        legacy = _read_recovery_pending_snapshot(root, child["coordinator_thread_id"], None)
        prior = {"cycle_index": 1, "coordinator_thread_id": child["coordinator_thread_id"], "pending_question": legacy["pending_question"], "pending_question_sha256": hashlib.sha256(canonical_json(legacy["pending_question"])).hexdigest(), "answer": prior_answer, "originating_resume_transcript": "runtime/runs/l3-real-20260730k/audit/coordinator.jsonl", "originating_resume_transcript_sha256": sha256_path(root / "audit" / "coordinator.jsonl"), "prior_cycle_sha256": None, "prior_revision_sha256": None}
        atomic_json(_recovery_cycle_path(root, 1), prior)
        records = [prior]
    index = len(records) + 1
    origin = _recovery_resume_origin(root, child["coordinator_thread_id"], index)
    previous = records[-1] if records else None
    record = {"cycle_index": index, "coordinator_thread_id": child["coordinator_thread_id"], "pending_question": question, "pending_question_sha256": hashlib.sha256(canonical_json(question)).hexdigest(), "answer": answer, "originating_resume_transcript": f"runtime/{origin.relative_to(RUNTIME_ROOT.parent).as_posix()}", "originating_resume_transcript_sha256": sha256_path(origin), "prior_cycle_sha256": _event_sha256(previous) if previous else None, "prior_revision_sha256": _event_sha256(revisions[-1]) if revisions else None}
    record_path = _recovery_cycle_path(root, index)
    if record_path.exists():
        if json.loads(record_path.read_text(encoding="utf-8")) != record:
            raise L3Error("recovery cycle evidence drift")
    else:
        atomic_json(record_path, record)


def release_answer(work: Path, answer_id: str) -> dict[str, Any]:
    pending = work / "pending-question.json"
    if not pending.exists():
        raise L3Error("answer cannot be released without a pending question")
    contract = json.loads(ANSWER_CONTRACT.read_text(encoding="utf-8"))
    matches = [entry for entry in contract["answers"] if entry["id"] == answer_id]
    if len(matches) != 1:
        raise L3Error("unsupported question must not receive an invented answer")
    answer = {"answer_id": answer_id, "answer": matches[0]["answer"], "sha256": hashlib.sha256(matches[0]["answer"].encode()).hexdigest()}
    if work.parent.name == RECOVERY_WAIT_RUN_ID:
        # Bind the current pending transition before replacing the prior released answer.
        local_scenario_status()
    _snapshot_recovery_pending_question(work, answer)
    atomic_json(work / "released-answer.json", answer)
    pending.unlink()
    if work.parent.name == RECOVERY_WAIT_RUN_ID:
        local_scenario_status()
    return answer


def isolated_command(paths: dict[str, Path], settings: dict[str, str], port: int) -> list[str]:
    """The isolated REST namespace mounts exactly app, venv, and the verified reasoner script."""
    python = BACKEND_ROOT / ".venv" / "bin" / "python"
    if not python.is_file() or not REASONER_SCRIPT.is_file():
        raise L3Error("isolated runtime prerequisites are unavailable")
    runtime = python.resolve().parent.parent
    command = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    for index in range(1, len(runtime.parts) - 1):
        command.extend(["--dir", str(Path("/").joinpath(*runtime.parts[1 : index + 1]))])
    command.extend(["--dir", "/backend", "--ro-bind", str(APP_ROOT), "/backend/app", "--ro-bind", str(BACKEND_ROOT / ".venv"), "/backend/.venv", "--ro-bind", str(runtime), str(runtime), "--dir", "/backend/scripts", "--ro-bind", str(REASONER_SCRIPT), "/backend/scripts/dev_owl_reasoner.py", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--setenv", "PATH", "/backend/.venv/bin:/usr/bin:/bin", "--setenv", "PYTHONPATH", "/backend", "--setenv", "SEMANTIC_REASONER_COMMAND", "/backend/scripts/dev_owl_reasoner.py"])
    for key, value in sorted(settings.items()):
        command.extend(["--setenv", key, value])
    return [*command, "--", "/backend/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]


def http(base: str, method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    call = request.Request(base.rstrip("/") + path, data=canonical_json(body) if body is not None else None, method=method, headers=headers)
    try:
        with request.urlopen(call, timeout=25) as response:
            raw = response.read()
            return {"status": response.status, "body": json.loads(raw) if raw else {}}
    except error.HTTPError as exc:
        raw = exc.read()
        return {"status": exc.code, "body": json.loads(raw) if raw else {}}
    except OSError as exc:
        raise L3Error(f"HTTP {method} {path} failed") from exc


def require_ok(result: dict[str, Any], expected: set[int] = {200, 201, 204}) -> dict[str, Any]:
    if result["status"] not in expected or not isinstance(result["body"], dict):
        raise L3Error(f"REST request failed: {result}")
    return result["body"]


def sanitized_settings() -> dict[str, str]:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    configured = Settings(_env_file=BACKEND_ROOT / ".env")
    return {"DATABASE_URL": str(configured.database_url), "OXIGRAPH_URL": str(configured.oxigraph_url), "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary", "SEMANTIC_CANONICAL_STORE": str(configured.semantic_canonical_store), "SEMANTIC_READ_MODE": str(configured.semantic_read_mode), "SEMANTIC_REASONER_TIMEOUT_SECONDS": str(configured.semantic_reasoner_timeout_seconds)}


def bootstrap_admin() -> tuple[str, str]:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.security.auth import create_api_key  # noqa: PLC0415
    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record, plaintext = create_api_key(session, name=f"r2-2-001-l3-probe-{int(time.time())}", project_id=None, scopes=["admin"])
    return plaintext, record.id


def revoke_admin(key_id: str) -> bool:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import Settings  # noqa: PLC0415
    from app.repositories.models import ApiKeyModel  # noqa: PLC0415
    from app.repositories.postgres import create_session_factory  # noqa: PLC0415
    from app.security.auth import revoke_key  # noqa: PLC0415
    with create_session_factory(Settings(_env_file=BACKEND_ROOT / ".env"))() as session:
        record = session.get(ApiKeyModel, key_id)
        return record is not None and revoke_key(session, record).revoked_at is not None


def cleanup_process(process: subprocess.Popen[str] | None) -> None:
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def launch_coordinator(run_root: Path) -> dict[str, Any]:
    """Launch the first fresh, no-MCP coordinator and retain its real transcript.

    Its prompt requires a child Modeling Agent delegation before any candidate or
    question.  The timestamp is recorded only immediately before this process starts.
    """
    if not CODEX_BINARY.is_file() or not HOST_CODEX_AUTH.is_file():
        raise L3Error("isolated Codex coordinator prerequisites are unavailable")
    visible, work, home = run_root / "coordinator-input", run_root / "team-work", run_root / "coordinator-home"
    work.mkdir(mode=0o700)
    home.mkdir(mode=0o700)
    shutil.copyfile(HOST_CODEX_AUTH, home / "auth.json")
    os.chmod(home / "auth.json", 0o600)
    agents = home / "agents"
    agents.mkdir(mode=0o700)
    shutil.copyfile(SCENARIO_ROOT / "agent-config" / "modeling-agent.toml", agents / "modeling_agent.toml")
    (home / "config.toml").write_text(
        "[features]\nmulti_agent = true\n[projects.\"/work\"]\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    command = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    command.extend(["--ro-bind", str(CODEX_BINARY.resolve()), "/codex", "--ro-bind", str(visible), "/opt", "--bind", str(work), "/work", "--bind", str(home), "/codex-home", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp", "--setenv", "CODEX_HOME", "/codex-home"])
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            command.extend(["--setenv", key, os.environ[key]])
    prompt = (AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8")
    transcript = run_root / "audit" / "coordinator.jsonl"
    started = time.monotonic()
    process = subprocess.run(
        [*command, "--", "/codex", "--ask-for-approval", "never", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "--ignore-rules", "--disable", "apps", "--disable", "browser_use", "--disable", "plugins", "--disable", "memories", "-C", "/work", "-"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    transcript.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    transcript.write_text(process.stdout, encoding="utf-8")
    transcript.with_suffix(".stderr.log").write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise L3Error(f"coordinator runtime/infrastructure: exit_{process.returncode}")
    child_audit = raw_verified_modeling_child(run_root)
    return {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "transcript": str(transcript),
        **child_audit,
    }


def _codex_exec_command(session_id: str | None = None) -> list[str]:
    common = [
        "/codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "-C",
        "/work",
        "--ignore-rules",
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "plugins",
        "--disable",
        "memories",
    ]
    if session_id:
        return [
            *common,
            "resume",
            session_id,
            "-",
        ]
    return [
        *common,
        "-",
    ]


def _coordinator_command(run_root: Path, session_id: str) -> list[str]:
    visible, work, home = run_root / "coordinator-input", run_root / "team-work", run_root / "coordinator-home"
    command = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    command.extend([
        "--ro-bind", str(CODEX_BINARY.resolve()), "/codex",
        "--ro-bind", str(visible), "/opt",
        "--bind", str(work), "/work",
        "--bind", str(home), "/codex-home",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "HOME", "/tmp",
        "--setenv", "CODEX_HOME", "/codex-home",
    ])
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            command.extend(["--setenv", key, os.environ[key]])
    return [*command, "--", *_codex_exec_command(session_id)]


def _protocol_command(run_root: Path, settings: dict[str, str]) -> list[str]:
    venv = BACKEND_ROOT / ".venv"
    home, visible, work = run_root / "protocol-home", run_root / "protocol-input", run_root / "protocol-work"
    if not (venv / "bin" / "python").is_file() or not REASONER_SCRIPT.is_file():
        raise L3Error("isolated protocol runtime prerequisites are unavailable")
    # Reuse the L1-proven runtime resolution. The venv interpreter is a symlink into uv's
    # managed Python tree; mounting venv.parent misses that target and exposes backend/.
    runtime = (venv / "bin" / "python").resolve().parent.parent
    command = ["bwrap", "--die-with-parent", "--new-session", "--share-net", "--clearenv"]
    for source in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/hosts", "/etc/resolv.conf"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    for index in range(1, len(runtime.parts) - 1):
        command.extend(["--dir", str(Path("/").joinpath(*runtime.parts[1 : index + 1]))])
    command.extend([
        "--ro-bind", str(CODEX_BINARY.resolve()), "/codex",
        "--dir", "/backend", "--ro-bind", str(APP_ROOT), "/backend/app",
        "--ro-bind", str(venv), "/backend/.venv", "--ro-bind", str(runtime), str(runtime),
        "--dir", "/backend/scripts", "--ro-bind", str(REASONER_SCRIPT), "/backend/scripts/dev_owl_reasoner.py",
        "--ro-bind", str(visible), "/opt", "--bind", str(work), "/work", "--bind", str(home), "/codex-home",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--setenv", "PATH", "/backend/.venv/bin:/usr/bin:/bin",
        "--setenv", "HOME", "/tmp", "--setenv", "CODEX_HOME", "/codex-home",
        "--setenv", "PYTHONPATH", "/backend", "--setenv", "SEMANTIC_REASONER_COMMAND", "/backend/scripts/dev_owl_reasoner.py",
    ])
    for key, value in sorted(settings.items()):
        command.extend(["--setenv", key, value])
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            command.extend(["--setenv", key, os.environ[key]])
    return [*command, "--", *_codex_exec_command()]


def _execute_command(
    command: list[str],
    prompt: str,
    transcript: Path,
    role: str,
    *,
    terminal_timeout_seconds: int = TERMINAL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    assert process.stdin and process.stdout and process.stderr
    process.stdin.write(prompt)
    process.stdin.close()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    first_seen, terminal_error = False, None
    transcript.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with transcript.open("w", encoding="utf-8") as out, transcript.with_suffix(".stderr.log").open("w", encoding="utf-8") as err:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if (not first_seen and elapsed > FIRST_RESPONSE_SECONDS) or elapsed > terminal_timeout_seconds:
                terminal_error = "first_response_timeout" if not first_seen else "terminal_timeout"
                os.killpg(process.pid, signal.SIGTERM)
                break
            for key, _ in selector.select(timeout=0.5):
                line = key.fileobj.readline()
                if not line:
                    continue
                target = out if key.data == "stdout" else err
                target.write(line)
                target.flush()
                if key.data == "stdout":
                    first_seen = True
                    if any(marker in line.lower() for marker in ("provider error", "agent terminal error", "fatal error")):
                        terminal_error = "agent_terminal_error"
                        os.killpg(process.pid, signal.SIGTERM)
                        break
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        for stream, target in ((process.stdout, out), (process.stderr, err)):
            remainder = stream.read()
            if remainder:
                target.write(remainder)
                target.flush()
            stream.close()
    selector.close()
    if terminal_error:
        raise L3Error(f"{role} runtime/infrastructure: {terminal_error}")
    if process.returncode != 0:
        raise L3Error(f"{role} runtime/infrastructure: exit_{process.returncode}")
    return {"exit_code": process.returncode, "elapsed_seconds": round(time.monotonic() - started, 3), "thread_id": _outer_thread_id(transcript)}


def _next_transcript(run_root: Path, prefix: str) -> Path:
    audit = run_root / "audit"
    index = 1
    while (audit / f"{prefix}-{index}.jsonl").exists():
        index += 1
    return audit / f"{prefix}-{index}.jsonl"


def _read_run_state(run_root: Path) -> dict[str, Any]:
    try:
        state = json.loads((run_root / "audit" / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("continuation requires a valid retained run state") from exc
    if not isinstance(state, dict) or state.get("run_id") != run_root.name:
        raise L3Error("continuation run state identity drift")
    return state


def _effective_continuation_state(run_id: str, raw_state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Overlay a hash-bound recovery state without rewriting the retained raw state."""
    def resolve(_stream, _events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> dict[str, Any] | None:
        return _authoritative_recovery_state(run_id, classifications)

    authoritative = _with_global_ledger(resolve)
    if authoritative is None:
        return raw_state, False
    return {**raw_state, **authoritative}, True


def _released_answer_is_exact(work: Path, *, allow_pending: bool = False) -> dict[str, Any]:
    pending, released = work / "pending-question.json", work / "released-answer.json"
    if pending.exists() and not allow_pending:
        raise L3Error("continuation requires Delivery to resolve the one pending question first")
    try:
        value = json.loads(released.read_text(encoding="utf-8"))
        contract = json.loads(ANSWER_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("continuation requires a valid mechanically released answer") from exc
    matches = [entry for entry in contract.get("answers", []) if entry.get("id") == value.get("answer_id")]
    if len(matches) != 1 or value != {
        "answer_id": matches[0]["id"],
        "answer": matches[0]["answer"],
        "sha256": hashlib.sha256(matches[0]["answer"].encode()).hexdigest(),
    }:
        raise L3Error("released answer does not exactly match the frozen answer contract")
    return value


def _candidate_and_dispatch(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        candidate = json.loads((work / "approved-candidate.json").read_text(encoding="utf-8"))
        dispatch = json.loads((work / "protocol-dispatch.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("coordinator did not publish approved candidate and dispatch") from exc
    if not isinstance(candidate, dict) or not candidate:
        raise L3Error("approved candidate is invalid")
    encoded = canonical_json(candidate).decode("utf-8").lower()
    if any(marker in encoded for marker in ("plaintext_key", "batch_id", "build_session", "query", "receipt")):
        raise L3Error("approved candidate leaks protocol mechanics or credentials")
    expected = {"task_id", "candidate_sha256", "requested_outcome"}
    if (
        not isinstance(dispatch, dict)
        or set(dispatch) != expected
        or not isinstance(dispatch.get("task_id"), str)
        or dispatch.get("candidate_sha256") != "PENDING_LAUNCHER_CANONICALIZATION"
        or dispatch.get("requested_outcome") != "apply_published_c_b_a_path"
    ):
        raise L3Error("coordinator dispatch integrity drift")
    return candidate, {**dispatch, "candidate_sha256": hashlib.sha256(canonical_json(candidate)).hexdigest()}


def _write_protocol_config(home: Path, model_key: str, settings: dict[str, str]) -> None:
    home.mkdir(mode=0o700, exist_ok=False)
    shutil.copyfile(HOST_CODEX_AUTH, home / "auth.json")
    os.chmod(home / "auth.json", 0o600)
    agents = home / "agents"
    agents.mkdir(mode=0o700)
    shutil.copyfile(SCENARIO_ROOT / "agent-config" / "platform-protocol-agent.toml", agents / "platform_protocol_agent.toml")
    enabled = ", ".join(json.dumps(tool) for tool in PROTOCOL_TOOLS)
    env = {**settings, "ONTOLOGY_MCP_API_KEY": model_key}
    lines = [
        '[projects."/work"]',
        'trust_level = "trusted"',
        "[mcp_servers.ontology_platform]",
        'command = "/backend/.venv/bin/python"',
        'args = ["-m", "app.mcp.server"]',
        'cwd = "/backend"',
        'default_tools_approval_mode = "approve"',
        "required = true",
        "startup_timeout_sec = 20.0",
        "tool_timeout_sec = 90.0",
        f"enabled_tools = [{enabled}]",
        "[mcp_servers.ontology_platform.env]",
    ]
    lines.extend(f"{key} = {json.dumps(value)}" for key, value in sorted(env.items()))
    (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(home / "config.toml", 0o600)


def _probe_mcp_requires_run_key(settings: dict[str, str]) -> None:
    command = isolated_command({}, settings, 1)
    separator = command.index("--")
    command = [*command[: separator + 1], "/backend/.venv/bin/python", "-m", "app.mcp.server"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode == 0 or "ONTOLOGY_MCP_API_KEY is required" not in result.stderr:
        raise L3Error("sanitized MCP without the run key did not reject authentication")


def _start_application_rest(run_root: Path, run_id: str, settings: dict[str, str]) -> tuple[subprocess.Popen[str], str]:
    port = 19700 + int(hashlib.sha256(run_id.encode()).hexdigest()[:4], 16) % 200
    audit = run_root / "audit"
    log_path = audit / "application-rest.log"
    if log_path.exists():
        index = 2
        while (audit / f"application-rest-{index}.log").exists():
            index += 1
        log_path = audit / f"application-rest-{index}.log"
    log = log_path.open("x", encoding="utf-8")
    process = subprocess.Popen(isolated_command({}, settings, port), stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        if process.poll() is not None:
            raise L3Error("isolated application REST exited before health")
        try:
            if http(base, "GET", "/api/health")["status"] == 200:
                return process, base
        except L3Error:
            pass
        time.sleep(0.25)
    cleanup_process(process)
    raise L3Error("isolated application REST did not become healthy")


def _validate_protocol_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise L3Error("protocol result is not an object")
    required = {"build_session_id", "batches", "workspace", "validation", "reasoning", "query"}
    if set(value) != required or not isinstance(value.get("build_session_id"), str):
        raise L3Error("protocol result fields drift")
    batches, workspace, validation, reasoning, query = (value[key] for key in ("batches", "workspace", "validation", "reasoning", "query"))
    if not isinstance(batches, dict) or set(batches) != {"applied", "invalid_dry_run"}:
        raise L3Error("protocol Batch receipt fields drift")
    applied, invalid = batches["applied"], batches["invalid_dry_run"]
    if (
        not isinstance(applied, list)
        or not applied
        or any(
            not isinstance(receipt, dict) or not isinstance(receipt.get("batch_id"), str)
            for receipt in applied
        )
        or not isinstance(invalid, dict)
        or not isinstance(invalid.get("batch_id"), str)
    ):
        raise L3Error("protocol Batch identities are invalid")
    if not isinstance(workspace, dict) or set(workspace) != {"before", "after"} or workspace["before"] == workspace["after"]:
        raise L3Error("protocol result does not prove workspace advancement")
    if not isinstance(validation, dict) or validation.get("conforms") is not True:
        raise L3Error("protocol result lacks conforming validation")
    if not isinstance(reasoning, dict) or reasoning.get("status") != "succeeded" or reasoning.get("consistent") is not True:
        raise L3Error("protocol result lacks consistent reasoning")
    if not isinstance(query, dict) or query.get("complete") is not True or query.get("published_path") is not True or query.get("draft_excluded") is not True or query.get("explicit_unknown") is not True:
        raise L3Error("protocol result lacks required governed query evidence")
    if any(marker in canonical_json(value).decode("utf-8") for marker in HOST_KEY_MARKERS):
        raise L3Error("protocol result contains credential material")
    return value


def _audit_protocol_rollout(transcript: Path) -> dict[str, Any]:
    calls: set[str] = set()
    for event in _jsonl_items(transcript, "protocol transcript"):
        item, payload = event.get("item"), event.get("payload")
        if isinstance(item, dict) and item.get("type") == "mcp_tool_call" and item.get("server") == "ontology_platform" and isinstance(item.get("tool"), str):
            calls.add(item["tool"])
        if isinstance(payload, dict) and payload.get("type") == "function_call" and payload.get("namespace") == "mcp__ontology_platform" and isinstance(payload.get("name"), str):
            calls.add(payload["name"])
    required = {"check_platform_health", "create_build_session", "acquire_ontology_lease", "submit_modeling_batch", "complete_build_session"}
    if not calls or calls - set(PROTOCOL_TOOLS) or not required.issubset(calls):
        raise L3Error("protocol rollout MCP calls are missing, unapproved, or incomplete")
    return {"protocol_mcp_tools": sorted(calls), "protocol_only": True}


def _audit_platform_facts(base: str, admin_key: str, scope: dict[str, str], result: dict[str, Any]) -> dict[str, Any]:
    session = require_ok(http(base, "GET", f"/api/build-sessions/{result['build_session_id']}", key=admin_key))
    summary, leases = session.get("session"), session.get("leases")
    if not isinstance(summary, dict) or summary.get("status") != "completed" or not isinstance(leases, list):
        raise L3Error("platform Build Session is not terminal completed")
    if scope["ontology_id"] not in {lease.get("ontology_id") for lease in leases if isinstance(lease, dict)} or any(lease.get("state") != "released" for lease in leases if isinstance(lease, dict)):
        raise L3Error("platform Build Session lease facts drift")
    applied, invalid = result["batches"]["applied"], result["batches"]["invalid_dry_run"]
    applied_details = [
        require_ok(
            http(base, "GET", f"/api/modeling-batches/{receipt['batch_id']}", key=admin_key)
        )
        for receipt in applied
    ]
    invalid_detail = require_ok(http(base, "GET", f"/api/modeling-batches/{invalid['batch_id']}", key=admin_key))
    if (
        any(
            detail.get("ontology_id") != scope["ontology_id"]
            or detail.get("batch_status") != "applied"
            for detail in applied_details
        )
        or invalid_detail.get("ontology_id") != scope["ontology_id"]
        or invalid_detail.get("batch_status") == "applied"
    ):
        raise L3Error("platform Batch facts drift")
    return {
        "build_session": {"id": result["build_session_id"], "status": "completed"},
        "applied_batches": [receipt["batch_id"] for receipt in applied],
        "invalid_batch": invalid["batch_id"],
    }


def _transcript_thread_id(transcript: Path) -> str:
    ids = {
        value
        for event in _jsonl_items(transcript, "agent transcript")
        for value in (
            [event.get("thread_id")] if event.get("type") == "thread.started" else []
        )
        if isinstance(value, str)
    }
    ids.update(
        payload["id"]
        for event in _jsonl_items(transcript, "agent transcript")
        if event.get("type") == "session_meta"
        and isinstance((payload := event.get("payload")), dict)
        and isinstance(payload.get("id"), str)
    )
    if len(ids) != 1:
        raise L3Error("Codex transcript lacks one exact Session identity")
    return ids.pop()


def _destroy_protocol_home(run_root: Path, secret: str) -> dict[str, Any]:
    """Destroy the uniquely owned Protocol credential home after its process has ended."""
    home = run_root / "protocol-home"
    if not home.exists():
        return {"protocol_home_removed": True, "credential_files_destroyed": 0, "secret_found_after_cleanup": False}
    if home.resolve().parent != run_root.resolve():
        raise L3Error("Protocol credential home path is unsafe")
    files = [path for path in home.rglob("*") if path.is_file()]
    for path in files:
        try:
            with path.open("r+b") as stream:
                size = path.stat().st_size
                stream.write(b"\0" * size)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise L3Error("Protocol credential material could not be destroyed") from exc
    shutil.rmtree(home)
    if home.exists():
        raise L3Error("Protocol credential home removal failed")
    secret_found = any(
        secret in path.read_text(encoding="utf-8", errors="replace")
        for path in run_root.rglob("*")
        if path.is_file()
    )
    if secret_found:
        raise L3Error("temporary Protocol key entered retained run-local artifacts")
    return {"protocol_home_removed": True, "credential_files_destroyed": len(files), "secret_found_after_cleanup": False}


def _continuation_failure_category(exc: Exception) -> str:
    text = str(exc).lower()
    if "runtime/infrastructure" in text or any(
        marker in text
        for marker in (
            "provider",
            "timeout",
            "exit_",
            "isolated runtime",
            "isolated application rest exited",
            "isolated application rest did not become healthy",
            "process exited",
            "process exit",
        )
    ):
        return "runtime/infrastructure"
    if any(
        marker in text
        for marker in (
            "did not resume",
            "pending question",
            "released answer",
            "coordinator published dispatch",
            "l3_waiting_for_answer without",
        )
    ):
        return "collaboration/routing"
    return "platform-contract"


def _prepare_protocol_work(root: Path) -> None:
    """Create fresh work or archive only the proven residue of the retained failed attempt."""
    work = root / "protocol-work"
    if not work.exists():
        work.mkdir(mode=0o700)
        return
    if not work.is_dir():
        raise L3Error("protocol runtime/infrastructure: retained Protocol work is not a directory")
    first_receipt = root / "audit" / "protocol-retry-receipt.json"
    second_receipt = root / "audit" / "protocol-retry-receipt-2.json"
    third_receipt = root / "audit" / "protocol-retry-receipt-3.json"
    fourth_receipt = root / "audit" / "protocol-retry-receipt-4.json"
    attempt = (
        5
        if fourth_receipt.is_file()
        else 4
        if third_receipt.is_file()
        else 3
        if second_receipt.is_file()
        else 2
        if first_receipt.is_file()
        else 1
    )
    work_items = list(work.iterdir())
    retained_result = work / "protocol-result.json"
    archived_result = root / "audit" / "protocol-result-attempt-5.json"
    if work_items and not (
        attempt == 5 and work_items == [retained_result] and retained_result.is_file()
    ):
        raise L3Error("protocol runtime/infrastructure: retained Protocol work is not empty")
    if attempt == 5 and not retained_result.is_file() and not archived_result.is_file():
        raise L3Error("protocol runtime/infrastructure: completed Protocol result is missing")
    transcript = root / "audit" / f"protocol-{attempt}.jsonl"
    stderr = root / "audit" / f"protocol-{attempt}.stderr.log"
    rest_log = root / "audit" / (
        "application-rest.log" if attempt == 1 else f"application-rest-{attempt}.log"
    )
    receipt = root / "audit" / (
        "protocol-retry-receipt.json"
        if attempt == 1
        else f"protocol-retry-receipt-{attempt}.json"
    )
    stderr_text = stderr.read_text(encoding="utf-8") if stderr.is_file() else ""
    rest_text = rest_log.read_text(encoding="utf-8") if rest_log.is_file() else ""
    transcript_text = transcript.read_text(encoding="utf-8") if transcript.is_file() else ""
    if attempt == 1 and transcript.is_file():
        attempt_failure_matches = (
            transcript.stat().st_size == 0
            and "required MCP servers failed to initialize" in stderr_text
        )
    elif attempt == 2:
        attempt_failure_matches = (
            '"tool":"cancel_build_session"' in transcript_text
            and '\\"status\\": \\"cancelled\\"' in transcript_text
            and "Blocked by the credential lifecycle precondition" in transcript_text
            and stderr_text == ""
        )
    elif attempt == 3:
        attempt_failure_matches = (
            "Expected RDF IRI, got: 'entity-a-published'" in transcript_text
            and "ontology_write_fenced" in transcript_text
            and "Managed read models confirm reasoning is `missing`" in transcript_text
            and stderr_text == ""
        )
    elif attempt == 4:
        attempt_failure_matches = (
            "schema and executable SHACL shape are applied atomically" in transcript_text
            and "materializing only the approved instances and relations" in transcript_text
            and "Expected RDF IRI" not in transcript_text
            and "ontology_write_fenced" not in transcript_text
            and stderr_text == ""
        )
    else:
        try:
            retained_value = json.loads(
                (retained_result if retained_result.is_file() else archived_result).read_text(
                    encoding="utf-8"
                )
            )
            _validate_protocol_result(retained_value)
            result_is_valid = True
        except (OSError, json.JSONDecodeError, L3Error):
            result_is_valid = False
        attempt_failure_matches = (
            '"type":"turn.completed"' in transcript_text
            and "Created and validated" in transcript_text
            and result_is_valid
            and "Expected RDF IRI" not in transcript_text
            and "ontology_write_fenced" not in transcript_text
            and stderr_text == ""
        )
    if (
        receipt.exists()
        or not transcript.is_file()
        or not stderr.is_file()
        or not rest_log.is_file()
        or not attempt_failure_matches
        or 'POST /api/api-keys/' not in rest_text
        or '%3Arevoke HTTP/1.1" 200 OK' not in rest_text
        or 'DELETE /api/projects/' not in rest_text
        or 'HTTP/1.1" 204 No Content' not in rest_text
        or (root / "protocol-home").exists()
    ):
        raise L3Error("protocol runtime/infrastructure: retained Protocol retry evidence drift")
    if attempt == 5 and retained_result.is_file():
        os.replace(retained_result, archived_result)
    atomic_json(
        receipt,
        {
            "attempt": attempt,
            "category": "platform-contract" if attempt == 5 else "runtime/infrastructure",
            "reason": (
                "Protocol MCP interpreter target was not mounted"
                if attempt == 1
                else "Protocol Agent repeated the launcher-owned no-key proof after key injection"
                if attempt == 2
                else "Platform dry-run admitted relative relation IRIs before atomic application"
                if attempt == 3
                else "Valid Protocol progress exceeded the original 300-second terminal budget"
                if attempt == 4
                else "L3 launcher expected one applied Batch while the protocol produced a Batch list"
            ),
            "protocol_transcript_sha256": sha256_path(transcript),
            "protocol_stderr_sha256": sha256_path(stderr),
            "application_rest_log_sha256": sha256_path(rest_log),
            "protocol_work_empty": True,
            "protocol_home_absent": True,
            "model_key_revoke_status": 200,
            "project_delete_status": 204,
            **(
                {"protocol_result_sha256": sha256_path(archived_result)}
                if attempt == 5
                else {}
            ),
        },
    )


def _persist_recovery_success(root: Path, state: dict[str, Any]) -> None:
    """Publish one hash-bindable terminal snapshot, then append its authoritative correction."""
    final_path = _recovery_final_state_path(root)
    if final_path.exists():
        raise L3Error("recovery final state already exists")
    atomic_json(final_path, state)
    local_scenario_status()


def continue_run(run_id: str, *, execute: bool) -> dict[str, Any]:
    """Continue exactly one retained non-terminal L3 coordinator session; never reserve a new start."""
    if not execute:
        raise L3Error("refusing continuation without --execute")
    root = run_dir(run_id)
    state, recovered = _effective_continuation_state(run_id, _read_run_state(root))
    if state.get("state") not in {
        "WAITING_FOR_COORDINATOR_OUTPUT",
        "WAITING_FOR_ANSWER",
        "READY_FOR_PROTOCOL",
    } or state.get("outcome") == "NOT_PASSED":
        raise L3Error("continuation requires one retained non-terminal waiting run")
    coordinator = state.get("coordinator")
    if not isinstance(coordinator, dict) or not isinstance(coordinator.get("coordinator_thread_id"), str):
        raise L3Error("continuation lacks recorded coordinator Session identity")
    work = root / "team-work"
    if state.get("state") == "WAITING_FOR_ANSWER" and (work / "pending-question.json").exists():
        return state
    if not CODEX_BINARY.is_file() or not HOST_CODEX_AUTH.is_file():
        raise L3Error("isolated Codex continuation prerequisites are unavailable")
    _released_answer_is_exact(work)
    transcript = _next_transcript(root, "coordinator-resume")
    prompt = (
        "Resume exactly your retained L3 coordinator Session. Consume only the verbatim released answer "
        "already present at /work/released-answer.json and continue the frozen coordinator task. If one "
        "additional consequential business gap remains, atomically write exactly one pending-question.json "
        "and stop with L3_WAITING_FOR_ANSWER. Otherwise publish approved-candidate.json and "
        "protocol-dispatch.json exactly as the task requires, then stop with L3_COORDINATOR_DISPATCHED."
    )
    try:
        if state.get("state") == "READY_FOR_PROTOCOL":
            candidate, dispatch = _candidate_and_dispatch(work)
            state["dispatch"] = dispatch
            _apply_protocol(root, state, candidate, dispatch)
            state.update({"state": "PASS", "outcome": "PASSED", "category": "passed", "updated_at": now()})
            return state
        resumed = _execute_command(_coordinator_command(root, coordinator["coordinator_thread_id"]), prompt, transcript, "coordinator")
        if resumed["thread_id"] != coordinator["coordinator_thread_id"]:
            raise L3Error("coordinator continuation did not resume the recorded Session")
        if (work / "pending-question.json").exists():
            if (work / "approved-candidate.json").exists() or (work / "protocol-dispatch.json").exists():
                raise L3Error("coordinator published dispatch while a new question remains pending")
            state.update({"state": "WAITING_FOR_COORDINATOR_OUTPUT", "coordinator_resume": resumed, "updated_at": now()})
            return state
        if transcript.is_file() and _exact_agent_message_marker(transcript, "L3_WAITING_FOR_ANSWER"):
            raise L3Error("coordinator emitted L3_WAITING_FOR_ANSWER without atomically publishing pending-question.json")
        candidate, dispatch = _candidate_and_dispatch(work)
        state["coordinator_resume"] = resumed
        state["dispatch"] = dispatch
        _apply_protocol(root, state, candidate, dispatch)
        state.update({"state": "PASS", "outcome": "PASSED", "updated_at": now()})
        return state
    except Exception as exc:
        category = _continuation_failure_category(exc)
        state.update({"state": "PAUSED", "outcome": "NOT_PASSED", "category": category, "error": str(exc), "updated_at": now()})
        try:
            state["terminal_outcome"] = record_terminal_outcome(run_id, category)
        except L3Error as terminal_exc:
            state["terminal_recording_error"] = str(terminal_exc)
        raise
    finally:
        if recovered and state.get("state") == "PASS":
            _persist_recovery_success(root, state)
        elif not recovered:
            atomic_json(root / "audit" / "state.json", state)


def _apply_protocol(run_root: Path, state: dict[str, Any], candidate: dict[str, Any], dispatch: dict[str, Any]) -> None:
    """L1-derived isolated scope, key, Protocol Agent, platform audit, and exact cleanup path."""
    run_id, settings = state["run_id"], sanitized_settings()
    process: subprocess.Popen[str] | None = None
    admin_key: str | None = None
    admin_id: str | None = None
    model_key: str | None = None
    model_key_id: str | None = None
    project_id: str | None = None
    base: str | None = None
    try:
        _prepare_protocol_work(run_root)
        process, base = _start_application_rest(run_root, run_id, settings)
        admin_key, admin_id = bootstrap_admin()
        project = require_ok(
            http(base, "POST", "/api/projects", {"name": f"R2.2 L3 {run_id}", "description": f"owned L3 continuation {run_id}"}, admin_key)
        )
        project_id = project.get("id")
        if not isinstance(project_id, str):
            raise L3Error("owned Project creation lacked id")
        ontology = require_ok(
            http(base, "POST", f"/api/projects/{project_id}/ontologies", {"name": f"L3 {run_id}", "description": "owned L3 ontology", "external_mappings": {}}, admin_key)
        )
        ontology_id = ontology.get("id")
        if not isinstance(ontology_id, str):
            raise L3Error("owned Ontology creation lacked id")
        scope = {"project_id": project_id, "ontology_id": ontology_id}
        state["scope"] = scope
        stage_protocol_handoff(run_root / "protocol-input", candidate, dispatch, scope)
        _probe_mcp_requires_run_key(settings)
        state["mcp_no_key_authentication"] = "rejected"
        stage_credential_proof(run_root / "protocol-input")
        created = require_ok(http(base, "POST", "/api/api-keys", {"name": f"r2-2-001-l3-model-{run_id}", "project_id": project_id, "scopes": ["model"]}, admin_key))
        model_key, model_key_id = created.pop("plaintext_key", None), created.get("id")
        if not isinstance(model_key, str) or not isinstance(model_key_id, str):
            raise L3Error("Project-scoped Protocol key creation failed")
        state["protocol_key"] = {"key_id": model_key_id, "project_id": project_id, "scope": "model"}
        _write_protocol_config(run_root / "protocol-home", model_key, settings)
        prompt = (
            (SCENARIO_ROOT / "protocol-agent-prompt.md").read_text(encoding="utf-8")
            + "\nWrite /work/protocol-result.json with exactly build_session_id, batches, workspace, validation, reasoning, query. "
            "batches.applied must be a non-empty list containing every applied Batch receipt, and "
            "batches.invalid_dry_run must be one rejected Batch receipt; workspace must contain before/after; "
            "validation.conforms=true; reasoning.status=succeeded and consistent=true; query must set complete, "
            "published_path, draft_excluded, explicit_unknown all true."
        )
        protocol_transcript = _next_transcript(run_root, "protocol")
        state["protocol_execution"] = _execute_command(
            _protocol_command(run_root, settings),
            prompt,
            protocol_transcript,
            "protocol",
            terminal_timeout_seconds=PROTOCOL_TERMINAL_TIMEOUT_SECONDS,
        )
        try:
            protocol_result_value = json.loads(
                (run_root / "protocol-work" / "protocol-result.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise L3Error("Protocol Agent did not publish a valid protocol-result.json") from exc
        protocol_result = _validate_protocol_result(protocol_result_value)
        state["protocol_rollout_audit"] = _audit_protocol_rollout(protocol_transcript)
        state["platform_fact_audit"] = _audit_platform_facts(base, admin_key, scope, protocol_result)
        atomic_json(run_root / "audit" / "protocol-result.json", protocol_result)
        atomic_json(run_root / "audit" / "protocol-rollout-audit.json", state["protocol_rollout_audit"])
        atomic_json(run_root / "audit" / "platform-fact-audit.json", state["platform_fact_audit"])
    finally:
        cleanup: dict[str, Any] = {}
        if base and admin_key and model_key_id:
            revoked = http(base, "POST", f"/api/api-keys/{model_key_id}:revoke", key=admin_key)
            cleanup["model_key_revoked"] = revoked.get("status") == 200 and bool(revoked.get("body", {}).get("revoked_at"))
        if base and admin_key and project_id:
            deletion = http(base, "DELETE", f"/api/projects/{project_id}", key=admin_key)
            cleanup["project_deleted"] = deletion.get("status") == 204
            cleanup["project_id"] = project_id
        if admin_id:
            cleanup["host_admin_revoked"] = revoke_admin(admin_id)
        cleanup_process(process)
        cleanup["isolated_runtime_exited"] = process is None or process.poll() is not None
        if model_key:
            cleanup["protocol_credentials"] = _destroy_protocol_home(run_root, model_key)
        elif (run_root / "protocol-home").exists():
            raise L3Error("Protocol credential home exists without an owned temporary key")
        state["cleanup"] = cleanup
        if model_key:
            model_key = None
        required_cleanup = ["project_deleted", "host_admin_revoked", "isolated_runtime_exited"]
        if model_key_id:
            required_cleanup.extend(["model_key_revoked", "protocol_credentials"])
        if project_id and not all(cleanup.get(key) for key in required_cleanup):
            raise L3Error("owned Protocol scope cleanup is incomplete")


def managed_reasoning_preflight(run_root: Path, run_id: str) -> dict[str, Any]:
    """Real, business-empty managed reasoning in the same isolated REST namespace."""
    settings, port, process, admin_key, admin_id, project_id = sanitized_settings(), 19000 + int(hashlib.sha256(run_id.encode()).hexdigest()[:4], 16) % 700, None, None, None, None
    audit = run_root / "audit"
    audit.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        command = isolated_command({}, settings, port)
        log = (audit / "isolated-rest.log").open("w", encoding="utf-8")
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        base = f"http://127.0.0.1:{port}"
        for _ in range(80):
            if process.poll() is not None:
                raise L3Error("isolated REST exited before managed-reasoning preflight")
            try:
                if http(base, "GET", "/api/health")["status"] == 200:
                    break
            except L3Error:
                pass
            time.sleep(0.25)
        else:
            raise L3Error("isolated REST did not become healthy")
        admin_key, admin_id = bootstrap_admin()
        project = require_ok(http(base, "POST", "/api/projects", {"name": f"L3 reasoner probe {run_id}", "description": "L3-owned business-empty reasoner probe"}, admin_key))
        project_id = project.get("id")
        if not isinstance(project_id, str):
            raise L3Error("probe Project identity is missing")
        ontology = require_ok(http(base, "POST", f"/api/projects/{project_id}/ontologies", {"name": f"L3 probe {run_id}", "description": "business-empty", "external_mappings": {}}, admin_key))
        workspace = ontology.get("workspace")
        graph_set_id = workspace.get("default_graph_set_id") if isinstance(workspace, dict) else None
        if not isinstance(graph_set_id, str):
            raise L3Error("probe Ontology lacks a managed graph set")
        graph_set = require_ok(http(base, "GET", f"/api/semantic/graph-sets/{graph_set_id}", key=admin_key))
        members = graph_set.get("members")
        source_graphs = [
            member["graph_iri"]
            for member in members
            if isinstance(member, dict)
            and member.get("role") in {"asserted_ontology", "asserted_data"}
            and isinstance(member.get("graph_iri"), str)
        ] if isinstance(members, list) else []
        if len(source_graphs) != 2:
            raise L3Error("probe graph set lacks managed reasoning source graphs")
        # This isolated technical sentinel creates the otherwise empty managed graph; it contains
        # no L3 business fact and is deleted with the uniquely owned probe Project.
        for source_graph in source_graphs:
            require_ok(http(base, "POST", "/api/semantic/edits", {"format": "turtle", "content": "<urn:l3:reasoner-probe> <urn:l3:technical> <urn:l3:sentinel> .", "target_graph_iri": source_graph, "validate": True, "reason": "L3 business-empty reasoner preflight"}, admin_key))
        result = require_ok(http(base, "POST", f"/api/semantic/graph-sets/{graph_set_id}/reasoning-runs", {"tasks": ["consistency"], "persist_result_graph": True}, admin_key))
        atomic_json(audit / "reasoner-preflight-result.json", result)
        if result.get("status") != "succeeded" or result.get("consistent") is not True:
            raise L3Error("isolated managed reasoning did not succeed consistently")
        return {"passed": True, "graph_set_id": graph_set_id, "reasoning_run_id": result.get("run_id"), "consistent": True}
    finally:
        cleanup: dict[str, Any] = {}
        if admin_key and project_id:
            deletion = http(f"http://127.0.0.1:{port}", "DELETE", f"/api/projects/{project_id}", key=admin_key)
            cleanup["project_deleted"] = deletion["status"] == 204
            cleanup["project_id"] = project_id
        if admin_id:
            cleanup["host_admin_revoked"] = revoke_admin(admin_id)
        cleanup_process(process)
        cleanup["isolated_runtime_exited"] = process is None or process.poll() is not None
        atomic_json(audit / "reasoner-preflight-cleanup.json", cleanup)


def run(run_id: str, *, execute: bool) -> dict[str, Any]:
    if not execute:
        raise L3Error("refusing mutation without --execute")
    root = run_dir(run_id)
    if root.exists():
        raise L3Error("run directory already exists")
    # This global reservation happens before staging, preflight or credentials, so a rejected
    # fourth start cannot create another probe or a new runtime artifact.
    coordinator_start = reserve_coordinator_start(run_id)
    root.mkdir(mode=0o700, parents=True)
    state: dict[str, Any] = {
        "run_id": run_id,
        "preparation_started_at": coordinator_start.get(
            "preparation_started_at", recovery_preparation_started_at().isoformat()
        ),
        "coordinator_start": coordinator_start,
        "state": "PREPARING",
    }
    try:
        manifest = read_manifest()
        state["staged_input"] = stage_role_packs(manifest, root, run_id)
        # Mandatory isolated managed-reasoner gate occurs before any Agent receives scope or key.
        state["reasoner_preflight"] = managed_reasoning_preflight(root, run_id)
        state["coordinator"] = launch_coordinator(root)
        state["first_modeling"] = record_modeling_delegation(
            run_id,
            state["coordinator"]["coordinator_thread_id"],
            state["coordinator"]["modeling_agent_thread_id"],
        )
        # The question/answer continuation and Protocol Agent are deliberately not simulated by
        # Delivery.  A real coordinator result is retained for the next live interaction step.
        state.update({"state": "WAITING_FOR_COORDINATOR_OUTPUT", "updated_at": now()})
    except Exception as exc:
        category = "collaboration/routing" if "Modeling Agent child" in str(exc) else "runtime/infrastructure"
        state.update({"state": "PAUSED", "outcome": "NOT_PASSED", "category": category, "error": str(exc), "updated_at": now()})
        try:
            state["terminal_outcome"] = record_terminal_outcome(run_id, category)
        except L3Error as terminal_exc:
            state["terminal_recording_error"] = str(terminal_exc)
        raise
    finally:
        atomic_json(root / "audit" / "state.json", state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    child = parser.add_subparsers(dest="command", required=True)
    run_parser = child.add_parser("run")
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--execute", action="store_true")
    continue_parser = child.add_parser("continue")
    continue_parser.add_argument("--run-id", required=True)
    continue_parser.add_argument("--execute", action="store_true")
    child.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "status":
            print(json.dumps(scenario_status(), ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "continue":
            print(json.dumps(continue_run(args.run_id, execute=args.execute), ensure_ascii=False, sort_keys=True))
            return 0
        print(json.dumps(run(args.run_id, execute=args.execute), ensure_ascii=False, sort_keys=True))
        return 0
    except L3Error as exc:
        print(f"L3 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
