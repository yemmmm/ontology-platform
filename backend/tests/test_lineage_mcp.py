"""R4.0-012 withdraws tracing MCP tools and their old alias for all callers."""

import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.mcp.server import mcp


@pytest.mark.parametrize(
    "name,arguments",
    [
        (
            "get_ontology_lineage",
            {"ontology_id": "o", "target_type": "resource", "target_id": "iri"},
        ),
        ("inspect_semantic_statement_provenance", {"graph_set_id": "gs", "statement_iri": "iri"}),
        (
            "create_evidence_reference",
            {"project_id": "p", "document_name": "source", "excerpt": "text"},
        ),
        ("list_evidence_references", {"project_id": "p"}),
        ("get_evidence_reference", {"evidence_reference_id": "historical"}),
        ("associate_evidence_reference", {"project_id": "p", "target_id": "item"}),
    ],
)
def test_tracing_tools_are_absent_and_direct_calls_fail(name, arguments):
    assert mcp._tool_manager.get_tool(name) is None  # noqa: SLF001 - real registry seam
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert name not in names
    with pytest.raises(ToolError, match="Unknown tool: " + name):
        asyncio.run(mcp.call_tool(name, arguments))
