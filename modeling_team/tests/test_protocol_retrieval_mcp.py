from __future__ import annotations

import importlib.util
import json
import os
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
                    "graph_role": "asserted_data",
                    "subject": "subject",
                    "predicate": "predicate",
                    "object": "object",
                    "object_kind": "iri",
                    "object_datatype": None,
                    "object_language": None,
                }],
                "materialized_digest": "18513bd05c3d61acf98c54f760b400741a073fc3b5b90355c87abade2d90bfd2",
                "materialized_quads": [{
                    "graph_role": "asserted_data",
                    "source_graph_iri": "graph:data",
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
                        "graph_role": "asserted_data",
                        "source_graph_iri": "graph:data",
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
        citation = {
            "document_name": "domain.md",
            "excerpt": "A term.",
            "source_artifact_sha256": "a" * 64,
            "source_locator": "domain.md#1",
            "excerpt_sha256": "e" * 64,
            "owner_answer_id": None,
        }
        item = {
            "assertion_id": "assertion-1",
            "graph_role": "asserted_data",
            "subject": "subject",
            "predicate": "predicate",
            "object": "object",
            "object_kind": "iri",
            "object_datatype": None,
            "object_language": None,
            "evidence_citations": [citation],
        }
        # The proof-v2 citation validator checks the excerpt digest.  Keep the
        # fixture canonical while avoiding a dependency on source files.
        import hashlib

        citation["excerpt_sha256"] = hashlib.sha256(b"A term.").hexdigest()
        semantic = canonical_digest(
            {"schema_version": "candidate-required-assertions/v2", "statements": [item]}
        )
        binding = {
            "schema_version": "candidate-required-assertions/v2",
            "candidate_revision": "revision-1",
            "delivery_id": "delivery-1",
            "reply_chain": ["delivery-1"],
            "semantic_digest": semantic,
        }
        return {**binding, "candidate_digest": canonical_digest(binding), "items": [item]}

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
        _validate_candidate_receipt(delivery, candidate, "delivery-1")

    def test_candidate_conflict_tool_exposes_only_canonical_content_and_structured_content(self) -> None:
        wrapper = self._wrapper()
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v2",
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

    def test_proof_gate_rejects_neutral_candidate_at_raw_mcp_boundary(self) -> None:
        wrapper = self._wrapper()
        neutral = {
            "candidate_kind": "semantic-candidate",
            "candidate_revision": 1,
            "scope": {"project_id": "project-smoke", "ontology_id": "ontology-smoke"},
            "constraints": [],
            "items": [{"item_id": "item-1", "item_kind": "class", "semantic": {"label": "Tool"}}],
        }
        with patch.dict(os.environ, {wrapper.PROOF_GATE_ENV: "1"}, clear=False), patch.object(
            wrapper, "build_candidate_receipt"
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
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("candidate-required-assertions/v2", response["error"]["message"])
        builder.assert_not_called()

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

        for arguments in (
            {},
            {"candidate": candidate, "status": "accepted"},
            {"candidate": candidate, "candidate_digest": candidate["candidate_digest"]},
        ):
            with self.subTest(arguments=arguments):
                result = call(arguments)
                assert result is not None
                self.assertEqual(result["error"]["code"], -32602)

        for tampered in (
            {**candidate, "unexpected": True},
            {**candidate, "semantic_digest": "f" * 64},
            {
                **candidate,
                "items": [dict(candidate["items"][0], object="tampered")],
            },
        ):
            with self.subTest(tampered=tampered):
                result = call({"candidate": tampered})
                assert result is not None
                self.assertEqual(result["error"]["code"], -32012)

        candidate_two = json.loads(json.dumps(candidate))
        candidate_two["candidate_revision"] = "revision-2"
        candidate_two["candidate_digest"] = canonical_digest(
            {
                "schema_version": candidate_two["schema_version"],
                "candidate_revision": candidate_two["candidate_revision"],
                "delivery_id": candidate_two["delivery_id"],
                "reply_chain": candidate_two["reply_chain"],
                "semantic_digest": candidate_two["semantic_digest"],
            }
        )
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
            _validate_candidate_receipt(cross_candidate_delivery, candidate, "delivery-1")

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
                _validate_candidate_receipt(Delivery(**values), candidate, "delivery-1")

    def test_tools_list_exposes_exact_closed_direct_proof_v2_schema(self) -> None:
        wrapper = self._wrapper()
        expected_fields = [
            "mode",
            "initial_modeling_context",
            "final_modeling_context",
            "workspace_context",
            "batch_inventory",
            "batch_details",
            "entities_read",
            "statements_read",
            "candidate_required_assertions",
            "term_bindings",
            "materialized_quads",
            "materialized_digest",
            "evidence_bindings",
            "statement_lineage",
            "pagination",
        ]
        response = wrapper.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = response["result"]["tools"]
        tool = next(item for item in tools if item["name"] == wrapper.TOOL_NAME)
        schema = tool["inputSchema"]
        self.assertEqual(tool["name"], wrapper.TOOL_NAME)
        self.assertEqual(schema["required"], expected_fields)
        self.assertEqual(set(schema["properties"]), set(expected_fields))
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("strict native retrieval proof v2", schema["description"])
        self.assertEqual(schema["properties"]["mode"]["enum"], ["create"])
        self.assertIn("exact literal `create`", schema["properties"]["mode"]["description"])
        self.assertEqual(
            {name: schema["properties"][name]["type"] for name in expected_fields},
            {
                "mode": "string",
                "initial_modeling_context": "object",
                "final_modeling_context": "object",
                "workspace_context": "object",
                "batch_inventory": "object",
                "batch_details": "array",
                "entities_read": "object",
                "statements_read": "object",
                "candidate_required_assertions": "object",
                "term_bindings": "array",
                "materialized_quads": "array",
                "materialized_digest": "string",
                "evidence_bindings": "array",
                "statement_lineage": "array",
                "pagination": "object",
            },
        )
        for name in ("initial_modeling_context", "final_modeling_context", "workspace_context", "entities_read"):
            self.assertEqual(schema["properties"][name]["required"], ["ok", "data"])
            self.assertEqual(schema["properties"][name]["properties"]["ok"]["type"], "boolean")
            self.assertEqual(schema["properties"][name]["properties"]["data"]["type"], "object")
        self.assertEqual(schema["properties"]["batch_details"]["items"]["type"], "object")
        self.assertEqual(
            schema["properties"]["statement_lineage"]["items"]["required"],
            ["assertion_id", "fact_id", "quad", "target", "response"],
        )
        self.assertEqual(
            schema["properties"]["candidate_required_assertions"]["properties"]["items"]["items"]["required"],
            [
                "assertion_id",
                "graph_role",
                "subject",
                "predicate",
                "object",
                "object_kind",
                "object_datatype",
                "object_language",
                "evidence_citations",
            ],
        )
        self.assertIn("direct arguments", schema["description"].lower())

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
            },
        )
        self.assertEqual(schema["properties"]["requirement_id"]["enum"], ["R2.3-003"])
        project_id = "project-003"
        ontology_id = "ontology-003"
        workspace_version = "workspace-v1"
        target_ids = (
            "unknown-cross-release-output-meaning",
            "unknown-b-no-score-behavior",
        )
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v2",
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
        self.assertEqual([batch["stage_kind"] for batch in plan["batches"]], ["class", "delete-only"])
        self.assertTrue(plan["batches"][-1]["delete_only"])
        self.assertEqual(plan["batches"][-1]["phase"], "B")

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
        self.assertEqual(blocked_plan["batches"], [{"stage_kind": "class", "client_batch_id": "1-stage1-class", "idempotency_key": "1-stage1-class-v1", "items": [{"client_item_id": "new-class", "command_kind": "create_class", "payload": {"class_id": "ReviewOutcome", "name": "ReviewOutcome"}, "evidence": []}]}])
        self.assertEqual(
            {conflict["code"] for conflict in blocked_plan["conflicts"]},
            {"phase_a_readback_required"},
        )
        candidate_005 = {
            "candidate_kind": "platform-neutral-candidate-v2",
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

    def test_candidate_map_tool_emits_exact_map_and_is_idempotent(self) -> None:
        wrapper = self._wrapper()
        candidate = self._valid_candidate()
        arguments = {
            "candidate": candidate,
            "client_item_ids": {"assertion-1": "item-1"},
        }
        request = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": wrapper.EVIDENCE_MAP_TOOL_NAME, "arguments": arguments},
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            previous = Path.cwd()
            os.chdir(base)
            try:
                with self._runtime_authority(wrapper, base, "run-1"):
                    response = wrapper.handle(request)
                self.assertIsNotNone(response)
                assert response is not None
                self.assertNotIn("error", response)
                value = response["result"]["structuredContent"]
                self.assertEqual(
                    set(value), {"schema_version", "run_id", "candidate_digest", "rows", "map_digest"}
                )
                self.assertEqual(
                    set(value["rows"][0]),
                    {
                        "assertion_id",
                        "citation_digest",
                        "client_item_id",
                        "document_name",
                        "excerpt_sha256",
                        "inline_evidence_identity",
                        "citation_group_digest",
                    },
                )
                wrapper.validate_candidate_item_evidence_map(candidate, value, expected_run_id="run-1")
                target = base / "evidence/candidate-item-evidence-map.json"
                first_bytes = target.read_bytes()
                metadata = target.stat()
                self.assertTrue(stat.S_ISREG(metadata.st_mode))
                self.assertFalse(target.is_symlink())
                self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)

                with self._runtime_authority(wrapper, base, "run-1"):
                    repeated = wrapper.handle({**request, "id": 11})
                self.assertIsNotNone(repeated)
                assert repeated is not None
                self.assertNotIn("error", repeated)
                self.assertEqual(first_bytes, target.read_bytes())

                target.write_bytes(first_bytes.replace(b"item-1", b"item-x"))
                with self._runtime_authority(wrapper, base, "run-1"):
                    tampered_on_disk = wrapper.handle({**request, "id": 12})
                self.assertIsNotNone(tampered_on_disk)
                assert tampered_on_disk is not None
                self.assertEqual(tampered_on_disk["error"]["code"], -32011)
                target.write_bytes(first_bytes)

                tampered = dict(candidate)
                tampered["items"] = [dict(candidate["items"][0], object="different")]
                with self._runtime_authority(wrapper, base, "run-1"):
                    rejected = wrapper.handle(
                        {
                            **request,
                            "id": 13,
                            "params": {
                                "name": wrapper.EVIDENCE_MAP_TOOL_NAME,
                                "arguments": {**arguments, "candidate": tampered},
                            },
                        }
                    )
                self.assertIsNotNone(rejected)
                assert rejected is not None
                self.assertEqual(rejected["error"]["code"], -32011)
                self.assertEqual(first_bytes, target.read_bytes())

                malformed = wrapper.handle(
                    {
                        **request,
                        "id": 14,
                        "params": {
                            "name": wrapper.EVIDENCE_MAP_TOOL_NAME,
                            "arguments": {**arguments, "unexpected": True},
                        },
                    }
                )
                self.assertIsNotNone(malformed)
                assert malformed is not None
                self.assertEqual(malformed["error"]["code"], -32602)
            finally:
                os.chdir(previous)

    def test_candidate_map_tool_uses_runtime_authority_and_rejects_context_or_caller_drift(self) -> None:
        wrapper = self._wrapper()
        candidate = self._valid_candidate()
        arguments = {
            "candidate": candidate,
            "client_item_ids": {"assertion-1": "item-1"},
        }

        def call(value: dict[str, object]):
            return wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 20,
                    "method": "tools/call",
                    "params": {"name": wrapper.EVIDENCE_MAP_TOOL_NAME, "arguments": value},
                }
            )

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            previous = Path.cwd()
            os.chdir(base)
            try:
                with self._runtime_authority(wrapper, base, "run-1"):
                    response = call(arguments)
                assert response is not None
                self.assertNotIn("error", response)
                produced = response["result"]["structuredContent"]
                self.assertEqual(produced["run_id"], "run-1")
                wrapper.validate_candidate_item_evidence_map(
                    candidate, produced, expected_run_id="run-1"
                )

                spoofed = call({**arguments, "run_id": "run-attacker"})
                assert spoofed is not None
                self.assertEqual(spoofed["error"]["code"], -32602)

                with patch.dict(os.environ, {}, clear=True), patch.object(
                    wrapper, "RUNTIME_CONTEXT_PATH", base / "mechanics-contract.json"
                ):
                    missing_env = call(arguments)
                assert missing_env is not None
                self.assertEqual(missing_env["error"]["code"], -32011)

                context = base / "mechanics-contract.json"
                context.unlink()
                with patch.object(wrapper, "RUNTIME_CONTEXT_PATH", context), patch.dict(
                    os.environ, {wrapper.RUNTIME_RUN_ID_ENV: "run-1"}, clear=False
                ):
                    missing_context = call(arguments)
                assert missing_context is not None
                self.assertEqual(missing_context["error"]["code"], -32011)

                context.write_bytes(wrapper.protocol_mechanics_contract_bytes("run-2"))
                os.chmod(context, 0o444)
                with patch.object(wrapper, "RUNTIME_CONTEXT_PATH", context), patch.dict(
                    os.environ, {wrapper.RUNTIME_RUN_ID_ENV: "run-1"}, clear=False
                ):
                    cross_run = call(arguments)
                assert cross_run is not None
                self.assertEqual(cross_run["error"]["code"], -32011)

                os.chmod(context, 0o444)
                os.chmod(context, 0o600)
                context.write_bytes(b"tampered")
                os.chmod(context, 0o444)
                with patch.object(wrapper, "RUNTIME_CONTEXT_PATH", context), patch.dict(
                    os.environ, {wrapper.RUNTIME_RUN_ID_ENV: "run-1"}, clear=False
                ):
                    tampered = call(arguments)
                assert tampered is not None
                self.assertEqual(tampered["error"]["code"], -32011)
            finally:
                os.chdir(previous)

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
        map_tool = next(
            item
            for item in wrapper.handle({"method": "tools/list"})["result"]["tools"]
            if item["name"] == wrapper.EVIDENCE_MAP_TOOL_NAME
        )
        self.assertEqual(map_tool["inputSchema"]["required"], ["candidate", "client_item_ids"])
        self.assertEqual(
            set(map_tool["inputSchema"]["properties"]), {"candidate", "client_item_ids"}
        )
        self.assertNotIn("run_id", map_tool["inputSchema"]["properties"])
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

    def test_wrapper_rejects_malformed_proof_and_passes_valid_direct_arguments_unchanged(self) -> None:
        wrapper = self._wrapper()
        valid = self._valid_arguments(wrapper)
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": wrapper.TOOL_NAME, "arguments": valid},
        }
        expected_result = {"complete": True, "ontology_id": "ontology-1"}
        with patch.object(wrapper, "verify_scoped_retrieval_fallback", return_value=expected_result) as verifier:
            response = wrapper.handle(request)
        assert response is not None
        self.assertEqual(response["result"]["structuredContent"], expected_result)
        self.assertIs(verifier.call_args.args[0], valid)

        malformed = (
            {**valid, "mode": []},
            {name: value for name, value in valid.items() if name != "mode"},
            {**valid, "unexpected": True},
            {"proof": valid},
        )
        for arguments in malformed:
            with self.subTest(arguments=json.dumps(arguments, sort_keys=True)):
                response = wrapper.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": wrapper.TOOL_NAME, "arguments": arguments},
                    }
                )
                assert response is not None
                self.assertEqual(response["error"]["code"], -32602)

        with patch.object(wrapper, "verify_scoped_retrieval_fallback") as verifier:
            response = wrapper.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": wrapper.TOOL_NAME,
                        "arguments": {**valid, "mode": "fresh_create"},
                    },
                }
            )
        assert response is not None
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("exact literal create", response["error"]["message"])
        verifier.assert_not_called()

    def test_protocol_instructions_and_reference_require_direct_arguments(self) -> None:
        root = repository_root()
        instructions = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text(encoding="utf-8")
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(encoding="utf-8")
        )
        self.assertIn("ten proof fields as direct arguments", instructions)
        self.assertIn("never nest a\n`proof` object", instructions)
        self.assertIn("only the exact literal\n`create`; `fresh_create` is not accepted", instructions)
        helper_rule = reference["semantic_retrieval_completion_contract"]["fallback"]["deterministic_helper"]["rule"]
        self.assertIn("ten mechanical proof fields as direct arguments", helper_rule)
        self.assertIn("mode field MUST equal the exact string create; fresh_create is not accepted", helper_rule)
        self.assertIn("-32602", helper_rule)
