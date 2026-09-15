from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
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
            # R2.3-009 follow-up (user 2026-08-20): a role self-declares that it
            # is definitively stuck, so ``blocked`` no longer requires upstream
            # terminal handoffs; only ``completed`` does.
            broker.report("protocol", "blocked", "protocol result")
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling, protocol"):
                broker.report("coordinator", "completed", "early coordinator retry")
            broker.ack_terminal_handoff("coordinator", "modeling")
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
                self.assertEqual(early["error"]["code"], -32000)
                # R2.3-009/#14: the stdio facade keeps the broker's fixed typed
                # rejection text instead of collapsing every refusal into the
                # generic sentence, so the role can diagnose its own call.
                self.assertEqual(
                    early["error"]["message"],
                    "terminal result requires terminal handoffs: modeling",
                )
                self.assertNotIn("result", early)
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

    def test_stdio_issue_control_rejection_is_jsonrpc_error(self) -> None:
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("protocol", "coordinator"), ("coordinator", "protocol")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            broker.start(["coordinator"])
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                item for item in (str(root), environment.get("PYTHONPATH", "")) if item
            )
            environment["TEAM_TRANSPORT_SOCKET"] = str(broker.endpoint("coordinator"))
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
                rejected = rpc(
                    2,
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "issue_control",
                            "arguments": {
                                "issue_id": "issue-1",
                                "reporter_id": "protocol",
                                "action": "pause",
                                "control_epoch": 1,
                                "unknown": None,
                            },
                        },
                    },
                )
                self.assertEqual(
                    rejected,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "error": {
                            "code": -32000,
                            # The broker's own fixed text, not the generic
                            # fallback: the caller learns which field was wrong
                            # without the rejected argument value being echoed.
                            "message": "issue_control arguments are invalid",
                        },
                    },
                )
                self.assertNotIn("unknown", json.dumps(rejected))
            finally:
                if process.stdin is not None:
                    process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                broker.stop()

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

    def test_terminal_reply_rejection_names_the_delivery_and_the_legal_exits(self) -> None:
        """R3.0-015 issue-4: the terminal-reply refusal must be locatable.

        The incident's first failure was ``MCP -32000: terminal result requires
        delivered reply``: no delivery id, no peer, and no legal exit, so the
        host could not tell whether to wait, to have Protocol answer, or to
        settle the issue, and Modeling could not see that ``blocked`` was still
        open to it.  The guard itself stays -- a completed report still needs
        its delivered reply -- but the refusal now names both.
        """

        with tempfile.TemporaryDirectory() as directory:
            events: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
                transport_event_observer=events.append,
            )
            candidate = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            with self.assertRaises(RoutingError) as rejection:
                mcp_response(
                    self._report_request("completed", "candidate is final"),
                    broker=broker,
                    agent_id="modeling",
                )
            message = str(rejection.exception)
            self.assertIn(f"delivery_id={candidate.delivery_id}", message)
            self.assertIn("to protocol", message)
            self.assertIn("report blocked", message)
            self.assertEqual(
                [(event["status"], event["category"]) for event in events],
                [("rejected", "terminal_reply_undelivered")],
            )
            # The sanitized event shape is unchanged: only the category differs.
            self.assertEqual(
                set(events[0]),
                {"agent", "tool", "status", "category", "ack", "recorded_at_ns"},
            )
            # ``blocked`` stays the legal escape while the reply is outstanding.
            broker.report("modeling", "blocked", "the reply can never arrive")
            self.assertEqual(broker.results["modeling"].status, "blocked")

    def test_terminal_reply_gate_categories_are_distinct_and_name_their_exit(self) -> None:
        """Each reply-binding refusal is observable as its own category (issue-4)."""

        with tempfile.TemporaryDirectory() as directory:
            events: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
                transport_event_observer=events.append,
            )
            with self.assertRaisesRegex(RoutingError, "established reply request"):
                mcp_response(
                    self._report_request("completed", "no request"),
                    broker=broker,
                    agent_id="modeling",
                )
            request = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            conflict = broker.send(
                "protocol",
                "modeling",
                "conflict",
                expects_reply=True,
                reply_to_delivery_id=request.delivery_id,
            )
            broker.ack_delivery(conflict.delivery_id)
            with self.assertRaises(RoutingError) as revision:
                mcp_response(
                    self._report_request("completed", "conflict unanswered"),
                    broker=broker,
                    agent_id="modeling",
                )
            self.assertIn(f"delivery_id={conflict.delivery_id}", str(revision.exception))
            self.assertIn("to protocol", str(revision.exception))
            self.assertIn("report blocked", str(revision.exception))
            self.assertEqual(
                [event["category"] for event in events],
                ["terminal_reply_request_missing", "terminal_revision_pending"],
            )

    def test_prompt_contract_names_standalone_delivery_and_resume_completion_request(self) -> None:
        """run6 issue-1/issue-2: the authoritative role prompts must state the
        reply-binding contract the terminal gate mechanically enforces.

        A standalone delivery that answers no delivered request never carries
        ``reply_to_delivery_id``; in a resumed or continued session with no open
        candidate request, Modeling establishes its reply request through one
        bounded completion-confirmation request and Coordinator answers it with
        a bound reply -- never a standalone ``expects_reply=false`` message and
        never an instruction to report terminal instead.
        """

        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("never carries `reply_to_delivery_id`", modeling)
        self.assertIn("bounded completion-confirmation request", modeling)
        self.assertIn("only then report `completed`", modeling)
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("completion-confirmation request", coordinator)
        self.assertIn("standalone `expects_reply=false` message", coordinator)
        self.assertIn("never tell Modeling to report terminal `completed`", coordinator)

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

    def test_stdio_facade_bounds_broker_error_text_and_hides_non_string_payloads(self) -> None:
        """The facade surfaces only the broker's own bounded fixed text.

        The broker socket is an internal channel: what reaches the Agent must
        stay a bounded string, so an over-long or non-string broker error keeps
        the generic rejection sentence instead of widening the reflection
        surface to structured broker payloads.
        """

        root = Path(__file__).parents[2]
        cases = [
            ("typed broker text", "recipient is not allowed by frozen Profile"),
            ("over-long broker text", "x" * 201),
            ("non-string broker payload", {"detail": "recipient is not allowed"}),
        ]
        for label, broker_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                endpoint = Path(directory) / "stub-broker.sock"
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(endpoint))
                server.listen(1)
                expected = (
                    broker_error
                    if isinstance(broker_error, str) and 0 < len(broker_error) <= 200
                    else "Team Transport request rejected"
                )

                def serve_once() -> None:
                    connection, _ = server.accept()
                    with connection:
                        connection.makefile("r", encoding="utf-8").readline()
                        connection.sendall(
                            (json.dumps({"error": broker_error}) + "\n").encode("utf-8")
                        )

                thread = threading.Thread(target=serve_once, daemon=True)
                thread.start()
                environment = os.environ.copy()
                environment["PYTHONPATH"] = os.pathsep.join(
                    item for item in (str(root), environment.get("PYTHONPATH", "")) if item
                )
                environment["TEAM_TRANSPORT_SOCKET"] = str(endpoint)
                process = subprocess.Popen(
                    [sys.executable, "-m", "modeling_team.transport_mcp"],
                    cwd=root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                try:
                    assert process.stdin is not None
                    assert process.stdout is not None
                    process.stdin.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": 7,
                                "method": "tools/call",
                                "params": {"name": "send_team_message", "arguments": {}},
                            }
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    response = json.loads(process.stdout.readline())
                finally:
                    if process.stdin is not None:
                        process.stdin.close()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    server.close()
                    thread.join(timeout=5)
                self.assertEqual(response["error"]["code"], -32000)
                self.assertEqual(response["error"]["message"], expected)
                self.assertNotIn("result", response)
                if not isinstance(broker_error, str):
                    self.assertNotIn("detail", json.dumps(response))

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
