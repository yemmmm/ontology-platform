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
import re
from typing import Callable


_TERMINAL_ROLE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
TERMINAL_REPORT_GUARD_ERROR = (
    "Protocol retrieval evidence is incomplete; retry the required query or verifier before terminal report"
)


class RoutingError(ValueError):
    pass


@dataclass(frozen=True)
class Delivery:
    sequence: int
    sender_id: str
    recipient_id: str
    text: str
    timestamp: float
    delivery_id: str
    expects_reply: bool = False
    reply_to_delivery_id: str | None = None


@dataclass(frozen=True)
class TaskResult:
    agent_id: str
    status: str
    summary: str
    timestamp: float


class TeamTransportBroker:
    def __init__(
        self,
        root: Path,
        permissions: set[tuple[str, str]],
        terminal_dependencies: dict[str, set[str]] | None = None,
        modeling_agent_id: str | None = None,
        terminal_report_guard: Callable[[str, bool], object] | None = None,
        transport_event_observer: Callable[[dict[str, object]], None] | None = None,
    ):
        self.evidence_root = root
        # Linux Unix sockets have a short pathname limit. The run-local requested path is
        # retained as evidence; only the live private socket directory uses a hashed /tmp path.
        if len(str(root / "source-specialist.sock")) >= 100:
            root = Path("/tmp") / f"mt-{sha256(str(root).encode()).hexdigest()[:24]}"
        self.root, self.permissions = root, permissions
        self.terminal_dependencies = {
            agent_id: frozenset(dependencies)
            for agent_id, dependencies in (terminal_dependencies or {}).items()
        }
        self.modeling_agent_id = modeling_agent_id
        self.terminal_report_guard = terminal_report_guard
        self.transport_event_observer = transport_event_observer
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._deliveries: list[Delivery] = []
        self._delivery_sequence = 0
        self._delivery_by_id: dict[str, Delivery] = {}
        self._pending_replies: dict[str, str | None] = {}
        self._reply_delivery_ids: dict[str, str] = {}
        self._acknowledged_deliveries: set[str] = set()
        self._results: dict[str, TaskResult] = {}
        self._terminal_handoff_acks: set[tuple[str, str]] = set()
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

    def send(
        self,
        sender_id: str,
        recipient_id: str,
        text: str,
        expects_reply: bool = False,
        reply_to_delivery_id: str | None = None,
    ) -> Delivery:
        if (
            not isinstance(text, str)
            or (sender_id, recipient_id) not in self.permissions
            or not isinstance(expects_reply, bool)
            or (reply_to_delivery_id is not None and not isinstance(reply_to_delivery_id, str))
        ):
            raise RoutingError("recipient is not allowed by frozen Profile")
        with self._lock:
            if reply_to_delivery_id is not None:
                original = self._delivery_by_id.get(reply_to_delivery_id)
                if (
                    not original
                    or original.sender_id != recipient_id
                    or original.recipient_id != sender_id
                    or not original.expects_reply
                    or reply_to_delivery_id not in self._pending_replies
                    or self._pending_replies[reply_to_delivery_id] is not None
                ):
                    raise RoutingError("Team Transport reply is not an active reversed request")
            self._delivery_sequence += 1
            delivery = Delivery(
                self._delivery_sequence,
                sender_id,
                recipient_id,
                text,
                time.time(),
                f"delivery-{self._delivery_sequence}",
                expects_reply,
                reply_to_delivery_id,
            )
            self._deliveries.append(delivery)
            self._delivery_by_id[delivery.delivery_id] = delivery
            if expects_reply:
                self._pending_replies[delivery.delivery_id] = None
            if reply_to_delivery_id is not None:
                self._pending_replies[reply_to_delivery_id] = delivery.delivery_id
                self._reply_delivery_ids[delivery.delivery_id] = reply_to_delivery_id
            return delivery

    def ack_delivery(self, delivery_id: str) -> None:
        with self._lock:
            if (
                not isinstance(delivery_id, str)
                or delivery_id not in self._delivery_by_id
                or delivery_id in self._acknowledged_deliveries
            ):
                raise RoutingError("Team Transport delivery acknowledgement is invalid")
            self._acknowledged_deliveries.add(delivery_id)
            request_id = self._reply_delivery_ids.get(delivery_id)
            if request_id is not None:
                if self._pending_replies.get(request_id) != delivery_id:
                    raise RoutingError("Team Transport reply acknowledgement is invalid")
                del self._pending_replies[request_id]

    def ack_terminal_handoff(self, recipient_id: str, source_id: str) -> None:
        with self._lock:
            pair = (recipient_id, source_id)
            if (
                pair in self._terminal_handoff_acks
                or source_id not in self._results
                or source_id not in self.terminal_dependencies.get(recipient_id, frozenset())
            ):
                raise RoutingError("terminal handoff acknowledgement is invalid")
            self._terminal_handoff_acks.add(pair)

    def report(
        self,
        agent_id: str,
        status: str,
        summary: str,
        *,
        already_synchronized: bool = False,
    ) -> TaskResult:
        if self.terminal_report_guard is not None:
            try:
                allowed = self.terminal_report_guard(agent_id, already_synchronized)
            except Exception:
                raise RoutingError(TERMINAL_REPORT_GUARD_ERROR) from None
            if allowed is not False:
                raise RoutingError(TERMINAL_REPORT_GUARD_ERROR)
        if status not in {"completed", "blocked"} or not isinstance(summary, str):
            raise RoutingError("terminal result is invalid")
        with self._lock:
            if agent_id in self._results:
                raise RoutingError("Agent already reported a terminal result")
            if agent_id == self.modeling_agent_id:
                pending = [
                    delivery_id
                    for delivery_id in self._pending_replies
                    if self._delivery_by_id[delivery_id].sender_id == agent_id
                ]
                if pending:
                    raise RoutingError("terminal result requires delivered reply")
                inbound_revision_requests = [
                    delivery_id
                    for delivery_id in self._pending_replies
                    if self._delivery_by_id[delivery_id].recipient_id == agent_id
                ]
                if status == "completed" and inbound_revision_requests:
                    raise RoutingError("completed terminal result requires an explicit revision response")
                requested = any(
                    delivery.sender_id == agent_id and delivery.expects_reply
                    for delivery in self._delivery_by_id.values()
                )
                if status == "completed" and not requested:
                    raise RoutingError("completed terminal result requires an established reply request")
            missing = sorted(
                dependency
                for dependency in self.terminal_dependencies.get(agent_id, frozenset())
                if dependency not in self._results or (agent_id, dependency) not in self._terminal_handoff_acks
            )
            if missing:
                if not all(isinstance(role, str) and _TERMINAL_ROLE_ID.fullmatch(role) for role in missing):
                    raise RoutingError("terminal result dependencies are invalid")
                raise RoutingError("terminal result requires terminal handoffs: " + ", ".join(missing))
            result = TaskResult(agent_id, status, summary, time.time())
            self._results[agent_id] = result
            return result

    def drain(self) -> list[Delivery]:
        with self._lock:
            values, self._deliveries = self._deliveries[:], []
            return values

    def drain_for(
        self,
        *,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        delivery_id: str | None = None,
    ) -> list[Delivery]:
        """Claim only the queued deliveries owned by one transport consumer.

        The ordinary ``drain`` operation remains the FIFO Runner operation.  A producer that
        injects a delivery directly into the real Runtime must instead claim that exact delivery
        (or select its reply direction) so it cannot mistake its own outbound request for an
        Agent reply.  Unmatched deliveries remain queued and retain their original order.
        """
        if (
            sender_id is None
            and recipient_id is None
            and delivery_id is None
        ):
            raise RoutingError("targeted Team Transport drain requires a selector")
        with self._lock:
            selected: list[Delivery] = []
            remaining: list[Delivery] = []
            for delivery in self._deliveries:
                matches = (
                    (sender_id is None or delivery.sender_id == sender_id)
                    and (recipient_id is None or delivery.recipient_id == recipient_id)
                    and (delivery_id is None or delivery.delivery_id == delivery_id)
                )
                if matches:
                    selected.append(delivery)
                else:
                    remaining.append(delivery)
            self._deliveries = remaining
            return selected

    @property
    def results(self) -> dict[str, TaskResult]:
        return dict(self._results)


def _report_rejection_category(error: RoutingError) -> str:
    """Map a Broker rejection to the small, non-sensitive event vocabulary."""
    message = str(error)
    if message.startswith("terminal result requires terminal handoffs: "):
        missing = message.rsplit(": ", 1)[-1].split(", ")
        if "modeling" in missing:
            return "missing_modeling_handoff"
    return "broker_rejection"


def _observe_report_event(
    broker: TeamTransportBroker,
    agent_id: str,
    *,
    status: str,
    category: str,
    already_synchronized: bool,
) -> None:
    """Notify the host with only the fixed, sanitized terminal-report metadata."""
    observer = broker.transport_event_observer
    # Dynamic App Server callbacks already append this exact event through the Adapter.  The
    # private marker is intentionally accepted only at the top-level request, after the exact
    # MCP argument check, so ordinary stdio requests cannot opt out of host observation.
    if observer is None or already_synchronized:
        return
    if not isinstance(agent_id, str) or not _TERMINAL_ROLE_ID.fullmatch(agent_id):
        return
    event = {
        "agent": agent_id,
        "tool": "report_task_result",
        "status": status,
        "category": category,
        "ack": "not_applicable",
        "recorded_at_ns": time.time_ns(),
    }
    try:
        observer(event)
    except Exception:
        # Evidence is best-effort and must never change the Broker's transport contract.
        return


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
                            "expects_reply": {"type": "boolean"},
                            "reply_to_delivery_id": {"type": ["string", "null"]},
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
        if set(args) - {"recipient_id", "text", "expects_reply", "reply_to_delivery_id"}:
            raise RoutingError("invalid Team Transport arguments")
        value = broker.send(
            agent_id,
            args.get("recipient_id"),
            args.get("text"),
            args.get("expects_reply", False),
            args.get("reply_to_delivery_id"),
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(value.__dict__, ensure_ascii=False)}
            ]
        }
    if name == "report_task_result":
        if set(args) != {"status", "summary"}:
            raise RoutingError("invalid Team Transport arguments")
        already_synchronized = request.get("already_synchronized") is True
        try:
            value = broker.report(
                agent_id,
                args.get("status"),
                args.get("summary"),
                already_synchronized=already_synchronized,
            )
        except RoutingError as error:
            _observe_report_event(
                broker,
                agent_id,
                status="rejected",
                category=_report_rejection_category(error),
                already_synchronized=already_synchronized,
            )
            raise
        _observe_report_event(
            broker,
            agent_id,
            status="accepted",
            category="terminal_report_accepted",
            already_synchronized=already_synchronized,
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
        # `already_synchronized` is a Host-internal marker used only by the legacy dynamic
        # callback.  The Agent-controlled stdio envelope cannot set it for the Broker.
        line = json.dumps(
            {key: value for key, value in request.items() if key != "already_synchronized"},
            ensure_ascii=False,
        ) + "\n"
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
