#!/usr/bin/env python3
"""Synchronize the generated HTTP and MCP inventories in the documentation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
API_DOC = REPO_ROOT / "docs" / "reference" / "api.md"
MCP_DOC = REPO_ROOT / "docs" / "reference" / "mcp.md"

HTTP_BEGIN = "<!-- BEGIN GENERATED HTTP API INVENTORY -->"
HTTP_END = "<!-- END GENERATED HTTP API INVENTORY -->"
MCP_BEGIN = "<!-- BEGIN GENERATED MCP TOOL INVENTORY -->"
MCP_END = "<!-- END GENERATED MCP TOOL INVENTORY -->"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
HTTP_METHOD_ORDER = {method: index for index, method in enumerate(HTTP_METHODS)}


def _load_runtime() -> tuple[Any, Any]:
    backend = str(BACKEND_DIR)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.api.mcp_catalog import _enumerate_tools
    from app.main import app

    return app, _enumerate_tools


def _escape_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def enumerate_http_operations() -> list[dict[str, str]]:
    app, _ = _load_runtime()
    operations: list[dict[str, str]] = []
    for path, path_item in app.openapi().get("paths", {}).items():
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags") or ["untagged"]
            operations.append(
                {
                    "tag": ", ".join(str(tag) for tag in tags),
                    "method": method.upper(),
                    "path": path,
                    "summary": str(operation.get("summary") or ""),
                }
            )
    operations.sort(
        key=lambda item: (
            item["tag"].casefold(),
            HTTP_METHOD_ORDER[item["method"].lower()],
            item["path"],
        )
    )
    return operations


def enumerate_mcp_tools() -> list[dict[str, Any]]:
    _, enumerate_tools = _load_runtime()
    return list(enumerate_tools())


def render_http_inventory() -> str:
    lines = [
        HTTP_BEGIN,
        "",
        "| Tag | Method | Path | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for operation in enumerate_http_operations():
        lines.append(
            "| {tag} | `{method}` | `{path}` | {summary} |".format(
                **{key: _escape_cell(value) for key, value in operation.items()}
            )
        )
    lines.extend(["", HTTP_END])
    return "\n".join(lines)


def render_mcp_inventory() -> str:
    lines = [
        MCP_BEGIN,
        "",
        "| Category | Tool | Description | Required parameters | All parameters | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tool in enumerate_mcp_tools():
        summary = tool.get("input_schema_summary") or {}
        required = ", ".join(summary.get("required") or []) or "-"
        properties = ", ".join(summary.get("properties") or []) or "-"
        lines.append(
            "| {category} | `{name}` | {description} | {required} | {properties} | "
            "`backend/app/mcp/tools/{source_file}` |".format(
                category=_escape_cell(tool.get("category")),
                name=_escape_cell(tool.get("name")),
                description=_escape_cell(tool.get("description")),
                required=_escape_cell(required),
                properties=_escape_cell(properties),
                source_file=_escape_cell(tool.get("source_file")),
            )
        )
    lines.extend(["", MCP_END])
    return "\n".join(lines)


def replace_generated_block(text: str, begin: str, end: str, replacement: str) -> str:
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError(f"expected exactly one ordered marker pair: {begin} ... {end}")
    start = text.index(begin)
    finish = text.index(end)
    if start >= finish:
        raise ValueError(f"markers are out of order: {begin} ... {end}")
    finish += len(end)
    return text[:start] + replacement + text[finish:]


def expected_documents() -> dict[Path, str]:
    specifications = (
        (API_DOC, HTTP_BEGIN, HTTP_END, render_http_inventory()),
        (MCP_DOC, MCP_BEGIN, MCP_END, render_mcp_inventory()),
    )
    expected: dict[Path, str] = {}
    for path, begin, end, replacement in specifications:
        current = path.read_text(encoding="utf-8")
        expected[path] = replace_generated_block(current, begin, end, replacement)
    return expected


def write_documents() -> int:
    changed: list[Path] = []
    for path, expected in expected_documents().items():
        if path.read_text(encoding="utf-8") == expected:
            continue
        path.write_text(expected, encoding="utf-8")
        changed.append(path)
    if changed:
        print("Updated interface inventories:")
        for path in changed:
            print(f"- {path.relative_to(REPO_ROOT)}")
    else:
        print("Interface documentation is already synchronized.")
    return 0


def check_documents() -> int:
    drifted = [
        path
        for path, expected in expected_documents().items()
        if path.read_text(encoding="utf-8") != expected
    ]
    if not drifted:
        print("Interface documentation is synchronized.")
        return 0
    print("Interface documentation drift detected:", file=sys.stderr)
    for path in drifted:
        print(f"- {path.relative_to(REPO_ROOT)}", file=sys.stderr)
    print(
        "Run: cd backend && uv run python ../scripts/sync-interface-docs.py --write",
        file=sys.stderr,
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="update generated inventories")
    mode.add_argument("--check", action="store_true", help="check inventories without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return write_documents() if args.write else check_documents()


if __name__ == "__main__":
    raise SystemExit(main())
