"""Runner-owned Acceptance contracts for R2.3-005.

This module intentionally contains deterministic, local-only mechanics.  It does not
start an Agent, read a source bundle, call the platform, or decide a semantic answer.
The real Runtime adapter may use the records emitted here, while unit tests can exercise
the complete ticket/child/report/verdict lifecycle without a semantic start.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import time
from dataclasses import dataclass, field as dataclass_field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .capability_mcp import (
    ACCEPTANCE_OPERATIONS,
    COORDINATOR_OPERATIONS,
    COORDINATOR_FORMAL_OPERATIONS,
    MODELING_OPERATIONS,
    PROTOCOL_OPERATIONS,
    PROTOCOL_STAGE_OPERATIONS,
    ROLE_OPERATIONS,
    RunnerCapabilityEndpoint,
    token_digest,
)
from .protocol_retrieval_gate import (
    ProtocolRetrievalGate,
    ProtocolRetrievalGateError,
)


class AcceptanceContractError(ValueError):
    """A malformed or out-of-scope Acceptance contract must fail closed."""


class AcceptancePhase(StrEnum):
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    MODELING_ACTIVE = "MODELING_ACTIVE"
    WAITING_ACCEPTANCE = "WAITING_ACCEPTANCE"
    ACCEPTANCE_ROUND_ACTIVE = "ACCEPTANCE_ROUND_ACTIVE"
    ACCEPTANCE_REPORTS_READY = "ACCEPTANCE_REPORTS_READY"
    STATE_REVALIDATION = "STATE_REVALIDATION"
    TICKET_REISSUED = "TICKET_REISSUED"
    SETTLED = "SETTLED"
    CLEANED = "CLEANED"


PERSISTENT_ROLES: tuple[str, ...] = ("coordinator", "modeling", "protocol", "acceptance")
EXAMINER_KINDS: frozenset[str] = frozenset({"source", "platform"})
EXAMINER_DESCRIPTOR_KINDS: frozenset[str] = frozenset(
    {"source_examiner", "platform_examiner"}
)
ACCEPTANCE_FAILURE_LAYERS: frozenset[str] = frozenset(
    {"modeling-quality", "interview", "protocol-delivery", "platform", "runtime"}
)
BLOCKED_REASONS: frozenset[str] = frozenset(
    {"acceptance-evidence", "acceptance-input", "runtime-infrastructure", "source-missing", "state-invalidated"}
)
CHECK_KEYS: tuple[str, ...] = (
    "source_fidelity",
    "scope",
    "ontology_structure",
    "explicit_unknowns",
    "validation_reasoning",
    "governed_retrieval",
    "evidence_lineage",
    "competency_questions",
)
MODELING_STAGES: tuple[str, ...] = ("dry-run", "apply", "readback", "validation", "reasoning")
READ_ONLY_VALIDATION_TOOLS: frozenset[str] = frozenset(
    {
        "list_semantic_validation_runs",
        "get_semantic_validation_run",
        "list_semantic_reasoning_runs",
        "get_semantic_reasoning_run",
    }
)
MODEL_STATE_FIELDS: tuple[str, ...] = (
    "project_id",
    "ontology_id",
    "workspace_version",
    "source_signature",
    "build_session_id",
    "graph_set_id",
)

# The formal stage handoff does not accept an arbitrary platform read as proof
# of a particular stage.  These are the only Runner-observed calls that may
# bind each receipt.  The write modes are carried in the original MCP request
# arguments; readback is deliberately restricted to the generic model-context
# read wrappers, while validation/reasoning each have one dedicated tool.
STAGE_TOOL_BINDINGS: dict[str, tuple[frozenset[str], str | None]] = {
    "dry-run": (frozenset({"submit_modeling_batch"}), "dry_run"),
    "apply": (frozenset({"submit_modeling_batch"}), "apply_atomic"),
    "readback": (frozenset({"get_modeling_context"}), None),
    "validation": (frozenset({"run_semantic_validation"}), None),
    "reasoning": (frozenset({"run_semantic_reasoning"}), None),
}

# Prompt E keeps the Protocol-to-Coordinator boundary a typed, Runner-bound
# handoff.  The handoff is deliberately not an Acceptance ticket: it carries
# only current-run mechanics and opaque semantic/candidate digests.  The
# Runner-owned draft builder adds the approved source manifest, frozen CQ
# policy, read allowlist, and live model state before the existing strict
# ticket validator is invoked.
STAGE_HANDOFF_SCHEMA = "r2-3-005-acceptance-stage-handoff/v1"


def _error(message: str) -> None:
    raise AcceptanceContractError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strip_digest_fields(value: Any, *, self_field: str) -> Any:
    """Create the one canonical digest preimage used by tickets and verdicts.

    Only the envelope's self digest and nested ticket-digest references are removed.
    Other digest fields are evidence bindings and remain part of the preimage.
    """
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key == self_field:
                result[key] = None
            elif key == "ticket_digest":
                result[key] = None
            else:
                result[key] = _strip_digest_fields(child, self_field=self_field)
        return result
    if isinstance(value, list):
        return [_strip_digest_fields(item, self_field=self_field) for item in value]
    if isinstance(value, tuple):
        return [_strip_digest_fields(item, self_field=self_field) for item in value]
    return value


def canonical_digest(value: Mapping[str, Any], *, self_field: str) -> str:
    """Return the SHA-256 of a canonical self-reference-safe envelope."""
    if not isinstance(value, Mapping) or not isinstance(self_field, str) or not self_field:
        _error("digest preimage must be an object and self field must be non-empty")
    return _sha256_bytes(_canonical_json(_strip_digest_fields(value, self_field=self_field)))


def ticket_digest(ticket: Mapping[str, Any]) -> str:
    return canonical_digest(ticket, self_field="ticket_digest")


def model_state_digest(model_state: Mapping[str, Any]) -> str:
    """Hash the complete Producer state without recursively including the digest.

    The six identity/version fields are the sole canonical preimage.  Keeping the
    schema marker and explicit field map stable prevents a caller from supplying an
    arbitrary 64-hex placeholder that would otherwise flow through ticket, report,
    and verdict bindings as if it represented the platform state.
    """

    if not isinstance(model_state, Mapping):
        _error("model-state digest preimage must be an object")
    if set(model_state) - set(MODEL_STATE_FIELDS) - {"state_digest"}:
        _error("model-state digest preimage contains unknown fields")
    fields = {
        field: model_state.get(field)
        for field in MODEL_STATE_FIELDS
    }
    return _sha256_bytes(
        _canonical_json(
            {
                "schema_version": "r2-3-005-model-state/v1",
                "fields": fields,
            }
        )
    )


def modeling_receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the canonical digest for one Producer stage receipt."""

    return canonical_digest(receipt, self_field="receipt_digest")


def verdict_digest(verdict: Mapping[str, Any]) -> str:
    return canonical_digest(verdict, self_field="verdict_digest")


def _digest_matches(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _safe_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,127}", value):
        _error(f"{field} must be a safe stable identifier")
    return value


def _safe_platform_id(value: Any, field: str) -> str:
    """Validate a concrete platform identifier without imposing role-ID rules.

    Platform resources use UUID-shaped identifiers in live runs, including values
    whose first character is a digit.  Keep the stricter ``_safe_id`` contract for
    task, role, and other stable workflow identifiers, while allowing the platform
    scope to represent the identifiers returned by the platform itself.
    """

    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?", value):
        _error(f"{field} must be a safe platform identifier")
    return value


def _safe_digest(value: Any, field: str) -> str:
    if not _digest_matches(value):
        _error(f"{field} must be a lowercase sha256 digest")
    return value


def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        _error(f"{field} must be a repository-relative path")
    return value


def _require_exact_keys(value: Any, keys: Iterable[str], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        _error(f"{name} fields drift")
    return dict(value)


def _require_fields(value: Any, keys: Iterable[str], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not set(keys).issubset(value):
        _error(f"{name} is missing required fields")
    return dict(value)


def _safe_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def validate_profile_roster(agents: Any, *, strict: bool = True) -> tuple[dict[str, Any], ...]:
    """Validate the exact formal roster while retaining an explicit legacy opt-out.

    ``strict=True`` is used by the R2.3-005 Profile/Runner.  The opt-out exists only
    for archived R2.3-001/R2.3-002 deterministic fixtures and cannot be used by the
    formal ``RunnerAcceptanceCarrier``.
    """
    if not isinstance(agents, list) or not agents:
        _error("Profile requires agents")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    roles: list[str] = []
    for item in agents:
        if not isinstance(item, Mapping) or set(item) != {"agent_id", "package"}:
            _error("Profile Agent fields drift")
        agent_id = _safe_id(item["agent_id"], "agent_id")
        package = _safe_id(item["package"], "package")
        if agent_id in ids:
            _error("Profile duplicates Agent ID")
        ids.add(agent_id)
        normalized.append({"agent_id": agent_id, "package": package})
        roles.append(package)
    if strict:
        if len(normalized) != 4 or set(roles) != set(PERSISTENT_ROLES) or len(set(roles)) != 4:
            _error("formal Profile requires exactly Coordinator, Modeling, Protocol, and Acceptance")
    elif roles.count("coordinator") != 1 or roles.count("protocol") != 1:
        _error("Profile requires exactly one Coordinator and Protocol")
    return tuple(normalized)


def validate_child_descriptor(descriptor: Any) -> dict[str, Any]:
    expected = {
        "kind",
        "package_digest",
        "platform_mode",
        "can_team_transport",
        "can_spawn",
        "can_write",
        "max_children",
    }
    data = _require_exact_keys(descriptor, expected, "child descriptor")
    if data["kind"] not in EXAMINER_DESCRIPTOR_KINDS:
        _error("arbitrary Examiner package kind is rejected")
    _safe_digest(data["package_digest"], "child descriptor package_digest")
    if data["platform_mode"] not in {"none", "read"}:
        _error("Examiner platform mode must be none or read")
    if any(data[field] is not False for field in ("can_team_transport", "can_spawn", "can_write")):
        _error("Examiner cannot transport, spawn, or write")
    if data["max_children"] != 0:
        _error("Examiner cannot create nested children")
    return data


def validate_child_input(kind: str, value: Any) -> dict[str, Any]:
    if kind == "source":
        data = _require_exact_keys(value, {"question", "approved_sources", "source_bundle_digest"}, "Source projection")
        if not isinstance(data["question"], str) or not data["question"]:
            _error("Source projection question is invalid")
        if not isinstance(data["approved_sources"], list) or not data["approved_sources"]:
            _error("Source projection requires approved sources")
        _safe_digest(data["source_bundle_digest"], "Source projection source_bundle_digest")
        return data
    if kind == "platform":
        data = _require_exact_keys(
            value,
            {"question", "model_state", "platform_read_scope", "allowed_read_tools"},
            "Platform projection",
        )
        if not isinstance(data["question"], str) or not data["question"]:
            _error("Platform projection question is invalid")
        validate_model_state(data["model_state"], allow_runner_bound=False)
        validate_platform_read_scope(data["platform_read_scope"])
        if not isinstance(data["allowed_read_tools"], list) or not data["allowed_read_tools"]:
            _error("Platform projection allowlist is empty")
        if any(tool not in set(canonical_platform_allowlist()) for tool in data["allowed_read_tools"]):
            _error("Platform projection allowlist contains a non-read-only tool")
        if any(tool not in set(data["allowed_read_tools"]) for tool in READ_ONLY_VALIDATION_TOOLS):
            # The four generic result readers are mandatory for the formal contract.
            _error("Platform projection omits a generic validation/reasoning read wrapper")
        if any(not isinstance(tool, str) for tool in data["allowed_read_tools"]):
            _error("Platform projection allowlist contains invalid tool")
        return data
    _error("unknown child input kind")


def validate_platform_read_scope(value: Any) -> dict[str, Any]:
    data = _require_exact_keys(value, {"project_id", "ontology_id", "graph_set_id"}, "platform_read_scope")
    for field in data:
        _safe_platform_id(data[field], f"platform_read_scope.{field}")
    return data


def validate_model_state(value: Any, *, allow_runner_bound: bool = True) -> dict[str, Any]:
    fields = set(MODEL_STATE_FIELDS) | {"state_digest"}
    data = _require_exact_keys(value, fields, "model_state")
    for field in MODEL_STATE_FIELDS:
        if not isinstance(data[field], str) or not data[field]:
            _error(f"model_state.{field} is invalid")
        if not allow_runner_bound and data[field] == "runner-bound":
            _error("model_state must be resolved before child start")
    _safe_digest(data["state_digest"], "model_state.state_digest")
    if data["state_digest"] != model_state_digest(data):
        _error("model_state.state_digest does not match canonical state")
    return data


def validate_typed_evidence_ref(value: Any, *, expected_ticket: str | None = None, expected_state: str | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("type") not in {"approved_source", "platform_read", "infrastructure_failure"}:
        _error("typed evidence reference has an invalid type")
    data = dict(value)
    kind = data["type"]
    if kind == "approved_source":
        expected = {"type", "ref_id", "ticket_digest", "source_bundle_digest", "location", "artifact_path", "artifact_digest"}
        if set(data) != expected:
            _error("approved_source evidence fields drift")
        _safe_id(data["ref_id"], "approved_source.ref_id")
        _safe_digest(data["ticket_digest"], "approved_source.ticket_digest")
        _safe_digest(data["source_bundle_digest"], "approved_source.source_bundle_digest")
        _safe_relative_path(data["artifact_path"], "approved_source.artifact_path")
        _safe_digest(data["artifact_digest"], "approved_source.artifact_digest")
        if not isinstance(data["location"], str) or not data["location"]:
            _error("approved_source location is invalid")
    elif kind == "platform_read":
        expected = {"type", "ref_id", "ticket_digest", "model_state_digest", "tool", "request_digest", "response_digest", "artifact_path", "page"}
        if set(data) != expected:
            _error("platform_read evidence fields drift")
        _safe_id(data["ref_id"], "platform_read.ref_id")
        _safe_digest(data["ticket_digest"], "platform_read.ticket_digest")
        _safe_digest(data["model_state_digest"], "platform_read.model_state_digest")
        _safe_digest(data["request_digest"], "platform_read.request_digest")
        _safe_digest(data["response_digest"], "platform_read.response_digest")
        _safe_relative_path(data["artifact_path"], "platform_read.artifact_path")
        page = _require_exact_keys(data["page"], {"ordinal", "input_cursor", "output_cursor", "has_more", "sequence_complete"}, "platform_read.page")
        if not isinstance(page["ordinal"], int) or page["ordinal"] < 0:
            _error("platform_read page ordinal is invalid")
        if not isinstance(page["has_more"], bool) or not isinstance(page["sequence_complete"], bool):
            _error("platform_read page flags are invalid")
        if page["has_more"] and page["sequence_complete"]:
            _error("a page cannot be both incomplete and sequence complete")
    else:
        # A failure ref is emitted only after Runner has a durable cleanup
        # receipt.  The compact core is stable; optional ticket/input digests
        # are retained when the carrier has them so the ref can be joined back
        # to the immutable failure record without exposing an error string.
        expected = {
            "type",
            "failure_digest",
            "cleanup_receipt_digest",
            "task_id",
            "acceptance_round_id",
            "child_handle_digest",
            "attempt",
            "failure_category",
        }
        optional = {"ticket_digest", "child_input_digest", "reason_code"}
        if set(data) - expected - optional or not expected.issubset(data):
            _error("infrastructure_failure evidence fields drift")
        for field in ("failure_digest", "cleanup_receipt_digest", "child_handle_digest"):
            _safe_digest(data[field], f"infrastructure_failure.{field}")
        _safe_id(data["task_id"], "infrastructure_failure.task_id")
        _safe_id(data["acceptance_round_id"], "infrastructure_failure.acceptance_round_id")
        for field in ("ticket_digest", "child_input_digest"):
            if field in data:
                _safe_digest(data[field], f"infrastructure_failure.{field}")
        if data["attempt"] not in {0, 1} or not isinstance(data["failure_category"], str) or not data["failure_category"]:
            _error("infrastructure_failure attempt/category is invalid")
        if "reason_code" in data and (not isinstance(data["reason_code"], str) or not data["reason_code"]):
            _error("infrastructure_failure reason_code is invalid")
    if expected_ticket is not None and data.get("ticket_digest") not in {expected_ticket, None}:
        _error("typed evidence ticket digest mismatch")
    if expected_state is not None and kind == "platform_read" and data.get("model_state_digest") != expected_state:
        _error("typed evidence model-state digest mismatch")
    return data


def validate_page_chain(refs: Iterable[Mapping[str, Any]]) -> None:
    pages: list[dict[str, Any]] = []
    for ref in refs:
        if ref.get("type") == "platform_read":
            pages.append(validate_typed_evidence_ref(ref))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ref in pages:
        grouped.setdefault((str(ref["tool"]), str(ref["request_digest"])), []).append(ref)
    for chain in grouped.values():
        chain.sort(key=lambda item: item["page"]["ordinal"])
        for index, item in enumerate(chain):
            page = item["page"]
            if page["ordinal"] != index:
                _error("platform evidence page chain has a gap")
            if index < len(chain) - 1:
                if page["output_cursor"] is None:
                    _error("platform evidence cursor chain is broken")
                if chain[index + 1]["page"]["input_cursor"] != page["output_cursor"]:
                    _error("platform evidence input cursor does not continue the prior page")
            if index == len(chain) - 1 and not page["sequence_complete"]:
                _error("platform evidence page chain is incomplete")


def validate_modeling_receipt(value: Any, *, run_id: str, project_id: str, ontology_id: str, slice_revision: str, state_digest: str, ticket_digest: str) -> dict[str, Any]:
    fields = {"stage", "status", "receipt_digest", "run_id", "project_id", "ontology_id", "slice_revision", "model_state_digest", "evidence_ref"}
    data = _require_exact_keys(value, fields, "modeling receipt")
    if data["stage"] not in MODELING_STAGES:
        _error("modeling receipt stage is invalid")
    required_status = {"dry-run": "validated", "apply": "applied", "readback": "complete", "validation": "succeeded", "reasoning": "succeeded"}[data["stage"]]
    if data["status"] != required_status:
        _error("modeling receipt status is not successful for its stage")
    _safe_digest(data["receipt_digest"], "modeling receipt digest")
    if data["receipt_digest"] != modeling_receipt_digest(data):
        _error("modeling receipt digest does not match canonical preimage")
    for field, expected in (("run_id", run_id), ("project_id", project_id), ("ontology_id", ontology_id), ("slice_revision", slice_revision), ("model_state_digest", state_digest)):
        if data[field] != expected:
            _error(f"modeling receipt {field} mismatch")
    ref = validate_typed_evidence_ref(data["evidence_ref"], expected_ticket=ticket_digest, expected_state=state_digest)
    if ref["type"] != "platform_read":
        _error("modeling receipt evidence must be platform_read")
    return data


def stage_handoff_digest(handoff: Mapping[str, Any]) -> str:
    """Return the canonical digest for one Protocol stage handoff."""

    return canonical_digest(handoff, self_field="handoff_digest")


def validate_stage_handoff(
    value: Any,
    *,
    expected_task_id: str | None = None,
    expected_run_id: str | None = None,
    expected_nonce: str | None = None,
    expected_delivery_digest: str | None = None,
) -> dict[str, Any]:
    """Validate the exact current-run receipt handoff used by Prompt E.

    ``handoff_digest`` is used as the temporary ticket binding for each typed
    platform evidence reference.  It is intentionally replaced by the draft
    ticket digest only after all Runner-owned values have been assembled.  The
    receipt digest itself excludes nested ``ticket_digest`` fields, so this
    rebinding cannot relabel or fabricate stage evidence.
    """

    fields = {
        "schema_version",
        "handoff_id",
        "handoff_nonce",
        "task_id",
        "producer_run_id",
        "slice_id",
        "slice_revision",
        "model_state",
        "model_state_digest",
        "candidate_digest",
        "modeling_receipts",
        "handoff_digest",
    }
    data = _require_exact_keys(value, fields, "acceptance stage handoff")
    if data["schema_version"] != STAGE_HANDOFF_SCHEMA:
        _error("acceptance stage handoff schema_version is unsupported")
    for field in (
        "handoff_id",
        "task_id",
        "producer_run_id",
        "slice_id",
        "slice_revision",
    ):
        _safe_id(data[field], f"stage handoff.{field}")
    _safe_digest(data["handoff_nonce"], "stage handoff.handoff_nonce")
    _safe_digest(data["candidate_digest"], "stage handoff.candidate_digest")
    _safe_digest(data["handoff_digest"], "stage handoff.handoff_digest")
    state = validate_model_state(data["model_state"], allow_runner_bound=False)
    if data["model_state_digest"] != state["state_digest"]:
        _error("stage handoff model_state_digest mismatch")
    _safe_digest(data["model_state_digest"], "stage handoff.model_state_digest")
    if expected_task_id is not None and data["task_id"] != expected_task_id:
        _error("stage handoff task does not match Runner task")
    if expected_run_id is not None and data["producer_run_id"] != expected_run_id:
        _error("stage handoff run does not match Runner run")
    if expected_nonce is not None and data["handoff_nonce"] != expected_nonce:
        _error("stage handoff nonce is not the Runner-issued nonce")
    if expected_delivery_digest is not None and _sha256_bytes(_canonical_json(data)) != expected_delivery_digest:
        _error("stage handoff canonical bytes do not match Team Transport delivery")
    if data["handoff_digest"] != stage_handoff_digest(data):
        _error("stage handoff digest does not match canonical preimage")

    receipts = data["modeling_receipts"]
    if not isinstance(receipts, list) or len(receipts) != len(MODELING_STAGES):
        _error("stage handoff must contain exactly five modeling receipts")
    seen_stages: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            _error("stage handoff modeling receipt is invalid")
        evidence = receipt.get("evidence_ref")
        if not isinstance(evidence, Mapping) or evidence.get("ticket_digest") != data["handoff_digest"]:
            _error("stage handoff evidence is not bound to handoff digest")
        normalized = validate_modeling_receipt(
            receipt,
            run_id=data["producer_run_id"],
            project_id=state["project_id"],
            ontology_id=state["ontology_id"],
            slice_revision=data["slice_revision"],
            state_digest=data["model_state_digest"],
            ticket_digest=data["handoff_digest"],
        )
        if normalized["stage"] in seen_stages:
            _error("stage handoff modeling receipts duplicate a stage")
        seen_stages.add(normalized["stage"])
    if seen_stages != set(MODELING_STAGES):
        _error("stage handoff modeling receipts omit a required stage")
    return _safe_copy(data)


def _validate_sources(sources: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(sources, list) or not sources:
        _error("ticket approved_sources is empty")
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        data = _require_exact_keys(source, {"path", "sha256"}, "approved source")
        path = _safe_relative_path(data["path"], "approved source path")
        digest = _safe_digest(data["sha256"], "approved source sha256")
        if path in seen:
            _error("ticket approved_sources contains duplicates")
        seen.add(path)
        output.append({"path": path, "sha256": digest})
    if output != sorted(output, key=lambda item: item["path"]):
        _error("ticket approved_sources must be canonical ordered")
    return tuple(output)


def validate_ticket(ticket: Any, *, expected_owner_revision: str | None = None) -> dict[str, Any]:
    fields = {
        "schema_version", "ticket_id", "acceptance_round_id", "task_id", "producer_run_id", "slice_id", "slice_revision", "question_id", "question", "approved_sources", "source_bundle_digest", "platform_read_scope", "model_state", "model_state_digest", "competency_questions", "allowed_read_tools", "modeling_receipts", "timeout_seconds", "quality_standard_ref", "quality_standard_digest", "quality_standard_artifact", "unknown_policy", "ticket_revision", "ticket_digest",
    }
    data = _require_exact_keys(ticket, fields, "acceptance ticket")
    if data["schema_version"] != "r2-3-005-slice-acceptance-ticket/v1":
        _error("ticket schema_version is unsupported")
    for field in ("ticket_id", "acceptance_round_id", "task_id", "producer_run_id", "slice_id", "slice_revision", "question_id"):
        _safe_id(data[field], f"ticket.{field}")
    if not isinstance(data["question"], str) or not data["question"]:
        _error("ticket question is invalid")
    sources = _validate_sources(data["approved_sources"])
    _safe_digest(data["source_bundle_digest"], "ticket source_bundle_digest")
    validate_platform_read_scope(data["platform_read_scope"])
    state = validate_model_state(data["model_state"], allow_runner_bound=False)
    if data["model_state_digest"] != state["state_digest"]:
        _error("ticket model_state_digest mismatch")
    cqs = data["competency_questions"]
    if not isinstance(cqs, list) or not cqs:
        _error("ticket competency_questions is empty")
    cq_by_id: dict[str, str] = {}
    for cq in cqs:
        item = _require_exact_keys(cq, {"id", "question"}, "competency question")
        cq_id = _safe_id(item["id"], "competency question id")
        if not isinstance(item["question"], str) or not item["question"] or cq_id in cq_by_id:
            _error("ticket competency question is invalid or duplicated")
        cq_by_id[cq_id] = item["question"]
    if data["question_id"] not in cq_by_id or cq_by_id[data["question_id"]] != data["question"]:
        _error("ticket question projection does not match competency_questions")
    tools = data["allowed_read_tools"]
    if not isinstance(tools, list) or not tools or any(not isinstance(tool, str) for tool in tools) or list(dict.fromkeys(tools)) != tools:
        _error("ticket allowed_read_tools is invalid")
    canonical_tools = set(canonical_platform_allowlist())
    if any(tool not in canonical_tools for tool in tools):
        _error("ticket allowed_read_tools contains a non-read-only tool")
    if not READ_ONLY_VALIDATION_TOOLS.issubset(tools):
        _error("ticket omits generic validation/reasoning read wrappers")
    receipts = data["modeling_receipts"]
    if not isinstance(receipts, list) or not receipts:
        _error("ticket modeling_receipts is empty")
    seen_stages: set[str] = set()
    for receipt in receipts:
        normalized = validate_modeling_receipt(
            receipt,
            run_id=data["producer_run_id"],
            project_id=data["model_state"]["project_id"],
            ontology_id=data["model_state"]["ontology_id"],
            slice_revision=data["slice_revision"],
            state_digest=data["model_state_digest"],
            ticket_digest=data["ticket_digest"],
        )
        if normalized["stage"] in seen_stages:
            _error("ticket modeling_receipts duplicates a stage")
        seen_stages.add(normalized["stage"])
    if seen_stages != set(MODELING_STAGES):
        _error("ticket modeling_receipts must contain all five current-run stages")
    if not isinstance(data["timeout_seconds"], int) or isinstance(data["timeout_seconds"], bool) or data["timeout_seconds"] <= 0:
        _error("ticket timeout_seconds must be positive")
    _safe_digest(data["quality_standard_digest"], "ticket quality_standard_digest")
    artifact = _require_exact_keys(data["quality_standard_artifact"], {"path", "digest"}, "ticket quality_standard_artifact")
    _safe_relative_path(artifact["path"], "ticket quality_standard_artifact.path")
    _safe_digest(artifact["digest"], "ticket quality_standard_artifact.digest")
    if not isinstance(data["quality_standard_ref"], str) or not data["quality_standard_ref"]:
        _error("ticket quality_standard_ref is invalid")
    if data["unknown_policy"] != "preserve-explicit-unknown" or not isinstance(data["ticket_revision"], int) or data["ticket_revision"] <= 0:
        _error("ticket unknown policy/revision is invalid")
    if expected_owner_revision is not None and data["quality_standard_ref"] != expected_owner_revision:
        _error("ticket owner revision mismatch")
    computed = ticket_digest(data)
    if data["ticket_digest"] != computed:
        _error("ticket_digest does not match canonical preimage")
    # The source bundle digest is a bundle identity, not a digest of paths alone; at
    # minimum ensure it is deterministic for the ordered source manifest supplied.
    if _sha256_bytes(_canonical_json(list(sources))) != data["source_bundle_digest"]:
        _error("source_bundle_digest does not match approved source manifest")
    return _safe_copy(data)


def validate_report(report: Any, *, ticket: Mapping[str, Any], kind: str, handle_digest: str, input_digest: str, session_id: str) -> dict[str, Any]:
    fields = {"task_id", "acceptance_round_id", "ticket_digest", "examiner_kind", "child_handle_digest", "child_session_id", "child_input_digest", "source_bundle_digest", "answerability", "conclusion", "evidence", "coverage", "gaps", "model_state", "evidence_refs", "report_digest"}
    data = _require_exact_keys(report, fields, "Examiner report")
    if kind not in EXAMINER_KINDS:
        _error("unknown Examiner kind")
    if data["examiner_kind"] != kind or data["ticket_digest"] != ticket["ticket_digest"] or data["child_handle_digest"] != handle_digest or data["child_input_digest"] != input_digest or data["child_session_id"] != session_id:
        _error("Examiner report binding mismatch")
    if data["task_id"] != ticket["task_id"] or data["acceptance_round_id"] != ticket["acceptance_round_id"]:
        _error("Examiner report task/round mismatch")
    if kind == "source":
        if data["source_bundle_digest"] != ticket["source_bundle_digest"]:
            _error("Source report source bundle mismatch")
    elif data["source_bundle_digest"] is not None:
        _error("Platform report cannot carry source bundle")
    if data["answerability"] not in {"answerable", "insufficient-evidence", "unavailable"}:
        _error("Examiner report answerability is invalid")
    if not isinstance(data["conclusion"], str) or not data["conclusion"]:
        _error("Examiner report conclusion is empty")
    if not isinstance(data["evidence"], list) or not isinstance(data["gaps"], list):
        _error("Examiner report evidence/gaps are invalid")
    coverage = _require_exact_keys(data["coverage"], {"queries_or_sections", "complete"}, "Examiner report coverage")
    if not isinstance(coverage["queries_or_sections"], list) or not isinstance(coverage["complete"], bool):
        _error("Examiner report coverage is invalid")
    state = validate_model_state(data["model_state"])
    if state["state_digest"] != ticket["model_state_digest"]:
        _error("Examiner report model state mismatch")
    refs = data["evidence_refs"]
    if not isinstance(refs, list) or not refs:
        _error("Examiner report requires typed evidence references")
    for ref in refs:
        typed = validate_typed_evidence_ref(ref, expected_ticket=ticket["ticket_digest"], expected_state=ticket["model_state_digest"])
        if kind == "source" and typed["type"] != "approved_source":
            _error("Source report may only cite approved_source evidence")
        if kind == "source":
            source_path = str(typed.get("location", "")).split("#", 1)[0]
            approved_paths = {item["path"] for item in ticket["approved_sources"]}
            if source_path not in approved_paths:
                _error("Source report location is outside approved sources")
        if kind == "platform":
            if typed["type"] != "platform_read":
                _error("Platform report may only cite platform_read evidence")
            if typed.get("tool") not in ticket["allowed_read_tools"]:
                _error("Platform report cites a tool outside the ticket allowlist")
            if typed.get("tool") not in set(canonical_platform_allowlist()):
                _error("Platform report cites a non-read-only tool")
    validate_page_chain(refs)
    expected = report_digest(data)
    if data["report_digest"] != expected:
        _error("report_digest does not match canonical preimage")
    if data["answerability"] == "insufficient-evidence" and "因缺少相关证据无法回答" not in data["conclusion"]:
        _error("insufficient source evidence must preserve explicit unknown text")
    return _safe_copy(data)


def _assert_report_persistence_safe(value: Any) -> None:
    """Reject raw credential/error material before it reaches durable evidence."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("token", "password", "secret", "credential", "authorization")):
                _error("Examiner report contains a forbidden sensitive field")
            _assert_report_persistence_safe(child)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            _assert_report_persistence_safe(child)
        return
    if not isinstance(value, str):
        return
    if "\x00" in value or re.search(r"(?:Bearer\s+\S+|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|AKIA[0-9A-Z]{12,})", value):
        _error("Examiner report contains forbidden sensitive text")
    if value.startswith("/") or "/home/" in value or "/tmp/" in value:
        _error("Examiner report contains an unsanitized host path")


def report_digest(report: Mapping[str, Any]) -> str:
    return canonical_digest(report, self_field="report_digest")


def validate_verdict(verdict: Any, *, ticket: Mapping[str, Any], source_report: Mapping[str, Any] | None, platform_report: Mapping[str, Any] | None, infrastructure_failures: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    fields = {"schema_version", "task_id", "acceptance_round_id", "question_id", "slice_id", "slice_revision", "ticket_id", "ticket_digest", "quality_standard_digest", "quality_standard_artifact", "model_state", "model_state_digest", "source_bundle_digest", "modeling_receipts", "source_report_digest", "platform_report_digest", "failure_evidence_digests", "infrastructure_failure_digests", "failure_evidence_refs", "verdict", "failure_layer", "blocked_reason", "evidence_refs", "checks", "competency_question_results", "recommended_action", "summary", "verdict_digest"}
    data = _require_exact_keys(verdict, fields, "Acceptance verdict")
    if data["schema_version"] != "r2-3-005-acceptance-verdict/v1":
        _error("verdict schema_version is unsupported")
    for field in ("task_id", "acceptance_round_id", "question_id", "slice_id", "slice_revision", "ticket_id"):
        _safe_id(data[field], f"verdict.{field}")
    for field, expected in (("task_id", ticket["task_id"]), ("acceptance_round_id", ticket["acceptance_round_id"]), ("question_id", ticket["question_id"]), ("slice_id", ticket["slice_id"]), ("slice_revision", ticket["slice_revision"]), ("ticket_id", ticket["ticket_id"]), ("ticket_digest", ticket["ticket_digest"]), ("quality_standard_digest", ticket["quality_standard_digest"]), ("model_state_digest", ticket["model_state_digest"]), ("source_bundle_digest", ticket["source_bundle_digest"])):
        if data[field] != expected:
            _error(f"verdict {field} mismatch")
    validate_model_state(data["model_state"], allow_runner_bound=False)
    if data["model_state"]["state_digest"] != ticket["model_state_digest"]:
        _error("verdict model_state mismatch")
    artifact = _require_exact_keys(data["quality_standard_artifact"], {"path", "digest"}, "verdict standard artifact")
    if artifact != ticket["quality_standard_artifact"]:
        _error("verdict quality standard artifact mismatch")
    receipt_by_stage: dict[str, dict[str, Any]] = {}
    for receipt in data["modeling_receipts"]:
        valid = validate_modeling_receipt(receipt, run_id=ticket["producer_run_id"], project_id=ticket["model_state"]["project_id"], ontology_id=ticket["model_state"]["ontology_id"], slice_revision=ticket["slice_revision"], state_digest=ticket["model_state_digest"], ticket_digest=ticket["ticket_digest"])
        if valid["stage"] in receipt_by_stage:
            _error("verdict modeling receipts duplicate a stage")
        receipt_by_stage[valid["stage"]] = valid
    ticket_receipts = {item["stage"]: item for item in ticket["modeling_receipts"]}
    if receipt_by_stage != ticket_receipts:
        _error("verdict modeling receipts differ from ticket")
    for field in ("failure_evidence_digests", "infrastructure_failure_digests"):
        if not isinstance(data[field], list) or any(not _digest_matches(item) for item in data[field]):
            _error(f"verdict {field} is invalid")
    if data["verdict"] not in {"PASS", "FAIL", "BLOCKED"}:
        _error("verdict result is invalid")
    if data["failure_layer"] is not None and data["failure_layer"] not in ACCEPTANCE_FAILURE_LAYERS:
        _error("verdict failure_layer is invalid")
    if data["blocked_reason"] is not None and data["blocked_reason"] not in BLOCKED_REASONS:
        _error("verdict blocked_reason is invalid")
    refs = data["evidence_refs"]
    if not isinstance(refs, list):
        _error("verdict evidence_refs is invalid")
    for ref in refs:
        validate_typed_evidence_ref(ref, expected_ticket=ticket["ticket_digest"], expected_state=ticket["model_state_digest"])
    validate_page_chain(refs)
    checks = _require_exact_keys(data["checks"], CHECK_KEYS, "verdict checks")
    if any(checks[key] not in {"PASS", "FAIL", "BLOCKED"} for key in CHECK_KEYS):
        _error("verdict checks contain invalid status")
    cq_results = data["competency_question_results"]
    if not isinstance(cq_results, list) or len(cq_results) != 1:
        _error("verdict competency question results do not match ticket")
    cq_item = _require_exact_keys(cq_results[0], {"id", "status", "answer", "evidence_refs"}, "competency question result")
    if cq_item["id"] != ticket["question_id"] or cq_item["status"] not in {"PASS", "FAIL", "BLOCKED"}:
        _error("verdict competency question result does not match ticket")
    if not isinstance(cq_item["answer"], str) or not cq_item["answer"] or not isinstance(cq_item["evidence_refs"], list):
        _error("competency question result fields are invalid")
    for ref in cq_item["evidence_refs"]:
        if not isinstance(ref, Mapping):
            _error("competency question evidence ref is invalid")
        validate_typed_evidence_ref(ref, expected_ticket=ticket["ticket_digest"], expected_state=ticket["model_state_digest"])
    source_digest = source_report.get("report_digest") if source_report else None
    platform_digest = platform_report.get("report_digest") if platform_report else None
    if data["source_report_digest"] != source_digest or data["platform_report_digest"] != platform_digest:
        _error("verdict report digest binding mismatch")
    infra = list(infrastructure_failures)
    infra_by_digest = {
        item.get("failure_digest") if isinstance(item, Mapping) else getattr(item, "failure_digest", None): item
        for item in infra
    }
    if data["verdict"] == "PASS":
        if source_report is None or platform_report is None or data["failure_layer"] is not None or data["blocked_reason"] is not None or data["failure_evidence_digests"] or data["infrastructure_failure_digests"]:
            _error("PASS requires two reports and no failure fields")
        if any(value != "PASS" for value in checks.values()) or cq_item["status"] != "PASS":
            _error("PASS requires every check and competency question to pass")
    elif data["verdict"] == "FAIL":
        if data["failure_layer"] != "modeling-quality" or data["blocked_reason"] is not None or source_report is None or platform_report is None:
            _error("semantic FAIL must be modeling-quality with two reports")
        if not any(value != "PASS" for value in checks.values()) and cq_item["status"] == "PASS":
            _error("FAIL must identify a non-PASS check or question")
    else:
        if data["blocked_reason"] is None or data["failure_layer"] not in ACCEPTANCE_FAILURE_LAYERS:
            _error("BLOCKED requires a reason and failure layer")
        failure_refs = data["failure_evidence_refs"]
        if not isinstance(failure_refs, list):
            _error("verdict failure evidence refs are invalid")
        for ref in failure_refs:
            typed = validate_typed_evidence_ref(ref, expected_ticket=ticket["ticket_digest"], expected_state=ticket["model_state_digest"])
            if typed["type"] != "infrastructure_failure":
                _error("verdict failure evidence ref is not infrastructure_failure")
            failure_record = infra_by_digest.get(typed["failure_digest"])
            if failure_record is None:
                _error("verdict references an unknown infrastructure failure")
            expected_task = failure_record.get("task_id") if isinstance(failure_record, Mapping) else failure_record.task_id
            expected_round = failure_record.get("acceptance_round_id") if isinstance(failure_record, Mapping) else failure_record.acceptance_round_id
            expected_handle = failure_record.get("child_handle_digest") if isinstance(failure_record, Mapping) else failure_record.child_handle_digest
            expected_attempt = failure_record.get("attempt") if isinstance(failure_record, Mapping) else failure_record.attempt
            if typed["task_id"] != expected_task or typed["acceptance_round_id"] != expected_round or typed["child_handle_digest"] != expected_handle or typed["attempt"] != expected_attempt:
                _error("verdict infrastructure failure binding drifted")
        failure_ref_digests = [ref["failure_digest"] for ref in failure_refs]
        if set(failure_ref_digests) != set(data["failure_evidence_digests"]):
            _error("verdict failure evidence digest bindings drifted")
        if data["blocked_reason"] == "runtime-infrastructure":
            if not data["infrastructure_failure_digests"] or not failure_refs:
                _error("runtime BLOCKED requires infrastructure failure evidence")
            if set(data["infrastructure_failure_digests"]) != set(failure_ref_digests):
                _error("runtime BLOCKED infrastructure digest bindings drifted")
            if source_report is None and platform_report is None and not data["infrastructure_failure_digests"]:
                _error("runtime BLOCKED has no failure record")
        elif not refs:
            _error("non-runtime BLOCKED requires evidence refs")
        if data["recommended_action"] == "model-repair":
            _error("BLOCKED cannot recommend model repair")
    if data["recommended_action"] not in {"advance", "model-repair", "retry-after-recovery", "revise-ticket", "wait", "end"}:
        _error("verdict recommended_action is invalid")
    if not isinstance(data["summary"], str) or not data["summary"]:
        _error("verdict summary is empty")
    if data["verdict_digest"] != verdict_digest(data):
        _error("verdict_digest does not match canonical preimage")
    return _safe_copy(data)


@dataclass(frozen=True)
class ChildHandle:
    token: str
    digest: str
    task_id: str
    acceptance_round_id: str
    kind: str
    input_digest: str
    ticket_digest: str
    session_id: str
    attempt: int
    request_id: str

    @property
    def opaque(self) -> str:
        return self.token


@dataclass(frozen=True)
class CleanupReceipt:
    task_id: str
    acceptance_round_id: str
    child_handle_digest: str
    completion_kind: str
    completion_digest: str
    cleanup_status: str
    destroyed_resources: tuple[str, ...]
    receipt_digest: str
    infrastructure_failure_digest: str | None = None
    read_key_id: str | None = None
    private_input_path: str | None = None


@dataclass(frozen=True)
class InfrastructureFailure:
    task_id: str
    acceptance_round_id: str
    ticket_digest: str
    child_handle_digest: str
    child_input_digest: str
    attempt: int
    failure_category: str
    reason_code: str
    recorded_at: str
    failure_digest: str


@dataclass(frozen=True)
class VerdictReceipt:
    task_id: str
    acceptance_round_id: str
    request_id: str
    verdict_digest: str
    receipt_digest: str
    verdict: str


@dataclass(frozen=True)
class ChildResourceReceipt:
    """Runner-side description of one temporary child resource.

    The resource object itself is deliberately opaque to Acceptance.  It is supplied by a
    Runner/Codex adapter seam and may wrap a process, session, key, or a deterministic fake.
    ``private_root`` is retained only as a relative, sanitized cleanup reference.
    """

    child_handle_digest: str
    session_id: str
    kind: str
    private_root: str
    read_key_id: str | None
    config_digest: str | None = None
    proxy_socket_path: str | None = None
    status: str = "active"


class ChildReportSink:
    """Runner-owned child report sink; it is not Team Transport and accepts one envelope."""

    def __init__(self, carrier: "RunnerAcceptanceCarrier", *, round_id: str, handle: ChildHandle):
        self._carrier = carrier
        self._round_id = round_id
        self._handle = handle
        self._submitted = False

    def submit(self, report: Mapping[str, Any]) -> dict[str, Any]:
        if self._submitted:
            # The carrier still performs digest-checked replay handling, but a child-local
            # sink cannot be used as an unconstrained second submission path.
            raise AcceptanceContractError("child report sink accepts one submission")
        value = self._carrier.ingest_report(
            acceptance_id=self._carrier.acceptance_id,
            round_id=self._round_id,
            handle=self._handle,
            report=report,
        )
        self._submitted = True
        return value


class _NoopChildResource:
    """Default local resource seam used by deterministic tests and preflight paths."""

    def __init__(self, spec: Mapping[str, Any]):
        self.spec = _safe_copy(spec)
        self.stopped = False
        self.destroyed = False

    def stop(self) -> None:
        self.stopped = True

    def destroy(self) -> None:
        self.destroyed = True


def _write_exclusive_json(path: Path, value: Mapping[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        _error("immutable artifact path is a symlink")
    if path.exists():
        _error("immutable artifact already exists")
    payload = _canonical_json(value) + b"\n"
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-linking the fsynced private temp file gives an atomic no-overwrite
        # publication.  A pre-existing destination (including a symlink) fails
        # closed instead of being replaced.
        os.link(temporary, path)
        temporary.unlink(missing_ok=True)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        temporary.unlink(missing_ok=True)
        raise AcceptanceContractError("immutable artifact already exists") from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def _write_exclusive_token(path: Path, token: str) -> None:
    """Write an opaque capability token without putting it in a manifest."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.exists():
        _error("capability token already exists")
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(token.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise AcceptanceContractError("capability token already exists") from exc


def _write_exclusive_bytes(path: Path, payload: bytes, *, mode: int = 0o440) -> None:
    """Publish one exact source byte stream into a child-private tree."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.exists():
        _error("immutable source artifact already exists")
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise AcceptanceContractError("immutable source artifact already exists") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceContractError("immutable artifact is unreadable") from exc
    if not isinstance(value, dict):
        _error("immutable artifact is not an object")
    return value


class RunnerAcceptanceCarrier:
    """Task-local immutable carrier and narrow Acceptance child capability."""

    def __init__(
        self,
        root: Path,
        *,
        task_id: str,
        acceptance_id: str,
        descriptors: Mapping[str, Mapping[str, Any]] | None = None,
        child_factory: Callable[[Mapping[str, Any]], Any] | None = None,
        key_lifecycle: ReadOnlyKeyLifecycle | None = None,
        source_materials: Mapping[str, Path] | None = None,
        ticket_policy: Mapping[str, Any] | None = None,
        candidate_publisher: Callable[[str], Mapping[str, Any]] | None = None,
        candidate_receipt_builder: Callable[[str, str], Mapping[str, Any]] | None = None,
        candidate_conflict_builder: Callable[[str, str, str, str], Mapping[str, Any]] | None = None,
    ):
        self.root = root
        self.task_id = _safe_id(task_id, "task_id")
        self.acceptance_id = _safe_id(acceptance_id, "acceptance_id")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_metadata = os.lstat(self.root)
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
            or root_metadata.st_uid != os.getuid()
        ):
            _error("Acceptance carrier root is not private")
        self.acceptance_root = self.root / "acceptance"
        self.acceptance_root.mkdir(mode=0o700, exist_ok=True)
        self._tickets: dict[str, dict[str, Any]] = {}
        self._rounds: dict[str, dict[str, Any]] = {}
        self._handles: dict[str, ChildHandle] = {}
        self._resources: dict[str, tuple[ChildResourceReceipt, Any]] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        # A real Codex child can finish its first turn while the factory is still
        # returning the resource object.  Queue that one report until the opaque
        # handle's resource/provider is registered, then run the same validation
        # path exactly once.  No report is durable while it is queued.
        self._pending_reports: dict[str, list[dict[str, Any]]] = {}
        self._failures: dict[str, InfrastructureFailure] = {}
        self._cleanups: dict[str, CleanupReceipt] = {}
        self._verdicts: dict[str, VerdictReceipt] = {}
        self._request_receipts: dict[str, tuple[str, Any]] = {}
        self._child_factory = child_factory
        self.key_lifecycle = key_lifecycle or ReadOnlyKeyLifecycle()
        self._formal_platform_scope: Any | None = None
        self._formal_platform_repository_root: Path | None = None
        self._source_materials = {
            str(name): Path(path).resolve()
            for name, path in (source_materials or {}).items()
        }
        self._ticket_policy = _safe_copy(ticket_policy) if ticket_policy else None
        self._candidate_publisher = candidate_publisher
        self._candidate_receipt_builder = candidate_receipt_builder
        self._candidate_conflict_builder = candidate_conflict_builder
        # Prompt E state is Runner-private.  The nonce is surfaced to Protocol
        # as a non-secret binding in its task text, while exact delivery bytes
        # are recorded only as a digest by TeamRunner before Coordinator can
        # invoke the draft capability.
        self._stage_handoff_nonce = secrets.token_hex(32)
        self._stage_handoff_deliveries: dict[str, dict[str, Any]] = {}
        # Keep the parsed handoff in the Runner-owned carrier so a Coordinator
        # can bind a draft by opaque delivery identity without reconstructing
        # or re-sending business bytes.  The original text is represented only
        # by the immutable digest in ``_stage_handoff_deliveries``.
        self._stage_handoff_payloads: dict[str, dict[str, Any]] = {}
        # TeamRunner drains every Protocol -> Coordinator delivery.  Keep the
        # exact canonical bytes emitted by the Runner-private builder so only
        # that output can enter the handoff registry; ordinary replies (such as
        # frozen-question ID arrays) remain ordinary peer deliveries.
        self._stage_handoff_builder_outputs: dict[str, dict[str, str]] = {}
        self._typed_ticket_draft_revisions: dict[tuple[str, str], int] = {}
        self._typed_ticket_draft_requests: set[tuple[str, str, int]] = set()
        # These records are populated only by the host Runtime when a formal
        # Protocol MCP item actually completes.  Coordinator/Protocol have no
        # capability to add or alter them; the draft builder uses the registry
        # and the immutable files as the evidence owner of stage digests.
        self._accepted_candidate_identity: dict[str, Any] | None = None
        self._accepted_candidate: dict[str, Any] | None = None
        self._ordinary_retrieval_gate: ProtocolRetrievalGate | None = None
        self._ordinary_retrieval_receipt: dict[str, Any] | None = None
        self._platform_read_artifacts: dict[str, dict[str, Any]] = {}
        self._platform_artifact_sequence = 0
        self._ticket_drafts: dict[str, dict[str, Any]] = {}
        self._ticket_draft_bindings: dict[str, dict[str, Any]] = {}
        self._settlement_payload: dict[str, Any] | None = None
        self._cleanup_payload: dict[str, Any] | None = None
        # C-stage integrity state is deliberately kept in the Runner-owned carrier.
        # It is not model-visible and does not introduce a write gate: the carrier only
        # decides whether previously persisted acceptance evidence is still consumable.
        self._model_state_boundary: ModelStateBoundary | None = None
        self._model_state_reader: Callable[[], Mapping[str, Any]] | None = None
        self._settlement_state_reader: Callable[[], Mapping[str, Any]] | None = None
        self._state_invalidations: list[dict[str, Any]] = []
        self._state_revalidation_count = 0
        # Boundary receipts are bound to the state epoch and digest.  Keeping the
        # complete event rather than only the boundary name prevents an old epoch's
        # revalidation from satisfying a fresh CQ pair after state invalidation.
        self._state_revalidation_boundaries: list[dict[str, Any]] = []
        self._state_epoch = 0
        self._state_revision_required = False
        self._abort_reason: str | None = None
        # Capability tokens are generated per task and never written into model-visible
        # evidence.  The operation set is exposed separately for deterministic capability
        # checks and config/manifest staging.
        self._capability_tokens = {
            "coordinator": secrets.token_urlsafe(32),
            "protocol": secrets.token_urlsafe(32),
            "acceptance": secrets.token_urlsafe(32),
        }
        if candidate_publisher is not None:
            self._capability_tokens["modeling"] = secrets.token_urlsafe(32)
        self.capability_root = self.root / "capabilities"
        self.capability_root.mkdir(mode=0o700, exist_ok=True)
        capability_metadata = os.lstat(self.capability_root)
        if (
            stat.S_ISLNK(capability_metadata.st_mode)
            or not stat.S_ISDIR(capability_metadata.st_mode)
            or stat.S_IMODE(capability_metadata.st_mode) != 0o700
            or capability_metadata.st_uid != os.getuid()
        ):
            _error("Runner capability root is not private")
        # AF_UNIX paths have a small platform-dependent length limit.  Keep the
        # human-readable path in the run directory when possible and use a stable
        # opaque /tmp path only for unusually deep checkouts.
        socket_root = self.capability_root
        if any(len(str(socket_root / f"{role}.sock")) >= 100 for role in ROLE_OPERATIONS):
            socket_root = Path("/tmp") / f"mt-cap-{hashlib.sha256(str(self.root).encode()).hexdigest()[:24]}"
        self.capability_socket_root = socket_root
        self._capability_endpoints: dict[str, RunnerCapabilityEndpoint] = {}
        for role, token in self._capability_tokens.items():
            _write_exclusive_token(self.capability_token_path(role), token)
            operations = (
                ROLE_OPERATIONS[role]
                if role != "protocol"
                else (
                    PROTOCOL_OPERATIONS
                    if candidate_receipt_builder is not None and candidate_conflict_builder is not None
                    else PROTOCOL_STAGE_OPERATIONS
                )
            )
            if role == "coordinator" and ticket_policy is None:
                operations = COORDINATOR_OPERATIONS
            elif role == "coordinator":
                operations = COORDINATOR_FORMAL_OPERATIONS
            self._capability_endpoints[role] = RunnerCapabilityEndpoint(
                role=role,
                socket_path=self.capability_socket_path(role),
                token=token,
                dispatch=self._dispatch_capability,
                operations=operations,
            )
        self._active_acceptance = True
        self._round_sequence = 0
        self.descriptors = {
            "source": validate_child_descriptor(descriptors["source"] if descriptors else self.default_descriptor("source")),
            "platform": validate_child_descriptor(descriptors["platform"] if descriptors else self.default_descriptor("platform")),
        }

    @property
    def stage_handoff_nonce(self) -> str:
        """The current Runner-issued non-secret handoff nonce."""

        return self._stage_handoff_nonce

    def frozen_question_ids(self) -> tuple[str, ...]:
        """Return the exact requirement-owned competency-question IDs."""

        policy = self._ticket_policy
        questions = policy.get("competency_questions") if isinstance(policy, Mapping) else None
        if not isinstance(questions, list) or len(questions) != 2:
            _error("acceptance policy must freeze exactly two competency question IDs")
        ids: list[str] = []
        for question in questions:
            if not isinstance(question, Mapping) or not isinstance(question.get("id"), str) or not question["id"]:
                _error("acceptance policy competency question ID is invalid")
            ids.append(question["id"])
        if len(set(ids)) != 2:
            _error("acceptance policy competency question IDs are duplicated")
        return tuple(ids)

    def register_stage_handoff_delivery(
        self,
        *,
        delivery_id: str,
        text: str,
        sender_role: str,
        recipient_role: str,
    ) -> dict[str, str]:
        """Record the exact Protocol -> Coordinator delivery identity.

        The delivery digest, fixed role metadata, and the parsed handoff object
        are retained only in Runner memory.  Raw handoff text is not persisted
        or exposed as a Coordinator-visible carrier artifact.  Re-registering
        the same immutable delivery is idempotent; changing its bytes or role
        binding fails closed.
        """

        _safe_id(delivery_id, "stage handoff delivery_id")
        if not isinstance(text, str) or not text:
            _error("stage handoff delivery text is invalid")
        if sender_role != "protocol" or recipient_role != "coordinator":
            _error("stage handoff delivery role binding is invalid")
        digest = _sha256_bytes(text.encode("utf-8"))
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AcceptanceContractError("stage handoff delivery is not valid JSON") from exc
        if not isinstance(parsed, Mapping):
            _error("stage handoff delivery is not an object")
        canonical_digest = _sha256_bytes(_canonical_json(parsed))
        existing = self._stage_handoff_deliveries.get(delivery_id)
        record = {
            "delivery_id": delivery_id,
            "text_digest": digest,
            "canonical_digest": canonical_digest,
            "sender_role": sender_role,
            "recipient_role": recipient_role,
        }
        if existing is not None:
            if existing != record:
                _error("stage handoff delivery identity was mutated")
            if self._stage_handoff_payloads.get(delivery_id) != dict(parsed):
                _error("stage handoff delivery payload was mutated")
            return _safe_copy(record)
        self._stage_handoff_deliveries[delivery_id] = record
        self._stage_handoff_payloads[delivery_id] = _safe_copy(dict(parsed))
        return _safe_copy(record)

    def classify_stage_handoff_delivery(self, text: str) -> bool:
        """Return whether *text* has the builder's canonical handoff identity.

        JSON key order and insignificant whitespace may differ at Transport,
        but canonical semantic identity must match exactly.  A delivery
        carrying a known handoff identity but mutated fields fails closed;
        unrelated arrays, text, and objects return ``False`` and remain
        ordinary peer messages.
        """

        if not isinstance(text, str) or not text:
            _error("stage handoff delivery text is invalid")
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(parsed, Mapping):
            return False
        canonical_digest = _sha256_bytes(_canonical_json(parsed))
        if canonical_digest in self._stage_handoff_builder_outputs:
            return True
        if not self._stage_handoff_builder_outputs:
            return False
        # A formal handoff keeps its schema marker even when an Agent mutates
        # another field.  Treat that reserved shape as an attempted handoff,
        # while unrelated objects remain ordinary peer deliveries.
        if parsed.get("schema_version") == STAGE_HANDOFF_SCHEMA:
            _error("stage handoff builder output was mutated")
        known_ids = {
            value
            for output in self._stage_handoff_builder_outputs.values()
            for value in (
                output["handoff_id"],
                output["handoff_digest"],
                output["handoff_nonce"],
            )
        }
        if any(
            parsed.get(field) in known_ids
            for field in ("handoff_id", "handoff_digest", "handoff_nonce")
        ):
            _error("stage handoff builder output was mutated")
        return False

    def register_accepted_candidate(
        self,
        *,
        candidate_revision: Any,
        candidate_digest: str,
        candidate: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Bind the one formal candidate accepted by the Modeling/Protocol gate.

        The identity comes from :class:`FormalCandidateProgress` in TeamRunner,
        never from a Protocol handoff or Coordinator argument.  R2.3-005 uses a
        safe string revision because it is also the immutable ticket slice
        revision; integer/boolean revisions from archived fixtures cannot enter
        this formal binding.
        """

        _safe_id(candidate_revision, "accepted candidate_revision")
        _safe_digest(candidate_digest, "accepted candidate_digest")
        record = {
            "candidate_revision": candidate_revision,
            "candidate_digest": candidate_digest,
        }
        if self._accepted_candidate_identity is not None:
            if self._accepted_candidate_identity != record:
                _error("accepted candidate identity was mutated")
            if candidate is not None:
                detached = _safe_copy(dict(candidate))
                if self._accepted_candidate is not None and self._accepted_candidate != detached:
                    _error("accepted candidate semantic payload was mutated")
                if self._accepted_candidate is None:
                    self._accepted_candidate = detached
                    try:
                        gate = ProtocolRetrievalGate(
                            detached,
                            candidate_revision=candidate_revision,
                            candidate_digest=candidate_digest,
                        )
                    except ProtocolRetrievalGateError as exc:
                        _error(str(exc))
                    self._ordinary_retrieval_gate = gate if gate.enabled else None
            return _safe_copy(record)
        self._accepted_candidate_identity = record
        if candidate is not None:
            detached = _safe_copy(dict(candidate))
            try:
                gate = ProtocolRetrievalGate(
                    detached,
                    candidate_revision=candidate_revision,
                    candidate_digest=candidate_digest,
                )
            except ProtocolRetrievalGateError as exc:
                _error(str(exc))
            self._accepted_candidate = detached
            self._ordinary_retrieval_gate = gate if gate.enabled else None
        return _safe_copy(record)

    @property
    def ordinary_retrieval_receipt(self) -> dict[str, Any] | None:
        """Return the Runner-registered ordinary retrieval receipt, if complete."""

        return _safe_copy(self._ordinary_retrieval_receipt) if self._ordinary_retrieval_receipt else None

    def validate_ordinary_retrieval(self) -> dict[str, Any]:
        """Validate and register the candidate-bound receipt from host artifacts."""

        gate = self._ordinary_retrieval_gate
        if gate is None:
            _error("ordinary retrieval candidate plan is unavailable")
        try:
            state = self._observed_model_state(None)
            receipt = gate.build_receipt(runtime_root=self.root.parent, model_state=state)
        except ProtocolRetrievalGateError as exc:
            _error(str(exc))
        existing = self._ordinary_retrieval_receipt
        if existing is not None and existing != receipt:
            _error("ordinary retrieval receipt was mutated")
        self._ordinary_retrieval_receipt = _safe_copy(receipt)
        return _safe_copy(receipt)

    def _try_register_ordinary_retrieval(self) -> None:
        """Promote a complete gate result without failing the MCP event sink early."""

        if self._ordinary_retrieval_gate is None or self._ordinary_retrieval_receipt is not None:
            return
        try:
            self.validate_ordinary_retrieval()
        except AcceptanceContractError:
            # A partial page sequence is expected while Protocol is still
            # retrieving.  Handoff calls the public validator and fails closed
            # with the precise missing/invalid path reason.
            return

    def register_platform_tool_result(
        self,
        *,
        tool: str,
        arguments: Mapping[str, Any],
        result: Any,
    ) -> dict[str, str]:
        """Persist one host-observed Protocol platform MCP result.

        This method is called by the Runtime only after an actual completed
        ``ontology_platform`` MCP item.  It intentionally exposes no model
        capability and accepts no caller-supplied digest/path: both are
        derived from the observed request/result.  The immutable artifact is
        the exact canonical result envelope; its SHA is the response digest
        used by the structured handoff.
        """

        if not isinstance(tool, str) or not tool:
            _error("observed platform tool is invalid")
        if not isinstance(arguments, Mapping):
            _error("observed platform request arguments are invalid")
        # Keep the sink broad enough to retain deterministic write/read stage
        # results; the stage validator below still restricts which tool/mode
        # can satisfy each receipt.
        request_digest = _sha256_bytes(_canonical_json(dict(arguments)))
        response_bytes = _canonical_json(result)
        response_digest = _sha256_bytes(response_bytes)
        artifact_path = f"evidence/platform-responses/{request_digest}-{response_digest}.json"
        target = self.root.parent / artifact_path
        try:
            runtime_root = self.root.parent.resolve(strict=True)
            target_parent = target.parent.resolve(strict=False)
            target_parent.relative_to(runtime_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise AcceptanceContractError("observed platform artifact path escapes run root") from exc
        record = {
            "tool": tool,
            "request_digest": request_digest,
            "response_digest": response_digest,
            "artifact_path": artifact_path,
            "request_arguments": _safe_copy(dict(arguments)),
            "successful": bool(
                isinstance(result, Mapping)
                and result.get("isError") is not True
                and "error" not in result
                and (
                    not isinstance(result.get("structuredContent"), Mapping)
                    or result["structuredContent"].get("ok") is not False
                )
            ),
        }
        existing = self._platform_read_artifacts.get(artifact_path)
        if existing is not None:
            if any(existing.get(key) != record.get(key) for key in record):
                _error("observed platform artifact identity was mutated")
            try:
                if target.is_symlink() or not target.is_file() or target.read_bytes() != response_bytes:
                    _error("observed platform artifact bytes were mutated")
            except OSError as exc:
                raise AcceptanceContractError("observed platform artifact is unreadable") from exc
            return {
                key: record[key]
                for key in ("tool", "request_digest", "response_digest", "artifact_path")
            }
        record["observation_sequence"] = self._platform_artifact_sequence + 1
        if target.exists() or target.is_symlink():
            _error("observed platform artifact path is already occupied")
        _write_exclusive_bytes(target, response_bytes, mode=0o440)
        try:
            metadata = os.lstat(target)
            if stat.S_IMODE(metadata.st_mode) != 0o440 or not stat.S_ISREG(metadata.st_mode) or target.is_symlink():
                _error("observed platform artifact metadata is invalid")
        except OSError as exc:
            raise AcceptanceContractError("observed platform artifact is unavailable") from exc
        self._platform_read_artifacts[artifact_path] = record
        self._platform_artifact_sequence += 1
        if self._ordinary_retrieval_gate is not None:
            try:
                self._ordinary_retrieval_gate.observe(record, target)
            except ProtocolRetrievalGateError as exc:
                _error(str(exc))
            self._try_register_ordinary_retrieval()
        return {
            key: record[key]
            for key in ("tool", "request_digest", "response_digest", "artifact_path")
        }

    def bind_model_state(
        self,
        model_state: Mapping[str, Any],
        *,
        state_reader: Callable[[], Mapping[str, Any]] | None = None,
        settlement_reader: Callable[[], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Bind the complete Producer snapshot used by every ticket and verdict.

        The snapshot is intentionally supplied as a value, not a path.  A caller may
        provide read callbacks for the three passive revalidation boundaries; those
        callbacks must return the same complete state envelope and are never allowed to
        mutate platform state.
        """

        state = validate_model_state(model_state, allow_runner_bound=False)
        if self._model_state_boundary is not None and not self._state_revision_required:
            if self._model_state_boundary.digest != state["state_digest"]:
                _error("model-state binding cannot drift without a ticket revision")
        if self._model_state_boundary is None or self._state_revision_required:
            self._state_epoch = max(1, self._state_epoch + 1)
        self._model_state_boundary = ModelStateBoundary(state)
        self._model_state_reader = state_reader
        self._settlement_state_reader = settlement_reader or state_reader
        self._state_revision_required = False
        return _safe_copy(state)

    @property
    def model_state_snapshot(self) -> dict[str, Any] | None:
        return (
            _safe_copy(self._model_state_boundary.current)
            if self._model_state_boundary is not None
            else None
        )

    @property
    def state_invalidations(self) -> tuple[dict[str, Any], ...]:
        return tuple(_safe_copy(self._state_invalidations))

    @property
    def is_settled(self) -> bool:
        return bool(self._settlement_payload and self._settlement_payload.get("status") == "settled")

    def _observed_model_state(self, observed: Mapping[str, Any] | None) -> dict[str, Any]:
        value: Mapping[str, Any] | None = observed
        if value is None and self._model_state_reader is not None:
            value = self._model_state_reader()
        if value is None:
            if self._formal_platform_scope is not None:
                _error("formal model-state reader is unavailable")
            if self._model_state_boundary is None:
                _error("model-state snapshot is not bound")
            return _safe_copy(self._model_state_boundary.current)
        if not isinstance(value, Mapping):
            _error("model-state revalidation returned an invalid envelope")
        if "model_state" in value and isinstance(value.get("model_state"), Mapping):
            value = value["model_state"]
        return validate_model_state(value, allow_runner_bound=False)

    def _destroy_invalidated_child(self, found: ChildHandle, *, state_digest: str) -> None:
        """Reclaim an active pair when a passive state boundary drifts.

        This path is separate from normal ``recycle_child`` because no terminal or
        infrastructure report is authoritative after state invalidation.  It still
        records the same durable cleanup fields and removes every host-owned resource.
        """

        resource_entry = self._resources.pop(found.token, None)
        resource_receipt, resource = resource_entry if resource_entry is not None else (None, None)
        if resource is not None:
            for method in ("stop", "destroy"):
                action = getattr(resource, method, None)
                if callable(action):
                    try:
                        action()
                    except Exception as exc:
                        raise AcceptanceContractError("state-invalidation child cleanup failed") from exc
        if resource_receipt is not None and resource_receipt.read_key_id is not None:
            self.key_lifecycle.revoke(resource_receipt.read_key_id)
        private_root = self.root / resource_receipt.private_root if resource_receipt is not None else None
        if private_root is not None:
            if private_root.is_symlink() or (private_root.exists() and not private_root.is_dir()):
                _error("state-invalidation child private tree is invalid")
            shutil.rmtree(private_root, ignore_errors=True)
        completion_digest = state_digest
        payload = {
            "task_id": self.task_id,
            "acceptance_round_id": found.acceptance_round_id,
            "child_handle_digest": found.digest,
            "completion_kind": "state-invalidated",
            "completion_digest": completion_digest,
            "cleanup_status": "destroyed",
            "destroyed_resources": [
                "child-session",
                "child-input",
                "child-credentials",
                "child-report-sink",
                *( ["platform-read-proxy"] if resource_receipt is not None and resource_receipt.proxy_socket_path else [] ),
            ],
            "infrastructure_failure_digest": None,
            "read_key_id": resource_receipt.read_key_id if resource_receipt is not None else None,
            "private_input_path": "child-input" if resource_receipt is not None else None,
        }
        receipt = CleanupReceipt(
            **payload,
            receipt_digest=_sha256_bytes(_canonical_json(payload)),
        )
        self._cleanups[found.token] = receipt
        round_data = self._rounds[found.acceptance_round_id]
        round_data["cleanup"].add(found.kind)
        round_data["children"].pop(found.kind, None)
        self._handles.pop(found.token, None)
        self._append(
            found.acceptance_round_id,
            "child-cleanup.jsonl",
            {**payload, "receipt_digest": receipt.receipt_digest},
        )

    def revalidate_model_state(
        self,
        *,
        boundary: str,
        observed: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Passively compare a complete state snapshot and invalidate stale PASS evidence."""

        if self._model_state_boundary is None:
            _error("model-state snapshot is not bound")
        if not isinstance(boundary, str) or not boundary:
            _error("state revalidation boundary is invalid")
        state = self._observed_model_state(observed)
        bound_digest = self._model_state_boundary.digest
        is_valid = self._model_state_boundary.revalidate(state, boundary=boundary)
        boundary_event = {
            "boundary": boundary,
            "epoch": self._state_epoch,
            "bound_state_digest": bound_digest,
            "observed_state_digest": state["state_digest"],
            "status": "valid" if is_valid else "state_invalidated",
        }
        self._state_revalidation_boundaries.append(boundary_event)
        if is_valid:
            self._state_revalidation_count += 1
            result = {
                "status": "valid",
                "boundary": boundary,
                "epoch": self._state_epoch,
                "model_state_digest": self._model_state_boundary.digest,
            }
            self._append_root(
                f"state-revalidation-{self._state_revalidation_count}.json",
                result,
            )
            return result
        old_digest = self._model_state_boundary.digest
        # ``ModelStateBoundary`` retains the original snapshot so every stale ticket,
        # report, and PASS remains auditable.  The new digest is carried only by the
        # returned event; Coordinator must publish a new ticket revision before retry.
        invalidation = {
            "status": "state_invalidated",
            "boundary": boundary,
            "epoch": self._state_epoch,
            "bound_state_digest": old_digest,
            "old_model_state_digest": old_digest,
            "new_model_state_digest": state["state_digest"],
            "rerun_competency_questions": True,
            "new_ticket_revision_required": True,
        }
        self._state_invalidations.append(invalidation)
        self._state_revision_required = True
        for round_id, round_data in self._rounds.items():
            verdict = round_data.get("verdict")
            if isinstance(verdict, Mapping) and verdict.get("verdict") == "PASS":
                invalidated = _safe_copy(dict(verdict))
                invalidated["usable"] = False
                invalidated["invalidated_reason"] = "state_invalidated"
                round_data["verdict"] = invalidated
                round_data["verdict_usable"] = False
                round_data["status"] = "state_invalidated"
            for child in list(round_data.get("children", {}).values()):
                self._destroy_invalidated_child(child, state_digest=state["state_digest"])
            if round_data.get("children"):
                round_data["status"] = "state_invalidated"
            elif round_data.get("status") != "state_invalidated":
                round_data["status"] = "state_invalidated"
        self._append_root(
            f"state-invalidated-{len(self._state_invalidations)}.json",
            invalidation,
        )
        return _safe_copy(invalidation)

    def issue_ticket_revision(
        self,
        ticket: Mapping[str, Any],
        *,
        coordinator_id: str = "coordinator",
        owner_revision: str,
        model_state: Mapping[str, Any],
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Publish the new state-bound ticket required after invalidation.

        The caller supplies fresh current-run receipts in ``ticket``; this helper never
        fabricates or re-labels a receipt.  A stale receipt therefore fails in
        ``validate_ticket`` when its run/state/evidence/page facts do not match the new
        snapshot.
        """

        if not self._state_revision_required:
            _error("ticket revision is not required")
        state = validate_model_state(model_state, allow_runner_bound=False)
        candidate = _safe_copy(dict(ticket))
        candidate["model_state"] = state
        candidate["model_state_digest"] = state["state_digest"]
        candidate["ticket_revision"] = int(candidate.get("ticket_revision", 0)) + 1
        # Only the nested self-reference is mechanical carrier metadata.  All stage,
        # run/state, request/response, and page facts remain caller-owned and are
        # validated below without relabelling.
        for receipt in candidate.get("modeling_receipts", []):
            evidence = receipt.get("evidence_ref") if isinstance(receipt, Mapping) else None
            if isinstance(evidence, Mapping):
                evidence["ticket_digest"] = None
        candidate["ticket_digest"] = ticket_digest(candidate)
        for receipt in candidate.get("modeling_receipts", []):
            evidence = receipt.get("evidence_ref") if isinstance(receipt, Mapping) else None
            if isinstance(evidence, Mapping):
                evidence["ticket_digest"] = candidate["ticket_digest"]
        validate_ticket(candidate, expected_owner_revision=owner_revision)
        # ``publish_ticket`` installs the new boundary after validating the complete
        # candidate.  Clearing the old one here makes the transition explicit while
        # ``_state_revision_required`` still rejects an accidental old-state ticket.
        self._model_state_boundary = None
        result = self.publish_ticket(
            candidate,
            coordinator_id=coordinator_id,
            owner_revision=owner_revision,
            capability=capability,
        )
        self._state_revision_required = False
        return result

    def bind_platform_scope(self, scope: Any, *, repository_root: Path) -> None:
        """Switch the formal carrier from its offline test double to Platform API.

        ``TeamRunner`` calls this only after ``PlatformScope.prepare`` has created and
        authenticated the owned Project/Ontology.  Keeping the binding as a narrow
        carrier operation avoids modifying the high-risk ``PlatformScope.cleanup``
        workflow while ensuring every formal child uses a real project read key.
        """
        if self._formal_platform_scope is not None:
            if self._formal_platform_scope is not scope:
                _error("formal PlatformScope binding cannot be replaced")
            return
        self._formal_platform_scope = scope
        self._formal_platform_repository_root = repository_root.resolve()
        self.key_lifecycle = PlatformApiReadKeyLifecycle(
            scope,
            repository_root=self._formal_platform_repository_root,
        )

        def read_live_model_state() -> Mapping[str, Any]:
            """Read the current authenticated Producer context without mutation."""

            context_reader = getattr(scope, "_modeling_context", None)
            workspace_reader = getattr(scope, "_workspace_context", None)
            if not callable(context_reader) or not callable(workspace_reader):
                raise AcceptanceContractError("formal platform scope has no read-only state reader")
            context = context_reader()
            workspace_context = workspace_reader()
            if not isinstance(context, Mapping) or not isinstance(workspace_context, Mapping):
                raise AcceptanceContractError("formal platform state context is invalid")
            project = context.get("project")
            ontology = context.get("ontology")
            workspace = context.get("workspace")
            project_id = project.get("id") if isinstance(project, Mapping) else None
            ontology_id = ontology.get("id") if isinstance(ontology, Mapping) else None
            workspace_version = workspace.get("workspace_version") if isinstance(workspace, Mapping) else None
            graph_set_id = workspace_context.get("default_graph_set_id")
            source_signature = workspace_context.get("source_signature")
            if not all(
                isinstance(value, str) and value
                for value in (project_id, ontology_id, workspace_version, graph_set_id, source_signature)
            ):
                raise AcceptanceContractError("formal platform state is incomplete")
            build_session_id = getattr(scope, "completed_session_id", None)
            if not isinstance(build_session_id, str) or not build_session_id:
                batches = context.get("recent_batches")
                if isinstance(batches, list):
                    for batch in batches:
                        if isinstance(batch, Mapping) and isinstance(batch.get("build_session_id"), str) and batch["build_session_id"]:
                            build_session_id = batch["build_session_id"]
                            break
            if not isinstance(build_session_id, str) or not build_session_id:
                raise AcceptanceContractError("formal platform state has no Producer Build Session")
            state = {
                "project_id": project_id,
                "ontology_id": ontology_id,
                "workspace_version": workspace_version,
                "source_signature": source_signature,
                "build_session_id": build_session_id,
                "graph_set_id": graph_set_id,
            }
            state["state_digest"] = model_state_digest(state)
            return state

        # Formal settlement must always read the authenticated platform context;
        # it may never fall back to the ticket snapshot as a self-comparison.
        self._model_state_reader = read_live_model_state
        self._settlement_state_reader = read_live_model_state

    @staticmethod
    def default_descriptor(kind: str) -> dict[str, Any]:
        if kind not in EXAMINER_KINDS:
            _error("unknown Examiner kind")
        package_kind = f"{kind}_examiner"
        return {
            "kind": package_kind,
            "package_digest": _sha256_bytes(package_kind.encode()),
            "platform_mode": "read" if kind == "platform" else "none",
            "can_team_transport": False,
            "can_spawn": False,
            "can_write": False,
            "max_children": 0,
        }

    def _check_acceptance(self, acceptance_id: str) -> None:
        if not self._active_acceptance or acceptance_id != self.acceptance_id:
            _error("only the live Acceptance runtime may invoke the child capability")

    def _check_capability(self, role: str, actor_id: str, capability: str | None = None) -> None:
        expected_id = {
            "coordinator": "coordinator",
            "modeling": "modeling",
            "protocol": "protocol",
            "acceptance": self.acceptance_id,
        }.get(role)
        if expected_id is None:
            _error("unknown Runner capability role")
        if actor_id != expected_id:
            _error(f"only {role.title()} may invoke this Runner capability")
        if capability is not None and capability != self._capability_tokens[role]:
            _error(f"{role.title()} Runner capability token is invalid")
        if role == "acceptance":
            self._check_acceptance(actor_id)

    @property
    def is_live(self) -> bool:
        return self._active_acceptance

    @property
    def capability_descriptors(self) -> dict[str, dict[str, Any]]:
        """Return non-secret capability metadata for private config assertions."""
        descriptors = {
            "coordinator": {
                "token_digest": token_digest(self._capability_tokens["coordinator"]),
                "operations": list(self._capability_endpoints["coordinator"].operations),
                "socket_mode": "0600",
                "token_file_mode": "0400",
            },
            "protocol": {
                "token_digest": token_digest(self._capability_tokens["protocol"]),
                "operations": list(self._capability_endpoints["protocol"].operations),
                "socket_mode": "0600",
                "token_file_mode": "0400",
            },
            "acceptance": {
                "token_digest": token_digest(self._capability_tokens["acceptance"]),
                "operations": list(ACCEPTANCE_OPERATIONS),
                "socket_mode": "0600",
                "token_file_mode": "0400",
            },
        }
        if "modeling" in self._capability_tokens:
            descriptors["modeling"] = {
                "token_digest": token_digest(self._capability_tokens["modeling"]),
                "operations": list(MODELING_OPERATIONS),
                "socket_mode": "0600",
                "token_file_mode": "0400",
            }
        return descriptors

    def capability_socket_path(self, role: str) -> Path:
        if role not in ROLE_OPERATIONS:
            _error("unknown Runner capability role")
        return self.capability_socket_root / f"{role}.sock"

    def capability_token_path(self, role: str) -> Path:
        if role not in ROLE_OPERATIONS:
            _error("unknown Runner capability role")
        return self.capability_root / f"{role}.token"

    def capability_endpoint(self, role: str) -> RunnerCapabilityEndpoint:
        try:
            return self._capability_endpoints[role]
        except KeyError as exc:
            raise AcceptanceContractError("unknown Runner capability role") from exc

    def start_capability_endpoints(self) -> None:
        """Start every configured private MCP capability before Agent processes."""

        started: list[RunnerCapabilityEndpoint] = []
        try:
            for endpoint in self._capability_endpoints.values():
                endpoint.start()
                started.append(endpoint)
        except Exception:
            for endpoint in reversed(started):
                endpoint.stop()
            raise

    def stop_capability_endpoints(self) -> None:
        for endpoint in self._capability_endpoints.values():
            endpoint.stop()
        if self.capability_socket_root != self.capability_root:
            try:
                self.capability_socket_root.rmdir()
            except OSError:
                pass

    def _carrier_run_id(self) -> str | None:
        """Resolve the formal run ID from the Runner-owned carrier path."""

        parts = self.root.parts
        try:
            index = parts.index("modeling-runs")
        except ValueError:
            return None
        if index + 1 >= len(parts):
            return None
        candidate = parts[index + 1]
        return candidate if isinstance(candidate, str) and candidate else None

    def _validate_observed_stage_evidence(
        self,
        receipt: Mapping[str, Any],
        *,
        state_digest: str,
    ) -> None:
        """Bind one receipt to an actual Runtime-observed MCP artifact."""

        live_state = self._observed_model_state(None)
        if live_state["state_digest"] != state_digest:
            _error("stage receipt state digest is not the live Runner state")
        stage = receipt.get("stage")
        evidence = receipt.get("evidence_ref")
        if stage not in STAGE_TOOL_BINDINGS or not isinstance(evidence, Mapping):
            _error("stage receipt evidence binding is invalid")
        if evidence.get("type") != "platform_read":
            _error("stage receipt evidence must be platform_read")
        if evidence.get("model_state_digest") != state_digest:
            _error("stage receipt evidence model state drifts")
        tool = evidence.get("tool")
        request_digest = evidence.get("request_digest")
        response_digest = evidence.get("response_digest")
        artifact_path = evidence.get("artifact_path")
        _safe_digest(request_digest, "stage receipt request_digest")
        _safe_digest(response_digest, "stage receipt response_digest")
        artifact_path = _safe_relative_path(artifact_path, "stage receipt artifact_path")
        expected_path = f"evidence/platform-responses/{request_digest}-{response_digest}.json"
        if artifact_path != expected_path:
            _error("stage receipt artifact_path is not Runner-owned")
        observed = self._platform_read_artifacts.get(artifact_path)
        if observed is None:
            _error("stage receipt artifact was not observed by Runner")
        if observed["tool"] != tool or observed["request_digest"] != request_digest or observed["response_digest"] != response_digest:
            _error("stage receipt artifact digest binding drifts")
        if not observed.get("successful"):
            _error("stage receipt artifact result was unsuccessful")
        allowed_tools, required_mode = STAGE_TOOL_BINDINGS[stage]
        if tool not in allowed_tools:
            _error("stage receipt tool does not match its stage")
        arguments = observed.get("request_arguments")
        if not isinstance(arguments, Mapping):
            _error("stage receipt observed request arguments are unavailable")
        if required_mode is not None and arguments.get("mode") != required_mode:
            _error("stage receipt request mode does not match its stage")
        if required_mode is None and stage in {"readback", "validation", "reasoning"} and "mode" in arguments:
            _error("stage receipt read request carries an unexpected mode")
        target = self.root.parent / artifact_path
        try:
            metadata = os.lstat(target)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                _error("stage receipt artifact is not a regular file")
            if _sha256_bytes(target.read_bytes()) != response_digest:
                _error("stage receipt artifact bytes do not match response_digest")
            result = json.loads(target.read_text(encoding="utf-8"))
        except OSError as exc:
            raise AcceptanceContractError("stage receipt artifact is unreadable") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceContractError("stage receipt artifact is not canonical JSON") from exc
        if not isinstance(result, Mapping):
            _error("stage receipt artifact result is not an object")
        structured = result.get("structuredContent")
        data = structured.get("data") if isinstance(structured, Mapping) else result
        if isinstance(structured, Mapping) and structured.get("ok") is not True:
            _error("stage receipt MCP result did not report success")
        if not isinstance(data, Mapping):
            _error("stage receipt MCP result data is unavailable")
        if stage in {"dry-run", "apply"}:
            if (
                data.get("mode") != required_mode
                or data.get("attempt_status") != ("validated" if stage == "dry-run" else "applied")
            ):
                _error("stage receipt result status does not match its stage")
            if stage == "apply":
                workspace = data.get("workspace")
                if (
                    not isinstance(workspace, Mapping)
                    or workspace.get("after_version") != live_state["workspace_version"]
                ):
                    _error("stage receipt apply workspace version is stale")
                target_snapshot = data.get("target")
                if isinstance(target_snapshot, Mapping) and "source_signature_after" in target_snapshot:
                    if target_snapshot.get("source_signature_after") != live_state["source_signature"]:
                        _error("stage receipt apply source signature is stale")
        elif stage == "readback":
            ontology = data.get("ontology")
            workspace = data.get("workspace")
            if (
                not isinstance(ontology, Mapping)
                or ontology.get("id") != live_state["ontology_id"]
                or not isinstance(workspace, Mapping)
                or workspace.get("workspace_version") != live_state["workspace_version"]
            ):
                _error("stage receipt readback ontology binding is invalid")
        elif stage in {"validation", "reasoning"}:
            if data.get("status") != "succeeded" or data.get("graph_set_id") != live_state["graph_set_id"]:
                _error("stage receipt result status or graph scope is invalid")
        if stage in {"dry-run", "apply"}:
            if (
                arguments.get("ontology_id") != live_state["ontology_id"]
                or arguments.get("session_id") != live_state["build_session_id"]
            ):
                _error("stage receipt submit scope is invalid")
        elif stage == "readback":
            if arguments.get("ontology_id") != live_state["ontology_id"]:
                _error("stage receipt readback request scope is invalid")
        elif stage in {"validation", "reasoning"}:
            if arguments.get("graph_set_id") != live_state["graph_set_id"]:
                _error("stage receipt request graph scope is invalid")

    def coordinator_build_acceptance_ticket_draft_from_delivery(
        self,
        *,
        handoff_delivery_id: str,
        question_id: str,
        ticket_revision: int,
        coordinator_id: str = "coordinator",
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Build a formal draft from one Runner-registered handoff delivery.

        The Coordinator receives only the opaque delivery identity and frozen
        question/revision bindings.  The parsed handoff and its digest remain
        in the Runner-owned carrier and are passed to the existing canonical
        builder unchanged.  A question may be drafted again only with a fresh
        positive revision; the two frozen questions therefore both accept
        revision one without sharing a global duplicate counter.
        """

        self._check_capability("coordinator", coordinator_id, capability)
        if self._ticket_policy is None:
            _error("delivery-bound acceptance ticket capability is unavailable")
        _safe_id(handoff_delivery_id, "stage handoff delivery_id")
        if not isinstance(question_id, str) or not question_id:
            _error("ticket draft question_id is invalid")
        _safe_id(question_id, "ticket draft question_id")
        if not isinstance(ticket_revision, int) or isinstance(ticket_revision, bool) or ticket_revision <= 0:
            _error("ticket draft revision is invalid")

        delivery = self._stage_handoff_deliveries.get(handoff_delivery_id)
        handoff = self._stage_handoff_payloads.get(handoff_delivery_id)
        if delivery is None or handoff is None:
            _error("stage handoff delivery is not recorded by Runner")
        if delivery["sender_role"] != "protocol" or delivery["recipient_role"] != "coordinator":
            _error("stage handoff delivery role binding is invalid")

        request_key = (handoff_delivery_id, question_id, ticket_revision)
        already_bound = any(
            binding.get("handoff_delivery_id") == handoff_delivery_id
            and binding.get("question_id") == question_id
            and binding.get("ticket_revision") == ticket_revision
            for binding in self._ticket_draft_bindings.values()
            if isinstance(binding, Mapping)
        )
        if request_key in self._typed_ticket_draft_requests or already_bound:
            _error("delivery-bound ticket draft request was already built")
        previous_revisions = [
            int(binding["ticket_revision"])
            for binding in self._ticket_draft_bindings.values()
            if isinstance(binding, Mapping)
            and binding.get("handoff_delivery_id") == handoff_delivery_id
            and binding.get("question_id") == question_id
            and isinstance(binding.get("ticket_revision"), int)
        ]
        previous_revision = max(
            [
                *previous_revisions,
                self._typed_ticket_draft_revisions.get((handoff_delivery_id, question_id), 0),
            ]
        )
        if previous_revision and ticket_revision <= previous_revision:
            _error("delivery-bound ticket draft revision is stale")

        handoff_digest = handoff.get("handoff_digest")
        if not isinstance(handoff_digest, str):
            _error("stage handoff digest is unavailable")
        draft = self.coordinator_build_acceptance_ticket_draft(
            handoff,
            handoff_delivery_id=handoff_delivery_id,
            handoff_digest=handoff_digest,
            question_id=question_id,
            ticket_revision=ticket_revision,
            coordinator_id=coordinator_id,
            capability=capability,
        )
        self._typed_ticket_draft_requests.add(request_key)
        self._typed_ticket_draft_revisions[(handoff_delivery_id, question_id)] = ticket_revision
        return draft

    def coordinator_build_acceptance_ticket_draft(
        self,
        handoff: Mapping[str, Any],
        *,
        handoff_delivery_id: str,
        handoff_digest: str,
        question_id: str,
        ticket_revision: int,
        coordinator_id: str = "coordinator",
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Build and retain one canonical ticket draft from a live handoff.

        This is the only path that can create a formal ticket candidate.  The
        Coordinator supplies an unchanged handoff and the exact Team Transport
        delivery ID; all source bytes, policy fields, allowlist entries, and
        authenticated model-state bindings come from this Runner carrier.
        """

        self._check_capability("coordinator", coordinator_id, capability)
        if not self._ticket_policy:
            _error("acceptance ticket draft capability is unavailable")
        _safe_id(handoff_delivery_id, "stage handoff delivery_id")
        _safe_digest(handoff_digest, "stage handoff digest argument")
        delivery = self._stage_handoff_deliveries.get(handoff_delivery_id)
        if delivery is None:
            _error("stage handoff delivery is not recorded by Runner")
        if delivery["sender_role"] != "protocol" or delivery["recipient_role"] != "coordinator":
            _error("stage handoff delivery role binding is invalid")
        if not isinstance(handoff, Mapping):
            _error("stage handoff payload is invalid")
        # The MCP capability receives a parsed JSON object. Compare its
        # canonical semantic identity with the recorded delivery identity so
        # harmless whitespace/key-order differences survive, while any field
        # mutation still fails before ticket construction.
        if _sha256_bytes(_canonical_json(handoff)) != delivery["canonical_digest"]:
            _error("stage handoff payload is not the unchanged delivered object")
        normalized = validate_stage_handoff(
            handoff,
            expected_task_id=self.task_id,
            expected_run_id=self._carrier_run_id(),
            expected_nonce=self._stage_handoff_nonce,
            expected_delivery_digest=delivery["canonical_digest"],
        )
        if normalized["handoff_digest"] != handoff_digest:
            _error("stage handoff digest argument does not match payload")
        accepted_candidate = self._accepted_candidate_identity
        if accepted_candidate is None:
            _error("formal accepted candidate identity is unavailable")
        if (
            normalized["slice_revision"] != accepted_candidate["candidate_revision"]
            or normalized["candidate_digest"] != accepted_candidate["candidate_digest"]
        ):
            _error("stage handoff candidate binding does not match accepted candidate")
        for receipt in normalized["modeling_receipts"]:
            self._validate_observed_stage_evidence(
                receipt,
                state_digest=normalized["model_state_digest"],
            )
        live_state = self._observed_model_state(None)
        if live_state != normalized["model_state"]:
            _error("stage handoff model state does not match authenticated live state")

        if not isinstance(question_id, str) or not question_id:
            _error("ticket draft question_id is invalid")
        if not isinstance(ticket_revision, int) or isinstance(ticket_revision, bool) or ticket_revision <= 0:
            _error("ticket draft revision is invalid")
        policy = self._ticket_policy
        expected_questions = policy.get("competency_questions")
        if not isinstance(expected_questions, list) or not expected_questions:
            _error("acceptance standard has no competency questions")
        question_map = {
            item["id"]: item["question"]
            for item in expected_questions
            if isinstance(item, Mapping)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("question"), str)
        }
        if question_id not in question_map:
            _error("ticket draft question is not in the acceptance standard")
        _safe_id(question_id, "ticket draft question_id")

        source_paths_by_question = policy.get("approved_source_paths_by_question")
        if not isinstance(source_paths_by_question, Mapping):
            _error("acceptance standard source paths are unavailable")
        raw_paths = source_paths_by_question.get(question_id)
        if not isinstance(raw_paths, list) or not raw_paths:
            _error("ticket draft approved sources are unavailable")
        approved_sources: list[dict[str, str]] = []
        for raw_path in sorted(raw_paths):
            path = _safe_relative_path(raw_path, "ticket draft approved source path")
            source = self._source_materials.get(path)
            if source is None:
                _error("ticket draft approved source is not staged for Runner")
            try:
                digest = _sha256_bytes(source.read_bytes())
            except OSError as exc:
                raise AcceptanceContractError("ticket draft approved source is unreadable") from exc
            approved_sources.append({"path": path, "sha256": digest})
        source_bundle_digest = _sha256_bytes(_canonical_json(approved_sources))

        run_id = normalized["producer_run_id"]
        ticket_id = f"acceptance-ticket-{run_id}-{question_id}-{ticket_revision}"
        round_id = f"acceptance-round-{run_id}-{question_id}-{ticket_revision}"
        _safe_id(ticket_id, "ticket draft ticket_id")
        _safe_id(round_id, "ticket draft acceptance_round_id")
        state = _safe_copy(live_state)
        receipts = _safe_copy(normalized["modeling_receipts"])
        # Receipt evidence is temporarily handoff-bound.  ``ticket_digest`` is
        # excluded from all canonical receipt/ticket preimages, so this is a
        # mechanical rebinding after validation, never a receipt rewrite.
        for receipt in receipts:
            evidence = receipt["evidence_ref"]
            evidence["ticket_digest"] = None
        ticket: dict[str, Any] = {
            "schema_version": "r2-3-005-slice-acceptance-ticket/v1",
            "ticket_id": ticket_id,
            "acceptance_round_id": round_id,
            "task_id": self.task_id,
            "producer_run_id": run_id,
            "slice_id": normalized["slice_id"],
            "slice_revision": normalized["slice_revision"],
            "question_id": question_id,
            "question": question_map[question_id],
            "approved_sources": approved_sources,
            "source_bundle_digest": source_bundle_digest,
            "platform_read_scope": {
                "project_id": state["project_id"],
                "ontology_id": state["ontology_id"],
                "graph_set_id": state["graph_set_id"],
            },
            "model_state": state,
            "model_state_digest": state["state_digest"],
            "competency_questions": _safe_copy(expected_questions),
            "allowed_read_tools": list(canonical_platform_allowlist()),
            "modeling_receipts": receipts,
            "timeout_seconds": 600,
            "quality_standard_ref": policy["quality_standard_ref"],
            "quality_standard_digest": policy["quality_standard_digest"],
            "quality_standard_artifact": _safe_copy(policy["quality_standard_artifact"]),
            "unknown_policy": policy["unknown_policy"],
            "ticket_revision": ticket_revision,
            "ticket_digest": None,
        }
        draft_digest = ticket_digest(ticket)
        ticket["ticket_digest"] = draft_digest
        for receipt in ticket["modeling_receipts"]:
            receipt["evidence_ref"]["ticket_digest"] = draft_digest
        normalized_ticket = validate_ticket(
            ticket,
            expected_owner_revision=policy["quality_standard_ref"],
        )
        existing = self._ticket_drafts.get(draft_digest)
        if existing is not None and existing != normalized_ticket:
            _error("ticket draft digest collision contains mutated content")
        if existing is None:
            self._ticket_drafts[draft_digest] = _safe_copy(normalized_ticket)
            self._ticket_draft_bindings[draft_digest] = {
                "handoff_delivery_id": handoff_delivery_id,
                "handoff_digest": handoff_digest,
                "candidate_digest": normalized["candidate_digest"],
                "question_id": question_id,
                "ticket_revision": ticket_revision,
            }
            path = self.acceptance_root / round_id / "ticket-draft.json"
            _write_exclusive_json(path, normalized_ticket, mode=0o440)
        return _safe_copy(normalized_ticket)

    def protocol_build_acceptance_stage_handoff(
        self,
        stage_calls: Mapping[str, Mapping[str, Any]],
        *,
        protocol_id: str = "protocol",
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Build the canonical handoff from Runner-observed stage calls.

        Protocol supplies only the complete request objects and exact artifact
        paths selected from the observed catalog.  The Runner resolves those
        selections against its immutable MCP-result registry and computes every
        digest, page, receipt, nonce, candidate/state binding, and handoff
        self-reference.
        """

        self._check_capability("protocol", protocol_id, capability)
        if not isinstance(stage_calls, Mapping) or len(stage_calls) != len(MODELING_STAGES):
            _error("stage handoff builder requires exactly five stage calls")
        accepted = self._accepted_candidate_identity
        if accepted is None:
            _error("formal accepted candidate identity is unavailable")
        if self._ordinary_retrieval_gate is not None and self._ordinary_retrieval_receipt is None:
            self.validate_ordinary_retrieval()
        run_id = self._carrier_run_id()
        if run_id is None:
            _error("formal stage handoff run identity is unavailable")
        state = self._observed_model_state(None)
        by_stage: dict[str, Mapping[str, Any]] = {}
        for stage, entry in stage_calls.items():
            if not isinstance(stage, str) or not isinstance(entry, Mapping) or set(entry) != {"tool", "arguments", "artifact_path"}:
                _error("stage handoff builder stage call fields drift")
            if stage in by_stage or stage not in MODELING_STAGES:
                _error("stage handoff builder stage is duplicated or unknown")
            if (
                not isinstance(entry["tool"], str)
                or not entry["tool"]
                or not isinstance(entry["arguments"], Mapping)
                or not isinstance(entry["artifact_path"], str)
            ):
                _error("stage handoff builder stage call is invalid")
            by_stage[stage] = entry
        if set(by_stage) != set(MODELING_STAGES):
            _error("stage handoff builder omits a required stage")

        receipts: list[dict[str, Any]] = []
        for stage in MODELING_STAGES:
            entry = by_stage[stage]
            matches = [
                record
                for record in self._platform_read_artifacts.values()
                if record["tool"] == entry["tool"]
                and record.get("request_arguments") == dict(entry["arguments"])
                and record["artifact_path"] == entry["artifact_path"]
            ]
            if len(matches) != 1:
                _error("stage handoff builder request is not one observed platform call")
            observed = matches[0]
            receipt = {
                "stage": stage,
                "status": {
                    "dry-run": "validated",
                    "apply": "applied",
                    "readback": "complete",
                    "validation": "succeeded",
                    "reasoning": "succeeded",
                }[stage],
                "receipt_digest": None,
                "run_id": run_id,
                "project_id": state["project_id"],
                "ontology_id": state["ontology_id"],
                "slice_revision": accepted["candidate_revision"],
                "model_state_digest": state["state_digest"],
                "evidence_ref": {
                    "type": "platform_read",
                    "ref_id": f"platform-{stage}-{observed['request_digest'][:16]}",
                    "ticket_digest": "0" * 64,
                    "model_state_digest": state["state_digest"],
                    "tool": observed["tool"],
                    "request_digest": observed["request_digest"],
                    "response_digest": observed["response_digest"],
                    "artifact_path": observed["artifact_path"],
                    "page": {
                        "ordinal": 0,
                        "input_cursor": None,
                        "output_cursor": None,
                        "has_more": False,
                        "sequence_complete": True,
                    },
                },
            }
            receipt["receipt_digest"] = modeling_receipt_digest(receipt)
            self._validate_observed_stage_evidence(
                receipt,
                state_digest=state["state_digest"],
            )
            receipts.append(receipt)

        handoff: dict[str, Any] = {
            "schema_version": STAGE_HANDOFF_SCHEMA,
            "handoff_id": f"handoff-{run_id}-{accepted['candidate_digest'][:16]}",
            "handoff_nonce": self._stage_handoff_nonce,
            "task_id": self.task_id,
            "producer_run_id": run_id,
            "slice_id": f"slice-{accepted['candidate_revision']}",
            "slice_revision": accepted["candidate_revision"],
            "model_state": _safe_copy(state),
            "model_state_digest": state["state_digest"],
            "candidate_digest": accepted["candidate_digest"],
            "modeling_receipts": receipts,
            "handoff_digest": None,
        }
        _safe_id(handoff["handoff_id"], "stage handoff.handoff_id")
        _safe_id(handoff["slice_id"], "stage handoff.slice_id")
        handoff_digest = stage_handoff_digest(handoff)
        handoff["handoff_digest"] = handoff_digest
        for receipt in handoff["modeling_receipts"]:
            receipt["evidence_ref"]["ticket_digest"] = handoff_digest
        validate_stage_handoff(
            handoff,
            expected_task_id=self.task_id,
            expected_run_id=run_id,
            expected_nonce=self._stage_handoff_nonce,
        )
        canonical_digest = _sha256_bytes(_canonical_json(handoff))
        self._stage_handoff_builder_outputs[canonical_digest] = {
            "canonical_digest": canonical_digest,
            "handoff_id": handoff["handoff_id"],
            "handoff_digest": handoff["handoff_digest"],
            "handoff_nonce": handoff["handoff_nonce"],
            "task_id": handoff["task_id"],
            "producer_run_id": handoff["producer_run_id"],
        }
        return {
            "handoff_json": _safe_copy(handoff),
            "handoff_digest": handoff_digest,
        }

    def protocol_list_platform_artifacts(
        self,
        *,
        protocol_id: str = "protocol",
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Expose only observed artifact metadata needed for stage selection."""

        self._check_capability("protocol", protocol_id, capability)
        artifacts = []
        for record in sorted(
            self._platform_read_artifacts.values(),
            key=lambda item: item["observation_sequence"],
        ):
            artifacts.append(
                {
                    key: record[key]
                    for key in (
                        "tool",
                        "request_digest",
                        "response_digest",
                        "artifact_path",
                        "request_arguments",
                        "successful",
                        "observation_sequence",
                    )
                }
            )
        return {"artifacts": artifacts}

    def protocol_build_candidate_receipt(
        self,
        *,
        protocol_id: str,
        delivery_id: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Bind the active formal candidate to the canonical receipt builder.

        The Protocol Agent supplies only its role identity and the original
        Modeling delivery ID.  The Runner callback resolves the retained
        candidate and validates its active progress state; no candidate bytes,
        digests, paths, or recipient fields cross this capability boundary.
        """

        self._check_capability("protocol", protocol_id, capability)
        if self._candidate_receipt_builder is None:
            _error("typed candidate receipt capability is unavailable")
        result = self._candidate_receipt_builder(protocol_id, delivery_id)
        if not isinstance(result, Mapping):
            _error("typed candidate receipt builder returned an invalid result")
        return _safe_copy(dict(result))

    def protocol_build_candidate_conflict(
        self,
        *,
        protocol_id: str,
        delivery_id: str,
        conflict_code: str,
        conflict_detail: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Bind a concrete translation conflict to the retained candidate."""

        self._check_capability("protocol", protocol_id, capability)
        if self._candidate_conflict_builder is None:
            _error("typed candidate conflict capability is unavailable")
        result = self._candidate_conflict_builder(
            protocol_id,
            delivery_id,
            conflict_code,
            conflict_detail,
        )
        if not isinstance(result, Mapping):
            _error("typed candidate conflict builder returned an invalid result")
        return _safe_copy(dict(result))

    def _dispatch_capability(
        self,
        role: str,
        operation: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Dispatch only exact role-owned operations after socket auth."""

        if operation not in ROLE_OPERATIONS.get(role, ()):
            _error("Runner capability operation is not available to this role")
        args = dict(arguments)
        capability = self.capability_token(role)
        if role == "modeling" and operation == "modeling_publish_staged_candidate":
            self._check_capability("modeling", args["modeling_id"], capability)
            if self._candidate_publisher is None:
                _error("staged candidate publication is unavailable")
            return self._candidate_publisher(args["modeling_id"])
        if role == "protocol" and operation == "protocol_build_acceptance_stage_handoff":
            stage_calls = args["stage_calls"]
            if not isinstance(stage_calls, Mapping):
                _error("stage handoff builder stage_calls is invalid")
            return self.protocol_build_acceptance_stage_handoff(
                stage_calls,
                protocol_id=args["protocol_id"],
                capability=capability,
            )
        if role == "protocol" and operation == "protocol_list_platform_artifacts":
            return self.protocol_list_platform_artifacts(
                protocol_id=args["protocol_id"],
                capability=capability,
            )
        if role == "protocol" and operation == "protocol_build_candidate_receipt":
            return self.protocol_build_candidate_receipt(
                protocol_id=args["protocol_id"],
                delivery_id=args["delivery_id"],
                capability=capability,
            )
        if role == "protocol" and operation == "protocol_build_candidate_conflict":
            return self.protocol_build_candidate_conflict(
                protocol_id=args["protocol_id"],
                delivery_id=args["delivery_id"],
                conflict_code=args["conflict_code"],
                conflict_detail=args["conflict_detail"],
                capability=capability,
            )
        if role == "coordinator":
            if operation == "coordinator_build_acceptance_ticket_draft_from_delivery":
                return self.coordinator_build_acceptance_ticket_draft_from_delivery(
                    handoff_delivery_id=args["handoff_delivery_id"],
                    question_id=args["question_id"],
                    ticket_revision=args["ticket_revision"],
                    coordinator_id=args["coordinator_id"],
                    capability=capability,
                )
            if operation == "coordinator_build_acceptance_ticket_draft":
                handoff_payload = args["handoff_json"]
                if not isinstance(handoff_payload, Mapping):
                    _error("stage handoff payload is invalid")
                return self.coordinator_build_acceptance_ticket_draft(
                    handoff_payload,
                    handoff_delivery_id=args["handoff_delivery_id"],
                    handoff_digest=args["handoff_digest"],
                    question_id=args["question_id"],
                    ticket_revision=args["ticket_revision"],
                    coordinator_id=args["coordinator_id"],
                    capability=capability,
                )
            if operation == "coordinator_publish_acceptance_ticket":
                ticket_payload = args["ticket_json"]
                if not isinstance(ticket_payload, Mapping):
                    _error("ticket payload is invalid")
                if ticket_payload.get("ticket_digest") != args["ticket_digest"]:
                    _error("ticket digest argument does not match payload")
                if ticket_payload.get("quality_standard_ref") != args["requirement_ref"]:
                    _error("ticket requirement reference does not match payload")
                return self.coordinator_publish_acceptance_ticket(
                    ticket_payload,
                    coordinator_id=args["coordinator_id"],
                    owner_revision=args["owner_revision"],
                    capability=capability,
                )
            return self.coordinator_get_verdict(
                round_id=args["acceptance_round_id"],
                verdict_digest_value=args.get("verdict_digest"),
                coordinator_id=args["coordinator_id"],
                capability=capability,
            )
        if operation == "acceptance_get_ticket":
            ticket = self.get_ticket(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                capability=capability,
            )
            # The model-visible operation is the fixed get/ack surface from the
            # Acceptance contract: retrieving the immutable ticket acknowledges
            # that exact digest before child lifecycle can begin.
            self.ack_ticket(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                ticket_digest_value=ticket["ticket_digest"],
                capability=capability,
            )
            return ticket
        if operation == "acceptance_child_start":
            # The projection and its digest are Runner-owned mechanics.  Keep
            # accepting the legacy explicit fields for compatibility, but
            # require them to be the exact immutable projection for this
            # round/kind.  A model never has to reconstruct or hash either
            # value, and a fabricated binding cannot be silently accepted.
            projected_input, projected_digest = self.project_child_input(
                round_id=args["round_id"],
                kind=args["kind"],
            )
            supplied_input = args.get("input_ref")
            supplied_digest = args.get("input_digest")
            if (supplied_input is None) != (supplied_digest is None):
                _error("child input binding must include both input_ref and input_digest")
            if supplied_input is None:
                supplied_input = projected_input
                supplied_digest = projected_digest
            elif supplied_input != projected_input or supplied_digest != projected_digest:
                _error("child input binding does not match the Runner projection")
            return self.start_child(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                kind=args["kind"],
                input_ref=supplied_input,
                input_digest=supplied_digest,
                ticket_digest_value=args["ticket_digest"],
                attempt=args["attempt"],
                request_id=args["request_id"],
                capability=capability,
            )
        if operation == "acceptance_child_get_report":
            return self.get_report(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                handle=args["child_handle"],
                request_id=args["request_id"],
                capability=capability,
            )
        if operation == "acceptance_child_recycle":
            return self.recycle_child(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                handle=args["child_handle"],
                completion_ref=args["completion_ref"],
                request_id=args["request_id"],
                capability=capability,
            )
        if operation == "acceptance_get_failure_record":
            return self.get_failure_record(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                failure_digest=args["failure_digest"],
                capability=capability,
            )
        if operation == "submit_acceptance_result":
            verdict = args["verdict_json"]
            if not isinstance(verdict, Mapping):
                _error("verdict payload is invalid")
            if verdict.get("verdict_digest") != args["verdict_digest"]:
                _error("verdict digest argument does not match payload")
            return self.submit_verdict(
                acceptance_id=args["acceptance_id"],
                round_id=args["round_id"],
                verdict=verdict,
                request_id=args["request_id"],
                capability=capability,
            )
        return self.get_verdict(
            acceptance_id=args["acceptance_id"],
            round_id=args["round_id"],
            verdict_digest_value=args["verdict_digest"],
            capability=capability,
        )

    def capability_token(self, role: str) -> str:
        if role not in self._capability_tokens:
            _error("unknown Runner capability role")
        return self._capability_tokens[role]

    def coordinator_publish_acceptance_ticket(
        self,
        ticket: Mapping[str, Any],
        *,
        coordinator_id: str = "coordinator",
        owner_revision: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        return self.publish_ticket(
            ticket,
            coordinator_id=coordinator_id,
            owner_revision=owner_revision,
            capability=capability,
        )

    def publish_ticket(
        self,
        ticket: Mapping[str, Any],
        *,
        coordinator_id: str,
        owner_revision: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        self._check_capability("coordinator", coordinator_id, capability)
        if self._ticket_policy is not None:
            if not isinstance(ticket, Mapping):
                _error("formal Coordinator publication requires a Runner-built ticket draft")
            draft_digest = ticket.get("ticket_digest")
            stored = self._ticket_drafts.get(draft_digest) if isinstance(draft_digest, str) else None
            if stored is None:
                _error("formal Coordinator publication requires a Runner-built ticket draft")
            if dict(ticket) != stored:
                _error("formal Coordinator ticket draft was mutated")
        normalized = validate_ticket(ticket, expected_owner_revision=owner_revision)
        self._enforce_ticket_policy(normalized)
        if normalized["task_id"] != self.task_id:
            _error("ticket task does not match carrier")
        if self._formal_platform_scope is not None:
            # Coordinator input is only a candidate binding.  The immutable
            # Runner snapshot is established from the authenticated read path,
            # never from a self-reported ticket digest.
            live_state = self._observed_model_state(None)
            if live_state["state_digest"] != normalized["model_state_digest"]:
                _error("ticket model-state digest does not match live platform state")
        if self._model_state_boundary is None:
            self._model_state_boundary = ModelStateBoundary(normalized["model_state"])
            self._state_epoch = max(1, self._state_epoch + 1)
        elif not self._state_revision_required and normalized["model_state_digest"] != self._model_state_boundary.digest:
            _error("ticket model-state digest is not the current Runner snapshot")
        elif self._state_revision_required and normalized["model_state_digest"] == self._model_state_boundary.digest:
            _error("ticket revision must carry the newly observed model state")
        round_id = normalized["acceptance_round_id"]
        if round_id in self._tickets:
            _error("Acceptance ticket round was already published")
        semantic_fingerprint = self._ticket_semantic_fingerprint(normalized)
        for prior_round_id, prior_ticket in self._tickets.items():
            prior_round = self._rounds.get(prior_round_id, {})
            prior_verdict = prior_round.get("verdict")
            prior_status = prior_round.get("status")
            prior_failed = isinstance(prior_verdict, Mapping) and prior_verdict.get("verdict") in {
                "FAIL",
                "BLOCKED",
            }
            prior_blocked = prior_status == "blocked" or prior_round.get("blocked") is True
            if (prior_failed or prior_blocked) and prior_status != "state_invalidated" and semantic_fingerprint == self._ticket_semantic_fingerprint(prior_ticket):
                _error("unchanged Acceptance rerun is rejected after FAIL/BLOCKED")
        path = self.acceptance_root / round_id / "ticket.json"
        _write_exclusive_json(path, normalized, mode=0o440)
        self._tickets[round_id] = normalized
        self._rounds[round_id] = {
            "ticket_digest": normalized["ticket_digest"],
            "status": "published",
            "children": {},
            "attempts": {},
            "attempt_lineage": {},
            "retryable": False,
            "retryable_kinds": set(),
            "reports": {},
            "cleanup": set(),
            "blocked": False,
            "verdict": None,
            "state_epoch": self._state_epoch,
            "verdict_usable": False,
        }
        return {"ticket_id": normalized["ticket_id"], "acceptance_round_id": round_id, "ticket_digest": normalized["ticket_digest"], "receipt_digest": _sha256_bytes(_canonical_json(normalized))}

    @staticmethod
    def _ticket_semantic_fingerprint(ticket: Mapping[str, Any]) -> str:
        """Hash ticket meaning while ignoring round/request identity bindings.

        A fresh round must carry a real source, model-state, requirement, or other
        semantic correction.  Reissuing the same content with only new ticket/run
        IDs and the resulting digest references is not a new modeling attempt.
        """

        ignored = {
            "ticket_id",
            "acceptance_round_id",
            "producer_run_id",
            "ticket_digest",
            # A Coordinator-side ticket counter is not itself a semantic
            # correction.  It must not make an unchanged failed/blocked rerun
            # eligible when only IDs/digests/counters changed.
            "ticket_revision",
            "run_id",
            "ref_id",
            "request_id",
            "session_id",
        }
        semantic_digests = {
            "source_bundle_digest",
            "model_state_digest",
            "state_digest",
            "quality_standard_digest",
        }

        def project(value: Any, *, key: str | None = None) -> Any:
            if key == "ticket_digest" or (
                key is not None
                and key.endswith("_digest")
                and key not in semantic_digests
            ):
                return None
            if isinstance(value, Mapping):
                return {
                    str(child_key): project(child_value, key=str(child_key))
                    for child_key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
                    if str(child_key) not in ignored
                }
            if isinstance(value, list):
                return [project(child) for child in value]
            if isinstance(value, tuple):
                return [project(child) for child in value]
            return value

        return _sha256_bytes(_canonical_json(project(ticket)))

    def _enforce_ticket_policy(self, ticket: Mapping[str, Any]) -> None:
        """Keep Coordinator-owned ticket fields bound to the fixed requirement standard."""

        policy = self._ticket_policy
        if not policy:
            return
        for field in ("quality_standard_ref", "quality_standard_digest", "quality_standard_artifact", "unknown_policy"):
            expected = policy.get(field)
            if expected is not None and ticket.get(field) != expected:
                _error(f"ticket {field} is not fixed by the acceptance standard")
        expected_cqs = policy.get("competency_questions")
        if expected_cqs is not None and ticket.get("competency_questions") != expected_cqs:
            _error("ticket competency questions are not fixed by the acceptance standard")
        source_paths_by_question = policy.get("approved_source_paths_by_question")
        if isinstance(source_paths_by_question, Mapping):
            question_id = ticket.get("question_id")
            expected_paths = source_paths_by_question.get(question_id)
            if expected_paths is None:
                _error("ticket question is not in the fixed acceptance standard")
            actual_paths = [item["path"] for item in ticket["approved_sources"]]
            if actual_paths != sorted(str(path) for path in expected_paths):
                _error("ticket approved sources are not fixed by the acceptance standard")
        # When the Runner has the staged source bytes, Coordinator-provided
        # digests are checked against those bytes before durable publication.
        for source in ticket["approved_sources"]:
            material = self._source_materials.get(source["path"])
            if material is None:
                continue
            try:
                digest = _sha256_bytes(material.read_bytes())
            except OSError as exc:
                raise AcceptanceContractError("approved source material is unreadable") from exc
            if digest != source["sha256"]:
                _error("ticket approved source digest does not match exact source bytes")

    def get_ticket(self, *, acceptance_id: str, round_id: str, capability: str | None = None) -> dict[str, Any]:
        self._check_capability("acceptance", acceptance_id, capability)
        if round_id not in self._tickets:
            _error("Acceptance ticket not found")
        return _safe_copy(self._tickets[round_id])

    def ack_ticket(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        ticket_digest_value: str,
        capability: str | None = None,
    ) -> dict[str, str]:
        ticket = self.get_ticket(acceptance_id=acceptance_id, round_id=round_id, capability=capability)
        if ticket["ticket_digest"] != ticket_digest_value:
            _error("Acceptance ticket digest mismatch")
        self._rounds[round_id]["status"] = "acknowledged"
        return {"acceptance_round_id": round_id, "ticket_digest": ticket_digest_value, "status": "acknowledged"}

    def _round(
        self,
        acceptance_id: str,
        round_id: str,
        ticket_digest_value: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        self._check_capability("acceptance", acceptance_id, capability)
        if round_id not in self._rounds or self._rounds[round_id]["ticket_digest"] != ticket_digest_value:
            _error("Acceptance round or ticket digest is invalid")
        if self._rounds[round_id]["status"] not in {"acknowledged", "active", "reports_ready", "retryable"}:
            _error("Acceptance round is not ready for child lifecycle")
        self._rounds[round_id]["status"] = "active"
        return self._rounds[round_id]

    def project_child_input(self, *, round_id: str, kind: str) -> tuple[dict[str, Any], str]:
        if round_id not in self._tickets:
            _error("Acceptance ticket not found")
        ticket = self._tickets[round_id]
        if kind == "source":
            projection = {"question": ticket["question"], "approved_sources": ticket["approved_sources"], "source_bundle_digest": ticket["source_bundle_digest"]}
        elif kind == "platform":
            projection = {"question": ticket["question"], "model_state": ticket["model_state"], "platform_read_scope": ticket["platform_read_scope"], "allowed_read_tools": ticket["allowed_read_tools"]}
        else:
            _error("unknown child projection kind")
        validate_child_input(kind, projection)
        digest = _sha256_bytes(_canonical_json(projection))
        path = self.acceptance_root / round_id / f"{kind}-input.json"
        if not path.exists():
            _write_exclusive_json(path, projection, mode=0o400)
        elif _read_json(path) != projection:
            _error("projected child input drifted")
        return _safe_copy(projection), digest

    def start_child(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        kind: str,
        input_ref: Mapping[str, Any],
        input_digest: str,
        ticket_digest_value: str,
        request_id: str,
        attempt: int,
        capability: str | None = None,
    ) -> ChildHandle:
        # C2 boundary (a): pair creation is always preceded by a passive complete
        # model-state read when a Provider has supplied one.
        self.revalidate_model_state(boundary="before-pair")
        round_data = self._round(acceptance_id, round_id, ticket_digest_value, capability)
        if kind not in EXAMINER_KINDS or not isinstance(request_id, str) or not request_id:
            _error("child start kind/request is invalid")
        if attempt not in {0, 1}:
            _error("Examiner attempt must be 0 or 1")
        validate_child_input(kind, input_ref)
        computed_input_digest = _sha256_bytes(_canonical_json(input_ref))
        if input_digest != computed_input_digest:
            _error("child input digest mismatch")
        existing_request = self._request_receipts.get(request_id)
        if existing_request is not None:
            if (
                existing_request[0] != "start"
                or existing_request[1].get("input_digest") != input_digest
                or existing_request[1].get("ticket_digest") != ticket_digest_value
            ):
                _error("child request_id replay conflicts with frozen input")
            return existing_request[1]["handle"]
        active = round_data["children"].get(kind)
        if active is not None:
            if active.attempt == attempt and active.input_digest == input_digest and active.ticket_digest == ticket_digest_value:
                _error("duplicate child start requires the original request_id")
            _error("only one active child of each kind is allowed")
        previous_attempt = round_data["attempts"].get(kind)
        if previous_attempt is not None and attempt != previous_attempt + 1:
            _error("Examiner retry must increment the prior attempt exactly once")
        if previous_attempt == 1:
            _error("Examiner retry budget is exhausted")
        if previous_attempt is None and attempt != 0:
            _error("first Examiner attempt must be zero")
        if previous_attempt == 0 and kind not in round_data.get("retryable_kinds", set()):
            _error("attempt one requires an identical-input infrastructure retry")
        prior_lineage = round_data.get("attempt_lineage", {}).get(kind, {})
        if previous_attempt is not None:
            previous_record = prior_lineage.get(str(previous_attempt))
            if not isinstance(previous_record, Mapping):
                _error("Examiner retry lineage is unavailable")
            if (
                previous_record.get("input_digest") != input_digest
                or previous_record.get("ticket_digest") != ticket_digest_value
            ):
                _error("Examiner retry must reuse the identical frozen input and ticket")
        # Round ordering: every prior round must have durable cleanup before this start.
        current_index = list(self._rounds).index(round_id)
        for prior in list(self._rounds)[:current_index]:
            if self._rounds[prior]["status"] not in {"cleaned", "invalidated", "state_invalidated", "blocked"}:
                _error("next Acceptance round cannot start before prior child cleanup")
        session_id = f"examiner-{secrets.token_hex(12)}"
        token = f"child-handle-{secrets.token_urlsafe(24)}"
        binding = {"task_id": self.task_id, "acceptance_round_id": round_id, "kind": kind, "input_digest": input_digest, "ticket_digest": ticket_digest_value, "session_id": session_id, "request_id": request_id}
        digest = _sha256_bytes(_canonical_json(binding))
        handle = ChildHandle(token, digest, self.task_id, round_id, kind, input_digest, ticket_digest_value, session_id, attempt, request_id)
        private_root = self.acceptance_root / round_id / "children" / digest
        private_root.mkdir(parents=True, mode=0o700, exist_ok=False)
        private_input = private_root / "input.json"
        _write_exclusive_json(private_input, input_ref, mode=0o400)
        if kind == "source" and self._source_materials:
            # The Source child alone receives exact approved source bytes.  The
            # platform child and all persistent role manifests receive only the
            # ticket's digest-bound projection.
            for source in self._tickets[round_id]["approved_sources"]:
                source_path = str(source["path"])
                material = self._source_materials.get(source_path)
                if material is None:
                    _error("approved source material is unavailable")
                try:
                    payload = material.read_bytes()
                except OSError:
                    _error("approved source material is unreadable")
                if _sha256_bytes(payload) != source["sha256"]:
                    _error("approved source material digest mismatch")
                target = private_root / "sources" / source_path
                _write_exclusive_bytes(target, payload)
        read_key: ReadOnlyKeyRecord | None = None
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None
        if kind == "platform":
            ticket = self._tickets[round_id]
            config_digest = _sha256_bytes(
                _canonical_json(
                    {
                        "kind": kind,
                        "allowlist": ticket["allowed_read_tools"],
                        "scope": ticket["platform_read_scope"],
                    }
                )
            )
            try:
                read_key = self.key_lifecycle.create(
                    project_id=ticket["model_state"]["project_id"],
                    ontology_id=ticket["model_state"]["ontology_id"],
                    acceptance_round_id=round_id,
                    ticket_digest_value=ticket_digest_value,
                    input_digest=input_digest,
                    config_digest=config_digest,
                )
            except Exception:
                shutil.rmtree(private_root, ignore_errors=True)
                raise
            if isinstance(self.key_lifecycle, PlatformApiReadKeyLifecycle):
                try:
                    platform_forwarder = self.key_lifecycle.forwarder_for(
                        read_key.key_id,
                        expected_tools=ticket["allowed_read_tools"],
                    )
                except Exception as exc:
                    # A key created by the formal API must never survive a forwarder
                    # startup/inventory failure.
                    try:
                        self.key_lifecycle.revoke(read_key.key_id)
                    except Exception:
                        pass
                    shutil.rmtree(private_root, ignore_errors=True)
                    raise AcceptanceContractError("platform read forwarder start failed") from exc
        ticket = self._tickets[round_id]
        descriptor = self.descriptors[kind]
        resource_spec = {
            "task_id": self.task_id,
            "acceptance_round_id": round_id,
            "kind": kind,
            "attempt": attempt,
            "session_id": session_id,
            "child_handle_digest": digest,
            "ticket_digest": ticket_digest_value,
            "input_digest": input_digest,
            "private_root": str(private_root),
            "private_input": str(private_input),
            "read_key_id": read_key.key_id if read_key else None,
            "read_key_digest": read_key.key_digest if read_key else None,
            # The following fields are Runner-private inputs to the adapter.  They are
            # deliberately removed from every durable receipt/config and are never
            # returned through the opaque child handle API.  The platform read key is
            # handed to the adapter only so its local proxy can hold it; the child
            # process itself never receives this plaintext.
            "descriptor": _safe_copy(descriptor),
            "source_bundle_digest": ticket["source_bundle_digest"],
            "platform_read_scope": _safe_copy(ticket["platform_read_scope"]),
            "model_state_digest": ticket["model_state_digest"],
            "allowed_read_tools": list(ticket["allowed_read_tools"]),
            "timeout_seconds": ticket.get("timeout_seconds", 60),
            "read_key_plaintext": (
                self.key_lifecycle.plaintext_for(read_key.key_id) if read_key is not None else None
            ),
            "read_key_revoke": self.key_lifecycle.revoke,
            "platform_forwarder": platform_forwarder,
            "formal_platform": isinstance(self.key_lifecycle, PlatformApiReadKeyLifecycle),
            "report_submit": lambda report: self.ingest_report(
                acceptance_id=self.acceptance_id,
                round_id=round_id,
                handle=handle,
                report=report,
            ),
            "record_infrastructure_failure": lambda failure_category, reason_code: self.record_infrastructure_failure(
                acceptance_id=self.acceptance_id,
                round_id=round_id,
                handle=handle,
                failure_category=failure_category,
                reason_code=reason_code,
            ),
        }
        # Publish the opaque handle before launching the process so an immediately
        # crashing child can bind its watchdog receipt to the same handle.  Any launch
        # failure removes this provisional entry below.
        self._handles[token] = handle
        try:
            resource = self._child_factory(resource_spec) if self._child_factory else _NoopChildResource(resource_spec)
        except Exception as exc:
            self._handles.pop(token, None)
            self._pending_reports.pop(token, None)
            if read_key is not None:
                self.key_lifecycle.revoke(read_key.key_id)
            shutil.rmtree(private_root, ignore_errors=True)
            raise AcceptanceContractError("child resource start failed") from exc
        receipt = ChildResourceReceipt(
            child_handle_digest=digest,
            session_id=session_id,
            kind=kind,
            private_root=f"acceptance/{round_id}/children/{digest}",
            read_key_id=read_key.key_id if read_key else None,
            config_digest=(config_digest if kind == "platform" else None),
            proxy_socket_path=(
                "platform-read-proxy"
                if kind == "platform"
                else None
            ),
        )
        round_data["children"][kind] = handle
        round_data["attempts"][kind] = attempt
        round_data["attempt_lineage"].setdefault(kind, {})[str(attempt)] = {
            "attempt": attempt,
            "input_digest": input_digest,
            "ticket_digest": ticket_digest_value,
            "request_id": request_id,
            "session_id": session_id,
            "handle_digest": digest,
        }
        # A process-start failure may be recorded by the child factory before the
        # handle is fully published.  Preserve its attempt-0 retry marker until the
        # typed failure is recycled; normal healthy starts clear the marker here.
        failure_during_start = any(
            item.child_handle_digest == digest and item.attempt == attempt
            for item in self._failures.values()
        )
        if not failure_during_start:
            round_data["retryable_kinds"].discard(kind)
        round_data["retryable"] = bool(round_data["retryable_kinds"])
        self._resources[token] = (receipt, resource)
        pending_reports = self._pending_reports.pop(token, [])
        try:
            for pending in pending_reports:
                self.ingest_report(
                    acceptance_id=self.acceptance_id,
                    round_id=round_id,
                    handle=handle,
                    report=pending,
                )
        except Exception:
            self._resources.pop(token, None)
            self._handles.pop(token, None)
            round_data["children"].pop(kind, None)
            if round_data["attempts"].get(kind) == attempt:
                round_data["attempts"].pop(kind, None)
            round_data["attempt_lineage"].get(kind, {}).pop(str(attempt), None)
            for method in ("stop", "destroy"):
                action = getattr(resource, method, None)
                if callable(action):
                    try:
                        action()
                    except Exception:
                        pass
            if read_key is not None:
                try:
                    self.key_lifecycle.revoke(read_key.key_id)
                except Exception:
                    pass
            shutil.rmtree(private_root, ignore_errors=True)
            raise
        start_receipt = {"handle": handle, "input_digest": input_digest, "ticket_digest": ticket_digest_value}
        self._request_receipts[request_id] = ("start", start_receipt)
        self._append(round_id, "child-start.jsonl", {"kind": kind, "attempt": attempt, "handle_digest": digest, "input_digest": input_digest, "ticket_digest": ticket_digest_value, "session_id": session_id, "request_id": request_id, "attempt_lineage": round_data["attempt_lineage"][kind]})
        return handle

    def _lookup_handle(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        handle: ChildHandle | str,
        ticket_digest_value: str | None = None,
        capability: str | None = None,
    ) -> ChildHandle:
        self._check_capability("acceptance", acceptance_id, capability)
        token = handle.token if isinstance(handle, ChildHandle) else handle
        found = self._handles.get(token)
        if found is None or found.acceptance_round_id != round_id or (ticket_digest_value is not None and found.ticket_digest != ticket_digest_value):
            _error("opaque child handle is invalid or replayed")
        return found

    def _proxy_receipts_for(self, found: ChildHandle) -> tuple[Mapping[str, Any], ...]:
        entry = self._resources.get(found.token)
        resource = entry[1] if entry is not None else None
        proxy = getattr(resource, "proxy", None)
        snapshot = getattr(proxy, "receipt_snapshot", None)
        if callable(snapshot):
            snapshot = snapshot()
        if snapshot is None:
            snapshot = getattr(resource, "proxy_receipt_snapshot", ())
            if callable(snapshot):
                snapshot = snapshot()
        if not isinstance(snapshot, (tuple, list)):
            return ()
        output: list[Mapping[str, Any]] = []
        for item in snapshot:
            if isinstance(item, Mapping):
                output.append(_safe_copy(dict(item)))
            elif hasattr(item, "__dict__"):
                output.append(_safe_copy(vars(item)))
        return tuple(output)

    def _validate_platform_proxy_evidence(
        self,
        *,
        found: ChildHandle,
        refs: Iterable[Mapping[str, Any]],
        ticket: Mapping[str, Any],
    ) -> None:
        platform_refs = [ref for ref in refs if ref.get("type") == "platform_read"]
        if not platform_refs:
            return
        resource_entry = self._resources.get(found.token)
        resource = resource_entry[1] if resource_entry is not None else None
        has_proxy = getattr(resource, "proxy", None) is not None
        actual = self._proxy_receipts_for(found)
        if not actual:
            if self._formal_platform_scope is not None or has_proxy:
                _error("Platform report has no successful scoped proxy receipt")
            return
        expected_scope = ticket["platform_read_scope"]
        used: set[int] = set()
        artifacts_to_write: list[tuple[Path, dict[str, Any]]] = []
        for index, receipt in enumerate(actual):
            required = {
                "ordinal",
                "project_id",
                "ontology_id",
                "graph_set_id",
                "ticket_digest",
                "model_state_digest",
                "tool",
                "request_digest",
                "response_digest",
                "artifact_path",
            }
            if set(receipt) != required:
                _error("scoped proxy receipt fields drifted")
            if (
                receipt["project_id"] != expected_scope["project_id"]
                or receipt["ontology_id"] != expected_scope["ontology_id"]
                or receipt["graph_set_id"] != expected_scope["graph_set_id"]
                or receipt["ticket_digest"] != ticket["ticket_digest"]
                or receipt["model_state_digest"] != ticket["model_state_digest"]
            ):
                _error("scoped proxy receipt scope binding drifted")
            if not isinstance(receipt["ordinal"], int) or receipt["ordinal"] < 0:
                _error("scoped proxy receipt ordinal is invalid")
            if receipt["ordinal"] != index:
                _error("scoped proxy receipt ordinal sequence drifted")
            if receipt["tool"] not in set(canonical_platform_allowlist()):
                _error("scoped proxy receipt tool is outside the read allowlist")
            _safe_digest(receipt["request_digest"], "scoped proxy request digest")
            _safe_digest(receipt["response_digest"], "scoped proxy response digest")
            _safe_relative_path(receipt["artifact_path"], "scoped proxy artifact path")
            expected_artifact_path = (
                f"acceptance/{found.acceptance_round_id}/platform-read/"
                f"{found.digest}/{index}.json"
            )
            if receipt["artifact_path"] != expected_artifact_path:
                _error("scoped proxy artifact path is not Runner-retained")
        for ref in platform_refs:
            matches = [
                (index, receipt)
                for index, receipt in enumerate(actual)
                if (
                    receipt["tool"] == ref.get("tool")
                    and receipt["request_digest"] == ref.get("request_digest")
                    and receipt["response_digest"] == ref.get("response_digest")
                    and receipt["artifact_path"] == ref.get("artifact_path")
                )
            ]
            if len(matches) != 1:
                _error("platform evidence does not match a current scoped proxy receipt")
            index, receipt = matches[0]
            if index in used:
                _error("platform evidence repeats a scoped proxy receipt")
            used.add(index)
            artifact = self.root / receipt["artifact_path"]
            if artifact.is_symlink() or (artifact.exists() and not artifact.is_file()):
                _error("scoped proxy evidence artifact is invalid")
            if artifact.exists():
                try:
                    existing = _read_json(artifact)
                except Exception as exc:
                    raise AcceptanceContractError("scoped proxy evidence artifact is unreadable") from exc
                if existing != dict(receipt):
                    _error("scoped proxy evidence artifact drifted")
            else:
                artifacts_to_write.append((artifact, dict(receipt)))
        # Do not publish any newly retained receipt artifact until every report
        # reference has passed scope, digest, path, and duplicate checks.  A
        # rejected report therefore leaves no partial evidence trail behind.
        for artifact, payload in artifacts_to_write:
            _write_exclusive_json(artifact, payload, mode=0o440)

    def _validate_source_artifacts(
        self,
        *,
        round_id: str,
        refs: Iterable[Mapping[str, Any]],
        ticket: Mapping[str, Any],
    ) -> None:
        # Offline contract doubles do not have staged source bytes.  Formal runs do,
        # and therefore require a Runner-retained manifest artifact rather than a
        # model-reported virtual path or digest.
        if not self._source_materials:
            return
        approved = {item["path"]: item["sha256"] for item in ticket["approved_sources"]}
        seen: set[str] = set()
        artifacts_to_write: list[tuple[Path, dict[str, Any]]] = []
        for ref in refs:
            if ref.get("type") != "approved_source":
                continue
            location = str(ref.get("location", "")).split("#", 1)[0]
            if location not in approved:
                _error("Source evidence location is outside the approved manifest")
            material = self._source_materials.get(location)
            if material is None:
                _error("approved source material is unavailable")
            try:
                actual_digest = _sha256_bytes(material.read_bytes())
            except OSError as exc:
                raise AcceptanceContractError("approved source material is unreadable") from exc
            if actual_digest != approved[location] or ref.get("artifact_digest") != approved[location]:
                _error("Source evidence artifact digest does not match approved manifest")
            expected_path = f"acceptance/{round_id}/approved-source/{location}.json"
            if ref.get("artifact_path") != expected_path:
                _error("Source evidence artifact path is not Runner-retained")
            if location in seen:
                _error("Source evidence repeats an approved artifact")
            seen.add(location)
            artifact = self.root / expected_path
            if artifact.is_symlink() or (artifact.exists() and not artifact.is_file()):
                _error("approved source evidence artifact is invalid")
            payload = {"path": location, "sha256": approved[location]}
            if artifact.exists():
                if _read_json(artifact) != payload:
                    _error("approved source evidence artifact drifted")
            else:
                artifacts_to_write.append((artifact, payload))
        # Keep source-artifact publication transactional with report validation;
        # malformed or duplicate refs cannot leave a misleading retained artifact.
        for artifact, payload in artifacts_to_write:
            _write_exclusive_json(artifact, payload, mode=0o440)

    def ingest_report(self, *, acceptance_id: str, round_id: str, handle: ChildHandle | str, report: Mapping[str, Any], capability: str | None = None) -> dict[str, Any]:
        found = self._lookup_handle(acceptance_id=acceptance_id, round_id=round_id, handle=handle, capability=capability)
        _assert_report_persistence_safe(report)
        if found.token not in self._resources:
            pending = self._pending_reports.setdefault(found.token, [])
            if pending:
                _error("child report is submitted more than once before resource binding")
            pending.append(_safe_copy(dict(report)))
            return {"status": "queued", "child_handle_digest": found.digest}
        ticket = self._tickets[round_id]
        normalized = dict(report)
        # Runner, not the child, supplies the model-state envelope.
        normalized["model_state"] = _safe_copy(ticket["model_state"])
        normalized["report_digest"] = report_digest({**normalized, "report_digest": None})
        valid = validate_report(normalized, ticket=ticket, kind=found.kind, handle_digest=found.digest, input_digest=found.input_digest, session_id=found.session_id)
        self._validate_platform_proxy_evidence(found=found, refs=valid["evidence_refs"], ticket=ticket)
        self._validate_source_artifacts(round_id=round_id, refs=valid["evidence_refs"], ticket=ticket)
        if found.token in self._reports:
            if self._reports[found.token]["report_digest"] == valid["report_digest"]:
                return _safe_copy(self._reports[found.token])
            _error("child report is immutable")
        self._reports[found.token] = valid
        self._rounds[round_id]["reports"][found.kind] = valid
        self._rounds[round_id]["status"] = "reports_ready" if len(self._rounds[round_id]["reports"]) == 2 else "active"
        self._append(round_id, f"{found.kind}-report.json", valid)
        return _safe_copy(valid)

    def report_sink(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        handle: ChildHandle | str,
        capability: str | None = None,
    ) -> ChildReportSink:
        found = self._lookup_handle(
            acceptance_id=acceptance_id,
            round_id=round_id,
            handle=handle,
            capability=capability,
        )
        return ChildReportSink(self, round_id=round_id, handle=found)

    def child_resource_receipt(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        handle: ChildHandle | str,
        capability: str | None = None,
    ) -> ChildResourceReceipt:
        found = self._lookup_handle(
            acceptance_id=acceptance_id,
            round_id=round_id,
            handle=handle,
            capability=capability,
        )
        entry = self._resources.get(found.token)
        if entry is None:
            _error("child resource receipt is unavailable")
        return entry[0]

    def get_report(self, *, acceptance_id: str, round_id: str, handle: ChildHandle | str, request_id: str, capability: str | None = None) -> dict[str, Any]:
        found = self._lookup_handle(acceptance_id=acceptance_id, round_id=round_id, handle=handle, capability=capability)
        if not isinstance(request_id, str) or not request_id:
            _error("report request_id is invalid")
        report = self._reports.get(found.token)
        if report is not None:
            return _safe_copy(report)
        failure = next(
            (
                item
                for item in self._failures.values()
                if item.child_handle_digest == found.digest and item.attempt == found.attempt
            ),
            None,
        )
        if failure is not None:
            # Keep the model-visible operation a strict two-way readiness surface:
            # terminal report or a typed, handle/attempt-bound infrastructure failure.
            return {
                "type": "infrastructure_failure",
                "ready": True,
                "failure_digest": failure.failure_digest,
                "failure_category": failure.failure_category,
                "reason_code": failure.reason_code,
                "ticket_digest": failure.ticket_digest,
                "child_input_digest": failure.child_input_digest,
                "child_handle_digest": failure.child_handle_digest,
                "attempt": failure.attempt,
            }
        return {
            "type": "not_ready",
            "ready": False,
            "code": "examiner-result-not-ready",
            "ticket_digest": found.ticket_digest,
            "child_input_digest": found.input_digest,
            "child_handle_digest": found.digest,
            "attempt": found.attempt,
        }

    def get_failure_readiness(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        handle: ChildHandle | str,
        request_id: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Return typed readiness for a watchdog-recorded infrastructure failure."""
        found = self._lookup_handle(
            acceptance_id=acceptance_id,
            round_id=round_id,
            handle=handle,
            capability=capability,
        )
        if not isinstance(request_id, str) or not request_id:
            _error("failure readiness request_id is invalid")
        failure = next(
            (
                item
                for item in self._failures.values()
                if item.child_handle_digest == found.digest and item.attempt == found.attempt
            ),
            None,
        )
        if failure is None:
            _error("infrastructure failure readiness is unavailable")
        return {
            "type": "infrastructure_failure",
            "ready": True,
            "failure_digest": failure.failure_digest,
            "failure_category": failure.failure_category,
            "reason_code": failure.reason_code,
            "ticket_digest": failure.ticket_digest,
            "child_input_digest": failure.child_input_digest,
            "child_handle_digest": failure.child_handle_digest,
            "attempt": failure.attempt,
        }

    def record_infrastructure_failure(self, *, acceptance_id: str, round_id: str, handle: ChildHandle | str, failure_category: str, reason_code: str, capability: str | None = None) -> InfrastructureFailure:
        found = self._lookup_handle(acceptance_id=acceptance_id, round_id=round_id, handle=handle, capability=capability)
        if not isinstance(failure_category, str) or not failure_category or not isinstance(reason_code, str) or not reason_code:
            _error("infrastructure failure category/reason is invalid")
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", failure_category)
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", reason_code)
        ):
            _error("infrastructure failure category/reason is not a sanitized code")
        for existing in self._failures.values():
            if (
                existing.child_handle_digest == found.digest
                and existing.attempt == found.attempt
            ):
                return existing
        payload = {"task_id": self.task_id, "acceptance_round_id": round_id, "ticket_digest": found.ticket_digest, "child_handle_digest": found.digest, "child_input_digest": found.input_digest, "attempt": found.attempt, "failure_category": failure_category, "reason_code": reason_code, "recorded_at": str(time.time_ns())}
        digest = _sha256_bytes(_canonical_json(payload))
        failure = InfrastructureFailure(**payload, failure_digest=digest)
        self._failures[digest] = failure
        if found.attempt == 1:
            # Attempt 0 plus one identical-input retry is the complete
            # infrastructure budget. The persistent Acceptance and the other
            # three roles stay live, but this round is terminally blocked.
            self._rounds[round_id]["blocked"] = True
            self._rounds[round_id]["status"] = "blocked"
        else:
            # Attempt 0 is retryable only after its child has been recycled.  The
            # round remains active while the crashed child is still present.
            self._rounds[round_id]["retryable_kinds"].add(found.kind)
            self._rounds[round_id]["retryable"] = True
        self._append(round_id, "infrastructure-failure.jsonl", {**payload, "failure_digest": digest})
        return failure

    def get_failure_record(self, *, acceptance_id: str, round_id: str, failure_digest: str, capability: str | None = None) -> InfrastructureFailure:
        self._check_capability("acceptance", acceptance_id, capability)
        failure = self._failures.get(failure_digest)
        if failure is None or failure.acceptance_round_id != round_id:
            _error("infrastructure failure record is unavailable")
        return failure

    def failure_evidence_ref(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        failure_digest: str,
        cleanup_receipt_digest: str,
        capability: str | None = None,
    ) -> dict[str, Any]:
        """Resolve one typed infrastructure reference after durable child cleanup."""
        failure = self.get_failure_record(
            acceptance_id=acceptance_id,
            round_id=round_id,
            failure_digest=failure_digest,
            capability=capability,
        )
        _safe_digest(cleanup_receipt_digest, "cleanup_receipt_digest")
        cleanup = next(
            (
                receipt
                for receipt in self._cleanups.values()
                if receipt.child_handle_digest == failure.child_handle_digest
                and receipt.infrastructure_failure_digest == failure.failure_digest
            ),
            None,
        )
        if cleanup is None or cleanup.receipt_digest != cleanup_receipt_digest:
            _error("infrastructure failure cleanup receipt is unavailable or mismatched")
        ref = {
            "type": "infrastructure_failure",
            "failure_digest": failure.failure_digest,
            "cleanup_receipt_digest": cleanup_receipt_digest,
            "task_id": failure.task_id,
            "acceptance_round_id": failure.acceptance_round_id,
            "child_handle_digest": failure.child_handle_digest,
            "attempt": failure.attempt,
            "failure_category": failure.failure_category,
            "reason_code": failure.reason_code,
            "ticket_digest": failure.ticket_digest,
            "child_input_digest": failure.child_input_digest,
        }
        return validate_typed_evidence_ref(ref, expected_ticket=failure.ticket_digest)

    def recycle_child(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        handle: ChildHandle | str,
        completion_ref: Mapping[str, Any],
        request_id: str,
        capability: str | None = None,
    ) -> CleanupReceipt:
        if not isinstance(request_id, str) or not request_id:
            _error("recycle request_id is invalid")
        prior_request = self._request_receipts.get(request_id)
        if prior_request is not None:
            if prior_request[0] != "recycle":
                _error("recycle request_id was used by another operation")
            prior_receipt = prior_request[1]
            if isinstance(handle, ChildHandle) and prior_receipt.child_handle_digest != handle.digest:
                _error("recycle request_id handle binding drifted")
            if set(completion_ref) == {"terminal_report_digest"}:
                completion_digest = completion_ref["terminal_report_digest"]
            elif set(completion_ref) == {"infrastructure_failure_digest"}:
                completion_digest = completion_ref["infrastructure_failure_digest"]
            else:
                _error("recycle completion_ref must contain exactly one typed digest")
            if prior_receipt.completion_digest != completion_digest:
                _error("recycle request_id completion binding drifted")
            return prior_receipt
        found = self._lookup_handle(acceptance_id=acceptance_id, round_id=round_id, handle=handle, capability=capability)
        if found.token not in self._handles:
            _error("child handle has already been recycled")
        keys = set(completion_ref)
        if keys == {"terminal_report_digest"}:
            completion_kind = "terminal_report"
            completion_digest = completion_ref["terminal_report_digest"]
            if found.token not in self._reports or self._reports[found.token]["report_digest"] != completion_digest:
                _error("terminal recycle requires matching immutable report digest")
            failure_digest = None
        elif keys == {"infrastructure_failure_digest"}:
            completion_kind = "infrastructure_failure"
            completion_digest = completion_ref["infrastructure_failure_digest"]
            failure = self._failures.get(completion_digest)
            if failure is None or failure.child_handle_digest != found.digest:
                _error("infrastructure recycle requires matching failure digest")
            failure_digest = completion_digest
        else:
            _error("recycle completion_ref must contain exactly one typed digest")
        existing = self._cleanups.get(found.token)
        if existing is not None:
            if existing.completion_digest == completion_digest:
                return existing
            _error("child cleanup is immutable")
        resource_entry = self._resources.get(found.token)
        resource_receipt, resource = resource_entry if resource_entry is not None else (None, None)
        if resource is not None:
            try:
                stop = getattr(resource, "stop", None)
                if callable(stop):
                    stop()
                destroy = getattr(resource, "destroy", None)
                if callable(destroy):
                    destroy()
            except Exception as exc:
                raise AcceptanceContractError("child resource cleanup failed") from exc
        read_key_id = resource_receipt.read_key_id if resource_receipt is not None else None
        if read_key_id is not None:
            self.key_lifecycle.revoke(read_key_id)
        private_root = self.root / (resource_receipt.private_root if resource_receipt is not None else "")
        if resource_receipt is not None:
            if private_root.is_symlink() or (private_root.exists() and not private_root.is_dir()):
                _error("child private input tree is invalid")
            shutil.rmtree(private_root, ignore_errors=True)
        # Durable cleanup evidence names the capability, never the host private path.
        private_input_path = "child-input" if resource_receipt is not None else None
        destroyed_resources = ["child-session", "child-input", "child-credentials", "child-report-sink"]
        if resource_receipt is not None and resource_receipt.proxy_socket_path is not None:
            destroyed_resources.append("platform-read-proxy")
        receipt_payload = {"task_id": self.task_id, "acceptance_round_id": round_id, "child_handle_digest": found.digest, "completion_kind": completion_kind, "completion_digest": completion_digest, "cleanup_status": "destroyed", "destroyed_resources": destroyed_resources, "infrastructure_failure_digest": failure_digest, "read_key_id": read_key_id, "private_input_path": private_input_path}
        receipt_digest = _sha256_bytes(_canonical_json(receipt_payload))
        receipt = CleanupReceipt(**receipt_payload, receipt_digest=receipt_digest)
        self._cleanups[found.token] = receipt
        self._request_receipts[request_id] = ("recycle", receipt)
        self._rounds[round_id]["cleanup"].add(found.kind)
        self._rounds[round_id]["children"].pop(found.kind, None)
        self._append(round_id, "child-cleanup.jsonl", {**receipt_payload, "receipt_digest": receipt_digest})
        self._handles.pop(found.token, None)
        self._resources.pop(found.token, None)
        if self._rounds[round_id]["cleanup"] == EXAMINER_KINDS:
            if self._rounds[round_id]["blocked"]:
                self._rounds[round_id]["status"] = "blocked"
            elif self._rounds[round_id].get("retryable"):
                self._rounds[round_id]["status"] = "retryable"
            else:
                self._rounds[round_id]["status"] = "cleaned"
        return receipt

    def submit_verdict(
        self,
        *,
        acceptance_id: str,
        round_id: str,
        verdict: Mapping[str, Any],
        request_id: str,
        capability: str | None = None,
    ) -> VerdictReceipt:
        self._check_capability("acceptance", acceptance_id, capability)
        if round_id not in self._tickets or not isinstance(request_id, str) or not request_id:
            _error("verdict submission binding is invalid")
        existing = self._verdicts.get(round_id)
        if existing is not None:
            if existing.request_id == request_id and existing.verdict_digest == verdict.get("verdict_digest"):
                return existing
            _error("conflicting verdict retry is rejected")
        ticket = self._tickets[round_id]
        reports = self._rounds[round_id]["reports"]
        if verdict.get("verdict") == "PASS":
            # C2 boundary (b): a PASS is never persisted against a state that changed
            # after the child reports were accepted.
            prior_passes = sum(
                1
                for item in self._rounds.values()
                if isinstance(item.get("verdict"), Mapping)
                and item["verdict"].get("verdict") == "PASS"
                and item.get("verdict_usable", True) is not False
            )
            boundary = (
                "after-pass-before-next-cq"
                if prior_passes == 0
                else "after-pass-before-settlement"
            )
            revalidation = self.revalidate_model_state(boundary=boundary)
            if revalidation.get("status") != "valid":
                # The invalidation record is durable, but this request must not
                # partially create a new verdict/receipt for the stale state.
                _error("PASS model state was invalidated before verdict persistence")
        normalized = validate_verdict(verdict, ticket=ticket, source_report=reports.get("source"), platform_report=reports.get("platform"), infrastructure_failures=self._failures.values())
        receipt_payload = {"task_id": self.task_id, "acceptance_round_id": round_id, "request_id": request_id, "verdict_digest": normalized["verdict_digest"], "verdict": normalized["verdict"]}
        receipt_digest = _sha256_bytes(_canonical_json(receipt_payload))
        receipt = VerdictReceipt(**receipt_payload, receipt_digest=receipt_digest)
        self._verdicts[round_id] = receipt
        self._rounds[round_id]["verdict"] = normalized
        self._rounds[round_id]["state_digest"] = normalized["model_state_digest"]
        self._rounds[round_id]["verdict_usable"] = normalized["verdict"] == "PASS"
        if normalized["verdict"] == "PASS" and self._model_state_boundary is not None:
            self._model_state_boundary.record_pass(normalized["verdict_digest"])
        self._append(round_id, "verdict.json", normalized)
        return receipt

    def get_verdict(self, *, acceptance_id: str, round_id: str, verdict_digest_value: str | None = None, capability: str | None = None) -> VerdictReceipt:
        self._check_capability("acceptance", acceptance_id, capability)
        receipt = self._verdicts.get(round_id)
        if receipt is None:
            _error("verdict receipt not found")
        if self._rounds.get(round_id, {}).get("verdict_usable") is False:
            _error("Acceptance verdict was invalidated by model-state drift")
        if verdict_digest_value is not None and receipt.verdict_digest != verdict_digest_value:
            _error("verdict digest mismatch")
        return receipt

    def coordinator_get_verdict(
        self,
        *,
        coordinator_id: str = "coordinator",
        round_id: str,
        verdict_digest_value: str | None = None,
        capability: str | None = None,
    ) -> VerdictReceipt:
        self._check_capability("coordinator", coordinator_id, capability)
        receipt = self._verdicts.get(round_id)
        if receipt is None:
            _error("verdict receipt not found")
        if self._rounds.get(round_id, {}).get("verdict_usable") is False:
            _error("Acceptance verdict was invalidated by model-state drift")
        if verdict_digest_value is not None and receipt.verdict_digest != verdict_digest_value:
            _error("verdict digest mismatch")
        return receipt

    def round_summary(self, round_id: str) -> dict[str, Any]:
        if round_id not in self._rounds:
            _error("Acceptance round not found")
        data = self._rounds[round_id]
        return {
            "acceptance_round_id": round_id,
            "status": data["status"],
            "ticket_digest": data["ticket_digest"],
            "report_kinds": sorted(data["reports"]),
            "cleaned_kinds": sorted(data["cleanup"]),
            "verdict": data["verdict"]["verdict"] if data["verdict"] else None,
            "acceptance_live": self._active_acceptance,
            "active_child_kinds": sorted(data["children"]),
        }

    def _settlement_prerequisites_ready(self, *, require_settlement_boundary: bool) -> bool:
        """Check the exact two-CQ, cleanup, ordering, and boundary contract."""

        if self.is_settled:
            return True
        if self._model_state_boundary is None or self._model_state_boundary.invalidated:
            return False
        current_epoch = self._state_epoch
        current_digest = self._model_state_boundary.digest
        # State invalidation deliberately retains old rounds and receipts as
        # evidence.  Settlement considers only the fresh epoch; requiring the
        # complete current-epoch set to be exactly two prevents a stale PASS or an
        # extra retry from being mistaken for the CQ1 -> CQ2 pair.
        rounds = [
            (round_id, data)
            for round_id, data in self._rounds.items()
            if data.get("state_epoch") == current_epoch
        ]
        if len(rounds) != 2 or self._handles:
            return False
        first_ticket = self._tickets.get(rounds[0][0])
        if not isinstance(first_ticket, Mapping):
            return False
        standard_questions = first_ticket.get("competency_questions")
        if (
            not isinstance(standard_questions, list)
            or len(standard_questions) != 2
            or any(not isinstance(item, Mapping) for item in standard_questions)
        ):
            return False
        expected_question_ids = tuple(str(item["id"]) for item in standard_questions)
        if len(set(expected_question_ids)) != 2:
            return False
        passes: list[Mapping[str, Any]] = []
        for index, (round_id, data) in enumerate(rounds):
            ticket = self._tickets.get(round_id)
            if not isinstance(ticket, Mapping) or ticket.get("question_id") != expected_question_ids[index]:
                return False
            if (
                data.get("status") != "cleaned"
                or data.get("children")
                or data.get("cleanup") != EXAMINER_KINDS
                or data.get("verdict_usable") is not True
            ):
                return False
            verdict = data.get("verdict")
            if (
                isinstance(verdict, Mapping)
                and verdict.get("verdict") == "PASS"
                and verdict.get("usable", True) is not False
            ):
                passes.append(verdict)
        if len(passes) != 2:
            return False
        state_digests = {str(item.get("model_state_digest")) for item in passes}
        if len(state_digests) != 1 or state_digests != {current_digest}:
            return False
        valid_events = [
            event
            for event in self._state_revalidation_boundaries
            if (
                event.get("status") == "valid"
                and event.get("epoch") == current_epoch
                and event.get("bound_state_digest") == current_digest
                and event.get("observed_state_digest") == current_digest
            )
        ]
        if sum(event.get("boundary") == "before-pair" for event in valid_events) < 2:
            return False
        required_after_pass = {"after-pass-before-next-cq", "after-pass-before-settlement"}
        if not required_after_pass.issubset({event.get("boundary") for event in valid_events}):
            return False
        if require_settlement_boundary and not any(
            event.get("boundary") == "before-settlement" for event in valid_events
        ):
            return False
        return True

    def settlement_ready(self) -> bool:
        """Return whether the carrier has the two same-state PASS CQs and no residue."""

        return self._settlement_prerequisites_ready(require_settlement_boundary=False)

    def settle(self) -> dict[str, Any]:
        if self._settlement_payload is not None:
            return _safe_copy(self._settlement_payload)
        if self._model_state_reader is None:
            _error("settlement requires an explicit model-state reader")
        # C3/C4: child cleanup and two persistent PASS verdicts are prerequisites;
        # calling carrier cleanup must never satisfy this method implicitly.
        if not self._settlement_prerequisites_ready(require_settlement_boundary=False):
            _error("settlement requires two same-state PASS verdicts and durable child cleanup")
        self.revalidate_model_state(boundary="before-settlement")
        if not self._settlement_prerequisites_ready(require_settlement_boundary=True):
            _error("settlement model state was invalidated")
        assert self._model_state_boundary is not None
        state = self._model_state_boundary.current
        cas = SettlementCAS.create(
            expected_state_digest=state["state_digest"],
            workspace_version=state["workspace_version"],
        )
        observed = {
            **state,
            "phase": "SETTLED",
            "token": cas.token,
        }
        post_cleanup = observed
        if self._settlement_state_reader is not None:
            post_value = self._settlement_state_reader()
            post_state = self._observed_model_state(post_value)
            post_cleanup = {
                **post_state,
                "phase": "SETTLED",
                "token": cas.token,
            }
        decision = cas.evaluate(observed, post_cleanup=post_cleanup)
        self._append_root(
            "settlement-cas.json",
            {
                **decision,
                "expected_state_digest": cas.expected_state_digest,
                "workspace_version": cas.workspace_version,
                "token": cas.token,
            },
        )
        if decision["status"] != "settled":
            # The post-cleanup readback is another state boundary.  Preserve the
            # old PASS evidence but withhold settlement and require both CQs again.
            self.revalidate_model_state(boundary="post-cleanup", observed=post_cleanup)
            _error("settlement CAS/readback mismatch withheld settlement")
        self._active_acceptance = False
        payload = {
            "task_id": self.task_id,
            "acceptance_id": self.acceptance_id,
            "rounds": sorted(self._rounds),
            "status": "settled",
            "settlement_cas": {
                "cas_digest": cas.cas_digest,
                "expected_state_digest": cas.expected_state_digest,
                "workspace_version": cas.workspace_version,
            },
            "final_readback": {
                "state_digest": post_cleanup.get("state_digest"),
                "workspace_version": post_cleanup.get("workspace_version"),
                "matched": True,
            },
        }
        self._append_root("settlement.json", payload)
        self._settlement_payload = _safe_copy(payload)
        return _safe_copy(payload)

    def abort_cleanup(self, reason: str = "runner-abort") -> dict[str, Any]:
        """Mark this carrier aborted without producing a settlement or PASS."""

        if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", reason):
            _error("abort reason is not a sanitized code")
        self._abort_reason = reason
        return self.cleanup()

    def cleanup(self) -> dict[str, Any]:
        if self._cleanup_payload is not None:
            return _safe_copy(self._cleanup_payload)
        try:
            # Abort cleanup is also used when startup/semantic execution fails.  It
            # destroys every still-active child before revoking keys and endpoints,
            # but deliberately does not call settle().
            for found in list(self._handles.values()):
                if found.token in self._handles:
                    self._destroy_invalidated_child(
                        found,
                        state_digest=(
                            self._model_state_boundary.digest
                            if self._model_state_boundary is not None
                            else "0" * 64
                        ),
                    )
            revoke_all = getattr(self.key_lifecycle, "revoke_all", None)
            if callable(revoke_all):
                revoke_all()
            self.key_lifecycle.assert_no_active()
            settled = self.is_settled
            self._active_acceptance = False
            payload = {
                "task_id": self.task_id,
                "acceptance_id": self.acceptance_id,
                "active_handles": len(self._handles),
                "status": "cleaned" if settled else "aborted",
                "settled": settled,
                "aborted_reason": None if settled else (self._abort_reason or "runner-cleanup-before-settlement"),
                "credentials_destroyed": True,
                "zero_child_residue": not self._handles and not self._resources,
            }
            self._append_root("cleanup.json", payload)
            self._cleanup_payload = _safe_copy(payload)
            return _safe_copy(payload)
        finally:
            # Capability sockets and token files are Runner-private resources;
            # they never survive the carrier cleanup boundary.
            self.stop_capability_endpoints()
            for role in ROLE_OPERATIONS:
                self.capability_token_path(role).unlink(missing_ok=True)
            try:
                self.capability_root.rmdir()
            except OSError:
                pass

    def _append(self, round_id: str, name: str, value: Mapping[str, Any]) -> None:
        path = self.acceptance_root / round_id / name
        if path.suffix == ".jsonl":
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        elif not path.exists():
            _write_exclusive_json(path, value)

    def _append_root(self, name: str, value: Mapping[str, Any]) -> None:
        path = self.root / "evidence" / name
        if path.exists():
            _error("root Acceptance artifact is immutable")
        _write_exclusive_json(path, value)


class CoordinatorPhaseController:
    """Serial Coordinator phase and non-terminal readiness/silence messages."""

    def __init__(self, *, coordinator_id: str = "coordinator", modeling_id: str = "modeling", protocol_id: str = "protocol", acceptance_id: str = "acceptance"):
        self.coordinator_id, self.modeling_id, self.protocol_id, self.acceptance_id = coordinator_id, modeling_id, protocol_id, acceptance_id
        self.phase = AcceptancePhase.PREPARED
        self._ready: set[str] = set()
        self._silent: set[str] = set()
        self._events: list[dict[str, Any]] = []
        self._ticket_revision = 0
        self.generation = 0
        self._revision_pending = False

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(_safe_copy(self._events))

    def start(self) -> None:
        if self.phase != AcceptancePhase.PREPARED:
            _error("Coordinator phase start is invalid")
        self.generation = 1
        self._revision_pending = False
        self.phase = AcceptancePhase.RUNNING
        self._record("phase", "RUNNING")

    def assign_slice(self, *, sender_id: str, objective: str) -> dict[str, Any]:
        if sender_id != self.coordinator_id or self.phase not in {
            AcceptancePhase.RUNNING,
            AcceptancePhase.MODELING_ACTIVE,
            AcceptancePhase.WAITING_ACCEPTANCE,
        }:
            _error("Coordinator can only assign a slice during modeling")
        if not isinstance(objective, str) or not objective:
            _error("slice objective is invalid")
        if self.phase == AcceptancePhase.MODELING_ACTIVE:
            if self._revision_pending:
                self._revision_pending = False
            else:
                self.generation += 1
        elif self.phase == AcceptancePhase.WAITING_ACCEPTANCE:
            # A changed slice/model revision invalidates the old readiness pair.
            self.generation += 1
        self._ready.clear()
        self._silent.clear()
        self.phase = AcceptancePhase.MODELING_ACTIVE
        return self._record("slice-assignment", "MODELING_ACTIVE", recipient=self.modeling_id, objective=objective)

    def readiness(self, *, sender_id: str, message_kind: str, text: str = "", generation: int) -> dict[str, Any]:
        if (
            (sender_id, message_kind)
            not in {
                (self.modeling_id, "ready_for_acceptance"),
                (self.protocol_id, "silent_for_acceptance"),
            }
        ):
            _error("invalid readiness/silence message")
        if self.phase not in {AcceptancePhase.MODELING_ACTIVE, AcceptancePhase.WAITING_ACCEPTANCE}:
            _error("readiness/silence is out of phase")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation != self.generation:
            _error("coordination message belongs to a stale generation")
        if not isinstance(text, str):
            _error("coordination message text is invalid")
        target = self._ready if message_kind == "ready_for_acceptance" else self._silent
        target.add(sender_id)
        event = self._record("coordination", self.phase.value, sender=sender_id, message_kind=message_kind, text=text, terminal=False, settles=False)
        if self._ready == {self.modeling_id} and self._silent == {self.protocol_id}:
            self.phase = AcceptancePhase.WAITING_ACCEPTANCE
            self._record("phase", "WAITING_ACCEPTANCE")
        return event

    def start_acceptance_round(self, *, sender_id: str, round_id: str, generation: int) -> dict[str, Any]:
        if sender_id != self.coordinator_id or self.phase != AcceptancePhase.WAITING_ACCEPTANCE:
            _error("Coordinator cannot start Acceptance before both ready/silence acknowledgements")
        if not isinstance(round_id, str) or not round_id:
            _error("acceptance round identity is invalid")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation != self.generation:
            _error("acceptance round belongs to a stale generation")
        self.phase = AcceptancePhase.ACCEPTANCE_ROUND_ACTIVE
        return self._record("acceptance-start", self.phase.value, recipient=self.acceptance_id, acceptance_round_id=round_id, terminal=False)

    def route_verdict(self, *, sender_id: str, verdict: Mapping[str, Any], generation: int) -> dict[str, Any]:
        if sender_id != self.acceptance_id or self.phase not in {AcceptancePhase.ACCEPTANCE_REPORTS_READY, AcceptancePhase.ACCEPTANCE_ROUND_ACTIVE}:
            _error("Acceptance verdict can only route to Coordinator")
        if verdict.get("verdict") not in {"PASS", "FAIL", "BLOCKED"}:
            _error("invalid Acceptance verdict")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation != self.generation:
            _error("verdict belongs to a stale generation")
        target = self.coordinator_id
        result = self._record("verdict-route", self.phase.value, sender=sender_id, recipient=target, verdict=verdict["verdict"], terminal=False)
        if verdict["verdict"] == "FAIL":
            self.generation += 1
            self._revision_pending = True
            self._ready.clear()
            self._silent.clear()
            self.phase = AcceptancePhase.MODELING_ACTIVE
        elif verdict["verdict"] == "PASS":
            # CQ1 PASS on an unchanged model reuses the same generation for
            # CQ2; the completed ready/silent pair remains valid.
            self.phase = (
                AcceptancePhase.WAITING_ACCEPTANCE
                if self._ready == {self.modeling_id} and self._silent == {self.protocol_id}
                else AcceptancePhase.MODELING_ACTIVE
            )
        elif verdict["verdict"] == "BLOCKED":
            # BLOCKED closes only the temporary child round.  The four persistent
            # roles remain live and Coordinator waits for recovery/ticket revision.
            self.phase = AcceptancePhase.WAITING_ACCEPTANCE
        return result

    def set_reports_ready(self) -> None:
        if self.phase != AcceptancePhase.ACCEPTANCE_ROUND_ACTIVE:
            _error("Acceptance reports-ready event is out of phase")
        self.phase = AcceptancePhase.ACCEPTANCE_REPORTS_READY
        self._record("phase", self.phase.value)

    def _record(self, event: str, phase: str, **extra: Any) -> dict[str, Any]:
        record = {"event": event, "phase": phase, "generation": self.generation, "recorded_at_ns": time.time_ns(), **extra}
        self._events.append(record)
        return _safe_copy(record)


@dataclass
class ModelStateBoundary:
    current: dict[str, Any]
    invalidated: bool = False
    invalidation_reason: str | None = None
    old_passes: list[str] = dataclass_field(default_factory=list)

    def __post_init__(self) -> None:
        self.current = validate_model_state(self.current, allow_runner_bound=False)

    @property
    def digest(self) -> str:
        return self.current["state_digest"]

    def revalidate(self, observed: Mapping[str, Any], *, boundary: str) -> bool:
        state = validate_model_state(observed, allow_runner_bound=False)
        if state["state_digest"] != self.digest:
            self.invalidated = True
            self.invalidation_reason = f"state_invalidated:{boundary}"
            self.old_passes.clear()
            return False
        return True

    def record_pass(self, verdict_digest_value: str) -> None:
        if self.invalidated:
            _error("cannot retain PASS on invalidated model state")
        _safe_digest(verdict_digest_value, "PASS verdict digest")
        self.old_passes.append(verdict_digest_value)


@dataclass(frozen=True)
class SettlementCAS:
    expected_state_digest: str
    workspace_version: str
    phase: str
    token: str
    cas_digest: str

    @classmethod
    def create(cls, *, expected_state_digest: str, workspace_version: str, phase: str = "SETTLED") -> "SettlementCAS":
        _safe_digest(expected_state_digest, "settlement expected_state_digest")
        if not isinstance(workspace_version, str) or not workspace_version or phase != "SETTLED":
            _error("settlement CAS fields are invalid")
        token = secrets.token_hex(12)
        payload = {"expected_state_digest": expected_state_digest, "workspace_version": workspace_version, "phase": phase, "token": token}
        return cls(**payload, cas_digest=_sha256_bytes(_canonical_json(payload)))

    def verify(self, observed: Mapping[str, Any]) -> bool:
        return (
            observed.get("state_digest") == self.expected_state_digest
            and observed.get("workspace_version") == self.workspace_version
            and observed.get("phase") == self.phase
            and observed.get("token", self.token) == self.token
        )

    def evaluate(
        self,
        observed: Mapping[str, Any],
        *,
        post_cleanup: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a durable settlement decision without mutating runtime state.

        A pre-settlement or post-cleanup state drift withholds ``SETTLED`` and
        exposes the boundary that must rerun both competency questions.
        """
        if not self.verify(observed):
            return {
                "status": "withheld",
                "reason": "state_invalidated:pre-settlement",
                "rerun_competency_questions": True,
                "cas_digest": self.cas_digest,
            }
        if post_cleanup is None or not self.verify(post_cleanup):
            return {
                "status": "withheld",
                "reason": "state_invalidated:post-cleanup",
                "rerun_competency_questions": True,
                "cas_digest": self.cas_digest,
            }
        return {
            "status": "settled",
            "reason": "cas-and-post-cleanup-match",
            "rerun_competency_questions": False,
            "cas_digest": self.cas_digest,
        }

    def commit(
        self,
        observed: Mapping[str, Any],
        *,
        post_cleanup: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.evaluate(observed, post_cleanup=post_cleanup)


@dataclass(frozen=True)
class ReadOnlyKeyRecord:
    key_id: str
    project_id: str
    ontology_id: str
    acceptance_round_id: str
    ticket_digest: str
    input_digest: str
    config_digest: str
    status: str
    key_digest: str


class ReadOnlyKeyLifecycle:
    """Explicit deterministic test double for the Platform Examiner read key.

    Formal Runner runs replace this object with :class:`PlatformApiReadKeyLifecycle`
    after ``PlatformScope.prepare`` succeeds.  Keeping this implementation in-memory
    is useful for offline contract tests, but it is never the formal platform path.
    """

    def __init__(self) -> None:
        self._records: dict[str, ReadOnlyKeyRecord] = {}
        self._plaintext: dict[str, str] = {}
        self._post_revoke_denials: dict[str, int] = {}

    def create(
        self,
        *,
        project_id: str,
        ontology_id: str,
        acceptance_round_id: str,
        ticket_digest_value: str,
        input_digest: str,
        config_digest: str,
    ) -> ReadOnlyKeyRecord:
        for field, value in (
            ("project_id", project_id),
            ("ontology_id", ontology_id),
            ("acceptance_round_id", acceptance_round_id),
        ):
            _safe_id(value, field)
        _safe_digest(ticket_digest_value, "read key ticket_digest")
        _safe_digest(input_digest, "read key input_digest")
        _safe_digest(config_digest, "read key config_digest")
        key_id = f"read-key-{secrets.token_hex(10)}"
        plaintext = secrets.token_urlsafe(32)
        payload = {
            "key_id": key_id,
            "project_id": project_id,
            "ontology_id": ontology_id,
            "acceptance_round_id": acceptance_round_id,
            "ticket_digest": ticket_digest_value,
            "input_digest": input_digest,
            "config_digest": config_digest,
            "status": "active",
        }
        digest = _sha256_bytes(_canonical_json(payload))
        record = ReadOnlyKeyRecord(**payload, key_digest=digest)
        self._records[key_id] = record
        self._plaintext[key_id] = plaintext
        return record

    def plaintext_for(self, key_id: str) -> str:
        record = self._records.get(key_id)
        if record is None or record.status != "active" or key_id not in self._plaintext:
            if record is not None and record.status == "revoked":
                self._post_revoke_denials[key_id] = self._post_revoke_denials.get(key_id, 0) + 1
            _error("read key is revoked or unavailable")
        return self._plaintext[key_id]

    def post_revoke_denial_count(self, key_id: str) -> int:
        return self._post_revoke_denials.get(key_id, 0)

    def assert_post_revoke_denied(self, key_id: str) -> None:
        if self.post_revoke_denial_count(key_id) < 1:
            _error("post-revoke read-key denial is not evidenced")

    def revoke(self, key_id: str) -> ReadOnlyKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            _error("read key is unknown")
        if record.status == "revoked":
            return record
        revoked = ReadOnlyKeyRecord(
            key_id=record.key_id,
            project_id=record.project_id,
            ontology_id=record.ontology_id,
            acceptance_round_id=record.acceptance_round_id,
            ticket_digest=record.ticket_digest,
            input_digest=record.input_digest,
            config_digest=record.config_digest,
            status="revoked",
            key_digest=record.key_digest,
        )
        self._records[key_id] = revoked
        self._plaintext.pop(key_id, None)
        return revoked

    def get(self, key_id: str) -> ReadOnlyKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            _error("read key is unknown")
        return record

    def assert_no_active(self) -> None:
        if any(record.status == "active" for record in self._records.values()):
            _error("active Platform Examiner read key remains")

    def revoke_all(self) -> None:
        """Best-effort deterministic cleanup hook shared with formal lifecycle."""
        for key_id, record in list(self._records.items()):
            if record.status == "active":
                self.revoke(key_id)


class PlatformApiReadKeyLifecycle(ReadOnlyKeyLifecycle):
    """Project-scoped read-key lifecycle backed by the existing PlatformScope API.

    The Runner never mints a local substitute in the formal profile.  The admin key
    prepared by ``PlatformScope`` creates the temporary ``read`` key, and the same API
    path revokes it, reads back ``revoked_at``, and proves a harmless request with the
    old plaintext is denied.  The plaintext remains process memory only until the
    child proxy has copied it into its private host-side forwarder.
    """

    def __init__(
        self,
        scope: Any,
        *,
        repository_root: Path | None = None,
        forwarder_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__()
        self.scope = scope
        self.repository_root = repository_root.resolve() if repository_root else None
        self.forwarder_factory = forwarder_factory
        self._forwarders: dict[str, Any] = {}
        self._platform_evidence: dict[str, dict[str, Any]] = {}

    def _platform_request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None,
        key: str,
    ) -> tuple[int, Any]:
        request = getattr(self.scope, "request", None)
        if not callable(request):
            _error("PlatformScope request API is unavailable")
        return request(method, path, dict(body) if body is not None else None, key)

    def create(
        self,
        *,
        project_id: str,
        ontology_id: str,
        acceptance_round_id: str,
        ticket_digest_value: str,
        input_digest: str,
        config_digest: str,
    ) -> ReadOnlyKeyRecord:
        for field, value in (
            ("project_id", project_id),
            ("ontology_id", ontology_id),
            ("acceptance_round_id", acceptance_round_id),
        ):
            _safe_id(value, field)
        _safe_digest(ticket_digest_value, "read key ticket_digest")
        _safe_digest(input_digest, "read key input_digest")
        _safe_digest(config_digest, "read key config_digest")
        admin_key = getattr(self.scope, "admin_key", None)
        scope_project = getattr(self.scope, "project_id", None)
        if not isinstance(admin_key, str) or not admin_key:
            _error("PlatformScope admin key is unavailable")
        if scope_project != project_id:
            _error("read key project is outside the prepared PlatformScope")
        status, value = self._platform_request(
            "POST",
            "/api/api-keys",
            {"name": f"r2-3-005-acceptance-{acceptance_round_id}", "project_id": project_id, "scopes": ["read"]},
            admin_key,
        )
        if status != 201 or not isinstance(value, Mapping):
            _error("Platform read key creation failed")
        key_id = value.get("id")
        plaintext = value.get("plaintext_key")
        if not isinstance(key_id, str) or not key_id or not isinstance(plaintext, str) or not plaintext:
            _error("Platform read key creation receipt is incomplete")
        payload = {
            "key_id": key_id,
            "project_id": project_id,
            "ontology_id": ontology_id,
            "acceptance_round_id": acceptance_round_id,
            "ticket_digest": ticket_digest_value,
            "input_digest": input_digest,
            "config_digest": config_digest,
            "status": "active",
        }
        record = ReadOnlyKeyRecord(**payload, key_digest=_sha256_bytes(_canonical_json(payload)))
        self._records[key_id] = record
        self._plaintext[key_id] = plaintext
        self._platform_evidence[key_id] = {
            "create_status": status,
            "key_id": key_id,
            "project_id": project_id,
            "key_digest": record.key_digest,
            "revoke_status": None,
            "status_readback": None,
            "post_revoke_status": None,
            "post_revoke_denied": False,
        }
        return record

    def forwarder_for(
        self,
        key_id: str,
        *,
        expected_tools: Iterable[str],
    ) -> Callable[[str, Mapping[str, Any], str], Mapping[str, Any]]:
        record = self.get(key_id)
        if record.status != "active":
            _error("read key is revoked or unavailable")
        existing = self._forwarders.get(key_id)
        if existing is None:
            if self.forwarder_factory is not None:
                existing = self.forwarder_factory(
                    repository_root=self.repository_root,
                    read_key=self.plaintext_for(key_id),
                    expected_tools=tuple(expected_tools),
                )
            else:
                from .acceptance_runtime import McpReadForwarder

                if self.repository_root is None:
                    _error("formal read forwarder repository root is unavailable")
                existing = McpReadForwarder(
                    repository_root=self.repository_root,
                    read_key=self.plaintext_for(key_id),
                    expected_tools=tuple(expected_tools),
                )
            starter = getattr(existing, "start", None)
            if callable(starter):
                starter()
            self._forwarders[key_id] = existing
        forward = getattr(existing, "forward", None)
        if not callable(forward):
            _error("Platform read forwarder is invalid")
        return forward

    def revoke(self, key_id: str) -> ReadOnlyKeyRecord:
        record = self._records.get(key_id)
        if record is None:
            _error("read key is unknown")
        if record.status == "revoked":
            return record
        admin_key = getattr(self.scope, "admin_key", None)
        if not isinstance(admin_key, str) or not admin_key:
            _error("PlatformScope admin key is unavailable")
        plaintext = self._plaintext.get(key_id)
        evidence = self._platform_evidence.setdefault(key_id, {"key_id": key_id})
        try:
            status, value = self._platform_request(
                "POST", f"/api/api-keys/{key_id}:revoke", None, admin_key
            )
            evidence["revoke_status"] = status
            revoked_at = value.get("revoked_at") if isinstance(value, Mapping) else None
            if status != 200 or not revoked_at:
                _error("Platform read key revoke failed")
            status_readback, readback = self._platform_request(
                "GET", f"/api/api-keys/{key_id}", None, admin_key
            )
            evidence["status_readback"] = {
                "status": status_readback,
                "revoked": bool(isinstance(readback, Mapping) and readback.get("revoked_at")),
            }
            if status_readback != 200 or not isinstance(readback, Mapping) or not readback.get("revoked_at"):
                _error("Platform read key revoke status readback failed")
            if not isinstance(plaintext, str) or not plaintext:
                _error("Platform read key plaintext was unavailable for denial proof")
            scope_project = getattr(self.scope, "project_id", None)
            denial_status, _denial_value = self._platform_request(
                "GET", f"/api/projects/{scope_project}", None, plaintext
            )
            evidence["post_revoke_status"] = denial_status
            if denial_status not in {401, 403}:
                _error("post-revoke Platform read key denial was not proven")
            self._post_revoke_denials[key_id] = self._post_revoke_denials.get(key_id, 0) + 1
            evidence["post_revoke_denied"] = True
            revoked = ReadOnlyKeyRecord(
                key_id=record.key_id,
                project_id=record.project_id,
                ontology_id=record.ontology_id,
                acceptance_round_id=record.acceptance_round_id,
                ticket_digest=record.ticket_digest,
                input_digest=record.input_digest,
                config_digest=record.config_digest,
                status="revoked",
                key_digest=record.key_digest,
            )
            self._records[key_id] = revoked
            return revoked
        finally:
            forwarder = self._forwarders.pop(key_id, None)
            if forwarder is not None:
                stopper = getattr(forwarder, "stop", None)
                if callable(stopper):
                    stopper()
            if self._records.get(key_id, record).status == "revoked":
                self._plaintext.pop(key_id, None)

    def evidence(self, key_id: str) -> dict[str, Any]:
        return _safe_copy(self._platform_evidence.get(key_id, {"key_id": key_id}))

    def revoke_all(self) -> None:
        errors: list[BaseException] = []
        for key_id, record in list(self._records.items()):
            if record.status != "active":
                continue
            try:
                self.revoke(key_id)
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise AcceptanceContractError("one or more Platform read keys could not be revoked") from errors[0]


class PlatformScopeShim:
    """Ticket-bound read request shim used by Platform Examiner calls."""

    def __init__(self, ticket: Mapping[str, Any]):
        self.ticket = validate_ticket(ticket)
        self.requests: list[dict[str, Any]] = []

    def authorize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        normalized = validate_platform_read_request(ticket=self.ticket, request=request)
        self.requests.append(_safe_copy(normalized))
        return normalized

    def response_ref(
        self,
        *,
        request: Mapping[str, Any],
        response: Any,
        artifact_path: str,
        page: Mapping[str, Any],
        ref_id: str,
    ) -> dict[str, Any]:
        request_data = self.authorize(request)
        page_data = _require_exact_keys(page, {"ordinal", "input_cursor", "output_cursor", "has_more", "sequence_complete"}, "platform response page")
        ref = {
            "type": "platform_read",
            "ref_id": _safe_id(ref_id, "platform response ref_id"),
            "ticket_digest": self.ticket["ticket_digest"],
            "model_state_digest": self.ticket["model_state_digest"],
            "tool": request_data["tool"],
            "request_digest": request_data["request_digest"],
            "response_digest": _sha256_bytes(_canonical_json(response)),
            "artifact_path": _safe_relative_path(artifact_path, "platform response artifact_path"),
            "page": page_data,
        }
        return validate_typed_evidence_ref(ref, expected_ticket=self.ticket["ticket_digest"], expected_state=self.ticket["model_state_digest"])


def canonical_platform_allowlist(*, include_validation_reasoning: bool = True) -> tuple[str, ...]:
    base = [
        "check_platform_health", "get_project_build_context", "get_build_session", "get_modeling_context", "get_ontology_workspace_context", "get_ontology_read_model", "get_semantic_read_model", "query_semantic_context", "semantic_sparql_query", "describe_semantic_graph_set", "list_semantic_derived_pointers", "inspect_semantic_projection_status", "list_evidence_references", "get_evidence_reference", "get_ontology_lineage", "inspect_semantic_statement_provenance",
    ]
    if include_validation_reasoning:
        base.extend(sorted(READ_ONLY_VALIDATION_TOOLS))
    return tuple(base)


def validate_platform_read_request(*, ticket: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"project_id", "ontology_id", "graph_set_id", "tool", "ticket_digest", "request_digest"}
    data = _require_exact_keys(request, fields, "platform read request")
    scope = ticket["platform_read_scope"]
    if any(data[field] != scope[field] for field in ("project_id", "ontology_id", "graph_set_id")):
        _error("Platform Examiner read scope is outside the ticket")
    if data["ticket_digest"] != ticket["ticket_digest"] or data["tool"] not in ticket["allowed_read_tools"] or data["tool"] not in set(canonical_platform_allowlist()):
        _error("Platform Examiner read request is outside the ticket allowlist")
    data["request_digest"] = _sha256_bytes(_canonical_json({**data, "request_digest": None}))
    if request["request_digest"] != data["request_digest"]:
        _error("Platform read request digest mismatch")
    return data


def canonical_mode_preflight(*, response: Mapping[str, Any], status_code: int, unit: str, pid: int, started_at: str, process_env: Mapping[str, str]) -> dict[str, Any]:
    """Validate the authenticated no-start canonical writer gate."""
    if status_code != 200:
        _error("canonical-mode preflight must return HTTP 200")
    expected = {"product_write_mode": "rdf_primary"}
    if any(response.get(key) != value for key, value in expected.items()):
        _error("canonical-mode product_write_mode is not rdf_primary")
    if not isinstance(unit, str) or not unit or not isinstance(pid, int) or pid <= 0 or not isinstance(started_at, str) or not started_at:
        _error("canonical-mode process binding is invalid")
    required_env = {"SEMANTIC_CANONICAL_STORE": "rdf", "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary", "SEMANTIC_READ_MODE": "canonical"}
    if any(process_env.get(key) != value for key, value in required_env.items()):
        _error("canonical-mode process environment binding is invalid")
    evidence = {"status_code": status_code, "response": dict(response), "unit": unit, "pid": pid, "started_at": started_at, "process_env": {key: process_env[key] for key in sorted(required_env)}}
    evidence["digest"] = _sha256_bytes(_canonical_json(evidence))
    return evidence


def validate_location_hint(hint: Mapping[str, Any], *, approved_paths: Iterable[str]) -> dict[str, Any]:
    allowed = {"path", "document_range", "section", "keywords", "format", "read_method"}
    if not isinstance(hint, Mapping) or not set(hint).issubset(allowed) or not hint:
        _error("source location hint contains disallowed answer-bearing fields")
    paths = set(approved_paths)
    if "path" in hint and hint["path"] not in paths:
        _error("source location hint path is not approved")
    for key in hint:
        value = hint[key]
        if not isinstance(value, (str, list)) or (isinstance(value, list) and any(not isinstance(item, str) for item in value)):
            _error("source location hint value is invalid")
    return _safe_copy(dict(hint))


def classify_comparison(*, source: Mapping[str, Any], platform: Mapping[str, Any]) -> tuple[str, str, str]:
    """Pure semantic comparison policy consumed by Acceptance.

    It intentionally returns a classification only; it does not inspect source/platform bytes.
    """
    source_answerable = source.get("answerability") == "answerable"
    platform_answerable = platform.get("answerability") == "answerable"
    if not source_answerable:
        if "因缺少相关证据无法回答" in str(source.get("conclusion", "")) and not platform_answerable:
            return "PASS", "", "advance"
        return "BLOCKED", "acceptance-evidence", "revise-ticket"
    if not platform_answerable:
        return "FAIL", "modeling-quality", "model-repair"
    # A matching string without grounded evidence is not semantic agreement.  The
    # reports remain answerable-shaped, but Acceptance must classify this as a
    # modeling-quality gap rather than silently accepting unsupported text.
    if not source.get("evidence") or not platform.get("evidence"):
        return "FAIL", "modeling-quality", "model-repair"
    if source.get("conclusion") != platform.get("conclusion"):
        return "FAIL", "modeling-quality", "model-repair"
    return "PASS", "", "advance"


__all__ = [
    "AcceptanceContractError", "AcceptancePhase", "PERSISTENT_ROLES", "EXAMINER_KINDS", "READ_ONLY_VALIDATION_TOOLS", "canonical_digest", "model_state_digest", "modeling_receipt_digest", "stage_handoff_digest", "ticket_digest", "verdict_digest", "report_digest", "validate_profile_roster", "validate_child_descriptor", "validate_child_input", "validate_model_state", "validate_platform_read_scope", "validate_typed_evidence_ref", "validate_page_chain", "validate_modeling_receipt", "validate_stage_handoff", "validate_ticket", "validate_report", "validate_verdict", "ChildHandle", "CleanupReceipt", "InfrastructureFailure", "VerdictReceipt", "RunnerAcceptanceCarrier", "CoordinatorPhaseController", "ModelStateBoundary", "SettlementCAS", "ReadOnlyKeyLifecycle", "PlatformApiReadKeyLifecycle", "canonical_platform_allowlist", "validate_platform_read_request", "canonical_mode_preflight", "validate_location_hint", "classify_comparison",
]
