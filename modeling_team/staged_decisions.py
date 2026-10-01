"""R3.0-008B segment 1: pure mechanical contracts for staged modeling decisions.

Seven-stage time gates, the ``analyzed_not_materialized`` analysis-conclusion
artifact, the materialization unlock/approvals/ledger artifacts, the stage 3
minimal slot, the joint acceptance checklist, and the Runner-private staged
batch submission path (envelope mirroring ``submit_modeling_batch``, durable
submission intents, authoritative receipts, and deterministic reconciliation).

This module is the ``scenario_map.py`` precedent applied to R3.0-008B: pure
deterministic functions with typed reason codes, loaders that reject symlinks
and escaping paths, and no business semantics.  Domain-flavored names appear
only in fixtures and assertions, never here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .scenario_map import _ABSOLUTE_IRI, _nonempty

# --- Schema constants -------------------------------------------------------

ANALYSIS_CONCLUSIONS_SCHEMA = "r3-0-008b-analysis-conclusions/v2"
STAGE3_SLOT_SCHEMA = "r3-0-008b-stage3-slot/v1"
MATERIALIZATION_UNLOCK_SCHEMA = "r3-0-008b-materialization-unlock/v1"
APPROVALS_SCHEMA = "r3-0-008b-approvals/v1"
JOINT_ACCEPTANCE_CHECKLIST_SCHEMA = "r3-0-008b-joint-acceptance-checklist/v1"
MATERIALIZATION_LEDGER_SCHEMA = "r3-0-008b-materialization-ledger/v1"
SUBMISSION_INTENT_SCHEMA = "r3-0-008b-submission-intent/v1"
SUBMISSION_RECEIPT_SCHEMA = "r3-0-008b-submission-receipt/v1"
STAGED_GATE_FEEDBACK_SCHEMA = "r3-0-008b-staged-gate-feedback/v1"

# R3.0-009 unified semantic graph (design §9.1): the same artifact paths carry
# versioned schemas. R4.0-012 removes source-tracing fields from the active
# unified contracts, so new artifacts use v2; historical v1 run files remain
# immutable and are not migrated in place.
UNIFIED_STAGE3_SLOT_SCHEMA = "r3-0-009-stage3-slot/v1"
UNIFIED_GRAPH_CANDIDATE_SCHEMA = "r3-0-009-unified-graph/v2"
UNIFIED_APPROVALS_SCHEMA = "r3-0-009-approvals/v2"
UNIFIED_MATERIALIZATION_PLAN_SCHEMA = "r3-0-009-materialization-plan/v2"
# The intent/receipt envelope field sets are unchanged.  Their projection
# digest naturally changes with the active item projection, but that does not
# require a second envelope schema or a compatibility branch.
UNIFIED_SUBMISSION_INTENT_SCHEMA = "r3-0-009-submission-intent/v1"
UNIFIED_SUBMISSION_RECEIPT_SCHEMA = "r3-0-009-submission-receipt/v1"
UNIFIED_GRAPH_TASK_PARAMETER = "unified_semantic_graph"
UNIFIED_GRAPH_CONTRACT_VERSION = UNIFIED_GRAPH_CANDIDATE_SCHEMA

# --- Directory and filename constants ---------------------------------------

VALUE_SEMANTICS_DIR = "value-semantics"
CONCLUSIONS_DIRNAME = "conclusions"
CONCLUSIONS_ARCHIVE_DIRNAME = "conclusions-archive"
UNLOCK_DIRNAME = "unlock"
APPROVALS_DIRNAME = "approvals"
LEDGER_DIRNAME = "ledger"
RECEIPTS_DIRNAME = "submission-receipts"
INTENTS_DIRNAME = "submission-intents"
STAGE3_NEUTRAL_GRAPH_DIR = "stage3-neutral-graph"
JOINT_ACCEPTANCE_DIR = "joint-acceptance"
# R3.0-009: the neutral-graph directory gains two role-scoped sub-directories.
CANDIDATES_DIRNAME = "candidates"
MATERIALIZATION_PLANS_DIRNAME = "materialization-plans"

CONCLUSIONS_FILENAME = "analysis-conclusions.json"
STAGE3_SLOT_FILENAME = "neutral-candidate.json"
UNLOCK_FILENAME = "materialization-unlock.json"
APPROVALS_FILENAME = "approvals.json"
LEDGER_FILENAME = "materialization-ledger.json"
CHECKLIST_FILENAME = "joint-acceptance-checklist.json"

STAGE3_DEFERRED_CONTRACT = "R3.0-009"
UNLOCK_SKIP_REASON = "no_schema_no_interface"
SUBMITTED_VIA = "protocol_staged_submit_modeling_batch"

# --- Closed value sets ------------------------------------------------------

CONCLUSION_STATUSES = ("analyzed", "confirmed", "materialized", "conflict")
VALUE_LEVELS = ("L1", "L2", "L3")
UNLOCK_MODES = ("materialize", "skip")
MAPPING_SOURCE_TYPES = ("database_schema", "interface")
APPROVAL_KINDS = ("conclusion_confirmation", "stage3_slot")
CHECKLIST_VERDICTS = ("pass", "fail", "pending")
CHECKLIST_ITEM_IDS = (
    "business_semantics_recall",
    "commonality_recall",
    "cross_slice_cross_ontology_recall",
    "value_semantics_recall",
    "sql_mapping_chain",
    "r30008a_representative_question_recheck",
    "rdf_no_business_rows",
)
BATCH_MODES = ("dry_run", "apply_atomic")
ENUM_COMMAND_KINDS = ("create_enum_meaning", "update_enum_meaning")
INTENT_STATUSES = ("submitted", "receipted", "unknown")

# R3.0-009 closed value sets: commonality decisions and their translation.
DECISION_KINDS = ("approved", "rejected", "deferred")
DECISION_TARGET_KINDS = ("commonality_node", "member_relation", "commonality_relation")
UNIFIED_CANDIDATE_ITEM_KINDS = ("entity", "relation", "property", "shape")

# The legal cross-revision conclusion state transitions (design section 3.3).
LEGAL_CONCLUSION_TRANSITIONS = frozenset(
    {
        ("analyzed", "confirmed"),
        ("confirmed", "materialized"),
        ("analyzed", "conflict"),
        ("confirmed", "conflict"),
        ("conflict", "analyzed"),
    }
)

# --- Deterministic reason codes (design section 4.1) -----------------------

STAGE3_REASON_CODES = (
    "stage3_missing_artifact",
    "stage3_unparsable",
    "stage3_schema_mismatch",
    "stage3_missing_approval",
    "stage3_approval_record_missing",
    "stage3_candidate_artifact_unavailable",
)
CONCLUSIONS_REASON_CODES = (
    "conclusions_unparsable",
    "conclusions_schema_mismatch",
    "conclusions_invalid_status_fields",
    "conclusions_illegal_transition",
    "conclusions_revision_regression",
    "conclusions_materialized_without_ledger",
    "conclusions_approval_missing",
)
APPROVALS_REASON_CODES = ("approvals_unparsable", "approvals_schema_mismatch")
UNLOCK_REASON_CODES = (
    "unlock_unparsable",
    "unlock_schema_mismatch",
    "unlock_code_mismatch",
    "unlock_dangling_conclusion",
    "unlock_skip_inconsistent",
)
STAGED_REASON_CODES = (
    "staged_gate_closed",
    "staged_submit_unparsable",
    "staged_submit_schema_mismatch",
    "staged_conclusions_unavailable",
    "staged_value_materialization_locked",
    "staged_missing_trace",
    "staged_conclusion_not_confirmed",
    "staged_conclusion_conflict",
    "staged_conclusion_already_materialized",
    "staged_trace_mismatch",
    "staged_unknown_enum_target",
    "staged_l3_unapproved",
    "staged_dangling_semantic_value",
    "staged_batch_forward_failed",
    "staged_batch_forward_unknown",
    # #17: the evidence-repost projection's own forwarder outcomes.  The envelope
    # shape reuses ``staged_submit_schema_mismatch`` and the write-integrity latch
    # reuses ``staged_gate_closed``: both mean exactly what they already mean.
    "staged_evidence_forward_failed",
    "staged_evidence_forward_unknown",
    "staged_ledger_stale",
    "staged_unreconciled_batch",
)
ACCEPTANCE_CHECKLIST_REASON_CODES = (
    "acceptance_checklist_missing",
    "acceptance_checklist_unparsable",
    "acceptance_checklist_schema_mismatch",
)
# R3.0-009 typed results (design §8). These are the locatable, repairable
# codes the unified-graph chain must return instead of an opaque run failure;
# ``staged_unreconciled_batch`` keeps its existing kill-switch meaning.
UNIFIED_REASON_CODES = (
    "missing_candidate_reference",
    "approval_missing",
    "approval_stale",
    "approval_content_mismatch",
    "relation_scope_ambiguous",
    "shape_conflict",
    "forbidden",
    "workspace_version_conflict",
    "staged_unreconciled_batch",
    "unified_schema_mismatch",
    # R3.0-014 (design §3.3/§3.4): apply-only gates over the current-plan
    # translation approval and the Runner-owned platform dry-run proof. A
    # dry-run never fails with these codes.
    "approval_conflict",
    "dry_run_proof_missing",
    "dry_run_proof_not_validated",
    "dry_run_proof_content_mismatch",
    "dry_run_proof_workspace_mismatch",
    "idempotency_conflict",
)

# --- R3.0-014 attempt-proof contract -----------------------------------------

# The Runner-owned platform Attempt binding appended to the staged-decisions
# host evidence (design §3.4). Agents never write this file, so no plan or
# message can self-report a proof.
ATTEMPT_PROOF_SCHEMA = "r3-0-014-attempt-proof/v1"
ATTEMPT_PROOF_EVENT = "submission-attempt-proof-written"
# ``recorded_at`` is stamped by the host evidence writer, not by the builder.
ATTEMPT_PROOF_FIELDS = frozenset(
    {
        "schema_version",
        "event",
        "intent_ordinal",
        "receipt_ordinal",
        "plan_ref",
        "projection_digest",
        "batch_id",
        "attempt_id",
        "client_batch_id",
        "idempotency_key",
        "mode",
        "attempt_status",
        "content_hash",
        "workspace_before_version",
        "response_digest",
    }
)
# The fields a forwarder result must carry before the Runner records a proof:
# without the full Attempt identity plus the read-back content hash the record
# would guess at what the platform did, so no proof is written at all.
ATTEMPT_PROOF_REQUIRED_RESULT_FIELDS = (
    "batch_id",
    "attempt_id",
    "mode",
    "attempt_status",
    "content_hash",
)

# --- Field sets (closed collections) ---------------------------------------

CONCLUSIONS_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "maintained_by",
        "entries",
    }
)
CONCLUSION_ENTRY_FIELDS = frozenset(
    {
        "conclusion_id",
        "mapped_property",
        "candidate_value",
        "business_meaning_hypothesis",
        "proposed_level",
        "blocking_unknowns",
        "status",
        "confirmed_enum_value",
        "confirmed_level",
        "confirmed_by",
        "conflict_note",
        "revision",
    }
)
STAGE3_SLOT_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "produced_by",
        "approved_by",
        "candidate_artifacts",
        "deferred_contract",
        "slot_note",
    }
)
UNLOCK_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "unlocked_by",
        "mode",
        "mapping_sources",
        "confirmed_codes",
        "skip_reason",
    }
)
APPROVALS_FIELDS = frozenset({"schema_version", "scenario_id", "maintained_by", "entries"})
APPROVAL_ENTRY_FIELDS = frozenset(
    {
        "kind",
        "target_id",
        "revision",
        "confirmed_enum_value",
        "approved_by",
        "note",
    }
)
CHECKLIST_FIELDS = frozenset({"schema_version", "scenario_id", "produced_by", "items"})
CHECKLIST_ITEM_FIELDS = frozenset({"item_id", "verdict", "evidence_ref", "checked_by"})
LEDGER_FIELDS = frozenset({"schema_version", "scenario_id", "maintained_by", "entries"})
LEDGER_ENTRY_FIELDS = frozenset(
    {
        "conclusion_id",
        "receipt_ordinal",
        "batch_id",
        "command_digest",
        "semantic_value_iri",
    }
)
INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "idempotency_key",
        "client_batch_id",
        "session_id",
        "mode",
        "commands",
        "value_traces",
        "l3_nodes",
        "status",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "intent_ordinal",
        "idempotency_key",
        "mode",
        "batch_id",
        "commands",
        "value_traces",
        "l3_nodes",
        "response_digest",
        "submitted_via",
    }
)

# The staged capability envelope mirrors the real ``submit_modeling_batch``
# signature (backend/app/mcp/tools/modeling_batches.py): session_id,
# client_batch_id, ontology_id, idempotency_key, expected_workspace_version,
# items[{command_kind, payload}], mode, lease_token.  ``value_traces`` and
# ``l3_nodes`` are Runner-side trace attachments and are never forwarded.
BATCH_ENVELOPE_REQUIRED_FIELDS = (
    "session_id",
    "client_batch_id",
    "ontology_id",
    "idempotency_key",
    "expected_workspace_version",
    "items",
    "mode",
)
BATCH_ENVELOPE_OPTIONAL_FIELDS = ("lease_token",)
VALUE_TRACE_FIELDS = frozenset({"command_index", "conclusion_id", "mapped_property"})
L3_NODE_FIELDS = frozenset({"command_index", "entity_id", "semantic_value_iri"})

# --- R3.0-009 closed field sets (design §9.1) -------------------------------

UNIFIED_STAGE3_SLOT_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "produced_by",
        "approved_by",
        "candidate_artifacts",
        "candidate_contract",
        "slot_note",
    }
)
UNIFIED_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "candidate_id",
        "revision",
        "items",
        "explicit_unknowns",
    }
)
# A candidate item keeps business meaning, value/relation endpoints,
# slice/shared-scope provenance and its own unknowns — never a platform IRI.
UNIFIED_CANDIDATE_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "item_kind",
        "business_meaning",
        "value",
        "relation_endpoints",
        "slice_ids",
        "shared_scope",
        "unknowns",
    }
)
UNIFIED_CANDIDATE_ITEM_OPTIONAL_FIELDS = frozenset({
    "semantic_definition", "action_definition", "parameter_definition",
})
UNIFIED_APPROVALS_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "maintained_by",
        "entries",
        "decisions",
        "translation_approvals",
    }
)
DECISION_FIELDS = frozenset(
    {
        "decision_id",
        "target_kind",
        "target_id",
        "candidate_id",
        "content_revision",
        "content_digest",
        "decision",
        "reason",
        "slice_ids",
        "shared_scope",
        "scope",
    }
)
TRANSLATION_APPROVAL_FIELDS = frozenset(
    {"plan_ref", "projection_digest", "approved_by", "decision", "reason"}
)
UNIFIED_MATERIALIZATION_PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "plan_id",
        "revision",
        "projection",
        "projection_digest",
    }
)
APPROVAL_PROJECTION_FIELDS = frozenset(
    {
        "task_id",
        "contract_version",
        "scenario_id",
        "session_id",
        "client_batch_id",
        "ontology_id",
        "candidate_id",
        "candidate_revision",
        "candidate_digest",
        "items",
        "decision_bindings",
        "identity_bindings",
    }
)
DECISION_BINDING_FIELDS = frozenset(
    {
        "command_index",
        "client_item_id",
        "candidate_item_ids",
        "candidate_revision",
        "candidate_content_digests",
        "decision_ids",
    }
)
IDENTITY_BINDING_FIELDS = frozenset(
    {"candidate_item_id", "resource_iri", "receipt_ref", "evidence_ref"}
)
# The 009 intent/receipt keep every 008B field and add the plan/projection
# bindings; the receipt copies them from the saved intent (design §9.2).
UNIFIED_INTENT_FIELDS = INTENT_FIELDS | {
    "plan_ref",
    "projection",
    "projection_digest",
    "decision_bindings",
}
UNIFIED_RECEIPT_FIELDS = RECEIPT_FIELDS | {
    "plan_ref",
    "projection_digest",
    "decision_bindings",
}

_INTENT_FILENAME = re.compile(r"^intent-(\d+)\.json$")
_RECEIPT_FILENAME = re.compile(r"^receipt-(\d+)\.json$")


class StagedDecisionArtifactError(RuntimeError):
    """A staged artifact failed to load; ``reason_code`` is deterministic."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


@dataclass
class StagedDecisionIssue:
    """One deterministic structural violation of a staged contract."""

    reason_code: str
    detail: str
    artifact: str = ""


class StagedSubmissionRejection(ValueError):
    """A typed, self-healing staged capability rejection.

    Carries a Mapping ``data`` attribute so the capability endpoint surfaces
    it as ``structuredContent`` ``{ok: False, error: {reason_code, detail}}``
    instead of the opaque ``-32001`` error.
    """

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.data = {"reason_code": reason_code, "detail": str(detail)}


class StagedBatchForwardError(RuntimeError):
    """A definite host-side write-forward failure (backend said no)."""


class StagedBatchForwardUnknown(RuntimeError):
    """An indeterminate host-side write-forward result (timeout/unparseable)."""


def unified_graph_mode(parameters: Mapping[str, Any] | None) -> bool:
    """True only when the Task explicitly selected the 009 unified schema set.

    Selecting 009 is opt-in per run; flipping the parameter on an existing run
    to skip a gate is rejected upstream (contracts) and never migrates files.
    """

    return isinstance(parameters, Mapping) and parameters.get(UNIFIED_GRAPH_TASK_PARAMETER) is True


def staged_decision_artifact_paths(run_root: Path, *, unified: bool = False) -> dict[str, Path]:
    """Canonical staged artifact paths inside one run workspace.

    ``unified=True`` adds the two R3.0-009 neutral-graph sub-directories; the
    pre-existing 008B paths keep their exact previous locations and keys.
    """

    root = Path(run_root)
    value_semantics = root / VALUE_SEMANTICS_DIR
    paths: dict[str, Path] = {
        "conclusions": value_semantics / CONCLUSIONS_DIRNAME / CONCLUSIONS_FILENAME,
        "unlock": value_semantics / UNLOCK_DIRNAME / UNLOCK_FILENAME,
        "approvals": value_semantics / APPROVALS_DIRNAME / APPROVALS_FILENAME,
        "ledger": value_semantics / LEDGER_DIRNAME / LEDGER_FILENAME,
        "checklist": root / JOINT_ACCEPTANCE_DIR / CHECKLIST_FILENAME,
        "stage3_slot": root / STAGE3_NEUTRAL_GRAPH_DIR / STAGE3_SLOT_FILENAME,
        "intents_dir": value_semantics / INTENTS_DIRNAME,
        "receipts_dir": value_semantics / RECEIPTS_DIRNAME,
        "conclusions_dir": value_semantics / CONCLUSIONS_DIRNAME,
        "conclusions_archive_dir": value_semantics / CONCLUSIONS_ARCHIVE_DIRNAME,
    }
    if unified:
        neutral_graph = root / STAGE3_NEUTRAL_GRAPH_DIR
        paths["candidates_dir"] = neutral_graph / CANDIDATES_DIRNAME
        paths["materialization_plans_dir"] = neutral_graph / MATERIALIZATION_PLANS_DIRNAME
    return paths


def staged_decision_directories(run_root: Path, *, unified: bool = False) -> list[Path]:
    """Every staged artifact directory the Runner prepares (mkdir only)."""

    root = Path(run_root)
    value_semantics = root / VALUE_SEMANTICS_DIR
    directories = [
        value_semantics / CONCLUSIONS_DIRNAME,
        value_semantics / CONCLUSIONS_ARCHIVE_DIRNAME,
        value_semantics / UNLOCK_DIRNAME,
        value_semantics / APPROVALS_DIRNAME,
        value_semantics / LEDGER_DIRNAME,
        value_semantics / RECEIPTS_DIRNAME,
        value_semantics / INTENTS_DIRNAME,
        root / STAGE3_NEUTRAL_GRAPH_DIR,
        root / JOINT_ACCEPTANCE_DIR,
    ]
    if unified:
        neutral_graph = root / STAGE3_NEUTRAL_GRAPH_DIR
        directories.extend(
            [
                neutral_graph / CANDIDATES_DIRNAME,
                neutral_graph / MATERIALIZATION_PLANS_DIRNAME,
            ]
        )
    return directories


# --- Loaders ----------------------------------------------------------------


def _load_json_artifact(path: Path, *, unparsable_code: str) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise StagedDecisionArtifactError(unparsable_code, f"{candidate} is unavailable")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StagedDecisionArtifactError(unparsable_code, str(exc)) from exc
    if not isinstance(value, dict):
        raise StagedDecisionArtifactError(unparsable_code, "artifact is not a JSON object")
    return value


def load_analysis_conclusions(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="conclusions_unparsable")


def load_stage3_slot(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="stage3_unparsable")


def load_materialization_unlock(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="unlock_unparsable")


def load_approvals(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="approvals_unparsable")


def load_joint_acceptance_checklist(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="acceptance_checklist_unparsable")


def load_materialization_ledger(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="staged_ledger_stale")


def load_unified_candidate(path: Path) -> dict[str, Any]:
    """Load one immutable ``candidates/<candidate_id>-r<revision>.json``."""

    return _load_json_artifact(path, unparsable_code="missing_candidate_reference")


def load_materialization_plan(path: Path) -> dict[str, Any]:
    """Load one ``materialization-plans/<plan_id>-r<revision>.json``."""

    return _load_json_artifact(path, unparsable_code="missing_candidate_reference")


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_nonempty(item) for item in value)


def _optional_nonempty_strings(value: Any) -> bool:
    return value is None or (isinstance(value, list) and all(_nonempty(item) for item in value))


def _enum_code_set(value: Any) -> frozenset[str] | None:
    """Enum codes carried by a conclusion/approval field.

    A field holds either one non-empty string (single code) or a non-empty list
    of non-empty strings (one code per materialized enum meaning, since the
    backend compiles one ``create_enum_meaning`` command per code).  Returns
    ``None`` for any other shape.
    """

    if isinstance(value, str):
        return frozenset({value.strip()}) if value.strip() else None
    if isinstance(value, list) and bool(value) and all(_nonempty(item) for item in value):
        return frozenset(item.strip() for item in value)
    return None


def _safe_relative_artifact_path(value: Any) -> bool:
    """A non-empty run-workspace-relative path without escape or absolute form."""

    if not _nonempty(value):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


# --- Conclusions artifact ---------------------------------------------------


def load_conclusion_archive(archive_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load immutable archived conclusion revisions, keyed by conclusion_id.

    Archive files are ``<conclusion_id>.r<revision>.json``.  A malformed or
    symlinked file is skipped deterministically (the revision-chain check then
    fails against the surviving archive view); this loader never raises.
    """

    archive: dict[str, list[dict[str, Any]]] = {}
    directory = Path(archive_dir)
    if not directory.is_dir():
        return archive
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json":
            continue
        match = re.match(r"^(.+)\.r(\d+)$", entry.stem)
        if match is None:
            continue
        try:
            value = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        value = dict(value)
        value.setdefault("conclusion_id", match.group(1))
        value.setdefault("revision", int(match.group(2)))
        archive.setdefault(match.group(1), []).append(value)
    for revisions in archive.values():
        revisions.sort(key=lambda item: item.get("revision", 0))
    return archive


def validate_analysis_conclusions(
    value: Any,
    *,
    archive: Mapping[str, list[dict[str, Any]]] | None = None,
    ledger_entries: list[dict[str, Any]] | None = None,
) -> tuple[StagedDecisionIssue, ...]:
    """Structural, state-machine, revision-chain, and ledger cross-checks."""

    artifact = f"{VALUE_SEMANTICS_DIR}/{CONCLUSIONS_DIRNAME}/{CONCLUSIONS_FILENAME}"
    if not isinstance(value, Mapping) or set(value) != CONCLUSIONS_FIELDS:
        return (StagedDecisionIssue("conclusions_schema_mismatch", "fields drift", artifact),)
    if value["schema_version"] != ANALYSIS_CONCLUSIONS_SCHEMA:
        return (StagedDecisionIssue("conclusions_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["maintained_by"]):
        return (StagedDecisionIssue("conclusions_schema_mismatch", "identity", artifact),)
    entries = value["entries"]
    if not isinstance(entries, list):
        return (StagedDecisionIssue("conclusions_schema_mismatch", "entries", artifact),)
    archive = dict(archive or {})
    ledger_conclusion_ids = {
        entry.get("conclusion_id")
        for entry in (ledger_entries or [])
        if isinstance(entry, Mapping)
    }
    issues: list[StagedDecisionIssue] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) - CONCLUSION_ENTRY_FIELDS:
            issues.append(StagedDecisionIssue("conclusions_schema_mismatch", "entry fields", artifact))
            continue
        conclusion_id = entry.get("conclusion_id")
        if not _nonempty(conclusion_id) or conclusion_id in seen_ids:
            issues.append(StagedDecisionIssue("conclusions_schema_mismatch", "conclusion_id", artifact))
            continue
        seen_ids.add(conclusion_id)
        status = entry.get("status")
        if status not in CONCLUSION_STATUSES:
            issues.append(
                StagedDecisionIssue("conclusions_invalid_status_fields", f"{conclusion_id}:status", artifact)
            )
            continue
        if not isinstance(entry.get("mapped_property"), str) or not _ABSOLUTE_IRI.match(
            entry.get("mapped_property", "")
        ):
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:mapped_property", artifact)
            )
        text_field_problems = []
        if _enum_code_set(entry.get("candidate_value")) is None:
            text_field_problems.append(
                "candidate_value expected one non-empty string or a non-empty list of non-empty strings, "
                f"got {type(entry.get('candidate_value')).__name__}"
            )
        if not _nonempty(entry.get("business_meaning_hypothesis")):
            text_field_problems.append(
                "business_meaning_hypothesis expected a non-empty string, "
                f"got {type(entry.get('business_meaning_hypothesis')).__name__}"
            )
        if text_field_problems:
            issues.append(
                StagedDecisionIssue(
                    "conclusions_schema_mismatch", f"{conclusion_id}:{'; '.join(text_field_problems)}", artifact
                )
            )
        if entry.get("proposed_level") not in VALUE_LEVELS:
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:proposed_level", artifact)
            )
        if not _optional_nonempty_strings(entry.get("blocking_unknowns")):
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:blocking_unknowns", artifact)
            )
        if entry.get("confirmed_level") is not None and entry.get("confirmed_level") not in VALUE_LEVELS:
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:confirmed_level", artifact)
            )
        revision = entry.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:revision", artifact)
            )
            continue
        # Per-status required/forbidden fields (design section 3.3 table).
        has_confirmed_value = _enum_code_set(entry.get("confirmed_enum_value")) is not None
        has_confirmed_by = _nonempty(entry.get("confirmed_by"))
        has_conflict_note = _nonempty(entry.get("conflict_note"))
        if status == "analyzed":
            if has_confirmed_value or has_confirmed_by or has_conflict_note:
                issues.append(
                    StagedDecisionIssue(
                        "conclusions_invalid_status_fields", f"{conclusion_id}:analyzed", artifact
                    )
                )
        elif status in {"confirmed", "materialized"}:
            status_field_problems = []
            if not has_confirmed_value:
                status_field_problems.append(
                    "confirmed_enum_value expected one non-empty string or a non-empty list of non-empty strings"
                )
            if not has_confirmed_by:
                status_field_problems.append("confirmed_by expected a non-empty string")
            if has_conflict_note:
                status_field_problems.append("conflict_note must be absent")
            if status_field_problems:
                issues.append(
                    StagedDecisionIssue(
                        "conclusions_invalid_status_fields",
                        f"{conclusion_id}:{status}:{'; '.join(status_field_problems)}",
                        artifact,
                    )
                )
        elif status == "conflict":
            if not has_conflict_note or has_confirmed_by:
                issues.append(
                    StagedDecisionIssue(
                        "conclusions_invalid_status_fields", f"{conclusion_id}:conflict", artifact
                    )
                )
        # Revision chain against the immutable archive.
        archived = [
            item
            for item in archive.get(conclusion_id, [])
            if isinstance(item.get("revision"), int)
            and not isinstance(item.get("revision"), bool)
            and item.get("revision") >= 1
        ]
        if archived:
            highest = max(item["revision"] for item in archived)
            if revision != highest + 1:
                issues.append(
                    StagedDecisionIssue(
                        "conclusions_revision_regression",
                        f"{conclusion_id}: current {revision} after archive {highest}",
                        artifact,
                    )
                )
            else:
                previous_status = archived[-1].get("status")
                if (previous_status, status) not in LEGAL_CONCLUSION_TRANSITIONS:
                    issues.append(
                        StagedDecisionIssue(
                            "conclusions_illegal_transition",
                            f"{conclusion_id}: {previous_status} -> {status}",
                            artifact,
                        )
                    )
        elif revision != 1:
            issues.append(
                StagedDecisionIssue(
                    "conclusions_revision_regression",
                    f"{conclusion_id}: revision {revision} without archive",
                    artifact,
                )
            )
        if status == "materialized" and conclusion_id not in ledger_conclusion_ids:
            issues.append(
                StagedDecisionIssue(
                    "conclusions_materialized_without_ledger", conclusion_id, artifact
                )
            )
    return tuple(issues)


# --- Approvals artifact -----------------------------------------------------


def validate_approvals(value: Any, *, unified: bool = False) -> tuple[StagedDecisionIssue, ...]:
    """Approvals artifact; ``unified`` selects the r3-0-009 structure.

    In 009 mode the legacy ``entries`` keep their exact 008B field set and
    meaning and the new ``decisions``/``translation_approvals`` collections are
    validated separately, so neither object is pushed through the other's
    closed-field validator. The default stays byte-identical to 008B.
    """

    artifact = f"{VALUE_SEMANTICS_DIR}/{APPROVALS_DIRNAME}/{APPROVALS_FILENAME}"
    fields = UNIFIED_APPROVALS_FIELDS if unified else APPROVALS_FIELDS
    schema = UNIFIED_APPROVALS_SCHEMA if unified else APPROVALS_SCHEMA
    schema_code = "unified_schema_mismatch" if unified else "approvals_schema_mismatch"
    if not isinstance(value, Mapping) or set(value) != set(fields):
        return (StagedDecisionIssue(schema_code, "fields drift", artifact),)
    if value["schema_version"] != schema:
        return (StagedDecisionIssue(schema_code, "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["maintained_by"]):
        return (StagedDecisionIssue(schema_code, "identity", artifact),)
    entries = value["entries"]
    if not isinstance(entries, list):
        return (StagedDecisionIssue(schema_code, "entries", artifact),)
    issues: list[StagedDecisionIssue] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) - APPROVAL_ENTRY_FIELDS:
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "entry fields", artifact))
            continue
        kind = entry.get("kind")
        if kind not in APPROVAL_KINDS:
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "kind", artifact))
            continue
        revision = entry.get("revision")
        if not _nonempty(entry.get("target_id")) or not _nonempty(entry.get("approved_by")):
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "identity fields", artifact))
            continue
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "revision", artifact))
            continue
        if kind == "conclusion_confirmation" and _enum_code_set(entry.get("confirmed_enum_value")) is None:
            issues.append(
                StagedDecisionIssue(
                    "approvals_schema_mismatch",
                    "confirmed_enum_value expected one non-empty string or a non-empty list of non-empty strings, "
                    f"got {type(entry.get('confirmed_enum_value')).__name__}",
                    artifact,
                )
            )
        if kind == "stage3_slot" and entry.get("confirmed_enum_value") is not None:
            issues.append(
                StagedDecisionIssue("approvals_schema_mismatch", "stage3 confirmed_enum_value", artifact)
            )
        if entry.get("note") is not None and not _nonempty(entry.get("note")):
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "note", artifact))
    if unified:
        issues.extend(validate_unified_approvals(value))
    return tuple(issues)


def cross_validate_approvals(
    approvals: Mapping[str, Any] | None,
    conclusions: Mapping[str, Any] | None,
    stage3_slot: Mapping[str, Any] | None,
) -> tuple[StagedDecisionIssue, ...]:
    """Anchor approvals to confirmed conclusions and the stage 3 slot."""

    issues: list[StagedDecisionIssue] = []
    conclusions_artifact = f"{VALUE_SEMANTICS_DIR}/{CONCLUSIONS_DIRNAME}/{CONCLUSIONS_FILENAME}"
    approvals_artifact = f"{VALUE_SEMANTICS_DIR}/{APPROVALS_DIRNAME}/{APPROVALS_FILENAME}"
    if approvals is None or conclusions is None:
        return tuple(issues)
    entries = approvals.get("entries")
    records = [item for item in entries if isinstance(item, Mapping)] if isinstance(entries, list) else []
    for entry in conclusions.get("entries", []) or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("status") not in {"confirmed", "materialized"}:
            continue
        conclusion_id = entry.get("conclusion_id")
        matching = [
            record
            for record in records
            if record.get("kind") == "conclusion_confirmation"
            and record.get("target_id") == conclusion_id
            and record.get("revision") == entry.get("revision")
            and record.get("confirmed_enum_value") == entry.get("confirmed_enum_value")
        ]
        if not matching:
            issues.append(
                StagedDecisionIssue(
                    "conclusions_approval_missing",
                    f"{conclusion_id} at revision {entry.get('revision')}",
                    conclusions_artifact,
                )
            )
    if stage3_slot is not None and isinstance(stage3_slot, Mapping):
        approved_by = stage3_slot.get("approved_by")
        scenario_id = stage3_slot.get("scenario_id")
        matching = [
            record
            for record in records
            if record.get("kind") == "stage3_slot"
            and record.get("target_id") == scenario_id
            and record.get("approved_by") == approved_by
        ]
        if not matching:
            issues.append(
                StagedDecisionIssue(
                    "stage3_approval_record_missing",
                    f"approved_by={approved_by}",
                    approvals_artifact,
                )
            )
    return tuple(issues)


# --- Stage 3 minimal slot ---------------------------------------------------


def validate_stage3_slot(value: Any, *, unified: bool = False) -> tuple[StagedDecisionIssue, ...]:
    """Stage 3 slot; ``unified`` requires ``candidate_contract`` (design §9.1)."""

    artifact = f"{STAGE3_NEUTRAL_GRAPH_DIR}/{STAGE3_SLOT_FILENAME}"
    fields = UNIFIED_STAGE3_SLOT_FIELDS if unified else STAGE3_SLOT_FIELDS
    schema = UNIFIED_STAGE3_SLOT_SCHEMA if unified else STAGE3_SLOT_SCHEMA
    contract_field = "candidate_contract" if unified else "deferred_contract"
    expected_contract = UNIFIED_GRAPH_CANDIDATE_SCHEMA if unified else STAGE3_DEFERRED_CONTRACT
    if not isinstance(value, Mapping) or set(value) - set(fields):
        return (StagedDecisionIssue("stage3_schema_mismatch", "fields drift", artifact),)
    missing = set(fields) - set(value)
    if missing:
        return (StagedDecisionIssue("stage3_schema_mismatch", f"missing {sorted(missing)}", artifact),)
    if value["schema_version"] != schema:
        return (StagedDecisionIssue("stage3_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["produced_by"]):
        return (StagedDecisionIssue("stage3_schema_mismatch", "identity", artifact),)
    if not _nonempty(value["approved_by"]):
        return (StagedDecisionIssue("stage3_missing_approval", "approved_by", artifact),)
    if value.get(contract_field) != expected_contract:
        return (StagedDecisionIssue("stage3_schema_mismatch", contract_field, artifact),)
    if value.get("slot_note") is not None and not _nonempty(value["slot_note"]):
        return (StagedDecisionIssue("stage3_schema_mismatch", "slot_note", artifact),)
    candidates = value.get("candidate_artifacts")
    if not isinstance(candidates, list) or not candidates:
        return (StagedDecisionIssue("stage3_schema_mismatch", "candidate_artifacts", artifact),)
    for item in candidates:
        if not _safe_relative_artifact_path(item):
            return (StagedDecisionIssue("stage3_candidate_artifact_unavailable", str(item), artifact),)
    return ()


def check_stage3_candidate_artifacts(run_root: Path, slot: Mapping[str, Any]) -> StagedDecisionIssue | None:
    """Every declared candidate must exist, be a regular file, and not escape."""

    artifact = f"{STAGE3_NEUTRAL_GRAPH_DIR}/{STAGE3_SLOT_FILENAME}"
    root = Path(run_root)
    for item in slot.get("candidate_artifacts", []) or []:
        candidate = root / str(item)
        if candidate.is_symlink() or not candidate.is_file():
            return StagedDecisionIssue(
                "stage3_candidate_artifact_unavailable", str(item), artifact
            )
        try:
            candidate.resolve().relative_to(root.resolve())
        except ValueError:
            return StagedDecisionIssue(
                "stage3_candidate_artifact_unavailable", str(item), artifact
            )
    return None


# --- Materialization unlock -------------------------------------------------


def validate_materialization_unlock(
    value: Any,
    *,
    conclusions: Mapping[str, Any] | None = None,
) -> tuple[StagedDecisionIssue, ...]:
    artifact = f"{VALUE_SEMANTICS_DIR}/{UNLOCK_DIRNAME}/{UNLOCK_FILENAME}"
    if not isinstance(value, Mapping) or set(value) - UNLOCK_FIELDS:
        return (StagedDecisionIssue("unlock_schema_mismatch", "fields drift", artifact),)
    missing = UNLOCK_FIELDS - {"mapping_sources", "confirmed_codes", "skip_reason"} - set(value)
    if missing:
        return (StagedDecisionIssue("unlock_schema_mismatch", f"missing {sorted(missing)}", artifact),)
    if value["schema_version"] != MATERIALIZATION_UNLOCK_SCHEMA:
        return (StagedDecisionIssue("unlock_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["unlocked_by"]):
        return (StagedDecisionIssue("unlock_schema_mismatch", "identity", artifact),)
    mode = value.get("mode")
    if mode not in UNLOCK_MODES:
        return (StagedDecisionIssue("unlock_schema_mismatch", "mode", artifact),)
    issues: list[StagedDecisionIssue] = []
    if mode == "materialize":
        if value.get("skip_reason") is not None:
            issues.append(StagedDecisionIssue("unlock_skip_inconsistent", "skip_reason present", artifact))
        sources = value.get("mapping_sources")
        if not isinstance(sources, list) or not sources:
            issues.append(StagedDecisionIssue("unlock_schema_mismatch", "mapping_sources", artifact))
        else:
            for item in sources:
                if (
                    not isinstance(item, Mapping)
                    or set(item) != {"source_type", "reference"}
                    or item.get("source_type") not in MAPPING_SOURCE_TYPES
                    or not _nonempty(item.get("reference"))
                ):
                    issues.append(
                        StagedDecisionIssue("unlock_schema_mismatch", "mapping_sources entry", artifact)
                    )
    else:
        if value.get("mapping_sources") is not None:
            issues.append(StagedDecisionIssue("unlock_skip_inconsistent", "mapping_sources present", artifact))
        if value.get("confirmed_codes") not in (None, []):
            issues.append(StagedDecisionIssue("unlock_skip_inconsistent", "confirmed_codes present", artifact))
        if value.get("skip_reason") != UNLOCK_SKIP_REASON:
            issues.append(StagedDecisionIssue("unlock_skip_inconsistent", "skip_reason", artifact))
        if isinstance(conclusions, Mapping):
            for entry in conclusions.get("entries", []) or []:
                if isinstance(entry, Mapping) and entry.get("status") in {"confirmed", "materialized"}:
                    issues.append(
                        StagedDecisionIssue(
                            "unlock_skip_inconsistent",
                            f"{entry.get('conclusion_id')} is {entry.get('status')}",
                            artifact,
                        )
                    )
    codes = value.get("confirmed_codes")
    if mode == "materialize":
        if not isinstance(codes, list):
            issues.append(StagedDecisionIssue("unlock_schema_mismatch", "confirmed_codes", artifact))
            return tuple(issues)
        confirmed_index: dict[str, Mapping[str, Any]] = {}
        if isinstance(conclusions, Mapping):
            confirmed_index = {
                entry.get("conclusion_id"): entry
                for entry in conclusions.get("entries", []) or []
                if isinstance(entry, Mapping)
            }
        for item in codes:
            expected_keys = {"conclusion_id", "mapped_property", "confirmed_enum_value", "confirmed_level"}
            if not isinstance(item, Mapping) or set(item) != expected_keys:
                issues.append(StagedDecisionIssue("unlock_schema_mismatch", "confirmed_codes entry", artifact))
                continue
            conclusion = confirmed_index.get(item.get("conclusion_id"))
            if conclusion is None:
                issues.append(
                    StagedDecisionIssue("unlock_dangling_conclusion", str(item.get("conclusion_id")), artifact)
                )
                continue
            if conclusion.get("status") != "confirmed":
                issues.append(
                    StagedDecisionIssue("unlock_code_mismatch", str(item.get("conclusion_id")), artifact)
                )
                continue
            for field in ("mapped_property", "confirmed_enum_value", "confirmed_level"):
                if item.get(field) != conclusion.get(field):
                    issues.append(
                        StagedDecisionIssue(
                            "unlock_code_mismatch",
                            f"{item.get('conclusion_id')}:{field}",
                            artifact,
                        )
                    )
    return tuple(issues)


# --- Joint acceptance checklist ---------------------------------------------


def validate_joint_acceptance_checklist(value: Any) -> tuple[StagedDecisionIssue, ...]:
    artifact = f"{JOINT_ACCEPTANCE_DIR}/{CHECKLIST_FILENAME}"
    if not isinstance(value, Mapping) or set(value) != CHECKLIST_FIELDS:
        return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "fields drift", artifact),)
    if value["schema_version"] != JOINT_ACCEPTANCE_CHECKLIST_SCHEMA:
        return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["produced_by"]):
        return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "identity", artifact),)
    items = value["items"]
    if not isinstance(items, list) or len(items) != len(CHECKLIST_ITEM_IDS):
        return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "items", artifact),)
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != CHECKLIST_ITEM_FIELDS:
            return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "item fields", artifact),)
        item_id = item.get("item_id")
        if item_id not in CHECKLIST_ITEM_IDS or item_id in seen:
            return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", f"item_id {item_id}", artifact),)
        seen.add(item_id)
        if item.get("verdict") not in CHECKLIST_VERDICTS:
            return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", f"{item_id}:verdict", artifact),)
        if not _nonempty(item.get("evidence_ref")) or not _nonempty(item.get("checked_by")):
            return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", f"{item_id}:fields", artifact),)
    if seen != set(CHECKLIST_ITEM_IDS):
        return (StagedDecisionIssue("acceptance_checklist_schema_mismatch", "fixed item set", artifact),)
    return ()


# --- Materialization ledger -------------------------------------------------


def validate_materialization_ledger(
    value: Any,
    *,
    receipts: list[dict[str, Any]] | None = None,
) -> tuple[StagedDecisionIssue, ...]:
    artifact = f"{VALUE_SEMANTICS_DIR}/{LEDGER_DIRNAME}/{LEDGER_FILENAME}"
    if not isinstance(value, Mapping) or set(value) != LEDGER_FIELDS:
        return (StagedDecisionIssue("staged_ledger_stale", "fields drift", artifact),)
    if value["schema_version"] != MATERIALIZATION_LEDGER_SCHEMA:
        return (StagedDecisionIssue("staged_ledger_stale", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["maintained_by"]):
        return (StagedDecisionIssue("staged_ledger_stale", "identity", artifact),)
    entries = value["entries"]
    if not isinstance(entries, list):
        return (StagedDecisionIssue("staged_ledger_stale", "entries", artifact),)
    receipts = receipts or []
    receipt_index = {
        receipt.get("ordinal"): receipt
        for receipt in receipts
        if isinstance(receipt.get("ordinal"), int)
    }
    issues: list[StagedDecisionIssue] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) - LEDGER_ENTRY_FIELDS:
            issues.append(StagedDecisionIssue("staged_ledger_stale", "entry fields", artifact))
            continue
        required_ok = (
            _nonempty(entry.get("conclusion_id"))
            and _nonempty(entry.get("batch_id"))
            and _nonempty(entry.get("command_digest"))
            and isinstance(entry.get("receipt_ordinal"), int)
            and not isinstance(entry.get("receipt_ordinal"), bool)
            and entry.get("receipt_ordinal") >= 1
            and (entry.get("semantic_value_iri") is None or _nonempty(entry.get("semantic_value_iri")))
        )
        if not required_ok:
            issues.append(StagedDecisionIssue("staged_ledger_stale", "entry shape", artifact))
            continue
        receipt = receipt_index.get(entry.get("receipt_ordinal"))
        if (
            receipt is None
            or receipt.get("batch_id") != entry.get("batch_id")
            or receipt.get("mode") != "apply_atomic"
            or entry.get("command_digest") not in (receipt.get("commands") or [])
        ):
            issues.append(
                StagedDecisionIssue(
                    "staged_ledger_stale",
                    f"{entry.get('conclusion_id')} vs receipt {entry.get('receipt_ordinal')}",
                    artifact,
                )
            )
    return tuple(issues)


# --- Staged submission (capability checks 1-6) ------------------------------


# R3.0-009: the batch items are the full ModelingItemInput projection
# (backend/app/api/schemas.py), whose defaults the platform fills in.  The 008B
# envelope keeps its narrower two-field shape.
UNIFIED_BATCH_ITEM_FIELDS = frozenset(
    {
        "client_item_id",
        "command_kind",
        "payload",
        "depends_on",
        "rationale",
        "competency_question_ids",
    }
)


def _batch_envelope_issues(batch: Any, *, unified: bool = False) -> StagedDecisionIssue | None:
    artifact = "capability:batch"
    if not isinstance(batch, Mapping):
        return StagedDecisionIssue("staged_submit_schema_mismatch", "batch is not an object", artifact)
    keys = set(batch)
    allowed = set(BATCH_ENVELOPE_REQUIRED_FIELDS) | set(BATCH_ENVELOPE_OPTIONAL_FIELDS)
    if keys - allowed or any(field not in keys for field in BATCH_ENVELOPE_REQUIRED_FIELDS):
        return StagedDecisionIssue("staged_submit_schema_mismatch", "batch fields", artifact)
    for field in ("session_id", "client_batch_id", "ontology_id", "idempotency_key", "expected_workspace_version"):
        if not _nonempty(batch.get(field)):
            return StagedDecisionIssue("staged_submit_schema_mismatch", field, artifact)
    if batch.get("mode") not in BATCH_MODES:
        return StagedDecisionIssue("staged_submit_schema_mismatch", "mode", artifact)
    if batch.get("mode") == "apply_atomic" and not _nonempty(batch.get("lease_token")):
        return StagedDecisionIssue("staged_submit_schema_mismatch", "lease_token", artifact)
    items = batch.get("items")
    if not isinstance(items, list) or not items:
        return StagedDecisionIssue("staged_submit_schema_mismatch", "items", artifact)
    for item in items:
        if unified:
            if (
                not isinstance(item, Mapping)
                or set(item) - UNIFIED_BATCH_ITEM_FIELDS
                or not _nonempty(item.get("client_item_id"))
                or not _nonempty(item.get("command_kind"))
                or not isinstance(item.get("payload"), Mapping)
            ):
                return StagedDecisionIssue("staged_submit_schema_mismatch", "item shape", artifact)
            for field in ("depends_on", "competency_question_ids"):
                value = item.get(field, [])
                if not isinstance(value, list) or any(not _nonempty(entry) for entry in value):
                    return StagedDecisionIssue(
                        "staged_submit_schema_mismatch", field, artifact
                    )
            rationale = item.get("rationale")
            if rationale is not None and not isinstance(rationale, str):
                return StagedDecisionIssue("staged_submit_schema_mismatch", "rationale", artifact)
            continue
        if (
            not isinstance(item, Mapping)
            or set(item) != {"command_kind", "payload"}
            or not _nonempty(item.get("command_kind"))
            or not isinstance(item.get("payload"), Mapping)
        ):
            return StagedDecisionIssue("staged_submit_schema_mismatch", "item shape", artifact)
    return None


def _trace_issues(value: Any, *, kind: str) -> StagedDecisionIssue | None:
    artifact = f"capability:{kind}"
    if not isinstance(value, list):
        return StagedDecisionIssue("staged_submit_schema_mismatch", kind, artifact)
    allowed_fields = VALUE_TRACE_FIELDS if kind == "value_traces" else L3_NODE_FIELDS
    for item in value:
        if not isinstance(item, Mapping) or set(item) - allowed_fields:
            return StagedDecisionIssue("staged_submit_schema_mismatch", f"{kind} entry", artifact)
        command_index = item.get("command_index")
        if not isinstance(command_index, int) or isinstance(command_index, bool) or command_index < 0:
            return StagedDecisionIssue("staged_submit_schema_mismatch", f"{kind}:command_index", artifact)
        if kind == "value_traces":
            if not _nonempty(item.get("conclusion_id")) or (
                item.get("mapped_property") is not None and not _nonempty(item.get("mapped_property"))
            ):
                return StagedDecisionIssue("staged_submit_schema_mismatch", "value_traces fields", artifact)
        else:
            if not _nonempty(item.get("entity_id")) or not _nonempty(item.get("semantic_value_iri")):
                return StagedDecisionIssue("staged_submit_schema_mismatch", "l3_nodes fields", artifact)
    return None


def effective_confirmed_level(entry: Mapping[str, Any]) -> Any:
    return entry.get("confirmed_level") or entry.get("proposed_level")


def receipted_l3_iris(receipts: list[dict[str, Any]]) -> set[str]:
    iris: set[str] = set()
    for receipt in receipts:
        for node in receipt.get("l3_nodes") or []:
            if isinstance(node, Mapping) and _nonempty(node.get("semantic_value_iri")):
                iris.add(node["semantic_value_iri"])
    return iris


def receipted_enum_targets(receipts: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Enum command identities already covered by authoritative receipts.

    Receipt ``value_traces`` entries carry an optional ``enum_target`` (the
    ``enum_meaning_id`` or ``enum_meaning_iri`` of the traced enum command);
    the Runner stamps it when writing the receipt so that later
    ``update_enum_meaning`` commands without ``enum_value`` can close their
    target back to a receipted command and the same conclusion.
    """

    targets: dict[str, set[str]] = {}
    for receipt in receipts:
        for trace in receipt.get("value_traces") or []:
            if not isinstance(trace, Mapping):
                continue
            target = trace.get("enum_target")
            conclusion_id = trace.get("conclusion_id")
            if _nonempty(target) and _nonempty(conclusion_id):
                targets.setdefault(target, set()).add(conclusion_id)
    return targets


def _materialization_command_indices(batch: Mapping[str, Any], l3_nodes: list[Any]) -> set[int]:
    indices = {
        index
        for index, item in enumerate(batch.get("items") or [])
        if isinstance(item, Mapping) and item.get("command_kind") in ENUM_COMMAND_KINDS
    }
    for node in l3_nodes:
        if isinstance(node, Mapping):
            command_index = node.get("command_index")
            item = (batch.get("items") or [])[command_index] if isinstance(command_index, int) and 0 <= command_index < len(batch.get("items") or []) else None
            if isinstance(item, Mapping) and item.get("command_kind") == "create_entity":
                indices.add(command_index)
    return indices


def validate_staged_submission(
    payload: Any,
    *,
    gate_open: bool,
    conclusions: Mapping[str, Any] | None,
    unlock: Mapping[str, Any] | None,
    unlock_issues: tuple[StagedDecisionIssue, ...] = (),
    receipts: list[dict[str, Any]] | None = None,
    unified: bool = False,
) -> tuple[StagedDecisionIssue, ...]:
    """Design section 3.6 mechanical checks 1-6 in fixed evaluation order."""

    if not gate_open:
        return (StagedDecisionIssue("staged_gate_closed", "platform MCP gate is not open", "capability"),)
    if not isinstance(payload, Mapping):
        return (StagedDecisionIssue("staged_submit_unparsable", "payload is not an object", "capability"),)
    batch = payload.get("batch")
    value_traces = payload.get("value_traces")
    l3_nodes = payload.get("l3_nodes")
    for issue in (
        _batch_envelope_issues(batch, unified=unified),
        _trace_issues(value_traces, kind="value_traces"),
        _trace_issues(l3_nodes, kind="l3_nodes"),
    ):
        if issue is not None:
            return (issue,)
    assert isinstance(batch, Mapping)
    assert isinstance(value_traces, list)
    assert isinstance(l3_nodes, list)
    items = batch["items"]
    materialization_indices = _materialization_command_indices(batch, l3_nodes)
    if materialization_indices:
        if unlock is None:
            return (
                StagedDecisionIssue(
                    "staged_value_materialization_locked",
                    "no valid materialize-mode unlock is registered",
                    "capability",
                ),
            )
        if unlock_issues:
            return (unlock_issues[0],)
        if unlock.get("mode") != "materialize":
            return (
                StagedDecisionIssue(
                    "staged_value_materialization_locked",
                    "unlock mode is skip",
                    "capability",
                ),
            )
        if conclusions is None:
            return (StagedDecisionIssue("staged_conclusions_unavailable", "conclusions artifact", "capability"),)
    conclusion_index: dict[str, Mapping[str, Any]] = {}
    if isinstance(conclusions, Mapping):
        conclusion_index = {
            entry.get("conclusion_id"): entry
            for entry in conclusions.get("entries") or []
            if isinstance(entry, Mapping)
        }
    traces_by_index: dict[int, list[Mapping[str, Any]]] = {}
    for trace in value_traces:
        traces_by_index.setdefault(trace["command_index"], []).append(trace)
    receipt_targets = receipted_enum_targets(receipts or [])
    receipt_iris = receipted_l3_iris(receipts or [])
    batch_l3_iris = {node["semantic_value_iri"] for node in l3_nodes}
    issues: list[StagedDecisionIssue] = []
    for index, item in enumerate(items):
        kind = item["command_kind"]
        payload_map = item["payload"]
        if kind == "create_enum_meaning":
            traces = traces_by_index.get(index, [])
            if not traces:
                issues.append(StagedDecisionIssue("staged_missing_trace", f"command {index}", "capability"))
                continue
            trace = traces[0]
            conclusion = conclusion_index.get(trace.get("conclusion_id"))
            if conclusion is None:
                issues.append(
                    StagedDecisionIssue(
                        "staged_trace_mismatch",
                        f"command {index}: dangling conclusion {trace.get('conclusion_id')}",
                        "capability",
                    )
                )
                continue
            status = conclusion.get("status")
            if status == "analyzed":
                issues.append(StagedDecisionIssue("staged_conclusion_not_confirmed", f"command {index}", "capability"))
                continue
            if status == "conflict":
                issues.append(StagedDecisionIssue("staged_conclusion_conflict", f"command {index}", "capability"))
                continue
            if status == "materialized":
                issues.append(
                    StagedDecisionIssue("staged_conclusion_already_materialized", f"command {index}", "capability")
                )
                continue
            confirmed_codes = _enum_code_set(conclusion.get("confirmed_enum_value"))
            payload_value = payload_map.get("enum_value")
            if (
                conclusion.get("mapped_property") != payload_map.get("property_iri")
                or confirmed_codes is None
                or not _nonempty(payload_value)
                or payload_value.strip() not in confirmed_codes
            ):
                issues.append(
                    StagedDecisionIssue(
                        "staged_trace_mismatch",
                        (
                            f"command {index}: payload enum_value {payload_value!r} must equal one code of the "
                            f"conclusion's confirmed_enum_value {sorted(confirmed_codes) if confirmed_codes else None} "
                            f"on mapped_property {conclusion.get('mapped_property')!r}"
                        ),
                        "capability",
                    )
                )
                continue
        elif kind == "update_enum_meaning":
            traces = traces_by_index.get(index, [])
            if not traces:
                issues.append(StagedDecisionIssue("staged_missing_trace", f"command {index}", "capability"))
                continue
            trace = traces[0]
            conclusion = conclusion_index.get(trace.get("conclusion_id"))
            if conclusion is None:
                issues.append(
                    StagedDecisionIssue(
                        "staged_trace_mismatch",
                        f"command {index}: dangling conclusion {trace.get('conclusion_id')}",
                        "capability",
                    )
                )
                continue
            status = conclusion.get("status")
            if status == "analyzed":
                issues.append(StagedDecisionIssue("staged_conclusion_not_confirmed", f"command {index}", "capability"))
                continue
            if status == "conflict":
                issues.append(StagedDecisionIssue("staged_conclusion_conflict", f"command {index}", "capability"))
                continue
            if status == "materialized":
                issues.append(
                    StagedDecisionIssue("staged_conclusion_already_materialized", f"command {index}", "capability")
                )
                continue
            if trace.get("mapped_property") is None or trace.get("mapped_property") != conclusion.get("mapped_property"):
                issues.append(StagedDecisionIssue("staged_trace_mismatch", f"command {index}", "capability"))
                continue
            if payload_map.get("enum_value") is not None:
                confirmed_codes = _enum_code_set(conclusion.get("confirmed_enum_value"))
                payload_value = payload_map.get("enum_value")
                if (
                    confirmed_codes is None
                    or not _nonempty(payload_value)
                    or payload_value.strip() not in confirmed_codes
                ):
                    issues.append(StagedDecisionIssue("staged_trace_mismatch", f"command {index}", "capability"))
                    continue
            else:
                target = payload_map.get("enum_meaning_id") or payload_map.get("enum_meaning_iri")
                covered = receipt_targets.get(target, set()) if _nonempty(target) else set()
                if trace.get("conclusion_id") not in covered:
                    issues.append(
                        StagedDecisionIssue("staged_unknown_enum_target", f"command {index}", "capability")
                    )
                    continue
        if _nonempty(payload_map.get("semantic_value")):
            if payload_map["semantic_value"] not in batch_l3_iris | receipt_iris:
                issues.append(
                    StagedDecisionIssue("staged_dangling_semantic_value", f"command {index}", "capability")
                )
    for node in l3_nodes:
        command_index = node["command_index"]
        item = items[command_index] if 0 <= command_index < len(items) else None
        if (
            not isinstance(item, Mapping)
            or item.get("command_kind") != "create_entity"
            or item.get("payload", {}).get("entity_id") != node.get("entity_id")
            and item.get("payload", {}).get("label") != node.get("entity_id")
        ):
            issues.append(StagedDecisionIssue("staged_l3_unapproved", f"l3 node {command_index}", "capability"))
            continue
        backed = any(
            trace.get("command_index") is not None
            and 0 <= trace["command_index"] < len(items)
            and items[trace["command_index"]].get("command_kind") in ENUM_COMMAND_KINDS
            and _nonempty(items[trace["command_index"]].get("payload", {}).get("semantic_value"))
            and items[trace["command_index"]]["payload"]["semantic_value"] == node.get("semantic_value_iri")
            and (conclusion_index.get(trace.get("conclusion_id")) or {}).get("status") == "confirmed"
            and effective_confirmed_level(conclusion_index.get(trace.get("conclusion_id")) or {}) == "L3"
            for trace in value_traces
        )
        if not backed:
            issues.append(StagedDecisionIssue("staged_l3_unapproved", f"l3 node {command_index}", "capability"))
    return tuple(issues)


# --- Submission intents and receipts ----------------------------------------


def canonical_command_digest(command: Mapping[str, Any]) -> str:
    payload = json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _read_ordinal_records(directory: Path, pattern: re.Pattern[str], unparsable_code: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not directory.is_dir():
        return records
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        match = pattern.match(entry.name)
        if match is None:
            continue
        try:
            value = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StagedDecisionArtifactError(unparsable_code, str(exc)) from exc
        if not isinstance(value, dict):
            raise StagedDecisionArtifactError(unparsable_code, f"{entry} is not a JSON object")
        records.append(value)
    records.sort(key=lambda item: item.get("ordinal", 0) if isinstance(item.get("ordinal"), int) else 0)
    return records


def read_submission_intents(run_root: Path) -> list[dict[str, Any]]:
    paths = staged_decision_artifact_paths(run_root)
    return _read_ordinal_records(paths["intents_dir"], _INTENT_FILENAME, "staged_unreconciled_batch")


def read_submission_receipts(run_root: Path) -> list[dict[str, Any]]:
    paths = staged_decision_artifact_paths(run_root)
    return _read_ordinal_records(paths["receipts_dir"], _RECEIPT_FILENAME, "staged_unreconciled_batch")


def next_intent_ordinal(intents: list[Mapping[str, Any]]) -> int:
    return max((item.get("ordinal", 0) for item in intents if isinstance(item.get("ordinal"), int)), default=0) + 1


def next_receipt_ordinal(receipts: list[Mapping[str, Any]]) -> int:
    return max((item.get("ordinal", 0) for item in receipts if isinstance(item.get("ordinal"), int)), default=0) + 1


def build_submission_intent(
    ordinal: int,
    *,
    idempotency_key: str,
    client_batch_id: str,
    session_id: str,
    mode: str,
    commands: list[Mapping[str, Any]],
    value_traces: list[Mapping[str, Any]],
    l3_nodes: list[Mapping[str, Any]],
    plan_ref: str | None = None,
    projection: Mapping[str, Any] | None = None,
    decision_bindings: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the durable intent record.

    With no 009 arguments this is byte-identical to the 008B intent. With a
    ``plan_ref`` plus projection the record switches to
    ``r3-0-009-submission-intent/v2`` and carries the approved projection and
    its digest; ``projection_digest`` is always recomputed here so a caller
    cannot store a projection under a foreign digest.
    """

    intent: dict[str, Any] = {
        "schema_version": SUBMISSION_INTENT_SCHEMA,
        "ordinal": ordinal,
        "idempotency_key": idempotency_key,
        "client_batch_id": client_batch_id,
        "session_id": session_id,
        "mode": mode,
        "commands": [canonical_command_digest(command) for command in commands],
        "value_traces": [dict(trace) for trace in value_traces],
        "l3_nodes": [dict(node) for node in l3_nodes],
        "status": "submitted",
    }
    if plan_ref is None and projection is None and decision_bindings is None:
        return intent
    if not _nonempty(plan_ref) or projection is None:
        raise StagedDecisionArtifactError(
            "missing_candidate_reference",
            "a 009 intent needs plan_ref and the approved projection",
        )
    if not isinstance(projection, Mapping):
        raise StagedDecisionArtifactError("unified_schema_mismatch", "projection must be a mapping")
    intent["schema_version"] = UNIFIED_SUBMISSION_INTENT_SCHEMA
    intent["plan_ref"] = plan_ref
    intent["projection"] = dict(projection)
    intent["projection_digest"] = projection_digest(projection)
    intent["decision_bindings"] = [dict(binding) for binding in decision_bindings or []]
    return intent


def mark_intent_status(intent: Mapping[str, Any], status: str) -> dict[str, Any]:
    if status not in INTENT_STATUSES:
        raise ValueError("unknown submission intent status")
    updated = dict(intent)
    updated["status"] = status
    return updated


def build_submission_receipt(
    ordinal: int,
    intent: Mapping[str, Any],
    *,
    batch_id: str,
    response_digest: str,
) -> dict[str, Any]:
    """Build the authoritative receipt; 009 bindings are copied, never rebuilt."""

    receipt: dict[str, Any] = {
        "schema_version": SUBMISSION_RECEIPT_SCHEMA,
        "ordinal": ordinal,
        "intent_ordinal": intent["ordinal"],
        "idempotency_key": intent["idempotency_key"],
        "mode": intent["mode"],
        "batch_id": batch_id,
        "commands": list(intent.get("commands") or []),
        "value_traces": [dict(trace) for trace in intent.get("value_traces") or []],
        "l3_nodes": [dict(node) for node in intent.get("l3_nodes") or []],
        "response_digest": response_digest,
        "submitted_via": SUBMITTED_VIA,
    }
    if intent.get("schema_version") != UNIFIED_SUBMISSION_INTENT_SCHEMA:
        return receipt
    receipt["schema_version"] = UNIFIED_SUBMISSION_RECEIPT_SCHEMA
    receipt["plan_ref"] = intent.get("plan_ref")
    receipt["projection_digest"] = intent.get("projection_digest")
    receipt["decision_bindings"] = [dict(binding) for binding in intent.get("decision_bindings") or []]
    return receipt


def write_submission_intent(run_root: Path, intent: Mapping[str, Any]) -> None:
    paths = staged_decision_artifact_paths(run_root)
    _atomic_write(paths["intents_dir"] / f"intent-{intent['ordinal']}.json", intent)


def write_submission_receipt(run_root: Path, receipt: Mapping[str, Any]) -> None:
    paths = staged_decision_artifact_paths(run_root)
    _atomic_write(paths["receipts_dir"] / f"receipt-{receipt['ordinal']}.json", receipt)


def candidate_gate_open(run_root: Path) -> bool:
    """Read the shared candidate platform gate state without side effects."""

    state_path = Path(run_root) / "candidate-gate" / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(state, dict) and state.get("state") == "open"


# --- Unknown-result adjudication and platform reconciliation ----------------


def adjudicate_unknown_intent(
    intent: Mapping[str, Any],
    platform_batch_listing: list[Mapping[str, Any]] | None,
) -> tuple[str, Mapping[str, Any] | None]:
    """Deterministic three-branch adjudication for one ``unknown`` intent.

    Returns ``("claim", batch)`` when the platform listing hits the intent's
    ``client_batch_id``/``idempotency_key`` (claim the batch, write the
    receipt, mark the intent ``receipted`` — the backend idempotency key
    makes same-key replay safe), ``("retry", None)`` when the listing is
    reachable and has no match (retry with the SAME key), and
    ``("suspend", None)`` when the listing is unreachable (keep the intent
    ``unknown``; the monitor kill-switch fires on suspended intents).
    """

    if platform_batch_listing is None:
        return ("suspend", None)
    for batch in platform_batch_listing:
        if not isinstance(batch, Mapping):
            continue
        if (
            batch.get("idempotency_key") == intent.get("idempotency_key")
            or batch.get("client_batch_id") == intent.get("client_batch_id")
        ):
            return ("claim", batch)
    return ("retry", None)


def reconcile_platform_batches(
    platform_batch_listing: list[Mapping[str, Any]] | None,
    intents: list[Mapping[str, Any]],
    receipts: list[Mapping[str, Any]],
) -> tuple[StagedDecisionIssue, ...]:
    """Compare the platform batch listing with Runner intents and receipts.

    A platform batch with no Runner intent is a bypassed direct submission;
    a ``receipted`` intent with no platform batch is a fake receipt.  Both
    close the gate via the ``staged_unreconciled_batch`` kill-switch.  An
    unreachable listing (``None``) reconciles nothing (adjudication owns
    that path).
    """

    if platform_batch_listing is None:
        return ()
    issues: list[StagedDecisionIssue] = []
    known_keys = {intent.get("idempotency_key") for intent in intents}
    for batch in platform_batch_listing:
        if not isinstance(batch, Mapping):
            continue
        if batch.get("idempotency_key") not in known_keys:
            issues.append(
                StagedDecisionIssue(
                    "staged_unreconciled_batch",
                    f"platform batch {batch.get('batch_id')} has no Runner intent",
                    "platform-reconciliation",
                )
            )
    receipted_keys = {
        intent.get("idempotency_key")
        for intent in intents
        if intent.get("status") == "receipted"
    }
    platform_keys = {batch.get("idempotency_key") for batch in platform_batch_listing if isinstance(batch, Mapping)}
    for key in sorted(str(item) for item in receipted_keys - platform_keys):
        issues.append(
            StagedDecisionIssue(
                "staged_unreconciled_batch",
                f"receipted intent {key} has no platform batch",
                "platform-reconciliation",
            )
        )
    return tuple(issues)


# --- Monitor-side composite checks ------------------------------------------


def _try_load(loader, path) -> tuple[Mapping[str, Any] | None, StagedDecisionIssue | None]:
    try:
        return loader(path), None
    except StagedDecisionArtifactError as exc:
        return None, StagedDecisionIssue(exc.reason_code, exc.detail, path.name)


def staged_stage3_issue(
    run_root: Path,
    approvals: Mapping[str, Any] | None,
    *,
    unified: bool = False,
) -> StagedDecisionIssue | None:
    """The first deterministic stage 3 slot issue, or ``None`` when valid."""

    paths = staged_decision_artifact_paths(run_root)
    slot_path = paths["stage3_slot"]
    artifact = f"{STAGE3_NEUTRAL_GRAPH_DIR}/{STAGE3_SLOT_FILENAME}"
    if not slot_path.exists() or slot_path.is_symlink():
        return StagedDecisionIssue("stage3_missing_artifact", artifact, artifact)
    slot, issue = _try_load(load_stage3_slot, slot_path)
    if issue is not None or slot is None:
        return issue
    issues = validate_stage3_slot(slot, unified=unified)
    if issues:
        return issues[0]
    reachability = check_stage3_candidate_artifacts(run_root, slot)
    if reachability is not None:
        return reachability
    if approvals is not None:
        cross = cross_validate_approvals(approvals, None, slot)
        if cross:
            return cross[0]
    return None


def staged_artifact_issues(
    run_root: Path, *, unified: bool = False
) -> tuple[StagedDecisionIssue, ...]:
    """Monitor tick cross-checks over conclusions/approvals/unlock/ledger."""

    paths = staged_decision_artifact_paths(run_root)
    issues: list[StagedDecisionIssue] = []
    conclusions: Mapping[str, Any] | None = None
    if paths["conclusions"].exists():
        conclusions, issue = _try_load(load_analysis_conclusions, paths["conclusions"])
        if issue is not None:
            issues.append(issue)
        elif conclusions is not None:
            archive = load_conclusion_archive(paths["conclusions_archive_dir"])
            ledger_entries = None
            if paths["ledger"].exists():
                ledger, ledger_issue = _try_load(load_materialization_ledger, paths["ledger"])
                if ledger_issue is not None:
                    issues.append(ledger_issue)
                elif ledger is not None:
                    ledger_entries = list(ledger.get("entries") or [])
            issues.extend(
                validate_analysis_conclusions(
                    conclusions, archive=archive, ledger_entries=ledger_entries
                )
            )
    approvals: Mapping[str, Any] | None = None
    if paths["approvals"].exists():
        approvals, issue = _try_load(load_approvals, paths["approvals"])
        if issue is not None:
            issues.append(issue)
        elif approvals is not None and unified:
            # 009 only: the legacy tick never validated the approvals artifact
            # here, so 008B behavior is preserved byte-for-byte.
            issues.extend(validate_approvals(approvals, unified=True))
    if approvals is not None:
        slot = None
        if paths["stage3_slot"].exists():
            slot, _ = _try_load(load_stage3_slot, paths["stage3_slot"])
        issues.extend(cross_validate_approvals(approvals, conclusions, slot))
    if paths["unlock"].exists():
        unlock, issue = _try_load(load_materialization_unlock, paths["unlock"])
        if issue is not None:
            issues.append(issue)
        elif unlock is not None:
            issues.extend(validate_materialization_unlock(unlock, conclusions=conclusions))
    if paths["ledger"].exists():
        ledger, issue = _try_load(load_materialization_ledger, paths["ledger"])
        if issue is not None:
            issues.append(issue)
        elif ledger is not None:
            issues.extend(
                validate_materialization_ledger(ledger, receipts=read_submission_receipts(run_root))
            )
    return tuple(issues)


# --- R3.0-009 unified graph: canonical digest, projection and validation ----


def canonical_json_digest(value: Any) -> str:
    """SHA-256 over the standard canonical JSON form (design §9.2).

    UTF-8, ``ensure_ascii=False``, ``sort_keys=True`` and ``(',', ':')``
    separators; self-referential ``*_digest`` fields must be removed by the
    caller before digesting.
    """

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_class_iris(values: Any) -> list[str]:
    """Deduplicate and sort expanded Class IRIs; order never changes a digest."""

    if not isinstance(values, list):
        return []
    expanded = {str(value).strip() for value in values if _nonempty(value)}
    return sorted(expanded)


def build_decision_binding(
    *,
    command_index: int,
    client_item_id: str,
    candidate_item_ids: list[str],
    candidate_revision: int,
    candidate_content_digests: dict[str, str],
    decision_ids: list[str],
) -> dict[str, Any]:
    """One fixed-shape candidate/approval binding for a forwarded item."""

    return {
        "command_index": command_index,
        "client_item_id": client_item_id,
        "candidate_item_ids": list(candidate_item_ids),
        "candidate_revision": candidate_revision,
        "candidate_content_digests": dict(candidate_content_digests),
        "decision_ids": list(decision_ids),
    }


def build_identity_binding(
    *,
    candidate_item_id: str,
    resource_iri: str | None = None,
    receipt_ref: str | None = None,
    evidence_ref: str | None = None,
) -> dict[str, Any]:
    """Bind one candidate item to an existing resource or a future receipt.

    Exactly one of ``resource_iri`` (existing resource, backed by an approved
    read ``evidence_ref``) and ``receipt_ref`` (identity created by a later
    receipt) may be set; both is a contradiction, neither is unresolvable.
    """

    if bool(resource_iri) == bool(receipt_ref):
        raise StagedDecisionArtifactError(
            "missing_candidate_reference",
            "identity binding needs exactly one of resource_iri or receipt_ref",
        )
    if resource_iri and not evidence_ref:
        raise StagedDecisionArtifactError(
            "missing_candidate_reference",
            "an existing resource binding needs the approved read evidence_ref",
        )
    if resource_iri is None:
        evidence_ref = None
    return {
        "candidate_item_id": candidate_item_id,
        "resource_iri": resource_iri,
        "receipt_ref": receipt_ref,
        "evidence_ref": evidence_ref,
    }


def build_approval_projection(
    *,
    task_id: str,
    scenario_id: str,
    session_id: str,
    client_batch_id: str,
    ontology_id: str,
    candidate_id: str,
    candidate_revision: int,
    candidate_digest: str,
    items: list[Mapping[str, Any]],
    decision_bindings: list[Mapping[str, Any]],
    identity_bindings: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """The complete, forwardable projection an approval proves (design §9.2).

    ``items`` are full ``ModelingItemInput`` projections; missing optional
    fields are filled with the interface defaults so the digest covers exactly
    what will be forwarded. Execution parameters (lease, mode, idempotency
    key, expected workspace version) never enter the projection.
    """

    projection = {
        "task_id": task_id,
        "contract_version": UNIFIED_GRAPH_CONTRACT_VERSION,
        "scenario_id": scenario_id,
        "session_id": session_id,
        "client_batch_id": client_batch_id,
        "ontology_id": ontology_id,
        "candidate_id": candidate_id,
        "candidate_revision": candidate_revision,
        "candidate_digest": candidate_digest,
        "items": [_normalize_item_projection(item) for item in items],
        "decision_bindings": [dict(binding) for binding in decision_bindings],
        "identity_bindings": [dict(binding) for binding in identity_bindings],
    }
    unexpected = set(projection) - APPROVAL_PROJECTION_FIELDS
    if unexpected:
        raise StagedDecisionArtifactError(
            "unified_schema_mismatch", f"projection has unexpected fields: {sorted(unexpected)}"
        )
    return projection


def _normalize_item_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    """Fill the ModelingItemInput defaults so omitted and explicit agree."""

    normalized = {
        "client_item_id": item.get("client_item_id"),
        "command_kind": item.get("command_kind"),
        "payload": item.get("payload") or {},
        "depends_on": list(item.get("depends_on") or []),
        "rationale": item.get("rationale"),
        "competency_question_ids": list(item.get("competency_question_ids") or []),
    }
    unexpected = set(item) - set(normalized)
    if unexpected:
        raise StagedDecisionArtifactError(
            "unified_schema_mismatch", f"item projection has unexpected fields: {sorted(unexpected)}"
        )
    return normalized


def projection_digest(projection: Mapping[str, Any]) -> str:
    """Digest of an approval projection; the projection carries no digest field."""

    return canonical_json_digest(projection)


def validate_unified_stage3_slot(value: Any) -> tuple[StagedDecisionIssue, ...]:
    """``r3-0-009-stage3-slot/v1``: candidate_contract replaces the deferral."""

    if not isinstance(value, Mapping) or value.get("schema_version") != UNIFIED_STAGE3_SLOT_SCHEMA:
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "stage3 slot is not r3-0-009-stage3-slot/v1", ""
            ),
        )
    if set(value) != set(UNIFIED_STAGE3_SLOT_FIELDS):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch",
                "stage3 slot fields drift from r3-0-009-stage3-slot/v1",
                "",
            ),
        )
    issues: list[StagedDecisionIssue] = []
    if not _nonempty_strings(value.get("candidate_artifacts")):
        issues.append(StagedDecisionIssue("missing_candidate_reference", "slot lists no candidates", ""))
    contract = value.get("candidate_contract")
    if not _nonempty(contract) or not str(contract).startswith("r3-0-009"):
        issues.append(
            StagedDecisionIssue(
                "unified_schema_mismatch", "candidate_contract must name the 009 contract", ""
            )
        )
    return tuple(issues)


def validate_unified_candidate(value: Any) -> tuple[StagedDecisionIssue, ...]:
    """``r3-0-009-unified-graph/v2`` candidate items are neutral and closed."""

    if not isinstance(value, Mapping) or value.get("schema_version") != UNIFIED_GRAPH_CANDIDATE_SCHEMA:
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "candidate is not r3-0-009-unified-graph/v2", ""
            ),
        )
    if set(value) != set(UNIFIED_CANDIDATE_FIELDS):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "candidate fields drift from r3-0-009-unified-graph/v2", ""
            ),
        )
    issues: list[StagedDecisionIssue] = []
    for field in ("scenario_id", "candidate_id"):
        if not _nonempty(value.get(field)) or "://" in str(value.get(field)):
            issues.append(
                StagedDecisionIssue(
                    "missing_candidate_reference", f"candidate {field} is invalid", ""
                )
            )
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        issues.append(StagedDecisionIssue("approval_stale", "candidate revision is invalid", ""))
    items = value.get("items")
    if not isinstance(items, list) or not items:
        issues.append(StagedDecisionIssue("missing_candidate_reference", "candidate has no items", ""))
        items = []
    seen_items: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or (
            set(item) - UNIFIED_CANDIDATE_ITEM_OPTIONAL_FIELDS
            != set(UNIFIED_CANDIDATE_ITEM_FIELDS)
        ):
            issues.append(
                StagedDecisionIssue(
                    "unified_schema_mismatch", "candidate item fields drift from the contract", ""
                )
            )
            continue
        item_id = item.get("item_id")
        if not _nonempty(item_id):
            issues.append(StagedDecisionIssue("missing_candidate_reference", "item_id is missing", ""))
        elif item_id in seen_items:
            issues.append(
                StagedDecisionIssue("missing_candidate_reference", f"item_id {item_id} repeats", "")
            )
        else:
            seen_items.add(item_id)
        if item.get("item_kind") not in UNIFIED_CANDIDATE_ITEM_KINDS:
            issues.append(
                StagedDecisionIssue("unified_schema_mismatch", "candidate item_kind is invalid", "")
            )
    return tuple(issues)


def validate_unified_approvals(value: Any) -> tuple[StagedDecisionIssue, ...]:
    """``r3-0-009-approvals/v2``: legacy entries plus decisions/translations.

    ``entries`` keeps its 008B meaning and closed field set; ``decisions`` is
    validated entry by entry because every business decision gates both modes,
    while ``translation_approvals`` is only checked to be a list — since
    R3.0-014 the current-plan translation decision is matched per key at apply
    time (``unified_translation_issue``), so stale or malformed history cannot
    block a dry-run and cannot release an apply either.
    """

    if not isinstance(value, Mapping) or value.get("schema_version") != UNIFIED_APPROVALS_SCHEMA:
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "approvals are not r3-0-009-approvals/v2", ""
            ),
        )
    if set(value) != set(UNIFIED_APPROVALS_FIELDS):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "approvals fields drift from r3-0-009-approvals/v2", ""
            ),
        )
    issues: list[StagedDecisionIssue] = []
    decisions = value.get("decisions") or []
    if not isinstance(decisions, list):
        return (StagedDecisionIssue("unified_schema_mismatch", "decisions is not a list", ""),)
    by_id: dict[str, Mapping[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, Mapping) or set(decision) != set(DECISION_FIELDS):
            issues.append(
                StagedDecisionIssue(
                    "unified_schema_mismatch", "decision fields drift from r3-0-009-approvals/v2", ""
                )
            )
            continue
        decision_id = decision.get("decision_id")
        if not _nonempty(decision_id):
            issues.append(StagedDecisionIssue("approval_missing", "decision_id is missing", ""))
            continue
        if decision_id in by_id:
            issues.append(
                StagedDecisionIssue("approval_missing", f"decision_id {decision_id} repeats", "")
            )
        by_id[decision_id] = decision
        if decision.get("decision") not in DECISION_KINDS:
            issues.append(
                StagedDecisionIssue("approval_missing", f"decision {decision_id} kind is invalid", "")
            )
        if decision.get("target_kind") not in DECISION_TARGET_KINDS:
            issues.append(
                StagedDecisionIssue(
                    "approval_missing", f"decision {decision_id} target_kind is invalid", ""
                )
            )
        if not _nonempty(decision.get("content_digest")):
            issues.append(
                StagedDecisionIssue(
                    "approval_content_mismatch", f"decision {decision_id} has no content digest", ""
                )
            )
        # Scope is mandatory only for commonality relations; everywhere else it
        # must stay null so a missing scope cannot silently widen a relation.
        scope = decision.get("scope")
        if decision.get("target_kind") == "commonality_relation":
            if not isinstance(scope, Mapping) or not scope:
                issues.append(
                    StagedDecisionIssue(
                        "relation_scope_ambiguous",
                        f"decision {decision_id} needs a relation scope",
                        "",
                    )
                )
        elif scope is not None:
            issues.append(
                StagedDecisionIssue(
                    "relation_scope_ambiguous",
                    f"decision {decision_id} must keep scope null",
                    "",
                )
            )

    translations = value.get("translation_approvals") or []
    if not isinstance(translations, list):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch", "translation_approvals is not a list", ""
            ),
        )
    # R3.0-014 (design §3.3): per-entry translation shape is no longer a
    # file-wide gate. Old-plan, rejected or format-drifted entries are
    # history — they must not block a dry-run — and apply does its own
    # exact ``(plan_ref, projection_digest)`` match in
    # ``unified_translation_issue`` instead of trusting any well-formed entry.
    return tuple(issues)


def validate_materialization_plan(value: Any) -> tuple[StagedDecisionIssue, ...]:
    """``r3-0-009-materialization-plan/v2``: projection plus its digest."""

    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != UNIFIED_MATERIALIZATION_PLAN_SCHEMA
    ):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch",
                "materialization plan is not r3-0-009-materialization-plan/v2",
                "",
            ),
        )
    if set(value) != set(UNIFIED_MATERIALIZATION_PLAN_FIELDS):
        return (
            StagedDecisionIssue(
                "unified_schema_mismatch",
                "materialization plan fields drift from the contract",
                "",
            ),
        )
    issues: list[StagedDecisionIssue] = []
    plan_projection = value.get("projection")
    if not isinstance(plan_projection, Mapping):
        issues.append(
            StagedDecisionIssue("missing_candidate_reference", "plan projection is missing", "")
        )
    elif set(plan_projection) != set(APPROVAL_PROJECTION_FIELDS):
        issues.append(
            StagedDecisionIssue(
                "unified_schema_mismatch", "plan projection fields drift from the contract", ""
            )
        )
    if isinstance(plan_projection, Mapping):
        # The plan is the only binding boundary the submission close checks
        # read from, so it is validated with the same binding validator the
        # intent/receipt schemas use: a malformed binding shape is a typed,
        # fixable rejection at load time instead of a raw AttributeError in a
        # later close check.
        binding_issue = _decision_binding_issue(plan_projection.get("decision_bindings"))
        if binding_issue is not None:
            issues.append(binding_issue)
    digest = value.get("projection_digest")
    if not _nonempty(digest) or not str(digest).startswith("sha256:"):
        issues.append(
            StagedDecisionIssue(
                "approval_content_mismatch", "plan projection_digest is missing", ""
            )
        )
    elif isinstance(plan_projection, Mapping):
        expected = projection_digest(plan_projection)
        if digest != expected:
            issues.append(
                StagedDecisionIssue(
                    "approval_content_mismatch",
                    "plan projection digest does not match its projection",
                    "",
                )
            )
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        issues.append(StagedDecisionIssue("approval_stale", "plan revision is invalid", ""))
    return tuple(issues)


# --- R3.0-009 receipt-time comparison (design §9.2) --------------------------

# Digest conventions published in the 009 contract: a candidate item digest is
# the canonical JSON digest of the whole published item object, and a candidate
# digest is the canonical JSON digest of the candidate's ordered ``items`` list.


def candidate_item_digest(item: Mapping[str, Any]) -> str:
    """Canonical digest of one published candidate item (all its fields)."""

    return canonical_json_digest(item)


def candidate_items_digest(items: list[Mapping[str, Any]]) -> str:
    """Canonical digest of a candidate's ``items`` list, in published order."""

    return canonical_json_digest([dict(item) for item in items])


def build_batch_projection(
    *,
    task_id: str,
    batch: Mapping[str, Any],
    scenario_id: str,
    candidate_id: str,
    candidate_revision: int,
    candidate_digest: str,
    decision_bindings: list[Mapping[str, Any]],
    identity_bindings: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild the approved projection from the batch actually being forwarded.

    The comparison is against real payloads, not against a self-reported
    digest: items are re-normalized from ``batch["items"]`` and execution
    parameters (lease, mode, idempotency key, expected workspace version)
    never enter the projection.
    """

    return build_approval_projection(
        task_id=task_id,
        scenario_id=scenario_id,
        session_id=batch.get("session_id") or "",
        client_batch_id=batch.get("client_batch_id") or "",
        ontology_id=batch.get("ontology_id") or "",
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        candidate_digest=candidate_digest,
        items=[item for item in batch.get("items") or [] if isinstance(item, Mapping)],
        decision_bindings=decision_bindings,
        identity_bindings=identity_bindings,
    )


def load_materialization_plan_ref(
    run_root: Path, plan_ref: Any
) -> tuple[Mapping[str, Any] | None, StagedDecisionIssue | None]:
    """Load the plan a submission binds to; only the published directory is legal."""

    if not _safe_relative_artifact_path(plan_ref):
        return None, StagedDecisionIssue(
            "missing_candidate_reference", "plan_ref is not a run-relative path", ""
        )
    prefix = f"{STAGE3_NEUTRAL_GRAPH_DIR}/{MATERIALIZATION_PLANS_DIRNAME}/"
    if not str(plan_ref).startswith(prefix):
        return None, StagedDecisionIssue(
            "missing_candidate_reference", f"plan_ref must live under {prefix}", ""
        )
    path = Path(run_root) / str(plan_ref)
    if path.is_symlink() or not path.is_file():
        return None, StagedDecisionIssue(
            "missing_candidate_reference", f"materialization plan {plan_ref} is missing", ""
        )
    plan, issue = _try_load(load_materialization_plan, path)
    if issue is not None or plan is None:
        return None, issue
    plan_issues = validate_materialization_plan(plan)
    if plan_issues:
        return None, plan_issues[0]
    return plan, None


def unified_plan_issue(
    *,
    plan: Mapping[str, Any],
    batch: Mapping[str, Any],
    task_id: str,
) -> StagedDecisionIssue | None:
    """Compare the projection being forwarded with the approved projection.

    The approved projection is authoritative: items are rebuilt from the real
    batch payloads and compared field by field, so a correct self-reported
    digest never substitutes for matching content (design §9.2 step 1).
    """

    approved = plan.get("projection") or {}
    rebuilt = build_batch_projection(
        task_id=task_id,
        batch=batch,
        scenario_id=approved.get("scenario_id") or "",
        candidate_id=approved.get("candidate_id") or "",
        candidate_revision=approved.get("candidate_revision") or 0,
        candidate_digest=approved.get("candidate_digest") or "",
        decision_bindings=approved.get("decision_bindings") or [],
        identity_bindings=approved.get("identity_bindings") or [],
    )
    if projection_digest(rebuilt) != plan.get("projection_digest") or rebuilt != approved:
        return StagedDecisionIssue(
            "approval_content_mismatch",
            "forwarded items do not match the approved projection",
            "",
        )
    return None


def unified_candidate_issue(
    run_root: Path, projection: Mapping[str, Any]
) -> StagedDecisionIssue | None:
    """Close the projection against the currently published candidate revision."""

    candidate_id = projection.get("candidate_id")
    revision = projection.get("candidate_revision")
    if not _nonempty(candidate_id) or isinstance(revision, bool) or not isinstance(revision, int):
        return StagedDecisionIssue("missing_candidate_reference", "projection names no candidate", "")
    path = (
        Path(run_root)
        / STAGE3_NEUTRAL_GRAPH_DIR
        / CANDIDATES_DIRNAME
        / f"{candidate_id}-r{revision}.json"
    )
    if path.is_symlink() or not path.is_file():
        return StagedDecisionIssue(
            "approval_stale",
            f"candidate {candidate_id}-r{revision} is not the published revision",
            "",
        )
    candidate, issue = _try_load(load_unified_candidate, path)
    if issue is not None or candidate is None:
        return issue
    candidate_issues = validate_unified_candidate(candidate)
    if candidate_issues:
        return candidate_issues[0]
    items = candidate.get("items") or []
    if candidate_items_digest(items) != projection.get("candidate_digest"):
        return StagedDecisionIssue(
            "approval_content_mismatch",
            "candidate content does not match the approved candidate digest",
            "",
        )
    published = {item.get("item_id"): item for item in items if isinstance(item, Mapping)}
    for binding in projection.get("decision_bindings") or []:
        for item_id, digest in (binding.get("candidate_content_digests") or {}).items():
            item = published.get(item_id)
            if item is None or candidate_item_digest(item) != digest:
                return StagedDecisionIssue(
                    "approval_content_mismatch",
                    f"candidate item {item_id} does not match its approved digest",
                    "",
                )
    return None


def unified_approval_issue(
    approvals: Mapping[str, Any], projection: Mapping[str, Any]
) -> StagedDecisionIssue | None:
    """Close every decision binding against an approved, current decision."""

    issues = validate_unified_approvals(approvals)
    if issues:
        return issues[0]
    decisions = {
        decision.get("decision_id"): decision
        for decision in approvals.get("decisions") or []
        if isinstance(decision, Mapping)
    }
    for binding in projection.get("decision_bindings") or []:
        for decision_id in binding.get("decision_ids") or []:
            decision = decisions.get(decision_id)
            if decision is None:
                return StagedDecisionIssue(
                    "approval_missing", f"decision {decision_id} is not in the approvals", ""
                )
            if decision.get("decision") != "approved":
                return StagedDecisionIssue(
                    "approval_missing", f"decision {decision_id} is not approved", ""
                )
            if decision.get("candidate_id") != projection.get("candidate_id"):
                return StagedDecisionIssue(
                    "approval_missing", f"decision {decision_id} names another candidate", ""
                )
            if decision.get("content_revision") != binding.get("candidate_revision"):
                return StagedDecisionIssue(
                    "approval_stale", f"decision {decision_id} approves another revision", ""
                )
            if decision.get("content_digest") not in (
                binding.get("candidate_content_digests") or {}
            ).values():
                return StagedDecisionIssue(
                    "approval_content_mismatch",
                    f"decision {decision_id} approves other content",
                    "",
                )
    return None


def unified_translation_issue(
    approvals: Mapping[str, Any],
    *,
    plan_ref: str,
    projection_digest: str,
    coordinator_id: str,
) -> StagedDecisionIssue | None:
    """R3.0-014: the apply-time current-plan translation approval gate.

    Selects the entries of the current approvals artifact that carry exactly
    the submitted plan's ``(plan_ref, projection_digest)`` key. Old-plan,
    rejected or malformed entries are history: they neither gate nor release
    an apply. Equivalent repeats — same key, approver and decision — count as
    one decision; only a genuine decision or approver conflict on the same
    key is a typed ``approval_conflict``. The single surviving decision must
    be ``approved`` by the run's current Coordinator role ID.
    """

    if not isinstance(approvals, Mapping):
        return StagedDecisionIssue(
            "unified_schema_mismatch", "approvals are not r3-0-009-approvals/v2", ""
        )
    translations = approvals.get("translation_approvals")
    if not isinstance(translations, list):
        return StagedDecisionIssue(
            "unified_schema_mismatch", "translation_approvals is not a list", ""
        )
    if not _nonempty(plan_ref) or not _nonempty(projection_digest):
        return StagedDecisionIssue(
            "missing_candidate_reference", "the submission names no plan identity", ""
        )
    if not _nonempty(coordinator_id):
        return StagedDecisionIssue(
            "missing_candidate_reference", "the run resolves no current Coordinator", ""
        )
    matched: list[tuple[Any, Any]] = []
    for entry in translations:
        if not isinstance(entry, Mapping) or set(entry) != set(TRANSLATION_APPROVAL_FIELDS):
            continue
        if entry.get("plan_ref") != plan_ref or entry.get("projection_digest") != projection_digest:
            continue
        matched.append((entry.get("decision"), entry.get("approved_by")))
    if not matched:
        # R3.0-016 #20 family: a bare "no approval matches" left the modeling
        # role unable to distinguish "Coordinator never approved" from "my
        # approval was recorded at an older projection digest" (a stateful
        # call revises the digest).  List the digests that ARE recorded for
        # this plan, prefix-truncated: host-owned sha256 values only.
        recorded = sorted(
            {
                str(entry.get("projection_digest"))
                for entry in translations
                if isinstance(entry, Mapping)
                and set(entry) == set(TRANSLATION_APPROVAL_FIELDS)
                and entry.get("plan_ref") == plan_ref
            }
        )
        if recorded:
            shown = ", ".join(digest[:16] for digest in recorded[:4])
            if len(recorded) > 4:
                shown += f", …(+{len(recorded) - 4} more)"
            detail = f"no translation approval matches plan {plan_ref} at the current projection digest (recorded digests for this plan: {shown})"
        else:
            detail = f"no translation approval matches plan {plan_ref} at the current projection digest (no approval for this plan is recorded)"
        return StagedDecisionIssue("approval_missing", detail, "")
    if len(set(matched)) > 1:
        return StagedDecisionIssue(
            "approval_conflict",
            f"plan {plan_ref} carries conflicting translation decisions or approvers",
            "",
        )
    decision, approved_by = matched[0]
    if decision != "approved":
        return StagedDecisionIssue(
            "approval_missing",
            f"the translation approval for plan {plan_ref} is {decision!r}, not approved",
            "",
        )
    if approved_by != coordinator_id:
        return StagedDecisionIssue(
            "approval_missing",
            f"the translation approval for plan {plan_ref} was recorded by "
            f"{approved_by!r}, not this run's Coordinator {coordinator_id!r}",
            "",
        )
    return None


def platform_content_hash(batch: Mapping[str, Any]) -> str:
    """The backend ``ModelingBatchService`` content hash, computed locally.

    Replicates ``_hash(_content(payload))`` from
    ``backend/app/services/modeling_batches.py``: the ontology id plus the
    ModelingItemInput projections sorted by ``client_item_id`` with the three
    set-valued lists sorted and deduplicated. Mode, lease, idempotency key and
    workspace version never enter it, so a dry-run proof and an apply of the
    same immutable content hash identically.
    """

    items: list[dict[str, Any]] = []
    ordered = sorted(
        (item for item in batch.get("items") or [] if isinstance(item, Mapping)),
        key=lambda value: str(value.get("client_item_id") or ""),
    )
    for item in ordered:
        data = _normalize_item_projection(item)
        data["depends_on"] = sorted(set(data["depends_on"]))
        data["competency_question_ids"] = sorted(set(data["competency_question_ids"]))
        items.append(data)
    content = {"ontology_id": batch.get("ontology_id"), "items": items}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_attempt_proof(
    *,
    intent_ordinal: int,
    receipt_ordinal: int,
    plan_ref: str | None,
    projection_digest: str | None,
    batch: Mapping[str, Any],
    result: Mapping[str, Any],
    response_digest: str,
) -> dict[str, Any] | None:
    """Build the Runner-owned platform Attempt binding (design §3.2/§3.4).

    Returns ``None`` — no proof, the apply gate then fails closed on the
    missing record — when the forwarder result carries no complete Attempt
    identity: a receipt without a read-back-verified Attempt is not proof,
    and a half-guessed record would be worse than none.
    """

    for field in ATTEMPT_PROOF_REQUIRED_RESULT_FIELDS:
        if not _nonempty(result.get(field)):
            return None
    if result.get("mode") not in BATCH_MODES or result.get("mode") != batch.get("mode"):
        return None
    workspace = result.get("workspace")
    workspace_before = (
        workspace.get("before_version") if isinstance(workspace, Mapping) else None
    )
    return {
        "schema_version": ATTEMPT_PROOF_SCHEMA,
        "event": ATTEMPT_PROOF_EVENT,
        "intent_ordinal": intent_ordinal,
        "receipt_ordinal": receipt_ordinal,
        "plan_ref": plan_ref,
        "projection_digest": projection_digest,
        "batch_id": result.get("batch_id"),
        "attempt_id": result.get("attempt_id"),
        "client_batch_id": batch.get("client_batch_id"),
        "idempotency_key": result.get("idempotency_key") or batch.get("idempotency_key"),
        "mode": result.get("mode"),
        "attempt_status": result.get("attempt_status"),
        "content_hash": result.get("content_hash"),
        "workspace_before_version": workspace_before,
        "response_digest": response_digest,
    }


def read_attempt_proofs(run_root: Path) -> list[dict[str, Any]]:
    """Read the Runner-written platform Attempt proofs from host evidence.

    Only records this Runner appended to ``staged-decisions.jsonl`` carry the
    fixed proof schema; agent-writable artifacts are never consulted. Records
    whose fields drift from the proof contract are not trusted as proofs and
    are skipped; an unreadable or unparsable evidence file is a typed
    reconciliation failure instead of a silent empty list.
    """

    path = Path(run_root) / "evidence" / "staged-decisions.jsonl"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise StagedDecisionArtifactError(
            "staged_unreconciled_batch", f"attempt-proof evidence is unreadable: {error}"
        ) from error
    proofs: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as error:
            raise StagedDecisionArtifactError(
                "staged_unreconciled_batch",
                f"attempt-proof evidence is unparsable: {error}",
            ) from error
        if not isinstance(record, dict):
            continue
        if record.get("schema_version") != ATTEMPT_PROOF_SCHEMA:
            continue
        if set(record) != set(ATTEMPT_PROOF_FIELDS) | {"recorded_at"}:
            continue
        proofs.append(record)
    return proofs


def unified_dry_run_proof_issue(
    run_root: Path,
    batch: Mapping[str, Any],
    *,
    plan_ref: str,
    projection_digest: str,
) -> StagedDecisionIssue | None:
    """R3.0-014: apply needs a real validated dry-run proof of this content.

    Checks the Runner-written proofs by plan identity, client batch, key
    non-reuse, the platform ``validated`` status, the immutable content hash
    and the workspace timepoint the dry-run was taken at.
    """

    proofs = [
        proof
        for proof in read_attempt_proofs(run_root)
        if proof.get("mode") == "dry_run"
        and proof.get("plan_ref") == plan_ref
        and proof.get("projection_digest") == projection_digest
        and proof.get("client_batch_id") == batch.get("client_batch_id")
    ]
    if not proofs:
        return StagedDecisionIssue(
            "dry_run_proof_missing",
            f"no Runner-recorded dry-run attempt proves plan {plan_ref}",
            "",
        )
    if batch.get("idempotency_key") in {proof.get("idempotency_key") for proof in proofs}:
        return StagedDecisionIssue(
            "idempotency_conflict",
            "the apply reuses a dry-run idempotency key",
            "",
        )
    validated = [proof for proof in proofs if proof.get("attempt_status") == "validated"]
    if not validated:
        return StagedDecisionIssue(
            "dry_run_proof_not_validated",
            f"the recorded dry-run attempts for plan {plan_ref} are not validated",
            "",
        )
    content = platform_content_hash(batch)
    matching = [proof for proof in validated if proof.get("content_hash") == content]
    if not matching:
        return StagedDecisionIssue(
            "dry_run_proof_content_mismatch",
            "the dry-run proof covers different batch content",
            "",
        )
    expected = batch.get("expected_workspace_version")
    if expected is not None and all(
        proof.get("workspace_before_version") not in (None, expected) for proof in matching
    ):
        return StagedDecisionIssue(
            "dry_run_proof_workspace_mismatch",
            "the validated dry-run proof was taken at another workspace version",
            "",
        )
    return None


def staged_intent_schema_issue(record: Mapping[str, Any]) -> StagedDecisionIssue | None:
    """Dispatch one stored intent by its recorded schema (design §9.1)."""

    schema = record.get("schema_version")
    if schema == SUBMISSION_INTENT_SCHEMA:
        if set(record) != set(INTENT_FIELDS):
            return StagedDecisionIssue(
                "unified_schema_mismatch", "intent fields drift from r3-0-008b-submission-intent/v1", ""
            )
        return None
    if schema == UNIFIED_SUBMISSION_INTENT_SCHEMA:
        if set(record) != set(UNIFIED_INTENT_FIELDS):
            return StagedDecisionIssue(
                "unified_schema_mismatch", "intent fields drift from r3-0-009-submission-intent/v2", ""
            )
        if not _nonempty(record.get("plan_ref")):
            return StagedDecisionIssue("missing_candidate_reference", "intent has no plan_ref", "")
        if record.get("projection_digest") != projection_digest(record.get("projection") or {}):
            return StagedDecisionIssue(
                "approval_content_mismatch", "intent projection digest does not match", ""
            )
        return _decision_binding_issue(record.get("decision_bindings"))
    return StagedDecisionIssue(
        "unified_schema_mismatch", f"intent schema {schema!r} is not supported", ""
    )


def staged_receipt_schema_issue(record: Mapping[str, Any]) -> StagedDecisionIssue | None:
    """Dispatch one stored receipt by its recorded schema (design §9.1)."""

    schema = record.get("schema_version")
    if schema == SUBMISSION_RECEIPT_SCHEMA:
        if set(record) != set(RECEIPT_FIELDS):
            return StagedDecisionIssue(
                "unified_schema_mismatch",
                "receipt fields drift from r3-0-008b-submission-receipt/v1",
                "",
            )
        return None
    if schema == UNIFIED_SUBMISSION_RECEIPT_SCHEMA:
        if set(record) != set(UNIFIED_RECEIPT_FIELDS):
            return StagedDecisionIssue(
                "unified_schema_mismatch",
                "receipt fields drift from r3-0-009-submission-receipt/v2",
                "",
            )
        if not _nonempty(record.get("plan_ref")):
            return StagedDecisionIssue("missing_candidate_reference", "receipt has no plan_ref", "")
        if not _nonempty(record.get("projection_digest")):
            return StagedDecisionIssue(
                "approval_content_mismatch", "receipt has no projection digest", ""
            )
        return _decision_binding_issue(record.get("decision_bindings"))
    return StagedDecisionIssue(
        "unified_schema_mismatch", f"receipt schema {schema!r} is not supported", ""
    )


def _decision_binding_issue(value: Any) -> StagedDecisionIssue | None:
    if not isinstance(value, list) or not value:
        return StagedDecisionIssue(
            "missing_candidate_reference", "submission carries no decision bindings", ""
        )
    for binding in value:
        if not isinstance(binding, Mapping) or set(binding) != set(DECISION_BINDING_FIELDS):
            return StagedDecisionIssue(
                "unified_schema_mismatch", "decision binding fields drift from the contract", ""
            )
        # The field set alone is not the shape: every close check reads the
        # digests as a map, so a non-object value (auth005: a bare ``[digest]``)
        # must be a typed rejection here, before any ``.items()``/``.values()``.
        if not isinstance(binding.get("candidate_content_digests"), Mapping):
            return StagedDecisionIssue(
                "unified_schema_mismatch",
                "decision binding candidate_content_digests must be a JSON object "
                "mapping candidate item_id to its digest",
                "",
            )
    return None


def staged_intent_receipt_issues(run_root: Path) -> tuple[StagedDecisionIssue, ...]:
    """Intent/receipt cross-checks; every issue is a kill-switch trigger."""

    intents = read_submission_intents(run_root)
    receipts = read_submission_receipts(run_root)
    receipt_ordinals = {
        receipt.get("intent_ordinal") for receipt in receipts if isinstance(receipt, Mapping)
    }
    issues: list[StagedDecisionIssue] = []
    intents_by_ordinal = {
        intent.get("ordinal"): intent for intent in intents if isinstance(intent, Mapping)
    }
    for receipt in receipts:
        receipt_issue = staged_receipt_schema_issue(receipt)
        if receipt_issue is not None:
            issues.append(receipt_issue)
            continue
        # A 009 receipt must stay bound to the projection its intent recorded;
        # a drifting digest means the receipt no longer proves the approval.
        intent = intents_by_ordinal.get(receipt.get("intent_ordinal"))
        intent_is_unified = isinstance(intent, Mapping) and (
            intent.get("schema_version") == UNIFIED_SUBMISSION_INTENT_SCHEMA
        )
        if receipt.get("schema_version") == UNIFIED_SUBMISSION_RECEIPT_SCHEMA:
            if (
                not intent_is_unified
                or intent.get("projection_digest") != receipt.get("projection_digest")
                or intent.get("plan_ref") != receipt.get("plan_ref")
            ):
                issues.append(
                    StagedDecisionIssue(
                        "approval_content_mismatch",
                        f"receipt {receipt.get('ordinal')} does not match its intent projection",
                        "capability",
                    )
                )
        elif intent_is_unified:
            # A 009 intent may only be closed by a 009 receipt; an old receipt
            # proves the old contract and never unlocks a 009 write.
            issues.append(
                StagedDecisionIssue(
                    "unified_schema_mismatch",
                    f"receipt {receipt.get('ordinal')} does not carry the 009 contract",
                    "capability",
                )
            )
    for intent in intents:
        schema_issue = staged_intent_schema_issue(intent)
        if schema_issue is not None:
            issues.append(schema_issue)
            continue
        if intent.get("status") == "unknown":
            issues.append(
                StagedDecisionIssue(
                    "staged_unreconciled_batch",
                    f"suspended unknown intent {intent.get('ordinal')}",
                    "capability",
                )
            )
        elif intent.get("status") == "receipted" and intent.get("ordinal") not in receipt_ordinals:
            issues.append(
                StagedDecisionIssue(
                    "staged_unreconciled_batch",
                    f"receipted intent {intent.get('ordinal')} has no receipt",
                    "capability",
                )
            )
    return tuple(issues)


def staged_checklist_issue(run_root: Path) -> StagedDecisionIssue | None:
    paths = staged_decision_artifact_paths(run_root)
    checklist_path = paths["checklist"]
    artifact = f"{JOINT_ACCEPTANCE_DIR}/{CHECKLIST_FILENAME}"
    if not checklist_path.exists() or checklist_path.is_symlink():
        return StagedDecisionIssue("acceptance_checklist_missing", artifact, artifact)
    checklist, issue = _try_load(load_joint_acceptance_checklist, checklist_path)
    if issue is not None or checklist is None:
        return issue
    issues = validate_joint_acceptance_checklist(checklist)
    return issues[0] if issues else None


__all__ = [
    "ANALYSIS_CONCLUSIONS_SCHEMA",
    "APPROVAL_PROJECTION_FIELDS",
    "APPROVALS_FIELDS",
    "APPROVALS_SCHEMA",
    "ACCEPTANCE_CHECKLIST_REASON_CODES",
    "ATTEMPT_PROOF_EVENT",
    "ATTEMPT_PROOF_FIELDS",
    "ATTEMPT_PROOF_REQUIRED_RESULT_FIELDS",
    "ATTEMPT_PROOF_SCHEMA",
    "BATCH_MODES",
    "CANDIDATES_DIRNAME",
    "CHECKLIST_ITEM_IDS",
    "CHECKLIST_VERDICTS",
    "CONCLUSION_ENTRY_FIELDS",
    "CONCLUSIONS_FIELDS",
    "CONCLUSIONS_REASON_CODES",
    "CONCLUSION_STATUSES",
    "DECISION_BINDING_FIELDS",
    "DECISION_FIELDS",
    "DECISION_KINDS",
    "DECISION_TARGET_KINDS",
    "ENUM_COMMAND_KINDS",
    "IDENTITY_BINDING_FIELDS",
    "INTENT_FIELDS",
    "INTENT_STATUSES",
    "JOINT_ACCEPTANCE_CHECKLIST_SCHEMA",
    "LEGAL_CONCLUSION_TRANSITIONS",
    "MAPPING_SOURCE_TYPES",
    "MATERIALIZATION_LEDGER_SCHEMA",
    "MATERIALIZATION_PLANS_DIRNAME",
    "MATERIALIZATION_UNLOCK_SCHEMA",
    "RECEIPT_FIELDS",
    "STAGE3_REASON_CODES",
    "STAGE3_SLOT_SCHEMA",
    "STAGED_GATE_FEEDBACK_SCHEMA",
    "STAGED_REASON_CODES",
    "STAGE3_DEFERRED_CONTRACT",
    "SUBMITTED_VIA",
    "SUBMISSION_INTENT_SCHEMA",
    "SUBMISSION_RECEIPT_SCHEMA",
    "TRANSLATION_APPROVAL_FIELDS",
    "UNIFIED_APPROVALS_FIELDS",
    "UNIFIED_APPROVALS_SCHEMA",
    "UNIFIED_CANDIDATE_FIELDS",
    "UNIFIED_CANDIDATE_ITEM_FIELDS",
    "UNIFIED_CANDIDATE_ITEM_KINDS",
    "UNIFIED_GRAPH_CANDIDATE_SCHEMA",
    "UNIFIED_GRAPH_CONTRACT_VERSION",
    "UNIFIED_GRAPH_TASK_PARAMETER",
    "UNIFIED_INTENT_FIELDS",
    "UNIFIED_MATERIALIZATION_PLAN_SCHEMA",
    "UNIFIED_REASON_CODES",
    "UNIFIED_RECEIPT_FIELDS",
    "UNIFIED_STAGE3_SLOT_FIELDS",
    "UNIFIED_STAGE3_SLOT_SCHEMA",
    "UNIFIED_SUBMISSION_INTENT_SCHEMA",
    "UNIFIED_SUBMISSION_RECEIPT_SCHEMA",
    "UNLOCK_MODES",
    "UNLOCK_REASON_CODES",
    "VALUE_LEVELS",
    "StagedBatchForwardError",
    "StagedBatchForwardUnknown",
    "StagedDecisionArtifactError",
    "StagedDecisionIssue",
    "StagedSubmissionRejection",
    "adjudicate_unknown_intent",
    "build_approval_projection",
    "build_attempt_proof",
    "build_batch_projection",
    "build_decision_binding",
    "build_identity_binding",
    "build_submission_intent",
    "build_submission_receipt",
    "candidate_gate_open",
    "candidate_item_digest",
    "candidate_items_digest",
    "check_stage3_candidate_artifacts",
    "cross_validate_approvals",
    "effective_confirmed_level",
    "load_analysis_conclusions",
    "load_approvals",
    "load_conclusion_archive",
    "load_joint_acceptance_checklist",
    "load_materialization_ledger",
    "load_materialization_plan",
    "load_materialization_plan_ref",
    "load_materialization_unlock",
    "load_stage3_slot",
    "load_unified_candidate",
    "mark_intent_status",
    "next_intent_ordinal",
    "next_receipt_ordinal",
    "normalize_class_iris",
    "platform_content_hash",
    "projection_digest",
    "read_attempt_proofs",
    "read_submission_intents",
    "read_submission_receipts",
    "receipted_enum_targets",
    "receipted_l3_iris",
    "reconcile_platform_batches",
    "staged_artifact_issues",
    "staged_checklist_issue",
    "staged_decision_artifact_paths",
    "staged_decision_directories",
    "staged_intent_receipt_issues",
    "staged_intent_schema_issue",
    "staged_receipt_schema_issue",
    "staged_stage3_issue",
    "unified_approval_issue",
    "unified_candidate_issue",
    "unified_dry_run_proof_issue",
    "unified_graph_mode",
    "unified_plan_issue",
    "unified_translation_issue",
    "validate_analysis_conclusions",
    "validate_approvals",
    "validate_joint_acceptance_checklist",
    "validate_materialization_ledger",
    "validate_materialization_plan",
    "validate_materialization_unlock",
    "validate_stage3_slot",
    "validate_staged_submission",
    "validate_unified_approvals",
    "validate_unified_candidate",
    "validate_unified_stage3_slot",
    "write_submission_intent",
    "write_submission_receipt",
]
