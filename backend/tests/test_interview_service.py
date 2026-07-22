import os
import uuid
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
    states.update(
        {key: "skipped" for key in interview.BRIEF_FIELDS[len(interview.REQUIRED_FIELDS) :]}
    )

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

    interview.invalidate_questions_for_brief_change([related, unrelated], {"business_goal"})

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


class _FakeSparqlStore:
    """Minimal fake RDF store that returns a SPARQL JSON result with a count binding."""

    def __init__(self, count: int):
        self.count = count

    def query_sparql(self, query, timeout_seconds, limit):
        class _R:
            result_format = "application/sparql-results+json"

        r = _R()
        r.result = {"results": {"bindings": [{"count": {"value": str(self.count)}}]}}
        return r


class _FakeSettings:
    competency_question_sparql_timeout_seconds = 5.0


def test_run_question_validation_passes_when_count_meets_threshold(monkeypatch) -> None:
    session = MagicMock()
    item = question(
        status="testable",
        query_definition={"kind": "entity_count", "class_id": "c1", "min_count": 1},
    )
    session.get.return_value = item
    monkeypatch.setattr(
        interview,
        "active_data_and_ontology_graphs_for_question",
        lambda s, qid: ["https://x/g/data"],
    )
    monkeypatch.setattr(
        interview, "resolve_class_iri", lambda s, oid, cid: f"https://x/ont/{oid}/class/{cid}"
    )

    result = interview.run_question_validation(
        session, _FakeSparqlStore(3), item.id, _FakeSettings()
    )

    assert item.status == "passed"
    assert result["status"] == "passed"
    assert result["validation_result"]["matches"] == 3
    session.commit.assert_called()


def test_run_question_validation_fails_below_threshold(monkeypatch) -> None:
    session = MagicMock()
    item = question(
        status="testable",
        query_definition={"kind": "entity_count", "class_id": "c1", "min_count": 5},
    )
    session.get.return_value = item
    monkeypatch.setattr(
        interview,
        "active_data_and_ontology_graphs_for_question",
        lambda s, qid: ["https://x/g/data"],
    )
    monkeypatch.setattr(
        interview, "resolve_class_iri", lambda s, oid, cid: f"https://x/ont/{oid}/class/{cid}"
    )

    result = interview.run_question_validation(
        session, _FakeSparqlStore(2), item.id, _FakeSettings()
    )

    assert item.status == "failed"
    assert result["status"] == "failed"


def test_run_question_validation_rejects_unsupported_definition(monkeypatch) -> None:
    session = MagicMock()
    item = question(status="testable", query_definition={"kind": "unknown"})
    session.get.return_value = item
    monkeypatch.setattr(
        interview,
        "active_data_and_ontology_graphs_for_question",
        lambda s, qid: ["https://x/g/data"],
    )

    with pytest.raises(HTTPException, match="Unsupported query definition"):
        interview.run_question_validation(session, _FakeSparqlStore(0), item.id, _FakeSettings())


def test_run_question_validation_rejects_non_testable_status() -> None:
    session = MagicMock()
    item = question(status="draft", query_definition={"kind": "entity_count", "class_id": "c1"})
    session.get.return_value = item

    with pytest.raises(HTTPException, match="Only testable"):
        interview.run_question_validation(session, _FakeSparqlStore(0), item.id, _FakeSettings())


def test_run_question_validation_relation_count_uses_relation_type_filter(monkeypatch) -> None:
    session = MagicMock()
    item = question(
        status="testable",
        query_definition={"kind": "relation_count", "relation_type_id": "rt1", "min_count": 5},
    )
    session.get.return_value = item
    monkeypatch.setattr(
        interview,
        "active_data_and_ontology_graphs_for_question",
        lambda s, qid: ["https://x/g/data"],
    )
    monkeypatch.setattr(
        interview,
        "resolve_relation_type_iri",
        lambda s, oid, rid: f"https://x/ont/{oid}/relation/{rid}",
    )

    result = interview.run_question_validation(
        session, _FakeSparqlStore(7), item.id, _FakeSettings()
    )

    assert result["status"] == "passed"
    assert result["validation_result"]["matches"] == 7


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
    in_memory_session.add(
        CompetencyQuestionModel(
            id="q-1",
            project_id="p-1",
            ontology_id="o-1",
            question="q",
            position=0,
            status="testable",
            query_definition={},
            source_brief_fields=[],
        )
    )
    in_memory_session.add(
        SemanticGraphSetModel(
            id="gs-1",
            name="GS",
            scope_type="ontology",
            scope_id="o-1",
            status="active",
        )
    )
    in_memory_session.flush()
    for role, iri in [
        ("asserted_ontology", "https://x/graph/ontology/o-1"),
        ("asserted_data", "https://x/graph/data/o-1"),
    ]:
        in_memory_session.add(
            SemanticGraphSetMemberModel(
                id=f"m-{role}",
                graph_set_id="gs-1",
                graph_iri=iri,
                role=role,
            )
        )
    in_memory_session.commit()

    iris = active_data_and_ontology_graphs_for_question(in_memory_session, "q-1")
    assert "https://x/graph/ontology/o-1" in iris
    assert "https://x/graph/data/o-1" in iris
    assert len(iris) == 2


def test_resolve_class_iri_returns_canonical_fallback(in_memory_session):
    from app.repositories.models import OntologyModel, ProjectModel
    from app.services.interview import resolve_class_iri

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.commit()

    assert (
        resolve_class_iri(in_memory_session, "o-1", "class-1")
        == "http://ontology-platform.local/semantic/class/class-1"
    )


def test_resolve_relation_type_iri_returns_canonical_fallback(in_memory_session):
    from app.repositories.models import OntologyModel, ProjectModel
    from app.services.interview import resolve_relation_type_iri

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.commit()

    assert (
        resolve_relation_type_iri(in_memory_session, "o-1", "rt-1")
        == "http://ontology-platform.local/semantic/relation-type/rt-1"
    )


def test_resolve_iris_preserve_phase2_mapping_precedence(in_memory_session, monkeypatch):
    from app.services import semantic_phase2_mapping

    monkeypatch.setattr(
        semantic_phase2_mapping,
        "lookup_class_iri",
        lambda _session, _ontology_id, _class_id: "https://mapped.test/class",
    )
    monkeypatch.setattr(
        semantic_phase2_mapping,
        "lookup_relation_type_iri",
        lambda _session, _ontology_id, _relation_type_id: "https://mapped.test/relation",
    )

    assert (
        interview.resolve_class_iri(in_memory_session, "o-1", "class id")
        == "https://mapped.test/class"
    )
    assert (
        interview.resolve_relation_type_iri(in_memory_session, "o-1", "relation id")
        == "https://mapped.test/relation"
    )


def test_resolve_iris_sanitize_fallback_identifiers(in_memory_session):
    assert (
        interview.resolve_class_iri(in_memory_session, "o-1", "class id/")
        == "http://ontology-platform.local/semantic/class/class_id_"
    )
    assert (
        interview.resolve_relation_type_iri(in_memory_session, "o-1", "relation id/")
        == "http://ontology-platform.local/semantic/relation-type/relation_id_"
    )


def test_run_question_validation_entity_count_sparql_passes(in_memory_session, monkeypatch):
    from app.services import interview as svc
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
    )

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.flush()
    in_memory_session.add(
        CompetencyQuestionModel(
            id="q-1",
            project_id="p-1",
            ontology_id="o-1",
            question="q",
            position=0,
            status="testable",
            query_definition={"kind": "entity_count", "class_id": "class-1", "min_count": 1},
            source_brief_fields=[],
        )
    )
    in_memory_session.commit()

    monkeypatch.setattr(
        svc, "active_data_and_ontology_graphs_for_question", lambda s, qid: ["https://x/g/data"]
    )
    monkeypatch.setattr(
        svc, "resolve_class_iri", lambda s, oid, cid: f"https://x/ont/{oid}/class/{cid}"
    )

    class _Settings:
        competency_question_sparql_timeout_seconds = 5.0

    class _Store:
        last_query = None

        def query_sparql(self, query, timeout_seconds, limit):
            self.last_query = query

            class _R:
                result = {"results": {"bindings": [{"count": {"value": "5"}}]}}
                result_format = "application/sparql-results+json"

            return _R()

    store = _Store()
    result = svc.run_question_validation(in_memory_session, store, "q-1", _Settings())
    assert result["status"] == "passed"
    assert result["validation_result"]["matches"] == 5
    assert "<http://www.w3.org/2000/01/rdf-schema#subClassOf>*" in store.last_query


@pytest.mark.skipif(
    os.environ.get("RUN_OXIGRAPH_SPARQL_RUNNER_TESTS") != "1",
    reason="requires a running local Oxigraph server",
)
def test_run_question_validation_entity_count_uses_canonical_fallback_iri_in_real_oxigraph(
    in_memory_session,
):
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
        SemanticGraphSetMemberModel,
        SemanticGraphSetModel,
    )
    from app.repositories.rdf_store import RdfStoreRepository
    from app.services import interview as svc

    token = uuid.uuid4().hex
    project_id = f"project-{token}"
    ontology_id = f"ontology-{token}"
    question_id = f"question-{token}"
    graph_id = f"graph-set-{token}"
    graph_iri = f"http://ontology-platform.test/interview-cq/{token}"
    class_id = f"workflow-{token}"
    class_iri = f"http://ontology-platform.local/semantic/class/{class_id}"
    store = RdfStoreRepository(os.environ.get("OXIGRAPH_URL", "http://127.0.0.1:7878"))

    in_memory_session.add(ProjectModel(id=project_id, name="P", normalized_label=project_id))
    in_memory_session.flush()
    in_memory_session.add(OntologyModel(id=ontology_id, project_id=project_id, name="O"))
    in_memory_session.flush()
    in_memory_session.add(
        CompetencyQuestionModel(
            id=question_id,
            project_id=project_id,
            ontology_id=ontology_id,
            question="Does a workflow exist?",
            position=0,
            status="testable",
            query_definition={"kind": "entity_count", "class_id": class_id, "min_count": 1},
            source_brief_fields=[],
        )
    )
    in_memory_session.add(
        SemanticGraphSetModel(
            id=graph_id,
            name="active",
            scope_type="ontology",
            scope_id=ontology_id,
            status="active",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        SemanticGraphSetMemberModel(
            id=f"member-{token}",
            graph_set_id=graph_id,
            graph_iri=graph_iri,
            role="asserted_data",
        )
    )
    in_memory_session.commit()

    class _Settings:
        competency_question_sparql_timeout_seconds = 5.0

    try:
        store.update_sparql(
            f"INSERT DATA {{ GRAPH <{graph_iri}> {{ "
            f"<http://ontology-platform.test/interview-cq/{token}/entity> a <{class_iri}> . "
            "} }"
        )
        result = svc.run_question_validation(in_memory_session, store, question_id, _Settings())
        assert result["status"] == "passed"
        assert result["validation_result"]["matches"] == 1
    finally:
        store.update_sparql(f"CLEAR GRAPH <{graph_iri}>")


def test_run_question_validation_sparql_count_rejects_non_select(in_memory_session, monkeypatch):
    from app.services import interview as svc
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
    )
    from fastapi import HTTPException

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.flush()
    in_memory_session.add(
        CompetencyQuestionModel(
            id="q-2",
            project_id="p-1",
            ontology_id="o-1",
            question="q",
            position=0,
            status="testable",
            query_definition={
                "kind": "sparql_count",
                "sparql": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
                "expected_min": 1,
            },
            source_brief_fields=[],
        )
    )
    in_memory_session.commit()

    monkeypatch.setattr(
        svc, "active_data_and_ontology_graphs_for_question", lambda s, qid: ["https://x/g/data"]
    )

    class _Settings:
        competency_question_sparql_timeout_seconds = 5.0

    class _Store:
        def query_sparql(self, query, timeout_seconds, limit):
            raise AssertionError("should not reach the store")

    with pytest.raises(HTTPException) as exc:
        svc.run_question_validation(in_memory_session, _Store(), "q-2", _Settings())
    assert exc.value.status_code == 422
    assert "only SELECT allowed" in str(exc.value.detail)


def test_run_question_validation_sparql_count_passes(in_memory_session, monkeypatch):
    from app.services import interview as svc
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
    )

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.flush()
    in_memory_session.add(
        CompetencyQuestionModel(
            id="q-3",
            project_id="p-1",
            ontology_id="o-1",
            question="q",
            position=0,
            status="testable",
            query_definition={
                "kind": "sparql_count",
                "sparql": "SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }",
                "expected_min": 1,
                "expected_max": 100,
            },
            source_brief_fields=[],
        )
    )
    in_memory_session.commit()

    monkeypatch.setattr(
        svc, "active_data_and_ontology_graphs_for_question", lambda s, qid: ["https://x/g/data"]
    )

    class _Settings:
        competency_question_sparql_timeout_seconds = 5.0

    class _Store:
        def query_sparql(self, query, timeout_seconds, limit):
            class _R:
                result = {"results": {"bindings": [{"count": {"value": "42"}}]}}
                result_format = "application/sparql-results+json"

            return _R()

    result = svc.run_question_validation(in_memory_session, _Store(), "q-3", _Settings())
    assert result["status"] == "passed"
    assert result["validation_result"]["matches"] == 42


def test_run_question_validation_409_when_not_testable(in_memory_session):
    from app.services import interview as svc
    from app.repositories.models import (
        CompetencyQuestionModel,
        OntologyModel,
        ProjectModel,
    )
    from fastapi import HTTPException

    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="p-1"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.flush()
    in_memory_session.add(
        CompetencyQuestionModel(
            id="q-4",
            project_id="p-1",
            ontology_id="o-1",
            question="q",
            position=0,
            status="draft",
            query_definition={},
            source_brief_fields=[],
        )
    )
    in_memory_session.commit()

    with pytest.raises(HTTPException) as exc:
        svc.run_question_validation(in_memory_session, None, "q-4", None)
    assert exc.value.status_code == 409
