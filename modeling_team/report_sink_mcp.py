"""Child-local MCP write-only report sink bridge.

The endpoint accepts exactly one opaque report payload and has no Team Transport or
platform operation.  Runner validates the report after receiving it through its own
carrier; this script only forwards bytes to the private sink socket.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys


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
    for line in sys.stdin:
        request = json.loads(line)
        request_id = request.get("id") if isinstance(request, dict) else None
        method = request.get("method") if isinstance(request, dict) else None
        try:
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "examiner_report", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [{"name": "submit_examiner_report", "description": "submit one bounded report", "inputSchema": {"type": "object"}}]}
            elif method == "tools/call":
                params = request.get("params", {})
                if params.get("name") != "submit_examiner_report":
                    raise RuntimeError("report-tool-denied")
                arguments = params.get("arguments") or {}
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(5)
                    client.connect(args.socket)
                    client.sendall(json.dumps({"token": token, "report": arguments}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    response = json.loads(client.recv(65536).decode("utf-8"))
                if not response.get("ok"):
                    raise RuntimeError(str(response.get("code", "report-rejected")))
                result = {"content": [{"type": "text", "text": "report-submitted"}], "isError": False}
            else:
                raise RuntimeError("report-method-denied")
            print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False, separators=(",", ":")), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
