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
    scope = {
        key: os.environ.get(key, "")
        for key in ("PLATFORM_PROXY_PROJECT_ID", "PLATFORM_PROXY_ONTOLOGY_ID", "PLATFORM_PROXY_GRAPH_SET_ID", "PLATFORM_PROXY_TICKET_DIGEST", "PLATFORM_PROXY_MODEL_STATE_DIGEST")
    }
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method") if isinstance(request, dict) else None
            request_id = request.get("id") if isinstance(request, dict) else None
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "platform_read_proxy", "version": "1"}}
            elif method == "tools/list":
                tools = _proxy_call(args.socket, {"token": token, "operation": "tools/list"}).get("tools", [])
                result = {"tools": [{"name": name, "description": "ticket-bound read-only platform query", "inputSchema": {"type": "object"}} for name in tools]}
            elif method == "tools/call":
                params = request.get("params", {}) if isinstance(request, dict) else {}
                name = params.get("name")
                arguments = dict(params.get("arguments") or {})
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
                    raise RuntimeError(str(response.get("code", "proxy-call-denied")))
                result = {"content": [{"type": "text", "text": _json(response.get("result", {}))}], "isError": False}
            else:
                raise RuntimeError("mcp-method-denied")
            sys.stdout.write(_json({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        except Exception as exc:
            sys.stdout.write(_json({"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32000, "message": str(exc)}}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
