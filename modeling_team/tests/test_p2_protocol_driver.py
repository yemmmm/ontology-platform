from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from shutil import rmtree

from modeling_team.contracts import digest_file, repository_root
from modeling_team.p2_protocol_driver import (
    CONTRACT_RELATIVE_PATH,
    PROTOCOL_ID,
    SYNTHETIC_MODELING_ID,
    _Evidence,
    SYNTHETIC_RELATION_IRI,
    SYNTHETIC_SOURCE_IRI,
    SYNTHETIC_TARGET_IRI,
    _validate_candidate_receipt,
    _build_configuration,
    _synthetic_candidate,
    load_contract,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import AgentRuntimeIdentity, RuntimeAdapter, RuntimeDelivery


class _HandoffAdapter(RuntimeAdapter):
    def __init__(self) -> None:
        self.messages: list[tuple[str, RuntimeDelivery]] = []

    def start_roster(self, run, agents):
        return [AgentRuntimeIdentity(agent.agent_id, "test") for agent in agents]

    def start_task(self, agent_id, task_text, skill_paths, roster):
        return None

    def probe_role_visibility(self, run):
        return {}

    def send_message(self, agent_id, delivery):
        self.messages.append((agent_id, delivery))

    def receive_messages(self):
        return []

    def get_agent_states(self):
        return []

    def wait_settled(self, agent_ids, timeout):
        return True

    def pause(self):
        return None

    def resume(self):
        return None

    def stop(self):
        return None

    def cleanup_identifiers(self):
        return {}


class P2ProtocolDriverTests(unittest.TestCase):
    def test_synthetic_candidate_compiles_to_exact_asserted_relation_quad(self) -> None:
        from app.core.config import Settings
        from app.services.semantic_command_compiler import compile_create_relation
        from app.services.semantic_export import SemanticNamespace

        candidate, _ = _synthetic_candidate()
        item = candidate["items"][0]
        settings = Settings(_env_file=None)
        namespace = SemanticNamespace(settings.semantic_base_iri, settings.semantic_graph_iri_prefix)
        compiled = compile_create_relation(
            {
                "ontology_id": "p2-ontology",
                "source_entity_iri": SYNTHETIC_SOURCE_IRI,
                "relation_type_iri": SYNTHETIC_RELATION_IRI,
                "target_entity_iri": SYNTHETIC_TARGET_IRI,
            },
            namespace,
            settings,
        )
        expected = (
            f"<{item['subject']}>",
            f"<{item['predicate']}>",
            f"<{item['object']}>",
            str(namespace.graph("data", "p2-ontology")),
        )
        self.assertEqual(compiled.delta.inserts, [expected])
        self.assertEqual(item["object_kind"], "iri")
        self.assertIsNone(item["object_datatype"])
        self.assertIsNone(item["object_language"])

    def test_candidate_receipt_requires_exact_identity_and_status(self) -> None:
        from modeling_team.transport_mcp import Delivery

        candidate, digest = _synthetic_candidate()
        reply = Delivery(
            sequence=2,
            sender_id=PROTOCOL_ID,
            recipient_id=SYNTHETIC_MODELING_ID,
            text=json.dumps(
                {
                    "status": "accepted",
                    "candidate_revision": candidate["candidate_revision"],
                    "semantic_digest": digest,
                },
                sort_keys=True,
            ),
            timestamp=1.0,
            delivery_id="delivery-2",
            reply_to_delivery_id="delivery-1",
        )
        _validate_candidate_receipt(reply, candidate, digest, "delivery-1")
        with self.assertRaisesRegex(RuntimeError, "receipt"):
            _validate_candidate_receipt(
                Delivery(**{**reply.__dict__, "text": "{}"}),
                candidate,
                digest,
                "delivery-1",
            )

    def test_descriptor_and_schema_v2_protocol_only_configuration(self) -> None:
        root = repository_root()
        contract_path = root / CONTRACT_RELATIVE_PATH
        contract = load_contract(contract_path)
        self.assertEqual(contract["candidate_sender_id"], SYNTHETIC_MODELING_ID)
        self.assertEqual(contract["protocol_agent_id"], PROTOCOL_ID)
        configuration = _build_configuration(root, contract)
        self.assertEqual(configuration.task.schema_version, 2)
        self.assertEqual([agent.package.role for agent in configuration.profile.agents], ["protocol"])
        self.assertEqual(configuration.task.role_sources[0].roles, frozenset({"protocol"}))
        self.assertNotIn("business-source", [source.classification for source in configuration.task.role_sources])

    def test_baseline_binds_driver_and_descriptor(self) -> None:
        root = repository_root()
        manifest, _ = TeamRunner.preview_baseline(
            repository_root=root,
            run_id="p2-protocol-baseline",
            profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
        )
        self.assertEqual(
            manifest["files"]["p2_protocol_driver"],
            digest_file(root / "modeling_team/p2_protocol_driver.py"),
        )
        self.assertEqual(
            manifest["files"]["p2_protocol_driver_contract"],
            digest_file(root / CONTRACT_RELATIVE_PATH),
        )
        self.assertEqual(
            manifest["runtime_contract"]["p2_protocol_driver"]["required_terminal_stage"],
            "protocol_report_accepted",
        )
        self.assertEqual(
            manifest["files"]["proof_v2"],
            digest_file(root / "modeling_team/proof_v2.py"),
        )
        self.assertEqual(
            manifest["files"]["p2_monitor_adverse_order_profile"],
            digest_file(root / "modeling_team/profiles/p2-adverse-order-smoke.yaml"),
        )
        self.assertEqual(
            manifest["files"]["p2_monitor_adverse_order_task"],
            digest_file(root / "modeling_team/tasks/p2-adverse-order-smoke.yaml"),
        )
        self.assertEqual(
            manifest["runtime_contract"]["p2_monitor_adverse_order"]["extractor"],
            "modeling_team.foreground_monitor.extract_adverse_order",
        )
        self.assertEqual(
            manifest["files"]["monitor_handoff"],
            digest_file(root / "modeling_team/monitor_handoff.py"),
        )
        self.assertEqual(
            manifest["files"]["p2_monitor_handoff_contract"],
            digest_file(root / "modeling_team/references/p2-monitor-handoff-contract.json"),
        )
        self.assertEqual(
            manifest["runtime_contract"]["p2_monitor_adverse_order"]["handoff_environment"],
            "ONTOLOGY_P2_MONITOR_HANDOFF",
        )
        self.assertEqual(
            manifest["runtime_contract"]["p2_monitor_adverse_order"]["handoff_phase_deadlines_seconds"],
            {"prepared": 30.0, "foreground_run": 120.0, "extraction_complete": 30.0},
        )

    def test_candidate_is_nonempty_canonical_and_evidence_rejects_forbidden_provenance(self) -> None:
        candidate, digest = _synthetic_candidate()
        self.assertTrue(candidate["items"])
        self.assertEqual(
            candidate["items"],
            sorted(
                candidate["items"],
                key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                ),
            ),
        )
        self.assertEqual(len(digest), 64)
        with tempfile.TemporaryDirectory() as directory:
            evidence = _Evidence(Path(directory) / "evidence.jsonl", ["runner/terminal-result"])
            evidence.append("candidate_delivered", delivery_id="delivery-1")
            with self.assertRaisesRegex(RuntimeError, "forbidden"):
                evidence.append("bad", sender_id="runner/terminal-result")

    def test_targeted_broker_claim_keeps_candidate_out_of_reply_queue(self) -> None:
        from modeling_team.transport_mcp import TeamTransportBroker

        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory),
                {(SYNTHETIC_MODELING_ID, PROTOCOL_ID), (PROTOCOL_ID, SYNTHETIC_MODELING_ID)},
            )
            candidate = broker.send(
                SYNTHETIC_MODELING_ID,
                PROTOCOL_ID,
                "candidate",
                expects_reply=True,
            )
            self.assertEqual(broker.drain_for(delivery_id=candidate.delivery_id), [candidate])
            reply = broker.send(
                PROTOCOL_ID,
                SYNTHETIC_MODELING_ID,
                "receipt",
                reply_to_delivery_id=candidate.delivery_id,
            )
            self.assertEqual(
                broker.drain_for(sender_id=PROTOCOL_ID, recipient_id=SYNTHETIC_MODELING_ID),
                [reply],
            )

    def test_runner_terminal_handoff_contains_bounded_protocol_redrive(self) -> None:
        root = repository_root()
        run_id = "p2-redrive-test"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        adapter = _HandoffAdapter()
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "synthetic result")
            runner.drain()
            protocol_handoffs = [
                delivery
                for recipient, delivery in adapter.messages
                if recipient == "protocol" and delivery.kind == "terminal-handoff"
            ]
            self.assertEqual(len(protocol_handoffs), 1)
            payload = json.loads(protocol_handoffs[0].text)
            self.assertEqual(payload["next_action"], "retry_report_task_result_once")
            self.assertIn("exactly once", payload["instruction"])
        finally:
            if runner.run is not None:
                runner.cleanup()
            if run_root.exists():
                rmtree(run_root)


if __name__ == "__main__":
    unittest.main()
