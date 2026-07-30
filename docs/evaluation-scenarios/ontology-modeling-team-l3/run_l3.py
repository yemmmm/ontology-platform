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
PREPARATION_STARTED_AT = "2026-07-30T12:37:43+08:00"
FIRST_MODELING_DEADLINE = datetime.fromisoformat(PREPARATION_STARTED_AT) + timedelta(minutes=20)
HOST_KEY_MARKERS = ("ONTOLOGY_MCP_API_KEY", "sk_admin_", "bootstrap-admin")
CODEX_BINARY = Path(os.environ.get("L3_CODEX_BINARY", "/home/yangxiang/.local/bin/codex"))
HOST_CODEX_AUTH = Path(os.environ.get("L3_HOST_CODEX_AUTH", "/home/yangxiang/.codex/auth.json"))
HISTORICAL_RUN_IDS = ("l3-real-20260730g", "l3-real-20260730h", "l3-real-20260730i")


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
        "run_ids",
        "recovery_requirements",
    }
    try:
        policy = json.loads(EXECUTION_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L3Error("committed L3 execution policy is unavailable") from exc
    if not isinstance(policy, dict) or set(policy) != required or policy.get("policy_version") != 1:
        raise L3Error("committed L3 execution policy fields drift")
    if not isinstance(policy.get("live_execution_authorized"), bool) or not isinstance(policy.get("starts_consumed"), int):
        raise L3Error("committed L3 execution policy types drift")
    run_ids = policy.get("run_ids")
    recovery = policy.get("recovery_requirements")
    if not isinstance(run_ids, list) or not all(isinstance(value, str) for value in run_ids) or not isinstance(recovery, list) or not all(isinstance(value, str) for value in recovery):
        raise L3Error("committed L3 execution policy lists drift")
    if not policy["live_execution_authorized"] and (policy.get("state"), policy.get("outcome")) != ("PAUSED", "NOT_PASSED"):
        raise L3Error("disabled L3 execution policy must remain PAUSED/NOT_PASSED")
    return policy


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
    return {
        "state_path": f"runtime/{state_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
        "state_sha256": sha256_path(state_path),
        "transcript_path": f"runtime/{transcript_path.relative_to(RUNTIME_ROOT.parent).as_posix()}",
        "transcript_sha256": sha256_path(transcript_path),
    }


def _classification_correction(run_id: str) -> dict[str, Any]:
    return {
        "event": "historical_classification_correction",
        "correction_id": f"l3-child-identity-correction-v1:{run_id}",
        "run_id": run_id,
        "original": {"state": "INCONCLUSIVE", "category": "runtime/infrastructure"},
        "authoritative": {"state": "PAUSED", "outcome": "NOT_PASSED", "category": "collaboration/routing"},
        "reason": "missing verified Modeling Agent child Session/delegation",
        "evidence": _historical_evidence(run_id),
    }


def _reconcile_historical_classifications() -> list[dict[str, Any]]:
    CLASSIFICATION_LEDGER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with CLASSIFICATION_LEDGER.open("a+", encoding="utf-8") as stream:
        stream.seek(0)
        corrections = _read_jsonl(CLASSIFICATION_LEDGER)
        present = [run_id for run_id in HISTORICAL_RUN_IDS if (RUNTIME_ROOT / run_id).exists()]
        if not present:
            return corrections
        if set(present) != set(HISTORICAL_RUN_IDS):
            raise L3Error("historical classification coverage is incomplete")
        existing = {value.get("correction_id"): value for value in corrections}
        for run_id in HISTORICAL_RUN_IDS:
            correction = _classification_correction(run_id)
            previous = existing.get(correction["correction_id"])
            if previous is None:
                _append_locked(stream, correction)
                corrections.append(correction)
                existing[correction["correction_id"]] = correction
            elif previous != correction:
                raise L3Error(f"historical classification evidence hash drift: {run_id}")
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
                classifications = _reconcile_historical_classifications()
                return callback(stream, events, classifications)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _team_start_count(events: list[dict[str, Any]]) -> int:
    return sum(event.get("event") in {"historical_coordinator_started", "coordinator_started"} for event in events)


def reserve_coordinator_start(run_id: str, at: datetime | None = None) -> dict[str, Any]:
    """Reserve one globally budgeted fresh coordinator start before any live resource exists."""
    require_live_execution_authorized()
    at = at or datetime.now(FIRST_MODELING_DEADLINE.tzinfo)

    def reserve(stream, events: list[dict[str, Any]], _classifications: list[dict[str, Any]]) -> dict[str, Any]:
        if any(event.get("event") == "preparation_halted" for event in events):
            raise L3Error("L3 is paused after the first-modeling deadline")
        if _team_start_count(events) >= 3:
            raise L3Error("L3 global coordinator start limit reached; state is PAUSED/NOT_PASSED")
        if at > FIRST_MODELING_DEADLINE:
            halt = {"event": "preparation_halted", "at": at.isoformat(), "reason": "20-minute first-modeling gate missed"}
            _append_locked(stream, halt)
            raise L3Error("20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED")
        event = {"event": "coordinator_started", "run_id": run_id, "started_at": at.isoformat(), "preparation_started_at": PREPARATION_STARTED_AT}
        _append_locked(stream, event)
        return event

    return _with_global_ledger(reserve)


def record_modeling_delegation(
    run_id: str,
    coordinator_thread_id: str,
    modeling_agent_thread_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Record the first real modeling time only after a verifiable child identity exists."""
    at = at or datetime.now(FIRST_MODELING_DEADLINE.tzinfo)
    if not coordinator_thread_id or not modeling_agent_thread_id:
        raise L3Error("modeling delegation lacks authoritative child Session identity")

    def record(stream, events: list[dict[str, Any]], _classifications: list[dict[str, Any]]) -> dict[str, Any]:
        if at > FIRST_MODELING_DEADLINE:
            _append_locked(stream, {"event": "preparation_halted", "at": at.isoformat(), "reason": "20-minute first-modeling gate missed before child delegation"})
            raise L3Error("20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED")
        if not any(event.get("event") == "coordinator_started" and event.get("run_id") == run_id for event in events):
            raise L3Error("modeling delegation lacks an owned coordinator start")
        if any(event.get("event") == "modeling_started" and event.get("run_id") == run_id for event in events):
            raise L3Error("first modeling delegation is already recorded")
        event = {"event": "modeling_started", "run_id": run_id, "coordinator_thread_id": coordinator_thread_id, "modeling_agent_thread_id": modeling_agent_thread_id, "first_modeling_started_at": at.isoformat(), "preparation_started_at": PREPARATION_STARTED_AT}
        _append_locked(stream, event)
        return event

    return _with_global_ledger(record)


def local_scenario_status() -> dict[str, Any]:
    """Read local ignored evidence only when it exists; it cannot authorize execution."""
    def status(_stream, events: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> dict[str, Any]:
        halted = any(event.get("event") == "preparation_halted" for event in events)
        starts = _team_start_count(events)
        category = "collaboration/routing" if classifications else None
        ledger_path = f"runtime/{CLASSIFICATION_LEDGER.relative_to(RUNTIME_ROOT.parent).as_posix()}"
        if halted or starts >= 3:
            return {"state": "PAUSED", "outcome": "NOT_PASSED", "category": category, "team_starts": starts, "halted": halted, "classification_ledger": ledger_path, "classification_count": len(classifications)}
        return {"state": "READY", "outcome": "PENDING", "category": category, "team_starts": starts, "halted": False, "classification_ledger": ledger_path, "classification_count": len(classifications)}

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
        local["state"] == policy["state"]
        and local["outcome"] == policy["outcome"]
        and local["category"] == policy["category"]
        and local["team_starts"] == policy["starts_consumed"]
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


def release_answer(work: Path, answer_id: str) -> dict[str, Any]:
    pending = work / "pending-question.json"
    if not pending.exists():
        raise L3Error("answer cannot be released without a pending question")
    contract = json.loads(ANSWER_CONTRACT.read_text(encoding="utf-8"))
    matches = [entry for entry in contract["answers"] if entry["id"] == answer_id]
    if len(matches) != 1:
        raise L3Error("unsupported question must not receive an invented answer")
    answer = {"answer_id": answer_id, "answer": matches[0]["answer"], "sha256": hashlib.sha256(matches[0]["answer"].encode()).hexdigest()}
    atomic_json(work / "released-answer.json", answer)
    pending.unlink()
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


def verified_modeling_child(transcript: str) -> tuple[str, str]:
    coordinator_ids: set[str] = set()
    child_ids: set[str] = set()
    for line in transcript.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            coordinator_ids.add(event["thread_id"])
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "collab_tool_call" and item.get("tool") == "spawn_agent":
            receivers = item.get("receiver_thread_ids")
            if isinstance(receivers, list):
                child_ids.update(value for value in receivers if isinstance(value, str) and value)
    if len(coordinator_ids) != 1 or len(child_ids) != 1:
        raise L3Error("coordinator did not evidence one authoritative Modeling Agent child delegation")
    return coordinator_ids.pop(), child_ids.pop()


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
    coordinator_thread_id, modeling_agent_thread_id = verified_modeling_child(process.stdout)
    return {"elapsed_seconds": round(time.monotonic() - started, 3), "transcript": str(transcript), "coordinator_thread_id": coordinator_thread_id, "modeling_agent_thread_id": modeling_agent_thread_id}


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
    state: dict[str, Any] = {"run_id": run_id, "preparation_started_at": PREPARATION_STARTED_AT, "coordinator_start": coordinator_start, "state": "PREPARING"}
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
        raise
    finally:
        atomic_json(root / "audit" / "state.json", state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    child = parser.add_subparsers(dest="command", required=True)
    run_parser = child.add_parser("run")
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--execute", action="store_true")
    child.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "status":
            print(json.dumps(scenario_status(), ensure_ascii=False, sort_keys=True))
            return 0
        print(json.dumps(run(args.run_id, execute=args.execute), ensure_ascii=False, sort_keys=True))
        return 0
    except L3Error as exc:
        print(f"L3 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
