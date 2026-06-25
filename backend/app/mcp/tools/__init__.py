"""Per-domain MCP tool registry.

``register_all`` is the single source of truth for which tools the MCP server
exposes. Adding or removing a tool means editing both the relevant
``register_<domain>`` function and the call list here.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools.catalog import register_catalog
from app.mcp.tools.documents import register_documents
from app.mcp.tools.facts import register_facts
from app.mcp.tools.graph import register_graph
from app.mcp.tools.interview import register_interview
from app.mcp.tools.proposals import register_proposals
from app.mcp.tools.publication import register_publication
from app.mcp.tools.review import register_review
from app.mcp.tools.system import register_system


def register_all(server: FastMCP) -> None:
    """Register every MCP tool on ``server`` in stable, domain-grouped order."""
    register_system(server)
    register_graph(server)
    register_catalog(server)
    register_proposals(server)
    register_review(server)
    register_interview(server)
    register_documents(server)
    register_facts(server)
    register_publication(server)


__all__ = ["register_all"]
