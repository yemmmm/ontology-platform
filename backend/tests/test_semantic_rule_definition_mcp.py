"""R4.0-022: direct legacy REST/MCP and internal commands are retired.

Replaces R1.2-005 executable-definition parity after product retirement.
Ordinary rule entity contracts are covered by test_r4005_business_rule_semantics.
"""
from __future__ import annotations

import asyncio
import importlib.util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.semantic import router
from app.core.config import Settings
from app.mcp.server import mcp
from app.mcp.tools import register_all
from app.repositories.models import SemanticRuleDefinitionModel, SemanticRuleRunModel
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
import test_modeling_batches_service as batches


@pytest.mark.parametrize("method,path", [
    ("get", "/rule-definitions"), ("post", "/rule-definitions"),
    ("get", "/rule-definitions/legacy"), ("patch", "/rule-definitions/legacy"),
    ("delete", "/rule-definitions/legacy"),
    ("post", "/graph-sets/gs/construct-runs"),
    ("post", "/graph-sets/gs/rule-runs"),
    ("get", "/rule-runs"), ("get", "/rule-runs/legacy"),
])
def test_direct_legacy_rest_routes_are_gone(method, path, in_memory_session):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    response = TestClient(app).request(method, "/api/semantic" + path)
    assert response.status_code == 404
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticRuleRunModel)) == 0
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticRuleDefinitionModel)) == 0
    paths = app.openapi()["paths"]
    assert not any("rule-definition" in p or "rule-runs" in p or "construct-runs" in p for p in paths)


def test_retired_mcp_tools_are_not_registered_or_authorized():
    from app.mcp.runtime import MCP_TOOL_POLICIES
    register_all(mcp)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    for name in ("submit_semantic_rule_definition", "run_semantic_rule", "get_semantic_rule_definition"):
        assert name not in names
        assert name not in MCP_TOOL_POLICIES
        assert mcp._tool_manager.get_tool(name) is None
    assert {"query_semantic_context", "run_semantic_validation", "run_semantic_reasoning"} <= names


@pytest.mark.parametrize("command", ["create_rule_definition", "update_rule_definition", "delete_rule_definition"])
def test_legacy_batch_and_canonical_commands_are_unavailable(command, in_memory_session):
    registry = ModelingCommandHandlerRegistry(Settings())
    assert command not in registry.command_kinds
    with pytest.raises(InvalidCommandPayload, match="Unsupported Modeling command"):
        registry.prepare(batch_id="b", ontology_id="o", client_item_id="r", command_kind=command, payload={})
    with pytest.raises(Exception, match="Unsupported.*command"):
        compile_command(command, {"ontology_id": "o"}, Settings())
    service, db, store, session_id, lease, version = batches.modeling.__wrapped__(in_memory_session)
    item = batches._item("r", command_kind=command, payload={})
    response = service.submit(session_id, batches._request(version, [item]))
    assert response["attempt_status"] == "validation_failed"
    assert any("Unsupported Modeling command" in str(f) for f in response["findings"])
    assert store.deltas == []
    assert db.scalar(select(func.count()).select_from(SemanticRuleDefinitionModel)) == 0
    assert db.scalar(select(func.count()).select_from(SemanticRuleRunModel)) == 0


@pytest.mark.parametrize("module", ["semantic_rule_definition", "semantic_rule_execution", "semantic_construct", "semantic_dsl"])
def test_legacy_executor_implementations_have_been_removed(module):
    assert importlib.util.find_spec("app.services." + module) is None


def test_archived_rule_pointers_are_not_live_scopes_counts_or_projection_inputs(in_memory_session):
    from app.services.semantic_derived_state import DerivedStateError, SemanticDerivedStateService
    from app.services.semantic_graph_set import SemanticGraphSetService
    from app.services.semantic_projection_job import SemanticProjectionJobService
    from app.services.semantic_read_scope import ReadScopeError, SemanticReadScopeResolver
    from app.repositories.models import SemanticDerivedResultPointerModel
    from test_semantic_read_scope import _make_graph_set, _add_pointer

    _make_graph_set(in_memory_session, [("http://op/s/graph/data/ov-1", "asserted_data")])
    _add_pointer(in_memory_session, "rule")
    _add_pointer(in_memory_session, "reasoning")
    archived = in_memory_session.get(SemanticDerivedResultPointerModel, "ptr-rule")
    resolver = SemanticReadScopeResolver(in_memory_session)
    scope = resolver.resolve("gs-1", include="full-working-view")
    assert set(scope.derived_state) == {"reasoning"}
    assert not hasattr(scope, "rule_result_graph_iri")
    with pytest.raises(ReadScopeError, match="Unsupported include value"):
        resolver.resolve("gs-1", include="asserted-plus-rules")
    derived = SemanticDerivedStateService(in_memory_session, Settings())
    assert {p.result_kind for p in derived.list_pointers("gs-1")} == {"reasoning"}
    with pytest.raises(DerivedStateError, match="Unsupported result kind"):
        derived.list_pointers("gs-1", result_kind="rule")
    summary = derived.status_summary()
    assert set(summary["derived_pointer_counts"]) == {"reasoning"}
    described = SemanticGraphSetService(in_memory_session, Settings()).describe("gs-1")
    assert {p["result_kind"] for p in described["current_pointers"]} == {"reasoning"}
    projection = SemanticProjectionJobService(in_memory_session, writers={}, scope_resolver_builder=SemanticReadScopeResolver)
    job = projection.create_job("gs-1", "search", "retirement-v1", include="full-working-view")
    assert set(job.input_derived_pointers) == {"reasoning"}
    assert job.rule_result_graph_iri is None
    assert in_memory_session.get(SemanticDerivedResultPointerModel, "ptr-rule") is archived
    assert archived.status == "current"
