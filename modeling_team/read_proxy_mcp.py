"""Tiny child-local MCP stdio bridge for the Runner's scoped read proxy.

It intentionally knows only the proxy socket and ticket-scope environment.  It does not
contain platform credentials or a platform client.  The Codex child starts this script as
its sole platform MCP server; deterministic tests can exercise it with a local proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from typing import Any


# R3.0-011 v3 acceptance mode (PLATFORM_PROXY_MODE): the packet-authorized
# multi-Ontology scope is Host-owned, so the bridge forwards only the invariant
# batch ticket and passes the proxy's exact tool schemas through.  Injecting the
# legacy primary-entry singleton scope here is what made a subset read that
# excluded the primary Ontology arrive at the proxy with contradictory values.
_V3_ACCEPTANCE_MODE = "v3-acceptance"

_MODELING_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_modeling_context": {
        "name": "get_modeling_context",
        "description": "Read the authoritative current state for the bound Ontology.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ontology_id": {
                    "type": "string",
                    "description": "The Runner-bound Ontology ID; the bridge injects the exact value.",
                },
            },
            "required": ["ontology_id"],
            "additionalProperties": False,
        },
    },
    "get_ontology_read_model": {
        "name": "get_ontology_read_model",
        "description": "Read one fixed, asserted Ontology semantic model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ontology_id": {
                    "type": "string",
                    "description": "The Runner-bound Ontology ID; the bridge injects the exact value.",
                },
                "model_name": {
                    "type": "string",
                    "enum": ["classes", "entities", "facts", "rules"],
                },
                "include": {"type": "string", "enum": ["asserted"], "default": "asserted"},
                "allow_stale_derived": {"const": False, "default": False},
                "field_set": {"type": "string", "enum": ["summary", "full"], "default": "summary"},
                "limit": {"type": "integer", "minimum": 1},
                "entity_iri": {"type": "string", "minLength": 1},
                "class_iri": {"type": "string", "minLength": 1},
                "kind": {"type": "string", "minLength": 1},
                "q": {"type": "string", "minLength": 1},
            },
            "required": ["ontology_id", "model_name"],
            "additionalProperties": False,
        },
    },
    "query_semantic_context": {
        "name": "query_semantic_context",
        "description": "Recall structured semantic context from the bound Ontology.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The Runner-bound Project ID; the bridge injects the exact value.",
                },
                "scope_mode": {"const": "ontologies", "default": "ontologies"},
                "query": {"type": "string", "minLength": 1},
                "queries": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "ontology_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {"type": "string", "minLength": 1},
                    "description": "The Runner-bound Ontology ID; the bridge injects the exact singleton list.",
                },
                "resource_types": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "assertion_types": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "search_mode": {"type": "string", "default": "hybrid"},
                "depth": {"type": "integer", "minimum": 1, "default": 1},
                "limit": {"type": "integer", "minimum": 1, "default": 20},
                "context_limit": {"type": "integer", "minimum": 1, "default": 100},
                "match_cursor": {"type": "string", "minLength": 1},
                "context_cursor": {"type": "string", "minLength": 1},
            },
            "required": ["project_id", "scope_mode"],
            "anyOf": [{"required": ["query"]}, {"required": ["queries"]}],
            "additionalProperties": False,
        },
    },
}


_MODELING_SCOPE_FIELDS: dict[str, dict[str, str]] = {
    "get_modeling_context": {"ontology_id": "PLATFORM_PROXY_ONTOLOGY_ID"},
    "get_ontology_read_model": {"ontology_id": "PLATFORM_PROXY_ONTOLOGY_ID"},
    "query_semantic_context": {
        "project_id": "PLATFORM_PROXY_PROJECT_ID",
        "scope_mode": "ontologies",
        "ontology_ids": "PLATFORM_PROXY_ONTOLOGY_ID",
    },
}


def _modeling_tool_schema(name: str) -> dict[str, Any]:
    schema = _MODELING_TOOL_SCHEMAS.get(name)
    if schema is None:
        return {
            "name": name,
            "description": "ticket-bound read-only platform query",
            "inputSchema": {"type": "object", "additionalProperties": False},
        }
    return json.loads(json.dumps(schema))


def _project_modeling_arguments(
    name: str, arguments: dict[str, Any], scope: dict[str, str]
) -> dict[str, Any]:
    fields = _MODELING_SCOPE_FIELDS.get(name)
    if fields is None:
        return arguments
    projected = dict(arguments)
    for field, source in fields.items():
        expected = source if source == "ontologies" else scope[source]
        normalized_expected = [expected] if field == "ontology_ids" else expected
        if field in projected and projected[field] != normalized_expected:
            raise ValueError(f"modeling proxy scope mismatch for {field}")
        projected[field] = normalized_expected
    return projected


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _proxy_call(socket_path: str, request: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(socket_path)
        client.sendall((_json(request) + "\n").encode("utf-8"))
        buffer = b""
        while b"\n" not in buffer:
            block = client.recv(8192)
            if not block:
                break
            buffer += block
    if not buffer:
        return {"ok": False, "error": "proxy-empty-response", "code": "proxy-empty-response"}
    value = json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))
    return value if isinstance(value, dict) else {"ok": False, "error": "proxy-invalid-response", "code": "proxy-invalid-response"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()
    try:
        token = open(args.token_file, encoding="utf-8").read().strip()
    except OSError:
        return 2
    modeling_mode = os.environ.get("PLATFORM_PROXY_MODE") == "modeling"
    v3_mode = os.environ.get("PLATFORM_PROXY_MODE") == _V3_ACCEPTANCE_MODE
    scope = {
        key: os.environ.get(key, "")
        for key in (
            "PLATFORM_PROXY_PROJECT_ID",
            "PLATFORM_PROXY_ONTOLOGY_ID",
            "PLATFORM_PROXY_GRAPH_SET_ID",
            "PLATFORM_PROXY_TICKET_DIGEST",
            "PLATFORM_PROXY_MODEL_STATE_DIGEST",
        )
    }
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method") if isinstance(request, dict) else None
            request_id = request.get("id") if isinstance(request, dict) else None
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "platform_read_proxy", "version": "1"}}
            elif method == "tools/list":
                listing = _proxy_call(args.socket, {"token": token, "operation": "tools/list"})
                tools = listing.get("tools", [])
                if v3_mode:
                    # Pass the proxy's exact schemas through unchanged: the
                    # proxy is the source of truth for what it will accept.
                    exact = listing.get("schemas")
                    exact = [item for item in (exact if isinstance(exact, list) else []) if isinstance(item, dict) and item.get("name") in set(tools)]
                    result = {
                        "tools": exact
                        or [
                            {
                                "name": name,
                                "description": "ticket-bound read-only platform query",
                                "inputSchema": {"type": "object"},
                            }
                            for name in tools
                        ]
                    }
                elif modeling_mode:
                    result = {"tools": [_modeling_tool_schema(name) for name in tools]}
                else:
                    result = {
                        "tools": [
                            {
                                "name": name,
                                "description": "ticket-bound read-only platform query",
                                "inputSchema": {"type": "object"},
                            }
                            for name in tools
                        ]
                    }
            elif method == "tools/call":
                params = request.get("params", {}) if isinstance(request, dict) else {}
                name = params.get("name")
                arguments = dict(params.get("arguments") or {})
                if modeling_mode:
                    arguments = _project_modeling_arguments(name, arguments, scope)
                elif v3_mode:
                    # Only the invariant batch ticket is bridged; the proxy owns
                    # every per-Ontology scope value for the selected entries.
                    arguments.setdefault("ticket_digest", scope["PLATFORM_PROXY_TICKET_DIGEST"])
                else:
                    mapping = {
                        "project_id": "PLATFORM_PROXY_PROJECT_ID",
                        "ontology_id": "PLATFORM_PROXY_ONTOLOGY_ID",
                        "graph_set_id": "PLATFORM_PROXY_GRAPH_SET_ID",
                        "ticket_digest": "PLATFORM_PROXY_TICKET_DIGEST",
                        "model_state_digest": "PLATFORM_PROXY_MODEL_STATE_DIGEST",
                    }
                    for field, env_name in mapping.items():
                        arguments.setdefault(field, scope[env_name])
                response = _proxy_call(args.socket, {"token": token, "operation": "tools/call", "tool": name, "arguments": arguments})
                if not response.get("ok"):
                    # Surface the platform's full error detail instead of a single opaque
                    # code, so the Agent can tell a bad argument from a service fault and
                    # stop blind-retrying parameter names.
                    err_fields = {k: response[k] for k in ("code", "error", "message", "detail") if response.get(k) is not None}
                    raise RuntimeError(_json(err_fields) if err_fields else "proxy-call-denied")
                # Preserve the digest locators ScopedReadProxy returns at the top level
                # (request_digest/response_digest/artifact_path). They sit next to, not
                # inside, ``result``; forwarding only ``result`` dropped them, which left
                # the Examiner unable to fill evidence_refs and got its report rejected.
                result_data = response.get("result", {})
                digest_locators = {k: response[k] for k in ("request_digest", "response_digest", "artifact_path") if response.get(k)}
                if digest_locators:
                    payload = {**result_data, **digest_locators} if isinstance(result_data, dict) else {"result": result_data, **digest_locators}
                else:
                    payload = result_data
                result = {"content": [{"type": "text", "text": _json(payload)}], "isError": False}
            else:
                raise RuntimeError("mcp-method-denied")
            sys.stdout.write(_json({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        except Exception as exc:
            sys.stdout.write(_json({"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32000, "message": str(exc)}}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
