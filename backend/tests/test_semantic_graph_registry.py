"""Phase 4 graph registry: IRI classification, registration, and direct-edit policy."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphStateModel,
)
from app.services.semantic_graph_registry import (
    DirectEditCategoryDenied,
    GraphCategory,
    GraphClassification,
    GraphRegistryError,
    SemanticGraphRegistryService,
    UnmanagedGraphIri,
)


PREFIX = "http://ontology-platform.local/semantic/graph/"


@pytest.fixture
def service(in_memory_session):
    return SemanticGraphRegistryService(in_memory_session, Settings())


def test_classifier_returns_every_canonical_category() -> None:
    classifier = GraphClassification(PREFIX)
    cases = {
        f"{PREFIX}ontology/demo": GraphCategory.ONTOLOGY,
        f"{PREFIX}data/demo": GraphCategory.DATA,
        f"{PREFIX}proposal/p1": GraphCategory.PROPOSAL,
        f"{PREFIX}evidence/e1": GraphCategory.EVIDENCE,
        f"{PREFIX}policy/p1": GraphCategory.POLICY,
        f"{PREFIX}import/s1/r1": GraphCategory.IMPORT,
        f"{PREFIX}validation-run/v1": GraphCategory.VALIDATION_RUN,
        f"{PREFIX}reasoning-run/r1": GraphCategory.REASONING_RUN,
        f"{PREFIX}reasoning-result/r1": GraphCategory.REASONING_RESULT,
        f"{PREFIX}rule-run/rr1": GraphCategory.RULE_RUN,
        f"{PREFIX}rule-result/rr1": GraphCategory.RULE_RESULT,
        f"{PREFIX}review/rv1": GraphCategory.REVIEW,
    }
    for graph_iri, expected in cases.items():
        assert classifier.classify(graph_iri) is expected, graph_iri


def test_classifier_marks_unknown_and_unmanaged() -> None:
    classifier = GraphClassification(PREFIX)
    assert classifier.classify(f"{PREFIX}unknown/extra") is GraphCategory.UNKNOWN
    assert classifier.classify("http://other.test/foo") is GraphCategory.UNKNOWN


def test_register_graph_creates_record_with_classified_category(service) -> None:
    record = service.register_graph(
        f"{PREFIX}ontology/demo",
        owner_type="ontology",
        owner_id="ont-1",
        created_by="agent:test",
    )
    assert record.category == "ontology"
    assert record.mutable_by_direct_edit is True


def test_register_graph_rejects_unmanaged_iri(service) -> None:
    with pytest.raises(UnmanagedGraphIri):
        service.register_graph("http://other.test/foo")


def test_direct_edit_only_allowed_for_ontology_data(service) -> None:
    assert (
        service.require_direct_editable_category(f"{PREFIX}ontology/demo")
        is GraphCategory.ONTOLOGY
    )
    assert service.require_direct_editable_category(f"{PREFIX}data/demo") is GraphCategory.DATA
    with pytest.raises(DirectEditCategoryDenied):
        service.require_direct_editable_category(f"{PREFIX}reasoning-result/r1")
    with pytest.raises(DirectEditCategoryDenied):
        service.require_direct_editable_category(f"{PREFIX}evidence/e1")


def test_ensure_registered_for_direct_edit_autoregisters(service) -> None:
    record = service.ensure_registered_for_direct_edit(
        f"{PREFIX}data/demo", actor="agent:test"
    )
    assert record.category == "data"
    assert record.mutable_by_direct_edit is True
    # second call should return the existing record
    record_again = service.ensure_registered_for_direct_edit(
        f"{PREFIX}data/demo", actor="agent:test"
    )
    assert record_again.id == record.id


def test_graph_status_includes_revision_and_editability(service, in_memory_session) -> None:
    graph_iri = f"{PREFIX}ontology/demo"
    in_memory_session.add(
        SemanticGraphRevisionModel(
            id="rev-1", graph_iri=graph_iri, revision=4, content_hash="hash-123"
        )
    )
    in_memory_session.add(
        SemanticGraphStateModel(id="state-1", graph_iri=graph_iri, editable=False, reason="freeze")
    )
    service.register_graph(graph_iri, category="ontology")
    in_memory_session.commit()
    status = service.graph_status(graph_iri)
    assert status["registered"] is True
    assert status["revision"] == 4
    assert status["content_hash"] == "hash-123"
    assert status["editable"] is False
    assert status["editability_reason"] == "freeze"
    assert status["category"] == "ontology"


def test_status_summary_counts_categories(service, in_memory_session) -> None:
    service.register_graph(f"{PREFIX}ontology/demo", category="ontology")
    service.register_graph(f"{PREFIX}ontology/other", category="ontology")
    service.register_graph(f"{PREFIX}data/demo", category="data")
    service.register_graph(f"{PREFIX}reasoning-result/r1", category="reasoning_result")
    in_memory_session.commit()
    summary = service.status_summary()
    assert summary["graph_counts_by_category"]["ontology"] == 2
    assert summary["graph_counts_by_category"]["data"] == 1
    assert summary["graph_counts_by_category"]["reasoning_result"] == 1
    # Three editable actual graphs (no locked state set) and zero locked.
    assert summary["editable_actual_graphs"] == 3
    assert summary["locked_actual_graphs"] == 0


def test_unknown_category_value_raises(service) -> None:
    with pytest.raises(GraphRegistryError):
        service.register_graph(f"{PREFIX}ontology/demo", category="bogus")
