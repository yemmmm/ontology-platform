from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    model_state_digest,
    modeling_receipt_digest,
    stage_handoff_digest,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.runtimes.base import RuntimeDelivery


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _policy() -> dict:
    return {
        "quality_standard_ref": "docs/requirements/requirements-v2.3.md#R2.3-005",
        "quality_standard_digest": "a" * 64,
        "quality_standard_artifact": {
            "path": "modeling_team/references/r2-3-005-acceptance-standard.json",
            "digest": "b" * 64,
        },
        "unknown_policy": "preserve-explicit-unknown",
        "competency_questions": [
            {"id": "cq-001", "question": "Which output is consumed?"},
            {"id": "cq-002", "question": "What happens when scoring is unavailable?"},
        ],
        "approved_source_paths_by_question": {
            "cq-001": ["source.md"],
            "cq-002": ["source.md"],
        },
    }


def _handoff(
    nonce: str,
    *,
    run_id: str = "run-r23005-e",
    task_id: str = "task-r23005-e",
    candidate_revision: str = "revision-1",
    candidate_digest: str = "e" * 64,
    artifact_records: dict[str, dict[str, str]] | None = None,
) -> dict:
    state = {
        "project_id": "project-r23005-e",
        "ontology_id": "ontology-r23005-e",
        "workspace_version": "workspace-e-1",
        "source_signature": "source-e-1",
        "build_session_id": "session-r23005-e",
        "graph_set_id": "graph-r23005-e",
    }
    state["state_digest"] = model_state_digest(state)
    receipts: list[dict] = []
    for stage, status in (
        ("dry-run", "validated"),
        ("apply", "applied"),
        ("readback", "complete"),
        ("validation", "succeeded"),
        ("reasoning", "succeeded"),
    ):
        artifact = artifact_records.get(stage) if artifact_records else None
        if artifact is None:
            artifact = {
                "tool": "get_modeling_context",
                "request_digest": "c" * 64,
                "response_digest": "d" * 64,
                "artifact_path": f"evidence/platform-responses/{'c' * 64}.json",
            }
        receipt = {
            "stage": stage,
            "status": status,
            "receipt_digest": None,
            "run_id": run_id,
            "project_id": state["project_id"],
            "ontology_id": state["ontology_id"],
            "slice_revision": candidate_revision,
            "model_state_digest": state["state_digest"],
            "evidence_ref": {
                "type": "platform_read",
                "ref_id": f"evidence-{stage}",
                "ticket_digest": "0" * 64,
                "model_state_digest": state["state_digest"],
                "tool": artifact["tool"],
                "request_digest": artifact["request_digest"],
                "response_digest": artifact["response_digest"],
                "artifact_path": artifact["artifact_path"],
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
        }
        receipt["receipt_digest"] = modeling_receipt_digest(receipt)
        receipts.append(receipt)
    handoff = {
        "schema_version": "r2-3-005-acceptance-stage-handoff/v1",
        "handoff_id": "handoff-r23005-e",
        "handoff_nonce": nonce,
        "task_id": task_id,
        "producer_run_id": run_id,
        "slice_id": "slice-r23005-e",
        "slice_revision": candidate_revision,
        "model_state": state,
        "model_state_digest": state["state_digest"],
        "candidate_digest": candidate_digest,
        "modeling_receipts": receipts,
        "handoff_digest": None,
    }
    handoff_digest = stage_handoff_digest(handoff)
    handoff["handoff_digest"] = handoff_digest
    for receipt in handoff["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = handoff_digest
    return handoff


def _register_stage_artifacts(carrier: RunnerAcceptanceCarrier) -> dict[str, dict[str, str]]:
    state = {
        "ontology_id": "ontology-r23005-e",
        "session_id": "session-r23005-e",
        "graph_set_id": "graph-r23005-e",
    }

    def submit_arguments(
        *,
        mode: str,
        client_batch_id: str,
        idempotency_key: str,
        expected_workspace_version: str,
        include_lease: bool,
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "session_id": state["session_id"],
            "client_batch_id": client_batch_id,
            "ontology_id": state["ontology_id"],
            "idempotency_key": idempotency_key,
            "expected_workspace_version": expected_workspace_version,
            "items": [
                {
                    "client_item_id": f"{client_batch_id}-item",
                    "command_kind": "create_class",
                    "payload": {"name": "Example"},
                }
            ],
            "mode": mode,
        }
        if include_lease:
            arguments["lease_token"] = "lease-r23005-e"
        return arguments

    calls = {
        "dry-run": (
            "submit_modeling_batch",
            submit_arguments(
                mode="dry_run",
                client_batch_id="batch-e-dry",
                idempotency_key="idempotency-e-dry",
                expected_workspace_version="workspace-e-0",
                include_lease=False,
            ),
            {"mode": "dry_run", "attempt_status": "validated"},
        ),
        "apply": (
            "submit_modeling_batch",
            submit_arguments(
                mode="apply_atomic",
                client_batch_id="batch-e-apply",
                idempotency_key="idempotency-e-apply",
                expected_workspace_version="workspace-e-0",
                include_lease=True,
            ),
            {
                "mode": "apply_atomic",
                "attempt_status": "applied",
                "workspace": {
                    "before_version": "workspace-e-0",
                    "after_version": "workspace-e-1",
                },
                "target": {"source_signature_after": "source-e-1"},
            },
        ),
        "readback": (
            "get_modeling_context",
            {"ontology_id": state["ontology_id"]},
            {
                "ontology": {"id": state["ontology_id"]},
                "workspace": {"workspace_version": "workspace-e-1"},
            },
        ),
        "validation": (
            "run_semantic_validation",
            {"graph_set_id": state["graph_set_id"]},
            {"status": "succeeded", "graph_set_id": state["graph_set_id"]},
        ),
        "reasoning": (
            "run_semantic_reasoning",
            {"graph_set_id": state["graph_set_id"]},
            {"status": "succeeded", "graph_set_id": state["graph_set_id"]},
        ),
    }
    records: dict[str, dict[str, str]] = {}
    for stage, (tool, arguments, data) in calls.items():
        records[stage] = carrier.register_platform_tool_result(
            tool=tool,
            arguments=arguments,
            result={"structuredContent": {"ok": True, "data": {"stage": stage, **data}}},
        )
    return records


def _stage_call_selection(
    carrier: RunnerAcceptanceCarrier,
    records: dict[str, dict[str, str]],
) -> dict[str, dict[str, object]]:
    catalog = carrier.protocol_list_platform_artifacts(
        protocol_id="protocol", capability=carrier.capability_token("protocol")
    )
    by_path = {item["artifact_path"]: item for item in catalog["artifacts"]}
    return {
        stage: {
            "tool": item["tool"],
            "arguments": item["request_arguments"],
            "artifact_path": item["artifact_path"],
        }
        for stage, record in records.items()
        for item in [by_path[record["artifact_path"]]]
    }


class R23005TicketPipelineTests(unittest.TestCase):
    def _carrier(self, root: Path, source: Path) -> RunnerAcceptanceCarrier:
        carrier = RunnerAcceptanceCarrier(
            root / "acceptance-carrier",
            task_id="task-r23005-e",
            acceptance_id="acceptance",
            source_materials={"source.md": source},
            ticket_policy=_policy(),
        )
        state = _handoff(carrier.stage_handoff_nonce)["model_state"]
        carrier.bind_model_state(state)
        carrier.register_accepted_candidate(
            candidate_revision="revision-1", candidate_digest="e" * 64
        )
        return carrier

    def test_handoff_builder_validates_delivery_then_unchanged_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                built = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                handoff = built["handoff_json"]
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                delivery = carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-1",
                    text=text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                self.assertEqual(delivery["text_digest"], _digest(handoff))
                draft = carrier.coordinator_build_acceptance_ticket_draft(
                    handoff,
                    handoff_delivery_id="delivery-1",
                    handoff_digest=handoff["handoff_digest"],
                    question_id="cq-001",
                    ticket_revision=1,
                    capability=carrier.capability_token("coordinator"),
                )
                self.assertEqual(draft["question_id"], "cq-001")
                self.assertEqual(len(draft["modeling_receipts"]), 5)
                published = carrier.coordinator_publish_acceptance_ticket(
                    draft,
                    owner_revision=draft["quality_standard_ref"],
                    capability=carrier.capability_token("coordinator"),
                )
                self.assertEqual(published["ticket_digest"], draft["ticket_digest"])
            finally:
                carrier.cleanup()

    def test_builder_output_classifier_ignores_question_reply_and_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                built = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                handoff_text = json.dumps(
                    built["handoff_json"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                self.assertTrue(carrier.classify_stage_handoff_delivery(handoff_text))
                reordered = dict(reversed(list(built["handoff_json"].items())))
                reordered_text = json.dumps(reordered, ensure_ascii=False, sort_keys=False, separators=(",", ":"))
                self.assertNotEqual(reordered_text, handoff_text)
                self.assertTrue(carrier.classify_stage_handoff_delivery(reordered_text))
                self.assertFalse(carrier.classify_stage_handoff_delivery('["cq-001","cq-002"]'))
                self.assertFalse(carrier.classify_stage_handoff_delivery('{"question_ids":["cq-001","cq-002"]}'))
                self.assertFalse(
                    carrier.classify_stage_handoff_delivery(
                        json.dumps(
                            {
                                "task_id": "task-r23005-e",
                                "producer_run_id": "run-r23005-e",
                                "answer": "ordinary protocol response",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                )

                mutated = json.loads(handoff_text)
                mutated["slice_revision"] = "revision-2"
                mutated_text = json.dumps(mutated, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                with self.assertRaisesRegex(AcceptanceContractError, "builder output was mutated"):
                    carrier.classify_stage_handoff_delivery(mutated_text)
            finally:
                carrier.cleanup()

    def test_wrong_frozen_question_id_does_not_consume_typed_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                handoff = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )["handoff_json"]
                handoff_text = json.dumps(
                    handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-5",
                    text=handoff_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                operation = "coordinator_build_acceptance_ticket_draft_from_delivery"
                with self.assertRaisesRegex(AcceptanceContractError, "not in the acceptance standard"):
                    carrier._dispatch_capability(
                        "coordinator",
                        operation,
                        {
                            "coordinator_id": "coordinator",
                            "handoff_delivery_id": "delivery-5",
                            "question_id": "cq-1",
                            "ticket_revision": 1,
                        },
                    )
                first = carrier._dispatch_capability(
                    "coordinator",
                    operation,
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-5",
                        "question_id": "cq-001",
                        "ticket_revision": 1,
                    },
                )
                self.assertEqual(first["question_id"], "cq-001")
                second = carrier._dispatch_capability(
                    "coordinator",
                    operation,
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-5",
                        "question_id": "cq-002",
                        "ticket_revision": 1,
                    },
                )
                self.assertEqual(second["question_id"], "cq-002")
            finally:
                carrier.cleanup()

    def test_runner_routes_question_id_reply_after_exact_handoff_registration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                handoff = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )["handoff_json"]
                reordered_handoff = dict(reversed(list(handoff.items())))
                reordered_text = json.dumps(
                    reordered_handoff, ensure_ascii=False, sort_keys=False, separators=(",", ":")
                )
                runner = TeamRunner(repository_root=Path(__file__).resolve().parents[2], adapter=object())
                runner.acceptance = carrier
                runner._formal_coordination_enabled = lambda: True  # type: ignore[method-assign]
                runner._formal_coordination_role_ids = lambda: {  # type: ignore[method-assign]
                    "coordinator": "coordinator",
                    "modeling": "modeling",
                    "protocol": "protocol",
                    "acceptance": "acceptance",
                }
                evidence: list[tuple[str, dict[str, str]]] = []
                runner._append_evidence = lambda name, value: evidence.append((name, value))  # type: ignore[method-assign]

                registered = runner._register_stage_handoff_delivery_if_exact(
                    RuntimeDelivery(
                        sender_id="protocol",
                        recipient_id="coordinator",
                        kind="peer",
                        text=reordered_text,
                        delivery_id="delivery-5",
                    )
                )
                self.assertEqual(registered["delivery_id"], "delivery-5")
                self.assertIsNone(
                    runner._register_stage_handoff_delivery_if_exact(
                        RuntimeDelivery(
                            sender_id="protocol",
                            recipient_id="coordinator",
                            kind="peer",
                            text='["cq-001","cq-002"]',
                            delivery_id="delivery-7",
                        )
                    )
                )
                self.assertEqual([name for name, _ in evidence], ["acceptance-stage-handoff"])
                first = carrier._dispatch_capability(
                    "coordinator",
                    "coordinator_build_acceptance_ticket_draft_from_delivery",
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-5",
                        "question_id": "cq-001",
                        "ticket_revision": 1,
                    },
                )
                second = carrier._dispatch_capability(
                    "coordinator",
                    "coordinator_build_acceptance_ticket_draft_from_delivery",
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-5",
                        "question_id": "cq-002",
                        "ticket_revision": 1,
                    },
                )
                self.assertEqual((first["question_id"], second["question_id"]), ("cq-001", "cq-002"))
            finally:
                carrier.cleanup()

    def _build_runner_for_carrier(self, carrier: RunnerAcceptanceCarrier) -> TeamRunner:
        runner = TeamRunner(repository_root=Path(__file__).resolve().parents[2], adapter=object())
        runner.acceptance = carrier
        runner._formal_coordination_enabled = lambda: True  # type: ignore[method-assign]
        runner._formal_coordination_role_ids = lambda: {  # type: ignore[method-assign]
            "coordinator": "coordinator",
            "modeling": "modeling",
            "protocol": "protocol",
            "acceptance": "acceptance",
        }
        evidence: list[tuple[str, dict[str, str]]] = []
        runner._append_evidence = lambda name, value: evidence.append((name, value))  # type: ignore[method-assign]
        runner._handoff_evidence = evidence  # type: ignore[attr-defined]
        return runner

    def test_token_relay_records_handoff_without_resent_json(self) -> None:
        # start58 regression: Protocol re-serializing ~7 KB of nested handoff
        # JSON mangled the bytes (dropped receipt braces), so classify's
        # json.loads failed and the delivery was never recorded.  The builder
        # now pre-binds the handoff under an opaque token (its handoff_id) and
        # Protocol relays only that short token, which cannot be mangled.
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                built = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                token = built["handoff_delivery_text"]
                self.assertEqual(token, built["handoff_json"]["handoff_id"])
                runner = self._build_runner_for_carrier(carrier)

                registered = runner._register_stage_handoff_delivery_if_exact(
                    RuntimeDelivery(
                        sender_id="protocol",
                        recipient_id="coordinator",
                        kind="peer",
                        text=token,
                        delivery_id="delivery-6",
                    )
                )
                self.assertEqual(registered["delivery_id"], "delivery-6")
                self.assertEqual(
                    registered["canonical_digest"], _digest(built["handoff_json"])
                )
                self.assertEqual(
                    [name for name, _ in runner._handoff_evidence],  # type: ignore[attr-defined]
                    ["acceptance-stage-handoff"],
                )
                draft = carrier._dispatch_capability(
                    "coordinator",
                    "coordinator_build_acceptance_ticket_draft_from_delivery",
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-6",
                        "question_id": "cq-001",
                        "ticket_revision": 1,
                    },
                )
                self.assertEqual(draft["question_id"], "cq-001")
                self.assertEqual(len(draft["modeling_receipts"]), 5)
            finally:
                carrier.cleanup()

    def test_token_relay_survives_where_mangled_json_text_fails(self) -> None:
        # The exact start58 failure mode: the re-serialized handoff JSON drops a
        # closing brace per receipt, so json.loads fails and the legacy
        # full-JSON classify path returns False.  The token relay path records
        # the same handoff without depending on that text.
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                built = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                token = built["handoff_delivery_text"]
                # Corrupt the full JSON the way start58 did: the re-serialized
                # nested receipts lost closing braces, leaving the document
                # unbalanced.  Drop one closing brace after the receipts array
                # opens so json.loads fails the same way.
                full_text = json.dumps(
                    built["handoff_json"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                break_at = full_text.find("}", full_text.find('"modeling_receipts"'))
                mangled_text = full_text[:break_at] + full_text[break_at + 1:]
                self.assertRaises(json.JSONDecodeError, json.loads, mangled_text)
                self.assertFalse(carrier.classify_stage_handoff_delivery(mangled_text))
                runner = self._build_runner_for_carrier(carrier)

                # Mangled text is not a recognized token and cannot classify.
                self.assertIsNone(
                    runner._register_stage_handoff_delivery_if_exact(
                        RuntimeDelivery(
                            sender_id="protocol",
                            recipient_id="coordinator",
                            kind="peer",
                            text=mangled_text,
                            delivery_id="delivery-mangled",
                        )
                    )
                )
                # The same handoff relayed by token records cleanly.
                registered = runner._register_stage_handoff_delivery_if_exact(
                    RuntimeDelivery(
                        sender_id="protocol",
                        recipient_id="coordinator",
                        kind="peer",
                        text=token,
                        delivery_id="delivery-token",
                    )
                )
                self.assertEqual(registered["delivery_id"], "delivery-token")
            finally:
                carrier.cleanup()

    def test_repeated_builds_keep_delivery_token_idempotent(self) -> None:
        # start58 built the handoff more than once.  The token pre-bind must
        # stay idempotent: repeated deterministic builds re-register the same
        # token/payload without corrupting the registry or blocking the relay.
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                first = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                second = carrier.protocol_build_acceptance_stage_handoff(
                    _stage_call_selection(carrier, artifacts),
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                self.assertEqual(
                    first["handoff_delivery_text"], second["handoff_delivery_text"]
                )
                token = first["handoff_delivery_text"]
                self.assertEqual(len(carrier._stage_handoff_delivery_tokens), 1)
                runner = self._build_runner_for_carrier(carrier)
                registered = runner._register_stage_handoff_delivery_if_exact(
                    RuntimeDelivery(
                        sender_id="protocol",
                        recipient_id="coordinator",
                        kind="peer",
                        text=token,
                        delivery_id="delivery-once",
                    )
                )
                self.assertEqual(registered["delivery_id"], "delivery-once")
                # A second relay of the same token binds a distinct broker id.
                again = runner._register_stage_handoff_delivery_if_exact(
                    RuntimeDelivery(
                        sender_id="protocol",
                        recipient_id="coordinator",
                        kind="peer",
                        text=token,
                        delivery_id="delivery-twice",
                    )
                )
                self.assertEqual(again["delivery_id"], "delivery-twice")
            finally:
                carrier.cleanup()

    def test_delivery_bound_draft_keeps_handoff_runner_private_and_allows_two_questions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=artifacts)
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-bound",
                    text=text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                operation = "coordinator_build_acceptance_ticket_draft_from_delivery"
                descriptor = carrier.capability_descriptors["coordinator"]
                self.assertIn(operation, descriptor["operations"])
                first = carrier._dispatch_capability(
                    "coordinator",
                    operation,
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-bound",
                        "question_id": "cq-001",
                        "ticket_revision": 1,
                    },
                )
                second = carrier._dispatch_capability(
                    "coordinator",
                    operation,
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-bound",
                        "question_id": "cq-002",
                        "ticket_revision": 1,
                    },
                )
                self.assertEqual(first["question_id"], "cq-001")
                self.assertEqual(second["question_id"], "cq-002")
                self.assertEqual(first["ticket_revision"], 1)
                self.assertEqual(second["ticket_revision"], 1)
                with self.assertRaisesRegex(AcceptanceContractError, "already built"):
                    carrier._dispatch_capability(
                        "coordinator",
                        operation,
                        {
                            "coordinator_id": "coordinator",
                            "handoff_delivery_id": "delivery-bound",
                            "question_id": "cq-001",
                            "ticket_revision": 1,
                        },
                    )
                carrier._dispatch_capability(
                    "coordinator",
                    operation,
                    {
                        "coordinator_id": "coordinator",
                        "handoff_delivery_id": "delivery-bound",
                        "question_id": "cq-001",
                        "ticket_revision": 3,
                    },
                )
                with self.assertRaisesRegex(AcceptanceContractError, "revision is stale"):
                    carrier._dispatch_capability(
                        "coordinator",
                        operation,
                        {
                            "coordinator_id": "coordinator",
                            "handoff_delivery_id": "delivery-bound",
                            "question_id": "cq-001",
                            "ticket_revision": 2,
                        },
                    )
                with self.assertRaisesRegex(AcceptanceContractError, "revision is invalid"):
                    carrier._dispatch_capability(
                        "coordinator",
                        operation,
                        {
                            "coordinator_id": "coordinator",
                            "handoff_delivery_id": "delivery-bound",
                            "question_id": "cq-001",
                            "ticket_revision": 0,
                        },
                    )
                with self.assertRaisesRegex(AcceptanceContractError, "not recorded"):
                    carrier._dispatch_capability(
                        "coordinator",
                        operation,
                        {
                            "coordinator_id": "coordinator",
                            "handoff_delivery_id": "delivery-foreign",
                            "question_id": "cq-001",
                            "ticket_revision": 1,
                        },
                    )
                endpoint = carrier.capability_endpoint("coordinator")
                response = endpoint.handle(
                    {
                        "id": "typed-extra",
                        "token": carrier.capability_token("coordinator"),
                        "method": "tools/call",
                        "params": {
                            "name": operation,
                            "arguments": {
                                "coordinator_id": "coordinator",
                                "handoff_delivery_id": "delivery-bound",
                                "question_id": "cq-001",
                                "ticket_revision": 2,
                                "handoff_json": handoff,
                            },
                        },
                    }
                )
                self.assertIn("error", response)
            finally:
                carrier.cleanup()

    def test_delivery_bound_draft_is_not_advertised_by_legacy_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "carrier",
                task_id="task-legacy",
                acceptance_id="acceptance",
            )
            try:
                self.assertNotIn(
                    "coordinator_build_acceptance_ticket_draft_from_delivery",
                    carrier.capability_descriptors["coordinator"]["operations"],
                )
            finally:
                carrier.cleanup()

    def test_formal_protocol_runtime_sink_records_completed_platform_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                adapter = CodexRuntimeAdapter(repository_root=Path(__file__).resolve().parents[2])
                adapter._coordination_enabled = True
                adapter._acceptance = carrier
                adapter._run_root = run_root
                agent = SimpleNamespace(package=SimpleNamespace(role="protocol"))
                adapter._record_protocol_platform_artifact(
                    agent,
                    {
                        "item": {
                            "type": "mcpToolCall",
                            "server": "ontology_platform",
                            "tool": "get_modeling_context",
                            "status": "completed",
                            "arguments": {"ontology_id": "ontology-r23005-e"},
                            "result": {
                                "structuredContent": {
                                    "ok": True,
                                    "data": {
                                        "ontology": {"id": "ontology-r23005-e"},
                                        "workspace": {"workspace_version": "workspace-e-1"},
                                    },
                                }
                            },
                        }
                    },
                )
                catalog = carrier.protocol_list_platform_artifacts(
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                self.assertEqual(len(catalog["artifacts"]), 1)
                artifact = catalog["artifacts"][0]
                self.assertEqual(artifact["tool"], "get_modeling_context")
                self.assertTrue((run_root / artifact["artifact_path"]).is_file())
            finally:
                carrier.cleanup()

    def test_handoff_and_draft_mutations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=artifacts)
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-1", text=text, sender_role="protocol", recipient_role="coordinator"
                )
                mutated = json.loads(text)
                mutated["slice_revision"] = "revision-2"
                with self.assertRaisesRegex(AcceptanceContractError, "unchanged delivered object"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        mutated,
                        handoff_delivery_id="delivery-1",
                        handoff_digest=handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )
                draft = carrier.coordinator_build_acceptance_ticket_draft(
                    handoff,
                    handoff_delivery_id="delivery-1",
                    handoff_digest=handoff["handoff_digest"],
                    question_id="cq-001",
                    ticket_revision=1,
                    capability=carrier.capability_token("coordinator"),
                )
                draft["question"] = "mutated"
                with self.assertRaisesRegex(AcceptanceContractError, "draft was mutated"):
                    carrier.coordinator_publish_acceptance_ticket(
                        draft,
                        owner_revision=draft["quality_standard_ref"],
                        capability=carrier.capability_token("coordinator"),
                    )
                with self.assertRaisesRegex(AcceptanceContractError, "Runner-built ticket draft"):
                    carrier.coordinator_publish_acceptance_ticket(
                        {},
                        owner_revision=_policy()["quality_standard_ref"],
                        capability=carrier.capability_token("coordinator"),
                    )
            finally:
                carrier.cleanup()

    def test_role_capability_isolation_and_binding_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=artifacts)
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-1", text=text, sender_role="protocol", recipient_role="coordinator"
                )
                with self.assertRaisesRegex(AcceptanceContractError, "operation is not available"):
                    carrier._dispatch_capability(
                        "acceptance",
                        "coordinator_build_acceptance_ticket_draft",
                        {},
                    )
                wrong_run = _handoff(
                    carrier.stage_handoff_nonce,
                    run_id="run-other",
                    artifact_records=artifacts,
                )
                wrong_text = json.dumps(wrong_run, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-2", text=wrong_text, sender_role="protocol", recipient_role="coordinator"
                )
                with self.assertRaisesRegex(AcceptanceContractError, "run does not match"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        wrong_run,
                        handoff_delivery_id="delivery-2",
                        handoff_digest=wrong_run["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )
            finally:
                carrier.cleanup()

    def test_stage_tool_binding_candidate_binding_and_artifact_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / "run-r23005-e"
            run_root.mkdir(parents=True)
            source = run_root / "source.md"
            source.write_text("approved source", encoding="utf-8")
            carrier = self._carrier(run_root, source)
            try:
                artifacts = _register_stage_artifacts(carrier)
                stale_read = carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-r23005-e"},
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {
                                "ontology": {"id": "ontology-r23005-e"},
                                "workspace": {"workspace_version": "workspace-old"},
                            },
                        }
                    },
                )
                self.assertNotEqual(stale_read["artifact_path"], artifacts["readback"]["artifact_path"])
                self.assertEqual(
                    len(carrier.protocol_list_platform_artifacts(protocol_id="protocol", capability=carrier.capability_token("protocol"))["artifacts"]),
                    6,
                )
                bad_mode = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments={
                        "session_id": "session-r23005-e",
                        "client_batch_id": "batch-e-bad",
                        "ontology_id": "ontology-r23005-e",
                        "idempotency_key": "idempotency-e-bad",
                        "expected_workspace_version": "workspace-e-0",
                        "items": [
                            {
                                "client_item_id": "batch-e-bad-item",
                                "command_kind": "create_class",
                                "payload": {"name": "Example"},
                            }
                        ],
                        "mode": "apply_atomic",
                        "lease_token": "lease-r23005-e",
                    },
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {
                                "stage": "bad",
                                "mode": "apply_atomic",
                                "attempt_status": "applied",
                            },
                        }
                    },
                )
                wrong_binding = dict(artifacts)
                wrong_binding["dry-run"] = bad_mode
                handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=wrong_binding)
                text = json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-stage-binding",
                    text=text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "request mode"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        handoff,
                        handoff_delivery_id="delivery-stage-binding",
                        handoff_digest=handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                bad_status = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments={
                        "session_id": "session-r23005-e",
                        "client_batch_id": "batch-e-status",
                        "ontology_id": "ontology-r23005-e",
                        "idempotency_key": "idempotency-e-status",
                        "expected_workspace_version": "workspace-e-0",
                        "items": [
                            {
                                "client_item_id": "batch-e-status-item",
                                "command_kind": "create_class",
                                "payload": {"name": "Example"},
                            }
                        ],
                        "mode": "dry_run",
                    },
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {"mode": "dry_run", "attempt_status": "applied"},
                        }
                    },
                )
                wrong_status = dict(artifacts)
                wrong_status["dry-run"] = bad_status
                status_handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=wrong_status)
                status_text = json.dumps(status_handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-stage-status",
                    text=status_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "result status"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        status_handoff,
                        handoff_delivery_id="delivery-stage-status",
                        handoff_digest=status_handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                stale_apply = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments={
                        "session_id": "session-r23005-e",
                        "client_batch_id": "batch-e-apply",
                        "ontology_id": "ontology-r23005-e",
                        "idempotency_key": "idempotency-e-apply",
                        "expected_workspace_version": "workspace-e-0",
                        "items": [
                            {
                                "client_item_id": "batch-e-apply-item",
                                "command_kind": "create_class",
                                "payload": {"name": "Example"},
                            }
                        ],
                        "mode": "apply_atomic",
                        "lease_token": "lease-r23005-e",
                    },
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {
                                "mode": "apply_atomic",
                                "attempt_status": "applied",
                                "workspace": {
                                    "before_version": "workspace-e-0",
                                    "after_version": "workspace-old",
                                },
                                "target": {"source_signature_after": "source-old"},
                            },
                        }
                    },
                )
                stale_apply_binding = dict(artifacts)
                stale_apply_binding["apply"] = stale_apply
                stale_apply_handoff = _handoff(
                    carrier.stage_handoff_nonce,
                    artifact_records=stale_apply_binding,
                )
                stale_apply_text = json.dumps(
                    stale_apply_handoff,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-stale-apply",
                    text=stale_apply_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "workspace version"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        stale_apply_handoff,
                        handoff_delivery_id="delivery-stale-apply",
                        handoff_digest=stale_apply_handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                stale_source = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments={
                        "session_id": "session-r23005-e",
                        "client_batch_id": "batch-e-apply",
                        "ontology_id": "ontology-r23005-e",
                        "idempotency_key": "idempotency-e-apply",
                        "expected_workspace_version": "workspace-e-0",
                        "items": [
                            {
                                "client_item_id": "batch-e-apply-item",
                                "command_kind": "create_class",
                                "payload": {"name": "Example"},
                            }
                        ],
                        "mode": "apply_atomic",
                        "lease_token": "lease-r23005-e",
                    },
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {
                                "mode": "apply_atomic",
                                "attempt_status": "applied",
                                "workspace": {
                                    "before_version": "workspace-e-0",
                                    "after_version": "workspace-e-1",
                                },
                                "target": {"source_signature_after": "source-old"},
                            },
                        }
                    },
                )
                stale_source_binding = dict(artifacts)
                stale_source_binding["apply"] = stale_source
                stale_source_handoff = _handoff(
                    carrier.stage_handoff_nonce,
                    artifact_records=stale_source_binding,
                )
                stale_source_text = json.dumps(
                    stale_source_handoff,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-stale-source",
                    text=stale_source_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "source signature"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        stale_source_handoff,
                        handoff_delivery_id="delivery-stale-source",
                        handoff_digest=stale_source_handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                wrong_scope_artifact = carrier.register_platform_tool_result(
                    tool="run_semantic_validation",
                    arguments={"graph_set_id": "graph-other"},
                    result={
                        "structuredContent": {
                            "ok": True,
                            "data": {"status": "succeeded", "graph_set_id": "graph-other"},
                        }
                    },
                )
                wrong_scope = dict(artifacts)
                wrong_scope["validation"] = wrong_scope_artifact
                scope_handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=wrong_scope)
                scope_text = json.dumps(scope_handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-stage-scope",
                    text=scope_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "graph scope"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        scope_handoff,
                        handoff_delivery_id="delivery-stage-scope",
                        handoff_digest=scope_handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                good_handoff = _handoff(carrier.stage_handoff_nonce, artifact_records=artifacts)
                good_text = json.dumps(good_handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-artifact-tamper",
                    text=good_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                artifact_path = run_root / artifacts["dry-run"]["artifact_path"]
                os.chmod(artifact_path, 0o600)
                artifact_path.write_bytes(b"tampered")
                with self.assertRaisesRegex(AcceptanceContractError, "artifact bytes"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        good_handoff,
                        handoff_delivery_id="delivery-artifact-tamper",
                        handoff_digest=good_handoff["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )

                candidate_mismatch = _handoff(
                    carrier.stage_handoff_nonce,
                    candidate_digest="f" * 64,
                    artifact_records=artifacts,
                )
                candidate_text = json.dumps(
                    candidate_mismatch,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                carrier.register_stage_handoff_delivery(
                    delivery_id="delivery-candidate-binding",
                    text=candidate_text,
                    sender_role="protocol",
                    recipient_role="coordinator",
                )
                with self.assertRaisesRegex(AcceptanceContractError, "candidate binding"):
                    carrier.coordinator_build_acceptance_ticket_draft(
                        candidate_mismatch,
                        handoff_delivery_id="delivery-candidate-binding",
                        handoff_digest=candidate_mismatch["handoff_digest"],
                        question_id="cq-001",
                        ticket_revision=1,
                        capability=carrier.capability_token("coordinator"),
                    )
            finally:
                carrier.cleanup()

    def test_prompt_and_task_contract_expose_nested_handoff_schema(self) -> None:
        root = Path(__file__).resolve().parents[2]
        reference = json.loads(
            (root / "modeling_team/references/acceptance-stage-handoff-contract.json").read_text()
        )
        self.assertEqual(reference["modeling_receipt_fields"][-1], "evidence_ref")
        self.assertIn("page", reference["platform_read_evidence_fields"])
        self.assertIn("handoff_nonce", reference["handoff_fields"])
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text()
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text()
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text()
        self.assertIn("acceptance-stage-handoff-contract.json", protocol)
        self.assertIn(
            "do not call `mcp__team_transport__report_task_result` until the Runner delivers the explicit Protocol",
            protocol,
        )
        self.assertIn("explicit Modeling `terminal-handoff`", modeling)
        self.assertIn("coordinator_build_acceptance_ticket_draft", coordinator)
        self.assertIn("coordinator_build_acceptance_ticket_draft_from_delivery", coordinator)
        self.assertIn("Runner-provided frozen-question list", coordinator)
        self.assertIn("do not guess an abbreviated ID", coordinator)
        self.assertIn("owner_revision", coordinator)
        self.assertIn("quality_standard_ref", coordinator)
        self.assertIn("For `pause`, the argument object must contain exactly", coordinator)
        self.assertIn("An `abort` argument object must contain exactly", coordinator)
        self.assertIn("`reason` must equal the persisted abort `resolution_text` byte-for-byte", coordinator)
        self.assertIn("Never include `resolution_type`, `resolution_text`, `null`", coordinator)

    def test_prompt_contract_serializes_gate_notice_readiness_and_ticket_drafts(self) -> None:
        root = Path(__file__).resolve().parents[2]
        protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text()
        modeling = (root / "modeling_team/agent-packages/modeling/instructions.md").read_text()
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text()
        protocol_words = " ".join(protocol.split())
        modeling_words = " ".join(modeling.split())
        coordinator_words = " ".join(coordinator.split())

        self.assertIn(
            "handoff to Coordinator, bound gate-complete notice to Modeling, then",
            protocol_words,
        )
        self.assertIn("then `silent_for_acceptance`", protocol_words)
        self.assertIn("accepted `candidate_digest`", protocol)
        self.assertIn("acceptance-stage handoff `delivery_id`", protocol)
        self.assertIn("sole permission to send `ready_for_acceptance`", modeling)
        self.assertIn("Protocol's direct", modeling)
        self.assertIn(
            "notice's digest equals your retained accepted candidate digest",
            modeling_words,
        )
        self.assertIn("only after the bound notice arrives", modeling_words)
        self.assertIn("Wait until both readiness signals", coordinator_words)
        self.assertIn("`cq-001` draft first", coordinator_words)
        self.assertIn("before calling `cq-002`", coordinator_words)
        self.assertIn("Never issue the two draft calls in parallel", coordinator_words)
        self.assertIn("`Promise.all`", coordinator)


if __name__ == "__main__":
    unittest.main()
