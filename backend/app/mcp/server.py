"""ontology-platform MCP server entrypoint.

Tool implementations live in ``app.mcp.tools``; this module owns only the
FastMCP instance and the registration call.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools import register_all

mcp = FastMCP("ontology-platform")
register_all(mcp)


if __name__ == "__main__":
    mcp.run()
