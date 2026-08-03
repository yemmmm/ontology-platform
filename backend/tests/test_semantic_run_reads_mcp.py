"""R2.3-005 MCP read-only validation/reasoning-run carrier checks."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

import app.mcp.tools.semantic as semantic_tools
from app.mcp.runtime import MCP_TOOL_POLICIES, McpOwnership
from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel, SemanticGraphSetModel


RUN_TOOLS = {
    "list_semantic_validation_runs",
    "get_semantic_validation_run",
    "list_semantic_reasoning_runs",
    "get_semantic_reasoning_run",
}


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None, name
    return tool


def _bind_scope(session, monkeypatch, mcp_principal_factory, *, project_id: str = "run-p"):
    session.add(ProjectModel(id=project_id, name=project_id, normalized_label=project_id))
    session.add(OntologyModel(id=f"{project_id}-o", project_id=project_id, name="Run ontology"))
    session.add(
        SemanticGraphSetModel(
            id=f"{project_id}-graph-set",
            name="Run graph set",
            scope_type="ontology",
            scope_id=f"{project_id}-o",
            status="active",
            source_signature="run-source",
        )
    )
    session.commit()
    mcp_principal_factory(session, project_id=project_id, scopes=["read"])
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, None))
    return f"{project_id}-graph-set"


class _ReadOnlyValidationService:
    def __init__(self, expected_graph_set: str, item: dict):
        self.expected_graph_set = expected_graph_set
        self.item = item
        self.calls: list[tuple] = []

    def list_validation_runs(self, *, limit, offset, graph_set_id, kind):
        self.calls.append(("list", limit, offset, graph_set_id, kind))
        assert graph_set_id == self.expected_graph_set
        return [self.item], 4

    def get_validation_run(self, run_id):
        self.calls.append(("get", run_id))
        return self.item

    def run_validation(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("read wrapper must never start validation")


class _ReadOnlyReasoningService:
    def __init__(self, expected_graph_set: str, item: dict):
        self.expected_graph_set = expected_graph_set
        self.item = item
        self.calls: list[tuple] = []

    def list_reasoning_runs(self, *, limit, offset, graph_set_id, kind):
        self.calls.append(("list", limit, offset, graph_set_id, kind))
        assert graph_set_id == self.expected_graph_set
        return [self.item], 3

    def get_reasoning_run(self, run_id):
        self.calls.append(("get", run_id))
        return self.item

    def run_reasoning(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("read wrapper must never start reasoning")


def test_run_read_tools_are_registered_and_read_only() -> None:
    assert RUN_TOOLS <= set(MCP_TOOL_POLICIES)
    for name in RUN_TOOLS:
        policy = MCP_TOOL_POLICIES[name]
        assert policy.required_scope == "read"
        assert policy.ownership is McpOwnership.PROJECT_RESOURCE
        assert policy.mutates_state is False

    properties = {
        name: set(_tool(name).fn.__annotations__)
        for name in RUN_TOOLS
    }
    assert properties["list_semantic_validation_runs"] >= {"graph_set_id", "limit", "offset", "kind"}
    assert properties["get_semantic_validation_run"] >= {"validation_run_id", "graph_set_id"}
    assert properties["list_semantic_reasoning_runs"] >= {"graph_set_id", "limit", "offset", "kind"}
    assert properties["get_semantic_reasoning_run"] >= {"reasoning_run_id", "graph_set_id"}
    assert set(_tool("get_semantic_validation_run").parameters["required"]) == {
        "validation_run_id",
        "graph_set_id",
    }
    assert set(_tool("get_semantic_reasoning_run").parameters["required"]) == {
        "reasoning_run_id",
        "graph_set_id",
    }


def test_validation_list_binds_project_graph_scope_and_filters(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    graph_set_id = _bind_scope(in_memory_session, monkeypatch, mcp_principal_factory)
    item = {"run_id": "validation-1", "graph_set_id": graph_set_id, "status": "succeeded"}
    service = _ReadOnlyValidationService(graph_set_id, item)
    monkeypatch.setattr(semantic_tools, "_validation_service", lambda _session: service)

    result = _tool("list_semantic_validation_runs").fn(
        graph_set_id=graph_set_id,
        limit=2,
        offset=3,
        kind="asserted_only",
    )

    assert result == {
        "ok": True,
        "data": {
            "graph_set_id": graph_set_id,
            "items": [item],
            "total": 4,
        },
    }
    assert service.calls == [("list", 2, 3, graph_set_id, "asserted_only")]


def test_reasoning_list_and_get_are_scope_bound_and_never_run(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    graph_set_id = _bind_scope(in_memory_session, monkeypatch, mcp_principal_factory)
    item = {"run_id": "reasoning-1", "graph_set_id": graph_set_id, "status": "succeeded"}
    service = _ReadOnlyReasoningService(graph_set_id, item)
    monkeypatch.setattr(semantic_tools, "_reasoning_service", lambda _session: service)

    listed = _tool("list_semantic_reasoning_runs").fn(
        graph_set_id=graph_set_id,
        limit=1,
        offset=0,
        kind="consistency",
    )
    fetched = _tool("get_semantic_reasoning_run").fn(
        reasoning_run_id=item["run_id"], graph_set_id=graph_set_id
    )

    assert listed["ok"] is True
    assert listed["data"]["items"] == [item]
    assert listed["data"]["total"] == 3
    assert fetched == {"ok": True, "data": item}
    assert service.calls == [
        ("list", 1, 0, graph_set_id, "consistency"),
        ("get", item["run_id"]),
    ]


def test_run_reads_reject_foreign_scope_and_missing_records(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    graph_set_id = _bind_scope(in_memory_session, monkeypatch, mcp_principal_factory)
    in_memory_session.add(ProjectModel(id="foreign-p", name="foreign-p", normalized_label="foreign-p"))
    in_memory_session.add(OntologyModel(id="foreign-p-o", project_id="foreign-p", name="Foreign"))
    in_memory_session.add(
        SemanticGraphSetModel(
            id="foreign-graph-set",
            name="Foreign graph set",
            scope_type="ontology",
            scope_id="foreign-p-o",
            status="active",
            source_signature="foreign-source",
        )
    )
    in_memory_session.commit()
    foreign_item = {"run_id": "foreign", "graph_set_id": "another-graph-set"}
    validation = _ReadOnlyValidationService(graph_set_id, foreign_item)
    monkeypatch.setattr(semantic_tools, "_validation_service", lambda _session: validation)

    foreign_project = _tool("get_semantic_validation_run").fn(
        validation_run_id=foreign_item["run_id"], graph_set_id="foreign-graph-set"
    )
    assert foreign_project["ok"] is False
    assert foreign_project["error_code"] == "forbidden_scope"
    assert validation.calls == []

    foreign = _tool("get_semantic_validation_run").fn(
        validation_run_id=foreign_item["run_id"], graph_set_id=graph_set_id
    )
    assert foreign["ok"] is False
    assert foreign["error_code"] == "forbidden_scope"

    class _Missing:
        def get_reasoning_run(self, _run_id):
            raise ValueError("Reasoning run not found")

    monkeypatch.setattr(semantic_tools, "_reasoning_service", lambda _session: _Missing())
    missing = _tool("get_semantic_reasoning_run").fn(
        reasoning_run_id="missing", graph_set_id=graph_set_id
    )
    assert missing["ok"] is False
    assert missing["error_code"] == "validation_error"
