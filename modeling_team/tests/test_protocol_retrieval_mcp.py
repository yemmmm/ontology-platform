from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path

from modeling_team.contracts import _load_package, repository_root
from modeling_team.p2a_protocol_driver import (
    P2AProtocolDriverError,
    _validate_candidate_receipt,
)
from modeling_team.proof_v2 import canonical_digest
from modeling_team.protocol_mechanics import build_existing_entity_binding_receipt
from modeling_team.r23003_contract import build_delete_impact_receipt
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent
from modeling_team.transport_mcp import Delivery


class ProtocolRetrievalMcpTests(unittest.TestCase):
    @staticmethod
    def _wrapper():
        root = repository_root()
        module_path = root / "modeling_team" / "protocol_retrieval_mcp.py"
        spec = importlib.util.spec_from_file_location("protocol_retrieval_mcp_test", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(module_path.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        return module

    @staticmethod
    def _valid_arguments(wrapper) -> dict[str, object]:
        return {
            "mode": "create",
            "initial_modeling_context": {"ok": True, "data": {}},
            "final_modeling_context": {"ok": True, "data": {}},
            "workspace_context": {"ok": True, "data": {}},
            "batch_inventory": {"requested_limit": 1, "response": {"ok": True, "data": {}}},
            "batch_details": [],
            "entities_read": {"ok": True, "data": {}},
            "statements_read": {"requested_limit": 1, "response": {"ok": True, "data": {}}},
            "candidate_required_assertions": {
                "schema_version": "candidate-required-assertions/v1",
                "candidate_revision": "revision-1",
                "delivery_id": "delivery-1",
                "reply_chain": ["delivery-1"],
                "semantic_digest": "d864bba0d2372f63d87233e5191ba137bb5ed655f68ebeb2f1810a0e5a231691",
                "candidate_digest": "7ec1a6654807a2dea9b494368465bb2103969a9e4aff9934d816475729d32fab",
                "items": [{
                    "subject": "subject",
                    "predicate": "predicate",
                    "object": "object",
                    "object_kind": "iri",
                    "object_datatype": None,
                    "object_language": None,
                }],
                "materialized_digest": "18513bd05c3d61acf98c54f760b400741a073fc3b5b90355c87abade2d90bfd2",
                "materialized_quads": [{
                    "ontology_id": "graph:data",
                    "subject": "subject",
                    "predicate": "predicate",
                    "object": "object",
                    "object_kind": "iri",
                    "object_datatype": None,
                    "object_language": None,
                }],
            },
            "statement_lineage": {
                "schema_version": "candidate-required-assertions/v1",
                "candidate_revision": "revision-1",
                "delivery_id": "delivery-1",
                "reply_chain": ["delivery-1"],
                "semantic_digest": "d864bba0d2372f63d87233e5191ba137bb5ed655f68ebeb2f1810a0e5a231691",
                "candidate_digest": "7ec1a6654807a2dea9b494368465bb2103969a9e4aff9934d816475729d32fab",
                "materialized_digest": "18513bd05c3d61acf98c54f760b400741a073fc3b5b90355c87abade2d90bfd2",
                "max_depth": 0,
                "records": [{
                    "fact_id": "a3b5365df0a9f1d9de30165798cb28336d7e7ad0f45d6cc3354ac4c2eaad98d3",
                    "quad": {
                        "ontology_id": "graph:data",
                        "subject": "subject",
                        "predicate": "predicate",
                        "object": "object",
                        "object_kind": "iri",
                        "object_datatype": None,
                        "object_language": None,
                    },
                    "response": {"ok": True, "data": {}},
                }],
            },
        }

    @staticmethod
    def _valid_candidate() -> dict[str, object]:
        item = {
            "item_id": "class-1",
            "item_kind": "class",
            "semantic": {"class_id": "Tool", "description": "A semantic tool."},
        }
        return {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": "revision-1",
            "scope": {"name": "protocol-test"},
            "constraints": ["source-grounded"],
            "items": [item],
        }

    @staticmethod
    @contextmanager
    def _runtime_authority(wrapper, base: Path, run_id: str):
        context = base / "mechanics-contract.json"
        if context.exists():
            os.chmod(context, 0o600)
        context.write_bytes(wrapper.protocol_mechanics_contract_bytes(run_id))
        os.chmod(context, 0o444)
        with patch.object(wrapper, "RUNTIME_CONTEXT_PATH", context), patch.dict(
            os.environ, {wrapper.RUNTIME_RUN_ID_ENV: run_id}, clear=False
        ):
            yield

    def test_candidate_receipt_tool_output_passes_driver_validator_and_preserves_transport_binding(self) -> None:
        wrapper = self._wrapper()
        candidate = self._valid_candidate()
        response = wrapper.handle(
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": wrapper.CANDIDATE_RECEIPT_TOOL_NAME,
                    "arguments": {"candidate": candidate},
                },
            }
        )
        assert response is not None
        self.assertNotIn("error", response)
        result = response["result"]
        receipt = result["structuredContent"]
        self.assertEqual(
            set(receipt), {"status", "candidate_revision", "semantic_digest", "candidate_digest"}
        )
        self.assertEqual(json.loads(result["content"][0]["text"]), receipt)
        delivery = Delivery(
            2,
            "protocol",
            "p2a-synthetic-modeling",
            result["content"][0]["text"],
            1.0,
            "receipt-delivery-1",
            False,
            "delivery-1",
        )
        # The archival P2a validator consumes its historical candidate identity
        # fields; bind the current neutral receipt into that checker without
        # putting those transport fields back into the active candidate.
        bound_candidate = {
            **candidate,
            "semantic_digest": receipt["semantic_digest"],
            "candidate_digest": receipt["candidate_digest"],
        }
        _validate_candidate_receipt(delivery, bound_candidate, "delivery-1")

    def test_candidate_conflict_tool_exposes_only_canonical_content_and_structured_content(self) -> None:
        wrapper = self._wrapper()
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": 1,
            "scope": "retained",
            "constraints": ["source-grounded"],
            "items": [{"item_id": "item-1", "item_kind": "class", "semantic": {"label": "Tool"}}],
        }
        with patch.dict(os.environ, {wrapper.FORMAL_CANDIDATE_GATE_ENV: "1"}, clear=False):
            response = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.CANDIDATE_CONFLICT_TOOL_NAME,
                        "arguments": {
                            "candidate": candidate,
                            "conflict_code": "candidate_translation_conflict",
                            "conflict_detail": "delete declaration requires revision",
                        },
                    },
                }
            )
        assert response is not None
        self.assertNotIn("error", response)
        result = response["result"]
        self.assertEqual(set(result), {"content", "structuredContent"})
        self.assertNotIn("conflict_json", result)
        self.assertEqual(
            result["content"],
            [{"type": "text", "text": json.dumps(
                result["structuredContent"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )}],
        )
        self.assertEqual(
            json.loads(result["content"][0]["text"]),
            result["structuredContent"],
        )

    def test_legacy_proof_gate_does_not_change_neutral_candidate_boundary(self) -> None:
        wrapper = self._wrapper()
        neutral = {
            "candidate_kind": "semantic-candidate",
            "candidate_revision": 1,
            "scope": {"project_id": "project-smoke", "ontology_id": "ontology-smoke"},
            "constraints": [],
            "items": [{"item_id": "item-1", "item_kind": "class", "semantic": {"label": "Tool"}}],
        }
        with patch.dict(os.environ, {wrapper.PROOF_GATE_ENV: "1"}, clear=False), patch.object(
            wrapper, "build_candidate_receipt", wraps=wrapper.build_candidate_receipt
        ) as builder:
            response = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.CANDIDATE_RECEIPT_TOOL_NAME,
                        "arguments": {"candidate": neutral},
                    },
                }
            )
        assert response is not None
        self.assertNotIn("error", response)
        self.assertEqual(
            set(response["result"]["structuredContent"]),
            {"status", "candidate_revision", "semantic_digest", "candidate_digest"},
        )
        builder.assert_called_once_with(neutral)

    def test_proof_verifier_stays_unavailable_when_legacy_gate_is_enabled(self) -> None:
        """The retired verifier cannot be reopened through the production facade."""
        wrapper = self._wrapper()
        with patch.dict(os.environ, {wrapper.PROOF_GATE_ENV: "1"}, clear=False), patch.object(
            wrapper, "verify_scoped_retrieval_fallback"
        ) as verifier:
            listed = wrapper.handle({"jsonrpc": "2.0", "id": 34, "method": "tools/list"})
            called = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 35,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.TOOL_NAME,
                        "arguments": self._valid_arguments(wrapper),
                    },
                }
            )
        assert listed is not None
        assert called is not None
        self.assertNotIn(wrapper.TOOL_NAME, {tool["name"] for tool in listed["result"]["tools"]})
        receipt = next(
            tool for tool in listed["result"]["tools"] if tool["name"] == wrapper.CANDIDATE_RECEIPT_TOOL_NAME
        )
        self.assertNotIn("evidence_citations", json.dumps(receipt["inputSchema"], sort_keys=True))
        self.assertEqual(called["error"]["code"], -32601)
        verifier.assert_not_called()

    def test_unbound_runtime_accepts_neutral_candidate_receipt(self) -> None:
        wrapper = self._wrapper()
        neutral = {
            "candidate_kind": "semantic-candidate",
            "candidate_revision": 1,
            "scope": {"project_id": "project-smoke", "ontology_id": "ontology-smoke"},
            "constraints": [],
            "items": [{"item_id": "item-1", "item_kind": "class", "semantic": {"label": "Tool"}}],
        }
        with patch.dict(os.environ, {wrapper.PROOF_GATE_ENV: "0"}, clear=False):
            response = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 33,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.CANDIDATE_RECEIPT_TOOL_NAME,
                        "arguments": {"candidate": neutral},
                    },
                }
            )
        assert response is not None
        self.assertNotIn("error", response)
        self.assertEqual(
            set(response["result"]["structuredContent"]),
            {"status", "candidate_revision", "semantic_digest", "candidate_digest"},
        )

    def test_candidate_receipt_tool_fails_closed_for_spoof_missing_extra_tamper_and_cross_candidate(self) -> None:
        wrapper = self._wrapper()
        candidate = self._valid_candidate()

        def call(arguments: object):
            return wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.CANDIDATE_RECEIPT_TOOL_NAME,
                        "arguments": arguments,
                    },
                }
            )

        initial = call({"candidate": candidate})
        assert initial is not None
        self.assertNotIn("error", initial)
        initial_receipt = initial["result"]["structuredContent"]
        bound_candidate = {
            **candidate,
            "semantic_digest": initial_receipt["semantic_digest"],
            "candidate_digest": initial_receipt["candidate_digest"],
        }

        for arguments in (
            {},
            {"candidate": candidate, "status": "accepted"},
            {"candidate": candidate, "candidate_digest": "spoofed"},
        ):
            with self.subTest(arguments=arguments):
                result = call(arguments)
                assert result is not None
                self.assertEqual(result["error"]["code"], -32602)

        for tampered in (
            {**candidate, "unexpected": True},
            {
                **candidate,
                "items": [dict(candidate["items"][0], evidence_citations=[{"excerpt": "retired"}])],
            },
        ):
            with self.subTest(tampered=tampered):
                result = call({"candidate": tampered})
                assert result is not None
                self.assertEqual(result["error"]["code"], -32012)

        candidate_two = json.loads(json.dumps(candidate))
        candidate_two["candidate_revision"] = "revision-2"
        result = call({"candidate": candidate_two})
        assert result is not None
        self.assertNotIn("error", result)
        cross_candidate_delivery = Delivery(
            3,
            "protocol",
            "p2a-synthetic-modeling",
            result["result"]["content"][0]["text"],
            1.0,
            "receipt-delivery-2",
            False,
            "delivery-1",
        )
        with self.assertRaisesRegex(P2AProtocolDriverError, "binding drifted"):
            _validate_candidate_receipt(cross_candidate_delivery, bound_candidate, "delivery-1")

        for field, value in (
            ("sender_id", "spoofed-protocol"),
            ("recipient_id", "protocol"),
            ("reply_to_delivery_id", "other-delivery"),
        ):
            values = {
                "sequence": 4,
                "sender_id": "protocol",
                "recipient_id": "p2a-synthetic-modeling",
                "text": json.dumps(result["result"]["structuredContent"], sort_keys=True),
                "timestamp": 1.0,
                "delivery_id": "receipt-delivery-3",
                "expects_reply": False,
                "reply_to_delivery_id": "delivery-1",
            }
            values[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                P2AProtocolDriverError, "envelope is invalid"
            ):
                _validate_candidate_receipt(Delivery(**values), bound_candidate, "delivery-1")

    def test_tools_list_excludes_retired_proof_v2_surface(self) -> None:
        wrapper = self._wrapper()
        response = wrapper.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = response["result"]["tools"]
        names = {item["name"] for item in tools}
        self.assertNotIn(wrapper.TOOL_NAME, names)
        self.assertNotIn(wrapper.EVIDENCE_MAP_TOOL_NAME, names)
        receipt = next(item for item in tools if item["name"] == wrapper.CANDIDATE_RECEIPT_TOOL_NAME)
        schema_text = json.dumps(receipt["inputSchema"], sort_keys=True)
        for retired_field in ("evidence_citations", "evidence_bindings", "statement_lineage"):
            self.assertNotIn(retired_field, schema_text)
        self.assertFalse(receipt["inputSchema"]["properties"]["candidate"]["additionalProperties"])

    def test_translate_tool_uses_full_r23003_mechanics_and_isolates_005(self) -> None:
        wrapper = self._wrapper()
        tools = wrapper.handle({"jsonrpc": "2.0", "id": 39, "method": "tools/list"})["result"]["tools"]
        translate_tool = next(item for item in tools if item["name"] == wrapper.TRANSLATE_CANDIDATE_TOOL_NAME)
        schema = translate_tool["inputSchema"]
        self.assertEqual(schema["required"], ["candidate"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["properties"]),
            {
                "candidate",
                "requirement_id",
                "existing_binding_receipt",
                "deletion_impact_receipts",
                "phase_a_readback",
                "semantic_base_iri",
            },
        )
        self.assertEqual(
            schema["properties"]["requirement_id"]["enum"], ["R2.3-003", "R4.0-010"]
        )
        project_id = "project-003"
        ontology_id = "ontology-003"
        workspace_version = "workspace-v1"
        target_ids = (
            "unknown-cross-release-output-meaning",
            "unknown-b-no-score-behavior",
        )
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": 1,
            "scope": "retained",
            "constraints": ["source-grounded"],
            "items": [
                {
                    "item_id": "new-class",
                    "item_kind": "class",
                    "semantic": {"class_id": "ReviewOutcome"},
                },
                {
                    "item_id": "existing-b",
                    "item_kind": "existing_entity_ref",
                    "semantic": {
                        "semantic_id": target_ids[1],
                        "expected_class": "ExplicitUnknown",
                    },
                },
                {
                    "item_id": "existing-cross",
                    "item_kind": "existing_entity_ref",
                    "semantic": {
                        "semantic_id": target_ids[0],
                        "expected_class": "ExplicitUnknown",
                    },
                },
                {
                    "item_id": "delete-cross",
                    "item_kind": "delete_existing_entity",
                    "semantic": {
                        "semantic_id": target_ids[0],
                        "expected_class": "ExplicitUnknown",
                        "delete_mode": "full_live_impact",
                    },
                },
                {
                    "item_id": "delete-b",
                    "item_kind": "delete_existing_entity",
                    "semantic": {
                        "semantic_id": target_ids[1],
                        "expected_class": "ExplicitUnknown",
                        "delete_mode": "full_live_impact",
                    },
                },
            ],
        }
        rows = [
            {
                "semantic_id": semantic_id,
                "entity_iri": f"http://ontology-platform.local/semantic/entity/{semantic_id}",
                "class_semantic_id": "ExplicitUnknown",
                "class_iri": "http://ontology-platform.local/semantic/class/ExplicitUnknown",
                "project_id": project_id,
                "ontology_id": ontology_id,
                "workspace_version": workspace_version,
                "read_evidence": {"source": "live-read"},
            }
            for semantic_id in sorted(target_ids)
        ]
        binding = build_existing_entity_binding_receipt(
            candidate,
            {"entities": rows},
            project_id=project_id,
            ontology_id=ontology_id,
            workspace_version=workspace_version,
        )
        candidate_digest = canonical_digest(candidate)
        impact_receipts = {}
        for semantic_id in target_ids:
            entity_iri = next(row["entity_iri"] for row in rows if row["semantic_id"] == semantic_id)
            empty_statements_digest = canonical_digest([])
            impact_receipts[semantic_id] = build_delete_impact_receipt(
                [
                    {
                        "project_id": project_id,
                        "ontology_id": ontology_id,
                        "entity_iri": entity_iri,
                        "workspace_version": workspace_version,
                        "statements": [],
                        "page_digest": empty_statements_digest,
                        "snapshot_digest": empty_statements_digest,
                        "next_cursor": None,
                        "complete": True,
                    }
                ],
                target_semantic_id=semantic_id,
                candidate_digest=candidate_digest,
                project_id=project_id,
                ontology_id=ontology_id,
                workspace_version=workspace_version,
            )

        def call(arguments: dict[str, object]) -> dict[str, object]:
            response = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 40,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.TRANSLATE_CANDIDATE_TOOL_NAME,
                        "arguments": arguments,
                    },
                }
            )
            assert response is not None
            return response

        complete = call(
            {
                "candidate": candidate,
                "requirement_id": "R2.3-003",
                "existing_binding_receipt": binding,
                "deletion_impact_receipts": impact_receipts,
                "phase_a_readback": True,
            }
        )
        self.assertNotIn("error", complete)
        plan = complete["result"]["structuredContent"]
        self.assertEqual(
            [batch["stage_kind"] for batch in plan["batches"]],
            ["class", "delete-only", "delete-only"],
        )
        delete_batches = plan["batches"][1:]
        self.assertTrue(all(batch["delete_only"] for batch in delete_batches))
        self.assertTrue(all(batch["phase"] == "B" for batch in delete_batches))
        self.assertEqual([len(batch["items"]) for batch in delete_batches], [1, 1])
        self.assertEqual(
            [batch["items"][0]["payload"]["semantic_id"] for batch in delete_batches],
            list(target_ids),
        )
        self.assertEqual(
            len({batch["client_batch_id"] for batch in delete_batches}),
            2,
        )
        self.assertEqual(
            len({batch["idempotency_key"] for batch in delete_batches}),
            2,
        )

        missing_binding = call(
            {
                "candidate": candidate,
                "requirement_id": "R2.3-003",
                "deletion_impact_receipts": impact_receipts,
                "phase_a_readback": True,
            }
        )
        self.assertEqual(missing_binding["error"]["code"], -32014)
        self.assertIn("existing binding receipt is required", missing_binding["error"]["message"])

        missing_impact = call(
            {
                "candidate": candidate,
                "requirement_id": "R2.3-003",
                "existing_binding_receipt": binding,
                "phase_a_readback": True,
            }
        )
        self.assertNotIn("error", missing_impact)
        self.assertEqual(
            {conflict["code"] for conflict in missing_impact["result"]["structuredContent"]["conflicts"]},
            {"delete_impact_receipt_required"},
        )
        self.assertNotIn(
            "delete-only",
            [batch["stage_kind"] for batch in missing_impact["result"]["structuredContent"]["batches"]],
        )

        before_phase_b = call(
            {
                "candidate": candidate,
                "requirement_id": "R2.3-003",
                "existing_binding_receipt": binding,
                "deletion_impact_receipts": impact_receipts,
                "phase_a_readback": False,
            }
        )
        self.assertNotIn("error", before_phase_b)
        blocked_plan = before_phase_b["result"]["structuredContent"]
        self.assertEqual(
            blocked_plan["batches"],
            [{
                "stage_kind": "class",
                "client_batch_id": "1-stage1-class",
                "idempotency_key": "1-stage1-class-v1",
                "apply_idempotency_key": "1-stage1-class-apply-v1",
                "items": [{
                    "client_item_id": "new-class",
                    "command_kind": "create_class",
                    "payload": {"class_id": "ReviewOutcome", "name": "ReviewOutcome"},
                }],
            }],
        )
        self.assertEqual(
            {conflict["code"] for conflict in blocked_plan["conflicts"]},
            {"phase_a_readback_required"},
        )
        candidate_005 = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": 1,
            "scope": "new",
            "constraints": [],
            "items": [{"item_id": "class-005", "item_kind": "class", "semantic": {"class_id": "Tool"}}],
        }
        ordinary = call({"candidate": candidate_005})
        self.assertNotIn("error", ordinary)
        self.assertEqual(ordinary["result"]["structuredContent"]["batches"][0]["stage_kind"], "class")
        extra_005 = call(
            {
                "candidate": candidate_005,
                "requirement_id": "R2.3-005",
                "phase_a_readback": True,
            }
        )
        self.assertEqual(extra_005["error"]["code"], -32602)
        self.assertIn("restricted to R2.3-003", extra_005["error"]["message"])

    def test_translate_tool_owns_dry_and_apply_key_convention(self) -> None:
        wrapper = self._wrapper()
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": 3,
            "scope": "new",
            "constraints": [],
            "items": [
                {"item_id": "class-a", "item_kind": "class", "semantic": {"class_id": "Tool"}},
                {"item_id": "class-b", "item_kind": "class", "semantic": {"class_id": "Workflow"}},
                {"item_id": "prop-a", "item_kind": "predicate", "semantic": {"predicate": "hasTool", "predicate_kind": "fact", "range": "string", "domain": "class-a"}},
            ],
        }
        response = wrapper.handle(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": wrapper.TRANSLATE_CANDIDATE_TOOL_NAME, "arguments": {"candidate": candidate}},
            }
        )
        assert response is not None
        self.assertNotIn("error", response)
        plan = response["result"]["structuredContent"]
        batches = plan["batches"]
        self.assertGreaterEqual(len(batches), 2)
        dry_keys = [batch["idempotency_key"] for batch in batches]
        apply_keys = [batch["apply_idempotency_key"] for batch in batches]
        self.assertEqual(len(set(dry_keys)), len(dry_keys))
        self.assertEqual(len(set(apply_keys)), len(apply_keys))
        self.assertFalse(set(dry_keys) & set(apply_keys))
        for batch in batches:
            self.assertRegex(batch["idempotency_key"], r"-v\d+$")
            self.assertEqual(
                batch["apply_idempotency_key"],
                re.sub(r"-v(\d+)$", r"-apply-v\1", batch["idempotency_key"]),
            )
        self.assertIn("key_convention", plan)
        for fragment in ("apply_idempotency_key", "idempotency_conflict", "v1 -> v2"):
            self.assertIn(fragment, plan["key_convention"])

    def test_candidate_map_tool_is_unavailable(self) -> None:
        wrapper = self._wrapper()
        response = wrapper.handle({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": wrapper.EVIDENCE_MAP_TOOL_NAME, "arguments": {}},
        })
        assert response is not None
        self.assertEqual(response["error"]["code"], -32601)
        self.assertFalse((Path.cwd() / "evidence" / "candidate-item-evidence-map.json").exists())

    def test_candidate_map_tool_never_dispatches_even_with_runtime_authority(self) -> None:
        wrapper = self._wrapper()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self._runtime_authority(wrapper, base, "run-1"):
                response = wrapper.handle({
                    "jsonrpc": "2.0",
                    "id": 20,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.EVIDENCE_MAP_TOOL_NAME,
                        "arguments": {"candidate": self._valid_candidate(), "client_item_ids": {"class-1": "item-1"}},
                    },
                })
            assert response is not None
            self.assertEqual(response["error"]["code"], -32601)
            self.assertFalse((base / "evidence" / "candidate-item-evidence-map.json").exists())

    def test_candidate_map_tool_surface_matches_manifest_and_adapter_preflight(self) -> None:
        wrapper = self._wrapper()
        root = repository_root()
        baseline, _ = TeamRunner.preview_baseline(
            repository_root=root,
            run_id="r23002-map-contract-surface",
            profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
        )
        manifest_tools = set(baseline["runtime_contract"]["protocol_retrieval_mcp"]["tools"])
        listed_tools = {item["name"] for item in wrapper.handle({"method": "tools/list"})["result"]["tools"]}
        self.assertEqual(manifest_tools, listed_tools)
        self.assertNotIn(wrapper.EVIDENCE_MAP_TOOL_NAME, listed_tools)
        self.assertNotIn(wrapper.TOOL_NAME, listed_tools)
        self.assertEqual(
            baseline["runtime_contract"]["protocol_retrieval_mcp"]["runtime_run_id_env"],
            wrapper.RUNTIME_RUN_ID_ENV,
        )
        self.assertEqual(
            baseline["runtime_contract"]["protocol_retrieval_mcp"]["runtime_context_path"],
            str(wrapper.RUNTIME_CONTEXT_PATH),
        )

        adapter = CodexRuntimeAdapter(repository_root=root)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                platform_tools=frozenset({"check_platform_health"}),
                schema_version=2,
                proof_gate=True,
            )
            observed = [
                {"name": "team_transport", "tools": [{"name": "send_team_message"}, {"name": "report_task_result"}]},
                {"name": "ontology_platform", "tools": [{"name": "check_platform_health"}]},
                {"name": "protocol_mechanics", "tools": [{"name": name} for name in sorted(listed_tools)]},
            ]
            adapter._rpc = lambda _agent, _method, _params: {"data": observed}  # type: ignore[method-assign]
            adapter._require_expected_mcp_servers(agent)

    def test_wrapper_rejects_retired_proof_dispatch(self) -> None:
        wrapper = self._wrapper()
        valid = self._valid_arguments(wrapper)
        for arguments in (valid, {**valid, "unexpected": True}, {"proof": valid}):
            with self.subTest(arguments=json.dumps(arguments, sort_keys=True)):
                with patch.object(wrapper, "verify_scoped_retrieval_fallback") as verifier:
                    response = wrapper.handle(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": wrapper.TOOL_NAME, "arguments": arguments},
                        }
                    )
                assert response is not None
                self.assertEqual(response["error"]["code"], -32601)
                verifier.assert_not_called()

    def test_protocol_instructions_and_reference_use_active_neutral_contract(self) -> None:
        root = repository_root()
        instructions = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(encoding="utf-8")
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(encoding="utf-8")
        )
        self.assertIn("Do not require assertion matrices, proof-only envelopes", instructions)
        self.assertIn("only `candidate_kind`, `candidate_revision`, `scope`, `constraints`, and `items`", instructions)
        self.assertNotIn("evidence_citations", instructions)
        self.assertIn("ordinary_v3_execution", reference["semantic_retrieval_completion_contract"])
        self.assertNotIn("deterministic_helper", reference["semantic_retrieval_completion_contract"]["fallback"])
