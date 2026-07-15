"""R-005 statement identity, lifecycle, context, and derivation tests."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import Settings
from app.repositories.models import (
    BuildSessionModel,
    CompetencyQuestionModel,
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    ModelingBatchModel,
    ModelingItemModel,
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
    SemanticStatementOccurrenceModel,
    SemanticStatementOriginModel,
    SemanticStatementPremiseModel,
)
from app.repositories.rdf_store import RdfGraphDelta, SparqlResult, UpdateResult
from app.services.owl_reasoner import OwlReasonerResult, OwlReasonerRunner
from app.services.ontology_lineage import LineageTargetNotFound, OntologyLineageService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_rule_definition import SemanticRuleDefinitionService
from app.services.semantic_rule_execution import SemanticRuleExecutionService


def _workspace(session):
    settings = Settings(
        semantic_graph_iri_prefix="https://lineage.test/graph/",
        semantic_base_iri="https://lineage.test/resource/",
    )
    session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    ontology = OntologyModel(id="ontology", project_id="project", name="Ontology")
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    workspace = OntologyWorkspaceService(session, settings).context(ontology.id)
    roles = {member["role"]: member["graph_iri"] for member in workspace["members"]}
    return settings, ontology, workspace["default_graph_set_id"], roles


def _audit(session, audit_id="audit", graphs=None):
    row = SemanticEditAuditModel(
        id=audit_id,
        actor="agent:dev",
        reason="model fact",
        input_format="canonical-write",
        target_graph_iri=(graphs or [None])[0],
        affected_graph_iris=graphs or [],
        graph_delta={},
        applied=True,
    )
    session.add(row)
    session.flush()
    return row


def test_statement_identity_preserves_rdf_term_kinds() -> None:
    base = ("https://e.test/s", "https://e.test/p")
    graph = "https://e.test/g"
    ids = {
        statement_id_for_quad(*base, '"1"', graph),
        statement_id_for_quad(*base, '"1"^^<http://www.w3.org/2001/XMLSchema#integer>', graph),
        statement_id_for_quad(*base, '"one"@en', graph),
        statement_id_for_quad(*base, "<https://e.test/one>", graph),
    }
    assert len(ids) == 4
    statement_id = statement_id_for_quad(*base, '"1"', graph)
    assert occurrence_id_for(statement_id, 1) == occurrence_id_for(statement_id, 1)
    assert occurrence_id_for(statement_id, 1) != occurrence_id_for(statement_id, 2)


def test_recorder_is_idempotent_and_reinsert_creates_new_occurrence(
    in_memory_session,
) -> None:
    _settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    graph = roles["asserted_data"]
    quad = (
        "<https://lineage.test/entity/alice>",
        "<https://lineage.test/property/name>",
        '"Alice"@en',
        graph,
    )
    _audit(in_memory_session, "audit-1", [graph])
    recorder = SemanticLineageRecorder(in_memory_session)
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id="audit-1",
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id="audit-1",
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementOccurrenceModel))
        == 1
    )
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementOriginModel))
        == 1
    )

    _audit(in_memory_session, "audit-2", [graph])
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(deletes=[quad]),
        graph_revisions={graph: 2},
        audit_id="audit-2",
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    _audit(in_memory_session, "audit-3", [graph])
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 3},
        audit_id="audit-3",
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    rows = list(
        in_memory_session.scalars(
            select(SemanticStatementOccurrenceModel).order_by(
                SemanticStatementOccurrenceModel.graph_revision
            )
        )
    )
    assert [row.graph_revision for row in rows] == [1, 3]
    assert [row.status for row in rows] == ["invalidated", "active"]
    assert rows[0].statement_id == rows[1].statement_id
    assert rows[0].id != rows[1].id

    current = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=rows[0].statement_id,
    )
    history = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=rows[0].statement_id,
        include_history=True,
    )
    assert [item["graph_revision"] for item in current["items"]] == [3]
    assert {item["graph_revision"] for item in history["items"]} == {1, 3}


def test_modeling_context_keeps_evidence_rationale_question_and_audit_separate(
    in_memory_session,
) -> None:
    _settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    graph = roles["asserted_ontology"]
    in_memory_session.add(
        BuildSessionModel(
            id="session",
            project_id="project",
            client_session_id="client",
            create_request_hash="0" * 64,
        )
    )
    batch = ModelingBatchModel(
        id="batch",
        project_id="project",
        ontology_id=ontology.id,
        build_session_id="session",
        client_batch_id="batch-client",
        content_hash="1" * 64,
        status="applied",
    )
    item = ModelingItemModel(
        id="item",
        batch_id="batch",
        client_item_id="class",
        ordinal=0,
        command_kind="create_class",
        payload={"name": "Person"},
        rationale="Needed for customer modeling",
        competency_question_ids=["cq"],
    )
    question = CompetencyQuestionModel(
        id="cq",
        project_id="project",
        ontology_id=ontology.id,
        question="Which people are customers?",
    )
    reference = EvidenceReferenceModel(
        id="evidence",
        project_id="project",
        document_name="requirements.md",
        normalized_document_name="requirements.md",
        excerpt="A customer is a person.",
        excerpt_hash="2" * 64,
    )
    in_memory_session.add_all([batch, item, question, reference])
    audit = _audit(in_memory_session, graphs=[graph])
    in_memory_session.add(
        EvidenceAssociationModel(
            id="association",
            project_id="project",
            ontology_id=ontology.id,
            graph_set_id=graph_set_id,
            evidence_reference_id=reference.id,
            target_type="modeling_item",
            target_id=item.id,
            edit_audit_id=audit.id,
        )
    )
    quad = (
        "<https://lineage.test/class/person>",
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
        "<http://www.w3.org/2002/07/owl#Class>",
        graph,
    )
    recorder = SemanticLineageRecorder(in_memory_session)
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id=audit.id,
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
        modeling_item_effects={quad: [item.id]},
    )
    in_memory_session.commit()

    result = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="resource",
        target_id="https://lineage.test/class/person",
    )
    context = result["items"][0]["supporting_context"]
    assert result["evidence_status"] == "supported"
    assert context["evidence_references"][0]["excerpt"] == "A customer is a person."
    assert context["rationales"] == [
        {"modeling_item_id": "item", "text": "Needed for customer modeling"}
    ]
    assert context["competency_questions"][0]["id"] == "cq"
    assert context["edit_audits"][0]["reason"] == "model fact"
    assert "rationale" not in context["evidence_references"][0]


class _DslStore:
    def __init__(self, graph_iri: str) -> None:
        self.graph_iri = graph_iri
        self.updates: list[str] = []

    def query_sparql(self, _query, timeout_seconds, limit):
        return SparqlResult(
            result={
                "head": {"vars": ["g", "student", "score"]},
                "results": {
                    "bindings": [
                        {
                            "g": {"type": "uri", "value": self.graph_iri},
                            "student": {
                                "type": "uri",
                                "value": "https://lineage.test/entity/alice",
                            },
                            "score": {
                                "type": "literal",
                                "value": "95",
                                "datatype": "http://www.w3.org/2001/XMLSchema#integer",
                            },
                        }
                    ]
                },
            }
        )

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()


def test_platform_dsl_records_exact_premise_without_copying_evidence(
    in_memory_session,
) -> None:
    settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    graph = roles["asserted_data"]
    audit = _audit(in_memory_session, graphs=[graph])
    premise_quad = (
        "<https://lineage.test/entity/alice>",
        "<https://lineage.test/property/score>",
        '"95"^^<http://www.w3.org/2001/XMLSchema#integer>',
        graph,
    )
    SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[premise_quad]),
        graph_revisions={graph: 1},
        audit_id=audit.id,
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    rule = SemanticRuleDefinitionService(in_memory_session, settings).create_rule(
        rule_iri="https://lineage.test/rule/excellent",
        name="Excellent",
        language="platform_dsl",
        body={
            "when": [
                {
                    "s": "?student",
                    "p": "<https://lineage.test/property/score>",
                    "o": "?score",
                },
                {"filter": {"gte": ["?score", 90]}},
            ],
            "then": [
                {
                    "s": "?student",
                    "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                    "o": "<https://lineage.test/class/ExcellentStudent>",
                }
            ],
        },
        input_roles=["asserted_data"],
    )
    # Standalone rule service definitions are executable even though Rule IRI
    # lineage itself is reserved for ontology-owned R-004 Rule records.
    store = _DslStore(graph)
    result = SemanticRuleExecutionService(in_memory_session, store, settings).execute_rule(
        graph_set_id=graph_set_id,
        rule_definition_id=rule.id,
    )
    assert result["status"] == "succeeded", result
    output = result["statements"][0]
    statement_id = statement_id_for_quad(
        output["s"], output["p"], output["o"], result["result_graph_iri"]
    )
    lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=statement_id,
    )
    item = lineage["items"][0]
    assert item["evidence_status"] == "not_applicable"
    assert item["supporting_context"]["evidence_references"] == []
    assert item["derivation"]["proof_level"] == "exact"
    assert len(item["derivation"]["premises"]) == 1
    assert item["dependency_evidence_status"] == "contains_missing"
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementPremiseModel))
        == 1
    )


def test_rule_group_preserves_all_rule_versions_and_exact_dsl_premises(
    in_memory_session,
) -> None:
    settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    graph = roles["asserted_data"]
    audit = _audit(in_memory_session, graphs=[graph])
    premise_quad = (
        "<https://lineage.test/entity/alice>",
        "<https://lineage.test/property/score>",
        '"95"^^<http://www.w3.org/2001/XMLSchema#integer>',
        graph,
    )
    SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[premise_quad]),
        graph_revisions={graph: 1},
        audit_id=audit.id,
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    rules = []
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    for threshold in (80, 90):
        rules.append(
            service.create_rule(
                rule_iri=f"https://lineage.test/rule/excellent-{threshold}",
                name=f"Excellent {threshold}",
                language="platform_dsl",
                body={
                    "when": [
                        {
                            "s": "?student",
                            "p": "<https://lineage.test/property/score>",
                            "o": "?score",
                        },
                        {"filter": {"gte": ["?score", threshold]}},
                    ],
                    "then": [
                        {
                            "s": "?student",
                            "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                            "o": "<https://lineage.test/class/ExcellentStudent>",
                        }
                    ],
                },
                input_roles=["asserted_data"],
            )
        )

    result = SemanticRuleExecutionService(
        in_memory_session, _DslStore(graph), settings
    ).execute_rule_group(
        graph_set_id=graph_set_id,
        rule_definition_ids=[rule.id for rule in rules],
    )
    assert result["status"] == "succeeded", result
    statement = in_memory_session.scalar(
        select(SemanticStatementOccurrenceModel).where(
            SemanticStatementOccurrenceModel.graph_iri == result["result_graph_iri"]
        )
    )
    lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=statement.statement_id,
    )
    item = lineage["items"][0]
    origin = next(origin for origin in item["origins"] if origin["kind"] == "rule_run")
    sources = origin["metadata"]["rule_sources"]
    assert {source["rule_definition_id"] for source in sources} == {rule.id for rule in rules}
    assert {source["rule_version"] for source in sources} == {rule.version for rule in rules}
    assert {definition["id"] for definition in item["derivation"]["definitions"]} == {
        rule.id for rule in rules
    }
    assert item["derivation"]["proof_level"] == "exact"
    assert len(item["derivation"]["premises"]) == 1


class _DerivedStore:
    def __init__(self, construct_result: str = "") -> None:
        self.construct_result = construct_result
        self.updates: list[str] = []

    def query_sparql(self, _query, timeout_seconds, limit):
        return SparqlResult(result=self.construct_result)

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()

    def get_graph(self, _graph_iri, _format):
        return ""


class _Reasoner(OwlReasonerRunner):
    def run(self, source_documents, tasks, timeout_seconds):
        return OwlReasonerResult(
            consistent=True,
            inferred_rdf=(
                "<https://lineage.test/entity/alice> "
                "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
                "<https://lineage.test/class/Person> ."
            ),
        )


class _FailingLineageRecorder:
    def ontology_id_for_graph_set(self, _graph_set_id):
        return "ontology"

    def record_derived_statements(self, **_kwargs):
        raise RuntimeError("lineage persistence failed")


def test_lineage_failure_marks_rule_run_failed_without_occurrences(
    in_memory_session,
) -> None:
    settings, _ontology, graph_set_id, roles = _workspace(in_memory_session)
    store = _DerivedStore(
        "<https://lineage.test/entity/alice> <https://lineage.test/property/eligible> true ."
    )
    result = SemanticRuleExecutionService(
        in_memory_session,
        store,
        settings,
        lineage_recorder=_FailingLineageRecorder(),  # type: ignore[arg-type]
    ).execute_construct_template(
        graph_set_id=graph_set_id,
        template=(
            "CONSTRUCT { ?s <https://lineage.test/property/eligible> true } "
            f"WHERE {{ GRAPH <{roles['asserted_data']}> {{ ?s ?p ?o }} }}"
        ),
    )
    assert result["status"] == "failed"
    assert result["error"] == "lineage persistence failed"
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementOccurrenceModel))
        == 0
    )


def test_construct_and_owl_outputs_are_honestly_coarse(in_memory_session) -> None:
    settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    construct_store = _DerivedStore(
        "<https://lineage.test/entity/alice> <https://lineage.test/property/eligible> true ."
    )
    construct = SemanticRuleExecutionService(
        in_memory_session, construct_store, settings
    ).execute_construct_template(
        graph_set_id=graph_set_id,
        template=(
            "CONSTRUCT { ?s <https://lineage.test/property/eligible> true } "
            f"WHERE {{ GRAPH <{roles['asserted_data']}> {{ ?s ?p ?o }} }}"
        ),
    )
    construct_statement = construct["statements"][0]
    construct_id = statement_id_for_quad(
        construct_statement["s"],
        construct_statement["p"],
        construct_statement["o"],
        construct["result_graph_iri"],
    )
    construct_lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=construct_id,
    )
    construct_item = construct_lineage["items"][0]
    assert construct_item["derivation"]["proof_level"] == "coarse"
    assert construct_item["derivation"]["premises"] == []
    assert construct_item["supporting_context"]["evidence_references"] == []
    assert construct_item["derivation"]["run"]["input_graph_revisions"]

    reasoning_store = _DerivedStore()
    reasoning = SemanticReasoningService(
        in_memory_session,
        reasoning_store,
        settings,
        reasoner=_Reasoner(),
    ).run_reasoning(
        [roles["asserted_ontology"], roles["asserted_data"]],
        ["classification"],
        persist_result_graph=True,
        graph_set_id=graph_set_id,
        engine_version="reasoner:test",
    )
    reasoning_id = statement_id_for_quad(
        "https://lineage.test/entity/alice",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        "<https://lineage.test/class/Person>",
        reasoning["result_graph_iri"],
    )
    reasoning_lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="statement",
        target_id=reasoning_id,
    )
    reasoning_item = reasoning_lineage["items"][0]
    assert reasoning_item["derivation"]["proof_level"] == "coarse"
    assert reasoning_item["derivation"]["run"]["engine_version"] == "reasoner:test"
    assert reasoning_item["derivation"]["premises"] == []
    assert reasoning_item["evidence_status"] == "not_applicable"


class _LegacyStore:
    def __init__(self, graph_iri: str) -> None:
        self.graph_iri = graph_iri

    def query_sparql(self, _query, timeout_seconds, limit):
        return SparqlResult(
            result={
                "results": {
                    "bindings": [
                        {
                            "p": {
                                "type": "uri",
                                "value": "https://lineage.test/property/name",
                            },
                            "o": {"type": "literal", "value": "Legacy"},
                            "g": {"type": "uri", "value": self.graph_iri},
                        },
                        {
                            "p": {
                                "type": "uri",
                                "value": "https://lineage.test/property/code",
                            },
                            "o": {"type": "literal", "value": "L-1"},
                            "g": {"type": "uri", "value": self.graph_iri},
                        },
                    ]
                }
            }
        )


def test_legacy_current_rdf_is_partial_and_node_limit_is_deterministic(
    in_memory_session,
) -> None:
    _settings, ontology, graph_set_id, roles = _workspace(in_memory_session)
    graph = roles["asserted_data"]
    legacy = OntologyLineageService(in_memory_session, _LegacyStore(graph)).get_lineage(
        ontology_id=ontology.id,
        target_type="resource",
        target_id="https://lineage.test/entity/legacy",
    )
    assert legacy["lineage_status"] == "partial"
    assert legacy["warnings"] == ["legacy_lineage_unavailable"]
    legacy_limited = OntologyLineageService(in_memory_session, _LegacyStore(graph)).get_lineage(
        ontology_id=ontology.id,
        target_type="resource",
        target_id="https://lineage.test/entity/legacy",
        limit=1,
    )
    assert legacy_limited["truncated"] is True
    assert legacy_limited["warnings"] == [
        "legacy_lineage_unavailable",
        "lineage_truncated",
    ]

    audit = _audit(in_memory_session, graphs=[graph])
    subject = "<https://lineage.test/entity/many>"
    SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(
            inserts=[
                (subject, "<https://lineage.test/property/a>", '"A"', graph),
                (subject, "<https://lineage.test/property/b>", '"B"', graph),
            ]
        ),
        graph_revisions={graph: 1},
        audit_id=audit.id,
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )
    limited = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id=ontology.id,
        target_type="resource",
        target_id="https://lineage.test/entity/many",
        limit=1,
    )
    assert len(limited["items"]) == 1
    assert limited["truncated"] is True
    assert limited["warnings"] == ["lineage_truncated"]


def test_scope_rejects_statement_from_other_ontology(in_memory_session) -> None:
    _settings, first, graph_set_id, roles = _workspace(in_memory_session)
    in_memory_session.add(OntologyModel(id="other", project_id="project", name="Other"))
    graph = roles["asserted_data"]
    audit = _audit(in_memory_session, graphs=[graph])
    quad = (
        "<https://lineage.test/entity/secret>",
        "<https://lineage.test/property/value>",
        '"secret"',
        graph,
    )
    occurrence = SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id=audit.id,
        ontology_id=first.id,
        graph_set_id=graph_set_id,
    )[0]
    in_memory_session.commit()
    try:
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id="other",
            target_type="statement",
            target_id=occurrence.statement_id,
        )
    except LineageTargetNotFound as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("cross-Ontology statement must not be visible")
