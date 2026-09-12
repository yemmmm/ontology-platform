"""MCP contract and compatibility coverage for R-005 lineage."""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.mcp.server import mcp
from app.repositories.models import (
    BuildSessionModel,
    ModelingBatchModel,
    ModelingItemModel,
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
)
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
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    graph_set_id, statement_id = _seed(in_memory_session)
    mcp_principal_factory(in_memory_session)
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


def _seed_created_item(session) -> str:
    """Seed a resource asserted by a create item, and return that resource IRI.

    The structural triple is the one a create item really produces (an ``rdf:type``
    assertion), and its only origin is the ``modeling_item``: exactly the shape the
    auth010 start4 terminal gate failed on (item ``e80f85b1``), where the owner-answer
    evidence could not be re-posted through the staged channel.
    """

    settings = Settings(semantic_graph_iri_prefix="https://lineage-mcp.test/graph/")
    session.add(ProjectModel(id="p2", name="P2", normalized_label="p2"))
    ontology = OntologyModel(id="o2", project_id="p2", name="O2")
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
            id="audit-item",
            actor="agent",
            reason="create item",
            input_format="canonical-write",
            target_graph_iri=graph,
            affected_graph_iris=[graph],
            graph_delta={},
            applied=True,
        )
    )
    session.add(
        BuildSessionModel(
            id="session",
            project_id="p2",
            client_session_id="client-2",
            create_request_hash="3" * 64,
        )
    )
    session.add(
        ModelingBatchModel(
            id="batch",
            project_id="p2",
            ontology_id="o2",
            build_session_id="session",
            client_batch_id="batch-client-2",
            content_hash="4" * 64,
            status="applied",
        )
    )
    item = ModelingItemModel(
        id="item",
        batch_id="batch",
        client_item_id="customer",
        ordinal=0,
        command_kind="create_class",
        payload={"name": "Customer"},
        rationale="the owner described customers as parties",
        competency_question_ids=[],
    )
    session.add(item)
    resource = "https://lineage-mcp.test/class/customer"
    quad = (
        f"<{resource}>",
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
        "<http://www.w3.org/2002/07/owl#Class>",
        graph,
    )
    SemanticLineageRecorder(session).record_asserted_delta(
        delta=RdfGraphDelta(inserts=[quad]),
        graph_revisions={graph: 1},
        audit_id="audit-item",
        ontology_id=ontology.id,
        graph_set_id=workspace["default_graph_set_id"],
        modeling_item_effects={quad: [item.id]},
    )
    session.commit()
    return resource


def test_mcp_evidence_repost_satisfies_a_created_items_lineage_gate(
    in_memory_session, monkeypatch, mcp_principal_factory
) -> None:
    """The staged evidence repost must be able to satisfy the terminal retrieval gate.

    ``protocol_staged_associate_evidence`` only carries this call across to the host; the
    gate itself is satisfied by the platform association it produces.  This is the
    backend half of that lock: the one assertion a staged run could not complete before
    the projection existed.
    """

    resource = _seed_created_item(in_memory_session)
    mcp_principal_factory(in_memory_session)
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))

    def lineage() -> dict:
        return _tool("get_ontology_lineage").fn(
            ontology_id="o2",
            target_type="resource",
            target_id=resource,
            include_history=False,
            max_depth=3,
            limit=100,
        )

    before = lineage()
    assert before["ok"] is True, before
    item = before["data"]["items"][0]
    assert item["statement"]["predicate"] == (
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    )
    item_origins = {
        origin["kind"]: origin for origin in item["origins"] if origin["kind"] == "modeling_item"
    }
    assert item_origins["modeling_item"]["id"] == "item"
    assert before["data"]["evidence_status"] == "missing"

    repost = _tool("associate_evidence_reference").fn(
        project_id="p2",
        ontology_id="o2",
        target_type="modeling_item",
        target_id="item",
        evidence=[
            {
                "document_name": "owner-answer-2026-09-12.md",
                "excerpt": "The owner confirmed that customers are a kind of party.",
            }
        ],
    )
    assert repost["ok"] is True, repost
    assert repost["data"]["total"] == 1

    after = lineage()
    assert after["ok"] is True, after
    assert after["data"]["evidence_status"] == "supported"
    assert after["data"]["items"][0]["evidence_status"] == "supported"

    # Replay safety: the staged forwarder may retry the identical association after an
    # indeterminate reply, and the (target, reference) uniqueness makes that a no-op.
    replayed = _tool("associate_evidence_reference").fn(
        project_id="p2",
        ontology_id="o2",
        target_type="modeling_item",
        target_id="item",
        evidence=[
            {
                "document_name": "owner-answer-2026-09-12.md",
                "excerpt": "The owner confirmed that customers are a kind of party.",
            }
        ],
    )
    assert replayed["ok"] is True, replayed
    assert replayed["data"]["total"] == 1
    assert lineage()["data"]["evidence_status"] == "supported"


def test_mcp_schema_has_bounded_business_scope_only() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["get_ontology_lineage"].inputSchema
    assert set(schema["required"]) == {"ontology_id", "target_type", "target_id"}
    assert {"graph_set_id", "graph_iri"}.isdisjoint(schema["properties"])
