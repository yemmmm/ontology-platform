from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.repositories.models import SemanticGraphStateModel
from app.repositories.rdf_store import DatasetLoadResult, UpdateResult
from app.services.semantic import LockedSemanticGraph, ReadOnlySparqlViolation, SemanticService


GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"


class FakeSession:
    def __init__(self) -> None:
        self.objects = []
        self.commits = 0

    def add(self, obj) -> None:
        self.objects.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def scalar(self, statement):
        for obj in self.objects:
            if isinstance(obj, SemanticGraphStateModel) and obj.graph_iri == GRAPH:
                return obj
        return None


class FakeRdfStore:
    def __init__(self) -> None:
        self.updates = []
        self.loaded = []

    def query_sparql(self, query, timeout_seconds, limit):
        return SimpleNamespace(result={"ok": True}, result_format="json", truncated=False)

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()

    def load_dataset(self, content, format):
        self.loaded.append((content, format))
        return DatasetLoadResult(loaded=True, format=format, graph_count=1, triple_count=2)

    def export_dataset(self, format, graph_iris=None):
        return Path("tests/fixtures/semantic/tiny.trig").read_text(encoding="utf-8")


def test_load_trig_query_and_export_round_trip_boundary() -> None:
    store = FakeRdfStore()
    service = SemanticService(FakeSession(), store, Settings())

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


def test_read_sparql_rejects_write_forms() -> None:
    service = SemanticService(FakeSession(), FakeRdfStore(), Settings())

    with pytest.raises(ReadOnlySparqlViolation):
        service.query_sparql("INSERT DATA { <s> <p> <o> }")


def test_locked_graph_rejects_edit_without_mutation() -> None:
    session = FakeSession()
    session.add(SemanticGraphStateModel(id="state", graph_iri=GRAPH, editable=False))
    store = FakeRdfStore()
    service = SemanticService(session, store, Settings())

    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    with pytest.raises(LockedSemanticGraph):
        service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)

    assert store.updates == []


def test_turtle_edit_builds_insert_data_update() -> None:
    store = FakeRdfStore()
    service = SemanticService(FakeSession(), store, Settings())

    turtle = Path("tests/fixtures/semantic/tiny.ttl").read_text(encoding="utf-8")
    result = service.apply_edit("turtle", turtle, target_graph_iri=GRAPH, validate=False)

    assert result["applied"] is True
    assert result["affected_graph_iris"] == [GRAPH]
    assert store.updates
    assert "INSERT DATA" in store.updates[0]
