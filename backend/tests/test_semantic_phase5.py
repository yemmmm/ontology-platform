"""Phase 5 service tests: validation, reasoning, CONSTRUCT, DSL, rules."""

from __future__ import annotations

from datetime import UTC, datetime

from typing import Any

import pytest

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
)
from app.repositories.rdf_store import SparqlResult, UpdateResult
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_validation import SemanticValidationService
from app.services.owl_reasoner import OwlReasonerResult, OwlReasonerRunner


PREFIX = "http://ontology-platform.local/semantic/graph/"


class StubReasoner(OwlReasonerRunner):
    def __init__(self, inferred_rdf: str | None = None) -> None:
        self.inferred_rdf = inferred_rdf or (
            "@prefix ex: <http://example.test/> . ex:inferred a ex:Inferred ."
        )

    def run(self, source_documents, tasks, timeout_seconds):
        return OwlReasonerResult(
            consistent=True,
            classification={"classes": ["http://example.test/Student"]},
            entailments=[],
            inferred_rdf=self.inferred_rdf,
        )


class FailingReasoner(OwlReasonerRunner):
    def run(self, source_documents, tasks, timeout_seconds):
        raise RuntimeError("reasoner failed")


class FakeStore:
    def __init__(
        self,
        *,
        construct_result: str = "",
        select_result: dict[str, Any] | None = None,
    ) -> None:
        self.updates: list[str] = []
        self.queries: list[str] = []
        self._graphs: dict[str, str] = {}
        self._exist: set[str] = set()
        self._construct_result = construct_result
        self._select_result = select_result or {
            "head": {"vars": []},
            "results": {"bindings": []},
        }

    def get_graph(self, graph_iri: str, format: str) -> str:
        return self._graphs.get(graph_iri, "")

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._graphs[graph_iri] = content
        self._exist.add(graph_iri)

    def update_sparql(self, update: str) -> UpdateResult:
        self.updates.append(update)
        return UpdateResult()

    def query_sparql(self, query: str, timeout_seconds: float, limit: int) -> SparqlResult:
        self.queries.append(query)
        if "CONSTRUCT" in query.upper():
            return SparqlResult(result=self._construct_result)
        return SparqlResult(result=self._select_result)

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._exist


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def graph_set_service(in_memory_session, settings):
    return SemanticGraphSetService(in_memory_session, settings)


@pytest.fixture
def derived_service(in_memory_session, settings):
    return SemanticDerivedStateService(in_memory_session, settings)


@pytest.fixture
def validation_service(in_memory_session, settings, graph_set_service):
    return SemanticValidationService(
        in_memory_session, FakeStore(), settings, graph_set_service=graph_set_service
    )


def _seed_graph_set(in_memory_session, graph_set_service, members):
    return graph_set_service.create_graph_set(
        name="gs",
        scope_type="version",
        scope_id="v1",
        members=[
            {"graph_iri": iri, "role": role, "sort_order": idx, "required": True}
            for idx, (iri, role) in enumerate(members)
        ],
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validation_persists_graph_set_metadata_and_engine_version(
    in_memory_session, graph_set_service, validation_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session,
        graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data"), (f"{PREFIX}shape/demo", "shape")],
    )
    result = validation_service.run_validation(
        data_graph_iris=[f"{PREFIX}data/demo"],
        shape_graph_iris=[f"{PREFIX}shape/demo"],
        graph_set_id=graph_set.id,
        shape_version="sha256:abc",
        persist_report_graph=True,
    )
    assert result["status"] == "succeeded"
    assert result["graph_set_id"] == graph_set.id
    assert result["shape_version"] == "sha256:abc"
    assert result["engine_version"].startswith("pyshacl=")
    assert result["report_graph_iri"].endswith(result["run_id"])
    assert "violations" in result["summary"]


def test_validation_record_marks_stale_when_signature_changes(
    in_memory_session, graph_set_service, validation_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session,
        graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data"), (f"{PREFIX}shape/demo", "shape")],
    )
    validation_service.run_validation(
        data_graph_iris=[f"{PREFIX}data/demo"],
        shape_graph_iris=[f"{PREFIX}shape/demo"],
        graph_set_id=graph_set.id,
    )
    # Mutate membership to change the source signature.
    graph_set_service.update_membership(
        graph_set.id,
        [
            {"graph_iri": f"{PREFIX}data/demo", "role": "asserted_data"},
            {"graph_iri": f"{PREFIX}shape/demo", "role": "shape"},
            {"graph_iri": f"{PREFIX}data/extra", "role": "asserted_data"},
        ],
    )
    runs, total = validation_service.list_validation_runs()
    assert runs
    assert total == 1
    latest = runs[0]
    assert latest["staleness"]["stale"] is True
    assert latest["staleness"]["reason"] in {
        "source_signature_mismatch",
        "input_graph_revisions_changed",
    }


def test_validation_requires_reasoning_result_for_asserted_plus_reasoning(
    in_memory_session, graph_set_service, validation_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session,
        graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data")],
    )
    with pytest.raises(ValueError):
        validation_service.run_validation(
            data_graph_iris=[f"{PREFIX}data/demo"],
            shape_graph_iris=[],
            graph_set_id=graph_set.id,
            validation_scope="asserted_plus_reasoning",
        )


# ---------------------------------------------------------------------------
# Reasoning
# ---------------------------------------------------------------------------


def test_reasoning_does_not_promote_pointer_on_failure(
    in_memory_session, graph_set_service, derived_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session, graph_set_service,
        [(f"{PREFIX}ontology/demo", "asserted_ontology")],
    )
    settings = Settings()
    store = FakeStore()
    service = SemanticReasoningService(
        in_memory_session,
        store,
        settings,
        reasoner=FailingReasoner(),
        graph_set_service=graph_set_service,
        derived_state_service=derived_service,
    )
    result = service.run_reasoning(
        [f"{PREFIX}ontology/demo"],
        ["consistency"],
        persist_result_graph=True,
        graph_set_id=graph_set.id,
    )
    assert result["status"] == "failed"
    pointer = derived_service.current_pointer(graph_set.id, "reasoning")
    assert pointer is None
    assert store.updates == []  # no result graph written


def test_reasoning_records_input_revisions_and_preserves_archived_rule_pointers(
    in_memory_session, graph_set_service, derived_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session,
        graph_set_service,
        [(f"{PREFIX}ontology/demo", "asserted_ontology")],
    )
    settings = Settings()
    store = FakeStore()
    service = SemanticReasoningService(
        in_memory_session,
        store,
        settings,
        reasoner=StubReasoner(),
        graph_set_service=graph_set_service,
        derived_state_service=derived_service,
    )
    archive = SemanticDerivedResultPointerModel(
        id="archive-rule-pointer", graph_set_id=graph_set.id, result_kind="rule",
        run_id="rule-pre-existing", result_graph_iri=f"{PREFIX}rule-result/archive",
        source_signature=graph_set.source_signature, status="current",
    )
    in_memory_session.add(archive)
    in_memory_session.commit()
    result = service.run_reasoning(
        [f"{PREFIX}ontology/demo"],
        ["consistency"],
        persist_result_graph=True,
        graph_set_id=graph_set.id,
        engine_version="hermit:1.4",
    )
    assert result["status"] == "succeeded"
    assert result["input_graph_revisions"] == {}
    assert result["engine_version"] == "hermit:1.4"
    assert in_memory_session.get(SemanticDerivedResultPointerModel, archive.id).status == "current"
    assert {p.result_kind for p in derived_service.list_pointers(graph_set_id=graph_set.id)} == {"reasoning"}


# ---------------------------------------------------------------------------
# CONSTRUCT
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DSL
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rule execution flow + pointer promotion + staleness
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Construct only writes to result graph
# ---------------------------------------------------------------------------


def test_reasoning_stub_identity_and_warning_are_preserved_in_response_and_reads(
    in_memory_session, graph_set_service, derived_service,
):
    class DeclaredStub(StubReasoner):
        def run(self, source_documents, tasks, timeout_seconds):
            result = super().run(source_documents, tasks, timeout_seconds)
            result.classification["mode"] = "development_stub"
            result.metadata = {
                "engine_name": "development_stub", "engine_version": "dev",
                "warning": "Development stub only; no OWL DL reasoning was performed.",
            }
            return result

    graph_set = _seed_graph_set(in_memory_session, graph_set_service, [(f"{PREFIX}data/demo", "asserted_data")])
    service = SemanticReasoningService(
        in_memory_session, FakeStore(), Settings(), reasoner=DeclaredStub(),
        graph_set_service=graph_set_service, derived_state_service=derived_service,
    )
    result = service.run_reasoning([f"{PREFIX}data/demo"], ["consistency"], graph_set_id=graph_set.id)
    stored = service.get_reasoning_run(result["run_id"])
    listed, total = service.list_reasoning_runs()
    assert total == 1
    for view in (result, stored, listed[0]):
        assert view["status"] == "succeeded"
        assert view["profile"] == "owl2_dl"
        assert view["implementation_mode"] == "development_stub"
        assert view["engine_name"] == "development_stub"
        assert view["engine_version"] == "dev"
        assert view["warnings"] == ["Development stub only; no OWL DL reasoning was performed."]


@pytest.mark.parametrize("classification,mode,warning", [
    ({"mode": "development_stub"}, "development_stub", "No OWL DL reasoning was performed."),
    ({}, None, None),
])
def test_historical_reasoning_read_keeps_declared_mode_or_unknown(
    in_memory_session, classification, mode, warning,
):
    from app.api.schemas import SemanticReasoningRunRead
    from app.repositories.models import SemanticReasoningRunModel

    metadata = {"profile": "owl2_dl", "classification": classification, "warnings": []}
    if warning:
        metadata["warning"] = warning
    run = SemanticReasoningRunModel(
        id="historical-reasoning", source_graph_iris=[], reasoner="historic-command",
        status="succeeded", consistent=True, started_at=datetime(2026, 7, 6, tzinfo=UTC),
        run_metadata=metadata,
    )
    in_memory_session.add(run)
    in_memory_session.commit()
    view = SemanticReasoningService(in_memory_session, FakeStore(), Settings()).get_reasoning_run(run.id)
    response = SemanticReasoningRunRead(**view).model_dump()
    assert response["implementation_mode"] == mode
    assert response["engine_name"] is None
    assert response["warnings"] == ([warning] if warning else [])
