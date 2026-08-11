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
    modeling_mode = os.environ.get("PLATFORM_PROXY_MODE") == "modeling"
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
                tools = _proxy_call(args.socket, {"token": token, "operation": "tools/list"}).get("tools", [])
                result = {"tools": [{"name": name, "description": "ticket-bound read-only platform query", "inputSchema": {"type": "object"}} for name in tools]}
            elif method == "tools/call":
                params = request.get("params", {}) if isinstance(request, dict) else {}
                name = params.get("name")
                arguments = dict(params.get("arguments") or {})
                mapping = (
                    {
                        "project_id": "PLATFORM_PROXY_PROJECT_ID",
                        "ontology_id": "PLATFORM_PROXY_ONTOLOGY_ID",
                    }
                    if modeling_mode
                    else {
                        "project_id": "PLATFORM_PROXY_PROJECT_ID",
                        "ontology_id": "PLATFORM_PROXY_ONTOLOGY_ID",
                        "graph_set_id": "PLATFORM_PROXY_GRAPH_SET_ID",
                        "ticket_digest": "PLATFORM_PROXY_TICKET_DIGEST",
                        "model_state_digest": "PLATFORM_PROXY_MODEL_STATE_DIGEST",
                    }
                )
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
