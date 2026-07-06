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

    assert result["missing_fields"][:3] == ["scope", "core_concepts", "identity_rules"]
    assert [item["field"] for item in result["clarification_items"]] == [
        "scope",
        "core_concepts",
        "identity_rules",
    ]
    assert result["completeness"] == pytest.approx(2 / 10, abs=0.001)


def test_confirmed_and_skipped_fields_are_not_reasked() -> None:
    content = {key: f"value-{key}" for key in interview.REQUIRED_FIELDS}
    states = {key: "confirmed" for key in interview.REQUIRED_FIELDS}
    states.update({key: "skipped" for key in interview.BRIEF_FIELDS[len(interview.REQUIRED_FIELDS):]})

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


def _graph_session(count: int) -> MagicMock:
    driver = MagicMock()
    graph_session = MagicMock()
    graph_session.run.return_value.single.return_value = {"count": count}
    driver.session.return_value.__enter__.return_value = graph_session
    return driver


def test_run_question_validation_passes_when_count_meets_threshold() -> None:
    session = MagicMock()
    driver = _graph_session(3)
    item = question(
        status="testable",
        query_definition={"kind": "entity_count", "class_id": "c1", "min_count": 1},
    )
    session.get.return_value = item

    result = interview.run_question_validation(session, driver, item.id)

    assert item.status == "passed"
    assert result["passed"] is True
    assert result["matches"] == 3
    session.commit.assert_called_once()


def test_run_question_validation_fails_below_threshold() -> None:
    session = MagicMock()
    driver = _graph_session(2)
    item = question(
        status="testable",
        query_definition={"kind": "entity_count", "class_id": "c1", "min_count": 5},
    )
    session.get.return_value = item

    result = interview.run_question_validation(session, driver, item.id)

    assert item.status == "failed"
    assert result["passed"] is False


def test_run_question_validation_rejects_unsupported_definition() -> None:
    session = MagicMock()
    item = question(status="testable", query_definition={"kind": "unknown"})
    session.get.return_value = item

    with pytest.raises(HTTPException, match="Unsupported query definition"):
        interview.run_question_validation(session, MagicMock(), item.id)


def test_run_question_validation_rejects_non_testable_status() -> None:
    session = MagicMock()
    item = question(status="draft", query_definition={"kind": "entity_count", "class_id": "c1"})
    session.get.return_value = item

    with pytest.raises(HTTPException, match="Only testable"):
        interview.run_question_validation(session, MagicMock(), item.id)


def test_run_question_validation_relation_count_uses_relation_type_filter() -> None:
    session = MagicMock()
    driver = _graph_session(7)
    item = question(
        status="testable",
        query_definition={"kind": "relation_count", "relation_type_id": "rt1", "min_count": 5},
    )
    session.get.return_value = item

    result = interview.run_question_validation(session, driver, item.id)

    assert result["passed"] is True
    assert result["matches"] == 7


def test_active_data_and_ontology_graphs_for_question_returns_member_iris(
    in_memory_session,
):
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
        SemanticGraphSetMemberModel,
        SemanticGraphSetModel,
    )
    from app.services.interview import active_data_and_ontology_graphs_for_question

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.flush()
    in_memory_session.add(CompetencyQuestionModel(
        id="q-1", project_id="p-1", ontology_id="o-1",
        question="q", position=0, status="testable",
        query_definition={}, source_brief_fields=[],
    ))
    in_memory_session.add(SemanticGraphSetModel(
        id="gs-1", name="GS", scope_type="ontology", scope_id="o-1",
        status="active",
    ))
    in_memory_session.flush()
    for role, iri in [
        ("asserted_ontology", "https://x/graph/ontology/o-1"),
        ("asserted_data", "https://x/graph/data/o-1"),
    ]:
        in_memory_session.add(SemanticGraphSetMemberModel(
            id=f"m-{role}", graph_set_id="gs-1", graph_iri=iri, role=role,
        ))
    in_memory_session.commit()

    iris = active_data_and_ontology_graphs_for_question(in_memory_session, "q-1")
    assert "https://x/graph/ontology/o-1" in iris
    assert "https://x/graph/data/o-1" in iris
    assert len(iris) == 2


def test_resolve_class_iri_returns_phase2_mapping_or_fallback(in_memory_session):
    from app.repositories.models import OntologyModel, ProjectModel
    from app.services.interview import resolve_class_iri

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.commit()

    iri = resolve_class_iri(in_memory_session, "o-1", "class-1")
    assert "class-1" in iri or "class_1" in iri
    assert iri.startswith("http://ontology-platform.local/semantic/")


def test_resolve_relation_type_iri_returns_phase2_mapping_or_fallback(in_memory_session):
    from app.repositories.models import OntologyModel, ProjectModel
    from app.services.interview import resolve_relation_type_iri

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.commit()

    iri = resolve_relation_type_iri(in_memory_session, "o-1", "rt-1")
    assert "rt-1" in iri or "rt_1" in iri
    assert iri.startswith("http://ontology-platform.local/semantic/")
