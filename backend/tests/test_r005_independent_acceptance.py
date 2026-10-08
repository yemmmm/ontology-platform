"""R4.0-012 regressions for suspended commands and lineage collection."""

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
from app.repositories.rdf_store import RdfGraphDelta, UpdateResult
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic import SemanticService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder
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

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri == self.graph_iri

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
