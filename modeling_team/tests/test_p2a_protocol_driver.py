from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import digest_file, load_team_configuration
from modeling_team.matrix_artifact import load_matrix
from modeling_team.p2a_protocol_driver import (
    CONTRACT_RELATIVE_PATH,
    P2AProtocolDriverError,
    SYNTHETIC_MODELING_ID,
    _CONTINUATION_TEXT,
    _canonical_digest,
    _continuation_delivery,
    _continuation_evidence_payload,
    _continuation_eligible,
    _read_continuation_baseline,
    _idle_stage_error,
    _read_native_verifier_attempt_events,
    _read_native_verifier_events,
    _observe_authoritative_dry_run,
    _observe_postapply_same_evidence_ids,
    _promote_candidate_item_evidence_map,
    _generated_candidate,
    _task_text,
    load_contract,
)
from modeling_team.proof_v2 import build_candidate_item_evidence_map
from modeling_team.runner import TeamRunner


class P2AProtocolDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1].parent

    def test_contract_and_candidate_are_static_and_runner_free(self) -> None:
        contract = load_contract(self.root / CONTRACT_RELATIVE_PATH)
        self.assertEqual(contract["candidate_sender_id"], SYNTHETIC_MODELING_ID)
        self.assertEqual(contract["protocol_agent_id"], "protocol")
        self.assertIn("dry_run_observed", contract["required_stages"])
        self.assertEqual(contract["runtime_contract"]["idle_flush_grace_seconds"], 1.0)
        retrieval_contract = contract["runtime_contract"]["protocol_retrieval_mcp"]
        self.assertEqual(retrieval_contract["runtime_run_id_env"], "PROTOCOL_RUNTIME_RUN_ID")
        self.assertEqual(retrieval_contract["runtime_context_path"], "/opt/mechanics-contract.json")
        self.assertEqual(
            retrieval_contract["tools"],
            [
                "build_candidate_receipt",
                "verify_scoped_retrieval_fallback",
                "write_candidate_item_evidence_map",
            ],
        )
        proof_asset = contract["runtime_contract"]["proof_v2_asset"]
        self.assertEqual(proof_asset["source_path"], "modeling_team/proof_v2.py")
        self.assertEqual(proof_asset["staged_path"], "runtime-assets/protocol/proof_v2.py")
        self.assertEqual(proof_asset["mount_path"], "/opt/proof_v2.py")
        self.assertEqual(proof_asset["sha256"], digest_file(self.root / "modeling_team/proof_v2.py"))
        self.assertIn("semantic_start", " ".join(contract["forbidden_evidence"]))
        source = (self.root / "modeling_team/p2a_protocol_driver.py").read_text(encoding="utf-8")
        self.assertNotIn("from .runner import", source)
        self.assertNotIn("from .start_ledger import", source)

        matrix = load_matrix(self.root)
        candidate, selected = _generated_candidate(matrix)
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            {row["binding_category"] for row in selected},
            {"resource_output", "relation_delta", "literal_delta", "vocabulary"},
        )
        self.assertEqual(set(candidate), {
            "schema_version",
            "candidate_revision",
            "delivery_id",
            "reply_chain",
            "semantic_digest",
            "candidate_digest",
            "items",
        })
        self.assertEqual(candidate["schema_version"], "candidate-required-assertions/v2")
        self.assertEqual(candidate["candidate_revision"], "p2a-generated-2")
        by_assertion = {item["assertion_id"]: item for item in candidate["items"]}
        self.assertEqual(by_assertion["r23002-a008"]["subject"], "p2a:generated-subject")
        self.assertEqual(
            by_assertion["r23002-a008"]["object_datatype"],
            "http://www.w3.org/2001/XMLSchema#string",
        )
        self.assertEqual(
            contract["runtime_contract"]["native_mcp"],
            [
                "team_transport",
                "ontology_platform",
                "protocol_mechanics",
                "p2a_protocol_overlay",
            ],
        )

    def test_native_verifier_failure_reader_accepts_only_safe_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            evidence = run_root / "evidence"
            evidence.mkdir()
            safe = {
                "error_code": -32010,
                "failure_layer": "proof_validation",
                "error_message_sha256": "a" * 64,
                "top_level_exact": True,
                "types_valid": True,
                "mode_create": True,
            }
            (evidence / "native-verifier-events.jsonl").write_text(
                json.dumps(safe) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(_read_native_verifier_events(run_root), [safe])

    def test_native_verifier_failure_reader_rejects_extra_or_raw_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            evidence = run_root / "evidence"
            evidence.mkdir()
            unsafe = {
                "error_code": -32602,
                "failure_layer": "argument_contract",
                "error_message_sha256": "b" * 64,
                "top_level_exact": False,
                "types_valid": False,
                "mode_create": True,
                "raw": "must-not-pass",
            }
            (evidence / "native-verifier-events.jsonl").write_text(
                json.dumps(unsafe) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(P2AProtocolDriverError, "fields drifted"):
                _read_native_verifier_events(run_root)

    def test_native_attempt_reader_is_strict_and_counts_only_accepted_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            evidence = run_root / "evidence"
            evidence.mkdir()
            values = [
                {
                    "event": "native_verifier_approval",
                    "native_call_count": count,
                    "action": "accept",
                    "created_at_ns": count,
                }
                for count in (1, 2, 3)
            ]
            values.append(
                {
                    "event": "native_verifier_approval",
                    "native_call_count": 3,
                    "action": "decline",
                    "created_at_ns": 4,
                }
            )
            path = evidence / "native-verifier-attempt-events.jsonl"
            path.write_text("".join(json.dumps(value) + "\n" for value in values))
            self.assertEqual(_read_native_verifier_attempt_events(run_root), values)
            values[0]["raw"] = "must-not-pass"
            path.write_text("".join(json.dumps(value) + "\n" for value in values))
            with self.assertRaisesRegex(P2AProtocolDriverError, "fields drifted"):
                _read_native_verifier_attempt_events(run_root)

    def test_continuation_eligibility_is_exact_and_delivery_is_fixed(self) -> None:
        eligible = {
            "receipt_seen": True,
            "map_seen": True,
            "dry_run_seen": True,
            "apply_seen": True,
            "postapply_seen": True,
            "retrieval_seen": True,
            "failure_layer": "proof_validation",
            "verifier_seen": False,
            "broker_seen": False,
            "agent_state": "idle",
            "active_turn_id": None,
            "continuation_count": 0,
            "native_call_count": 2,
        }
        self.assertTrue(_continuation_eligible(**eligible))
        ineligible_values = {
            "receipt_seen": False,
            "map_seen": False,
            "dry_run_seen": False,
            "apply_seen": False,
            "postapply_seen": False,
            "retrieval_seen": False,
            "failure_layer": "transport",
            "verifier_seen": True,
            "broker_seen": True,
            "agent_state": "running",
            "active_turn_id": "turn-active",
            "continuation_count": 1,
            "native_call_count": 3,
        }
        for field, value in ineligible_values.items():
            with self.subTest(field=field):
                changed = {**eligible, field: value}
                self.assertFalse(_continuation_eligible(**changed))
        delivery = _continuation_delivery("p2a-run-1")
        self.assertEqual(delivery.delivery_id, "p2a-run-1-native-continuation-1")
        self.assertEqual(delivery.sender_id, "p2a-host")
        self.assertEqual(delivery.recipient_id, "protocol")
        self.assertEqual(delivery.kind, "p2a-native-correction")
        self.assertEqual(delivery.text, _CONTINUATION_TEXT)
        self.assertIn("error visible in the preceding turn", delivery.text)
        self.assertIn("Correct only the proof input", delivery.text)
        self.assertIn("additional read-only platform reads", delivery.text)
        self.assertIn("Do not repeat dry_run or apply_atomic", delivery.text)
        self.assertIn("complete=true", delivery.text)
        self.assertFalse(delivery.expects_reply)
        self.assertIsNone(delivery.reply_to_delivery_id)
        safe = _continuation_evidence_payload(
            continuation_index=1,
            native_call_count=2,
            failure_layer="proof_validation",
            baseline_match=True,
            created_at_ns=7,
        )
        self.assertEqual(
            safe,
            {
                "continuation_index": 1,
                "native_call_count": 2,
                "failure_layer": "proof_validation",
                "baseline_match": True,
                "created_at_ns": 7,
            },
        )
        self.assertTrue(all(token not in safe for token in ("raw", "message", "args", "secret")))

    def test_contract_freezes_bounded_correction_without_new_lifecycle(self) -> None:
        contract = load_contract(self.root / CONTRACT_RELATIVE_PATH)
        correction = contract["runtime_contract"]["bounded_correction"]
        self.assertEqual(
            correction,
            {
                "adapter_method": "send_message",
                "credential_expiry": "explicit_null_when_unsupported",
                "lease_policy": "exact_identity_and_original_expiry_no_renew",
                "max_continuations": 1,
                "max_native_verifier_calls": 3,
                "same_agent_thread_run": True,
            },
        )

    def test_task_text_allows_only_bounded_proof_correction(self) -> None:
        matrix = load_matrix(self.root)
        candidate, _ = _generated_candidate(matrix)
        run = SimpleNamespace(protocol_context={"ontology_id": "ontology-1"})
        text = _task_text(run, candidate, matrix)
        self.assertIn("correct only the proof input", text)
        self.assertIn("additional read-only platform reads", text)
        self.assertIn("at most three times", text)
        self.assertIn("Never repeat dry_run or apply_atomic", text)
        self.assertIn("Report terminal once only after complete=true", text)

    def test_continuation_baseline_exact_identity_expiry_and_movement_gate(self) -> None:
        batch = {
            "batch_id": "batch-1",
            "ontology_id": "ontology-1",
            "build_session_id": "session-1",
            "items": [],
            "attempts": [
                {
                    "attempt_id": "dry-1",
                    "mode": "dry_run",
                    "attempt_status": "validated",
                    "findings": [],
                    "operation_plan": {"evidence": []},
                },
                {
                    "attempt_id": "apply-1",
                    "mode": "apply_atomic",
                    "attempt_status": "applied",
                    "findings": [],
                },
            ],
        }
        values = {
            "/api/modeling-batches/batch-1": batch,
            "/api/build-sessions/session-1": {
                "session": {
                    "id": "session-1",
                    "project_id": "project-1",
                    "status": "active",
                    "revision": 4,
                },
                "leases": [
                    {
                        "ontology_id": "ontology-1",
                        "build_session_id": "session-1",
                        "lease_revision": 1,
                        "state": "active",
                        "expires_at": "2099-01-01T00:00:00+00:00",
                        "renewed_at": None,
                    }
                ],
            },
            "/api/api-keys/key-1": {
                "id": "key-1",
                "project_id": "project-1",
                "scopes": ["model"],
                "created_at": "2026-08-02T00:00:00+00:00",
                "revoked_at": None,
            },
            "/api/ontologies/ontology-1/workspace-context": {
                "state": "ready",
                "workspace_version": "workspace-2",
            },
            "/api/ontologies/ontology-1/modeling-context": {
                "project": {"id": "project-1"},
                "ontology": {"id": "ontology-1"},
                "workspace": {"state": "ready", "workspace_version": "workspace-2"},
            },
        }

        class Scope:
            project_id = "project-1"
            ontology_id = "ontology-1"
            protocol_key_id = "key-1"
            protocol_key = "secret"
            admin_key = "admin"

            def __init__(self):
                self.calls = []

            def request(self, method, path, body, key):
                self.calls.append((method, path, body, key))
                return (200, values[path]) if path in values else (404, None)

        scope = Scope()
        run = SimpleNamespace(run_id="p2a-run-1", protocol_key="secret")
        agent = SimpleNamespace(agent_id="protocol", thread_id="thread-1")
        batch_snapshot = {"candidate_batch_id": "batch-1", "dry_run_attempt_id": "dry-1"}
        applied_snapshot = {
            "apply_attempt_id": "apply-1",
            "detail_sha256": _canonical_digest(batch),
        }
        baseline = _read_continuation_baseline(
            scope, run, agent, batch_snapshot, applied_snapshot
        )
        self.assertEqual(
            baseline,
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot),
        )
        self.assertEqual(baseline["lease_identity"], ["session-1", "ontology-1"])
        self.assertEqual(baseline["lease_expires_at"], "2099-01-01T00:00:00+00:00")
        self.assertIsNone(baseline["credential_expires_at"])
        self.assertFalse(baseline["credential_expiry_present"])

        original_lease = dict(values["/api/build-sessions/session-1"]["leases"][0])
        for field, value in (
            ("lease_revision", 2),
            ("renewed_at", "2026-08-02T01:00:00+00:00"),
        ):
            with self.subTest(field=field):
                values["/api/build-sessions/session-1"]["leases"][0] = {
                    **original_lease,
                    field: value,
                }
                with self.assertRaisesRegex(P2AProtocolDriverError, "Lease is not valid"):
                    _read_continuation_baseline(
                        scope, run, agent, batch_snapshot, applied_snapshot
                    )
        values["/api/build-sessions/session-1"]["leases"][0] = {
            **original_lease,
            "expires_at": "2099-02-01T00:00:00+00:00",
        }
        changed = _read_continuation_baseline(
            scope, run, agent, batch_snapshot, applied_snapshot
        )
        self.assertNotEqual(changed, baseline)
        values["/api/build-sessions/session-1"]["leases"][0] = {
            **original_lease,
            "expires_at": "2000-01-01T00:00:00+00:00",
        }
        with self.assertRaisesRegex(P2AProtocolDriverError, "Lease is not valid"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        values["/api/build-sessions/session-1"]["leases"][0] = original_lease

        values["/api/build-sessions/session-1"]["session"]["revision"] = 5
        changed = _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        self.assertNotEqual(changed, baseline)
        values["/api/build-sessions/session-1"]["session"]["revision"] = 4
        values["/api/build-sessions/session-1"]["session"]["id"] = "session-recreated"
        with self.assertRaisesRegex(P2AProtocolDriverError, "Build Session baseline"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        values["/api/build-sessions/session-1"]["session"]["id"] = "session-1"

        credential = values["/api/api-keys/key-1"]
        credential["expires_at"] = None
        changed = _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        self.assertNotEqual(changed, baseline)
        credential.pop("expires_at")
        credential["revoked_at"] = "2026-08-02T01:00:00+00:00"
        with self.assertRaisesRegex(P2AProtocolDriverError, "credential is not valid"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        credential["revoked_at"] = None
        credential["id"] = "key-recreated"
        with self.assertRaisesRegex(P2AProtocolDriverError, "credential is not valid"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        credential["id"] = "key-1"

        values["/api/ontologies/ontology-1/workspace-context"]["workspace_version"] = "drift"
        with self.assertRaisesRegex(P2AProtocolDriverError, "workspace baseline"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        values["/api/ontologies/ontology-1/workspace-context"]["workspace_version"] = "workspace-2"
        batch["attempts"].append(
            {"attempt_id": "apply-2", "mode": "apply_atomic", "attempt_status": "applied"}
        )
        with self.assertRaisesRegex(P2AProtocolDriverError, "batch baseline drifted"):
            _read_continuation_baseline(scope, run, agent, batch_snapshot, applied_snapshot)
        self.assertTrue(scope.calls)
        self.assertEqual({call[0] for call in scope.calls}, {"GET"})
        self.assertFalse(
            any(
                action in call[1]
                for call in scope.calls
                for action in (":acquire", ":renew", ":resume", "/api/api-keys")
                if call[1] != "/api/api-keys/key-1"
            )
        )

    def test_baseline_registers_p2a_driver_without_gating_legacy_task(self) -> None:
        manifest, _ = TeamRunner.preview_baseline(
            repository_root=self.root,
            run_id="p2a-baseline-test",
            profile_path=self.root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=self.root / "modeling_team/tasks/new-scope-business-slice.yaml",
        )
        self.assertEqual(
            manifest["files"]["p2a_protocol_driver"],
            digest_file(self.root / "modeling_team/p2a_protocol_driver.py"),
        )
        self.assertEqual(
            manifest["files"]["p2a_protocol_driver_contract"],
            digest_file(self.root / CONTRACT_RELATIVE_PATH),
        )
        self.assertEqual(
            manifest["runtime_contract"]["p2a_protocol_driver"]["candidate_sender_id"],
            SYNTHETIC_MODELING_ID,
        )
        self.assertEqual(
            manifest["runtime_contract"]["proof_v2"]["runtime_asset"]["sha256"],
            digest_file(self.root / "modeling_team/proof_v2.py"),
        )
        legacy = load_team_configuration(
            self.root / "modeling_team/profiles/base-three-agent.yaml",
            self.root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=self.root,
        )
        self.assertIsNone(legacy.task.expected_matrix_binding)

    def test_candidate_map_promotion_and_authoritative_dry_run_group_compare(self) -> None:
        matrix = load_matrix(self.root)
        candidate, _ = _generated_candidate(matrix)
        mapping = {
            "r23002-a008": "p2a-01-literal-a008",
            "r23002-a009": "p2a-02-resource-a009",
            "r23002-a004": "p2a-03-relation-a004",
            "r23002-a001": "p2a-04-vocabulary-a001",
        }
        evidence_map = build_candidate_item_evidence_map(candidate, mapping, run_id="p2a-test")
        identities = {
            identity: f"reference-{index}"
            for index, identity in enumerate(
                sorted({row["inline_evidence_identity"] for row in evidence_map["rows"]}),
                1,
            )
        }
        grouped_rows = {
            (row["client_item_id"], row["inline_evidence_identity"]): row
            for row in evidence_map["rows"]
        }
        plan_rows = [
            {
                "client_item_id": row["client_item_id"],
                "document_name": row["document_name"],
                "normalized_excerpt_sha256": row["excerpt_sha256"],
                "dedupe_identity": identities[row["inline_evidence_identity"]],
            }
            for row in grouped_rows.values()
        ]
        detail = {
            "batch_id": "batch-1",
            "ontology_id": "ontology-1",
            "build_session_id": "session-1",
            "items": [{"client_item_id": item_id} for item_id in sorted(mapping.values())],
            "attempts": [
                {
                    "attempt_id": "attempt-1",
                    "mode": "dry_run",
                    "attempt_status": "validated",
                    "findings": [],
                    "operation_plan": {"evidence": plan_rows},
                }
            ],
        }

        class Scope:
            ontology_id = "ontology-1"
            admin_key = "admin"

            def request(self, method, path, body, key):
                assert method == "GET"
                assert key == "admin"
                if path.endswith("?limit=100"):
                    return 200, {"batches": [{"batch_id": "batch-1"}], "next_cursor": None}
                assert path == "/api/modeling-batches/batch-1"
                return 200, detail

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            runtime = base / "runtime-work"
            source = runtime / "evidence/candidate-item-evidence-map.json"
            source.parent.mkdir(parents=True, mode=0o700)
            source.write_text(json.dumps(evidence_map, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            promoted, digest = _promote_candidate_item_evidence_map(
                base / "run",
                runtime,
                candidate,
                "p2a-test",
            )
            target = base / "run/evidence/candidate-item-evidence-map.json"
            self.assertEqual(promoted, evidence_map)
            self.assertEqual(digest, digest_file(target))
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            snapshot = _observe_authoritative_dry_run(Scope(), candidate, promoted)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot["candidate_batch_id"], "batch-1")
            self.assertEqual(snapshot["dry_run_attempt_id"], "attempt-1")
            self.assertEqual(len(snapshot["plan_rows"]), 4)
            self.assertTrue(
                all(
                    set(row)
                    == {
                        "client_item_id",
                        "inline_evidence_identity",
                        "dedupe_identity",
                    }
                    for row in snapshot["plan_rows"]
                )
            )

    def test_candidate_map_missing_duplicate_and_plan_mismatch_fail_closed(self) -> None:
        matrix = load_matrix(self.root)
        candidate, _ = _generated_candidate(matrix)
        mapping = {
            "r23002-a008": "p2a-01-literal-a008",
            "r23002-a009": "p2a-02-resource-a009",
            "r23002-a004": "p2a-03-relation-a004",
            "r23002-a001": "p2a-04-vocabulary-a001",
        }
        evidence_map = build_candidate_item_evidence_map(candidate, mapping, run_id="p2a-test")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaisesRegex(P2AProtocolDriverError, "unavailable"):
                _promote_candidate_item_evidence_map(base / "run", base / "runtime", candidate, "p2a-test")
            runtime = base / "runtime"
            source = runtime / "evidence/candidate-item-evidence-map.json"
            source.parent.mkdir(parents=True, mode=0o700)
            duplicate = {**evidence_map, "rows": [*evidence_map["rows"], evidence_map["rows"][0]]}
            source.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(P2AProtocolDriverError, "invalid"):
                _promote_candidate_item_evidence_map(base / "run", runtime, candidate, "p2a-test")

        class Scope:
            ontology_id = "ontology-1"
            admin_key = "admin"

            def request(self, method, path, body, key):
                if path.endswith("?limit=100"):
                    return 200, {"batches": [{"batch_id": "batch-1"}], "next_cursor": None}
                return 200, {
                    "batch_id": "batch-1",
                    "ontology_id": "ontology-1",
                    "items": [{"client_item_id": item_id} for item_id in sorted(mapping.values())],
                    "attempts": [
                        {
                            "attempt_id": "attempt-1",
                            "mode": "dry_run",
                            "attempt_status": "validated",
                            "findings": [],
                            "operation_plan": {"evidence": []},
                        }
                    ],
                }

        with self.assertRaisesRegex(P2AProtocolDriverError, "mismatches"):
            _observe_authoritative_dry_run(Scope(), candidate, evidence_map)

    def test_idle_flush_reports_missing_stage_without_waiting_for_hard_timeout(self) -> None:
        message = _idle_stage_error(
            agent_state="idle",
            retrieval_seen=True,
            terminal_present=False,
            idle_since=10.0,
            now=10.0 + 1.1,
            stages={"dry_run_observed": False, "native_verifier_completed": False},
        )
        self.assertEqual(
            message,
            "P2a Protocol turn completed idle before stages: dry_run_observed, native_verifier_completed",
        )

    def test_postapply_observer_requires_same_dry_run_reference_ids(self) -> None:
        plan_rows = [
            {
                "client_item_id": client_item_id,
                "inline_evidence_identity": f"identity-{index}",
                "dedupe_identity": f"reference-{index}",
            }
            for index, client_item_id in enumerate(
                (
                    "p2a-01-literal-a008",
                    "p2a-02-resource-a009",
                    "p2a-03-relation-a004",
                    "p2a-04-vocabulary-a001",
                ),
                1,
            )
        ]
        detail = {
            "batch_id": "batch-1",
            "attempts": [
                {
                    "attempt_id": "apply-1",
                    "mode": "apply_atomic",
                    "attempt_status": "applied",
                    "items": [
                        {
                            "client_item_id": row["client_item_id"],
                            "evidence_reference_ids": [row["dedupe_identity"]],
                        }
                        for row in plan_rows
                    ],
                }
            ],
        }

        class Scope:
            admin_key = "admin"

            def request(self, method, path, body, key):
                self.assert_request = (method, path, body, key)
                return 200, detail

        observed = _observe_postapply_same_evidence_ids(
            Scope(),
            {"candidate_batch_id": "batch-1", "plan_rows": plan_rows},
        )
        self.assertIsNotNone(observed)
        detail["attempts"][0]["items"][0]["evidence_reference_ids"] = ["drift"]
        with self.assertRaisesRegex(P2AProtocolDriverError, "drift"):
            _observe_postapply_same_evidence_ids(
                Scope(),
                {"candidate_batch_id": "batch-1", "plan_rows": plan_rows},
            )

    def test_task_text_freezes_overlay_order_platform_ownership_and_plain_literal(self) -> None:
        matrix = load_matrix(self.root)
        candidate, _ = _generated_candidate(matrix)
        run = SimpleNamespace(protocol_context={"ontology_id": "ontology-1"})
        text = _task_text(run, candidate, matrix)

        self.assertLess(text.index("build_candidate_receipt"), text.index("write_candidate_item_evidence_map"))
        self.assertLess(text.index("write_candidate_item_evidence_map"), text.index("build_p2a_batch_plan"))
        self.assertIn("you personally own every ontology-platform MCP call", text)
        self.assertIn("two authorized get_modeling_batch detail reads R1 and R2", text)
        self.assertIn("postapply_evidence_bindings", text)
        self.assertIn("plain literal published", text)
        self.assertIn("full XSD string IRI is proof normalization only", text)

    def test_idle_flush_stage_matrix_fails_at_the_first_missing_stage(self) -> None:
        stage_names = (
            "candidate_item_evidence_map_promoted",
            "dry_run_observed",
            "apply_observed",
            "retrieval_observed",
            "native_verifier_completed",
            "protocol_report_accepted",
        )
        for missing_stage in stage_names:
            with self.subTest(missing_stage=missing_stage):
                stages = {name: True for name in stage_names}
                stages[missing_stage] = False
                message = _idle_stage_error(
                    agent_state="idle",
                    terminal_present=False,
                    idle_since=10.0,
                    now=11.1,
                    stages=stages,
                    turn_started=True,
                )
                self.assertEqual(
                    message,
                    "P2a Protocol turn completed idle before stages: " + missing_stage,
                )

        active = _idle_stage_error(
            agent_state="running",
            terminal_present=False,
            idle_since=10.0,
            now=11.1,
            stages={name: False for name in stage_names},
            turn_started=True,
        )
        self.assertIsNone(active)

        grace_pending = _idle_stage_error(
            agent_state="idle",
            terminal_present=False,
            idle_since=10.0,
            now=10.9,
            stages={name: False for name in stage_names},
            turn_started=True,
        )
        self.assertIsNone(grace_pending)

        unstarted = _idle_stage_error(
            agent_state="idle",
            terminal_present=False,
            idle_since=10.0,
            now=11.1,
            stages={name: False for name in stage_names},
            turn_started=False,
        )
        self.assertIsNone(unstarted)


if __name__ == "__main__":
    unittest.main()
