"""A narrow, mechanically attributed broker for run-local Team Transport."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path


class RoutingError(ValueError):
    pass


@dataclass(frozen=True)
class Delivery:
    sequence: int
    sender_id: str
    recipient_id: str
    text: str
    timestamp: float


@dataclass(frozen=True)
class TaskResult:
    agent_id: str
    status: str
    summary: str
    timestamp: float


class TeamTransportBroker:
    def __init__(self, root: Path, permissions: set[tuple[str, str]]):
        self.evidence_root = root
        # Linux Unix sockets have a short pathname limit. The run-local requested path is
        # retained as evidence; only the live private socket directory uses a hashed /tmp path.
        if len(str(root / "source-specialist.sock")) >= 100:
            root = Path("/tmp") / f"mt-{sha256(str(root).encode()).hexdigest()[:24]}"
        self.root, self.permissions = root, permissions
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._deliveries: list[Delivery] = []
        self._results: dict[str, TaskResult] = {}
        self._lock = threading.Lock()
        self._servers: list[socket.socket] = []

    def endpoint(self, agent_id: str) -> Path:
        return self.root / f"{agent_id}.sock"

    def start(self, agent_ids: list[str]) -> None:
        """Publish one Unix endpoint per Agent; endpoint identity is the sender identity."""
        for agent_id in agent_ids:
            endpoint = self.endpoint(agent_id)
            endpoint.unlink(missing_ok=True)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(endpoint))
            os.chmod(endpoint, 0o600)
            server.listen()
            self._servers.append(server)
            threading.Thread(
                target=self._serve, args=(server, agent_id), daemon=True
            ).start()

    def _serve(self, server: socket.socket, agent_id: str) -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                try:
                    request = json.loads(
                        connection.makefile("r", encoding="utf-8").readline()
                    )
                    response = mcp_response(request, broker=self, agent_id=agent_id)
                except (json.JSONDecodeError, RoutingError) as exc:
                    response = {"error": str(exc)}
                connection.sendall(
                    (json.dumps(response, ensure_ascii=False) + "\n").encode()
                )

    def stop(self) -> None:
        for server in self._servers:
            server.close()
        self._servers.clear()
        if self.root.exists():
            for endpoint in self.root.glob("*.sock"):
                endpoint.unlink(missing_ok=True)
            self.root.rmdir()

    def send(self, sender_id: str, recipient_id: str, text: str) -> Delivery:
        if (
            not isinstance(text, str)
            or (sender_id, recipient_id) not in self.permissions
        ):
            raise RoutingError("recipient is not allowed by frozen Profile")
        with self._lock:
            delivery = Delivery(
                len(self._deliveries) + 1, sender_id, recipient_id, text, time.time()
            )
            self._deliveries.append(delivery)
            return delivery

    def report(self, agent_id: str, status: str, summary: str) -> TaskResult:
        if status not in {"completed", "blocked"} or not isinstance(summary, str):
            raise RoutingError("terminal result is invalid")
        with self._lock:
            if agent_id in self._results:
                raise RoutingError("Agent already reported a terminal result")
            result = TaskResult(agent_id, status, summary, time.time())
            self._results[agent_id] = result
            return result

    def drain(self) -> list[Delivery]:
        with self._lock:
            values, self._deliveries = self._deliveries[:], []
            return values

    @property
    def results(self) -> dict[str, TaskResult]:
        return dict(self._results)


def mcp_response(
    request: dict[str, object], *, broker: TeamTransportBroker, agent_id: str
) -> dict[str, object]:
    """Small stdio-MCP-compatible handler used by an Agent-private transport process."""
    method, params = request.get("method"), request.get("params", {})
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "send_team_message",
                    "description": "Deliver exact text to one Profile-authorized teammate.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "recipient_id": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["recipient_id", "text"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "report_task_result",
                    "description": "Report this Agent's single terminal result to the Team Runner.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["completed", "blocked"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["status", "summary"],
                        "additionalProperties": False,
                    },
                },
            ]
        }
    if method != "tools/call" or not isinstance(params, dict):
        raise RoutingError("unsupported Team Transport request")
    name, args = params.get("name"), params.get("arguments", {})
    if not isinstance(args, dict):
        raise RoutingError("invalid Team Transport arguments")
    if name == "send_team_message":
        value = broker.send(
            agent_id, str(args.get("recipient_id", "")), args.get("text")
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(value.__dict__, ensure_ascii=False)}
            ]
        }
    if name == "report_task_result":
        value = broker.report(
            agent_id, str(args.get("status", "")), str(args.get("summary", ""))
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(value.__dict__, ensure_ascii=False)}
            ]
        }
    raise RoutingError("unknown Team Transport tool")


def main() -> int:
    endpoint = os.environ.get("TEAM_TRANSPORT_SOCKET")
    if not endpoint:
        raise SystemExit("TEAM_TRANSPORT_SOCKET is required")
    for line in __import__("sys").stdin:
        request = json.loads(line)
        if request.get("method") == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "team-transport", "version": "1"},
            }
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
                ),
                flush=True,
            )
            continue
        if request.get("method") == "notifications/initialized":
            continue
        if request.get("method") == "ping":
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request.get("id"), "result": {}}
                ),
                flush=True,
            )
            continue
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(endpoint)
            connection.sendall(line.encode())
            response = connection.makefile("r", encoding="utf-8").readline()
        print(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": json.loads(response),
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
