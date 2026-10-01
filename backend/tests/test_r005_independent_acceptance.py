"""Independent R-005 acceptance probes for security and lifecycle boundaries.

These tests intentionally cover requirements that are not exercised by the
implementation-owned lineage tests.  They are expected to remain black-box
regressions after the implementation is corrected.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
    SemanticStatementOccurrenceModel,
)
from app.repositories.rdf_store import RdfGraphDelta, SparqlResult, UpdateResult
from app.services.ontology_lineage import LineageTargetNotFound, OntologyLineageService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic import SemanticService
from app.services.semantic_lineage_identity import statement_id_for_quad
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
from app.services.semantic_rule_definition import SemanticRuleDefinitionService
from app.services.semantic_rule_execution import SemanticRuleExecutionService
from app.services.semantic_command_compiler import UnsupportedCommandKind, compile_command


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


def test_fact_evidence_write_command_is_unavailable() -> None:
    with pytest.raises(UnsupportedCommandKind):
        compile_command("bind_fact_evidence", {}, Settings())


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
    def __init__(self) -> None:
        self.updated = False

    def update_sparql(self, _update: str) -> UpdateResult:
        self.updated = True
        return UpdateResult()

    def get_graph(self, _graph_iri: str, _format: str) -> str:
        predicate = "new" if self.updated else "old"
        return (
            "<https://r005-update.test/entity/alice> "
            f'<https://r005-update.test/property/{predicate}> "value" .'
        )


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


def test_restricted_where_update_does_not_collect_new_lineage(
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
    # D2 stops pure tracing collection. Existing historical rows are not
    # rewritten and no replacement occurrence is created by the edit.
    assert old.status == "active"


def test_restricted_where_snapshot_does_not_collect_inserted_lineage(
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
    assert old.status == "active"
    assert inserted is None
    assert result["graph_revisions"][graph] >= 1


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


def test_rule_group_dsl_does_not_collect_lineage(in_memory_session) -> None:
    settings, graph_set_id, graph, first, _second = _rule_group_setup(in_memory_session)
    result = SemanticRuleExecutionService(
        in_memory_session, _RuleGroupStore(graph), settings
    ).execute_rule_group(graph_set_id=graph_set_id, rule_definition_ids=[first.id])
    assert result["status"] == "succeeded", result
    with pytest.raises(LineageTargetNotFound):
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id="ontology",
            target_type="statement",
            target_id=statement_id_for_quad(
                "https://r005-rule-group.test/entity/alice",
                "https://r005-rule-group.test/property/eligible",
                '"yes"',
                result["result_graph_iri"],
            ),
        )


def test_rule_group_duplicate_output_does_not_collect_lineage(in_memory_session) -> None:
    settings, graph_set_id, graph, first, second = _rule_group_setup(in_memory_session)
    result = SemanticRuleExecutionService(
        in_memory_session, _RuleGroupStore(graph), settings
    ).execute_rule_group(
        graph_set_id=graph_set_id,
        rule_definition_ids=[first.id, second.id],
    )
    assert result["status"] == "succeeded", result
    with pytest.raises(LineageTargetNotFound):
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id="ontology",
            target_type="statement",
            target_id=statement_id_for_quad(
                "https://r005-rule-group.test/entity/alice",
                "https://r005-rule-group.test/property/eligible",
                '"yes"',
                result["result_graph_iri"],
            ),
        )
