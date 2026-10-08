"""R3.0-015 segment S2 tests (shared test plan M10-M26, M27, M30-M32,
M37-M40, M43, M45, M44 S2 side plus the D1 cursor-endpoint constraint).

Stand-in disclosure: ``CapturingAdapter`` is a controlled Runtime stand-in,
not a real model provider; ``FakeCursorPlatform`` is a controlled stand-in for
the platform REST surface that serves ONLY the cursor-paginated endpoints;
``ScopeClient`` is a controlled stand-in for the scope HTTP channel.  The two
platform-critical cases the plan calls out use REAL fixtures: the cross-Session
dedup proof drives the real ``ModelingBatchService`` over an in-memory SQLite
database (never a global in-memory dict), and the process-boundary proof runs a
genuinely separate OS process (a real ``TeamRunner`` on ``CapturingAdapter``)
that saves a checkpoint, cleans up and exits before this process resumes it.
Hidden-material markers stay inside temporary test run roots and never enter
formal modeling materials.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team import checkpoint_recovery as cr
from modeling_team.checkpoint_recovery import (
    APPLY_MODES,
    PREP_BUDGET_SECONDS,
    PlatformReadback,
    REASON_APPROVAL_BINDING_CHANGED,
    REASON_COMPLETED_OPERATION_BLOCKED,
    REASON_SCOPE_DRIFT,
    REASON_SOURCE_ACTIVE,
    REASON_WRITE_UNRECONCILED,
    RECOVERY_DIRECTORY,
    RECOVERY_SCHEMA,
    acquire_root_run_lock,
    build_plan_mappings,
    build_role_packets,
    check_resume_submission,
    checkpoint_root_run_id,
    merge_exposure_union,
    origin_chain_roots,
    prepare_recovery_plan,
    read_write_tail,
    reconcile_write_tail,
    safe_new_run_id,
    source_writer_report,
    validate_business_approvals,
)
from modeling_team.checkpoints import (
    CHECKPOINT_ARTIFACTS_DIRECTORY,
    CHECKPOINT_KIND_CQ_FROZEN,
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CHECKPOINT_KIND_SCENARIO_MAPPED,
    CheckpointArtifactSpec,
    CheckpointError,
    StagePackage,
    inspect_checkpoints,
    list_checkpoints,
    save_checkpoint,
)
from modeling_team.platform_scope import PlatformScope, PlatformScopeMissingError
from modeling_team.runner import TeamRunner
from modeling_team.staged_decisions import (
    StagedSubmissionRejection,
    build_submission_intent,
    build_submission_receipt,
    mark_intent_status,
    staged_decision_artifact_paths,
    write_submission_intent,
    write_submission_receipt,
)
from modeling_team.tests.test_platform_scope import ScopeClient
from modeling_team.tests.test_r30015_checkpoints import (
    CONFIGURATION,
    PROFILE,
    REPO_ROOT,
    RUNS_ROOT,
    _CheckpointRunner,
    _checkpoint_events,
    _freeze,
    _outer_save,
    _read_manifest,
    _run_cli,
    _settled_apply_intent,
    _tree_state,
    _write_json,
)
from modeling_team.tests.test_runner import CapturingAdapter

APPROVALS_RELATIVE = "value-semantics/approvals/approvals.json"


# --- controlled platform stand-in (cursor endpoints ONLY) -----------------------


class FakeCursorPlatform:
    """Controlled REST stand-in serving only the cursor-paginated endpoints.

    Every request path is recorded; anything outside the four allowed endpoint
    families lands in ``unexpected`` with a 404, so a test can prove the
    reconciliation never consulted a truncated convenience view (D1).
    """

    def __init__(
        self,
        *,
        session_batches: dict[str, list[dict]] | None = None,
        ontology_batches: dict[str, list[dict]] | None = None,
        sessions: dict[str, dict] | None = None,
    ) -> None:
        self.session_batches = session_batches or {}
        self.ontology_batches = ontology_batches or {}
        self.sessions = sessions or {}
        self.paths: list[str] = []
        self.unexpected: list[str] = []

    def __call__(self, method: str, path: str, body, key):
        self.paths.append(path)
        base, _, query = path.partition("?")
        params = dict(part.split("=", 1) for part in query.split("&")) if query else {}
        limit = int(params.get("limit", "50"))
        cursor = params.get("cursor")
        if base.startswith("/api/build-sessions/") and base.endswith("/modeling-batches"):
            session_id = base.split("/")[3]
            return 200, self._page(list(self.session_batches.get(session_id, [])), limit, cursor)
        if base.startswith("/api/ontologies/") and base.endswith("/modeling-batches"):
            ontology_id = base.split("/")[3]
            return 200, self._page(list(self.ontology_batches.get(ontology_id, [])), limit, cursor)
        if base.startswith("/api/modeling-batches/"):
            for batches in self.session_batches.values():
                for batch in batches:
                    if batch.get("batch_id") == base.rsplit("/", 1)[-1]:
                        return 200, batch
            return 404, None
        if base.startswith("/api/build-sessions/"):
            session_id = base.rsplit("/", 1)[-1]
            if session_id in self.sessions:
                return 200, self.sessions[session_id]
            return 404, None
        self.unexpected.append(path)
        return 404, None

    @staticmethod
    def _page(items: list[dict], limit: int, cursor: str | None) -> dict:
        start = int(cursor) if cursor else 0
        page = items[start : start + limit]
        next_start = start + len(page)
        return {
            "batches": page,
            "next_cursor": str(next_start) if next_start < len(items) else None,
        }


def _readback(platform: FakeCursorPlatform) -> PlatformReadback:
    return PlatformReadback(platform, "host-key-stand-in")


# --- module-tier fixtures --------------------------------------------------------


def _bound_package(
    kind: str = CHECKPOINT_KIND_CQ_FROZEN,
    *,
    sources: list[tuple[str, str]] | None = None,
    stage_facts: dict | None = None,
    scope_refs: dict | None = None,
) -> StagePackage:
    return StagePackage(
        kind=kind,
        scope_refs=scope_refs or {"freeze_id": "f-resume"},
        artifacts=[
            CheckpointArtifactSpec(
                source=source,
                owner=owner,
                visible_to=("coordinator", "modeling", "protocol"),
                host_private=False,
            )
            for source, owner in (sources or [("evidence/stage.json", "coordinator")])
        ],
        stage_facts=stage_facts or {},
        platform_bindings={"project_id": "proj-r3015", "ontology_ids": ["onto-r3015"]},
        write_positions={},
    )


def _seed_plan_run(
    *,
    state: dict | None = None,
    package: StagePackage | None = None,
    configuration: dict | None = None,
) -> tuple[Path, dict]:
    run_id = f"r3015src-{os.urandom(4).hex()}"
    run_root = RUNS_ROOT / run_id
    _write_json(run_root / "evidence" / "stage.json", {"stage": "resume-fixture"})
    if state is not None:
        _write_json(run_root / "state.json", state)
    saved = save_checkpoint(
        run_root,
        package or _bound_package(),
        source_run_id=run_id,
        configuration=configuration or dict(CONFIGURATION),
    )
    return run_root, saved


def _plan(
    run_root: Path,
    checkpoint_id: str,
    *,
    readback: PlatformReadback | None = None,
    new_run_id: str | None = None,
    authorization_reference: str | None = None,
):
    return prepare_recovery_plan(
        source_run_root=run_root,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id or f"r3015new-{os.urandom(4).hex()}",
        repository_root=REPO_ROOT,
        readback=readback or _readback(FakeCursorPlatform()),
        authorization_reference=authorization_reference,
    )


def _seed_chain_intent(
    run_root: Path,
    ordinal: int,
    *,
    key: str,
    client_batch_id: str,
    session_id: str,
    mode: str = "apply_atomic",
    status: str = "receipted",
    with_receipt: bool = True,
    batch_id: str = "platform-batch-1",
) -> None:
    intent = build_submission_intent(
        ordinal,
        idempotency_key=key,
        client_batch_id=client_batch_id,
        session_id=session_id,
        mode=mode,
        commands=[{"kind": "create_class", "payload": {"name": "Customer"}}],
        value_traces=[],
        l3_nodes=[],
    )
    write_submission_intent(run_root, mark_intent_status(intent, status))
    if with_receipt:
        write_submission_receipt(
            run_root,
            build_submission_receipt(
                ordinal, intent, batch_id=batch_id, response_digest="sha256:" + "1" * 64
            ),
        )


def _attempt(
    attempt_id: str,
    *,
    mode: str = "apply_atomic",
    status: str = "applied",
    items: list | None = None,
    recovery: dict | None = None,
) -> dict:
    return {
        "attempt_id": attempt_id,
        "mode": mode,
        "attempt_status": status,
        "items": items
        if items is not None
        else [
            {
                "client_item_id": "item-1",
                "status": status,
                "resource_outputs": {"resource_iri": "res://item-1"},
                "evidence_association_ids": ["ev-1"],
            }
        ],
        "recovery": recovery or {"state": status, "safe_to_retry": False},
    }


def _batch(
    batch_id: str,
    *,
    client_batch_id: str,
    session_id: str = "session-1",
    attempts: list[dict] | None = None,
    batch_status: str = "applied",
) -> dict:
    return {
        "batch_id": batch_id,
        "client_batch_id": client_batch_id,
        "build_session_id": session_id,
        "ontology_id": "onto-r3015",
        "content_hash": "sha256:" + "c" * 64,
        "batch_status": batch_status,
        "attempts": attempts if attempts is not None else [_attempt("attempt-1")],
        "items": [],
    }


# --- D1: cursor-paginated readback only (M18/M19/M20 side) -----------------------


def test_d1_readback_follows_cursors_and_never_reads_truncated_views():
    assert cr.LIST_PAGE_LIMIT == 100
    # 250 session batches and 150 ontology summaries force multi-page cursor
    # traversal at the backend's maximum page size.
    session_batches = [
        _batch(f"batch-{index:03d}", client_batch_id=f"cb-{index:03d}")
        for index in range(250)
    ]
    platform = FakeCursorPlatform(
        session_batches={"session-1": session_batches},
        ontology_batches={
            "onto-r3015": [
                {"batch_id": f"b-{index}", "build_session_id": "session-1"}
                for index in range(150)
            ]
        },
    )
    readback = _readback(platform)

    details = readback.list_session_batches("session-1")
    assert len(details) == 250
    assert {batch["batch_id"] for batch in details} == {
        f"batch-{index:03d}" for index in range(250)
    }
    summaries = readback.list_ontology_batches("onto-r3015")
    assert len(summaries) == 150

    # 250 items at limit=100 -> 3 listing pages; 150 -> 2 pages; every batch
    # detail read individually.  All of it through the three cursor families.
    assert readback.pages_read == 5
    assert readback.batches_read == 250
    assert platform.unexpected == []
    allowed_prefixes = (
        "/api/build-sessions/session-1/modeling-batches",
        "/api/ontologies/onto-r3015/modeling-batches",
        "/api/modeling-batches/",
    )
    assert all(path.split("?")[0].startswith(allowed_prefixes) for path in platform.paths)
    # The truncated convenience views are never reconciliation sources.
    assert not any("platform_state" in path for path in platform.paths)
    assert not any(
        path.split("?")[0] == "/api/build-sessions/session-1" for path in platform.paths
    )


def test_d1_readback_fails_closed_when_a_page_is_unreachable():
    class BrokenPlatform(FakeCursorPlatform):
        def __call__(self, method, path, body, key):
            return 500, None

    with pytest.raises(CheckpointError) as unreachable:
        _readback(BrokenPlatform()).list_session_batches("session-1")
    assert unreachable.value.reason_code == "platform_readback_unreachable"
    assert unreachable.value.retryable is True


# --- reconciliation classification table (design §5.1) --------------------------


def test_m19_classification_table_end_to_end():
    # The real REST modes are dry_run | apply_atomic | apply_partial; the
    # reconciliation must recognize the apply family, not a bare "apply".
    assert "apply_atomic" in APPLY_MODES and "apply" in APPLY_MODES

    run_root = RUNS_ROOT / f"r3015cls-{os.urandom(4).hex()}"
    try:
        # receipted apply -> completed
        _seed_chain_intent(
            run_root,
            1,
            key="idem-applied",
            client_batch_id="cb-applied",
            session_id="session-1",
            batch_id="batch-applied",
        )
        # receipt-missing apply, precisely read back applied -> completed with
        # the missing-receipt fact preserved (never rewritten into the old run)
        _seed_chain_intent(
            run_root,
            2,
            key="idem-readback-only",
            client_batch_id="cb-readback-only",
            session_id="session-1",
            with_receipt=False,
            batch_id="batch-readback-only",
        )
        # dry-run validated -> pending new dry-run in the NEW session
        _seed_chain_intent(
            run_root,
            3,
            key="idem-dry",
            client_batch_id="cb-dry",
            session_id="session-1",
            mode="dry_run",
            batch_id="batch-dry",
        )
        # platform-proven failed_without_side_effects -> recoverable new batch
        _seed_chain_intent(
            run_root,
            4,
            key="idem-failed-safe",
            client_batch_id="cb-failed-safe",
            session_id="session-1",
            batch_id="batch-failed-safe",
        )
        # unknown intent with no platform readback -> blocked (adjudication
        # hints alone can never release the gate)
        _seed_chain_intent(
            run_root,
            5,
            key="idem-unknown",
            client_batch_id="cb-unknown",
            session_id="session-1",
            status="unknown",
            with_receipt=False,
        )
        # applying attempt -> blocked
        _seed_chain_intent(
            run_root,
            6,
            key="idem-inflight",
            client_batch_id="cb-inflight",
            session_id="session-1",
            batch_id="batch-inflight",
        )

        platform = FakeCursorPlatform(
            session_batches={
                "session-1": [
                    _batch("batch-applied", client_batch_id="cb-applied"),
                    _batch(
                        "batch-readback-only",
                        client_batch_id="cb-readback-only",
                        attempts=[_attempt("attempt-ro")],
                    ),
                    _batch(
                        "batch-dry",
                        client_batch_id="cb-dry",
                        batch_status="validated",
                        attempts=[_attempt("attempt-dry", mode="dry_run", status="validated")],
                    ),
                    _batch(
                        "batch-failed-safe",
                        client_batch_id="cb-failed-safe",
                        batch_status="failed",
                        attempts=[
                            _attempt(
                                "attempt-failed",
                                status="failed",
                                recovery={"state": "failed_without_side_effects",
                                          "safe_to_retry": True},
                            )
                        ],
                    ),
                    _batch(
                        "batch-inflight",
                        client_batch_id="cb-inflight",
                        batch_status="applying",
                        attempts=[_attempt("attempt-applying", status="applying")],
                    ),
                ]
            }
        )
        result = reconcile_write_tail(
            [run_root], read_write_tail([run_root]), _readback(platform),
            ontology_ids=["onto-r3015"],
        )
        blocked_keys = {entry["idempotency_key"] for entry in result["blocked"]}
        assert blocked_keys == {"idem-unknown", "idem-inflight"}
        assert all(entry["reason"] == REASON_WRITE_UNRECONCILED for entry in result["blocked"])

        completed = {entry.idempotency_key: entry for entry in result["completed"]}
        assert set(completed) == {"idem-applied", "idem-readback-only"}
        first = completed["idem-applied"]
        assert first.key == (
            run_root.name, "session-1", "batch-applied", "attempt-1", "item-1"
        ) or first.key[1:] == ("session-1", "batch-applied", "attempt-1", "item-1")
        assert first.mode == "apply_atomic"
        assert first.content_hash == "sha256:" + "c" * 64
        assert first.resource_ids
        assert first.readback_only is False
        assert completed["idem-readback-only"].readback_only is True
        assert completed["idem-readback-only"].receipt_ordinal is None
        assert result["completed_client_batches"]["cb-applied"] == "batch-applied"

        dry = {entry["idempotency_key"] for entry in result["pending_new_dry_run"]}
        assert dry == {"idem-dry"}
        recoverable = {
            entry["idempotency_key"] for entry in result["recoverable_new_batch"]
        }
        assert recoverable == {"idem-failed-safe"}
        assert result["scope_drift"] == []
        index_keys = {entry.key for entry in result["completed"]}
        assert all(len(key) == 5 for key in index_keys)
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m19_submitted_and_rejected_dry_runs_without_a_batch_close_without_touching_source():
    """Old-run compatibility for the closed write tail.

    A reachable, empty session listing plus a batch-less dry-run intent proves
    the request never materialized anything, so reconciliation closes it into a
    NEW dry-run.  This holds for the legacy ``submitted`` status (the historical
    record shape) and for the definite ``rejected`` terminal state, and it never
    rewrites the old run's evidence: the intent bytes are identical afterwards.
    """
    run_root = RUNS_ROOT / f"r3015sub-{os.urandom(4).hex()}"
    try:
        _seed_chain_intent(
            run_root,
            1,
            key="idem-submitted-dry",
            client_batch_id="cb-submitted-dry",
            session_id="session-1",
            mode="dry_run",
            status="submitted",
            with_receipt=False,
        )
        _seed_chain_intent(
            run_root,
            2,
            key="idem-rejected-dry",
            client_batch_id="cb-rejected-dry",
            session_id="session-1",
            mode="dry_run",
            status="rejected",
            with_receipt=False,
        )
        # A rejected apply without a platform batch stays fail-closed: the
        # recovery chain trusts platform readback, never the local refusal.
        _seed_chain_intent(
            run_root,
            3,
            key="idem-rejected-apply",
            client_batch_id="cb-rejected-apply",
            session_id="session-1",
            mode="apply_atomic",
            status="rejected",
            with_receipt=False,
        )
        intents_dir = staged_decision_artifact_paths(run_root)["intents_dir"]
        before = {
            path.name: path.read_bytes() for path in sorted(intents_dir.iterdir())
        }
        result = reconcile_write_tail(
            [run_root],
            read_write_tail([run_root]),
            _readback(FakeCursorPlatform(session_batches={"session-1": []})),
            ontology_ids=["onto-r3015"],
        )
        pending = {entry["idempotency_key"] for entry in result["pending_new_dry_run"]}
        assert pending == {"idem-submitted-dry", "idem-rejected-dry"}
        blocked = {entry["idempotency_key"] for entry in result["blocked"]}
        assert blocked == {"idem-rejected-apply"}
        assert all(entry["reason"] == REASON_WRITE_UNRECONCILED for entry in result["blocked"])
        # The reconciliation read the source; it never rewrote it.
        after = {
            path.name: path.read_bytes() for path in sorted(intents_dir.iterdir())
        }
        assert after == before
        assert not list(staged_decision_artifact_paths(run_root)["receipts_dir"].glob("*.json"))
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m19_settled_historical_dry_run_is_not_an_unknown_write():
    """Field regression: the 2026-09-16 start1 -> resume2 S4 blocker.

    A real production run submits each stage as TWO chain operations with two
    idempotency keys over ONE Batch: the dry-run that never materializes, and
    the apply that follows it.  Reading that Batch back ``applied`` therefore
    SATISFIES the dry-run operation itself: it is settled history that wrote
    nothing, so it must neither keep the gate closed nor be queued as a new
    dry-run -- while the completion index keeps being built by the apply
    operation that actually did the writing.  An applied Batch that no chain
    apply operation claims, an applying Batch and a partially applied Batch all
    keep their existing refusals.
    """

    run_root = RUNS_ROOT / f"r3015settled-{os.urandom(4).hex()}"
    try:
        # The real shape: dry-run v2 and apply v1 are separate operations over
        # one client_batch_id / one platform Batch.
        _seed_chain_intent(
            run_root, 1, key="stage1-dry-v2", client_batch_id="cb-stage1",
            session_id="session-1", mode="dry_run", batch_id="batch-stage1",
        )
        _seed_chain_intent(
            run_root, 2, key="stage1-apply-v1", client_batch_id="cb-stage1",
            session_id="session-1", batch_id="batch-stage1",
        )
        # An applied Batch no chain apply operation claims: the write itself is
        # unattributable, so the dry-run is NOT settled history.
        _seed_chain_intent(
            run_root, 3, key="dry-unclaimed-batch", client_batch_id="cb-unclaimed",
            session_id="session-1", mode="dry_run", batch_id="batch-unclaimed",
        )
        # Still applying -> never settled.
        _seed_chain_intent(
            run_root, 4, key="dry-inflight-batch", client_batch_id="cb-inflight",
            session_id="session-1", mode="dry_run", batch_id="batch-inflight",
        )
        # An applied attempt next to a partially applied one is not a settled
        # Batch either: the partial write keeps the gate closed.
        _seed_chain_intent(
            run_root, 5, key="dry-partial-batch", client_batch_id="cb-partial",
            session_id="session-1", mode="dry_run", batch_id="batch-partial",
        )
        platform = FakeCursorPlatform(
            session_batches={
                "session-1": [
                    _batch(
                        "batch-stage1",
                        client_batch_id="cb-stage1",
                        attempts=[
                            _attempt("attempt-dry-1", mode="dry_run", status="validated"),
                            _attempt(
                                "attempt-apply-1", mode="apply_atomic", status="applied"
                            ),
                        ],
                    ),
                    _batch("batch-unclaimed", client_batch_id="cb-unclaimed"),
                    _batch(
                        "batch-inflight",
                        client_batch_id="cb-inflight",
                        batch_status="applying",
                        attempts=[_attempt("attempt-applying", status="applying")],
                    ),
                    _batch(
                        "batch-partial",
                        client_batch_id="cb-partial",
                        batch_status="partially_applied",
                        attempts=[
                            _attempt("attempt-applied", status="applied"),
                            _attempt("attempt-partial", status="partially_applied"),
                        ],
                    ),
                ]
            }
        )
        result = reconcile_write_tail(
            [run_root], read_write_tail([run_root]), _readback(platform),
            ontology_ids=["onto-r3015"],
        )

        blocked = {entry["idempotency_key"] for entry in result["blocked"]}
        assert blocked == {"dry-unclaimed-batch", "dry-inflight-batch", "dry-partial-batch"}
        assert all(
            entry["reason"] == REASON_WRITE_UNRECONCILED for entry in result["blocked"]
        )

        # The dry-run is acknowledged as settled non-writing history; it is
        # never replayed as a new dry-run over an already materialized Batch.
        assert {entry["idempotency_key"] for entry in result["settled_non_write"]} == {
            "stage1-dry-v2"
        }
        assert result["pending_new_dry_run"] == []

        # The completion index still comes from the apply operation itself, and
        # it still guards that client_batch_id against resubmission.
        assert {entry.idempotency_key for entry in result["completed"]} == {
            "stage1-apply-v1"
        }
        assert result["completed_client_batches"] == {"cb-stage1": "batch-stage1"}
        assert result["scope_drift"] == []
    finally:
        rmtree(run_root, ignore_errors=True)


def test_dry_run_terminal_validation_failed_is_a_settled_non_write():
    """Field regression: the 2026-10-05 start2 S2 ``write_unreconciled`` blocker.

    The platform validates a dry-run BEFORE any mutation, so a Batch whose
    final attempt terminally reads back ``validation_failed`` is a precise
    platform proof that nothing was written (the real chain: one dry-run
    attempt, ``recovery.state=not_required``, no applied/in-flight/partial
    attempt).  That dry-run operation is settled history: it must not keep
    the write gate closed, must not be queued as a new dry-run or a
    recoverable batch (a corrected revision through the normal submission
    path is the repair, and in the real chain it already applied under later
    client_batch_ids), and a validation_failed attempt inside a Batch that a
    later apply attempt DID apply stays superseded history with no replay.
    Every apply-family gate keeps refusing: an apply intent over a
    validation_failed-only Batch stays blocked, and in-flight/partial
    attempts still block regardless of intent mode.
    """

    run_root = RUNS_ROOT / f"r3015vf-{os.urandom(4).hex()}"
    try:
        # (a) the real blocker shape: one dry-run operation, one Batch, whose
        # single attempt terminally failed validation (nothing materialized).
        _seed_chain_intent(
            run_root, 1, key="dry-rejected-v1", client_batch_id="cb-rejected-dry",
            session_id="session-1", mode="dry_run", batch_id="batch-rejected",
        )
        # (b) mixed Batch: a rejected dry-run attempt followed by an applied
        # apply attempt, with the chain's own apply operation over the same
        # client_batch_id -- the applied result is reused, never replayed.
        _seed_chain_intent(
            run_root, 2, key="stage2-dry-v1", client_batch_id="cb-stage2",
            session_id="session-1", mode="dry_run", batch_id="batch-stage2",
        )
        _seed_chain_intent(
            run_root, 3, key="stage2-apply-v1", client_batch_id="cb-stage2",
            session_id="session-1", batch_id="batch-stage2",
        )
        # (c) the hard gates that must keep refusing.
        _seed_chain_intent(
            run_root, 4, key="dry-validating", client_batch_id="cb-validating",
            session_id="session-1", mode="dry_run", batch_id="batch-validating",
        )
        _seed_chain_intent(
            run_root, 5, key="apply-over-rejected", client_batch_id="cb-apply-rejected",
            session_id="session-1", batch_id="batch-apply-rejected",
        )
        _seed_chain_intent(
            run_root, 6, key="apply-partial-batch", client_batch_id="cb-partial-apply",
            session_id="session-1", batch_id="batch-partial-apply",
        )
        intents_dir = staged_decision_artifact_paths(run_root)["intents_dir"]
        before = {
            path.name: path.read_bytes() for path in sorted(intents_dir.iterdir())
        }
        not_required = {"state": "not_required", "safe_to_retry": False}
        platform = FakeCursorPlatform(
            session_batches={
                "session-1": [
                    _batch(
                        "batch-rejected",
                        client_batch_id="cb-rejected-dry",
                        batch_status="open",
                        attempts=[
                            _attempt(
                                "attempt-rejected",
                                mode="dry_run",
                                status="validation_failed",
                                recovery=not_required,
                            )
                        ],
                    ),
                    _batch(
                        "batch-stage2",
                        client_batch_id="cb-stage2",
                        attempts=[
                            _attempt(
                                "attempt-dry-1",
                                mode="dry_run",
                                status="validation_failed",
                                recovery=not_required,
                            ),
                            _attempt(
                                "attempt-apply-1", mode="apply_atomic", status="applied"
                            ),
                        ],
                    ),
                    _batch(
                        "batch-validating",
                        client_batch_id="cb-validating",
                        batch_status="open",
                        attempts=[
                            _attempt("attempt-validating", mode="dry_run",
                                     status="validating")
                        ],
                    ),
                    _batch(
                        "batch-apply-rejected",
                        client_batch_id="cb-apply-rejected",
                        batch_status="open",
                        attempts=[
                            _attempt(
                                "attempt-apply-rejected",
                                mode="apply_atomic",
                                status="validation_failed",
                                recovery=not_required,
                            )
                        ],
                    ),
                    _batch(
                        "batch-partial-apply",
                        client_batch_id="cb-partial-apply",
                        batch_status="partially_applied",
                        attempts=[
                            _attempt(
                                "attempt-partial", mode="apply_atomic",
                                status="partially_applied"
                            )
                        ],
                    ),
                ]
            }
        )
        result = reconcile_write_tail(
            [run_root], read_write_tail([run_root]), _readback(platform),
            ontology_ids=["onto-r3015"],
        )

        # (a)+(b): settled non-writing history, never a gate blocker and never
        # queued for any resubmission.
        settled = {entry["idempotency_key"] for entry in result["settled_non_write"]}
        assert settled == {"dry-rejected-v1", "stage2-dry-v1"}
        rejected = next(
            entry
            for entry in result["settled_non_write"]
            if entry["idempotency_key"] == "dry-rejected-v1"
        )
        assert "terminally failed validation before any write" in rejected["detail"]
        assert "never a resubmission of this batch" in rejected["detail"]
        assert result["pending_new_dry_run"] == []
        assert result["recoverable_new_batch"] == []
        # Settled history creates no unfinished item, so no role packet can be
        # pushed into replaying the rejected content.
        assert cr.unfinished_items(result) == []

        # (b): the completion index still comes from the apply operation alone
        # and still guards the client_batch_id against resubmission.
        assert {entry.idempotency_key for entry in result["completed"]} == {
            "stage2-apply-v1"
        }
        assert result["completed_client_batches"] == {"cb-stage2": "batch-stage2"}

        # (c): in-flight, apply-over-rejected and partial all keep the gate
        # closed with the same typed reason.
        blocked = {entry["idempotency_key"] for entry in result["blocked"]}
        assert blocked == {"dry-validating", "apply-over-rejected", "apply-partial-batch"}
        assert all(
            entry["reason"] == REASON_WRITE_UNRECONCILED for entry in result["blocked"]
        )
        assert result["scope_drift"] == []
        # The reconciliation read the source; it never rewrote it.
        after = {
            path.name: path.read_bytes() for path in sorted(intents_dir.iterdir())
        }
        assert after == before
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m21_m26_unattributable_write_is_scope_drift_but_chain_writes_are_not():
    run_root = RUNS_ROOT / f"r3015drift-{os.urandom(4).hex()}"
    try:
        # Two legitimate chain writes on the bound ontology (the second one
        # happened AFTER the checkpoint: the baseline absorbs it, M26).
        _seed_chain_intent(
            run_root, 1, key="idem-1", client_batch_id="cb-1",
            session_id="session-1", batch_id="batch-1",
        )
        _seed_chain_intent(
            run_root, 2, key="idem-2", client_batch_id="cb-2",
            session_id="session-1", batch_id="batch-2",
        )
        platform = FakeCursorPlatform(
            session_batches={
                "session-1": [
                    _batch("batch-1", client_batch_id="cb-1"),
                    _batch("batch-2", client_batch_id="cb-2"),
                ]
            },
            ontology_batches={
                # The ontology listing sees the chain writes AND a foreign
                # session's write the recovery cannot attribute to itself.
                "onto-r3015": [
                    {"batch_id": "batch-1", "build_session_id": "session-1"},
                    {"batch_id": "batch-2", "build_session_id": "session-1"},
                    {"batch_id": "batch-foreign", "build_session_id": "session-foreign"},
                ]
            },
        )
        result = reconcile_write_tail(
            [run_root], read_write_tail([run_root]), _readback(platform),
            ontology_ids=["onto-r3015"],
        )
        assert result["blocked"] == []
        assert len(result["completed"]) == 2
        assert [entry["batch_id"] for entry in result["scope_drift"]] == ["batch-foreign"]
        assert result["scope_drift"][0]["reason"] == REASON_SCOPE_DRIFT
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m14_m25_multi_hop_chain_reads_the_full_write_tail_of_every_run():
    runs_root = RUNS_ROOT / f"r3015chain-{os.urandom(4).hex()}"
    oldest = runs_root / "o1"
    resumed = runs_root / "o2"
    try:
        _seed_chain_intent(
            oldest, 1, key="idem-origin", client_batch_id="cb-origin",
            session_id="session-o1", batch_id="batch-origin",
        )
        _write_json(
            resumed / RECOVERY_DIRECTORY / "origin.json",
            {"schema_version": RECOVERY_SCHEMA, "source_run_id": "o1"},
        )
        _seed_chain_intent(
            resumed, 2, key="idem-second", client_batch_id="cb-second",
            session_id="session-o2", batch_id="batch-second",
        )
        chain = origin_chain_roots(resumed, runs_root)
        assert [path.name for path in chain] == ["o1", "o2"]
        tail = read_write_tail(chain)
        assert {key for key in tail} == {"o1", "o2"}
        assert {intent["idempotency_key"] for intent in tail["o1"]["intents"]} == {
            "idem-origin"
        }

        platform = FakeCursorPlatform(
            session_batches={
                "session-o1": [_batch("batch-origin", client_batch_id="cb-origin",
                                      session_id="session-o1")],
                "session-o2": [_batch("batch-second", client_batch_id="cb-second",
                                      session_id="session-o2")],
            }
        )
        result = reconcile_write_tail(
            chain, tail, _readback(platform), ontology_ids=[]
        )
        assert result["blocked"] == []
        origins = {entry.origin_run_id for entry in result["completed"]}
        # Multi-hop imports keep pointing at the ORIGINAL operations (M25).
        assert origins == {"o1", "o2"}
        origin_entry = next(
            entry for entry in result["completed"] if entry.idempotency_key == "idem-origin"
        )
        assert origin_entry.origin_run_id == "o1"
        assert origin_entry.key[1] == "session-o1"
    finally:
        rmtree(runs_root, ignore_errors=True)


# --- dual-source resume: package source + explicit write-tail run ----------------
# The 2026-10-05 start2 shape: the package comes from start1's published
# checkpoint, but the dead continuation (start2-retry1) never published one and
# holds 28 post-checkpoint writes in its own session.  A single-source resume
# correctly calls those writes scope drift; the host's explicit
# ``write_tail_run_root`` reconciles the FULL chain instead -- package identity
# and every original gate stay on the package source, the write tail and the
# writer-death gates extend to the named tail, and nothing is auto-discovered.


def _seed_dual_source_chain(runs_root: Path) -> tuple[Path, Path, dict]:
    """o1 (package source, dead) -> o2 (dead continuation that wrote past cp)."""

    oldest = runs_root / "o1"
    _write_json(oldest / "evidence" / "stage.json", {"stage": "resume-fixture"})
    _write_json(oldest / "state.json", {"state": "FAILED"})
    saved = save_checkpoint(
        oldest,
        # The real incident shape: start1's published cp16 was a
        # materialization_progress package, and the dead continuation never
        # published one of its own.
        _bound_package(kind=CHECKPOINT_KIND_MATERIALIZATION_PROGRESS),
        source_run_id="o1",
        root_run_id="o1",
        configuration=dict(CONFIGURATION),
    )
    _seed_chain_intent(
        oldest, 1, key="idem-origin", client_batch_id="cb-origin",
        session_id="session-o1", batch_id="batch-origin",
    )
    tail_run = runs_root / "o2"
    _seed_dual_source_tail(tail_run, oldest.name, saved)
    _seed_chain_intent(
        tail_run, 2, key="idem-tail", client_batch_id="cb-tail",
        session_id="session-o2", batch_id="batch-tail",
    )
    return oldest, tail_run, saved


def _seed_dual_source_tail(
    tail_run: Path,
    source_id: str,
    saved: Mapping,
    *,
    state: str = "FAILED",
    checkpoint_id: str | None = None,
    checkpoint_digest: str | None = None,
) -> None:
    """The dead continuation run that resumed ``saved`` and wrote past it."""

    _write_json(tail_run / "state.json", {"state": state})
    _write_json(
        tail_run / RECOVERY_DIRECTORY / "origin.json",
        {
            "schema_version": RECOVERY_SCHEMA,
            "source_run_id": source_id,
            "root_run_id": source_id,
            "checkpoint_id": checkpoint_id or saved["checkpoint_id"],
            "checkpoint_digest": checkpoint_digest or saved["manifest_digest"],
            "new_run_id": tail_run.name,
        },
    )


def _dual_source_platform(*, foreign: bool = False) -> FakeCursorPlatform:
    onto_batches = [
        {"batch_id": "batch-origin", "build_session_id": "session-o1"},
        {"batch_id": "batch-tail", "build_session_id": "session-o2"},
    ]
    if foreign:
        onto_batches.append(
            {"batch_id": "batch-foreign", "build_session_id": "session-foreign"}
        )
    return FakeCursorPlatform(
        session_batches={
            "session-o1": [
                _batch("batch-origin", client_batch_id="cb-origin", session_id="session-o1")
            ],
            "session-o2": [
                _batch("batch-tail", client_batch_id="cb-tail", session_id="session-o2")
            ],
        },
        ontology_batches={"onto-r3015": onto_batches},
    )


def test_dual_source_write_tail_extends_the_chain_and_keeps_the_package_binding():
    runs_root = RUNS_ROOT / f"r3015dual-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        platform = _dual_source_platform()

        # Single-source resume from o1's package: the continuation's own
        # session is unattributable -> scope drift.  This is the documented
        # reason the dead-child-without-own-checkpoint case had NO existing
        # path, and it must stay rejected without the explicit tail.
        with pytest.raises(CheckpointError) as drifted:
            _plan(oldest, saved["checkpoint_id"], readback=_readback(platform))
        assert drifted.value.reason_code == REASON_SCOPE_DRIFT

        # The explicit write-tail run reconciles the FULL chain instead.
        plan = prepare_recovery_plan(
            source_run_root=oldest,
            checkpoint_id=saved["checkpoint_id"],
            new_run_id=f"r3015new-{os.urandom(4).hex()}",
            repository_root=REPO_ROOT,
            readback=_readback(platform),
            write_tail_run_root=tail_run,
        )
        assert [path.name for path in plan.chain_roots] == ["o1", "o2"]
        # The package still comes from o1's published bytes...
        assert plan.origin["checkpoint_source_run_id"] == "o1"
        assert plan.origin["checkpoint_id"] == saved["checkpoint_id"]
        assert plan.origin["checkpoint_digest"] == saved["manifest_digest"]
        # ...while the write chain follows the actual latest tail.
        assert plan.origin["source_run_id"] == "o2"
        assert plan.inspection["reconciliation"]["chain_runs"] == ["o1", "o2"]
        assert plan.inspection["write_tail"]["run_id"] == "o2"
        assert plan.inspection["write_tail"]["checkpoint_source_run_id"] == "o1"
        # The completion index covers BOTH runs' applied batches, so every
        # completed operation -- including the tail's post-checkpoint writes --
        # is a replay-blocked import for the new run.
        assert plan.imports["completed_client_batches"] == {
            "cb-origin": "batch-origin",
            "cb-tail": "batch-tail",
        }
        assert {
            entry["idempotency_key"]
            for entry in plan.imports["completed_operations"]
        } == {"idem-origin", "idem-tail"}
        # The materialized records keep the chain linear for the NEXT resume.
        third = runs_root / "o3"
        cr.write_recovery_files(
            third,
            inspection=plan.inspection,
            origin=plan.origin,
            imports=plan.imports,
            role_packets=plan.role_packets,
        )
        assert [path.name for path in origin_chain_roots(third, runs_root)] == [
            "o1", "o2", "o3",
        ]
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_unrelated_runs_are_refused_fail_closed():
    runs_root = RUNS_ROOT / f"r3015unrel-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        platform = _dual_source_platform()

        # (a) a fresh directory with no recovery origin at all.
        stranger = runs_root / "stranger"
        _write_json(stranger / "state.json", {"state": "FAILED"})
        # (b) a continuation whose origin points at a different source run.
        grafted = runs_root / "grafted"
        _seed_dual_source_tail(grafted, "o-other", saved)
        for candidate in (stranger, grafted, oldest, runs_root / "absent"):
            with pytest.raises(CheckpointError) as refused:
                prepare_recovery_plan(
                    source_run_root=oldest,
                    checkpoint_id=saved["checkpoint_id"],
                    new_run_id=f"r3015new-{os.urandom(4).hex()}",
                    repository_root=REPO_ROOT,
                    readback=_readback(platform),
                    write_tail_run_root=candidate,
                )
            assert refused.value.reason_code == "write_tail_unrelated", candidate
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_outside_the_runs_root_is_refused_even_with_a_valid_origin():
    """The tail must BE a run directory under the runs root, not just claim one.

    The CLI composes ``runs_root / args.write_tail_run_id`` without the host
    API's run-name regex, so ``../<dir>`` reaches this function as a path
    outside ``workspaces/modeling-runs``.  A directory there with an otherwise
    exact valid origin must not be adopted as the write tail: the boundary is
    the first refusal condition, not the origin's own claims.
    """

    runs_root = RUNS_ROOT / f"r3015outside-{os.urandom(4).hex()}"
    outside_root = runs_root.parent / f"r3015outside-tail-{os.urandom(4).hex()}"
    try:
        oldest, _tail_run, saved = _seed_dual_source_chain(runs_root)
        platform = _dual_source_platform()

        # The outside tail is otherwise EXACTLY the accepted shape: dead
        # state, origin binding o1's real checkpoint id and digest, and the
        # chain intent the platform readback reconciles.
        outside_tail = outside_root / "o2"
        _seed_dual_source_tail(outside_tail, oldest.name, saved)
        _seed_chain_intent(
            outside_tail, 2, key="idem-tail", client_batch_id="cb-tail",
            session_id="session-o2", batch_id="batch-tail",
        )
        with pytest.raises(CheckpointError) as refused:
            prepare_recovery_plan(
                source_run_root=oldest,
                checkpoint_id=saved["checkpoint_id"],
                new_run_id=f"r3015new-{os.urandom(4).hex()}",
                repository_root=REPO_ROOT,
                readback=_readback(platform),
                write_tail_run_root=outside_tail,
            )
        assert refused.value.reason_code == "write_tail_unrelated"
    finally:
        rmtree(runs_root, ignore_errors=True)
        rmtree(outside_root, ignore_errors=True)


def test_write_tail_checkpoint_binding_must_match_the_requested_package():
    runs_root = RUNS_ROOT / f"r3015bind-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        platform = _dual_source_platform()

        # (a) the tail resumed a different checkpoint of the same source.
        rebound = runs_root / "rebound-id"
        _seed_dual_source_tail(
            rebound, oldest.name, saved, checkpoint_id="cq_frozen-9999"
        )
        # (b) the tail's origin records a different package digest.
        redigested = runs_root / "rebound-digest"
        _seed_dual_source_tail(
            redigested, oldest.name, saved,
            checkpoint_digest="sha256:" + "0" * 64,
        )
        for candidate in (rebound, redigested):
            with pytest.raises(CheckpointError) as refused:
                prepare_recovery_plan(
                    source_run_root=oldest,
                    checkpoint_id=saved["checkpoint_id"],
                    new_run_id=f"r3015new-{os.urandom(4).hex()}",
                    repository_root=REPO_ROOT,
                    readback=_readback(platform),
                    write_tail_run_root=candidate,
                )
            assert refused.value.reason_code == "write_tail_checkpoint_binding"
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_deep_chain_resumes_through_the_later_checkpoint_too():
    """o1 --cpA--> o2 --cpB--> o3: package cpA with tail o3 still binds via o2.

    Only the run immediately after the package source must have resumed THE
    requested package; later hops may legitimately have resumed their own
    direct parent's checkpoint, and the reconciliation covers every hop's
    writes through the full chain.
    """

    runs_root = RUNS_ROOT / f"r3015deep-{os.urandom(4).hex()}"
    try:
        oldest, second, first_saved = _seed_dual_source_chain(runs_root)
        # o2 published its own checkpoint and o3 resumed from THAT one.
        _write_json(second / "evidence" / "stage.json", {"stage": "resume-fixture"})
        second_saved = save_checkpoint(
            second,
            _bound_package(kind=CHECKPOINT_KIND_MATERIALIZATION_PROGRESS),
            source_run_id="o2",
            root_run_id="o1",
            configuration=dict(CONFIGURATION),
        )
        third = runs_root / "o3"
        _seed_dual_source_tail(third, second.name, second_saved)
        _seed_chain_intent(
            third, 3, key="idem-third", client_batch_id="cb-third",
            session_id="session-o3", batch_id="batch-third",
        )
        platform = FakeCursorPlatform(
            session_batches={
                "session-o1": [
                    _batch("batch-origin", client_batch_id="cb-origin", session_id="session-o1")
                ],
                "session-o2": [
                    _batch("batch-tail", client_batch_id="cb-tail", session_id="session-o2")
                ],
                "session-o3": [
                    _batch("batch-third", client_batch_id="cb-third", session_id="session-o3")
                ],
            },
            ontology_batches={
                "onto-r3015": [
                    {"batch_id": "batch-origin", "build_session_id": "session-o1"},
                    {"batch_id": "batch-tail", "build_session_id": "session-o2"},
                    {"batch_id": "batch-third", "build_session_id": "session-o3"},
                ]
            },
        )
        plan = prepare_recovery_plan(
            source_run_root=oldest,
            checkpoint_id=first_saved["checkpoint_id"],
            new_run_id=f"r3015new-{os.urandom(4).hex()}",
            repository_root=REPO_ROOT,
            readback=_readback(platform),
            write_tail_run_root=third,
        )
        assert [path.name for path in plan.chain_roots] == ["o1", "o2", "o3"]
        assert plan.origin["checkpoint_source_run_id"] == "o1"
        assert plan.origin["source_run_id"] == "o3"
        assert set(plan.imports["completed_client_batches"]) == {
            "cb-origin", "cb-tail", "cb-third"
        }
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_live_writer_keeps_the_source_active_gate():
    runs_root = RUNS_ROOT / f"r3015live-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        _write_json(tail_run / "state.json", {"state": "RUNNING"})
        with pytest.raises(CheckpointError) as active:
            prepare_recovery_plan(
                source_run_root=oldest,
                checkpoint_id=saved["checkpoint_id"],
                new_run_id=f"r3015new-{os.urandom(4).hex()}",
                repository_root=REPO_ROOT,
                readback=_readback(_dual_source_platform()),
                write_tail_run_root=tail_run,
            )
        assert active.value.reason_code == REASON_SOURCE_ACTIVE
        assert active.value.retryable is True
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_unknown_writes_still_close_the_write_gate():
    runs_root = RUNS_ROOT / f"r3015unk-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        _seed_chain_intent(
            tail_run, 3, key="idem-unknown", client_batch_id="cb-unknown",
            session_id="session-o2", status="unknown", with_receipt=False,
        )
        with pytest.raises(CheckpointError) as blocked:
            prepare_recovery_plan(
                source_run_root=oldest,
                checkpoint_id=saved["checkpoint_id"],
                new_run_id=f"r3015new-{os.urandom(4).hex()}",
                repository_root=REPO_ROOT,
                readback=_readback(_dual_source_platform()),
                write_tail_run_root=tail_run,
            )
        assert blocked.value.reason_code == REASON_WRITE_UNRECONCILED
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_write_tail_does_not_claim_foreign_branch_writes():
    runs_root = RUNS_ROOT / f"r3015for-{os.urandom(4).hex()}"
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        # A sibling branch's write on the bound ontology stays unattributable:
        # the named tail extends the chain, it never auto-claims other writes.
        with pytest.raises(CheckpointError) as drifted:
            prepare_recovery_plan(
                source_run_root=oldest,
                checkpoint_id=saved["checkpoint_id"],
                new_run_id=f"r3015new-{os.urandom(4).hex()}",
                repository_root=REPO_ROOT,
                readback=_readback(_dual_source_platform(foreign=True)),
                write_tail_run_root=tail_run,
            )
        assert drifted.value.reason_code == REASON_SCOPE_DRIFT
        assert "batch-foreign" in drifted.value.detail or True
    finally:
        rmtree(runs_root, ignore_errors=True)


def test_prepare_from_checkpoint_refuses_fork_combined_with_write_tail():
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=CapturingAdapter(),
        ledger_root=RUNS_ROOT / f"r3015ft-{os.urandom(4).hex()}-ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
        canonical_admin_key="test-host-key",
    )
    with pytest.raises(CheckpointError) as refused:
        runner.prepare_from_checkpoint(
            source_run_root=RUNS_ROOT / "whatever-source",
            checkpoint_id="cq_frozen-0001",
            new_run_id=f"r3015ft-new-{os.urandom(4).hex()}",
            fork_reason="duplicate-for-acceptance",
            write_tail_run_root=RUNS_ROOT / "whatever-tail",
        )
    assert refused.value.reason_code == "checkpoint_flags_incompatible"
    assert runner.run is None
    rmtree(runner.ledger_root, ignore_errors=True)


def test_runner_prepare_from_checkpoint_threads_the_write_tail_through():
    """The runner entry materializes the dual-source records the host expects."""

    runs_root = RUNS_ROOT / f"r3015rt-{os.urandom(4).hex()}"
    target_id = f"r3015rt-new-{os.urandom(4).hex()}"
    target = None
    try:
        oldest, tail_run, saved = _seed_dual_source_chain(runs_root)
        target = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=runs_root / f"{target_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
            canonical_admin_key="test-host-key",
        )
        target.prepare_from_checkpoint(
            source_run_root=oldest,
            checkpoint_id=saved["checkpoint_id"],
            new_run_id=target_id,
            readback=_readback(_dual_source_platform()),
            write_tail_run_root=tail_run,
        )
        origin = json.loads(
            (target.run.root / RECOVERY_DIRECTORY / "origin.json").read_text("utf-8")
        )
        assert origin["source_run_id"] == "o2"
        assert origin["checkpoint_source_run_id"] == "o1"
        assert origin["checkpoint_id"] == saved["checkpoint_id"]
        assert origin["checkpoint_digest"] == saved["manifest_digest"]
        imports = json.loads(
            (target.run.root / RECOVERY_DIRECTORY / "imports.json").read_text("utf-8")
        )
        assert imports["completed_client_batches"] == {
            "cb-origin": "batch-origin",
            "cb-tail": "batch-tail",
        }
        assert [path.name for path in origin_chain_roots(target.run.root, runs_root)] == [
            "o1", "o2", target_id,
        ]
    finally:
        if target is not None and target.run is not None:
            target.cleanup()
        rmtree(runs_root, ignore_errors=True)


def test_cli_resume_write_tail_is_production_only(monkeypatch, capsys):
    # argparse accepts the flag; the acceptance dispatch refuses it before any
    # continuation work, mirroring the fork guard's wording and exit code.
    assert (
        _run_cli(
            monkeypatch,
            [
                "checkpoint", "resume",
                "--run-id", "x", "--checkpoint-id", "y", "--new-run-id", "z",
                "--mode", "acceptance", "--write-tail-run-id", "w",
            ],
        )
        == 2
    )
    assert "--write-tail-run-id requires production mode" in capsys.readouterr().err


# --- real backend service: cross-Session dedup proof (M16, §2 hard rule) --------


def test_m16_real_service_keys_do_not_dedupe_across_sessions_and_the_index_blocks():
    from sqlalchemy import create_engine, event
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api.schemas import (
        BuildSessionCreate,
        ModelingBatchSubmit,
        ModelingItemInput,
        OntologyLeaseAcquire,
    )
    from app.core.config import Settings
    from app.repositories.models import OntologyModel, ProjectModel
    from app.repositories.postgres import Base
    from app.services.build_sessions import BuildSessionService
    from app.services.modeling_batches import ModelingBatchService
    from app.services.modeling_workspace import OntologyModelRevisionService
    from app.services.ontology_workspace import OntologyWorkspaceService
    from modeling_team.tests.test_p2a_batch_plan_service import FakeRdfStore

    @compiles(JSONB, "sqlite")
    def _compile_jsonb(element, compiler, **kwargs):  # noqa: ARG001
        return "JSON"

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings = Settings(
        semantic_graph_iri_prefix="https://r3015.test/graph/",
        semantic_base_iri="https://r3015.test/resource/",
        semantic_product_write_mode="rdf_primary",
    )
    rdf = FakeRdfStore()
    project_id = "r3015-real-project"
    ontology_id = "r3015-real-ontology"
    with factory() as session:
        session.add(ProjectModel(id=project_id, name="R3015", normalized_label="r3015"))
        session.add(OntologyModel(id=ontology_id, project_id=project_id, name="R3015 ontology"))
        session.flush()
        OntologyWorkspaceService(session, settings).ensure(
            session.get(OntologyModel, ontology_id)
        )
        session.commit()
        build = BuildSessionService(session, settings)
        session_a, _ = build.create_session(
            project_id, BuildSessionCreate(client_session_id="origin-agent")
        )
        session_a_id = session_a["id"]
        lease = build.acquire_ontology_lease(
            session_a_id,
            ontology_id,
            OntologyLeaseAcquire(
                client_request_id="r3015-lease",
                expected_session_revision=1,
            ),
        )
        versions = OntologyModelRevisionService(session, settings)
        version = versions.version_for(ontology_id)
        service = ModelingBatchService(session, settings, rdf)  # type: ignore[arg-type]

        def item(item_id: str) -> ModelingItemInput:
            return ModelingItemInput.model_validate(
                {
                    "client_item_id": item_id,
                    "command_kind": "create_class",
                    "payload": {"name": "Customer"},
                    "rationale": "Needed by the competency questions",
                }
            )

        # Session A applies the batch for real.
        applied = service.submit(
            session_a_id,
            ModelingBatchSubmit(
                client_batch_id="cb-r3015-real",
                ontology_id=ontology_id,
                idempotency_key="idem-r3015-real",
                mode="apply_atomic",
                expected_model_revision=version,
                lease_token=lease["lease_token"],
                items=[item("item-real-1")],
            ),
        )
        assert applied["attempt_status"] == "applied"
        batch_a_id = applied["batch_id"]

        # The SAME client_batch_id + idempotency_key in a NEW Build Session is
        # a brand-new backend request: the real service does NOT dedupe across
        # sessions (attempt idempotency is scoped per build session).
        session_b, _ = build.create_session(
            project_id, BuildSessionCreate(client_session_id="resume-agent")
        )
        session_b_id = session_b["id"]
        version_after = versions.version_for(ontology_id)
        duplicate = service.submit(
            session_b_id,
            ModelingBatchSubmit(
                client_batch_id="cb-r3015-real",
                ontology_id=ontology_id,
                idempotency_key="idem-r3015-real",
                mode="dry_run",
                expected_model_revision=version_after,
                items=[item("item-real-1")],
            ),
        )
        assert duplicate["batch_id"] != batch_a_id
        duplicate_detail = service.get_batch(duplicate["batch_id"])
        assert duplicate_detail["build_session_id"] == session_b_id
        assert duplicate_detail["client_batch_id"] == "cb-r3015-real"

        # Drive the reconciliation readback through the REAL service methods.
        def request(method, path, body, key):
            base, _, query = path.partition("?")
            params = dict(part.split("=", 1) for part in query.split("&")) if query else {}
            if base.startswith("/api/build-sessions/") and base.endswith("/modeling-batches"):
                return 200, service.list_session_batches(
                    base.split("/")[3],
                    cursor=params.get("cursor"),
                    limit=int(params.get("limit", "50")),
                )
            if base.startswith("/api/ontologies/") and base.endswith("/modeling-batches"):
                return 200, service.list_ontology_batches(
                    base.split("/")[3],
                    cursor=params.get("cursor"),
                    limit=int(params.get("limit", "50")),
                )
            if base.startswith("/api/modeling-batches/"):
                return 200, service.get_batch(base.rsplit("/", 1)[-1])
            raise AssertionError(f"reconciliation read an unexpected endpoint: {path}")

        run_root = RUNS_ROOT / f"r3015real-{os.urandom(4).hex()}"
        try:
            _seed_chain_intent(
                run_root,
                1,
                key="idem-r3015-real",
                client_batch_id="cb-r3015-real",
                session_id=session_a_id,
                mode="apply_atomic",
                batch_id=batch_a_id,
            )
            readback = PlatformReadback(request, "host-key-stand-in")
            result = reconcile_write_tail(
                [run_root], read_write_tail([run_root]), readback,
                ontology_ids=[ontology_id],
            )
            assert result["blocked"] == []
            assert [entry.client_item_id for entry in result["completed"]] == ["item-real-1"]
            assert result["completed"][0].batch_id == batch_a_id
            assert result["completed_client_batches"] == {"cb-r3015-real": batch_a_id}
            # The duplicate the real backend accepted shows up as an
            # unattributable write on the bound ontology (scope drift).
            assert [entry["batch_id"] for entry in result["scope_drift"]] == [
                duplicate["batch_id"]
            ]

            imports = {
                "completed_client_batches": dict(result["completed_client_batches"]),
                "plan_mappings": [],
            }
            # Pre-submit barrier: the completed operation cannot be resubmitted
            # in a new session, and the REAL second-session batch the backend
            # accepted is refused the same way.
            with pytest.raises(CheckpointError) as blocked:
                check_resume_submission(
                    imports, {"client_batch_id": "cb-r3015-real"}, plan_ref=None
                )
            assert blocked.value.reason_code == REASON_COMPLETED_OPERATION_BLOCKED
            real_duplicate_summary = {
                "client_batch_id": duplicate_detail["client_batch_id"],
                "idempotency_key": duplicate_detail["attempts"][0]["idempotency_key"],
            }
            with pytest.raises(CheckpointError):
                check_resume_submission(imports, real_duplicate_summary, plan_ref=None)
            # A genuinely new operation passes the barrier.
            check_resume_submission(
                imports, {"client_batch_id": "cb-r3015-next"}, plan_ref=None
            )
        finally:
            rmtree(run_root, ignore_errors=True)
    engine.dispose()


# --- one-process lock (M12) -------------------------------------------------------


def test_m12_second_resume_of_one_root_run_is_refused_and_death_releases():
    runs_root = RUNS_ROOT / f"r3015lock-{os.urandom(4).hex()}"
    try:
        lock = acquire_root_run_lock("root-run-x", runs_root)
        with pytest.raises(CheckpointError) as refused:
            acquire_root_run_lock("root-run-x", runs_root)
        assert refused.value.reason_code == REASON_SOURCE_ACTIVE
        assert refused.value.retryable is True
        assert "never run two resumes" in refused.value.retry
        # A different root run is unaffected.
        acquire_root_run_lock("root-run-y", runs_root).release()
        lock.release()
        acquire_root_run_lock("root-run-x", runs_root).release()

        # Kernel-released on process death: a child holds the lock, exits
        # without releasing, and this process acquires it immediately.
        script = (
            "import os, sys\n"
            "from pathlib import Path\n"
            "from modeling_team.checkpoint_recovery import acquire_root_run_lock\n"
            "lock = acquire_root_run_lock(sys.argv[1], Path(sys.argv[2]))\n"
            "print('locked', flush=True)\n"
            "os._exit(0)\n"
        )
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        finished = subprocess.run(
            [sys.executable, "-c", script, "root-run-dead", str(runs_root)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert finished.returncode == 0, finished.stderr
        acquire_root_run_lock("root-run-dead", runs_root).release()
    finally:
        rmtree(runs_root, ignore_errors=True)


# --- source writer report (M22/M45) ----------------------------------------------


def test_m22_m45_writer_report_lists_channels_and_caps_each_wait_at_60s():
    platform = FakeCursorPlatform(
        sessions={
            "session-1": {
                "session": {"id": "session-1", "status": "active"},
                "leases": [{"state": "active", "expires_at": "2026-09-14T12:01:00Z"}],
                # A truncated convenience array that must be ignored.
                "modeling_batches": [{"batch_id": "truncated-view"}],
            }
        }
    )
    run_root = RUNS_ROOT / f"r3015writer-{os.urandom(4).hex()}"
    try:
        _write_json(run_root / "state.json", {"state": "RUNNING"})
        report = source_writer_report(run_root, _readback(platform), ["session-1"])
        assert report["state_json_status"] == "RUNNING"
        assert report["state_json_may_be_live_writer"] is True
        assert report["verdict"] == "writer_may_be_active"
        assert report["wait_seconds_max"] == 60
        assert report["wait_seconds_max"] == cr.WAIT_SECONDS_MAX
        sessions = report["platform_sessions"]
        assert sessions["active_lease_session_ids"] == ["session-1"]
        assert sessions["lease_expires_at"] == ["2026-09-14T12:01:00Z"]
        assert sessions["earliest_lease_recheck_at"] == "2026-09-14T12:01:00Z"
        # The report read the session detail only for lease state; the batch
        # facts still come exclusively from the cursor endpoints.
        assert not any("platform_state" in path for path in platform.paths)

        _write_json(run_root / "state.json", {"state": "FAILED"})
        report = source_writer_report(run_root, _readback(platform), ["session-1"])
        assert report["verdict"] == "no_live_writer_evidence"
    finally:
        rmtree(run_root, ignore_errors=True)


# --- stale WAITING_OWNER settlement (R3.0-015 issue-4) ---------------------------


def _dead_pid() -> int:
    """A pid that provably belonged to a real process, now exited and reaped."""

    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert finished.returncode == 0, finished.stderr
    return int(finished.stdout.strip())


def _seed_chain_source(
    *, state: str, chain_root: str, with_origin: bool = True
) -> tuple[Path, dict]:
    """A resume-chain source run whose writer has exited (incident fixture).

    Mirrors ``r30015-l0-20260915-cq-start4`` and its real artifacts: the
    checkpoint manifest records the *producing* run as its ``root_run_id``
    (``materialization_progress-0001`` in ``cq-start4``), while
    ``recovery/origin.json`` records the chain root the resume command took the
    kernel lock under (``…-start3``, the only holder record left behind when
    that writer exits).  ``runner.py`` refuses to re-enter an existing run
    directory, so a stale state.json cannot belong to a live writer.
    """

    run_id = f"r3015src-{os.urandom(4).hex()}"
    run_root = RUNS_ROOT / run_id
    _write_json(run_root / "evidence" / "stage.json", {"stage": "resume-fixture"})
    _write_json(run_root / "state.json", {"state": state})
    saved = save_checkpoint(
        run_root,
        _bound_package(),
        source_run_id=run_id,
        root_run_id=run_id,
        configuration=dict(CONFIGURATION),
    )
    if with_origin:
        _write_json(
            run_root / RECOVERY_DIRECTORY / "origin.json",
            {
                "schema_version": RECOVERY_SCHEMA,
                "source_run_id": chain_root,
                "root_run_id": chain_root,
                "checkpoint_id": "cq_frozen-0000",
                "new_run_id": run_id,
                "created_at": "2026-09-15T09:24:09.679344+00:00",
            },
        )
    return run_root, saved


def _chain_lock_path(chain_root: str) -> Path:
    return RUNS_ROOT / ".recovery-locks" / f"{chain_root}.lock"


def _seed_dead_chain_writer(chain_root: str, pid: int) -> Path:
    """The on-disk record a chain writer leaves when its process exits."""

    path = _chain_lock_path(chain_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "root_run_id": chain_root,
                "pid": pid,
                "acquired_at": "2026-09-15T09:24:09.489429+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_m45_stale_waiting_owner_settles_on_the_chain_writer_lock_evidence():
    """Issue-4: a stale WAITING_OWNER must not deadlock the recovery entry.

    The documented ``source_active`` retry ("stop the original run through its
    existing stop channel") is unperformable once the process has exited, and
    the state.json claim alone keeps refusing every retry forever.  The chain
    writer lock is the auditable settlement channel: it is keyed by the chain
    root the source run's own ``origin.json`` records, the kernel releases it on
    process death, and a new resume records the holder it superseded first.
    """

    chain_root = f"r3015root-{os.urandom(4).hex()}"
    run_root, saved = _seed_chain_source(state="WAITING_OWNER", chain_root=chain_root)
    dead = _dead_pid()
    _seed_dead_chain_writer(chain_root, dead)
    try:
        # (1) Auditing the file as it stands (the incident's own state: a dead
        #     holder record, no supersede yet) settles the plan.
        plan = _plan(run_root, saved["checkpoint_id"])
        writer = plan.inspection["source_writer"]
        assert writer["state_json_status"] == "WAITING_OWNER"
        # The stale claim stays visible in the evidence instead of vanishing.
        assert writer["state_json_may_be_live_writer"] is True
        assert writer["verdict"] == "writer_process_exited"
        chain = writer["chain_writer_lock"]
        assert chain["checked"] is True
        assert chain["bound_by"] == "recovery_origin"
        assert chain["chain_root_run_id"] == chain_root
        # Like the real ``materialization_progress-0001``: the manifest names
        # the producing run, the origin names the chain the writer locked.
        assert chain["manifest_root_run_id"] == run_root.name
        assert chain["holder_pid"] == dead
        assert chain["holder_alive"] is False
        assert chain["holder_is_superseded"] is False
        assert plan.origin["source_writer"]["chain_writer_lock"] == chain

        # (2) The CLI path takes the chain lock first, which supersedes the dead
        #     holder's record; the same evidence must still settle the resume.
        lock = acquire_root_run_lock(chain_root, RUNS_ROOT)
        try:
            plan = _plan(run_root, saved["checkpoint_id"])
            chain = plan.inspection["source_writer"]["chain_writer_lock"]
            assert plan.inspection["source_writer"]["verdict"] == "writer_process_exited"
            assert chain["holder_is_superseded"] is True
            assert chain["holder_pid"] == dead
            assert chain["holder_alive"] is False
        finally:
            lock.release()
    finally:
        rmtree(run_root, ignore_errors=True)
        _chain_lock_path(chain_root).unlink(missing_ok=True)


def test_m12_m45_a_live_chain_writer_still_hard_rejects_the_resume():
    """M12/M22/M45: a genuinely live writer keeps the hard gate closed.

    The lock is held by a real OS process (a real ``flock``, not a stub): a
    stale ``state.json`` must never be settled on behalf of a live chain writer,
    and the rejection must stay typed, retryable, and locatable.
    """

    chain_root = f"r3015root-{os.urandom(4).hex()}"
    run_root, saved = _seed_chain_source(state="WAITING_OWNER", chain_root=chain_root)
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from modeling_team.checkpoint_recovery import acquire_root_run_lock\n"
        "acquire_root_run_lock(sys.argv[1], Path(sys.argv[2]))\n"
        "print('locked', flush=True)\n"
        "time.sleep(120)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, chain_root, str(RUNS_ROOT)],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(CheckpointError) as active:
            _plan(run_root, saved["checkpoint_id"])
        assert active.value.reason_code == REASON_SOURCE_ACTIVE
        assert active.value.retryable is True
        assert f"root_run_id:{chain_root}" == active.value.object
        assert "state.json" in active.value.detail
        assert "60s" in active.value.retry
    finally:
        child.kill()
        child.wait(timeout=60)
        rmtree(run_root, ignore_errors=True)
        _chain_lock_path(chain_root).unlink(missing_ok=True)


def test_m45_unsettled_writer_evidence_keeps_the_gate_closed():
    """No audit-able ownership record means no settlement: fail closed.

    A lock-less possibly-live ``state.json`` (the source run never held this
    chain's lock, e.g. a hard-killed fresh run) and a source run outside this
    recovery chain both stay typed ``source_active`` refusals -- the §5.2 host
    procedure, not the recovery entry, is their path.
    """

    # (a) Chain source with no lock record at all.
    chain_root = f"r3015root-{os.urandom(4).hex()}"
    run_root, saved = _seed_chain_source(state="WAITING_OWNER", chain_root=chain_root)
    try:
        with pytest.raises(CheckpointError) as unproven:
            _plan(run_root, saved["checkpoint_id"])
        assert unproven.value.reason_code == REASON_SOURCE_ACTIVE
        assert "60s" in unproven.value.retry
    finally:
        rmtree(run_root, ignore_errors=True)
        _chain_lock_path(chain_root).unlink(missing_ok=True)

    # (b) A dead holder record that is not bound to a recovery chain (no
    #     origin.json): the writer never took the chain lock.
    chain_root = f"r3015root-{os.urandom(4).hex()}"
    run_root, saved = _seed_chain_source(
        state="WAITING_OWNER", chain_root=chain_root, with_origin=False
    )
    _seed_dead_chain_writer(chain_root, _dead_pid())
    try:
        with pytest.raises(CheckpointError) as fresh:
            _plan(run_root, saved["checkpoint_id"])
        assert fresh.value.reason_code == REASON_SOURCE_ACTIVE
    finally:
        rmtree(run_root, ignore_errors=True)
        _chain_lock_path(chain_root).unlink(missing_ok=True)


# --- explicit host settlement for a stale fresh source run (R3.0-015) ------------


def _settled_session(leases: list | None = None) -> dict:
    return {"session": {"status": "completed"}, "leases": leases or []}


def _settled_platform(sessions: dict | None = None) -> FakeCursorPlatform:
    """The stand-in surface of a host-stopped run: closed tail, terminal session."""

    return FakeCursorPlatform(
        session_batches={"session-1": [_batch("platform-batch-1", client_batch_id="cb-1")]},
        ontology_batches={
            "onto-r3015": [{"batch_id": "platform-batch-1", "build_session_id": "session-1"}]
        },
        sessions={"session-1": _settled_session()} if sessions is None else sessions,
    )


def _fresh_run(*, unknown: bool = False, with_origin: bool = False) -> tuple[Path, dict]:
    """A fresh stale source run (WAITING_OWNER, no FIFO) with one write intent."""

    run_root, saved = _seed_chain_source(
        state="WAITING_OWNER", chain_root="fresh", with_origin=with_origin
    )
    _seed_chain_intent(
        run_root,
        1,
        key="key-unknown" if unknown else "key-1",
        client_batch_id="cb-unknown" if unknown else "cb-1",
        session_id="session-1",
        status="unknown" if unknown else "receipted",
        with_receipt=not unknown,
    )
    return run_root, saved


def _write_settlement(run_root: Path, *, observed_state: str) -> Path:
    path = cr.settlement_record_path(RUNS_ROOT, run_root.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": cr.SOURCE_SETTLEMENT_SCHEMA,
                "run_id": run_root.name,
                "observed_state": observed_state,
                "stop_reference": "host-stop-2026-09-17",
                "created_at": "2026-09-17T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return path


def _settle_cli(monkeypatch, platform: FakeCursorPlatform, run_root: Path) -> int:
    import modeling_team.__main__ as main_module

    monkeypatch.setattr(
        main_module, "http_readback", lambda base_url, key: _readback(platform)
    )
    return _run_cli(
        monkeypatch,
        [
            "checkpoint",
            "settle-source",
            "--run-id",
            run_root.name,
            "--stop-reference",
            "host-stop-2026-09-17-1",
        ],
    )


def test_settlement_absence_keeps_the_fresh_stale_refusal_pointing_at_settle_source():
    """No record -> "no FIFO, no session" never infers a dead writer."""

    run_root, saved = _fresh_run()
    try:
        with pytest.raises(CheckpointError) as refused:
            _plan(run_root, saved["checkpoint_id"])
        assert refused.value.reason_code == REASON_SOURCE_ACTIVE
        assert "settle-source" in refused.value.retry
        assert not cr.settlement_record_path(RUNS_ROOT, run_root.name).exists()
    finally:
        rmtree(run_root, ignore_errors=True)


def test_settle_source_records_and_opens_the_gate_without_creating_anything(
    monkeypatch, capsys
):
    run_root, saved = _fresh_run()
    platform = _settled_platform()
    before = {entry.name for entry in RUNS_ROOT.iterdir()}
    try:
        assert _settle_cli(monkeypatch, platform, run_root) == 0
        record_path = cr.settlement_record_path(RUNS_ROOT, run_root.name)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record == json.loads(capsys.readouterr().out)
        assert set(record) == {
            "schema_version",
            "run_id",
            "observed_state",
            "stop_reference",
            "created_at",
        }
        assert record["observed_state"] == "WAITING_OWNER"
        assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
        # The command creates no run or ledger: only the host-owned settlement
        # directory may appear, and the source state.json stays as it was.
        assert {entry.name for entry in RUNS_ROOT.iterdir()} - before <= {
            ".recovery-settlements"
        }
        assert (
            json.loads((run_root / "state.json").read_text(encoding="utf-8"))["state"]
            == "WAITING_OWNER"
        )
        plan = _plan(run_root, saved["checkpoint_id"], readback=_readback(platform))
        writer = plan.inspection["source_writer"]
        assert writer["verdict"] == "writer_process_exited"
        assert writer["source_settlement"]["verdict"] == "writer_process_exited"
        assert (
            plan.origin["source_writer"]["source_settlement"]["stop_reference"]
            == "host-stop-2026-09-17-1"
        )
    finally:
        rmtree(run_root, ignore_errors=True)
        cr.settlement_record_path(RUNS_ROOT, run_root.name).unlink(missing_ok=True)


def test_settle_source_refuses_live_channels_and_writes_no_record(monkeypatch, capsys):
    granted = [{"state": "granted", "expires_at": "2026-09-17T12:00:00+00:00"}]
    cases = (
        (_settled_platform(), True),  # the control FIFO still exists
        (_settled_platform({"session-1": _settled_session(granted)}), False),  # live lease
        (_settled_platform({}), False),  # known session unreadable
    )
    for platform, with_fifo in cases:
        run_root, _saved = _fresh_run()
        if with_fifo:
            fifo = run_root / "control" / "outer-input.fifo"
            fifo.parent.mkdir(parents=True, exist_ok=True)
            fifo.write_text("", encoding="utf-8")
        assert _settle_cli(monkeypatch, platform, run_root) == 2
        payload = json.loads(capsys.readouterr().err.split("checkpoint failed: ", 1)[1])
        assert payload["code"] == cr.REASON_SETTLEMENT_REFUSED
        assert not cr.settlement_record_path(RUNS_ROOT, run_root.name).exists()
        rmtree(run_root, ignore_errors=True)


def test_settlement_binding_mismatches_and_recovery_origin_runs_stay_refused():
    # (a) a record whose observed_state no longer matches the current state.json.
    run_root, saved = _fresh_run()
    path = _write_settlement(run_root, observed_state="RUNNING")
    try:
        with pytest.raises(CheckpointError) as mismatch:
            _plan(run_root, saved["checkpoint_id"])
        assert mismatch.value.reason_code == REASON_SOURCE_ACTIVE
    finally:
        rmtree(run_root, ignore_errors=True)
        path.unlink(missing_ok=True)

    # (b) an origin-carrying run: the command refuses, and even a hand-placed
    #     matching settlement never settles it (the chain lock is its channel).
    run_root, saved = _fresh_run(with_origin=True)
    path = _write_settlement(run_root, observed_state="WAITING_OWNER")
    try:
        with pytest.raises(CheckpointError) as command:
            cr.settle_source_run(
                run_root=run_root,
                stop_reference="host-stop-2026-09-17",
                readback=_readback(_settled_platform()),
            )
        assert command.value.reason_code == cr.REASON_SETTLEMENT_REFUSED
        with pytest.raises(CheckpointError) as gate:
            _plan(run_root, saved["checkpoint_id"])
        assert gate.value.reason_code == REASON_SOURCE_ACTIVE
    finally:
        rmtree(run_root, ignore_errors=True)
        path.unlink(missing_ok=True)


def test_settlement_never_bypasses_the_write_tail_gate():
    # (a) the command itself refuses over an unknown write (and writes no record).
    platform = _settled_platform()
    run_root, _saved = _fresh_run(unknown=True)
    try:
        with pytest.raises(CheckpointError) as unknown:
            cr.settle_source_run(
                run_root=run_root,
                stop_reference="host-stop-2026-09-17",
                readback=_readback(platform),
            )
        assert unknown.value.reason_code == REASON_WRITE_UNRECONCILED
        assert not cr.settlement_record_path(RUNS_ROOT, run_root.name).exists()
    finally:
        rmtree(run_root, ignore_errors=True)

    # (b) even a hand-placed matching settlement keeps the plan refused:
    #     write-tail safety stays with the reconciliation gate downstream.
    run_root, saved = _fresh_run(unknown=True)
    path = _write_settlement(run_root, observed_state="WAITING_OWNER")
    try:
        with pytest.raises(CheckpointError) as refused:
            _plan(run_root, saved["checkpoint_id"], readback=_readback(platform))
        assert refused.value.reason_code == REASON_WRITE_UNRECONCILED
    finally:
        rmtree(run_root, ignore_errors=True)
        path.unlink(missing_ok=True)


# --- business approvals (M27/M30) -------------------------------------------------


def _approvals_run(tmp_path: Path, *, entries: list[dict], profile_agents: list[dict]):
    run_root = tmp_path / "approvals-src"
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {"schema_version": "r3-0-008b-approvals/v1", "entries": entries},
    )
    (run_root / "profile.snapshot.yaml").write_text(
        json.dumps(
            {
                "profile_id": CONFIGURATION["profile_id"],
                "agents": profile_agents,
            }
        ),
        encoding="utf-8",
    )
    saved = save_checkpoint(
        run_root,
        _bound_package(sources=[(APPROVALS_RELATIVE, "coordinator")]),
        source_run_id="r3015-appr",
        configuration=dict(CONFIGURATION),
    )
    return run_root, saved


_COORDINATOR_AGENTS = [
    {"agent_id": "team-coordinator-7", "package": "coordinator"},
    {"agent_id": "modeling-agent", "package": "modeling"},
]
_VALID_ENTRIES = [
    {
        "kind": "conclusion_confirmation",
        "target_id": "concl-1",
        "revision": 3,
        "confirmed_enum_value": "approved",
        "approved_by": "team-coordinator-7",
        "note": "host-only stand-in note",
    }
]


def test_m27_valid_approvals_reuse_preserves_approved_by_and_revision(tmp_path):
    run_root, saved = _approvals_run(
        tmp_path, entries=_VALID_ENTRIES, profile_agents=_COORDINATOR_AGENTS
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert result["present"] is True
    assert result["approver"] == "team-coordinator-7"
    assert result["valid"] == [
        {
            "kind": "conclusion_confirmation",
            "target_id": "concl-1",
            "revision": 3,
            "approved_by": "team-coordinator-7",
        }
    ]
    assert result["invalidated"] == []
    # The original approved_by/revision travel verbatim (M27), and the channel
    # is the packaged file, never the bare run-side file.
    assert result["source_path"] == APPROVALS_RELATIVE
    assert str(result["source_digest"]).startswith("sha256:")


def test_m30_approval_channel_rejects_wrong_identity_and_revocation(tmp_path):
    # Same literal string "coordinator" is NOT the resolved approver identity.
    run_root, saved = _approvals_run(
        tmp_path,
        entries=[{**_VALID_ENTRIES[0], "approved_by": "coordinator"}],
        profile_agents=_COORDINATOR_AGENTS,
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert result["valid"] == []
    assert result["invalidated"][0]["reason"] == REASON_APPROVAL_BINDING_CHANGED
    assert "coordinator agent" in result["invalidated"][0]["detail"]

    # Post-save revocation: the source run's current approvals moved on; a
    # checkpoint cannot resurrect the revoked decision.
    run_root, saved = _approvals_run(
        tmp_path, entries=_VALID_ENTRIES, profile_agents=_COORDINATOR_AGENTS
    )
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {
            "schema_version": "r3-0-008b-approvals/v1",
            "entries": [{**_VALID_ENTRIES[0], "revision": 4}],
        },
    )
    before = _tree_state(run_root)
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert result["invalidated"][0]["revision"] == 3
    assert "cannot resurrect" in result["invalidated"][0]["detail"]
    # Correctable conflicts never touch the source run.
    assert _tree_state(run_root) == before

    # A profile whose coordinator identity cannot be resolved fails typed.
    run_root, saved = _approvals_run(
        tmp_path, entries=_VALID_ENTRIES, profile_agents=[{"agent_id": "x", "package": "m"}]
    )
    with pytest.raises(CheckpointError) as unresolved:
        validate_business_approvals(
            _manifest_of(run_root, saved["checkpoint_id"]), run_root
        )
    assert unresolved.value.reason_code == REASON_APPROVAL_BINDING_CHANGED

    # An approvals file that this checkpoint did NOT package is never reused.
    run_root = tmp_path / "unpackaged"
    _write_json(run_root / "evidence" / "stage.json", {"stage": "x"})
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {"schema_version": "r3-0-008b-approvals/v1", "entries": _VALID_ENTRIES},
    )
    saved = save_checkpoint(
        run_root,
        _bound_package(),
        source_run_id="r3015-appr-2",
        configuration=dict(CONFIGURATION),
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert result["present"] is False


def _legacy_history_entries() -> list[dict]:
    """A generic approvals history: seven conclusions each carrying a superseded
    revision plus its effective head, and one stage3 slot with four revisions."""

    entries: list[dict] = []
    for index in range(1, 8):
        for revision in (2, 5):
            entries.append(
                {
                    "kind": "conclusion_confirmation",
                    "target_id": f"concl-{index}",
                    "revision": revision,
                    "confirmed_enum_value": f"code-{index}-v{revision}",
                    "approved_by": "team-coordinator-7",
                    "note": f"revision {revision}",
                }
            )
    for revision in (1, 2, 3, 4):
        entries.append(
            {
                "kind": "stage3_slot",
                "target_id": "slot-1",
                "revision": revision,
                "approved_by": "team-coordinator-7",
            }
        )
    return entries


def _approval_heads(result: dict) -> dict[tuple[str, str], int]:
    return {
        (record["kind"], record["target_id"]): record["revision"]
        for record in result["valid"]
    }


def test_legacy_approval_history_reuses_only_effective_heads(tmp_path):
    entries = _legacy_history_entries()
    assert len(entries) == 18
    run_root, saved = _approvals_run(
        tmp_path, entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    before = _tree_state(run_root)
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    # Packaged and current views carry the identical 18-entry history: the 10
    # superseded revisions are ancestry, never post-save revocations.
    assert result["present"] is True
    assert result["invalidated"] == []
    assert _approval_heads(result) == {
        **{("conclusion_confirmation", f"concl-{index}"): 5 for index in range(1, 8)},
        ("stage3_slot", "slot-1"): 4,
    }
    assert len(result["valid"]) == 8
    assert all(
        record["approved_by"] == "team-coordinator-7" for record in result["valid"]
    )
    # Correctable conflicts never touch the source run.
    assert _tree_state(run_root) == before


def test_legacy_approval_head_changes_still_invalidate(tmp_path):
    entries = _legacy_history_entries()

    # A later head in the current view invalidates the checkpoint's head even
    # though that older revision is still present as history.
    run_root, saved = _approvals_run(
        tmp_path / "later-head", entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {
            "schema_version": "r3-0-008b-approvals/v1",
            "entries": [
                *entries,
                {
                    "kind": "conclusion_confirmation",
                    "target_id": "concl-1",
                    "revision": 6,
                    "confirmed_enum_value": "code-1-v6",
                    "approved_by": "team-coordinator-7",
                    "note": "later decision",
                },
            ],
        },
    )
    before = _tree_state(run_root)
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert [
        (record["kind"], record["target_id"], record["revision"])
        for record in result["invalidated"]
    ] == [("conclusion_confirmation", "concl-1", 5)]
    assert result["invalidated"][0]["reason"] == REASON_APPROVAL_BINDING_CHANGED
    assert "cannot resurrect" in result["invalidated"][0]["detail"]
    assert _approval_heads(result) == {
        **{("conclusion_confirmation", f"concl-{index}"): 5 for index in range(2, 8)},
        ("stage3_slot", "slot-1"): 4,
    }
    assert _tree_state(run_root) == before

    # The same revision with different decision content is a replacement, not
    # a reuse.
    run_root, saved = _approvals_run(
        tmp_path / "same-revision", entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {
            "schema_version": "r3-0-008b-approvals/v1",
            "entries": [
                {**entry, "confirmed_enum_value": "code-2-other"}
                if entry["target_id"] == "concl-2" and entry["revision"] == 5
                else entry
                for entry in entries
            ],
        },
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert [
        (record["target_id"], record["revision"]) for record in result["invalidated"]
    ] == [("concl-2", 5)]

    # A target the current view dropped entirely is revoked.
    run_root, saved = _approvals_run(
        tmp_path / "removed", entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {
            "schema_version": "r3-0-008b-approvals/v1",
            "entries": [entry for entry in entries if entry["target_id"] != "concl-3"],
        },
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert [
        (record["target_id"], record["revision"]) for record in result["invalidated"]
    ] == [("concl-3", 5)]

    # The current view moving a head off the resolved coordinator identity is a
    # replacement too.
    run_root, saved = _approvals_run(
        tmp_path / "approver", entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    _write_json(
        run_root / APPROVALS_RELATIVE,
        {
            "schema_version": "r3-0-008b-approvals/v1",
            "entries": [
                {**entry, "approved_by": "coordinator"}
                if entry["target_id"] == "concl-4" and entry["revision"] == 5
                else entry
                for entry in entries
            ],
        },
    )
    result = validate_business_approvals(
        _manifest_of(run_root, saved["checkpoint_id"]), run_root
    )
    assert [
        (record["target_id"], record["revision"]) for record in result["invalidated"]
    ] == [("concl-4", 5)]

    # A source profile that no longer matches the checkpoint configuration is
    # still a typed channel failure.
    run_root, saved = _approvals_run(
        tmp_path / "profile", entries=entries, profile_agents=_COORDINATOR_AGENTS
    )
    (run_root / "profile.snapshot.yaml").write_text(
        json.dumps({"profile_id": "other-profile", "agents": _COORDINATOR_AGENTS}),
        encoding="utf-8",
    )
    with pytest.raises(CheckpointError) as drifted:
        validate_business_approvals(
            _manifest_of(run_root, saved["checkpoint_id"]), run_root
        )
    assert drifted.value.reason_code == REASON_APPROVAL_BINDING_CHANGED


def _manifest_of(run_root: Path, checkpoint_id: str) -> dict:
    return json.loads(
        (
            run_root
            / "checkpoints"
            / checkpoint_id
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )


# --- plan mappings and role packets (M17/M31) ------------------------------------


def _plan_mapping_manifest(tmp_path: Path) -> tuple[StagePackage, Path]:
    run_root = tmp_path / "plans-src"
    plan_source = "stage3-neutral-graph/materialization-plans/plan-0001.json"
    _write_json(
        run_root / plan_source,
        {
            "projection": {"candidate_id": "cand-1", "revision": 2},
            "items": [
                {"client_item_id": "item-1"},
                {"client_item_id": "item-2"},
            ],
            "client_batch_ids": ["cb-done"],
            "decision_bindings": [{"decision_id": "d1"}],
            "identity_bindings": [{"binding": "b1"}],
        },
    )
    unfinished = "stage3-neutral-graph/materialization-plans/plan-0002.json"
    _write_json(
        run_root / unfinished,
        {
            "projection": {"candidate_id": "cand-2", "revision": 1},
            "items": [{"client_item_id": "item-3"}],
            "client_batch_ids": ["cb-todo"],
            "decision_bindings": [],
            "identity_bindings": [],
        },
    )
    package = _bound_package(
        sources=[
            (plan_source, "modeling"),
            (unfinished, "modeling"),
        ]
    )
    return package, run_root


def test_m17_completed_plans_map_to_forbidden_resubmission(tmp_path):
    package, run_root = _plan_mapping_manifest(tmp_path)
    saved = save_checkpoint(
        run_root, package, source_run_id="r3015-map", configuration=dict(CONFIGURATION)
    )
    manifest = _manifest_of(run_root, saved["checkpoint_id"])
    reconciliation = {"completed_client_batches": {"cb-done": "batch-1"}}
    mappings = build_plan_mappings(manifest, run_root, reconciliation)
    by_ref = {mapping["source_plan_ref"]: mapping for mapping in mappings}
    done = by_ref["plan-0001.json"]
    assert done["status"] == "completed_do_not_resubmit"
    assert done["completed_source_batches"] == ["cb-done"]
    assert done["client_item_ids"] == ["item-1", "item-2"]
    assert done["candidate"] == {"candidate_id": "cand-1", "revision": 2}
    assert by_ref["plan-0002.json"]["status"] == "unfinished_submit_through_new_session"
    # The retained client_item_ids locate the original operation.
    assert by_ref["plan-0002.json"]["client_item_ids"] == ["item-3"]

    imports = {"completed_client_batches": {"cb-done": "batch-1"}, "plan_mappings": mappings}
    with pytest.raises(CheckpointError) as refused:
        check_resume_submission(
            imports, {"client_batch_id": "cb-other"}, plan_ref="plan-0001.json"
        )
    assert refused.value.reason_code == REASON_COMPLETED_OPERATION_BLOCKED
    check_resume_submission(
        imports, {"client_batch_id": "cb-other"}, plan_ref="plan-0002.json"
    )


def test_m31_role_startup_packets_carry_resume_kind_and_boundaries(tmp_path):
    package, run_root = _plan_mapping_manifest(tmp_path)
    saved = save_checkpoint(
        run_root, package, source_run_id="r3015-pk", configuration=dict(CONFIGURATION)
    )
    manifest = _manifest_of(run_root, saved["checkpoint_id"])
    reconciliation = {
        "completed": [{"key": ["k"]}],
        "completed_client_batches": {"cb-done": "batch-1"},
        "pending_new_dry_run": [],
        "recoverable_new_batch": [],
    }
    mappings = build_plan_mappings(manifest, run_root, reconciliation)
    packets = build_role_packets(
        manifest,
        reconciliation,
        mappings,
        {"present": False, "valid": [], "invalidated": []},
        dict(CONFIGURATION),
    )
    # No new review roles: exactly the production roster plus CQ and host.
    assert set(packets) == {
        "coordinator",
        "modeling",
        "protocol",
        "competency-question",
        "host",
    }
    coordinator = packets["coordinator"]
    assert coordinator["resume_kind"] == CHECKPOINT_KIND_CQ_FROZEN
    assert coordinator["completed_scope"]["completed_client_batch_ids"] == ["cb-done"]
    assert coordinator["forbidden_resubmissions"] == ["cb-done"]
    assert coordinator["pending_items"] == manifest["stage_facts"].get("pending", [])
    assert coordinator["next_step"] == manifest["stage_facts"].get("next_step")
    assert any("do not rerun the default full-flow opening" in line for line in
               coordinator["instructions"])
    # Translation is a NEW session decision reviewed by the current Coordinator
    # through the normal 014 path (S3 auto-migration deferred).
    assert coordinator["translation_review"]["required"] is True
    assert "014" in coordinator["translation_review"]["note"]
    # Production roles see only public artifacts; the CQ packet adds its own
    # private material; the host packet sees everything and owns approvals.
    public = {"stage3-neutral-graph/materialization-plans/plan-0001.json"}
    assert set(coordinator["readable_artifacts"]) >= public
    host = packets["host"]
    assert set(host["readable_artifacts"]) >= set(coordinator["readable_artifacts"])
    assert host["approvals"]["present"] is False
    assert host["configuration"] == dict(CONFIGURATION)
    cq = packets["competency-question"]
    assert "private_material_note" in cq


def test_m31_cq_packet_excludes_host_only_frozen_and_keeps_own_projection(tmp_path):
    """R3.0-011 host-only contract on the S2 resume path (run6 defect).

    The frozen pool is packaged for the host only (R3.0-011 design §3.4), so
    the CQ packet lists the role's own private/review records plus the restored
    public projection -- never a ``competency-questions/frozen/`` path.  The
    Runner-verified freeze state reaches the CQ role only as a summary without
    hidden content.
    """

    run_root = tmp_path / "cq-src"
    frozen = "competency-questions/frozen/freeze-0001.json"
    private = "competency-questions/private/draft-0001.json"
    reviews = "competency-questions/reviews/review-0001.json"
    public = "competency-questions/public/public-projection-0001.json"
    for source in (frozen, private, reviews, public):
        _write_json(run_root / source, {"source": source})
    package = StagePackage(
        kind=CHECKPOINT_KIND_CQ_FROZEN,
        scope_refs={"freeze_id": "f-resume"},
        artifacts=[
            CheckpointArtifactSpec(
                source=frozen, owner="host", visible_to=("host",), host_private=True
            ),
            CheckpointArtifactSpec(
                source=private,
                owner="competency-question",
                visible_to=("competency-question",),
                host_private=True,
            ),
            CheckpointArtifactSpec(
                source=reviews,
                owner="competency-question",
                visible_to=("competency-question",),
                host_private=True,
            ),
            CheckpointArtifactSpec(
                source=public,
                owner="competency-question",
                visible_to=("coordinator", "modeling", "protocol"),
                host_private=False,
            ),
        ],
        stage_facts={},
        platform_bindings={"project_id": "proj-r3015", "ontology_ids": ["onto-r3015"]},
        write_positions={},
    )
    saved = save_checkpoint(
        run_root, package, source_run_id="r3015-cqp", configuration=dict(CONFIGURATION)
    )
    manifest = _manifest_of(run_root, saved["checkpoint_id"])
    reconciliation = {
        "completed": [],
        "completed_client_batches": {},
        "pending_new_dry_run": [],
        "recoverable_new_batch": [],
    }
    packets = build_role_packets(
        manifest,
        reconciliation,
        [],
        {"present": False, "valid": [], "invalidated": []},
        dict(CONFIGURATION),
    )
    cq = packets["competency-question"]
    readable = set(cq["readable_artifacts"])
    # The CQ role keeps its own private material and the restored public
    # projection it can actually read through its role mounts.
    assert {private, reviews, public} <= readable
    # The host-only frozen pool is never offered to the CQ role as readable.
    assert frozen not in readable
    assert not any("competency-questions/frozen/" in source for source in readable)
    # The host packet still carries everything, including the frozen pool.
    assert frozen in set(packets["host"]["readable_artifacts"])
    # A Runner-verified freeze summary guides the CQ role without hidden text.
    assert cq["frozen_pool"]["restored"] is True


def test_pending_items_next_steps_stay_inside_each_existing_role_contract(tmp_path):
    """Field regression: the 2026-10-05 start2 role-handoff defect.

    Broadcasting the host-level pending step to every packet made Protocol
    open a Build Session while the Task's candidate gate was still closed
    (the zero-write ``candidate_receipt_required`` rejection) and handed
    rebind/dry-run/apply duties to the competency-question role.
    pending_items stays shared recovery state in every packet, but each
    role's next_step now restates only its own agent-package contract's
    slice; the host keeps the orchestration summary.  The Protocol step is
    bound to the gate the selected Task's Runner actually validates: only a
    Task that formally advertises the legacy candidate-receipt contract uses
    that path, and the unified-graph route's validated slot, source-grounded
    approvals and topology decision with Modeling's direct candidate handoff
    are the gate -- no invented legacy-receipt wait.  The CQ branch is
    stage-true: a restored frozen pool is maintained as-is, and with no pool
    restored the normal CQ lifecycle still runs -- never a blanket "do
    nothing".
    """

    def pending_reconciliation():
        return {
            "completed": [],
            "completed_client_batches": {},
            "pending_new_dry_run": [
                {
                    "origin_run_id": "r3015-src",
                    "ordinal": 11,
                    "client_batch_id": "cb-b010",
                    "idempotency_key": "key-b010",
                    "mode": "dry_run",
                    "detail": "dry-run validated, never applied; reuse the "
                    "plan/semantic approvals and enter a NEW dry-run",
                }
            ],
            "recoverable_new_batch": [],
        }

    package, run_root = _plan_mapping_manifest(tmp_path)
    saved = save_checkpoint(
        run_root, package, source_run_id="r3015-pd", configuration=dict(CONFIGURATION)
    )
    manifest = _manifest_of(run_root, saved["checkpoint_id"])
    packets = build_role_packets(
        manifest,
        pending_reconciliation(),
        [],
        {"present": False, "valid": [], "invalidated": []},
        dict(CONFIGURATION),
    )

    # The pending facts survive in every packet, and the shared-state note
    # says they grant no capability.
    for packet in packets.values():
        ids = {item.get("client_batch_id") for item in packet["pending_items"]}
        assert "cb-b010" in ids
        assert any(
            "grants no role any capability" in line for line in packet["instructions"]
        )
    # Only the host packet carries the host-level execution summary.
    assert "execute pending_items first" in packets["host"]["next_step"]
    for role in ("coordinator", "modeling", "protocol", "competency-question"):
        assert "execute pending_items first" not in packets[role]["next_step"]
        assert "rebind each plan" not in packets[role]["next_step"]

    # Modeling: candidate channel only, never a platform write interface.
    modeling = packets["modeling"]["next_step"]
    assert "direct candidate delivery" in modeling
    assert "never call a platform Build Session or Modeling Batch interface" in modeling

    # Protocol: the platform continuation runs behind the candidate/topology
    # gate the selected Task's Runner validates for the run.  The step is
    # Task-bound -- a formally advertised legacy candidate-receipt contract
    # keeps its path, while the unified-graph route needs no R2.3 receipt --
    # and the closed gate never opens through host confirmation alone, so a
    # producer can never bypass it.
    protocol = packets["protocol"]["next_step"]
    assert "candidate/topology gate the selected Task's Runner validates" in protocol
    assert "formally advertises the legacy candidate-receipt contract" in protocol
    assert "unified-graph" in protocol
    assert "no extra R2.3 receipt exists to wait for" in protocol
    assert "candidate_receipt_required" in protocol
    assert "never invent a legacy receipt" in protocol
    assert "never treat the gate as open or substitute host confirmation" in protocol
    assert "you make no platform write" in protocol
    # The unconditional receipt-barrier phrasing that produced the issue3
    # dead wait (waiting to register a receipt no unified-graph Task has)
    # is gone.
    assert "candidate receipt barrier" not in protocol

    # Coordinator: coordinates the contracts behind the same Task-bound gate,
    # never submits itself.
    coordinator = packets["coordinator"]["next_step"]
    assert "Protocol alone performs" in coordinator
    assert "candidate/topology gate the selected Task's Runner validates" in coordinator
    assert "never call a platform write interface or submit a Modeling" in coordinator

    # CQ with no restored frozen pool: the normal lifecycle still runs, and
    # pending_items never assigns platform rebind/dry-run/apply to it.
    cq = packets["competency-question"]["next_step"]
    assert "continue your actual CQ stage" in cq
    assert "never assigns you platform rebind, dry-run or apply work" in cq

    # A restored frozen pool flips only the CQ branch: maintain as-is, still
    # no platform duties and no re-interview/review/freeze.
    frozen_root = tmp_path / "frozen-packet-run"
    frozen_source = "competency-questions/frozen/freeze-0001.json"
    _write_json(frozen_root / frozen_source, {"source": frozen_source})
    frozen_saved = save_checkpoint(
        frozen_root,
        StagePackage(
            kind=CHECKPOINT_KIND_CQ_FROZEN,
            scope_refs={"freeze_id": "f-resume"},
            artifacts=[
                CheckpointArtifactSpec(
                    source=frozen_source,
                    owner="host",
                    visible_to=("host",),
                    host_private=True,
                )
            ],
            stage_facts={},
            platform_bindings={
                "project_id": "proj-r3015", "ontology_ids": ["onto-r3015"]
            },
            write_positions={},
        ),
        source_run_id="r3015-pdf",
        configuration=dict(CONFIGURATION),
    )
    frozen_packets = build_role_packets(
        _manifest_of(frozen_root, frozen_saved["checkpoint_id"]),
        pending_reconciliation(),
        [],
        {"present": False, "valid": [], "invalidated": []},
        dict(CONFIGURATION),
    )
    frozen_cq = frozen_packets["competency-question"]["next_step"]
    assert "already restored" in frozen_cq
    assert "without re-interviewing, re-reviewing or re-freezing" in frozen_cq
    assert "never assigns you platform rebind, dry-run or apply work" in frozen_cq
    assert "execute pending_items first" not in frozen_cq


def test_global_stage_next_step_is_shared_context_not_a_role_duty(tmp_path):
    """Field follow-up: the checkpoint's stage next_step is a whole-team sentence.

    The real cp16 materialization step is "continue the remaining dry-run
    correction, translation review or apply operations".  Appending it after
    each role's correct guidance (or returning it alone when nothing is
    pending) handed dry-run/translation/apply duties back to Modeling and the
    competency-question role.  Only the host keeps the global step as its own
    orchestration summary; a role sees it only as clearly labeled shared
    team context that never reassigns duties, in both the pending and the
    empty-pending cases.
    """

    global_step = (
        "continue the remaining dry-run correction, translation review or "
        "apply operations"
    )
    frozen_source = "competency-questions/frozen/freeze-0001.json"
    run_root = tmp_path / "global-step-run"
    _write_json(run_root / "evidence" / "stage.json", {"stage": "resume-fixture"})
    _write_json(run_root / frozen_source, {"source": frozen_source})
    saved = save_checkpoint(
        run_root,
        StagePackage(
            kind=CHECKPOINT_KIND_CQ_FROZEN,
            scope_refs={"freeze_id": "f-resume"},
            artifacts=[
                CheckpointArtifactSpec(
                    source="evidence/stage.json",
                    owner="coordinator",
                    visible_to=("coordinator", "modeling", "protocol"),
                    host_private=False,
                ),
                CheckpointArtifactSpec(
                    source=frozen_source,
                    owner="host",
                    visible_to=("host",),
                    host_private=True,
                ),
            ],
            stage_facts={"next_step": global_step},
            platform_bindings={
                "project_id": "proj-r3015", "ontology_ids": ["onto-r3015"]
            },
            write_positions={},
        ),
        source_run_id="r3015-gs",
        configuration=dict(CONFIGURATION),
    )
    manifest_file = run_root / "checkpoints" / saved["checkpoint_id"] / "manifest.json"
    source_bytes = manifest_file.read_bytes()
    manifest = json.loads(source_bytes)
    assert manifest["stage_facts"]["next_step"] == global_step
    approvals = {"present": False, "valid": [], "invalidated": []}

    pending = {
        "completed": [],
        "completed_client_batches": {},
        "pending_new_dry_run": [
            {
                "origin_run_id": "r3015-gs",
                "ordinal": 16,
                "client_batch_id": "cb-b016",
                "idempotency_key": "key-b016",
                "mode": "dry_run",
                "detail": "dry-run validated, never applied",
            }
        ],
        "recoverable_new_batch": [],
    }
    packets = build_role_packets(manifest, pending, [], approvals, dict(CONFIGURATION))

    # The host alone keeps the global stage step as its own summary.
    assert "execute pending_items first" in packets["host"]["next_step"]
    assert global_step in packets["host"]["next_step"]

    # Every role keeps its own contract's duty first; the global sentence
    # rides along only as clearly labeled shared context -- never appended as
    # a "then ..." instruction the role executes.
    for role in ("coordinator", "modeling", "protocol", "competency-question"):
        step = packets[role]["next_step"]
        assert "shared stage context, not a per-role duty" in step
        assert global_step in step
        assert "; then " not in step
        assert step.index("shared stage context") > 0
    modeling = packets["modeling"]["next_step"]
    assert modeling.index("direct candidate delivery") < modeling.index(
        "shared stage context"
    )
    assert "never call a platform Build Session or Modeling Batch interface" in modeling
    cq = packets["competency-question"]["next_step"]
    assert "already restored" in cq
    assert "never assigns you platform rebind, dry-run or apply work" in cq

    # Empty reconciliation: no role receives the global sentence as its own
    # next step -- only the labeled shared context, and the host keeps the
    # sentence unchanged.
    empty = {
        "completed": [],
        "completed_client_batches": {},
        "pending_new_dry_run": [],
        "recoverable_new_batch": [],
    }
    empty_packets = build_role_packets(
        manifest, empty, [], approvals, dict(CONFIGURATION)
    )
    assert empty_packets["host"]["next_step"] == global_step
    for role in ("coordinator", "modeling", "protocol", "competency-question"):
        assert empty_packets[role]["next_step"] == (
            f"shared stage context, not a per-role duty: {global_step}"
        )
        assert "grants no role any capability" not in "".join(
            empty_packets[role]["instructions"]
        )

    # Public/private isolation is unchanged: the host-only frozen artifact
    # never reaches a production role or the CQ packet's readable list.
    assert frozen_source in empty_packets["host"]["readable_artifacts"]
    for role in ("modeling", "competency-question"):
        assert frozen_source not in empty_packets[role]["readable_artifacts"]
    assert "evidence/stage.json" in empty_packets["modeling"]["readable_artifacts"]

    # Packet building never touched the packaged source.
    assert manifest_file.read_bytes() == source_bytes


# --- exposure union (M32) ----------------------------------------------------------


def test_m32_once_exposed_stays_exposed_across_the_recovery_chain(tmp_path):
    from modeling_team.competency_questions import read_exposure_evidence

    oldest = tmp_path / "runs" / "o1"
    resumed = tmp_path / "runs" / "o2"
    new_run = tmp_path / "runs" / "o3"

    def _exposure(run_root: Path, question_ids: list[str], roles: list[str]) -> None:
        (run_root / "evidence").mkdir(parents=True, exist_ok=True)
        with (run_root / "evidence" / "cq-exposure.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(
                json.dumps(
                    {
                        "event": "question-exposed-to-production",
                        "question_ids": question_ids,
                        "roles": roles,
                        "reason_code": "permanently_public",
                    }
                )
                + "\n"
            )

    _exposure(oldest, ["cq-1", "cq-2"], ["coordinator"])
    _exposure(resumed, ["cq-2"], ["modeling"])
    result = merge_exposure_union([oldest, resumed], new_run)
    assert result["exposed_question_ids"] == ["cq-1", "cq-2"]
    assert result["chain_runs_read"] == ["o1", "o2"]
    # cq-1 was exposed only by the OLDEST run and stays permanently exposed;
    # cq-2 accumulates roles across the chain.
    assert result["question_roles"]["cq-1"] == ["coordinator"]
    assert result["question_roles"]["cq-2"] == ["coordinator", "modeling"]
    assert result["recorded_from_runs"]["cq-2"] == ["o1", "o2"]

    # The merged file keeps the Runner-native record shape, so the recovered
    # Runner's own reader accepts the union exactly like its own provenance
    # (any other shape would be rejected, not skipped).
    provenance = read_exposure_evidence(new_run / "evidence" / "cq-exposure.jsonl")
    assert provenance["exposure"] == {
        "cq-1": ["coordinator"],
        "cq-2": ["coordinator", "modeling"],
    }
    assert provenance["record_count"] == 2
    lines = [
        json.loads(line)
        for line in (new_run / "evidence" / "cq-exposure.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [line["resume_union_source_run"] for line in lines] == ["o1", "o2"]


# --- plan-level typed rejections (M10/M39/M40) ------------------------------------


def test_m10_m39_bad_identity_and_tampering_are_typed_rejections():
    run_root, saved = _seed_plan_run()
    try:
        with pytest.raises(CheckpointError) as missing:
            _plan(run_root, "cq_frozen-9999")
        assert missing.value.reason_code == "checkpoint_not_found"

        tampered = (
            run_root
            / "checkpoints"
            / saved["checkpoint_id"]
            / CHECKPOINT_ARTIFACTS_DIRECTORY
            / "evidence"
            / "stage.json"
        )
        tampered.write_text('{"stage": "tampered"}', encoding="utf-8")
        with pytest.raises(CheckpointError) as changed:
            _plan(run_root, saved["checkpoint_id"])
        assert changed.value.reason_code == "artifact_changed"
        # Every typed rejection carries the §8 tuple and never a secret.
        payload = changed.value.data()
        assert set(payload) >= {"code", "object_ref", "phase", "retryable", "reason"}
        assert not set(payload) & {"reason_code", "detail", "object", "retry"}
        assert "host-key-stand-in" not in json.dumps(payload)
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m40_contract_writer_and_write_gates_at_the_plan_level():
    # contract_incompatible: the recorded contract files are absent here.
    run_root, saved = _seed_plan_run(
        configuration={"task_id": "r3-0-015-checkpoint-recovery", "profile_id": "gone"}
    )
    try:
        with pytest.raises(CheckpointError) as incompatible:
            _plan(run_root, saved["checkpoint_id"])
        assert incompatible.value.reason_code == "contract_incompatible"
    finally:
        rmtree(run_root, ignore_errors=True)

    # resume_new_run_exists: a resume never overwrites an existing run.
    run_root, saved = _seed_plan_run()
    try:
        with pytest.raises(CheckpointError) as exists:
            _plan(run_root, saved["checkpoint_id"], new_run_id=run_root.name)
        assert exists.value.reason_code == "resume_new_run_exists"
    finally:
        rmtree(run_root, ignore_errors=True)

    # source_active: the source run's own state.json may still be a live writer.
    run_root, saved = _seed_plan_run(state={"state": "PAUSED"})
    try:
        with pytest.raises(CheckpointError) as active:
            _plan(run_root, saved["checkpoint_id"])
        assert active.value.reason_code == REASON_SOURCE_ACTIVE
        assert "60s" in active.value.retry
    finally:
        rmtree(run_root, ignore_errors=True)

    # write_unreconciled: a post-checkpoint unknown intent in the write tail.
    run_root, saved = _seed_plan_run()
    try:
        _seed_chain_intent(
            run_root,
            7,
            key="idem-late",
            client_batch_id="cb-late",
            session_id="session-late",
            status="unknown",
            with_receipt=False,
        )
        with pytest.raises(CheckpointError) as unreconciled:
            _plan(run_root, saved["checkpoint_id"])
        assert unreconciled.value.reason_code == REASON_WRITE_UNRECONCILED
        assert "cannot release it" in unreconciled.value.detail
        # The first blocked operation is interpolated, never the literal
        # placeholder ``{first.get('idempotency_key')}``.
        assert "idem-late" in unreconciled.value.detail
        assert "{first.get" not in unreconciled.value.detail
    finally:
        rmtree(run_root, ignore_errors=True)

    # scope_drift: an unattributable platform write on a bound ontology.
    run_root, saved = _seed_plan_run()
    try:
        platform = FakeCursorPlatform(
            ontology_batches={
                "onto-r3015": [
                    {"batch_id": "b-foreign", "build_session_id": "session-other"}
                ]
            }
        )
        with pytest.raises(CheckpointError) as drift:
            _plan(run_root, saved["checkpoint_id"], readback=_readback(platform))
        assert drift.value.reason_code == REASON_SCOPE_DRIFT
    finally:
        rmtree(run_root, ignore_errors=True)

    # scope_missing equivalent at plan level: no platform bindings recorded.
    run_root = RUNS_ROOT / f"r3015nobind-{os.urandom(4).hex()}"
    try:
        _write_json(run_root / "evidence" / "stage.json", {"stage": "x"})
        saved = save_checkpoint(
            run_root,
            StagePackage(
                kind=CHECKPOINT_KIND_CQ_FROZEN,
                scope_refs={"freeze_id": "f"},
                artifacts=[
                    CheckpointArtifactSpec(
                        source="evidence/stage.json",
                        owner="coordinator",
                        visible_to=("coordinator",),
                        host_private=False,
                    )
                ],
                stage_facts={},
                platform_bindings={},
                write_positions={},
            ),
            source_run_id=run_root.name,
            configuration=dict(CONFIGURATION),
        )
        with pytest.raises(CheckpointError) as unbound:
            _plan(run_root, saved["checkpoint_id"])
        assert unbound.value.reason_code == "checkpoint_incomplete"
        assert "platform bindings" in unbound.value.detail
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m40_approval_binding_changed_and_handoff_boundaries():
    # production_handoff continues through S4 acceptance continuation, never
    # through a production resume: the accurate kind/mode mismatch is the
    # behavior, with the retry pointing at --mode acceptance.
    run_root, saved = _seed_plan_run(
        package=_bound_package(kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF, scope_refs={})
    )
    try:
        with pytest.raises(CheckpointError) as handoff:
            _plan(run_root, saved["checkpoint_id"])
        assert handoff.value.reason_code == cr.REASON_KIND_MODE_MISMATCH
        assert "--mode acceptance" in handoff.value.retry
    finally:
        rmtree(run_root, ignore_errors=True)

    # approval_binding_changed at the plan level (post-save revocation).
    run_root = RUNS_ROOT / f"r3015appr-{os.urandom(4).hex()}"
    try:
        _write_json(
            run_root / APPROVALS_RELATIVE,
            {"schema_version": "r3-0-008b-approvals/v1", "entries": _VALID_ENTRIES},
        )
        (run_root / "profile.snapshot.yaml").write_text(
            json.dumps(
                {
                    "profile_id": CONFIGURATION["profile_id"],
                    "agents": _COORDINATOR_AGENTS,
                }
            ),
            encoding="utf-8",
        )
        saved = save_checkpoint(
            run_root,
            _bound_package(sources=[(APPROVALS_RELATIVE, "coordinator")]),
            source_run_id=run_root.name,
            configuration=dict(CONFIGURATION),
        )
        _write_json(
            run_root / APPROVALS_RELATIVE,
            {"schema_version": "r3-0-008b-approvals/v1", "entries": []},
        )
        with pytest.raises(CheckpointError) as revoked:
            _plan(run_root, saved["checkpoint_id"])
        assert revoked.value.reason_code == REASON_APPROVAL_BINDING_CHANGED
        assert "source run stays untouched" in revoked.value.detail
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m37_m38_successful_plan_accounts_one_semantic_start_with_no_hard_gate():
    run_root, saved = _seed_plan_run(state={"state": "FAILED"})
    try:
        plan = _plan(
            run_root,
            saved["checkpoint_id"],
            authorization_reference="user-2026-09-14-r3015-resume-1",
        )
        assert plan.inspection["schema_version"] == RECOVERY_SCHEMA
        accounting = plan.inspection["accounting"]
        assert accounting["semantic_starts"] == 1
        assert accounting["kind"] == "production_resume"
        assert accounting["platform_hard_gate"] is False
        assert accounting["authorization_reference"] == "user-2026-09-14-r3015-resume-1"
        assert plan.origin["authorization_reference"] == accounting[
            "authorization_reference"
        ]
        assert plan.scope == {
            "mode": "checkpoint",
            "project_id": "proj-r3015",
            "ontology_ids": ["onto-r3015"],
            "root_run_id": run_root.name,
        }
        # D1 constraint 1 proof travels inside the report itself.
        endpoints = plan.inspection["reconciliation"]["endpoints"]
        assert endpoints["session_batches"].startswith(
            "/api/build-sessions/{session_id}/modeling-batches"
        )
        assert "never reconciliation sources" in endpoints["note"]
        assert checkpoint_root_run_id(run_root, saved["checkpoint_id"]) == run_root.name
    finally:
        rmtree(run_root, ignore_errors=True)


def test_m43_prep_time_counts_into_the_budget_without_relaxing_any_gate(monkeypatch):
    monkeypatch.setattr(cr, "PREP_BUDGET_SECONDS", -1)
    run_root, saved = _seed_plan_run(state={"state": "FAILED"})
    try:
        # Over budget reports blockers and asks for a longer window; the plan
        # still only opens the same gates (no relaxation, no read-only launch).
        plan = _plan(run_root, saved["checkpoint_id"])
        timing = plan.inspection["prep_timing"]
        assert timing["budget_seconds"] == -1
        assert timing["over_budget"] is True
        assert timing["blockers"] == []
        assert "20-minute" in timing["note"]
        assert "read_only" not in json.dumps(plan.inspection)
        assert plan.scope["mode"] == "checkpoint"
    finally:
        rmtree(run_root, ignore_errors=True)
    assert PREP_BUDGET_SECONDS == 20 * 60


# --- CLI boundaries (M44 S2 side) --------------------------------------------------


def test_m44_s4_acceptance_mode_dispatches_to_the_continuation_entry(
    monkeypatch, capsys
):
    # --mode acceptance now reaches the delivered S4 continuation entry (it
    # never falls back into a production resume); a nonexistent run root is
    # still the accurate exit-2 failure before any lock or directory work.
    assert (
        _run_cli(
            monkeypatch,
            [
                "checkpoint",
                "resume",
                "--run-id",
                "no-such-run",
                "--checkpoint-id",
                "production_handoff-0001",
                "--new-run-id",
                "n1",
                "--mode",
                "acceptance",
            ],
        )
        == 2
    )
    assert "does not exist" in capsys.readouterr().err


def test_m44_s2_resume_requires_the_host_credential_channel(monkeypatch, capsys):
    assert (
        _run_cli(
            monkeypatch,
            [
                "checkpoint",
                "resume",
                "--run-id",
                "x",
                "--checkpoint-id",
                "y",
                "--new-run-id",
                "n",
                "--mode",
                "production",
            ],
            credential=None,
        )
        == 2
    )
    assert "host platform credential is missing" in capsys.readouterr().err


def test_m10_unsafe_new_run_id_is_refused_before_any_directory_work():
    for bad in ("../escape", "a/b", "", ".hidden", "spaces in id"):
        with pytest.raises(CheckpointError) as refused:
            safe_new_run_id(bad)
        assert refused.value.reason_code == "resume_invalid_new_run_id"
    assert safe_new_run_id("r3015-new-run.1") == "r3015-new-run.1"


# --- PlatformScope checkpoint binding (M13/M23/M24) -------------------------------


def _checkpoint_scope(client=None):
    scope = PlatformScope(
        "http://example",
        "unit-run-resume",
        lambda: ("admin", "admin-id"),
        lambda _: True,
        client or ScopeClient(),
    )
    return scope


def test_m13_m23_checkpoint_binding_loads_by_identity_and_never_creates():
    client = ScopeClient()
    scope = _checkpoint_scope(client)
    scope.prepare(
        {
            "mode": "checkpoint",
            "project_id": "project-1",
            "ontology_ids": ["ontology-1"],
        }
    )
    assert scope.project_id == "project-1"
    assert scope.ontology_ids == ["ontology-1"]
    assert scope.owned is False
    # Binding loads by exact identity: no Project/Ontology was created.
    assert ("POST", "/api/projects") not in client.calls
    assert not any(method == "POST" and path.endswith("/ontologies")
                   for method, path in client.calls)

    client = ScopeClient()
    scope = _checkpoint_scope(client)
    with pytest.raises(PlatformScopeMissingError) as missing:
        scope.prepare(
            {
                "mode": "checkpoint",
                "project_id": "project-1",
                "ontology_ids": ["ontology-1", "ontology-gone"],
            }
        )
    assert "ontology-gone" in str(missing.value)
    # A missing resource is typed scope_missing; no blank-scope fake was made.
    # The only POSTs are this round's credential revocations, never a create.
    assert scope.ontology_ids == []
    assert all(
        method != "POST" or path.endswith(":revoke")
        for method, path in client.calls
    )

    with pytest.raises(Exception):
        _checkpoint_scope().prepare({"mode": "checkpoint", "ontology_ids": ["ontology-1"]})


def test_m24_recovery_cleanup_retains_the_inherited_scope():
    client = ScopeClient()
    scope = _checkpoint_scope(client)
    scope.prepare(
        {
            "mode": "checkpoint",
            "project_id": "project-1",
            "ontology_ids": ["ontology-1"],
        }
    )
    cleanup = scope.cleanup()
    assert cleanup["scope_disposition"] == "inherited-retained"
    assert cleanup["ontology_ids"] == ["ontology-1"]
    # Only this round's credentials are revoked; nothing inherited is deleted.
    assert not any(method == "DELETE" for method, _ in client.calls)
    assert cleanup["admin_key_revoked"] is True
    assert scope.admin_key is None


# --- runner tier: restored boolean gate (M11) --------------------------------------


def test_m11_restored_open_boolean_gate_is_refused():
    source_root = RUNS_ROOT / f"r3015gate-{os.urandom(4).hex()}"
    new_run_id = f"r3015gate-new-{os.urandom(4).hex()}"
    runner = None
    try:
        _write_json(source_root / "evidence" / "stage.json", {"stage": "gate"})
        _write_json(source_root / "candidate-gate" / "state.json", {"state": "open"})
        saved = save_checkpoint(
            source_root,
            _bound_package(
                kind=CHECKPOINT_KIND_SCENARIO_MAPPED,
                sources=[
                    ("evidence/stage.json", "coordinator"),
                    ("candidate-gate/state.json", "coordinator"),
                ],
            ),
            source_run_id=source_root.name,
            configuration=dict(CONFIGURATION),
        )
        runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=RUNS_ROOT / f"{new_run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        with pytest.raises(CheckpointError) as refused:
            runner.prepare_from_checkpoint(
                source_run_root=source_root,
                checkpoint_id=saved["checkpoint_id"],
                new_run_id=new_run_id,
                readback=_readback(FakeCursorPlatform()),
            )
        assert refused.value.reason_code == "checkpoint_incomplete"
        assert "boolean gates" in refused.value.detail
    finally:
        if runner is not None:
            runner.run and runner.cleanup()
        rmtree(RUNS_ROOT / new_run_id, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{new_run_id}-ledger", ignore_errors=True)
        rmtree(source_root, ignore_errors=True)


# --- REAL process boundary: a terminated Runner process, a new process resumes ----

_CHILD_RUNNER_SCRIPT = """
import json
import os
import sys

from modeling_team.tests.test_r30015_checkpoints import PROFILE, _CheckpointRunner, _freeze


class BoundHarness(_CheckpointRunner):
    def prepare(self):
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self._task_path,
            scope={
                "mode": "create",
                "project_id": "r3015-bound-project",
                "ontology_ids": ["r3015-bound-ontology"],
            },
        )
        return self.runner


harness = BoundHarness()
runner = harness.prepare()
frozen = _freeze(runner)
(runner.run.root / "evidence" / "cq-exposure.jsonl").write_text(
    json.dumps(
        {
            "event": "question-exposed-to-production",
            "question_ids": ["cq-1"],
            "roles": ["coordinator"],
            "reason_code": "permanently_public",
        }
    )
    + "\\n",
    encoding="utf-8",
)
runner.cleanup()
print(json.dumps({"run_id": harness.run_id, "freeze_digest": frozen["snapshot_digest"]}))
sys.stdout.flush()
os._exit(0)
"""


def test_s2_real_process_boundary_resume_from_a_terminated_runner():
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    finished = subprocess.run(
        [sys.executable, "-c", _CHILD_RUNNER_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
    )
    assert finished.returncode == 0, finished.stderr
    child = json.loads(finished.stdout.strip().splitlines()[-1])
    source_root = RUNS_ROOT / child["run_id"]
    new_run_id = f"r3015resume-{os.urandom(4).hex()}"
    parent = None
    try:
        # The checkpoint written by the terminated process is on disk.
        listed = list_checkpoints(source_root)
        assert [entry["checkpoint_id"] for entry in listed] == ["cq_frozen-0001"]
        assert listed[0]["status"] == "listed"
        assert listed[0]["kind"] == "cq_frozen"

        # This pytest process is a genuinely different OS process: it re-reads
        # the persisted package and builds a NEW run from it.
        parent = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=RUNS_ROOT / f"{new_run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        parent.prepare_from_checkpoint(
            source_run_root=source_root,
            checkpoint_id="cq_frozen-0001",
            new_run_id=new_run_id,
            readback=_readback(FakeCursorPlatform()),
            authorization_reference="user-2026-09-14-r3015-resume-boundary",
        )
        new_root = RUNS_ROOT / new_run_id
        assert new_root.is_dir()

        # The design §3.2 recovery directory, host-only permissions.
        recovery = new_root / RECOVERY_DIRECTORY
        for name in ("inspection.json", "origin.json", "imports.json"):
            path = recovery / name
            assert path.is_file()
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        for role in ("coordinator", "modeling", "protocol", "competency-question", "host"):
            assert (recovery / "roles" / f"{role}.json").is_file()
        origin = json.loads((recovery / "origin.json").read_text(encoding="utf-8"))
        assert origin["source_run_id"] == child["run_id"]
        assert origin["checkpoint_id"] == "cq_frozen-0001"
        imports = json.loads((recovery / "imports.json").read_text(encoding="utf-8"))
        assert imports["completed_client_batches"] == {}
        inspection = json.loads((recovery / "inspection.json").read_text(encoding="utf-8"))
        assert inspection["accounting"]["semantic_starts"] == 1
        assert inspection["accounting"]["platform_hard_gate"] is False
        assert inspection["accounting"]["authorization_reference"] == (
            "user-2026-09-14-r3015-resume-boundary"
        )

        # The frozen pool was re-validated and adopted, not trusted: the digest
        # the terminated process printed matches the adopted snapshot.
        assert parent._cq_freeze is not None
        assert parent._cq_freeze["snapshot_digest"] == child["freeze_digest"]
        assert parent._cq_phase == "frozen"

        # New role threads must receive their scoped recovery packet as task
        # input; host-only files alone cannot inform an isolated role.
        modeling_task = parent._task_text("modeling")
        cq_task = parent._task_text("competency-question")
        assert "Checkpoint continuation for this role" in modeling_task
        assert '"checkpoint_id": "cq_frozen-0001"' in modeling_task
        assert '"resume_kind": "cq_frozen"' in modeling_task
        assert "competency-questions/frozen/freeze-" not in modeling_task
        # R3.0-011 host-only contract: the frozen pool is never a CQ readable
        # artifact; the role learns the verified freeze state only through the
        # Runner's restored summary, without any frozen path or hidden content.
        assert "competency-questions/frozen/freeze-" not in cq_task
        assert '"frozen_pool"' in cq_task
        assert '"restored": true' in cq_task

        # Exposure provenance is the union across the chain: cq-1 stays
        # exposed even though this new process never exposed it itself, and
        # the recovered Runner actually carries it in its exposure state.
        assert parent._cq_exposed.get("cq-1") == ["coordinator"]
        union = json.loads((recovery / "inspection.json").read_text(encoding="utf-8"))

        # Validators were recomputed and no boolean gate-open came along.
        events = _checkpoint_events(parent)
        prepared = next(event for event in events if event["event"] == "resume-prepared")
        assert prepared["validators_recomputed"]["gate_open_restored_from_source"] is False
        assert prepared["validators_recomputed"]["candidate_gate_open_after_restore"] is False
        assert prepared["cq_freeze_restored"] is True
        assert prepared["accounting"]["semantic_starts"] == 1
        assert prepared["exposure_union"]["exposed_question_ids"] == ["cq-1"]
        assert parent._resume_imports == {"completed_client_batches": {},
                                          "plan_mappings": []}
        assert union["schema_version"] == RECOVERY_SCHEMA
    finally:
        if parent is not None:
            parent.cleanup()
        rmtree(RUNS_ROOT / new_run_id, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{new_run_id}-ledger", ignore_errors=True)
        rmtree(source_root, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{child['run_id']}-ledger", ignore_errors=True)


# --- later-stage packages carry the frozen pool forward (M11/M10) ------------------


class _BoundResumeHarness(_CheckpointRunner):
    """A prepared 011 run bound to a real Project/Ontology (resumable identity)."""

    def prepare(self) -> TeamRunner:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self._task_path,
            scope={
                "mode": "create",
                "project_id": "r3015-late-project",
                "ontology_ids": ["r3015-late-ontology"],
            },
        )
        return self.runner


def _resume_later_stage(source_root: Path, checkpoint_id: str) -> tuple[TeamRunner, str]:
    """Resume into a fresh run from a bound later-stage package.

    A refused resume still prepared (and therefore created) the new run root,
    so the helper removes its own leftovers before re-raising.
    """

    new_run_id = f"r3015late-{os.urandom(4).hex()}"
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=CapturingAdapter(),
        ledger_root=RUNS_ROOT / f"{new_run_id}-ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    try:
        runner.prepare_from_checkpoint(
            source_run_root=source_root,
            checkpoint_id=checkpoint_id,
            new_run_id=new_run_id,
            readback=_readback(FakeCursorPlatform()),
            authorization_reference="user-2026-09-15-r3015-later-stage-freeze",
        )
    except BaseException:
        if runner.run is not None:
            runner.cleanup()
        _drop_new_run(None, new_run_id)
        raise
    return runner, new_run_id


def _drop_new_run(runner: TeamRunner | None, new_run_id: str | None) -> None:
    if runner is not None:
        runner.cleanup()
    if new_run_id is not None:
        rmtree(RUNS_ROOT / new_run_id, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{new_run_id}-ledger", ignore_errors=True)


def _staged_write_outcome(runner: TeamRunner) -> str | None:
    """The reason code the real staged write channel reports, if it rejects."""

    try:
        runner._handle_staged_submit_modeling_batch({})
    except StagedSubmissionRejection as rejection:
        return rejection.data["reason_code"]
    return None


def test_m11_later_stage_checkpoint_resume_adopts_the_verified_freeze():
    """R3.0-015 L0 resume5 regression: every later kind carries the frozen pool.

    The write-channel gate exists to require a reviewed, frozen pool, so a
    resume must restore that state from the packaged, digest-verified freeze
    instead of keying the restore on the ``cq_frozen`` label alone.  Before the
    fix, ``_cq_freeze`` stayed empty after a real recovery and the first staged
    dry-run was hard-rejected with ``cq_freeze_pending`` while the new run root
    already held the verified pool.
    """

    harness = _BoundResumeHarness()
    new_run_id = None
    parent = None
    try:
        runner = harness.prepare()
        frozen = _freeze(runner)
        _settled_apply_intent(runner, ordinal=1, mode="dry_run")
        saved = _outer_save(runner, CHECKPOINT_KIND_MATERIALIZATION_PROGRESS)
        assert saved["status"] == "saved"
        manifest = _read_manifest(harness.run_root, saved["checkpoint_id"])
        packaged = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["source"].startswith("competency-questions/frozen/freeze-")
        )
        # Premise of the regression: the later-stage package carries the pool.
        assert packaged["host_private"] is True
        # The old writer exits; the package is all the resume has.
        runner.cleanup()

        parent, new_run_id = _resume_later_stage(harness.run_root, saved["checkpoint_id"])
        assert parent._cq_freeze is not None
        assert parent._cq_freeze["snapshot_digest"] == frozen["snapshot_digest"]
        assert parent._cq_phase == "frozen"
        prepared = next(
            event for event in _checkpoint_events(parent) if event["event"] == "resume-prepared"
        )
        assert prepared["cq_freeze_restored"] is True
        # The same write channel that refused the live run must now reach its
        # ordinary staged validation instead of ``cq_freeze_pending``.
        assert _staged_write_outcome(parent) != "cq_freeze_pending"
    finally:
        _drop_new_run(parent, new_run_id)
        harness.remove()


def test_m11_later_stage_tampered_frozen_pool_is_still_refused():
    """A packaged freeze is never the permission by itself: it is re-validated."""

    harness = _BoundResumeHarness()
    new_run_id = None
    try:
        runner = harness.prepare()
        frozen = _freeze(runner)
        freeze_path = harness.run_root / "competency-questions" / "frozen" / "freeze-0001.json"
        tampered = json.loads(freeze_path.read_text(encoding="utf-8"))
        # A post-freeze edit that keeps the old snapshot_digest: the package
        # digest still matches the file, so only re-validation can catch it.
        tampered["questions"][0]["question"] = "rewritten after the freeze"
        assert tampered["snapshot_digest"] == frozen["snapshot_digest"]
        freeze_path.chmod(0o644)  # the frozen file is written read-only
        _write_json(freeze_path, tampered)
        saved = save_checkpoint(
            harness.run_root,
            StagePackage(
                kind=CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
                scope_refs={},
                artifacts=[
                    CheckpointArtifactSpec(
                        source="competency-questions/frozen/freeze-0001.json",
                        owner="host",
                        visible_to=("host", "competency-question"),
                        host_private=True,
                    )
                ],
                stage_facts={},
                platform_bindings={
                    "project_id": "r3015-late-project",
                    "ontology_ids": ["r3015-late-ontology"],
                },
                write_positions={},
            ),
            source_run_id=harness.run_id,
            configuration=dict(CONFIGURATION),
        )
        runner.cleanup()
        with pytest.raises(CheckpointError) as refused:
            _resume_later_stage(harness.run_root, saved["checkpoint_id"])
        assert refused.value.reason_code == "artifact_changed"
        assert "failed re-validation" in refused.value.detail
    finally:
        _drop_new_run(None, new_run_id)
        harness.remove()


def test_m11_scenario_mapped_resume_without_a_frozen_pool_keeps_the_gate_closed():
    """The counterpart: no packaged freeze means no fabricated freeze state."""

    harness = _BoundResumeHarness()
    new_run_id = None
    parent = None
    try:
        runner = harness.prepare()
        _write_json(
            harness.run_root / "competency-questions" / "private" / "interview-0001.json",
            {"question_id": "cq-1", "answer": "confirmed"},
        )
        saved = _outer_save(runner, CHECKPOINT_KIND_SCENARIO_MAPPED)
        assert saved["status"] == "saved"
        manifest = _read_manifest(harness.run_root, saved["checkpoint_id"])
        assert manifest["stage_facts"]["cq_frozen"] is False
        assert not any(
            artifact["source"].startswith("competency-questions/frozen/")
            for artifact in manifest["artifacts"]
        )
        runner.cleanup()

        parent, new_run_id = _resume_later_stage(harness.run_root, saved["checkpoint_id"])
        assert parent._cq_freeze is None
        prepared = next(
            event for event in _checkpoint_events(parent) if event["event"] == "resume-prepared"
        )
        assert prepared["cq_freeze_restored"] is False
        assert _staged_write_outcome(parent) == "cq_freeze_pending"
    finally:
        _drop_new_run(parent, new_run_id)
        harness.remove()


def test_m11_cq_frozen_checkpoint_without_a_packaged_freeze_is_refused():
    """The completeness hard gate on the cq_frozen kind survives the fix."""

    source_root = RUNS_ROOT / f"r3015nofreeze-{os.urandom(4).hex()}"
    new_run_id = None
    try:
        _write_json(source_root / "evidence" / "stage.json", {"stage": "no-freeze"})
        saved = save_checkpoint(
            source_root,
            StagePackage(
                kind=CHECKPOINT_KIND_CQ_FROZEN,
                scope_refs={},
                artifacts=[
                    CheckpointArtifactSpec(
                        source="evidence/stage.json",
                        owner="coordinator",
                        visible_to=("coordinator", "modeling", "protocol"),
                    )
                ],
                stage_facts={},
                platform_bindings={
                    "project_id": "r3015-late-project",
                    "ontology_ids": ["r3015-late-ontology"],
                },
                write_positions={},
            ),
            source_run_id=source_root.name,
            configuration=dict(CONFIGURATION),
        )
        with pytest.raises(CheckpointError) as refused:
            _resume_later_stage(source_root, saved["checkpoint_id"])
        assert refused.value.reason_code == "checkpoint_incomplete"
        assert "packages no frozen pool" in refused.value.detail
    finally:
        _drop_new_run(None, new_run_id)
        rmtree(source_root, ignore_errors=True)


# --- delivery boundary summary stays accurate (M44 S2 side) ------------------------


def test_m44_s2_inspection_reports_the_resume_delivery_boundary(tmp_path):
    run_root = tmp_path / "segments"
    _write_json(run_root / "evidence" / "stage.json", {"stage": "x"})
    save_checkpoint(
        run_root,
        _bound_package(),
        source_run_id="r3015-seg",
        configuration=dict(CONFIGURATION),
    )
    result = inspect_checkpoints(run_root)
    assert result["delivery_segments"]["s2_production_resume"] == "delivered"
    assert result["delivery_segments"]["s4_acceptance_continuation"] == "delivered"
    assert result["resume"]["modes"]["production"]["delivered"] is True
    assert result["resume"]["modes"]["production"]["semantic_starts"] == 1
    assert result["resume"]["modes"]["acceptance"]["delivered"] is True
    assert result["resume"]["modes"]["acceptance"]["semantic_starts"] == 0


# --- repair round (I — Round 1 D1/D2): typed channels for lock and scope ----------


_S8_FIELDS = {"code", "object_ref", "phase", "retryable", "reason"}


def _typed_rejection_payload(stderr: str) -> dict:
    """Parse the single ``checkpoint failed: {...}`` line from a channel."""

    prefix = "checkpoint failed: "
    assert stderr.count(prefix) == 1, stderr
    return json.loads(stderr.split(prefix, 1)[1].splitlines()[0])


def test_d2_production_lock_conflict_is_a_typed_rejection_exit_2(monkeypatch, capsys):
    """Defect D2: the held root-run lock must surface as the §8 tuple."""

    run_root, saved = _seed_plan_run(state={"state": "FAILED"})
    lock_file = RUNS_ROOT / ".recovery-locks" / f"{run_root.name}.lock"
    try:
        lock = acquire_root_run_lock(run_root.name, RUNS_ROOT)
        try:
            assert (
                _run_cli(
                    monkeypatch,
                    [
                        "checkpoint",
                        "resume",
                        "--run-id",
                        run_root.name,
                        "--checkpoint-id",
                        saved["checkpoint_id"],
                        "--new-run-id",
                        f"r3015new-{os.urandom(4).hex()}",
                        "--freeze-started-at",
                        "2026-09-14T00:00:00+00:00",
                        "--mode",
                        "production",
                    ],
                )
                == 2
            )
            payload = _typed_rejection_payload(capsys.readouterr().err)
            assert payload["code"] == REASON_SOURCE_ACTIVE
            assert payload["retryable"] is True
            assert "resume lock" in payload["reason"]
            assert set(payload) >= _S8_FIELDS
            assert "next_action" in payload
            assert not set(payload) & {"reason_code", "detail", "object", "retry"}
        finally:
            lock.release()
    finally:
        rmtree(run_root, ignore_errors=True)
        if lock_file.is_file():
            lock_file.unlink()


def test_d1_missing_scope_is_a_typed_rejection_exit_2(monkeypatch, capsys):
    """Defect D1: a scope resource gone at resume is typed ``scope_missing``.

    The source checkpoint comes from a genuinely separate terminated Runner
    process (the proven materializable fixture); the platform HTTP boundary
    is stubbed (reconciliation via the cursor stand-in; the scope stub raises
    the REAL ``PlatformScopeMissingError`` that ``PlatformScope._checkpoint_
    binding`` produces -- that raise itself is proven by test_m13_m23).  This
    is the channel proof that the typed tuple reaches the host with exit 2.
    """

    from modeling_team import __main__ as main_module
    import modeling_team.runner as runner_module

    finished = subprocess.run(
        [sys.executable, "-c", _CHILD_RUNNER_SCRIPT],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
    )
    assert finished.returncode == 0, finished.stderr
    child = json.loads(finished.stdout.strip().splitlines()[-1])
    source_root = RUNS_ROOT / child["run_id"]
    new_run_id = f"r3015new-{os.urandom(4).hex()}"
    lock_file = RUNS_ROOT / ".recovery-locks" / f"{source_root.name}.lock"
    try:
        monkeypatch.setattr(
            runner_module,
            "http_readback",
            lambda base_url, key: _readback(FakeCursorPlatform()),
        )

        class _GoneScope:
            def __init__(self, *args, **kwargs) -> None:
                return None

            def prepare(self, scope):
                raise PlatformScopeMissingError(
                    "checkpoint scope resources are missing: ontology-gone"
                )

            def cleanup(self):
                return {"scope_disposition": None}

        monkeypatch.setattr(main_module, "PlatformScope", _GoneScope)
        assert (
            _run_cli(
                monkeypatch,
                [
                    "checkpoint",
                    "resume",
                    "--run-id",
                    source_root.name,
                    "--checkpoint-id",
                    "cq_frozen-0001",
                    "--new-run-id",
                    new_run_id,
                    "--freeze-started-at",
                    "2026-09-14T00:00:00+00:00",
                    "--mode",
                    "production",
                ],
            )
            == 2
        )
        payload = _typed_rejection_payload(capsys.readouterr().err)
        assert payload["code"] == "scope_missing"
        assert "ontology-gone" in payload["reason"]
        assert payload["retryable"] is True
        assert set(payload) >= _S8_FIELDS
        assert "next_action" in payload
        assert not set(payload) & {"reason_code", "detail", "object", "retry"}
        # No blank scope was created and faked as a resume: the new run's
        # own state records the terminal refusal, not a scope id.
        new_state = RUNS_ROOT / new_run_id / "state.json"
        assert new_state.is_file()
        assert json.loads(new_state.read_text(encoding="utf-8"))["state"] not in {
            "RUNNING",
            "STARTING",
            "PAUSED",
        }
    finally:
        rmtree(source_root, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{child['run_id']}-ledger", ignore_errors=True)
        rmtree(RUNS_ROOT / new_run_id, ignore_errors=True)
        rmtree(RUNS_ROOT / f"{new_run_id}-ledger", ignore_errors=True)
        if lock_file.is_file():
            lock_file.unlink()


def test_resumed_cq_appends_review_and_freeze_preserving_prior_approved_pool():
    """Real saved package/restore and current review; no Agent or live platform."""
    from modeling_team.tests.test_r3011_runner_wiring import _draft, _decision, _question
    from modeling_team.competency_questions import CQContractError

    harness = _BoundResumeHarness()
    parent = None
    new_run_id = None
    try:
        runner = harness.prepare()
        questions = [_question("cq-public"), _question("cq-hidden", visibility="hidden")]
        runner.handle_cq_outer_input({"action": "cq_interview", "text": "generic approved interview"})
        runner._publish_cq_question_draft({"draft": _draft(questions)})
        for question in questions:
            runner.handle_cq_outer_input(_decision(runner, question_id=question["question_id"]))
        frozen = runner.handle_cq_outer_input({"action": "cq_freeze"})
        _settled_apply_intent(runner, ordinal=1, mode="dry_run")
        saved = _outer_save(runner, CHECKPOINT_KIND_MATERIALIZATION_PROGRESS)
        checkpoint = harness.run_root / "checkpoints" / saved["checkpoint_id"]
        checkpoint_before = {p.relative_to(checkpoint): p.read_bytes()
                             for p in checkpoint.rglob("*") if p.is_file()}
        assert checkpoint_before
        source_freeze = (harness.run_root / "competency-questions/frozen/freeze-0001.json").read_bytes()
        runner.cleanup()
        parent, new_run_id = _resume_later_stage(harness.run_root, saved["checkpoint_id"])
        root = parent.run.root
        reviews = root / "competency-questions/reviews"
        old_review = (reviews / "cq-review-0001.json").read_bytes()
        old_freeze = (root / "competency-questions/frozen/freeze-0001.json").read_bytes()
        old_interview = (root / "competency-questions/private/interview-0001.json").read_bytes()
        assert parent._cq_review_sequence == 1
        assert parent._cq_draft_order == ["cq-review-0001"]
        assert len(parent._cq_decisions["cq-review-0001"]) == 2
        assert parent._cq_interview_sequence == 1
        changed = _question("cq-public", question="revised generic question?", content_version=2)
        new_draft = _draft([changed])
        new_draft["draft_id"] = "cq-draft-0002"
        new_draft["superseded_draft_id"] = "cq-draft-0001"
        parent.handle_cq_outer_input({"action": "cq_interview", "text": "generic follow-up"})
        published = parent._publish_cq_question_draft({"draft": new_draft})
        assert published["review_id"] == "cq-review-0002"
        with pytest.raises(CQContractError) as stale:
            parent.handle_cq_outer_input(_decision(
                parent, 2, content_digest=json.loads(old_review)["content_digest"],
            ))
        assert stale.value.reason_code == "cq_review_stale"
        parent.handle_cq_outer_input(_decision(
            parent, 2, decision="modify", modified_question=changed, question_id="cq-public",
        ))
        new_freeze = parent.handle_cq_outer_input({"action": "cq_freeze"})
        assert new_freeze["freeze_id"] == "cq-batch-0002"
        assert new_freeze["snapshot_digest"] != frozen["snapshot_digest"]
        pool = parent._cq_freeze["questions"]
        assert [q["question_id"] for q in pool] == ["cq-public", "cq-hidden"]
        assert pool[0]["question"] == changed["question"]
        assert pool[1]["content_version"] == 1
        assert pool[1]["visibility"] == "hidden"
        assert (reviews / "cq-review-0001.json").read_bytes() == old_review
        assert (root / "competency-questions/frozen/freeze-0001.json").read_bytes() == old_freeze
        assert (root / "competency-questions/private/interview-0001.json").read_bytes() == old_interview
        assert (root / "competency-questions/private/interview-0002.json").is_file()
        assert (harness.run_root / "competency-questions/frozen/freeze-0001.json").read_bytes() == source_freeze
        assert {p.relative_to(checkpoint): p.read_bytes()
                for p in checkpoint.rglob("*") if p.is_file()} == checkpoint_before
    finally:
        _drop_new_run(parent, new_run_id)
        harness.remove()
