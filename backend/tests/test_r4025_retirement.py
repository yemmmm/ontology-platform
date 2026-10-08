"""R4.0-025 retirement, ordinary knowledge and recoverable write contracts."""
import asyncio
import importlib.util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.semantic import router
from app.core.config import Settings
from app.mcp.server import mcp
from app.mcp.tools import register_all
from app.mcp.runtime import MCP_TOOL_POLICIES
from app.repositories.models import SemanticValidationRunModel, SemanticReasoningRunModel
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
from app.services.semantic_read_scope import SemanticReadScopeResolver, ReadScopeError
from modeling_team.protocol_mechanics import translate_candidate_to_batches
import test_modeling_batches_service as batches


@pytest.mark.parametrize("method,path", [
    ("POST", "/validation-runs"), ("GET", "/validation-runs"),
    ("GET", "/validation-runs/old"), ("POST", "/reasoning-runs"),
    ("GET", "/reasoning-runs"), ("GET", "/reasoning-runs/old"),
    ("POST", "/ontologies/old/validation-runs"),
    ("POST", "/ontologies/old/reasoning-runs"),
    ("GET", "/ontologies/old/shapes/classes/urn:test"),
    ("POST", "/derived-results:reconcile"),
])
def test_retired_rest_routes_absent_even_with_direct_requests(method, path):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    response = TestClient(app).request(method, "/api/semantic" + path, json={})
    assert response.status_code == 404
    assert not any(term in p for p in app.openapi()["paths"]
                   for term in ("validation-runs", "reasoning-runs", "/shapes/"))


def test_retired_mcp_tools_and_engine_implementations_absent():
    register_all(mcp)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    retired = {"run_semantic_validation", "run_semantic_reasoning",
               "list_semantic_validation_runs", "get_semantic_validation_run",
               "list_semantic_reasoning_runs", "get_semantic_reasoning_run",
               "list_semantic_derived_pointers", "check_semantic_staleness"}
    assert retired.isdisjoint(names)
    assert retired.isdisjoint(MCP_TOOL_POLICIES)
    for module in ("semantic_validation", "semantic_reasoning", "owl_reasoner",
                   "semantic_shape_endpoint_service", "semantic_shape_generator",
                   "business_rule_semantics"):
        assert importlib.util.find_spec("app.services." + module) is None
    assert {"submit_modeling_batch", "get_modeling_context", "query_semantic_context"} <= names


@pytest.mark.parametrize("command", ["create_shape", "update_shape", "delete_shape"])
def test_shape_commands_not_advertised_or_compilable(command):
    registry = ModelingCommandHandlerRegistry(Settings())
    assert command not in registry.command_kinds
    with pytest.raises(InvalidCommandPayload, match="Unsupported Modeling command"):
        registry.prepare(batch_id="b", ontology_id="o", client_item_id="i",
                         command_kind=command, payload={})
    with pytest.raises(Exception, match="Unsupported product command"):
        compile_command(command, {"ontology_id": "o"}, Settings())


@pytest.mark.parametrize("value", [{"script_source": "raise RuntimeError()"}, None, {}])
def test_rule_annotation_rejected_without_silent_loss(value):
    with pytest.raises(InvalidCommandPayload, match="rule_definition is retired"):
        compile_command("create_entity", {"ontology_id": "o", "label": "规则",
                                          "rule_definition": value}, Settings())


def test_bad_fields_and_references_repair_then_apply_without_shape_dependency(in_memory_session):
    service, db, rdf, session_id, lease, version = batches.modeling.__wrapped__(in_memory_session)
    for key, payload in [("missing", {}), ("bad-type", {"label": "规则", "properties": []}),
                         ("retired", {"label": "规则", "rule_definition": {}})]:
        result = service.submit(session_id, batches._request(
            version, [batches._item(key, command_kind="create_entity", payload=payload)],
            key=key, batch=key))
        assert result["attempt_status"] == "validation_failed"
        assert result["findings"][0]["client_item_ids"] == [key]
    unresolved = batches._item("reference", command_kind="create_entity", payload={
        "label": "规则", "class_iri_or_legacy_id": {"item_ref": "absent", "output": "resource_id"}})
    result = service.submit(session_id, batches._request(version, [unresolved],
                                                         key="reference", batch="reference"))
    assert result["attempt_status"] == "validation_failed"
    assert rdf.deltas == []
    rule = batches._item("rule", command_kind="create_entity", payload={
        "entity_id": "rule", "label": "工单关闭规则",
        "semantic_definition": {"semantic_role": "rule",
            "business_meaning": "未验收工单不能关闭；SLA 从报修时间开始计时",
            "applicability": "工单", "conflicting_meanings": ["超时例外待确认"]},
    })
    dry = service.submit(session_id, batches._request(version, [rule], key="fixed-dry", batch="fixed"))
    assert dry["attempt_status"] == "validated", dry["findings"]
    applied = service.submit(session_id, batches._request(version, [rule], key="fixed-apply",
        batch="fixed", mode="apply_atomic", token=lease["lease_token"]))
    assert applied["attempt_status"] == "applied", applied["findings"]
    assert len(rdf.deltas) == 1
    assert any("未验收工单不能关闭" in q[2] for q in rdf.deltas[0].inserts)
    assert db.query(SemanticValidationRunModel).count() == 0
    assert db.query(SemanticReasoningRunModel).count() == 0


def test_historical_derived_graphs_excluded_and_records_preserved(in_memory_session):
    from single_model_support import seed_model
    from app.repositories.models import SemanticDerivedResultPointerModel
    seed_model(in_memory_session, "gs-1")
    in_memory_session.add(SemanticDerivedResultPointerModel(id="ptr-reasoning", ontology_id="gs-1", result_kind="reasoning", run_id="old", result_graph_iri="urn:old-result", status="current"))
    in_memory_session.commit()
    resolver = SemanticReadScopeResolver(in_memory_session)
    scope = resolver.resolve("gs-1", include="full-working-view")
    assert scope.reasoning_result_graph_iri is None
    assert scope.shape_graph_iris == []
    assert scope.derived_state == {}
    assert scope.warnings == []
    assert in_memory_session.get(SemanticDerivedResultPointerModel, "ptr-reasoning") is not None
    with pytest.raises(ReadScopeError, match="Unsupported include"):
        resolver.resolve("gs-1", include="asserted-plus-reasoning")


def test_protocol_retired_artifacts_return_item_local_conflict():
    def candidate(semantic, kind="entity"):
        return {"candidate_kind": "platform-neutral-candidate-v3", "candidate_revision": "r1",
                "scope": "approved", "constraints": [], "items": [
                    {"item_id": "rule", "item_kind": kind, "semantic": semantic}]}
    for value in (candidate({"rule_definition": {}}), candidate({"shape_id": "s"}, "shape")):
        conflicts = translate_candidate_to_batches(value)["conflicts"]
        assert conflicts[0]["item_id"] == "rule"
        assert conflicts[0]["code"] == "retired_modeling_capability"


def test_export_has_no_dedicated_shape_or_reasoning_branch():
    import inspect
    from app.services.semantic_ontology_export import SemanticExportService
    from app.services.semantic_read_scope import ScopeResolution
    from test_semantic_export_graph_set import FakeScopeResolver, FakeStore
    scope = ScopeResolution(ontology_id="g", source_signature="s", include="full-working-view",
        model_graph_iris=[], shape_graph_iris=["https://old.test/shapes"],
        governance_graph_iris=[], reasoning_result_graph_iri="https://old.test/reasoning-result",
        derived_state={"reasoning": {"status": "current"}})
    assert "include_shapes" not in inspect.signature(SemanticExportService.export).parameters
    store = FakeStore({})
    service = SemanticExportService(store, FakeScopeResolver(scope), Settings())
    payload, warnings = service.export("g", "trig", include="full-working-view")
    assert store.requested == []
    assert "old.test" not in payload
    assert warnings == []
