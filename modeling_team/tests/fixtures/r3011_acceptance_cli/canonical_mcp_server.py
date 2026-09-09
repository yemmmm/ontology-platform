#!/usr/bin/env python3
"""Controlled canonical backend MCP server fixture (no database, no services).

This executable stands in for ``backend/app/mcp.server`` at the one external
process boundary the local ``McpReadForwarder`` owns.  It speaks the same
JSON-RPC MCP surface over stdio and mirrors the canonical read-tool signatures
that the real server exposes, but it serves deterministic state from a fixture
state file instead of a live database.

The forwarder environment is allowlisted, so every scenario switch is passed as
argv by the fixture CLI wrapper, never through the environment.

Usage:
  canonical_mcp_server.py --state-file STATE.json [--counter-file COUNT]
      [--drift-after-read N] [--fail-read-after N] [--evidence-file E.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Canonical tool inventories mirror backend/app/mcp/tools/{interview,semantic}.py
# signatures.  The forwarder projects wrapper control fields (ticket_digest and
# per-Ontology scope) away against exactly this property set.
TOOLS: dict[str, dict[str, Any]] = {
    "get_ontology_workspace_context": {
        "name": "get_ontology_workspace_context",
        "description": "Read the default Graph Set, graph roles, revisions, and editability.",
        "inputSchema": {
            "type": "object",
            "properties": {"ontology_id": {"type": "string"}},
            "required": ["ontology_id"],
            "additionalProperties": False,
        },
    },
    "query_semantic_context": {
        "name": "query_semantic_context",
        "description": "Recall structured semantic context from one Project's current Ontologies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "scope_mode": {"type": "string"},
                "query": {"type": ["string", "null"]},
                "queries": {"type": ["array", "null"], "items": {"type": "string"}},
                "ontology_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                "resource_types": {"type": ["array", "null"], "items": {"type": "string"}},
                "assertion_types": {"type": ["array", "null"], "items": {"type": "string"}},
                "search_mode": {"type": "string"},
                "depth": {"type": "integer"},
                "limit": {"type": "integer"},
                "context_limit": {"type": "integer"},
                "context_detail": {"type": "string"},
                "match_cursor": {"type": ["string", "null"]},
                "context_cursor": {"type": ["string", "null"]},
            },
        },
    },
}


class FixtureState:
    def __init__(self, path: Path, counter_path: Path | None) -> None:
        self.raw = json.loads(path.read_text(encoding="utf-8"))
        self.ontologies: dict[str, Any] = self.raw["ontologies"]
        self.counter_path = counter_path or path.with_suffix(path.suffix + ".counter")
        self.calls: list[dict[str, Any]] = []

    def _next_read_index(self) -> int:
        try:
            current = int(self.counter_path.read_text(encoding="utf-8").strip() or "0")
        except OSError:
            current = 0
        current += 1
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        self.counter_path.write_text(str(current), encoding="utf-8")
        return current

    def workspace_context(self, ontology_id: str, *, drift_after: int, fail_after: int) -> dict[str, Any]:
        entry = self.ontologies.get(ontology_id)
        if entry is None:
            raise RuntimeError(f"fixture: unknown ontology {ontology_id}")
        index = self._next_read_index()
        revision = int(entry["revision"])
        if drift_after and index > drift_after:
            # Deterministic post-batch state change: one later graph revision.
            revision += 1
        context = {
            "ontology_id": ontology_id,
            "state": "ready",
            "source_signature": entry["source_signature"],
            "graph_set_status": "ready",
            "default_graph_set_id": entry["default_graph_set_id"],
            "members": [
                {
                    "role": member["role"],
                    "revision": revision + offset,
                    "content_hash": member["content_hash"],
                }
                for offset, member in enumerate(entry["members"])
            ],
            "fixture_read_index": index,
        }
        if fail_after and index >= fail_after:
            raise RuntimeError("fixture: canonical workspace read unavailable")
        return context

    def query(self, ontology_ids: list[str]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "ontology_id": ontology_id,
                    "matches": [
                        {"text": fact, "resource_type": "fact"}
                        for fact in self.ontologies[ontology_id]["facts"]
                    ],
                }
                for ontology_id in ontology_ids
                if ontology_id in self.ontologies
            ],
        }


def _rpc_result(request_id: Any, payload: dict[str, Any]) -> str:
    """One JSON-RPC result whose payload is the response object itself."""

    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "result": payload},
        ensure_ascii=False,
    )


def _call_result(request_id: Any, payload: dict[str, Any]) -> str:
    """One CallToolResult carrying a typed payload, like the canonical server."""

    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "structuredContent": payload,
                "isError": False,
            },
        },
        ensure_ascii=False,
    )


def _tool_error(request_id: Any, message: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": message}],
                "isError": True,
            },
        },
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--counter-file", default=None)
    parser.add_argument("--drift-after-read", type=int, default=0)
    parser.add_argument("--fail-read-after", type=int, default=0)
    parser.add_argument("--evidence-file", default=None)
    args = parser.parse_args()

    state = FixtureState(Path(args.state_file), Path(args.counter_file) if args.counter_file else None)
    evidence_path = Path(args.evidence_file) if args.evidence_file else None

    def record(kind: str, detail: dict[str, Any]) -> None:
        state.calls.append({"kind": kind, **detail})
        if evidence_path is not None:
            evidence_path.write_text(
                json.dumps({"calls": state.calls}, indent=2, sort_keys=True), encoding="utf-8"
            )

    request_id: Any = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if method == "initialize":
            sys.stdout.write(
                _rpc_result(
                    request_id,
                    {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture-canonical-mcp", "version": "1"},
                    },
                )
                + "\n"
            )
        elif method == "tools/list":
            # ListToolsResult: the tool inventory is the result object itself, not
            # a CallToolResult envelope.
            sys.stdout.write(_rpc_result(request_id, {"tools": list(TOOLS.values())}) + "\n")
        elif method == "tools/call":
            name = params.get("name")
            arguments = dict(params.get("arguments") or {})
            record("tools/call", {"tool": name, "arguments": arguments})
            try:
                if name == "get_ontology_workspace_context":
                    payload = state.workspace_context(
                        str(arguments["ontology_id"]),
                        drift_after=int(args.drift_after_read),
                        fail_after=int(args.fail_read_after),
                    )
                elif name == "query_semantic_context":
                    payload = state.query([str(item) for item in arguments.get("ontology_ids") or []])
                    payload["project_id"] = arguments.get("project_id")
                    payload["scope_mode"] = arguments.get("scope_mode")
                else:
                    raise RuntimeError(f"fixture: unknown tool {name}")
                sys.stdout.write(_call_result(request_id, payload) + "\n")
            except Exception as exc:  # typed MCP tool error, like the canonical server
                sys.stdout.write(_tool_error(request_id, str(exc)) + "\n")
        elif method == "ping":
            sys.stdout.write(_rpc_result(request_id, {}) + "\n")
        else:
            # Notifications (``notifications/initialized``) carry no id and are dropped.
            if request_id is None:
                continue
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"fixture: {method} unsupported"},
                    }
                )
                + "\n"
            )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
