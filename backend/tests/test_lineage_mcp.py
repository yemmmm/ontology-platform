"""MCP contract and compatibility coverage for R-005 lineage."""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel, SemanticEditAuditModel
from app.repositories.rdf_store import RdfGraphDelta
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None
    return tool


def _seed(session):
    settings = Settings(semantic_graph_iri_prefix="https://lineage-mcp.test/graph/")
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    workspace = OntologyWorkspaceService(session, settings).context(ontology.id)
    graph = next(
        member["graph_iri"] for member in workspace["members"] if member["role"] == "asserted_data"
    )
    session.add(
        SemanticEditAuditModel(
            id="audit",
            actor="agent",
            reason="seed",
            input_format="canonical-write",
            target_graph_iri=graph,
            affected_graph_iris=[graph],
            graph_delta={},
            applied=True,
        )
    )
    occurrence = SemanticLineageRecorder(session).record_asserted_delta(
        delta=RdfGraphDelta(
            inserts=[
                (
                    "<https://lineage-mcp.test/entity/alice>",
                    "<https://lineage-mcp.test/property/name>",
                    '"Alice"',
                    graph,
                )
            ]
        ),
        graph_revisions={graph: 1},
        audit_id="audit",
        ontology_id=ontology.id,
        graph_set_id=workspace["default_graph_set_id"],
    )[0]
    session.commit()
    return workspace["default_graph_set_id"], occurrence.statement_id


def test_mcp_new_and_deprecated_tools_share_service_semantics(
    in_memory_session, monkeypatch
) -> None:
    graph_set_id, statement_id = _seed(in_memory_session)
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))
    new = _tool("get_ontology_lineage").fn(
        ontology_id="o",
        target_type="statement",
        target_id=statement_id,
        include_history=False,
        max_depth=3,
        limit=100,
    )
    assert new["ok"] is True, new
    assert new["data"]["target"]["type"] == "statement"
    assert new["data"]["evidence_status"] == "missing"

    compatibility = _tool("inspect_semantic_statement_provenance").fn(
        graph_set_id=graph_set_id,
        statement_iri="https://lineage-mcp.test/entity/alice",
        include="asserted",
    )
    assert compatibility["ok"] is True, compatibility
    assert compatibility["data"]["deprecated"] is True
    assert compatibility["data"]["replacement_tool"] == "get_ontology_lineage"
    assert compatibility["data"]["items"][0]["statement_id"] == statement_id

    missing = _tool("get_ontology_lineage").fn(
        ontology_id="o",
        target_type="statement",
        target_id="0" * 64,
        include_history=False,
        max_depth=3,
        limit=100,
    )
    assert missing["ok"] is False
    assert missing["error_code"] == "not_found"


def test_mcp_schema_has_bounded_business_scope_only() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["get_ontology_lineage"].inputSchema
    assert set(schema["required"]) == {"ontology_id", "target_type", "target_id"}
    assert {"graph_set_id", "graph_iri"}.isdisjoint(schema["properties"])
