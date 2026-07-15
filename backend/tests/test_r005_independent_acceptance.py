"""Independent R-005 acceptance probes for security and lifecycle boundaries.

These tests intentionally cover requirements that are not exercised by the
implementation-owned lineage tests.  They are expected to remain black-box
regressions after the implementation is corrected.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.fact_evidence import BindFactEvidenceRequest, create_fact_evidence
from app.core.config import Settings
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.models import (
    EvidenceReferenceModel,
    OntologyModel,
    ProjectModel,
    SemanticDerivedResultPointerModel,
    SemanticEditAuditModel,
    SemanticRuleRunModel,
    SemanticStatementOccurrenceModel,
)
from app.repositories.rdf_store import RdfGraphDelta, SparqlResult, UpdateResult
from app.services.ontology_lineage import OntologyLineageService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic import SemanticService
from app.services.semantic_lineage_identity import statement_id_for_quad
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
from app.services.semantic_rule_definition import SemanticRuleDefinitionService
from app.services.semantic_rule_execution import SemanticRuleExecutionService


def _workspace(session, settings: Settings, ontology_id: str) -> tuple[str, dict[str, str]]:
    ontology = OntologyModel(id=ontology_id, project_id="project", name=ontology_id)
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    context = OntologyWorkspaceService(session, settings).context(ontology_id)
    roles = {member["role"]: member["graph_iri"] for member in context["members"]}
    return context["default_graph_set_id"], roles


def _audit(session, audit_id: str, graph_iri: str, reason: str) -> None:
    session.add(
        SemanticEditAuditModel(
            id=audit_id,
            actor="agent:test",
            reason=reason,
            input_format="canonical-write",
            target_graph_iri=graph_iri,
            affected_graph_iris=[graph_iri],
            graph_delta={},
            applied=True,
        )
    )
    session.flush()


def test_derived_lineage_never_copies_cross_ontology_evidence(in_memory_session) -> None:
    settings = Settings(
        semantic_graph_iri_prefix="https://r005-independent.test/graph/",
        semantic_base_iri="https://r005-independent.test/resource/",
    )
    in_memory_session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    first_graph_set, _first_roles = _workspace(in_memory_session, settings, "ontology-a")
    second_graph_set, _second_roles = _workspace(in_memory_session, settings, "ontology-b")

    result_graph = "https://r005-independent.test/graph/rule-result/run-b"
    in_memory_session.add(
        SemanticRuleRunModel(
            id="run-b",
            graph_set_id=second_graph_set,
            result_graph_iri=result_graph,
            engine_name="sparql_construct",
            source_signature="source-b",
            status="succeeded",
        )
    )
    in_memory_session.add(
        SemanticDerivedResultPointerModel(
            id="pointer-b",
            graph_set_id=second_graph_set,
            result_kind="rule",
            run_id="run-b",
            result_graph_iri=result_graph,
            source_signature="source-b",
            status="current",
        )
    )
    occurrence = SemanticLineageRecorder(in_memory_session).record_derived_statements(
        ontology_id="ontology-b",
        graph_set_id=second_graph_set,
        result_graph_iri=result_graph,
        statements=[
            {
                "s": "<https://r005-independent.test/entity/alice>",
                "p": "<https://r005-independent.test/property/eligible>",
                "o": '"Eligible"',
            }
        ],
        assertion_kind="construct_derived",
        origin_kind="rule_run",
        run_id="run-b",
        proof_level="coarse",
    )[0]
    in_memory_session.commit()

    # The public write path rejects both a derived assertion kind and a graph
    # outside Ontology A's asserted-data scope.
    with pytest.raises(HTTPException) as error:
        create_fact_evidence(
            first_graph_set,
            BindFactEvidenceRequest(
                ontology_id="ontology-a",
                subject_iri="https://r005-independent.test/entity/alice",
                predicate_iri="https://r005-independent.test/property/eligible",
                object_value="Eligible",
                graph_iri=result_graph,
                assertion_kind="construct_derived",
                document_filename="ontology-a-secret.md",
                text="Secret evidence owned by ontology A",
            ),
            in_memory_session,
            settings,
        )
    assert error.value.status_code == 409

    # Simulate a malicious binding written by an older, unscoped code path.
    reference = EvidenceReferenceModel(
        id="malicious-reference",
        project_id="project",
        document_name="ontology-a-secret.md",
        normalized_document_name="ontology-a-secret.md",
        excerpt="Secret evidence owned by ontology A",
        excerpt_hash="f" * 64,
    )
    in_memory_session.add(reference)
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=occurrence.statement_id,
        subject_iri="https://r005-independent.test/entity/alice",
        predicate_iri="https://r005-independent.test/property/eligible",
        object_value='"Eligible"',
        graph_iri=result_graph,
        text=reference.excerpt,
        evidence_reference_id=reference.id,
    )
    in_memory_session.commit()

    lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id="ontology-b",
        target_type="statement",
        target_id=occurrence.statement_id,
    )

    assert lineage["items"][0]["evidence_status"] == "not_applicable"
    assert lineage["items"][0]["supporting_context"]["evidence_references"] == []


def test_history_resolves_the_invalidation_audit_not_only_its_id(in_memory_session) -> None:
    settings = Settings(semantic_graph_iri_prefix="https://r005-history.test/graph/")
    in_memory_session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    graph_set_id, roles = _workspace(in_memory_session, settings, "ontology")
    graph = roles["asserted_data"]
    quad = (
        "<https://r005-history.test/entity/alice>",
        "<https://r005-history.test/property/name>",
        '"Alice"',
        graph,
    )
    recorder = SemanticLineageRecorder(in_memory_session)
    _audit(in_memory_session, "audit-create", graph, "create the name")
    occurrence = recorder.record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id="audit-create",
        ontology_id="ontology",
        graph_set_id=graph_set_id,
    )[0]
    _audit(in_memory_session, "audit-delete", graph, "remove the name")
    recorder.record_asserted_delta(
        delta=RdfGraphDelta(deletes=[quad]),
        graph_revisions={graph: 2},
        audit_id="audit-delete",
        ontology_id="ontology",
        graph_set_id=graph_set_id,
    )
    in_memory_session.commit()

    history = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id="ontology",
        target_type="statement",
        target_id=occurrence.statement_id,
        include_history=True,
    )

    audits = history["items"][0]["supporting_context"]["edit_audits"]
    assert {audit["id"] for audit in audits} == {"audit-create", "audit-delete"}
    assert any(audit["reason"] == "remove the name" for audit in audits)


class _UpdateStore:
    def update_sparql(self, _update: str) -> UpdateResult:
        return UpdateResult()


class _SnapshotUpdateStore:
    def __init__(self, graph_iri: str) -> None:
        self.graph_iri = graph_iri
        self.updated = False

    def update_sparql(self, _update: str) -> UpdateResult:
        self.updated = True
        return UpdateResult()

    def get_graph(self, graph_iri: str, _format: str) -> str:
        assert graph_iri == self.graph_iri
        predicate = "new" if self.updated else "old"
        return (
            "<https://r005-update.test/entity/alice> "
            f'<https://r005-update.test/property/{predicate}> "value" .'
        )


def test_restricted_where_update_does_not_leave_removed_occurrence_active(
    in_memory_session,
) -> None:
    settings = Settings(semantic_graph_iri_prefix="https://r005-update.test/graph/")
    in_memory_session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    graph_set_id, roles = _workspace(in_memory_session, settings, "ontology")
    graph = roles["asserted_data"]
    old_quad = (
        "<https://r005-update.test/entity/alice>",
        "<https://r005-update.test/property/old>",
        '"value"',
        graph,
    )
    _audit(in_memory_session, "audit-create", graph, "create old value")
    old = SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[old_quad]),
        graph_revisions={graph: 0},
        audit_id="audit-create",
        ontology_id="ontology",
        graph_set_id=graph_set_id,
    )[0]
    in_memory_session.commit()

    SemanticService(in_memory_session, _UpdateStore(), settings).apply_edit(
        "sparql-update",
        f"""
        DELETE {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/old> ?old }} }}
        INSERT {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/new> ?old }} }}
        WHERE  {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/old> ?old }} }}
        """,
        validate=False,
        actor="agent:test",
        reason="rename predicate",
    )

    in_memory_session.refresh(old)
    assert old.status == "invalidated"


def test_restricted_where_snapshot_records_the_inserted_occurrence(
    in_memory_session,
) -> None:
    settings = Settings(semantic_graph_iri_prefix="https://r005-update.test/graph/")
    in_memory_session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    graph_set_id, roles = _workspace(in_memory_session, settings, "ontology")
    graph = roles["asserted_data"]
    old_quad = (
        "<https://r005-update.test/entity/alice>",
        "<https://r005-update.test/property/old>",
        '"value"',
        graph,
    )
    _audit(in_memory_session, "audit-create", graph, "create old value")
    old = SemanticLineageRecorder(in_memory_session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[old_quad]),
        graph_revisions={graph: 0},
        audit_id="audit-create",
        ontology_id="ontology",
        graph_set_id=graph_set_id,
    )[0]
    in_memory_session.commit()

    result = SemanticService(in_memory_session, _SnapshotUpdateStore(graph), settings).apply_edit(
        "sparql-update",
        f"""
        DELETE {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/old> ?old }} }}
        INSERT {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/new> ?old }} }}
        WHERE  {{ GRAPH <{graph}> {{ ?s <https://r005-update.test/property/old> ?old }} }}
        """,
        validate=False,
        actor="agent:test",
        reason="rename predicate",
    )

    in_memory_session.refresh(old)
    inserted = in_memory_session.scalar(
        select(SemanticStatementOccurrenceModel).where(
            SemanticStatementOccurrenceModel.predicate_iri
            == "https://r005-update.test/property/new"
        )
    )
    assert old.status == "invalidated"
    assert inserted is not None
    assert inserted.status == "active"
    assert inserted.graph_revision == result["graph_revisions"][graph]


class _RuleGroupStore:
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
                                "value": "https://r005-rule-group.test/entity/alice",
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


def _rule_group_setup(session):
    settings = Settings(
        semantic_graph_iri_prefix="https://r005-rule-group.test/graph/",
        semantic_base_iri="https://r005-rule-group.test/resource/",
    )
    session.add(ProjectModel(id="project", name="Project", normalized_label="project"))
    graph_set_id, roles = _workspace(session, settings, "ontology")
    graph = roles["asserted_data"]
    _audit(session, "audit-premise", graph, "seed exact group premise")
    premise_quad = (
        "<https://r005-rule-group.test/entity/alice>",
        "<https://r005-rule-group.test/property/score>",
        '"95"^^<http://www.w3.org/2001/XMLSchema#integer>',
        graph,
    )
    SemanticLineageRecorder(session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[premise_quad]),
        graph_revisions={graph: 1},
        audit_id="audit-premise",
        ontology_id="ontology",
        graph_set_id=graph_set_id,
    )
    body = {
        "when": [
            {
                "s": "?student",
                "p": "<https://r005-rule-group.test/property/score>",
                "o": "?score",
            }
        ],
        "then": [
            {
                "s": "?student",
                "p": "<https://r005-rule-group.test/property/eligible>",
                "o": '"yes"',
            }
        ],
    }
    service = SemanticRuleDefinitionService(session, settings)
    first = service.create_rule(
        rule_iri="https://r005-rule-group.test/rule/first",
        name="First",
        language="platform_dsl",
        body=body,
        input_roles=["asserted_data"],
    )
    second = service.create_rule(
        rule_iri="https://r005-rule-group.test/rule/second",
        name="Second",
        language="platform_dsl",
        body=body,
        input_roles=["asserted_data"],
    )
    return settings, graph_set_id, graph, first, second


def test_rule_group_dsl_retains_exact_premise_and_definition(in_memory_session) -> None:
    settings, graph_set_id, graph, first, _second = _rule_group_setup(in_memory_session)
    result = SemanticRuleExecutionService(
        in_memory_session, _RuleGroupStore(graph), settings
    ).execute_rule_group(graph_set_id=graph_set_id, rule_definition_ids=[first.id])
    assert result["status"] == "succeeded", result
    lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id="ontology",
        target_type="statement",
        target_id=statement_id_for_quad(
            "https://r005-rule-group.test/entity/alice",
            "https://r005-rule-group.test/property/eligible",
            '"yes"',
            result["result_graph_iri"],
        ),
    )
    derivation = lineage["items"][0]["derivation"]
    assert derivation["proof_level"] == "exact"
    assert len(derivation["premises"]) == 1
    assert derivation["definition"]["id"] == first.id
    assert derivation["definition"]["version"] == first.version
    assert {source["rule_definition_id"] for source in derivation["rule_sources"]} == {first.id}


def test_rule_group_duplicate_output_preserves_all_rule_sources(in_memory_session) -> None:
    settings, graph_set_id, graph, first, second = _rule_group_setup(in_memory_session)
    result = SemanticRuleExecutionService(
        in_memory_session, _RuleGroupStore(graph), settings
    ).execute_rule_group(
        graph_set_id=graph_set_id,
        rule_definition_ids=[first.id, second.id],
    )
    assert result["status"] == "succeeded", result
    lineage = OntologyLineageService(in_memory_session).get_lineage(
        ontology_id="ontology",
        target_type="statement",
        target_id=statement_id_for_quad(
            "https://r005-rule-group.test/entity/alice",
            "https://r005-rule-group.test/property/eligible",
            '"yes"',
            result["result_graph_iri"],
        ),
    )
    derivation = lineage["items"][0]["derivation"]
    expected_ids = {first.id, second.id}
    assert {definition["id"] for definition in derivation["definitions"]} == expected_ids
    assert {source["rule_definition_id"] for source in derivation["rule_sources"]} == expected_ids
