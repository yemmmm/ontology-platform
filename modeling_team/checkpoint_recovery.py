"""R3.0-015 segments S2/S4: cross-process resume from a checkpoint.

Design §4–§8.  The production resume entry (S2) re-verifies everything at
resume time: the full write tail of the source run and its recovery chain
(including writes that happened after the checkpoint), the platform readback
of every Build Session's Modeling Batches through the cursor-paginated
endpoints, and the business-approval source channel.  Only a reconciled,
closed tail can open a new production run; anything unknown, partially
applied or unattributable keeps the write gate closed with a typed reason.

The acceptance continuation entry (S4, design §7) applies the same read-only
discipline to a ``production_handoff`` checkpoint: the packaged handoff must
still equal the run's published handoff, the frozen pool must re-validate
under its recorded digest, the write tail must be closed clean and the source
writer stopped — then the frozen batch's independent acceptance re-executes
through the existing cq-acceptance path with the read-only evidence inputs
kept on the source run and every new attempt/report/host closing record
written to a fresh output run root.  A complete usable PASS report means
verification and host closing only — never a model re-call, and never a
spliced partial answer promoted into a new PASS.

Nothing in this module mutates the source run: every read is read-only and
every typed rejection leaves the source tree, its evidence and its failure
classification untouched.  The one fresh-run exception is ``settle_source_run``
(the ``checkpoint settle-source`` CLI): a host-owned record of an
already-performed controlled stop, never a resume, which the two §5.2 gates
re-verify live.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from modeling_team.checkpoints import (
    CHECKPOINT_ARTIFACTS_DIRECTORY,
    CHECKPOINT_DELIVERY_SEGMENTS,
    CHECKPOINT_HOST_PRIVATE_DIRECTORY,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CHECKPOINT_KINDS,
    CheckpointError,
    checkpoints_root,
    file_digest,
    manifest_digest,
    manifest_path,
    production_resume_bindings,
    safe_checkpoint_id,
    _handoff_manifest_entries,
)
from modeling_team.competency_questions import (
    CQ_FREEZE_DIRECTORY,
    CQContractError,
    batch_report_is_full_pass,
    reload_frozen_pool,
)
from modeling_team.staged_decisions import (
    read_submission_intents,
    read_submission_receipts,
    staged_decision_artifact_paths,
)

RECOVERY_DIRECTORY = "recovery"
RECOVERY_SCHEMA = "r3-0-015-recovery/v1"
RECOVERY_ROLES_DIRECTORY = "roles"
ACCEPTANCE_CONTINUATION_RECORD = "acceptance-continuation.json"
ACCEPTANCE_CONTINUATION_SCHEMA = "r3-0-015-acceptance-continuation/v1"
# Design §5.2 stale-state path: the host's explicit settlement record for a
# host-stopped FRESH source run (never inside the source run itself).
RECOVERY_SETTLEMENTS_DIRECTORY = ".recovery-settlements"
SOURCE_SETTLEMENT_SCHEMA = "r3-0-015-source-settlement/v1"
# The backend Build Session lifecycle (build_sessions.py) terminal set.
SESSION_TERMINAL_STATUSES = frozenset({"completed", "cancelled"})

# Design §4.3: the reconciliation itself counts into the 20-minute budget that
# starts at user authorization; the report separates prep time from semantic
# time instead of silently dropping the reconciliation cost.
PREP_BUDGET_SECONDS = 20 * 60
# Design §5.2: every wait on the hung original writer is capped at 60s.
WAIT_SECONDS_MAX = 60
# Cursor-paginated endpoint page size (backend caps limit at 100).
LIST_PAGE_LIMIT = 100
LIST_PAGE_ENDPOINT = "/api/build-sessions/{session_id}/modeling-batches"
ONTOLOGY_LIST_PAGE_ENDPOINT = "/api/ontologies/{ontology_id}/modeling-batches"
BATCH_DETAIL_ENDPOINT = "/api/modeling-batches/{batch_id}"
SESSION_DETAIL_ENDPOINT = "/api/build-sessions/{session_id}"

# Reason codes specific to resume (design §8 minimum set, S2/S4 additions
# marked).
REASON_SOURCE_ACTIVE = "source_active"
REASON_CONTRACT_INCOMPATIBLE = "contract_incompatible"
REASON_SCOPE_MISSING = "scope_missing"
REASON_SCOPE_DRIFT = "scope_drift"
REASON_WRITE_UNRECONCILED = "write_unreconciled"
REASON_APPROVAL_BINDING_CHANGED = "approval_binding_changed"
REASON_COMPLETED_OPERATION_BLOCKED = "completed_operation_resubmission"
REASON_KIND_MODE_MISMATCH = "checkpoint_kind_mode_mismatch"
REASON_ACCEPTANCE_BINDING_CHANGED = "acceptance_binding_changed"
# settle-source command refusals (fresh-run stale-state path, design §5.2).
REASON_SETTLEMENT_REFUSED = "source_settlement_refused"
# explicit dual-source resume refusals (the --write-tail-run-id channel).
REASON_WRITE_TAIL_UNRELATED = "write_tail_unrelated"
REASON_WRITE_TAIL_CHECKPOINT_BINDING = "write_tail_checkpoint_binding"

# state.json values that mean the original process may still be a live writer
# (every value TeamRunner._state writes before a terminal FAILED/CLEANED).
POSSIBLY_LIVE_STATES = frozenset(
    {
        "RUNNING",
        "STARTING",
        "PAUSED",
        "WAITING_OWNER",
        "WAITING_REPAIR",
        "CLEANING",
        "ABORTING",
        "POST_SETTLEMENT_REPORTING",
        "READ_ONLY_WAIT",
        "STANDBY",
    }
)
# The real backend accepts ``dry_run | apply_atomic | apply_partial`` (there is
# no bare ``apply`` REST mode); runner-side intent records may say ``apply``.
# Every apply-family mode is a materializing write for reconciliation.
APPLY_MODES = frozenset({"apply", "apply_atomic", "apply_partial"})
_RECOVERY_LOCK_DIRECTORY = ".recovery-locks"
# The only lock-record fields a supersede keeps; an unknown nested supersede
# chain or a foreign extra field is never carried into the new record.
LOCK_RECORD_KEYS = ("root_run_id", "pid", "acquired_at")
_APPROVALS_SOURCE = "value-semantics/approvals/approvals.json"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _reject(
    code: str,
    detail: str,
    *,
    obj: str,
    phase: str = "checkpoint-resume",
    retryable: bool = False,
    retry: str | None = None,
) -> CheckpointError:
    return CheckpointError(
        code, detail, obj=obj, phase=phase, retryable=retryable, retry=retry
    )


def scope_missing_rejection(detail: str) -> CheckpointError:
    """The §8 typed tuple for a missing checkpoint-bound scope resource.

    ``PlatformScopeMissingError`` is the platform layer's own exception (a
    ``RuntimeError``); the resume entry converts it here so the host receives
    the advertised ``scope_missing`` code instead of a generic failure line.
    No blank scope is ever created or faked as a resume (design §5.2).
    """

    return _reject(
        REASON_SCOPE_MISSING,
        detail,
        obj="scope_binding",
        phase="checkpoint-resume",
        retryable=True,
        retry="restore or recreate the missing platform resources through the "
        "owning channels (the checkpoint records their exact ids), then retry",
    )


def safe_new_run_id(value: Any) -> str:
    if not isinstance(value, str) or not _RUN_ID_PATTERN.fullmatch(value):
        raise _reject(
            "resume_invalid_new_run_id",
            "--new-run-id must be a single new run-directory name",
            obj="new_run_id",
            retry="choose a fresh run id that does not exist yet",
        )
    return value


def http_readback(base_url: str, admin_key: str) -> PlatformReadback:
    """Build the default host-credential readback over the REST endpoints."""

    import urllib.error
    import urllib.request

    def request(
        method: str, path: str, body: dict[str, Any] | None, key: str
    ) -> tuple[int, Any]:
        payload = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base_url + path,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"null")
            except json.JSONDecodeError:
                return exc.code, None

    return PlatformReadback(request, admin_key)


# --- same-machine one-process lock (design §4.2) -------------------------------


class RootRunLock:
    """One exclusive resume lock per root_run_id on this machine.

    ``flock`` is used deliberately: the kernel releases it when the owning
    process dies, so a crashed resume never leaves a permanently stuck lock,
    while a second live resume of the same root run is refused immediately.
    """

    def __init__(self, path: Path, root_run_id: str) -> None:
        self.path = path
        self.root_run_id = root_run_id
        self._handle: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(handle)
            raise _reject(
                REASON_SOURCE_ACTIVE,
                "another production resume holds the resume lock for this "
                "root run on this machine",
                obj=f"root_run_id:{self.root_run_id}",
                retryable=True,
                retry="let the active resume finish or stop it through its own "
                "stop channel, then retry; never run two resumes of one root run",
            ) from exc
        # R3.0-015 M45: the kernel lock is the settlement evidence for a later
        # recovery, so the holder this acquire supersedes is preserved (one
        # level) instead of being silently truncated away.  A recovery that
        # finds its own process as the holder still reads the record of the
        # writer it superseded.
        previous = read_lock_record_handle(handle)
        os.ftruncate(handle, 0)
        # The read above left the offset at EOF; without this seek the new
        # record would be written past a sparse hole instead of at offset 0.
        os.lseek(handle, 0, os.SEEK_SET)
        record: dict[str, Any] = {
            "root_run_id": self.root_run_id,
            "pid": os.getpid(),
            "acquired_at": datetime.now(UTC).isoformat(),
        }
        if previous is not None:
            record["previous"] = {
                key: previous[key] for key in LOCK_RECORD_KEYS if key in previous
            }
        os.write(handle, json.dumps(record).encode() + b"\n")
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
        finally:
            os.close(self._handle)
            self._handle = None

    def __enter__(self) -> RootRunLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.release()


def acquire_root_run_lock(root_run_id: str, runs_root: Path) -> RootRunLock:
    path = Path(runs_root) / _RECOVERY_LOCK_DIRECTORY / f"{root_run_id}.lock"
    lock = RootRunLock(path, root_run_id)
    lock.acquire()
    return lock


def acquire_acceptance_lock(root_run_id: str, runs_root: Path) -> RootRunLock:
    lock = RootRunLock(Path(runs_root) / _RECOVERY_LOCK_DIRECTORY / f"{root_run_id}.acceptance.lock", root_run_id)
    lock.acquire()
    return lock


def source_safe_for_acceptance(source_run_root: Path, readback: PlatformReadback,
                               request_id: str, root_run_id: str) -> dict[str, Any]:
    """Verify a fresh owner receipt and live platform state; never settles a producer for recovery."""
    from .host_ops import get_request_result, get_run_status
    source_run_root = Path(source_run_root)
    state = read_run_state(source_run_root) or {}
    status = get_run_status(source_run_root.name, repository_root=source_run_root.parents[2])
    owner = status["liveness"]["process_observation"]
    owner_pid = owner.get("pid")
    if owner.get("basis") == "chain_writer_lock":
        owner_pid = owner.get("report", {}).get("holder_pid")
    receipt = get_request_result(source_run_root.name, request_id=request_id,
                                 repository_root=source_run_root.parents[2])
    consumed = receipt if receipt.get("outcome") in {"accepted", "rejected"} else {}
    if not isinstance(consumed, dict):
        consumed = {}
    origin = load_origin_record(source_run_root) or {}
    sealed = state.get("write_seal", {})
    ready = state.get("readiness", {})
    if (state.get("standby_request_id") != request_id or consumed.get("outcome") != "accepted"
            or consumed.get("action") != "standby" or state.get("state") not in {"READ_ONLY_WAIT", "STANDBY"}
            or state.get("owner_pid") != owner_pid or pid_is_alive(owner_pid) is not True
            or (origin.get("root_run_id") or source_run_root.name) != root_run_id
            or state.get("write_phase") != "read-only" or ready.get("in_flight_writes")
            or ready.get("unknown_writes") or sealed.get("write_credentials_non_active") is not True):
        raise _acceptance_reject(REASON_SOURCE_ACTIVE, "fresh live-source sealing receipt is incomplete",
                                 obj=f"request_id:{request_id}", retryable=True,
                                 retry="query the original standby request and reconcile pending writes; retry without stopping the source")
    key_receipts = list(sealed.get("project_scoped_keys", []))
    admin = sealed.get("second_stage", {}).get("org_admin_key")
    if admin:
        key_receipts.append(admin)
    for key in key_receipts:
        detail = readback._get(f"/api/api-keys/{key['id']}")
        if not isinstance(detail, dict) or not detail.get("revoked_at"):
            raise _acceptance_reject(REASON_SOURCE_ACTIVE, "source write key is not revoked", obj=str(key["id"]),
                                     retryable=True, retry="verify the actual owned key revocation")
    revisions = sealed.get("model_revisions", {})
    if not revisions:
        raise _acceptance_reject(REASON_SOURCE_ACTIVE, "source model revision seal is missing", obj="model_revisions", retryable=True)
    for ontology_id, revision in revisions.items():
        context = readback._get(f"/api/ontologies/{ontology_id}/workspace-context")
        workspace = context.get("workspace", {}) if isinstance(context, dict) else {}
        actual = workspace.get("model_revision", context.get("model_revision"))
        if actual != revision:
            raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "live-source model revision changed", obj=ontology_id)
    handoff = source_run_root / _PUBLISHED_HANDOFF_SOURCE
    if state.get("handoff_digest") != file_digest(handoff):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "live-source handoff digest changed", obj=_PUBLISHED_HANDOFF_SOURCE)
    return {"source_run_id": source_run_root.name, "root_run_id": root_run_id, "request_id": request_id,
            "owner_pid": owner_pid, "write_phase": "read-only", "model_revisions": revisions,
            "handoff_digest": state["handoff_digest"]}


def lock_record_path(runs_root: Path, root_run_id: str) -> Path:
    return Path(runs_root) / _RECOVERY_LOCK_DIRECTORY / f"{root_run_id}.lock"


def read_lock_record_handle(handle: int) -> dict[str, Any] | None:
    """Read the current lock record from an already-open handle.

    Used by :meth:`RootRunLock.acquire` before it rewrites the file; a missing,
    empty or unreadable record is ``None`` (there is then nothing to supersede).
    """

    try:
        os.lseek(handle, 0, os.SEEK_SET)
        raw = os.read(handle, 4096)
    except OSError:
        return None
    if not raw:
        return None
    try:
        value = json.loads(raw.decode("utf-8", "replace").strip() or "null")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def read_root_run_lock_record(runs_root: Path, root_run_id: str) -> dict[str, Any] | None:
    """Read one chain lock record without acquiring or mutating it."""

    try:
        raw = lock_record_path(runs_root, root_run_id).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        value = json.loads(raw.strip() or "null")
    except json.JSONDecodeError:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def pid_is_alive(pid: Any) -> bool | None:
    """Process existence for one lock holder; ``None`` means unverifiable.

    ``None`` is never treated as "exited": the caller keeps its hard gate
    closed.  A zombie still owns its pid until reaped and reports alive; the
    kernel ``flock`` (not this probe) is what proves the current holder.
    """

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def lock_holder_record(record: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Pick the holder this evidence is about, preferring the superseded one.

    A recovery process that already took the chain lock writes its own record,
    so its ``previous`` entry is the only remaining evidence of the writer the
    recovery must settle.  Only the immediate predecessor is trusted: a nested
    supersede chain is not followed.
    """

    if record.get("pid") == os.getpid():
        previous = record.get("previous")
        if isinstance(previous, Mapping):
            return dict(previous), True
    return dict(record), False


def chain_writer_lock_report(
    source_run_root: Path, manifest: Mapping[str, Any], runs_root: Path
) -> dict[str, Any]:
    """Audit the chain's kernel-backed lock as writer-liveness evidence (M45).

    A run that was started by a production resume holds its own lock for its
    whole lifetime, keyed by the ``root_run_id`` of the checkpoint it resumed
    from -- the same value its ``recovery/origin.json`` records (verified
    against the 2026-09-15 ``start1 -> start2 -> start3 -> cq-start4`` chain:
    each step's origin names the previous step, and that step's lock is the one
    its writer held).  The kernel releases ``flock`` on process death and
    :meth:`RootRunLock.acquire` preserves the record it superseded, so a dead
    holder pid is positive evidence that the writer exited.
    Only a run bound to that evidence by its own origin record is settled here;
    a fresh run never takes this lock, so nothing about it is claimed.  Every
    unverifiable field keeps the hard gate closed.
    """

    run_root = Path(source_run_root)
    origin = load_origin_record(run_root)
    origin_root = origin.get("root_run_id") if isinstance(origin, Mapping) else None
    origin_new_run_id = origin.get("new_run_id") if isinstance(origin, Mapping) else None
    bound = bool(
        isinstance(origin_root, str)
        and origin_root
        and isinstance(origin_new_run_id, str)
        and origin_new_run_id == run_root.name
    )
    report: dict[str, Any] = {
        "checked": bound,
        "bound_by": "recovery_origin" if bound else None,
        "chain_root_run_id": origin_root if bound else None,
        "manifest_root_run_id": manifest.get("root_run_id") or manifest.get("source_run_id"),
        "lock_present": False,
        "holder_pid": None,
        "holder_acquired_at": None,
        "holder_is_superseded": False,
        "holder_alive": None,
        "missing": None,
        "verdict": "no_live_writer_evidence",
    }
    if not bound:
        report["missing"] = "chain_origin_binding"
        return report
    record = read_root_run_lock_record(runs_root, str(origin_root))
    if record is None:
        report["missing"] = "lock_record"
        return report
    report["lock_present"] = True
    holder, superseded = lock_holder_record(record)
    holder_pid = holder.get("pid")
    alive = pid_is_alive(holder_pid)
    report["holder_pid"] = (
        holder_pid if isinstance(holder_pid, int) and not isinstance(holder_pid, bool) else None
    )
    report["holder_acquired_at"] = (
        holder.get("acquired_at")
        if isinstance(holder.get("acquired_at"), str)
        else None
    )
    report["holder_is_superseded"] = superseded
    report["holder_alive"] = alive
    holder_root = holder.get("root_run_id")
    if not isinstance(holder_root, str) or holder_root != origin_root:
        report["missing"] = "lock_holder_binding"
        return report
    if report["holder_pid"] is None:
        report["missing"] = "holder_pid"
        return report
    if alive is None:
        report["missing"] = "holder_liveness_unverifiable"
        return report
    if alive is False:
        report["verdict"] = "writer_process_exited"
    else:
        report["verdict"] = "writer_may_be_active"
    return report


def source_writer_settles_recovery(report: Mapping[str, Any]) -> bool:
    """Fail-closed settlement predicate for the two §5.2 source-writer gates.

    A ``state.json`` that claims a possibly-live writer is settled by positive,
    auditable evidence that the writer process exited: the chain writer lock
    for a recovery-chain run, or an explicit host settlement record for a
    fresh run.  Everything else -- a live holder, a missing or unreadable
    record, an unbound chain, an unverifiable pid, no settlement -- keeps the
    original hard refusal: the §5.2 host procedure, not the recovery entry,
    is the path for those runs.
    """

    if not report.get("state_json_may_be_live_writer"):
        return True
    chain = report.get("chain_writer_lock")
    if isinstance(chain, Mapping) and chain.get("verdict") == "writer_process_exited":
        return True
    settlement = report.get("source_settlement")
    return isinstance(settlement, Mapping) and settlement.get("verdict") == (
        "writer_process_exited"
    )


def source_active_evidence(
    report: Mapping[str, Any], source_run_root: Path
) -> tuple[str, str]:
    """Locatable object plus the unchanged 60s host procedure for a refusal."""

    chain = report.get("chain_writer_lock")
    if isinstance(chain, Mapping) and chain.get("lock_present"):
        holder = chain.get("holder_pid")
        return (
            f"root_run_id:{chain.get('chain_root_run_id')}",
            "stop the original run through its existing stop channel (each wait "
            "at most 60s) and confirm its writer process exited; the lock record "
            f"under .recovery-locks/{chain.get('chain_root_run_id')}.lock and its "
            f"holder pid {holder!r} are the settlement evidence for the retry",
        )
    return (
        f"state.json:{Path(source_run_root).name}",
        "stop the original run through its existing stop channel (each wait at "
        "most 60s) and verify the platform writer state; if the host already "
        "controlled-stopped that writer of a fresh run and its stop channel is "
        "gone, record the explicit host settlement with "
        "`python -m modeling_team checkpoint settle-source --run-id <run-id> "
        "--stop-reference <reference>` and retry",
    )


def checkpoint_root_run_id(source_run_root: Path, checkpoint_id: str) -> str:
    """Read only the lock identity; a cheap pre-lock read for the CLI."""

    manifest = _load_manifest(source_run_root, checkpoint_id)
    root_run_id = manifest.get("root_run_id") or manifest.get("source_run_id")
    if not isinstance(root_run_id, str) or not root_run_id:
        raise _reject(
            "checkpoint_incomplete",
            "the checkpoint manifest carries no root_run_id",
            obj="manifest.json",
        )
    return root_run_id


# --- explicit host settlement for a stale fresh source run (design §5.2) --------


def settlement_record_path(runs_root: Path, run_id: str) -> Path:
    return Path(runs_root) / RECOVERY_SETTLEMENTS_DIRECTORY / f"{run_id}.json"


def read_source_settlement(runs_root: Path, run_id: str) -> dict[str, Any] | None:
    """Read one host settlement record; absent/unreadable is ``None``."""

    try:
        raw = settlement_record_path(runs_root, run_id).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        value = json.loads(raw.strip() or "null")
    except json.JSONDecodeError:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _settlement_obstacles(
    source_run_root: Path, readback: PlatformReadback, session_ids: list[str]
) -> list[dict[str, Any]]:
    """Live channels contradicting a settlement right now: the control FIFO
    must be gone and every known Build Session reachable, terminal and
    lease-free.  ``no FIFO + no session`` alone never proves anything (an
    active fresh run without them yet looks the same), so this only runs
    behind an explicit host record."""

    obstacles: list[dict[str, Any]] = []
    if (Path(source_run_root) / "control" / "outer-input.fifo").exists():
        obstacles.append(
            {
                "channel": "control_fifo",
                "session_id": None,
                "detail": "the run's control FIFO still exists",
            }
        )
    sessions = session_lease_report(readback, session_ids)
    for session_id in sorted(set(session_ids)):
        detail = sessions["sessions"].get(session_id) or {}
        if not detail.get("reachable"):
            obstacles.append(
                {
                    "channel": "session_unreachable",
                    "session_id": session_id,
                    "detail": f"Build Session {session_id} cannot be read back",
                }
            )
        elif detail.get("status") not in SESSION_TERMINAL_STATUSES:
            obstacles.append(
                {
                    "channel": "session_not_terminal",
                    "session_id": session_id,
                    "detail": f"Build Session {session_id} is not completed/cancelled",
                }
            )
    for session_id in sessions["active_lease_session_ids"]:
        obstacles.append(
            {
                "channel": "session_lease_active",
                "session_id": session_id,
                "detail": f"Build Session {session_id} still holds an active lease",
            }
        )
    return obstacles


def source_settlement_report(
    source_run_root: Path,
    runs_root: Path,
    readback: PlatformReadback,
    session_ids: list[str],
) -> dict[str, Any]:
    """The explicit host settlement as writer-liveness evidence (fresh runs).

    Only a record whose ``run_id`` and ``observed_state`` match the CURRENT
    ``state.json`` counts, and only for a fresh run (chain runs settle through
    their chain writer lock); the FIFO and known sessions are re-checked live,
    and write-tail safety stays with the reconciliation gate downstream.
    """

    root = Path(source_run_root)
    record = read_source_settlement(runs_root, root.name)
    report: dict[str, Any] = {
        "observed_state": None,
        "stop_reference": None,
        "created_at": None,
        "missing": None,
        "verdict": "no_settlement",
    }
    if record is None:
        return report
    for field_name in ("observed_state", "stop_reference", "created_at"):
        report[field_name] = record.get(field_name)
    if (
        record.get("schema_version") != SOURCE_SETTLEMENT_SCHEMA
        or record.get("run_id") != root.name
        or load_origin_record(root) is not None
    ):
        report["missing"] = "settlement_binding"
        report["verdict"] = "settlement_not_applicable"
        return report
    state = read_run_state(root)
    status = state.get("state") if isinstance(state, dict) else None
    if status not in POSSIBLY_LIVE_STATES or record.get("observed_state") != status:
        report["missing"] = "observed_state_mismatch"
        report["verdict"] = "settlement_not_applicable"
        return report
    obstacles = _settlement_obstacles(root, readback, session_ids)
    if obstacles:
        report["missing"] = obstacles[0].get("channel")
        report["obstacles"] = obstacles
        report["verdict"] = "settlement_contradicted"
        return report
    report["verdict"] = "writer_process_exited"
    return report


def settle_source_run(
    *,
    run_root: Path,
    stop_reference: str,
    readback: PlatformReadback,
) -> dict[str, Any]:
    """The host-only ``checkpoint settle-source`` settlement record.

    Called only AFTER the host controlled-stopped the original writer of a
    FRESH source run whose ``state.json`` still claims a possibly-live state.
    Creates no run, Build Session, Agent or start, writes nothing inside the
    source run; every unmet precondition is a typed refusal leaving no record.
    """

    run_root = Path(run_root)
    runs_root = run_root.parent
    if not isinstance(stop_reference, str) or not stop_reference.strip():
        raise _reject(
            REASON_SETTLEMENT_REFUSED,
            "--stop-reference must name how/when the original writer was stopped",
            obj="stop_reference",
        )
    if load_origin_record(run_root) is not None:
        raise _reject(
            REASON_SETTLEMENT_REFUSED,
            "this run carries a recovery origin; a recovery-chain run settles "
            "only through its chain writer lock evidence, never settle-source",
            obj=f"run_id:{run_root.name}",
        )
    state = read_run_state(run_root)
    status = state.get("state") if isinstance(state, dict) else None
    if status not in POSSIBLY_LIVE_STATES:
        raise _reject(
            REASON_SETTLEMENT_REFUSED,
            f"state.json reports {status!r}, not a possibly-live writer state; "
            "there is no stale live-writer claim to settle",
            obj=f"state.json:{run_root.name}",
        )
    if read_source_settlement(runs_root, run_root.name) is not None:
        raise _reject(
            REASON_SETTLEMENT_REFUSED,
            f"a settlement record already exists under "
            f"{RECOVERY_SETTLEMENTS_DIRECTORY}/{run_root.name}.json",
            obj=f"run_id:{run_root.name}",
        )
    tail = read_write_tail([run_root])
    session_ids = sorted(
        {
            intent.get("session_id")
            for intent in (tail.get(run_root.name) or {}).get("intents") or []
            if isinstance(intent, Mapping)
            and isinstance(intent.get("session_id"), str)
            and intent.get("session_id")
        }
    )
    obstacles = _settlement_obstacles(run_root, readback, session_ids)
    if obstacles:
        first = obstacles[0]
        raise _reject(
            REASON_SETTLEMENT_REFUSED,
            f"a live channel contradicts the settlement ({first.get('detail')}); "
            "the record is not written",
            obj=str(first.get("session_id") or first.get("channel")),
            retryable=True,
            retry="close the channel through its own lifecycle (stop channel, "
            "session complete/cancel, lease release/expire) or wait for the "
            "writer to actually stop, then re-run settle-source",
        )
    reconciliation = reconcile_write_tail([run_root], tail, readback, ontology_ids=[])
    if reconciliation["blocked"]:
        first = reconciliation["blocked"][0]
        raise _reject(
            REASON_WRITE_UNRECONCILED,
            f"{len(reconciliation['blocked'])} operation(s) are unknown or still "
            f"in flight (first: {first.get('idempotency_key')}); settle-source "
            "does not settle over an unclosed write tail",
            obj=str(first.get("idempotency_key")),
            retryable=True,
            retry="resolve the unknown writes with the existing platform "
            "recovery/diagnosis channels, then re-run settle-source",
        )
    record: dict[str, Any] = {
        "schema_version": SOURCE_SETTLEMENT_SCHEMA,
        "run_id": run_root.name,
        "observed_state": status,
        "stop_reference": stop_reference,
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = settlement_record_path(runs_root, run_root.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return record


# --- run-tree reads ------------------------------------------------------------


def _resolve_contract_file(
    snapshot: Path,
    recorded_digest: Any,
    repository_root: Path,
    directory: str,
    recorded_id: str,
) -> Path | None:
    """Resolve one frozen contract file by recorded identity (§4.2).

    The source run's snapshot wins when it still matches the digest recorded
    in the manifest; otherwise the repository checkout at the exact recorded
    id — or its id-prefixed file, because a logical profile id like
    ``r3-0-011`` maps to a longer file name — is the fallback.
    """

    if snapshot.is_file() and (
        recorded_digest is None or file_digest(snapshot) == recorded_digest
    ):
        return snapshot
    if not _RUN_ID_PATTERN.fullmatch(recorded_id):
        return None
    base = Path(repository_root) / "modeling_team" / directory
    candidates = [base / f"{recorded_id}.yaml", *sorted(base.glob(f"{recorded_id}-*.yaml"))]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_manifest(source_run_root: Path, checkpoint_id: str) -> dict[str, Any]:
    checkpoint_id = safe_checkpoint_id(checkpoint_id)
    path = manifest_path(Path(source_run_root), checkpoint_id)
    if not path.is_file():
        raise _reject(
            "checkpoint_not_found",
            f"no published checkpoint {checkpoint_id!r} in this run",
            obj="checkpoint_id",
            retryable=False,
            retry="run checkpoint inspect --run-id <run> to list published ids",
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _reject(
            "checkpoint_manifest_unparsable",
            f"checkpoint manifest is not readable JSON ({type(exc).__name__})",
            obj="manifest.json",
        ) from exc
    if not isinstance(manifest, dict):
        raise _reject(
            "checkpoint_manifest_unparsable",
            "checkpoint manifest is not a JSON object",
            obj="manifest.json",
        )
    return manifest


def _verify_packaged_digests(
    source_run_root: Path,
    manifest: Mapping[str, Any],
    checkpoint_id: str,
    *,
    phase: str = "checkpoint-resume",
) -> None:
    """Verify every packaged digest before anything downstream trusts it."""

    package_root = checkpoints_root(Path(source_run_root)) / checkpoint_id
    for artifact in manifest.get("artifacts") or []:
        if not isinstance(artifact, Mapping):
            raise _reject(
                "checkpoint_incomplete",
                "a manifest artifact entry is not an object",
                obj="manifest.json",
                phase=phase,
            )
        side = (
            CHECKPOINT_HOST_PRIVATE_DIRECTORY
            if artifact.get("host_private")
            else CHECKPOINT_ARTIFACTS_DIRECTORY
        )
        snapshot = package_root / side / str(artifact.get("source") or "")
        if not snapshot.is_file():
            raise _reject(
                "checkpoint_incomplete",
                f"packaged artifact {artifact.get('source')!r} is missing",
                obj=str(artifact.get("source")),
                phase=phase,
                retryable=True,
                retry="the package is incomplete; re-save it from a stable run",
            )
        if file_digest(snapshot) != artifact.get("digest"):
            raise _reject(
                "artifact_changed",
                f"packaged artifact {artifact.get('source')!r} digest mismatch",
                obj=str(artifact.get("source")),
                phase=phase,
                retryable=True,
                retry="re-save the checkpoint from a stable source run",
            )


def _resolve_checkpoint_contracts(
    source_run_root: Path,
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> tuple[Path, Path]:
    """Resolve the frozen Task/Profile files by their recorded identity (§4.2).

    The source run's snapshot wins when it still matches the digest recorded
    in the manifest; otherwise the repository checkout at the exact recorded
    id — or its id-prefixed file, because a logical profile id like
    ``r3-0-011`` maps to a longer file name — is the fallback.
    """

    source_run_root = Path(source_run_root)
    configuration = manifest.get("configuration") or {}
    recorded_files = {
        str(entry.get("path")): entry.get("digest")
        for entry in configuration.get("configuration_files") or []
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }
    profile_id = str(configuration.get("profile_id"))
    task_id = str(configuration.get("task_id"))
    profile_path = _resolve_contract_file(
        source_run_root / "profile.snapshot.yaml",
        recorded_files.get("profile.snapshot.yaml"),
        repository_root,
        "profiles",
        profile_id,
    )
    task_path = _resolve_contract_file(
        source_run_root / "task.snapshot.yaml",
        recorded_files.get("task.snapshot.yaml"),
        repository_root,
        "tasks",
        task_id,
    )
    if profile_path is None or task_path is None:
        raise _reject(
            REASON_CONTRACT_INCOMPATIBLE,
            "the checkpoint's frozen Task/Profile files are not present at their "
            "recorded identities (source-run snapshot or repository checkout)",
            obj="configuration",
            retryable=True,
            retry="restore the recorded contract files or record a compatible "
            "fix in the recovery origin before resuming",
        )
    return profile_path, task_path


def _require_configuration_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    configuration = manifest.get("configuration") or {}
    for name in ("profile_id", "task_id"):
        if not isinstance(configuration.get(name), str) or not configuration.get(name):
            raise _reject(
                "checkpoint_incomplete",
                f"the checkpoint configuration is missing {name}",
                obj="configuration",
            )
    return configuration


def read_run_state(run_root: Path) -> dict[str, Any] | None:
    path = Path(run_root) / "state.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_origin_record(run_root: Path) -> dict[str, Any] | None:
    path = Path(run_root) / RECOVERY_DIRECTORY / "origin.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_recovery_imports(run_root: Path) -> dict[str, Any] | None:
    """This run's completion index, or None when it is not a trusted source.

    Strict loader for ``recovery/imports.json`` (what ``write_recovery_files``
    publishes at resume time): the schema must match, the completed operations
    must be a list, the completed client batches a mapping, and the record must
    sit next to this run's own recovery origin bound to the same checkpoint.
    Anything else keeps the caller's fail-closed classification.
    """

    origin = load_origin_record(run_root)
    if origin is None:
        return None
    try:
        value = json.loads(
            (Path(run_root) / RECOVERY_DIRECTORY / "imports.json").read_text("utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("schema_version") != RECOVERY_SCHEMA:
        return None
    if origin.get("checkpoint_id") != value.get("checkpoint_id"):
        return None
    if not isinstance(value.get("completed_operations"), list):
        return None
    if not isinstance(value.get("completed_client_batches"), dict):
        return None
    return value


def recovery_index_settled_entry(
    imports: Mapping[str, Any] | None,
    intent: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """The completion-index entry proving ``intent`` already applied, or None.

    The index was proven over the full recovery chain by the resume-time
    platform readback; this binds one durable intent to its entry on the
    complete operation identity the existing fields can confirm — never on the
    key or client batch name alone, never on a partial item completion
    (whole-batch proof additionally requires the client batch in
    ``completed_client_batches`` mapped to this receipt's platform batch).
    Every miss keeps the caller's fail-closed unknown.
    """

    if not imports or receipt is None:
        return None
    idempotency_key = intent.get("idempotency_key")
    client_batch_id = intent.get("client_batch_id")
    applied_batches = imports.get("completed_client_batches") or {}
    for entry in imports.get("completed_operations") or []:
        if not isinstance(entry, Mapping):
            continue
        key = entry.get("key")
        if not isinstance(key, list) or len(key) < 5:
            continue
        if entry.get("idempotency_key") != idempotency_key:
            continue
        if entry.get("client_batch_id") != client_batch_id:
            continue
        if key[1] != intent.get("session_id"):
            continue
        if key[2] != receipt.get("batch_id"):
            continue
        if entry.get("receipt_ordinal") != receipt.get("ordinal"):
            continue
        if entry.get("mode") != intent.get("mode"):
            continue
        # A projection bound on one side only is a different operation.
        if (entry.get("projection_digest") or None) != (
            intent.get("projection_digest") or None
        ):
            continue
        entry_commands = entry.get("command_digests")
        if entry_commands and list(entry_commands) != list(
            intent.get("commands") or []
        ):
            continue
        if applied_batches.get(client_batch_id) != receipt.get("batch_id"):
            continue
        return entry
    return None


def origin_chain_roots(source_run_root: Path, runs_root: Path) -> list[Path]:
    """The recovery chain, oldest root run first, source run last (M25).

    A resumed run records its own ``recovery/origin.json`` pointing back to its
    source; following those records collects every prior execution whose
    intents/receipts/platform writes must be reconciled before this new resume.
    """

    chain: list[Path] = []
    current = Path(source_run_root)
    seen: set[Path] = {current}
    while True:
        chain.append(current)
        origin = load_origin_record(current)
        if origin is None:
            break
        if origin.get("schema_version") == "r3-0-017-fork/v1":
            # A fork's imported snapshot starts a new write chain. Historical
            # exposure was already unioned into this run before it started.
            break
        source_id = origin.get("source_run_id")
        if not isinstance(source_id, str) or not source_id:
            break
        parent = Path(runs_root) / source_id
        if parent in seen or not parent.is_dir():
            break
        seen.add(parent)
        current = parent
    chain.reverse()
    return chain


def read_write_tail(chain_roots: list[Path]) -> dict[str, dict[str, Any]]:
    """Full intents/receipts per chain run, including post-checkpoint writes."""

    tail: dict[str, dict[str, Any]] = {}
    for run_root in chain_roots:
        run_root = Path(run_root)
        run_id = run_root.name
        try:
            intents: list[dict[str, Any]] = list(read_submission_intents(run_root))
            receipts: list[dict[str, Any]] = list(read_submission_receipts(run_root))
        except Exception:  # noqa: BLE001 - a dead chain run may miss staged dirs
            intents, receipts = [], []
        tail[run_id] = {"intents": intents, "receipts": receipts}
    return tail


# --- source writer state (design §5.2 hung-run procedure) ----------------------


def source_writer_report(
    source_run_root: Path, readback: PlatformReadback, session_ids: list[str]
) -> dict[str, Any]:
    """Facts about whether the original writer can still be alive (M45).

    The report never claims a stopped writer from PID-style evidence alone;
    it lists the observable channels (state.json, control FIFO, run-directory
    ownership) and the actual platform Session/Lease state with ``expires_at``
    plus the earliest lease-recheck time.  Each individual wait is capped at
    :data:`WAIT_SECONDS_MAX` seconds.
    """

    root = Path(source_run_root)
    state = read_run_state(root)
    # ``TeamRunner._state`` writes the run state under the ``state`` key with
    # values like RUNNING/PAUSED/WAITING_OWNER/ABORTING/CLEANED.
    status = state.get("state") if isinstance(state, dict) else None
    control_fifo = root / "control" / "outer-input.fifo"
    stat = os.stat(root)
    sessions = session_lease_report(readback, session_ids)
    writer_alive = str(status) in POSSIBLY_LIVE_STATES
    return {
        "source_run_id": root.name,
        "state_json_status": status,
        "state_json_may_be_live_writer": writer_alive,
        "control_fifo_present": control_fifo.exists(),
        "run_directory_owner_uid": stat.st_uid,
        "wait_seconds_max": WAIT_SECONDS_MAX,
        "platform_sessions": sessions,
        "verdict": "writer_may_be_active" if writer_alive else "no_live_writer_evidence",
    }


def session_lease_report(
    readback: PlatformReadback, session_ids: list[str]
) -> dict[str, Any]:
    """Actual Session/Lease readback with the earliest lease-recheck time."""

    details: dict[str, Any] = {}
    active_leases: list[str] = []
    expires: list[str] = []
    for session_id in sorted(set(session_ids)):
        try:
            detail = readback.get_session(session_id)
        except CheckpointError:
            details[session_id] = {"reachable": False}
            continue
        session = detail.get("session", detail) if isinstance(detail, dict) else {}
        leases = detail.get("leases", []) if isinstance(detail, dict) else []
        states = []
        for lease in leases if isinstance(leases, list) else []:
            if not isinstance(lease, dict):
                continue
            states.append(str(lease.get("state")))
            if lease.get("state") not in {"released", "expired", "cancelled"}:
                active_leases.append(session_id)
                if isinstance(lease.get("expires_at"), str):
                    expires.append(lease["expires_at"])
        details[session_id] = {
            "reachable": True,
            "status": session.get("status") if isinstance(session, dict) else None,
            "lease_states": states,
        }
    return {
        "sessions": details,
        "active_lease_session_ids": sorted(set(active_leases)),
        "lease_expires_at": sorted(set(expires)),
        "earliest_lease_recheck_at": min(expires) if expires else None,
    }


# --- platform readback (D1: cursor endpoints only, never truncated views) -----


class PlatformReadback:
    """Read-only platform traversal through the cursor-paginated endpoints.

    The batch listing endpoints (``GET /api/build-sessions/{id}/modeling-batches``
    and ``GET /api/ontologies/{id}/modeling-batches``) are the ONLY enumeration
    sources: their ``limit`` is capped at 100 by the backend and pagination is
    followed through ``next_cursor`` until exhaustion.  The convenience views
    that truncate (``platform_state.modeling_batches`` at 20 entries and the
    Build Session detail's ``modeling_batches`` at 50) are never consulted for
    reconciliation facts.  Batch content identity comes from
    ``GET /api/modeling-batches/{batch_id}`` (``content_hash`` plus every
    Attempt and item result).
    """

    def __init__(
        self,
        request: Callable[[str, str, dict[str, Any] | None, str], tuple[int, Any]],
        admin_key: str,
    ) -> None:
        self._request = request
        self._admin_key = admin_key
        self.pages_read = 0
        self.batches_read = 0
        self.sessions_read = 0

    def _get(self, path: str) -> Any:
        status, value = self._request("GET", path, None, self._admin_key)
        if status != 200:
            raise _reject(
                "platform_readback_unreachable",
                f"platform readback {path} failed with status {status}",
                obj=path,
                retryable=True,
                retry="the write gate stays closed until every page of the "
                "reconciliation readback is reachable",
            )
        return value

    def _paginate(self, endpoint: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            path = f"{endpoint}?limit={LIST_PAGE_LIMIT}"
            if cursor is not None:
                path += f"&cursor={cursor}"
            value = self._get(path)
            page = value.get("batches", value.get("items")) if isinstance(value, dict) else None
            if not isinstance(page, list):
                raise _reject(
                    "platform_readback_unreachable",
                    f"platform readback {endpoint} returned an invalid page",
                    obj=endpoint,
                    retryable=True,
                )
            items.extend(item for item in page if isinstance(item, dict))
            self.pages_read += 1
            cursor = value.get("next_cursor") if isinstance(value, dict) else None
            if not cursor:
                return items

    def list_session_batches(self, session_id: str) -> list[dict[str, Any]]:
        """Every batch of one session: full pagination + authoritative detail."""

        summaries = self._paginate(LIST_PAGE_ENDPOINT.format(session_id=session_id))
        details: list[dict[str, Any]] = []
        for summary in summaries:
            batch_id = summary.get("batch_id")
            if not isinstance(batch_id, str):
                raise _reject(
                    "platform_readback_unreachable",
                    "a batch summary in the paginated listing has no batch_id",
                    obj="batch_listing",
                    retryable=True,
                )
            details.append(self.get_batch(batch_id))
        return details

    def list_ontology_batches(self, ontology_id: str) -> list[dict[str, Any]]:
        return self._paginate(ONTOLOGY_LIST_PAGE_ENDPOINT.format(ontology_id=ontology_id))

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        value = self._get(BATCH_DETAIL_ENDPOINT.format(batch_id=batch_id))
        if not isinstance(value, dict):
            raise _reject(
                "platform_readback_unreachable",
                f"batch detail for {batch_id} is not an object",
                obj=BATCH_DETAIL_ENDPOINT.format(batch_id=batch_id),
                retryable=True,
            )
        self.batches_read += 1
        return value

    def get_session(self, session_id: str) -> dict[str, Any]:
        value = self._get(SESSION_DETAIL_ENDPOINT.format(session_id=session_id))
        if not isinstance(value, dict):
            raise _reject(
                "platform_readback_unreachable",
                f"Build Session detail for {session_id} is not an object",
                obj=SESSION_DETAIL_ENDPOINT.format(session_id=session_id),
                retryable=True,
            )
        self.sessions_read += 1
        return value


# --- write-tail reconciliation (design §5.1) ------------------------------------


@dataclass(frozen=True)
class CompletedOperation:
    """One entry of the completion index (same-operation reuse only)."""

    origin_run_id: str
    session_id: str
    batch_id: str
    attempt_id: str
    client_item_id: str
    client_batch_id: str | None = None
    idempotency_key: str | None = None
    mode: str | None = None
    content_hash: str | None = None
    projection_digest: str | None = None
    command_digests: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()
    evidence_association_ids: tuple[str, ...] = ()
    receipt_ordinal: int | None = None
    readback_only: bool = False

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.origin_run_id,
            self.session_id,
            self.batch_id,
            self.attempt_id,
            self.client_item_id,
        )

    def index_entry(self) -> dict[str, Any]:
        return {
            "key": list(self.key),
            "client_batch_id": self.client_batch_id,
            "idempotency_key": self.idempotency_key,
            "mode": self.mode,
            "content_hash": self.content_hash,
            "projection_digest": self.projection_digest,
            "command_digests": list(self.command_digests),
            "resource_ids": list(self.resource_ids),
            "evidence_association_ids": list(self.evidence_association_ids),
            "receipt_ordinal": self.receipt_ordinal,
            "receipt_missing_readback_proved": self.readback_only,
        }


def _attempt_items(attempt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = attempt.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _terminal_attempts(batch: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    attempts = batch.get("attempts")
    if not isinstance(attempts, list):
        return []
    return [item for item in attempts if isinstance(item, Mapping)]


def reconcile_write_tail(
    chain_roots: list[Path],
    tail: Mapping[str, Mapping[str, Any]],
    readback: PlatformReadback,
    *,
    ontology_ids: list[str],
) -> dict[str, Any]:
    """Classify every chain operation against the live platform state.

    Implements the design §5.1 table.  ``adjudicate_unknown_intent``-style
    hit/miss hints never release the gate here: an ``unknown`` intent stays
    ``write_unreconciled`` unless the precise platform readback proves the
    operation's terminal outcome, and even then the missing-receipt fact is
    preserved rather than rewritten into the old run.

    One operation can be a NON-write and still share its Batch with the apply
    operation that followed it (the real runner submits ``stage-dry-vN`` and
    ``stage-apply-vN`` as two operations over one ``client_batch_id``).  Such a
    dry-run is settled history once that Batch reads back ``applied``: it never
    materialized anything, so it neither blocks the gate nor schedules another
    dry-run, while the apply operation remains the only source of the
    completion index.
    """

    # Read back every session referenced by the chain's intents.
    session_ids: set[str] = set()
    for run in tail.values():
        for intent in run.get("intents") or []:
            session_id = intent.get("session_id")
            if isinstance(session_id, str) and session_id:
                session_ids.add(session_id)
    session_batches: dict[str, list[dict[str, Any]]] = {
        session_id: readback.list_session_batches(session_id)
        for session_id in sorted(session_ids)
    }

    completed: list[CompletedOperation] = []
    completed_client_batches: dict[str, str] = {}
    pending_new_dry_run: list[dict[str, Any]] = []
    settled_non_write: list[dict[str, Any]] = []
    recoverable_new_batch: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []

    def batch_by_identity(session_id: str, intent: Mapping[str, Any]) -> dict[str, Any] | None:
        for batch in session_batches.get(session_id) or []:
            if batch.get("client_batch_id") == intent.get("client_batch_id") or (
                batch.get("build_session_id") == session_id
                and batch.get("idempotency_key") == intent.get("idempotency_key")
            ):
                return batch
        return None

    chain_keys: set[tuple[str, str]] = set()
    for run_id, run in tail.items():
        for intent in run.get("intents") or []:
            key = intent.get("idempotency_key")
            if isinstance(key, str):
                chain_keys.add((run_id, key))

    # The Batch identities a chain apply-family operation claims.  Only such an
    # operation can have materialized a Batch, so an applied Batch that no
    # apply intent names is an unattributable write and never settles anything.
    chain_apply_client_batches = {
        str(intent.get("client_batch_id"))
        for run in tail.values()
        for intent in run.get("intents") or []
        if str(intent.get("mode") or "") in APPLY_MODES and intent.get("client_batch_id")
    }

    seen_operations: set[tuple[str, str]] = set()
    for run_root, (run_id, run) in zip(chain_roots, tail.items()):
        receipts_by_key = {
            receipt.get("idempotency_key"): receipt
            for receipt in run.get("receipts") or []
            if receipt.get("idempotency_key")
        }
        for intent in run.get("intents") or []:
            operation = (run_id, str(intent.get("idempotency_key")))
            if operation in seen_operations:
                continue
            seen_operations.add(operation)
            base = {
                "origin_run_id": run_id,
                "ordinal": intent.get("ordinal"),
                "idempotency_key": intent.get("idempotency_key"),
                "client_batch_id": intent.get("client_batch_id"),
                "session_id": intent.get("session_id"),
                "mode": intent.get("mode"),
                "intent_status": intent.get("status"),
            }
            session_id = intent.get("session_id")
            batch = batch_by_identity(session_id, intent) if session_id else None
            receipt = receipts_by_key.get(intent.get("idempotency_key"))
            intent_mode = str(intent.get("mode") or "")
            intent_is_apply = intent_mode in APPLY_MODES
            if intent.get("status") == "unknown" and batch is None:
                if intent_mode == "dry_run":
                    # A dry run is a non-write, and ``batch is None`` here means
                    # the session listing itself was reachable (an unreachable
                    # listing raises before this loop).  That reachable empty
                    # listing is the same provable platform fact
                    # ``adjudicate_unknown_intent``'s retry branch uses: the
                    # request never materialized anything, so the gate releases
                    # into a NEW dry-run instead of blocking forever on a batch
                    # row that cannot exist.  Apply-mode unknowns stay blocked.
                    pending_new_dry_run.append(
                        {
                            **base,
                            "detail": "unknown-result dry-run with no platform "
                            "batch: the reachable session listing proves the "
                            "request never materialized anything; enter a NEW "
                            "dry-run in the new session",
                        }
                    )
                    continue
                # Design §5.1: only the Agent's own safe_to_retry claim, no
                # provable platform fact -> keep reconciling, never bypass.
                blocked.append(
                    {
                        **base,
                        "reason": REASON_WRITE_UNRECONCILED,
                        "detail": "unknown-result intent with no precise platform "
                        "readback; adjudication hints alone cannot release the gate",
                    }
                )
                continue
            if batch is None:
                if intent.get("status") == "pending":
                    pending_new_dry_run.append({**base, "detail": "never submitted"})
                elif intent_mode == "dry_run":
                    pending_new_dry_run.append(
                        {**base, "detail": "dry-run never reached the platform"}
                    )
                else:
                    blocked.append(
                        {
                            **base,
                            "reason": REASON_WRITE_UNRECONCILED,
                            "detail": "apply intent with no receipt and no platform "
                            "batch; the request outcome cannot be proven",
                        }
                    )
                continue
            attempts = _terminal_attempts(batch)
            applied = [
                attempt
                for attempt in attempts
                if attempt.get("attempt_status") == "applied"
                and str(attempt.get("mode") or "") in APPLY_MODES
            ]
            in_flight = [
                attempt
                for attempt in attempts
                if attempt.get("attempt_status") in {"applying", "recovering", "validating"}
            ]
            failed = [
                attempt
                for attempt in attempts
                if attempt.get("attempt_status") == "failed"
            ]
            partially = [
                attempt
                for attempt in attempts
                if attempt.get("attempt_status") == "partially_applied"
            ]
            if in_flight or partially:
                blocked.append(
                    {
                        **base,
                        "batch_id": batch.get("batch_id"),
                        "reason": REASON_WRITE_UNRECONCILED,
                        "detail": "platform attempt is applying/recovering/partially "
                        "applied; the write gate stays closed",
                    }
                )
                continue
            if applied and intent_is_apply:
                attempt = applied[-1]
                readback_only = receipt is None
                for result in _attempt_items(attempt):
                    client_item_id = result.get("client_item_id")
                    if not isinstance(client_item_id, str):
                        continue
                    completed.append(
                        CompletedOperation(
                            origin_run_id=run_id,
                            session_id=str(batch.get("build_session_id") or session_id),
                            batch_id=str(batch.get("batch_id")),
                            attempt_id=str(attempt.get("attempt_id")),
                            client_item_id=client_item_id,
                            client_batch_id=intent.get("client_batch_id"),
                            idempotency_key=intent.get("idempotency_key"),
                            mode=intent_mode,
                            content_hash=batch.get("content_hash"),
                            projection_digest=intent.get("projection_digest"),
                            command_digests=tuple(
                                str(item) for item in intent.get("commands") or []
                            ),
                            resource_ids=tuple(
                                str(value)
                                for value in (result.get("resource_outputs") or [])
                            ),
                            evidence_association_ids=tuple(
                                str(value)
                                for value in (result.get("evidence_association_ids") or [])
                            ),
                            receipt_ordinal=(
                                receipt.get("ordinal") if isinstance(receipt, dict) else None
                            ),
                            readback_only=readback_only,
                        )
                    )
                # A receipt-missing-but-readback-proved operation keeps that
                # fact on every index entry (readback_only=True); the old run
                # is never given a fabricated receipt.
                completed_client_batches[
                    str(intent.get("client_batch_id"))
                ] = str(batch.get("batch_id"))
                continue
            if applied and intent_mode == "dry_run":
                # A settled historical NON-write.  The dry-run materialized
                # nothing, and the Batch it names was applied afterwards by its
                # own apply operation (same client_batch_id; that intent's row
                # above built the completion index).  It is not an unknown write
                # and it is never queued as a new dry-run over a Batch that is
                # already materialized.
                if str(intent.get("client_batch_id")) in chain_apply_client_batches:
                    settled_non_write.append(
                        {
                            **base,
                            "batch_id": batch.get("batch_id"),
                            "detail": "historical non-write: the dry-run is "
                            "superseded by the applied Batch its own apply "
                            "operation registered; nothing to resubmit",
                        }
                    )
                else:
                    blocked.append(
                        {
                            **base,
                            "batch_id": batch.get("batch_id"),
                            "reason": REASON_WRITE_UNRECONCILED,
                            "detail": "the Batch reads back applied but no chain "
                            "apply operation claims it; the write stays "
                            "unattributable",
                        }
                    )
                continue
            if (
                intent_mode == "dry_run"
                and not applied
                and attempts
                and attempts[-1].get("attempt_status") == "validation_failed"
            ):
                # Field defect (the 2026-10-05 start2 S2 blocker): a dry-run
                # Batch whose final attempt terminally read back
                # ``validation_failed`` matched no §5.1 row and fell into the
                # catch-all blocked refusal.  The platform validates BEFORE
                # any mutation, so this terminal state is a precise platform
                # fact that nothing was written -- the same proof class as the
                # failed_without_side_effects row, never a role claim.  The
                # rejected content is settled history: its repair is a
                # corrected revision through the normal submission path
                # (which already applies under later client_batch_ids), so it
                # neither keeps the gate closed nor queues a replay of this
                # batch.  Apply-family intents keep the existing rows: an
                # apply over a validation_failed Batch stays blocked.
                settled_non_write.append(
                    {
                        **base,
                        "batch_id": batch.get("batch_id"),
                        "detail": "historical non-write: the dry-run attempt "
                        "terminally failed validation before any write "
                        "(nothing materialized); the rejected content is "
                        "settled history -- its repair is a corrected "
                        "revision through the normal submission path, never "
                        "a resubmission of this batch",
                    }
                )
                continue
            if intent_mode == "dry_run" or (not intent_is_apply and not applied):
                validated = [
                    attempt
                    for attempt in attempts
                    if attempt.get("attempt_status") == "validated"
                ]
                if validated and not applied:
                    pending_new_dry_run.append(
                        {
                            **base,
                            "batch_id": batch.get("batch_id"),
                            "detail": "dry-run validated, never applied; reuse the "
                            "plan/semantic approvals and enter a NEW dry-run in the "
                            "new session (not materialized)",
                        }
                    )
                    continue
            if failed and not applied:
                recovery = (failed[-1].get("recovery") or {})
                safe = (
                    recovery.get("safe_to_retry") is True
                    or failed[-1].get("attempt_status") == "failed"
                    and recovery.get("state") == "failed_without_side_effects"
                )
                if safe:
                    recoverable_new_batch.append(
                        {
                            **base,
                            "batch_id": batch.get("batch_id"),
                            "detail": "platform-proven failed_without_side_effects; "
                            "continue only the unfinished items in a new Batch",
                        }
                    )
                else:
                    blocked.append(
                        {
                            **base,
                            "batch_id": batch.get("batch_id"),
                            "reason": REASON_WRITE_UNRECONCILED,
                            "detail": "failed attempt without an explicit "
                            "failed_without_side_effects platform fact",
                        }
                    )
                continue
            blocked.append(
                {
                    **base,
                    "batch_id": batch.get("batch_id"),
                    "reason": REASON_WRITE_UNRECONCILED,
                    "detail": "operation outcome did not fall into a classification "
                    "row; keep the write gate closed",
                }
            )

    # Scope drift (M21/M26): platform batches on the recovery-bound ontologies
    # whose session is outside the chain are writes this recovery cannot
    # attribute to itself.
    chain_sessions = set(session_ids)
    for ontology_id in ontology_ids:
        for summary in readback.list_ontology_batches(ontology_id):
            session_id = summary.get("build_session_id")
            if session_id not in chain_sessions:
                drift.append(
                    {
                        "ontology_id": ontology_id,
                        "batch_id": summary.get("batch_id"),
                        "session_id": session_id,
                        "reason": REASON_SCOPE_DRIFT,
                        "detail": "platform write that cannot be attributed to the "
                        "recovery chain",
                    }
                )

    return {
        "completion_index": {entry.key: entry for entry in completed},
        "completed": completed,
        "completed_client_batches": completed_client_batches,
        "pending_new_dry_run": pending_new_dry_run,
        "settled_non_write": settled_non_write,
        "recoverable_new_batch": recoverable_new_batch,
        "blocked": blocked,
        "scope_drift": drift,
        "readback_counters": {
            "sessions_read": readback.sessions_read,
            "batches_read": readback.batches_read,
            "pages_read": readback.pages_read,
        },
    }


# --- business approval reuse (design §6.1) --------------------------------------


def _coordinator_agent_id(profile_snapshot: Mapping[str, Any]) -> str | None:
    """Resolve the approving logical identity from the packaged profile.

    The expected approver is the agent whose *package* binds the coordinator
    role in the source run's own profile snapshot — never a literal comparison
    against the string ``coordinator`` (M30).
    """

    agents = profile_snapshot.get("agents")
    if not isinstance(agents, list):
        return None
    for agent in agents:
        if not isinstance(agent, Mapping):
            continue
        package = str(agent.get("package") or "")
        agent_id = str(agent.get("agent_id") or "")
        if package == "coordinator" or (agent_id == "coordinator" and not package):
            return agent_id
    return None


def _approvals_of(manifest: Mapping[str, Any], source_run_root: Path) -> dict[str, Any] | None:
    for artifact in manifest.get("artifacts") or []:
        if not isinstance(artifact, Mapping) or artifact.get("host_private"):
            continue
        if artifact.get("source") == _APPROVALS_SOURCE:
            path = (
                checkpoints_root(source_run_root)
                / str(manifest.get("checkpoint_id"))
                / CHECKPOINT_ARTIFACTS_DIRECTORY
                / _APPROVALS_SOURCE
            )
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise _reject(
                    "checkpoint_incomplete",
                    "the packaged business approvals artifact is unreadable",
                    obj=_APPROVALS_SOURCE,
                )
            if not isinstance(value, dict):
                raise _reject(
                    "checkpoint_incomplete",
                    "the packaged business approvals artifact is not an object",
                    obj=_APPROVALS_SOURCE,
                )
            return value
    return None


def _approval_heads(entries: Any) -> dict[tuple[str, str], Mapping[str, Any]]:
    """Collapse approvals entries to the effective head per decision key.

    A decision binds at ``(kind, target_id)``; its head is the entry with the
    highest revision and everything older is history (never a decision to
    resurrect, never a revocation by itself).  List order never outranks the
    revision.
    """

    heads: dict[tuple[str, str], Mapping[str, Any]] = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, Mapping):
            continue
        key = (str(entry.get("kind")), str(entry.get("target_id")))
        head = heads.get(key)
        if head is None or _approval_revision(entry) >= _approval_revision(head):
            heads[key] = entry
    return heads


def _approval_revision(entry: Mapping[str, Any]) -> int:
    revision = entry.get("revision")
    if isinstance(revision, int) and not isinstance(revision, bool):
        return revision
    return -1


def validate_business_approvals(
    manifest: Mapping[str, Any], source_run_root: Path
) -> dict[str, Any]:
    """Validate the approval source channel; produce the imports record (M27/M30).

    Accepts an approval only when the file is packaged by THIS exact checkpoint
    (digest-verified by the package check), its ``approved_by`` matches the
    coordinator agent id resolved from the source run's own profile snapshot,
    and the source run's CURRENT approvals file still carries the same effective
    decision for every ``(kind, target_id)``: the highest revision on each side
    must agree in both revision and approved decision content, so older packaged
    revisions are history rather than decisions to resurrect, and a post-save
    revocation or replacement of the head stays revoked.  Rejections are
    typed and item-scoped: the source run is never modified and correctable
    conflicts only make the affected items wait.
    """

    packaged = _approvals_of(manifest, Path(source_run_root))
    if packaged is None:
        return {"present": False, "valid": [], "invalidated": [], "approver": None}
    configuration = manifest.get("configuration") or {}
    profile_path = Path(source_run_root) / "profile.snapshot.yaml"
    try:
        profile_snapshot = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        profile_snapshot = None
    if not isinstance(profile_snapshot, Mapping):
        raise _reject(
            "checkpoint_incomplete",
            "the source run's profile snapshot is not readable; the approval "
            "channel cannot be verified",
            obj="profile.snapshot.yaml",
        )
    if str(profile_snapshot.get("profile_id") or "") != str(configuration.get("profile_id") or ""):
        raise _reject(
            REASON_APPROVAL_BINDING_CHANGED,
            "the packaged approvals were produced by a different profile than "
            "the checkpoint configuration records",
            obj="profile.snapshot.yaml",
            retryable=True,
            retry="re-save a checkpoint from the matching profile run",
        )
    approver = _coordinator_agent_id(profile_snapshot)
    if approver is None:
        raise _reject(
            REASON_APPROVAL_BINDING_CHANGED,
            "the source profile binds no coordinator role; the approval channel "
            "cannot be verified",
            obj="profile.snapshot.yaml",
            retryable=False,
        )
    packaged_heads = _approval_heads(packaged.get("entries"))
    current_heads: dict[tuple[str, str], Mapping[str, Any]] = {}
    current_path = staged_decision_artifact_paths(Path(source_run_root))["approvals"]
    if current_path.is_file():
        try:
            current_value = json.loads(current_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current_value = None
        if isinstance(current_value, Mapping):
            current_heads = _approval_heads(current_value.get("entries"))
    valid: list[dict[str, Any]] = []
    invalidated: list[dict[str, Any]] = []
    for entry in packaged_heads.values():
        record = {
            "kind": entry.get("kind"),
            "target_id": entry.get("target_id"),
            "revision": entry.get("revision"),
            "approved_by": entry.get("approved_by"),
        }
        # Coordinator-identity binding is the in-process contract for decision
        # approvals (``conclusion_confirmation``).  A ``stage3_slot`` entry is
        # a slot marker whose ``approved_by`` only needs to be nonempty in the
        # frozen approvals schema, and whose own note disclaims submission
        # authority -- demanding the coordinator identity here would be
        # stricter than the contract that produced the packaged evidence.
        if (
            str(entry.get("kind")) == "conclusion_confirmation"
            and entry.get("approved_by") != approver
        ):
            invalidated.append(
                {
                    **record,
                    "reason": REASON_APPROVAL_BINDING_CHANGED,
                    "detail": f"approved_by does not match the source run's "
                    f"coordinator agent {approver!r} resolved from its own profile",
                }
            )
            continue
        key = (str(entry.get("kind")), str(entry.get("target_id")))
        current_entry = current_heads.get(key)
        if current_entry is None or current_entry.get("revision") != entry.get("revision"):
            invalidated.append(
                {
                    **record,
                    "reason": REASON_APPROVAL_BINDING_CHANGED,
                    "detail": "the source run's current approvals no longer carry "
                    "this decision at this revision (revoked or replaced after "
                    "the save); a checkpoint cannot resurrect it",
                }
            )
            continue
        # Same revision, different decision content: the head was replaced in
        # place, so the packaged decision must not slip through as a reuse.
        if (
            current_entry.get("approved_by") != entry.get("approved_by")
            or current_entry.get("confirmed_enum_value")
            != entry.get("confirmed_enum_value")
        ):
            invalidated.append(
                {
                    **record,
                    "reason": REASON_APPROVAL_BINDING_CHANGED,
                    "detail": "the source run's current approvals carry different "
                    "decision content at this revision (replaced after the save); "
                    "a checkpoint cannot resurrect it",
                }
            )
            continue
        valid.append(record)
    return {
        "present": True,
        "approver": approver,
        "source_path": _APPROVALS_SOURCE,
        "source_digest": next(
            (
                artifact.get("digest")
                for artifact in manifest.get("artifacts") or []
                if isinstance(artifact, Mapping)
                and artifact.get("source") == _APPROVALS_SOURCE
            ),
            None,
        ),
        "valid": valid,
        "invalidated": invalidated,
    }


# --- plan mapping, role packets, recovery files ---------------------------------


def build_plan_mappings(
    manifest: Mapping[str, Any],
    source_run_root: Path,
    reconciliation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Host-owned plan mapping: source plan identity -> current plan identity.

    Unfinished plans keep their original ``plan_ref``/digest as the source side
    and gain the current-run side once the new session republishes them; the
    retained ``client_item_id`` set plus the projection's candidate/decision/
    identity bindings locate the original operation (design §5.2).  Completed
    plans are not mapped for execution; they land in the forbidden-resubmission
    list.
    """

    checkpoint_id = str(manifest.get("checkpoint_id"))
    package_root = checkpoints_root(Path(source_run_root)) / checkpoint_id
    plans = [
        artifact
        for artifact in manifest.get("artifacts") or []
        if isinstance(artifact, Mapping)
        and str(artifact.get("source") or "").startswith(
            "stage3-neutral-graph/materialization-plans/"
        )
    ]
    completed_batches = set(reconciliation.get("completed_client_batches") or {})
    mappings: list[dict[str, Any]] = []
    for artifact in plans:
        source = str(artifact.get("source"))
        plan_ref = source.rsplit("/", 1)[-1]
        try:
            payload = json.loads(
                (
                    package_root / CHECKPOINT_ARTIFACTS_DIRECTORY / source
                ).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        projection = payload.get("projection") or {}
        client_item_ids = sorted(
            str(item.get("client_item_id"))
            for item in payload.get("items") or []
            if isinstance(item, Mapping) and item.get("client_item_id")
        )
        referenced_batches = [
            batch
            for batch in payload.get("client_batch_ids") or []
            if isinstance(batch, str)
        ]
        mappings.append(
            {
                "source_plan_ref": plan_ref,
                "source_plan_digest": artifact.get("digest"),
                "current_plan_ref": plan_ref,
                "current_plan_digest": None,
                "client_item_ids": client_item_ids,
                "candidate": {
                    "candidate_id": projection.get("candidate_id"),
                    "revision": projection.get("revision"),
                },
                "decision_bindings": list(payload.get("decision_bindings") or []),
                "identity_bindings": list(payload.get("identity_bindings") or []),
                "source_client_batch_ids": referenced_batches,
                "completed_source_batches": [
                    batch for batch in referenced_batches if batch in completed_batches
                ],
                "status": (
                    "completed_do_not_resubmit"
                    if referenced_batches and referenced_batches[0] in completed_batches
                    else "unfinished_submit_through_new_session"
                ),
            }
        )
    return mappings


def unfinished_items(reconciliation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Public unfinished-work rows from the reconciliation (design §5.1).

    ``pending_new_dry_run`` and ``recoverable_new_batch`` are the classifier's
    own "provably unfinished" outputs; they belong in every role packet, not
    only in the host inspection — a resumed team that cannot see them will
    conclude the run while the authorized work is still outstanding.
    """

    rows: list[dict[str, Any]] = []
    for source in ("pending_new_dry_run", "recoverable_new_batch"):
        for item in reconciliation.get(source) or []:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "kind": source,
                    "origin_run_id": item.get("origin_run_id"),
                    "ordinal": item.get("ordinal"),
                    "client_batch_id": item.get("client_batch_id"),
                    "idempotency_key": item.get("idempotency_key"),
                    "mode": item.get("mode"),
                    "detail": item.get("detail"),
                }
            )
    return rows


def next_step_with_pending(
    base_next_step: Any, reconciliation: Mapping[str, Any]
) -> Any:
    """Name the unfinished items in the next step when reconciliation found any.

    The step is a review-first instruction, not an execution order: the host
    summary names the entries so the team verifies successor coverage before
    any rebind or apply.
    """

    pending = unfinished_items(reconciliation)
    if not pending:
        return base_next_step
    named = ", ".join(
        str(item.get("client_batch_id") or item.get("idempotency_key"))
        for item in pending
    )
    return (
        "review pending_items first ("
        + named
        + "): a listed pending attempt is retained history, not by itself "
        "proof its content is still unmaterialized -- first verify the "
        "successful successor receipts, current candidates and actual "
        "coverage for it; what an applied successor already covered stays "
        "history and is not rebuilt, re-approved or replayed, and only "
        "content still missing materialization is rebound: rebind each "
        "remaining plan/client_batch_id/idempotency key to the fresh "
        "session, enter a NEW dry-run, then apply on a clean dry run, "
        "before any production conclusion; the platform does not judge "
        "semantic equivalence -- compare actual receipts and readback"
        + (f"; then {base_next_step}" if isinstance(base_next_step, str) else "")
    )


# The start2 handoff defect (2026-10-05): broadcasting the host-level pending
# text above to every role made Protocol open a Build Session while the
# Task's candidate gate was still closed (the zero-write
# candidate_receipt_required rejection) and handed rebind/dry-run/apply
# duties to the competency-question role.  Each production role instead gets
# only its own agent-package contract's slice of the same continuation;
# pending_items stays shared team state that grants no role a capability.
# Follow-up correction: the gate is whatever the selected Task's Runner
# actually validates.  On the unified-graph route a legacy R2.3 candidate
# receipt does not exist (the Runner forbids the old builder on 009
# candidates), so these texts stay Task-bound and never invent a receipt
# wait from the generic closed-gate rejection.
_PENDING_NEXT_STEP_BY_ROLE = {
    "coordinator": (
        "coordinate the outstanding pending_items inside the existing role "
        "contracts: a listed pending attempt is retained history, not by "
        "itself proof its content is still unmaterialized, so before any "
        "rebind or republish adjudicate from the successful successor "
        "receipts, current candidates and actual coverage -- content an "
        "applied successor already covered stays history and is not "
        "rebuilt, re-approved or replayed, and the team moves to the "
        "genuinely remaining scope. Modeling continues the work through "
        "its direct candidate delivery, Protocol alone performs the "
        "platform rebind, NEW dry-run and apply -- for content still "
        "missing materialization -- through its authorized mechanical "
        "calls behind the candidate/topology gate the selected Task's "
        "Runner validates for this run, and competency-question continues "
        "its stage-appropriate CQ lifecycle; you coordinate and "
        "adjudicate, and still never call a platform write interface or "
        "submit a Modeling Batch yourself"
    ),
    "modeling": (
        "continue the outstanding work through your existing candidate "
        "channel only: check this packet's completed scope and pending facts, "
        "then hand the continuation or corrected candidate to Protocol "
        "through direct candidate delivery; never call a platform Build "
        "Session or Modeling Batch interface yourself"
    ),
    "protocol": (
        "the platform continuation of pending_items -- Build Session "
        "creation, plan/client_batch_id/idempotency-key rebind, a NEW "
        "dry-run, then apply -- runs only through your authorized "
        "mechanical translation calls and only behind the candidate/"
        "topology gate the selected Task's Runner validates for this run: "
        "only a Task that formally advertises the legacy candidate-receipt "
        "contract uses its registered-receipt path, while the unified-graph "
        "route's Runner-validated slot, source-grounded approvals and "
        "topology decision together with Modeling's direct candidate "
        "handoff are that gate, and no extra R2.3 receipt exists to wait "
        "for. A listed pending attempt is retained history, not by itself "
        "proof its content is still unmaterialized: before any rebind, new "
        "identity or NEW dry-run verify the successful successor receipts, "
        "current candidates and actual coverage; what an applied successor "
        "already covered stays history -- do not rebuild, re-approve or "
        "replay it, and do not mint a new identity for it -- and only "
        "content still missing materialization enters the rebind, NEW "
        "dry-run and apply path. The platform does not judge semantic "
        "equivalence: compare actual receipts and readback yourself; this "
        "never bypasses the current plan's own deterministic dry-run/apply, "
        "its source-grounded approvals, or the unknown-write "
        "reconciliation contract. A candidate_receipt_required rejection "
        "only reports the Task's gate still closed: follow the Task's "
        "advertised contract for the real opening path, never invent a "
        "legacy receipt, never treat the gate as open or substitute host "
        "confirmation for the Runner gate, and you make no platform write "
        "while the gate is closed"
    ),
}


def _role_next_step(
    role: str,
    base_next_step: Any,
    pending: list[dict[str, Any]],
    *,
    frozen_pool_restored: bool | None = None,
) -> Any:
    """Role-scoped next step; the global stage step is never a role duty.

    The start2 follow-up (2026-10-05): a checkpoint's
    ``stage_facts.next_step`` is a whole-team materialization sentence (the
    real cp16 says "continue the remaining dry-run correction, translation
    review or apply operations").  Appending it after the correct role
    guidance -- or returning it alone to every role when nothing is pending
    -- re-assigned dry-run/translation/apply duties to Modeling and the
    competency-question role.  Only the host packet keeps the global step as
    its own orchestration summary.  A role's step is its own contract's
    slice when reconciliation found pending work and nothing role-specific
    otherwise; when the global step is a string it rides along only as
    clearly labeled shared team context, never as an instruction the role
    executes.
    """

    if pending:
        if role == "competency-question":
            step = (
                "the frozen pool for this scope is already restored: own the "
                "normal CQ lifecycle and maintain it without re-interviewing, "
                "re-reviewing or re-freezing"
                if frozen_pool_restored
                else "continue your actual CQ stage for this continuation: no "
                "frozen pool is restored for this scope yet, so the normal CQ "
                "lifecycle -- ending in the freeze this scope still needs -- "
                "still runs"
            )
            step += (
                "; pending_items is shared team state and never assigns you "
                "platform rebind, dry-run or apply work"
            )
        else:
            step = _PENDING_NEXT_STEP_BY_ROLE[role]
    else:
        step = None
    if isinstance(base_next_step, str) and base_next_step:
        context = f"shared stage context, not a per-role duty: {base_next_step}"
        step = context if step is None else f"{step}; {context}"
    return step


def build_role_packets(
    manifest: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    plan_mappings: list[dict[str, Any]],
    approvals: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Per-role public continuation packets (design §4.2).

    ``resume_kind`` plus the readable artifact references, completed scope,
    pending items, the forbidden-resubmission list and the next step.  Host
    private material appears only in the host and competency-question packets;
    production roles never see the frozen pool or hidden basis through this
    channel.  No new review roles are introduced.
    """

    stage_facts = manifest.get("stage_facts") or {}
    forbidden = sorted(
        str(item)
        for item in (reconciliation.get("completed_client_batches") or {})
    )
    public_artifacts = [
        str(artifact.get("source"))
        for artifact in manifest.get("artifacts") or []
        if isinstance(artifact, Mapping) and not artifact.get("host_private")
    ]
    private_artifacts = [
        str(artifact.get("source"))
        for artifact in manifest.get("artifacts") or []
        if isinstance(artifact, Mapping) and artifact.get("host_private")
    ]
    handoff_materials = [
        {
            "source": str(artifact.get("source")),
            "digest": artifact.get("digest"),
            "owner": artifact.get("owner"),
            "visible_to": list(artifact.get("visible_to") or []),
        }
        for artifact in _handoff_manifest_entries(manifest)
        if isinstance(artifact, Mapping)
    ]
    pending = unfinished_items(reconciliation)
    base = {
        "resume_kind": str(manifest.get("kind")),
        "checkpoint_id": str(manifest.get("checkpoint_id")),
        "source_run_id": str(manifest.get("source_run_id")),
        "completed_scope": {
            "completed_operations": len(reconciliation.get("completed") or []),
            "completed_client_batch_ids": forbidden,
        },
        "pending_items": list(stage_facts.get("pending") or []) + pending,
        "forbidden_resubmissions": forbidden,
        "next_step": next_step_with_pending(stage_facts.get("next_step"), reconciliation),
        "instructions": [
            "do not rerun the default full-flow opening; continue from the "
            "completed results referenced above",
            "report reused results as part of your own handoff; do not re-interview "
            "or re-review already frozen/approved material",
            *(
                [
                    "pending_items is shared recovery state naming outstanding "
                    "work for the whole team; it grants no role any capability "
                    "beyond its existing contract, and each role acts only "
                    "inside its own contract"
                ]
                if pending
                else []
            ),
        ],
    }
    packets: dict[str, dict[str, Any]] = {}
    for role in ("coordinator", "modeling", "protocol"):
        packets[role] = {
            **base,
            "role": role,
            "next_step": _role_next_step(
                role, stage_facts.get("next_step"), pending
            ),
            "readable_artifacts": public_artifacts,
            "handoff_materials": [
                entry for entry in handoff_materials
                if role in (entry.get("visible_to") or [])
            ],
            "plan_mappings": plan_mappings if role in {"coordinator", "modeling", "protocol"} else [],
            "translation_review": {
                "required": True,
                "note": "the new session must republish plan/client_batch_id/key "
                "and a fresh dry-run; the current Coordinator reviews the new "
                "translation plan through the normal 014 path (S3 auto-migration "
                "is deferred by design)",
            },
        }
    # R3.0-011 host-only contract: the frozen pool rides in the host packet
    # only.  The competency-question packet lists the role's own private/
    # review records (which its role mounts expose) plus the restored public
    # projection; the frozen files themselves stay host-only and unmounted,
    # with the Runner-verified freeze state reduced to a summary without any
    # hidden content.
    frozen_pool_refs = [
        str(artifact.get("source"))
        for artifact in manifest.get("artifacts") or []
        if isinstance(artifact, Mapping)
        and str(artifact.get("source") or "").startswith(f"{CQ_FREEZE_DIRECTORY}/")
    ]
    packets["competency-question"] = {
        **base,
        "role": "competency-question",
        "next_step": _role_next_step(
            "competency-question",
            stage_facts.get("next_step"),
            pending,
            frozen_pool_restored=bool(frozen_pool_refs),
        ),
        "readable_artifacts": public_artifacts
        + [
            source
            for source in private_artifacts
            if source.startswith(("competency-questions/private/", "competency-questions/reviews/"))
        ],
        "handoff_materials": [
            entry for entry in handoff_materials
            if "competency-question" in (entry.get("visible_to") or [])
        ],
        "private_material_note": "own private drafts/reviews/interviews ride only "
        "in this packet and the host's; production roles never see them",
        "frozen_pool": {
            "restored": bool(frozen_pool_refs),
            "note": "the Runner re-validated the restored frozen pool; the pool "
            "itself stays host-only and is never mounted to any Agent; read the "
            "restored public projection mount and continue without re-interviewing "
            "or re-reviewing",
        },
    }
    packets["host"] = {
        **base,
        "role": "host",
        "readable_artifacts": public_artifacts + private_artifacts,
        "handoff_materials": handoff_materials,
        "approvals": approvals,
    }
    packets["host"]["configuration"] = dict(configuration)
    return packets


def write_recovery_files(
    new_run_root: Path,
    *,
    inspection: Mapping[str, Any],
    origin: Mapping[str, Any],
    imports: Mapping[str, Any],
    role_packets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Path]:
    """Write the design §3.2 recovery directory under the new run root."""

    recovery = Path(new_run_root) / RECOVERY_DIRECTORY
    roles = recovery / RECOVERY_ROLES_DIRECTORY
    roles.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, payload in (
        ("inspection.json", inspection),
        ("origin.json", origin),
        ("imports.json", imports),
    ):
        path = recovery / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
        paths[name] = path
    for role, packet in sorted(role_packets.items()):
        path = roles / f"{role}.json"
        path.write_text(
            json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths[f"roles/{role}.json"] = path
    return paths


def restore_checkpoint_artifacts(
    manifest: Mapping[str, Any], source_run_root: Path, new_run_root: Path,
    *, handoff_materials: Any | None = None,
    handoff_actor_id: str = "runner",
) -> dict[str, Any]:
    """Copy packaged artifacts to their original run-relative paths (§4.2).

    Every copy is digest-verified against the manifest; a mismatch is the
    typed ``artifact_changed`` rejection and nothing partial is left behind.
    """

    checkpoint_id = str(manifest.get("checkpoint_id"))
    package_root = checkpoints_root(Path(source_run_root)) / checkpoint_id
    new_run_root = Path(new_run_root)
    restored: list[str] = []
    for artifact in manifest.get("artifacts") or []:
        if not isinstance(artifact, Mapping):
            continue
        source = str(artifact.get("source"))
        side = (
            CHECKPOINT_HOST_PRIVATE_DIRECTORY
            if artifact.get("host_private")
            else CHECKPOINT_ARTIFACTS_DIRECTORY
        )
        snapshot = package_root / side / source
        if not snapshot.is_file():
            raise _reject(
                "checkpoint_incomplete",
                f"packaged artifact {source!r} is missing from the package",
                obj=source,
            )
        if file_digest(snapshot) != artifact.get("digest"):
            raise _reject(
                "artifact_changed",
                f"packaged artifact {source!r} no longer matches its digest",
                obj=source,
                retryable=True,
                retry="re-save the checkpoint from a stable source run",
            )
        destination = new_run_root.joinpath(*source.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            # The freshly prepared run may already hold its own read-only
            # staged initialization for this path (e.g. candidate-gate); the
            # checkpoint's packaged state replaces it wholesale.
            destination.unlink()
        destination.write_bytes(snapshot.read_bytes())
        restored.append(source)
    bindings: list[dict[str, Any]] = []
    material_ids = {
        Path(str(entry.get("source"))).parts[1]
        for entry in _handoff_manifest_entries(manifest)
        if isinstance(entry, Mapping)
        and str(entry.get("source") or "").startswith("handoff-materials/")
        and len(Path(str(entry.get("source"))).parts) >= 3
    }
    for material_id in sorted(material_ids):
        package = Path(new_run_root) / "handoff-materials" / material_id
        manifest_file = package / "manifest.json"
        try:
            raw = manifest_file.read_bytes()
            # HandoffMaterials' manifest.sha256 contract is the raw hex
            # digest (the checkpoint manifest itself uses ``sha256:``).
            original_digest = hashlib.sha256(raw).hexdigest()
            value = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise _reject(
                "checkpoint_incomplete",
                f"restored handoff manifest {material_id!r} is unreadable",
                obj=f"handoff-materials/{material_id}/manifest.json",
                retryable=True,
                retry="re-save the checkpoint from a stable handoff package",
            )
        if not isinstance(value, dict) or value.get("material_id") != material_id:
            raise _reject(
                "material_binding_changed",
                f"restored handoff manifest {material_id!r} has changed identity",
                obj=f"handoff-materials/{material_id}/manifest.json",
                retryable=True,
                retry="republish the material and save a new checkpoint",
            )
        binding = {
            "material_id": material_id,
            "origin_scope_id": value.get("scope_id"),
            "origin_manifest_digest": original_digest,
            "checkpoint_id": manifest.get("checkpoint_id"),
            "source": f"handoff-materials/{material_id}",
        }
        if handoff_materials is not None:
            binder = getattr(handoff_materials, "bind_restored_material", None)
            if not callable(binder):
                raise _reject(
                    "material_binding_changed",
                    "the target handoff store cannot bind a restored material",
                    obj=f"handoff-materials/{material_id}",
                    retryable=True,
                    retry="use a Runner handoff store with restored-material binding support",
                )
            def rebind_path(value: Any) -> Any:
                """Translate only paths rooted in the source run.

                Handoff manifests retain their immutable original provenance.
                The binding written in the restored store may point at the
                equivalent current run root, but an external/virtual alias is
                left untouched and must match an explicitly registered grant.
                """

                if not isinstance(value, str):
                    return value
                path = Path(value)
                try:
                    relative = path.relative_to(Path(source_run_root))
                except ValueError:
                    return value
                return str(Path(new_run_root) / relative)

            current_source_alias = rebind_path(value.get("source_alias"))
            current_source_path = rebind_path(value.get("source_path"))
            try:
                result = binder(
                    material_id,
                    origin_scope_id=value.get("scope_id"),
                    manifest_digest=original_digest,
                    source_alias=current_source_alias,
                    source_path=current_source_path,
                )
            except Exception as exc:
                raise _reject(
                    "material_binding_changed",
                    "the restored material is not authorized for this target run",
                    obj=f"handoff-materials/{material_id}",
                    retryable=True,
                    retry="republish the material through the current recipient channel",
                ) from exc
            binding["target_binding"] = result
        bindings.append(binding)
    return {"restored_artifacts": restored, "handoff_material_bindings": bindings}


def merge_exposure_union(chain_roots: list[Path], new_run_root: Path) -> dict[str, Any]:
    """Exposure provenance is the union across the recovery chain (M32).

    Appends every chain run's ``cq-exposure`` records to the new run's evidence
    file in the same native ``question-exposed-to-production`` shape the Runner
    writes, tagged with the chain run they came from.  A question once shown to
    a production role can therefore never become hidden again in the new
    execution: the recovered Runner re-reads the merged file exactly like its
    own provenance (``reload``-style readers reject any other shape).
    """

    merged: dict[str, set[str]] = {}
    origins: dict[str, set[str]] = {}
    native_lines: list[str] = []
    for run_root in chain_roots:
        path = Path(run_root) / "evidence" / "cq-exposure.jsonl"
        if not path.is_file():
            continue
        run_id = Path(run_root).name
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, Mapping):
                continue
            question_ids = [
                str(item)
                for item in record.get("question_ids") or []
                if isinstance(item, str) and item
            ]
            roles = sorted(
                {
                    str(role)
                    for role in record.get("roles") or []
                    if isinstance(role, str) and role
                }
            )
            if not question_ids or not roles:
                continue
            for question_id in question_ids:
                merged.setdefault(question_id, set()).update(roles)
                origins.setdefault(question_id, set()).add(run_id)
            native_lines.append(
                json.dumps(
                    {
                        "event": "question-exposed-to-production",
                        "question_ids": question_ids,
                        "roles": roles,
                        "reason_code": "permanently_public",
                        "resume_union_source_run": run_id,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    if native_lines:
        evidence_dir = Path(new_run_root) / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        with (evidence_dir / "cq-exposure.jsonl").open("a", encoding="utf-8") as stream:
            for line in native_lines:
                stream.write(line + "\n")
    return {
        "exposed_question_ids": sorted(merged),
        "question_roles": {key: sorted(merged[key]) for key in sorted(merged)},
        "recorded_from_runs": {
            key: sorted(origins[key]) for key in sorted(origins)
        },
        "chain_runs_read": [str(path.name) for path in chain_roots],
    }


def check_resume_submission(
    imports: Mapping[str, Any],
    batch: Mapping[str, Any],
    *,
    plan_ref: str | None,
) -> None:
    """Pre-submit check against the imported completion index (design §5.2).

    The backend keys dedupe per Build Session, so the same key in a new Session
    is a brand-new request; this check is the runner-side barrier that refuses
    a submission whose operation identity was already completed by the origin
    chain.  Same-operation reuse only — equal command text never merges two
    different business operations.
    """

    forbidden = set(imports.get("completed_client_batches") or {})
    client_batch_id = batch.get("client_batch_id")
    if isinstance(client_batch_id, str) and client_batch_id in forbidden:
        raise _reject_for_submission(
            f"client_batch_id {client_batch_id!r} was already completed by the "
            "origin run; resubmitting it in a new session would duplicate the "
            "write (backend idempotency keys are scoped per session)",
        )
    if plan_ref:
        for mapping in imports.get("plan_mappings") or []:
            if not isinstance(mapping, Mapping):
                continue
            if (
                str(mapping.get("source_plan_ref")) == str(plan_ref)
                and mapping.get("status") == "completed_do_not_resubmit"
            ):
                raise _reject_for_submission(
                    f"plan {plan_ref!r} maps to completed origin operations and "
                    "must not be resubmitted",
                )


def _reject_for_submission(detail: str) -> CheckpointError:
    return _reject(
        REASON_COMPLETED_OPERATION_BLOCKED,
        detail,
        obj="submit_modeling_batch",
        phase="resume-submit-check",
        retryable=False,
        retry="submit only operations the reconciliation proved unfinished",
    )


# --- the recovery plan (read-only, reusable before any run root exists) ----------


@dataclass
class RecoveryPlan:
    """Everything ``prepare_from_checkpoint`` needs after read-only checks."""

    manifest: dict[str, Any]
    manifest_digest: str
    source_run_root: Path
    checkpoint_id: str
    new_run_id: str
    chain_roots: list[Path]
    reconciliation: dict[str, Any]
    approvals: dict[str, Any]
    plan_mappings: list[dict[str, Any]]
    role_packets: dict[str, dict[str, Any]]
    inspection: dict[str, Any]
    origin: dict[str, Any]
    imports: dict[str, Any]
    profile_path: Path
    task_path: Path
    scope: dict[str, Any] = field(default_factory=dict)
    workspace_baselines: dict[str, Any] = field(default_factory=dict)
    prep_started_at: float = 0.0
    prep_finished_at: float = 0.0


def _resolve_write_tail_run(
    source_run_root: Path,
    checkpoint_id: str,
    package_digest: str,
    write_tail_run_root: Path | None,
    runs_root: Path,
) -> Path | None:
    """Resolve the host's explicit dual-source write-tail run, fail-closed.

    Returns ``None`` for the ordinary single-source resume (the default
    behavior never changes).  The named tail must itself be a recovery
    continuation whose origin chain contains the package source, and the run
    immediately after the package source must have resumed EXACTLY the
    requested package -- its origin records the same checkpoint id and digest.
    The explicit parameter only extends the reconciled chain; it never
    discovers branches, substitutes a different package, or rewrites a dead
    source.
    """

    if write_tail_run_root is None:
        return None
    tail = Path(write_tail_run_root)
    if (
        not tail.is_dir()
        or tail.resolve() == Path(source_run_root).resolve()
        # The tail must BE a run directory of this runs root -- the CLI
        # composes runs_root / <id> without the host API's run-name regex, so
        # a ../-escaped directory's own origin claims are not boundary proof.
        or tail.resolve().parent != Path(runs_root).resolve()
    ):
        raise _reject(
            REASON_WRITE_TAIL_UNRELATED,
            f"the write-tail run {tail.name!r} is not a distinct continuation "
            "run directory under the same runs root",
            obj=tail.name,
            retryable=False,
            retry="pass the dead continuation run that resumed the package, or "
            "omit --write-tail-run-id for an ordinary single-source resume",
        )
    chain = origin_chain_roots(tail, runs_root)
    names = [run.name for run in chain]
    if source_run_root.name not in names or names[-1] != tail.name:
        raise _reject(
            REASON_WRITE_TAIL_UNRELATED,
            f"the write-tail run {tail.name!r} does not sit on the package "
            f"source {source_run_root.name!r}'s recovery chain",
            obj=tail.name,
            retryable=False,
            retry="name the latest run of the package source's own chain",
        )
    successor = load_origin_record(chain[names.index(source_run_root.name) + 1])
    if (
        not isinstance(successor, Mapping)
        or successor.get("checkpoint_id") != checkpoint_id
        or successor.get("checkpoint_digest") != package_digest
    ):
        raise _reject(
            REASON_WRITE_TAIL_CHECKPOINT_BINDING,
            f"the run after the package source did not verifiably resume "
            f"checkpoint {checkpoint_id!r} of {source_run_root.name!r}",
            obj=tail.name,
            retryable=False,
            retry="resume the package the chain actually bound, or name a "
            "tail whose chain binds this exact package",
        )
    return chain[-1]


def prepare_recovery_plan(
    *,
    source_run_root: Path,
    checkpoint_id: str,
    new_run_id: str,
    repository_root: Path,
    readback: PlatformReadback,
    authorization_reference: str | None = None,
    write_tail_run_root: Path | None = None,
) -> RecoveryPlan:
    """The complete read-only reconciliation; raises typed rejections only.

    Order: package verification -> configuration/compatibility -> source
    writer state -> write tail + platform readback -> classification ->
    approval channel -> plan mapping/packets.  Nothing here creates the new
    run root, writes the source run, or starts anything.

    ``write_tail_run_root`` names the dead continuation run whose post-
    checkpoint writes a dual-source resume must reconcile (the package still
    comes from ``source_run_root``); omitting it keeps the ordinary
    single-source behavior byte-for-byte.
    """

    prep_started_at = time.monotonic()
    source_run_root = Path(source_run_root)
    checkpoint_id = safe_checkpoint_id(checkpoint_id)
    new_run_id = safe_new_run_id(new_run_id)
    repository_root = Path(repository_root)
    manifest = _load_manifest(source_run_root, checkpoint_id)

    if manifest.get("kind") not in CHECKPOINT_KINDS:
        raise _reject(
            "checkpoint_invalid_kind",
            f"unknown checkpoint kind {manifest.get('kind')!r}",
            obj="kind",
        )
    kind = str(manifest.get("kind"))
    if kind == CHECKPOINT_KIND_PRODUCTION_HANDOFF:
        # §4.1/§7: a production_handoff checkpoint continues through
        # independent acceptance continuation (S4), never through production
        # resume; the kind/mode mismatch is itself the accurate error.
        raise _reject(
            REASON_KIND_MODE_MISMATCH,
            "a production_handoff checkpoint continues through independent "
            "acceptance continuation of its frozen batch, not a production "
            "resume of the write path",
            obj="kind",
            retryable=False,
            retry="rerun with --mode acceptance to continue the handoff's "
            "frozen acceptance batch",
        )
    # Verify every packaged digest before anything downstream trusts it.
    _verify_packaged_digests(source_run_root, manifest, checkpoint_id)
    configuration = _require_configuration_identity(manifest)
    # Contract files resolve by recorded identity (design §4.2): the source
    # run's digest-verified snapshot is the strongest record; the repository
    # checkout at the exact recorded id (or its id-prefixed file) is the
    # fallback.
    profile_path, task_path = _resolve_checkpoint_contracts(
        source_run_root, manifest, repository_root
    )

    runs_root = source_run_root.parent
    package_digest = manifest_digest(manifest_path(source_run_root, checkpoint_id))
    tail_run = _resolve_write_tail_run(
        source_run_root, checkpoint_id, package_digest, write_tail_run_root, runs_root
    )
    chain_roots = origin_chain_roots(tail_run or source_run_root, runs_root)
    if (runs_root / new_run_id).exists():
        raise _reject(
            "resume_new_run_exists",
            f"the new run directory {new_run_id!r} already exists; a resume "
            "never overwrites an existing run",
            obj="new_run_id",
            retryable=False,
            retry="choose a fresh new-run id",
        )

    tail = read_write_tail(chain_roots)
    session_ids: set[str] = set()
    for run in tail.values():
        for intent in run.get("intents") or []:
            session_id = intent.get("session_id")
            if isinstance(session_id, str) and session_id:
                session_ids.add(session_id)

    writer = source_writer_report(source_run_root, readback, sorted(session_ids))
    writer["chain_writer_lock"] = chain_writer_lock_report(
        source_run_root, manifest, runs_root
    )
    if writer["chain_writer_lock"]["verdict"] == "writer_process_exited":
        # Audit-only verdict: the stale state.json claim stays visible in
        # ``state_json_may_be_live_writer``, and the settlement rests on the
        # chain lock record it names.
        writer["verdict"] = "writer_process_exited"
    writer["source_settlement"] = source_settlement_report(
        source_run_root, runs_root, readback, sorted(session_ids)
    )
    if writer["source_settlement"]["verdict"] == "writer_process_exited":
        writer["verdict"] = "writer_process_exited"
    if not source_writer_settles_recovery(writer):
        obj, retry = source_active_evidence(writer, source_run_root)
        raise _reject(
            REASON_SOURCE_ACTIVE,
            "the source run's own state.json still reports a possibly-live "
            "writer; resume does not run alongside the original writer",
            obj=obj,
            retryable=True,
            retry=retry,
        )

    tail_writer: dict[str, Any] | None = None
    if tail_run is not None:
        # The same §5.2 writer-death evidence, applied to the named tail run:
        # a possibly-live continuation writer keeps the resume refused, so an
        # explicit tail never widens the writer gate.
        tail_writer = source_writer_report(tail_run, readback, sorted(session_ids))
        tail_writer["chain_writer_lock"] = chain_writer_lock_report(
            tail_run, manifest, runs_root
        )
        if tail_writer["chain_writer_lock"]["verdict"] == "writer_process_exited":
            tail_writer["verdict"] = "writer_process_exited"
        tail_writer["source_settlement"] = source_settlement_report(
            tail_run, runs_root, readback, sorted(session_ids)
        )
        if tail_writer["source_settlement"]["verdict"] == "writer_process_exited":
            tail_writer["verdict"] = "writer_process_exited"
        if not source_writer_settles_recovery(tail_writer):
            obj, retry = source_active_evidence(tail_writer, tail_run)
            raise _reject(
                REASON_SOURCE_ACTIVE,
                f"the write-tail run {tail_run.name!r} still reports a "
                "possibly-live writer; resume does not run alongside the "
                "continuation that owns the unreconciled writes",
                obj=obj,
                retryable=True,
                retry=retry,
            )

    bindings = production_resume_bindings(manifest)
    if bindings is None:
        # Shared with inspect's availability judgment: the hard gate itself
        # stays — a manifest without a reattachable Project/Ontology identity
        # never starts a production resume.
        raise _reject(
            "checkpoint_incomplete",
            "the checkpoint records no Project/Ontology platform bindings to "
            "reattach",
            obj="platform_bindings",
            retryable=False,
            retry="re-save the checkpoint from a run that had bound its scope",
        )
    project_id = bindings["project_id"]
    ontology_ids = bindings["ontology_ids"]

    reconciliation = reconcile_write_tail(
        chain_roots, tail, readback, ontology_ids=ontology_ids
    )
    if reconciliation["scope_drift"]:
        raise _reject(
            REASON_SCOPE_DRIFT,
            f"{len(reconciliation['scope_drift'])} platform write(s) on the "
            "recovery-bound ontologies cannot be attributed to the recovery "
            "chain; listing them is the report, not auto-claiming them",
            obj="platform_batches",
            retryable=True,
            retry="attribute or resolve the drift through the owning session, "
            "then retry the resume",
        )
    if reconciliation["blocked"]:
        first = reconciliation["blocked"][0]
        raise _reject(
            REASON_WRITE_UNRECONCILED,
            f"{len(reconciliation['blocked'])} chain operation(s) are unknown or "
            f"still in flight (first: {first.get('idempotency_key')}); the write "
            "gate stays closed and unknown adjudication hints cannot release it",
            obj=str(first.get("idempotency_key")),
            retryable=True,
            retry="resolve the unknown writes with the existing platform "
            "recovery/diagnosis channels, then retry",
        )

    approvals = validate_business_approvals(manifest, source_run_root)
    if approvals.get("invalidated"):
        first = approvals["invalidated"][0]
        raise _reject(
            REASON_APPROVAL_BINDING_CHANGED,
            f"{len(approvals['invalidated'])} imported approval(s) failed the "
            f"source-channel check (first: {first.get('target_id')}); affected "
            "items wait for clarification and the source run stays untouched",
            obj=str(first.get("target_id")),
            retryable=True,
            retry="correct the approval source (fresh decision in the source "
            "run, then a new checkpoint) or continue without that approval",
        )

    plan_mappings = build_plan_mappings(manifest, source_run_root, reconciliation)
    role_packets = build_role_packets(
        manifest, reconciliation, plan_mappings, approvals, configuration
    )
    prep_finished_at = time.monotonic()
    prep_seconds = round(prep_finished_at - prep_started_at, 3)
    over_budget = prep_seconds > PREP_BUDGET_SECONDS
    unfinished = len(reconciliation["pending_new_dry_run"]) + len(
        reconciliation["recoverable_new_batch"]
    )
    inspection = {
        "schema_version": RECOVERY_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "source_run_id": manifest.get("source_run_id"),
        "root_run_id": manifest.get("root_run_id") or manifest.get("source_run_id"),
        "kind": kind,
        "manifest_digest": package_digest,
        "reconciliation": {
            "chain_runs": [str(path.name) for path in chain_roots],
            "completed_operations": len(reconciliation["completed"]),
            "pending_new_dry_run": reconciliation["pending_new_dry_run"],
            "recoverable_new_batch": reconciliation["recoverable_new_batch"],
            "readback": reconciliation["readback_counters"],
            "endpoints": {
                "session_batches": LIST_PAGE_ENDPOINT + " (cursor, limit<=100)",
                "ontology_batches": ONTOLOGY_LIST_PAGE_ENDPOINT + " (cursor, limit<=100)",
                "batch_detail": BATCH_DETAIL_ENDPOINT + " (content_hash + all attempts)",
                "note": "truncated convenience views (platform_state.modeling_batches, "
                "session-detail modeling_batches) are never reconciliation sources",
            },
        },
        "source_writer": writer,
        "prep_timing": {
            "prep_seconds": prep_seconds,
            "budget_seconds": PREP_BUDGET_SECONDS,
            "over_budget": over_budget,
            "unfinished_items": unfinished,
            "blockers": (
                [
                    {
                        "reason": REASON_WRITE_UNRECONCILED,
                        "detail": "blocked operations keep the gate closed",
                    }
                ]
                if reconciliation["blocked"]
                else []
            ),
            "note": "reconciliation counts into the 20-minute budget from user "
            "authorization; over budget reports blockers and requests a longer "
            "explicit preparation window without relaxing any gate",
        },
        "accounting": {
            "semantic_starts": 1,
            "kind": "production_resume",
            "authorization_reference": authorization_reference,
            "platform_hard_gate": False,
            "note": "a cross-process production resume is one fresh semantic "
            "start recorded by the host; no platform count hard-gate exists "
            "(save/inspect/readonly reads consume none)",
        },
        "delivery_segments": dict(CHECKPOINT_DELIVERY_SEGMENTS),
    }
    if tail_run is not None:
        inspection["write_tail"] = {
            "run_id": tail_run.name,
            "checkpoint_source_run_id": source_run_root.name,
            "writer": tail_writer,
            "note": "explicit dual-source resume: the package identity comes "
            "from checkpoint_source_run_id, while the write chain, completion "
            "index and writer-death gates follow this tail run through the "
            "full origin chain",
        }
    origin = {
        "schema_version": RECOVERY_SCHEMA,
        "source_run_id": (
            tail_run.name if tail_run is not None else manifest.get("source_run_id")
        ),
        "root_run_id": manifest.get("root_run_id") or manifest.get("source_run_id"),
        "checkpoint_id": checkpoint_id,
        "checkpoint_kind": kind,
        "checkpoint_digest": inspection["manifest_digest"],
        "new_run_id": new_run_id,
        "authorization_reference": authorization_reference,
        "created_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "task_id": configuration.get("task_id"),
            "profile_id": configuration.get("profile_id"),
            "model_profile_id": configuration.get("model_profile_id"),
            "configuration_files": list(configuration.get("configuration_files") or []),
            "narrow_fixes": list(configuration.get("narrow_fixes") or []),
            "contract_check": "profile/task resolved by recorded identity and "
            "digest-verified package; schema-compatible",
        },
        "source_writer": {
            "state_json_status": writer["state_json_status"],
            "state_json_may_be_live_writer": writer["state_json_may_be_live_writer"],
            "verdict": writer["verdict"],
            "chain_writer_lock": writer["chain_writer_lock"],
            "source_settlement": writer["source_settlement"],
            "platform_sessions": writer["platform_sessions"],
        },
    }
    if tail_run is not None:
        # Dual-source provenance: the write chain's latest tail is the run the
        # next resume continues from, while the package source stays recorded
        # separately so the chain and the package identity never blur.
        origin["checkpoint_source_run_id"] = source_run_root.name
    imports = {
        "schema_version": RECOVERY_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "recovered_artifacts": [
            {
                "source": artifact.get("source"),
                "digest": artifact.get("digest"),
                "owner": artifact.get("owner"),
                "host_private": bool(artifact.get("host_private")),
            }
            for artifact in manifest.get("artifacts") or []
            if isinstance(artifact, Mapping)
        ],
        "business_approvals": approvals,
        "completed_operations": [
            entry.index_entry() for entry in reconciliation["completed"]
        ],
        "completed_client_batches": dict(reconciliation["completed_client_batches"]),
        "plan_mappings": plan_mappings,
        "identity_mappings": {
            "sessions": {
                session_id: session_id for session_id in sorted(session_ids)
            },
            "note": "inherited history stays bound to the original sessions; the "
            "new session identity is appended when the new run creates it",
        },
        "issues": {
            "original_issues": "remain history in the source run; a new thread "
            "that must wait opens a NEW bound issue instead of faking a resume "
            "ack on the old one",
        },
        "transport": {
            "note": "fresh Transport/terminal/deadline in the new run; the old "
            "delivery queue is never replayed and old completed reports are not "
            "imported as new terminal reports",
        },
        "validators": {
            "note": "staged gates/validators are recomputed from the restored "
            "artifacts; boolean gate-open states are never restored",
        },
    }
    scope = {
        "mode": "checkpoint",
        "project_id": project_id,
        "ontology_ids": ontology_ids,
        "root_run_id": str(manifest.get("root_run_id") or manifest.get("source_run_id")),
    }
    return RecoveryPlan(
        manifest=manifest,
        manifest_digest=inspection["manifest_digest"],
        source_run_root=source_run_root,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        chain_roots=chain_roots,
        reconciliation=reconciliation,
        approvals=approvals,
        plan_mappings=plan_mappings,
        role_packets=role_packets,
        inspection=inspection,
        origin=origin,
        imports=imports,
        profile_path=profile_path,
        task_path=task_path,
        scope=scope,
        prep_started_at=prep_started_at,
        prep_finished_at=prep_finished_at,
    )


# --- S4: acceptance-only continuation from a production_handoff checkpoint -------


_PUBLISHED_HANDOFF_SOURCE = "acceptance-v3/production-handoff.json"
_ATTEMPT_PATTERN = re.compile(r"^attempt-(\d{4})$")


def _acceptance_reject(code: str, detail: str, *, obj: str, **kwargs: Any) -> CheckpointError:
    kwargs.setdefault("retryable", False)
    return _reject(code, detail, obj=obj, phase="checkpoint-resume-acceptance", **kwargs)


def prior_continuation_roots(runs_root: Path, source_run_id: str) -> list[Path]:
    """Output roots of earlier acceptance continuations of this source run.

    Each S4 run records ``recovery/origin.json`` with
    ``kind=acceptance_continuation`` and the source run id at output-root
    creation, so chained continuations stay discoverable and attempt ids stay
    unique across them without touching the source run.
    """

    roots: list[Path] = []
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return roots
    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir() or entry.is_symlink() or entry.name == source_run_id:
            continue
        origin = load_origin_record(entry)
        if (
            isinstance(origin, dict)
            and origin.get("kind") == "acceptance_continuation"
            and origin.get("source_run_id") == source_run_id
        ):
            roots.append(entry)
    return roots


def attempt_directories(report_roots: list[Path], batch_id: str) -> dict[str, Path]:
    """Every existing ``attempt-NNNN`` directory for one batch across roots."""

    found: dict[str, Path] = {}
    for root in report_roots:
        reports = Path(root) / "acceptance-v3" / "reports" / batch_id
        if not reports.is_dir():
            continue
        for entry in sorted(reports.iterdir()):
            if entry.is_dir() and not entry.is_symlink() and _ATTEMPT_PATTERN.fullmatch(entry.name):
                found.setdefault(entry.name, entry)
    return found


def next_acceptance_attempt(report_roots: list[Path], batch_id: str) -> str:
    """The next free ``attempt-NNNN`` across the source run and continuations.

    Mirrors ``TeamRunner._cq_next_acceptance_attempt``: a re-acceptance never
    reuses -- let alone overwrites -- a published attempt directory.
    """

    existing = set(attempt_directories(report_roots, batch_id))
    ordinal = 1
    while f"attempt-{ordinal:04d}" in existing:
        ordinal += 1
    return f"attempt-{ordinal:04d}"


def find_complete_pass_report(
    report_roots: list[Path], batch_id: str, freeze_digest: str,
    *, question_visibility: str = "hidden", question_ids: list[str] | None = None,
) -> tuple[dict[str, Any], Path] | None:
    """A complete, usable PASS report for this exact batch and freeze (M34).

    Only a published ``batch-report.json`` bound to the same batch id and
    freeze digest whose full-denominator verdict recomputes as a full pass
    counts; a partial or failed report is never promoted and stays where it
    is (its presence simply means this continuation re-executes a new
    attempt).
    """

    attempts = attempt_directories(report_roots, batch_id)
    for name in sorted(attempts, reverse=True):
        path = attempts[name] / "batch-report.json"
        if not path.is_file() or path.is_symlink():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict):
            continue
        if report.get("batch_id") != batch_id or report.get("freeze_digest") != freeze_digest:
            continue
        selection = report.get("question_selection", {"visibility": "hidden"})
        if not isinstance(selection, dict) or selection.get("visibility") != question_visibility:
            continue
        selected_ids = selection.get("question_ids", [])
        if not isinstance(selected_ids, list) or any(
            not isinstance(item, str) for item in selected_ids
        ):
            continue
        executed = report.get("executed_question_ids", [])
        if question_ids is not None and (
            set(executed) != set(question_ids)
            or (question_visibility == "public"
                and set(selected_ids) != set(question_ids))
        ):
            continue
        if report.get("full_pass") is True and batch_report_is_full_pass(report):
            return report, path
    return None


def _settled_handoff_evidence(handoff: Mapping[str, Any]) -> None:
    """The v012 settled read-only evidence fields (same rule as acceptance)."""

    unknown_writes = handoff.get("unknown_writes")
    if (
        handoff.get("write_phase") != "read-only"
        or (isinstance(unknown_writes, list) and unknown_writes)
        or handoff.get("ready") is not True
        or handoff.get("pending_writes") is not False
    ):
        raise _acceptance_reject(
            REASON_WRITE_UNRECONCILED,
            "the production handoff is not a settled read-only handoff "
            "(unknown writes or a non read-only phase)",
            obj=_PUBLISHED_HANDOFF_SOURCE,
            retryable=True,
            retry="settle or reconcile the outstanding writes through the "
            "existing reconciliation channels, then retry",
        )


def _revalidate_frozen_pool(
    source_run_root: Path, handoff: Mapping[str, Any]
) -> tuple[dict[str, Any], Path]:
    """Reload the frozen pool from the source run and re-bind it (§7).

    The handoff binds the pool by batch id and snapshot digest, never by file
    name (the Runner stores snapshots as ``freeze-NNNN.json`` while the
    handoff's ``freeze_id`` is the batch id), so every stored snapshot is
    rebuilt through :func:`reload_frozen_pool` and the one whose recomputed
    digest and batch match the handoff is adopted.  A post-freeze edit, or a
    digest no stored snapshot reproduces, is the typed
    ``acceptance_binding_changed`` refusal -- the continuation never freezes a
    different pool than the one the handoff delivered.
    """

    batch_id = handoff.get("batch_id")
    freeze_digest = handoff.get("freeze_digest")
    if not isinstance(batch_id, str) or not batch_id or not isinstance(
        freeze_digest, str
    ) or not freeze_digest:
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            "the production handoff names no frozen pool",
            obj="freeze_id",
        )
    frozen_dir = Path(source_run_root) / "competency-questions" / "frozen"
    matches: list[tuple[dict[str, Any], Path]] = []
    failures: list[str] = []
    if frozen_dir.is_dir():
        for entry in sorted(frozen_dir.iterdir()):
            if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json":
                continue
            try:
                raw = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                failures.append("unreadable")
                continue
            try:
                freeze = reload_frozen_pool(raw)
            except CQContractError as exc:
                # Only the typed code is retained: the reload detail may quote
                # frozen material, and rejections never carry private content
                # (§8).
                failures.append(str(exc.reason_code))
                continue
            if (
                freeze.get("batch_id") == batch_id
                and freeze.get("snapshot_digest") == freeze_digest
            ):
                matches.append((freeze, entry))
    if not matches:
        detail = (
            f"the frozen pool bound by the handoff failed re-validation "
            f"({failures[0]})"
            if failures
            else "no frozen pool matching the handoff's batch/freeze digest "
            "re-validates in the source run"
        )
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            detail,
            obj="freeze_id",
        )
    return matches[0]


@dataclass
class AcceptanceContinuation:
    """Everything the S4 entry needs after its read-only re-verification."""

    manifest: dict[str, Any]
    manifest_digest: str
    source_run_root: Path
    checkpoint_id: str
    new_run_id: str
    root_run_id: str
    chain_roots: list[Path]
    prior_output_roots: list[Path]
    handoff: dict[str, Any]
    handoff_digest: str
    freeze: dict[str, Any]
    freeze_file: Path
    freeze_id: str
    freeze_digest: str
    batch_id: str
    attempt_id: str
    prior_attempts: list[str]
    complete_report: dict[str, Any] | None
    writer: dict[str, Any]
    inspection: dict[str, Any]
    origin: dict[str, Any]
    prep_started_at: float = 0.0
    prep_finished_at: float = 0.0
    complete_report_path: Path | None = None

    @property
    def report_roots(self) -> list[Path]:
        return [self.source_run_root, *self.prior_output_roots]


def prepare_acceptance_continuation(
    *,
    source_run_root: Path,
    checkpoint_id: str,
    new_run_id: str,
    readback: PlatformReadback,
    authorization_reference: str | None = None,
    question_visibility: str = "hidden",
    live_source_request_id: str | None = None,
) -> AcceptanceContinuation:
    """Design §7 paragraph 1: the read-only S4 entry verification.

    Only a COMPLETE ``production_handoff`` checkpoint can continue: the
    packaged handoff must still equal the run's published handoff, the frozen
    pool must re-validate under the recorded digest, the full recovery-chain
    write tail must be closed clean with no unknown/partial/applying/
    recovering writes, and the source writer must be stopped.  Any drift is
    the typed ``acceptance_binding_changed`` refusal; nothing here writes the
    source run, wakes a producer, or starts a production thread.
    """

    prep_started_at = time.monotonic()
    source_run_root = Path(source_run_root)
    checkpoint_id = safe_checkpoint_id(checkpoint_id)
    new_run_id = safe_new_run_id(new_run_id)
    manifest = _load_manifest(source_run_root, checkpoint_id)
    if manifest.get("kind") != CHECKPOINT_KIND_PRODUCTION_HANDOFF:
        raise _acceptance_reject(
            REASON_KIND_MODE_MISMATCH,
            f"--mode acceptance continues a production_handoff checkpoint, not "
            f"{manifest.get('kind')!r}",
            obj="kind",
            retry="use --mode production for the pre-handoff kinds",
        )
    _verify_packaged_digests(
        source_run_root, manifest, checkpoint_id, phase="checkpoint-resume-acceptance"
    )
    runs_root = source_run_root.parent
    if (runs_root / new_run_id).exists():
        raise _reject(
            "resume_new_run_exists",
            f"the new run directory {new_run_id!r} already exists; a "
            "continuation never overwrites an existing run",
            obj="new_run_id",
            phase="checkpoint-resume-acceptance",
            retryable=False,
            retry="choose a fresh new-run id",
        )

    chain_roots = origin_chain_roots(source_run_root, runs_root)
    tail = read_write_tail(chain_roots)
    session_ids: set[str] = set()
    for run in tail.values():
        for intent in run.get("intents") or []:
            session_id = intent.get("session_id")
            if isinstance(session_id, str) and session_id:
                session_ids.add(session_id)
    writer = source_writer_report(source_run_root, readback, sorted(session_ids))
    writer["chain_writer_lock"] = chain_writer_lock_report(
        source_run_root, manifest, runs_root
    )
    if writer["chain_writer_lock"]["verdict"] == "writer_process_exited":
        writer["verdict"] = "writer_process_exited"
    writer["source_settlement"] = source_settlement_report(
        source_run_root, runs_root, readback, sorted(session_ids)
    )
    if writer["source_settlement"]["verdict"] == "writer_process_exited":
        writer["verdict"] = "writer_process_exited"
    if not source_writer_settles_recovery(writer) and live_source_request_id:
        writer["live_source_seal"] = source_safe_for_acceptance(source_run_root, readback, live_source_request_id,
                                                               str(manifest.get("root_run_id") or manifest.get("source_run_id")))
    if not source_writer_settles_recovery(writer) and not writer.get("live_source_seal"):
        obj, retry = source_active_evidence(writer, source_run_root)
        raise _acceptance_reject(
            REASON_SOURCE_ACTIVE,
            "the source run's own state.json still reports a possibly-live "
            "writer; acceptance continuation does not run alongside the "
            "production writer",
            obj=obj,
            retryable=True,
            retry=retry,
        )

    # The packaged handoff must still equal the run's published handoff: the
    # package side is digest-verified above, the published side is compared
    # payload-for-payload now (M35: the acceptance never binds a drifted or
    # replaced handoff, and never fixes the model itself).
    package_root = checkpoints_root(source_run_root) / checkpoint_id
    packaged_path = (
        package_root / CHECKPOINT_HOST_PRIVATE_DIRECTORY / _PUBLISHED_HANDOFF_SOURCE
    )
    published_path = source_run_root / _PUBLISHED_HANDOFF_SOURCE
    if not published_path.is_file() or published_path.is_symlink():
        raise _acceptance_reject(
            "checkpoint_incomplete",
            "the source run has no published production handoff to continue",
            obj=_PUBLISHED_HANDOFF_SOURCE,
        )
    try:
        packaged_handoff = json.loads(packaged_path.read_text(encoding="utf-8"))
        handoff = json.loads(published_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            "the packaged or published production handoff is unreadable",
            obj=_PUBLISHED_HANDOFF_SOURCE,
        ) from exc
    if packaged_handoff != handoff:
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            "the checkpoint's packaged handoff no longer equals the run's "
            "published production handoff",
            obj=_PUBLISHED_HANDOFF_SOURCE,
        )
    if handoff.get("schema_version") != "r3-0-012-production-handoff/v1":
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            "the published production handoff carries an unknown schema",
            obj=_PUBLISHED_HANDOFF_SOURCE,
        )
    if handoff.get("run_id") != manifest.get("source_run_id"):
        raise _acceptance_reject(
            REASON_ACCEPTANCE_BINDING_CHANGED,
            "the published production handoff is not bound to this source run",
            obj="run_id",
        )
    _settled_handoff_evidence(handoff)
    handoff_digest = file_digest(published_path)
    freeze, freeze_file = _revalidate_frozen_pool(source_run_root, handoff)
    batch_id = str(freeze["batch_id"])
    freeze_id = str(handoff.get("freeze_id") or batch_id)
    freeze_digest = str(freeze["snapshot_digest"])

    scope = handoff.get("scope_binding")
    ontology_ids = scope.get("ontology_ids") if isinstance(scope, dict) else None
    if (
        not isinstance(scope, dict)
        or not isinstance(scope.get("project_id"), str)
        or not scope.get("project_id")
        or not isinstance(ontology_ids, list)
        or not any(isinstance(item, str) and item for item in ontology_ids)
    ):
        raise _acceptance_reject(
            "checkpoint_incomplete",
            "the production handoff lists no authorized Ontology to re-verify "
            "against",
            obj="scope_binding",
        )
    ontology_ids = [str(item) for item in ontology_ids if isinstance(item, str) and item]

    reconciliation = reconcile_write_tail(
        chain_roots, tail, readback, ontology_ids=ontology_ids
    )
    if reconciliation["scope_drift"]:
        raise _acceptance_reject(
            REASON_SCOPE_DRIFT,
            f"{len(reconciliation['scope_drift'])} platform write(s) on the "
            "acceptance-bound ontologies cannot be attributed to the recovery "
            "chain",
            obj="platform_batches",
            retryable=True,
            retry="attribute or resolve the drift through the owning session, "
            "then retry the continuation",
        )
    if reconciliation["blocked"]:
        first = reconciliation["blocked"][0]
        raise _acceptance_reject(
            REASON_WRITE_UNRECONCILED,
            f"{len(reconciliation['blocked'])} chain operation(s) are unknown or "
            f"still in flight (first: {first.get('idempotency_key')}); the write "
            "gate must be closed clean before acceptance continues",
            obj=str(first.get("idempotency_key")),
            retryable=True,
            retry="resolve the unknown writes with the existing platform "
            "recovery/diagnosis channels, then retry",
        )

    prior_output_roots = prior_continuation_roots(runs_root, source_run_root.name)
    report_roots = [source_run_root, *prior_output_roots]
    prior_attempts = sorted(attempt_directories(report_roots, batch_id))
    attempt_id = next_acceptance_attempt(report_roots, batch_id)
    if question_visibility not in {"hidden", "public"}:
        raise ValueError("question_visibility must be hidden or public")
    selected_ids = [
        str(question["question_id"]) for question in freeze["questions"]
        if question.get("visibility") == question_visibility
    ]
    complete = find_complete_pass_report(
        report_roots, batch_id, freeze_digest,
        question_visibility=question_visibility, question_ids=selected_ids,
    )
    complete_report = complete[0] if complete else None
    complete_report_path = complete[1] if complete else None

    prep_finished_at = time.monotonic()
    prep_seconds = round(prep_finished_at - prep_started_at, 3)
    root_run_id = str(manifest.get("root_run_id") or manifest.get("source_run_id"))
    inspection = {
        "schema_version": RECOVERY_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "source_run_id": manifest.get("source_run_id"),
        "root_run_id": root_run_id,
        "kind": "acceptance_continuation",
        "manifest_digest": manifest_digest(manifest_path(source_run_root, checkpoint_id)),
        "handoff": {
            "freeze_id": freeze_id,
            "freeze_digest": freeze_digest,
            "batch_id": batch_id,
            "published_digest": handoff_digest,
            "write_phase": handoff.get("write_phase"),
            "acceptance_attempt_id": handoff.get("acceptance_attempt_id"),
            "acceptance_target": handoff.get("acceptance_target"),
        },
        "frozen_pool": {
            "revalidated": True,
            "source_file": freeze_file.relative_to(source_run_root).as_posix(),
            "question_count": len(freeze.get("questions") or []),
            "hidden_question_count": sum(
                1
                for question in freeze.get("questions") or []
                if isinstance(question, Mapping)
                and question.get("visibility") == "hidden"
            ),
        },
        "attempts": {
            "new_attempt_id": attempt_id,
            "prior_attempts": prior_attempts,
            "prior_continuation_runs": [path.name for path in prior_output_roots],
        },
        "complete_report": (
            None
            if complete_report is None
            else {
                "batch_id": complete_report.get("batch_id"),
                "freeze_digest": complete_report.get("freeze_digest"),
                "full_pass": True,
                "report_path": str(complete_report_path),
                "note": "a complete usable PASS report exists; this continuation "
                "verifies and closes only, with no model re-call",
            }
        ),
        "source_writer": writer,
        "reconciliation": {
            "chain_runs": [str(path.name) for path in chain_roots],
            "blocked_operations": len(reconciliation["blocked"]),
            "readback": reconciliation["readback_counters"],
        },
        "prep_timing": {
            "prep_seconds": prep_seconds,
            "budget_seconds": PREP_BUDGET_SECONDS,
            "over_budget": prep_seconds > PREP_BUDGET_SECONDS,
            "note": "preparation (re-verification) counts into the 20-minute "
            "budget from user authorization; acceptance execution time is "
            "reported separately in the closing record",
        },
        "accounting": {
            "semantic_starts": 0,
            "consumes_semantic_start": False,
            "kind": "acceptance_continuation",
            "authorization_reference": authorization_reference,
            "platform_hard_gate": False,
            "note": "acceptance-only continuation consumes no modeling start; "
            "the host records an independent attempt linked to the source run",
        },
        "delivery_segments": dict(CHECKPOINT_DELIVERY_SEGMENTS),
    }
    if question_visibility == "public":
        inspection["question_selection"] = {
            "visibility": "public", "question_ids": selected_ids,
        }
    origin = {
        "schema_version": RECOVERY_SCHEMA,
        "kind": "acceptance_continuation",
        "source_run_id": manifest.get("source_run_id"),
        "root_run_id": root_run_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_kind": manifest.get("kind"),
        "checkpoint_digest": inspection["manifest_digest"],
        "new_run_id": new_run_id,
        "batch_id": batch_id,
        "freeze_id": freeze_id,
        "freeze_digest": freeze_digest,
        "handoff_digest": handoff_digest,
        "authorization_reference": authorization_reference,
        "created_at": datetime.now(UTC).isoformat(),
        "source_writer": {
            "state_json_status": writer["state_json_status"],
        },
    }
    return AcceptanceContinuation(
        manifest=manifest,
        manifest_digest=inspection["manifest_digest"],
        source_run_root=source_run_root,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        root_run_id=root_run_id,
        chain_roots=chain_roots,
        prior_output_roots=prior_output_roots,
        handoff=handoff,
        handoff_digest=handoff_digest,
        freeze=freeze,
        freeze_file=freeze_file,
        freeze_id=freeze_id,
        freeze_digest=freeze_digest,
        batch_id=batch_id,
        attempt_id=attempt_id,
        prior_attempts=prior_attempts,
        complete_report=complete_report,
        complete_report_path=complete_report_path,
        writer=writer,
        inspection=inspection,
        origin=origin,
        prep_started_at=prep_started_at,
        prep_finished_at=prep_finished_at,
    )


def write_acceptance_origin(continuation: AcceptanceContinuation, output_root: Path) -> Path:
    """Create the output run root and record its recovery origin (§7).

    The origin lands before any execution, so a continuation that crashes
    mid-flight still leaves the machine-checkable reference to its source run
    and checkpoint, and later continuations can discover it.
    """

    recovery = Path(output_root) / RECOVERY_DIRECTORY
    recovery.mkdir(parents=True, exist_ok=True)
    os.chmod(recovery, 0o700)
    path = recovery / "origin.json"
    path.write_text(
        json.dumps(continuation.origin, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return path


def acceptance_continuation_report(source_root: Path, output_root: Path) -> Path:
    """Resolve a closed S4 report without copying or rewriting any source evidence."""
    if output_root.is_symlink():
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "continuation root changed", obj=output_root.name)
    origin = load_origin_record(output_root) or {}
    closing = json.loads((output_root / RECOVERY_DIRECTORY / ACCEPTANCE_CONTINUATION_RECORD).read_text())
    handoff = source_root / _PUBLISHED_HANDOFF_SOURCE
    if (origin.get("kind") != "acceptance_continuation"
            or origin.get("source_run_id") != source_root.name
            or origin.get("new_run_id") != output_root.name
            or origin.get("handoff_digest") != file_digest(handoff)
            or closing.get("source_run_id") != source_root.name
            or closing.get("new_run_id") != output_root.name
            or closing.get("report_published") is not True):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED,
                                 "closed continuation is not bound to this source", obj=output_root.name)
    checkpoint = str(origin.get("checkpoint_id", ""))
    if origin.get("checkpoint_digest") != manifest_digest(manifest_path(source_root, checkpoint)):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "source checkpoint changed", obj=checkpoint)
    batch, attempt = closing.get("batch_id"), closing.get("attempt_id")
    if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)
               for value in (batch, attempt)):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "continuation report identity is invalid", obj=output_root.name)
    report_path = output_root / "acceptance-v3" / "reports" / batch / attempt / "batch-report.json"
    if report_path.is_symlink() or not report_path.resolve().is_relative_to(output_root.resolve()):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "continuation report path changed", obj=output_root.name)
    report = json.loads(report_path.read_text())
    if (report.get("run_id") != source_root.name or report.get("batch_id") != origin.get("batch_id")
            or report.get("freeze_digest") != origin.get("freeze_digest")
            or report.get("sessions", {}).get("cleanup", {}).get("tasks_closed") is not True):
        raise _acceptance_reject(REASON_ACCEPTANCE_BINDING_CHANGED, "continuation task/report is not sealed", obj=output_root.name)
    return report_path


def write_acceptance_continuation_record(
    output_root: Path, payload: Mapping[str, Any]
) -> Path:
    """Write the host closing record (design §7 paragraph 3).

    The record captures the continuation's final state -- success, failure or
    a refusal after start -- because the original Delivery/Runner process is
    gone and nothing is ever posted to its dead FIFO.  It is written under the
    new output root only; the source run's own failure classification stays
    exactly as it was.
    """

    recovery = Path(output_root) / RECOVERY_DIRECTORY
    recovery.mkdir(parents=True, exist_ok=True)
    path = recovery / ACCEPTANCE_CONTINUATION_RECORD
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return path


__all__ = [
    "ACCEPTANCE_CONTINUATION_RECORD",
    "ACCEPTANCE_CONTINUATION_SCHEMA",
    "APPLY_MODES",
    "AcceptanceContinuation",
    "BATCH_DETAIL_ENDPOINT",
    "CHECKPOINT_KIND_PRODUCTION_HANDOFF",
    "CheckpointError",
    "CompletedOperation",
    "LIST_PAGE_ENDPOINT",
    "ONTOLOGY_LIST_PAGE_ENDPOINT",
    "PlatformReadback",
    "PREP_BUDGET_SECONDS",
    "REASON_ACCEPTANCE_BINDING_CHANGED",
    "REASON_APPROVAL_BINDING_CHANGED",
    "REASON_COMPLETED_OPERATION_BLOCKED",
    "REASON_CONTRACT_INCOMPATIBLE",
    "REASON_KIND_MODE_MISMATCH",
    "REASON_SCOPE_DRIFT",
    "REASON_SCOPE_MISSING",
    "scope_missing_rejection",
    "REASON_SETTLEMENT_REFUSED",
    "REASON_SOURCE_ACTIVE",
    "REASON_WRITE_UNRECONCILED",
    "RECOVERY_DIRECTORY",
    "RECOVERY_ROLES_DIRECTORY",
    "RECOVERY_SCHEMA",
    "RecoveryPlan",
    "RootRunLock",
    "SOURCE_SETTLEMENT_SCHEMA",
    "WAIT_SECONDS_MAX",
    "acquire_root_run_lock",
    "attempt_directories",
    "build_plan_mappings",
    "build_role_packets",
    "check_resume_submission",
    "checkpoint_root_run_id",
    "find_complete_pass_report",
    "http_readback",
    "load_recovery_imports",
    "merge_exposure_union",
    "next_acceptance_attempt",
    "origin_chain_roots",
    "prepare_acceptance_continuation",
    "prepare_recovery_plan",
    "prior_continuation_roots",
    "read_run_state",
    "read_write_tail",
    "recovery_index_settled_entry",
    "restore_checkpoint_artifacts",
    "safe_new_run_id",
    "session_lease_report",
    "settle_source_run",
    "settlement_record_path",
    "source_writer_report",
    "validate_business_approvals",
    "write_acceptance_continuation_record",
    "write_acceptance_origin",
    "write_recovery_files",
]
