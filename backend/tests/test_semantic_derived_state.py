"""Phase 4 derived-state: revisions, pointer promotion, and staleness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.services.semantic_derived_state import (
    SemanticDerivedStateService,
    SemanticRevisionService,
)
from app.services.semantic_graph_set import SemanticGraphSetService


PREFIX = "http://ontology-platform.local/semantic/graph/"


@pytest.fixture
def revision_service(in_memory_session):
    return SemanticRevisionService(in_memory_session)


@pytest.fixture
def derived_service(in_memory_session):
    return SemanticDerivedStateService(in_memory_session, Settings())


@pytest.fixture
def graph_set_service(in_memory_session):
    return SemanticGraphSetService(in_memory_session, Settings())


def _seed_graph_set(in_memory_session, graph_set_service, members=None):
    members = members or [(f"{PREFIX}data/demo", "asserted_data")]
    return graph_set_service.create_graph_set(
        name="gs",
        scope_type="version",
        scope_id="v1",
        members=[
            {"graph_iri": iri, "role": role, "sort_order": idx, "required": True}
            for idx, (iri, role) in enumerate(members)
        ],
    )


def test_bump_revisions_increments_per_graph(revision_service, in_memory_session) -> None:
    bumps = revision_service.bump_revisions(
        [f"{PREFIX}data/demo", f"{PREFIX}ontology/demo"],
        audit_id="audit-1",
        actor="agent:test",
    )
    assert bumps == {f"{PREFIX}data/demo": 1, f"{PREFIX}ontology/demo": 1}
    bumps_again = revision_service.bump_revisions([f"{PREFIX}data/demo"], audit_id="audit-2")
    assert bumps_again == {f"{PREFIX}data/demo": 2}


def test_bump_revisions_records_content_hash(revision_service) -> None:
    revision_service.bump_revisions(
        [f"{PREFIX}data/demo"],
        audit_id="audit-1",
        content_hashes={f"{PREFIX}data/demo": "abc123"},
    )
    record = revision_service.get_revision(f"{PREFIX}data/demo")
    assert record is not None
    assert record.content_hash == "abc123"
    assert record.last_edit_audit_id == "audit-1"


def test_mark_stale_after_edit_flags_only_current_pointers_for_affected_graphs(
    derived_service, graph_set_service, in_memory_session
) -> None:
    graph_set = _seed_graph_set(in_memory_session, graph_set_service)
    signature = graph_set_service.source_signature_for(graph_set.id)
    pointer = _historical_pointer(derived_service,
        graph_set_id=graph_set.id,
        run_id="run-1",
        result_graph_iri=f"{PREFIX}reasoning-result/run-1",
        source_signature=signature,
    )

    stale_rows = derived_service.mark_stale_after_edit(
        [f"{PREFIX}data/demo"], audit_id="audit-1"
    )
    assert len(stale_rows) == 1
    in_memory_session.refresh(pointer)
    assert pointer.status == "stale"
    assert pointer.pointer_metadata["stale_reason"] == "source_graph_revision_changed"
    assert pointer.pointer_metadata["stale_audit_id"] == "audit-1"


def test_mark_stale_after_edit_skips_unrelated_graph_sets(
    derived_service, graph_set_service, in_memory_session
) -> None:
    graph_set = _seed_graph_set(in_memory_session, graph_set_service)
    signature = graph_set_service.source_signature_for(graph_set.id)
    _historical_pointer(derived_service,
        graph_set_id=graph_set.id,
        run_id="run-1",
        result_graph_iri=f"{PREFIX}reasoning-result/run-1",
        source_signature=signature,
    )

    stale_rows = derived_service.mark_stale_after_edit(
        [f"{PREFIX}data/unrelated"], audit_id="audit-2"
    )
    assert stale_rows == []


def _historical_pointer(service, **fields):
    from uuid import uuid4
    row = SemanticDerivedResultPointerModel(id=str(uuid4()), result_kind="reasoning",
        status="current", **fields)
    service.session.add(row)
    service.session.commit()
    return row
