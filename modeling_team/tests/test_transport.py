from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from modeling_team.transport_mcp import (
    TERMINAL_REPORT_GUARD_ERROR,
    RoutingError,
    TeamTransportBroker,
    mcp_response,
)


class TransportTests(unittest.TestCase):
    @staticmethod
    def _report_request(status: str, summary: str) -> dict[str, object]:
        return {
            "method": "tools/call",
            "params": {
                "name": "report_task_result",
                "arguments": {"status": status, "summary": summary},
            },
        }

    def test_terminal_guard_is_fail_closed_without_mutating_or_affecting_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = TeamTransportBroker(root / "default", set())
            default.report("default", "completed", "default guard absent")
            self.assertEqual(default.results["default"].status, "completed")

            blocked = TeamTransportBroker(
                root / "blocked",
                {("protocol", "modeling")},
                terminal_report_guard=lambda _agent_id, _synchronized: True,
            )
            delivery = blocked.send("protocol", "modeling", "ordinary delivery")
            with self.assertRaisesRegex(RoutingError, f"^{TERMINAL_REPORT_GUARD_ERROR}$"):
                blocked.report("protocol", "blocked", "must not persist")
            self.assertEqual(blocked.results, {})
            self.assertEqual(blocked.drain(), [delivery])

            allowed = TeamTransportBroker(
                root / "allowed", set(), terminal_report_guard=lambda _agent_id, _synchronized: False
            )
            allowed.report("protocol", "blocked", "exact false allows")
            self.assertIn("protocol", allowed.results)

            for value in (True, None, 0, "false"):
                with self.subTest(value=value):
                    candidate = TeamTransportBroker(
                        root / f"nonbool-{type(value).__name__}-{str(value).lower()}",
                        set(),
                        terminal_report_guard=lambda _agent_id, _synchronized, value=value: value,
                    )
                    with self.assertRaisesRegex(RoutingError, f"^{TERMINAL_REPORT_GUARD_ERROR}$"):
                        candidate.report("protocol", "blocked", "fail closed")
                    self.assertEqual(candidate.results, {})

            def raises(_agent_id, _synchronized):
                raise RuntimeError("callback-secret")

            exceptional = TeamTransportBroker(
                root / "exception", set(), terminal_report_guard=raises
            )
            with self.assertRaisesRegex(RoutingError, f"^{TERMINAL_REPORT_GUARD_ERROR}$"):
                exceptional.report("protocol", "blocked", "fail closed")
            self.assertEqual(exceptional.results, {})

    def test_only_host_top_level_marker_reaches_terminal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seen: list[tuple[str, bool]] = []
            broker = TeamTransportBroker(
                Path(directory),
                set(),
                terminal_report_guard=lambda agent_id, synchronized: seen.append(
                    (agent_id, synchronized)
                ) or False,
            )
            mcp_response(
                {
                    "already_synchronized": True,
                    "method": "tools/call",
                    "params": {
                        "name": "report_task_result",
                        "arguments": {"status": "blocked", "summary": "host marker"},
                    },
                },
                broker=broker,
                agent_id="protocol",
            )
            self.assertEqual(seen, [("protocol", True)])
            with self.assertRaisesRegex(RoutingError, "invalid Team Transport arguments"):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "report_task_result",
                            "arguments": {
                                "status": "blocked",
                                "summary": "forged marker",
                                "already_synchronized": True,
                            },
                        },
                    },
                    broker=broker,
                    agent_id="other",
                )
            self.assertEqual(seen, [("protocol", True)])

    def test_exact_unicode_multiline_delivery_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), {("modeling", "protocol")})
            text = "补充事实\nexact: Δ"
            self.assertEqual(broker.send("modeling", "protocol", text).text, text)
            self.assertEqual(broker.drain()[0].text, text)

    def test_unauthorized_and_duplicate_terminal_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), set())
            with self.assertRaises(RoutingError):
                broker.send("modeling", "protocol", "x")
            broker.report("modeling", "completed", "done")
            with self.assertRaises(RoutingError):
                broker.report("modeling", "blocked", "again")

    def test_coordinator_dependency_rejection_is_not_terminal_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                set(),
                terminal_dependencies={
                    "protocol": {"modeling"},
                    "coordinator": {"modeling", "protocol"},
                },
            )
            request = {
                "method": "tools/call",
                "params": {"name": "report_task_result", "arguments": {"status": "completed", "summary": "early"}},
            }
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling, protocol"):
                mcp_response(request, broker=broker, agent_id="coordinator")
            self.assertNotIn("coordinator", broker.results)
            broker.report("modeling", "completed", "modeling result")
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling"):
                broker.report("protocol", "blocked", "protocol result")
            broker.ack_terminal_handoff("protocol", "modeling")
            broker.ack_terminal_handoff("coordinator", "modeling")
            broker.report("protocol", "blocked", "protocol result")
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: protocol"):
                broker.report("coordinator", "completed", "early coordinator retry")
            broker.ack_terminal_handoff("coordinator", "protocol")
            broker.report("coordinator", "completed", "coordinator retry")
            self.assertEqual(set(broker.results), {"coordinator", "modeling", "protocol"})
            with self.assertRaisesRegex(RoutingError, "already reported"):
                broker.report("coordinator", "completed", "duplicate")

    def test_report_observer_records_ordered_sanitized_reject_and_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                Path(directory),
                set(),
                terminal_dependencies={"protocol": {"modeling"}},
                transport_event_observer=events.append,
            )
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling"):
                mcp_response(
                    self._report_request("completed", "private early summary"),
                    broker=broker,
                    agent_id="protocol",
                )
            broker.report("modeling", "completed", "private modeling summary")
            broker.ack_terminal_handoff("protocol", "modeling")
            mcp_response(
                self._report_request("completed", "private retry summary"),
                broker=broker,
                agent_id="protocol",
            )
            self.assertEqual(
                [(event["status"], event["category"]) for event in events],
                [
                    ("rejected", "missing_modeling_handoff"),
                    ("accepted", "terminal_report_accepted"),
                ],
            )
            for event in events:
                self.assertEqual(
                    set(event),
                    {"agent", "tool", "status", "category", "ack", "recorded_at_ns"},
                )
                self.assertEqual(event["agent"], "protocol")
                self.assertEqual(event["tool"], "report_task_result")
                self.assertEqual(event["ack"], "not_applicable")
                self.assertIsInstance(event["recorded_at_ns"], int)
                self.assertNotIn("private", json.dumps(event))

    def test_report_observer_failure_cannot_change_broker_result_or_error(self) -> None:
        def broken_observer(_event: dict[str, object]) -> None:
            raise OSError("observer-secret")

        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                set(),
                terminal_dependencies={"protocol": {"modeling"}},
                transport_event_observer=broken_observer,
            )
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling"):
                mcp_response(
                    self._report_request("completed", "early"),
                    broker=broker,
                    agent_id="protocol",
                )
            self.assertEqual(broker.results, {})
            broker.report("modeling", "completed", "modeling")
            broker.ack_terminal_handoff("protocol", "modeling")
            response = mcp_response(
                self._report_request("completed", "retry"),
                broker=broker,
                agent_id="protocol",
            )
            self.assertIn("content", response)
            self.assertIn("protocol", broker.results)

    def test_host_marker_does_not_duplicate_legacy_dynamic_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                Path(directory),
                set(),
                transport_event_observer=events.append,
            )
            request = self._report_request("blocked", "host synchronized")
            request["already_synchronized"] = True
            mcp_response(request, broker=broker, agent_id="protocol")
            self.assertEqual(events, [])

    def test_stdio_subprocess_over_real_unix_socket_notifies_observer(self) -> None:
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            events: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                Path(directory) / "broker",
                set(),
                terminal_dependencies={"protocol": {"modeling"}},
                transport_event_observer=events.append,
            )
            broker.start(["protocol"])
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                item for item in (str(root), environment.get("PYTHONPATH", "")) if item
            )
            environment["TEAM_TRANSPORT_SOCKET"] = str(broker.endpoint("protocol"))
            process = subprocess.Popen(
                [sys.executable, "-m", "modeling_team.transport_mcp"],
                cwd=root,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            def rpc(request_id: int, payload: dict[str, object]) -> dict[str, object]:
                assert process.stdin is not None
                assert process.stdout is not None
                process.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "id": request_id, **payload}) + "\n"
                )
                process.stdin.flush()
                return json.loads(process.stdout.readline())

            try:
                self.assertIn("result", rpc(1, {"method": "initialize", "params": {}}))
                early_request = self._report_request("completed", "early")
                early_request["already_synchronized"] = True
                early = rpc(2, early_request)
                self.assertIn("terminal handoffs: modeling", early["result"]["error"])
                broker.report("modeling", "completed", "modeling")
                broker.ack_terminal_handoff("protocol", "modeling")
                retry = rpc(3, self._report_request("completed", "retry"))
                self.assertIn("content", retry["result"])
            finally:
                if process.stdin is not None:
                    process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                broker.stop()
            self.assertEqual(
                [(event["status"], event["category"]) for event in events],
                [
                    ("rejected", "missing_modeling_handoff"),
                    ("accepted", "terminal_report_accepted"),
                ],
            )

    def test_tools_list_has_complete_mcp_input_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), set())
            response = mcp_response({"method": "tools/list"}, broker=broker, agent_id="modeling")
        tools = {item["name"]: item for item in response["tools"]}
        self.assertEqual(set(tools), {"send_team_message", "report_task_result"})
        self.assertEqual(
            tools["send_team_message"]["inputSchema"]["required"],
            ["recipient_id", "text"],
        )
        self.assertEqual(
            tools["send_team_message"]["inputSchema"]["properties"]["expects_reply"]["type"],
            "boolean",
        )
        self.assertEqual(
            tools["report_task_result"]["inputSchema"]["required"], ["status", "summary"]
        )

    def test_reply_correlation_closes_only_after_actual_reply_delivery_ack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            candidate = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            self.assertEqual(candidate.delivery_id, "delivery-1")
            self.assertTrue(candidate.expects_reply)
            queued_reply = broker.send(
                "protocol", "modeling", "receipt", reply_to_delivery_id=candidate.delivery_id
            )
            with self.assertRaisesRegex(RoutingError, "delivered reply"):
                broker.report("modeling", "completed", "too early")
            broker.ack_delivery(queued_reply.delivery_id)
            broker.report("modeling", "completed", "reply delivered")

    def test_reply_correlation_rejects_forged_wrong_direction_and_duplicate_replies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {
                    ("modeling", "protocol"),
                    ("protocol", "modeling"),
                    ("coordinator", "modeling"),
                    ("modeling", "coordinator"),
                },
            )
            request = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            with self.assertRaisesRegex(RoutingError, "active reversed"):
                broker.send("modeling", "protocol", "forged", reply_to_delivery_id=request.delivery_id)
            with self.assertRaisesRegex(RoutingError, "active reversed"):
                broker.send("coordinator", "modeling", "unrelated", reply_to_delivery_id=request.delivery_id)
            ordinary = broker.send("protocol", "modeling", "ordinary")
            broker.ack_delivery(ordinary.delivery_id)
            reply = broker.send("protocol", "modeling", "receipt", reply_to_delivery_id=request.delivery_id)
            with self.assertRaisesRegex(RoutingError, "active reversed"):
                broker.send("protocol", "modeling", "duplicate", reply_to_delivery_id=request.delivery_id)
            broker.ack_delivery(reply.delivery_id)
            with self.assertRaisesRegex(RoutingError, "invalid"):
                broker.ack_delivery(reply.delivery_id)

    def test_modeling_completed_needs_a_reply_request_but_blocked_and_ordinary_protocol_are_ungated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            broker.send("protocol", "modeling", "ordinary")
            broker.report("protocol", "completed", "ordinary outbound is not gated")
            with self.assertRaisesRegex(RoutingError, "established reply request"):
                broker.report("modeling", "completed", "no request")
            broker.report("modeling", "blocked", "unrevisable")

    def test_revision_reply_loop_allows_completed_or_unrevisable_blocked_terminal_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            first = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            conflict = broker.send(
                "protocol",
                "modeling",
                "conflict",
                expects_reply=True,
                reply_to_delivery_id=first.delivery_id,
            )
            broker.ack_delivery(conflict.delivery_id)
            with self.assertRaisesRegex(RoutingError, "explicit revision response"):
                broker.report("modeling", "completed", "conflict needs a revision or blocked result")
            with self.assertRaisesRegex(RoutingError, "active reversed"):
                broker.send(
                    "modeling",
                    "protocol",
                    "wrong revision",
                    expects_reply=True,
                    reply_to_delivery_id=first.delivery_id,
                )
            revision = broker.send(
                "modeling",
                "protocol",
                "revision",
                expects_reply=True,
                reply_to_delivery_id=conflict.delivery_id,
            )
            broker.ack_delivery(revision.delivery_id)
            with self.assertRaisesRegex(RoutingError, "delivered reply"):
                broker.report("modeling", "completed", "revision is still pending")
            receipt = broker.send("protocol", "modeling", "receipt", reply_to_delivery_id=revision.delivery_id)
            broker.ack_delivery(receipt.delivery_id)
            broker.report("modeling", "completed", "receipt delivered")

            blocked = TeamTransportBroker(
                Path(directory) / "blocked",
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            request = blocked.send("modeling", "protocol", "candidate", expects_reply=True)
            conflict = blocked.send(
                "protocol",
                "modeling",
                "conflict",
                expects_reply=True,
                reply_to_delivery_id=request.delivery_id,
            )
            blocked.ack_delivery(conflict.delivery_id)
            with self.assertRaisesRegex(RoutingError, "explicit revision response"):
                blocked.report("modeling", "completed", "cannot silently complete after conflict")
            blocked.report("modeling", "blocked", "cannot revise")

    def test_mcp_rejects_forged_reply_fields_and_preserves_optional_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(Path(directory), {("modeling", "protocol")})
            request = {
                "method": "tools/call",
                "params": {
                    "name": "send_team_message",
                    "arguments": {
                        "recipient_id": "protocol",
                        "text": "candidate",
                        "expects_reply": "true",
                    },
                },
            }
            with self.assertRaises(RoutingError):
                mcp_response(request, broker=broker, agent_id="modeling")
            request["params"]["arguments"] = {
                "recipient_id": "protocol",
                "text": "candidate",
                "reply_to_delivery_id": "delivery-forged",
            }
            with self.assertRaises(RoutingError):
                mcp_response(request, broker=broker, agent_id="modeling")
