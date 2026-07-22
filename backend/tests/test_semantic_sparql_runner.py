import os
import uuid

import pytest
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_sparql_runner import (
    SparqlCountResult,
    SparqlGuardError,
    run_select_count,
)


class _FakeSparqlResult:
    def __init__(self, bindings):
        self.result = {"results": {"bindings": bindings}}
        self.result_format = "application/sparql-results+json"


class _FakeStore:
    def __init__(self, bindings=None):
        self._bindings = bindings or []
        self.last_query = None
        self.last_timeout = None
        self.last_limit = None

    def query_sparql(self, query, timeout_seconds, limit):
        self.last_query = query
        self.last_timeout = timeout_seconds
        self.last_limit = limit
        return _FakeSparqlResult(self._bindings)


def _count_binding(value):
    return {"count": {"value": str(value), "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}


def test_run_select_count_returns_count():
    store = _FakeStore(bindings=[_count_binding(5)])
    result = run_select_count(
        store=store,
        query="SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }",
        graph_iris=["https://x/g"],
        timeout_seconds=5,
    )
    assert isinstance(result, SparqlCountResult)
    assert result.count == 5
    assert "FROM <https://x/g>" in store.last_query
    assert "FROM NAMED <https://x/g>" in store.last_query
    assert store.last_query.startswith("SELECT (COUNT(*) AS ?count)")


def test_run_select_count_rejects_construct():
    store = _FakeStore()
    with pytest.raises(SparqlGuardError, match="only SELECT allowed"):
        run_select_count(
            store=store,
            query="CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_insert():
    store = _FakeStore()
    with pytest.raises(SparqlGuardError, match="only SELECT allowed"):
        run_select_count(
            store=store,
            query="INSERT DATA { <a> <b> <c> }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_ask():
    store = _FakeStore()
    with pytest.raises(SparqlGuardError, match="only SELECT allowed"):
        run_select_count(
            store=store,
            query="ASK { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_load_keyword():
    store = _FakeStore()
    with pytest.raises(SparqlGuardError, match="only SELECT allowed"):
        run_select_count(
            store=store,
            query="SELECT * WHERE { ?s ?p ?o } LOAD <file:data>",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_missing_count_column():
    store = _FakeStore(bindings=[{"foo": {"value": "1"}}])
    with pytest.raises(SparqlGuardError, match="missing count"):
        run_select_count(
            store=store,
            query="SELECT (COUNT(*) AS ?foo) WHERE { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_empty_result_is_zero():
    store = _FakeStore(bindings=[])
    result = run_select_count(
        store=store,
        query="SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
        graph_iris=["https://x/g"],
        timeout_seconds=5,
    )
    assert result.count == 0


@pytest.mark.parametrize(
    "query",
    [
        "SELECT (COUNT(*) AS ?count)",
        "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o ",
    ],
)
def test_run_select_count_rejects_missing_or_malformed_where_group(query):
    with pytest.raises(SparqlGuardError):
        run_select_count(
            store=_FakeStore(),
            query=query,
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_unsafe_graph_iri():
    with pytest.raises(SparqlGuardError, match="safe scoped SPARQL"):
        run_select_count(
            store=_FakeStore(),
            query="SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }",
            graph_iris=["https://x/g> } #"],
            timeout_seconds=5,
        )


@pytest.mark.skipif(
    os.environ.get("RUN_OXIGRAPH_SPARQL_RUNNER_TESTS") != "1",
    reason="requires a running local Oxigraph server",
)
def test_run_select_count_scopes_real_oxigraph_queries_to_authorized_graphs():
    """Exercise the generated CQ query shapes against the real SPARQL parser."""
    store = RdfStoreRepository(os.environ.get("OXIGRAPH_URL", "http://127.0.0.1:7878"))
    token = uuid.uuid4().hex
    allowed_graph = f"http://ontology-platform.test/sparql-runner/{token}/allowed"
    denied_graph = f"http://ontology-platform.test/sparql-runner/{token}/denied"
    class_iri = f"http://ontology-platform.test/sparql-runner/{token}/Workflow"
    predicate_iri = f"http://ontology-platform.test/sparql-runner/{token}/hasNode"
    allowed_subject = f"http://ontology-platform.test/sparql-runner/{token}/allowed-subject"
    denied_subject = f"http://ontology-platform.test/sparql-runner/{token}/denied-subject"

    try:
        store.update_sparql(
            "INSERT DATA { "
            f"GRAPH <{allowed_graph}> {{ "
            f"<{allowed_subject}> a <{class_iri}> ; <{predicate_iri}> <{allowed_subject}/node> . "
            "} "
            f"GRAPH <{denied_graph}> {{ "
            f"<{denied_subject}> a <{class_iri}> ; <{predicate_iri}> <{denied_subject}/node> . "
            "} }"
        )

        entity_count = run_select_count(
            store=store,
            query=(
                "SELECT (COUNT(DISTINCT ?e) AS ?count) WHERE { "
                "GRAPH ?g { ?e a/"
                f"<http://www.w3.org/2000/01/rdf-schema#subClassOf>* <{class_iri}> }} "
                "}"
            ),
            graph_iris=[allowed_graph],
            timeout_seconds=5,
        )
        relation_count = run_select_count(
            store=store,
            query=(
                "SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE { "
                f"GRAPH ?g {{ ?s <{predicate_iri}> ?o }} "
                "}"
            ),
            graph_iris=[allowed_graph],
            timeout_seconds=5,
        )
        user_sparql_count = run_select_count(
            store=store,
            query=(
                "SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE { "
                f"GRAPH <{denied_graph}> {{ ?s <{predicate_iri}> ?o }} "
                "}"
            ),
            graph_iris=[allowed_graph],
            timeout_seconds=5,
        )

        assert entity_count.count == 1
        assert relation_count.count == 1
        assert user_sparql_count.count == 0
    finally:
        store.update_sparql(f"CLEAR GRAPH <{allowed_graph}>")
        store.update_sparql(f"CLEAR GRAPH <{denied_graph}>")
