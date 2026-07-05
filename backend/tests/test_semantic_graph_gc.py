"""Phase 4 reasoning-result garbage collection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.repositories.models import SemanticDerivedResultPointerModel
from app.repositories.rdf_store import UpdateResult
from app.services.semantic_graph_gc import (
    GraphGcError,
    SemanticGraphGcService,
)


PREFIX = "http://ontology-platform.local/semantic/graph/"


class RecordingStore:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    def clear_graph(self, graph_iri: str) -> UpdateResult:
        self.cleared.append(graph_iri)
        return UpdateResult()


@pytest.fixture
def gc_service(in_memory_session):
    return SemanticGraphGcService(
        in_memory_session,
        RecordingStore(),
        Settings(),
        retention_days=0,
    )


def _seed_pointer(
    session,
    *,
    graph_iri: str,
    status: str,
    superseded_at: datetime | None = None,
    kind: str = "reasoning",
) -> SemanticDerivedResultPointerModel:
    metadata: dict = {}
    if superseded_at:
        metadata["superseded_at"] = superseded_at.isoformat()
    pointer = SemanticDerivedResultPointerModel(
        id=f"ptr-{graph_iri}",
        graph_set_id="gs-1",
        result_kind=kind,
        run_id=f"run-{graph_iri}",
        result_graph_iri=graph_iri,
        source_signature="sig",
        status=status,
        became_current_at=datetime(2026, 1, 1, tzinfo=UTC),
        pointer_metadata=metadata,
    )
    session.add(pointer)
    return pointer


def test_list_candidates_returns_only_superseded_reasoning(gc_service, in_memory_session) -> None:
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        in_memory_session,
        graph_iri=f"{PREFIX}reasoning-result/old",
        status="superseded",
        superseded_at=superseded_at,
    )
    _seed_pointer(
        in_memory_session,
        graph_iri=f"{PREFIX}reasoning-result/current",
        status="current",
    )
    in_memory_session.commit()
    candidates = gc_service.list_candidates()
    assert [c["graph_iri"] for c in candidates] == [f"{PREFIX}reasoning-result/old"]


def test_execute_dry_run_does_not_call_clear(gc_service) -> None:
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        gc_service.session,
        graph_iri=f"{PREFIX}reasoning-result/old",
        status="superseded",
        superseded_at=superseded_at,
    )
    gc_service.session.commit()

    result = gc_service.execute(dry_run=True)
    assert result["dry_run"] is True
    assert result["deleted_count"] == 1
    assert gc_service.rdf_store.cleared == []


def test_execute_deletes_eligible_superseded(gc_service) -> None:
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        gc_service.session,
        graph_iri=f"{PREFIX}reasoning-result/old",
        status="superseded",
        superseded_at=superseded_at,
    )
    gc_service.session.commit()

    result = gc_service.execute(dry_run=False)
    assert result["deleted_count"] == 1
    assert gc_service.rdf_store.cleared == [f"{PREFIX}reasoning-result/old"]


def test_execute_does_not_delete_current(gc_service) -> None:
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        gc_service.session,
        graph_iri=f"{PREFIX}reasoning-result/current",
        status="current",
        superseded_at=superseded_at,
    )
    gc_service.session.commit()

    result = gc_service.execute()
    assert result["candidate_count"] == 0
    assert result["deleted_count"] == 0
    assert gc_service.rdf_store.cleared == []


def test_execute_refuses_unsupported_target_kind(gc_service) -> None:
    with pytest.raises(GraphGcError):
        gc_service.execute(target_kind="rule_result")


def test_execute_protects_source_graph_iris(gc_service) -> None:
    """Even if a non-derived category slips in, GC must refuse to delete it."""
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        gc_service.session,
        graph_iri=f"{PREFIX}data/demo",  # Not a reasoning-result graph
        status="superseded",
        superseded_at=superseded_at,
    )
    gc_service.session.commit()

    result = gc_service.execute()
    assert result["deleted_count"] == 0
    assert result["errors"]
    assert gc_service.rdf_store.cleared == []


def test_recent_runs_are_persisted(gc_service) -> None:
    superseded_at = datetime.now(UTC) - timedelta(days=1)
    _seed_pointer(
        gc_service.session,
        graph_iri=f"{PREFIX}reasoning-result/old",
        status="superseded",
        superseded_at=superseded_at,
    )
    gc_service.session.commit()
    gc_service.execute()
    runs = gc_service.list_recent_runs()
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].deleted_count == 1
