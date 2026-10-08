"""Shared statement identity and R4.0-012 suspended collection regressions."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
)
from app.repositories.rdf_store import SparqlResult, UpdateResult
from app.services.ontology_lineage import LineageTargetNotFound, OntologyLineageService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad


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


class _FailingLineageRecorder:
    def ontology_id_for_graph_set(self, _graph_set_id):
        return "ontology"

    def record_derived_statements(self, **_kwargs):
        raise RuntimeError("lineage persistence failed")
