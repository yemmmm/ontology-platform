from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import RdfStoreUnavailable, SparqlQueryTimeout, SparqlResult
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.scoped_sparql_query import ScopedSparqlQueryService
from app.services.semantic_context_query import SemanticContextQueryService
from app.services.semantic_query_scope import SemanticQueryScopeResolver


def test_context_and_sparql_mcp_schemas_use_public_scope_only():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    context = tools["query_semantic_context"].inputSchema
    sparql = tools["semantic_sparql_query"].inputSchema
    for schema in (context, sparql):
        properties = schema["properties"]
        assert {"project_id", "scope_mode", "ontology_ids", "query"} <= set(properties)
        assert "graph_set_id" not in properties
        assert "graph_iri" not in properties

    assert context["properties"]["depth"]["default"] == 1
    assert context["properties"]["limit"]["default"] == 20


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None
    return tool


@pytest.fixture()
def scoped_mcp(in_memory_session, monkeypatch, mcp_principal_factory):
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")
    in_memory_session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session)
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))

    def install(store):
        monkeypatch.setattr(
            "app.mcp.tools.semantic._scoped_sparql_service",
            lambda session: ScopedSparqlQueryService(
                SemanticQueryScopeResolver(session, settings), store, settings
            ),
        )

    return install


class EmptyStore:
    def query_sparql(self, query, timeout_seconds, limit):
        return SparqlResult(
            result={"head": {}, "boolean": False},
            result_format="application/sparql-results+json",
        )


@pytest.mark.parametrize(
    "invalid",
    [
        {"timeout_seconds": 0, "result_limit": 1},
        {"timeout_seconds": 1, "result_limit": 0},
        {"timeout_seconds": 1, "result_limit": -1},
    ],
)
def test_sparql_mcp_rejects_invalid_bounds_in_shared_service(scoped_mcp, invalid):
    scoped_mcp(EmptyStore())

    result = _tool("semantic_sparql_query").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="ASK { ?s ?p ?o }",
        **invalid,
    )

    assert result["ok"] is False
    assert result["error_code"] == "invalid_query"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SparqlQueryTimeout("timed out"), "query_timeout"),
        (RdfStoreUnavailable("offline"), "query_unavailable"),
    ],
)
def test_sparql_mcp_preserves_runtime_error_codes(scoped_mcp, error, code):
    class FailingStore:
        def query_sparql(self, query, timeout_seconds, limit):
            raise error

    scoped_mcp(FailingStore())
    result = _tool("semantic_sparql_query").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="ASK { ?s ?p ?o }",
    )

    assert result["ok"] is False
    assert result["error_code"] == code


def test_context_mcp_keeps_bilingual_asserted_label_exactness(scoped_mcp, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")
    graph = "https://mcp.test/graph/ontology/o"

    class BilingualStore:
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={
                    "head": {"vars": []},
                    "results": {
                        "bindings": [
                            {
                                "graph": {"type": "uri", "value": graph},
                                "subject": {
                                    "type": "uri",
                                    "value": "https://example.test/CustomerSupportWorkflow",
                                },
                                "predicate": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/2000/01/rdf-schema#label",
                                },
                                "object": {
                                    "type": "literal",
                                    "value": "客户支持工作流",
                                    "xml:lang": "zh",
                                },
                                "subjectLabel": {
                                    "type": "literal",
                                    "value": "Customer Support Workflow",
                                    "xml:lang": "en",
                                },
                                "subjectTypes": {
                                    "type": "literal",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                                "matchedField": {"type": "literal", "value": "label"},
                                "matchedValue": {
                                    "type": "literal",
                                    "value": "客户支持工作流",
                                },
                            }
                        ]
                    },
                },
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.mcp.tools.semantic._context_query_service",
        lambda session: SemanticContextQueryService(
            session,
            BilingualStore(),
            SemanticQueryScopeResolver(session, settings),
        ),
    )
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall",
        lambda *_args, **_kwargs: {
            "candidates": [],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    result = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="客户支持工作流",
        resource_types=["concept"],
        depth=0,
    )

    assert result["ok"] is True
    body = result["data"]
    assert body["recall"]["match_status"] == "exact"
    assert body["primary_matches"][0]["label"] == "客户支持工作流"
    assert body["primary_matches"][0]["match"]["reasons"] == ["exact_label"]
