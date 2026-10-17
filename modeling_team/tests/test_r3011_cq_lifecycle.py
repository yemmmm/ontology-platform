"""R3.0-011 competency-question lifecycle fixtures (M5, M6, M8, M9, M16, R2, R3).

Pure mechanical validation: no Agent, no platform, no LLM.  Expected reason
codes are written independently from the design's narrow list.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from modeling_team.competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
    CQ_DRAFT_SCHEMA,
    CQ_FREEZE_SCHEMA,
    CQ_PUBLIC_PROJECTION_SCHEMA,
    CQ_REVIEW_SCHEMA,
    CQContractError,
    advisory_question_count_feedback,
    content_digest,
    coverage_gaps_from_projection,
    cross_slice_projection_issues,
    freeze_question_pool,
    public_projection,
    reload_frozen_pool,
    revised_freeze_version,
    review_decision_digest,
    validate_draft_document,
    validate_review_decision,
    write_public_projection,
)

QUESTION_ID = "cq-panorama-0001"
SLICE_ID = "slice-0001"


def _question(**overrides) -> dict:
    question = {
        "question_id": QUESTION_ID,
        "scope": {"kind": "panorama", "slice_ids": []},
        "question": "placeholder panorama question?",
        "answer_points": ["point one", "point two"],
        "evidence_refs": [{"source": "scenario-brief", "locator": "section 2"}],
        "unknown": [],
        "proposed_visibility": "public",
        "content_version": 1,
    }
    question.update(overrides)
    return question


def _draft(questions: list[dict] | None = None, phase: str = "panorama-draft") -> dict:
    return {
        "schema_version": CQ_DRAFT_SCHEMA,
        "phase": phase,
        "draft_id": "cq-draft-0001",
        "questions": [_question()] if questions is None else questions,
        "superseded_draft_id": None,
        "note": "fixture draft",
    }


def _review(draft: dict | None = None, **overrides) -> dict:
    draft = draft or {}
    payload = {
        "schema_version": CQ_REVIEW_SCHEMA,
        "review_id": draft.get("review_id", "cq-review-0001"),
        "question_id": QUESTION_ID,
        "decision": "approve",
        "content_version": draft.get("content_version", 1),
        "content_digest": draft.get("content_digest", "sha256:" + "0" * 64),
        "revision": 1,
        "modified_question": None,
        "note": "fixture decision",
    }
    payload.update(overrides)
    return payload


def _freeze(questions: list[dict] | None = None) -> dict:
    items = [_question()] if questions is None else questions
    return {
        "schema_version": CQ_FREEZE_SCHEMA,
        "batch_id": "batch-r3011",
        "material_digest": "material-r3011",
        "panorama_question_ids": [item["question_id"] for item in items],
        "slice_question_ids": [],
        "ordering": [item["question_id"] for item in items],
        "review_binding": {
            "review_id": "cq-review-0001",
            "review_content_version": 1,
            "decision_digest": review_decision_digest(_review()),
        },
        "questions": items,
    }


# --- M5: the draft capability payload ----------------------------------------


def test_m5_draft_document_fields_and_digest_are_mechanical():
    normalized = validate_draft_document(_draft())
    assert set(normalized) == {
        "schema_version",
        "phase",
        "draft_id",
        "questions",
        "superseded_draft_id",
        "note",
        "content_digest",
    }
    assert normalized["content_digest"] == content_digest(
        {"draft_id": "cq-draft-0001", "questions": normalized["questions"]}
    )


def test_m5_draft_rejects_an_extra_field_and_a_bad_visibility():
    document = _draft()
    document["provenance"] = "x"
    with pytest.raises(CQContractError) as error:
        validate_draft_document(document)
    assert error.value.data["reason_code"] == "cq_freeze_schema_mismatch"
    with pytest.raises(CQContractError):
        validate_draft_document(_draft(questions=[_question(proposed_visibility="secret")]))


def test_m5_draft_rejects_a_runner_owned_exposure_field():
    document = _draft(questions=[_question(_exposed_to=["coordinator"])])
    with pytest.raises(CQContractError):
        validate_draft_document(document)


# --- M7/R2: review decisions -------------------------------------------------


def test_m7_review_accepts_every_decision_shape():
    draft = validate_draft_document(_draft())
    draft["review_id"] = "cq-review-0001"
    draft["content_version"] = 1
    for decision in ("approve", "delete"):
        decision_payload = _review(draft, decision=decision)
        assert validate_review_decision(decision_payload, draft=draft)["decision"] == decision
    modified = _review(draft, decision="modify", modified_question=_question())
    assert validate_review_decision(modified, draft=draft)["decision"] == "modify"
    supplement = _review(
        draft,
        decision="supplement",
        question_id="cq-supplement-0001",
        modified_question=_question(question_id="cq-supplement-0001"),
    )
    assert validate_review_decision(supplement, draft=draft)["question_id"] == "cq-supplement-0001"


def test_m7_stale_revision_digest_or_owner_rejects_only_this_input():
    draft = validate_draft_document(_draft())
    draft.update(review_id="cq-review-0001", content_version=1)
    for mutation in (
        {"review_id": "cq-review-0002"},
        {"content_version": 2},
        {"content_digest": "sha256:" + "1" * 64},
        {"decision": "postpone"},
    ):
        with pytest.raises(CQContractError) as error:
            validate_review_decision(_review(draft, **mutation), draft=draft)
        assert error.value.data["reason_code"] == "cq_review_stale"
        assert set(error.value.data) == {"object", "phase", "reason_code", "retry"}


# --- M6: public projection and the scenario-map rule -------------------------


def test_m6_projection_carries_only_approved_public_questions():
    frozen = freeze_question_pool(
        _freeze([_question(), _question(question_id="cq-hidden-0001", proposed_visibility="hidden")])
    )
    projection = public_projection(frozen)
    assert projection["schema_version"] == CQ_PUBLIC_PROJECTION_SCHEMA
    ids = [question["question_id"] for question in projection["questions"]]
    assert ids == [QUESTION_ID]
    text = json.dumps(projection)
    assert "cq-hidden-0001" not in text
    assert set(projection["questions"][0]) == {
        "question_id",
        "scope",
        "question",
        "answer_points",
        "unknown",
        "review_content_version",
    }


def test_m6_projection_write_is_append_only(tmp_path):
    frozen = freeze_question_pool(_freeze())
    projection = public_projection(frozen)
    path = tmp_path / "public-projection-0001.json"
    write_public_projection(path, projection)
    with pytest.raises(FileExistsError):
        write_public_projection(path, projection)
    assert json.loads(path.read_text(encoding="utf-8"))["projection_digest"]
    assert path.stat().st_mode & 0o222 == 0


def test_m6_scenario_map_keeps_three_fields_and_rejects_new_question_text():
    frozen = freeze_question_pool(_freeze())
    projection = public_projection(frozen)
    good = [
        {
            "question_id": QUESTION_ID,
            "question": "placeholder panorama question?",
            "spans_slices": [SLICE_ID],
        }
    ]
    assert cross_slice_projection_issues(good, projection) == []
    empty = cross_slice_projection_issues([], projection)
    assert empty[0]["reason_code"] == "cq_public_projection_missing"
    assert empty[0]["coverage_gap"] is True
    minted = cross_slice_projection_issues(
        [{"question_id": "cq-new", "question": "new text", "spans_slices": []}], projection
    )
    assert minted[0]["reason_code"] == "cq_public_projection_missing"
    provenance = cross_slice_projection_issues(
        [{
            "question_id": QUESTION_ID,
            "question": "placeholder panorama question?",
            "spans_slices": [SLICE_ID],
            "provenance": "projection-0001",
        }],
        projection,
    )
    assert provenance[0]["reason_code"] == "cq_freeze_schema_mismatch"


def test_cross_slice_empty_section_respects_actual_slice_scope():
    projection = public_projection(freeze_question_pool(_freeze()))
    assert cross_slice_projection_issues([], projection, slice_ids=[SLICE_ID]) == []
    assert cross_slice_projection_issues([], projection, slice_ids=[SLICE_ID, SLICE_ID]) == []
    issues = cross_slice_projection_issues([], projection, slice_ids=[SLICE_ID, "second"])
    assert issues[0]["coverage_gap"] is True
    # A single slice does not waive question identity or text checks.
    minted = [{"question_id": "new", "question": "invented", "spans_slices": [SLICE_ID]}]
    assert cross_slice_projection_issues(minted, projection, slice_ids=[SLICE_ID])


# --- M8/I5: shown means permanently public -----------------------------------


def test_m8_a_question_shown_to_a_production_role_can_never_return_to_hidden():
    exposed = _question(proposed_visibility="hidden", _exposed_to=["coordinator"])
    with pytest.raises(CQContractError) as error:
        freeze_question_pool(_freeze([exposed]))
    assert error.value.data["reason_code"] == "cq_hidden_exposed"
    assert error.value.data["phase"] == "frozen"


def test_m8_an_unexposed_hidden_question_stays_hidden():
    frozen = freeze_question_pool(_freeze([_question(proposed_visibility="hidden")]))
    assert frozen["questions"][0]["visibility"] == "hidden"


# --- M9/R3: freeze closure and append-only revisions -------------------------


def test_m9_freeze_closes_over_ids_and_digests_the_snapshot():
    frozen = freeze_question_pool(_freeze())
    assert set(frozen) == {
        "schema_version",
        "batch_id",
        "material_digest",
        "panorama_question_ids",
        "slice_question_ids",
        "ordering",
        "questions",
        "review_binding",
        "snapshot_digest",
    }
    assert set(frozen["review_binding"]) == {
        "review_id",
        "review_content_version",
        "decision_digest",
    }
    broken = _freeze()
    broken["ordering"] = ["missing-id"]
    with pytest.raises(CQContractError) as error:
        freeze_question_pool(broken)
    assert error.value.data["reason_code"] == "cq_freeze_schema_mismatch"


def test_m9_freeze_rejects_an_unclosed_scope_split():
    snapshot = _freeze([_question(scope={"kind": "slice", "slice_ids": [SLICE_ID]})])
    snapshot["slice_question_ids"] = []
    with pytest.raises(CQContractError):
        freeze_question_pool(snapshot)


def test_r3_revised_freeze_keeps_a_new_version_and_the_previous_snapshot():
    frozen = freeze_question_pool(_freeze())
    replacement = _question(content_version=2)
    revised = revised_freeze_version(
        frozen,
        revised_questions=[replacement],
        batch_id=frozen["batch_id"],
    )
    assert revised["snapshot_digest"] != frozen["snapshot_digest"]
    assert revised["questions"][0]["content_version"] == 2
    assert frozen["snapshot_digest"]  # the previous snapshot is unchanged
    assert frozen["questions"][0]["content_version"] == 1
    with pytest.raises(CQContractError) as error:
        revised_freeze_version(frozen, revised_questions=[_question()], batch_id=frozen["batch_id"])
    assert error.value.data["reason_code"] == "cq_freeze_schema_mismatch"


# --- M16: coverage gaps ------------------------------------------------------


def test_m16_coverage_gaps_are_recorded_for_empty_and_partial_projections():
    gaps = coverage_gaps_from_projection(
        public_projection(freeze_question_pool(_freeze())), ["slice-0001"]
    )
    assert gaps["slices_without_public_question"] == ["slice-0001"]
    empty = coverage_gaps_from_projection(
        {"schema_version": CQ_PUBLIC_PROJECTION_SCHEMA, "questions": []}, []
    )
    assert empty["empty_projection"] is True


def test_m10_advisory_counts_are_returned_but_never_gate_the_freeze():
    feedback = advisory_question_count_feedback(
        [
            _question(),
            _question(question_id="cq-2", proposed_visibility="hidden"),
        ]
    )
    assert feedback  # 2 hidden questions is below the advisory range
    assert all(entry["note"] == "advisory coverage range" for entry in feedback)


def test_m14_batch_report_schema_constant_is_versioned():
    assert CQ_BATCH_REPORT_SCHEMA == "r3-0-011-acceptance-batch-report/v1"


# --- M12: a stored freeze snapshot reloads and rejects edits ------------------


def test_m12_a_stored_freeze_snapshot_reloads_with_the_same_digest():
    frozen = freeze_question_pool(_freeze())
    reloaded = reload_frozen_pool(json.loads(json.dumps(frozen)))
    assert reloaded["snapshot_digest"] == frozen["snapshot_digest"]
    assert reloaded["questions"][0]["visibility"] == frozen["questions"][0]["visibility"]
    # The stored snapshot is not a valid freeze input: the two entry points stay
    # distinct.
    with pytest.raises(CQContractError):
        freeze_question_pool(frozen)


def test_m12_an_edited_freeze_file_no_longer_matches_its_digest():
    frozen = freeze_question_pool(_freeze())
    stored = json.loads(json.dumps(frozen))
    stored["questions"][0]["question"] = "edited after the freeze?"
    with pytest.raises(CQContractError) as error:
        reload_frozen_pool(stored)
    assert error.value.data["reason_code"] == "cq_freeze_schema_mismatch"
