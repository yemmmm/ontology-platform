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
from modeling_team.runtimes.codex import CodexRuntimeAdapter


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
        coordinator = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text()
        self.assertIn("acceptance-stage-handoff-contract.json", protocol)
        self.assertIn("coordinator_build_acceptance_ticket_draft", coordinator)
        self.assertIn("owner_revision", coordinator)
        self.assertIn("quality_standard_ref", coordinator)


if __name__ == "__main__":
    unittest.main()
