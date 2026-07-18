"""Per-domain MCP tool registry.

``register_all`` is the single source of truth for which tools the MCP server
exposes. Adding or removing a tool means editing both the relevant
``register_<domain>`` function and the call list here.

Stage 3 B2 hard-cut: legacy governance/publication/catalog/graph/documents/
facts tooling was removed; only the semantic stack, the interview CRUD, and
system introspection remain.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools.interview import register_interview
from app.mcp.tools.modeling_batches import register_modeling_batches
from app.mcp.tools.modeling_workflow import register_modeling_workflow
from app.mcp.tools.build_sessions import register_build_sessions
from app.mcp.tools.evidence import register_evidence
from app.mcp.tools.semantic import register_semantic
from app.mcp.tools.system import register_system


def register_all(server: FastMCP) -> None:
    """Register every MCP tool on ``server`` in stable, domain-grouped order."""
    register_system(server)
    register_interview(server)
    register_build_sessions(server)
    register_modeling_batches(server)
    register_modeling_workflow(server)
    register_evidence(server)
    register_semantic(server)


__all__ = ["register_all"]
