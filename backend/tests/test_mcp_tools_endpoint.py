"""Stage 4 §5.4 ``GET /api/mcp/tools`` coverage.

Asserts the response:

* Carries ≥ 30 tools (current registration count is 32: 24 semantic +
  7 interview + 1 system).
* Includes ``compile_and_apply_canonical_command`` — the canonical-write
  compiler entry point surfaced in spec §11 step 6.
* Surfaces all three categories (``system``, ``interview``, ``semantic``).
* Each entry carries ``name``, ``description``, ``input_schema_summary``,
  ``source_file``, and ``category``.

The endpoint has no DB / RDF dependencies, so we mount the router on a
minimal FastAPI app without overriding dependencies.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mcp_catalog import router as mcp_catalog_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(mcp_catalog_router, prefix="/api")
    return TestClient(app)


def test_mcp_tools_returns_at_least_thirty_tools():
    client = _client()
    response = client.get("/api/mcp/tools")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 30, payload["total"]
    assert len(payload["tools"]) == payload["total"]


def test_mcp_tools_includes_canonical_write_command():
    client = _client()
    response = client.get("/api/mcp/tools")
    payload = response.json()
    names = {tool["name"] for tool in payload["tools"]}
    assert "compile_and_apply_canonical_command" in names, sorted(names)[:10]


def test_mcp_tools_covers_all_registered_categories():
    client = _client()
    response = client.get("/api/mcp/tools")
    payload = response.json()
    by_category = payload["by_category"]
    # Each category has at least one tool registered.
    assert by_category.get("system", 0) >= 1, by_category
    assert by_category.get("interview", 0) >= 1, by_category
    assert by_category.get("build_sessions", 0) >= 1, by_category
    assert by_category.get("semantic", 0) >= 1, by_category
    # No tool leaks the ``uncategorized`` fallback — every registered tool
    # is mapped back to its source file via AST scanning.
    assert by_category.get("uncategorized", 0) == 0, by_category


def test_mcp_tools_entry_shape_is_complete():
    client = _client()
    response = client.get("/api/mcp/tools")
    payload = response.json()
    for tool in payload["tools"]:
        assert tool["name"], tool
        # Description is required by the FastMCP registration contract;
        # the McpToolsPage renders it next to the tool name.
        assert isinstance(tool["description"], str)
        assert tool["source_file"], tool
        assert tool["category"] in {
            "system",
            "interview",
            "build_sessions",
            "semantic",
        }, tool
        summary = tool["input_schema_summary"]
        assert isinstance(summary, dict)
        assert "properties" in summary
        assert "required" in summary
