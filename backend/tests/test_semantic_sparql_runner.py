import pytest
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
    assert "VALUES ?g" in store.last_query


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
