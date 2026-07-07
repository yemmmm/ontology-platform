from pathlib import Path

import pytest

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


GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"
RESULT_GRAPH = "http://ontology-platform.local/semantic/graph/reasoning-result/r1"


class FakeRdfStore:
    def __init__(self) -> None:
        self.updates = []
        self.loaded = []

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
        return False

    def get_graph(self, graph_iri, format):
        return ""

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
    in_memory_session.add(
        SemanticGraphStateModel(id="state", graph_iri=GRAPH, editable=False)
    )
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
