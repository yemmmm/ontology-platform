from pathlib import Path
import json

import pytest
from rdflib import Literal

from app.core.config import Settings
from app.repositories.models import (
    SemanticEditAuditModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphStateModel,
)
from app.repositories.rdf_store import DatasetLoadResult, SparqlResult, UpdateResult
from app.services.semantic import (
    LockedSemanticGraph,
    ReadOnlySparqlViolation,
    SemanticGraphPolicyViolation,
    SemanticService,
    UnsupportedSemanticEdit,
)
from app.services.operation_semantics import operation_quads, operation_vocabulary


GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"
RESULT_GRAPH = "http://ontology-platform.local/semantic/graph/reasoning-result/r1"


class FakeRdfStore:
    def __init__(self, graphs: dict[str, str] | None = None) -> None:
        self.updates = []
        self.loaded = []
        self.graphs = graphs or {}

    def query_sparql(self, query, timeout_seconds, limit):
        return SparqlResult(result={"ok": True}, result_format="json", truncated=False)

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()

    def load_dataset(self, content, format):
        self.loaded.append((content, format))
        return DatasetLoadResult(loaded=True, format=format, graph_count=1, triple_count=2)

    def export_dataset(self, format, graph_iris=None):
        return Path("tests/fixtures/semantic/tiny.trig").read_text(encoding="utf-8")

    def graph_exists(self, graph_iri):
        return graph_iri in self.graphs

    def get_graph(self, graph_iri, format):
        return self.graphs.get(graph_iri, "")

    def clear_graph(self, graph_iri):
        return UpdateResult()

    def graph_content_hash(self, graph_iri):
        return None


@pytest.fixture()
def settings():
    return Settings()


@pytest.fixture()
def service(in_memory_session, settings):
    return SemanticService(in_memory_session, FakeRdfStore(), settings)


def test_load_trig_query_and_export_round_trip_boundary(in_memory_session, settings) -> None:
    store = FakeRdfStore()
    service = SemanticService(in_memory_session, store, settings)

    trig = Path("tests/fixtures/semantic/tiny.trig").read_text(encoding="utf-8")
    load_result = service.load_dataset(trig, "trig")
    query_result = service.query_sparql(
        "SELECT ?s WHERE { GRAPH <http://ontology-platform.local/semantic/graph/data/demo> { ?s ?p ?o } }",
        timeout_seconds=3,
        result_limit=10,
    )
    exported = service.export_dataset("trig", [GRAPH])

    assert load_result.loaded is True
    assert store.loaded[0][1] == "trig"
    assert query_result.result == {"ok": True}
    assert "http://ontology-platform.local/semantic/graph/data/demo" in exported


def test_read_sparql_rejects_write_forms(service) -> None:
    with pytest.raises(ReadOnlySparqlViolation):
        service.query_sparql("INSERT DATA { <s> <p> <o> }")


def test_locked_graph_rejects_edit_without_mutation(in_memory_session, settings) -> None:
    in_memory_session.add(SemanticGraphStateModel(id="state", graph_iri=GRAPH, editable=False))
    in_memory_session.commit()
    store = FakeRdfStore()
    service = SemanticService(in_memory_session, store, settings)

    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    with pytest.raises(LockedSemanticGraph):
        service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)

    assert store.updates == []


def test_turtle_edit_builds_insert_data_update(service, in_memory_session) -> None:
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    result = service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)

    assert result["applied"] is True
    assert result["audit_id"]
    assert result["affected_graph_iris"] == [GRAPH]
    assert service.rdf_store.updates
    assert "INSERT DATA" in service.rdf_store.updates[0]
    assert result["graph_revisions"][GRAPH] == 1


def test_edit_keeps_committed_fact_when_retrieval_rebuild_fails(
    in_memory_session, settings, monkeypatch
) -> None:
    """A disposable vector failure must not turn a successful RDF edit into a failure."""

    calls = []

    class FailingRetrievalCoordinator:
        def __init__(self, session, rdf_store, settings):  # noqa: ANN001, ARG002
            self.session = session

        def rebuild_affected(self, *, affected_graph_iris=(), ontology_ids=()):
            calls.append((list(affected_graph_iris), list(ontology_ids)))
            return [
                {
                    "ontology_id": "ontology-1",
                    "write_applied": True,
                    "status": "failed",
                    "warning": "retrieval_index_failed",
                }
            ]

    monkeypatch.setattr(
        "app.services.semantic.SemanticRetrievalCoordinator", FailingRetrievalCoordinator
    )
    store = FakeRdfStore()
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")

    result = SemanticService(in_memory_session, store, settings).apply_edit(
        "turtle", turtle, target_graph_iri=GRAPH, validate=False
    )

    assert result["applied"] is True
    assert store.updates
    assert in_memory_session.get(SemanticEditAuditModel, result["audit_id"]) is not None
    assert result["retrieval_indexes"][0]["status"] == "failed"
    assert calls == [([GRAPH], [])]


def test_edit_records_audit_metadata(service, in_memory_session) -> None:
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    result = service.apply_edit(
        "turtle",
        turtle,
        target_graph_iri=GRAPH,
        validate=False,
        actor="agent:test",
        reason="phase3 coverage",
    )

    audit = in_memory_session.get(SemanticEditAuditModel, result["audit_id"])
    assert audit.actor == "agent:test"
    assert audit.reason == "phase3 coverage"
    assert audit.input_format == "turtle"
    assert audit.target_graph_iri == GRAPH
    assert audit.affected_graph_iris == [GRAPH]
    assert audit.graph_delta["inserted_statements"]
    assert "SHACL validation skipped by request" in audit.warning_state["warnings"]


def test_edit_auto_registers_managed_graph_in_registry(service, in_memory_session) -> None:
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    service.apply_edit(
        "turtle",
        turtle,
        target_graph_iri=GRAPH,
        validate=False,
        actor="agent:test",
    )

    record = (
        in_memory_session.query(SemanticGraphRegistryModel)
        .filter(SemanticGraphRegistryModel.graph_iri == GRAPH)
        .one()
    )
    assert record.category == "data"
    assert record.mutable_by_direct_edit is True


def test_edit_rejects_non_direct_editable_category(service) -> None:
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    with pytest.raises(SemanticGraphPolicyViolation):
        service.apply_edit(
            "turtle",
            turtle,
            target_graph_iri=RESULT_GRAPH,
            validate=False,
        )
    assert service.rdf_store.updates == []


def test_edit_increments_revision_per_affected_graph(service, in_memory_session) -> None:
    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    first = service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)
    second = service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)

    assert first["graph_revisions"][GRAPH] == 1
    assert second["graph_revisions"][GRAPH] == 2

    revision = (
        in_memory_session.query(SemanticGraphRevisionModel)
        .filter(SemanticGraphRevisionModel.graph_iri == GRAPH)
        .one()
    )
    assert revision.revision == 2


def test_restricted_delete_insert_where_is_allowed_with_explicit_graphs(service) -> None:
    update = f"""
    DELETE {{ GRAPH <{GRAPH}> {{ ?s <http://example.test/old> ?old }} }}
    INSERT {{ GRAPH <{GRAPH}> {{ ?s <http://example.test/new> ?old }} }}
    WHERE  {{ GRAPH <{GRAPH}> {{ ?s <http://example.test/old> ?old }} }}
    """

    result = service.apply_edit("sparql-update", update, validate=False)

    assert result["applied"] is True
    assert result["delta"]["operation"] == "delete_insert_where"
    assert result["affected_graph_iris"] == [GRAPH]
    assert service.rdf_store.updates == [update]


def test_restricted_delete_insert_where_rejects_variable_graphs(service) -> None:
    update = """
    DELETE { GRAPH ?g { ?s <http://example.test/old> ?old } }
    INSERT { GRAPH ?g { ?s <http://example.test/new> ?old } }
    WHERE  { GRAPH ?g { ?s <http://example.test/old> ?old } }
    """

    with pytest.raises(UnsupportedSemanticEdit):
        service.apply_edit("sparql-update", update, validate=False)


def test_operation_invariant_cannot_be_bypassed_with_validate_false(
    in_memory_session, settings
) -> None:
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/direct-r007"
    operation = {
        "operation_id": "publish",
        "name": "Publish",
        "target_resource_type_iri": "https://example.test/Workflow",
        "parameters": [],
        "preconditions": [],
        "effects": [],
        "possible_failures": [],
        "idempotency": {"kind": "idempotent"},
        "risk_level": "low",
        "tool_bindings": [
            {
                "binding_id": "publish",
                "kind": "http_api",
                "system": "generic",
                "operation_identifier": "POST /publish",
            }
        ],
        "credential_requirements": [],
    }
    quads = operation_quads(operation, settings, "direct-r007")
    vocab = operation_vocabulary(settings)
    secret_literal = Literal(
        json.dumps([{"name": "auth", "reference_type": "api_key", "token": "leak"}]),
        datatype="http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON",
    ).n3()
    credential_predicate = f"<{vocab['credential_requirements']}>"
    turtle = "\n".join(
        [
            "<https://example.test/Workflow> a <http://www.w3.org/2002/07/owl#Class> .",
            *(
                f"{subject} {predicate} "
                f"{secret_literal if predicate == credential_predicate else obj} ."
                for subject, predicate, obj, _graph in quads
            ),
        ]
    )
    store = FakeRdfStore()
    direct = SemanticService(in_memory_session, store, settings)

    with pytest.raises(Exception) as rejected:
        direct.apply_edit("turtle", turtle, target_graph_iri=graph_iri, validate=False)

    assert "operation_secret_forbidden" in str(rejected.value)
    assert "leak" not in str(rejected.value)
    assert store.updates == []


def test_operation_where_edit_fails_closed_before_mutation(in_memory_session, settings) -> None:
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/direct-r007"
    vocab = operation_vocabulary(settings)
    vocab_prefix = vocab["type"].removesuffix("Operation")
    update = f"""
    PREFIX op: <{vocab_prefix}>
    DELETE {{ GRAPH <{graph_iri}> {{ ?operation op:riskLevel ?old }} }}
    INSERT {{ GRAPH <{graph_iri}> {{ ?operation op:riskLevel "high" }} }}
    WHERE  {{ GRAPH <{graph_iri}> {{
      ?operation a op:Operation ; op:riskLevel ?old
    }} }}
    """
    store = FakeRdfStore()

    with pytest.raises(Exception) as rejected:
        SemanticService(in_memory_session, store, settings).apply_edit(
            "sparql-update", update, validate=False
        )

    assert "operation_edit_not_deterministic" in str(rejected.value)
    assert store.updates == []


def test_non_operation_where_edit_on_ontology_graph_remains_allowed(
    in_memory_session, settings
) -> None:
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/direct-r007"
    update = f"""
    DELETE {{ GRAPH <{graph_iri}> {{ ?class <http://example.test/old> ?value }} }}
    INSERT {{ GRAPH <{graph_iri}> {{ ?class <http://example.test/new> ?value }} }}
    WHERE  {{ GRAPH <{graph_iri}> {{ ?class <http://example.test/old> ?value }} }}
    """
    store = FakeRdfStore()

    result = SemanticService(in_memory_session, store, settings).apply_edit(
        "sparql-update", update, validate=False
    )

    assert result["applied"] is True
    assert result["affected_graph_iris"] == [graph_iri]
    assert store.updates == [update]


def test_generic_where_fails_closed_when_current_graph_contains_operation(
    in_memory_session, settings
) -> None:
    ontology_id = "generic-existing-operation"
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{ontology_id}"
    operation = {
        "operation_id": "publish",
        "name": "Publish",
        "target_resource_type_iri": "https://example.test/Workflow",
        "parameters": [],
        "preconditions": [],
        "effects": [],
        "possible_failures": [],
        "idempotency": {"kind": "idempotent"},
        "risk_level": "low",
        "tool_bindings": [
            {
                "binding_id": "publish",
                "kind": "mcp_tool",
                "system": "generic",
                "operation_identifier": "publish_workflow",
            }
        ],
        "credential_requirements": [],
    }
    current_graph = "\n".join(
        [
            "<https://example.test/Workflow> a <http://www.w3.org/2002/07/owl#Class> .",
            *(
                f"{subject} {predicate} {obj} ."
                for subject, predicate, obj, _graph in operation_quads(
                    operation, settings, ontology_id
                )
            ),
        ]
    )
    update = f"""
    DELETE {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?old }} }}
    INSERT {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?new }} }}
    WHERE  {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?old }} }}
    """
    store = FakeRdfStore({graph_iri: current_graph})

    with pytest.raises(Exception) as rejected:
        SemanticService(in_memory_session, store, settings).apply_edit(
            "sparql-update", update, validate=False
        )

    assert "operation_edit_not_deterministic" in str(rejected.value)
    assert store.updates == []


def test_restricted_where_fails_closed_when_current_graph_cannot_be_inspected(
    in_memory_session, settings
) -> None:
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/inspection-failure"
    update = f"""
    DELETE {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?old }} }}
    INSERT {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?new }} }}
    WHERE  {{ GRAPH <{graph_iri}> {{ ?subject ?predicate ?old }} }}
    """

    class InspectionFailureStore(FakeRdfStore):
        def get_graph(self, graph_iri, format):
            raise RuntimeError("store unavailable")

    store = InspectionFailureStore()
    with pytest.raises(Exception) as rejected:
        SemanticService(in_memory_session, store, settings).apply_edit(
            "sparql-update", update, validate=False
        )

    assert "operation_edit_not_deterministic" in str(rejected.value)
    assert store.updates == []


def test_operation_unknown_secret_predicate_is_rejected_before_direct_rdf_write(
    in_memory_session, settings
) -> None:
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/direct-secret"
    operation = {
        "operation_id": "publish",
        "name": "Publish",
        "target_resource_type_iri": "https://example.test/Workflow",
        "parameters": [],
        "preconditions": [],
        "effects": [],
        "possible_failures": [],
        "idempotency": {"kind": "idempotent"},
        "risk_level": "low",
        "tool_bindings": [
            {
                "binding_id": "publish",
                "kind": "mcp_tool",
                "system": "generic",
                "operation_identifier": "publish_workflow",
            }
        ],
        "credential_requirements": [],
    }
    quads = operation_quads(operation, settings, "direct-secret")
    subject = quads[0][0]
    turtle = "\n".join(
        [
            "<https://example.test/Workflow> a <http://www.w3.org/2002/07/owl#Class> .",
            *(f"{s} {p} {o} ." for s, p, o, _graph in quads),
            f'{subject} <{settings.semantic_base_iri.rstrip("/")}/vocab/token> "leak" .',
        ]
    )
    store = FakeRdfStore()

    with pytest.raises(Exception) as rejected:
        SemanticService(in_memory_session, store, settings).apply_edit(
            "turtle", turtle, target_graph_iri=graph_iri, validate=False
        )

    assert "operation_secret_forbidden" in str(rejected.value)
    assert "leak" not in str(rejected.value)
    assert store.updates == []
