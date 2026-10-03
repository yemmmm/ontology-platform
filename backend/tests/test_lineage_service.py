"""Shared statement identity and R4.0-012 suspended collection regressions."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
    SemanticStatementOccurrenceModel,
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


def test_platform_dsl_does_not_record_suspended_lineage(
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
    with pytest.raises(LineageTargetNotFound):
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id=ontology.id,
            target_type="statement",
            target_id=statement_id,
        )
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementPremiseModel))
        == 0
    )


def test_rule_group_does_not_record_suspended_lineage(
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
    assert statement is None
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementPremiseModel))
        == 0
    )


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


def test_lineage_failure_hook_is_not_called_for_rule_runs(
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
    assert result["status"] == "succeeded"
    assert result.get("error") is None
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticStatementOccurrenceModel))
        == 0
    )


def test_construct_and_owl_outputs_do_not_record_suspended_lineage(in_memory_session) -> None:
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
    with pytest.raises(LineageTargetNotFound):
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id=ontology.id,
            target_type="statement",
            target_id=construct_id,
        )

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
    with pytest.raises(LineageTargetNotFound):
        OntologyLineageService(in_memory_session).get_lineage(
            ontology_id=ontology.id,
            target_type="statement",
            target_id=reasoning_id,
        )
