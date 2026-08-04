from __future__ import annotations

import io
import json
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

from modeling_team.acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    RunnerAcceptanceCarrier,
    modeling_receipt_digest,
    ticket_digest,
)
from modeling_team.capability_mcp import run_stdio_client
from modeling_team.tests.test_r23005_contracts import _ticket
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


class R23005ARevisionTests(unittest.TestCase):
    def test_c91_acceptance_start_requires_distinct_modeling_and_protocol_phase_signals(self) -> None:
        phases = CoordinatorPhaseController()
        phases.start()
        phases.assign_slice(sender_id="coordinator", objective="fresh producer slice")
        generation = phases.generation
        with self.assertRaises(AcceptanceContractError):
            phases.start_acceptance_round(
                sender_id="coordinator", round_id="round-before-ready", generation=generation
            )
        phases.readiness(
            sender_id="modeling", message_kind="ready_for_acceptance", generation=generation
        )
        with self.assertRaises(AcceptanceContractError):
            phases.start_acceptance_round(
                sender_id="coordinator", round_id="round-before-silent", generation=generation
            )
        phases.readiness(
            sender_id="protocol", message_kind="silent_for_acceptance", generation=generation
        )
        phases.start_acceptance_round(
            sender_id="coordinator", round_id="round-after-both", generation=generation
        )

    def test_phase_controller_enforces_role_generation_and_round_reuse(self) -> None:
        phases = CoordinatorPhaseController()
        phases.start()
        phases.assign_slice(sender_id="coordinator", objective="slice")
        generation = phases.generation
        with self.assertRaises(AcceptanceContractError):
            phases.readiness(
                sender_id="protocol",
                message_kind="ready_for_acceptance",
                generation=generation,
            )
        with self.assertRaises(AcceptanceContractError):
            phases.readiness(
                sender_id="modeling",
                message_kind="ready_for_acceptance",
                generation=generation + 1,
            )
        phases.readiness(
            sender_id="modeling",
            message_kind="ready_for_acceptance",
            generation=generation,
        )
        phases.readiness(
            sender_id="protocol",
            message_kind="silent_for_acceptance",
            generation=generation,
        )
        self.assertEqual(phases.phase.value, "WAITING_ACCEPTANCE")
        phases.start_acceptance_round(
            sender_id="coordinator", round_id="round-one", generation=generation
        )
        phases.set_reports_ready()
        phases.route_verdict(
            sender_id="acceptance",
            verdict={"verdict": "PASS"},
            generation=generation,
        )
        self.assertEqual(phases.phase.value, "WAITING_ACCEPTANCE")
        self.assertEqual(phases.generation, generation)
        phases.start_acceptance_round(
            sender_id="coordinator", round_id="round-two", generation=generation
        )
        phases.set_reports_ready()
        phases.route_verdict(
            sender_id="acceptance",
            verdict={"verdict": "BLOCKED"},
            generation=generation,
        )
        self.assertEqual(phases.phase.value, "WAITING_ACCEPTANCE")
        self.assertEqual(phases.generation, generation)
        phases.assign_slice(sender_id="coordinator", objective="revised slice")
        self.assertEqual(phases.generation, generation + 1)
        generation = phases.generation
        phases.readiness(
            sender_id="modeling",
            message_kind="ready_for_acceptance",
            generation=generation,
        )
        phases.readiness(
            sender_id="protocol",
            message_kind="silent_for_acceptance",
            generation=generation,
        )
        phases.start_acceptance_round(
            sender_id="coordinator", round_id="round-three", generation=generation
        )
        phases.set_reports_ready()
        phases.route_verdict(
            sender_id="acceptance",
            verdict={"verdict": "FAIL"},
            generation=generation,
        )
        self.assertEqual(phases.phase.value, "MODELING_ACTIVE")
        self.assertEqual(phases.generation, generation + 1)

    def test_transport_coordination_is_role_aware_and_reaches_phase_controller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phases = CoordinatorPhaseController()
            phases.start()
            phases.assign_slice(sender_id="coordinator", objective="slice")

            def callback(sender, recipient, kind, text, generation):
                if kind in {"ready_for_acceptance", "silent_for_acceptance"}:
                    return phases.readiness(
                        sender_id=sender,
                        message_kind=kind,
                        text=text,
                        generation=generation,
                    )
                if kind == "acceptance_start":
                    return phases.start_acceptance_round(
                        sender_id=sender, round_id=text, generation=generation
                    )
                return phases.route_verdict(
                    sender_id=sender,
                    verdict=json.loads(text),
                    generation=generation,
                )

            permissions = {
                ("modeling", "coordinator"),
                ("protocol", "coordinator"),
                ("coordinator", "acceptance"),
                ("acceptance", "coordinator"),
            }
            broker = TeamTransportBroker(
                root / "transport",
                permissions,
                coordination_phase_callback=callback,
            )
            listed = mcp_response(
                {"method": "tools/list"}, broker=broker, agent_id="modeling"
            )
            coordination_tool = next(
                tool for tool in listed["tools"] if tool["name"] == "send_coordination"
            )
            self.assertEqual(
                coordination_tool["inputSchema"]["properties"]["message_kind"]["enum"],
                ["ready_for_acceptance"],
            )
            with self.assertRaises(RoutingError):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "send_coordination",
                            "arguments": {
                                "recipient_id": "coordinator",
                                "message_kind": "silent_for_acceptance",
                                "text": "wrong role",
                                "generation": 1,
                            },
                        },
                    },
                    broker=broker,
                    agent_id="modeling",
                )
            for agent, recipient, kind, text in (
                ("modeling", "coordinator", "ready_for_acceptance", "ready"),
                ("protocol", "coordinator", "silent_for_acceptance", "quiet"),
                ("coordinator", "acceptance", "acceptance_start", "round-one"),
            ):
                result = mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "send_coordination",
                            "arguments": {
                                "recipient_id": recipient,
                                "message_kind": kind,
                                "text": text,
                                "generation": 1,
                            },
                        },
                    },
                    broker=broker,
                    agent_id=agent,
                )
                self.assertIn("content", result)
            phases.set_reports_ready()
            mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "send_coordination",
                        "arguments": {
                            "recipient_id": "coordinator",
                            "message_kind": "acceptance_verdict_route",
                            "text": json.dumps({"verdict": "PASS"}),
                            "generation": 1,
                        },
                    },
                },
                broker=broker,
                agent_id="acceptance",
            )
            with self.assertRaises(RoutingError):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "send_coordination",
                            "arguments": {
                                "recipient_id": "coordinator",
                                "message_kind": "ready_for_acceptance",
                                "text": "stale",
                                "generation": 2,
                            },
                        },
                    },
                    broker=broker,
                    agent_id="modeling",
                )

    def test_coordination_observer_failure_is_fatal_and_cannot_be_retried_cleanly(self) -> None:
        callback_calls: list[str] = []

        def callback(sender, _recipient, kind, _text, generation):
            callback_calls.append(kind)
            return {"event": "coordination", "generation": generation}

        def broken_observer(_event):
            raise OSError("observer-secret")

        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {("modeling", "coordinator"), ("protocol", "coordinator")},
                coordination_phase_callback=callback,
                coordination_event_observer=broken_observer,
            )
            with self.assertRaisesRegex(RoutingError, "^coordination evidence observer failed$"):
                broker.send_coordination(
                    "modeling", "coordinator", "ready_for_acceptance", "ready", 1
                )
            failure = broker.coordination_failure
            self.assertIsNotNone(failure)
            assert failure is not None
            self.assertEqual(failure["code"], "coordination_evidence_observer_failed")
            self.assertNotIn("observer-secret", json.dumps(failure))
            self.assertEqual(callback_calls, ["ready_for_acceptance"])
            with self.assertRaisesRegex(RoutingError, "^coordination evidence observer failed$"):
                broker.send_coordination(
                    "protocol", "coordinator", "silent_for_acceptance", "quiet", 1
                )
            self.assertEqual(callback_calls, ["ready_for_acceptance"])
            messages = broker.drain_coordination()
            self.assertEqual(len(messages), 1)
            self.assertTrue(messages[0].phase_event["fatal"])

    def test_capability_socket_stdio_and_exact_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance"
            )
            endpoint = carrier.capability_endpoint("acceptance")
            carrier.start_capability_endpoints()
            try:
                self.assertEqual(stat.S_IMODE(os.stat(carrier.capability_root).st_mode), 0o700)
                socket_root = carrier.capability_socket_root
                self.assertEqual(stat.S_IMODE(os.stat(socket_root).st_mode), 0o700)
                for role in ("coordinator", "acceptance"):
                    self.assertEqual(
                        stat.S_IMODE(os.stat(carrier.capability_token_path(role)).st_mode),
                        0o400,
                    )
                    self.assertEqual(
                        stat.S_IMODE(os.stat(carrier.capability_socket_path(role)).st_mode),
                        0o600,
                    )
                token = carrier.capability_token("acceptance")
                listed = endpoint.handle(
                    {"id": 1, "token": token, "method": "tools/list", "params": {}}
                )
                self.assertEqual(
                    [tool["name"] for tool in listed["result"]["tools"]],
                    list(carrier.capability_descriptors["acceptance"]["operations"]),
                )
                wrong_token = endpoint.handle(
                    {"id": 2, "token": "wrong", "method": "tools/list", "params": {}}
                )
                self.assertIn("error", wrong_token)
                rejected_extra = endpoint.handle(
                    {
                        "id": 3,
                        "token": token,
                        "method": "tools/call",
                        "params": {
                            "name": "acceptance_get_ticket",
                            "arguments": {
                                "acceptance_id": "acceptance",
                                "round_id": "round-one",
                                "ack": False,
                            },
                        },
                    }
                )
                self.assertIn("error", rejected_extra)
                rejected_role = endpoint.handle(
                    {
                        "id": 4,
                        "token": token,
                        "method": "tools/call",
                        "params": {
                            "name": "coordinator_get_verdict",
                            "arguments": {
                                "coordinator_id": "coordinator",
                                "acceptance_round_id": "round-one",
                                "verdict_digest": None,
                            },
                        },
                    }
                )
                self.assertIn("error", rejected_role)
                input_stream = io.StringIO(
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                    + "\n"
                    + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                    + "\n"
                    + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                    + "\n"
                )
                output_stream = io.StringIO()
                self.assertEqual(
                    run_stdio_client(
                        str(endpoint.socket_path),
                        carrier.capability_token_path("acceptance"),
                        stdin=input_stream,
                        stdout=output_stream,
                    ),
                    0,
                )
                responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
                self.assertEqual([item["id"] for item in responses], [1, 2])
                self.assertEqual(responses[1]["result"]["tools"][0]["name"], "acceptance_get_ticket")
            finally:
                carrier.cleanup()
                self.assertFalse(carrier.capability_root.exists())
                self.assertFalse(carrier.capability_socket_path("acceptance").exists())
                self.assertFalse(carrier.capability_socket_path("coordinator").exists())
                self.assertFalse(carrier.capability_token_path("acceptance").exists())
                self.assertFalse(carrier.capability_token_path("coordinator").exists())
                if socket_root != carrier.capability_root:
                    self.assertFalse(socket_root.exists())

    def test_failed_round_rejects_id_only_rerun(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance"
            )
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            carrier._rounds[ticket["acceptance_round_id"]]["verdict"] = {"verdict": "FAIL"}
            rerun = json.loads(json.dumps(ticket))
            rerun["ticket_id"] = "ticket-r23005-2"
            rerun["acceptance_round_id"] = "round-r23005-2"
            rerun["producer_run_id"] = "producer-r23005-2"
            rerun["ticket_revision"] = 2
            for receipt in rerun["modeling_receipts"]:
                receipt["run_id"] = rerun["producer_run_id"]
                receipt["receipt_digest"] = None
                receipt["receipt_digest"] = modeling_receipt_digest(receipt)
            rerun["ticket_digest"] = ticket_digest(rerun)
            for receipt in rerun["modeling_receipts"]:
                receipt["evidence_ref"]["ticket_digest"] = rerun["ticket_digest"]
            with self.assertRaisesRegex(AcceptanceContractError, "unchanged Acceptance rerun"):
                carrier.publish_ticket(
                    rerun,
                    coordinator_id="coordinator",
                    owner_revision=rerun["quality_standard_ref"],
                )
            semantic_rerun = json.loads(json.dumps(rerun))
            semantic_rerun["slice_revision"] = "slice-2"
            for receipt in semantic_rerun["modeling_receipts"]:
                receipt["slice_revision"] = semantic_rerun["slice_revision"]
                receipt["receipt_digest"] = None
                receipt["receipt_digest"] = modeling_receipt_digest(receipt)
            semantic_rerun["ticket_digest"] = ticket_digest(semantic_rerun)
            for receipt in semantic_rerun["modeling_receipts"]:
                receipt["evidence_ref"]["ticket_digest"] = semantic_rerun["ticket_digest"]
            carrier.publish_ticket(
                semantic_rerun,
                coordinator_id="coordinator",
                owner_revision=semantic_rerun["quality_standard_ref"],
            )
            self.assertIn(semantic_rerun["acceptance_round_id"], carrier._tickets)
            carrier._rounds[ticket["acceptance_round_id"]]["status"] = "cleaned"
            carrier._rounds[semantic_rerun["acceptance_round_id"]]["status"] = "cleaned"
            carrier.cleanup()

    def test_source_child_receives_exact_staged_bytes(self) -> None:
        payload = b"staged source bytes\n"
        ticket = _ticket()
        source_digest = hashlib.sha256(payload).hexdigest()
        ticket["approved_sources"][0]["sha256"] = source_digest
        ticket["source_bundle_digest"] = hashlib.sha256(
            json.dumps(
                ticket["approved_sources"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        ticket["ticket_digest"] = ticket_digest(ticket)
        for receipt in ticket["modeling_receipts"]:
            receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.md"
            source.write_bytes(payload)
            carrier = RunnerAcceptanceCarrier(
                base / "carrier",
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
                source_materials={"source.md": source},
            )
            try:
                carrier.publish_ticket(
                    ticket,
                    coordinator_id="coordinator",
                    owner_revision=ticket["quality_standard_ref"],
                )
                carrier.ack_ticket(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    ticket_digest_value=ticket["ticket_digest"],
                )
                projection, projection_digest = carrier.project_child_input(
                    round_id=ticket["acceptance_round_id"], kind="source"
                )
                handle = carrier.start_child(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    kind="source",
                    input_ref=projection,
                    input_digest=projection_digest,
                    ticket_digest_value=ticket["ticket_digest"],
                    request_id="source-staged",
                    attempt=0,
                )
                staged = (
                    carrier.root
                    / "acceptance"
                    / ticket["acceptance_round_id"]
                    / "children"
                    / handle.digest
                    / "sources"
                    / "source.md"
                )
                self.assertEqual(staged.read_bytes(), payload)
            finally:
                round_data = carrier._rounds[ticket["acceptance_round_id"]]
                round_data["children"].clear()
                round_data["status"] = "cleaned"
                carrier._handles.clear()
                carrier._resources.clear()
                carrier.cleanup()


if __name__ == "__main__":
    unittest.main()
