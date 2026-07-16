from __future__ import annotations

import pytest
from rdflib import Graph
from rdflib.plugins.sparql.parser import parseQuery

from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.scoped_sparql_query import (
    ScopedSparqlQueryError,
    ScopedSparqlQueryService,
    enforce_top_level_limit,
    inject_dataset_clauses,
    validate_read_only_query,
)
from app.services.semantic_query_scope import SemanticQueryScopeResolver


class ScopedStore:
    def __init__(self, result=None) -> None:
        self.calls = []
        self.result = result

    def query_sparql(self, query, timeout_seconds, limit):
        self.calls.append((query, timeout_seconds, limit))
        return self.result or SparqlResult(
            result={"head": {"vars": ["s"]}, "results": {"bindings": []}},
            result_format="application/sparql-results+json",
        )


def _scope(session, settings):
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    return SemanticQueryScopeResolver(session, settings)


@pytest.mark.parametrize(
    ("query", "query_type"),
    [
        ("SELECT * WHERE { ?s ?p ?o }", "select"),
        ("ASK { ?s ?p ?o }", "ask"),
        ("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "construct"),
        ("DESCRIBE ?s WHERE { ?s ?p ?o }", "describe"),
    ],
)
def test_read_only_query_forms(query, query_type):
    assert validate_read_only_query(query) == query_type


@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <s> <p> <o> }",
        "DELETE WHERE { ?s ?p ?o }",
        "LOAD <https://example.test/data>",
        "CLEAR ALL",
        "DROP ALL",
        "SELECT * FROM <https://example.test/g> WHERE { ?s ?p ?o }",
        "SELECT * FROM NAMED <https://example.test/g> WHERE { GRAPH ?g { ?s ?p ?o } }",
        "SELECT * WHERE { SERVICE <https://example.test/sparql> { ?s ?p ?o } }",
    ],
)
def test_update_and_dataset_bypass_forms_are_rejected(query):
    with pytest.raises(ScopedSparqlQueryError):
        validate_read_only_query(query)


def test_comments_and_literals_do_not_trigger_forbidden_clause_detection():
    query = '''
    # SERVICE <https://example.test/sparql>
    SELECT ?value WHERE { VALUES ?value { "FROM NAMED SERVICE" } }
    '''
    assert validate_read_only_query(query) == "select"


@pytest.mark.parametrize(
    ("query", "query_type"),
    [
        ("SELECT * WHERE { ?s ?p ?o }", "select"),
        ("SELECT * { ?s ?p ?o }", "select"),
        ("ASK WHERE { ?s ?p ?o }", "ask"),
        ("ASK { ?s ?p ?o }", "ask"),
        ("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "construct"),
        ("CONSTRUCT WHERE { ?s ?p ?o }", "construct"),
        ("DESCRIBE ?s WHERE { ?s ?p ?o }", "describe"),
        ("DESCRIBE <urn:resource>", "describe"),
    ],
)
def test_dataset_injection_is_query_form_aware(query, query_type):
    scoped = inject_dataset_clauses(
        query,
        ["urn:allowed:one", "urn:allowed:two"],
        query_type=query_type,
    )

    assert scoped.count("FROM <urn:allowed:one>") == 1
    assert scoped.count("FROM NAMED <urn:allowed:one>") == 1
    assert scoped.count("FROM <urn:allowed:two>") == 1
    assert scoped.count("FROM NAMED <urn:allowed:two>") == 1
    assert parseQuery(scoped)[1].name.lower().startswith(query_type)


def test_dataset_injection_skips_prologue_comments_strings_and_subquery():
    query = '''
    PREFIX ex: <urn:example:>
    # WHERE { SERVICE <urn:ignored> }
    SELECT ("WHERE { FROM NAMED }" AS ?text) ?s
    WHERE {
      { SELECT ?s WHERE { ?s ex:name "SELECT WHERE" } }
    }
    '''

    scoped = inject_dataset_clauses(query, ["urn:allowed"])

    injected = scoped.index("FROM <urn:allowed>")
    assert injected > scoped.index("SELECT")
    assert injected < scoped.index("WHERE {", injected)
    assert scoped.count("FROM <urn:allowed>") == 1
    assert "{ SELECT ?s WHERE" in scoped


def test_dataset_injection_serializes_server_graph_iris():
    scoped = inject_dataset_clauses(
        "ASK { ?s ?p ?o }",
        ["https://example.test/graphs/allowed"],
    )

    assert "FROM <https://example.test/graphs/allowed>" in scoped
    assert scoped.count("FROM <https://example.test/graphs/allowed>") == 1
    assert scoped.count("FROM NAMED <https://example.test/graphs/allowed>") == 1


def test_dataset_injection_rejects_ambiguous_top_level_form(monkeypatch):
    monkeypatch.setattr(
        "app.services.scoped_sparql_query._scan_tokens",
        lambda _query: [],
    )
    with pytest.raises(ScopedSparqlQueryError):
        inject_dataset_clauses("SELECT * WHERE { ?s ?p ?o }", ["urn:allowed"])


def test_top_level_limit_clamp_ignores_comments_strings_and_subqueries():
    query = '''
    # LIMIT 800
    SELECT ("LIMIT 700" AS ?text) ?s WHERE {
      { SELECT ?s WHERE { ?s ?p ?o } LIMIT 600 }
    }
    LIMIT 500
    '''

    bounded = enforce_top_level_limit(query, max_solutions=2, query_type="select")

    assert "# LIMIT 800" in bounded
    assert '"LIMIT 700"' in bounded
    assert "LIMIT 600" in bounded
    assert "LIMIT 500" not in bounded
    assert bounded.rstrip().endswith("LIMIT 2")
    assert parseQuery(bounded)[1].name == "SelectQuery"


def test_top_level_limit_is_added_when_missing():
    bounded = enforce_top_level_limit(
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
        max_solutions=3,
        query_type="construct",
    )

    assert bounded.endswith("LIMIT 3")
    assert parseQuery(bounded)[1].name == "ConstructQuery"


def test_scoped_service_passes_only_resolved_current_graphs(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    store = ScopedStore()
    service = ScopedSparqlQueryService(_scope(in_memory_session, settings), store, settings)

    result = service.query(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="SELECT * WHERE { GRAPH ?g { ?s ?p ?o } }",
        result_limit=25,
    )

    assert result["query_type"] == "select"
    assert result["scope"]["ontologies"][0]["ontology_id"] == "o"
    executed_query = store.calls[0][0]
    assert executed_query.count("FROM <https://graphs.test/") == 3
    assert executed_query.count("FROM NAMED <https://graphs.test/") == 3
    assert "graph_iri" not in str(result)


def test_select_result_limit_is_hard_even_with_a_larger_caller_limit(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    store = ScopedStore(
        SparqlResult(
            result={
                "head": {"vars": ["s"]},
                "results": {
                    "bindings": [
                        {"s": {"type": "uri", "value": f"urn:item:{index}"}}
                        for index in range(3)
                    ]
                },
            },
            result_format="application/sparql-results+json",
        )
    )
    service = ScopedSparqlQueryService(_scope(in_memory_session, settings), store, settings)

    result = service.query(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="SELECT ?s WHERE { ?s ?p ?o } LIMIT 100",
        result_limit=1,
    )

    assert len(result["result"]["results"]["bindings"]) == 1
    assert result["truncated"] is True
    assert "LIMIT 100" not in store.calls[0][0]
    assert store.calls[0][0].rstrip().endswith("LIMIT 2")


@pytest.mark.parametrize(
    "query",
    [
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } LIMIT 100",
        "DESCRIBE ?s WHERE { ?s ?p ?o } LIMIT 100",
    ],
)
def test_graph_result_limit_is_a_hard_triple_limit(in_memory_session, query):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    turtle = "\n".join(
        f"<urn:item:{index}> <urn:property> \"{index}\" ." for index in range(3)
    )
    store = ScopedStore(SparqlResult(result=turtle, result_format="text/turtle"))
    service = ScopedSparqlQueryService(_scope(in_memory_session, settings), store, settings)

    result = service.query(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query=query,
        result_limit=1,
    )

    bounded = Graph()
    bounded.parse(data=result["result"], format="turtle")
    assert len(bounded) == 1
    assert result["truncated"] is True
    assert "LIMIT 100" not in store.calls[0][0]
    assert store.calls[0][0].rstrip().endswith("LIMIT 2")


def test_ask_and_exact_graph_limit_do_not_report_false_truncation(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    ask_store = ScopedStore(
        SparqlResult(
            result={"head": {}, "boolean": True},
            result_format="application/sparql-results+json",
        )
    )
    ask = ScopedSparqlQueryService(
        _scope(in_memory_session, settings), ask_store, settings
    ).query(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="ASK { ?s ?p ?o }",
        result_limit=1,
    )
    assert ask["result"]["boolean"] is True
    assert ask["truncated"] is False


@pytest.mark.parametrize(
    ("timeout_seconds", "result_limit"),
    [(0, 1), (-1, 1), (121, 1), (1, 0), (1, -1), (1, 10001)],
)
def test_shared_service_rejects_invalid_query_bounds(
    in_memory_session, timeout_seconds, result_limit
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    service = ScopedSparqlQueryService(
        _scope(in_memory_session, settings), ScopedStore(), settings
    )

    with pytest.raises(ScopedSparqlQueryError):
        service.query(
            project_id="p",
            scope_mode="ontologies",
            ontology_ids=["o"],
            query="ASK { ?s ?p ?o }",
            timeout_seconds=timeout_seconds,
            result_limit=result_limit,
        )
