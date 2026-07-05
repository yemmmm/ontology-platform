"""Phase 4 graph set service: membership, source signature, staleness."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
)
from app.services.semantic_graph_set import (
    GraphSetError,
    GraphSetNotFound,
    SemanticGraphSetService,
)


PREFIX = "http://ontology-platform.local/semantic/graph/"


@pytest.fixture
def service(in_memory_session):
    return SemanticGraphSetService(in_memory_session, Settings())


def _member(graph_iri: str, role: str, sort_order: int = 0) -> dict:
    return {
        "graph_iri": graph_iri,
        "role": role,
        "required": True,
        "sort_order": sort_order,
        "metadata": {},
    }


def test_create_graph_set_persists_members_and_signature(service, in_memory_session) -> None:
    graph_set = service.create_graph_set(
        name="working-version:v1",
        scope_type="version",
        scope_id="v1",
        members=[
            _member(f"{PREFIX}ontology/demo", "asserted_ontology", 0),
            _member(f"{PREFIX}data/demo", "asserted_data", 1),
        ],
        created_by="agent:test",
    )

    assert graph_set.id
    assert graph_set.source_signature
    description = service.describe(graph_set.id)
    assert len(description["members"]) == 2
    assert description["members"][0]["role"] == "asserted_ontology"


def test_signature_changes_when_source_revisions_change(service, in_memory_session) -> None:
    graph_set = service.create_graph_set(
        name="gs",
        scope_type="version",
        scope_id="v1",
        members=[_member(f"{PREFIX}data/demo", "asserted_data")],
    )
    signature_before = graph_set.source_signature

    in_memory_session.add(
        SemanticGraphRevisionModel(id="rev-1", graph_iri=f"{PREFIX}data/demo", revision=3)
    )
    in_memory_session.commit()

    signature_after = service.source_signature_for(graph_set.id)
    assert signature_after != signature_before


def test_update_membership_marks_dependent_pointers_stale(service, in_memory_session) -> None:
    graph_set = service.create_graph_set(
        name="gs",
        scope_type="version",
        scope_id="v1",
        members=[_member(f"{PREFIX}data/demo", "asserted_data")],
    )
    in_memory_session.add(
        SemanticDerivedResultPointerModel(
            id="ptr-1",
            graph_set_id=graph_set.id,
            result_kind="reasoning",
            run_id="r1",
            result_graph_iri=f"{PREFIX}reasoning-result/r1",
            source_signature=graph_set.source_signature,
            status="current",
        )
    )
    in_memory_session.commit()

    service.update_membership(
        graph_set.id,
        [_member(f"{PREFIX}data/demo", "asserted_data"), _member(f"{PREFIX}data/extra", "asserted_data")],
    )

    rows = service._current_pointers(graph_set.id)  # noqa: SLF001
    assert rows[0]["status"] == "stale"


def test_create_requires_members(service) -> None:
    with pytest.raises(GraphSetError):
        service.create_graph_set(
            name="empty",
            scope_type="version",
            scope_id="v1",
            members=[],
        )


def test_get_unknown_raises_graph_set_not_found(service) -> None:
    with pytest.raises(GraphSetNotFound):
        service.describe("missing-id")


def test_describe_lists_revisions_per_member(service, in_memory_session) -> None:
    graph_set = service.create_graph_set(
        name="gs",
        scope_type="version",
        scope_id="v1",
        members=[_member(f"{PREFIX}data/demo", "asserted_data")],
    )
    in_memory_session.add(
        SemanticGraphRevisionModel(id="rev-1", graph_iri=f"{PREFIX}data/demo", revision=2)
    )
    in_memory_session.commit()
    description = service.describe(graph_set.id)
    assert description["members"][0]["revision"] == 2


def test_supersedes_marks_prior_set_superseded(service) -> None:
    prior = service.create_graph_set(
        name="gs-v1",
        scope_type="version",
        scope_id="v1",
        members=[_member(f"{PREFIX}data/demo", "asserted_data")],
    )
    service.create_graph_set(
        name="gs-v1",
        scope_type="version",
        scope_id="v1",
        members=[_member(f"{PREFIX}data/demo", "asserted_data")],
        supersedes=prior.id,
    )
    assert service.get_graph_set(prior.id).status == "superseded"
