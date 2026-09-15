"""Foreground single-run lifecycle and newline-delimited JSON outer protocol."""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import shutil
import stat
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ClassVar, Mapping, Sequence


from .contracts import (
    MODELING_CHECKPOINTS_PARAMETER,
    STAGED_MODELING_DECISIONS_PARAMETER,
    UNIFIED_GRAPH_TASK_PARAMETER,
    TeamConfiguration,
    TeamConfigurationError,
    digest_file,
    load_formal_team_configuration,
    load_multi_slice_team_configuration,
    normalize_acceptance_target,
    task_declares_multi_slice_workflow,
)
from .model_routing import (
    MODEL_PROFILE_DIRECTORY,
    MODEL_PROFILE_PACKAGE_IDS,
    TeamModelProfile,
    load_team_model_profile,
    preflight_codex_subscription_auth,
    preflight_profile_credentials,
    profile_requires_codex_subscription_auth,
)
from .formal_runs import (
    FORMAL_PROFILE_IDS,
    FORMAL_TASK_IDS,
    FormalRunContract,
    formal_run_contract_for,
    load_formal_run_configuration,
)
from .r23003_contract import (
    R2_3_003_TARGET_IDS,
    validate_r23003_candidate_declarations,
    validate_deletion_policy,
)
from .acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    RunnerAcceptanceCarrier,
)
from .protocol_retrieval_gate import (
    ProtocolRetrievalGate,
    ProtocolRetrievalGateError,
)
from .preflight import (
    normalize_scope_for_contract,
    run_existing_scope_preflight,
    run_prestart_preflight,
)
from .runtimes.base import RuntimeAdapter, RuntimeDelivery, RuntimeDispatchReceipt
from .capability_mcp import STAGED_PROTOCOL_OPERATION, STAGED_PROTOCOL_RUN_OPERATIONS
from .candidate_progress import (
    FormalCandidateError,
    FormalCandidatePlatformContractError,
    FormalCandidateProgress,
    FormalCandidateProgressTimeout,
    FormalCandidateRoutingError,
    canonical_digest,
    formal_candidate_digests,
    validate_formal_conflict,
    validate_formal_receipt,
)
from .candidate_platform_gate import (
    CANDIDATE_RECEIPT_REGISTERED_KIND,
    CandidatePlatformGate,
    CandidatePlatformGateError,
    candidate_receipt_registered_notice,
)
from .candidate_publication import (
    CandidatePublicationError,
    StagedCandidatePublication,
    ValidatedCandidatePublication,
    stage_candidate_publication,
    validate_candidate_publication,
)
from .interventions import (
    IssueControl,
    IssueError,
    IssueResolution,
    RecoverableOuterInputError,
    REPAIR_COMPONENTS,
)
from .protocol_mcp_launch import (
    canonical_protocol_mcp_mode_contract,
    protocol_mcp_reasoner_contract,
)
from .scenario_map import (
    TOPOLOGY_ONTOLOGY_PLAN_FIELD,
    ScenarioMapArtifactError,
    load_scenario_map,
    load_topology_decision,
    scenario_map_artifact_paths,
    validate_scenario_map,
    validate_topology_decision,
)
from .staged_decisions import (
    ENUM_COMMAND_KINDS,
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    StagedDecisionArtifactError,
    StagedDecisionIssue,
    StagedSubmissionRejection,
    build_submission_intent,
    build_submission_receipt,
    candidate_gate_open,
    load_analysis_conclusions,
    load_approvals,
    load_materialization_plan_ref,
    load_materialization_unlock,
    mark_intent_status,
    next_intent_ordinal,
    next_receipt_ordinal,
    read_submission_intents,
    read_submission_receipts,
    staged_artifact_issues,
    staged_checklist_issue,
    staged_decision_artifact_paths,
    staged_decision_directories,
    staged_intent_receipt_issues,
    staged_stage3_issue,
    UNIFIED_SUBMISSION_RECEIPT_SCHEMA,
    build_attempt_proof,
    unified_approval_issue,
    unified_candidate_issue,
    unified_dry_run_proof_issue,
    unified_plan_issue,
    unified_translation_issue,
    validate_materialization_unlock,
    validate_staged_submission,
    write_submission_intent,
    write_submission_receipt,
)
from .competency_questions import (
    COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER,
    COMPETENCY_QUESTION_ROLE,
    CQ_ACCEPTANCE_COMPLETE_FIELDS,
    CQ_ACCEPTANCE_MODE,
    CQ_ACCEPTANCE_VERDICTS,
    CQ_FREEZE_SCHEMA,
    CQ_RUN_DIRECTORIES,
    CQContractError,
    CQWaitWindowTracker,
    advisory_question_count_feedback,
    batch_report_acceptance_verdict,
    canonical_json_bytes,
    content_digest,
    coverage_gaps_from_projection,
    cross_slice_projection_issues,
    freeze_question_pool,
    public_projection,
    read_exposure_evidence,
    reload_frozen_pool,
    review_decision_digest,
    validate_draft_document,
    validate_review_decision,
    write_public_projection,
)
from .checkpoints import (
    CHECKPOINT_DIRECTORY,
    CHECKPOINT_EVIDENCE_NAME,
    CHECKPOINT_KIND_CQ_FROZEN,
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CHECKPOINT_KIND_SCENARIO_MAPPED,
    CHECKPOINT_KIND_SEMANTIC_APPROVED,
    CHECKPOINT_KINDS,
    PRODUCTION_ROLES,
    WRITE_CLAIMING_KINDS,
    CheckpointArtifactSpec,
    CheckpointError,
    StagePackage,
    file_digest as checkpoint_file_digest,
    inspect_checkpoints,
    save_checkpoint,
    scope_retention_reference,
)
from .checkpoint_recovery import (
    PlatformReadback,
    RecoveryPlan,
    check_resume_submission,
    http_readback,
    merge_exposure_union,
    prepare_recovery_plan,
    restore_checkpoint_artifacts,
    write_recovery_files,
)
from .protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_conflict,
    build_candidate_receipt,
    build_candidate_item_evidence_map,
    build_existing_scope_candidate_conflict,
)
from .matrix_artifact import MatrixArtifactError, verify_matrix as verify_proof_matrix
from .start_ledger import (
    R2_3_002_REQUIREMENT_ID,
    R2_3_005_REQUIREMENT_ID,
    StartLedger,
    StartLedgerConfig,
    resolve_ledger_config,
)
from .transport_mcp import RoutingError, TeamTransportBroker, _call_terminal_report_guard
from .task_overlay import TaskInputOverlay, load_task_input_overlay
from .modeling_readonly import (
    MODELING_READ_TOOLS,
    ModelingContextGate,
    ModelingReadKeyLifecycle,
    ModelingReadProxy,
    ModelingReadError,
    canonical_digest as modeling_canonical_digest,
    _candidate_value as modeling_candidate_value,
)


_PROOF_MATRIX_RELATIVE = "modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json"
_P2A_PASS_RELATIVE = "workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json"
_MATRIX_SCHEMA = "r2-3-002-proof-v2-assertion-matrix/v1"
_P2A_SCHEMA = "r2-3-002-proof-v2-gates/p2a-pass/v1"
_OWNER_ANSWER_AUTHORIZATION = "r2-3-002-owner-answer-authorization"
# R3.0-006 M2: the roles message routing cannot work without.  The Runner
# requires their existence (fail-closed) but no longer assumes an exact
# roster; extra Profile roles carry no terminal dependency.
RUNNER_CORE_ROLE_VALUES = frozenset({"coordinator", "modeling", "protocol"})

#: 2026-09-14 provider-recovery: spacing between retries of one failed provider
#: recovery dispatch.  A fixed window (not an attempt counter) so an externally
#: fixable provider condition is never permanently killed by retry exhaustion.
_PROVIDER_RECOVERY_RETRY_SECONDS = 60.0

#: The only target kind the staged evidence repost may address.  Evidence backs a
#: Modeling Item's lineage; anything else (a resource IRI, a statement id) is not
#: the staged write the Runner projects and must not be silently accepted.
STAGED_EVIDENCE_TARGET_TYPE = "modeling_item"


def _staged_evidence_issue(association: Any) -> str | None:
    """The reason a staged evidence envelope may not be forwarded, else ``None``.

    This is the mechanical half of the projection's contract: shape and target
    legality only.  Whether the evidence itself is owner-authorized is the
    Protocol role's discipline (stated in its instructions), not something the
    Runner can verify, so the Runner never judges content -- it only guarantees
    that a call which cannot be a real association never reaches the platform.
    """

    if not isinstance(association, Mapping):
        return "the association envelope is not an object"
    for key in ("project_id", "ontology_id", "target_type", "target_id"):
        value = association.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"association {key} is required"
    if association["target_type"].strip() != STAGED_EVIDENCE_TARGET_TYPE:
        return f"association target_type must be {STAGED_EVIDENCE_TARGET_TYPE}"
    reference_ids = association.get("evidence_reference_ids")
    if reference_ids is not None and (
        not isinstance(reference_ids, (list, tuple))
        or not all(isinstance(item, str) and item.strip() for item in reference_ids)
    ):
        return "association evidence_reference_ids must be a list of reference ids"
    evidence = association.get("evidence")
    if evidence is not None and (
        not isinstance(evidence, (list, tuple))
        or not all(
            isinstance(item, Mapping)
            and isinstance(item.get("document_name"), str)
            and item["document_name"].strip()
            and isinstance(item.get("excerpt"), str)
            and item["excerpt"].strip()
            for item in evidence
        )
    ):
        return "association evidence entries must carry document_name and excerpt"
    # Nothing was named to associate: the platform would answer with an empty
    # association list, which reads as success while satisfying no retrieval gate.
    if not reference_ids and not evidence:
        return "association must name at least one evidence reference or excerpt"
    return None


# R3.0-012 (design §4.4): bounded drain wait for in-flight staged writes at
# the production-handoff boundary.  The wait itself holds no lock, so the
# foreground loop stays responsive and Delivery can retry or stop.
_CQ_WRITE_DRAIN_TIMEOUT_SECONDS = 60.0


class CQWriteAdmission:
    """Run-local atomic admission for the two staged platform write entry points.

    R3.0-012 design §4.4: the outer-input handoff and the CapabilityBroker
    staged writes arrive from different threads, so the run shares one local
    mutex/condition, one handoff phase, and one in-flight mutation registry
    between ``_handle_staged_submit_modeling_batch`` and
    ``_handle_staged_associate_evidence``.  A mutation is admitted only while
    the phase is ``open``; the remote forwarder call always runs *outside* the
    lock; every admitted ticket reports its outcome so a drain can observe
    zero.  This is deliberately not a general coordination framework: one
    instance per run, no cross-run or cross-process scope, and no lock is ever
    held across a network wait.

    Phases move ``open -> quiescing -> read-only`` and never reopen: a failed
    handoff verification keeps the scene quiesced (recoverable rejection), and
    resuming production is a separate Delivery request, not something the
    acceptance side may lift.

    R3.0-015 S1 (design §3.3.2 / D1 review note 2): the one-way phase ladder
    above must NOT be reused for the brief write-position capture a checkpoint
    save needs, so a separate reversible ``capturing`` flag blocks new
    admissions for the capture window only; ``end_capture`` restores admission
    while the phase is still ``open``.  The barrier is never held across a
    cross-LLM review or a network wait.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._phase = "open"
        self._capturing = False
        self._in_flight: dict[int, dict[str, Any]] = {}
        self._records: list[dict[str, Any]] = []
        self._next_ticket = 0

    @property
    def phase(self) -> str:
        with self._condition:
            return self._phase

    @property
    def capturing(self) -> bool:
        with self._condition:
            return self._capturing

    def admit(self, kind: str) -> int | None:
        """Register one staged mutation; ``None`` rejects it as recoverable."""

        with self._condition:
            if self._phase != "open" or self._capturing:
                return None
            self._next_ticket += 1
            self._in_flight[self._next_ticket] = {
                "ticket": self._next_ticket,
                "kind": kind,
            }
            return self._next_ticket

    def begin_capture(self) -> bool:
        """Briefly stop admitting new writes for a checkpoint capture.

        Returns ``False`` when the phase is already past ``open`` — writes are
        then blocked anyway, so the caller may capture without the barrier.
        Unlike :meth:`begin_quiescing` this is reversible via
        :meth:`end_capture` and never advances the phase ladder.
        """

        with self._condition:
            if self._phase != "open":
                return False
            self._capturing = True
            return True

    def end_capture(self) -> None:
        """Reopen admission after a checkpoint capture (idempotent)."""

        with self._condition:
            self._capturing = False
            self._condition.notify_all()

    def complete(self, ticket: int, outcome: str) -> None:
        """Record the determined outcome of one admitted mutation."""

        with self._condition:
            record = self._in_flight.pop(ticket, None)
            if record is not None:
                record["outcome"] = outcome
                self._records.append(record)
            self._condition.notify_all()

    def begin_quiescing(self) -> bool:
        """Stop admitting new writes; ``False`` when already past ``open``."""

        with self._condition:
            if self._phase != "open":
                return False
            self._phase = "quiescing"
            self._condition.notify_all()
            return True

    def enter_read_only(self) -> None:
        """Publish the handoff: writes stay rejected until the run ends."""

        with self._condition:
            if self._phase != "open":
                self._phase = "read-only"
                self._condition.notify_all()

    def wait_until_drained(self, timeout: float) -> bool:
        """Wait (lock released) for every admitted mutation to complete."""

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._condition.wait(remaining):
                    if self._in_flight:
                        return False
            return True

    def snapshot(self) -> dict[str, Any]:
        """The host-verified write-state view consumed by readiness."""

        with self._condition:
            return {
                "phase": self._phase,
                "capturing": self._capturing,
                "in_flight": [dict(item) for item in self._in_flight.values()],
                "records": [dict(item) for item in self._records],
            }


@dataclass
class TeamRun:
    run_id: str
    root: Path
    configuration: TeamConfiguration
    scope: dict[str, str]
    protocol_key: str | None = None
    transport_root: Path | None = None
    baseline_hash: str | None = None
    terminal_results: dict[str, dict[str, Any]] | None = None
    protocol_context: dict[str, str] | None = None
    gate_binding: dict[str, str] | None = None
    acceptance: RunnerAcceptanceCarrier | None = None
    team_model_profile: TeamModelProfile | None = None
    formal_contract: FormalRunContract | None = None
    provider_credential_bindings: Mapping[str, Any] | None = None
    # Fixed safe label only (``chatgpt-subscription``); never a token, account,
    # auth cache path/digest, or login-status output.
    codex_subscription_auth_mode: str | None = None
    modeling_read_key_id: str | None = None
    modeling_read_proxy: ModelingReadProxy | None = None


class TeamRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        adapter: RuntimeAdapter,
        scope_factory: Any | None = None,
        ledger_root: Path | None = None,
        ledger_factory: Callable[..., StartLedger] | None = None,
        freeze_started_at: str | None = None,
        ledger_now: Callable[[], datetime] | None = None,
        prestart_preflight: Callable[..., dict[str, Any]] | None = None,
        canonical_base_url: str = "http://127.0.0.1:8001",
        canonical_admin_key: str | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        deepseek_credential_path: Path | None = None,
        glm_credential_path: Path | None = None,
        staged_batch_forwarder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        staged_evidence_forwarder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ):
        self.repository_root, self.adapter, self.scope_factory, self.ledger_root, self.ledger_factory, self.freeze_started_at, self.ledger_now = (
            repository_root,
            adapter,
            scope_factory,
            ledger_root,
            ledger_factory,
            freeze_started_at,
            ledger_now,
        )
        self.prestart_preflight = prestart_preflight
        self.canonical_base_url = canonical_base_url
        self.canonical_admin_key = canonical_admin_key
        self.monotonic_clock = monotonic_clock or time.monotonic
        # R3.0-008B: the injected host-side write forwarder for staged Modeling
        # Batch submissions.  Production wiring (cli/runtime assembly) binds the
        # real backend submit_modeling_batch write path; ``None`` keeps the
        # staged capability fail-closed with the typed
        # ``staged_batch_forward_failed`` reason code.  It must NOT reuse the
        # read-only McpReadForwarder/PLATFORM_PROXY_READ_TOOLS surface.
        self.staged_batch_forwarder = staged_batch_forwarder
        # R3.0-008B/#17: the injected host-side forwarder for the staged evidence
        # repost.  It reaches the canonical ``associate_evidence_reference`` and
        # nothing else.  ``None`` keeps the capability fail-closed with the typed
        # ``staged_evidence_forward_failed`` reason code.
        self.staged_evidence_forwarder = staged_evidence_forwarder
        # These paths are constructor-only test seams.  Production callers leave
        # them unset and therefore bind each route's fixed external credential
        # location; a profile only ever reads the routes it actually names.
        self.deepseek_credential_path = deepseek_credential_path
        self.glm_credential_path = glm_credential_path
        # Safe conclusion of the Host ChatGPT subscription preflight; only the
        # fixed label from model_routing is ever stored here (no token, account,
        # cache path/digest, or login-status output).
        self.codex_subscription_auth_mode: str | None = None
        self.run: TeamRun | None = None
        self.transport: TeamTransportBroker | None = None
        self.scope: Any | None = None
        self._terminal_emitted = False
        self._runtime_failure_finalized = False
        self._terminal_handoffs_notified: set[tuple[str, str]] = set()
        self._terminal_handoff_sequence = 0
        # Acceptance settlement can be reached from both the foreground drain and
        # the formal Acceptance terminal-report guard. Serialize only that
        # finalization boundary; the method itself is idempotent after the lock.
        self._acceptance_settlement_lock = threading.Lock()
        self._acceptance_settlement_evidence_recorded = False
        self._post_settlement_reporting_requested = False
        self._coordinator_final_captured = False
        self._outer_user_texts: set[str] = set()
        self._outer_questions: dict[str, dict[str, Any]] = {}
        self._owner_answers: dict[tuple[str, str], dict[str, str]] = {}
        self._owner_answer_failures: set[tuple[str, str]] = set()
        self._owner_answer_consumed: set[str] = set()
        self._owner_answer_attempts: dict[str, dict[str, str]] = {}
        self._outer_answer_sequence = 0
        self._ledger: StartLedger | None = None
        self.acceptance: RunnerAcceptanceCarrier | None = None
        self.coordinator_phase: CoordinatorPhaseController | None = None
        self._cleanup_evidence_cache: dict[str, Any] | None = None
        self._candidate_progress: FormalCandidateProgress | None = None
        self._candidate_platform_gate: CandidatePlatformGate | None = None
        # R3.0-002: independent platform MCP gate state for multi-slice tasks.
        # Every flag stays False for tasks without ``multi_slice_workflow``.
        self._multi_slice_workflow = False
        self._multi_slice_artifact_paths: dict[str, Path] = {}
        self._multi_slice_gate_opened = False
        self._multi_slice_gate_feedback_fingerprints: set[str] = set()
        # R3.0-008B segment 1: staged modeling decision state.  Every flag stays
        # False for tasks without ``staged_modeling_decisions``.
        self._staged_decisions = False
        # R3.0-009: unified semantic graph mode; False unless the task opts in.
        self._unified_graph = False
        # R3.0-015 S1: persistent modeling-stage checkpoints.  False for every
        # task without ``modeling_checkpoints``; the flag enables checkpoint
        # saves/inspection only, never a resume capability.
        self._modeling_checkpoints = False
        # R3.0-011: competency-question acceptance state.  Every flag stays
        # False/empty for tasks without ``competency_question_acceptance``.
        self._competency_questions = False
        self._cq_directories: dict[str, Path] = {}
        self._cq_drafts: dict[str, dict[str, Any]] = {}
        self._cq_draft_order: list[str] = []
        self._cq_decisions: dict[str, list[dict[str, Any]]] = {}
        # D2: a question that any production role has already seen is permanently
        # public.  The Runner records the exposure itself at the exposure event
        # (the public-projection write); ``freeze_question_pool`` then rejects any
        # later attempt to land that question hidden (design §5).
        self._cq_exposed: dict[str, list[str]] = {}
        self._cq_freeze: dict[str, Any] | None = None
        self._cq_handoff_complete = False
        self._cq_terminal_reported = False
        self._cq_review_sequence = 0
        self._cq_interview_sequence = 0
        self._cq_projection_written = False
        self._cq_phase: str = "panorama-draft"
        # R3.0-012: the frozen acceptance-target scope (design §2.2).  The
        # default keeps every pre-existing run on ``full_joint``; only a Task
        # that declared ``parameters.acceptance_target: cq_semantic`` (and,
        # per contracts.py, also selected the 011 CQ flow) ever flips it.
        self._acceptance_target = "full_joint"
        # R3.0-012 (design §4.4): the run-local write admission shared by the
        # two staged write entry points and the production handoff, plus the
        # acceptance attempt the handoff allocated (report directory and
        # handoff digest) for the completion channel to verify against.
        self._cq_write_admission = CQWriteAdmission()
        self._cq_acceptance_attempt: dict[str, Any] | None = None
        # R3.0-012 (design §4.5): the read-only acceptance lifecycle.  ``None``
        # until a handoff quiesces the run; ``quiescing`` -> ``acceptance_
        # pending`` when the handoff publishes (cq_semantic scope only) ->
        # ``acceptance_complete`` once the completion channel accepts the
        # current attempt's retained report.  The pending phase holds the
        # terminal report but never dispatches or kills production roles.
        self._cq_acceptance_phase: str | None = None
        # The accepted completion summary retained for idempotent duplicate
        # confirmations (report digest + recomputed aggregate verdict).
        self._cq_acceptance_result: dict[str, Any] | None = None
        # Runner-owned CQ wait windows excluded from the T3 active clock
        # (design §3.2 / Round 4 follow-up (a) and (b)).
        self._cq_wait_windows = CQWaitWindowTracker()
        self._staged_gate_feedback_fingerprints: set[str] = set()
        self._staged_gate_killed = False
        # R3.0-015 S2: the imported completion index of a resumed run.  None
        # on every normal (non-resume) run, so the submit path below behaves
        # byte-identically for runs that never resumed.
        self._resume_imports: dict[str, Any] | None = None
        self._resume_plan: RecoveryPlan | None = None
        self._candidate_receipt_wakeup_sent: set[tuple[str, str]] = set()
        # One typed Protocol response is allowed for each active original
        # Modeling delivery.  The set is Runner-owned so a capability retry
        # cannot emit a second receipt/conflict for the same delivery.
        self._protocol_candidate_responses: dict[str, str] = {}
        self._protocol_candidate_receipt_digests: dict[str, str] = {}
        self._formal_workspace_version: str | None = None
        self._task_overlay: TaskInputOverlay | None = None
        self._validated_candidate_publication: ValidatedCandidatePublication | None = None
        self._candidate_publication: StagedCandidatePublication | None = None
        self._modeling_read_lifecycle: ModelingReadKeyLifecycle | None = None
        self._modeling_read_proxy: ModelingReadProxy | None = None
        self._modeling_context_gate: ModelingContextGate | None = None
        self._formal_failure_latched = False
        # Issue callbacks are invoked by the Broker/App-Server side.  They only
        # append to this queue; Runtime dispatch and evidence writes happen in
        # ``drain`` after all App-Server I/O locks have been released.
        self._issue_event_queue: list[dict[str, Any]] = []
        self._issue_event_lock = threading.Lock()
        # A Broker coordination callback runs while the Broker's emit lock is
        # held.  Queue the Acceptance start here and dispatch it from ``drain``
        # after the callback/observer stack has returned, so Runtime delivery
        # can never re-enter Broker locking.
        self._coordination_runtime_queue: list[dict[str, Any]] = []
        self._coordination_runtime_lock = threading.Lock()
        self._coordination_runtime_message_ids: set[str] = set()
        self._coordination_runtime_signal_keys: set[str] = set()
        self._issue_abort_requested = False
        self._issue_abort_terminal_failure_recorded = False
        # R2.3-009 feedback bookkeeping: typed conflict feedback is counted per
        # (class, code, responsible agent) so later escalation tiers and the
        # run-level timeout evidence can describe what the run already tried.
        self._feedback_counts: dict[tuple[str, str, str], int] = {}
        self._nudges_sent = 0
        self._issues_opened = 0
        self._last_responsible_agent: str | None = None
        # R2.3-009 timeout tiers: one cooperative issue per stall cause, the
        # run-level fallback active clock, and the issue-pending exclusion it
        # must subtract while a cooperative issue pauses the candidate gate.
        self._stall_issue_opened = False
        self._feedback_issue_keys: set[tuple[str, str, str]] = set()
        self._run_fallback_started: float | None = None
        self._issue_pending_started: float | None = None
        self._issue_pending_elapsed = 0.0
        self._run_fallback_timeout_seconds = 10800.0
        self._candidate_redrive_limit = 3
        self._feedback_escalation_repeat = 3
        # Cooperative idle inquiry (start10/12): no role activity + no work in
        # flight + no candidate channel yet is a silent stall the candidate
        # nudges cannot see.  ``_idle_inquiry_baseline`` is reset when the run
        # actually starts so the pre-start period cannot count as idle.  There
        # is deliberately no per-run budget (start15): the idle window between
        # two inquiries is the only rate limit.
        self._idle_inquiry_seconds = 300.0
        self._idle_inquiries_sent = 0
        self._idle_inquiry_baseline: float | None = None

    @staticmethod
    def _safe_run_id(value: str) -> bool:
        import re

        return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", value))

    @staticmethod
    def _write_frozen_bytes(path: Path, payload: bytes, *, mode: int = 0o444) -> None:
        """Write one immutable run-local input without following a symlink."""

        if path.exists() or path.is_symlink():
            raise TeamConfigurationError("frozen input path is already occupied")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, mode)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("frozen input write did not progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, mode)

    @staticmethod
    def _expected_matrix_binding(configuration: TeamConfiguration) -> dict[str, str] | None:
        """Project one proof marker from the loaded Task/Profile contract."""
        profile_binding = configuration.profile.expected_matrix_binding
        task_binding = configuration.task.expected_matrix_binding
        if profile_binding is not None and task_binding is not None and profile_binding != task_binding:
            raise TeamConfigurationError("Profile and Task expected_matrix_binding drift")
        return task_binding or profile_binding

    def _canonical_ledger_root(self) -> Path:
        return self.repository_root / "workspaces" / "modeling-runs"

    def _reject_formal_ledger_root_override(self) -> None:
        """Keep formal runs on the shared repository-owned ledger namespace."""

        if self.ledger_root is None:
            return
        supplied = Path(self.ledger_root).absolute()
        canonical = self._canonical_ledger_root().absolute()
        if supplied != canonical:
            raise TeamConfigurationError(
                "formal R2.3-005 Runner does not accept an alternate ledger_root"
            )

    def _create_ledger(
        self,
        *,
        root: Path,
        config: StartLedgerConfig,
    ) -> StartLedger:
        if self.ledger_factory is None:
            return StartLedger(root, now=self.ledger_now, config=config)
        factory = self.ledger_factory
        # The seam is intentionally explicit for deterministic temporary-ledger
        # tests.  Accept a small set of equivalent signatures so tests can keep
        # the factory independent of the production root while still receiving
        # the immutable requirement policy.
        import inspect

        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError) as exc:
            raise TeamConfigurationError("ledger factory signature is unavailable") from exc
        candidates = (
            {"root": root, "config": config, "now": self.ledger_now},
            {"ledger_root": root, "config": config, "ledger_now": self.ledger_now},
            {"root": root, "config": config},
            {"ledger_root": root, "config": config},
            {"config": config},
            {"root": root},
            {},
        )
        for kwargs in candidates:
            try:
                signature.bind(**kwargs)
            except TypeError:
                continue
            value = factory(**kwargs)
            if type(value) is not StartLedger:
                raise TeamConfigurationError("ledger factory returned an invalid ledger")
            if value.config != config:
                raise TeamConfigurationError("ledger factory configuration drifts")
            try:
                expected_path = (root / config.ledger_filename).resolve()
                expected_lock_path = (root / config.lock_filename).resolve()
                actual_path = Path(value.path).resolve()
                actual_lock_path = Path(value.lock_path).resolve()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise TeamConfigurationError("ledger factory returned invalid ledger paths") from exc
            if actual_path != expected_path or actual_lock_path != expected_lock_path:
                raise TeamConfigurationError(
                    "ledger factory returned paths outside the canonical ledger root"
                )
            return value
        raise TeamConfigurationError("ledger factory signature is invalid")

    def prepare(
        self,
        *,
        run_id: str,
        profile_path: Path,
        task_path: Path,
        scope: dict[str, str],
        task_overlay_path: Path | None = None,
        model_profile_id: str | None = None,
    ) -> TeamRun:
        if self.run is not None or not self._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        # R3.0-002 increment 6(b): non-formal multi-slice tasks load through
        # the three-role branch; every other task keeps the strict formal
        # loader unchanged.
        multi_slice_workflow = task_declares_multi_slice_workflow(task_path)
        if multi_slice_workflow:
            config = load_multi_slice_team_configuration(
                profile_path, task_path, root=self.repository_root
            )
        else:
            config = load_formal_team_configuration(
                profile_path, task_path, root=self.repository_root
            )
        formal_contract = formal_run_contract_for(config)
        if formal_contract is None and (
            config.profile.profile_id in FORMAL_PROFILE_IDS
            or config.task.task_id in FORMAL_TASK_IDS
        ):
            raise TeamConfigurationError("unknown or cross-wired formal run contract")
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            # Re-read through the closed registry so identity/path/asset checks
            # are performed before model/credential/preflight side effects.
            config, formal_contract = load_formal_run_configuration(
                profile_path, task_path, root=self.repository_root
            )
        formal_acceptance = formal_contract is not None
        # The model contract is the first formal gate after configuration
        # loading.  It performs only immutable package reads, so malformed,
        # partial, unsupported, inconsistent, or missing role declarations
        # cannot create a run root, reserve a ledger start, probe the platform,
        # start transport/capabilities, or invoke a process/child factory.
        selected_model_profile_id: str | None = None
        team_model_profile: TeamModelProfile | None = None
        if formal_contract is not None:
            selected_model_profile_id = (
                model_profile_id or formal_contract.default_model_profile_id
            )
            team_model_profile = load_team_model_profile(
                self.repository_root, selected_model_profile_id
            )
            # The formal six-role requirement lives here, not in the shared
            # loader: a formal contract may only ride a profile that binds the
            # complete formal role set.
            if set(team_model_profile.bindings) != set(MODEL_PROFILE_PACKAGE_IDS):
                raise TeamConfigurationError("team model profile role bindings drift")
        elif multi_slice_workflow and model_profile_id is not None:
            # R3.0-006 real validation: an explicit Team Model Profile binds a
            # non-formal multi-slice run's selected roles.  Every roster
            # package must be bound — an unbound role must fail closed here
            # rather than silently ride a package or OpenAI default.
            selected_model_profile_id = model_profile_id
            team_model_profile = load_team_model_profile(
                self.repository_root, selected_model_profile_id
            )
            missing_roles = sorted(
                {
                    agent.package.package_id
                    for agent in config.profile.agents
                }
                - set(team_model_profile.bindings)
            )
            if missing_roles:
                raise TeamConfigurationError(
                    "team model profile is missing roster role bindings: "
                    + ", ".join(missing_roles)
                )
        elif model_profile_id is not None:
            raise TeamConfigurationError(
                "model profile selection requires a formal run contract"
            )
        provider_credential_bindings: dict[str, Any] | None = None
        defer_existing_credential_until_preflight = (
            formal_contract is not None
            and formal_contract.requirement_id == "R2.3-003"
            and formal_contract.is_existing
        )
        if team_model_profile is not None and not defer_existing_credential_until_preflight:
            # The Host ChatGPT subscription preflight runs only when the frozen
            # profile references the Codex built-in route, and strictly before
            # any external credential read, ledger reservation, run-root
            # creation, or Agent start.  A DeepSeek-only profile never triggers
            # it.  Only the fixed safe auth-mode label is retained.
            if profile_requires_codex_subscription_auth(team_model_profile):
                self.codex_subscription_auth_mode = preflight_codex_subscription_auth()
            provider_credential_bindings = preflight_profile_credentials(
                team_model_profile,
                deepseek_credential_path=self.deepseek_credential_path,
                glm_credential_path=self.glm_credential_path,
            )
        if config.task.schema_version == 2 and not self.freeze_started_at:
            raise TeamConfigurationError("v2 Task requires explicit freeze_started_at")
        task_overlay: TaskInputOverlay | None = None
        validated_publication: ValidatedCandidatePublication | None = None
        if task_overlay_path is not None:
            if not formal_acceptance:
                raise TeamConfigurationError("Task overlay is formal R2.3-005-only")
            task_overlay = load_task_input_overlay(
                task_overlay_path,
                root=self.repository_root,
                task_path=task_path,
                task=config.task,
            )
            validated_publication = validate_candidate_publication(task_overlay)
        if formal_acceptance:
            self._reject_formal_ledger_root_override()
        normalized_scope: dict[str, str] = dict(scope)
        if formal_contract is not None:
            normalized_scope = normalize_scope_for_contract(scope, formal_contract.scope_mode)
        root = self.repository_root / "workspaces" / "modeling-runs" / run_id
        if root.exists():
            raise TeamConfigurationError("run directory already exists")
        baseline = self._baseline_manifest(
            run_id=run_id,
            configuration=config,
            profile_path=profile_path,
            task_path=task_path,
            frozen_task_overlay=task_overlay,
            model_profile_id=selected_model_profile_id,
        )
        if team_model_profile is not None:
            self._assert_team_model_profile(baseline, team_model_profile)
        baseline_hash = StartLedger.baseline_hash(baseline)
        preflight_evidence: dict[str, Any] | None = None
        if formal_acceptance:
            # This is deliberately before ledger reservation, run-root creation,
            # scope construction, or any Agent start.  A second baseline read
            # closes the TOCTOU gap between inventory and reservation.
            if formal_contract is not None and formal_contract.is_existing:
                preflight_evidence = run_existing_scope_preflight(
                    repository_root=self.repository_root,
                    scope=normalized_scope,
                    base_url=self.canonical_base_url,
                    admin_key=self.canonical_admin_key,
                    probe=self.prestart_preflight,
                )
                live_scope = preflight_evidence.get("live") if isinstance(preflight_evidence, dict) else None
                if isinstance(live_scope, dict) and isinstance(
                    live_scope.get("workspace_version"), str
                ):
                    self._formal_workspace_version = live_scope["workspace_version"]
            else:
                preflight_evidence = run_prestart_preflight(
                    repository_root=self.repository_root,
                    base_url=self.canonical_base_url,
                    admin_key=self.canonical_admin_key,
                    probe=self.prestart_preflight,
                )
            if task_overlay_path is not None:
                task_overlay = load_task_input_overlay(
                    task_overlay_path,
                    root=self.repository_root,
                    task_path=task_path,
                    task=config.task,
                )
                validated_publication = validate_candidate_publication(task_overlay)
        if defer_existing_credential_until_preflight:
            # R2.3-003 binds an existing live scope.  Read the Host ChatGPT
            # login conclusion and the external model credentials only after
            # that live preflight has proved the retained Project/Ontology
            # state is still safe, while remaining before the profile/baseline
            # re-read, ledger reservation, run-root creation, and any Agent
            # start.
            if profile_requires_codex_subscription_auth(team_model_profile):
                self.codex_subscription_auth_mode = preflight_codex_subscription_auth()
            provider_credential_bindings = preflight_profile_credentials(
                team_model_profile,
                deepseek_credential_path=self.deepseek_credential_path,
                glm_credential_path=self.glm_credential_path,
            )
        if formal_acceptance:
            if team_model_profile is not None:
                # Two-read freeze: digest or parse drift between the initial
                # baseline read and this post-preflight re-read fails closed
                # before reservation and any Agent start.
                reloaded_profile = load_team_model_profile(
                    self.repository_root, team_model_profile.profile_id
                )
                if reloaded_profile != team_model_profile:
                    raise TeamConfigurationError("team model profile drifted during preflight")
            baseline_after_preflight = self._baseline_manifest(
                run_id=run_id,
                configuration=config,
                profile_path=profile_path,
                task_path=task_path,
                frozen_task_overlay=task_overlay,
                model_profile_id=selected_model_profile_id,
            )
            self._assert_team_model_profile(baseline_after_preflight, team_model_profile)
            if StartLedger.baseline_hash(baseline_after_preflight) != baseline_hash:
                raise TeamConfigurationError("baseline manifest drifted during preflight")
        # The proof gate belongs to the loaded Task/Profile contract, not to the
        # formal R2.3-005 workflow flag.  Archived R2.3-002 runs still carry the
        # expected matrix binding and must project that same gate into TeamRun;
        # an unbound R2.3-005 run remains ordinary/non-proof.
        expected_binding = self._expected_matrix_binding(config)
        gate_binding = (
            self._resolve_expected_matrix_binding(expected_binding)
            if expected_binding
            else None
        )
        # R3.0-006 M1: non-formal multi_slice_workflow runs skip the StartLedger
        # budget gate entirely (no reservation, no rejection, no ledger entry);
        # attempts are recorded by the Delivery Agent instead.  Every other v2
        # task keeps its byte-identical ledger binding and reservation.
        multi_slice_budget_exempt = multi_slice_workflow and not formal_acceptance
        if config.task.schema_version == 2 and not multi_slice_budget_exempt:
            ledger_config = resolve_ledger_config(
                formal_contract.ledger_requirement_id
                if formal_contract is not None and formal_contract.ledger_requirement_id
                else R2_3_002_REQUIREMENT_ID
            )
            ledger_root = self._canonical_ledger_root()
            if not formal_acceptance and self.ledger_root is not None:
                ledger_root = self.ledger_root
            self._ledger = self._create_ledger(root=ledger_root, config=ledger_config)
            # The reservation is the freeze gate: no mutable run state exists before it succeeds.
            self._ledger.reserve(
                run_id,
                baseline_hash,
                self.freeze_started_at,
                gate_binding=gate_binding,
            )
        root.mkdir(parents=True, mode=0o700)
        (root / "evidence").mkdir(mode=0o700)
        self.run = TeamRun(
            run_id,
            root,
            config,
            normalized_scope,
            gate_binding=gate_binding,
            team_model_profile=team_model_profile,
            formal_contract=formal_contract,
            provider_credential_bindings=provider_credential_bindings,
            codex_subscription_auth_mode=self.codex_subscription_auth_mode,
        )
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            try:
                self._modeling_context_gate = ModelingContextGate(
                    run_id=run_id,
                    project_id=normalized_scope["project_id"],
                    ontology_id=normalized_scope["ontology_id"],
                )
            except (KeyError, ModelingReadError) as exc:
                raise TeamConfigurationError("R2.3-003 Modeling context gate scope is invalid") from exc
        self._task_overlay = task_overlay
        self._validated_candidate_publication = validated_publication
        self._candidate_publication = (
            stage_candidate_publication(task_overlay, validated_publication, run_root=root)
            if task_overlay is not None and validated_publication is not None
            else None
        )
        self._candidate_progress = (
            FormalCandidateProgress(
                clock=self.monotonic_clock,
                timeout_seconds=config.profile.parameters.get(
                    "candidate_progress_timeout_seconds", 120.0
                ),
                redrive_limit=config.profile.parameters.get(
                    "candidate_redrive_limit", 3
                ),
                allow_post_receipt_revision=(formal_contract is not None),
                # R2.3-009 start6 + T0 defense review (user 2026-08-20): the
                # typed-only post-receipt conflict envelope was unreachable
                # for this requirement (the typed builder is R2.3-003-only),
                # so an accepted-but-defective candidate had no repair
                # channel.  R2.3-008/009 additionally accept the plain
                # six-field conflict; the digest/revision gates below are
                # unchanged, and R2.3-003 keeps its typed envelope contract.
                plain_post_receipt_conflict=(
                    formal_contract is not None
                    and formal_contract.requirement_id in {"R2.3-008", "R2.3-009"}
                ),
                # R2.3-008 start7: keep the envelope gate aligned with
                # candidate registration so an integer revision for any other
                # task is a typed first-delivery rejection, not a post-gate
                # run-killing registration error.
                integer_revisions=(
                    formal_contract is not None
                    and formal_contract.requirement_id == "R2.3-003"
                ),
            )
            if formal_acceptance
            else None
        )
        multi_slice_gate = (
            CandidatePlatformGate.ensure(root / "candidate-gate")
            if formal_acceptance or multi_slice_workflow
            else None
        )
        self._candidate_platform_gate = multi_slice_gate
        if multi_slice_workflow and not formal_acceptance and multi_slice_gate is not None:
            # R3.0-002 increment 7: the independent platform MCP gate starts
            # fail-closed on the missing topology decision and registers the
            # canonical scenario-map artifact paths for the whole run.
            self._multi_slice_workflow = True
            self._multi_slice_artifact_paths = scenario_map_artifact_paths(root)
            # R3.0-006 start3: the Coordinator maintains these artifacts from
            # inside its sandbox through the writable runtime bind of exactly
            # this directory (runtimes/codex.py), so it must exist up front.
            (root / "scenario-map").mkdir(mode=0o700, exist_ok=True)
            self._multi_slice_gate_opened = False
            self._multi_slice_gate_feedback_fingerprints = set()
            multi_slice_gate.close("topology_missing_artifact")
            self._append_evidence(
                "multi-slice-workflow",
                {
                    "event": "artifacts-registered",
                    "gate_state": "closed",
                    "reason_code": "topology_missing_artifact",
                    "artifact_paths": {
                        name: path.relative_to(root).as_posix()
                        for name, path in self._multi_slice_artifact_paths.items()
                    },
                },
            )
        staged_parameters = config.task.parameters or {}
        # R3.0-009: the unified semantic graph flow is an opt-in extension of
        # the staged decisions path (contracts.py already enforces that both
        # underlying capabilities are declared).
        unified_graph = staged_parameters.get(UNIFIED_GRAPH_TASK_PARAMETER) is True
        if multi_slice_workflow and not formal_acceptance and staged_parameters.get(
            STAGED_MODELING_DECISIONS_PARAMETER
        ) is True:
            # R3.0-008B segment 1: staged modeling decisions ride on the
            # R3.0-002 multi-slice workflow.  The Runner prepares only the
            # artifact directories (mkdir); absent files ARE the gate
            # semantics, so no staged artifact is ever pre-created here.
            self._staged_decisions = True
            self._unified_graph = unified_graph
            self._staged_gate_feedback_fingerprints = set()
            self._staged_gate_killed = False
            for directory in staged_decision_directories(root, unified=unified_graph):
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._append_evidence(
                "staged-decisions",
                {
                    "event": "directories-registered",
                    "unified_semantic_graph": unified_graph,
                    "artifact_directories": [
                        path.relative_to(root).as_posix()
                        for path in staged_decision_directories(root, unified=unified_graph)
                    ],
                },
            )
        # R3.0-015 S1: the checkpoint selector rides on the staged path
        # (contracts.py enforces the multi_slice+staged+unified dependencies).
        # Enabling it only registers the checkpoint directory and the
        # save/inspect entry points; it never grants a resume capability.
        if (
            multi_slice_workflow
            and not formal_acceptance
            and self._staged_decisions
            and staged_parameters.get(MODELING_CHECKPOINTS_PARAMETER) is True
        ):
            self._modeling_checkpoints = True
            (root / CHECKPOINT_DIRECTORY).mkdir(mode=0o700, parents=True, exist_ok=True)
            self._append_evidence(
                CHECKPOINT_EVIDENCE_NAME,
                {
                    "event": "selector-enabled",
                    "selector": MODELING_CHECKPOINTS_PARAMETER,
                    "segments": "s1-save-inspect-only",
                },
            )
        cq_selected = staged_parameters.get(COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER) is True
        if multi_slice_workflow and not formal_acceptance and cq_selected:
            # R3.0-011: the competency-question stage.  Only the artifact
            # directories are prepared here (design §3.4); draft/review/freeze
            # files are written later by the Runner or the CQ capability, so an
            # absent file stays the gate semantics.
            self._competency_questions = True
            self._cq_directories = {
                name.split("/")[-1]: self._cq_directory(root, name)
                for name in CQ_RUN_DIRECTORIES
            }
            self._append_evidence(
                "competency-questions",
                {
                    "event": "directories-registered",
                    "selector": COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER,
                    "artifact_directories": list(CQ_RUN_DIRECTORIES),
                },
            )
            self._acceptance_target = normalize_acceptance_target(staged_parameters)
            # R3.0-011 §4.0: the run's configuration snapshot is what the
            # read-only ``cq-acceptance`` command later checks.  A run root
            # without this file is a legacy R2.3 run and can never be switched
            # to the v3 acceptance contract by the command name alone.
            # R3.0-012 (design §2.2): the normalized ``acceptance_target`` is
            # frozen here, before the first real start; the file is rewritten
            # nowhere else, so a later scope change is a digest mismatch, not
            # a silent reinterpretation of the same run.
            self._atomic_json(
                root / "acceptance-v3" / "run-contract.json",
                {
                    "schema_version": "r3-0-011-run-contract/v1",
                    "run_id": run_id,
                    "profile_id": config.profile.profile_id,
                    "task_id": config.task.task_id,
                    "parameters": {
                        COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER: True,
                        "multi_slice_workflow": True,
                        "staged_modeling_decisions": staged_parameters.get(
                            STAGED_MODELING_DECISIONS_PARAMETER
                        )
                        is True,
                        "acceptance_target": normalize_acceptance_target(
                            staged_parameters
                        ),
                    },
                },
            )
        self._protocol_candidate_responses = {}
        self._protocol_candidate_receipt_digests = {}
        self._candidate_receipt_wakeup_sent = set()
        self._formal_failure_latched = False
        acceptance_child_factory = getattr(self.adapter, "acceptance_child_factory", None)
        source_materials: dict[str, Path] = {}
        ticket_policy: dict[str, Any] | None = None
        examiner_descriptors: dict[str, dict[str, Any]] | None = None
        if formal_acceptance:
            for source in config.task.role_sources:
                if source.classification in {"business-source", "consumer-question"}:
                    # Resolve policy digests and Source-child bytes from the
                    # immutable run-local staging copy, not a mutable checkout
                    # path after prepare.
                    source_materials[source.relative_path.as_posix()] = (
                        root / "sources" / "modeling" / source.relative_path
                    )
            ticket_policy = self._acceptance_ticket_policy(config)
            examiner_descriptors = {}
            for kind in ("source", "platform"):
                package_path = self.repository_root / "modeling_team" / "agent-packages" / f"{kind}-examiner" / "package.yaml"
                descriptor = RunnerAcceptanceCarrier.default_descriptor(kind)
                descriptor["package_digest"] = digest_file(package_path)
                examiner_descriptors[kind] = descriptor
        self.acceptance = RunnerAcceptanceCarrier(
            root / "acceptance-carrier",
            task_id=config.task.task_id,
            acceptance_id="acceptance",
            child_factory=acceptance_child_factory if callable(acceptance_child_factory) else None,
            descriptors=examiner_descriptors,
            source_materials=source_materials,
            ticket_policy=ticket_policy,
            candidate_publisher=(
                self._publish_staged_candidate
                if self._candidate_publication is not None
                else None
            ),
            candidate_receipt_builder=(
                self._build_protocol_candidate_receipt
                if formal_acceptance
                else None
            ),
            candidate_conflict_builder=(
                self._build_protocol_candidate_conflict
                if formal_acceptance
                else None
            ),
            staged_submission_handler=(
                self._handle_staged_submit_modeling_batch if self._staged_decisions else None
            ),
            staged_association_handler=(
                self._handle_staged_associate_evidence if self._staged_decisions else None
            ),
            cq_draft_handler=(
                self._publish_cq_question_draft if self._competency_questions else None
            ),
            staged_protocol_capability=self._staged_decisions,
        )
        self.coordinator_phase = CoordinatorPhaseController()
        self.run.acceptance = self.acceptance
        self._atomic_json(
            root / "state.json",
            {
                "state": "PREPARING",
                "run_id": run_id,
                "profile_id": config.profile.profile_id,
                "task_id": config.task.task_id,
                "formal_roles": [agent.package.role for agent in config.profile.agents],
                "acceptance_carrier": "acceptance-carrier",
            },
        )
        shutil.copyfile(profile_path, root / "profile.snapshot.yaml")
        if task_overlay is None:
            shutil.copyfile(task_path, root / "task.snapshot.yaml")
        else:
            self._write_frozen_bytes(root / "task.snapshot.yaml", task_overlay.base_task_bytes)
            self._write_frozen_bytes(
                root / "task-overlay.snapshot.yaml",
                task_overlay.overlay_bytes,
            )
            self._write_frozen_bytes(
                root / "candidate-publication-manifest.json",
                json.dumps(
                    task_overlay.manifest(),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
            )
        self._stage_sources()
        self._record_runtime_core_hashes("before_start")
        self._atomic_json(root / "baseline-manifest.json", baseline)
        if preflight_evidence is not None:
            self._atomic_json(root / "evidence" / "prestart-preflight.json", preflight_evidence)
        self.run.baseline_hash = baseline_hash
        if config.task.schema_version == 2:
            self._append_evidence(
                "start-ledger",
                {
                    "event": "reservation",
                    "baseline_hash": self.run.baseline_hash,
                    **self._formal_ledger_identity(),
                },
            )
        return self.run

    @staticmethod
    def _assert_team_model_profile(
        baseline: dict[str, Any], team_model_profile: TeamModelProfile | None
    ) -> None:
        if team_model_profile is None:
            raise TeamConfigurationError("formal team model profile is unavailable")
        binding = baseline.get("team_model_profile")
        if (
            not isinstance(binding, dict)
            or binding.get("profile_id") != team_model_profile.profile_id
            or binding.get("path") != team_model_profile.relative_path
            or binding.get("sha256") != team_model_profile.digest
            or binding.get("roles") != team_model_profile.as_dict()["roles"]
        ):
            raise TeamConfigurationError("formal team model profile digest drifted")

    def _acceptance_ticket_policy(self, configuration: TeamConfiguration) -> dict[str, Any]:
        """Load the requirement-owned CQ/source standard without any answers."""

        parameter = configuration.profile.parameters.get("acceptance_standard")
        if not isinstance(parameter, str) or not parameter:
            raise TeamConfigurationError("formal profile omits acceptance standard")
        standard_path = (self.repository_root / parameter).resolve()
        if self.repository_root.resolve() not in standard_path.parents:
            raise TeamConfigurationError("acceptance standard escapes repository")
        try:
            standard = json.loads(standard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TeamConfigurationError("acceptance standard is unreadable") from exc
        if not isinstance(standard, dict):
            raise TeamConfigurationError("acceptance standard is not an object")
        questions = standard.get("competency_questions")
        if not isinstance(questions, list) or not questions:
            raise TeamConfigurationError("acceptance standard must declare at least one competency question")
        normalized_questions: list[dict[str, str]] = []
        source_paths_by_question: dict[str, list[str]] = {}
        question_ids: set[str] = set()
        for item in questions:
            if not isinstance(item, dict) or set(item) != {"id", "question", "approved_source_paths"}:
                raise TeamConfigurationError("acceptance standard competency question fields drift")
            if not isinstance(item["id"], str) or not isinstance(item["question"], str) or not item["id"] or not item["question"]:
                raise TeamConfigurationError("acceptance standard competency question is invalid")
            if item["id"] in question_ids:
                raise TeamConfigurationError("acceptance standard competency question IDs are duplicated")
            paths = item["approved_source_paths"]
            if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                raise TeamConfigurationError("acceptance standard source paths are invalid")
            question_ids.add(item["id"])
            normalized_questions.append({"id": item["id"], "question": item["question"]})
            source_paths_by_question[item["id"]] = sorted(paths)
        requirement_id = formal_run_contract_for(configuration).requirement_id if formal_run_contract_for(configuration) else None
        unknown_policy = standard.get("unknown_policy")
        deletion = None
        if requirement_id == "R2.3-003":
            try:
                deletion = validate_deletion_policy(unknown_policy)
            except ValueError as exc:
                raise TeamConfigurationError(str(exc)) from exc
            if tuple(item["semantic_id"] for item in deletion["targets"]) != R2_3_003_TARGET_IDS:
                raise TeamConfigurationError("R2.3-003 acceptance target IDs drift")
        elif unknown_policy != "preserve-explicit-unknown":
            raise TeamConfigurationError("formal create acceptance unknown policy drifts")
        artifact = {"path": parameter, "digest": digest_file(standard_path)}
        return {
            "quality_standard_ref": str(standard.get("requirement_ref", "")),
            "quality_standard_digest": artifact["digest"],
            "quality_standard_artifact": artifact,
            "unknown_policy": deletion if deletion is not None else unknown_policy,
            "deletion_policy": deletion,
            "competency_questions": normalized_questions,
            "approved_source_paths_by_question": source_paths_by_question,
            "question_count": len(normalized_questions),
        }

    def _stage_sources(self) -> None:
        assert self.run
        task = self.run.configuration.task
        sources = self.run.root / "sources"
        sources.mkdir(mode=0o700)
        manifest: list[dict[str, Any]] = []
        if task.schema_version == 1:
            for source in task.allowed_sources:
                target = sources / source.name
                shutil.copyfile(source, target)
                os.chmod(target, 0o444)
                manifest.append({"path": source.name, "sha256": digest_file(source), "roles": ["all"]})
        else:
            for agent in self.run.configuration.profile.agents:
                (sources / agent.package.role).mkdir(mode=0o700, parents=True, exist_ok=True)
            for source in task.role_sources:
                for role in source.roles:
                    target = sources / role / source.relative_path
                    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    shutil.copyfile(source.path, target)
                    os.chmod(target, 0o444)
                manifest.append(
                    {
                        "path": source.relative_path.as_posix(),
                        "classification": source.classification,
                        "roles": sorted(source.roles),
                        "sha256": digest_file(source.path),
                    }
                )
        self._atomic_json(self.run.root / "source-manifest.json", {"sources": manifest})

    def _baseline_manifest(
        self,
        *,
        run_id: str,
        configuration: TeamConfiguration,
        profile_path: Path,
        task_path: Path,
        task_overlay_path: Path | None = None,
        frozen_task_overlay: TaskInputOverlay | None = None,
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        if task_overlay_path is not None and frozen_task_overlay is not None:
            raise TeamConfigurationError("Task overlay cannot be both live and frozen")
        files = {
            "runner": self.repository_root / "modeling_team/runner.py",
            "acceptance_contract": self.repository_root / "modeling_team/acceptance.py",
            "acceptance_runtime": self.repository_root / "modeling_team/acceptance_runtime.py",
            "capability_mcp": self.repository_root / "modeling_team/capability_mcp.py",
            "staged_batch_write_forwarder": self.repository_root
            / "modeling_team/staged_batch_write_forwarder.py",
            "task_overlay": self.repository_root / "modeling_team/task_overlay.py",
            "candidate_publication": self.repository_root / "modeling_team/candidate_publication.py",
            "read_proxy_mcp": self.repository_root / "modeling_team/read_proxy_mcp.py",
            "report_sink_mcp": self.repository_root / "modeling_team/report_sink_mcp.py",
            "preflight": self.repository_root / "modeling_team/preflight.py",
            "codex_adapter": self.repository_root / "modeling_team/runtimes/codex.py",
            "team_transport": self.repository_root / "modeling_team/transport_mcp.py",
            "team_transport_interventions": self.repository_root / "modeling_team/interventions.py",
            "platform_scope": self.repository_root / "modeling_team/platform_scope.py",
            "protocol_mcp_launch": self.repository_root / "modeling_team/protocol_mcp_launch.py",
            "candidate_platform_gate": self.repository_root / "modeling_team/candidate_platform_gate.py",
            "protocol_mechanics": self.repository_root / "modeling_team/protocol_mechanics.py",
            "proof_v2": self.repository_root / "modeling_team/proof_v2.py",
            "proof_matrix_generator": self.repository_root / "modeling_team/matrix_artifact.py",
            "proof_matrix_retained_handoff": self.repository_root / "modeling_team/references/r2-3-002-retained-rev7-handoff.json",
            "proof_matrix_source_manifest": self.repository_root / "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/manifest.json",
            "protocol_retrieval_mcp": self.repository_root / "modeling_team/protocol_retrieval_mcp.py",
            "protocol_retrieval_verifier": self.repository_root / "modeling_team/protocol_mechanics.py",
            "foreground_monitor": self.repository_root / "modeling_team/foreground_monitor.py",
            "foreground_cli": self.repository_root / "modeling_team/__main__.py",
            "monitor_handoff": self.repository_root / "modeling_team/monitor_handoff.py",
            "candidate_required_assertions": self.repository_root / "modeling_team/references/candidate-required-assertions-v1.json",
            "native_retrieval_proof": self.repository_root / "modeling_team/references/native-retrieval-proof-v1.json",
            "candidate_required_assertions_v2": self.repository_root / "modeling_team/references/candidate-required-assertions-v2.json",
            "native_retrieval_proof_v2": self.repository_root / "modeling_team/references/native-retrieval-proof-v2.json",
            "p2_monitor_contract": self.repository_root / "modeling_team/references/p2-monitor-contract.json",
            "p2_monitor_handoff_contract": self.repository_root / "modeling_team/references/p2-monitor-handoff-contract.json",
            "p2_protocol_driver": self.repository_root / "modeling_team/p2_protocol_driver.py",
            "p2_protocol_driver_contract": self.repository_root / "modeling_team/references/p2-protocol-driver-contract.json",
            "p2a_protocol_driver": self.repository_root / "modeling_team/p2a_protocol_driver.py",
            "p2a_protocol_driver_contract": self.repository_root / "modeling_team/references/p2a-protocol-driver-contract.json",
            "p2_monitor_adverse_order_profile": self.repository_root / "modeling_team/profiles/p2-adverse-order-smoke.yaml",
            "p2_monitor_adverse_order_task": self.repository_root / "modeling_team/tasks/p2-adverse-order-smoke.yaml",
            "protocol_reasoner_script": self.repository_root / "backend/scripts/dev_owl_reasoner.py",
            "start_ledger": self.repository_root / "modeling_team/start_ledger.py",
            "profile": profile_path,
            "task": task_path,
            "examiner_source_package": self.repository_root / "modeling_team/agent-packages/source-examiner/package.yaml",
            "examiner_source_instructions": self.repository_root / "modeling_team/agent-packages/source-examiner/instructions.md",
            "examiner_platform_package": self.repository_root / "modeling_team/agent-packages/platform-examiner/package.yaml",
            "examiner_platform_instructions": self.repository_root / "modeling_team/agent-packages/platform-examiner/instructions.md",
            "examiner_source_skill": self.repository_root / "modeling_team/skills/source-examiner/SKILL.md",
            "examiner_platform_skill": self.repository_root / "modeling_team/skills/platform-examiner/SKILL.md",
        }
        task_overlay = frozen_task_overlay
        if task_overlay is None and task_overlay_path is not None:
            task_overlay = load_task_input_overlay(
                task_overlay_path,
                root=self.repository_root,
                task_path=task_path,
                task=configuration.task,
            )
            validate_candidate_publication(task_overlay)
        for agent in configuration.profile.agents:
            files[f"package:{agent.package.package_id}"] = self.repository_root / "modeling_team/agent-packages" / agent.package.package_id / "package.yaml"
            files[f"instructions:{agent.package.package_id}"] = agent.package.instructions_path
            for reference in agent.package.references:
                files[f"reference:{agent.package.package_id}:{reference.relative_to(self.repository_root).as_posix()}"] = reference
            for skill in agent.package.required_skills:
                files[f"skill:{agent.package.package_id}:{skill.name}"] = skill
        for source in configuration.task.allowed_sources:
            files[f"source:{source.relative_to(self.repository_root).as_posix()}"] = source
        if configuration.task.schema_version == 2:
            for source in configuration.task.role_sources:
                files[f"source:{source.path.relative_to(self.repository_root).as_posix()}"] = source.path
        platform = self.repository_root / "backend/app/mcp"
        if platform.is_dir():
            for source in sorted(platform.rglob("*.py")):
                files[f"mcp:{source.relative_to(self.repository_root).as_posix()}"] = source
        reasoner = files["protocol_reasoner_script"]
        if reasoner.is_symlink() or not reasoner.is_file():
            raise TeamConfigurationError("Protocol reasoner script is unavailable for baseline")
        if configuration.task.schema_version == 2:
            matrix = self.repository_root / _PROOF_MATRIX_RELATIVE
            p2a = self.repository_root / _P2A_PASS_RELATIVE
            # The expected binding is fixed in Task/Profile for fresh R2.3
            # runs.  Legacy cumulative tests may compute a baseline before
            # the tester-owned artifacts are installed; retain that path's
            # compatibility while binding actual artifacts whenever present.
            expected_binding = configuration.task.expected_matrix_binding or configuration.profile.expected_matrix_binding
            if expected_binding is not None and (not matrix.is_file() or not p2a.is_file()):
                raise TeamConfigurationError("proof matrix/P2a artifacts are unavailable for baseline")
            if matrix.is_file() and not matrix.is_symlink():
                files["proof_matrix_artifact"] = matrix
            if p2a.is_file() and not p2a.is_symlink():
                files["p2a_pass_artifact"] = p2a
        formal_contract = formal_run_contract_for(configuration)
        formal_acceptance_contract = formal_contract is not None
        selected_profile_id = model_profile_id
        if selected_profile_id is None and formal_acceptance_contract:
            assert formal_contract is not None
            selected_profile_id = formal_contract.default_model_profile_id
        if selected_profile_id is not None:
            files["team_model_profile"] = (
                self.repository_root
                / MODEL_PROFILE_DIRECTORY
                / f"{selected_profile_id}.yaml"
            )
        if formal_acceptance_contract:
            assert formal_contract is not None
            if formal_contract.requirement_id == "R2.3-003":
                files["modeling_readonly"] = self.repository_root / "modeling_team/modeling_readonly.py"
        digests = {name: digest_file(path) for name, path in sorted(files.items())}
        if task_overlay is not None:
            digests["task_input_overlay"] = task_overlay.sha256
            digests["candidate_publication_source"] = (
                task_overlay.candidate_publication.sha256
            )
        runner_capability_roles = {
            "protocol": [
                "protocol_list_platform_artifacts",
                "protocol_build_acceptance_stage_handoff",
            ],
            "coordinator": [
                "coordinator_ticket_draft",
                "coordinator_publish_acceptance_ticket",
                "coordinator_get_verdict",
            ],
            "acceptance": [
                "acceptance_get_ticket",
                "acceptance_child_start",
                "acceptance_child_get_report",
                "acceptance_child_recycle",
                "acceptance_get_failure_record",
                "build_acceptance_verdict",
                "submit_acceptance_result",
                "acceptance_get_verdict",
            ],
        }
        if formal_acceptance_contract:
            runner_capability_roles["coordinator"].insert(
                1, "coordinator_ticket_draft_from_delivery"
            )
        if task_overlay is not None:
            runner_capability_roles["modeling"] = ["modeling_publish_staged_candidate"]
        baseline = {
            "run_id": run_id,
            **(
                {"task_input_overlay": task_overlay.manifest()}
                if task_overlay is not None
                else {}
            ),
            "files": digests,
            "call_sites": {
                "runner.prepare": digests["runner"],
                "runner.start": digests["runner"],
                "runner._baseline_manifest": digests["runner"],
                "runner.terminal_handoff_settlement_cleanup": digests["runner"],
                "codex.start_roster": digests["codex_adapter"],
                "codex.start_task": digests["codex_adapter"],
                "transport.send": digests["team_transport"],
                "transport.report": digests["team_transport"],
                "transport.staged_interventions": digests["team_transport_interventions"],
                "transport.mcp_response_report_observer": digests["team_transport"],
                "transport.ack_terminal_handoff": digests["team_transport"],
                "foreground_monitor.extract_adverse_order": digests["foreground_monitor"],
                "foreground_monitor.run_foreground": digests["foreground_monitor"],
                "foreground_cli.monitor_handoff": digests["foreground_cli"],
                "monitor_handoff.protocol": digests["monitor_handoff"],
                "runner.terminal_handoff_evidence": digests["runner"],
                "runner.team_transport_event_sink": digests["runner"],
                "runner.proof_v2_preflight": digests["runner"],
                "runner.proof_v2_matrix_generator": digests["proof_matrix_generator"],
                "runner.outer_answer_fsync_delivery": digests["runner"],
                "runner.acceptance_carrier": digests["runner"],
                "runner.capability_broker": digests["capability_mcp"],
                "runner.task_overlay": digests["task_overlay"],
                "runner.candidate_publication": digests["candidate_publication"],
                "runner.acceptance_child_runtime": digests["acceptance_runtime"],
                "runner.acceptance_read_proxy": digests["read_proxy_mcp"],
                **(
                    {"runner.modeling_read_surface": digests["modeling_readonly"]}
                    if formal_contract is not None and formal_contract.requirement_id == "R2.3-003"
                    else {}
                ),
                "runner.acceptance_report_sink": digests["report_sink_mcp"],
                "runner.coordination_phase_callback": digests["runner"],
                "p2_protocol_driver.main": digests["p2_protocol_driver"],
                "p2a_protocol_driver.main": digests["p2a_protocol_driver"],
            },
            "runtime_contract": {
                "team_transport": {
                    "server": "team_transport",
                    "command": "/usr/bin/python3",
                    "args": ["/agent/home/transport_mcp.py"],
                    "source_path": "modeling_team/transport_mcp.py",
                    "sha256": digests["team_transport"],
                    "staged_dependency": {
                        "source_path": "modeling_team/interventions.py",
                        "staged_path": "/agent/home/interventions.py",
                        "sha256": digests["team_transport_interventions"],
                        "mode": "0444",
                    },
                },
                "runner_capability_mcp": {
                    "server": "runner_capability",
                    "source_path": "modeling_team/capability_mcp.py",
                    "sha256": digests["capability_mcp"],
                    "roles": runner_capability_roles,
                    "socket_mode": "0600",
                    "token_file_mode": "0400",
                },
                "examiner_children": {
                    "kinds": ["source_examiner", "platform_examiner"],
                    "source_package": {
                        "path": "modeling_team/agent-packages/source-examiner/package.yaml",
                        "sha256": digests["examiner_source_package"],
                        "instructions_sha256": digests["examiner_source_instructions"],
                        "skill_sha256": digests["examiner_source_skill"],
                        "platform_mode": "none",
                    },
                    "platform_package": {
                        "path": "modeling_team/agent-packages/platform-examiner/package.yaml",
                        "sha256": digests["examiner_platform_package"],
                        "instructions_sha256": digests["examiner_platform_instructions"],
                        "skill_sha256": digests["examiner_platform_skill"],
                        "platform_mode": "read",
                    },
                    "read_proxy": {
                        "source_path": "modeling_team/read_proxy_mcp.py",
                        "sha256": digests["read_proxy_mcp"],
                        "socket_mode": "0600",
                        "token_file_mode": "0400",
                    },
                    "report_sink": {
                        "source_path": "modeling_team/report_sink_mcp.py",
                        "sha256": digests["report_sink_mcp"],
                        "socket_mode": "0600",
                        "token_file_mode": "0400",
                    },
                    "private_runtime": {
                        "home_mode": "0700",
                        "auth_mode": "0600",
                        "env": ["CODEX_HOME", "HOME", "PATH", "TERM", "LANG", "LC_ALL"],
                        "team_transport": False,
                        "generic_spawn": False,
                    },
                },
                "protocol_mcp_mode_env": canonical_protocol_mcp_mode_contract(),
                "protocol_mcp_reasoner_env": protocol_mcp_reasoner_contract(),
                "protocol_retrieval_mcp": {
                    "server": "protocol_mechanics",
                    "command": "/usr/bin/python3",
                    "args": ["/opt/protocol-retrieval-mcp.py"],
                    "runtime_run_id_env": "PROTOCOL_RUNTIME_RUN_ID",
                    "runtime_context_path": "/opt/mechanics-contract.json",
                    "tools": [
                        "build_candidate_receipt",
                        "verify_scoped_retrieval_fallback",
                        "write_candidate_item_evidence_map",
                        "translate_candidate_to_batches",
                    ],
                },
                "proof_v2": {
                    "candidate_schema": "candidate-required-assertions/v2",
                    "candidate_item_evidence_map_path": "evidence/candidate-item-evidence-map.json",
                    "candidate_item_evidence_map_schema": "r2-3-002-candidate-item-evidence-map/v1",
                    "matrix_path": _PROOF_MATRIX_RELATIVE,
                    "p2a_pass_path": _P2A_PASS_RELATIVE,
                    "matrix_schema": _MATRIX_SCHEMA,
                    "p2a_pass_schema": _P2A_SCHEMA,
                    "runtime_asset": {
                        "source_path": "modeling_team/proof_v2.py",
                        "staged_path": "runtime-assets/protocol/proof_v2.py",
                        "mount_path": "/opt/proof_v2.py",
                        "mode": "0600",
                        "parent_mode": "0700",
                        "sha256": digests["proof_v2"],
                    },
                },
                "p2_protocol_driver": {
                    "command": "uv",
                    "argv": [
                        "run",
                        "--project",
                        "backend",
                        "python",
                        "-m",
                        "modeling_team.p2_protocol_driver",
                        "--contract",
                        "modeling_team/references/p2-protocol-driver-contract.json",
                    ],
                    "contract_file": "modeling_team/references/p2-protocol-driver-contract.json",
                    "candidate_sender_id": "p2-synthetic-modeling",
                    "protocol_agent_id": "protocol",
                    "required_terminal_stage": "protocol_report_accepted",
                },
                "p2a_protocol_driver": {
                    "command": "uv",
                    "argv": [
                        "run",
                        "--project",
                        "backend",
                        "python",
                        "-m",
                        "modeling_team.p2a_protocol_driver",
                        "--contract",
                        "modeling_team/references/p2a-protocol-driver-contract.json",
                    ],
                    "contract_file": "modeling_team/references/p2a-protocol-driver-contract.json",
                    "candidate_sender_id": "p2a-synthetic-modeling",
                    "protocol_agent_id": "protocol",
                    "required_terminal_stage": "protocol_report_accepted",
                    "semantic_start_written": False,
                },
                "p2_monitor_adverse_order": {
                    "profile_file": "modeling_team/profiles/p2-adverse-order-smoke.yaml",
                    "task_file": "modeling_team/tasks/p2-adverse-order-smoke.yaml",
                    "extractor": "modeling_team.foreground_monitor.extract_adverse_order",
                    "evidence_file": "evidence/p2-adverse-order.jsonl",
                    "required_order": [
                        "protocol_report_rejected_missing_modeling_handoff",
                        "modeling_terminal_handoff_delivered",
                        "terminal_handoff_ack_accepted",
                        "protocol_report_retry_accepted",
                        "all_four_terminal_results_completed",
                        "all_four_settled",
                    ],
                    "handoff_contract": "modeling_team/references/p2-monitor-handoff-contract.json",
                    "handoff_environment": "ONTOLOGY_P2_MONITOR_HANDOFF",
                    "handoff_phase_deadlines_seconds": {
                        "prepared": 30.0,
                        "foreground_run": 120.0,
                        "extraction_complete": 30.0,
                    },
                    "handoff_phases": [
                        "prepared",
                        "cleanup_pending",
                        "extraction_complete",
                        "extraction_failed",
                    ],
                },
            },
            "expected_matrix_binding": configuration.task.expected_matrix_binding or configuration.profile.expected_matrix_binding,
        }
        if selected_profile_id is not None:
            profile = load_team_model_profile(self.repository_root, selected_profile_id)
            if profile.digest != digests["team_model_profile"]:
                raise TeamConfigurationError("team model profile digest is inconsistent")
            # Safe projection only: identity, repo-relative path, source digest,
            # and per-role provider/model/effort.  No endpoint, credential
            # path/value/digest, or provider free text.
            baseline["team_model_profile"] = profile.as_dict()
        if formal_acceptance_contract:
            assert formal_contract is not None
            if formal_contract.requirement_id == "R2.3-003":
                baseline["runtime_contract"]["modeling_read_proxy"] = {
                    "server": "modeling_read_proxy",
                    "source_path": "modeling_team/modeling_readonly.py",
                    "bridge_source_path": "modeling_team/read_proxy_mcp.py",
                    "sha256": digests["modeling_readonly"],
                    "bridge_sha256": digests["read_proxy_mcp"],
                    "tools": list(MODELING_READ_TOOLS),
                    "socket_mode": "0600",
                    "token_file_mode": "0400",
                    "scope": "exact-project-ontology",
                }
        return baseline

    @classmethod
    def preview_baseline(
        cls,
        *,
        repository_root: Path,
        run_id: str,
        profile_path: Path,
        task_path: Path,
        task_overlay_path: Path | None = None,
        model_profile_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Compute the prepare-time binding without creating any run or ledger state."""
        if not cls._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        # R3.0-002 increment 6(b) completion: the prepare-time preview loads
        # through the same dispatch as ``prepare`` itself, so a non-formal
        # multi-slice Task no longer trips the strict four-role loader here.
        multi_slice_workflow = task_declares_multi_slice_workflow(task_path)
        if multi_slice_workflow:
            configuration = load_multi_slice_team_configuration(
                profile_path, task_path, root=repository_root
            )
        else:
            configuration = load_formal_team_configuration(
                profile_path, task_path, root=repository_root
            )
        formal_contract = formal_run_contract_for(configuration)
        if (
            model_profile_id is not None
            and formal_contract is None
            and not multi_slice_workflow
        ):
            raise TeamConfigurationError(
                "model profile selection requires a formal run contract"
            )
        if formal_contract is not None:
            configuration, _ = load_formal_run_configuration(
                profile_path, task_path, root=repository_root
            )
        elif (
            configuration.profile.profile_id in FORMAL_PROFILE_IDS
            or configuration.task.task_id in FORMAL_TASK_IDS
        ):
            raise TeamConfigurationError("unknown or cross-wired formal run contract")
        probe = object.__new__(cls)
        probe.repository_root = repository_root
        manifest = probe._baseline_manifest(
            run_id=run_id,
            configuration=configuration,
            profile_path=profile_path,
            task_path=task_path,
            task_overlay_path=task_overlay_path,
            model_profile_id=model_profile_id,
        )
        return manifest, StartLedger.baseline_hash(manifest)

    def _formal_coordination_enabled(self) -> bool:
        if not self.run:
            return False
        if getattr(self.run, "formal_contract", None) is not None:
            return True
        configuration = getattr(self.run, "configuration", None)
        task = getattr(configuration, "task", None)
        profile = getattr(configuration, "profile", None)
        return bool(
            getattr(task, "schema_version", 1) == 2
            and (
                getattr(task, "task_id", None)
                in {"r2-3-005-formal-acceptance", "r2-3-003-existing-scope-incremental"}
                or getattr(profile, "profile_id", None)
                in {"r2-3-005-modeling-team", "r2-3-003-modeling-team"}
            )
        )

    def _project_binding(self) -> str | None:
        """Resolve the Project identity owned by this run's coordination mode.

        Formal R2.3-005 create-mode runs receive their Project from the live
        ``PlatformScope`` after ``prepare``.  Their normalized ``TeamRun.scope``
        intentionally contains only ``{"mode": "create"}``, so falling back to
        that input would permit a caller-supplied identity to smuggle into outer
        question/answer evidence.  Historical non-formal runs retain the legacy
        ``TeamRun.scope`` binding, including schema-v2 R2.3-002 fixtures.
        """

        if self._formal_coordination_enabled():
            project_id = getattr(self.scope, "project_id", None) if self.scope is not None else None
        elif self.run is not None:
            project_id = self.run.scope.get("project_id")
            if project_id is None and self._multi_slice_workflow and self.scope is not None:
                # R3.0-006 start1: a non-formal multi-slice create run also
                # normalizes ``TeamRun.scope`` to ``{"mode": "create"}``, so the
                # legacy dict lookup left the outer question/answer interview
                # channel without a Project binding and killed the run on the
                # first Host question registration.  The live PlatformScope is
                # the single writer that created the Project; resolve the
                # binding from it exactly as the formal branch does.
                project_id = getattr(self.scope, "project_id", None)
        else:
            project_id = None
        return project_id if isinstance(project_id, str) and project_id else None

    def _coordination_phase_callback(
        self,
        sender_id: str,
        recipient_id: str,
        message_kind: str,
        text: str,
        generation: int,
    ) -> dict[str, Any]:
        """Validate model-visible coordination before Broker evidence is accepted."""

        if not self.coordinator_phase:
            raise TeamConfigurationError("Coordinator phase controller is unavailable")
        if message_kind == "ready_for_acceptance":
            return self.coordinator_phase.readiness(
                sender_id=sender_id,
                message_kind=message_kind,
                text=text,
                generation=generation,
            )
        if message_kind == "silent_for_acceptance":
            return self.coordinator_phase.readiness(
                sender_id=sender_id,
                message_kind=message_kind,
                text=text,
                generation=generation,
            )
        if message_kind == "acceptance_start":
            # Formal R2.3-005 keeps Coordinator as the sole round selector,
            # while the Runner-owned carrier validates that selection before
            # the generic controller changes phase or the observer queues the
            # Acceptance delivery.  Reject the generic controller's own
            # out-of-phase/stale-generation cases first so a rejected request
            # cannot append even a passive CQ2 revalidation record.
            formal_sequential = (
                self._formal_coordination_enabled()
                and self.acceptance is not None
                and getattr(self.acceptance, "_ticket_policy", None) is not None
            )
            if formal_sequential:
                phase = getattr(self.coordinator_phase, "phase", None)
                phase_value = getattr(phase, "value", phase)
                controller = self.coordinator_phase
                if (
                    sender_id != controller.coordinator_id
                    or phase_value != "WAITING_ACCEPTANCE"
                    or not isinstance(text, str)
                    or not text
                    or isinstance(generation, bool)
                    or not isinstance(generation, int)
                    or generation != controller.generation
                ):
                    return controller.start_acceptance_round(
                        sender_id=sender_id,
                        round_id=text,
                        generation=generation,
                    )
                self.acceptance.validate_coordinator_acceptance_start(round_id=text)
            return self.coordinator_phase.start_acceptance_round(
                sender_id=sender_id,
                round_id=text,
                generation=generation,
            )
        if message_kind == "acceptance_verdict_route":
            try:
                verdict = json.loads(text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise TeamConfigurationError("Acceptance verdict route is not canonical JSON") from exc
            if not isinstance(verdict, dict):
                raise TeamConfigurationError("Acceptance verdict route is not an object")
            return self.coordinator_phase.route_verdict(
                sender_id=sender_id,
                verdict=verdict,
                generation=generation,
            )
        raise TeamConfigurationError("coordination kind is not fixed by the formal Profile")

    def _terminal_report_guard(
        self,
        agent_id: str,
        already_synchronized: bool = False,
        status: str = "completed",
    ) -> bool:
        """Compose the existing Runtime guard with the formal Coordinator terminal gate.

        The Runtime guard still owns protocol retrieval safety.  For the formal four-role
        run, Acceptance and Coordinator are additionally blocked until Acceptance has
        persisted two same-state PASS verdicts, reclaimed both child pairs, and committed
        settlement CAS/readback.  No model/SSE/``agent_end`` semantics are changed here.
        """

        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return True
        # R2.3-009 follow-up (user 2026-08-20): a role self-declares that its
        # task is complete or definitively stuck, so the host-side Runtime
        # guard (e.g. Protocol retrieval-evidence completeness) gates only
        # ``completed`` reports.  A ``blocked`` role must always be able to
        # report, otherwise a platform-side deadlock has no exit but T3.
        adapter_guard = getattr(self.adapter, "terminal_report_blocked", None)
        if callable(adapter_guard) and status == "completed":
            try:
                if _call_terminal_report_guard(
                    adapter_guard,
                    agent_id,
                    already_synchronized,
                    status,
                ):
                    return True
            except Exception:
                return True
        # R3.0-011: the competency-question role may only report terminal after
        # the host-only ``cq_handoff_complete`` admission.  A premature report is
        # rejected for this call only, with the current phase and the
        # continuation action; nothing is latched and the run keeps running
        # (design §3.2).  A ``blocked`` CQ report still passes: an unrepairable
        # role keeps its existing exit instead of deadlocking into T3.
        cq_reason = self._cq_terminal_block_reason(agent_id)
        if cq_reason is not None and status != "blocked":
            self._deliver_cq_terminal_rejection(agent_id, cq_reason)
            return True
        if self._formal_coordination_enabled() and self.run is not None:
            role_ids = {
                agent.package.role: agent.agent_id
                for agent in self.run.configuration.profile.agents
            }
            coordinator_id = role_ids.get("coordinator", "coordinator")
            if agent_id == coordinator_id:
                # T0 defense review (user 2026-08-20, R2.3-009 start6): a
                # blocked Coordinator no longer requires Acceptance
                # settlement.  Settlement protects verdict completeness for
                # ``completed`` runs; a run the roles judge unrepairable must
                # reach the agent-blocked exit instead of deadlocking to T3.
                if status == "blocked":
                    return False
                return self.acceptance is None or not self.acceptance.is_settled
            acceptance_id = role_ids.get("acceptance", "acceptance")
            if agent_id == acceptance_id:
                # Acceptance cannot terminate after merely producing a
                # verdict. Only a completed report may cross this boundary, and
                # the Delivery/Runner path must first perform the complete
                # cleanup + CAS/readback settlement transition. Incomplete and
                # failed reports remain live even if a stale carrier happens
                # to expose a settled flag.  ``blocked`` is the one exception
                # (T0 defense review, user 2026-08-20): without it an
                # unrepairable run has no exit but the 90-minute T3 timeout.
                if status == "blocked":
                    return False
                if status != "completed":
                    return True
                self._finalize_acceptance_if_ready()
                return self.acceptance is None or not self.acceptance.is_settled
        # R3.0-008B staged runs: the Coordinator may not report ``completed``
        # while the joint acceptance checklist is missing or structurally
        # invalid (design section 3.7 terminal gate).  A ``blocked`` report
        # always passes (T0: an unrepairable run keeps its exit).
        if (
            status == "completed"
            and getattr(self, "_staged_decisions", False)
            and self.run is not None
            and agent_id
            == {
                agent.package.role: agent.agent_id
                for agent in self.run.configuration.profile.agents
            }.get("coordinator", "coordinator")
        ):
            issue = staged_checklist_issue(self.run.root)
            if issue is not None:
                self._deliver_staged_gate_feedback(
                    issue.reason_code, issue.artifact or issue.detail
                )
                return True
        return False

    def _finalize_acceptance_if_ready(self) -> None:
        """Commit explicit Acceptance settlement before Coordinator may report terminal."""

        if not self._formal_coordination_enabled() or self.acceptance is None:
            return
        settlement_ready = getattr(self.acceptance, "settlement_ready", None)
        if not callable(settlement_ready):
            # Lightweight legacy test doubles and offline adapters may expose
            # only ``is_settled``. They cannot claim the settlement boundary, so
            # leave the terminal guard blocked without invoking a partial path.
            return
        with self._acceptance_settlement_lock:
            # Both checks intentionally happen after acquiring the shared lock.
            # A concurrent guard/drain pair must observe the settled carrier and
            # return without a second CAS, settlement artifact, or evidence row.
            if self.acceptance.is_settled or not settlement_ready():
                return
            try:
                receipt = self.acceptance.settle()
            except AcceptanceContractError:
                # A state reader may have observed drift. The carrier records the
                # invalidation and remains non-settled; Coordinator cannot pass its guard.
                return
            if not self._acceptance_settlement_evidence_recorded:
                self._append_evidence(
                    "acceptance-settlement",
                    {
                        "status": receipt.get("status"),
                        "settlement_cas": receipt.get("settlement_cas"),
                        "final_readback": receipt.get("final_readback"),
                    },
                )
                self._acceptance_settlement_evidence_recorded = True

    def _consume_runtime_failures(self) -> list[tuple[str, dict[str, Any]]]:
        """Read the adapter-owned typed failure queue with legacy fallback."""

        reader = getattr(self.adapter, "consume_runtime_failures", None)
        if callable(reader):
            failures = reader()
            return list(failures) if isinstance(failures, (list, tuple)) else []
        # Older deterministic adapters expose only the inactivity projection.
        legacy = getattr(self.adapter, "consume_inactivity_failures", None)
        if callable(legacy):
            failures = legacy()
            return list(failures) if isinstance(failures, (list, tuple)) else []
        return []

    def _coordinator_failure_deferrable(
        self, agent_id: str, detail: dict[str, Any]
    ) -> bool:
        """A fatally failed Coordinator defers run teardown while waits survive.

        Identity/protocol hard failures keep their latch on the Coordinator
        process itself; only the whole-run cleanup is deferred while at least
        one other role is parked in an externally recoverable provider wait.
        """

        if not self.run:
            return False
        try:
            agents = self.run.configuration.profile.agents
        except AttributeError:
            return False
        coordinator_ids = {
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        }
        if agent_id not in coordinator_ids and detail.get("role") != "coordinator":
            return False
        return any(
            wait_agent != agent_id for wait_agent in self._live_provider_wait_agents()
        )

    def _finalize_runtime_failure(
        self, failures: list[tuple[str, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Settle one typed runtime failure exactly once and stop the roster."""

        if self._runtime_failure_finalized or not failures:
            return []
        agent_id, detail = failures[0]
        safe_detail = dict(detail) if isinstance(detail, dict) else {}
        if self._coordinator_failure_deferrable(agent_id, safe_detail):
            # 2026-09-14 provider-recovery host takeover: a fatally latched
            # Coordinator must not erase surviving roles that are parked in
            # externally recoverable provider waits.  The Coordinator stays
            # dead (its latch is never cleared); the run stays observable so
            # the outer owner can recover the waiting roles, and the same
            # failure finalizes once the last wait is gone.
            self._deferred_runtime_failures = failures
            waits = self._live_provider_wait_agents()
            self._append_evidence(
                "runtime-failure",
                {
                    "event": "coordinator-takeover-deferred",
                    "agent_id": agent_id,
                    **safe_detail,
                    "provider_waits": waits,
                },
            )
            self._state("WAITING_OWNER", coordinator_failure_deferred=True)
            return [
                {
                    "type": "coordinator-unavailable",
                    "agent_id": agent_id,
                    "role": safe_detail.get("role") or "coordinator",
                    "reason": safe_detail.get("reason"),
                    "provider_waits": waits,
                    "host_action": "recover_provider",
                    "note": (
                        "Coordinator stays unavailable (no rebuild); the host "
                        "owns ongoing orchestration of surviving roles — this "
                        "is not a complete-team recovery. End the run with an "
                        "explicit stop."
                    ),
                }
            ]
        self._runtime_failure_finalized = True
        self._append_evidence(
            "runtime-failure",
            {"agent_id": agent_id, **safe_detail},
        )
        self.record_terminal_failure("runtime/infrastructure", False)
        cleanup = self.cleanup()
        self._state(
            "TERMINAL_REPORT_COMPLETE",
            runtime_failure=True,
            agent_id=agent_id,
            role=safe_detail.get("role"),
            reason=safe_detail.get("reason"),
        )
        return [
            {
                "type": "runtime-failure",
                "agent_id": agent_id,
                "role": safe_detail.get("role"),
                "reason": safe_detail.get("reason"),
                "cleanup": cleanup,
            }
        ]

    def start(self) -> None:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        self._state("STARTING")
        try:
            formal_coordination = self._formal_coordination_enabled()
            if self.scope_factory:
                self.scope = self.scope_factory(self.run)
                self.scope.retain_nonempty = self.run.configuration.task.retain_nonempty
                self.scope.prepare(self.run.scope)
                if formal_coordination and self.acceptance is not None:
                    # Bind formal Acceptance read keys only after PlatformScope has
                    # authenticated and prepared the owned Project/Ontology.  The
                    # carrier then replaces its explicit offline test double with
                    # the API-backed lifecycle and host MCP forwarder.
                    self.acceptance.bind_platform_scope(
                        self.scope,
                        repository_root=self.repository_root,
                    )
                self.run.protocol_key = self.scope.protocol_key
                if self.run.configuration.task.schema_version == 2:
                    self.run.protocol_context = self.scope.read_protocol_context()
                if self._is_r23003_modeling_run():
                    self._ensure_modeling_read_surface()
            role_agents = {
                agent.package.role: agent.agent_id for agent in self.run.configuration.profile.agents
            }
            transport_event_lock = threading.Lock()

            def transport_event_observer(event: dict[str, object]) -> None:
                with transport_event_lock:
                    self._append_team_transport_event(event)

            def issue_event_callback(event: dict[str, object]) -> None:
                if not isinstance(event, dict):
                    return
                with self._issue_event_lock:
                    self._issue_event_queue.append(deepcopy(event))

            # R3.0-006 M2: the dependency graph is derived from the Profile's
            # actual role set instead of a hard-coded four-role roster.  The
            # three message-routing core roles stay mandatory (fail-closed
            # typed error); extra roles (future dynamic Agents) carry no
            # terminal dependency.  For every historical roster that includes
            # Acceptance this graph is byte-identical to the previous one.
            missing_core_roles = RUNNER_CORE_ROLE_VALUES - set(role_agents)
            if missing_core_roles:
                raise TeamConfigurationError(
                    "Team Profile is missing the core roles: "
                    + ",".join(sorted(missing_core_roles))
                )
            coordinator_dependencies = {role_agents["modeling"], role_agents["protocol"]}
            if "acceptance" in role_agents:
                coordinator_dependencies.add(role_agents["acceptance"])
            terminal_dependencies = {
                role_agents["protocol"]: {role_agents["modeling"]},
                role_agents["coordinator"]: coordinator_dependencies,
            }
            if formal_coordination:
                # Formal Acceptance is the semantic gate for the Modeling
                # terminal. Keep the historical non-formal dependency graph
                # unchanged; only the formal four-role run serializes the
                # final path Acceptance -> Modeling -> Protocol -> Coordinator.
                terminal_dependencies[role_agents["modeling"]] = {
                    role_agents["acceptance"]
                }
            self.transport = TeamTransportBroker(
                self.run.root / "transport" / "broker",
                set(self.run.configuration.profile.communication),
                terminal_dependencies=terminal_dependencies,
                modeling_agent_id=role_agents["modeling"],
                coordinator_agent_id=role_agents["coordinator"],
                terminal_report_guard=self._terminal_report_guard,
                transport_event_observer=transport_event_observer,
                coordination_phase_callback=(
                    self._coordination_phase_callback if formal_coordination else None
                ),
                coordination_event_observer=(
                    self._coordination_transport_event_observer if formal_coordination else None
                ),
                # 2026-09-11 auth006-start8: staged v3 runs are non-formal but
                # long-lived; without the cooperative issue channel a temporary
                # transport addressing failure left Protocol no recoverable
                # exit except terminal `blocked`, which latched irreversibly
                # and bricked the run.  Enable the typed issue escalation for
                # staged runs too: the same Coordinator pause/resume flow
                # applies, and terminal reports stay reserved for real
                # unresolvable blockers.
                issue_escalation_enabled=(formal_coordination or self._staged_decisions),
                issue_event_callback=(
                    issue_event_callback
                    if (formal_coordination or self._staged_decisions)
                    else None
                ),
                pre_send_validator=(
                    self._validate_modeling_transport_send
                    if self._is_r23003_modeling_run()
                    else None
                ),
            )
            self.transport.start(
                [agent.agent_id for agent in self.run.configuration.profile.agents]
            )
            self.run.transport_root = self.transport.root
            (self.run.root / "transport-root").write_text(
                str(self.transport.root), encoding="utf-8"
            )
            if (
                self.acceptance is not None
                and formal_coordination
            ):
                # Runner-private capability endpoints are live before any
                # Coordinator/Acceptance process is launched.
                self.acceptance.start_capability_endpoints()
            if (
                self.acceptance is not None
                and not formal_coordination
                and self._staged_decisions
            ):
                # R3.0-008B staged runs are non-formal, so the formal branch
                # above never runs; the protocol role still declares the
                # staged run operations (batch submission and the #17 evidence
                # repost) in its private config, so exactly that endpoint must be
                # live before any roster process is launched.  Nothing else starts
                # here: a non-staged non-formal run keeps every endpoint stopped.
                self.acceptance.capability_endpoint("protocol").start()
                self._append_evidence(
                    "staged-decisions",
                    {
                        "event": "protocol-capability-endpoint-started",
                        "operations": list(STAGED_PROTOCOL_RUN_OPERATIONS),
                    },
                )
            if self._competency_questions and self.acceptance is not None:
                # R3.0-011: only the CQ endpoint is live in a (non-formal) CQ
                # run, and it is live before any roster process is launched.
                self.acceptance.start_cq_endpoint()
                self._append_evidence(
                    "competency-questions",
                    {
                        "event": "cq-capability-endpoint-started",
                        "operations": ["cq_publish_question_draft"],
                    },
                )
            if formal_coordination and self.coordinator_phase is not None:
                self.coordinator_phase.start()
                assignment = self.coordinator_phase.assign_slice(
                    sender_id=role_agents["coordinator"],
                    objective=self.run.configuration.task.objective,
                )
                self._append_evidence("coordination-phase", assignment)
            identities = self.adapter.start_roster(
                self.run, self.run.configuration.profile.agents
            )
            roster = [identity.agent_id for identity in identities]
            # R3.0-006 M1: the pre-delivery visibility probe and the
            # semantic-start evidence belong to every v2 run, with or without
            # a StartLedger (multi_slice_workflow runs carry no ledger).
            if self._ledger or self.run.configuration.task.schema_version == 2:
                self._probe_role_visibility()
                runtime_probe = self.adapter.probe_role_visibility(self.run)
                self._append_evidence("runtime-visibility-probe", {"passed": True, "roles": runtime_probe})
                if self.run.configuration.task.schema_version == 2 and self.run.gate_binding is not None:
                    self._preflight_proof_v2_gate()
                if self._ledger:
                    self._ledger.mark_semantic_start(
                        self.run.run_id,
                        gate_binding=self.run.gate_binding,
                    )
                self._append_evidence(
                    "semantic-start",
                    {
                        "baseline_hash": self.run.baseline_hash,
                        **self._formal_ledger_identity(),
                    },
                )
            for agent in self.run.configuration.profile.agents:
                try:
                    self.adapter.start_task(
                        agent.agent_id,
                        self._task_text(agent.package.role),
                        [str(path) for path in agent.package.required_skills],
                        roster,
                    )
                except Exception:
                    failures = self._consume_runtime_failures()
                    if failures:
                        self._state("FAILED")
                        self._finalize_runtime_failure(failures)
                        return
                    raise
                failures = self._consume_runtime_failures()
                if failures:
                    self._state("FAILED")
                    self._finalize_runtime_failure(failures)
                    return
            self._state("RUNNING", identities=[item.agent_id for item in identities])
            # R2.3-009 T3: the run-level fallback clock starts only after the
            # whole role Runtime came up, and excludes later issue-pending time.
            parameters = self.run.configuration.profile.parameters
            self._candidate_redrive_limit = int(parameters.get("candidate_redrive_limit", 3))
            self._feedback_escalation_repeat = int(
                parameters.get("feedback_escalation_repeat", 3)
            )
            self._run_fallback_timeout_seconds = float(
                parameters.get("run_fallback_timeout_seconds", 10800.0)
            )
            self._run_fallback_started = self.monotonic_clock()
            # R2.3-009 start10/12: the slice-assignment-to-first-candidate
            # window has no progress owner, so an idle Coordinator silently
            # burns the whole fallback window.  Cooperative inquiries close
            # that gap; see ``_check_cooperative_idle``.
            self._idle_inquiry_seconds = float(
                parameters.get("idle_inquiry_seconds", 300.0)
            )
            self._idle_inquiries_sent = 0
            self._idle_inquiry_baseline = self.monotonic_clock()
        except Exception:
            failures = self._consume_runtime_failures()
            if failures:
                self._state("FAILED")
                self._finalize_runtime_failure(failures)
                return
            self._state("FAILED")
            if self._ledger and (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                self.record_terminal_failure("runtime/infrastructure", False)
            if self._ledger and not (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                self._ledger.release_presemantic(
                    self.run.run_id, "startup-config: startup failure before business delivery"
                )
            self.cleanup()
            raise

    def _probe_role_visibility(self) -> None:
        """Deterministically prove staged role inputs before first business delivery."""
        assert self.run
        expected: dict[str, set[Path]] = {
            agent.package.role: set() for agent in self.run.configuration.profile.agents
        }
        for source in self.run.configuration.task.role_sources:
            for role in source.roles:
                expected[role].add(source.relative_path)
        result: dict[str, Any] = {}
        for role, paths in expected.items():
            root = self.run.root / "sources" / role
            observed = {
                item.relative_to(root)
                for item in root.rglob("*")
                if item.is_file()
            } if root.exists() else set()
            if observed != paths:
                raise TeamConfigurationError(f"role visibility probe failed for {role}")
            result[role] = {
                "paths": sorted(path.as_posix() for path in observed),
                "sha256": {path.as_posix(): digest_file(root / path) for path in sorted(observed)},
            }
        self._append_evidence("role-visibility-probe", {"passed": True, "roles": result})

    def _resolve_expected_matrix_binding(self, expected: dict[str, str]) -> dict[str, str]:
        """Resolve the tester-owned P2a digest at reservation time.

        Task/Profile files freeze only immutable matrix identity and the P2a path.  The
        tester writes the P2a envelope later, so Delivery derives its canonical digest
        immediately before the reservation and passes the resulting five-field binding
        to the existing StartLedger contract.  A legacy full binding remains accepted
        for retained fixtures, but is still re-read by the pre-start gate.
        """
        if "p2a_pass_digest" in expected:
            return dict(expected)
        required = {"proof_matrix_path", "proof_matrix_digest", "p2a_pass_path", "source_run_id"}
        if not required.issubset(expected):
            raise TeamConfigurationError("expected matrix binding is incomplete")
        if expected["proof_matrix_path"] != _PROOF_MATRIX_RELATIVE or expected["p2a_pass_path"] != _P2A_PASS_RELATIVE:
            raise TeamConfigurationError("proof v2 gate path is not canonical")
        matrix_path = self._safe_gate_path(expected["proof_matrix_path"])
        p2a_path = self._safe_gate_path(expected["p2a_pass_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        try:
            verify_proof_matrix(matrix, source_run_id=expected["source_run_id"])
        except MatrixArtifactError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if expected["proof_matrix_digest"] != matrix.get("matrix_digest"):
            raise TeamConfigurationError("proof matrix gate digest drifts")
        if "source_candidate_digest" in expected and expected["source_candidate_digest"] != matrix.get("source_candidate_digest"):
            raise TeamConfigurationError("proof matrix source candidate digest drifts")
        p2a = self._read_gate_json(p2a_path, "P2a pass")
        if set(p2a) != {
            "schema_version",
            "matrix_path",
            "matrix_digest",
            "source_run_id",
            "p2a_run_id",
            "verifier_complete",
            "evidence_hashes",
            "tested_at",
        }:
            raise TeamConfigurationError("P2a pass fields drift")
        if (
            p2a.get("schema_version") != _P2A_SCHEMA
            or p2a.get("matrix_path") != _PROOF_MATRIX_RELATIVE
            or p2a.get("matrix_digest") != matrix.get("matrix_digest")
            or p2a.get("source_run_id") != expected["source_run_id"]
            or p2a.get("verifier_complete") is not True
            or not isinstance(p2a.get("p2a_run_id"), str)
            or not p2a["p2a_run_id"]
            or not isinstance(p2a.get("tested_at"), str)
            or not p2a["tested_at"]
        ):
            raise TeamConfigurationError("P2a pass binding is invalid")
        evidence_hashes = p2a.get("evidence_hashes")
        if not isinstance(evidence_hashes, list) or evidence_hashes != sorted(evidence_hashes) or len(set(evidence_hashes)) != len(evidence_hashes):
            raise TeamConfigurationError("P2a evidence hashes are not sorted and unique")
        for value in evidence_hashes:
            if not isinstance(value, str) or len(value) != 64:
                raise TeamConfigurationError("P2a evidence hash is invalid")
            try:
                int(value, 16)
            except ValueError as exc:
                raise TeamConfigurationError("P2a evidence hash is invalid") from exc
        return {
            "proof_matrix_path": expected["proof_matrix_path"],
            "proof_matrix_digest": expected["proof_matrix_digest"],
            "p2a_pass_path": expected["p2a_pass_path"],
            "p2a_pass_digest": self._canonical_digest(p2a),
            "source_run_id": expected["source_run_id"],
        }

    def _preflight_proof_v2_gate(self) -> None:
        """Validate tester-owned matrix/P2a artifacts before semantic_start.

        This is intentionally a local read-only gate.  It does not inspect a
        live candidate or candidate-local map; those belong to the post-start
        Protocol gate and are not prerequisites for consuming the ledger
        reservation.
        """
        assert self.run
        expected = self.run.gate_binding
        if expected is None:
            return
        if expected.get("proof_matrix_path") != _PROOF_MATRIX_RELATIVE or expected.get("p2a_pass_path") != _P2A_PASS_RELATIVE:
            raise TeamConfigurationError("proof v2 gate path is not canonical")
        matrix_path = self._safe_gate_path(expected["proof_matrix_path"])
        p2a_path = self._safe_gate_path(expected["p2a_pass_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        try:
            verify_proof_matrix(matrix, source_run_id=expected["source_run_id"])
        except MatrixArtifactError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if matrix.get("source_run_id") != expected["source_run_id"]:
            raise TeamConfigurationError("proof matrix schema/source drifts")
        if expected.get("proof_matrix_digest") != matrix.get("matrix_digest"):
            raise TeamConfigurationError("proof matrix gate digest drifts")

        p2a = self._read_gate_json(p2a_path, "P2a pass")
        if set(p2a) != {
            "schema_version",
            "matrix_path",
            "matrix_digest",
            "source_run_id",
            "p2a_run_id",
            "verifier_complete",
            "evidence_hashes",
            "tested_at",
        }:
            raise TeamConfigurationError("P2a pass fields drift")
        if (
            p2a.get("schema_version") != _P2A_SCHEMA
            or p2a.get("matrix_path") != _PROOF_MATRIX_RELATIVE
            or p2a.get("matrix_digest") != matrix.get("matrix_digest")
            or p2a.get("source_run_id") != expected["source_run_id"]
            or p2a.get("verifier_complete") is not True
            or not isinstance(p2a.get("p2a_run_id"), str)
            or not p2a["p2a_run_id"]
            or not isinstance(p2a.get("tested_at"), str)
            or not p2a["tested_at"]
        ):
            raise TeamConfigurationError("P2a pass binding is invalid")
        evidence_hashes = p2a.get("evidence_hashes")
        if not isinstance(evidence_hashes, list) or evidence_hashes != sorted(evidence_hashes) or len(set(evidence_hashes)) != len(evidence_hashes):
            raise TeamConfigurationError("P2a evidence hashes are not sorted and unique")
        for value in evidence_hashes:
            if not isinstance(value, str) or len(value) != 64:
                raise TeamConfigurationError("P2a evidence hash is invalid")
            try:
                int(value, 16)
            except ValueError as exc:
                raise TeamConfigurationError("P2a evidence hash is invalid") from exc
        p2a_digest = self._canonical_digest(p2a)
        if expected.get("p2a_pass_digest") != p2a_digest:
            raise TeamConfigurationError("P2a pass digest drifts")
        self._append_evidence(
            "proof-v2-preflight",
            {
                "matrix_path": _PROOF_MATRIX_RELATIVE,
                "matrix_digest": matrix["matrix_digest"],
                "p2a_pass_path": _P2A_PASS_RELATIVE,
                "p2a_pass_digest": p2a_digest,
                "source_run_id": expected["source_run_id"],
                "verifier_complete": True,
            },
        )

    def _safe_gate_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise TeamConfigurationError("proof v2 gate path escapes repository")
        path = self.repository_root / relative
        current = self.repository_root
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise TeamConfigurationError("proof v2 gate path cannot be a symlink")
        resolved = path.resolve()
        if resolved != self.repository_root and self.repository_root not in resolved.parents:
            raise TeamConfigurationError("proof v2 gate path escapes repository")
        if not path.is_file():
            raise TeamConfigurationError("proof v2 gate artifact is unavailable")
        return path

    @staticmethod
    def _read_gate_json(path: Path, name: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TeamConfigurationError(f"{name} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise TeamConfigurationError(f"{name} must contain an object")
        return value

    @staticmethod
    def _canonical_digest(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def validate_candidate_before_submit(
        self,
        candidate: dict[str, Any],
        client_item_ids: dict[str, str] | list[dict[str, str]],
        *,
        matrix_binding: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate the frozen candidate and persist its map before submit/dry-run."""
        if not self.run or self.run.configuration.task.schema_version != 2:
            raise TeamConfigurationError("candidate-before-submit gate requires a v2 run")
        expected_gate = self.run.gate_binding
        if expected_gate is None:
            raise TeamConfigurationError(
                "candidate evidence-map gate is disabled without expected_matrix_binding"
            )
        if not isinstance(matrix_binding, dict) or set(matrix_binding) != {"proof_matrix_path", "proof_matrix_digest"}:
            raise TeamConfigurationError("candidate matrix_binding is missing or invalid")
        if (
            matrix_binding.get("proof_matrix_path") != expected_gate["proof_matrix_path"]
            or matrix_binding.get("proof_matrix_digest") != expected_gate["proof_matrix_digest"]
        ):
            raise TeamConfigurationError("candidate matrix_binding drifts from frozen gate")
        self._validate_candidate_matrix(candidate, expected_gate)
        candidate_value = dict(candidate)
        if "matrix_binding" in candidate_value:
            # matrix_binding is proof metadata, not a candidate envelope field.
            candidate_value.pop("matrix_binding")
        try:
            evidence_map = build_candidate_item_evidence_map(
                candidate_value,
                client_item_ids,
                run_id=self.run.run_id,
            )
        except Exception as exc:
            if isinstance(exc, TeamConfigurationError):
                raise
            raise TeamConfigurationError(str(exc)) from exc
        path = self.run.root / "evidence" / "candidate-item-evidence-map.json"
        if path.exists() or path.is_symlink():
            raise TeamConfigurationError("candidate evidence map already exists and is immutable")
        self._write_immutable_json(path, evidence_map)
        self._append_evidence(
            "candidate-item-evidence-map",
            {
                "path": "evidence/candidate-item-evidence-map.json",
                "candidate_digest": evidence_map["candidate_digest"],
                "map_digest": evidence_map["map_digest"],
                "row_count": len(evidence_map["rows"]),
            },
        )
        return evidence_map

    def _validate_candidate_matrix(
        self, candidate: dict[str, Any], expected_gate: dict[str, str]
    ) -> None:
        matrix_path = self._safe_gate_path(expected_gate["proof_matrix_path"])
        matrix = self._read_gate_json(matrix_path, "proof matrix")
        rows = matrix.get("rows")
        if not isinstance(rows, list):
            raise TeamConfigurationError("proof matrix rows are invalid")
        row_by_id = {row.get("assertion_id"): row for row in rows if isinstance(row, dict)}
        items = candidate.get("items") if isinstance(candidate, dict) else None
        if not isinstance(items, list) or {item.get("assertion_id") for item in items if isinstance(item, dict)} != set(row_by_id):
            raise TeamConfigurationError("candidate assertion IDs do not match frozen matrix")
        for item in items:
            if not isinstance(item, dict):
                raise TeamConfigurationError("candidate assertion item is invalid")
            assertion_id = item.get("assertion_id")
            row = row_by_id.get(assertion_id)
            if row is None or item.get("graph_role") != "asserted_data":
                raise TeamConfigurationError("candidate assertion scope drifts from matrix")
            for field in ("subject", "predicate", "object", "object_kind", "object_datatype", "object_language"):
                if item.get(field) != row.get(field):
                    raise TeamConfigurationError("candidate assertion drifts from frozen matrix")
            candidate_citations = item.get("evidence_citations")
            matrix_citations = row.get("approved_citations")
            if not isinstance(candidate_citations, list) or not isinstance(matrix_citations, list):
                raise TeamConfigurationError("candidate citation set is invalid")
            if sorted(candidate_citations, key=self._canonical_bytes) != sorted(matrix_citations, key=self._canonical_bytes):
                raise TeamConfigurationError("candidate citations drift from frozen matrix")

    @staticmethod
    def _canonical_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, 0o444)

    def record_terminal_failure(
        self,
        classification: str,
        complete_modeling_quality_result: bool,
        repair_baseline_hash: str | None = None,
        terminal_evidence: dict[str, Any] | None = None,
    ) -> None:
        if not self.run or not self._ledger:
            return
        self._ledger.terminal_failure(
            self.run.run_id,
            classification,
            complete_modeling_quality_result,
            repair_baseline_hash,
            terminal_evidence,
        )
        self._append_evidence(
            "terminal-classification",
            {
                "classification": classification,
                "complete_modeling_quality_result": complete_modeling_quality_result,
                "repair_baseline_hash": repair_baseline_hash,
                **({"terminal_evidence": terminal_evidence} if terminal_evidence is not None else {}),
            },
        )

    def _record_issue_abort_terminal_failure(
        self,
        issue: Any,
        cleanup: dict[str, Any],
    ) -> None:
        """Reconcile a zero-mutation 003 issue abort into the append-only ledger."""

        if self._issue_abort_terminal_failure_recorded:
            return
        if not self.run or not self._ledger:
            return
        contract = formal_run_contract_for(self.run.configuration)
        if contract is None or contract.requirement_id != "R2.3-003":
            # R2.3-005 retains its existing issue/cleanup path; this narrow
            # reconciliation is only needed for the existing-scope ledger.
            return
        if issue is None or getattr(issue, "run_id", None) != self.run.run_id:
            raise TeamConfigurationError("issue abort run binding is invalid")
        raw_mutation_state = getattr(issue, "mutation_state", None)
        if not (
            isinstance(raw_mutation_state, str)
            and (
                raw_mutation_state == "zero-mutation"
                or raw_mutation_state.startswith("zero-mutation;")
            )
        ):
            raise TeamConfigurationError("issue abort lacks zero-mutation evidence")
        # Keep explanatory issue prose outside the strict ledger field.
        mutation_state = "zero-mutation"
        if not isinstance(cleanup, dict):
            raise TeamConfigurationError("issue abort cleanup evidence is invalid")
        acceptance = cleanup.get("acceptance")
        scope = cleanup.get("scope")
        if (
            not isinstance(acceptance, dict)
            or acceptance.get("status") != "aborted"
            or acceptance.get("zero_child_residue") is not True
            or not isinstance(scope, dict)
            or scope.get("cleanup_blocker")
            or scope.get("no_in_flight_attempts") is not True
        ):
            raise TeamConfigurationError("issue abort cleanup is not zero-mutation clean")
        before = scope.get("existing_context_before")
        after = scope.get("existing_context_after")
        if isinstance(before, dict) and isinstance(after, dict) and before != after:
            raise TeamConfigurationError("issue abort existing scope changed during cleanup")
        baseline_hash = self.run.baseline_hash
        if not isinstance(baseline_hash, str) or not baseline_hash:
            raise TeamConfigurationError("issue abort baseline binding is unavailable")
        issue_payload = {
            "run_id": self.run.run_id,
            "issue_id": issue.issue_id,
            "mutation_state": mutation_state,
            "failing_operation": issue.failing_operation,
            "error": issue.error,
        }
        evidence_payload = {
            "run_id": self.run.run_id,
            "baseline_hash": baseline_hash,
            "classification": "platform-contract",
            "mutation_state": "zero-mutation",
            "issue_id": issue.issue_id,
            "issue_digest": canonical_digest(issue_payload),
            "cleanup_digest": canonical_digest(cleanup),
            "evidence_path": "evidence/terminal-reconciliation.jsonl",
        }
        evidence_digest = canonical_digest(evidence_payload)
        terminal_evidence = {
            "run_id": self.run.run_id,
            "baseline_hash": baseline_hash,
            "classification": "platform-contract",
            "mutation_state": "zero-mutation",
            "issue_id": issue.issue_id,
            "evidence_path": evidence_payload["evidence_path"],
            "evidence_digest": evidence_digest,
        }
        self._append_evidence(
            "terminal-reconciliation",
            {**evidence_payload, "evidence_digest": evidence_digest},
        )
        try:
            self.record_terminal_failure(
                "platform-contract",
                False,
                terminal_evidence=terminal_evidence,
            )
        except Exception as exc:
            raise TeamConfigurationError(
                "issue-abort terminal reconciliation failed after cleanup evidence was persisted"
            ) from exc
        self._issue_abort_terminal_failure_recorded = True

    def _publish_staged_candidate(self, modeling_id: str) -> dict[str, Any]:
        """Publish one prevalidated candidate through ordinary Team Transport."""

        if self._candidate_publication is None or self.transport is None:
            raise CandidatePublicationError("staged candidate publication is unavailable")
        if self._modeling_context_gate is not None:
            self._modeling_context_gate.assert_open()
        role_ids = self._formal_coordination_role_ids()
        receipt = self._candidate_publication.publish(
            actor_id=modeling_id,
            modeling_id=role_ids["modeling"],
            protocol_id=role_ids["protocol"],
            send=self.transport.send,
        )
        identity = modeling_candidate_value(self._candidate_publication.candidate_text)
        if identity is not None and self._modeling_context_gate is not None:
            self._modeling_context_gate.bind_candidate(
                str(receipt.get("delivery_id")), modeling_canonical_digest(identity)
            )
        return receipt

    def _validate_modeling_transport_send(
        self,
        sender_id: str,
        recipient_id: str,
        text: str,
        expects_reply: bool,
        reply_to_delivery_id: str | None,
    ) -> None:
        """Keep an R2.3-003 candidate behind the immutable context receipt gate."""

        if not self._is_r23003_modeling_run() or self.run is None:
            return
        role_ids = self._formal_coordination_role_ids()
        if sender_id != role_ids.get("modeling") or recipient_id != role_ids.get("protocol"):
            return
        if self._modeling_context_gate is None:
            raise RoutingError("R2.3-003 Modeling context gate is unavailable")
        try:
            self._modeling_context_gate.assert_open()
        except ModelingReadError as exc:
            raise RoutingError("candidate publication requires an accepted Modeling context receipt") from exc

        # Modeling may open the first candidate request with a fresh reply slot,
        # or replace an accepted receipt only by replying to the currently
        # validated standalone Protocol conflict.  A receipt/conflict payload,
        # foreign reply anchor, stale conflict anchor, and partial revision are
        # all rejected before Team Transport can mutate its reply table.
        candidate: Mapping[str, Any] | None = None
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, Mapping):
                candidate = decoded if modeling_candidate_value(text) is not None else None

        if not expects_reply:
            if candidate is not None:
                raise RoutingError("R2.3-003 candidate publication must open a fresh reply slot")
            return
        if candidate is None:
            raise RoutingError("R2.3-003 Modeling reply must be a complete candidate")

        progress = self._candidate_progress
        pending = progress.pending if progress is not None else None
        if reply_to_delivery_id is None:
            # The initial candidate is the only fresh Modeling->Protocol
            # candidate request.  Once FormalCandidateProgress has an identity,
            # a second fresh request is stale rather than a new slot.
            if pending is not None:
                raise RoutingError("R2.3-003 fresh candidate slot is already occupied")
            try:
                formal_candidate_digests(candidate)
            except FormalCandidateError as exc:
                raise RoutingError("R2.3-003 candidate is not a complete formal candidate") from exc
            return

        if (
            pending is None
            or progress is None
            or progress.state != "awaiting_revision"
            or pending.conflict_delivery_id != reply_to_delivery_id
        ):
            raise RoutingError(
                "R2.3-003 revision must reply to the current standalone Protocol conflict"
            )
        try:
            formal_candidate_digests(candidate)
        except FormalCandidateError as exc:
            raise RoutingError("R2.3-003 revision is not a complete formal candidate") from exc

    def _is_r23003_modeling_run(self) -> bool:
        if self.run is None:
            return False
        contract = formal_run_contract_for(self.run.configuration)
        return contract is not None and contract.requirement_id == "R2.3-003"

    def _observe_modeling_context(
        self, response: Mapping[str, Any], call_receipt: Any
    ) -> None:
        gate = self._modeling_context_gate
        if gate is None:
            raise ModelingReadError("R2.3-003 Modeling context gate is unavailable")
        if gate.receipt is None or gate.state == "closed":
            gate.observe(response, call_receipt=call_receipt)
        else:
            gate.revalidate(response, call_receipt=call_receipt)
        self._append_evidence(
            "modeling-context-receipt",
            {
                "receipt_digest": gate.receipt.receipt_digest if gate.receipt else None,
                "workspace_version": gate.receipt.workspace_version if gate.receipt else None,
                "revalidation_receipt_digest": (
                    gate.revalidation_receipt.get("revalidation_receipt_digest")
                    if gate.revalidation_receipt
                    else None
                ),
                "project_id": gate.project_id,
                "ontology_id": gate.ontology_id,
            },
        )

    def _ensure_modeling_read_surface(self) -> None:
        """Create the short-lived Modeling read key and local policy proxy."""

        if not self._is_r23003_modeling_run() or self.run is None:
            return
        if self.scope is None:
            raise ModelingReadError("Modeling read surface requires a prepared PlatformScope")
        if self._modeling_read_lifecycle is not None:
            return
        lifecycle = ModelingReadKeyLifecycle(self.scope, repository_root=self.repository_root)
        self._modeling_read_lifecycle = lifecycle
        record = None
        proxy = None
        try:
            record = lifecycle.create(
                project_id=self.run.scope["project_id"],
                ontology_id=self.run.scope["ontology_id"],
                run_id=self.run.run_id,
            )
            socket_path = self.run.root / "modeling-read-proxy.sock"
            if len(str(socket_path)) >= 100:
                import hashlib as _hashlib

                socket_path = Path("/tmp") / (
                    "mt-mr-" + _hashlib.sha256(str(socket_path).encode()).hexdigest()[:24] + ".sock"
                )
            proxy = ModelingReadProxy(
                socket_path=socket_path,
                token=secrets.token_urlsafe(24),
                read_key=lifecycle.plaintext_for(record.key_id),
                project_id=record.project_id,
                ontology_id=record.ontology_id,
                forward=lifecycle.forwarder_for(record.key_id),
                on_context=self._observe_modeling_context,
            )
            proxy.start()
        except Exception:
            if proxy is not None:
                proxy.destroy()
            if record is not None:
                try:
                    lifecycle.revoke(record.key_id)
                except Exception:
                    pass
            self._modeling_read_lifecycle = None
            raise
        assert record is not None and proxy is not None
        self._modeling_read_proxy = proxy
        self.run.modeling_read_key_id = record.key_id
        self.run.modeling_read_proxy = proxy
        self._append_evidence(
            "modeling-read-key",
            {
                "key_id": record.key_id,
                "key_digest": record.key_digest,
                "project_id": record.project_id,
                "ontology_id": record.ontology_id,
                "allowed_tools": list(MODELING_READ_TOOLS),
                "proxy": proxy.receipt.__dict__,
            },
        )

    def _active_protocol_candidate(
        self,
        protocol_id: str,
        delivery_id: str,
        *,
        response_kind: str,
        idempotent_receipt: bool = False,
    ) -> tuple[dict[str, Any], Any]:
        """Resolve one live formal candidate without accepting model-supplied bytes."""

        if not self._formal_coordination_enabled() or self.run is None:
            raise TeamConfigurationError("typed candidate binding is unavailable")
        if self.transport is None or self.acceptance is None or not self.acceptance.is_live:
            raise TeamConfigurationError("typed candidate binding is not active")
        role_ids = self._formal_coordination_role_ids()
        if protocol_id != role_ids["protocol"]:
            raise TeamConfigurationError("typed candidate protocol identity is not bound")
        if not isinstance(delivery_id, str) or not delivery_id:
            raise TeamConfigurationError("typed candidate delivery_id is invalid")
        progress = self._candidate_progress
        identity = progress.identity if progress is not None else None
        candidate = progress.candidate if progress is not None else None
        if identity is None or candidate is None:
            raise TeamConfigurationError("typed candidate has no active FormalCandidateProgress")
        if identity.run_id != self.run.run_id:
            raise TeamConfigurationError("typed candidate run identity is stale")
        if identity.protocol_agent_id != protocol_id:
            raise TeamConfigurationError("typed candidate protocol identity drifts from progress")
        if identity.original_delivery_id != delivery_id:
            raise TeamConfigurationError("typed candidate delivery_id is foreign or stale")
        formal_contract = formal_run_contract_for(self.run.configuration)
        post_receipt_conflict = (
            response_kind == "conflict"
            and formal_contract is not None
            and progress.state == "complete"
            and self._protocol_candidate_responses.get(delivery_id) == "receipt"
            and progress.post_receipt_revision_enabled
        )
        # R2.3-009 start1: after the receipt is registered the Protocol Agent
        # still needs the retained candidate for the platform translation
        # stage, and a pause/resume can leave the transcript copy unusable as
        # an exact tool argument.  A read-only replay of the same receipt is a
        # deterministic function of Runner-retained state (byte-verified against
        # the registered digest below), so it is the authorized re-fetch path.
        post_registration_replay = (
            response_kind == "receipt"
            and formal_contract is not None
            and progress.state == "complete"
            and self._protocol_candidate_responses.get(delivery_id) == "receipt"
        )
        if (
            progress.state not in {"awaiting_receipt", "redrive_sent"}
            and not post_receipt_conflict
            and not post_registration_replay
        ) or progress.paused:
            raise TeamConfigurationError("typed candidate is not awaiting a Protocol response")
        if progress.terminal_failure_latched:
            raise TeamConfigurationError("typed candidate progress is terminal")
        try:
            candidate_digest, semantic_digest = formal_candidate_digests(candidate)
        except FormalCandidateError as exc:
            raise TeamConfigurationError("retained formal candidate is invalid") from exc
        if (
            candidate_digest != identity.candidate_digest
            or semantic_digest != identity.semantic_digest
        ):
            raise TeamConfigurationError("retained formal candidate identity drifted")
        previous_response = self._protocol_candidate_responses.get(delivery_id)
        if previous_response == "conflict":
            raise TeamConfigurationError("typed candidate response was already built")
        if response_kind == "conflict" and previous_response not in {
            "receipt",
            # R2.3-008 start10: a plan-rejected receipt attempt completed the
            # same Runner-owned mechanical binding step, so the typed conflict
            # path stays open for exactly that revision loop.
            "receipt_rejected",
        }:
            raise TeamConfigurationError(
                "typed candidate conflict requires the canonical receipt first"
            )
        # R2.3-008 start9: a repeat receipt request for the same still-answerable
        # candidate is an idempotent replay, not a rejection.  The receipt is a
        # deterministic function of Runner-retained state, so the replay returns
        # the identical canonical bytes and the Agent can deliver them as the
        # formal reply instead of escalating an opaque -32001.
        if (
            previous_response == "receipt"
            and response_kind == "receipt"
            and not idempotent_receipt
        ):
            raise TeamConfigurationError("typed candidate response was already built")
        return deepcopy(candidate), identity

    def _build_protocol_candidate_receipt(
        self,
        protocol_id: str,
        delivery_id: str,
    ) -> dict[str, Any]:
        """Build an exact formal receipt from Runner-retained candidate state.

        A repeat request for the same delivery_id while the candidate is still
        awaiting or redriving replays the identical canonical receipt.  After
        the receipt has been registered (progress complete, prior response
        receipt) the same replay remains available read-only: it re-exposes the
        retained candidate and byte-identical receipt for the Protocol Agent's
        platform translation stage without reopening any Team Transport reply
        slot.  The transport-side single-acceptance semantics are unchanged:
        the replay is byte-stable (verified against the registered digest) and
        the Runner still rejects requests after a conflict, terminal progress,
        or foreign delivery IDs.
        """

        replay = self._protocol_candidate_responses.get(delivery_id) == "receipt"
        candidate, identity = self._active_protocol_candidate(
            protocol_id,
            delivery_id,
            response_kind="receipt",
            idempotent_receipt=True,
        )
        formal_contract = formal_run_contract_for(self.run.configuration)
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            try:
                validate_r23003_candidate_declarations(candidate)
            except ValueError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        # R2.3-008 start10: run the exact registration-time retrieval-plan
        # validation before any receipt is issued.  An illegal consumer_query
        # plan previously surfaced only inside accepted-candidate registration,
        # after Protocol had already delivered a receipt, as an untyped
        # exception that burned the whole run.  Here the same rejection is a
        # structured success-path diagnostic the Protocol Agent can act on by
        # building a typed conflict, so Modeling receives one revisable
        # complete-revision request instead of a dead run.
        try:
            gate = ProtocolRetrievalGate(
                candidate,
                candidate_revision=identity.candidate_revision,
                candidate_digest=identity.candidate_digest,
            )
            # R2.3-009 start6: an accepted candidate with zero consumer_query
            # items leaves the gate disabled, so the receipt used to succeed
            # and the defect surfaced only at governed retrieval time -- after
            # the revision-1 application, where no formal revision channel
            # exists for this requirement.  Reject the empty plan at the same
            # pre-receipt boundary so the proven conflict/revision loop runs
            # before any platform mutation.  R2.3-005 keeps its accepted
            # planless-candidate contract: governed retrieval became a
            # mandatory stage only in R2.3-008.
            if formal_contract is not None and formal_contract.requirement_id in {
                "R2.3-008",
                "R2.3-009",
            } and not gate.enabled:
                raise ProtocolRetrievalGateError(
                    "accepted candidate carries no consumer_query item; "
                    "governed retrieval would have no retrieval plan to execute"
                )
        except ProtocolRetrievalGateError as exc:
            # Mark the delivery as a completed-but-rejected binding attempt so
            # the typed conflict builder (which requires a prior receipt
            # attempt) stays available for the revision loop.
            self._protocol_candidate_responses[delivery_id] = "receipt_rejected"
            raise AcceptanceContractError(
                "typed candidate receipt gate rejected the consumer_query retrieval plan",
                data={
                    "reason": "consumer_query_plan_invalid",
                    "detail": str(exc),
                    "action": (
                        "do not retry this call and do not send any accepted "
                        "receipt; build a typed candidate conflict with a "
                        "stable conflict_code and this detail, then send only "
                        "its conflict_json"
                    ),
                },
            ) from exc
        try:
            receipt = build_candidate_receipt(candidate)
        except ProtocolRetrievalFallbackError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        try:
            normalized = validate_formal_receipt(
                receipt,
                candidate_revision=identity.candidate_revision,
                semantic_digest=identity.semantic_digest,
                candidate_digest=identity.candidate_digest,
            )
        except FormalCandidateError as exc:
            raise TeamConfigurationError("canonical candidate receipt does not match active identity") from exc
        replay_digest = canonical_digest(normalized)
        if replay:
            registered_digest = self._protocol_candidate_receipt_digests.get(delivery_id)
            if registered_digest != replay_digest:
                raise TeamConfigurationError("typed candidate receipt replay is not byte-stable")
        self._protocol_candidate_responses[delivery_id] = "receipt"
        self._protocol_candidate_receipt_digests[delivery_id] = replay_digest
        result = {
            "delivery_id": delivery_id,
            "candidate": candidate,
            "receipt": deepcopy(normalized),
            "receipt_json": self._canonical_bytes(normalized).decode("utf-8"),
        }
        if replay:
            result["idempotent_replay"] = True
        return result

    def _build_protocol_candidate_conflict(
        self,
        protocol_id: str,
        delivery_id: str,
        conflict_code: str,
        conflict_detail: str,
    ) -> dict[str, Any]:
        """Build an exact formal conflict from Runner-retained candidate state."""

        candidate, identity = self._active_protocol_candidate(
            protocol_id,
            delivery_id,
            response_kind="conflict",
        )
        formal_contract = formal_run_contract_for(self.run.configuration)
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            receipt_digest = self._protocol_candidate_receipt_digests.get(delivery_id)
            workspace_version = self._formal_workspace_version or self.run.scope.get(
                "workspace_version"
            )
            if not isinstance(receipt_digest, str) or not receipt_digest:
                raise TeamConfigurationError("typed candidate conflict has no accepted receipt digest")
            if not isinstance(workspace_version, str) or not workspace_version:
                raise TeamConfigurationError("typed candidate conflict has no workspace version")
            try:
                conflict = build_existing_scope_candidate_conflict(
                    candidate,
                    conflict_code,
                    conflict_detail,
                    original_delivery_id=identity.original_delivery_id,
                    receipt_digest=receipt_digest,
                    workspace_version=workspace_version,
                )
            except ProtocolRetrievalFallbackError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        else:
            try:
                conflict = build_candidate_conflict(candidate, conflict_code, conflict_detail)
            except ProtocolRetrievalFallbackError as exc:
                raise TeamConfigurationError(str(exc)) from exc
        try:
            normalized = validate_formal_conflict(
                conflict,
                candidate_revision=identity.candidate_revision,
                semantic_digest=identity.semantic_digest,
                candidate_digest=identity.candidate_digest,
            )
        except FormalCandidateError as exc:
            raise TeamConfigurationError("canonical candidate conflict does not match active identity") from exc
        prior_response = self._protocol_candidate_responses.get(delivery_id)
        self._protocol_candidate_responses[delivery_id] = "conflict"
        if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
            if prior_response == "receipt" and self._modeling_context_gate is not None:
                self._modeling_context_gate.invalidate("post_receipt_context_drift")
            if self._candidate_platform_gate is not None:
                self._candidate_platform_gate.close("pre_mutation_binding_conflict")
        return {
            "delivery_id": delivery_id,
            "candidate": candidate,
            "conflict": deepcopy(normalized),
            "conflict_json": self._canonical_bytes(normalized).decode("utf-8"),
        }

    def _frozen_acceptance_question_ids(self) -> tuple[str, ...]:
        """Resolve the ordered standard-owned CQ IDs for Coordinator text."""

        if not self._formal_coordination_enabled() or self.run is None:
            return ()
        if self.acceptance is not None:
            ids = self.acceptance.frozen_question_ids()
        else:
            policy = self._acceptance_ticket_policy(self.run.configuration)
            ids = tuple(item["id"] for item in policy["competency_questions"])
        if not ids or len(set(ids)) != len(ids):
            raise TeamConfigurationError("formal acceptance must expose unique ordered question IDs")
        return ids

    def _task_text(self, role: str | None = None) -> str:
        assert self.run
        task = self.run.configuration.task
        if task.schema_version == 2:
            proof_gate = (
                getattr(self.run, "gate_binding", None) is not None
                or self._expected_matrix_binding(self.run.configuration) is not None
            )
            generation = (
                self.coordinator_phase.generation
                if self._formal_coordination_enabled() and self.coordinator_phase
                else None
            )
            formal_contract = formal_run_contract_for(self.run.configuration)
            is_r23003 = formal_contract is not None and formal_contract.requirement_id == "R2.3-003"
            formal_requirement_label = "R2.3-003" if is_r23003 else "R2.3-005"
            standard_policy = (
                self._acceptance_ticket_policy(self.run.configuration)
                if self._formal_coordination_enabled()
                else {}
            )
            question_count = int(standard_policy.get("question_count", 0) or 0)
            staged_sources = sorted(
                f"/agent/home/sources/{source.relative_path.as_posix()}"
                for source in task.role_sources
                if role in source.roles
            )
            # Prompt-cache contract (R3.0-002/006): the varying objective is one
            # trailing section, so the static role/instruction prefix stays
            # byte-identical whenever only the objective changes.  The reuse
            # guidance below is guidance for the same thread; it never relaxes
            # the mandatory initial complete read, live refreshes, or evidence
            # obligations, and never widens a role's authorized sources.
            objective_suffix = "\n\nTask objective:\n" + task.objective
            if self._resume_plan is not None and role in self._resume_plan.role_packets:
                objective_suffix += (
                    "\n\nCheckpoint continuation for this role (Runner-verified):\n"
                    + json.dumps(
                        self._resume_plan.role_packets[role],
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\nUse only artifacts mounted for your role. If a referenced public "
                    "artifact is not mounted, request its approved facts from the owning "
                    "role through Team Transport; do not infer it is missing from the run."
                )
            text = (
                "Before requesting any teammate work or reporting a terminal result, read every staged "
                + "role-private source in this canonical list:\n"
                + "\n".join(f"- {path}" for path in staged_sources)
                + "\nRead only these role-private sources. Complete that initial read of every staged source "
                + "in full. In this same thread, reuse the already-read "
                + "unchanged material and its exact locators instead of printing or re-reading a full file "
                + "again on every teammate turn. Reuse only this role's authorized sources and authorized "
                + "teammate handoffs; never access another role's private sources, inherit another run's "
                + "conversation, or use hidden material. Reread the necessary source "
                + "sections before relying on them whenever compaction lost them or the relevant content is "
                + "missing, stale, changed, or truncated. This reuse never skips a task-required live "
                + "workspace read, a refresh, a validation, or a full evidence obligation. "
                + "Use the Team Transport tool names your Runtime advertises in its tool catalog for this "
                + "run: a native dynamic-tool Runtime advertises them bare (for example "
                + "`send_team_message` for direct Team Transport messages), while an MCP-bound Runtime "
                + "advertises the same tools qualified (for example "
                + "`mcp__team_transport__send_team_message`). Use the advertised spelling for every Team "
                + "Transport call, including where this text names a tool without a prefix. Call the "
                + "advertised `report_task_result` exactly once before ending. "
                + "Protocol may use only its configured ontology-platform MCP tools."
            )
            # R3.0-011: the production roles' only legal competency-question
            # input is the read-only public projection mount.  Runs without
            # the 011 selector keep the previous text byte-identical.
            if self._competency_questions and role in {"coordinator", "modeling", "protocol"}:
                text += (
                    "\nApproved competency questions and answer points reach you only through the "
                    "read-only mount /agent/work/competency-questions/public/: read its "
                    "highest-ordinal public-projection-*.json and treat that file as the sole legal "
                    "source of the competency-question set. That file is the only place to take "
                    "question or answer wording from: never copy question/answer text or projection "
                    "dumps into the platform, a Team Transport message, or a candidate field, and "
                    "never use hidden material. You may still model the approved answers' public "
                    "business meaning as ordinary modeling input, citing the projection question_id "
                    "as evidence provenance."
                )
            if generation is not None:
                text += (
                    f"\nCurrent coordination generation: {generation}. "
                    "Include this non-secret generation unchanged in the role's fixed "
                    "`send_coordination` call."
                )
            if role == "acceptance":
                report_projection = (
                    f"an ordered standard-owned set of {question_count} competency questions"
                    if is_r23003
                    else "exactly two terminal Examiner reports per round"
                )
                final_projection = (
                    "Only after the Runner-projected final question (is_final_question=true) has a current, usable PASS "
                    if is_r23003
                    else "Only after the final cq-002 usable PASS has been routed successfully "
                )
                live_round_instruction = (
                    "Acceptance remains live after every non-final PASS, and "
                    if is_r23003
                    else "Acceptance remains live after every non-final cq-001 PASS, and "
                )
                return (
                    (
                        f"\nCurrent coordination generation: {generation}. "
                        if generation is not None
                        else ""
                    )
                    + "\nYou are the persistent Acceptance role. The Runner supplies an immutable ticket, "
                    "a versioned standard, and "
                    + report_projection
                    + ". Do not "
                    "read staged source paths, call platform tools, spawn Agents, or use generic multi-agent "
                    "features. Use only the Runner-owned Acceptance capability to acknowledge the ticket, "
                    "retrieve child reports, and submit one canonical PASS/FAIL/BLOCKED verdict to Coordinator. "
                    "Wait for the Runner's acceptance-start delivery before calling acceptance_get_ticket or "
                    "reporting a missing-ticket issue; it carries the fixed acceptance_id and the exact "
                    "round_id (the ticket's acceptance_round_id) to use for this round. "
                    "For acceptance_child_start, provide only acceptance_id, round_id, kind, and a fresh "
                    "unique request_id. The Host derives every mechanical field: the kind-specific child "
                    "projection and its digest (from the immutable ticket), the ticket_digest (from the "
                    "round), and the attempt (Host-tracked per round/kind: 0 for the first start, 1 for the "
                    "single permitted identical-input retry). Omit input_ref and input_digest entirely (the "
                    "schema rejects them) and omit ticket_digest/attempt (the schema ignores them); never "
                    "construct, hash, or substitute any of these mechanical bindings. "
                    "For acceptance_child_recycle, completion_ref is exactly one of two one-key JSON objects: "
                    "{\"terminal_report_digest\":\"<report_digest>\"} or "
                    "{\"infrastructure_failure_digest\":\"<failure_digest>\"}. For an infrastructure failure, "
                    "copy only the inner readiness/failure-record failure_digest string into the outer "
                    "infrastructure_failure_digest key. Never send failure_digest as the outer key, never pass "
                    "the whole readiness/failure object, and never add type, ready, failure_category, "
                    "reason_code, attempt, or other fields. "
                    "Keep the Acceptance session alive across rounds; never send child terminal state through "
                    "Team Transport. Bind question, acceptance_round_id, slice revision, ticket digest, typed "
                    "evidence, and complete model-state identity in every verdict. Route only "
                    "acceptance_verdict_route to coordinator with the current generation and canonical "
                    "verdict JSON as text. "
                    + live_round_instruction
                    + "after any FAIL or BLOCKED verdict; do not call report_task_result for those outcomes. "
                    + final_projection
                    + "may you call Team "
                    "Transport report_task_result exactly once, using report_task_result(status=completed, ...) "
                    "with a concise summary "
                    "before ending. The ordinary acceptance_verdict_route delivery is not a terminal report "
                    "and cannot substitute for that completed Team Transport call."
                    + objective_suffix
                    )
            if role == "protocol":
                protocol_capability_operations: set[str] = set()
                if self.acceptance is not None:
                    descriptor = self.acceptance.capability_descriptors.get("protocol", {})
                    advertised = descriptor.get("operations", [])
                    if isinstance(advertised, list):
                        protocol_capability_operations = {
                            value for value in advertised if isinstance(value, str)
                        }
                typed_candidate_binding = {
                    "protocol_build_candidate_receipt",
                    "protocol_build_candidate_conflict",
                }.issubset(protocol_capability_operations)
                legacy_protocol_text = (
                    "\nProtocol startup barrier: wait for a direct Modeling Team Transport delivery containing the "
                    "complete candidate before making any ontology_platform MCP call. Do not call any "
                    "ontology_platform health, read, write, validation, reasoning, or retrieval tool before that "
                    "delivery is received and its candidate receipt is successfully built. This prohibition "
                    "explicitly includes `check_platform_health`, `get_project_build_context`, "
                    "`get_ontology_workspace_context`, and `get_modeling_context`; it also covers every other "
                    "configured ontology_platform tool. First build the receipt with the Runner-private "
                    "`protocol_build_candidate_receipt` capability when advertised, otherwise with the native "
                    "`protocol_mechanics`/`build_candidate_receipt` tool using the unchanged delivered candidate. "
                    "The `candidate_receipt_required` error means this barrier is still closed: stop and wait for "
                    "Modeling rather than retrying a health/read call. Use the advertised Team Transport "
                    "name for every Team Transport call: `send_team_message`, `send_coordination`, and "
                    "`report_task_result` as your tool catalog advertises each of them. "
                    "\nYou must read the enumerated modeling-batch-item-contract.json source. "
                    "You must also read the enumerated acceptance-stage-handoff-contract.json source; it is the "
                    "authoritative nested schema for modeling_receipts, platform_read evidence_ref/page fields, "
                    "stage-specific successful statuses, and canonical handoff/delivery digest rules. Do not "
                    "guess nested receipt fields from this prompt or Python implementation. "
                    "Before any platform call, read /opt/mechanics-contract.json and follow its ordered "
                    "Build Session lifecycle exactly: create with initial_checkpoint omitted or null; save the "
                    "mandatory initial checkpoint before lease acquisition; after Batch/application, validation, "
                    "reasoning, and governed query, reread the Session before saving the mandatory final "
                    "checkpoint; complete using that final receipt revision and then reread the completed Session. "
                    "Use only the contract's exact receipt bindings and checkpoint fields; do not add custom fields. "
                    "When a Codex tool presents items as Array<unknown>, that file is the platform-general "
                    "nested construction contract derived from the public handler/MCP contract: use it to construct "
                    "the Batch/Item envelope, not as a conflict or missing input. Modeling sends a platform-neutral "
                    "semantic candidate; Protocol alone translates it into the envelope and must not require Modeling "
                    "to author exact items. The public tool remains the final execution and validation authority."
                    f" In the formal {formal_requirement_label} gate, first obtain the current candidate and mechanical receipt: use "
                    "the Runner-typed candidate receipt path when it is advertised below, otherwise call "
                    "build_candidate_receipt. This builder step does not send Team Transport. Complete the full "
                    "platform-translation decision before any response: if translation conflicts, call the "
                    "corresponding typed or native build_candidate_conflict path with a stable conflict_code and "
                    "concrete conflict_detail, then send only conflict_json; if translation succeeds, send only "
                    "receipt_json. Never hand-write a conflict or reuse prior-delivery digests. For every current "
                    "candidate or revision, send exactly one of those two responses through Team Transport, with "
                    "reply_to_delivery_id set to that candidate's delivery_id. Remain active for "
                    "revisions, and report terminal only after the Runner delivers Modeling's terminal-handoff. "
                    "Preserve source-grounded evidence_citations when present; do not read/guess source locators or "
                    "owner answers. Use the generic mechanics contract and configured retrieval fallback for ordinary "
                    "candidates. For ordinary formal retrieval, use the accepted candidate's consumer_query "
                    "required_paths as the sole plan: issue one query_semantic_context call per required path with "
                    "query exactly equal to that path, singleton relation/fact resource_types, asserted-only and "
                    "run-owned ontology scope; broad CQ/question queries and expected answers never count. The "
                    "host artifact gate validates each frozen cursor chain and registers the typed receipt. Emit only silent_for_acceptance to coordinator through "
                    "`send_coordination` with the current generation after the ordered protocol work is quiet."
                )
                if self._unified_graph and formal_contract is None:
                    text += (
                        "\nR3.0-009 unified-graph candidate continuation: wait for the direct Modeling "
                        "candidate and use the Runner-validated stage-3 slot, source-grounded approvals, "
                        "topology candidate gate, and frozen CQ when the Task enables CQ acceptance as the "
                        "current boundaries. Do not call the "
                        "R2.3 native build_candidate_receipt on an r3-0-009-unified-graph/v1 candidate; "
                        "that legacy builder requires a different candidate schema and its failure does "
                        "not invalidate the 009 candidate. Read the staged 009 and modeling-batch item "
                        "contracts, obtain the current workspace context, publish a fresh plan/client_batch_id/key, "
                        "and wait for the current Coordinator's R3.0-014 translation review before a "
                        "deterministic dry_run. Keep apply_atomic closed until its separate approval and "
                        "report exact typed blockers rather than adapting the business candidate to a "
                        "receipt schema. Use only authorized role mounts and scoped Team handoffs. "
                        "\nReply obligation on this route: each direct Modeling candidate or revision that "
                        "expects a reply must be answered through `send_team_message` with "
                        "`reply_to_delivery_id` set to that candidate's `delivery_id`, as soon as your "
                        "translation decision for it is complete. The Coordinator's R3.0-014 translation "
                        "review is not that answer, and waiting for it never closes the slot. If the "
                        "current candidate cannot be answered on this route, send the typed conflict as "
                        "that reply, or call `report_task_result(status=blocked, ...)`. A completed "
                        "terminal report while one of your replies is still undelivered is refused by "
                        "Team Transport, so never leave a reply slot open and wait."
                    )
                else:
                    text += legacy_protocol_text
                if is_r23003:
                    text += (
                        " Before invoking any Session, Lease, batch, validation, reasoning, or other stateful "
                        "ontology_platform tool after an accepted candidate receipt, call the exact-O "
                        "`get_modeling_context` read through the configured Protocol surface and verify the same "
                        "Project/Ontology, ready workspace, non-empty workspace_version, no issues, and no stale "
                        "derived state. An unequal workspace_version invalidates the old context and candidate "
                        "receipt; make the typed zero-mutation full-revision conflict path and wait for a complete "
                        "revised candidate before any mutation. Never reuse a stale receipt or send a patch."
                    )
                if self._formal_coordination_enabled() and self.acceptance is not None:
                    text += (
                        f" For the formal {formal_requirement_label} acceptance gate, the Runner has issued the exact non-secret "
                        f"stage-handoff nonce {self.acceptance.stage_handoff_nonce}. After all five current-run "
                        "stages (dry-run, apply, readback, validation, reasoning) and governed retrieval are "
                        "complete, send one canonical compact JSON object directly to Coordinator with "
                        "`send_team_message` (not `send_coordination`), using schema "
                        "r2-3-005-acceptance-stage-handoff/v1 and exact fields "
                        "schema_version,handoff_id,handoff_nonce,task_id,producer_run_id,slice_id,slice_revision, "
                        "model_state,model_state_digest,candidate_digest,modeling_receipts,handoff_digest. "
                        "The capability supplies the nonce, receipt bindings, and canonical digest; include no source "
                        "bytes, expected answers, or ticket fields. Call protocol_build_acceptance_stage_handoff with "
                        "exactly protocol_id=protocol and DO NOT supply stage_calls: the carrier auto-selects the "
                        "five canonical final-state observed calls (the final apply_atomic over the live workspace "
                        "version, its paired validated dry_run, the final get_modeling_context readback, and the "
                        "succeeded validation/reasoning over the live graph set). protocol_list_platform_artifacts "
                        "is for your awareness only; never hand-pick stages or compute receipts, pages, digests, or "
                        "artifact paths in model reasoning. "
                        "Send the returned handoff_json unchanged once. The "
                        "Runner rejects unobserved calls, wrong stage tool/mode/status/scope, artifact tamper, and "
                        "candidate identities other than the accepted candidate. Coordinator must pass the exact "
                        "delivery_id and unchanged object to its draft capability."
                    )
                if typed_candidate_binding:
                    text += (
                        " The Runner-private Protocol capability advertises typed formal candidate binding: "
                        "for every current Modeling candidate or candidate-redrive, call "
                        "protocol_build_candidate_receipt with exactly protocol_id=protocol and the original "
                        "delivery_id. Do not pass candidate JSON, candidate_text, path, digest, recipient, or "
                        "transport fields; the Runner resolves the retained exact candidate and returns structured "
                        "candidate plus receipt and exact canonical receipt_json; this obtains the retained data but "
                        "does not send it. Complete the translation decision before any Team Transport response. If "
                        "translation cannot proceed, call protocol_build_candidate_conflict with exactly the same "
                        "protocol_id and delivery_id plus stable conflict_code and concrete conflict_detail, then "
                        "send only its unchanged conflict_json with expects_reply=true. If translation succeeds, "
                        "send only the unchanged receipt_json with expects_reply=false. If the receipt capability "
                        "returns structuredContent {ok: false, error: {reason: consumer_query_plan_invalid, ...}}, "
                        "its retrieval-plan rejection is final for that exact candidate: do not retry the capability "
                        "and never send an accepted receipt; follow the error's action field and build the typed "
                        "conflict with a stable conflict_code and that detail so Modeling receives one complete "
                        "revision request. Every candidate or revision "
                        "gets exactly one of receipt_json or conflict_json, never both, with reply_to_delivery_id set "
                        "to the original delivery_id. The typed capability never sends Team Transport; it permits "
                        "one conflict immediately after that receipt build, before either response is sent. A "
                        "repeat receipt call for the same original delivery_id while that candidate is still "
                        "awaiting its reply or redriving returns the identical canonical receipt (marked "
                        "idempotent_replay): send that unchanged receipt_json as the formal reply; never escalate "
                        "an issue over it. It still rejects duplicate conflict calls, receipt calls after a "
                        "conflict was built, stale or foreign IDs, and terminal delivery IDs. After the receipt "
                        "for that delivery_id is registered and accepted, one further receipt call is the "
                        "authorized read-only re-fetch for the platform translation stage: it returns the same "
                        "retained candidate and byte-identical receipt marked idempotent_replay. Use it instead "
                        "of transcribing the candidate from transcript text, and never re-send the replayed "
                        "receipt_json as a new Team Transport reply."
                    )
                    if is_r23003:
                        text += (
                            " For R2.3-003 only, when an accepted receipt has already been sent and registered and a "
                            "later live binding read exposes a pre-mutation mismatch, call the typed conflict builder "
                            "with the original delivery_id, then send its unchanged conflict_json as a new standalone "
                            "Protocol-to-Modeling delivery with expects_reply=true and reply_to_delivery_id=None. The "
                            "typed conflict must retain original_delivery_id, receipt_digest, workspace_version, and "
                            "mutation_state=zero-mutation; Modeling replies with one full revised candidate bound to "
                            "this standalone conflict delivery_id. Pre-receipt conflicts and all R2.3-005 candidates keep "
                            "the original reply-bound semantics. "
                            " If protocol_build_candidate_receipt itself fails at the receipt gate (including the "
                            "R2.3-003 exact-delete validator), do not retry that call or send any accepted receipt. "
                            "Use the native protocol_mechanics build_candidate_conflict with the unchanged complete "
                            "candidate and a stable validator conflict code/detail. The native MCP result has only content "
                            "and structuredContent (no conflict_json): verify content[0].text parses to structuredContent "
                            "and equals its canonical JSON serialization (ensure_ascii=false, sorted keys, compact "
                            "separators), then send only content[0].text with expects_reply=true and "
                            "reply_to_delivery_id bound to the original candidate delivery. This is the reply-bound "
                            "request for Modeling to send one full revised candidate bound to the conflict delivery; "
                            "never send free text, a patch, or a duplicate receipt/reply. If the native conflict builder "
                            "or result-shape check fails, report blocked and send no receipt/reply."
                        )
                if proof_gate:
                    text += (
                        " For this proof-gated task, before the first submit_modeling_batch call, validate assertion "
                        "IDs/scope/citations against the frozen proof matrix, write the run-local "
                        "candidate-item-evidence-map, compare the group-projected safe dry-run Evidence plan, and "
                        "complete the native proof-v2 verifier."
                    )
                context = self.run.protocol_context
                if context:
                    return (
                        text
                        + "\nMechanical platform scope (no credential): "
                        + json.dumps(context, ensure_ascii=False, sort_keys=True)
                        + objective_suffix
                    )
            if role == "coordinator":
                typed_ticket_binding = False
                if self._formal_coordination_enabled() and self.acceptance is not None:
                    coordinator_descriptor = self.acceptance.capability_descriptors.get(
                        "coordinator", {}
                    )
                    advertised = coordinator_descriptor.get("operations", [])
                    typed_ticket_binding = (
                        isinstance(advertised, list)
                        and "coordinator_ticket_draft_from_delivery" in advertised
                    )
                frozen_question_ids = self._frozen_acceptance_question_ids()
                frozen_question_instruction = ""
                if frozen_question_ids:
                    rendered_ids = ", ".join(f"`{question_id}`" for question_id in frozen_question_ids)
                    if is_r23003:
                        frozen_question_instruction = (
                            " Before any typed ticket draft, read the Runner-provided ordered standard list; "
                            f"the question IDs in order are {rendered_ids} (question_count={len(frozen_question_ids)}). "
                            "Use each ID once with a positive ticket_revision and use Runner-projected ordinal/count/"
                            "previous/next/is_final metadata. Never infer order or finality from an ID name."
                        )
                    else:
                        frozen_question_instruction = (
                            " Before any typed ticket draft, read the task's Runner-provided frozen-question list; "
                            f"the exact two IDs are {rendered_ids}. Use only these IDs, once each, with a positive "
                            "ticket_revision (revision 1 for the first draft). Never guess an abbreviated ID such as "
                            "`cq-1`, derive an ID from Protocol, or ask Protocol to provide the IDs. If the task does "
                            "not expose exactly these two IDs, do not call the draft capability."
                        )
                draft_revision_instruction = (
                    " The Runner projects ordinal/count/previous/next/is_final metadata for each ordered "
                    "standard question; use that metadata and never infer finality or order from an ID."
                    if is_r23003
                    else " Both frozen questions may use revision 1; do not treat the second question as a duplicate."
                )
                if typed_ticket_binding:
                    ticket_instruction = (
                        " When Protocol sends the structured acceptance-stage handoff, retain only the "
                        "original delivery_id from the direct Team Transport envelope and call the "
                        "Runner-private coordinator_ticket_draft_from_delivery once "
                        "per frozen question, passing exactly coordinator_id=coordinator, "
                        "handoff_delivery_id, question_id, and positive ticket_revision. Do not parse, "
                        "copy, shorten, reconstruct, or resend handoff JSON; do not provide handoff_digest, "
                        "model_state, stage receipts, source paths, recipient, or transport fields. The "
                        "Runner resolves the exact registered Protocol delivery and owns nonce, current-run "
                        "stage receipts, authenticated live model state, canonical read allowlist, staged "
                        "source digests, and frozen policy."
                        + draft_revision_instruction
                        + " Publish only the complete returned draft "
                        "exactly once through coordinator_publish_acceptance_ticket."
                        + frozen_question_instruction
                    )
                else:
                    ticket_instruction = (
                        " When Protocol sends the structured acceptance-stage handoff, parse its exact JSON and "
                        "call the Runner-private coordinator_ticket_draft once per question, "
                        "passing the delivery_id from the direct Team Transport envelope, the unchanged "
                        "handoff object and digest, the frozen question_id, and the positive ticket_revision. "
                        "The capability owns staged source digests, authenticated live model_state, canonical "
                        "read allowlist, standard fields, and all five receipt checks. Publish only the returned "
                        "complete draft exactly once through coordinator_publish_acceptance_ticket, passing the "
                        "same object/digest/requirement reference; never hand-author, shorten, replace, or mutate "
                        "it. `{}`/shorthand, changed run/project/ontology/state/slice/digest, or any second draft "
                        "is rejected."
                        + frozen_question_instruction
                    )
                sequential_instruction = ""
                if self._formal_coordination_enabled():
                    if is_r23003:
                        sequential_instruction = (
                            "\nFormal ordered N-CQ acceptance is mandatory: after each current question receives a usable PASS, "
                            "start exactly the Runner-projected next_question_id only after the prior round's children are "
                            "reclaimed. A question with is_final_question=true starts no further round and waits for normal "
                            "settlement. FAIL/BLOCKED never advances, and rounds never overlap."
                        )
                    else:
                        sequential_instruction = (
                            "\nFormal R2.3-005 sequential acceptance is mandatory: after you receive and confirm the "
                            "cq-001 PASS verdict through the Runner-private verdict capability, immediately send "
                            "exactly one acceptance_start for the already published cq-002 ticket, using that "
                            "ticket's exact acceptance_round_id. Do not wait for a cq-002 verdict before starting "
                            "cq-002; no such verdict can exist until its round is started. Do not rebuild, mutate, "
                            "or republish either ticket while advancing. A final cq-002 PASS starts no further "
                            "round and waits for the normal Acceptance terminal handoff and settlement. FAIL returns "
                            "to the existing Modeling repair/revision path; BLOCKED waits for recovery or revision; "
                            "neither non-PASS verdict advances to the next CQ, and never overlap two rounds."
                        )
                return text + (
                    "\nCoordinator receives no raw business or consumer-source bytes. Use only the "
                    "Runner-private capability MCP to publish the fixed requirement-owned ticket and "
                    "read the Acceptance verdict; do not redefine CQs, approved-source paths, or the "
                    "quality standard. After Modeling-ready and Protocol-silent, emit only "
                    "acceptance_start to acceptance through `send_coordination` with the current "
                    "generation and acceptance_round_id as text. Use only the Project/Ontology created for this "
                    "run; never reuse or bind a prior/caller-supplied scope and never initiate a second semantic "
                    "start."
                    + ticket_instruction
                    + " Only after unchanged publication succeeds "
                    "send acceptance_start with the returned acceptance_round_id. Coordinator never reads staged "
                    "business sources or receipt payload bytes."
                    + sequential_instruction
                    + "\nWhen forwarding an outer answer to a grounded Modeling question, send that exact answer "
                    "once with reply_to_delivery_id set to the current Modeling question delivery_id. Do not "
                    "duplicate it or leave it unbound."
                    "\n`report_task_result` is recorded exactly once only after Modeling, Protocol, and Acceptance "
                    "have each reported completed or blocked. A dependency rejection is not recorded; wait for "
                    "their terminal handoffs and retry without reviewing their semantics. Coordinator reports last."
                ) + objective_suffix
            if role == "modeling":
                modeling_text = text + (
                    "\nEmit only ready_for_acceptance to coordinator through `send_coordination` with "
                    "the current generation once the semantic slice is ready; never emit "
                    "silent_for_acceptance or acceptance_start."
                    "\nSend each platform-neutral candidate or revision with expects_reply=true and retain the "
                    "returned delivery_id. Wait for Protocol's delivered receipt or conflict whose "
                    "reply_to_delivery_id matches it. On conflict, send a revision as a new expects_reply request; "
                    "if you cannot revise, send no further candidate and report blocked. Without an established "
                    "reply request, Modeling may report only blocked, never completed. Every candidate item must "
                    "preserve source-grounded evidence_citations when available; do not put platform IDs, Batch IDs, "
                    "or receipt labels into the platform-neutral candidate."
                )
                if is_r23003:
                    modeling_text += (
                        "\nR2.3-003 Modeling has one independent project-scoped read key and exactly three "
                        "read tools through the local `modeling_read_proxy`: `get_modeling_context`, "
                        "`get_ontology_read_model`, and `query_semantic_context`. Use the exact Project/Ontology "
                        "scope supplied by the proxy; read only model_name classes, entities, facts, or rules, "
                        "and use ontologies scope with ontology_ids containing exactly this ontology. Do not call "
                        "history/delta, writes, validation, reasoning, or any other platform tool. First call "
                        "`get_modeling_context` and require a ready workspace, non-empty workspace_version, "
                        "non-negative resource counts, no issues, and no stale derived state. The Runner keeps an "
                        "immutable context receipt; direct candidate Transport and the staged candidate capability "
                        "remain closed until that exact context call succeeds. After a receipt or before any later "
                        "Protocol stateful action, re-read the exact context; a workspace-version drift is a typed "
                        "zero-mutation conflict requiring one complete revised candidate, never a patch or stale receipt."
                    )
                if self._candidate_publication is not None:
                    identity = self._candidate_publication.identity
                    modeling_text += (
                        "\nThis run has one Runner-validated continuation candidate, revision "
                        f"{identity.candidate_revision}, candidate_digest {identity.candidate_digest}, and "
                        f"semantic_digest {identity.semantic_digest}. Reuse it only by calling the "
                        "Runner-private modeling_publish_staged_candidate capability exactly once with "
                        "modeling_id=modeling. Do not read or parse a carrier, invoke a shell or interpreter, "
                        "serialize JSON, send the outer continuation envelope, or call `send_team_message` for this "
                        "candidate. The capability owns the exact candidate_text, digest checks, recipient, "
                        "expects_reply flag, and delivery ID. Retain its returned delivery_id and wait for the "
                        "normal Protocol reply bound to that ID."
                    )
                if proof_gate:
                    modeling_text += (
                        " For this proof-gated task, every item must carry non-empty evidence_citations with the "
                        "exact document_name, excerpt, source artifact/locator/hash, and owner_answer_id fields, "
                        "and the candidate must satisfy the frozen assertion matrix."
                    )
                return modeling_text + objective_suffix
            if role == "competency-question" and self._competency_questions:
                return text + (
                    "\nYou learn the approved slice set only from the Runner's direct "
                    "cq-slices-approved delivery; do not poll shared run paths and do not read "
                    "production role artifacts. Publish every draft with the Runner-private "
                    "cq_publish_question_draft capability and wait for the cq-review-decision "
                    "delivery before any further draft. Keep hidden question text and answer "
                    "points out of your terminal `report_task_result` "
                    "message; report a status summary only."
                ) + objective_suffix
            return text + objective_suffix
        return (
            self.run.configuration.task.objective
            + "\nAllowed sources: "
            + ", ".join(
                f"/agent/home/sources/{path.name}"
                for path in self.run.configuration.task.allowed_sources
            )
            + "\nUse Team Transport for direct messages and call report_task_result exactly once before ending. Protocol must call check_platform_health once; do not call another platform tool."
        )

    def receive_outer(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        if not isinstance(message, dict):
            raise TeamConfigurationError("outer message must be a JSON object")
        action = message.get("action")
        if action == "question":
            if self._formal_coordination_enabled():
                raise RecoverableOuterInputError(
                    "schema-v2 outer questions are Runner-owned",
                    code="invalid_outer_question",
                    run_id=self.run.run_id,
                )
            self._record_outer_question(message)
        elif action == "issue_resolution":
            # 2026-09-11 auth006-start8: staged v3 runs enable the cooperative
            # issue channel, so outer resolutions must reach them too.
            if (
                not (self._formal_coordination_enabled() or self._staged_decisions)
                or self.transport is None
            ):
                raise TeamConfigurationError("issue escalation capability is unavailable")
            resolution = self._outer_issue_resolution(message)
            if resolution.resolution_type != "abort":
                blocker = self._staged_resolution_blocker()
                if blocker is not None:
                    raise RecoverableOuterInputError(
                        blocker,
                        code="unknown_mutation_requires_reconciliation",
                        run_id=resolution.run_id,
                        issue_id=resolution.issue_id,
                        reporter_id=resolution.reporter_id,
                        control_epoch=resolution.control_epoch,
                    )
            try:
                self.transport.persist_issue_resolution(resolution)
            except RoutingError as exc:
                if exc.code != "issue-resolution-rejected":
                    raise
                raise RecoverableOuterInputError(
                    str(exc),
                    code="issue_resolution_rejected",
                    run_id=message.get("run_id") if isinstance(message.get("run_id"), str) else self.run.run_id,
                    issue_id=message.get("issue_id") if isinstance(message.get("issue_id"), str) else None,
                    reporter_id=message.get("reporter_id") if isinstance(message.get("reporter_id"), str) else None,
                    control_epoch=message.get("control_epoch") if isinstance(message.get("control_epoch"), int) and not isinstance(message.get("control_epoch"), bool) else None,
                ) from exc
            # Persist first; only then make the resolution visible to Coordinator.
            self._append_evidence("issue-resolution", resolution.as_dict())
            coordinator = self._issue_coordinator_id()
            try:
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="issue-resolution",
                        text=json.dumps(resolution.as_dict(), ensure_ascii=False, sort_keys=True),
                    ),
                )
            except Exception as exc:
                if self._provider_rejection_pending(coordinator):
                    # The resolution is already persisted; a Coordinator parked
                    # in a provider wait cannot receive it yet.  Surface the
                    # bounded, actionable deferral instead of tearing the run.
                    self._append_evidence(
                        "issue-resolution",
                        {
                            "event": "coordinator-delivery-deferred",
                            "issue_id": resolution.issue_id,
                            "detail": str(exc)[:200],
                        },
                    )
                    raise RecoverableOuterInputError(
                        "Coordinator is parked in a provider wait; recover it "
                        "(recover_provider) so it can act on the persisted resolution",
                        code="coordinator_waiting_provider",
                        run_id=self.run.run_id,
                        issue_id=resolution.issue_id,
                        reporter_id=resolution.reporter_id,
                        control_epoch=resolution.control_epoch,
                    ) from exc
                raise TeamConfigurationError("issue resolution Coordinator delivery failed") from exc
            # R2.3-009 start15/start20: the Coordinator's discretionary relay of
            # the ruling to Modeling proved unreliable twice — Modeling kept a
            # stale precondition (an unanswered owner question in start15, a
            # digest-mismatched gate notice in start20) while the ruling that
            # lifted it never arrived. The ruling directly constrains the
            # candidate author's next action, so it is also delivered to the
            # Modeling role mechanically. Failures surface as evidence, not a
            # teardown of the already-persisted resolution.
            # 2026-09-11 auth006-start8: staged runs carry the same
            # cooperative issue channel, so the mechanical Modeling relay
            # applies to them identically.
            if self._formal_coordination_enabled() or self._staged_decisions:
                modeling_id = next(
                    (
                        agent.agent_id
                        for agent in self.run.configuration.profile.agents
                        if agent.package.role == "modeling"
                    ),
                    None,
                )
                if modeling_id is not None:
                    try:
                        self.adapter.send_message(
                            modeling_id,
                            RuntimeDelivery(
                                sender_id="user/outer",
                                recipient_id=modeling_id,
                                kind="issue-resolution",
                                text=json.dumps(
                                    resolution.as_dict(), ensure_ascii=False, sort_keys=True
                                ),
                            ),
                        )
                    except Exception:
                        self._append_evidence(
                            "issue-resolution",
                            {"event": "modeling_delivery_failed"},
                        )
        elif action == "user":
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                raise RecoverableOuterInputError(
                    "outer user text must be a non-empty string",
                    code="invalid_owner_answer",
                    run_id=self.run.run_id,
                )
            if self.run.configuration.task.schema_version == 2 and set(message) - {
                "action",
                "text",
                "question_delivery_id",
            }:
                raise RecoverableOuterInputError(
                    "schema-v2 owner answer envelope has invalid fields",
                    code="invalid_owner_answer",
                    run_id=self.run.run_id,
                )
            coordinator = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "coordinator"
            )
            if self.run.configuration.task.schema_version == 2:
                question_delivery_id: object
                if self._formal_coordination_enabled():
                    if "question_delivery_id" in message:
                        # An explicit ID is a mechanical disambiguator only.  The
                        # release path below remains the authority for displayed,
                        # unconsumed, same-run/project and origin bindings.
                        question_delivery_id = message["question_delivery_id"]
                    else:
                        # Preserve the text-only compatibility path when exactly
                        # one currently displayed question is eligible.
                        question_delivery_id = self._resolve_formal_owner_question(text)
                else:
                    question_delivery_id = message.get("question_delivery_id")
                self._release_owner_answer(
                    coordinator,
                    text,
                    question_delivery_id,
                )
            else:
                try:
                    self.adapter.send_message(
                        coordinator,
                        RuntimeDelivery(
                            sender_id="user/outer",
                            recipient_id=coordinator,
                            kind="outer-user",
                            text=text,
                        ),
                    )
                except Exception as exc:
                    if self._provider_rejection_pending(coordinator):
                        raise RecoverableOuterInputError(
                            "Coordinator is parked in a provider wait; recover it "
                            "(recover_provider) before delivering user input",
                            code="coordinator_waiting_provider",
                            run_id=self.run.run_id,
                        ) from exc
                    raise
                self._outer_user_texts.add(text)
                self._append_evidence("outer-user", {"text": text})
        elif action == "status":
            waits = self._provider_wait_status_records()
            if waits:
                return [
                    {"type": "provider-wait-status", "waits": waits}
                ] + self.drain()
        elif action == "pause":
            self.adapter.pause()
            self._state("PAUSED")
        elif action == "resume":
            self.adapter.resume()
            self._state("RUNNING")
        elif action == "recover_provider":
            # 2026-09-14 provider-recovery: host takeover after the user reports
            # the external condition lifted (quota reset, recharge, provider
            # recovered).  Never depends on a blocked Coordinator: the action
            # binds the user's message to the role's current pending wait and
            # starts a new turn on the original live thread.
            record = self._recover_provider_outer(message)
            return self.drain() + [record]
        elif action == "checkpoint":
            # R3.0-015 S1: host/Coordinator-originated checkpoint save or
            # inspect.  The action grants no new agent write permission: a
            # save only copies already-published run artifacts the Runner can
            # verify on disk, and a "phase complete" text claim without
            # artifacts is a typed missing-artifact rejection.
            record = self._handle_checkpoint_outer(message)
            return self.drain() + [record]
        elif action == "stop":
            # Explicit stop overrides the provider-wait cleanup deferral.
            self._provider_wait_stop_requested = True
            # R3.0-015 issue-4: the explicit host stop is also the last owner
            # answer for a still-open cooperative issue.  Without this the
            # cleanup deferral below keeps the process exiting 0 behind a
            # WAITING_OWNER state.json that no writer backs, and the documented
            # recovery retry ("stop the original run through its existing stop
            # channel, then retry") can never be performed by the host that just
            # performed the stop.
            self._settle_issue_for_outer_stop()
            deferred = getattr(self, "_deferred_runtime_failures", None)
            if deferred:
                # Settle the retained Coordinator-takeover failure record so
                # the terminal state names it; the takeover itself never ends
                # the run while a recovered role is alive.
                self._deferred_runtime_failures = None
                self._runtime_failure_finalized = True
                agent_id, detail = deferred[0]
                self._append_evidence(
                    "runtime-failure",
                    {
                        "event": "coordinator-takeover-stopped",
                        "agent_id": agent_id,
                        **(detail if isinstance(detail, dict) else {}),
                    },
                )
                self.record_terminal_failure("runtime/infrastructure", False)
            self.cleanup()
            return [{"type": "stopped"}]
        else:
            raise TeamConfigurationError("unknown outer Runner action")
        return self.drain()

    def _recover_provider_outer(self, message: dict[str, Any]) -> dict[str, Any]:
        """Bind one explicit host recovery to a pending provider wait.

        Schema: ``{"action": "recover_provider", "text": ..., "agent_id"|"role":
        ..., "wait_id": optional}``.  The wait must currently be pending on the
        Runtime; the message starts a new turn on the original live thread.  If
        a runtime_recovery cooperative issue is open for the same role, it is
        settled through the same ledger state machine so no dependent pause is
        leaked.  Never touches the staged write gate: reconciling an unknown
        write keeps its existing path.
        """

        if not self.run:
            raise TeamConfigurationError("Runner is not prepared")
        allowed = {"action", "text", "agent_id", "role", "wait_id", "run_id"}
        if set(message) - allowed:
            raise RecoverableOuterInputError(
                "recover_provider envelope has invalid fields",
                code="invalid_provider_recovery",
                run_id=self.run.run_id,
            )
        if "run_id" in message and message.get("run_id") != self.run.run_id:
            raise RecoverableOuterInputError(
                "provider recovery run binding is invalid",
                code="invalid_provider_recovery",
                run_id=self.run.run_id,
            )
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RecoverableOuterInputError(
                "provider recovery text must be a non-empty string",
                code="invalid_provider_recovery",
                run_id=self.run.run_id,
            )
        agent_id = message.get("agent_id") if isinstance(message.get("agent_id"), str) else None
        role = message.get("role") if isinstance(message.get("role"), str) else None
        wait_id = message.get("wait_id") if isinstance(message.get("wait_id"), str) else None
        if wait_id is not None and not wait_id.strip():
            raise RecoverableOuterInputError(
                "provider recovery wait_id must be a non-empty string",
                code="invalid_provider_recovery",
                run_id=self.run.run_id,
            )
        if (agent_id is None) == (role is None):
            raise RecoverableOuterInputError(
                "provider recovery requires exactly one of agent_id or role",
                code="invalid_provider_recovery",
                run_id=self.run.run_id,
            )
        if role is not None:
            agent_id = next(
                (
                    agent.agent_id
                    for agent in self.run.configuration.profile.agents
                    if agent.package.role == role
                ),
                None,
            )
            if agent_id is None:
                raise RecoverableOuterInputError(
                    f"provider recovery role {role} is not in this run",
                    code="invalid_provider_recovery",
                    run_id=self.run.run_id,
                )
        status_reader = getattr(self.adapter, "provider_wait_status", None)
        pending = status_reader(agent_id) if callable(status_reader) else None
        if pending is None:
            raise RecoverableOuterInputError(
                "target role has no pending provider wait",
                code="provider_wait_not_pending",
                run_id=self.run.run_id,
            )
        try:
            receipt = self.adapter.recover_provider_wait(
                agent_id,
                text,
                wait_id=wait_id,
            )
        except Exception as exc:
            # Expected, externally-remediable recovery failures (stale epoch
            # binding, still-exhausted provider re-entering its wait, refused
            # dispatch, unavailable App Server) surface as one typed nonfatal
            # rejection.  The foreground admission catches only
            # RecoverableOuterInputError, so anything else here would tear the
            # run down on a remediable retry.  Adapter errors carry our own
            # sanitized messages only, never provider text.
            raise RecoverableOuterInputError(
                f"provider recovery failed: {str(exc)[:200]}",
                code="provider_recovery_failed",
                run_id=self.run.run_id,
            ) from exc
        self._append_evidence(
            "provider-wait",
            {
                "event": "host-recovery",
                "agent_id": agent_id,
                "wait_id": pending.get("wait_id"),
                "dispatch_mode": receipt.mode,
            },
        )
        self._settle_provider_wait_issue(agent_id, text)
        self._state("RUNNING", provider_recovered_agent=agent_id)
        return {
            "type": "provider-recovery",
            "agent_id": agent_id,
            "role": pending.get("role"),
            "wait_id": pending.get("wait_id"),
            "dispatch_mode": receipt.mode,
        }

    def _settle_provider_wait_issue(self, agent_id: str, text: str) -> None:
        """Settle an open runtime_recovery issue after a successful recovery."""

        ledger = self._issue_ledger()
        if ledger is None or not ledger.pending:
            return
        active = ledger.active_issue
        if (
            active is None
            or active.reporter_id != agent_id
            or active.category != "runtime_recovery"
        ):
            return
        # The durable staged-evidence guard is the sole write authority: while
        # it reports an unreconciled write, host recovery may start the next
        # turn but must never settle the gated issue (a reporter's advisory
        # mutation_state token is not evidence).
        blocker = self._staged_resolution_blocker()
        if blocker is not None:
            self._append_evidence(
                "provider-wait",
                {
                    "event": "issue-settlement-skipped",
                    "agent_id": agent_id,
                    "issue_id": active.issue_id,
                    "reason": f"staged gate closed: {blocker}"[:200],
                },
            )
            return
        # Runner-owned settlement through the same ledger transitions a
        # Coordinator control would use; every step is evidence-recorded.
        coordinator = self._issue_coordinator_id()
        resolution = IssueResolution(
            run_id=ledger.run_id,
            issue_id=active.issue_id,
            reporter_id=agent_id,
            control_epoch=active.control_epoch,
            resolution_type="repair_completed",
            resolution_text=text[:200],
            repair_component="external_service",
        )
        try:
            # Drive the run-local ledger directly: the transport wrappers
            # enqueue dispatch events for the main loop, which would duplicate
            # the recovery turn that has already started.
            if ledger.state == "reported":
                ledger.control(
                    issue_id=active.issue_id,
                    coordinator_id=coordinator,
                    reporter_id=agent_id,
                    action="pause",
                    control_epoch=active.control_epoch,
                )
            if ledger.state in {"waiting_owner", "waiting_repair"}:
                ledger.persist_resolution(resolution)
            if ledger.state == "resolution_ready":
                control = ledger.control(
                    issue_id=active.issue_id,
                    coordinator_id=coordinator,
                    reporter_id=agent_id,
                    action="resume",
                    control_epoch=active.control_epoch,
                    resolution=resolution,
                )
                ledger.mark_dispatch(control)
        except IssueError as exc:
            # The recovery turn already started; the ledger stays as-is and
            # remains observable instead of failing the recovery.
            self._append_evidence(
                "provider-wait",
                {
                    "event": "issue-settlement-skipped",
                    "agent_id": agent_id,
                    "issue_id": active.issue_id,
                    "reason": str(exc)[:200],
                },
            )

    def _settle_issue_for_outer_stop(self) -> None:
        """Settle one open cooperative issue behind an explicit host stop.

        The host stop is not an owner resolution, so this never claims one: it
        releases the ledger through the existing "no owner can answer"
        transition (``rebind_required``) rather than the ``abort`` resolution a
        Coordinator control must persist first, and it never fabricates the
        R2.3-003 zero-mutation abort reconciliation. It only removes the
        cleanup deferral: the same abort request a sanctioned Coordinator abort
        sets makes ``cleanup`` run to a truthful terminal state. The issue
        record, its reporter and its state at stop time stay in the run
        evidence, so the stopped run remains auditable and a later recovery
        decision does not have to guess.
        """

        ledger = self._issue_ledger()
        if ledger is None or not ledger.pending:
            return
        active = ledger.active_issue
        if active is None:
            return
        self._issue_abort_requested = True
        self._append_evidence(
            "issue-abort",
            {
                "source": "outer-stop",
                "issue_id": active.issue_id,
                "reporter_id": active.reporter_id,
                "category": active.category,
                "issue_state": ledger.state,
                "reason": "host stop before any owner resolution",
            },
        )
        try:
            ledger.fail_rebind(
                issue_id=active.issue_id,
                reporter_id=active.reporter_id,
                reason="host stop: the run ended before the issue was resolved",
            )
        except IssueError as exc:
            # Observable, never fatal: the stop still tears the run down and
            # the ledger keeps its state instead of failing the stop.
            self._append_evidence(
                "issue-abort",
                {
                    "source": "outer-stop",
                    "issue_id": active.issue_id,
                    "issue_state": ledger.state,
                    "settlement_skipped": str(exc)[:200],
                },
            )

    def _outer_issue_resolution(self, message: dict[str, Any]) -> IssueResolution:
        """Parse one strict outer resolution envelope; no opaque JSON payloads."""
        base = {"action", "issue_id", "reporter_id", "control_epoch", "resolution_type"}
        allowed = {
            *base,
            "run_id",
            "resolution_text",
            "repair_component",
            "before_digest",
            "after_digest",
            "verification_reference",
            "mutation_reconciliation",
        }
        context = {
            "run_id": message.get("run_id") if isinstance(message.get("run_id"), str) else None,
            "issue_id": message.get("issue_id") if isinstance(message.get("issue_id"), str) else None,
            "reporter_id": message.get("reporter_id") if isinstance(message.get("reporter_id"), str) else None,
            "control_epoch": message.get("control_epoch") if isinstance(message.get("control_epoch"), int) and not isinstance(message.get("control_epoch"), bool) else None,
        }
        if message.get("action") != "issue_resolution":
            raise RecoverableOuterInputError(
                "issue resolution action is invalid", **context
            )
        if set(message) - allowed:
            raise RecoverableOuterInputError(
                "issue resolution envelope has invalid fields", **context
            )
        if not base.issubset(message):
            raise RecoverableOuterInputError(
                "issue resolution envelope is incomplete", **context
            )
        has_run_id = "run_id" in message
        supplied_run_id = message.get("run_id")
        if has_run_id and (
            not isinstance(supplied_run_id, str) or supplied_run_id != self.run.run_id
        ):
            raise RecoverableOuterInputError(
                "issue resolution run binding is invalid",
                code="issue_run_mismatch",
                **context,
            )
        resolution_type = message.get("resolution_type")
        if not isinstance(resolution_type, str):
            raise RecoverableOuterInputError(
                "issue resolution type is invalid", **context
            )
        if resolution_type in {"guidance", "abort"}:
            expected = base | {"resolution_text"}
            if set(message) - (expected | {"run_id"}) or not expected.issubset(message):
                raise RecoverableOuterInputError(
                    "issue resolution guidance fields are invalid", **context
                )
        elif resolution_type == "repair_completed":
            legacy_fields = {
                "repair_component",
                "before_digest",
                "after_digest",
                "verification_reference",
                "mutation_reconciliation",
            }
            expected = base | {"repair_component"}
            if set(message) - (expected | legacy_fields | {"run_id", "resolution_text"}):
                raise RecoverableOuterInputError(
                    "issue resolution repair fields are invalid", **context
                )
            if not expected.issubset(message):
                raise RecoverableOuterInputError(
                    "issue resolution repair fields are incomplete", **context
                )
            component = message.get("repair_component")
            if not isinstance(component, str) or component not in REPAIR_COMPONENTS:
                raise RecoverableOuterInputError(
                    "repair component is unsupported",
                    code="repair_rebind_required",
                    **context,
                )
            # The historical five-field envelope may omit run_id because its
            # FIFO/run binding was already established.  It is only legacy
            # compatible when all five values are present and non-empty; a
            # sparse/null envelope is the new short form and must carry the
            # explicit run binding.
            legacy_complete = legacy_fields.issubset(message) and all(
                isinstance(message[field], str) and bool(message[field].strip())
                for field in legacy_fields
            )
            if not legacy_complete and "run_id" not in message:
                raise RecoverableOuterInputError(
                    "short repair resolution requires run_id", **context
                )
        else:
            raise RecoverableOuterInputError(
                "issue resolution type is invalid", **context
            )
        try:
            return IssueResolution(
                run_id=supplied_run_id if isinstance(supplied_run_id, str) else self.run.run_id,
                issue_id=message["issue_id"],
                reporter_id=message["reporter_id"],
                resolution_type=resolution_type,
                control_epoch=message["control_epoch"],
                resolution_text=message.get("resolution_text"),
                repair_component=message.get("repair_component"),
                before_digest=message.get("before_digest"),
                after_digest=message.get("after_digest"),
                verification_reference=message.get("verification_reference"),
                mutation_reconciliation=message.get("mutation_reconciliation"),
            )
        except (TypeError, IssueError) as exc:
            raise RecoverableOuterInputError(
                "issue resolution envelope is invalid", **context
            ) from exc

    def _staged_resolution_blocker(self) -> str | None:
        """Return durable staged-write evidence that keeps repair closed.

        The Agent-reported mutation state is not authoritative.  A durable
        unknown intent, receipt mismatch, or an already-latched staged gate
        keeps the repair gate closed. This helper only reads the artifacts and
        never adjudicates or reopens the gate.
        """

        if not getattr(self, "_staged_decisions", False) or self.run is None:
            return None
        if getattr(self, "_staged_gate_killed", False):
            return "staged write gate is closed pending reconciliation"
        try:
            issues = staged_intent_receipt_issues(self.run.root)
        except StagedDecisionArtifactError as exc:
            return f"staged write evidence is unreadable: {exc.detail}"
        if issues:
            first = issues[0]
            return f"staged write evidence requires reconciliation: {first.detail}"
        return None

    def _observe_modeling_question(self, delivery: Any) -> None:
        """Register only a formal Modeling->Coordinator reply request internally."""
        if not self._formal_coordination_enabled() or not self.run or not self.transport:
            return
        modeling = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "modeling"
        )
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        if (
            delivery.sender_id != modeling
            or delivery.recipient_id != coordinator
            or not delivery.expects_reply
            or delivery.reply_to_delivery_id is not None
            or not isinstance(delivery.text, str)
            or not delivery.text
        ):
            return
        delivery_id = delivery.delivery_id
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")
        existing = self._outer_questions.get(delivery_id)
        if existing is not None:
            if (
                existing.get("text") != delivery.text
                or existing.get("sequence") != delivery.sequence
                or existing.get("timestamp") != delivery.timestamp
                or existing.get("run_id") != self.run.run_id
                or existing.get("project_id") != project_id
            ):
                raise TeamConfigurationError("outer question delivery is immutable")
            return
        self._outer_questions[delivery_id] = {
            "question_delivery_id": delivery_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "text": delivery.text,
            "sequence": delivery.sequence,
            "timestamp": delivery.timestamp,
            "origin_agent_id": modeling,
            "displayed": False,
            "consumed": False,
        }

    def _formal_candidate_roles(self) -> tuple[str, str] | None:
        if not self._formal_coordination_enabled() or not self.run:
            return None
        role_ids = {
            agent.package.role: agent.agent_id
            for agent in self.run.configuration.profile.agents
        }
        modeling, protocol = role_ids.get("modeling"), role_ids.get("protocol")
        # Small owner-answer/foreground fixtures from the pre-candidate formal
        # gate intentionally contain only Modeling+Coordinator.  They must keep
        # their existing display semantics; the production profile is validated
        # with all four roles before this gate is enabled.
        if not isinstance(modeling, str) or not isinstance(protocol, str):
            return None
        return modeling, protocol

    def _formal_protocol_thread_id(self, protocol_agent_id: str) -> str:
        agents = getattr(self.adapter, "agents", None)
        agent = agents.get(protocol_agent_id) if isinstance(agents, dict) else None
        thread_id = getattr(agent, "thread_id", None)
        if isinstance(thread_id, str) and thread_id:
            return thread_id
        # A fake/legacy adapter may not expose its private Codex thread.  The
        # fallback remains a stable pending identity while the real Codex path
        # always supplies its concrete thread id.
        return f"runtime-agent:{protocol_agent_id}"

    def _notify_candidate_receipt_registered(
        self,
        identity: Any,
        accepted_receipt_delivery_id: Any,
    ) -> None:
        """Wake the same Protocol Runtime thread once after the gate opens."""

        progress = self._candidate_progress
        gate = self._candidate_platform_gate
        if (
            gate is None
            or progress is None
            or self._formal_failure_latched
            or progress.paused
            or progress.terminal_failure_latched
        ):
            return
        if not isinstance(accepted_receipt_delivery_id, str) or not accepted_receipt_delivery_id:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "accepted-receipt-delivery-id-missing",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract",
                "internal-invariant:candidate-receipt-wakeup-delivery-id-missing",
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed")
        original_delivery_id = getattr(identity, "original_delivery_id", None)
        wakeup_key = (accepted_receipt_delivery_id, original_delivery_id)
        if wakeup_key in self._candidate_receipt_wakeup_sent:
            return
        try:
            notice = candidate_receipt_registered_notice(
                identity.__dict__ if hasattr(identity, "__dict__") else identity,
                accepted_receipt_delivery_id,
            )
        except CandidatePlatformGateError as exc:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "candidate-receipt-notice-invalid",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract",
                "internal-invariant:candidate-receipt-wakeup-notice-invalid",
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed") from exc
        self._candidate_receipt_wakeup_sent.add(wakeup_key)
        delivery = RuntimeDelivery(
            sender_id="runner/candidate-gate",
            recipient_id=identity.protocol_agent_id,
            kind=CANDIDATE_RECEIPT_REGISTERED_KIND,
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            delivery_id=f"candidate-receipt-registered:{accepted_receipt_delivery_id}",
            expects_reply=False,
            reply_to_delivery_id=accepted_receipt_delivery_id,
        )
        try:
            receipt = self.adapter.send_message(identity.protocol_agent_id, delivery)
        except Exception as exc:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "runtime/infrastructure",
                    "reason_code": "candidate-receipt-wakeup-dispatch-failed",
                },
            )
            self._latch_formal_candidate_failure(
                "runtime/infrastructure", "candidate-receipt-wakeup-dispatch-failed"
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed") from exc
        if not isinstance(getattr(receipt, "turn_id", None), str) or not receipt.turn_id:
            gate.close("receipt_notification_failed")
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": "candidate-receipt-notification-failed",
                    "classification": "platform-contract",
                    "reason_code": "candidate-receipt-wakeup-turn-binding-missing",
                },
            )
            self._latch_formal_candidate_failure(
                "platform-contract",
                "internal-invariant:candidate-receipt-wakeup-turn-binding-missing",
            )
            raise TeamConfigurationError("candidate receipt registration wakeup failed")
        self._append_evidence(
            "formal-candidate-progress",
            {
                "event": "candidate-receipt-registered",
                "run_id": notice["run_id"],
                "original_delivery_id": notice["original_delivery_id"],
                "accepted_receipt_delivery_id": notice["accepted_receipt_delivery_id"],
                "candidate_digest": notice["candidate_digest"],
                "dispatch_mode": getattr(receipt, "mode", None),
                "turn_id": receipt.turn_id,
            },
        )

    def _multi_slice_role_ids(self) -> dict[str, str]:
        return {
            agent.package.role: agent.agent_id
            for agent in self.run.configuration.profile.agents  # type: ignore[union-attr]
        }

    def _deliver_multi_slice_gate_feedback(
        self, reason_code: str, artifact: str
    ) -> None:
        """Typed, deduplicated closed-gate feedback to the Coordinator (T0)."""

        if not self.run:
            return
        coordinator = self._multi_slice_role_ids().get("coordinator")
        if not isinstance(coordinator, str) or not coordinator:
            return
        notice = {
            "schema_version": "r3-0-002-multi-slice-gate-feedback/v1",
            "run_id": self.run.run_id,
            "gate_state": "closed",
            "reason_code": reason_code,
            "artifact": artifact,
            "remediation": (
                "Repair the scenario-map artifact per "
                "modeling_team/references/r3-0-002-scenario-map-contract.json; "
                "the platform MCP gate re-checks it on the next Runner cycle. "
                "The run is not terminated; do not retry platform calls."
            ),
        }
        delivery = RuntimeDelivery(
            sender_id="runner/multi-slice-gate",
            recipient_id=coordinator,
            kind="multi-slice-topology-gate",
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            expects_reply=False,
        )
        try:
            receipt = self.adapter.send_message(coordinator, delivery)
        except Exception as exc:
            # A dispatch failure of the feedback itself is recorded evidence
            # only; it must never kill the run or block self-repair (T0).
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "gate-feedback-dispatch-failed",
                    "reason_code": reason_code,
                    "artifact": artifact,
                    "detail": str(exc),
                },
            )
            return
        self._append_evidence(
            "multi-slice-gate",
            {
                "event": "gate-feedback-delivered",
                "reason_code": reason_code,
                "artifact": artifact,
                "recipient": coordinator,
                "turn_id": getattr(receipt, "turn_id", None),
            },
        )

    def _multi_slice_gate_reject(
        self, reason_code: str, artifact: str, fingerprint: str
    ) -> None:
        """Keep the gate closed with one deterministic reason, feedback once."""

        gate = self._candidate_platform_gate
        if gate is not None:
            gate.close(reason_code)
        self._append_evidence(
            "multi-slice-gate",
            {
                "event": "topology-gate-closed",
                "reason_code": reason_code,
                "artifact": artifact,
            },
        )
        if fingerprint in self._multi_slice_gate_feedback_fingerprints:
            return
        self._multi_slice_gate_feedback_fingerprints.add(fingerprint)
        self._deliver_multi_slice_gate_feedback(reason_code, artifact)

    # --- R3.0-008B segment 1: staged modeling decision gates -----------------

    def _deliver_staged_gate_feedback(
        self,
        reason_code: str,
        artifact: str,
        recipient_role: str = "coordinator",
        details: Sequence[str] = (),
    ) -> None:
        """Typed, deduplicated staged-gate feedback (T0: never a terminal kill).

        The fingerprint includes a digest of the issue details: identical
        content stays deduplicated across ticks, while a changed issue on the
        same artifact (different conclusion, different field) re-arms the
        notice instead of being silently dropped (auth008-start1: a
        content-blind fingerprint let a stalled artifact idle the run to its
        fallback timeout after a single notice).
        """

        if not self.run:
            return
        recipient = self._multi_slice_role_ids().get(recipient_role)
        if not isinstance(recipient, str) or not recipient:
            return
        content = "\n".join(sorted(details))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        fingerprint = f"{recipient_role}:{reason_code}:{artifact}:{digest}"
        if fingerprint in self._staged_gate_feedback_fingerprints:
            return
        self._staged_gate_feedback_fingerprints.add(fingerprint)
        notice = {
            "schema_version": "r3-0-008b-staged-gate-feedback/v1",
            "run_id": self.run.run_id,
            "gate_state": "closed",
            "reason_code": reason_code,
            "artifact": artifact,
            "details": sorted(details),
            "remediation": (
                "Repair the staged artifact per "
                "modeling_team/references/r3-0-008b-staged-decisions-contract.json; "
                "the Runner re-checks it on the next cycle. The run is not "
                "terminated; fix the named artifact and retry."
            ),
        }
        delivery = RuntimeDelivery(
            sender_id="runner/staged-decision-gate",
            recipient_id=recipient,
            kind="staged-decision-gate",
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            expects_reply=False,
        )
        try:
            receipt = self.adapter.send_message(recipient, delivery)
        except Exception as exc:
            # A dispatch failure of the feedback itself is recorded evidence
            # only; it must never kill the run or block self-repair (T0).
            self._append_evidence(
                "staged-decisions",
                {
                    "event": "gate-feedback-dispatch-failed",
                    "reason_code": reason_code,
                    "artifact": artifact,
                    "recipient": recipient,
                    "detail": str(exc),
                },
            )
            return
        self._append_evidence(
            "staged-decisions",
            {
                "event": "gate-feedback-delivered",
                "reason_code": reason_code,
                "artifact": artifact,
                "recipient": recipient,
                "turn_id": getattr(receipt, "turn_id", None),
            },
        )

    def _staged_gate_kill_switch(self, reason_code: str, detail: str) -> None:
        """The one hard stop: an unreconciled platform write integrity break.

        The shared platform MCP gate closes with ``staged_unreconciled_batch``
        and the latch keeps every later staged check intervening until a human
        adjudicates the durable intent with the deterministic
        ``adjudicate_unknown_intent`` branches.
        """

        if self._staged_gate_killed:
            return
        self._staged_gate_killed = True
        gate = self._candidate_platform_gate
        if gate is not None:
            gate.close("staged_unreconciled_batch")
        self._append_evidence(
            "staged-decisions",
            {
                "event": "kill-switch",
                "gate_state": "closed",
                "reason_code": "staged_unreconciled_batch",
                "detail": detail,
                "classification": "platform-contract",
                "remediation": (
                    "Manual adjudication required: reconcile the platform batch "
                    "listing with value-semantics/submission-intents and "
                    "submission-receipts before any further staged submission."
                ),
            },
        )
        self._deliver_staged_gate_feedback(
            "staged_unreconciled_batch", "platform-reconciliation", "protocol"
        )

    def _load_staged_approvals(self, run_root: Path) -> dict[str, Any] | None:
        paths = staged_decision_artifact_paths(run_root, unified=self._unified_graph)
        if not paths["approvals"].exists():
            return None
        try:
            return load_approvals(paths["approvals"])
        except StagedDecisionArtifactError:
            return None

    def _check_staged_decision_gates(self) -> bool:
        """R3.0-008B staged checks; returns whether the topology check may run.

        Ordering (design section 3): the stage 3 minimal slot is a
        prerequisite of the R3.0-002 topology decision, so an invalid slot
        skips the topology check for this tick WITHOUT latching
        ``_multi_slice_gate_opened`` and WITHOUT re-closing the shared gate
        (its state.json keeps the prepare-time ``topology_missing_artifact``
        reason).  Stage 3 ``stage3_*`` reason codes surface only through
        feedback and evidence streams.  Once the slot is valid, this check
        stops intervening and the 002 topology gate logic is byte-identical.
        """

        if not getattr(self, "_staged_decisions", False) or self.run is None:
            return True
        run_root = self.run.root
        if self._staged_gate_killed:
            return False
        # 1) Write-integrity kill-switch first: suspended unknown intents or
        #    receipt/intent cross-check failures are unreconciled batches.
        #    A corrupt (unparsable) intent/receipt JSON file is the same
        #    write-integrity break: it converges to the typed kill-switch
        #    instead of escaping this monitor tick and crashing the run
        #    (design section 4.1: every failure is typed and fail-closed).
        try:
            intent_issues = staged_intent_receipt_issues(run_root)
        except StagedDecisionArtifactError as exc:
            self._staged_gate_kill_switch(exc.reason_code, exc.detail)
            return False
        for issue in intent_issues:
            self._staged_gate_kill_switch(issue.reason_code, issue.detail)
            return False
        # 2) Cross-artifact checks (conclusions state machine + archive chain,
        #    approvals anchoring, unlock consistency, ledger-vs-receipts).
        for issue in staged_artifact_issues(run_root, unified=self._unified_graph):
            if issue.reason_code == "staged_unreconciled_batch":
                self._staged_gate_kill_switch(issue.reason_code, issue.detail)
                return False
            self._deliver_staged_gate_feedback(issue.reason_code, issue.artifact, details=(issue.detail,))
        # 3) Stage 3 minimal slot prerequisite (approval cross-validated).
        approvals = self._load_staged_approvals(run_root)
        slot_issue = staged_stage3_issue(run_root, approvals, unified=self._unified_graph)
        if slot_issue is not None:
            # Prerequisite model: intervene without latch or gate close.
            self._deliver_staged_gate_feedback(
                slot_issue.reason_code, slot_issue.artifact, details=(slot_issue.detail,)
            )
            return False
        return True

    def _handle_staged_submit_modeling_batch(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """The Runner-private staged Modeling Batch submission capability.

        Mechanical checks run in the fixed design section 3.6 order; every
        rejection is a typed, self-healing ``StagedSubmissionRejection`` so the
        capability endpoint returns ``{ok: False, error: {...}}`` instead of an
        opaque transport error.  ``value_traces``/``l3_nodes`` never leave the
        Runner: only the verbatim ``batch`` envelope reaches the injected
        host-side write forwarder.

        R3.0-012 (design §4.4): this is one of the two staged write entry
        points sharing the run-local :class:`CQWriteAdmission`.  The mutation
        is admitted before its durable intent exists, the forwarder runs
        outside the admission lock, and the outcome (``receipted`` /
        ``unknown`` / ``rejected``) is registered when it is determined, so the
        production handoff can atomically stop new writes and drain this one.
        """

        if not getattr(self, "_staged_decisions", False) or self.run is None:
            raise StagedSubmissionRejection(
                "staged_gate_closed", "staged decisions are not enabled for this run"
            )
        ticket = self._cq_write_admission.admit("staged_submit_modeling_batch")
        if ticket is None:
            if self._cq_write_admission.capturing:
                # R3.0-015 §3.3.2: the brief checkpoint capture barrier; the
                # write is recoverably deferred, not lost.
                raise StagedSubmissionRejection(
                    "staged_write_checkpoint_capture",
                    "a checkpoint save is capturing the run's write positions; "
                    "retry this staged write once the save finishes",
                )
            raise StagedSubmissionRejection(
                "staged_write_quiescing",
                "the run is in its read-only acceptance handoff period; new staged "
                "writes are recoverably rejected until production resumes by a new "
                "Delivery request",
            )
        try:
            result = self._handle_staged_submit_modeling_batch_open(args)
        except StagedSubmissionRejection as rejection:
            outcome = (
                "unknown"
                if rejection.data.get("reason_code") == "staged_batch_forward_unknown"
                else "rejected"
            )
            self._cq_write_admission.complete(ticket, outcome)
            raise
        except BaseException:  # noqa: BLE001 - the ticket must never leak in-flight
            self._cq_write_admission.complete(ticket, "rejected")
            raise
        self._cq_write_admission.complete(ticket, "receipted")
        # R3.0-015 S1: every confirmed staged batch (a durable receipt exists)
        # is a materialization_progress save point (design §3.1).  A save
        # failure never terminates the run; it lands in checkpoint evidence.
        self._save_checkpoint_after_trigger(
            CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="staged-receipt"
        )
        return result

    def _handle_staged_submit_modeling_batch_open(
        self, args: Mapping[str, Any]
    ) -> dict[str, Any]:
        """The admitted submission body; runs with a live admission ticket."""

        # R3.0-011 freeze ordering is enforced at this, the only platform write
        # R3.0-011 freeze ordering is enforced at this, the only platform write
        # channel: while the competency-question pool is unfrozen, Modeling
        # cannot materialize anything, so the owning sequence (slice questions
        # reviewed and frozen before neutral candidate modeling) holds without
        # relying on a terminal re-check.  Runs without the 011 selector are
        # unaffected.
        if getattr(self, "_competency_questions", False) and getattr(self, "_cq_freeze", None) is None:
            raise StagedSubmissionRejection(
                "cq_freeze_pending",
                "the competency-question pool is not frozen yet; batch materialization "
                "waits for the frozen public projection",
            )
        run_root = self.run.root
        unified = bool(getattr(self, "_unified_graph", False))
        paths = staged_decision_artifact_paths(run_root, unified=unified)
        gate_open = candidate_gate_open(run_root)
        conclusions: Mapping[str, Any] | None = None
        if paths["conclusions"].exists():
            try:
                conclusions = load_analysis_conclusions(paths["conclusions"])
            except StagedDecisionArtifactError as exc:
                if gate_open:
                    raise StagedSubmissionRejection(exc.reason_code, exc.detail) from exc
        unlock: Mapping[str, Any] | None = None
        unlock_issues: tuple = ()
        if paths["unlock"].exists():
            try:
                unlock = load_materialization_unlock(paths["unlock"])
            except StagedDecisionArtifactError as exc:
                unlock_issues = (StagedDecisionIssue(exc.reason_code, exc.detail, ""),)
            else:
                unlock_issues = validate_materialization_unlock(unlock, conclusions=conclusions)
        try:
            receipts = read_submission_receipts(run_root)
        except StagedDecisionArtifactError as exc:
            self._staged_gate_kill_switch(exc.reason_code, exc.detail)
            raise StagedSubmissionRejection("staged_unreconciled_batch", exc.detail) from exc
        issues = validate_staged_submission(
            args,
            gate_open=gate_open,
            conclusions=conclusions,
            unlock=unlock,
            unlock_issues=unlock_issues,
            receipts=receipts,
            unified=unified,
        )
        if issues:
            raise StagedSubmissionRejection(issues[0].reason_code, issues[0].detail)
        batch = args["batch"]
        plan_ref = args.get("plan_ref")
        if self._resume_imports is not None:
            # R3.0-015 S2 (design §5.2): the backend scopes idempotency keys
            # per Build Session, so an operation the origin chain already
            # completed would become a brand-new write in this session.  The
            # imported completion index refuses it here, before any intent is
            # persisted or forwarded (test plan M16).
            try:
                check_resume_submission(
                    self._resume_imports, batch, plan_ref=str(plan_ref or "")
                )
            except CheckpointError as exc:
                raise StagedSubmissionRejection(exc.reason_code, exc.detail) from exc
        projection: Mapping[str, Any] | None = None
        if unified:
            # R3.0-009 §9.2: before anything is persisted or forwarded the plan
            # is re-read, the approved projection is compared with the payloads
            # actually being forwarded, and the bindings are closed against the
            # current candidate revision and the current approvals.  Any
            # mismatch is a typed, fixable rejection with no partial write.
            plan, plan_issue = load_materialization_plan_ref(run_root, plan_ref)
            if plan_issue is not None or plan is None:
                raise StagedSubmissionRejection(
                    plan_issue.reason_code if plan_issue else "missing_candidate_reference",
                    plan_issue.detail if plan_issue else "materialization plan is missing",
                )
            projection = plan.get("projection") or {}
            plan_digest = str(plan.get("projection_digest") or "")
            # The three close checks run in the fixed §9.2 order and stop at
            # the first issue: a later validator must never be evaluated once
            # an earlier one produced the typed rejection the Agent acts on
            # (auth005: eagerly building the tuple let the approval validator
            # crash before the plan issue was returned).
            close_issue = unified_plan_issue(
                plan=plan,
                batch=batch,
                task_id=self.run.configuration.task.task_id,
            )
            if close_issue is None:
                close_issue = unified_candidate_issue(run_root, projection)
            approvals = (
                load_approvals(paths["approvals"])
                if paths["approvals"].is_file() and not paths["approvals"].is_symlink()
                else {}
            )
            if close_issue is None:
                close_issue = unified_approval_issue(approvals, projection)
            if close_issue is None and batch.get("mode") != "dry_run":
                # R3.0-014 (design §3.3): a dry-run keeps its baseline
                # behavior — stale or rejected translation history never
                # blocks it.  An apply must additionally clear the
                # current-plan translation approval recorded by this run's
                # current Coordinator, and a Runner-owned validated dry-run
                # proof of the exact same content at the submitted workspace
                # timepoint.
                close_issue = unified_translation_issue(
                    approvals,
                    plan_ref=str(plan_ref or ""),
                    projection_digest=plan_digest,
                    coordinator_id=self._multi_slice_role_ids().get("coordinator") or "",
                )
                if close_issue is None:
                    try:
                        close_issue = unified_dry_run_proof_issue(
                            run_root,
                            batch,
                            plan_ref=str(plan_ref or ""),
                            projection_digest=plan_digest,
                        )
                    except StagedDecisionArtifactError as exc:
                        raise StagedSubmissionRejection(
                            exc.reason_code, exc.detail
                        ) from exc
            if close_issue is not None:
                raise StagedSubmissionRejection(close_issue.reason_code, close_issue.detail)
        try:
            intents = read_submission_intents(run_root)
        except StagedDecisionArtifactError as exc:
            self._staged_gate_kill_switch(exc.reason_code, exc.detail)
            raise StagedSubmissionRejection("staged_unreconciled_batch", exc.detail) from exc
        if any(intent.get("status") == "unknown" for intent in intents):
            # An adjudication is still pending: no new submission may race it.
            raise StagedSubmissionRejection(
                "staged_unreconciled_batch", "an unknown-result intent is pending"
            )
        idempotency_key = batch["idempotency_key"]
        existing = [item for item in intents if item.get("idempotency_key") == idempotency_key]
        if existing:
            intent_record = existing[0]
            if intent_record.get("status") == "receipted":
                raise StagedSubmissionRejection(
                    "staged_conclusion_already_materialized",
                    f"idempotency key {idempotency_key} is already receipted",
                )
            ordinal = intent_record["ordinal"]
        else:
            ordinal = next_intent_ordinal(intents)
        # The Runner stamps the enum-command target on each enum trace so a
        # later ``update_enum_meaning`` without ``enum_value`` can close its
        # target against receipts (additive field, Runner-side only).
        stamped_traces = []
        for trace in args["value_traces"]:
            stamped = dict(trace)
            command_index = trace.get("command_index")
            items = batch.get("items") or []
            item = items[command_index] if isinstance(command_index, int) and 0 <= command_index < len(items) else None
            if (
                isinstance(item, Mapping)
                and item.get("command_kind") in ENUM_COMMAND_KINDS
                and not stamped.get("enum_target")
            ):
                payload = item.get("payload") or {}
                stamped["enum_target"] = payload.get("enum_meaning_id") or payload.get(
                    "enum_meaning_iri"
                )
            stamped_traces.append(stamped)
        intent = build_submission_intent(
            ordinal,
            idempotency_key=idempotency_key,
            client_batch_id=batch["client_batch_id"],
            session_id=batch["session_id"],
            mode=batch["mode"],
            commands=list(batch["items"]),
            value_traces=stamped_traces,
            l3_nodes=list(args["l3_nodes"]),
            plan_ref=plan_ref if unified else None,
            projection=projection if unified else None,
            decision_bindings=(
                list((projection or {}).get("decision_bindings") or []) if unified else None
            ),
        )
        write_submission_intent(run_root, intent)
        self._append_evidence(
            "staged-decisions",
            {
                "event": "submission-intent-written",
                "intent_ordinal": ordinal,
                "idempotency_key": idempotency_key,
                "mode": batch["mode"],
                "command_digests": list(intent["commands"]),
            },
        )
        forwarder = getattr(self, "staged_batch_forwarder", None)
        if not callable(forwarder):
            raise StagedSubmissionRejection(
                "staged_batch_forward_failed",
                "no host-side write forwarder is configured for this run",
            )
        try:
            result = forwarder(batch)
        except StagedBatchForwardUnknown as exc:
            write_submission_intent(run_root, mark_intent_status(intent, "unknown"))
            self._append_evidence(
                "staged-decisions",
                {
                    "event": "submission-forward-unknown",
                    "intent_ordinal": ordinal,
                    "idempotency_key": idempotency_key,
                    "detail": str(exc),
                },
            )
            self._staged_gate_kill_switch(
                "staged_unreconciled_batch",
                f"intent {ordinal} result is unknown and requires adjudication",
            )
            raise StagedSubmissionRejection("staged_batch_forward_unknown", str(exc)) from exc
        except StagedBatchForwardError as exc:
            raise StagedSubmissionRejection("staged_batch_forward_failed", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - typed re-wrap, evidence below
            raise StagedSubmissionRejection("staged_batch_forward_failed", str(exc)) from exc
        if not isinstance(result, Mapping) or not result.get("batch_id"):
            raise StagedSubmissionRejection(
                "staged_batch_forward_failed", "forwarder returned no batch identity"
            )
        batch_id = str(result["batch_id"])
        response_digest = str(
            result.get("response_digest")
            or f"sha256:{hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}"
        )
        receipt = build_submission_receipt(
            next_receipt_ordinal(read_submission_receipts(run_root)),
            intent,
            batch_id=batch_id,
            response_digest=response_digest,
        )
        write_submission_receipt(run_root, receipt)
        write_submission_intent(run_root, mark_intent_status(intent, "receipted"))
        self._append_evidence(
            "staged-decisions",
            {
                "event": "submission-receipt-written",
                "intent_ordinal": ordinal,
                "receipt_ordinal": receipt["ordinal"],
                "batch_id": batch_id,
                "mode": batch["mode"],
                **(
                    {
                        "plan_ref": receipt.get("plan_ref"),
                        "projection_digest": receipt.get("projection_digest"),
                    }
                    if receipt.get("schema_version") == UNIFIED_SUBMISSION_RECEIPT_SCHEMA
                    else {}
                ),
            },
        )
        if unified:
            # R3.0-014 (design §3.4): the Runner binds the platform Attempt —
            # the only accepted proof source — to the plan and receipt in its
            # own host evidence. A result without complete Attempt identity
            # yields no proof; the apply gate then fails closed on the missing
            # record instead of on a half-guessed one.
            proof = build_attempt_proof(
                intent_ordinal=ordinal,
                receipt_ordinal=receipt["ordinal"],
                plan_ref=str(plan_ref or ""),
                projection_digest=plan_digest,
                batch=batch,
                result=result,
                response_digest=response_digest,
            )
            if proof is not None:
                self._append_evidence("staged-decisions", proof)
        # ``ok`` states only that the capability wrote its receipt. The
        # platform Attempt facts below are what stage transitions judge on
        # (validated vs validation_failed vs applied); they are passed through
        # verbatim when the forwarder could identify them.
        response = {
            "ok": True,
            "batch_id": batch_id,
            "intent_ordinal": ordinal,
            "receipt_ordinal": receipt["ordinal"],
            "response_digest": response_digest,
        }
        for field in ("mode", "attempt_id", "attempt_status", "content_hash"):
            if result.get(field) is not None:
                response[field] = result.get(field)
        if isinstance(result.get("findings"), list):
            response["findings"] = result["findings"]
        return response

    def _handle_staged_associate_evidence(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """The Runner-private staged evidence-repost capability (R3.0-008B/#17).

        The staged batch channel materializes items the terminal retrieval gate
        scores by lineage, and the owner-authorized evidence backing those items
        is attached outside the batch.  This projection carries that one platform
        call; without it the gate is unsatisfiable whenever the owner answers
        after materialization (auth010 start4, item ``e80f85b1``).

        Evidence is not materialization, so this path deliberately carries none
        of the batch path's machinery: no durable intent, no receipt, no plan or
        approval chain, and no competency-question freeze ordering (which exists
        to sequence platform *writes* against the frozen question pool).  What it
        does keep is the write-integrity latch: while an unreconciled platform
        write awaits adjudication, no staged capability may add platform state.

        R3.0-012 (design §4.4): the second staged write entry point on the same
        run-local :class:`CQWriteAdmission`.  An unknown association outcome is
        recoverable by replay, but it still registers as an undetermined write:
        the handoff cannot publish over it.
        """

        if not getattr(self, "_staged_decisions", False) or self.run is None:
            raise StagedSubmissionRejection(
                "staged_gate_closed", "staged decisions are not enabled for this run"
            )
        ticket = self._cq_write_admission.admit("staged_associate_evidence")
        if ticket is None:
            if self._cq_write_admission.capturing:
                # R3.0-015 §3.3.2: same brief, reversible capture barrier.
                raise StagedSubmissionRejection(
                    "staged_write_checkpoint_capture",
                    "a checkpoint save is capturing the run's write positions; "
                    "retry this evidence association once the save finishes",
                )
            raise StagedSubmissionRejection(
                "staged_write_quiescing",
                "the run is in its read-only acceptance handoff period; new staged "
                "writes are recoverably rejected until production resumes by a new "
                "Delivery request",
            )
        try:
            result = self._handle_staged_associate_evidence_open(args)
        except StagedSubmissionRejection as rejection:
            outcome = (
                "unknown"
                if rejection.data.get("reason_code") == "staged_evidence_forward_unknown"
                else "rejected"
            )
            self._cq_write_admission.complete(ticket, outcome)
            raise
        except BaseException:  # noqa: BLE001 - the ticket must never leak in-flight
            self._cq_write_admission.complete(ticket, "rejected")
            raise
        self._cq_write_admission.complete(ticket, "associated")
        return result

    def _handle_staged_associate_evidence_open(
        self, args: Mapping[str, Any]
    ) -> dict[str, Any]:
        """The admitted evidence-association body; runs with a live ticket."""

        if getattr(self, "_staged_gate_killed", False):
            raise StagedSubmissionRejection(
                "staged_gate_closed",
                "staged write gate is closed pending reconciliation",
            )
        association = args.get("association")
        issue = _staged_evidence_issue(association)
        if issue is not None:
            raise StagedSubmissionRejection("staged_submit_schema_mismatch", issue)
        forwarder = getattr(self, "staged_evidence_forwarder", None)
        if not callable(forwarder):
            raise StagedSubmissionRejection(
                "staged_evidence_forward_failed",
                "no host-side evidence forwarder is configured for this run",
            )
        try:
            result = forwarder(dict(association))
        except StagedBatchForwardUnknown as exc:
            # An association the platform may or may not have persisted: the
            # (target, reference) uniqueness makes the identical call safe to
            # replay, so this stays a repairable rejection with no latch.
            raise StagedSubmissionRejection("staged_evidence_forward_unknown", str(exc)) from exc
        except StagedBatchForwardError as exc:
            raise StagedSubmissionRejection("staged_evidence_forward_failed", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - typed re-wrap, evidence below
            raise StagedSubmissionRejection("staged_evidence_forward_failed", str(exc)) from exc
        if not isinstance(result, Mapping) or not isinstance(result.get("items"), list):
            raise StagedSubmissionRejection(
                "staged_evidence_forward_failed",
                "the evidence forwarder returned no association rows",
            )
        self._append_evidence(
            "staged-decisions",
            {
                "event": "evidence-associated",
                "ontology_id": association["ontology_id"],
                "target_type": association["target_type"],
                "target_id": association["target_id"],
                "association_count": len(result["items"]),
            },
        )
        return dict(result)

    def _check_multi_slice_topology_gate(self) -> None:
        """R3.0-002: open the independent platform MCP gate only after a
        structurally complete topology decision (plus the scenario map whose
        bytes synthesize the open identity, design A.1).

        The check is mechanical existence/coverage only, fail-closed, and
        self-repairable: the run keeps waiting and the Coordinator receives a
        typed reason code instead of a terminal failure.
        """

        # ``getattr`` defaults keep this a no-op for runners constructed without
        # ``__init__`` (resumed-run doubles); the flags only ever turn on in
        # ``prepare`` for a multi-slice task.
        if (
            not getattr(self, "_multi_slice_workflow", False)
            or self.run is None
            or getattr(self, "_candidate_platform_gate", None) is None
            or getattr(self, "_multi_slice_gate_opened", False)
        ):
            return
        run_root = self.run.root
        decision_path = self._multi_slice_artifact_paths["topology_decision"]
        map_path = self._multi_slice_artifact_paths["scenario_map"]
        decision_rel = decision_path.relative_to(run_root).as_posix()
        map_rel = map_path.relative_to(run_root).as_posix()
        if not decision_path.exists() or decision_path.is_symlink():
            self._multi_slice_gate_reject(
                "topology_missing_artifact", decision_rel, "topology_missing_artifact"
            )
            return
        try:
            decision = load_topology_decision(decision_path)
            decision_digest = digest_file(decision_path)
        except (ScenarioMapArtifactError, OSError) as exc:
            code = getattr(exc, "reason_code", "topology_unparsable")
            self._multi_slice_gate_reject(code, decision_rel, f"{code}:unreadable")
            return
        issues = validate_topology_decision(decision)
        if issues:
            code = issues[0].reason_code
            self._multi_slice_gate_reject(code, decision_rel, f"{code}:{decision_digest}")
            return
        if not map_path.exists() or map_path.is_symlink():
            self._multi_slice_gate_reject("map_unparsable", map_rel, "map_missing")
            return
        try:
            scenario_map = load_scenario_map(map_path)
            map_digest = digest_file(map_path)
        except (ScenarioMapArtifactError, OSError) as exc:
            code = getattr(exc, "reason_code", "map_unparsable")
            self._multi_slice_gate_reject(code, map_rel, f"{code}:unreadable")
            return
        map_issues = validate_scenario_map(scenario_map)
        if map_issues:
            code = map_issues[0].reason_code
            self._multi_slice_gate_reject(code, map_rel, f"{code}:{map_digest}")
            return
        # R3.0-006 M3 second pass: the topology decision is validated before
        # the map exists (so a missing map never blocks structural repair
        # feedback), and once the map is loaded its slice list closes the
        # decision's ``ontology_plan`` slice references (the
        # ``validate_protection_iri_suggestions`` precedent).
        if TOPOLOGY_ONTOLOGY_PLAN_FIELD in decision:
            slice_ids = {
                item["slice_id"]
                for item in scenario_map["slices"]
                if isinstance(item, dict) and isinstance(item.get("slice_id"), str)
            }
            closure_issues = validate_topology_decision(decision, slice_ids=slice_ids)
            if closure_issues:
                code = closure_issues[0].reason_code
                self._multi_slice_gate_reject(
                    code, decision_rel, f"{code}:{decision_digest}"
                )
                return
        role_ids = self._multi_slice_role_ids()
        protocol_agent_id = role_ids.get("protocol", "protocol")
        identity = {
            "run_id": self.run.run_id,
            "protocol_agent_id": protocol_agent_id,
            "protocol_thread_id": self._formal_protocol_thread_id(protocol_agent_id),
            "original_delivery_id": f"r30002-topology:{self.run.run_id}",
            "candidate_revision": "1",
            "semantic_digest": map_digest,
            "candidate_digest": decision_digest,
        }
        try:
            self._candidate_platform_gate.open(identity)
        except (CandidatePlatformGateError, OSError) as exc:
            # Internal open failure: deterministic typed evidence, gate stays
            # closed, run continues (no terminal kill).
            self._multi_slice_gate_reject(
                "multi_slice_gate_open_failed",
                decision_rel,
                f"open-failed:{decision_digest}",
            )
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "gate-open-failed",
                    "classification": "runtime/infrastructure",
                    "detail": str(exc),
                },
            )
            return
        self._multi_slice_gate_opened = True
        self._append_evidence(
            "multi-slice-gate",
            {
                "event": "topology-decision-accepted",
                "gate_state": "open",
                "run_id": identity["run_id"],
                "original_delivery_id": identity["original_delivery_id"],
                "candidate_revision": identity["candidate_revision"],
                "semantic_digest": identity["semantic_digest"],
                "candidate_digest": identity["candidate_digest"],
            },
        )
        self._apply_multi_slice_ontology_plan(decision)

    def _apply_multi_slice_ontology_plan(self, decision: dict[str, Any]) -> None:
        """R3.0-006 M3: apply an accepted multi-Ontology plan after gate open.

        The first plan entry is the scope-precreated Ontology; the Runner
        creates the remaining N-1 Ontologies as the single scope writer, then
        delivers the full ontology-id set to the Protocol Agent.  Apply or
        delivery failures are recorded evidence (runtime/infrastructure) and
        never terminate the run; ``PlatformScope.apply_ontology_plan`` stays
        idempotent so a later resume (or a fresh run over the same scope)
        can retry.
        """

        plan = decision.get(TOPOLOGY_ONTOLOGY_PLAN_FIELD)
        if not plan:
            return
        scope = getattr(self, "scope", None)
        if scope is None:
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "ontology-plan-scope-unavailable",
                    "classification": "runtime/infrastructure",
                },
            )
            return
        try:
            ontology_ids = scope.apply_ontology_plan(plan)
        except Exception as exc:
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "ontology-plan-apply-failed",
                    "classification": "runtime/infrastructure",
                    "detail": str(exc),
                },
            )
            return
        self._append_evidence(
            "multi-slice-gate",
            {
                "event": "ontology-plan-applied",
                "ontology_ids": list(ontology_ids),
            },
        )
        try:
            self.run.protocol_context = scope.read_protocol_context()
        except Exception as exc:
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "ontology-plan-context-refresh-failed",
                    "classification": "runtime/infrastructure",
                    "detail": str(exc),
                },
            )
        self._deliver_multi_slice_ontology_ids(ontology_ids)

    def _deliver_multi_slice_ontology_ids(self, ontology_ids: list[str]) -> None:
        """Gate-open delivery of the full ontology-id set to Protocol (M3)."""

        if not self.run or not ontology_ids:
            return
        protocol = self._multi_slice_role_ids().get("protocol", "protocol")
        notice = {
            "schema_version": "r3-0-006-multi-slice-ontology-plan/v1",
            "run_id": self.run.run_id,
            "ontology_ids": list(ontology_ids),
            "source_of_truth": (
                "get_project_build_context lists every planned Ontology and is "
                "authoritative; this delivery is a supplementary notification."
            ),
        }
        delivery = RuntimeDelivery(
            sender_id="runner/multi-slice-gate",
            recipient_id=protocol,
            kind="multi-slice-ontology-plan",
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            expects_reply=False,
        )
        try:
            receipt = self.adapter.send_message(protocol, delivery)
        except Exception as exc:
            self._append_evidence(
                "multi-slice-gate",
                {
                    "event": "ontology-plan-delivery-failed",
                    "detail": str(exc),
                },
            )
            return
        self._append_evidence(
            "multi-slice-gate",
            {
                "event": "ontology-plan-delivered",
                "recipient": protocol,
                "ontology_ids": list(ontology_ids),
                "turn_id": getattr(receipt, "turn_id", None),
            },
        )

    def _observe_formal_candidate_delivery(self, delivery: Any) -> str | None:
        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None or not self.run:
            return None
        modeling, protocol = roles
        try:
            result = self._candidate_progress.observe_delivery(
                delivery,
                modeling_agent_id=modeling,
                protocol_agent_id=protocol,
                run_id=self.run.run_id,
                protocol_thread_id=self._formal_protocol_thread_id(protocol),
            )
        except FormalCandidateError:
            # Keep the failure at the modeling-quality/protocol boundary.  The
            # outer loop records terminal evidence and performs one cleanup;
            # pending state is never silently advanced on malformed envelopes.
            raise
        if result is not None:
            identity = self._candidate_progress.identity
            if (
                result in {"candidate", "revision"}
                and identity is not None
                and self._modeling_context_gate is not None
            ):
                self._modeling_context_gate.bind_candidate(
                    str(getattr(delivery, "delivery_id", "")), identity.candidate_digest
                )
            if result == "accepted" and identity is not None and self.acceptance is not None:
                try:
                    self.acceptance.register_accepted_candidate(
                        candidate_revision=identity.candidate_revision,
                        candidate_digest=identity.candidate_digest,
                        candidate=self._candidate_progress.candidate,
                    )
                except AcceptanceContractError as exc:
                    disposition = self._classify_registration_rejection(exc)
                    if disposition is None:
                        # I-class (mutation / internal binding): the R2.3-008
                        # start10 typed terminal failure with one cleanup pass.
                        self._latch_formal_candidate_failure(
                            "platform-contract",
                            "internal-invariant:accepted-candidate-registration-rejected",
                        )
                        raise TeamConfigurationError(
                            f"accepted candidate registration failed: {exc}"
                        ) from exc
                    # R2.3-009 A-class: an Agent-controllable registration
                    # defect is typed feedback plus a reopen for one strictly
                    # newer revision, never a run kill.  The receipt delivery
                    # is consumed by the reopen: no platform-gate open, no
                    # receipt-registered wakeup for the invalidated receipt.
                    self._handle_registration_rejected(delivery, identity, exc, disposition)
                    return None
            if self._candidate_platform_gate is not None:
                if result in {"candidate", "revision", "conflict"}:
                    self._candidate_platform_gate.close(
                        "candidate_pending_receipt"
                        if result in {"candidate", "revision"}
                        else "protocol_conflict",
                    )
                elif result == "accepted" and identity is not None:
                    if self._candidate_progress.paused or self._formal_failure_latched:
                        self._candidate_platform_gate.close("receipt_notification_suppressed")
                    else:
                        gate_identity = dict(identity.__dict__)
                        if self._is_r23003_modeling_run():
                            context_gate = self._modeling_context_gate
                            context_receipt = context_gate.receipt if context_gate is not None else None
                            if context_gate is None or context_receipt is None:
                                self._candidate_platform_gate.close(
                                    "modeling_context_receipt_missing"
                                )
                                raise TeamConfigurationError(
                                    "R2.3-003 candidate receipt lacks the Modeling context binding"
                                )
                            gate_identity["modeling_context"] = {
                                "project_id": context_gate.project_id,
                                "ontology_id": context_gate.ontology_id,
                                "workspace_version": context_receipt.workspace_version,
                                "context_receipt_digest": context_receipt.receipt_digest,
                                "response_digest": context_receipt.response_digest,
                                "call_receipt_digest": context_receipt.call_receipt_digest,
                            }
                        self._candidate_platform_gate.open(gate_identity)
                        self._notify_candidate_receipt_registered(
                            identity,
                            getattr(delivery, "delivery_id", None),
                        )
            self._append_evidence(
                "formal-candidate-progress",
                {
                    "event": result,
                    "state": self._candidate_progress.state,
                    "delivery_id": getattr(delivery, "delivery_id", None),
                    "original_delivery_id": identity.original_delivery_id if identity else None,
                    "candidate_revision": identity.candidate_revision if identity else None,
                    "candidate_digest": identity.candidate_digest if identity else None,
                    "semantic_digest": identity.semantic_digest if identity else None,
                },
            )
        return result

    def _register_stage_handoff_delivery_if_exact(self, delivery: Any) -> dict[str, str] | None:
        """Register only the exact Runner-built Prompt-E delivery, if present."""

        if not self._formal_coordination_enabled() or self.acceptance is None:
            return None
        role_ids = self._formal_coordination_role_ids()
        is_handoff_channel = (
            delivery.sender_id == role_ids["protocol"]
            and delivery.recipient_id == role_ids["coordinator"]
        )
        # Primary path: Protocol relays the opaque builder token (the
        # handoff_id) as delivery text.  The Runner pre-bound the handoff at
        # build time, so recording does not depend on the Agent re-serializing
        # the nested handoff JSON -- a short token cannot be mangled the way
        # ~7 KB of nested JSON can.
        if is_handoff_channel:
            token_record = self.acceptance.register_stage_handoff_delivery_by_token(
                delivery_id=delivery.delivery_id,
                text=delivery.text,
                sender_role="protocol",
                recipient_role="coordinator",
            )
            if token_record is not None:
                self._append_evidence("acceptance-stage-handoff", token_record)
                return token_record
        # Backward-compatible path: a full unchanged handoff JSON text still
        # classifies by canonical bytes.  This keeps older sends and the exact
        # "builder output was mutated" guard available when no token is relayed.
        try:
            is_builder_output = self.acceptance.classify_stage_handoff_delivery(delivery.text)
        except AcceptanceContractError as exc:
            raise TeamConfigurationError(str(exc)) from exc
        if not is_builder_output:
            return None
        if not is_handoff_channel:
            raise TeamConfigurationError("stage handoff delivery role binding is invalid")
        handoff_record = self.acceptance.register_stage_handoff_delivery(
            delivery_id=delivery.delivery_id,
            text=delivery.text,
            sender_role="protocol",
            recipient_role="coordinator",
        )
        self._append_evidence("acceptance-stage-handoff", handoff_record)
        return handoff_record

    # R2.3-009 B-class: candidate-channel protocol violations are mapped to a
    # typed feedback code before the run-level evidence is written.  The mapped
    # messages come from ``FormalCandidateProgress.observe_delivery`` gates;
    # every other malformed envelope falls back to ``candidate-envelope-invalid``.
    _FORMAL_CANDIDATE_VIOLATION_CODES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("formal candidate revision is not strictly newer", "revision-not-strictly-newer"),
        ("formal candidate revision reuses the invalidated candidate digest", "revision-digest-reused"),
        ("formal candidate Runtime attribution is invalid", "candidate-attribution-invalid"),
        ("formal candidate delivery ID is not bound", "candidate-delivery-id-not-bound"),
    )

    # R2.3-009 conservation contract (design §9 acceptance 2): the complete,
    # declarative registry of run-killing latch call sites.  Every entry is
    # either the single T3 run-fallback timeout, an I-class internal
    # invariant, or the one runtime/infrastructure dispatch failure.  The
    # conservation test in test_r23009_gate_conservation.py source-scans this
    # module and fails when ``_latch_formal_candidate_failure`` is called with
    # any (classification, reason) pair outside this registry.
    _FORMAL_FAILURE_LATCH_WHITELIST: ClassVar[frozenset[str]] = frozenset(
        {
            "platform-contract:internal-invariant:candidate-receipt-wakeup-delivery-id-missing",
            "platform-contract:internal-invariant:candidate-receipt-wakeup-notice-invalid",
            "platform-contract:internal-invariant:candidate-receipt-wakeup-turn-binding-missing",
            "platform-contract:internal-invariant:accepted-candidate-registration-rejected",
            "platform-contract:internal-invariant:turn-binding-missing",
            "runtime/infrastructure:candidate-receipt-wakeup-dispatch-failed",
            "collaboration/routing:run-fallback-timeout",
        }
    )

    def _formal_candidate_violation_code(self, exc: FormalCandidateError) -> str:
        text = str(exc)
        for prefix, code in self._FORMAL_CANDIDATE_VIOLATION_CODES:
            if prefix in text:
                return code
        return "candidate-envelope-invalid"

    @staticmethod
    def _formal_violation_delivery_envelope(delivery: Any) -> dict[str, Any]:
        return {
            "delivery_id": getattr(delivery, "delivery_id", None),
            "sender_id": getattr(delivery, "sender_id", None),
            "recipient_id": getattr(delivery, "recipient_id", None),
            "kind": getattr(delivery, "kind", None),
            "text": getattr(delivery, "text", None),
            "expects_reply": getattr(delivery, "expects_reply", None),
            "reply_to_delivery_id": getattr(delivery, "reply_to_delivery_id", None),
        }

    def _record_observed_issue(
        self,
        delivery: Any,
        *,
        issue_class: str,
        code: str,
        responsible_agent: str | None,
        detail: str,
    ) -> None:
        """Persist the offending delivery first, then record the typed issue."""

        envelope = self._formal_violation_delivery_envelope(delivery)
        # Evidence before judgment (defect-10 lesson): the original bytes are
        # preserved exactly as delivered even though the gate rejected them.
        self._append_evidence("deliveries", {"type": "delivery", **envelope})
        identity = self._candidate_progress.identity if self._candidate_progress is not None else None
        self._append_evidence(
            "observed-issue",
            {
                "issue_class": issue_class,
                "code": code,
                "responsible_agent": responsible_agent,
                "original_delivery_id": envelope["delivery_id"],
                "original_text": envelope["text"],
                "detail": detail,
                "candidate_revision": identity.candidate_revision if identity is not None else None,
            },
        )
        if isinstance(responsible_agent, str) and responsible_agent:
            self._last_responsible_agent = responsible_agent

    def _deliver_formal_feedback(
        self,
        *,
        issue_class: str,
        code: str,
        responsible_agent: str | None,
        original_delivery_id: str | None,
        detail: str,
        remediation: str,
    ) -> None:
        """Channel-2 typed conflict: readable Runtime feedback, never a run kill."""

        if not isinstance(responsible_agent, str) or not responsible_agent:
            return
        notice = {
            "conflict_code": code,
            "conflict_detail": detail,
            "original_delivery_id": original_delivery_id,
            "remediation": remediation,
        }
        delivery = RuntimeDelivery(
            sender_id="runner/candidate-gate",
            recipient_id=responsible_agent,
            kind="candidate-conflict",
            text=json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            expects_reply=False,
        )
        try:
            receipt = self.adapter.send_message(responsible_agent, delivery)
        except Exception as exc:
            # A dispatch failure of the feedback itself is recorded evidence;
            # it must not convert a B-class issue into a new run kill.
            self._append_evidence(
                "validation-feedback",
                {
                    "issue_class": issue_class,
                    "code": code,
                    "responsible_agent": responsible_agent,
                    "channel": 2,
                    "dispatch_failed": True,
                    "detail": str(exc),
                },
            )
            return
        key = (issue_class, code, responsible_agent)
        self._feedback_counts[key] = self._feedback_counts.get(key, 0) + 1
        self._last_responsible_agent = responsible_agent
        if self._feedback_counts[key] >= getattr(self, "_feedback_escalation_repeat", 3):
            self._escalate_repeated_feedback(issue_class, code, responsible_agent, detail)
        self._append_evidence(
            "validation-feedback",
            {
                "issue_class": issue_class,
                "code": code,
                "responsible_agent": responsible_agent,
                "channel": 2,
                "kind": "candidate-conflict",
                "original_delivery_id": original_delivery_id,
                "turn_id": getattr(receipt, "turn_id", None),
                "detail": detail,
                "remediation": remediation,
                "retry_allowed": True,
            },
        )

    def _handle_formal_candidate_violation(self, delivery: Any, exc: FormalCandidateError) -> None:
        """R2.3-009 B-class: a candidate artifact defect goes back to Modeling."""

        roles = self._formal_candidate_roles()
        modeling = roles[0] if roles is not None else None
        code = self._formal_candidate_violation_code(exc)
        self._record_observed_issue(
            delivery,
            issue_class="B",
            code=code,
            responsible_agent=modeling,
            detail=str(exc),
        )
        self._deliver_formal_feedback(
            issue_class="B",
            code=code,
            responsible_agent=modeling,
            original_delivery_id=getattr(delivery, "delivery_id", None),
            detail=str(exc),
            remediation=(
                "Send a complete, strictly newer formal candidate revision with a distinct "
                "candidate digest; the rejected delivery did not advance the formal gate."
            ),
        )
        self._ack_quarantined_delivery(getattr(delivery, "delivery_id", None))

    def _ack_quarantined_delivery(self, delivery_id: Any) -> None:
        """Acknowledge one quarantined delivery; a duplicate ack is only evidence."""

        if not isinstance(delivery_id, str):
            return
        try:
            self.transport.ack_delivery(delivery_id)
        except RoutingError as exc:
            self._append_evidence(
                "observed-issue",
                {
                    "issue_class": "B",
                    "code": "quarantine-ack-rejected",
                    "original_delivery_id": delivery_id,
                    "detail": str(exc),
                },
            )

    # R2.3-009 A-class registration-rejected responsibility table (design
    # section 3.A).  The acceptance carrier raises AcceptanceContractError;
    # Agent-controllable rejections carry a typed ``data`` payload from the
    # upgraded ``_error`` sites, while mutation/internal rejections stay opaque
    # and therefore I-class fatal.
    _REGISTRATION_REJECTION_PROTOCOL_SITES: ClassVar[frozenset[str]] = frozenset(
        {
            "replacement_revision_not_newer",
            "replacement_digest_reused",
            "replacement_payload_missing",
        }
    )
    _REGISTRATION_REJECTION_MODELING_SITES: ClassVar[frozenset[str]] = frozenset(
        {"ordinary_retrieval_plan_invalid"}
    )

    def _classify_registration_rejection(
        self, exc: AcceptanceContractError
    ) -> tuple[str, str, str] | None:
        """Return ``(issue_class, code, responsible_agent)`` or None for I-class."""

        roles = self._formal_candidate_roles()
        modeling = roles[0] if roles is not None else None
        protocol = roles[1] if roles is not None else None
        payload = getattr(exc, "data", None)
        reason = payload.get("reason") if isinstance(payload, Mapping) else None
        code = payload.get("code") if isinstance(payload, Mapping) else None
        if not isinstance(code, str) or not code:
            # Opaque rejections are mutation/internal invariants (I-class).
            return None
        if reason in self._REGISTRATION_REJECTION_MODELING_SITES:
            return ("A", code, modeling)
        if reason in self._REGISTRATION_REJECTION_PROTOCOL_SITES:
            return ("A", code, protocol)
        # A typed payload that is not mutation-classified defaults to the
        # Agent-visible defect going back to Modeling (the candidate artifact
        # owner) rather than killing the run.
        return ("A", code, modeling)

    def _handle_registration_rejected(
        self,
        delivery: Any,
        identity: Any,
        exc: AcceptanceContractError,
        disposition: tuple[str, str, str],
    ) -> None:
        issue_class, code, responsible_agent = disposition
        self._record_observed_issue(
            delivery,
            issue_class=issue_class,
            code=code,
            responsible_agent=responsible_agent,
            detail=str(exc),
        )
        reopened = bool(
            self._candidate_progress is not None
            and self._candidate_progress.reopen_after_registration_rejection()
        )
        invalidated = bool(
            self.acceptance is not None and self.acceptance.invalidate_accepted_candidate()
        )
        if self._candidate_platform_gate is not None and reopened:
            self._candidate_platform_gate.close("registration_rejected_reopen")
        self._append_evidence(
            "formal-candidate-progress",
            {
                "event": "registration-rejected-reopened",
                "state": self._candidate_progress.state if self._candidate_progress else None,
                "original_delivery_id": identity.original_delivery_id if identity else None,
                "candidate_revision": identity.candidate_revision if identity else None,
                "responsible_agent": responsible_agent,
                "acceptance_registration_invalidated": invalidated,
            },
        )
        self._deliver_formal_feedback(
            issue_class=issue_class,
            code=code,
            responsible_agent=responsible_agent,
            original_delivery_id=getattr(delivery, "delivery_id", None),
            detail=str(exc),
            remediation=(
                "The accepted-candidate registration was rejected. Send one strictly newer "
                "complete revision (distinct digest) so the run can re-register it."
            ),
        )

    def _handle_formal_response_violation(
        self,
        delivery: Any,
        *,
        protocol: str,
        exc: RoutingError,
    ) -> None:
        """R2.3-009 B-class: a rejected reopen is typed feedback to Protocol."""

        self._record_observed_issue(
            delivery,
            issue_class="B",
            code="formal-reply-slot-reopen-rejected",
            responsible_agent=protocol,
            detail=str(exc),
        )
        self._deliver_formal_feedback(
            issue_class="B",
            code="formal-reply-slot-reopen-rejected",
            responsible_agent=protocol,
            original_delivery_id=getattr(delivery, "delivery_id", None),
            detail=str(exc),
            remediation=(
                "The bound formal reply slot could not be reopened for the invalid response. "
                "Resend one canonical receipt or conflict bound to the pending candidate."
            ),
        )
        self._ack_quarantined_delivery(getattr(delivery, "delivery_id", None))

    def _latch_formal_candidate_failure(
        self, classification: str, reason: str, *, terminal_evidence: dict[str, Any] | None = None
    ) -> None:
        """Record one terminal failure before the foreground performs cleanup.

        R2.3-009 conservation contract: the only permitted call sites are the
        whitelisted ``_FORMAL_FAILURE_LATCH_WHITELIST`` entries (T3
        run-fallback, I-class internal invariants, and the one
        runtime/infrastructure dispatch failure). The conservation test
        source-scans this file and fails on any other call site.
        """

        if self._formal_failure_latched:
            return
        self._formal_failure_latched = True
        if self._candidate_progress is not None:
            self._candidate_progress.mark_terminal_failure()
        if self._candidate_platform_gate is not None:
            self._candidate_platform_gate.close("formal_candidate_terminal_failure")
        self._state(
            "TERMINAL_FAILURE_PENDING_CLEANUP",
            failure_category=classification,
            reason_code=reason,
        )
        self._append_evidence(
            "formal-candidate-terminal-failure",
            {
                "classification": classification,
                "complete_modeling_quality_result": False,
                "reason_code": reason,
                "cleanup_required": True,
            },
        )
        self.record_terminal_failure(classification, False, terminal_evidence=terminal_evidence)

    def _check_formal_candidate_progress(self) -> None:
        """R2.3-009 T1: a candidate deadline miss is a bounded nudge, not a kill."""

        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None:
            return
        if self._candidate_progress.terminal_failure_latched:
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return
        if not self._candidate_progress.check_deadline(now=self.monotonic_clock()):
            return
        self._nudge_formal_candidate()

    def _nudge_formal_candidate(self) -> None:
        progress = self._candidate_progress
        if progress is None:
            return
        self._maybe_redrive_formal_candidate()

    def _maybe_redrive_formal_candidate(self) -> None:
        roles = self._formal_candidate_roles()
        if roles is None or self._candidate_progress is None:
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return
        _, protocol = roles
        if not self._candidate_progress.redrive_ready(now=self.monotonic_clock()):
            # R2.3-009 T2: when the bounded nudge budget is spent without a
            # typed response, escalate cooperatively instead of killing.
            if self._candidate_progress.redrive_exhausted:
                self._escalate_candidate_stall()
            return
        attribution = self._candidate_progress.original_runtime_attribution
        if attribution is None:
            raise FormalCandidateError("formal candidate redrive has no original Runtime attribution")
        delivery = RuntimeDelivery(
            sender_id=attribution.sender_id,
            recipient_id=attribution.recipient_id,
            kind="candidate-redrive",
            text=attribution.text,
            delivery_id=attribution.delivery_id,
            expects_reply=attribution.expects_reply,
            reply_to_delivery_id=attribution.reply_to_delivery_id,
        )
        try:
            receipt = self.adapter.send_message(protocol, delivery)
        except Exception as exc:
            if self._provider_rejection_pending(protocol):
                # The Protocol role is parked in a provider wait; this redrive
                # tick defers (evidence only) and retries after recovery.
                self._append_evidence(
                    "formal-candidate-progress",
                    {
                        "event": "redrive-deferred",
                        "recipient_id": protocol,
                        "detail": str(exc)[:200],
                    },
                )
                return
            raise
        self._candidate_progress.mark_redrive_dispatch(
            receipt, now=self.monotonic_clock()
        )
        self._nudges_sent += 1
        self._append_evidence(
            "formal-candidate-progress",
            {
                "event": "redrive_sent",
                "recipient_id": protocol,
                "state": self._candidate_progress.state,
                "dispatch_mode": getattr(receipt, "mode", None),
                "turn_id": getattr(receipt, "turn_id", None),
                "redrive_count": (
                    self._candidate_progress.pending.redrive_count
                    if self._candidate_progress.pending is not None
                    else None
                ),
                "redrive_limit": getattr(self, "_candidate_redrive_limit", 3),
            },
        )

    def _open_cooperative_issue(
        self,
        *,
        reason_code: str,
        summary: str,
        error: str,
    ) -> bool:
        """Open one cooperative issue as the Coordinator (T2 escalation)."""

        if not self.run:
            return False
        ledger = self._issue_ledger()
        if ledger is not None and ledger.pending:
            return False
        report_issue = getattr(self.transport, "report_issue", None)
        if not callable(report_issue):
            self._append_evidence(
                "issue-escalation-unavailable",
                {"reason_code": reason_code, "detail": "issue escalation is unavailable"},
            )
            return False
        try:
            coordinator = self._issue_coordinator_id()
        except TeamConfigurationError:
            self._append_evidence(
                "issue-escalation-unavailable",
                {"reason_code": reason_code, "detail": "issue Coordinator is unavailable"},
            )
            return False
        try:
            issue = report_issue(
                coordinator,
                category="protocol_guidance",
                summary=summary,
                failing_operation="formal candidate progress",
                error=error,
                mutation_state="zero-mutation",
                requested_action="provide guidance so the run can resume",
            )
        except Exception as exc:
            self._append_evidence(
                "issue-escalation-unavailable",
                {"reason_code": reason_code, "detail": str(exc)},
            )
            return False
        self._issues_opened += 1
        self._append_evidence(
            "issue-escalation",
            {
                "reason_code": reason_code,
                "issue_id": issue.get("issue_id") if isinstance(issue, dict) else None,
                "reporter": "runner",
                "category": "protocol_guidance",
                "summary": summary,
            },
        )
        return True

    def _escalate_candidate_stall(self) -> None:
        """R2.3-009 T2: bounded nudges exhausted, escalate cooperatively once."""

        if getattr(self, "_stall_issue_opened", False):
            return
        progress = self._candidate_progress
        if progress is None:
            return
        redrive_count = progress.pending.redrive_count if progress.pending is not None else None
        opened = self._open_cooperative_issue(
            reason_code="candidate-stall",
            summary=(
                "formal candidate progress stalled: nudges exhausted without a "
                "valid Protocol receipt"
            ),
            error=(
                f"redrive_count={redrive_count}; "
                f"redrive_limit={getattr(self, '_candidate_redrive_limit', 3)}; "
                f"nudges_sent={getattr(self, '_nudges_sent', 0)}"
            ),
        )
        if opened:
            self._stall_issue_opened = True

    def _escalate_repeated_feedback(
        self, issue_class: str, code: str, responsible_agent: str, detail: str
    ) -> None:
        """R2.3-009 T2: the same typed feedback repeated too often escalates."""

        key = (issue_class, code, responsible_agent)
        if key in getattr(self, "_feedback_issue_keys", set()):
            return
        opened = self._open_cooperative_issue(
            reason_code="repeated-validation-feedback",
            summary=(
                f"typed feedback {issue_class}/{code} to {responsible_agent} repeated "
                f"{self._feedback_counts.get(key, 0)} times without repair"
            ),
            error=detail,
        )
        if opened:
            self._feedback_issue_keys = getattr(self, "_feedback_issue_keys", set()) | {key}

    def _track_issue_pending(self) -> None:
        """Keep the T3 issue-pending exclusion aligned with the issue ledger."""

        ledger = self._issue_ledger()
        pending = bool(ledger is not None and ledger.pending)
        clock = getattr(self, "monotonic_clock", None) or time.monotonic
        started = getattr(self, "_issue_pending_started", None)
        if pending and started is None:
            self._issue_pending_started = clock()
        elif not pending and started is not None:
            self._issue_pending_elapsed = (
                getattr(self, "_issue_pending_elapsed", 0.0) + max(0.0, clock() - started)
            )
            self._issue_pending_started = None

    # --- 2026-09-14 provider-recovery: observable provider waits ---------------

    def _consume_provider_waits(self) -> list[tuple[str, dict[str, Any]]]:
        """Drain newly observed provider waits from the Runtime, when supported."""

        reader = getattr(self.adapter, "consume_provider_waits", None)
        if not callable(reader):
            return []
        values = reader()
        return list(values) if isinstance(values, (list, tuple)) else []

    def _provider_wait_active(self, agent_id: str) -> bool:
        """Ask the Runtime whether the role is currently parked in a provider wait."""

        reader = getattr(self.adapter, "provider_wait_status", None)
        if callable(reader):
            return reader(agent_id) is not None
        agent = getattr(self.adapter, "agents", {}).get(agent_id)
        return getattr(agent, "provider_wait", None) is not None

    def _provider_wait_registry(self) -> dict[str, dict[str, Any]]:
        registry = getattr(self, "_provider_waits", None)
        if registry is None:
            registry = {}
            self._provider_waits = registry
        return registry

    def _provider_rejection_pending(self, agent_id: str) -> bool:
        """Whether a send failure to this role is explained by a pending wait.

        Used to distinguish the Runtime's bounded provider-wait rejection from
        real dispatch failures: a role parked in a wait must defer the delivery
        (typed, actionable) instead of tearing the whole run down.
        """

        return self._provider_wait_active(agent_id)

    def _live_provider_wait_agents(self) -> list[str]:
        """Profile roles currently parked in a provider wait, live from the Runtime."""

        if not self.run:
            return []
        try:
            agents = self.run.configuration.profile.agents
        except AttributeError:
            return []
        return [
            agent.agent_id
            for agent in agents
            if self._provider_wait_active(agent.agent_id)
        ]

    def _provider_wait_status_records(self) -> list[dict[str, Any]]:
        """One sanitized, actionable record per pending provider wait."""

        if not self.run:
            return []
        try:
            agents = self.run.configuration.profile.agents
        except AttributeError:
            return []
        coordinator = next(
            (
                agent.agent_id
                for agent in agents
                if agent.package.role == "coordinator"
            ),
            None,
        )
        host_route = coordinator is None or self._provider_wait_active(
            coordinator
        ) or self._coordinator_latched()
        records: list[dict[str, Any]] = []
        for agent in agents:
            reader = getattr(self.adapter, "provider_wait_status", None)
            wait = reader(agent.agent_id) if callable(reader) else None
            if not isinstance(wait, dict):
                continue
            records.append(
                {
                    "agent_id": agent.agent_id,
                    "role": agent.package.role,
                    "wait_id": wait.get("wait_id"),
                    "epoch": wait.get("epoch"),
                    "variant": wait.get("variant"),
                    "http_status": wait.get("http_status"),
                    "state": wait.get("state"),
                    "notifications": wait.get("notifications"),
                    "recovery_failures": wait.get("recovery_failures"),
                    "recovery_route": "host" if host_route or agent.agent_id == coordinator else "coordinator",
                    "action": (
                        "recover_provider"
                        if host_route or agent.agent_id == coordinator
                        else "issue_resolution then coordinator resume"
                    ),
                }
            )
        return records

    def _track_provider_wait(self) -> None:
        """Exclude provider-wait time from the run fallback clock.

        Overlap with a pending cooperative issue is not double counted: while
        the issue ledger is pending, the issue-pending exclusion already covers
        the same wall-clock window.
        """

        waits_active = bool(self._provider_wait_registry())
        ledger = self._issue_ledger()
        issue_pending = bool(ledger is not None and ledger.pending)
        clock = getattr(self, "monotonic_clock", None) or time.monotonic
        started = getattr(self, "_provider_wait_started", None)
        if waits_active and not issue_pending and started is None:
            self._provider_wait_started = clock()
        elif (not waits_active or issue_pending) and started is not None:
            self._provider_wait_elapsed = (
                getattr(self, "_provider_wait_elapsed", 0.0) + max(0.0, clock() - started)
            )
            self._provider_wait_started = None

    def _check_provider_waits(self, output: list[dict[str, Any]]) -> None:
        """Observe provider waits and route the first one to a healthy Coordinator."""

        if not self.run:
            return
        registry = self._provider_wait_registry()
        for agent_id, record in self._consume_provider_waits():
            if not isinstance(record, dict) or record.get("state") != "waiting":
                continue
            registry[agent_id] = dict(record)
            self._append_evidence("provider-wait", {"event": "observed", **record})
            output.append(
                {
                    "type": "provider-wait",
                    "agent_id": agent_id,
                    "role": record.get("role"),
                    "variant": record.get("variant"),
                    "wait_id": record.get("wait_id"),
                }
            )
        for agent_id in list(registry):
            if not self._provider_wait_active(agent_id):
                record = registry.pop(agent_id)
                self._append_evidence(
                    "provider-wait",
                    {"event": "cleared", "agent_id": agent_id, "wait_id": record.get("wait_id")},
                )
        if not registry:
            return
        ledger = self._issue_ledger()
        if ledger is None or ledger.pending:
            # Either the escalation capability is off (host recovery remains
            # available) or the pending issue already pauses the run clock.
            return
        for agent_id in sorted(registry):
            if self._report_provider_wait_issue(agent_id, registry[agent_id]):
                break

    def _report_provider_wait_issue(self, agent_id: str, record: dict[str, Any]) -> bool:
        """Report one runtime_recovery issue for a parked role; soft-fail safely."""

        assert self.run and self.transport
        coordinator = self._issue_coordinator_id()
        if agent_id == coordinator:
            # The Coordinator itself is blocked; only the host can recover it.
            return False
        if self._provider_wait_active(coordinator) or self._coordinator_latched():
            return False
        agent = getattr(self.adapter, "agents", {}).get(agent_id)
        thread_id = getattr(agent, "thread_id", None) if agent is not None else None
        mutation_state = (
            "unknown"
            if self._staged_resolution_blocker() is not None
            else "confirmed_no_write"
        )
        try:
            issue = self.transport.report_issue(
                agent_id,
                category="runtime_recovery",
                summary=(
                    f"model provider wait: role {record.get('role')} is parked on "
                    f"{record.get('variant')}; external quota/balance/outage recovery needed"
                ),
                failing_operation="model-provider turn",
                error=(
                    f"provider error variant {record.get('variant')}"
                    + (
                        f" http {record.get('http_status')}"
                        if record.get("http_status") is not None
                        else ""
                    )
                ),
                mutation_state=mutation_state,
                requested_action="pause",
                thread_id=thread_id,
            )
        except RoutingError:
            # Registry + evidence keep the wait observable and host-recoverable.
            self._append_evidence(
                "provider-wait",
                {"event": "issue-report-unavailable", "agent_id": agent_id},
            )
            return False
        self._append_evidence(
            "provider-wait",
            {"event": "issue-reported", "agent_id": agent_id, "issue_id": issue.get("issue_id")},
        )
        return True

    def _coordinator_latched(self) -> bool:
        if not self.run:
            return False
        try:
            coordinator = self._issue_coordinator_id()
        except TeamConfigurationError:
            return True
        agent = getattr(self.adapter, "agents", {}).get(coordinator)
        if agent is None:
            return True
        return (
            getattr(agent, "runtime_failure", None) is not None
            or getattr(agent, "state", None) == "failed"
        )

    # --- R3.0-011: competency-question direct channel -------------------------

    @staticmethod
    def _cq_directory(root: Path, relative: str) -> Path:
        directory = root / relative
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        return directory

    def _cq_agent_id(self) -> str | None:
        if not self.run or not self._competency_questions:
            return None
        return next(
            (
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == COMPETENCY_QUESTION_ROLE
            ),
            None,
        )

    def _cq_selector_required(self) -> None:
        if not self._competency_questions:
            raise CQContractError(
                "cq_selector_incompatible",
                "this run did not select competency_question_acceptance",
                obj="competency_question_acceptance",
                retry="restart the run with the R3.0-011 Task selector enabled",
            )

    def _cq_next_ordinal(self, directory: Path, prefix: str) -> int:
        existing = [item.name for item in directory.glob(f"{prefix}-*.json")]
        return len(existing) + 1

    def _deliver_to_cq(self, kind: str, payload: dict[str, Any]) -> None:
        """Wake the CQ role on the Runner-owned direct channel (no transport)."""

        agent_id = self._cq_agent_id()
        if agent_id is None:
            raise CQContractError(
                "cq_selector_incompatible",
                "no competency-question Agent is configured for this run",
                obj="competency-question",
                retry="load the R3.0-011 Profile",
            )
        try:
            receipt = self.adapter.send_message(
                agent_id,
                RuntimeDelivery(
                    sender_id="user/outer",
                    recipient_id=agent_id,
                    kind=kind,
                    text=canonical_json_bytes(payload).decode("utf-8"),
                ),
            )
        except Exception as exc:
            if self._provider_rejection_pending(agent_id):
                # Typed, nonfatal: the foreground CQ branch turns this into a
                # cq-input-rejected envelope and keeps reading the next line.
                raise CQContractError(
                    "cq_waiting_provider",
                    "the competency-question role is parked in a provider wait",
                    obj="competency-question",
                    retry="send recover_provider for that role, then resend this input",
                ) from exc
            raise
        self._append_evidence(
            "competency-questions",
            {
                "event": "direct-delivery",
                "kind": kind,
                "recipient_id": agent_id,
                "turn_id": getattr(receipt, "turn_id", None),
            },
        )

    def _cq_check_scenario_map_slices(self) -> None:
        """Map-only approved-slice handoff to the CQ role (design §3.G3.3).

        Runs on every drain tick BEFORE any topology dependency: a validated
        Coordinator scenario map is what makes a slice set approved, so the
        CQ role learns the approved slices (with their existing public
        business scope) and can start slice questions before the topology
        decision, the neutral candidate stage, or the freeze exist.  The
        topology gate and its write protection are untouched.  A failed
        notification resets the fingerprint, so the next drain retries it even
        after the topology gate has opened.  Non-011 runs return untouched.
        """

        if self.run is None or not self._competency_questions:
            return
        map_path = self.run.root / "scenario-map" / "scenario-map.json"
        if not map_path.is_file() or map_path.is_symlink():
            return
        try:
            scenario_map = load_scenario_map(map_path)
            map_digest = digest_file(map_path)
        except (ScenarioMapArtifactError, OSError):
            return
        if validate_scenario_map(scenario_map):
            return
        slices = [
            {
                "slice_id": item["slice_id"],
                "name": item["name"],
                "scope": item["scope"],
                "owner": item["owner"],
                "status": item["status"],
            }
            for item in scenario_map["slices"]
            if isinstance(item, dict)
        ]
        fingerprint = content_digest({"map_digest": map_digest, "slices": slices})
        if getattr(self, "_cq_approved_slices_fingerprint", None) == fingerprint:
            return
        self._cq_approved_slices_fingerprint = fingerprint
        # A delivery failure resets the fingerprint and is recorded evidence,
        # so the next drain tick retries (design §3.G3.3 / T0).
        self._cq_deliver_approved_slices(slices, map_digest)

    def _cq_deliver_approved_slices(self, slices: list[dict[str, Any]], map_digest: str) -> None:
        """Deliver ``cq-slices-approved`` for one newly approved slice set.

        The payload carries protocol facts plus the validated map's existing
        per-slice business fields (``slice_id``/``name``/``scope``/``owner``/
        ``status`` -- no new semantic schema) so the CQ role knows what each
        approved slice covers.  It never carries question or answer text,
        hidden material, or any production workspace content.
        """

        if self.run is None or not self._competency_questions:
            return
        try:
            self._deliver_to_cq(
                "cq-slices-approved",
                {
                    "slices": slices,
                    "slice_ids": [item["slice_id"] for item in slices],
                    "scenario_map_digest": map_digest,
                    "run_id": self.run.run_id,
                },
            )
        except Exception as exc:
            # A failed notification is recorded evidence only: the map is
            # already validated, and the next drain tick retries it (T0 -- no
            # gate event, no run kill).
            self._cq_approved_slices_fingerprint = None
            self._append_evidence(
                "competency-questions",
                {
                    "event": "cq-slices-approved-delivery-failed",
                    "detail": str(exc),
                },
            )

    def _publish_cq_question_draft(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Runner-private ``cq_publish_question_draft`` capability handler.

        The CQ role has no writable artifact mount for drafts: every draft is
        saved here as an immutable, append-only version, a review snapshot is
        published for Delivery, and a ``cq-review-request`` wait window opens.
        A rejected draft rejects only this call (design §3.2).
        """

        self._cq_selector_required()
        document = validate_draft_document(dict(arguments.get("draft")))
        self._cq_assert_not_exposed_hidden(document["questions"])
        private_dir = self._cq_directories["private"]
        reviews_dir = self._cq_directories["reviews"]
        ordinal = self._cq_next_ordinal(private_dir, "draft")
        draft_path = private_dir / f"draft-{ordinal:04d}.json"
        draft_path.write_bytes(canonical_json_bytes(document))
        os.chmod(draft_path, 0o440)
        self._cq_review_sequence += 1
        review_id = f"cq-review-{self._cq_review_sequence:04d}"
        snapshot = {
            "schema_version": "r3-0-011-cq-review-snapshot/v1",
            "review_id": review_id,
            "phase": document["phase"],
            "draft_ref": draft_path.relative_to(self.run.root).as_posix(),
            "content_version": self._cq_review_sequence + 1,
            "content_digest": document["content_digest"],
            "question_ids": [question["question_id"] for question in document["questions"]],
            "advisory_count_feedback": advisory_question_count_feedback(document["questions"]),
        }
        snapshot_path = reviews_dir / f"{review_id}.json"
        snapshot_path.write_bytes(canonical_json_bytes(snapshot))
        os.chmod(snapshot_path, 0o440)
        live = dict(snapshot)
        live["questions"] = document["questions"]
        live["draft_path"] = str(draft_path)
        self._cq_drafts[review_id] = live
        self._cq_draft_order.append(review_id)
        self._cq_phase = document["phase"]
        now = self.monotonic_clock()
        self._cq_wait_windows.open_window("cq-review-request", now)
        self._cq_wait_windows.close_window("cq-interview-wait", now)
        self._append_evidence(
            "cq-review-request",
            {
                "review_id": review_id,
                "phase": document["phase"],
                "draft_ref": snapshot["draft_ref"],
                "content_digest": document["content_digest"],
                "question_ids": snapshot["question_ids"],
            },
        )
        return {
            "ok": True,
            "review_id": review_id,
            "phase": document["phase"],
            "draft_ref": snapshot["draft_ref"],
            "content_digest": document["content_digest"],
            "status": "awaiting_review",
        }

    def _cq_review_snapshot(self, review_id: str) -> dict[str, Any]:
        self._cq_selector_required()
        snapshot = self._cq_drafts.get(review_id)
        if snapshot is None:
            raise CQContractError(
                "cq_review_stale",
                f"unknown review_id {review_id}",
                obj="cq_review",
                phase=getattr(self, "_cq_phase", None),
                retry="read the current review snapshot path from the cq-review-request evidence",
            )
        return snapshot

    def _handle_cq_interview(self, message: dict[str, Any]) -> None:
        """One strict ``cq_interview`` outer input; never routed via transport."""

        self._cq_selector_required()
        allowed = {"action", "text", "wait_for_draft"}
        if set(message) - allowed:
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_interview envelope has invalid fields",
                obj="cq_interview",
                retry=f"send only {sorted(allowed)}",
            )
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_interview text must be a non-empty string",
                obj="cq_interview",
                retry="send the interview input as text",
            )
        self._cq_interview_sequence += 1
        ordinal = self._cq_interview_sequence
        private_dir = self._cq_directories["private"]
        interview_path = private_dir / f"interview-{ordinal:04d}.json"
        payload = {
            "schema_version": "r3-0-011-cq-interview/v1",
            "ordinal": ordinal,
            "text": text,
        }
        interview_path.write_bytes(canonical_json_bytes(payload))
        os.chmod(interview_path, 0o440)
        now = self.monotonic_clock()
        if message.get("wait_for_draft", True) is True:
            self._cq_wait_windows.open_window("cq-interview-wait", now)
        self._append_evidence(
            "cq-interview",
            {
                "ordinal": ordinal,
                "interview_ref": interview_path.relative_to(self.run.root).as_posix(),
                "wait_window_open": self._cq_wait_windows.has_open_window,
            },
        )
        # R3.0-015 S1: the published interview is an early saveable stage
        # result; a checkpoint failure does not block CQ delivery.
        self._save_checkpoint_after_trigger(
            CHECKPOINT_KIND_SCENARIO_MAPPED,
            trigger="cq-interview",
        )
        self._deliver_to_cq(
            "cq-interview",
            {
                "ordinal": ordinal,
                "interview_ref": interview_path.relative_to(self.run.root).as_posix(),
                "text": text,
            },
        )

    def _handle_cq_review(self, message: dict[str, Any]) -> None:
        """One strict ``cq_review`` outer decision, bound to a draft version."""

        self._cq_selector_required()
        review_id = message.get("review_id")
        if not isinstance(review_id, str) or not review_id:
            raise CQContractError(
                "cq_review_stale",
                "cq_review requires the review_id of the current snapshot",
                obj="cq_review",
                retry="send the review_id exactly as published",
            )
        snapshot = self._cq_review_snapshot(review_id)
        # ``action`` belongs to the outer envelope, never to the review schema.
        decision = validate_review_decision(
            {key: value for key, value in message.items() if key != "action"},
            draft=snapshot,
        )
        self._cq_decisions.setdefault(review_id, []).append(decision)
        reviews_dir = self._cq_directories["reviews"]
        ordinal = self._cq_next_ordinal(reviews_dir, "decision")
        record = {
            "schema_version": "r3-0-011-cq-review-decision/v1",
            "review_id": review_id,
            "decision": decision,
            "decision_digest": content_digest(decision),
        }
        decision_path = reviews_dir / f"decision-{ordinal:04d}.json"
        decision_path.write_bytes(canonical_json_bytes(record))
        os.chmod(decision_path, 0o440)
        now = self.monotonic_clock()
        self._cq_wait_windows.close_window("cq-review-request", now)
        if snapshot["phase"] == "panorama-review":
            self._cq_phase = "awaiting-slices"
            self._write_cq_public_projection(review_id)
        elif snapshot["phase"] == "slice-review":
            self._cq_phase = "slice-draft"
            # The decision is persisted above, so the appended projection is
            # derived from the decided slice draft (design §3.G3.2).
            self._write_cq_public_projection(review_id)
        self._append_evidence(
            "cq-review-decision",
            {
                "review_id": review_id,
                "phase": snapshot["phase"],
                "decision_ref": decision_path.relative_to(self.run.root).as_posix(),
                "decision": decision["decision"],
                "question_id": decision["question_id"],
            },
        )
        self._deliver_to_cq(
            "cq-review-decision",
            {
                "review_id": review_id,
                "decision_ref": decision_path.relative_to(self.run.root).as_posix(),
                "decision_digest": record["decision_digest"],
                "decision": decision["decision"],
                "question_id": decision["question_id"],
            },
        )

    def _cq_effective_panorama_questions(self) -> list[dict[str, Any]]:
        """Panorama questions after the recorded user decisions are applied.

        ``modify``/``supplement`` replace or add the reviewed question content,
        ``delete`` removes it; only panorama-review drafts participate, so slice
        questions never reach the pre-slice projection.
        """

        questions: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for review_id in self._cq_draft_order:
            draft = self._cq_drafts[review_id]
            if draft.get("phase") != "panorama-review":
                continue
            for question in draft["questions"]:
                if question["question_id"] not in questions:
                    order.append(question["question_id"])
                questions[question["question_id"]] = dict(question)
            for decision in self._cq_decisions.get(review_id, []):
                question_id = decision["question_id"]
                if decision["decision"] == "delete":
                    questions.pop(question_id, None)
                    if question_id in order:
                        order.remove(question_id)
                elif decision["decision"] in {"modify", "supplement"}:
                    replacement = decision.get("modified_question")
                    if replacement is None:
                        continue
                    if question_id not in questions:
                        order.append(question_id)
                    questions[question_id] = dict(replacement)
        return [questions[question_id] for question_id in order if question_id in questions]

    def _write_cq_public_projection(self, review_id: str) -> dict[str, Any]:
        """Project only the approved public questions into the public directory.

        Called after the first panorama-review decision and after every
        slice-review decision; the production roles read the highest-ordinal
        projection file through their read-only bind.  The pool is derived
        from the single ``_cq_pool_questions`` replay (panorama then slice), so
        this projection never re-implements a parallel decision replay: during
        the panorama phase the pool has no slice drafts yet and the shape stays
        exactly the pre-slice one (``slice_question_ids`` empty).
        """

        public_dir = self._cq_directories["public"]
        ordinal = self._cq_next_ordinal(public_dir, "public-projection")
        pool, order = self._cq_pool_questions()
        panorama_ids = [
            question["question_id"]
            for question in pool
            if question["scope"]["kind"] == "panorama"
        ]
        slice_ids = [
            question["question_id"]
            for question in pool
            if question["scope"]["kind"] == "slice"
        ]
        draft = self._cq_drafts.get(review_id, {})
        decisions = self._cq_decisions.get(review_id, [])
        last_decision = decisions[-1] if decisions else None
        snapshot = freeze_question_pool(
            {
                "schema_version": CQ_FREEZE_SCHEMA,
                "batch_id": f"panorama-{ordinal:04d}",
                "material_digest": self.run.baseline_hash or "",
                "panorama_question_ids": panorama_ids,
                "slice_question_ids": slice_ids,
                "ordering": order,
                "questions": pool,
                "review_binding": {
                    "review_id": review_id,
                    "review_content_version": draft.get("content_version", 1),
                    "decision_digest": review_decision_digest(last_decision or {"review_id": review_id}),
                },
            }
        )
        return self._cq_append_public_projection(
            public_projection(snapshot), snapshot["review_binding"]
        )

    def _cq_append_public_projection(
        self, projection: dict[str, Any], review_binding: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Write one append-only public projection and record its exposure.

        Shared tail of the panorama/slice review write and the freeze write,
        so the highest-ordinal projection is always the last pool event.  The
        ordinal is computed here, immediately before the write, so the file
        name and the evidence entry always agree.
        """

        public_dir = self._cq_directories["public"]
        ordinal = self._cq_next_ordinal(public_dir, "public-projection")
        path = public_dir / f"public-projection-{ordinal:04d}.json"
        write_public_projection(path, projection)
        self._cq_projection_written = True
        # D2: this write *is* the exposure event.  Every projected question is
        # now readable by the production roles, so the Runner records the
        # exposure here and it can never be undone by a later hidden proposal.
        # Exposure is monotone first-exposure provenance, so later writes that
        # re-publish an already-shown public set record nothing new.
        first_exposure = {
            question["question_id"]
            for question in projection["questions"]
            if question["question_id"] not in self._cq_exposed
        }
        if first_exposure:
            self._cq_record_exposure(first_exposure)
        self._append_evidence(
            "cq-public-projection",
            {
                "projection_ref": path.relative_to(self.run.root).as_posix(),
                "projection_digest": projection["projection_digest"],
                "public_question_ids": [
                    question["question_id"] for question in projection["questions"]
                ],
            },
        )
        self._cq_projection_consistency_feedback()
        return projection

    def _cq_projection_consistency_feedback(self) -> None:
        """Recoverable projection/scenario-map consistency feedback (T0).

        After a projection write, when the Coordinator scenario map already
        exists, ``verify_cq_scenario_map_projection`` compares the map's
        cross-slice section against the published projection.  A mismatch is
        author-fixable: the Runner records the evidence (inside the verify
        call) and sends Coordinator one typed continuation notice; the run is
        never killed and either repair (map update or re-projection) continues.
        """

        if self.run is None:
            return
        map_path = self.run.root / "scenario-map" / "scenario-map.json"
        if not map_path.is_file():
            return
        issues = self.verify_cq_scenario_map_projection()
        if not issues:
            return
        coordinator = self._multi_slice_role_ids().get("coordinator")
        if not isinstance(coordinator, str) or not coordinator:
            return
        notice = {
            "schema_version": "r3-0-011-cq-projection-feedback/v1",
            "run_id": self.run.run_id,
            "reason_code": "cq_projection_scenario_map_mismatch",
            "issues": [
                {key: value for key, value in issue.items() if key != "question"}
                for issue in issues
            ],
            "remediation": (
                "The scenario-map cross_slice_competency_questions section does "
                "not match the published public projection. Update the map to "
                "reference approved public projection questions exactly, or "
                "republish the projection; either repair lets the run continue."
            ),
        }
        delivery = RuntimeDelivery(
            sender_id="runner/competency-questions",
            recipient_id=coordinator,
            kind="cq-projection-feedback",
            text=json.dumps(
                notice, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            expects_reply=False,
        )
        try:
            self.adapter.send_message(coordinator, delivery)
        except Exception as exc:
            # A dispatch failure of the feedback itself is recorded evidence
            # only; it must never kill the run or block self-repair (T0).
            self._append_evidence(
                "competency-questions",
                {
                    "event": "cq-projection-feedback-dispatch-failed",
                    "detail": str(exc),
                },
            )

    def _cq_production_roles(self) -> list[str]:
        """Roles allowed to read the CQ public projection (design §3.2)."""

        production_roles = {"coordinator", "modeling", "protocol"}
        if self.run is None:
            return sorted(production_roles)
        return sorted(
            {
                agent.package.role
                for agent in self.run.configuration.profile.agents
                if agent.package.role in production_roles
            }
        )

    def _cq_record_exposure(self, question_ids: set[str]) -> None:
        """Record one exposure event permanently (D2 / design §5)."""

        roles = self._cq_production_roles()
        for question_id in sorted(question_ids):
            known = set(self._cq_exposed.setdefault(question_id, []))
            self._cq_exposed[question_id] = sorted(known | set(roles))
        self._append_evidence(
            "cq-exposure",
            {
                "event": "question-exposed-to-production",
                "question_ids": sorted(question_ids),
                "roles": roles,
                "reason_code": "permanently_public",
            },
        )

    def _cq_merge_exposure_evidence(self) -> None:
        """Re-apply recorded exposure from run evidence (D2 / design §5).

        ``self._cq_exposed`` is the Runner's pool-external provenance and is
        never cleared by a freeze.  Reading the ``cq-exposure`` evidence file
        back before the freeze keeps the permanently-public rule and the
        non-blind labeling working across a recovered Runner process, without
        adding any field to the frozen snapshot schema.
        """

        if self.run is None:
            return
        evidence_path = self.run.root / "evidence" / "cq-exposure.jsonl"
        if not evidence_path.is_file():
            return
        try:
            provenance = read_exposure_evidence(evidence_path)
        except CQContractError:
            return
        for question_id, roles in provenance["exposure"].items():
            known = set(self._cq_exposed.setdefault(question_id, []))
            self._cq_exposed[question_id] = sorted(known | set(roles))

    def _cq_assert_not_exposed_hidden(self, questions: list[dict[str, Any]]) -> None:
        """Reject any hidden proposal for a question already shown (D2 / §5)."""

        for question in questions:
            if question.get("proposed_visibility") != "hidden":
                continue
            question_id = question.get("question_id")
            if question_id in self._cq_exposed:
                raise CQContractError(
                    "cq_hidden_exposed",
                    f"question {question_id} was already shown to a production role",
                    obj="cq_publish_question_draft",
                    phase=getattr(self, "_cq_phase", None),
                    retry="keep the question public; a shown question is permanently public",
                )

    def _cq_public_projection(self) -> dict[str, Any]:
        public_dir = self._cq_directories.get("public")
        if public_dir is None:
            raise CQContractError(
                "cq_public_projection_missing",
                "this run has no competency-question public directory",
                obj="cq_public_projection",
                retry="enable the R3.0-011 selector",
            )
        projections = sorted(public_dir.glob("public-projection-*.json"))
        if not projections:
            raise CQContractError(
                "cq_public_projection_missing",
                "no public projection has been published for the production roles",
                obj="cq_public_projection",
                phase=getattr(self, "_cq_phase", None),
                retry="complete the panorama review first",
            )
        return json.loads(projections[-1].read_text(encoding="utf-8"))

    def verify_cq_scenario_map_projection(self) -> list[dict[str, Any]]:
        """Runner-side external consistency check (Round 4 follow-up (c)).

        Compares the Coordinator-maintained ``cross_slice_competency_questions``
        section against the published public projection.  The map entry shape is
        untouched (three fields, no provenance); the check lives entirely
        Runner-side and only records IDs, not question text.
        """

        map_path = self.run.root / "scenario-map" / "scenario-map.json"
        if not map_path.is_file():
            return [
                {
                    "reason_code": "cq_public_projection_missing",
                    "object": "scenario-map.json",
                    "note": "the scenario map has not been maintained yet",
                }
            ]
        scenario_map = json.loads(map_path.read_text(encoding="utf-8"))
        entries = (scenario_map or {}).get("cross_slice_competency_questions", [])
        issues = cross_slice_projection_issues(entries, self._cq_public_projection())
        if issues:
            self._append_evidence(
                "cq-projection-consistency",
                {
                    "event": "cross-slice-projection-mismatch",
                    "issues": [
                        {key: value for key, value in issue.items() if key != "question"}
                        for issue in issues
                    ],
                },
            )
        else:
            self._append_evidence(
                "cq-projection-consistency",
                {"event": "cross-slice-projection-consistent", "entry_count": len(entries)},
            )
        return issues

    def freeze_cq_question_pool(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append the immutable freeze snapshot under ``competency-questions/frozen``."""

        self._cq_selector_required()
        snapshot = freeze_question_pool(payload)
        frozen_dir = self._cq_directories["frozen"]
        ordinal = self._cq_next_ordinal(frozen_dir, "freeze")
        path = frozen_dir / f"freeze-{ordinal:04d}.json"
        path.write_bytes(canonical_json_bytes(snapshot))
        os.chmod(path, 0o440)
        self._cq_freeze = snapshot
        self._cq_phase = "frozen"
        self._append_evidence(
            "cq-freeze",
            {
                "freeze_ref": path.relative_to(self.run.root).as_posix(),
                "batch_id": snapshot["batch_id"],
                "snapshot_digest": snapshot["snapshot_digest"],
                "public_question_ids": [
                    question["question_id"]
                    for question in snapshot["questions"]
                    if question["visibility"] == "public"
                ],
                "hidden_question_count": sum(
                    1
                    for question in snapshot["questions"]
                    if question["visibility"] == "hidden"
                ),
            },
        )
        # The last projection is written from the frozen snapshot itself, so
        # the published public set always equals the frozen public set
        # (design §3.G3.2); hidden questions never reach the public directory.
        self._cq_append_public_projection(
            public_projection(snapshot), snapshot["review_binding"]
        )
        # R3.0-015 S1: a published freeze is the automatic cq_frozen save
        # point (design §3.1); a save failure never kills the run.
        self._save_checkpoint_after_trigger(
            CHECKPOINT_KIND_CQ_FROZEN,
            trigger="cq-freeze",
            scope_refs={"freeze_id": snapshot["batch_id"]},
        )
        return snapshot

    def _cq_pool_questions(self) -> tuple[list[dict[str, Any]], list[str]]:
        """Effective pool (panorama then slice) with its draft order.

        Panorama questions come from ``_cq_effective_panorama_questions``; slice
        questions are the decided slice drafts in publication order.
        """

        panorama = [dict(question) for question in self._cq_effective_panorama_questions()]
        panorama_ids = [question["question_id"] for question in panorama]
        slice_questions: dict[str, dict[str, Any]] = {}
        order = list(panorama_ids)
        for review_id in self._cq_draft_order:
            draft = self._cq_drafts[review_id]
            if draft.get("phase") != "slice-review":
                continue
            for question in draft["questions"]:
                if question["question_id"] in slice_questions:
                    continue
                if question["question_id"] not in order:
                    order.append(question["question_id"])
                slice_questions[question["question_id"]] = dict(question)
            for decision in self._cq_decisions.get(review_id, []):
                question_id = decision["question_id"]
                if decision["decision"] == "delete":
                    slice_questions.pop(question_id, None)
                    if question_id in order:
                        order.remove(question_id)
                elif decision["decision"] in {"modify", "supplement"}:
                    replacement = decision.get("modified_question")
                    if replacement is None:
                        continue
                    if question_id not in slice_questions and question_id not in order:
                        order.append(question_id)
                    slice_questions[question_id] = dict(replacement)
        return panorama + [slice_questions[key] for key in order if key in slice_questions], order

    def _cq_undecided_question_ids(self, questions: list[dict[str, Any]]) -> list[str]:
        """Question ids in ``questions`` that no recorded user decision covers."""

        decided = {
            decision["question_id"]
            for decisions in self._cq_decisions.values()
            for decision in decisions
        }
        return [
            question["question_id"]
            for question in questions
            if question["question_id"] not in decided
        ]

    def handle_cq_freeze(self, message: dict[str, Any]) -> dict[str, Any]:
        """Host-only ``cq_freeze``: Delivery freezes the user-approved pool.

        This is the production trigger for ``competency-questions/frozen``.  It
        is deliberately a Delivery-host action on the same recoverable CQ
        admission branch as ``cq_review`` (design §3.2 / Round 1 F2): the CQ and
        every other Agent may propose and answer, but only the user's recorded
        decisions plus this host action can close the pool, so D1 (no
        self-approval by Agents) holds.  The freeze is append-only, digest
        bound, and re-runs ``reload_frozen_pool`` style tamper checks on read.
        """

        self._cq_selector_required()
        allowed = {"action"}
        if set(message) - allowed:
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_freeze envelope has invalid fields",
                obj="cq_freeze",
                phase=getattr(self, "_cq_phase", None),
                retry=f"send only {sorted(allowed)}",
            )
        questions, order = self._cq_pool_questions()
        if not questions:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                "no reviewed competency question exists to freeze",
                obj="cq_freeze",
                phase=getattr(self, "_cq_phase", None),
                retry="publish and review at least one question first",
            )
        undecided = self._cq_undecided_question_ids(questions)
        if undecided:
            raise CQContractError(
                "cq_review_stale",
                "the pool still contains questions without a recorded user decision",
                obj="cq_freeze",
                phase=getattr(self, "_cq_phase", None),
                retry="record a cq_review decision for every published question first",
            )
        last_review_id = self._cq_draft_order[-1] if self._cq_draft_order else ""
        decisions = self._cq_decisions.get(last_review_id, [])
        last_decision = decisions[-1] if decisions else None
        payload = {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": f"cq-batch-{self._cq_next_ordinal(self._cq_directories['frozen'], 'freeze'):04d}",
            "material_digest": self.run.baseline_hash or "",
            "panorama_question_ids": [
                question["question_id"]
                for question in questions
                if question["scope"]["kind"] == "panorama"
            ],
            "slice_question_ids": [
                question["question_id"]
                for question in questions
                if question["scope"]["kind"] == "slice"
            ],
            "ordering": order,
            "questions": questions,
            "review_binding": {
                "review_id": last_review_id,
                "review_content_version": self._cq_review_sequence + 1,
                "decision_digest": review_decision_digest(
                    last_decision or {"review_id": last_review_id}
                ),
            },
        }
        # D2: the Runner stamps the exposure it recorded at projection time, so
        # ``freeze_question_pool`` rejects any shown question proposed hidden
        # with ``cq_hidden_exposed`` instead of silently regrouping it.  The
        # in-memory ``_cq_exposed`` state is pool-external and survives the
        # freeze on purpose: it is re-read from ``evidence/cq-exposure.jsonl``
        # here so a recovered Runner keeps enforcing it, and so later batches
        # still carry pool-level provenance for the non-blind label.  The frozen
        # snapshot schema itself never grows an exposure field (Round 2 R4);
        # ``freeze_question_pool`` pops the stamp it uses for this gate.
        self._cq_merge_exposure_evidence()
        for question in payload["questions"]:
            exposed = self._cq_exposed.get(question["question_id"])
            if exposed:
                question["_exposed_to"] = list(exposed)
        return self.freeze_cq_question_pool(payload)

    def _cq_production_readiness(self) -> dict[str, Any]:
        """Host-verified production handoff readiness (R3.0-012 design §3.1).

        Role transport statuses are *recorded inputs*, never the gate itself:
        ``ready`` and ``pending_writes`` are derived from what the host can
        verify on its own -- every declared apply closed by a durable receipt,
        no unknown-result intent, no unreconciled write latch, and no mutation
        still inside the run-local write admission.  A ``blocked`` production
        role is admitted only insofar as its write state is determined here;
        an idle-but-valid lease or a terminal advisory issue is invisible to
        this gate and never blocks on its own.  CQ settlement and any
        independent acceptance verdict are explicitly not part of readiness.
        """

        production_roles = {"coordinator", "modeling", "protocol"}
        results = getattr(self.transport, "results", {}) if self.transport else {}
        pending: list[str] = []
        blocked: list[str] = []
        role_states: dict[str, str] = {}
        for agent in self.run.configuration.profile.agents:
            if agent.package.role not in production_roles:
                continue
            status = getattr(results.get(agent.agent_id), "status", None)
            role_states[agent.agent_id] = status if isinstance(status, str) else "active"
            if status == "blocked":
                blocked.append(agent.agent_id)
            elif status != "completed":
                pending.append(agent.agent_id)
        admission = self._cq_write_admission.snapshot()
        unknown_writes: list[dict[str, Any]] = []
        try:
            intents = read_submission_intents(self.run.root)
            receipts = read_submission_receipts(self.run.root)
        except StagedDecisionArtifactError as exc:
            unknown_writes.append({"source": "staged-artifacts", "detail": exc.detail})
            intents = []
            receipts = []
        unknown_writes.extend(
            {
                "source": "intent",
                "intent_ordinal": intent.get("ordinal"),
                "idempotency_key": intent.get("idempotency_key"),
            }
            for intent in intents
            if intent.get("status") == "unknown"
        )
        if getattr(self, "_staged_gate_killed", False):
            unknown_writes.append(
                {
                    "source": "reconciliation-latch",
                    "detail": "the staged write gate is closed pending adjudication",
                }
            )
        unknown_writes.extend(
            {"source": "admission", "kind": record.get("kind"), "ticket": record.get("ticket")}
            for record in admission["records"]
            if record.get("outcome") == "unknown"
        )
        pending_writes = bool(admission["in_flight"]) or bool(unknown_writes)
        return {
            "ready": not pending and not pending_writes,
            # Derived pair only (design §3.1): the evidence fields above are
            # what a handoff consumer must re-verify, never these booleans.
            "pending_writes": pending_writes,
            "production_roles": sorted(production_roles),
            "pending_agents": pending,
            "blocked_agents": blocked,
            "role_states": role_states,
            "write_phase": admission["phase"],
            "in_flight_writes": admission["in_flight"],
            "unknown_writes": unknown_writes,
            "applied_batches": [
                {
                    "intent_ordinal": receipt.get("intent_ordinal"),
                    "batch_id": receipt.get("batch_id"),
                    "mode": receipt.get("mode"),
                    "response_digest": receipt.get("response_digest"),
                }
                for receipt in receipts
            ],
            "not_applied": [
                {"source": "admission", "kind": record.get("kind"), "ticket": record.get("ticket")}
                for record in admission["records"]
                if record.get("outcome") == "rejected"
            ],
            "checks": [
                "delivery",
                "quiescence",
                "write-determinism",
                "apply-closure",
                "scope-binding",
            ],
        }

    def _handle_cq_handoff_complete(self, message: dict[str, Any]) -> dict[str, Any]:
        """Host-only ``cq_handoff_complete``: release the CQ terminal report."""

        self._cq_selector_required()
        allowed = {"action", "freeze_id", "freeze_digest", "delivery_binding"}
        if set(message) - allowed:
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_handoff_complete envelope has invalid fields",
                obj="cq_handoff_complete",
                phase=getattr(self, "_cq_phase", None),
                retry=f"send only {sorted(allowed)}",
            )
        now = self.monotonic_clock()
        if self._cq_freeze is None:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                "no frozen question pool exists for this run",
                obj="cq_handoff_complete",
                phase=getattr(self, "_cq_phase", None),
                retry="freeze the question pool before the production handoff",
            )
        if message.get("freeze_id") != self._cq_freeze["batch_id"] or message.get(
            "freeze_digest"
        ) != self._cq_freeze["snapshot_digest"]:
            raise CQContractError(
                "cq_review_stale",
                "cq_handoff_complete does not match the current freeze snapshot",
                obj="cq_handoff_complete",
                phase="frozen",
                retry="send the current freeze id and snapshot digest",
            )
        if self._cq_handoff_complete:
            # T1-10/T1-14 analog: an already-released handoff only acknowledges
            # a duplicate complete.  The immutable handoff file and its events
            # are never rewritten, and the acknowledgment carries no new state.
            return {
                "ok": True,
                "freeze_id": self._cq_freeze["batch_id"],
                "idempotent": True,
            }
        readiness = self._cq_production_readiness()
        if readiness["pending_agents"]:
            # Production has not settled.  No phase change happens here, so
            # production keeps working and Delivery can retry this request --
            # quiescing over unsettled roles would wedge their final writes.
            self._cq_wait_windows.open_window("cq-handoff-request", now)
            raise CQContractError(
                "cq_batch_scope_unauthorized",
                "production roles have not settled their deliveries",
                obj="cq_handoff_complete",
                phase="frozen",
                retry="retry after the pending production agents report",
            )
        # R3.0-012 design §4.4 atomic admission: stop admitting new staged
        # writes first, then drain the already-admitted ones *outside* the
        # admission lock (no lock is held across a network wait).  The scene
        # stays quiesced when a write is undetermined -- preserving it is the
        # point, and the rejection is recoverable by adjudication and a retry.
        self._cq_write_admission.begin_quiescing()
        self._cq_acceptance_phase = "quiescing"
        self._cq_write_admission.wait_until_drained(_CQ_WRITE_DRAIN_TIMEOUT_SECONDS)
        now = self.monotonic_clock()
        readiness = self._cq_production_readiness()
        if not readiness["ready"]:
            self._cq_wait_windows.open_window("cq-handoff-request", now)
            raise CQContractError(
                "cq_unknown_write_pending",
                "staged platform writes are in flight or their results are unknown",
                obj="cq_handoff_complete",
                phase="frozen",
                retry="adjudicate or replay the unknown staged writes, then resend",
            )
        # Forced external consistency check at the handoff boundary (design
        # §3.G3.5): a scenario map whose cross-slice section does not match the
        # published projection must be repaired (map update or re-projection)
        # before the production handoff is released.  Runs without a map (no
        # multi-slice workflow) and explicitly-empty coverage gaps stay on the
        # recorded-feedback path; the typed rejection is retryable, so a real
        # mismatch stays author-fixable rather than terminal.
        map_path = self.run.root / "scenario-map" / "scenario-map.json"
        if map_path.is_file():
            issues = [
                issue
                for issue in self.verify_cq_scenario_map_projection()
                if not issue.get("coverage_gap")
            ]
            if issues:
                raise CQContractError(
                    "cq_projection_scenario_map_mismatch",
                    "the scenario map and the published public projection disagree",
                    obj="cq_handoff_complete",
                    phase="frozen",
                    retry=(
                        "align scenario-map cross_slice_competency_questions with the "
                        "published public projection (or republish the projection) and resend"
                    ),
                )
        self._cq_write_admission.enter_read_only()
        # The published record reflects the read-only state at publication
        # time, not the quiescing snapshot the gate above checked against.
        readiness = self._cq_production_readiness()
        handoff = self._cq_publish_production_handoff(readiness, message)
        self._cq_handoff_complete = True
        self._cq_wait_windows.close_window("cq-handoff-request", now)
        if self._acceptance_target == "cq_semantic":
            # R3.0-012 (design §4.5): the same transition that closes the
            # handoff request opens the acceptance wait.  Only the cq_semantic
            # scope holds the terminal report for the completion channel; a
            # full_joint run keeps the R3.0-011 in-run terminal path unchanged.
            self._cq_acceptance_phase = "acceptance_pending"
            self._cq_wait_windows.open_window("cq-acceptance-wait", now)
        else:
            # full_joint: the read-only period ends with the publish and the
            # acceptance lifecycle (with its wait window) never applies.
            self._cq_acceptance_phase = None
        self._append_evidence(
            "cq-handoff-complete",
            {
                "freeze_id": self._cq_freeze["batch_id"],
                "freeze_digest": self._cq_freeze["snapshot_digest"],
                "delivery_binding": message.get("delivery_binding"),
                "readiness": readiness,
                "handoff_digest": handoff["handoff_digest"],
                "acceptance_attempt_id": handoff["acceptance_attempt_id"],
                "report_directory": handoff["report_directory"],
                "write_phase": "read-only",
                "acceptance_phase": self._cq_acceptance_phase,
            },
        )
        return {
            "ok": True,
            "freeze_id": self._cq_freeze["batch_id"],
            "handoff_digest": handoff["handoff_digest"],
            "acceptance_attempt_id": handoff["acceptance_attempt_id"],
            "report_directory": handoff["report_directory"],
            "acceptance_phase": self._cq_acceptance_phase,
        }

    def _cq_scope_binding(self) -> dict[str, Any]:
        """Project identity plus the authorized Ontology set (design §3.1).

        The scope object exists only after ``start``; prepared-but-not-started
        runs fall back to the frozen ``run.scope`` mapping.  The handoff records
        what the host can see -- checking this set against the model binding and
        the actual delivery for equality is the ``cq-acceptance`` consumer's
        job, never a boolean here.
        """

        scope_object = getattr(self, "scope", None)
        ontology_ids = getattr(scope_object, "ontology_ids", None)
        project_id = getattr(scope_object, "project_id", None)
        if not isinstance(ontology_ids, list):
            ontology_ids = None
        run_scope = getattr(self.run, "scope", None)
        if isinstance(run_scope, Mapping):
            if not ontology_ids and isinstance(run_scope.get("ontology_ids"), list):
                ontology_ids = list(run_scope["ontology_ids"])
            if not project_id:
                project_id = run_scope.get("project_id")
        return {
            "project_id": project_id if isinstance(project_id, str) else "",
            "ontology_ids": [item for item in (ontology_ids or []) if isinstance(item, str)],
        }

    def _cq_next_acceptance_attempt(self, batch_id: str) -> dict[str, str]:
        """Allocate the unique report-attempt directory for this handoff.

        R3.0-012 design §4.5: report roots stay ``acceptance-v3/reports/
        <batch_id>/`` and every handoff allocates the next free
        ``attempt-NNNN`` subdirectory, so a re-acceptance of the same batch can
        never reuse -- let alone overwrite -- a published attempt.
        """

        reports = self._cq_directories["reports"] / batch_id
        prefix = "attempt-"
        existing: set[str] = set()
        if reports.is_dir():
            for entry in reports.iterdir():
                suffix = entry.name[len(prefix) :]
                if (
                    entry.is_dir()
                    and entry.name.startswith(prefix)
                    and suffix.isdigit()
                    and len(entry.name) == len(prefix) + 4
                ):
                    existing.add(entry.name)
        ordinal = 1
        while f"{prefix}{ordinal:04d}" in existing:
            ordinal += 1
        return {
            "acceptance_attempt_id": f"{prefix}{ordinal:04d}",
            "report_directory": f"acceptance-v3/reports/{batch_id}/{prefix}{ordinal:04d}",
        }

    def _cq_publish_production_handoff(
        self, readiness: dict[str, Any], message: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Write the immutable, host-verified production handoff (§3.1/§4.4).

        ``ready``/``pending_writes`` are printed from the verified evidence
        fields, so this file can never be a booleans-only handoff, and the
        ``O_EXCL`` first write makes a replacement attempt a typed conflict
        instead of an overwrite.  The digest covers the exact written bytes and
        is recorded in the event and the allocated attempt, never self-embedded.
        """

        batch_id = self._cq_freeze["batch_id"]
        attempt = self._cq_next_acceptance_attempt(batch_id)
        contract_path = self.run.root / "acceptance-v3" / "run-contract.json"
        contract_digest = (
            hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if contract_path.is_file() and not contract_path.is_symlink()
            else ""
        )
        payload = {
            "schema_version": "r3-0-012-production-handoff/v1",
            "run_id": self.run.run_id,
            "task_id": self.run.configuration.task.task_id,
            "profile_id": self.run.configuration.profile.profile_id,
            "run_contract_digest": contract_digest,
            "freeze_id": batch_id,
            "freeze_digest": self._cq_freeze["snapshot_digest"],
            "delivery_binding": message.get("delivery_binding"),
            "acceptance_target": self._acceptance_target,
            "scope_binding": self._cq_scope_binding(),
            "role_states": readiness["role_states"],
            "applied_batches": readiness["applied_batches"],
            "not_applied": readiness["not_applied"],
            "unknown_writes": readiness["unknown_writes"],
            "write_phase": readiness["write_phase"],
            "joint_checklist": {
                "state": "pending",
                "note": "the 008B joint checklist is not a cq_semantic "
                "precondition; its state stays recorded for the full_joint path",
            },
            # Derived pair only: re-verify the evidence fields above, never
            # these booleans (design §3.1 rejection contract).
            "ready": readiness["ready"],
            "pending_writes": readiness["pending_writes"],
            "acceptance_attempt_id": attempt["acceptance_attempt_id"],
            "batch_id": batch_id,
            "report_directory": attempt["report_directory"],
        }
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
        path = self.run.root / "acceptance-v3" / "production-handoff.json"
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            raise CQContractError(
                "cq_handoff_immutable",
                "a production handoff is already published for this run",
                obj="production-handoff",
                phase="frozen",
                retry="a re-acceptance must allocate a new attempt via a new handoff request",
            ) from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        handoff_digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        self._cq_acceptance_attempt = {
            **attempt,
            "batch_id": batch_id,
            "freeze_digest": self._cq_freeze["snapshot_digest"],
            "handoff_digest": handoff_digest,
        }
        # R3.0-015 S1: a published handoff is the automatic production_handoff
        # save point (design §3.1).  The admission phase is read-only here, so
        # the capture barrier is a no-op and the write state is settled.
        self._save_checkpoint_after_trigger(
            CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            trigger="production-handoff",
            scope_refs={
                "freeze_id": batch_id,
                "acceptance_attempt_id": attempt["acceptance_attempt_id"],
            },
        )
        return {**attempt, "handoff_digest": handoff_digest}

    def _handle_cq_acceptance_complete(self, message: dict[str, Any]) -> dict[str, Any]:
        """Host-only ``cq_acceptance_complete``: end the acceptance wait (§4.5).

        Delivery sends the digest-and-verdict summary after the independent
        ``cq-acceptance`` process exits.  The Runner re-reads the registered
        attempt's retained ``batch-report.json``, re-verifies the digest and
        recomputes the aggregate verdict itself -- the envelope is never
        trusted for any of them -- and only then releases the terminal report.
        Full, partial, and failure reports all complete the handoff the same
        way; a normal wrap-up never requires CQ to be all green.
        """

        self._cq_selector_required()
        if set(message) != CQ_ACCEPTANCE_COMPLETE_FIELDS:
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_acceptance_complete envelope has invalid fields",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry=f"send exactly the fields {sorted(CQ_ACCEPTANCE_COMPLETE_FIELDS)}",
            )
        if self._acceptance_target != "cq_semantic":
            # The completion channel exists for the cq_semantic scope; a
            # full_joint run keeps the R3.0-011 in-run terminal path.
            raise CQContractError(
                "cq_selector_incompatible",
                "cq_acceptance_complete applies only to a cq_semantic run",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="this run closes acceptance through the in-run terminal path",
            )
        if self._cq_freeze is None:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                "no frozen question pool exists for this run",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="freeze the question pool before the acceptance handoff",
            )
        if message.get("run_id") != self.run.run_id or message.get(
            "freeze_id"
        ) != self._cq_freeze["batch_id"] or message.get("freeze_digest") != self._cq_freeze[
            "snapshot_digest"
        ]:
            raise CQContractError(
                "cq_review_stale",
                "cq_acceptance_complete does not match this run's current freeze",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="send the current run id, freeze id and snapshot digest",
            )
        attempt = self._cq_acceptance_attempt
        if attempt is None or message.get("batch_id") != attempt["batch_id"] or message.get(
            "acceptance_attempt_id"
        ) != attempt["acceptance_attempt_id"]:
            # No pending attempt (a handoff that never published) or a stale
            # one: a re-acceptance must be requested as a new handoff, never
            # replayed against the directory of an old attempt.
            raise CQContractError(
                "cq_review_stale",
                "cq_acceptance_complete does not match the current acceptance attempt",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="request a new production handoff to allocate the current attempt",
            )
        if self._cq_acceptance_phase == "acceptance_complete":
            # T1-14: an exactly identical duplicate only confirms; a divergent
            # copy is a mismatch against the retained result, never a second
            # completion or a rewrite of the accepted one.
            result = self._cq_acceptance_result or {}
            if message.get("report_digest") == result.get("report_digest"):
                return {
                    "ok": True,
                    "freeze_id": self._cq_freeze["batch_id"],
                    "acceptance_attempt_id": attempt["acceptance_attempt_id"],
                    "cq_verdict": result.get("cq_verdict"),
                    "report_digest": result.get("report_digest"),
                    "idempotent": True,
                }
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "a duplicate completion disagrees with the accepted report",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="resend the digest of the accepted attempt report",
            )
        report_path = (
            self.run.root / attempt["report_directory"] / "batch-report.json"
        )
        if not report_path.is_file() or report_path.is_symlink():
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "the registered attempt report is missing",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="let the cq-acceptance process write the attempt report, then resend",
            )
        report_bytes = report_path.read_bytes()
        report_digest = f"sha256:{hashlib.sha256(report_bytes).hexdigest()}"
        if message.get("report_digest") != report_digest:
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "cq_acceptance_complete report_digest does not match the retained report",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="recompute the digest from the attempt's batch-report.json",
            )
        try:
            report = json.loads(report_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "the retained attempt report is not readable JSON",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="let the cq-acceptance process rewrite the attempt report",
            ) from exc
        if not isinstance(report, dict) or (
            report.get("run_id") != self.run.run_id
            or report.get("batch_id") != attempt["batch_id"]
            or report.get("freeze_digest") != attempt["freeze_digest"]
        ):
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "the retained report is not bound to this run's current attempt",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry="the attempt report must bind this run, batch and freeze",
            )
        cq_verdict = batch_report_acceptance_verdict(report)
        if message.get("cq_verdict") != cq_verdict or cq_verdict not in CQ_ACCEPTANCE_VERDICTS:
            # The aggregate verdict is recomputed from the verified report;
            # the envelope's copy is a consistency check, never the source.
            raise CQContractError(
                "cq_acceptance_report_mismatch",
                "cq_acceptance_complete cq_verdict disagrees with the retained report",
                obj="cq_acceptance_complete",
                phase=self._cq_acceptance_phase,
                retry=f"send the recomputed aggregate verdict ({cq_verdict})",
            )
        now = self.monotonic_clock()
        self._cq_acceptance_phase = "acceptance_complete"
        self._cq_acceptance_result = {
            "acceptance_attempt_id": attempt["acceptance_attempt_id"],
            "report_directory": attempt["report_directory"],
            "report_digest": report_digest,
            "cq_verdict": cq_verdict,
        }
        self._cq_wait_windows.close_window("cq-acceptance-wait", now)
        self._append_evidence(
            "cq-acceptance-complete",
            {
                "freeze_id": self._cq_freeze["batch_id"],
                "freeze_digest": self._cq_freeze["snapshot_digest"],
                "batch_id": attempt["batch_id"],
                "acceptance_attempt_id": attempt["acceptance_attempt_id"],
                "report_directory": attempt["report_directory"],
                "report_digest": report_digest,
                "cq_verdict": cq_verdict,
                "acceptance_phase": self._cq_acceptance_phase,
            },
        )
        return {
            "ok": True,
            "freeze_id": self._cq_freeze["batch_id"],
            "acceptance_attempt_id": attempt["acceptance_attempt_id"],
            "cq_verdict": cq_verdict,
            "report_digest": report_digest,
        }

    def _deliver_cq_terminal_rejection(self, agent_id: str, reason: dict[str, Any]) -> None:
        """Push the typed premature-terminal continuation to the CQ session.

        The payload carries only protocol facts (object, phase, reason code,
        retry guidance) -- never hidden question or answer text.
        """

        try:
            self.adapter.send_message(
                agent_id,
                RuntimeDelivery(
                    sender_id="runner/competency-questions",
                    recipient_id=agent_id,
                    kind="cq-terminal-rejected",
                    text=canonical_json_bytes(reason).decode("utf-8"),
                ),
            )
        except Exception:  # noqa: BLE001 - a failed wake must not mask the rejection
            self._append_evidence(
                "cq-terminal-report",
                {"event": "rejection-delivery-failed", "reason_code": reason.get("reason_code")},
            )
            return

    def handle_cq_outer_input(self, message: dict[str, Any]) -> dict[str, Any]:
        """Admit one ``cq_interview``/``cq_review``/``cq_freeze``/``cq_handoff_complete`` input.

        This is the public entry the foreground CLI/FIFO path calls *before*
        the existing fatal ``receive_outer`` boundary.  Expected input errors
        raise :class:`CQContractError` (a ``ValueError`` that is not a
        ``TeamConfigurationError``) carrying ``object``/``phase``/``reason
        code``/``retry`` data; persistence or Runtime delivery failures keep
        their existing fatal behavior.  Never carries hidden question or
        answer text in the acknowledgement.
        """

        action = message.get("action")
        if action == "cq_interview":
            self._handle_cq_interview(message)
            return {
                "type": "cq-interview-accepted",
                "action": action,
                "ordinal": self._cq_interview_sequence,
                "phase": self._cq_phase,
                "wait_window_open": self._cq_wait_windows.has_open_window,
            }
        if action == "cq_review":
            review_id = message.get("review_id")
            if not isinstance(review_id, str) or not review_id:
                raise CQContractError(
                    "cq_review_stale",
                    "cq_review requires the review_id of the current snapshot",
                    obj="cq_review",
                    retry="send the review_id exactly as published",
                )
            self._handle_cq_review(message)
            decisions = self._cq_decisions.get(review_id, [])
            decision = decisions[-1] if decisions else None
            return {
                "type": "cq-review-accepted",
                "action": action,
                "review_id": review_id,
                "phase": self._cq_phase,
                "decision": decision.get("decision") if decision else None,
                "question_id": decision.get("question_id") if decision else None,
                "pending_review": self._cq_wait_windows.has_open_window,
            }
        if action == "cq_freeze":
            snapshot = self.handle_cq_freeze(message)
            return {
                "type": "cq-frozen",
                "action": action,
                "freeze_id": snapshot["batch_id"],
                "snapshot_digest": snapshot["snapshot_digest"],
                "public_question_ids": [
                    question["question_id"]
                    for question in snapshot["questions"]
                    if question["visibility"] == "public"
                ],
                "hidden_question_count": sum(
                    1
                    for question in snapshot["questions"]
                    if question["visibility"] == "hidden"
                ),
                "phase": self._cq_phase,
            }
        if action == "cq_handoff_complete":
            result = self._handle_cq_handoff_complete(message)
            return {"type": "cq-handoff-complete", "action": action, **result}
        if action == "cq_acceptance_complete":
            result = self._handle_cq_acceptance_complete(message)
            return {"type": "cq-acceptance-complete", "action": action, **result}
        raise CQContractError(
            "cq_selector_incompatible",
            "unknown competency-question outer action",
            obj="cq_outer_input",
            phase=self._cq_phase,
            retry=(
                "use cq_interview, cq_review, cq_freeze, cq_handoff_complete "
                "or cq_acceptance_complete"
            ),
        )

    def _cq_acceptance_hold_pending(self) -> bool:
        """True while a cq_semantic run awaits its acceptance completion.

        R3.0-012 (design §4.5, functional contract item 8): during the
        ``acceptance_pending`` phase the run keeps its retained read
        credentials, scope and production pause, and must not enter
        ``TERMINAL_REPORT_COMPLETE`` just because the roster went terminal.
        The conjunction keeps every other run (full_joint, non-CQ) on its
        exact previous settlement behavior.
        """

        return bool(
            self._competency_questions
            and self._acceptance_target == "cq_semantic"
            and self._cq_acceptance_phase == "acceptance_pending"
        )

    def _cq_terminal_block_reason(self, agent_id: str) -> dict[str, Any] | None:
        """Typed continuation for a premature CQ terminal report.

        Returns ``None`` when the report may proceed.  A premature report is
        rejected for that call only: nothing is latched, the run is not killed,
        and the same CQ session continues (design §3.2).
        """

        if self._cq_agent_id() != agent_id or not self._competency_questions:
            return None
        if self._cq_terminal_reported:
            return None
        if self._cq_handoff_complete:
            self._cq_terminal_reported = True
            self._append_evidence(
                "cq-terminal-report",
                {"event": "accepted", "phase": getattr(self, "_cq_phase", None)},
            )
            return None
        phase = getattr(self, "_cq_phase", "panorama-draft")
        if self._cq_freeze is None:
            retry = "freeze the question pool before reporting a terminal result"
        else:
            retry = (
                "wait for the Delivery host to send cq_handoff_complete; the production "
                "handoff is not released yet"
            )
        reason = {
            "object": "report_task_result",
            "phase": phase,
            "reason_code": "cq_batch_scope_unauthorized",
            "retry": retry,
        }
        self._append_evidence("cq-terminal-report", {"event": "rejected", **reason})
        return reason

    def _wake_acceptance_on_child_terminal(self) -> None:
        """R2.3-009 follow-up (start5 live evidence 2026-08-20).

        Examiner children reach their terminal state (ingested report or
        recorded infrastructure failure) on pump/watchdog threads with no
        delivery to the persistent Acceptance role, which ends its turn while
        "awaiting terminal reports" and then sleeps forever.  The carrier now
        queues each terminal transition; this Host-loop hook drains the queue
        and wakes Acceptance with one mechanical notification so it can poll
        ``acceptance_child_get_report``, recycle, and retry or settle the
        round instead of deadlocking into T3.  The notification carries only
        protocol facts (round, kind, outcome, digest) -- no business
        semantics -- so deterministic mechanics stay out of model reasoning.
        """

        carrier = getattr(self, "acceptance", None)
        if carrier is None:
            return
        if getattr(carrier, "is_settled", False):
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            # Keep events queued; the next drain after the issue resolves
            # delivers the wake with the resume guidance.
            return
        drain_events = getattr(carrier, "drain_child_terminal_events", None)
        if not callable(drain_events):
            return
        events = drain_events()
        if not events or not self.run:
            return
        try:
            acceptance_agent = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "acceptance"
            )
        except StopIteration:
            return
        for event in events:
            delivery = RuntimeDelivery(
                sender_id="runner/examiner-terminal",
                recipient_id=acceptance_agent,
                kind="examiner-terminal",
                text=json.dumps(event, ensure_ascii=False, sort_keys=True),
            )
            receipt = self.adapter.send_message(acceptance_agent, delivery)
            self._append_evidence(
                "examiner-terminal-wake",
                {
                    "recipient_id": acceptance_agent,
                    "event": event,
                    "turn_id": getattr(receipt, "turn_id", None),
                },
            )

    def _check_run_fallback_timeout(self) -> None:
        """R2.3-009 T3: the only run-level timeout latch left in the Runner."""

        if getattr(self, "_formal_failure_latched", False):
            return
        started = getattr(self, "_run_fallback_started", None)
        if started is None:
            return
        if self.acceptance is not None and getattr(self.acceptance, "is_settled", False):
            return
        now = (getattr(self, "monotonic_clock", None) or time.monotonic)()
        excluded = getattr(self, "_issue_pending_elapsed", 0.0)
        pending_started = getattr(self, "_issue_pending_started", None)
        if pending_started is not None:
            excluded += max(0.0, now - pending_started)
        # 2026-09-14 provider-recovery: externally blocked waiting time (quota,
        # balance, concurrency, provider outage) is not run inactivity.
        provider_started = getattr(self, "_provider_wait_started", None)
        if provider_started is not None:
            excluded += max(0.0, now - provider_started)
        excluded += getattr(self, "_provider_wait_elapsed", 0.0)
        # R3.0-011 (design §3.2): explicit user-review / interview / handoff
        # waits are recoverable waits, not stalled progress.  Overlapping CQ
        # windows are unioned by the tracker, so a window that starts inside
        # another one never extends the exclusion twice.
        cq_excluded = self._cq_wait_windows.elapsed(now)
        active = max(0.0, now - started - excluded - cq_excluded)
        timeout_seconds = getattr(self, "_run_fallback_timeout_seconds", 10800.0)
        if active < timeout_seconds:
            return
        self._append_evidence(
            "run-fallback-timeout",
            {
                "active_seconds": active,
                "timeout_seconds": timeout_seconds,
                "cq_wait_excluded_seconds": cq_excluded,
                "cq_wait_windows": self._cq_wait_windows.evidence(now),
                "nudges_sent": getattr(self, "_nudges_sent", 0),
                "issues_opened": getattr(self, "_issues_opened", 0),
                "last_responsible_agent": getattr(self, "_last_responsible_agent", None),
                "feedback_counts": {
                    f"{issue_class}:{code}:{agent}": count
                    for (issue_class, code, agent), count in sorted(
                        getattr(self, "_feedback_counts", {}).items()
                    )
                },
            },
        )
        self._latch_formal_candidate_failure(
            "collaboration/routing",
            "run-fallback-timeout",
            terminal_evidence=self._run_fallback_terminal_evidence(),
        )
        raise FormalCandidateProgressTimeout(
            f"run fallback timeout exceeded {active:.0f} active seconds"
        )

    def _check_cooperative_idle(self) -> None:
        """Send one bounded inquiry to Coordinator when the run is fully idle.

        R2.3-009 start10/12 (2026-08-21): between the initial slice
        assignment and the first candidate dispatch, no component owns
        progress — the candidate-progress nudges require an already
        dispatched candidate.  A Coordinator that idles there (an unasked
        owner question, a capability probe given up) silently burns the whole
        run-fallback window.  This check is purely mechanical: when no role
        is in a turn, no notification was observed for the idle window, no
        cooperative issue is pending, no Examiner child is live, and no
        candidate channel is open, it asks the Coordinator to state the
        blocker and continue.  There is no per-run budget (start15 showed a
        budget can be consumed by legitimate waiting and leave a later
        deadlock unwatched); the baseline resets after each inquiry so the
        follow-up waits another full idle window — that window is the only
        rate limit.
        """

        if not self.run:
            return
        # auth008-start1: staged v3 runs (e.g. r3-0-006-real-full with the CQ
        # profile) are not formal coordination, but a Coordinator stall after
        # staged gate feedback deserves the same bounded nudge.
        if not (self._formal_coordination_enabled() or getattr(self, "_staged_decisions", False)):
            return
        idle_baseline = getattr(self, "_idle_inquiry_baseline", None)
        if idle_baseline is None:
            return
        if getattr(self, "_terminal_emitted", False):
            return
        if getattr(self, "_post_settlement_reporting_requested", False):
            return
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending:
            return
        # A terminal candidate (accepted receipt, exhausted redrives) leaves
        # its pending record alive; only an open channel owns progress.
        if self._candidate_progress is not None and self._candidate_progress.channel_open:
            return
        if self.acceptance is not None and self.acceptance.has_live_children:
            return
        states_reader = getattr(self.adapter, "get_agent_states", None)
        if callable(states_reader) and any(
            state.state in {"starting", "running"} for state in states_reader()
        ):
            return
        activity_reader = getattr(self.adapter, "last_output_monotonic", None)
        last_activity = float(activity_reader()) if callable(activity_reader) else None
        now = self.monotonic_clock()
        idle_started = idle_baseline
        if last_activity is not None:
            idle_started = max(idle_started, last_activity)
        idle_seconds = now - idle_started
        if idle_seconds < getattr(self, "_idle_inquiry_seconds", 300.0):
            return
        inquiries_sent = getattr(self, "_idle_inquiries_sent", 0)
        coordinator = next(
            (
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "coordinator"
            ),
            None,
        )
        if not coordinator:
            return
        self._idle_inquiries_sent = inquiries_sent + 1
        self._idle_inquiry_baseline = now
        receipt = self.adapter.send_message(
            coordinator,
            RuntimeDelivery(
                sender_id="runner/idle-inquiry",
                recipient_id=coordinator,
                kind="idle-inquiry",
                text=(
                    "The Runner observed no role activity for "
                    f"{idle_seconds:.0f} seconds with no candidate, Acceptance "
                    "child, or cooperative issue in flight. State the current "
                    "blocker and continue the assigned task: file any pending "
                    "owner question through the formal channel, dispatch the "
                    "next delivery, or submit your terminal report if the run "
                    "cannot proceed. Do not wait silently."
                ),
            ),
        )
        self._append_evidence(
            "idle-inquiry",
            {
                "idle_seconds": idle_seconds,
                "inquiry_count": self._idle_inquiries_sent,
                "recipient_id": coordinator,
                "delivery_kind": getattr(receipt, "mode", None),
                "turn_id": getattr(receipt, "turn_id", None),
            },
        )

    def _run_fallback_terminal_evidence(self) -> dict[str, Any] | None:
        """The R2.3-009 refund binding for a T3 run-fallback terminal failure."""

        ledger = getattr(self, "_ledger", None)
        if ledger is None or not self.run:
            return None
        if not getattr(ledger.config, "strict_sequence", False):
            # The legacy non-strict ledgers reject terminal evidence outright;
            # they keep their historical accounting without refunds.
            return None
        return {
            "run_id": self.run.run_id,
            "classification": "collaboration/routing",
            "mutation_state": "zero-mutation",
            "reason": "run-fallback-timeout",
        }

    def _issue_coordinator_id(self) -> str:
        if not self.run:
            raise TeamConfigurationError("issue Coordinator is unavailable")
        for agent in self.run.configuration.profile.agents:
            if agent.package.role == "coordinator":
                return agent.agent_id
        raise TeamConfigurationError("issue Coordinator is unavailable")

    def _issue_ledger(self) -> Any | None:
        return getattr(self.transport, "issue_ledger", None)

    def _issue_control_from_payload(self, value: Any) -> IssueControl:
        if not isinstance(value, dict):
            raise TeamConfigurationError("issue control payload is invalid")
        resolution_value = value.get("resolution")
        resolution: IssueResolution | None = None
        if resolution_value is not None:
            if not isinstance(resolution_value, dict):
                raise TeamConfigurationError("issue control resolution is invalid")
            try:
                resolution = IssueResolution(**resolution_value)
            except (TypeError, IssueError) as exc:
                raise TeamConfigurationError("issue control resolution is invalid") from exc
        try:
            return IssueControl(
                run_id=value.get("run_id"),
                issue_id=value.get("issue_id"),
                coordinator_id=value.get("coordinator_id"),
                reporter_id=value.get("reporter_id"),
                action=value.get("action"),
                control_epoch=value.get("control_epoch"),
                resolution=resolution,
                reason=value.get("reason"),
            )
        except (TypeError, IssueError) as exc:
            raise TeamConfigurationError("issue control payload is invalid") from exc

    def _handle_issue_events(self, output: list[dict[str, Any]]) -> None:
        """Process Broker issue callbacks in the Runner main loop only."""
        if not self.transport or not self.transport.issue_escalation_enabled or not self.run:
            return
        with self._issue_event_lock:
            events, self._issue_event_queue = self._issue_event_queue[:], []
        if not events:
            return
        coordinator = self._issue_coordinator_id()
        for event in events:
            kind = event.get("kind") if isinstance(event, dict) else None
            if kind == "issue_report":
                issue = event.get("issue")
                if not isinstance(issue, dict):
                    raise TeamConfigurationError("issue report callback payload is invalid")
                issue_id = issue.get("issue_id")
                reporter_id = issue.get("reporter_id")
                if isinstance(issue_id, str) and isinstance(reporter_id, str):
                    identity = self._candidate_progress.identity if self._candidate_progress else None
                    candidate_identity = identity.__dict__.copy() if identity is not None else None
                    thread_id = self._formal_protocol_thread_id(reporter_id)
                    try:
                        issue = self.transport.bind_issue_context(
                            issue_id=issue_id,
                            reporter_id=reporter_id,
                            thread_id=thread_id,
                            candidate_identity=candidate_identity,
                        )
                    except RoutingError as exc:
                        raise TeamConfigurationError("issue context binding failed") from exc
                self._append_evidence("issue-report", issue)
                try:
                    self.adapter.send_message(
                        coordinator,
                        RuntimeDelivery(
                            sender_id="runner/issue",
                            recipient_id=coordinator,
                            kind="issue",
                            text=json.dumps(issue, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                except Exception as exc:
                    if issue.get("category") == "runtime_recovery":
                        # 2026-09-14 provider-recovery: the Coordinator became
                        # unavailable between the health check and this delivery.
                        # The provider wait stays observable in evidence and the
                        # host recovery action remains usable; no rebind.
                        self._append_evidence(
                            "provider-wait",
                            {
                                "event": "coordinator-delivery-failed",
                                "issue_id": issue.get("issue_id"),
                                "reporter_id": issue.get("reporter_id"),
                            },
                        )
                        if self._candidate_progress is not None:
                            self._candidate_progress.pause(now=self.monotonic_clock())
                        self._state("WAITING_OWNER", issue_id=issue.get("issue_id"))
                        continue
                    issue_id = issue.get("issue_id")
                    reporter_id = issue.get("reporter_id")
                    if isinstance(issue_id, str) and isinstance(reporter_id, str):
                        try:
                            self.transport.fail_issue_rebind(
                                issue_id=issue_id,
                                reporter_id=reporter_id,
                                reason="Coordinator delivery failed",
                            )
                        except RoutingError:
                            pass
                    raise TeamConfigurationError("issue Coordinator delivery failed") from exc
                if self._candidate_progress is not None:
                    self._candidate_progress.pause(now=self.monotonic_clock())
                self._state(
                    "WAITING_REPAIR"
                    if issue.get("category") == "platform_repair"
                    else "WAITING_OWNER",
                    issue_id=issue.get("issue_id"),
                )
                self._append_evidence(
                    "issue-pause",
                    {
                        "issue_id": issue.get("issue_id"),
                        "reporter_id": issue.get("reporter_id"),
                        "state": "reported",
                        "candidate_paused": self._candidate_progress is not None,
                    },
                )
                continue
            if kind != "issue_control":
                raise TeamConfigurationError("unknown issue callback event")
            control = self._issue_control_from_payload(event.get("control"))
            self._dispatch_issue_control(control, output)

    def _dispatch_issue_control(self, control: IssueControl, output: list[dict[str, Any]]) -> None:
        if not self.transport or not self.run:
            raise TeamConfigurationError("issue transport is unavailable")
        if control.run_id != self.run.run_id or control.coordinator_id != self._issue_coordinator_id():
            raise TeamConfigurationError("issue control run binding is invalid")
        active_issue = self._issue_ledger().active_issue if self._issue_ledger() is not None else None
        if active_issue is None or active_issue.issue_id != control.issue_id:
            raise TeamConfigurationError("issue control issue binding is invalid")
        # 2026-09-14 provider-recovery: a failed provider recovery is requeued,
        # but never retried in a tight loop — each retry is spaced by a fixed
        # backoff window (no paid polling, no fixed attempt-count death).
        retry_gate = getattr(self, "_provider_recovery_retry_not_before", None)
        if (
            retry_gate is not None
            and control.action == "resume"
            and self._provider_wait_active(control.reporter_id)
        ):
            clock = getattr(self, "monotonic_clock", None) or time.monotonic
            if clock() < retry_gate:
                with self._issue_event_lock:
                    self._issue_event_queue.append(
                        {"kind": "issue_control", "control": control.as_dict()}
                    )
                output.append(
                    {
                        "type": "issue-control-waiting",
                        "reason_code": "provider_recovery_backoff",
                        **control.as_dict(),
                    }
                )
                return
        if control.action == "abort":
            self._issue_abort_requested = True
            self._append_evidence("issue-abort", control.as_dict())
            self._state("ABORTING", issue_id=control.issue_id)
            # Abort is explicit and terminal; no Runtime interrupt is used.
            return
        agent = getattr(self.adapter, "agents", {}).get(control.reporter_id)
        if agent is not None:
            process = getattr(agent, "process", None)
            if process is not None and callable(getattr(process, "poll", None)):
                try:
                    if process.poll() is not None:
                        self.transport.fail_issue_rebind(
                            issue_id=control.issue_id,
                            reporter_id=control.reporter_id,
                            reason="reporter App Server is dead",
                        )
                        raise TeamConfigurationError("issue reporter App Server is dead")
                except (IssueError, RoutingError) as exc:
                    raise TeamConfigurationError("issue reporter cannot be rebound") from exc
        if control.action == "resume" and control.resolution is not None:
            if control.resolution.resolution_type == "repair_completed":
                component = control.resolution.repair_component
                if component not in REPAIR_COMPONENTS:
                    self.transport.fail_issue_rebind(
                        issue_id=control.issue_id,
                        reporter_id=control.reporter_id,
                        reason="repair component requires rebind",
                    )
                    raise TeamConfigurationError("issue repair requires rebind")
        before_thread = self._formal_protocol_thread_id(control.reporter_id)
        if active_issue.thread_id is not None and active_issue.thread_id != before_thread:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control thread binding drift",
            )
            raise TeamConfigurationError("issue control thread binding drift")
        current_identity = self._candidate_progress.identity if self._candidate_progress else None
        current_candidate = current_identity.__dict__.copy() if current_identity is not None else None
        if active_issue.candidate_identity != current_candidate:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control candidate binding drift",
            )
            raise TeamConfigurationError("issue control candidate binding drift")
        before_turn = getattr(agent, "active_turn_id", None) if agent is not None else None
        # R2.3-009 start20: a Coordinator-reported issue is resumed from inside
        # the Coordinator's own live turn, so the idle-reporter and fresh-turn
        # expectations below can never hold for it.  The Coordinator already
        # holds the resolution (it dispatched this control itself); skipping
        # the reporter delivery is the recoverable path, not a teardown.
        self_resumed = (
            control.action == "resume"
            and control.reporter_id == control.coordinator_id
        )
        if control.action == "resume" and not self_resumed and before_turn is not None:
            # Broker persistence has already moved the ledger to
            # ``resume_sent``.  Keep that exact control and its resolution
            # pending until the reporter finishes this turn; converting a
            # transient busy observation into ``rebind_required`` would burn
            # the one live recovery path before any Runtime send occurred.
            pending_event = {
                "kind": "issue_control",
                "control": control.as_dict(),
            }
            with self._issue_event_lock:
                self._issue_event_queue.append(pending_event)
            waiting = {
                "type": "issue-control-waiting",
                "reason_code": "resume_waiting_reporter",
                **control.as_dict(),
            }
            output.append(waiting)
            self._append_evidence(
                "issue-control",
                {
                    "event": "resume_waiting_reporter",
                    "issue_id": control.issue_id,
                    "reporter_id": control.reporter_id,
                    "control_epoch": control.control_epoch,
                    "turn_id": before_turn,
                },
            )
            return
        receipt: RuntimeDispatchReceipt | None = None
        # 2026-09-14 provider-recovery: a reporter parked in a provider wait can
        # neither receive an ordinary control turn nor be rebound — its process
        # and thread are alive, only the provider is exhausted.
        provider_waiting = self._provider_wait_active(control.reporter_id)
        recovery_wait_id = None
        if provider_waiting:
            record = self._provider_wait_registry().get(control.reporter_id)
            if record is None:
                status_reader = getattr(self.adapter, "provider_wait_status", None)
                record = status_reader(control.reporter_id) if callable(status_reader) else None
            recovery_wait_id = record.get("wait_id") if isinstance(record, dict) else None
        try:
            if not self_resumed:
                if provider_waiting and control.action == "resume":
                    recovery_text = (
                        control.resolution.resolution_text
                        if control.resolution is not None and control.resolution.resolution_text
                        else json.dumps(control.as_dict(), ensure_ascii=False, sort_keys=True)
                    )
                    receipt = self.adapter.recover_provider_wait(
                        control.reporter_id,
                        recovery_text,
                        wait_id=recovery_wait_id,
                        sender_id="runner/issue-control",
                    )
                    if getattr(receipt, "mode", None) != "start":
                        raise RuntimeError("provider recovery did not start a new turn")
                elif provider_waiting:
                    # A pause for a parked role needs no Runtime turn: the wait
                    # itself already freezes the role.  Record and proceed to
                    # the dispatch/state transition below.
                    self._append_evidence(
                        "issue-control",
                        {
                            "event": "provider-wait-pause-noop",
                            "issue_id": control.issue_id,
                            "reporter_id": control.reporter_id,
                            "control_epoch": control.control_epoch,
                            "wait_id": recovery_wait_id,
                        },
                    )
                else:
                    receipt = self.adapter.send_message(
                        control.reporter_id,
                        RuntimeDelivery(
                            sender_id="runner/issue-control",
                            recipient_id=control.reporter_id,
                            kind="issue-control",
                            text=json.dumps(control.as_dict(), ensure_ascii=False, sort_keys=True),
                        ),
                    )
        except Exception as exc:
            if provider_waiting and control.action == "resume":
                # Recovery returned to the observable wait; the persisted
                # resolution and this control stay retryable instead of burning
                # the live thread with a rebind.
                with self._issue_event_lock:
                    self._issue_event_queue.append(
                        {"kind": "issue_control", "control": control.as_dict()}
                    )
                clock = getattr(self, "monotonic_clock", None) or time.monotonic
                self._provider_recovery_retry_not_before = clock() + _PROVIDER_RECOVERY_RETRY_SECONDS
                self._append_evidence(
                    "issue-control",
                    {
                        "event": "provider-wait-recovery-failed",
                        "issue_id": control.issue_id,
                        "reporter_id": control.reporter_id,
                        "control_epoch": control.control_epoch,
                        "wait_id": recovery_wait_id,
                    },
                )
                output.append(
                    {
                        "type": "issue-control-waiting",
                        "reason_code": "provider_recovery_retry",
                        **control.as_dict(),
                    }
                )
                return
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control Runtime delivery failed",
            )
            raise TeamConfigurationError("issue control Runtime delivery failed") from exc
        after_thread = self._formal_protocol_thread_id(control.reporter_id)
        after_turn = getattr(agent, "active_turn_id", None) if agent is not None else getattr(receipt, "turn_id", None)
        if (
            control.action == "resume"
            and not self_resumed
            and getattr(receipt, "mode", None) != "start"
        ):
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="resume did not start a new turn",
            )
            raise TeamConfigurationError("issue resume did not start a new turn")
        if before_thread != after_thread:
            self.transport.fail_issue_rebind(
                issue_id=control.issue_id,
                reporter_id=control.reporter_id,
                reason="issue control thread binding changed",
            )
            raise TeamConfigurationError("issue control thread binding changed")
        try:
            self.transport.mark_issue_dispatch(control)
        except RoutingError as exc:
            raise TeamConfigurationError("issue control CAS dispatch rejected") from exc
        if control.action == "pause":
            if self._candidate_progress is not None:
                self._candidate_progress.pause(now=self.monotonic_clock())
            self._state(
                "WAITING_REPAIR"
                if self._issue_ledger()
                and self._issue_ledger().active_issue
                and self._issue_ledger().active_issue.category == "platform_repair"
                else "WAITING_OWNER",
                issue_id=control.issue_id,
            )
            # Surface the issue only after Coordinator has reviewed it and
            # issued the bound cooperative pause. This is the structured
            # Coordinator-to-outer escalation boundary.
            output.append(
                {
                    "type": "issue",
                    "issue": active_issue.as_dict(state=self._issue_ledger().state),
                }
            )
        elif control.action == "resume":
            if self._candidate_progress is not None:
                self._candidate_progress.resume(now=self.monotonic_clock())
            self._state("RUNNING", issue_id=control.issue_id)
        self._append_evidence(
            "issue-control",
            {
                "issue_id": control.issue_id,
                "reporter_id": control.reporter_id,
                "action": control.action,
                "control_epoch": control.control_epoch,
                "before_thread_id": before_thread,
                "after_thread_id": after_thread,
                "before_turn_id": before_turn,
                "after_turn_id": after_turn,
                "turn_id": getattr(receipt, "turn_id", None),
                "dispatch_mode": getattr(receipt, "mode", None),
            },
        )
        output.append({"type": "issue-control", **control.as_dict()})

    def _observe_coordinator_message(self, message: Any) -> None:
        """Retain the coordinator hook without making prose a display authority.

        Formal outer-question display is bound only by
        :meth:`observe_foreground_output`, after the host successfully emits the
        exact Runner delivery envelope.  Coordinator text can be a paraphrase,
        can omit the question, or can contain unrelated text; none of those
        cases may change the pending question state.
        """
        del message

    def observe_foreground_output(self, output: list[dict[str, Any]]) -> None:
        """Bind formal outer questions to exact, successfully emitted envelopes.

        The foreground event loop calls this method only after ``emit`` returns.
        Validation is intentionally completed for the entire batch before any
        outer-question evidence is appended or any record is marked displayed.
        """
        if not self._formal_coordination_enabled() or not self.run:
            return
        if not isinstance(output, list):
            raise TeamConfigurationError("foreground output must be a list")

        modeling = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "modeling"
        )
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")

        expected_fields = {
            "type",
            "sequence",
            "sender_id",
            "recipient_id",
            "text",
            "timestamp",
            "delivery_id",
            "expects_reply",
            "reply_to_delivery_id",
        }
        records_to_display: list[dict[str, Any]] = []
        seen: set[str] = set()
        for envelope in output:
            if not isinstance(envelope, dict):
                raise TeamConfigurationError("foreground output envelope is invalid")
            delivery_id = envelope.get("delivery_id")
            if not isinstance(delivery_id, str):
                continue
            record = self._outer_questions.get(delivery_id)
            if record is None:
                # Ordinary peer/owner deliveries and terminal envelopes have
                # unrelated IDs.  They are not candidates for formal display.
                continue
            if set(envelope) != expected_fields:
                raise TeamConfigurationError("outer question display envelope fields drift")
            if (
                envelope.get("type") != "delivery"
                or not isinstance(envelope.get("sequence"), int)
                or isinstance(envelope.get("sequence"), bool)
                or not isinstance(envelope.get("timestamp"), (int, float))
                or isinstance(envelope.get("timestamp"), bool)
                or envelope.get("delivery_id") != record.get("question_delivery_id")
                or envelope.get("sequence") != record.get("sequence")
                or envelope.get("timestamp") != record.get("timestamp")
                or envelope.get("sender_id") != modeling
                or envelope.get("recipient_id") != coordinator
                or envelope.get("text") != record.get("text")
                or envelope.get("expects_reply") is not True
                or envelope.get("reply_to_delivery_id") is not None
            ):
                raise TeamConfigurationError("outer question display envelope drifts")
            if (
                record.get("run_id") != self.run.run_id
                or record.get("project_id") != project_id
                or record.get("origin_agent_id") != modeling
            ):
                raise TeamConfigurationError("outer question display binding drifts")
            if record.get("displayed") is True or record.get("consumed") is True:
                continue
            if delivery_id not in seen:
                records_to_display.append(record)
                seen.add(delivery_id)

        # Persist each record before flipping its in-memory display bit.  If a
        # later independent append fails, the already evidenced records remain
        # valid while the caller aborts before it can consume another input.
        for record in records_to_display:
            self._append_evidence(
                "outer-question",
                {
                    key: record[key]
                    for key in ("question_delivery_id", "project_id", "run_id", "text")
                },
            )
            record["displayed"] = True

    def _resolve_formal_owner_question(self, text: str) -> str:
        """Resolve a text-only schema-v2 answer to exactly one displayed question."""
        del text  # The answer text is intentionally not part of question ownership.
        unresolved = [
            record
            for record in self._outer_questions.values()
            if record.get("consumed") is not True
        ]
        eligible = [record for record in unresolved if record.get("displayed") is True]
        if len(eligible) == 0:
            if unresolved:
                raise RecoverableOuterInputError(
                    "owner answer question has not been displayed",
                    code="owner_answer_rejected",
                    run_id=self.run.run_id,
                )
            raise RecoverableOuterInputError(
                "owner answer has no unanswered displayed question",
                code="owner_answer_rejected",
                run_id=self.run.run_id,
            )
        if len(eligible) > 1:
            raise RecoverableOuterInputError(
                "owner answer matches multiple unanswered questions",
                code="owner_answer_rejected",
                run_id=self.run.run_id,
            )
        question = eligible[0]
        if question.get("run_id") != self.run.run_id:
            raise TeamConfigurationError("owner answer run binding drifts")
        if question.get("project_id") != self._project_binding():
            raise TeamConfigurationError("owner answer project binding drifts")
        modeling = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "modeling"
        )
        if question.get("origin_agent_id") != modeling:
            raise TeamConfigurationError("owner answer question origin drifts")
        return question["question_delivery_id"]

    def _record_outer_question(self, message: dict[str, Any]) -> None:
        assert self.run
        allowed = {"action", "delivery_id", "question_delivery_id", "text"}
        if set(message) - allowed or message.get("action") != "question":
            raise RecoverableOuterInputError(
                "outer question envelope is invalid",
                code="invalid_outer_question",
                run_id=self.run.run_id,
            )
        delivery_id = message.get("delivery_id")
        question_delivery_id = message.get("question_delivery_id")
        if delivery_id is not None and question_delivery_id is not None:
            if delivery_id != question_delivery_id:
                raise RecoverableOuterInputError(
                    "outer question delivery IDs do not match",
                    code="invalid_outer_question",
                    run_id=self.run.run_id,
                )
        if delivery_id is None:
            delivery_id = question_delivery_id
        text = message.get("text")
        if (
            not isinstance(delivery_id, str)
            or not delivery_id.strip()
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise RecoverableOuterInputError(
                "outer question delivery is invalid",
                code="invalid_outer_question",
                run_id=self.run.run_id,
            )
        existing = self._outer_questions.get(delivery_id)
        if existing is not None:
            if existing["text"] != text:
                raise RecoverableOuterInputError(
                    "outer question delivery is immutable",
                    code="invalid_outer_question",
                    run_id=self.run.run_id,
                )
            return
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("outer question project binding is missing")
        record: dict[str, Any] = {
            "question_delivery_id": delivery_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "text": text,
        }
        self._outer_questions[delivery_id] = record
        self._append_evidence("outer-question", record)

    def _release_owner_answer(
        self,
        coordinator: str,
        text: str,
        question_delivery_id: object,
    ) -> None:
        assert self.run
        if not isinstance(text, str) or not text.strip():
            raise RecoverableOuterInputError(
                "owner answer text is invalid",
                code="invalid_owner_answer",
                run_id=self.run.run_id,
            )
        if not isinstance(question_delivery_id, str) or not question_delivery_id:
            raise RecoverableOuterInputError(
                "owner answer requires a question delivery ID",
                code="owner_answer_rejected",
                run_id=self.run.run_id,
            )
        question = self._outer_questions.get(question_delivery_id)
        if question is None:
            raise RecoverableOuterInputError(
                "owner answer question delivery is unknown",
                code="owner_answer_rejected",
                run_id=self.run.run_id,
            )
        formal = self._formal_coordination_enabled()
        if question.get("project_id") != self._project_binding():
            raise TeamConfigurationError("owner answer project binding drifts")
        if formal:
            if question.get("run_id") != self.run.run_id:
                raise TeamConfigurationError("owner answer run binding drifts")
            if question.get("displayed") is not True:
                raise RecoverableOuterInputError(
                    "owner answer question has not been displayed",
                    code="owner_answer_rejected",
                    run_id=self.run.run_id,
                )
            modeling = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "modeling"
            )
            if question.get("origin_agent_id") != modeling:
                raise TeamConfigurationError("owner answer question origin drifts")
        key = (question_delivery_id, text)
        existing = self._owner_answers.get(key)
        if key in self._owner_answer_failures:
            raise TeamConfigurationError("owner answer delivery previously failed and cannot be reused")
        if question.get("consumed") is True or question_delivery_id in self._owner_answer_consumed:
            # Historical non-formal fixtures called this private helper directly and
            # relied on same-key idempotence; the formal schema-v2 envelope is strict
            # and rejects every replay, including identical text.
            if existing is not None and not formal:
                return
            if any(
                failed_question_id == question_delivery_id
                for failed_question_id, _failed_text in self._owner_answer_failures
            ):
                raise TeamConfigurationError("owner answer question delivery was already consumed")
            raise RecoverableOuterInputError(
                "owner answer question delivery was already consumed",
                code="owner_answer_rejected",
                run_id=self.run.run_id,
            )
        if existing is not None:
            return
        project_id = self._project_binding()
        if not isinstance(project_id, str) or not project_id:
            raise TeamConfigurationError("owner answer project binding is missing")
        authorization_id = self.run.configuration.profile.parameters.get(
            "owner_answer_authorization_id", _OWNER_ANSWER_AUTHORIZATION
        )
        if not isinstance(authorization_id, str) or not authorization_id:
            raise TeamConfigurationError("owner answer authorization binding is missing")
        owner_payload = {
            "run_id": self.run.run_id,
            "project_id": project_id,
            "question_delivery_id": question_delivery_id,
            "text": text,
        }
        owner_answer_id = "owner-answer-" + self._canonical_digest(owner_payload)
        self._outer_answer_sequence += 1
        release_id = f"owner-answer-delivery-{self._outer_answer_sequence}"
        record = {
            "owner_answer_id": owner_answer_id,
            "project_id": project_id,
            "run_id": self.run.run_id,
            "authorization_id": authorization_id,
            "release_id": release_id,
            "question_delivery_id": question_delivery_id,
            "delivery_id": release_id,
            "text": text,
            "released_at": datetime.now(UTC).isoformat(),
        }
        # The question is consumed before any persistence or send attempt.  This lock is
        # intentionally independent of answer text: persistence/send failures burn this
        # question and its generated identifiers rather than permitting a retry.
        question["consumed"] = True
        self._owner_answer_consumed.add(question_delivery_id)
        self._owner_answer_attempts[question_delivery_id] = record
        # The exact nine-field record is persisted and fsynced before the Broker queues
        # the direct Modeling answer.  A failed persistence/publication burns the IDs.
        try:
            self._append_exact_outer_user(record)
            if self.transport is not None and formal:
                self.transport.publish_owner_answer(
                    question_delivery_id=question_delivery_id,
                    owner_answer_id=owner_answer_id,
                    release_id=release_id,
                    text=text,
                )
            else:
                # Compatibility for the historical direct helper used by schema-v2 unit
                # fixtures that do not attach a Broker.  Formal started runs always use
                # the narrowed Broker publication above.
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="outer-user",
                        text=text,
                        delivery_id=release_id,
                        reply_to_delivery_id=question_delivery_id,
                    ),
                )
        except Exception:
            self._owner_answer_failures.add(key)
            self._state("FAILED", owner_answer_id=owner_answer_id, release_id=release_id)
            self._append_evidence(
                "owner-answer-failure",
                {"owner_answer_id": owner_answer_id, "release_id": release_id},
            )
            raise
        self._owner_answers[key] = record
        self._outer_user_texts.add(text)
        # R2.3-009 start24 (2026-08-22): the formal publication above reaches
        # only Modeling, while the Coordinator — which owns terminal handoffs —
        # stayed structurally blind to owner answers.  start24 wedged when the
        # Coordinator kept blocking on an "unanswered" owner question long
        # after the answer had been delivered to and acknowledged by Modeling.
        # Issue resolutions already notify the Coordinator; mirror that here.
        # The Modeling delivery already succeeded, so a notify failure must not
        # burn the answer — record it and continue.
        if formal:
            try:
                self.adapter.send_message(
                    coordinator,
                    RuntimeDelivery(
                        sender_id="user/outer",
                        recipient_id=coordinator,
                        kind="outer-user",
                        text=text,
                    ),
                )
            except Exception:
                self._append_evidence(
                    "owner-answer-coordinator-notify-failure",
                    {"owner_answer_id": owner_answer_id, "release_id": release_id},
                )

    def _append_exact_outer_user(self, record: dict[str, str]) -> None:
        assert self.run
        fields = {
            "owner_answer_id",
            "project_id",
            "run_id",
            "authorization_id",
            "release_id",
            "question_delivery_id",
            "delivery_id",
            "text",
            "released_at",
        }
        if set(record) != fields:
            raise TeamConfigurationError("outer-user owner answer fields drift")
        path = self.run.root / "evidence" / "outer-user.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _mark_owner_answer_failure(self, delivery: Any, reason: str) -> None:
        question_delivery_id = delivery.reply_to_delivery_id
        record = self._owner_answer_attempts.get(question_delivery_id)
        if record is None:
            return
        key = (question_delivery_id, record["text"])
        self._owner_answer_failures.add(key)
        self._state(
            "FAILED",
            owner_answer_id=record["owner_answer_id"],
            release_id=record["release_id"],
        )
        self._append_evidence(
            "owner-answer-failure",
            {
                "owner_answer_id": record["owner_answer_id"],
                "release_id": record["release_id"],
                "reason": reason,
            },
        )

    def drain(self) -> list[dict[str, Any]]:
        if not self.run or not self.transport:
            return []
        failures = self._consume_runtime_failures()
        if failures:
            return self._finalize_runtime_failure(failures)
        # 2026-09-14 final review: once host takeover is selected, the deferred
        # Coordinator failure never auto-finalizes on its own — a successful
        # host recovery of the last waiting role must not be punished by an
        # immediate teardown of that just-recovered role.  Only an explicit
        # stop (or an unrelated role's own fatal failure) ends the run.
        # Provider waits are reconciled before the fallback clock check so a
        # wait observed on this very tick already excludes its waiting time.
        output: list[dict[str, Any]] = []
        self._check_provider_waits(output)
        self._track_issue_pending()
        self._track_provider_wait()
        self._check_run_fallback_timeout()
        self._check_formal_candidate_progress()
        # R3.0-011: the approved-slice handoff is a map-only check and must
        # not wait for the topology decision, the neutral candidate stage, or
        # the freeze (requirements-v3.0.md:512-535 order).  It runs on every
        # drain tick, so a failed notification retries on the next tick even
        # after the topology gate has already opened.
        self._cq_check_scenario_map_slices()
        # R3.0-008B: the staged checks run BEFORE the R3.0-002 topology gate
        # and gate its invocation (stage 3 slot is a topology prerequisite).
        # The call count of ``_check_multi_slice_topology_gate`` itself stays
        # exactly one per drain tick for every run.
        if self._check_staged_decision_gates():
            self._check_multi_slice_topology_gate()
        self._check_cooperative_idle()
        self._wake_acceptance_on_child_terminal()
        self._handle_issue_events(output)
        if self._issue_abort_requested:
            cleanup = self.cleanup()
            issue = self._issue_ledger().active_issue if self._issue_ledger() is not None else None
            self._record_issue_abort_terminal_failure(issue, cleanup)
            output.append(
                {
                    "type": "issue-aborted",
                    "issue_id": issue.issue_id if issue else None,
                    "cleanup": cleanup,
                }
            )
            self._state(
                "TERMINAL_REPORT_COMPLETE",
                issue_abort=True,
                issue_id=issue.issue_id if issue else None,
            )
            return output
        self._drain_coordination_runtime_deliveries()
        issue_ledger = self._issue_ledger()
        issue_pending = bool(issue_ledger is not None and issue_ledger.pending)
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        deliveries = self.transport.drain()
        if issue_pending:
            # Preserve every ordinary delivery/reply slot while the cooperative
            # issue is waiting.  The Broker history remains immutable and no
            # candidate response can be accidentally consumed before guidance.
            self.transport.requeue(deliveries)
            # Pump App-Server notifications while the run is paused so the
            # Coordinator's issue_control callback can enter the queue.  No
            # ordinary peer/terminal Runtime message is delivered or consumed.
            self.adapter.receive_messages()
            failures = self._consume_runtime_failures()
            if failures:
                return self._finalize_runtime_failure(failures)
            # The original candidate dispatch may complete while the issue is
            # pending.  Observe that completion now, before a later pause/
            # recovery turn overwrites the Runtime's last-completed turn ID.
            # Keep the issue freeze intact: redrive and deadline checks remain
            # deferred until the issue has been resolved.
            if self._candidate_progress is not None:
                roles = self._formal_candidate_roles()
                states_reader = getattr(self.adapter, "get_agent_states", None)
                if roles is not None and callable(states_reader):
                    _, protocol = roles
                    self._candidate_progress.observe_states(
                        states_reader(), protocol_agent_id=protocol
                    )
            return output
        for delivery in deliveries:
            try:
                formal_candidate_event = self._observe_formal_candidate_delivery(delivery)
            except FormalCandidateError as exc:
                # R2.3-009 B-class: a candidate-channel protocol violation is
                # persisted evidence plus typed feedback to Modeling, not a run
                # kill.  The revision/digest gates have already rejected the
                # delivery; the run keeps waiting for a compliant candidate.
                self._handle_formal_candidate_violation(delivery, exc)
                continue
            self._register_stage_handoff_delivery_if_exact(delivery)
            formal_invalid_response = False
            formal_roles = self._formal_candidate_roles()
            if formal_roles is not None and self._candidate_progress is not None:
                modeling, protocol = formal_roles
                formal_invalid_response = self._candidate_progress.is_invalid_response(
                    delivery,
                    modeling_agent_id=modeling,
                    protocol_agent_id=protocol,
                )
                if formal_invalid_response:
                    identity = self._candidate_progress.identity
                    if identity is None:
                        raise FormalCandidateError(
                            "formal invalid response has no active candidate identity"
                        )
                    standalone_response = (
                        delivery.sender_id == protocol
                        and delivery.recipient_id == modeling
                        and delivery.expects_reply is True
                        and delivery.reply_to_delivery_id is None
                    )
                    if standalone_response:
                        # R2.3-009 follow-up (user 2026-08-20): the formal
                        # candidate channel stays typed, but ordinary peer
                        # communication is free.  A post-receipt standalone
                        # Protocol-to-Modeling message that is not a perfectly
                        # typed conflict no longer disappears into quarantine
                        # (start1's dead end); it is delivered below as an
                        # ordinary peer message that simply cannot advance the
                        # formal state machine.
                        self._append_evidence(
                            "formal-candidate-progress",
                            {
                                "event": "invalid-standalone-conflict-delivered-as-ordinary",
                                "state": self._candidate_progress.state,
                                "original_delivery_id": identity.original_delivery_id,
                                "invalid_reply_delivery_id": delivery.delivery_id,
                            },
                        )
                    else:
                        try:
                            self.transport.reopen_formal_reply_slot(
                                original_delivery_id=identity.original_delivery_id,
                                invalid_reply_delivery_id=delivery.delivery_id,
                                modeling_agent_id=modeling,
                                protocol_agent_id=protocol,
                                formal_candidate=True,
                            )
                        except RoutingError as reopen_error:
                            # R2.3-009 B-class: the reopen rejection is recorded as
                            # an observed issue with typed feedback to Protocol; the
                            # invalid response is quarantined and the run continues.
                            self._handle_formal_response_violation(
                                delivery,
                                protocol=protocol,
                                exc=reopen_error,
                            )
                            continue
                        self._append_evidence(
                            "formal-candidate-progress",
                            {
                                "event": "invalid-response-slot-reopened",
                                "state": self._candidate_progress.state,
                                "original_delivery_id": identity.original_delivery_id,
                                "invalid_reply_delivery_id": delivery.delivery_id,
                            },
                        )
                        # An invalid formal response is a transport-level recovery
                        # artifact, not a peer message.  Do not expose free text or
                        # malformed receipt payloads to Modeling: doing so would let
                        # the payload become a second, non-formal reply anchor (for
                        # example, a revision replying to an invalid guidance ID).
                        # The original formal slot was already reopened above, so the
                        # next candidate redrive can elicit one canonical conflict or
                        # receipt from Protocol.
                        self.transport.ack_delivery(delivery.delivery_id)
                        self._append_evidence(
                            "formal-candidate-progress",
                            {
                                "event": "invalid-response-quarantined",
                                "state": self._candidate_progress.state,
                                "original_delivery_id": identity.original_delivery_id,
                                "invalid_reply_delivery_id": delivery.delivery_id,
                            },
                        )
                        continue
            owner_answer = delivery.owner_answer_id is not None
            if delivery.recipient_id in self.transport.results:
                self._append_evidence(
                    "terminal-delivery-blocked",
                    {
                        "sender_id": delivery.sender_id,
                        "recipient_id": delivery.recipient_id,
                        "reason": "recipient already reported terminal result",
                    },
                )
                if owner_answer:
                    self._mark_owner_answer_failure(delivery, "recipient already reported terminal result")
                continue
            if owner_answer:
                runtime_delivery = RuntimeDelivery(
                    sender_id=delivery.sender_id,
                    recipient_id=delivery.recipient_id,
                    kind="owner-answer",
                    text=delivery.text,
                    delivery_id=delivery.delivery_id,
                    expects_reply=delivery.expects_reply,
                    reply_to_delivery_id=delivery.reply_to_delivery_id,
                    owner_answer_id=delivery.owner_answer_id,
                    release_id=delivery.release_id,
                )
            else:
                runtime_delivery = RuntimeDelivery(
                    sender_id=delivery.sender_id,
                    recipient_id=delivery.recipient_id,
                    kind=(
                        "outer-forward"
                        if delivery.sender_id == coordinator
                        and delivery.text in self._outer_user_texts
                        else "peer"
                    ),
                    text=delivery.text,
                    delivery_id=delivery.delivery_id,
                    expects_reply=delivery.expects_reply,
                    reply_to_delivery_id=delivery.reply_to_delivery_id,
                )
            try:
                dispatch_receipt = self.adapter.send_message(delivery.recipient_id, runtime_delivery)
                if formal_candidate_event in {"candidate", "revision"}:
                    assert self._candidate_progress is not None
                    self._candidate_progress.bind_dispatch(
                        dispatch_receipt, now=self.monotonic_clock()
                    )
            except FormalCandidatePlatformContractError:
                self._latch_formal_candidate_failure(
                    "platform-contract", "internal-invariant:turn-binding-missing"
                )
                raise
            except Exception:
                if owner_answer:
                    self._mark_owner_answer_failure(delivery, "Runtime Adapter delivery failed")
                raise
            self.transport.ack_delivery(delivery.delivery_id)
            envelope = {
                "type": "delivery",
                "sequence": delivery.sequence,
                "sender_id": delivery.sender_id,
                "recipient_id": delivery.recipient_id,
                "text": delivery.text,
                "timestamp": delivery.timestamp,
                "delivery_id": delivery.delivery_id,
                "expects_reply": delivery.expects_reply,
                "reply_to_delivery_id": delivery.reply_to_delivery_id,
            }
            if owner_answer:
                envelope.update(
                    {
                        "owner_answer_id": delivery.owner_answer_id,
                        "release_id": delivery.release_id,
                    }
                )
            output.append(envelope)
            self._append_evidence("deliveries", envelope)
            self._observe_modeling_question(delivery)
        results = self.transport.results
        self._finalize_acceptance_if_ready()
        for source_id, result in results.items():
            for recipient_id, dependencies in self.transport.terminal_dependencies.items():
                pair = (recipient_id, source_id)
                if source_id not in dependencies or pair in self._terminal_handoffs_notified:
                    continue
                # A Protocol report can be rejected before its dependency handoff arrives.  The
                # rejection is not a terminal result and must not be fabricated or counted as a
                # second report.  Include one deterministic redrive instruction in the real
                # handoff so the Protocol can retry its own report exactly once after the Broker
                # dependency is satisfied.  The immutable source result remains nested unchanged.
                recipient_role = next(
                    (
                        agent.package.role
                        for agent in self.run.configuration.profile.agents
                        if agent.agent_id == recipient_id
                    ),
                    recipient_id,
                )
                remaining_dependencies = sorted(
                    dependency
                    for dependency in dependencies
                    if dependency not in self.transport.results
                )
                if recipient_role == "protocol":
                    next_action = "retry_report_task_result_once"
                    instruction = (
                        "The Broker has now delivered the required terminal handoff. If your "
                        "earlier report_task_result was rejected for a missing dependency, call "
                        "report_task_result exactly once now; preserve Protocol ownership and "
                        "do not fabricate any other Agent result."
                    )
                elif remaining_dependencies:
                    next_action = "await_remaining_terminal_handoffs"
                    instruction = (
                        "This dependency handoff is recorded. Await every remaining terminal "
                        "handoff before calling report_task_result; do not retry or fabricate a "
                        "Coordinator result yet."
                    )
                else:
                    next_action = "retry_report_task_result_once"
                    instruction = (
                        "The Broker has now delivered all required terminal handoffs. If your "
                        "earlier report_task_result was rejected for a missing dependency, call "
                        "report_task_result exactly once now and preserve every dependency "
                        "summary."
                    )
                handoff = {
                    **result.__dict__,
                    "terminal_result": result.__dict__,
                    "next_action": next_action,
                    "instruction": instruction,
                }
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True)
                self.adapter.send_message(
                    recipient_id,
                    RuntimeDelivery(
                        sender_id="runner/terminal-result",
                        recipient_id=recipient_id,
                        kind="terminal-handoff",
                        text=text,
                    ),
                )
                self._terminal_handoff_sequence += 1
                handoff_id = f"terminal-handoff-{self._terminal_handoff_sequence}"
                delivered = {
                    "type": "terminal-result-handoff",
                    "recipient_id": recipient_id,
                    "source_id": source_id,
                    "handoff_id": handoff_id,
                    "sequence": self._terminal_handoff_sequence * 2 - 1,
                    "result": result.__dict__,
                }
                self._append_evidence("terminal-result-handoff", delivered)
                self.transport.ack_terminal_handoff(recipient_id, source_id)
                self._append_evidence(
                    "terminal-handoff-ack",
                    {
                        "agent": recipient_id,
                        "tool": "ack_terminal_handoff",
                        "status": "accepted",
                        "source_id": source_id,
                        "ack": True,
                        "handoff_id": handoff_id,
                        "sequence": self._terminal_handoff_sequence * 2,
                    },
                )
                output.append(delivered)
                self._terminal_handoffs_notified.add(pair)
        messages = self.adapter.receive_messages()
        failures = self._consume_runtime_failures()
        if failures:
            return self._finalize_runtime_failure(failures)
        try:
            if self._candidate_progress is not None:
                roles = self._formal_candidate_roles()
                states_reader = getattr(self.adapter, "get_agent_states", None)
                if roles is not None and callable(states_reader):
                    _, protocol = roles
                    self._candidate_progress.observe_states(
                        states_reader(), protocol_agent_id=protocol
                    )
                self._maybe_redrive_formal_candidate()
                self._check_formal_candidate_progress()
        except FormalCandidateRoutingError as exc:
            # The redrive quota guard is defensive (redrive_ready already bounds
            # dispatches); a hit is recorded, never a run kill by itself.
            self._append_evidence(
                "formal-candidate-progress",
                {"event": "redrive-guard-rejected", "detail": str(exc)},
            )
        except FormalCandidatePlatformContractError:
            self._latch_formal_candidate_failure(
                "platform-contract", "internal-invariant:turn-binding-missing"
            )
            raise
        for message in messages:
            if message.agent_id == coordinator:
                self._observe_coordinator_message(message)
                if self._post_settlement_reporting_requested:
                    self._capture_coordinator_final(message, output)
                    continue
                envelope = {"type": "coordinator", "text": message.text}
                output.append(envelope)
                self._append_evidence("coordinator", envelope)
        # R2.3-009 start19: the terminal-report guard already lets every role
        # report ``blocked`` when a run is judged unrepairable (the agent-blocked
        # exit), but this gate still demanded a settled Acceptance carrier.  When
        # Acceptance never started (no handoff existed) the carrier can never
        # settle, so a fully agent-blocked run deadlocked here until the T3
        # fallback timeout misclassified it.  A unanimous-blocked result set
        # waives only the Acceptance clause, mirroring the guard's ruling.
        agent_blocked_exit = bool(self.transport.results) and all(
            getattr(result, "status", None) == "blocked"
            for result in self.transport.results.values()
        )
        formal_settlement_ready = (
            not self._formal_coordination_enabled()
            or (
                not (
                    self._issue_ledger() is not None
                    and self._issue_ledger().pending
                )
                and (
                    agent_blocked_exit
                    or (
                        self.acceptance is not None
                        and self.acceptance.is_settled
                    )
                )
            )
        )
        if formal_settlement_ready and not self._terminal_emitted and not self._cq_acceptance_hold_pending() and len(self.transport.results) == len(
            self.run.configuration.profile.agents
        ) and self.adapter.wait_settled(
            [agent.agent_id for agent in self.run.configuration.profile.agents], 1
        ):
            self._terminal_emitted = True
            self.run.terminal_results = {
                key: value.__dict__ for key, value in self.transport.results.items()
            }
            envelope = {
                "type": "settled",
                "results": {
                    key: value.__dict__ for key, value in self.transport.results.items()
                },
            }
            output.append(envelope)
            self._append_evidence("settled", envelope)
            self._state("POST_SETTLEMENT_REPORTING")
            self._post_settlement_reporting_requested = True
            self.adapter.send_message(
                coordinator,
                RuntimeDelivery(
                    sender_id="runner/post-settlement",
                    recipient_id=coordinator,
                    kind="post-settlement",
                    text=self._post_settlement_prompt(envelope["results"]),
                ),
            )
        return output

    def send_coordination(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        message_kind: str,
        text: str = "",
        generation: int,
    ) -> dict[str, Any]:
        """Publish a non-terminal readiness/silence phase event.

        This is intentionally separate from ``report_task_result``.  It allows
        Coordinator to serialize Modeling/Protocol quiet acknowledgements while
        preserving the existing Agent settlement semantics.
        """
        if not self.run or not self.transport or not self.coordinator_phase:
            raise RuntimeError("Runner is not started")
        if not self._formal_coordination_enabled():
            raise TeamConfigurationError("coordination phase is unavailable for this run")
        delivery = self.transport.send_coordination(
            sender_id,
            recipient_id,
            message_kind,
            text,
            generation,
        )
        envelope = {
            "type": "coordination",
            "sender_id": delivery.sender_id,
            "recipient_id": delivery.recipient_id,
            "message_kind": delivery.message_kind,
            "message_id": delivery.message_id,
            "timestamp": delivery.timestamp,
            "terminal": False,
            "settles": False,
            "text_sha256": hashlib.sha256(delivery.text.encode("utf-8")).hexdigest(),
            "phase_event": {
                key: value
                for key, value in (delivery.phase_event or {}).items()
                if key not in {"text", "objective"}
            },
        }
        self._append_evidence("coordination", envelope)
        return envelope

    @staticmethod
    def _post_settlement_prompt(results: dict[str, Any]) -> str:
        return (
            "Runtime settlement is complete. Generate exactly one non-empty user-facing final "
            "summary from this immutable structured terminal-result snapshot. Preserve every "
            "Agent status and summary faithfully; do not call tools, send peer messages, or call "
            "report_task_result again.\nTerminal-result snapshot:\n"
            + json.dumps(results, ensure_ascii=False, sort_keys=True)
        )

    def _capture_coordinator_final(
        self, message: Any, output: list[dict[str, Any]]
    ) -> None:
        if self._coordinator_final_captured or not isinstance(message.text, str):
            return
        text = message.text.strip()
        if not text:
            return
        self._coordinator_final_captured = True
        envelope = {"type": "coordinator", "text": text}
        output.append(envelope)
        self._append_evidence("coordinator-final", envelope)
        self._state("TERMINAL_REPORT_COMPLETE")

    def _cleanup_cq_private(self) -> dict[str, Any] | None:
        """Delete owner-provable CQ private temp, keep every durable artifact.

        Design §5 (Round 1 F6): Delivery/Runner owns cleanup and may remove the
        CQ private working set (draft versions, interview transcripts), but the
        frozen snapshots, the review/decision history, the public projection,
        the acceptance reports and the failure/recovery/cleanup evidence stay.
        An entry whose owner cannot be proven (symlink, foreign uid, or a
        non-regular directory entry) is retained and reported instead of being
        blind-deleted.
        """

        if self.run is None:
            return None
        private_root = self.run.root / "competency-questions" / "private"
        if not private_root.exists():
            return None
        removed: list[str] = []
        retained: list[dict[str, Any]] = []
        try:
            entries = sorted(private_root.iterdir())
        except OSError as exc:
            self._append_evidence("cq-cleanup", {"event": "private-scan-failed", "error": type(exc).__name__})
            return {"removed": [], "retained_unknown_owner": [], "error": type(exc).__name__}
        for entry in entries:
            try:
                metadata = entry.lstat()
            except OSError as exc:
                retained.append({"entry": entry.name, "reason": type(exc).__name__})
                continue
            provable = (
                not stat.S_ISLNK(metadata.st_mode)
                and metadata.st_uid == os.getuid()
                and (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode))
            )
            if not provable:
                retained.append({"entry": entry.name, "reason": "unknown-owner"})
                continue
            if stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(entry, ignore_errors=False)
            else:
                entry.unlink()
            removed.append(entry.name)
        disposable = not retained
        if disposable:
            try:
                private_root.rmdir()
            except OSError:
                disposable = False
        evidence_record = {
            "event": "cq-private-cleanup",
            "removed": removed,
            "retained_unknown_owner": retained,
            "preserved": [
                "competency-questions/frozen",
                "competency-questions/reviews",
                "competency-questions/public",
                "acceptance-v3/reports",
                "evidence",
            ],
            "directory_removed": disposable,
        }
        self._append_evidence("cq-cleanup", evidence_record)
        return {
            "removed_count": len(removed),
            "retained_unknown_owner": retained,
            "directory_removed": disposable,
        }

    def cleanup(self) -> dict[str, Any]:
        if self._cleanup_evidence_cache is not None:
            return deepcopy(self._cleanup_evidence_cache)
        issue_ledger = self._issue_ledger()
        if issue_ledger is not None and issue_ledger.pending and not self._issue_abort_requested:
            active = issue_ledger.active_issue
            paused = {
                "status": "paused",
                "issue_id": active.issue_id if active else None,
                "state": issue_ledger.state,
                "cleanup_deferred": True,
            }
            self._state(
                "WAITING_REPAIR"
                if issue_ledger.state == "waiting_repair"
                else "WAITING_OWNER",
                issue_id=paused["issue_id"],
            )
            return paused
        # 2026-09-14 provider-recovery: a pending provider wait is an observable
        # externally-recoverable state, not run death.  Cleanup is deferred so
        # the live processes, threads, candidates, and evidence survive until
        # recovery or an explicit stop (which sets the stop flag first).
        live_provider_waits = {}
        for agent_id in self._live_provider_wait_agents():
            record = self._provider_wait_registry().get(agent_id)
            if record is None:
                status_reader = getattr(self.adapter, "provider_wait_status", None)
                record = status_reader(agent_id) if callable(status_reader) else None
            if isinstance(record, dict):
                live_provider_waits[agent_id] = record
            else:
                live_provider_waits[agent_id] = {"agent_id": agent_id}
        if (
            live_provider_waits
            and not getattr(self, "_provider_wait_stop_requested", False)
            and not getattr(self, "_issue_abort_requested", False)
        ):
            paused = {
                "status": "paused",
                "provider_waits": sorted(
                    {
                        str(record.get("wait_id"))
                        for record in live_provider_waits.values()
                    }
                ),
                "cleanup_deferred": True,
            }
            self._state(
                "WAITING_OWNER",
                provider_waits=paused["provider_waits"],
            )
            return paused
        evidence: dict[str, Any] = {}
        self._state("CLEANING") if self.run else None
        formal = self._formal_coordination_enabled()
        acceptance_settled = bool(self.acceptance and self.acceptance.is_settled)
        if formal and not acceptance_settled:
            self._state("ABORTING") if self.run else None
        try:
            self.adapter.stop()
            evidence["runtime"] = self.adapter.cleanup_identifiers()
            if self.acceptance:
                if formal and not acceptance_settled:
                    evidence["acceptance"] = self.acceptance.abort_cleanup(
                        "runner-abort-before-settlement"
                    )
                    self._append_evidence(
                        "aborted",
                        {
                            "status": "aborted",
                            "reason": evidence["acceptance"].get("aborted_reason"),
                            "settled": False,
                        },
                    )
                else:
                    evidence["acceptance"] = self.acceptance.cleanup()
        finally:
            if self._modeling_read_lifecycle is not None and self.run is not None:
                key_id = self.run.modeling_read_key_id
                if isinstance(key_id, str) and key_id:
                    try:
                        revoked = self._modeling_read_lifecycle.revoke(key_id)
                        evidence["modeling_read_key"] = {
                            "key_id": revoked.key_id,
                            "status": revoked.status,
                            "revoked_at": revoked.revoked_at,
                            **self._modeling_read_lifecycle.evidence(key_id),
                        }
                    except Exception as exc:
                        evidence["modeling_read_key_cleanup_error"] = type(exc).__name__
                if self._modeling_read_proxy is not None:
                    self._modeling_read_proxy.destroy()
            if self.scope:
                if self.run and self.run.terminal_results:
                    self.scope.terminal_results = self.run.terminal_results
                # R3.0-015 S1 (design §3.3.5): an otherwise-empty owned scope is
                # retained only when at least one fully published, digest-
                # verifying checkpoint package references the run.  A selector
                # flag alone, a failed save or a temp directory never counts.
                checkpoint_retention: dict[str, Any] | None = None
                if self.run is not None:
                    try:
                        checkpoint_retention = scope_retention_reference(self.run.root)
                    except Exception:  # noqa: BLE001 - retention is advisory-only here
                        checkpoint_retention = None
                if checkpoint_retention is not None:
                    self.scope.checkpoint_retention = checkpoint_retention
                evidence["scope"] = self.scope.cleanup()
                if checkpoint_retention is not None:
                    self._append_evidence(
                        CHECKPOINT_EVIDENCE_NAME,
                        {
                            "event": "scope-retention-reference",
                            **checkpoint_retention,
                            "scope_disposition": evidence["scope"].get("scope_disposition"),
                        },
                    )
                if self.run and evidence["scope"].get("scope_disposition") == "retained-pending-acceptance":
                    self._write_retained_handoff_evidence(evidence["scope"])
            if self.transport:
                self.transport.stop()
            if self.run:
                if self._ledger and not (self.run.root / "evidence" / "semantic-start.jsonl").exists():
                    try:
                        self._ledger.release_presemantic(
                            self.run.run_id, "startup-config: runner cleanup before semantic start"
                        )
                        self._append_evidence(
                            "start-ledger",
                            {
                                "event": "presemantic_release",
                                **self._formal_ledger_identity(),
                            },
                        )
                    except TeamConfigurationError:
                        # Startup failure may already have recorded the same immutable correction.
                        pass
                self._record_terminal_settlement_and_refund()
                secrets = self.run.root / "secrets"
                if secrets.exists():
                    shutil.rmtree(secrets)
                    evidence["secrets_destroyed"] = True
                evidence["cq_private_cleanup"] = self._cleanup_cq_private()
                # R3.0-012 (design §4.5): stop/failure exit closes every CQ
                # wait window while preserving the accumulated exclusion
                # evidence, so an exit leaves no window that still reads as
                # open and no exclusion interval is silently dropped.
                now = (getattr(self, "monotonic_clock", None) or time.monotonic)()
                closed_windows: list[str] = []
                if self._cq_wait_windows.has_open_window:
                    closed_windows = self._cq_wait_windows.open_kinds()
                    self._cq_wait_windows.close_all(now)
                evidence["cq_wait_windows"] = self._cq_wait_windows.evidence(now)
                if closed_windows:
                    self._append_evidence(
                        "cq-wait-windows",
                        {
                            "event": "closed-on-exit",
                            "closed_windows": closed_windows,
                            **evidence["cq_wait_windows"],
                        },
                    )
                self._record_runtime_core_hashes("after_cleanup")
                self._state(
                    "CLEANED",
                    cleanup=evidence,
                    terminal_results=self.run.terminal_results,
                )
        if self.run is None:
            return evidence
        self._cleanup_evidence_cache = deepcopy(evidence)
        return deepcopy(self._cleanup_evidence_cache)

    def _record_terminal_settlement_and_refund(self) -> None:
        """R2.3-009 budget bookkeeping: settlement marker plus eligible refund.

        Agent-terminal runs (every Agent reported completed/blocked) close the
        consumed start with ``terminal_settlement``; a blocked exit or a T3
        run-fallback terminal failure appends one ``budget_refund``. Every other
        outcome keeps the consumed start. Failures here are recorded evidence,
        never a cleanup abort.
        """

        if not self.run or not getattr(self, "_ledger", None):
            return
        if not (self.run.root / "evidence" / "semantic-start.jsonl").exists():
            return
        results = getattr(self.run, "terminal_results", None) or {}
        statuses = [
            value.get("status")
            for value in results.values()
            if isinstance(value, dict)
        ]
        if statuses:
            outcome = "agent_blocked" if "blocked" in statuses else "agent_completed"
            try:
                self._ledger.record_terminal_settlement(  # type: ignore[union-attr]
                    self.run.run_id, outcome=outcome
                )
            except TeamConfigurationError as exc:
                self._append_evidence(
                    "start-ledger",
                    {
                        "event": "terminal_settlement_skipped",
                        "outcome": outcome,
                        "detail": str(exc),
                        **self._formal_ledger_identity(),
                    },
                )
            else:
                self._append_evidence(
                    "start-ledger",
                    {
                        "event": "terminal_settlement",
                        "outcome": outcome,
                        **self._formal_ledger_identity(),
                    },
                )
        try:
            refunded = self._ledger.refund_budget(self.run.run_id)  # type: ignore[union-attr]
        except TeamConfigurationError as exc:
            self._append_evidence(
                "start-ledger",
                {
                    "event": "budget_refund_skipped",
                    "detail": str(exc),
                    **self._formal_ledger_identity(),
                },
            )
            return
        if refunded:
            self._append_evidence(
                "start-ledger",
                {"event": "budget_refund", **self._formal_ledger_identity()},
            )

    def _record_runtime_core_hashes(self, phase: str) -> None:
        self._append_evidence(
            "runtime-core-hashes",
            {
                "phase": phase,
                "runner_sha256": digest_file(self.repository_root / "modeling_team/runner.py"),
                "codex_adapter_sha256": digest_file(
                    self.repository_root / "modeling_team/runtimes/codex.py"
                ),
                "capability_mcp_sha256": digest_file(
                    self.repository_root / "modeling_team/capability_mcp.py"
                ),
                "transport_mcp_sha256": digest_file(
                    self.repository_root / "modeling_team/transport_mcp.py"
                ),
                "transport_interventions_sha256": digest_file(
                    self.repository_root / "modeling_team/interventions.py"
                ),
            },
        )

    def _state(self, value: str, **extra: Any) -> None:
        if self.run:
            self._atomic_json(
                self.run.root / "state.json",
                {"state": value, "run_id": self.run.run_id, **extra},
            )

    def _write_retained_handoff_evidence(self, scope: dict[str, Any]) -> None:
        """Freeze the non-semantic offline-handoff inputs exactly once after cleanup."""
        assert self.run
        required = ("project_id", "ontology_id", "workspace_version", "completed_session_id")
        if scope.get("owned") is not True or scope.get("scope_disposition") != "retained-pending-acceptance":
            raise TeamConfigurationError("retained scope evidence is not a successful owned producer")
        if (
            scope.get("mode") != "create"
            or scope.get("sessions_terminal") is not True
            or scope.get("protocol_key_revoked") is not True
            or scope.get("admin_key_revoked") is not True
        ):
            raise TeamConfigurationError("retained scope cleanup safety gate is incomplete")
        # R3.0-006 M3: a multi-Ontology retained scope records the aggregate
        # ontology set (workspace version and completed Build Session per
        # planned Ontology) instead of the single-Ontology tuple.
        ontology_ids = scope.get("ontology_ids")
        if isinstance(ontology_ids, list) and len(ontology_ids) > 1:
            versions = scope.get("workspace_versions")
            sessions = scope.get("completed_session_ids")
            if (
                not isinstance(scope.get("project_id"), str)
                or not scope["project_id"]
                or not isinstance(versions, dict)
                or not isinstance(sessions, dict)
                or set(versions) != set(ontology_ids)
                or set(sessions) != set(ontology_ids)
                or any(
                    not isinstance(versions.get(ontology_id), str)
                    or not versions[ontology_id]
                    or not isinstance(sessions.get(ontology_id), str)
                    or not sessions[ontology_id]
                    for ontology_id in ontology_ids
                )
            ):
                raise TeamConfigurationError("retained multi-Ontology scope evidence is incomplete")
            scope_fields = {
                "project_id": scope["project_id"],
                "ontology_id": scope["ontology_id"],
                "ontology_ids": list(ontology_ids),
                "workspace_versions": {key: versions[key] for key in ontology_ids},
                "completed_session_ids": {key: sessions[key] for key in ontology_ids},
                "scope_disposition": scope["scope_disposition"],
                "owned": True,
            }
        else:
            if any(not isinstance(scope.get(field), str) or not scope[field] for field in required):
                raise TeamConfigurationError("retained scope evidence is incomplete")
            scope_fields = {
                field: scope[field] for field in (*required, "scope_disposition", "owned")
            }
        results = self._completed_terminal_statuses(self.run.terminal_results)
        payload = {
            "run_id": self.run.run_id,
            "terminal_statuses": results,
            "scope": scope_fields,
        }
        path = self.run.root / "evidence" / "retained-handoff-input.json"
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            raise TeamConfigurationError("retained handoff evidence is immutable") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o444)

    def _completed_terminal_statuses(self, results: Any) -> dict[str, str]:
        # R3.0-006 M2: the completed-status contract is derived from the
        # Profile's actual role set (e.g. the three-role multi-slice roster)
        # instead of a hard-coded four-role requirement.  Doubles without a
        # configuration keep the historical four-role default.
        configuration = getattr(self.run, "configuration", None)
        profile = getattr(configuration, "profile", None) if configuration is not None else None
        agents = getattr(profile, "agents", None) if profile is not None else None
        roles = (
            {agent.package.role for agent in agents}
            if agents
            else {"coordinator", "modeling", "protocol", "acceptance"}
        )
        if (
            not isinstance(results, dict)
            or set(results) != roles
            or any(not isinstance(value, dict) or value.get("status") != "completed" for value in results.values())
        ):
            raise TeamConfigurationError(
                "retained scope requires every Profile Agent status completed"
            )
        return {role: "completed" for role in sorted(roles)}

    # --- R3.0-015 S1: checkpoint save/inspect ---------------------------------
    #
    # Save/inspect helpers implement segment S1 (design §3); segment S2
    # (cross-process production resume, design §4-§6) lives in the section
    # above through ``prepare_from_checkpoint``, and segment S4 (acceptance
    # continuation of a production_handoff, design §7) is delivered by
    # ``checkpoint_recovery`` / the CLI without touching this Runner.
    # ``checkpoints.CHECKPOINT_DELIVERY_SEGMENTS`` records that boundary for
    # every inspection result.

    def _checkpoint_spec(
        self,
        source: str,
        owner: str,
        *,
        host_private: bool = False,
        host_only: bool = False,
    ) -> CheckpointArtifactSpec:
        visible_to: tuple[str, ...]
        if host_only:
            visible_to = ("host",)
        elif host_private:
            visible_to = ("host", COMPETENCY_QUESTION_ROLE)
        else:
            # Production-visible entries keep the per-role projection open to
            # the CQ authoring role as well; only ownership is recorded here.
            visible_to = (*PRODUCTION_ROLES, COMPETENCY_QUESTION_ROLE)
        return CheckpointArtifactSpec(
            source=source, owner=owner, visible_to=visible_to, host_private=host_private
        )

    def _checkpoint_directory_sources(self, directory: Path, pattern: str) -> list[str]:
        """Run-relative posix sources for existing regular files (sorted)."""

        if not directory.is_dir():
            return []
        return sorted(
            path.relative_to(self.run.root).as_posix()
            for path in directory.glob(pattern)
            if path.is_file() and not path.is_symlink()
        )

    def _checkpoint_configuration(self) -> dict[str, Any]:
        """The manifest 配置 group: identity, parameters and frozen contracts."""

        config = self.run.configuration
        configuration: dict[str, Any] = {
            "task_id": config.task.task_id,
            "profile_id": config.profile.profile_id,
            "task_parameters": dict(config.task.parameters or {}),
            "unified_semantic_graph": bool(self._unified_graph),
            "acceptance_target": self._acceptance_target,
            "model_profile_id": (
                self.run.team_model_profile.profile_id
                if self.run.team_model_profile is not None
                else None
            ),
            "configuration_files": [],
        }
        for name in (
            "profile.snapshot.yaml",
            "task.snapshot.yaml",
            "task-overlay.snapshot.yaml",
        ):
            path = self.run.root / name
            if path.is_file() and not path.is_symlink():
                configuration["configuration_files"].append(
                    {"path": name, "digest": checkpoint_file_digest(path)}
                )
        return configuration

    def _checkpoint_write_positions(
        self, admission_snapshot: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """The manifest 写入位置 group: a point-in-time intents/receipts join.

        Deliberately timestamp-free: the dedup signature covers write
        positions, so a wall clock here would mint a new package per save
        (design §3.4).  The record states what was observable at save time and
        never claims anything about future writes.
        """

        positions: list[dict[str, Any]] = []
        if self._staged_decisions:
            try:
                intents = read_submission_intents(self.run.root)
                receipts = read_submission_receipts(self.run.root)
            except StagedDecisionArtifactError:
                intents, receipts = [], []
            receipt_by_key = {
                receipt.get("idempotency_key"): receipt
                for receipt in receipts
                if receipt.get("idempotency_key")
            }
            for intent in intents:
                key = intent.get("idempotency_key")
                receipt = receipt_by_key.get(key)
                if intent.get("status") == "unknown":
                    state = "unknown"
                elif receipt is not None or intent.get("status") == "receipted":
                    # dry-run validated is NOT applied (requirement §阶段 4).
                    state = (
                        "applied" if intent.get("mode") == "apply" else "validated_not_applied"
                    )
                else:
                    state = "pending"
                positions.append(
                    {
                        "ordinal": intent.get("ordinal"),
                        "idempotency_key": key,
                        "client_batch_id": intent.get("client_batch_id"),
                        "session_id": intent.get("session_id"),
                        "mode": intent.get("mode"),
                        "state": state,
                        "receipt_ordinal": receipt.get("ordinal") if receipt else None,
                        "batch_id": receipt.get("batch_id") if receipt else None,
                    }
                )
        snapshot = admission_snapshot or {}
        return {
            "positions": positions,
            "in_flight": [dict(item) for item in snapshot.get("in_flight") or []],
            "unknown": [
                {"ticket": record.get("ticket"), "kind": record.get("kind")}
                for record in snapshot.get("records") or []
                if record.get("outcome") == "unknown"
            ],
            "note": "point-in-time snapshot of durable intents/receipts; dry-run "
            "validated is not applied and nothing is claimed about future writes",
        }

    def _checkpoint_count_marker(self, value: Any, marker: str) -> int:
        """Count string values equal to ``marker`` anywhere in a parsed artifact."""

        if isinstance(value, str):
            return 1 if value == marker else 0
        if isinstance(value, Mapping):
            return sum(self._checkpoint_count_marker(item, marker) for item in value.values())
        if isinstance(value, (list, tuple)):
            return sum(self._checkpoint_count_marker(item, marker) for item in value)
        return 0

    def _checkpoint_load_json(self, source: str) -> Any:
        try:
            return json.loads((self.run.root / source).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _collect_checkpoint_stage(
        self, kind: str, scope_refs: Mapping[str, Any]
    ) -> StagePackage:
        """Build one per-kind stage package from the run's actual disk state.

        Only explicitly listed published artifacts are ever packaged; each kind
        declares the minimum evidence it needs, and a missing minimum raises
        the typed ``checkpoint_missing_artifact`` rejection so a bare "phase
        complete" claim can never produce a package (design §3.1).
        """

        root = self.run.root
        specs: list[CheckpointArtifactSpec] = []
        bindings: list[dict[str, str]] = []
        pending: list[str] = []

        def add(source: str, owner: str, **flags: Any) -> None:
            specs.append(self._checkpoint_spec(source, owner, **flags))

        def bind(source: str) -> None:
            bindings.append(
                {
                    "artifact": source,
                    "digest": checkpoint_file_digest(root / source),
                }
            )

        def require(present: bool, what: str) -> None:
            raise CheckpointError(
                "checkpoint_missing_artifact",
                f"cannot save {kind}: no published {what} exists in this run; a "
                "stage-complete claim without artifacts is not a saveable stage "
                "result",
                obj=what,
                phase="checkpoint-save",
                retryable=True,
                retry=f"publish the {what} artifact first, then retry this save",
            )

        # --- shared published material (packaged only when present) ---
        scenario_sources = [
            f"scenario-map/{name}"
            for name in (
                "scenario-map.json",
                "topology-decision.json",
                "protection-iri-suggestions.json",
            )
            if (root / "scenario-map" / name).is_file()
            and not (root / "scenario-map" / name).is_symlink()
        ]
        topology_present = "scenario-map/topology-decision.json" in scenario_sources
        interviews = self._checkpoint_directory_sources(
            root / "competency-questions" / "private", "interview-*.json"
        )
        drafts = self._checkpoint_directory_sources(
            root / "competency-questions" / "private", "draft-*.json"
        )
        review_snapshots = self._checkpoint_directory_sources(
            root / "competency-questions" / "reviews", "cq-review-*.json"
        )
        review_decisions = self._checkpoint_directory_sources(
            root / "competency-questions" / "reviews", "decision-*.json"
        )
        projections = self._checkpoint_directory_sources(
            root / "competency-questions" / "public", "public-projection-*.json"
        )
        freezes = self._checkpoint_directory_sources(
            root / "competency-questions" / "frozen", "freeze-*.json"
        )
        staged_paths = staged_decision_artifact_paths(root, unified=bool(self._unified_graph))

        def staged_source(key: str) -> str | None:
            path = staged_paths.get(key)
            if path is not None and path.is_file() and not path.is_symlink():
                return path.relative_to(root).as_posix()
            return None

        conclusions = staged_source("conclusions")
        unlock = staged_source("unlock")
        approvals = staged_source("approvals")
        ledger = staged_source("ledger")
        checklist = staged_source("checklist")
        stage3_slot = staged_source("stage3_slot")
        candidates = self._checkpoint_directory_sources(
            root / "stage3-neutral-graph" / "candidates", "*.json"
        )
        plans = self._checkpoint_directory_sources(
            root / "stage3-neutral-graph" / "materialization-plans", "*.json"
        )
        intents = self._checkpoint_directory_sources(
            staged_paths["intents_dir"], "intent-*.json"
        )
        receipts = self._checkpoint_directory_sources(
            staged_paths["receipts_dir"], "receipt-*.json"
        )

        def add_cq_material() -> None:
            for source in freezes:
                add(source, "host", host_private=True)
            for source in interviews + drafts + review_snapshots + review_decisions:
                add(source, "competency-question", host_private=True)
            for source in projections:
                add(source, "competency-question")

        def add_scenario_material() -> None:
            for source in scenario_sources:
                add(source, "coordinator")

        def add_staged_material(*, include_intents: bool) -> None:
            for source in candidates + plans:
                add(source, "modeling")
            for source in (conclusions, unlock, approvals, ledger, checklist, stage3_slot):
                if source is not None:
                    add(source, "coordinator")
            if include_intents:
                for source in intents + receipts:
                    add(source, "protocol")

        if kind == CHECKPOINT_KIND_SCENARIO_MAPPED:
            # The kind needs one published pre-CQ stage result: an accepted
            # scenario/slice decision or a confirmed interview.  CQ drafts and
            # reviews ride along with their real review state; unreviewed
            # drafts are never packaged as approved anything (requirement §1).
            add_scenario_material()
            add_cq_material()
            if not scenario_sources and not interviews:
                require(bool(scenario_sources or interviews), "scenario/interview decision")
            if "scenario-map/scenario-map.json" in scenario_sources:
                bind("scenario-map/scenario-map.json")
            if self._competency_questions and not freezes:
                pending.append("cq_freeze")
            if not topology_present:
                pending.append("topology_decision")
            pending.append("semantic_modeling")
            stage_facts: dict[str, Any] = {
                "stage": kind,
                "cq_phase": self._cq_phase,
                "cq_frozen": bool(freezes),
                "topology_decided": topology_present,
                "bindings": bindings,
                "pending": pending,
                "next_step": "continue the not-yet-completed CQ review, slice "
                "analysis or topology decision without redoing the confirmed "
                "interviews and published decisions",
            }
            default_scope: dict[str, Any] = {}
        elif kind == CHECKPOINT_KIND_CQ_FROZEN:
            if not freezes:
                require(bool(freezes), "frozen CQ pool")
            if not projections:
                require(bool(projections), "public CQ projection")
            add_scenario_material()
            add_cq_material()
            freeze_source = freezes[-1]
            bind(freeze_source)
            freeze_payload = self._checkpoint_load_json(freeze_source)
            if not topology_present:
                pending.append("topology_decision")
            pending.append("semantic_modeling")
            stage_facts = {
                "stage": kind,
                "freeze_ref": freeze_source,
                "freeze_id": (
                    freeze_payload.get("batch_id")
                    if isinstance(freeze_payload, Mapping)
                    else None
                ),
                "cq_phase": self._cq_phase,
                "topology_decided": topology_present,
                "bindings": bindings,
                "pending": pending,
                "next_step": "continue topology decision and semantic modeling "
                "without regenerating or re-reviewing the frozen pool",
            }
            default_scope = {
                "freeze_id": (
                    freeze_payload.get("batch_id")
                    if isinstance(freeze_payload, Mapping)
                    else freeze_source
                )
            }
        elif kind == CHECKPOINT_KIND_SEMANTIC_APPROVED:
            if approvals is None:
                require(approvals is not None, "staged value-semantics approvals")
            if conclusions is None and not candidates:
                require(
                    bool(conclusions or candidates),
                    "analysis conclusions or unified candidates",
                )
            add_scenario_material()
            add_cq_material()
            add_staged_material(include_intents=False)
            if approvals is not None:
                bind(approvals)
            if conclusions is not None:
                bind(conclusions)
            analyzed = 0
            if conclusions is not None:
                analyzed = self._checkpoint_count_marker(
                    self._checkpoint_load_json(conclusions), "analyzed_not_materialized"
                )
            if analyzed and unlock is None:
                pending.append("value_materialization")
            pending.append("remaining_semantics")
            stage_facts = {
                "stage": kind,
                "approvals_present": True,
                "candidate_count": len(candidates),
                "analyzed_not_materialized": analyzed,
                "bindings": bindings,
                "pending": pending,
                "next_step": "continue remaining semantics, value confirmation "
                "or translation; undecided content stays pending",
            }
            default_scope = {}
        elif kind == CHECKPOINT_KIND_MATERIALIZATION_PROGRESS:
            if not receipts:
                require(bool(receipts), "confirmed staged batch receipt")
            if not intents:
                require(bool(intents), "staged submission intent")
            add_scenario_material()
            add_cq_material()
            add_staged_material(include_intents=True)
            latest_receipt = receipts[-1]
            bind(latest_receipt)
            receipt_payload = self._checkpoint_load_json(latest_receipt)
            stage_facts = {
                "stage": kind,
                "receipt_count": len(receipts),
                "intent_count": len(intents),
                "plan_count": len(plans),
                "latest_receipt": latest_receipt,
                "latest_batch_id": (
                    receipt_payload.get("batch_id")
                    if isinstance(receipt_payload, Mapping)
                    else None
                ),
                "bindings": bindings,
                "pending": pending,
                "next_step": "continue the remaining dry-run correction, "
                "translation review or apply operations",
            }
            default_scope = {
                "batch_id": (
                    receipt_payload.get("batch_id")
                    if isinstance(receipt_payload, Mapping)
                    else None
                )
            }
        elif kind == CHECKPOINT_KIND_PRODUCTION_HANDOFF:
            handoff_source = "acceptance-v3/production-handoff.json"
            contract_source = "acceptance-v3/run-contract.json"
            handoff_path = root / handoff_source
            if not handoff_path.is_file() or handoff_path.is_symlink():
                require(handoff_path.is_file(), "production handoff")
            if not (root / contract_source).is_file():
                require((root / contract_source).is_file(), "run contract")
            handoff_payload = self._checkpoint_load_json(handoff_source)
            # M04: the handoff is saved because of its evidence fields, never
            # because a ``ready`` boolean is true.
            for field in (
                "freeze_id",
                "freeze_digest",
                "scope_binding",
                "applied_batches",
                "unknown_writes",
                "write_phase",
            ):
                if not isinstance(handoff_payload, Mapping) or field not in handoff_payload:
                    raise CheckpointError(
                        "checkpoint_missing_artifact",
                        f"cannot save {kind}: the production handoff lacks the "
                        f"evidence field {field!r}",
                        obj="production-handoff",
                        phase="checkpoint-save",
                        retryable=True,
                        retry="republish a complete production handoff first",
                    )
            if handoff_payload.get("unknown_writes"):
                raise CheckpointError(
                    "checkpoint_write_unreconciled",
                    "cannot save {kind}: the production handoff itself records "
                    "unknown writes".format(kind=kind),
                    obj="production-handoff",
                    phase="checkpoint-save",
                    retryable=True,
                    retry="reconcile the unknown writes through the existing "
                    "reconciliation path, then retry this save",
                )
            add(handoff_source, "host", host_private=True, host_only=True)
            add(contract_source, "host", host_private=True, host_only=True)
            add_scenario_material()
            add_cq_material()
            add_staged_material(include_intents=True)
            bind(handoff_source)
            stage_facts = {
                "stage": kind,
                "freeze_id": handoff_payload.get("freeze_id"),
                "freeze_digest": handoff_payload.get("freeze_digest"),
                "acceptance_target": handoff_payload.get("acceptance_target"),
                "applied_batch_count": len(handoff_payload.get("applied_batches") or []),
                "not_applied_count": len(handoff_payload.get("not_applied") or []),
                "bindings": bindings,
                "pending": [],
                "next_step": "continue independent acceptance from the handoff "
                "with ``checkpoint resume --mode acceptance`` (segment S4); a "
                "live run may also use the cq-acceptance entry directly",
            }
            default_scope = {
                "freeze_id": handoff_payload.get("freeze_id"),
                "acceptance_attempt_id": handoff_payload.get("acceptance_attempt_id"),
            }
        else:  # pragma: no cover - guarded by the caller's CHECKPOINT_KINDS gate
            raise CheckpointError(
                "checkpoint_invalid_kind",
                f"unknown checkpoint kind {kind!r}",
                obj="kind",
                retryable=False,
            )
        for name in (
            "profile.snapshot.yaml",
            "task.snapshot.yaml",
            "task-overlay.snapshot.yaml",
        ):
            if (root / name).is_file() and not (root / name).is_symlink():
                add(name, "host", host_private=True)
        return StagePackage(
            kind=kind,
            scope_refs=dict(scope_refs) if scope_refs else default_scope,
            artifacts=specs,
            stage_facts=stage_facts,
            platform_bindings=self._checkpoint_platform_bindings(),
            write_positions={},
        )

    def _checkpoint_platform_bindings(self) -> dict[str, Any]:
        """The manifest 平台绑定 group: the real scope identity (design §3.2).

        Reads the actual PlatformScope fields — the same identity the recovery
        entry re-attaches — never a detached stand-in.  A run whose scope is
        not bound records no identity: nothing is fabricated from resource
        names or request text.
        """

        bindings: dict[str, Any] = {"run_scope": dict(self.run.scope or {})}
        scope = self.scope
        project_id = getattr(scope, "project_id", None)
        ontology_id = getattr(scope, "ontology_id", None)
        ontology_ids = [
            item for item in getattr(scope, "ontology_ids", None) or [] if item
        ]
        if not ontology_ids and isinstance(ontology_id, str) and ontology_id:
            # Single-Ontology scope (R2.3 create/existing paths): the bound
            # Ontology is the full verified set the recovery entry reloads
            # (design §5.2 loads ``ontology_ids`` into the existing path).
            ontology_ids = [ontology_id]
        if isinstance(project_id, str) and project_id:
            bindings["project_id"] = project_id
        if ontology_ids:
            bindings["ontology_ids"] = ontology_ids
        if isinstance(ontology_id, str) and ontology_id:
            bindings["ontology_id"] = ontology_id
        if self.run.team_model_profile is not None:
            bindings["model_profile_digest"] = self.run.team_model_profile.digest
        return bindings

    def _save_run_checkpoint(
        self,
        kind: str,
        *,
        scope_refs: Mapping[str, Any] | None = None,
        trigger: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Save one checkpoint, enforcing the M07 write-claim gate (§3.3.2–3.3.3)."""

        if not self._modeling_checkpoints or self.run is None:
            raise CheckpointError(
                "checkpoint_selector_required",
                "this run did not enable modeling_checkpoints",
                obj="modeling_checkpoints",
                phase="checkpoint-save",
                retryable=False,
                retry="start a run from a v3 Task declaring "
                "parameters.modeling_checkpoints: true",
            )
        if kind not in CHECKPOINT_KINDS:
            raise CheckpointError(
                "checkpoint_invalid_kind",
                f"checkpoint kind must be one of {list(CHECKPOINT_KINDS)}",
                obj="kind",
                retryable=False,
            )
        package = self._collect_checkpoint_stage(kind, scope_refs or {})
        write_positions: dict[str, Any]
        if kind in WRITE_CLAIMING_KINDS:
            # §3.3.2: the reversible capture barrier briefly blocks new
            # admissions while the write positions are read; §3.3.3: with
            # in-flight or unknown writes no recoverable-write claim package
            # is published — the specific wait reason is returned instead.
            captured = self._cq_write_admission.begin_capture()
            try:
                if not self._cq_write_admission.wait_until_drained(
                    _CQ_WRITE_DRAIN_TIMEOUT_SECONDS
                ):
                    raise CheckpointError(
                        "checkpoint_write_unreconciled",
                        "in-flight staged writes did not settle within the "
                        "bounded drain wait; refusing to capture a recoverable "
                        "write state",
                        obj="write_positions",
                        phase="checkpoint-save",
                        retryable=True,
                        retry="wait for the in-flight staged writes to settle, "
                        "then retry this save",
                    )
                admission_snapshot = self._cq_write_admission.snapshot()
                write_positions = self._checkpoint_write_positions(admission_snapshot)
            finally:
                if captured:
                    self._cq_write_admission.end_capture()
            unsettled = [
                item
                for item in write_positions.get("positions") or []
                if item.get("state") in {"pending", "unknown", "in_flight"}
            ]
            if (
                write_positions.get("in_flight")
                or write_positions.get("unknown")
                or unsettled
            ):
                raise CheckpointError(
                    "checkpoint_write_unreconciled",
                    f"staged writes are still in flight or unknown "
                    f"({len(write_positions.get('in_flight') or [])} in flight, "
                    f"{len(write_positions.get('unknown') or [])} unknown, "
                    f"{len(unsettled)} unsettled intents); refusing to publish a "
                    "recoverable-write claim",
                    obj="write_positions",
                    phase="checkpoint-save",
                    retryable=True,
                    retry="let the staged writes settle through the existing "
                    "reconciliation path, then retry this save",
                )
        else:
            # Non-write-claiming kinds still record the honestly observed
            # write state without gating the save on it.
            write_positions = self._checkpoint_write_positions(
                self._cq_write_admission.snapshot()
            )
        package.write_positions = write_positions
        result = save_checkpoint(
            self.run.root,
            package,
            source_run_id=self.run.run_id,
            configuration=self._checkpoint_configuration(),
            request_id=request_id,
        )
        self._append_evidence(
            CHECKPOINT_EVIDENCE_NAME,
            {
                "event": f"checkpoint-{result['status']}",
                "kind": kind,
                "trigger": trigger,
                **({"request_id": request_id} if request_id else {}),
                "checkpoint_id": result["checkpoint_id"],
                "manifest_digest": result["manifest_digest"],
                "artifact_count": result["artifact_count"],
                "scope_refs": dict(package.scope_refs),
            },
        )
        return result

    def _save_checkpoint_after_trigger(
        self, kind: str, *, trigger: str, scope_refs: Mapping[str, Any] | None = None
    ) -> None:
        """Best-effort automatic save at an existing publication point (§3.1).

        A failed save never terminates the run and never rolls back the stage
        event itself: the typed reason lands in checkpoint evidence and the
        previously published checkpoint stays readable (design §3.3.4).
        """

        if not self._modeling_checkpoints or self.run is None:
            return
        try:
            self._save_run_checkpoint(kind, scope_refs=scope_refs, trigger=trigger)
        except CheckpointError as error:
            self._append_evidence(
                CHECKPOINT_EVIDENCE_NAME,
                {
                    "event": "checkpoint-save-failed",
                    "kind": kind,
                    "trigger": trigger,
                    **error.data(),
                },
            )
        except OSError as error:
            self._append_evidence(
                CHECKPOINT_EVIDENCE_NAME,
                {
                    "event": "checkpoint-save-failed",
                    "kind": kind,
                    "trigger": trigger,
                    # Same §8 key shape as the CheckpointError branch above
                    # (design §8); an I/O failure carries the save-side phase
                    # literal and only the exception class name, never a path.
                    "code": "checkpoint_write_failed",
                    "object_ref": "checkpoints",
                    "phase": "checkpoint-save",
                    "retryable": True,
                    "reason": type(error).__name__,
                    "next_action": "retry the save once the transient I/O "
                    "failure clears; the previously published checkpoint "
                    "stays readable",
                },
            )

    # --- R3.0-015 S2: cross-process production resume ---------------------------

    def prepare_from_checkpoint(
        self,
        *,
        source_run_root: Path,
        checkpoint_id: str,
        new_run_id: str,
        readback: PlatformReadback | None = None,
        authorization_reference: str | None = None,
    ) -> TeamRun:
        """Resume production from a published checkpoint (design §4.2).

        Read-only reconciliation first (the same entry the host can call
        before any credential bootstrap), then the normal ``prepare`` creates
        the NEW run root — never over an existing directory — and the
        recovery materialization restores artifacts, writes the recovery
        records, recomputes validators and loads the imported completion
        index.  Transport/terminal/deadline stay fresh: nothing replays the
        old delivery queue or imports old completed reports as new terminal
        reports.
        """

        if self.run is not None or not self._safe_run_id(new_run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        if readback is None:
            if not self.canonical_admin_key or not self.canonical_base_url:
                raise TeamConfigurationError(
                    "resume needs the host platform credential channel "
                    "(canonical base URL and admin key)"
                )
            readback = http_readback(self.canonical_base_url, self.canonical_admin_key)
        plan = prepare_recovery_plan(
            source_run_root=source_run_root,
            checkpoint_id=checkpoint_id,
            new_run_id=new_run_id,
            repository_root=self.repository_root,
            readback=readback,
            authorization_reference=authorization_reference,
        )
        configuration = plan.manifest.get("configuration") or {}
        run = self.prepare(
            run_id=plan.new_run_id,
            profile_path=plan.profile_path,
            task_path=plan.task_path,
            scope=plan.scope,
            model_profile_id=configuration.get("model_profile_id"),
        )
        self._materialize_checkpoint_recovery(plan)
        return run

    def _materialize_checkpoint_recovery(self, plan: RecoveryPlan) -> None:
        """Project the reconciled checkpoint into the new run (design §4.2 table).

        Artifacts land at their original run-relative paths (digest-verified),
        the recovery records are host-owned, staged validators are RECOMPUTED
        from the restored files — never a restored boolean gate-open — and the
        CQ frozen pool is re-validated and adopted rather than trusted.  The
        exposure union across the recovery chain is written before any role
        could start, so a once-exposed question can never become hidden again.
        """

        if self.run is None:
            raise TeamConfigurationError("Runner is not prepared")
        root = self.run.root
        restored = restore_checkpoint_artifacts(plan.manifest, plan.source_run_root, root)
        artifacts = [
            artifact
            for artifact in plan.manifest.get("artifacts") or []
            if isinstance(artifact, Mapping)
        ]

        exposure: dict[str, Any] | None = None
        cq_material = any(
            str(artifact.get("source") or "").startswith("competency-questions/")
            for artifact in artifacts
        )
        if cq_material:
            exposure = merge_exposure_union(plan.chain_roots, root)
            self._cq_merge_exposure_evidence()

        freeze_restored = False
        # Every stage kind packages the frozen pool once a freeze exists
        # (``add_cq_material``), so the restore is keyed on the packaged,
        # digest-verified frozen file, never on the kind label: a later-stage
        # resume (semantic_approved, materialization_progress,
        # production_handoff) must adopt the same freeze state, or the staged
        # write channel would reject the very freeze it exists to require.
        freeze_sources = [
            str(artifact.get("source"))
            for artifact in artifacts
            if str(artifact.get("source") or "").startswith("competency-questions/frozen/freeze-")
        ]
        if self._competency_questions and freeze_sources:
            payload_path = root.joinpath(*freeze_sources[-1].split("/"))
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                # A stored freeze record is not its own freeze input: it carries
                # ``snapshot_digest`` and Runner-owned ``visibility`` stamps.
                # ``reload_frozen_pool`` rebuilds the freeze from the file,
                # recomputes the digest and rejects any post-freeze edit.
                snapshot = reload_frozen_pool(payload)
            except (OSError, json.JSONDecodeError, CQContractError) as exc:
                raise CheckpointError(
                    "artifact_changed",
                    f"the packaged frozen pool failed re-validation ({exc})",
                    obj=freeze_sources[-1],
                    phase="checkpoint-resume",
                    retryable=True,
                    retry="re-save the checkpoint from a stable frozen pool",
                ) from exc
            self._cq_freeze = snapshot
            self._cq_phase = "frozen"
            freeze_restored = True
        elif plan.manifest.get("kind") == CHECKPOINT_KIND_CQ_FROZEN and self._competency_questions:
            raise CheckpointError(
                "checkpoint_incomplete",
                "a cq_frozen checkpoint packages no frozen pool",
                obj="competency-questions/frozen",
                phase="checkpoint-resume",
            )
        elif plan.manifest.get("kind") == CHECKPOINT_KIND_SCENARIO_MAPPED:
            # §4.2: scenario_mapped restores the ACTUAL draft/review phase; the
            # freeze state deliberately stays empty — unless the package
            # carried a re-validated frozen pool (the branch above), which is
            # real reviewed state, not a fabricated review or re-interview.
            self._cq_freeze = None
            recorded_phase = (plan.manifest.get("stage_facts") or {}).get("cq_phase")
            if isinstance(recorded_phase, str) and recorded_phase:
                self._cq_phase = recorded_phase

        # Validators are recomputed from the restored files; a boolean
        # gate-open state from the source run is never restored.
        validators = {
            "candidate_gate_open_after_restore": candidate_gate_open(root),
            "approvals_artifact_restored": (
                root / "value-semantics" / "approvals" / "approvals.json"
            ).is_file(),
            "gate_open_restored_from_source": False,
        }
        if validators["candidate_gate_open_after_restore"]:
            raise CheckpointError(
                "checkpoint_incomplete",
                "the restored candidate gate reads open before any new decision; "
                "restored boolean gates are not usable resume state",
                obj="candidate-gate/state.json",
                phase="checkpoint-resume",
            )

        self._resume_imports = {
            "completed_client_batches": dict(
                plan.imports.get("completed_client_batches") or {}
            ),
            "plan_mappings": list(plan.imports.get("plan_mappings") or []),
        }
        self._resume_plan = plan
        write_recovery_files(
            root,
            inspection=plan.inspection,
            origin=plan.origin,
            imports=plan.imports,
            role_packets=plan.role_packets,
        )
        self._append_evidence(
            CHECKPOINT_EVIDENCE_NAME,
            {
                "event": "resume-prepared",
                "source_run_id": plan.origin.get("source_run_id"),
                "checkpoint_id": plan.checkpoint_id,
                "checkpoint_kind": plan.manifest.get("kind"),
                "manifest_digest": plan.manifest_digest,
                "chain_runs": [str(path.name) for path in plan.chain_roots],
                "restored_artifact_count": len(restored["restored_artifacts"]),
                "completed_operations": len(plan.reconciliation["completed"]),
                "pending_new_dry_run": plan.reconciliation["pending_new_dry_run"],
                "recoverable_new_batch": plan.reconciliation["recoverable_new_batch"],
                "cq_freeze_restored": freeze_restored,
                "exposure_union": exposure,
                "validators_recomputed": validators,
                "accounting": plan.inspection["accounting"],
                "prep_timing": plan.inspection["prep_timing"],
            },
        )

    def _handle_checkpoint_outer(self, message: Mapping[str, Any]) -> dict[str, Any]:
        """Outer ``action=checkpoint`` dispatch: save or read-only inspect (§4.1)."""

        if not self.run:
            raise TeamConfigurationError("Runner is not prepared")
        command = message.get("command")
        if command == "inspect":
            checkpoint_id = message.get("checkpoint_id")
            if checkpoint_id is not None and not isinstance(checkpoint_id, str):
                raise RecoverableOuterInputError(
                    "checkpoint_id must be a string",
                    code="checkpoint_invalid_id",
                    run_id=self.run.run_id,
                )
            try:
                result = inspect_checkpoints(self.run.root, checkpoint_id)
            except CheckpointError as error:
                raise RecoverableOuterInputError(
                    error.detail,
                    code=error.reason_code,
                    run_id=self.run.run_id,
                ) from error
            return {"type": "checkpoint-inspect", **result}
        if command != "save":
            raise RecoverableOuterInputError(
                "outer checkpoint command must be 'save' or 'inspect'",
                code="invalid_checkpoint_command",
                run_id=self.run.run_id,
            )
        kind = message.get("kind")
        if kind not in CHECKPOINT_KINDS:
            raise RecoverableOuterInputError(
                f"checkpoint kind must be one of {list(CHECKPOINT_KINDS)}",
                code="checkpoint_invalid_kind",
                run_id=self.run.run_id,
            )
        scope_refs = message.get("scope_refs")
        if scope_refs is not None and not isinstance(scope_refs, dict):
            raise RecoverableOuterInputError(
                "checkpoint scope_refs must be a JSON object",
                code="invalid_checkpoint_scope",
                run_id=self.run.run_id,
            )
        request_id = message.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            raise RecoverableOuterInputError(
                "checkpoint request_id must be a string",
                code="invalid_checkpoint_request",
                run_id=self.run.run_id,
            )
        try:
            result = self._save_run_checkpoint(
                str(kind),
                scope_refs=scope_refs or {},
                trigger="outer-request",
                request_id=request_id,
            )
        except CheckpointError as error:
            self._append_evidence(
                CHECKPOINT_EVIDENCE_NAME,
                {
                    "event": "checkpoint-save-failed",
                    "kind": str(kind),
                    "trigger": "outer-request",
                    **error.data(),
                },
            )
            raise RecoverableOuterInputError(
                error.detail,
                code=error.reason_code,
                run_id=self.run.run_id,
            ) from error
        return {"type": "checkpoint-save", "kind": kind, **result}

    def _append_evidence(self, name: str, value: dict[str, Any]) -> None:
        if not self.run:
            return
        path = self.run.root / "evidence" / f"{name}.jsonl"
        envelope = {"recorded_at": datetime.now(UTC).isoformat(), **value}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def _formal_ledger_identity(self) -> dict[str, dict[str, str]]:
        if not self._ledger:
            return {}
        config = getattr(self._ledger, "config", None)
        strict_sequence = bool(getattr(config, "strict_sequence", False))
        # Keep cleanup compatible with lightweight legacy test doubles that
        # predate the immutable config carrier while retaining the formal
        # requirement-ID check used by the previous implementation.
        if not strict_sequence:
            strict_sequence = (
                getattr(self._ledger, "requirement_id", None)
                in {R2_3_005_REQUIREMENT_ID, "R2.3-003"}
            )
        if strict_sequence:
            return {"ledger_identity": self._ledger.identity}
        return {}

    def _append_team_transport_event(self, event: dict[str, object]) -> None:
        """Append one fixed-shape, sanitized report event in authoritative call order."""
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        expected = {"agent", "tool", "status", "category", "ack", "recorded_at_ns"}
        if not isinstance(event, dict) or set(event) != expected:
            raise ValueError("invalid Team Transport event")
        agent = event["agent"]
        status = event["status"]
        category = event["category"]
        if (
            not isinstance(agent, str)
            or not agent
            or len(agent) > 64
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in agent)
            or event["tool"] != "report_task_result"
            or event["ack"] != "not_applicable"
            or not isinstance(event["recorded_at_ns"], int)
            or isinstance(event["recorded_at_ns"], bool)
            or event["recorded_at_ns"] <= 0
            or status not in {"rejected", "accepted"}
            or (
                status == "rejected"
                and category not in {"missing_modeling_handoff", "broker_rejection"}
            )
            or (status == "accepted" and category != "terminal_report_accepted")
        ):
            raise ValueError("invalid Team Transport event")
        path = self.run.root / "evidence" / "team-transport-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, 0o600)

    def _formal_coordination_role_ids(self) -> dict[str, str]:
        """Resolve formal coordination roles to their configured agent IDs."""

        configuration = getattr(self.run, "configuration", None)
        profile = getattr(configuration, "profile", None)
        agents = getattr(profile, "agents", None)
        required_roles = {"coordinator", "modeling", "protocol", "acceptance"}
        if not isinstance(agents, (list, tuple)):
            raise TeamConfigurationError("formal coordination role identities are unavailable")
        role_ids: dict[str, str] = {}
        for agent in agents:
            package = getattr(agent, "package", None)
            role = getattr(package, "role", None)
            agent_id = getattr(agent, "agent_id", None)
            if (
                not isinstance(role, str)
                or role not in required_roles
                or role in role_ids
                or not isinstance(agent_id, str)
                or not agent_id
            ):
                raise TeamConfigurationError("formal coordination role identities are invalid")
            role_ids[role] = agent_id
        if set(role_ids) != required_roles:
            raise TeamConfigurationError("formal coordination role identities are incomplete")
        return role_ids

    def _coordination_transport_event_observer(self, event: dict[str, object]) -> None:
        """Persist a coordination event, then queue its Runner-owned delivery.

        ``TeamTransportBroker.send_coordination`` invokes the observer only after
        the phase callback has accepted the message and after it has released the
        Broker state lock.  The observer itself must remain non-reentrant: it
        records the immutable coordination evidence first and only then queues a
        validated phase delivery for the Runner's next ``drain`` turn.  Readiness,
        silence, and verdict-route signals go to Coordinator; only
        ``acceptance_start`` goes to Acceptance.
        """

        self._append_coordination_transport_event(event)
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("message_kind"), str)
            or event.get("message_kind")
            not in {
                "ready_for_acceptance",
                "silent_for_acceptance",
                "acceptance_start",
                "acceptance_verdict_route",
            }
            or not isinstance(event.get("sender_id"), str)
            or not isinstance(event.get("message_id"), str)
            or not event.get("message_id")
            or not isinstance(event.get("recipient_id"), str)
            or not isinstance(event.get("text"), str)
            or not isinstance(event.get("phase_event"), dict)
        ):
            return
        message_kind = event["message_kind"]
        sender_id = event["sender_id"]
        recipient_id = event["recipient_id"]
        role_ids = self._formal_coordination_role_ids()
        expected_sender, expected_recipient = {
            "ready_for_acceptance": (role_ids["modeling"], role_ids["coordinator"]),
            "silent_for_acceptance": (role_ids["protocol"], role_ids["coordinator"]),
            "acceptance_start": (role_ids["coordinator"], role_ids["acceptance"]),
            "acceptance_verdict_route": (role_ids["acceptance"], role_ids["coordinator"]),
        }[message_kind]
        if sender_id != expected_sender or recipient_id != expected_recipient:
            raise TeamConfigurationError("coordination Runtime delivery binding is invalid")
        generation = event["phase_event"].get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
            error = (
                "Acceptance start generation is invalid"
                if message_kind == "acceptance_start"
                else "coordination Runtime delivery generation is invalid"
            )
            raise TeamConfigurationError(error)
        queued = {
            "message_id": event["message_id"],
            "recipient_id": recipient_id,
            "message_kind": message_kind,
            "sender_id": sender_id,
            "text": event["text"],
            "generation": generation,
        }
        with self._coordination_runtime_lock:
            message_id = queued["message_id"]
            message_ids = getattr(self, "_coordination_runtime_message_ids", None)
            if not isinstance(message_ids, set):
                message_ids = set()
                self._coordination_runtime_message_ids = message_ids
            if message_id in message_ids:
                raise TeamConfigurationError("coordination Runtime delivery was queued twice")
            signal_keys = getattr(self, "_coordination_runtime_signal_keys", None)
            if not isinstance(signal_keys, set):
                signal_keys = set()
                self._coordination_runtime_signal_keys = signal_keys
            if message_kind in {"ready_for_acceptance", "silent_for_acceptance"}:
                signal_key = f"{generation}:{message_kind}:{sender_id}"
                if signal_key in signal_keys:
                    raise TeamConfigurationError("coordination readiness delivery was queued twice")
                signal_keys.add(signal_key)
            message_ids.add(message_id)
            self._coordination_runtime_queue.append(queued)

    def _drain_coordination_runtime_deliveries(self) -> None:
        """Dispatch queued coordination deliveries outside Broker callback locks."""

        with self._coordination_runtime_lock:
            queued, self._coordination_runtime_queue = self._coordination_runtime_queue, []
        if not queued:
            return
        role_ids = self._formal_coordination_role_ids()
        for event in queued:
            recipient_id = event.get("recipient_id")
            message_id = event.get("message_id")
            message_kind = event.get("message_kind")
            sender_id = event.get("sender_id")
            text = event.get("text")
            generation = event.get("generation")
            if (
                message_kind
                not in {
                    "ready_for_acceptance",
                    "silent_for_acceptance",
                    "acceptance_start",
                    "acceptance_verdict_route",
                }
                or not isinstance(message_id, str)
                or not message_id
                or not isinstance(sender_id, str)
                or not isinstance(text, str)
                or not isinstance(generation, int)
                or isinstance(generation, bool)
                or generation <= 0
            ):
                error = (
                    "Acceptance start delivery binding is invalid"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery binding is invalid"
                )
                raise TeamConfigurationError(error)
            expected_sender, expected_recipient = {
                "ready_for_acceptance": (role_ids["modeling"], role_ids["coordinator"]),
                "silent_for_acceptance": (role_ids["protocol"], role_ids["coordinator"]),
                "acceptance_start": (role_ids["coordinator"], role_ids["acceptance"]),
                "acceptance_verdict_route": (role_ids["acceptance"], role_ids["coordinator"]),
            }[message_kind]
            if sender_id != expected_sender or recipient_id != expected_recipient:
                error = (
                    "Acceptance start delivery binding is invalid"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery binding is invalid"
                )
                raise TeamConfigurationError(error)
            if message_kind == "acceptance_start":
                if self.acceptance is None or recipient_id != self.acceptance.acceptance_id:
                    raise TeamConfigurationError("Acceptance start delivery binding is invalid")
                payload = {
                    "acceptance_id": self.acceptance.acceptance_id,
                    "round_id": text,
                    "generation": generation,
                    "coordination_message_id": message_id,
                }
                delivery_kind = "acceptance-start"
            else:
                payload = {
                    "coordination_message_id": message_id,
                    "generation": generation,
                    "message_kind": message_kind,
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                    "text": text,
                }
                delivery_kind = "coordination-phase"
            try:
                self.adapter.send_message(
                    recipient_id,
                    RuntimeDelivery(
                        sender_id="runner/coordination",
                        recipient_id=recipient_id,
                        kind=delivery_kind,
                        text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        delivery_id=message_id,
                    ),
                )
            except Exception as exc:
                self._state("FAILED", coordination_message_id=message_id)
                error = (
                    "Acceptance start delivery failed"
                    if message_kind == "acceptance_start"
                    else "coordination Runtime delivery failed"
                )
                raise TeamConfigurationError(error) from exc

    def _append_coordination_transport_event(self, event: dict[str, object]) -> None:
        """Persist only fixed coordination metadata after phase validation."""

        if not self.run:
            return
        expected = {
            "sender_id",
            "recipient_id",
            "message_kind",
            "text",
            "timestamp",
            "message_id",
            "terminal",
            "settles",
            "phase_event",
        }
        if not isinstance(event, dict) or set(event) != expected:
            return
        sender = event["sender_id"]
        recipient = event["recipient_id"]
        kind = event["message_kind"]
        text = event["text"]
        phase_event = event["phase_event"]
        if (
            not isinstance(sender, str)
            or not isinstance(recipient, str)
            or not isinstance(kind, str)
            or kind
            not in {
                "ready_for_acceptance",
                "silent_for_acceptance",
                "acceptance_start",
                "acceptance_verdict_route",
            }
            or not isinstance(text, str)
            or not isinstance(phase_event, dict)
        ):
            return
        safe_phase = {
            key: value
            for key, value in phase_event.items()
            if key not in {"text", "objective"}
        }
        self._append_evidence(
            "coordination",
            {
                "sender_id": sender,
                "recipient_id": recipient,
                "message_kind": kind,
                "message_id": event["message_id"],
                "timestamp": event["timestamp"],
                "terminal": False,
                "settles": False,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "phase_event": safe_phase,
            },
        )

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
