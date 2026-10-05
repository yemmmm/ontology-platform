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
                            # fallback.  R3.0-016 #20 family: the refusal now
                            # names the schema field so the caller can fix the
                            # call without a diagnosis round trip, while the
                            # rejected argument VALUE stays unechoed.
                            "message": "issue_control arguments are invalid: unexpected: unknown",
                        },
                    },
                )
                self.assertNotIn('"unknown": null', json.dumps(rejected))
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
            self.assertIn(candidate.delivery_id, broker._pending_replies)
            broker.ack_delivery(queued_reply.delivery_id)
            self.assertNotIn(candidate.delivery_id, broker._pending_replies)
            broker.report("modeling", "completed", "reply delivered")

    def test_pending_reply_does_not_block_modeling_terminal_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            candidate = broker.send("modeling", "protocol", "candidate", expects_reply=True)
            broker.report("modeling", "completed", "candidate work is complete")
            self.assertEqual(broker.results["modeling"].status, "completed")
            self.assertIn(candidate.delivery_id, broker._pending_replies)

    def test_inbound_revision_request_does_not_create_a_terminal_hard_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "protocol"), ("protocol", "modeling")},
                modeling_agent_id="modeling",
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
            broker.report("modeling", "completed", "no more semantic work remains")
            self.assertEqual(broker.results["modeling"].status, "completed")

    def test_prompt_contract_does_not_require_synthetic_completion_request(self) -> None:
        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("never carries `reply_to_delivery_id`", modeling)
        self.assertNotIn("completion-confirmation request", modeling)
        self.assertIn("do not create a reply request solely to unlock a terminal result", modeling)

    def test_modeling_prompt_separates_annotation_omission_null_and_unknown(self) -> None:
        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        contract = json.loads(
            (
                root / "modeling_team/references/platform-neutral-candidate-authoring.json"
            ).read_text(encoding="utf-8")
        )
        parameter = contract["reusable_action_semantics"]["annotations"][
            "parameter_definition"
        ]
        self.assertEqual(
            parameter["result_kind"],
            ["updated_input", "new_object", "computed_value", "unknown"],
        )
        self.assertIn("omission means no information and no default is inferred", modeling)
        self.assertIn("never a placeholder for an unset field", modeling)
        self.assertIn("`result_kind` never take null", modeling)
        self.assertIn("`result_kind` allows exactly `updated_input`, `new_object`,", modeling)
        self.assertIn("`new_object` guess for an unknown or not-applicable input", modeling)
        self.assertIn("instead of encoding them as nulls", modeling)
        self.assertIn("re-validate the complete annotations", modeling)
        self.assertIn("Protocol translates approved annotations", modeling)
        for value in parameter["result_kind"]:
            self.assertIn(f"`{value}`", modeling)
        for field in ("value_type", "required", "unit", "missing_meaning"):
            self.assertIn(f"`{field}`", modeling)

    def test_protocol_prompt_omits_unused_reply_binding_instead_of_placeholders(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`reply_to_delivery_id` is an optional binding", protocol)
        self.assertIn("omits the field entirely: never write the strings", protocol)
        self.assertIn("`null`, `text` or `plain`", protocol)
        self.assertIn("omitting the field is the intended", protocol)
        self.assertIn("one correctable message-parameter error:", protocol)
        self.assertIn("resend the same report, never replaying already applied content", protocol)
        self.assertIn("keep the typed error for platform diagnosis", protocol)
        # The ambiguous notation that read as a literal "null" string is gone.
        self.assertNotIn("`reply_to_delivery_id=null`", protocol)
        self.assertIn("lost to a Team Transport delivery-parameter", coordinator)
        self.assertIn("never commissions re-modeling, replay or re-apply", coordinator)

    def test_modeling_prompt_omits_unused_reply_binding_instead_of_placeholders(self) -> None:
        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        # The start2 issue: Modeling sent reply_to_delivery_id as the string
        # "null" on standalone candidate handoffs, and every send was rejected
        # with MCP-32000 "reply is not an active reversed request" (zero real
        # delivery).  The prompt must carry the same omit-don't-placeholder
        # contract Protocol already has, adapted to direct candidate delivery.
        self.assertIn("`reply_to_delivery_id` is an optional binding", modeling)
        self.assertIn("omits the field entirely: never write the strings", modeling)
        self.assertIn("`null`, `text` or `plain`", modeling)
        self.assertIn("another Agent's ID such as the Coordinator's", modeling)
        self.assertIn("omitting the field is the intended representation", modeling)
        self.assertIn("one correctable message-parameter error:", modeling)
        self.assertIn("not grounds to pause the run", modeling)
        self.assertIn("the transport metadata and resend the SAME candidate unchanged", modeling)
        self.assertIn("never replaying an already applied operation to deliver it", modeling)
        self.assertIn("never counts as delivered; read the actual tool result", modeling)
        # No ambiguous null-style notation in the handoff section.
        self.assertNotIn("`reply_to_delivery_id=null`", modeling)

    def test_prompts_do_not_open_reply_duties_with_pure_acknowledgements(self) -> None:
        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        # The repeated defect: two roles kept exchanging pure confirmations
        # ("boundary accepted, content unchanged, holding") with
        # expects_reply=true, so every acknowledgement generated another
        # acknowledgement turn with no new content.  The ordinary-message
        # contract: a pure acknowledgement closes its own loop and never
        # opens a reply duty; a real request still gets exactly one reply.
        for prompt in (modeling, protocol):
            self.assertIn("confirming receipt, an accepted boundary, unchanged content, or a", prompt)
            self.assertIn("never opens a reply duty: send it with", prompt)
            self.assertIn("Never acknowledge an acknowledgement: an ordinary confirmation you receive", prompt)
            self.assertIn("keeps generating turns with no new", prompt)
            self.assertIn("gets exactly one reply,", prompt)
            self.assertIn("send no further handshake messages on your", prompt)
            self.assertIn("when you have no new question or result", prompt)
        # The rule never generalizes into bypassing real obligations: review
        # and approval requests keep expects_reply=true, and the typed
        # builder / candidate delivery contracts keep priority.
        self.assertIn("a candidate or translation review request, and", protocol)
        self.assertIn("keep the existing `expects_reply=true` contract, and the typed", protocol)
        self.assertIn("receipt/conflict builder requirements keep their priority", protocol)
        self.assertIn("a candidate review or revision request, and", modeling)
        self.assertIn("keep the existing `expects_reply=true` contract; the candidate", modeling)
        self.assertIn("delivery and revision contracts above keep their priority", modeling)

    def test_protocol_prompt_does_not_claim_a_completed_report_is_refused(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("A completed terminal report does not answer that candidate", protocol)
        self.assertNotIn("refuses a completed terminal report", protocol)

    def test_protocol_prompt_sources_property_meaning_from_the_property_item(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        # Synthetic generic unified-graph nodes: one property item whose
        # top-level business_meaning is distinct from its
        # semantic_definition.business_meaning (with an explicit unknown and
        # applicability), and two relation items using the same predicate,
        # each with its own per-edge business_meaning.  The first field
        # defect filled the property description from generic predicate
        # labels; the second aggregated the relation edges' meanings into the
        # predicate definition.  Both translations were rejected before the
        # dry-run with zero writes; the prompt must pin the correct source
        # for each node kind so the next translation starts correct.
        property_item = {
            "item_id": "prop-1",
            "item_kind": "property",
            "business_meaning": "confirmed definition meaning of the predicate",
            "unknowns": ["applicability to one subcase unconfirmed"],
            "semantic_definition": {
                "semantic_role": "object",
                "business_meaning": "distinct declared meaning of the definition",
                "applicability": "the scope the definition declares",
                "unknowns": ["one declared unknown"],
            },
        }
        relation_items = [
            {
                "item_id": "rel-1",
                "item_kind": "relation",
                "business_meaning": "meaning of this edge expression",
            },
            {
                "item_id": "rel-2",
                "item_kind": "relation",
                "business_meaning": "meaning of that other edge expression",
            },
        ]
        assert property_item["business_meaning"] != (
            property_item["semantic_definition"]["business_meaning"]
        )
        assert len({item["business_meaning"] for item in relation_items}) == len(relation_items)

        # create_property reads only the property item: both distinct
        # meanings are preserved, and the supported fields carry the rest.
        self.assertIn(
            "A `property` item's platform translation is sourced from that same approved property item",
            protocol,
        )
        self.assertIn("when its `semantic_definition` is present, that definition's", protocol)
        self.assertIn("both are preserved faithfully and never merged into", protocol)
        self.assertIn("`unknowns`, `not_applicable`/`conflicting_meanings` and `applicability`", protocol)
        self.assertIn("ride along through their existing supported payload fields", protocol)
        # Never the predicate label, a generic template, or an aggregation
        # over the edges that use the predicate.
        self.assertIn("from its predicate label, a generic template phrase, or an aggregation over the", protocol)
        self.assertIn("a meaning absent from the property item is an explicit", protocol)
        self.assertIn("never material sourced from elsewhere or", protocol)
        self.assertIn("add no new fields or business facts", protocol)
        # Each relation edge's meaning stays on that edge's translation and
        # lineage; it never redefines the predicate definition.
        self.assertIn("the meaning of that one edge expression", protocol)
        self.assertIn("stays in that edge's translation and lineage exactly as approved", protocol)
        self.assertIn("an edge-instance meaning is never aggregated, averaged or promoted into it", protocol)
        self.assertIn("property definition is never reconstructed from its usage", protocol)
        # Role boundary and unchanged validation.
        self.assertIn("never ask Modeling to write platform Items", protocol)
        self.assertIn("keep the existing faithful pre-write", protocol)

    def test_protocol_prompt_reads_relation_triples_through_the_facts_read_model(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        # The repeated field defect: after R1/R2 relation Batches applied,
        # get_ontology_read_model was called with model_name=relations and
        # then relation-list, each returning unsupported_read_model, and the
        # guesses kept coming instead of reading the mounted contract.  The
        # adapter (backend READ_MODEL_NAMES) offers no relations model: the
        # asserted data triples are facts -> statement-list.  The readback
        # also must verify rows, not counts: the baseline runs differ by
        # projection (one run's relation projection counts 32 triples over
        # 12 sources where another's core counts 29 over 17), so no listing
        # count proves a triple count.
        self.assertIn(
            "The read-model interface takes only the parameter and model names its mounted contract",
            protocol,
        )
        self.assertIn("read that contract first and never guess a spelling", protocol)
        self.assertIn(
            "rejection means the name sent is not offered by this adapter; it is not a hint that a sibling",
            protocol,
        )
        self.assertIn("`relations` or `relation-list` exists to discover by retrying", protocol)
        self.assertIn(
            "`model_name=facts` (the statement-list model), `include=asserted` and `field_set=detail`",
            protocol,
        )
        self.assertIn("(`field_set=evidence` is rejected)", protocol)
        # Verified against the mounted adapter: the request-level limit range
        # is 1..2000 and the model caps one page at its own ceiling with no
        # offset or cursor — no unverified unbounded-read convention.
        self.assertIn("`limit` accepts 1..2000", protocol)
        self.assertIn("the interface offers no offset or cursor", protocol)
        self.assertIn("(`returned`/`visible_count`/`has_more`/`truncated`/`complete`) says", protocol)
        self.assertIn(
            "never report it as complete coverage and never invent an offset, cursor,", protocol
        )
        self.assertIn("larger-limit or repeated-call continuation the contract does not offer", protocol)
        self.assertIn("`subject`/`predicate`/`object` rows themselves", protocol)
        self.assertIn("or projection row count is never the asserted triple count", protocol)
        self.assertIn("no count substitutes for the row-level check", protocol)
        # The data graph is not schema description; descriptions stay on the
        # governed query interfaces.
        self.assertIn("not a schema description", protocol)
        self.assertIn("existing governed interfaces such as", protocol)

    def test_prompts_adjudicate_cross_slice_relations_by_actual_triples(self) -> None:
        root = Path(__file__).resolve().parents[2]
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text(
            encoding="utf-8"
        )
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        # Issue4: the parts R1 plan was approved with 8 create_relation commands
        # and expected 656+8=664, but the complete asserted readback settled at
        # 662/662 — 2 of the 8 SPOs already existed from the immutable core and
        # the earlier R1 readback, so net new was 6 and every approved SPO was
        # present with no missing triple and no unknown write.  The defect
        # treated different client_item_ids as novel relations and command /
        # normalized-insert counts as the novel statement count.
        self.assertIn("A relation statement's identity across slices is its actual subject/predicate/object IRIs, not", modeling)
        self.assertIn("its candidate membership, `client_item_id`, or label spelling", modeling)
        self.assertIn("never a new one because a", modeling)
        self.assertIn("reference it per the mounted contract instead of authoring a duplicate", modeling)
        self.assertIn("Different predicates are never the same relation", modeling)
        self.assertIn("an unresolved identity is an explicit unknown or a Coordinator", modeling)
        self.assertIn("before-evidence instead of demanding a fresh full audit per batch.", modeling)
        self.assertIn("Cross-slice relation reuse and collision are adjudicated on the receipt-backed actual triple", protocol)
        self.assertIn("a command whose SPO already exists in the asserted set adds zero new unique", protocol)
        # Command insert counts are not set-growth counts; expected arithmetic
        # needs qualified before-evidence.
        self.assertIn("processed command inserts from new unique RDF statements in the set", protocol)
        self.assertIn("do not announce full-set counts or", protocol)
        self.assertIn("blindly expect before + command count", protocol)
        # The third-run delivery-15/16 defect: Protocol read
        # get_modeling_context semantic_counts relations moving 65 -> 68
        # across 7 submitted expressions as "4 duplicate SPOs".  Every
        # counter branch is COUNT(DISTINCT ?subject) -- relations counts
        # distinct source entities, facts distinct subjects -- while the
        # host's complete statement-list diff (662 -> 669) proved all 7
        # SPOs new, none preexisting, 0 extra, 0 removed.  The prompt must
        # pin the aggregate counter units so no delta arithmetic on those
        # fields substitutes for statement-list membership.
        self.assertIn("COUNT(DISTINCT ?subject)", protocol)
        self.assertIn("`relations` counts distinct source entities", protocol)
        self.assertIn("cannot derive the unique SPO count", protocol)
        self.assertIn("never arithmetic on", protocol)
        self.assertIn("`semantic_counts` deltas", protocol)
        # Post-apply: every approved SPO present under full paging; a missing
        # approved SPO is one concrete inconsistency, never the only kind —
        # unexplained extra content, deletions and binding differences are
        # write-integrity issues on the unknown-write gate, "no missing" is
        # never generalized into "no inconsistency", and only a fully-explained
        # pure count discrepancy reconciles; duplicates explain a count
        # difference without inventing unknown writes or compensations — and
        # count mismatch alone is never blanket-safe either.
        self.assertIn("check each approved SPO is present with full", protocol)
        self.assertIn("a genuinely missing approved SPO is one concrete inconsistency to", protocol)
        self.assertIn("investigate, not the only kind: unexplained extra content beyond the approved projection,", protocol)
        self.assertIn("a binding difference on an approved statement are equally real", protocol)
        self.assertIn("write-integrity inconsistencies that follow the existing unknown-write gate and recovery", protocol)
        self.assertIn('Never generalize "every approved SPO is present" into "no inconsistency exists".', protocol)
        self.assertIn("a pure count discrepancy that a complete readback and proven preexisting duplicates fully", protocol)
        self.assertIn("explain may be reconciled and continued.", protocol)
        self.assertNotIn("only a genuinely missing approved SPO", protocol)
        self.assertIn("keep the original expected and actual", protocol)
        self.assertIn("never infer an unknown write or make compensating writes from a", protocol)
        self.assertIn("never generalize the opposite rule that every count mismatch is safely", protocol)
        self.assertIn("a real unknown write keeps its existing closed write gate and recovery contract", protocol)
        # No new audit gate, no replay/delete/payload change.
        self.assertIn("no new per-batch full-audit gate", protocol)
        self.assertIn("is created, and no replay, delete or payload change is implied.", protocol)

    def test_transport_budget_splits_route_through_the_coordinator_not_new_tools(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text(
            encoding="utf-8"
        )
        # The exact-copy rule stays and is refined, not replaced, by the split rule.
        self.assertIn("complete `projection.items` copied exactly", protocol)
        self.assertIn("not a one-call completeness gate", protocol)
        self.assertIn(
            "request a new file-backed or reference-based batch tool", protocol
        )
        self.assertIn("do not treat submitting every item in a single call as a hard gate", protocol)
        self.assertIn("recoverable issue to the Coordinator and propose the split", protocol)
        self.assertIn("copied verbatim from the saved plan", protocol)
        self.assertIn("an arbitrary fixed chunk", protocol)
        self.assertIn("Old plan evidence is never overwritten", protocol)
        self.assertIn("already applied part is never", protocol)
        self.assertIn(
            "staged failure handling above before proposing any split", protocol
        )
        self.assertIn("not a tool gap", coordinator)
        self.assertIn("execute the saved projection as bounded parts", coordinator)
        self.assertIn("part's items copied exactly from the saved projection", coordinator)
        # The split approval never becomes direct batch submission authority.
        self.assertIn("never submit or approve a Modeling\nBatch directly", coordinator)

    def test_protocol_prompt_keeps_materialization_plan_root_closed(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(
            encoding="utf-8"
        )
        contract = json.loads(
            (root / "modeling_team/references/r3-0-009-unified-graph-contract.json").read_text(
                encoding="utf-8"
            )
        )
        # The p028 defect: the plan root carried a custom
        # existing_relation_triple_verifications key beyond the five canonical
        # fields; the Coordinator approved the business content, but the staged
        # capability still rejected the drift (unified_schema_mismatch) before
        # any forwarding — no Batch, Attempt or write.  The prompt must pin
        # the closed root and route verification-only evidence to a bound
        # companion artifact instead of a new root key.
        fields = contract["materialization_plan"]["fields"]
        self.assertEqual(
            fields,
            ["schema_version", "plan_id", "revision", "projection", "projection_digest"],
        )
        self.assertIn("The v2 materialization plan root is closed: exactly `schema_version`, `plan_id`, `revision`,", protocol)
        self.assertIn("`projection` and `projection_digest`, as the mounted contract's materialization-plan fields list", protocol)
        self.assertIn("Never add a custom root field for verification-only evidence, planning notes, status or", protocol)
        self.assertIn("an extra root key is schema drift the staged capability rejects before", protocol)
        self.assertIn("(`unified_schema_mismatch`), regardless of business approval", protocol)
        # Verification-only existing-fact checks ride outside the plan root,
        # digest-bound, full-content, and never a fabricated IRI.
        self.assertIn("checks of already-applied facts (for example existing relation triple verifications) are not plan", protocol)
        self.assertIn("keep them as a separate immutable companion artifact or existing approved message,", protocol)
        self.assertIn("explicitly bound to the plan's `plan_id`/`projection_digest`, with their full content preserved", protocol)
        self.assertIn("never folded into the plan root, never dropped, and never a fabricated", protocol)
        self.assertIn("relation resource IRI. Their existence never skips an approval or validation step, the", protocol)
        # Exact-copy forwarding unchanged; names verified against the schema,
        # not against runtime tolerance.
        self.assertIn("exact-copy projection forwarding below is unchanged, and field names are verified against the", protocol)
        self.assertIn("authoritative mounted schema, never inferred from what a runtime tool happens to accept.", protocol)

    def test_coordinator_prompt_uses_runner_dispatch_for_formal_issue_resolution(self) -> None:
        root = Path(__file__).resolve().parents[2]
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Runner's automatic broker `resume` or `abort`", coordinator)
        self.assertIn("automatically sends the bound broker `resume` or `abort`", coordinator)
        self.assertIn("check the actual gates before continuing without a second `resume`", coordinator)
        self.assertNotIn("your one bound `resume`", coordinator)
        self.assertNotIn("After the outer resolution is delivered, send exactly one bound", coordinator)
        self.assertNotIn("send exactly one bound `resume` carrying the exact", coordinator)
        self.assertNotIn("before sending the next `resume`", coordinator)
        self.assertIn("Runner's retained control dispatch", coordinator)
        self.assertIn('immediately call `issue_control` with `action: "pause"`', coordinator)
        self.assertIn("Reserve `unknown`, `uncertain`, `indeterminate`, and `mismatch`", coordinator)

    def test_coordinator_prompt_dispatches_only_to_the_frozen_profiles_enabled_peers(self) -> None:
        root = Path(__file__).resolve().parents[2]
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text(
            encoding="utf-8"
        )
        # The live defect: on the 4-role CQ Task the Coordinator sent
        # recipient_id=acceptance a hold-ticket/verdict message, the frozen
        # Profile rejected it (no delivery), and the prompt's hard-coded
        # "modeling, protocol, and acceptance" dispatch list kept the missing
        # role looking like an outstanding obligation.  The initial dispatch
        # must follow the Profile's actually-enabled peers; Acceptance exists
        # only when the current Profile enables it.
        self.assertIn("assign initial bounded work over Team Transport to each production peer the", coordinator)
        self.assertIn("current frozen Profile actually enables and gives a communication edge for this run", coordinator)
        self.assertIn("never requiring a role this Task's roster does not include", coordinator)
        self.assertIn("A role the current Profile does not enable — for example an acceptance role", coordinator)
        self.assertIn("that a CQ Task leaves to the Host's own Examiner handoff — has no communication edge", coordinator)
        self.assertIn("never send a hold, ticket, verdict or any other", coordinator)
        self.assertIn("message to a role the roster does not advertise", coordinator)
        self.assertIn("Profile-rejected send as an outstanding obligation to wait for or retry", coordinator)
        # No probing for names, no adding roles, no blanket gate-skipping.
        self.assertIn("probe alternative names,", coordinator)
        self.assertIn("or add the role yourself", coordinator)
        self.assertIn("Never skip Modeling or Protocol completion or their", coordinator)
        self.assertIn("review/dry-run/apply gates because a role is absent", coordinator)
        # The hard-coded roster list is gone; legacy typed-ticket Tasks with a
        # real Acceptance role keep their pipeline, and the Host-owned CQ
        # route never waives production validation/readback.
        self.assertNotIn("(modeling, protocol,", coordinator)
        self.assertIn("The formal ticket-based Tasks that genuinely include Acceptance keep", coordinator)
        self.assertIn("the Host-owned CQ acceptance route never waives actual", coordinator)
        self.assertIn("production validation and readback", coordinator)
        # The third-start handoff defect: the Coordinator listed all 18 public
        # questions in cross_slice_competency_questions and the runner rejected
        # the map (cq_projection_scenario_map_mismatch) because the check accepts
        # only panorama-scoped public projection entries -- 5 panorama vs 13
        # slice.  The prompt must pin that scope classification without touching
        # the frozen/public question sets: slice questions stay frozen and public
        # for independent acceptance, and map exclusion never drops a question.
        self.assertIn("`cross_slice_competency_questions` section carries only the approved public projection", coordinator)
        self.assertIn("questions whose `scope.kind` is `panorama`", coordinator)
        self.assertIn("each copied verbatim by `question_id` and", coordinator)
        self.assertIn("A public question scoped to", coordinator)
        self.assertIn("one slice never goes into this field", coordinator)
        self.assertIn("never dropping the question", coordinator)
        self.assertIn("and public sets for independent acceptance", coordinator)
        self.assertIn("before the final map update and the Host handoff", coordinator)
        self.assertIn("panorama-scoped entries only", coordinator)
        self.assertIn("you update the map section, not the frozen question sets", coordinator)

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

    def test_modeling_completed_does_not_need_a_reply_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("protocol", "modeling")},
                modeling_agent_id="modeling",
            )
            broker.send("protocol", "modeling", "ordinary")
            broker.report("protocol", "completed", "ordinary outbound is not gated")
            broker.report("modeling", "completed", "no synthetic request")

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
            self.assertIn(conflict.delivery_id, broker._pending_replies)
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
