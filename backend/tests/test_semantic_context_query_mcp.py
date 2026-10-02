from __future__ import annotations

import asyncio
from typing import Any

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
            lambda session, project_id=None: ScopedSparqlQueryService(
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
        lambda session, project_id=None: SemanticContextQueryService(
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


def test_context_mcp_strips_unknown_shape_lineage_marker(scoped_mcp, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")
    graph = "https://mcp.test/graph/ontology/o"

    class CandidateStore:
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
                                    "value": "https://example.test/Workflow",
                                },
                                "predicate": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                                },
                                "object": {
                                    "type": "uri",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                                "subjectLabel": {
                                    "type": "literal",
                                    "value": "Workflow",
                                },
                                "subjectTypes": {
                                    "type": "literal",
                                    "value": "http://www.w3.org/2002/07/owl#Class",
                                },
                            }
                        ]
                    },
                },
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.mcp.tools.semantic._context_query_service",
        lambda session, project_id=None: SemanticContextQueryService(
            session,
            CandidateStore(),
            SemanticQueryScopeResolver(session, settings),
        ),
    )

    def invalid_shape_items(self, primary, scope, *, limit):  # noqa: ARG001
        return [
            {
                "id": "shape-hash",
                "kind": "fact",
                "ontology_id": "o",
                "iri": None,
                "label": "custom property",
                "aliases": [],
                "description": None,
                "data": {
                    "target_class": "https://example.test/Workflow",
                    "constraint": {"path": "relative/property", "provenance": "custom"},
                },
                "distance": 1,
                "assertion_kind": "asserted",
                "match": {
                    "score": 275,
                    "matched_terms": [],
                    "matched_fields": ["constraint"],
                    "reasons": ["shape_constraint"],
                },
                "_lineage_target": {
                    "target_type": "synthetic",
                    "target_id": "shape-hash",
                },
            }
        ][:limit]

    monkeypatch.setattr(SemanticContextQueryService, "_shape_constraint_items", invalid_shape_items)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    scoped_mcp(EmptyStore())
    result = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="workflow",
        resource_types=["concept", "fact"],
        depth=1,
        context_limit=1,
        context_detail="full",
    )

    assert result["ok"] is True
    related = result["data"]["related_context"]
    assert len(related) == 1
    shape_item = related[0]
    assert "_lineage_target" not in shape_item
    assert "target_kind" not in shape_item
    assert "lineage" not in shape_item
    assert shape_item["warnings"] == []


# ---------------------------------------------------------------------------
# R1.2-004 MCP-level multi-expression Context Query validation and parity.
# ---------------------------------------------------------------------------


def test_mcp_context_query_accepts_canonical_queries(scoped_mcp, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")

    class EmptyCandidates:
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={"head": {"vars": []}, "results": {"bindings": []}},
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.mcp.tools.semantic._context_query_service",
        lambda session, project_id=None: SemanticContextQueryService(
            session,
            EmptyCandidates(),
            SemanticQueryScopeResolver(session, settings),
        ),
    )
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[], []],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    scoped_mcp(EmptyStore())
    result = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        queries=["one", "two"],
        depth=0,
    )
    assert result["ok"] is True
    body = result["data"]
    assert body["query"]["queries"] == ["one", "two"]
    assert body["matches_page"]["returned"] == 0


def test_mcp_context_query_rejects_both_query_and_queries(scoped_mcp):
    scoped_mcp(EmptyStore())
    result = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="x",
        queries=["x"],
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid_query"


def test_mcp_context_query_forwards_refreshed_principal(scoped_mcp, monkeypatch):
    """R1.2-004: MCP must forward the refreshed _authorize_tool principal."""
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")
    captured: dict[str, Any] = {}

    class CapturingStore(EmptyStore):
        def query_sparql(self, query, timeout_seconds, limit):  # noqa: ARG002
            return SparqlResult(
                result={"head": {"vars": []}, "results": {"bindings": []}},
                result_format="application/sparql-results+json",
            )

    monkeypatch.setattr(
        "app.mcp.tools.semantic._context_query_service",
        lambda session, project_id=None: SemanticContextQueryService(
            session,
            CapturingStore(),
            SemanticQueryScopeResolver(session, settings),
        ),
    )
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )

    real_query_multi = SemanticContextQueryService.query_multi

    def wrapper(self, *args, **kwargs):
        captured["principal"] = kwargs.get("principal")
        return real_query_multi(self, *args, **kwargs)

    monkeypatch.setattr(SemanticContextQueryService, "query_multi", wrapper)

    scoped_mcp(EmptyStore())
    result = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="ontologies",
        ontology_ids=["o"],
        query="topic",
        depth=0,
    )
    assert result["ok"] is True
    forwarded = captured.get("principal")
    assert forwarded is not None
    assert forwarded.subject_type == "api_key"


def test_mcp_context_cursor_survives_service_recreation_and_keeps_bindings(
    scoped_mcp, monkeypatch, in_memory_session, mcp_principal_factory
):
    """MCP calls rebuild the service, but continuation uses one process codec."""
    settings = Settings(semantic_graph_iri_prefix="https://mcp.test/graph/")

    def candidates(self, _rows, scope, _text, _terms):  # noqa: ARG001
        return [
            {
                "id": "https://mcp.test/resource/one",
                "kind": "instance",
                "target_kind": "resource",
                "ontology_id": "o",
                "iri": "https://mcp.test/resource/one",
                "label": "one",
                "aliases": [],
                "description": None,
                "data": {},
                "distance": 0,
                "assertion_kind": "asserted",
                "match": {
                    "score": 900,
                    "matched_terms": ["topic"],
                    "matched_fields": ["label"],
                    "reasons": ["exact_label"],
                },
            },
            {
                "id": "https://mcp.test/resource/two",
                "kind": "instance",
                "target_kind": "resource",
                "ontology_id": "o",
                "iri": "https://mcp.test/resource/two",
                "label": "two",
                "aliases": [],
                "description": None,
                "data": {},
                "distance": 0,
                "assertion_kind": "asserted",
                "match": {
                    "score": 800,
                    "matched_terms": ["topic"],
                    "matched_fields": ["label"],
                    "reasons": ["label_contains"],
                },
            },
        ]

    monkeypatch.setattr(
        "app.mcp.tools.semantic._rdf_store",
        lambda: EmptyStore(),
    )
    monkeypatch.setattr(
        "app.mcp.tools.semantic._scope_resolver",
        lambda session: SemanticQueryScopeResolver(session, settings),
    )
    monkeypatch.setattr(SemanticContextQueryService, "_lexical_candidate_rows", lambda *args: [])
    monkeypatch.setattr(SemanticContextQueryService, "_rdf_candidates", candidates)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        lambda *_args, **_kwargs: {
            "candidates_by_query": [[]],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        },
    )
    monkeypatch.setattr("app.mcp.runtime._context_cursor_codec", None)
    scoped_mcp(EmptyStore())

    request = {
        "project_id": "p",
        "scope_mode": "ontologies",
        "ontology_ids": ["o"],
        "query": "topic",
        "resource_types": ["instance"],
        "depth": 0,
        "limit": 1,
    }
    first = _tool("query_semantic_context").fn(**request)
    assert first["ok"] is True
    cursor = first["data"]["matches_page"]["next_match_cursor"]
    assert isinstance(cursor, str) and cursor

    continued = _tool("query_semantic_context").fn(**request, match_cursor=cursor)
    assert continued["ok"] is True
    assert [item["label"] for item in continued["data"]["primary_matches"]] == ["two"]

    changed_query = _tool("query_semantic_context").fn(
        **{**request, "query": "other"}, match_cursor=cursor
    )
    assert changed_query["ok"] is False
    assert changed_query["error_code"] == "context_cursor_mismatch"

    changed_scope = _tool("query_semantic_context").fn(
        project_id="p",
        scope_mode="project",
        query="topic",
        resource_types=["instance"],
        depth=0,
        limit=1,
        match_cursor=cursor,
    )
    assert changed_scope["ok"] is False
    assert changed_scope["error_code"] == "context_cursor_mismatch"

    mcp_principal_factory(in_memory_session, project_id="p", scopes=["read"])
    in_memory_session.commit()
    changed_principal = _tool("query_semantic_context").fn(**request, match_cursor=cursor)
    assert changed_principal["ok"] is False
    assert changed_principal["error_code"] == "context_cursor_mismatch"

    missing_query = _tool("query_semantic_context").fn(
        project_id="p", scope_mode="ontologies", ontology_ids=["o"]
    )
    assert missing_query["ok"] is False
    assert missing_query["error_code"] == "invalid_query"


def test_context_mcp_defaults_to_compact_related_context():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["query_semantic_context"].inputSchema
    detail = schema["properties"]["context_detail"]
    # R2.3-009 (2026-08-21): MCP consumers (Examiner/Protocol) default to the
    # compact related-context projection; REST keeps ``full`` as default.
    assert detail["default"] == "compact"
    assert detail["enum"] == ["full", "compact"]


def test_r4008_mcp_roles_are_forwarded_and_discoverable(scoped_mcp, monkeypatch):
    seen = {}
    class Service:
        def query_multi(self, **arguments):
            seen.update(arguments)
            return {"result_status": "no_match"}
    monkeypatch.setattr("app.mcp.tools.semantic._context_query_service", lambda *args: Service())
    result = asyncio.run(_tool("query_semantic_context").run({
        "project_id": "p", "scope_mode": "ontologies", "ontology_ids": ["o"],
        "queries": ["example"], "semantic_roles": ["Action"], "depth": 0,
    }))
    assert result["ok"] is True
    assert seen["semantic_roles"] == ["Action"]
    assert seen["context_detail"] == "compact"
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert "semantic_roles" in tools["query_semantic_context"].inputSchema["properties"]
