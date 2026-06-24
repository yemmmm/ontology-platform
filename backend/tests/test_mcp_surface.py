import asyncio

from app.mcp.server import mcp
from app.mcp.tools import register_all


ALLOWED_TOOLS = {
    "search_entities",
    "get_entity",
    "find_related_entities",
    "validate_entity",
    "explain_entity",
    "submit_proposal",
    "submit_proposal_json",
    "propose_schema_changes",
    "propose_entities",
    "propose_relations",
    "propose_entity_merges",
    "validate_proposal",
    "validate_draft",
    "get_proposal_status",
    "list_review_items",
    "get_review_batch",
    "get_build_context",
    "get_project_brief",
    "save_interview_answer",
    "update_project_brief",
    "list_competency_questions",
    "propose_competency_questions",
    "validate_competency_question",
    "list_source_documents",
    "get_source_document_status",
    "get_source_document_chunks",
    "generate_fact_claims",
    "list_fact_claims",
    "sample_fact_claims",
    "get_publication_readiness",
}


FORBIDDEN_TOOLS = {
    "approve_proposal",
    "apply_approved_proposal",
    "review_fact_claim",
    "resolve_conflict",
    "publish_version",
    "deprecate_version",
    "get_review_workspace_link",
}


def _tool_names() -> set[str]:
    tools = asyncio.run(mcp.list_tools())
    return {tool.name for tool in tools}


def test_mcp_surface_matches_registry_exactly() -> None:
    names = _tool_names()
    assert names == ALLOWED_TOOLS
    assert names.isdisjoint(FORBIDDEN_TOOLS)


def test_register_all_is_idempotent() -> None:
    before = _tool_names()
    register_all(mcp)
    after = _tool_names()
    assert before == after == ALLOWED_TOOLS


def test_compatibility_tools_use_scalar_arguments() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    assert tools["submit_proposal_json"].inputSchema["required"] == ["proposal_json"]
    assert tools["submit_proposal_json"].inputSchema["properties"]["proposal_json"]["type"] == "string"
    assert set(tools["get_source_document_chunks"].inputSchema["properties"]) == {
        "document_id",
        "offset",
        "limit",
    }
