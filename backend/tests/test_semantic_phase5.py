"""Phase 5 service tests: validation, reasoning, CONSTRUCT, DSL, rules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticRuleDefinitionModel,
)
from app.repositories.rdf_store import SparqlResult, UpdateResult
from app.services.semantic_construct import (
    ConstructTemplateError,
    execute_construct_template,
    validate_approved_construct,
)
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_dsl import (
    ConstructTemplateError as DslConstructTemplateError,
    compile_dsl_to_select,
    execute_dsl,
)
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_rule_definition import (
    RuleDefinitionError,
    SemanticRuleDefinitionService,
)
from app.services.semantic_rule_execution import (
    RuleExecutionError,
    SemanticRuleExecutionService,
)
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


def test_reasoning_records_input_revisions_and_marks_rule_pointers_stale(
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
    derived_service.promote_rule_pointer(
        graph_set_id=graph_set.id,
        run_id="rule-pre-existing",
        result_graph_iri=f"{PREFIX}rule-result/rule-pre-existing",
        source_signature=graph_set_service.source_signature_for(graph_set.id),
    )
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
    pointers = derived_service.list_pointers(graph_set_id=graph_set.id, result_kind="rule")
    assert pointers
    assert pointers[0].status == "stale"


# ---------------------------------------------------------------------------
# CONSTRUCT
# ---------------------------------------------------------------------------


def test_validate_approved_construct_rejects_service_clause() -> None:
    template = (
        "CONSTRUCT { ?s ?p ?o } WHERE { SERVICE <http://example.test/> { ?s ?p ?o } }"
    )
    with pytest.raises(ConstructTemplateError):
        validate_approved_construct(template)


def test_validate_approved_construct_rejects_property_paths() -> None:
    template = (
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s a/rdfs:subClassOf ?o . }"
    )
    with pytest.raises(ConstructTemplateError):
        validate_approved_construct(template)


def test_validate_approved_construct_rejects_unknown_graph_iris() -> None:
    template = (
        "CONSTRUCT { ?s ?p ?o } "
        "WHERE { GRAPH <http://ontology-platform.local/semantic/graph/data/unknown> "
        "{ ?s ?p ?o } }"
    )
    with pytest.raises(ConstructTemplateError):
        validate_approved_construct(
            template,
            graph_set_iris=["http://ontology-platform.local/semantic/graph/data/known"],
        )


def test_validate_approved_construct_accepts_template_within_graph_set() -> None:
    template = (
        "CONSTRUCT { ?s ?p ?o } "
        "WHERE { GRAPH <http://ontology-platform.local/semantic/graph/data/known> "
        "{ ?s ?p ?o } }"
    )
    result = validate_approved_construct(
        template,
        graph_set_iris=["http://ontology-platform.local/semantic/graph/data/known"],
    )
    assert "CONSTRUCT" in result


def test_execute_construct_template_injects_limit_with_space() -> None:
    """Regression: Oxigraph rejects ``}\\nLIMIT`` — the helper must use a space."""
    store = FakeStore(
        construct_result=(
            "@prefix ex: <http://example.test/> . ex:alice a ex:Person ."
        )
    )
    execute_construct_template(
        store,
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
        graph_set_iris=["http://example.test/"],
        timeout_seconds=5,
        statement_limit=42,
    )
    assert store.queries, "execute_construct_template should issue a SPARQL query"
    sent_query = store.queries[0]
    assert "LIMIT 42" in sent_query
    assert "\nLIMIT" not in sent_query
    assert sent_query.endswith(" LIMIT 42")


def test_execute_construct_writes_only_to_result_graph(
    in_memory_session, graph_set_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session, graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data")],
    )
    settings = Settings()
    store = FakeStore(
        construct_result=(
            "@prefix ex: <http://example.test/> . ex:alice a ex:ExcellentStudent ."
        )
    )
    service = SemanticRuleExecutionService(
        in_memory_session,
        store,
        settings,
        graph_set_service=graph_set_service,
    )
    result = service.execute_construct_template(
        graph_set_id=graph_set.id,
        template=(
            f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{PREFIX}data/demo> {{ ?s ?p ?o }} }}"
        ),
        promote_pointer=True,
    )
    if result["status"] != "succeeded":
        raise AssertionError(f"Expected succeeded, got: {result}")
    assert result["status"] == "succeeded"
    assert result["result_graph_iri"].startswith(f"{PREFIX}rule-result/")
    assert result["derived_pointer"]["status"] == "current"
    assert f"INSERT DATA {{ GRAPH <{PREFIX}data/demo>" not in "\n".join(store.updates)
    assert any(f"INSERT DATA {{ GRAPH <{PREFIX}rule-result/" in u for u in store.updates)


# ---------------------------------------------------------------------------
# DSL
# ---------------------------------------------------------------------------


def test_dsl_compile_rejects_unsupported_filter_operator() -> None:
    body = {
        "when": [
            {"s": "?s", "p": "?p", "o": "?o"},
            {"filter": {"regex": ["?s", "ex:Student"]}},
        ],
        "then": [{"s": "?s", "p": "ex:label", "o": '"hi"'}],
    }
    with pytest.raises(ConstructTemplateError):
        compile_dsl_to_select(
            body,
            graph_set_iris=[f"{PREFIX}data/demo"],
            statement_limit=10,
        )


def test_dsl_compile_rejects_unknown_output_predicate_when_no_graph_set() -> None:
    body = {
        "when": [{"s": "?s", "p": "?p", "o": "?o"}],
        "then": [{"s": "?s", "p": "?p", "o": "?o"}],
    }
    with pytest.raises(ConstructTemplateError):
        compile_dsl_to_select(body, graph_set_iris=[], statement_limit=10)


def test_dsl_execute_returns_deterministic_statements(in_memory_session) -> None:
    body = {
        "when": [
            {"s": "?student", "p": "<http://example.test/score>", "o": "?score"},
            {"filter": {"gte": ["?score", 90]}},
        ],
        "then": [
            {
                "s": "?student",
                "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                "o": "<http://example.test/ExcellentStudent>",
            }
        ],
        "explain": "Excellent student threshold reached",
    }

    class _Stub:
        def query_sparql(self, query: str, timeout_seconds: float, limit: int):
            return SparqlResult(
                result={
                    "head": {"vars": ["student", "score"]},
                    "results": {
                        "bindings": [
                            {
                                "student": {"value": "<http://example.test/alice>"},
                                "score": {"value": "95"},
                            }
                        ]
                    },
                }
            )

    execution = execute_dsl(
        _Stub(),
        body,
        graph_set_iris=[f"{PREFIX}data/demo"],
        timeout_seconds=5,
        statement_limit=10,
    )
    assert len(execution.statements) == 1
    assert execution.statements[0]["s"] == "<http://example.test/alice>"
    assert (
        execution.statements[0]["o"] == "<http://example.test/ExcellentStudent>"
    )
    assert execution.statements[0]["explanation"] == "Excellent student threshold reached"


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------


def test_rule_definition_validates_construct_template(in_memory_session) -> None:
    settings = Settings()
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    with pytest.raises(RuleDefinitionError):
        service.create_rule(
            rule_iri=f"{PREFIX}rule/bad",
            name="bad",
            language="sparql_construct",
            body={"template": "SELECT * WHERE { ?s ?p ?o }"},
            input_roles=["asserted_data"],
        )


def test_rule_definition_validates_platform_dsl_filter(in_memory_session) -> None:
    settings = Settings()
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    with pytest.raises(RuleDefinitionError):
        service.create_rule(
            rule_iri=f"{PREFIX}rule/dsl-bad",
            name="dsl-bad",
            language="platform_dsl",
            body={
                "when": [{"filter": {"regex": ["?s", "x"]}}],
                "then": [],
            },
            input_roles=["asserted_data"],
        )


def test_rule_definition_creates_new_version_for_new_body(
    in_memory_session, graph_set_service
) -> None:
    settings = Settings()
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    rule = service.create_rule(
        rule_iri=f"{PREFIX}rule/dsl",
        name="dsl",
        language="platform_dsl",
        body={
            "when": [
                {"s": "?s", "p": "<http://example.test/p>", "o": "?o"},
            ],
            "then": [
                {
                    "s": "?s",
                    "p": "<http://example.test/derived>",
                    "o": "?o",
                }
            ],
        },
        input_roles=["asserted_data"],
    )
    second = service.create_rule(
        rule_iri=f"{PREFIX}rule/dsl",
        name="dsl",
        language="platform_dsl",
        body={
            "when": [
                {"s": "?s", "p": "<http://example.test/p>", "o": "?o"},
            ],
            "then": [
                {
                    "s": "?s",
                    "p": "<http://example.test/derived>",
                    "o": "?o",
                }
            ],
            "explain": "updated",
        },
        input_roles=["asserted_data"],
    )
    assert second.version != rule.version
    assert second.id != rule.id


# ---------------------------------------------------------------------------
# Rule execution flow + pointer promotion + staleness
# ---------------------------------------------------------------------------


def test_rule_execution_promotes_pointer_and_supersedes_previous(
    in_memory_session, graph_set_service, derived_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session, graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data")],
    )
    settings = Settings()
    rule_service = SemanticRuleDefinitionService(in_memory_session, settings)
    rule = rule_service.create_rule(
        rule_iri=f"{PREFIX}rule/excellent",
        name="excellent",
        language="platform_dsl",
        body={
            "when": [
                {"s": "?s", "p": "<http://example.test/score>", "o": "?score"},
                {"filter": {"gte": ["?score", 90]}},
            ],
            "then": [
                {
                    "s": "?s",
                    "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                    "o": "<http://example.test/ExcellentStudent>",
                }
            ],
        },
        input_roles=["asserted_data"],
    )
    derived_service.promote_rule_pointer(
        graph_set_id=graph_set.id,
        run_id="prior-rule-run",
        result_graph_iri=f"{PREFIX}rule-result/prior",
        source_signature=graph_set_service.source_signature_for(graph_set.id),
    )
    store = FakeStore(
        select_result={
            "head": {"vars": ["student", "score"]},
            "results": {
                "bindings": [
                    {
                        "student": {"value": "<http://example.test/alice>"},
                        "score": {"value": "95"},
                    }
                ]
            },
        }
    )
    service = SemanticRuleExecutionService(
        in_memory_session,
        store,
        settings,
        graph_set_service=graph_set_service,
        derived_state_service=derived_service,
    )
    result = service.execute_rule(
        graph_set_id=graph_set.id,
        rule_definition_id=rule.id,
        promote_pointer=True,
    )
    assert result["status"] == "succeeded"
    assert result["derived_pointer"]["status"] == "current"
    pointers = derived_service.list_pointers(graph_set_id=graph_set.id, result_kind="rule")
    assert len(pointers) == 2
    statuses = {pointer.status for pointer in pointers}
    assert statuses == {"current", "superseded"}


def test_rule_pointer_becomes_stale_when_reasoning_pointer_promoted(
    in_memory_session, graph_set_service, derived_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session, graph_set_service,
        [(f"{PREFIX}ontology/demo", "asserted_ontology")],
    )
    settings = Settings()
    derived_service.promote_rule_pointer(
        graph_set_id=graph_set.id,
        run_id="rr1",
        result_graph_iri=f"{PREFIX}rule-result/rr1",
        source_signature=graph_set_service.source_signature_for(graph_set.id),
    )
    reasoning = SemanticReasoningService(
        in_memory_session,
        FakeStore(),
        settings,
        reasoner=StubReasoner(),
        graph_set_service=graph_set_service,
        derived_state_service=derived_service,
    )
    reasoning.run_reasoning(
        [f"{PREFIX}ontology/demo"],
        ["consistency"],
        persist_result_graph=True,
        graph_set_id=graph_set.id,
    )
    rule_pointer = derived_service.list_pointers(
        graph_set_id=graph_set.id, result_kind="rule"
    )
    assert rule_pointer
    assert rule_pointer[0].status == "stale"
    assert rule_pointer[0].pointer_metadata["stale_reason"] == "upstream_reasoning_pointer_changed"


# ---------------------------------------------------------------------------
# Construct only writes to result graph
# ---------------------------------------------------------------------------


def test_construct_rejects_template_referencing_graphs_outside_graph_set(
    in_memory_session, graph_set_service
) -> None:
    graph_set = _seed_graph_set(
        in_memory_session, graph_set_service,
        [(f"{PREFIX}data/demo", "asserted_data")],
    )
    settings = Settings()
    service = SemanticRuleExecutionService(
        in_memory_session,
        FakeStore(),
        settings,
        graph_set_service=graph_set_service,
    )
    with pytest.raises(RuleExecutionError):
        service.execute_construct_template(
            graph_set_id=graph_set.id,
            template=(
                "CONSTRUCT { ?s ?p ?o } WHERE { "
                f"GRAPH <{PREFIX}data/other> {{ ?s ?p ?o }} }}"
            ),
        )
