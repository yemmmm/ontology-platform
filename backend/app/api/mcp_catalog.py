"""Stage 4 §5.4 MCP tools enumeration endpoint.

Introspects the FastMCP tool registry and returns ``{tools: [...]}`` where
each entry carries ``{name, description, input_schema_summary, source_file,
category}``. ``category`` is bucketed by the source filename
(``system`` / ``interview`` / ``semantic``) as decided in spec §13.

The FastMCP ``list_tools()`` method returns ``mcp.types.Tool`` instances
carrying ``name``, ``description``, and ``inputSchema``. The source filename
is *not* exposed by the registry, so we AST-walk the per-domain tool files
and build a ``tool_name -> source_file`` map at request time.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.mcp.server import mcp

router = APIRouter(tags=["mcp-catalog"])

#: Per-category source files. Order mirrors ``register_all`` in
#: ``app/mcp/tools/__init__.py``.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "mcp" / "tools"
_TOOL_FILES: tuple[tuple[str, Path], ...] = (
    ("system", _TOOLS_DIR / "system.py"),
    ("interview", _TOOLS_DIR / "interview.py"),
    ("build_sessions", _TOOLS_DIR / "build_sessions.py"),
    ("build_sessions", _TOOLS_DIR / "modeling_batches.py"),
    ("build_sessions", _TOOLS_DIR / "modeling_workflow.py"),
    ("semantic", _TOOLS_DIR / "evidence.py"),
    ("semantic", _TOOLS_DIR / "semantic.py"),
)


def _extract_tool_names(path: Path) -> list[str]:
    """Return the function names decorated with ``@server.tool()`` in
    ``path``. Walks the AST recursively because the tools are defined
    nested inside ``register_<domain>`` functions."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                names.append(node.name)
                break
    return names


def _build_name_to_source() -> dict[str, tuple[str, str]]:
    """Build a ``{tool_name: (category, source_filename)}`` lookup."""
    out: dict[str, tuple[str, str]] = {}
    for category, path in _TOOL_FILES:
        for name in _extract_tool_names(path):
            out[name] = (category, path.name)
    return out


def _summarize_input_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Project a JSON Schema into a compact summary so the response stays
    small even when a tool declares many parameters. The frontend
    ``McpToolsPage`` only renders the property names + required flag."""
    if not isinstance(schema, dict):
        return {"properties": [], "required": []}
    properties = sorted((schema.get("properties") or {}).keys())
    required = sorted(schema.get("required") or [])
    return {
        "properties": properties,
        "required": required,
        "title": schema.get("title"),
    }


def _enumerate_tools() -> list[dict[str, Any]]:
    """Synchronously enumerate tools via FastMCP's ``list_tools`` method.

    FastMCP's ``list_tools`` is async; we run it on a fresh event loop
    instead of marking this route ``async def`` because the route handler
    does no other I/O and ``async def`` would force Starlette to dispatch
    it on the event loop thread (which conflicts with FastMCP's own loop
    management when introspection runs)."""
    import asyncio

    tools = asyncio.run(mcp.list_tools())
    name_to_source = _build_name_to_source()
    out: list[dict[str, Any]] = []
    for tool in tools:
        category, source_file = name_to_source.get(tool.name, ("uncategorized", "unknown.py"))
        out.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema_summary": _summarize_input_schema(getattr(tool, "inputSchema", None)),
                "source_file": source_file,
                "category": category,
            }
        )
    # Stable ordering: category, then tool name. Mirrors the registration
    # order in ``register_all``.
    category_order = {
        "system": 0,
        "interview": 1,
        "build_sessions": 2,
        "semantic": 3,
        "uncategorized": 4,
    }
    out.sort(key=lambda t: (category_order.get(t["category"], 99), t["name"]))
    return out


@router.get("/mcp/tools")
def list_mcp_tools() -> dict[str, Any]:
    """Stage 4 §5.4 enumeration surface for the McpToolsPage."""
    tools = _enumerate_tools()
    by_category: dict[str, int] = {}
    for tool in tools:
        by_category[tool["category"]] = by_category.get(tool["category"], 0) + 1
    return {
        "tools": tools,
        "total": len(tools),
        "by_category": by_category,
    }
