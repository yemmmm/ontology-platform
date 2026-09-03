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

ANALYSIS_CONCLUSIONS_SCHEMA = "r3-0-008b-analysis-conclusions/v1"
STAGE3_SLOT_SCHEMA = "r3-0-008b-stage3-slot/v1"
MATERIALIZATION_UNLOCK_SCHEMA = "r3-0-008b-materialization-unlock/v1"
APPROVALS_SCHEMA = "r3-0-008b-approvals/v1"
JOINT_ACCEPTANCE_CHECKLIST_SCHEMA = "r3-0-008b-joint-acceptance-checklist/v1"
MATERIALIZATION_LEDGER_SCHEMA = "r3-0-008b-materialization-ledger/v1"
SUBMISSION_INTENT_SCHEMA = "r3-0-008b-submission-intent/v1"
SUBMISSION_RECEIPT_SCHEMA = "r3-0-008b-submission-receipt/v1"
STAGED_GATE_FEEDBACK_SCHEMA = "r3-0-008b-staged-gate-feedback/v1"

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
    "staged_ledger_stale",
    "staged_unreconciled_batch",
)
ACCEPTANCE_CHECKLIST_REASON_CODES = (
    "acceptance_checklist_missing",
    "acceptance_checklist_unparsable",
    "acceptance_checklist_schema_mismatch",
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
        "evidence_refs",
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


def staged_decision_artifact_paths(run_root: Path) -> dict[str, Path]:
    """Canonical staged artifact paths inside one run workspace."""

    root = Path(run_root)
    value_semantics = root / VALUE_SEMANTICS_DIR
    return {
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


def staged_decision_directories(run_root: Path) -> list[Path]:
    """Every staged artifact directory the Runner prepares (mkdir only)."""

    root = Path(run_root)
    value_semantics = root / VALUE_SEMANTICS_DIR
    return [
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


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_nonempty(item) for item in value)


def _optional_nonempty_strings(value: Any) -> bool:
    return value is None or (isinstance(value, list) and all(_nonempty(item) for item in value))


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
        if not _nonempty(entry.get("candidate_value")) or not _nonempty(
            entry.get("business_meaning_hypothesis")
        ):
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:text fields", artifact)
            )
        if not _nonempty_strings(entry.get("evidence_refs")):
            issues.append(
                StagedDecisionIssue("conclusions_schema_mismatch", f"{conclusion_id}:evidence_refs", artifact)
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
        has_confirmed_value = _nonempty(entry.get("confirmed_enum_value"))
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
            if not has_confirmed_value or not has_confirmed_by or has_conflict_note:
                issues.append(
                    StagedDecisionIssue(
                        "conclusions_invalid_status_fields", f"{conclusion_id}:{status}", artifact
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


def validate_approvals(value: Any) -> tuple[StagedDecisionIssue, ...]:
    artifact = f"{VALUE_SEMANTICS_DIR}/{APPROVALS_DIRNAME}/{APPROVALS_FILENAME}"
    if not isinstance(value, Mapping) or set(value) != APPROVALS_FIELDS:
        return (StagedDecisionIssue("approvals_schema_mismatch", "fields drift", artifact),)
    if value["schema_version"] != APPROVALS_SCHEMA:
        return (StagedDecisionIssue("approvals_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["maintained_by"]):
        return (StagedDecisionIssue("approvals_schema_mismatch", "identity", artifact),)
    entries = value["entries"]
    if not isinstance(entries, list):
        return (StagedDecisionIssue("approvals_schema_mismatch", "entries", artifact),)
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
        if kind == "conclusion_confirmation" and not _nonempty(entry.get("confirmed_enum_value")):
            issues.append(
                StagedDecisionIssue("approvals_schema_mismatch", "confirmed_enum_value", artifact)
            )
        if kind == "stage3_slot" and entry.get("confirmed_enum_value") is not None:
            issues.append(
                StagedDecisionIssue("approvals_schema_mismatch", "stage3 confirmed_enum_value", artifact)
            )
        if entry.get("note") is not None and not _nonempty(entry.get("note")):
            issues.append(StagedDecisionIssue("approvals_schema_mismatch", "note", artifact))
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


def validate_stage3_slot(value: Any) -> tuple[StagedDecisionIssue, ...]:
    artifact = f"{STAGE3_NEUTRAL_GRAPH_DIR}/{STAGE3_SLOT_FILENAME}"
    if not isinstance(value, Mapping) or set(value) - STAGE3_SLOT_FIELDS:
        return (StagedDecisionIssue("stage3_schema_mismatch", "fields drift", artifact),)
    missing = STAGE3_SLOT_FIELDS - set(value)
    if missing:
        return (StagedDecisionIssue("stage3_schema_mismatch", f"missing {sorted(missing)}", artifact),)
    if value["schema_version"] != STAGE3_SLOT_SCHEMA:
        return (StagedDecisionIssue("stage3_schema_mismatch", "schema_version", artifact),)
    if not _nonempty(value["scenario_id"]) or not _nonempty(value["produced_by"]):
        return (StagedDecisionIssue("stage3_schema_mismatch", "identity", artifact),)
    if not _nonempty(value["approved_by"]):
        return (StagedDecisionIssue("stage3_missing_approval", "approved_by", artifact),)
    if value.get("deferred_contract") != STAGE3_DEFERRED_CONTRACT:
        return (StagedDecisionIssue("stage3_schema_mismatch", "deferred_contract", artifact),)
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


def _batch_envelope_issues(batch: Any) -> StagedDecisionIssue | None:
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
        _batch_envelope_issues(batch),
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
            if (
                conclusion.get("mapped_property") != payload_map.get("property_iri")
                or conclusion.get("confirmed_enum_value") != payload_map.get("enum_value")
            ):
                issues.append(StagedDecisionIssue("staged_trace_mismatch", f"command {index}", "capability"))
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
                if payload_map.get("enum_value") != conclusion.get("confirmed_enum_value"):
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
) -> dict[str, Any]:
    return {
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
    return {
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
    issues = validate_stage3_slot(slot)
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


def staged_artifact_issues(run_root: Path) -> tuple[StagedDecisionIssue, ...]:
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


def staged_intent_receipt_issues(run_root: Path) -> tuple[StagedDecisionIssue, ...]:
    """Intent/receipt cross-checks; every issue is a kill-switch trigger."""

    intents = read_submission_intents(run_root)
    receipts = read_submission_receipts(run_root)
    receipt_ordinals = {
        receipt.get("intent_ordinal") for receipt in receipts if isinstance(receipt, Mapping)
    }
    issues: list[StagedDecisionIssue] = []
    for intent in intents:
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
    "APPROVALS_FIELDS",
    "APPROVALS_SCHEMA",
    "ACCEPTANCE_CHECKLIST_REASON_CODES",
    "BATCH_MODES",
    "CHECKLIST_ITEM_IDS",
    "CHECKLIST_VERDICTS",
    "CONCLUSION_ENTRY_FIELDS",
    "CONCLUSIONS_FIELDS",
    "CONCLUSIONS_REASON_CODES",
    "CONCLUSION_STATUSES",
    "ENUM_COMMAND_KINDS",
    "INTENT_FIELDS",
    "INTENT_STATUSES",
    "JOINT_ACCEPTANCE_CHECKLIST_SCHEMA",
    "LEGAL_CONCLUSION_TRANSITIONS",
    "MAPPING_SOURCE_TYPES",
    "MATERIALIZATION_LEDGER_SCHEMA",
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
    "UNLOCK_MODES",
    "UNLOCK_REASON_CODES",
    "VALUE_LEVELS",
    "StagedBatchForwardError",
    "StagedBatchForwardUnknown",
    "StagedDecisionArtifactError",
    "StagedDecisionIssue",
    "StagedSubmissionRejection",
    "adjudicate_unknown_intent",
    "build_submission_intent",
    "build_submission_receipt",
    "canonical_command_digest",
    "candidate_gate_open",
    "check_stage3_candidate_artifacts",
    "cross_validate_approvals",
    "effective_confirmed_level",
    "load_analysis_conclusions",
    "load_approvals",
    "load_conclusion_archive",
    "load_joint_acceptance_checklist",
    "load_materialization_ledger",
    "load_materialization_unlock",
    "load_stage3_slot",
    "mark_intent_status",
    "next_intent_ordinal",
    "next_receipt_ordinal",
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
    "staged_stage3_issue",
    "validate_analysis_conclusions",
    "validate_approvals",
    "validate_joint_acceptance_checklist",
    "validate_materialization_ledger",
    "validate_materialization_unlock",
    "validate_stage3_slot",
    "validate_staged_submission",
    "write_submission_intent",
    "write_submission_receipt",
]
