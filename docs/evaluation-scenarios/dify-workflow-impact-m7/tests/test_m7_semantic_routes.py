from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import semantic
from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.security.auth import AuthPrincipal


class _GraphSets:
    def describe(self, graph_set_id: str):
        assert graph_set_id == "set"
        return {"id": "set", "status": "active", "source_signature": "sig", "members": [{"graph_iri": "https://m7.test/data", "role": "asserted_data"}, {"graph_iri": "https://m7.test/schema", "role": "asserted_ontology"}, {"graph_iri": "https://m7.test/shapes", "role": "shape"}]}


class _Reasoning:
    def run_reasoning(self, source_graph_iris, tasks, persist_result_graph, **kwargs):
        assert source_graph_iris == ["https://m7.test/data", "https://m7.test/schema"]
        assert tasks == ["consistency"] and persist_result_graph is False and kwargs["graph_set_id"] == "set"
        return {"run_id": "reasoning", "status": "completed", "consistent": True}
    def get_reasoning_run(self, run_id: str):
        assert run_id == "reasoning"
        return {"run_id": run_id, "status": "completed", "consistent": True, "graph_set_id": "set", "source_signature": "sig"}


class _Validation:
    def run_validation(self, **kwargs):
        assert kwargs["data_graph_iris"] == ["https://m7.test/data"]
        assert kwargs["shape_graph_iris"] == ["https://m7.test/shapes"]
        assert kwargs["persist_report_graph"] is False and kwargs["graph_set_id"] == "set"
        return {"run_id": "validation", "status": "completed", "conforms": True, "report_text": None, "summary": {}, "error": None}
    def get_validation_run(self, run_id: str):
        return {"run_id": run_id, "status": "completed", "conforms": True, "graph_set_id": "set", "source_signature": "sig"}


class _Sparql:
    def __init__(self, *args):
        pass
    def query(self, **kwargs):
        assert kwargs["scope_mode"] == "ontologies" and kwargs["ontology_ids"] == ["ontology"]
        return {"result": {"boolean": True}, "result_format": "application/sparql-results+json", "query_type": "ask", "scope": {"project_id": "project", "mode": "ontologies", "status": "complete", "ontologies": [{"ontology_id": "ontology", "ontology_name": "O", "workspace_version": "1", "source_signature": "sig", "derived_state": {}, "warnings": []}], "excluded_ontologies": []}, "truncated": False, "warnings": []}


def test_real_fastapi_pydantic_graph_set_and_scoped_sparql_contracts(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(semantic.router)
    app.dependency_overrides[get_db_session] = lambda: object()
    app.dependency_overrides[get_rdf_store] = lambda: object()
    app.dependency_overrides[get_settings] = lambda: object()
    app.dependency_overrides[semantic.principal_dependency] = lambda: AuthPrincipal("test", "test", "test", frozenset({"admin"}), None, "test")
    monkeypatch.setattr(semantic, "_graph_set_service", lambda *_args: _GraphSets())
    monkeypatch.setattr(semantic, "_reasoning_service", lambda *_args: _Reasoning())
    monkeypatch.setattr(semantic, "_validation_service", lambda *_args: _Validation())
    monkeypatch.setattr(semantic, "ScopedSparqlQueryService", _Sparql)
    client = TestClient(app)
    reasoning = client.post("/semantic/graph-sets/set/reasoning-runs", json={"tasks": ["consistency"], "persist_result_graph": False})
    validation = client.post("/semantic/graph-sets/set/validation-runs", json={"persist_report_graph": False})
    detail_r = client.get("/semantic/reasoning-runs/reasoning")
    detail_v = client.get("/semantic/validation-runs/validation")
    query = client.post("/semantic/sparql:query", json={"project_id": "project", "scope_mode": "ontologies", "ontology_ids": ["ontology"], "query": "ASK WHERE { ?s ?p ?o }", "result_limit": 1})
    assert [response.status_code for response in (reasoning, validation, detail_r, detail_v, query)] == [200] * 5
    assert detail_r.json()["source_signature"] == detail_v.json()["source_signature"] == "sig"
    assert query.json()["scope"]["status"] == "complete"
