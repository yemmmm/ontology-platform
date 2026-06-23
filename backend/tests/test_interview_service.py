from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.schemas import CompetencyQuestionStatusUpdate
from app.repositories.models import CompetencyQuestionModel
from app.services import interview


def question(status: str = "draft", **overrides) -> CompetencyQuestionModel:
    values = {
        "id": "question-1",
        "project_id": "project-1",
        "ontology_id": "ontology-1",
        "question": "Which suppliers provide each component?",
        "importance": 5,
        "position": 0,
        "status": status,
        "active": True,
        "query_definition": {},
        "validation_result": {},
        "source_answer_ids": ["answer-1"],
        "source_brief_fields": [],
    }
    values.update(overrides)
    return CompetencyQuestionModel(**values)


def test_brief_assessment_prioritizes_required_missing_fields() -> None:
    result = interview.assess_brief(
        {"domain_name": "Supply chain", "business_goal": "Trace disruptions"},
        {"domain_name": "confirmed", "business_goal": "confirmed"},
        {"domain_name": ["answer-1"], "business_goal": ["answer-1"]},
    )

    assert result["missing_fields"][:3] == ["scope", "core_concepts", "expected_granularity"]
    assert [item["field"] for item in result["clarification_items"]] == [
        "scope",
        "core_concepts",
        "expected_granularity",
    ]
    assert result["completeness"] == pytest.approx(2 / 9, abs=0.001)


def test_confirmed_and_skipped_fields_are_not_reasked() -> None:
    content = {key: f"value-{key}" for key in interview.REQUIRED_FIELDS}
    states = {key: "confirmed" for key in interview.REQUIRED_FIELDS}
    states.update({key: "skipped" for key in interview.BRIEF_FIELDS[5:]})

    result = interview.assess_brief(content, states, {})

    assert result["missing_fields"] == []
    assert result["completeness"] == 1.0
    assert all(item["question"] == "Skipped" for item in result["clarification_items"])
    assert "confidence" in result["clarification_items"][0]["reason"].lower()


def test_question_status_transitions_through_all_validation_states() -> None:
    session = MagicMock()
    item = question()
    session.get.return_value = item

    interview.set_question_status(
        session, item.id, CompetencyQuestionStatusUpdate(status="approved")
    )
    item.query_definition = {"kind": "graph_pattern", "pattern": "Supplier -> Component"}
    interview.set_question_status(
        session, item.id, CompetencyQuestionStatusUpdate(status="testable")
    )
    interview.set_question_status(
        session,
        item.id,
        CompetencyQuestionStatusUpdate(status="passed", validation_result={"matches": 4}),
    )

    assert item.status == "passed"
    assert item.validation_result == {"matches": 4}
    assert session.commit.call_count == 3


def test_approval_requires_traceable_source() -> None:
    session = MagicMock()
    item = question(source_answer_ids=[], source_brief_fields=[])
    session.get.return_value = item

    with pytest.raises(HTTPException, match="require an answer or Project Brief source"):
        interview.set_question_status(
            session, item.id, CompetencyQuestionStatusUpdate(status="approved")
        )


def test_testing_requires_structured_query_definition() -> None:
    session = MagicMock()
    item = question(status="approved")
    session.get.return_value = item

    with pytest.raises(HTTPException, match="query definition"):
        interview.set_question_status(
            session, item.id, CompetencyQuestionStatusUpdate(status="testable")
        )


def test_invalid_question_transition_is_rejected() -> None:
    session = MagicMock()
    item = question()
    session.get.return_value = item

    with pytest.raises(HTTPException, match="draft -> passed"):
        interview.set_question_status(
            session,
            item.id,
            CompetencyQuestionStatusUpdate(status="passed", validation_result={"matches": 0}),
        )


def test_brief_change_marks_related_validated_question_stale() -> None:
    related = question(
        status="passed",
        source_brief_fields=["business_goal"],
        validation_result={"matches": 4},
    )
    unrelated = question(
        status="passed",
        source_brief_fields=["scope"],
        validation_result={"matches": 2},
    )

    interview.invalidate_questions_for_brief_change(
        [related, unrelated], {"business_goal"}
    )

    assert related.status == "approved"
    assert related.validation_result == {
        "matches": 4,
        "stale": True,
        "reason": "source_project_brief_changed",
        "changed_fields": ["business_goal"],
    }
    assert unrelated.status == "passed"


def test_graph_change_marks_validated_questions_stale() -> None:
    passed = question(status="passed", validation_result={"matches": 3})
    draft = question(status="draft")
    testable_no_result = question(status="testable", validation_result={})

    affected = interview.invalidate_questions_for_graph_change(
        [passed, draft, testable_no_result], changed_entity_ids={"e1"}
    )

    assert affected == 1
    assert passed.status == "testable"
    assert passed.validation_result["stale"] is True
    assert passed.validation_result["reason"] == "graph_data_changed"
    assert passed.validation_result["changed_entity_ids"] == ["e1"]
    assert draft.status == "draft"
    assert testable_no_result.status == "testable"


def test_graph_change_invalidation_noops_without_changes() -> None:
    passed = question(status="passed", validation_result={"matches": 3})

    affected = interview.invalidate_questions_for_graph_change([passed], changed_entity_ids=set())

    assert affected == 0
    assert passed.status == "passed"
