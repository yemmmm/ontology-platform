"""R3.0-011 competency-question mechanical contracts.

Pure, Host-side validation and summary helpers for the competency-question
(CQ) lifecycle, the public/hidden freeze, the per-role public projection, and
the v3 hidden-batch acceptance report.  Nothing here judges business answer
quality: every function checks observable structure, revision bindings,
visibility, authorization scope, and execution state only (design §3.3/§4/§6).

No platform resource, API, database table, question bank, ACL service, or
scoring engine is introduced by this module; the question pool stays a run
artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- closed vocabularies ------------------------------------------------------

CQ_ROLE = "competency-question"
# Shared canonical role name: ``contracts.py`` registers the same value in its
# admitted-role set, and Runner/Runtime call sites import it from here.
COMPETENCY_QUESTION_ROLE = CQ_ROLE
COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER = "competency_question_acceptance"
CQ_TASK_PARAMETER = COMPETENCY_QUESTION_ACCEPTANCE_PARAMETER

CQ_DRAFT_SCHEMA = "r3-0-011-cq-draft/v1"
CQ_REVIEW_SCHEMA = "r3-0-011-cq-review/v1"
CQ_PUBLIC_PROJECTION_SCHEMA = "r3-0-011-cq-public-projection/v1"
CQ_FREEZE_SCHEMA = "r3-0-011-cq-freeze/v1"
CQ_BATCH_PACKET_SCHEMA = "r3-0-011-acceptance-batch-packet/v1"
CQ_BATCH_REPORT_SCHEMA = "r3-0-011-acceptance-batch-report/v1"
CQ_EVIDENCE_BUNDLE_SCHEMA = "r3-0-011-acceptance-evidence/v1"
CQ_EVIDENCE_REFERENCE_SCHEMA = "r4-3-006-acceptance-evidence-refs/v2"
CQ_REFERENCE_PACKET_SCHEMA = "r4-3-006-acceptance-batch-packet/v2"

# Round 4 follow-up (e): acceptance-batch LLM calls are attributed in evidence
# with this mode label.  It is recorded by the read-only acceptance path only;
# the StartLedger is never written by acceptance.
CQ_ACCEPTANCE_MODE = "read-only-acceptance"

CQ_LIFECYCLE_PHASES: tuple[str, ...] = (
    "panorama-draft",
    "panorama-review",
    "awaiting-slices",
    "slice-draft",
    "slice-review",
    "frozen",
)
CQ_SCOPE_KINDS: tuple[str, ...] = ("panorama", "slice")
CQ_VISIBILITIES: tuple[str, ...] = ("public", "hidden")
CQ_REVIEW_DECISIONS: tuple[str, ...] = ("approve", "modify", "delete", "supplement")
CQ_REVIEW_DECISION_BY_OPERATION: dict[str, str] = {
    "approve": "approve",
    "modify": "modify",
    "delete": "delete",
    "supplement": "supplement",
}

CQ_REASON_CODES: tuple[str, ...] = (
    "cq_selector_incompatible",
    # The CQ role may be parked in a Runtime provider wait while the Runner
    # is delivering an approved-slice notification.  This is recoverable
    # input routing feedback, not a terminal CQ contract failure.
    "cq_waiting_provider",
    "cq_review_stale",
    "cq_public_projection_missing",
    "cq_hidden_exposed",
    "cq_freeze_schema_mismatch",
    "cq_projection_scenario_map_mismatch",
    "cq_model_binding_missing",
    "cq_batch_scope_unauthorized",
    "cq_production_pending",
    "cq_batch_context_lost",
    # R3.0-012 (design §4.4): the production handoff cannot publish while a
    # staged platform write is in flight, returned an unknown result, or left
    # the reconciliation latch closed.  Recoverable by adjudication, never by
    # editing handoff booleans.
    "cq_unknown_write_pending",
    # R3.0-012 (design §3.4/§4.5): published handoff/report evidence is
    # first-write immutable; a replacement attempt is a typed conflict that
    # must allocate a new attempt, never an overwrite.
    "cq_handoff_immutable",
    # R3.0-012 (design §4.5): the completion-channel summary does not match the
    # registered attempt's retained report -- a missing file, a digest
    # conflict, run/freeze/batch binding drift, or a forged aggregate verdict.
    # A recoverable rejection: it never completes the acceptance lifecycle and
    # never pollutes the current attempt's retained result.
    "cq_acceptance_report_mismatch",
)

CQ_VERDICT_STATES: tuple[str, ...] = (
    "pass",
    "model-recall-insufficient",
    "question-answer-review",
    "platform-runtime-incomplete",
)
# ``question-answer-review`` is a question state, not a fifth failure layer.
CQ_FAILURE_LAYERS: tuple[str, ...] = (
    "modeling-quality",
    "platform-contract",
    "collaboration/routing",
    "runtime/infrastructure",
)
# Layers that require observed runtime/model evidence (design §4.2).  A pure
# ``question-answer-review`` question and a ``pass`` keep ``failure_layer``
# empty; every other verdict state must name its layer.
CQ_REQUIRED_FAILURE_LAYERS: dict[str, tuple[str, ...]] = {
    "model-recall-insufficient": ("modeling-quality",),
    "platform-runtime-incomplete": (
        "runtime/infrastructure", "platform-contract", "collaboration/routing"
    ),
}
# Design §5 (Round 2 R4): exposure provenance stays OUTSIDE the frozen snapshot
# schema (``r3-0-011-cq-freeze/v1`` is unchanged) and lives only in the
# Runner-written ``evidence/cq-exposure.jsonl``.  A batch whose pool carries
# recorded exposure is labeled a non-blind regression on the batch report; a
# pool with no recorded exposure is labeled blind.  The label is always present
# so a report without it can be told apart from a report that was checked.
CQ_EXPOSURE_EVIDENCE = "cq-exposure"
CQ_BLIND_STATUS_BLIND = "blind"
CQ_BLIND_STATUS_NON_BLIND = "non-blind-regression"
CQ_EXAMINER_STATUSES: tuple[str, ...] = ("completed", "unanswered", "runtime-incomplete")
CQ_BATCH_PRODUCTION_STATUSES: tuple[str, ...] = ("pass",)

# Advisory coverage ranges only (requirements D4/§3.3): never a hard gate.
ADVISORY_QUESTION_COUNTS: dict[str, tuple[int, int]] = {
    "panorama": (5, 8),
    "slice": (3, 6),
    "hidden_total": (6, 10),
}

# T3 wait-window kinds (design §3.2 H1 revision / Round 4 follow-up (a)).
CQ_WAIT_WINDOW_KINDS: tuple[str, ...] = (
    "user-flow-wait",
    "cq-review-request",
    "cq-interview-wait",
    "cq-handoff-request",
    # R3.0-012 (design §4.5): the read-only acceptance interval opened by the
    # same handoff transition that closes ``cq-handoff-request``, and closed
    # when the current attempt's report is verified (or the run stops).  A
    # pending run keeps polling the outer FIFO with no LLM output, so T3 must
    # exclude this interval like every other explicit CQ wait.
    "cq-acceptance-wait",
)

# R3.0-012 (design §4.5): the read-only acceptance lifecycle recorded in the
# Runner state and events.  ``quiescing`` covers the drain window inside
# ``cq_handoff_complete``; ``acceptance_pending`` opens the acceptance wait
# window for the ``cq_semantic`` scope only; ``acceptance_complete`` ends the
# handoff period and releases the terminal report.
CQ_ACCEPTANCE_PHASES: tuple[str, ...] = (
    "quiescing",
    "acceptance_pending",
    "acceptance_complete",
)
# The host-only ``cq_acceptance_complete`` envelope is exactly these fields;
# it never carries question text, answers, query results, or a host-chosen
# path (design §4.5).
CQ_ACCEPTANCE_COMPLETE_FIELDS = frozenset(
    {
        "action",
        "run_id",
        "freeze_id",
        "freeze_digest",
        "batch_id",
        "acceptance_attempt_id",
        "report_digest",
        "cq_verdict",
    }
)
# The aggregate verdict the Runner recomputes from the digest-verified batch
# report (never taken from the envelope): full, partial, and failure reports
# all complete the handoff, so the value summarizes the report instead of
# gating the wrap-up.
CQ_ACCEPTANCE_VERDICTS: tuple[str, ...] = ("pass", "partial", "fail")

# Run-root artifact directories (design §3.4).
CQ_RUN_DIRECTORIES: tuple[str, ...] = (
    "competency-questions/private",
    "competency-questions/reviews",
    "competency-questions/public",
    "competency-questions/frozen",
    "acceptance-v3/hidden-batch",
    "acceptance-v3/reports",
)
CQ_PUBLIC_DIRECTORY = "competency-questions/public"
CQ_FREEZE_DIRECTORY = "competency-questions/frozen"


class CQContractError(ValueError):
    """A typed, recoverable competency-question contract rejection.

    Deliberately *not* a :class:`~modeling_team.contracts.TeamConfigurationError`:
    these are expected user/input errors that must return a typed rejection
    object (object, phase, reason code, retry guidance) without crossing the
    outer-input fatal boundary (design §3.2 H1 revision).
    """

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        obj: str,
        phase: str | None = None,
        retry: str,
    ) -> None:
        if reason_code not in CQ_REASON_CODES:
            raise AssertionError(f"unregistered CQ reason code: {reason_code}")
        super().__init__(message)
        self.reason_code = reason_code
        self.obj = obj
        self.phase = phase
        self.retry = retry

    @property
    def data(self) -> dict[str, Any]:
        """The typed rejection payload; never carries question/answer text."""

        return {
            "object": self.obj,
            "phase": self.phase,
            "reason_code": self.reason_code,
            "retry": self.retry,
        }


# --- canonical digests --------------------------------------------------------


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def canonical_json_digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def content_digest(payload: Any) -> str:
    """Opaque content digest used in bindings and evidence (IDs only)."""

    return canonical_json_digest(payload)


# --- small structural helpers -------------------------------------------------


def _mapping(value: Any, obj: str, reason: str, retry: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CQContractError(reason, f"{obj} must be an object", obj=obj, retry=retry)
    return value


def _text(value: Any, obj: str, field_name: str, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CQContractError(
            reason,
            f"{obj}.{field_name} must be a non-empty string",
            obj=obj,
            retry=f"set {field_name} to a non-empty string",
        )
    return value


def _positive_int(value: Any, obj: str, field_name: str, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CQContractError(
            reason,
            f"{obj}.{field_name} must be a positive integer",
            obj=obj,
            retry=f"set {field_name} to an integer >= 1",
        )
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], obj: str, reason: str) -> None:
    if set(value) != expected:
        raise CQContractError(
            reason,
            f"{obj} fields drift from schema",
            obj=obj,
            retry=f"send exactly the fields {sorted(expected)}",
        )


# --- drafts -------------------------------------------------------------------

_DRAFT_QUESTION_FIELDS = {
    "question_id",
    "scope",
    "question",
    "answer_points",
    "evidence_refs",
    "unknown",
    "proposed_visibility",
    "content_version",
}
# Runner-owned mechanical exposure fact; a CQ draft never carries it.
_EXPOSURE_FIELD = "_exposed_to"


def validate_cq_question(
    payload: Any, *, obj: str, allow_exposure: bool = False
) -> dict[str, Any]:
    """Validate one CQ draft/freeze question record (mechanical fields only)."""

    question = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the question object")
    allowed = set(_DRAFT_QUESTION_FIELDS) | ({_EXPOSURE_FIELD} if allow_exposure else set())
    if not set(_DRAFT_QUESTION_FIELDS) <= set(question) or not set(question) <= allowed:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} fields drift from schema",
            obj=obj,
            retry=f"send exactly the fields {sorted(_DRAFT_QUESTION_FIELDS)}",
        )
    _text(question["question_id"], obj, "question_id", "cq_freeze_schema_mismatch")
    _text(question["question"], obj, "question", "cq_freeze_schema_mismatch")
    scope = _mapping(question["scope"], obj, "cq_freeze_schema_mismatch", "fix scope")
    _exact_fields(scope, {"kind", "slice_ids"}, obj, "cq_freeze_schema_mismatch")
    if scope["kind"] not in CQ_SCOPE_KINDS:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.scope.kind is invalid",
            obj=obj,
            retry="set scope.kind to panorama or slice",
        )
    slice_ids = scope["slice_ids"]
    if scope["kind"] == "panorama":
        if slice_ids != []:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.scope.slice_ids must be empty for a panorama question",
                obj=obj,
                retry="set scope.slice_ids to []",
            )
    else:
        if not isinstance(slice_ids, list) or not slice_ids or any(
            not isinstance(item, str) or not item for item in slice_ids
        ):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.scope.slice_ids is invalid",
                obj=obj,
                retry="list at least one approved slice id",
            )
    for field_name in ("answer_points", "unknown"):
        values = question[field_name]
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.{field_name} must be a list of strings",
                obj=obj,
                retry=f"set {field_name} to a list of strings",
            )
    refs = question["evidence_refs"]
    if not isinstance(refs, list):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.evidence_refs must be a list",
            obj=obj,
            retry="set evidence_refs to a list",
        )
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"source", "locator"}:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.evidence_refs entries drift",
                obj=obj,
                retry="send evidence refs as {source, locator}",
            )
        _text(ref["source"], obj, "evidence_refs.source", "cq_freeze_schema_mismatch")
        _text(ref["locator"], obj, "evidence_refs.locator", "cq_freeze_schema_mismatch")
    if question["proposed_visibility"] not in CQ_VISIBILITIES:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.proposed_visibility is invalid",
            obj=obj,
            retry="set proposed_visibility to public or hidden",
        )
    _positive_int(question["content_version"], obj, "content_version", "cq_freeze_schema_mismatch")
    return dict(question)


def validate_draft_document(payload: Any) -> dict[str, Any]:
    """Validate an immutable ``cq_publish_question_draft`` capability payload."""

    obj = "cq_publish_question_draft"
    document = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the draft document")
    _exact_fields(
        document,
        {
            "schema_version",
            "phase",
            "draft_id",
            "questions",
            "superseded_draft_id",
            "note",
        },
        obj,
        "cq_freeze_schema_mismatch",
    )
    if document["schema_version"] != CQ_DRAFT_SCHEMA:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_DRAFT_SCHEMA}",
        )
    phase = _text(document["phase"], obj, "phase", "cq_freeze_schema_mismatch")
    if phase not in CQ_LIFECYCLE_PHASES:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.phase is not a lifecycle phase",
            obj=obj,
            phase=phase,
            retry=f"use one of {list(CQ_LIFECYCLE_PHASES)}",
        )
    _text(document["draft_id"], obj, "draft_id", "cq_freeze_schema_mismatch")
    questions = document["questions"]
    if not isinstance(questions, list) or not questions:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.questions must be a non-empty list",
            obj=obj,
            phase=phase,
            retry="send at least one question draft",
        )
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in questions:
        question = validate_cq_question(item, obj=f"{obj}.questions[]")
        if question["question_id"] in seen:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} duplicates question_id {question['question_id']}",
                obj=obj,
                phase=phase,
                retry="send each question_id once",
            )
        seen.add(question["question_id"])
        normalized.append(question)
    normalized_document = dict(document)
    normalized_document["questions"] = normalized
    normalized_document["content_digest"] = content_digest(
        {"draft_id": document["draft_id"], "questions": normalized}
    )
    return normalized_document


def validate_review_decision(payload: Any, *, draft: dict[str, Any]) -> dict[str, Any]:
    """Validate one ``cq_review`` decision against the current draft version.

    Owner, schema, content version and content digest must match the draft that
    produced the review snapshot; ``revision`` is only a positive reviewer
    ordinal because the snapshot has no revision field.  Stale content or
    owner bindings reject only this input (design §3.2).
    """

    obj = "cq_review"
    decision = _mapping(payload, obj, "cq_review_stale", "resend the review decision")
    _exact_fields(
        decision,
        {
            "schema_version",
            "review_id",
            "question_id",
            "decision",
            "content_version",
            "content_digest",
            "revision",
            "modified_question",
            "note",
        },
        obj,
        "cq_review_stale",
    )
    if decision["schema_version"] != CQ_REVIEW_SCHEMA:
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_REVIEW_SCHEMA}",
        )
    review_id = _text(decision["review_id"], obj, "review_id", "cq_review_stale")
    if review_id != draft.get("review_id"):
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.review_id does not match the current review snapshot",
            obj=obj,
            retry="re-read the current review snapshot and resend",
        )
    question_id = _text(decision["question_id"], obj, "question_id", "cq_review_stale")
    known = {question["question_id"] for question in draft.get("questions", [])}
    if question_id not in known and decision["decision"] != "supplement":
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.question_id {question_id} is not part of review {review_id}",
            obj=obj,
            retry="review an existing question id or use supplement",
        )
    if decision["decision"] not in CQ_REVIEW_DECISIONS:
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.decision is invalid",
            obj=obj,
            retry=f"use one of {list(CQ_REVIEW_DECISIONS)}",
        )
    version = _positive_int(decision["content_version"], obj, "content_version", "cq_review_stale")
    if version != draft.get("content_version"):
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.content_version is stale for review {review_id}",
            obj=obj,
            retry="re-read the current review snapshot and resend",
        )
    if decision["content_digest"] != draft.get("content_digest"):
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.content_digest does not match review {review_id}",
            obj=obj,
            retry="re-read the current review snapshot and resend",
        )
    # ``revision`` is retained in the review envelope for the existing wire
    # contract, but it is not a snapshot binding.  Staleness is carried by the
    # immutable content_version/content_digest pair above.
    _positive_int(decision["revision"], obj, "revision", "cq_review_stale")
    if decision["decision"] in {"modify", "supplement"}:
        replacement = decision["modified_question"]
        if replacement is None:
            raise CQContractError(
                "cq_review_stale",
                f"{obj}.modified_question is required for {decision['decision']}",
                obj=obj,
                retry="attach modified_question",
            )
        validate_cq_question(replacement, obj=f"{obj}.modified_question")
    elif decision["modified_question"] is not None:
        raise CQContractError(
            "cq_review_stale",
            f"{obj}.modified_question is only valid for modify or supplement",
            obj=obj,
            retry="set modified_question to null",
        )
    return dict(decision)


def review_decision_digest(decision: dict[str, Any]) -> str:
    return content_digest(
        {
            "review_id": decision.get("review_id"),
            "question_id": decision.get("question_id"),
            "decision": decision.get("decision"),
            "content_version": decision.get("content_version"),
            "revision": decision.get("revision"),
            "modified_question": decision.get("modified_question"),
        }
    )


def advisory_question_count_feedback(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Advisory-only coverage feedback; never a rejection (requirements D4).

    Question counts are recommendations, so the result is a list of notes the
    Host may surface; the Runner must not fail the run on any entry here.
    """

    panorama = [item for item in questions if item.get("scope", {}).get("kind") == "panorama"]
    slices: dict[str, int] = {}
    for item in questions:
        if item.get("scope", {}).get("kind") != "slice":
            continue
        for slice_id in item.get("scope", {}).get("slice_ids", []):
            slices[slice_id] = slices.get(slice_id, 0) + 1
    checks: list[tuple[str, int, tuple[int, int]]] = [
        ("panorama", len(panorama), ADVISORY_QUESTION_COUNTS["panorama"]),
        (
            "hidden_total",
            sum(1 for item in questions if item.get("visibility") == "hidden"),
            ADVISORY_QUESTION_COUNTS["hidden_total"],
        ),
    ]
    checks.extend(
        (f"slice:{slice_id}", count, ADVISORY_QUESTION_COUNTS["slice"])
        for slice_id, count in sorted(slices.items())
    )
    feedback: list[dict[str, Any]] = []
    for label, count, (low, high) in checks:
        if count < low or count > high:
            feedback.append(
                {
                    "scope": label,
                    "count": count,
                    "advisory_range": [low, high],
                    "note": "advisory coverage range",
                }
            )
    return feedback


# --- freeze, projection and exposure -----------------------------------------


def freeze_question_pool(payload: Any) -> dict[str, Any]:
    """Validate and normalize one immutable ``r3-0-011-cq-freeze/v1`` snapshot."""

    obj = "cq_freeze"
    snapshot = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the freeze snapshot")
    _exact_fields(
        snapshot,
        {
            "schema_version",
            "batch_id",
            "material_digest",
            "panorama_question_ids",
            "slice_question_ids",
            "ordering",
            "questions",
            "review_binding",
        },
        obj,
        "cq_freeze_schema_mismatch",
    )
    if snapshot["schema_version"] != CQ_FREEZE_SCHEMA:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_FREEZE_SCHEMA}",
        )
    _text(snapshot["batch_id"], obj, "batch_id", "cq_freeze_schema_mismatch")
    _text(snapshot["material_digest"], obj, "material_digest", "cq_freeze_schema_mismatch")
    binding = _mapping(
        snapshot["review_binding"], obj, "cq_freeze_schema_mismatch", "fix review_binding"
    )
    _exact_fields(
        binding,
        {"review_id", "review_content_version", "decision_digest"},
        obj,
        "cq_freeze_schema_mismatch",
    )
    _text(binding["review_id"], obj, "review_binding.review_id", "cq_freeze_schema_mismatch")
    _positive_int(
        binding["review_content_version"],
        obj,
        "review_binding.review_content_version",
        "cq_freeze_schema_mismatch",
    )
    _text(
        binding["decision_digest"], obj, "review_binding.decision_digest", "cq_freeze_schema_mismatch"
    )
    questions = snapshot["questions"]
    if not isinstance(questions, list):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.questions must be a list",
            obj=obj,
            retry="set questions to a list",
        )
    exposed_public: list[str] = []
    exposed_hidden: list[str] = []
    normalized: list[dict[str, Any]] = []
    for item in questions:
        question = validate_cq_question(item, obj=f"{obj}.questions[]", allow_exposure=True)
        visibility = question.pop("proposed_visibility")
        # ``_exposed_to`` is a Runner-owned mechanical fact: any role that ever
        # saw the question/answer makes it permanently public (design D2).
        exposed_to = question.pop(_EXPOSURE_FIELD, None)
        if exposed_to is not None:
            if not isinstance(exposed_to, list) or any(
                not isinstance(role, str) or not role for role in exposed_to
            ):
                raise CQContractError(
                    "cq_freeze_schema_mismatch",
                    f"{obj}.questions[] {_EXPOSURE_FIELD} is invalid",
                    obj=obj,
                    retry=f"set {_EXPOSURE_FIELD} to a list of role names",
                )
            if visibility == "hidden" and exposed_to:
                raise CQContractError(
                    "cq_hidden_exposed",
                    f"question {question['question_id']} was shown to a production role",
                    obj=obj,
                    phase="frozen",
                    retry="set visibility to public for every previously shown question",
                )
            visibility = "public"
        question["visibility"] = visibility
        normalized.append(question)
        if visibility == "public":
            exposed_public.append(question["question_id"])
        else:
            exposed_hidden.append(question["question_id"])
    panorama_ids = snapshot["panorama_question_ids"]
    slice_ids = snapshot["slice_question_ids"]
    ordering = snapshot["ordering"]
    for label, value in (
        ("panorama_question_ids", panorama_ids),
        ("slice_question_ids", slice_ids),
        ("ordering", ordering),
    ):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.{label} must be a list of question ids",
                obj=obj,
                retry=f"set {label} to a list of question ids",
            )
    known = {question["question_id"] for question in normalized}
    for label, value in (
        ("panorama_question_ids", panorama_ids),
        ("slice_question_ids", slice_ids),
        ("ordering", ordering),
    ):
        unknown = [item for item in value if item not in known]
        if unknown:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj}.{label} references unknown question ids",
                obj=obj,
                retry="reference only frozen question ids",
            )
    if sorted(set(panorama_ids) | set(slice_ids)) != sorted(known):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} panorama/slice sets do not close over the frozen questions",
            obj=obj,
            retry="make panorama_question_ids and slice_question_ids cover every question once",
        )
    for question in normalized:
        expected = (
            panorama_ids if question["scope"]["kind"] == "panorama" else slice_ids
        )
        if question["question_id"] not in expected:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} question {question['question_id']} is listed under the wrong scope set",
                obj=obj,
                retry="list each question in the set matching its scope.kind",
            )
    if len(set(ordering)) != len(ordering) or set(ordering) != known:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.ordering must be a permutation of the frozen question ids",
            obj=obj,
            retry="list every frozen question id exactly once",
        )
    normalized_snapshot = {
        "schema_version": CQ_FREEZE_SCHEMA,
        "batch_id": snapshot["batch_id"],
        "material_digest": snapshot["material_digest"],
        "panorama_question_ids": list(panorama_ids),
        "slice_question_ids": list(slice_ids),
        "ordering": list(ordering),
        "questions": normalized,
        "review_binding": dict(binding),
    }
    normalized_snapshot["snapshot_digest"] = content_digest(
        {key: value for key, value in normalized_snapshot.items()}
    )
    return normalized_snapshot


def reload_frozen_pool(snapshot: Any) -> dict[str, Any]:
    """Re-validate a stored freeze snapshot exactly as the Runner wrote it.

    ``freeze_question_pool`` maps a draft question onto the frozen record
    (``proposed_visibility`` becomes the Runner-owned ``visibility``), so the
    stored snapshot is not its own input.  Readers rebuild the freeze from the
    file, recompute ``snapshot_digest`` and reject a file that was edited after
    it was frozen (design §3.4 append-only artifacts).
    """

    obj = "cq_freeze"
    stored = _mapping(
        snapshot, obj, "cq_freeze_schema_mismatch", "send the stored freeze snapshot"
    )
    if "snapshot_digest" not in stored:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} carries no snapshot_digest",
            obj=obj,
            retry="read the freeze file written by the Runner",
        )
    questions = stored.get("questions")
    if not isinstance(questions, list):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.questions must be a list",
            obj=obj,
            retry="read the freeze file written by the Runner",
        )
    rebuilt_input = {key: value for key, value in stored.items() if key != "snapshot_digest"}
    rebuilt_input["questions"] = [
        {
            **{key: value for key, value in question.items() if key != "visibility"},
            "proposed_visibility": question.get("visibility"),
        }
        if isinstance(question, dict)
        else question
        for question in questions
    ]
    rebuilt = freeze_question_pool(rebuilt_input)
    if rebuilt["snapshot_digest"] != stored["snapshot_digest"]:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} snapshot_digest does not match the frozen file contents",
            obj=obj,
            retry="read the freeze file again without editing it",
        )
    return rebuilt


def read_exposure_evidence(path: Any) -> dict[str, Any]:
    """Read the Runner-written ``evidence/cq-exposure.jsonl`` provenance.

    Returns ``{"exposure": {question_id: [roles]}, "digest": <sha256:...>,
    "record_count": n}``.  A missing or empty file means no recorded exposure
    (a pool that never projected a public question, or a legacy run root) and
    is reported as an empty provenance set, never as an error.  A line that is
    not a ``question-exposed-to-production`` record is rejected instead of
    being skipped: the non-blind label must never be guessed from partial
    evidence.  The digest covers every record, including exposure of questions
    that no longer belong to this batch, so a report can prove which evidence
    it was labeled from.
    """

    obj = "cq_exposure_evidence"
    if isinstance(path, (str, Path)) and Path(path).is_file():
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    records: list[dict[str, Any]] = []
    exposure: dict[str, list[str]] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} line is not JSON",
                obj=obj,
                retry="read the cq-exposure evidence written by the Runner",
            ) from exc
        if not isinstance(record, dict):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} line is not an object",
                obj=obj,
                retry="read the cq-exposure evidence written by the Runner",
            )
        question_ids = record.get("question_ids")
        roles = record.get("roles")
        if (
            record.get("event") != "question-exposed-to-production"
            or not isinstance(question_ids, list)
            or any(not isinstance(item, str) or not item for item in question_ids)
            or not isinstance(roles, list)
            or any(not isinstance(role, str) or not role for role in roles)
        ):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} record is not a question-exposed-to-production event",
                obj=obj,
                retry="read the cq-exposure evidence written by the Runner",
            )
        records.append(record)
        for question_id in question_ids:
            known = set(exposure.setdefault(question_id, []))
            exposure[question_id] = sorted(known | set(roles))
    return {
        "exposure": exposure,
        "digest": content_digest(records),
        "record_count": len(records),
    }


def blind_batch_label(*, question_ids: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    """Label one acceptance batch as blind or as a non-blind regression.

    Design §5 (Round 2 R4): a pool whose scope contains a question that was
    ever shown to a production role can no longer be answered blind, so the
    batch report must carry ``blind_status: "non-blind-regression"`` plus the
    exposed question ids and the ``cq-exposure`` evidence digest.  A pool with
    no recorded exposure is labeled ``blind``.  The label is advisory for
    judging and mandatory on the report; it changes no verdict logic.  The v3
    batch packet keeps its exact-field blind child-input contract and carries
    no copy of the label: the host report (and attribution record) are the
    authoritative, host-only place where the non-blind fact is recorded.
    """

    exposure = evidence.get("exposure") if isinstance(evidence, dict) else None
    if not isinstance(exposure, dict):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            "cq_exposure_evidence provenance is invalid",
            obj="cq_exposure_evidence",
            retry="read the cq-exposure evidence with read_exposure_evidence",
        )
    exposed = sorted({str(item) for item in question_ids} & set(exposure))
    return {
        "blind_status": (
            CQ_BLIND_STATUS_NON_BLIND if exposed else CQ_BLIND_STATUS_BLIND
        ),
        "exposed_question_ids": exposed,
        "exposure_evidence_digest": evidence.get("digest"),
        "exposure_record_count": evidence.get("record_count", 0),
    }


def public_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project only approved public questions for the production roles.

    The projection never carries hidden question ids, text, answers, CQ
    private conversation, or unreviewed records (design §3.4 / M6).
    """

    if snapshot.get("schema_version") != CQ_FREEZE_SCHEMA:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            "public projection requires a frozen question pool",
            obj="cq_public_projection",
            retry="freeze the question pool first",
        )
    questions = [
        {
            "question_id": question["question_id"],
            "scope": dict(question["scope"]),
            "question": question["question"],
            "answer_points": list(question["answer_points"]),
            "unknown": list(question["unknown"]),
            "review_content_version": question["content_version"],
        }
        for question in snapshot.get("questions", [])
        if question.get("visibility") == "public"
    ]
    projection = {
        "schema_version": CQ_PUBLIC_PROJECTION_SCHEMA,
        "batch_id": snapshot["batch_id"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "questions": questions,
    }
    projection["projection_digest"] = content_digest(
        {key: value for key, value in projection.items()}
    )
    return projection


def write_public_projection(path: Any, projection: dict[str, Any]) -> None:
    """Append-only projection write; an existing file is never overwritten."""

    import os

    payload = canonical_json_bytes(projection)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o444)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o444)


def cross_slice_projection_issues(
    entries: Any, projection: dict[str, Any], *, slice_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Runner-side external consistency check for the scenario-map section.

    The scenario-map ``cross_slice_competency_questions`` entries keep their
    exact three-field shape (``question_id``/``question``/``spans_slices``,
    ``scenario_map.py``) — no provenance field is added (Round 4 follow-up (c)).
    This check lives Runner-side and reports:

    * an empty section as a coverage gap unless only one actual slice exists;
    * any entry whose id/text is not exactly one approved public projection
      question as a rejection, so a production role cannot mint a parallel
      question set that bypasses the "shown means public" rule.
    """

    issues: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        issues.append(
            {
                "reason_code": "cq_freeze_schema_mismatch",
                "object": "cross_slice_competency_questions",
                "note": "section must be a list",
            }
        )
        return issues
    if not entries:
        # Panorama is a question classification, not proof of cross-slice scope.
        # A single-slice map correctly leaves this section empty. Unknown scope
        # retains the existing gap feedback rather than assuming no coverage.
        if slice_ids is not None and len(set(slice_ids)) == 1:
            return issues
        issues.append(
            {
                "reason_code": "cq_public_projection_missing",
                "object": "cross_slice_competency_questions",
                "note": "cross-slice coverage gap recorded (section explicitly empty)",
                "coverage_gap": True,
            }
        )
        return issues
    approved = {
        question["question_id"]: question
        for question in projection.get("questions", [])
        if question.get("scope", {}).get("kind") == "panorama"
    }
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"question_id", "question", "spans_slices"}:
            issues.append(
                {
                    "reason_code": "cq_freeze_schema_mismatch",
                    "object": "cross_slice_competency_questions",
                    "note": "entry fields drift; the map contract stays three-field",
                }
            )
            continue
        question_id = entry.get("question_id")
        approved_question = approved.get(question_id) if isinstance(question_id, str) else None
        if approved_question is None or approved_question.get("question") != entry.get("question"):
            issues.append(
                {
                    "reason_code": "cq_public_projection_missing",
                    "object": "cross_slice_competency_questions",
                    "note": (
                        f"question_id {question_id!r} is not an approved public projection"
                        " question; rewording or new cross-slice question text is rejected"
                    ),
                }
            )
            continue
        if question_id in seen:
            issues.append(
                {
                    "reason_code": "cq_freeze_schema_mismatch",
                    "object": "cross_slice_competency_questions",
                    "note": f"question_id {question_id} is referenced twice",
                }
            )
        seen.add(question_id)
    return issues


def coverage_gaps_from_projection(projection: dict[str, Any], slices: list[str]) -> dict[str, Any]:
    """Mechanical coverage-gap inventory for the acceptance batch report."""

    panorama = [
        question
        for question in projection.get("questions", [])
        if question.get("scope", {}).get("kind") == "panorama"
    ]
    per_slice: dict[str, int] = {}
    for question in projection.get("questions", []):
        if question.get("scope", {}).get("kind") != "slice":
            continue
        for slice_id in question.get("scope", {}).get("slice_ids", []):
            per_slice[slice_id] = per_slice.get(slice_id, 0) + 1
    return {
        "empty_projection": not projection.get("questions"),
        "panorama_public_count": len(panorama),
        "slices_without_public_question": sorted(
            slice_id for slice_id in slices if per_slice.get(slice_id, 0) == 0
        ),
    }


def revised_freeze_version(
    previous: dict[str, Any], revised_questions: list[dict[str, Any]], *, batch_id: str
) -> dict[str, Any]:
    """Freeze revision: a new immutable version, never an in-place rewrite.

    The previous snapshot is returned untouched alongside the new one so old
    answers, reports, and verdicts stay read-only and attributable (design §3.3
    / D4, test R3).
    """

    normalized_questions: list[dict[str, Any]] = []
    for question in revised_questions:
        candidate = dict(question)
        visibility = candidate.pop("visibility", None) or candidate.get("proposed_visibility")
        candidate["proposed_visibility"] = visibility
        candidate.pop("visibility", None)
        normalized_questions.append(candidate)
    payload = {
        "schema_version": CQ_FREEZE_SCHEMA,
        "batch_id": batch_id,
        "material_digest": previous.get("material_digest"),
        "panorama_question_ids": [
            question["question_id"]
            for question in normalized_questions
            if question["scope"]["kind"] == "panorama"
        ],
        "slice_question_ids": [
            question["question_id"]
            for question in normalized_questions
            if question["scope"]["kind"] == "slice"
        ],
        "ordering": [question["question_id"] for question in normalized_questions],
        "questions": normalized_questions,
        "review_binding": dict(previous.get("review_binding", {})),
    }
    revised = freeze_question_pool(payload)
    if revised["snapshot_digest"] == previous.get("snapshot_digest"):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            "freeze revision did not change the snapshot",
            obj="cq_freeze",
            phase="frozen",
            retry="bump the revised question content_version",
        )
    return revised


# --- evidence bundle (Acceptance basis package) -------------------------------


def validate_evidence_bundle(payload: Any) -> dict[str, Any]:
    """Validate the frozen reference/material bundle handed to Acceptance.

    Every entry must carry readable bytes plus locator, digest and review
    version (design §4.0): a path alone is never sufficient.  Tester-only
    truth is rejected by the Task loader and never accepted here either.
    """

    obj = "acceptance_evidence_bundle"
    bundle = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the evidence bundle")
    _exact_fields(
        bundle,
        {"schema_version", "batch_id", "freeze_digest", "entries"},
        obj,
        "cq_freeze_schema_mismatch",
    )
    reference_mode = bundle["schema_version"] == CQ_EVIDENCE_REFERENCE_SCHEMA
    if bundle["schema_version"] not in {CQ_EVIDENCE_BUNDLE_SCHEMA, CQ_EVIDENCE_REFERENCE_SCHEMA}:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_EVIDENCE_BUNDLE_SCHEMA}",
        )
    entries = bundle["entries"]
    if not isinstance(entries, list):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.entries must be a list",
            obj=obj,
            retry="set entries to a list",
        )
    if not entries:
        # An empty bundle leaves Acceptance without any reference material, so
        # every remaining outcome would be a pure question/answer review.  It is
        # rejected here so a batch can never pass on an empty evidence set
        # (Round 1 informational (ii)).
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.entries is empty",
            obj=obj,
            retry="attach the approved material for every frozen question",
        )
    for entry in entries:
        item = _mapping(entry, obj, "cq_freeze_schema_mismatch", "fix evidence entry")
        _exact_fields(
            item,
            {
                "question_id",
                "source",
                "locator",
                *( {"reference_id"} if reference_mode else {"content"} ),
                "content_digest",
                "review_content_version",
            },
            obj,
            "cq_freeze_schema_mismatch",
        )
        _text(item["question_id"], obj, "question_id", "cq_freeze_schema_mismatch")
        _text(item["source"], obj, "source", "cq_freeze_schema_mismatch")
        if "tester-only" in item["source"].lower():
            raise CQContractError(
                "cq_batch_scope_unauthorized",
                f"{obj} entry references tester-only truth",
                obj=obj,
                retry="attach only approved business or interview material",
            )
        _text(item["locator"], obj, "locator", "cq_freeze_schema_mismatch")
        if reference_mode:
            identity = {key: item[key] for key in (
                "source", "locator", "content_digest", "review_content_version"
            )}
            if item["reference_id"] != content_digest(identity):
                raise CQContractError("cq_freeze_schema_mismatch", "evidence reference identity changed",
                                      obj=obj, retry="restore the frozen reference identity")
            digest = item["content_digest"]
            if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
                raise CQContractError("cq_freeze_schema_mismatch", "evidence content digest invalid",
                                      obj=obj, retry="restore the frozen content digest")
            _positive_int(item["review_content_version"], obj, "review_content_version",
                          "cq_freeze_schema_mismatch")
            continue
        content = item["content"]
        if not isinstance(content, str) or not content:
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} entry content must be readable bytes, not a bare path",
                obj=obj,
                retry="attach the material text itself",
            )
        if item["content_digest"] != content_digest(content):
            raise CQContractError(
                "cq_freeze_schema_mismatch",
                f"{obj} entry content_digest does not match content",
                obj=obj,
                retry="recompute content_digest from the attached content",
            )
        _positive_int(
            item["review_content_version"],
            obj,
            "review_content_version",
            "cq_freeze_schema_mismatch",
        )
    normalized = dict(bundle)
    normalized["bundle_digest"] = content_digest({"entries": entries})
    return normalized


def referenced_evidence_bundle(payload: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Project verified frozen bytes to a manifest and a Host-only body registry."""
    bundle = validate_evidence_bundle(payload)
    if bundle["schema_version"] != CQ_EVIDENCE_BUNDLE_SCHEMA:
        raise ValueError("reference projection requires verified inline frozen material")
    manifest = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    manifest["schema_version"] = CQ_EVIDENCE_REFERENCE_SCHEMA
    entries, registry = [], {}
    for entry in bundle["entries"]:
        projected = {key: value for key, value in entry.items() if key != "content"}
        identity = {key: projected[key] for key in (
            "source", "locator", "content_digest", "review_content_version"
        )}
        projected["reference_id"] = content_digest(identity)
        registry[projected["reference_id"]] = entry["content"]
        entries.append(projected)
    manifest["entries"] = entries
    return manifest, registry


# --- D5 model binding and batch scope ----------------------------------------


def validate_model_binding(payload: Any, *, authorized_ontology_ids: list[str]) -> dict[str, Any]:
    """Bind each explicitly listed Ontology to its authorization and state.

    Called when the acceptance batch starts (D5): the freeze never carries a
    model binding, so a missing state or an Ontology outside the authorized
    list rejects the batch start instead of silently narrowing it.
    """

    obj = "acceptance_model_binding"
    binding = _mapping(payload, obj, "cq_model_binding_missing", "bind the model state first")
    _exact_fields(
        binding,
        {
            "schema_version",
            "batch_id",
            "freeze_digest",
            "bound_at",
            "ontologies",
        },
        obj,
        "cq_model_binding_missing",
    )
    if binding["schema_version"] != "r3-0-011-model-binding/v1":
        raise CQContractError(
            "cq_model_binding_missing",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry="set schema_version to r3-0-011-model-binding/v1",
        )
    _text(binding["batch_id"], obj, "batch_id", "cq_model_binding_missing")
    _text(binding["freeze_digest"], obj, "freeze_digest", "cq_model_binding_missing")
    _text(binding["bound_at"], obj, "bound_at", "cq_model_binding_missing")
    ontologies = binding["ontologies"]
    if not isinstance(ontologies, list) or not ontologies:
        raise CQContractError(
            "cq_model_binding_missing",
            f"{obj}.ontologies must list every authorized Ontology state",
            obj=obj,
            retry="bind one state entry per authorized Ontology",
        )
    seen: set[str] = set()
    for entry in ontologies:
        item = _mapping(entry, obj, "cq_model_binding_missing", "fix ontology state entry")
        _exact_fields(
            item,
            {
                "project_id",
                "ontology_id",
                "workspace_state",
                "model_version_state",
                "authorized_read_tools",
            },
            obj,
            "cq_model_binding_missing",
        )
        ontology_id = _text(item["ontology_id"], obj, "ontology_id", "cq_batch_scope_unauthorized")
        if ontology_id not in authorized_ontology_ids:
            raise CQContractError(
                "cq_batch_scope_unauthorized",
                f"ontology {ontology_id} is not in the authorized scope",
                obj=obj,
                retry="remove the Ontology or extend the user authorization",
            )
        if ontology_id in seen:
            raise CQContractError(
                "cq_batch_scope_unauthorized",
                f"ontology {ontology_id} is bound twice",
                obj=obj,
                retry="bind each Ontology once",
            )
        seen.add(ontology_id)
        _text(item["project_id"], obj, "project_id", "cq_model_binding_missing")
        for state_field in ("workspace_state", "model_version_state"):
            state = _mapping(item[state_field], obj, "cq_model_binding_missing", "fix state entry")
            if not state.get("state_digest"):
                raise CQContractError(
                    "cq_model_binding_missing",
                    f"{obj}.{state_field}.state_digest is missing",
                    obj=obj,
                    retry="bind a non-empty state_digest",
                )
        tools = item["authorized_read_tools"]
        if not isinstance(tools, list) or not tools or any(not isinstance(t, str) for t in tools):
            raise CQContractError(
                "cq_model_binding_missing",
                f"{obj}.authorized_read_tools must be a non-empty list",
                obj=obj,
                retry="list the authorized read-only tools",
            )
    return dict(binding)


def model_binding_drift(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return the Ontology states that drifted between batch start and end."""

    def index(binding: dict[str, Any]) -> dict[str, str]:
        return {
            entry["ontology_id"]: content_digest(
                {"workspace_state": entry["workspace_state"], "model_version_state": entry["model_version_state"]}
            )
            for entry in binding.get("ontologies", [])
        }

    before_states, after_states = index(before), index(after)
    drift: list[str] = []
    for ontology_id in sorted(set(before_states) | set(after_states)):
        if before_states.get(ontology_id) != after_states.get(ontology_id):
            drift.append(ontology_id)
    return drift


# --- examiner report and acceptance verdict ----------------------------------


def validate_examiner_report(payload: Any, *, question_ids: list[str]) -> dict[str, Any]:
    """Validate one v3 Platform Examiner per-question report entry."""

    obj = "platform_examiner_report"
    report = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the report entry")
    _exact_fields(
        report,
        {
            "schema_version",
            "batch_id",
            "question_id",
            "question_content_version",
            "answer",
            "evidence_refs",
            "explicit_unknown",
            "status",
            "failure_layer",
            "reason",
        },
        obj,
        "cq_freeze_schema_mismatch",
    )
    if report["schema_version"] != CQ_BATCH_REPORT_SCHEMA:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_BATCH_REPORT_SCHEMA}",
        )
    _text(report["batch_id"], obj, "batch_id", "cq_freeze_schema_mismatch")
    question_id = _text(report["question_id"], obj, "question_id", "cq_freeze_schema_mismatch")
    if question_id not in question_ids:
        raise CQContractError(
            "cq_batch_scope_unauthorized",
            f"{obj}.question_id {question_id} is not in the frozen batch",
            obj=obj,
            retry="answer only questions from the batch packet",
        )
    _positive_int(
        report["question_content_version"],
        obj,
        "question_content_version",
        "cq_freeze_schema_mismatch",
    )
    _text(report["answer"], obj, "answer", "cq_freeze_schema_mismatch")
    refs = report["evidence_refs"]
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.evidence_refs must be a list of strings",
            obj=obj,
            retry="list the semantic evidence ids used",
        )
    if not isinstance(report["explicit_unknown"], list):
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.explicit_unknown must be a list",
            obj=obj,
            retry="list explicit unknowns (possibly empty)",
        )
    if report["status"] not in CQ_EXAMINER_STATUSES:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.status is invalid",
            obj=obj,
            retry=f"use one of {list(CQ_EXAMINER_STATUSES)}",
        )
    if report["failure_layer"] is not None and report["failure_layer"] not in CQ_FAILURE_LAYERS:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.failure_layer is invalid",
            obj=obj,
            retry=(
                "use the JSON null value or omit the field for an empty layer, "
                f"never a string such as {report['failure_layer']!r}; otherwise "
                f"one of {list(CQ_FAILURE_LAYERS)}"
            ),
        )
    return dict(report)


def validate_acceptance_verdict(payload: Any, *, question_ids: list[str]) -> dict[str, Any]:
    """Validate one independent Acceptance per-question verdict entry."""

    obj = "acceptance_verdict"
    verdict = _mapping(payload, obj, "cq_freeze_schema_mismatch", "resend the verdict entry")
    _exact_fields(
        verdict,
        {
            "schema_version",
            "batch_id",
            "question_id",
            "verdict",
            "failure_layer",
            "conflicting_evidence",
            "note",
        },
        obj,
        "cq_freeze_schema_mismatch",
    )
    if verdict["schema_version"] != CQ_BATCH_REPORT_SCHEMA:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.schema_version is invalid",
            obj=obj,
            retry=f"set schema_version to {CQ_BATCH_REPORT_SCHEMA}",
        )
    question_id = _text(verdict["question_id"], obj, "question_id", "cq_freeze_schema_mismatch")
    if question_id not in question_ids:
        raise CQContractError(
            "cq_batch_scope_unauthorized",
            f"{obj}.question_id {question_id} is not in the frozen batch",
            obj=obj,
            retry="judge only frozen batch questions",
        )
    if verdict["verdict"] not in CQ_VERDICT_STATES:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.verdict is invalid",
            obj=obj,
            retry=f"use one of {list(CQ_VERDICT_STATES)}",
        )
    layer = verdict["failure_layer"]
    if layer is not None and layer not in CQ_FAILURE_LAYERS:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj}.failure_layer is invalid",
            obj=obj,
            retry=(
                "use the JSON null value or omit the field for an empty layer "
                f"(pass/question-answer-review), never a string such as {layer!r}; "
                f"otherwise one of {list(CQ_FAILURE_LAYERS)}"
            ),
        )
    # A pure question/answer review keeps the layer empty and must not be
    # mis-attributed to modeling quality (D7 / M14).
    if verdict["verdict"] == "question-answer-review" and layer == "modeling-quality":
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            "question-answer-review must not be attributed to modeling-quality",
            obj=obj,
            retry="set failure_layer to null unless runtime/model evidence exists",
        )
    # Design §4.2: the two non-pass, non-review states must name their layer, so
    # a missing/empty layer can never be silently reported as an unattributed
    # failure (Round 1 F4).
    required = CQ_REQUIRED_FAILURE_LAYERS.get(verdict["verdict"])
    if required is not None and layer not in required:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} verdict {verdict['verdict']} requires failure_layer {list(required)}",
            obj=obj,
            retry=f"set failure_layer to one of {list(required)}",
        )
    # Design §4.2 (Round 2 informational): a layer names observed failure
    # evidence, so a pass can never carry one -- only ``pass`` and
    # ``question-answer-review`` may leave ``failure_layer`` empty.
    if verdict["verdict"] == "pass" and layer is not None:
        raise CQContractError(
            "cq_freeze_schema_mismatch",
            f"{obj} verdict pass must keep failure_layer empty",
            obj=obj,
            retry="set failure_layer to the JSON null value or omit it for a pass verdict",
        )
    return dict(verdict)


def build_batch_report(
    *,
    run_id: str,
    batch_id: str,
    freeze_digest: str,
    model_binding_digest: str,
    hidden_questions: list[dict[str, Any]],
    examiner_reports: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    executed_question_ids: list[str],
    unexecuted_question_ids: list[str],
    slices: list[str] | None = None,
    cross_slice_projection_gap: bool = False,
    model_state_drift: list[str] | None = None,
    acceptance_mode: str = CQ_ACCEPTANCE_MODE,
    blind_status: dict[str, Any] | None = None,
    platform_read_responses: dict[str, list[dict[str, Any]]] | None = None,
    evidence_recheck: dict[str, Any] | None = None,
    question_visibility: str = "hidden",
) -> dict[str, Any]:
    """Assemble the host-only v3 acceptance batch report.

    The coverage-gap block is the Round 4 follow-up (d) landing spot: an empty
    hidden set, a slice without an effective hidden question, and an
    explicitly-empty cross-slice projection section are all recorded here so a
    narrow denominator can never produce a whole-batch or whole-scenario PASS.

    ``blind_status`` is the Round 2 R4 non-blind label (design §5).  It is
    always present on the report; callers that computed it from
    ``evidence/cq-exposure.jsonl`` pass it in, and a caller that did not gets
    the conservative ``blind`` default with no provenance digest.
    """

    if question_visibility not in {"hidden", "public"}:
        raise ValueError("question_visibility must be hidden or public")
    question_ids = [report["question_id"] for report in examiner_reports]
    scope_by_question = {
        question["question_id"]: question.get("scope", {}) for question in hidden_questions
    }
    counted: dict[str, dict[str, int]] = {
        "panorama": {state: 0 for state in CQ_VERDICT_STATES},
        "slice": {state: 0 for state in CQ_VERDICT_STATES},
    }
    for verdict in verdicts:
        verdict = validate_acceptance_verdict(verdict, question_ids=question_ids)
        scope = scope_by_question.get(verdict["question_id"], {})
        bucket = "slice" if scope.get("kind") == "slice" else "panorama"
        counted[bucket][verdict["verdict"]] = counted[bucket].get(verdict["verdict"], 0) + 1
    slice_ids = sorted(
        {
            slice_id
            for question in hidden_questions
            if question.get("scope", {}).get("kind") == "slice"
            for slice_id in question.get("scope", {}).get("slice_ids", [])
        }
        | set(slices or [])
    )
    empty_hidden_set = not hidden_questions
    report = {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "run_id": run_id,
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "model_binding_digest": model_binding_digest,
        "acceptance_mode": acceptance_mode,
        "blind_status": dict(blind_status)
        if blind_status is not None
        else {
            "blind_status": CQ_BLIND_STATUS_BLIND,
            "exposed_question_ids": [],
            "exposure_evidence_digest": None,
            "exposure_record_count": 0,
        },
        "executed_question_ids": sorted(set(executed_question_ids)),
        "unexecuted_question_ids": sorted(set(unexecuted_question_ids)),
        "examiner_reports": examiner_reports,
        "verdicts": verdicts,
        "coverage_gaps": {
            "empty_hidden_set": empty_hidden_set,
            "slices_without_hidden_question": sorted(
                slice_id
                for slice_id in slice_ids
                if not any(
                    slice_id in scope_by_question.get(question_id, {}).get("slice_ids", [])
                    for question_id in sorted(
                        {*executed_question_ids, *unexecuted_question_ids}
                    )
                )
            ),
            "cross_slice_projection_gap": bool(cross_slice_projection_gap),
            "model_state_drift": sorted(model_state_drift or []),
            "notes": [
                (
                    "empty hidden set keeps an acceptance coverage gap; no batch or scenario PASS"
                    if empty_hidden_set
                    else "coverage gaps are recorded per scope"
                )
            ],
        },
        "summary_by_scope": {
            "panorama": dict(counted["panorama"]),
            "slice": dict(counted["slice"]),
        },
        "report_digest": "",
    }
    if question_visibility == "public":
        report["question_selection"] = {
            "visibility": "public",
            "question_ids": [question["question_id"] for question in hidden_questions],
        }
        report["blind_status"]["blind_status"] = CQ_BLIND_STATUS_NON_BLIND
        gaps = report["coverage_gaps"]
        gaps["empty_public_set"] = gaps.pop("empty_hidden_set")
        gaps["slices_without_public_question"] = gaps.pop("slices_without_hidden_question")
        gaps["notes"] = ["public non-blind regression coverage; hidden acceptance is separate"]
    # R3.0-012 design §4.1/§4.2: the retained-response projection and the
    # recheck record land on the report only when this attempt actually
    # produced them; a report without the fields keeps the exact 011 shape
    # and the 011 full-pass boundary.
    if platform_read_responses is not None:
        report["platform_read_responses"] = {
            str(question_id): [dict(entry) for entry in entries]
            for question_id, entries in platform_read_responses.items()
        }
    if evidence_recheck is not None:
        report["evidence_recheck"] = dict(evidence_recheck)
    report["report_digest"] = content_digest(
        {key: value for key, value in report.items() if key != "report_digest"}
    )
    return report


def batch_report_is_full_pass(report: dict[str, Any]) -> bool:
    """L1 full-PASS boundary check (mechanical part only).

    Full PASS requires a valid verdict for every batch question, no pending
    review, no insufficient recall, no unexecuted question, and no coverage
    gap.  An empty hidden set can therefore never pass.

    R3.0-012 design §4.1/§4.2 (tolerant-absent gates): on a report that carries
    the retained-response projection, a PASS verdict is only valid for a
    question with at least one host-validated platform response; on a report
    that carries the evidence recheck, every rechecked question must be
    ``stable`` -- drift or an unavailable re-read never publishes a valid
    per-question or whole-batch PASS.  Reports without the fields (all 011
    reports) keep the exact historical boundary.

    R3.0-012 design §4.3 (verdict coverage): the denominator is every hidden
    question (``executed`` plus ``unexecuted`` -- an executed service failure
    with a ``runtime-incomplete`` report stays in the executed set), and full
    PASS requires a verdict for each of them.  A partially judged batch can
    therefore never publish a whole-batch PASS even when every produced
    verdict says pass.
    """

    if report.get("schema_version") != CQ_BATCH_REPORT_SCHEMA:
        return False
    gaps = report.get("coverage_gaps", {})
    if not isinstance(gaps, dict):
        return False
    selection = report.get("question_selection")
    public = isinstance(selection, dict) and selection.get("visibility") == "public"
    empty_key = "empty_public_set" if public else "empty_hidden_set"
    slices_key = "slices_without_public_question" if public else "slices_without_hidden_question"
    if gaps.get(empty_key) or gaps.get("cross_slice_projection_gap"):
        return False
    if gaps.get(slices_key) or gaps.get("model_state_drift"):
        return False
    if report.get("unexecuted_question_ids"):
        return False
    verdicts = report.get("verdicts", [])
    if not verdicts:
        return False
    denominator = {
        str(item)
        for item in (
            report.get("executed_question_ids", []) + report.get("unexecuted_question_ids", [])
        )
        if isinstance(item, str)
    }
    judged = {
        str(verdict.get("question_id")) for verdict in verdicts if isinstance(verdict, dict)
    }
    selected_ids = selection.get("question_ids") if public else None
    if public and (
        not isinstance(selected_ids, list)
        or any(not isinstance(item, str) for item in selected_ids)
        or set(selected_ids) != denominator
        or judged != denominator
        or report.get("blind_status", {}).get("blind_status") != CQ_BLIND_STATUS_NON_BLIND
    ):
        return False
    if not denominator <= judged:
        # A hidden question without a verdict is not fully accepted, whether it
        # was never executed or its executed report was not judgeable.
        return False
    responses = report.get("platform_read_responses")
    if responses is not None:
        if not isinstance(responses, dict):
            return False
        for verdict in verdicts:
            if verdict.get("verdict") != "pass":
                continue
            entries = responses.get(str(verdict.get("question_id")))
            if not isinstance(entries, list) or not entries:
                return False
    recheck = report.get("evidence_recheck")
    if recheck is not None:
        if not isinstance(recheck, dict):
            return False
        statuses = recheck.get("question_status")
        if not isinstance(statuses, dict):
            return False
        if any(status != "stable" for status in statuses.values()):
            return False
    return all(verdict.get("verdict") == "pass" for verdict in verdicts)


def batch_report_acceptance_verdict(report: dict[str, Any]) -> str:
    """Recompute the completion-envelope aggregate verdict from the report.

    The Runner recomputes this from the digest-verified ``batch-report.json``
    and never trusts the envelope's copy (design §4.5): ``pass`` is exactly
    the :func:`batch_report_is_full_pass` boundary, ``fail`` means nothing was
    judged (an attempt that produced no verdict records), and every other
    judged-but-not-full report is ``partial``.  All three values complete the
    acceptance lifecycle the same way -- a normal wrap-up never requires CQ to
    be all green.
    """

    verdicts = report.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return "fail"
    return "pass" if batch_report_is_full_pass(report) else "partial"


def acceptance_mode_evidence(*, batch_id: str, freeze_digest: str) -> dict[str, Any]:
    """Authorization-ledger attribution record for read-only acceptance calls.

    Round 4 follow-up (e): the acceptance batch's LLM calls are attributed as
    ``read-only-acceptance``.  This record is written to run evidence only; the
    StartLedger is never written and no fresh semantic start is consumed.
    """

    return {
        "event": "acceptance-batch-llm-attribution",
        "acceptance_mode": CQ_ACCEPTANCE_MODE,
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "start_ledger_write": False,
        "consumes_semantic_start": False,
    }


# --- T3 wait-window accounting ------------------------------------------------


@dataclass
class CQWaitWindowTracker:
    """Runner-owned CQ wait intervals excluded from the T3 active clock.

    Windows are recorded as ``[started, closed)`` monotonic intervals per kind
    and merged with interval-union dedup so overlapping review/interview/handoff
    windows are never double-counted (Round 4 follow-up (a)).  Closing a window
    only defers the active clock; it never erases time already accumulated for
    a real stall, and no ``_latch_formal_candidate_failure`` call site is added.
    """

    _open: dict[str, float] = field(default_factory=dict)
    _intervals: list[tuple[float, float]] = field(default_factory=list)

    def open_window(self, kind: str, now: float) -> None:
        if kind not in CQ_WAIT_WINDOW_KINDS:
            raise AssertionError(f"unknown CQ wait window kind: {kind}")
        if kind in self._open:
            return
        self._open[kind] = now

    def close_window(self, kind: str, now: float) -> None:
        started = self._open.pop(kind, None)
        if started is None:
            return
        self._intervals.append((started, max(started, now)))

    def close_all(self, now: float) -> None:
        for kind in sorted(self._open):
            self.close_window(kind, now)

    @property
    def has_open_window(self) -> bool:
        return bool(self._open)

    def open_kinds(self) -> list[str]:
        return sorted(self._open)

    @staticmethod
    def _union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        merged: list[tuple[float, float]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def elapsed(self, now: float) -> float:
        """Total excluded time, including windows still open at ``now``."""

        intervals = list(self._intervals)
        intervals.extend((started, max(started, now)) for started in self._open.values())
        return sum(end - start for start, end in self._union(intervals))

    def intervals(self) -> list[dict[str, float]]:
        return [
            {"started": start, "closed": end, "duration": end - start}
            for start, end in self._union(list(self._intervals))
        ]

    def evidence(self, now: float) -> dict[str, Any]:
        return {
            "open_windows": self.open_kinds(),
            "merged_windows": self.intervals(),
            "excluded_seconds": self.elapsed(now),
        }
