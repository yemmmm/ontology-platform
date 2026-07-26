"""Unit and safety checks for tester-owned M3 acceptance infrastructure."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCENARIO_ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


consumer_gateway = load("m3_consumer_gateway", "readonly_consumer_gateway.py")
consumer_launcher = load("m3_consumer_launcher", "run_readonly_consumer.py")
mutations = load("m3_acceptance_mutations", "tests/m3_acceptance_mutations.py")
gateway = load("m3_gateway_for_consumer_test", "m3_file_spool_gateway.py")
CONSUMER_RPC_CLIENT = SCENARIO_ROOT / "consumer-input-pack" / "m3_readonly_rpc.py"


class M3AcceptanceToolTests(unittest.TestCase):
    def valid_spec(self) -> dict:
        action = {"id": "tester-action", "items": []}
        return {
            "seed_actions": [action],
            "orthogonal_decoy_actions": [{"id": "tester-decoy", "items": []}],
            "roles": [
                {
                    "id": f"tester-role-{index}",
                    "remove": {"id": f"remove-{index}", "items": []},
                    "sentinel_replace": {"id": f"replace-{index}", "items": []},
                }
                for index in range(9)
            ],
            "queries": [
                {
                    "id": "tester-withheld-query",
                    "body": {"query": "tester supplies query text"},
                    "same_row_identity": ["workflow", "binding"],
                    "expected": {
                        "baseline": {
                            "row_count": 1,
                            "bindings": [{"workflow": "tester-workflow", "binding": "tester-binding"}],
                            "predicates": {
                                "binding": ["tester-binding"],
                                "workflow": ["tester-workflow"],
                            },
                            "same_row_identity": [
                                {"workflow": "tester-workflow", "binding": "tester-binding"}
                            ],
                        },
                        "decoy": {"same_as_baseline": True},
                        "remove": {"break": True, "row_count": 0},
                        "sentinel_replace": {"break": True, "row_count": 0},
                    },
                }
            ],
        }

    def test_mutation_spec_is_tester_defined_and_requires_nine_roles(self) -> None:
        spec = self.valid_spec()
        self.assertEqual(mutations.validate_spec(spec)["queries"][0]["id"], "tester-withheld-query")
        spec["roles"].pop()
        with self.assertRaises(mutations.AcceptanceSpecError):
            mutations.validate_spec(spec)

    def test_seed_items_files_imports_only_modeling_items_and_keeps_inline_compatibility(self) -> None:
        spec = self.valid_spec()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "schema-batch.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "client_item_id": "seed-one",
                                "evidence_reference_ids": ["source-project-only"],
                                "competency_question_ids": ["source-project-question"],
                            }
                        ],
                        "queries": [{"forbidden": True}],
                    }
                ),
                encoding="utf-8",
            )
            original_root = mutations.SCENARIO_ROOT
            mutations.SCENARIO_ROOT = root
            try:
                spec["seed_items_files"] = ["schema-batch.json"]
                imported, evidence = mutations.load_seed_items_files(mutations.validate_spec(spec))
                inventory = mutations.inspect_seed_items_files(["schema-batch.json"])
            finally:
                mutations.SCENARIO_ROOT = original_root
        self.assertEqual(
            imported,
            [
                {
                    "id": "seed-file-1-schema-batch",
                    "items": [
                        {
                            "client_item_id": "seed-one",
                            "evidence_reference_ids": [],
                            "evidence": [],
                            "competency_question_ids": [],
                        }
                    ],
                }
            ],
        )
        self.assertEqual(evidence[0]["item_count"], 1)
        self.assertEqual(
            inventory,
            [
                {
                    "source": "schema-batch.json",
                    "items": [
                        {
                            "index": 0,
                            "ref": "seed-one",
                            "type": None,
                            "payload_summary": {
                                "keys": [],
                                "sha256": mutations.sha256_bytes(mutations.canonical_json(None)),
                            },
                        }
                    ],
                }
            ],
        )
        self.assertEqual(spec["seed_actions"][0]["id"], "tester-action")
        starter = mutations.starter_spec()
        self.assertEqual(starter["seed_items_files"], mutations.STABLE_SEED_ITEMS_FILES)
        self.assertEqual(starter["roles"], [])
        self.assertEqual(starter["queries"], [])
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "tester-starter.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCENARIO_ROOT / "tests" / "m3_acceptance_mutations.py"),
                    "--write-starter-spec",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), starter)

    def test_mutation_evaluator_checks_baseline_decoy_and_both_breaks(self) -> None:
        spec = self.valid_spec()
        baseline_body = {
            "result": {
                "results": {
                    "bindings": [
                        {"workflow": {"value": "tester-workflow"}, "binding": {"value": "tester-binding"}}
                    ]
                }
            },
            "result_format": "application/sparql-results+json",
            "query_type": "select",
            "scope": {},
        }
        empty_body = {
            "result": {"results": {"bindings": []}},
            "result_format": "application/sparql-results+json",
            "query_type": "select",
            "scope": {},
        }

        def variant(name: str, body: dict) -> dict:
            observation = mutations.query_observation(200, body, ["workflow", "binding"])
            return {"variant": name, "queries_by_id": {"tester-withheld-query": {"actual": observation}}}

        evaluation = mutations.evaluate_queries(
            spec,
            variant("baseline", baseline_body),
            variant("decoy", baseline_body),
            variant("remove", empty_body),
            variant("sentinel_replace", empty_body),
        )
        self.assertTrue(evaluation["passed"])
        self.assertFalse(
            mutations.evaluate_queries(
                spec,
                variant("baseline", baseline_body),
                variant("decoy", empty_body),
                variant("remove", empty_body),
                variant("sentinel_replace", empty_body),
            )["passed"]
        )

    def test_query_observation_strictly_extracts_public_semantic_result(self) -> None:
        body = {
            "result": {
                "results": {
                    "bindings": [
                        {
                            "workflow": {"type": "uri", "value": "workflow-1"},
                            "binding": {"value": "binding-1"},
                        }
                    ]
                }
            },
            "result_format": "application/sparql-results+json",
            "query_type": "select",
            "scope": {},
        }
        observation = mutations.query_observation(200, body, ["workflow", "binding"])
        self.assertEqual(observation["http_status"], 200)
        self.assertNotIn("status", observation)
        self.assertEqual(observation["row_count"], 1)
        self.assertEqual(observation["bindings"], [{"workflow": "workflow-1", "binding": "binding-1"}])
        self.assertEqual(observation["same_row_identity"], [{"workflow": "workflow-1", "binding": "binding-1"}])
        with self.assertRaises(mutations.AcceptanceSpecError):
            mutations.query_observation(200, {"results": {"bindings": []}}, ["workflow"])

    def test_decoy_invariance_ignores_public_scope_but_rejects_semantic_change(self) -> None:
        spec = self.valid_spec()

        def response(binding: str, project_id: str) -> dict:
            return {
                "result": {
                    "results": {
                        "bindings": [
                            {"workflow": {"value": "tester-workflow"}, "binding": {"value": binding}}
                        ]
                    }
                },
                "result_format": "application/sparql-results+json",
                "query_type": "select",
                "scope": {"project_id": project_id, "workspace_version": f"workspace-{project_id}"},
            }

        def variant(name: str, body: dict) -> dict:
            return {
                "variant": name,
                "queries_by_id": {
                    "tester-withheld-query": {
                        "actual": mutations.query_observation(200, body, ["workflow", "binding"])
                    }
                },
            }

        empty = response("ignored", "empty")
        empty["result"]["results"]["bindings"] = []
        baseline = variant("baseline", response("tester-binding", "baseline-project"))
        decoy_same_semantics = variant("decoy", response("tester-binding", "decoy-project"))
        self.assertTrue(
            mutations.evaluate_queries(
                spec,
                baseline,
                decoy_same_semantics,
                variant("remove", empty),
                variant("sentinel_replace", empty),
            )["passed"]
        )
        self.assertFalse(
            mutations.evaluate_queries(
                spec,
                baseline,
                variant("decoy", response("changed-binding", "decoy-project")),
                variant("remove", empty),
                variant("sentinel_replace", empty),
            )["passed"]
        )

    def test_mutation_rows_preserve_per_row_identity(self) -> None:
        rows = mutations.same_row_identity(
            {"results": {"bindings": [{"workflow": {"value": "w1"}, "binding": {"value": "b1"}}]}},
            ["workflow", "binding"],
        )
        self.assertEqual(rows, [{"row_index": 0, "identity": {"workflow": "w1", "binding": "b1"}}])

    def test_consumer_gateway_allows_only_read_and_scoped_query_operations(self) -> None:
        project_id, ontology_id = "project-1", "ontology-1"
        allowed = consumer_gateway.consumer_request_allowed
        self.assertTrue(allowed({"method": "GET", "path": "/api/health"}, project_id, ontology_id))
        self.assertTrue(allowed({"method": "POST", "path": "/api/semantic/sparql:query"}, project_id, ontology_id))
        self.assertFalse(allowed({"method": "POST", "path": "/api/projects"}, project_id, ontology_id))
        self.assertFalse(allowed({"method": "DELETE", "path": "/api/ontologies/ontology-1"}, project_id, ontology_id))
        self.assertFalse(allowed({"method": "POST", "path": "/api/semantic/graph-sets/x/validation-runs"}, project_id, ontology_id))

    def test_consumer_request_staging_rejects_extra_producer_material(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            request = root / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "project_id": "00000000-0000-4000-8000-000000000001",
                        "ontology_id": "00000000-0000-4000-8000-000000000002",
                        "business_question": "q",
                    }
                )
            )
            staged = consumer_launcher.stage_inputs(request, root / "staging")
            self.assertEqual(
                staged["staged_files"],
                ["consumer-prompt.md", "consumer-read-query-contract.md", "consumer-request.json", "m3_readonly_rpc.py"],
            )
            prompt = (root / "staging" / "consumer-prompt.md").read_text(encoding="utf-8")
            self.assertIn(consumer_launcher.CONSUMER_PROMPT_PATH, prompt)
            self.assertIn(consumer_launcher.CONSUMER_CONTRACT_PATH, prompt)
            self.assertIn(consumer_launcher.CONSUMER_REQUEST_PATH, prompt)
            self.assertIn(consumer_launcher.CONSUMER_RPC_CLIENT_PATH, prompt)
            command = consumer_launcher.producer.bwrap_command(
                staging=root / "staging",
                workspace=root / "work",
                codex_home=root / "codex-home",
                responses=root / "responses",
                run_tag="m3-consumer-test",
            )
            mount_index = command.index(str(root / "staging"))
            self.assertEqual(command[mount_index + 1], consumer_launcher.CONSUMER_MOUNT_ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            request = Path(temp_dir) / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "project_id": "00000000-0000-4000-8000-000000000001",
                        "ontology_id": "00000000-0000-4000-8000-000000000002",
                        "business_question": "q",
                        "answer": "forbidden",
                    }
                )
            )
            with self.assertRaises(consumer_launcher.ConsumerInputError):
                consumer_launcher.validate_request(request)

    def test_consumer_zero_call_audit_reports_zero_calls_not_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            operation = consumer_launcher.consumer_operation_audit(run_dir)
            receipts = consumer_launcher.consumer_receipt_audit(run_dir, "m3-consumer-test")
            self.assertEqual(operation["errors"], ["consumer made zero RPC calls"])
            self.assertEqual(receipts["errors"], ["consumer made zero RPC calls"])
            self.assertNotIn("invalid consumer gateway audit", " ".join(operation["errors"]))

    def test_consumer_declared_result_uses_completed_agent_message_jsonl_only(self) -> None:
        def event(item_type: str, text: str) -> str:
            return json.dumps({"type": "item.completed", "item": {"type": item_type, "text": text}})

        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "agent-transcript.jsonl"
            transcript.write_text(event("agent_message", "DEVELOPMENT_READY") + "\n", encoding="utf-8")
            self.assertIsNone(consumer_launcher.consumer_agent_result(transcript))
            transcript.write_text(
                event("agent_message", "answer\nCONSUMER_RESULT CONSUMER_READY\nM3_RECEIPT_SUMMARY x") + "\n",
                encoding="utf-8",
            )
            self.assertEqual(consumer_launcher.consumer_agent_result(transcript), "CONSUMER_READY")
            transcript.write_text(event("agent_message", "CONSUMER_RESULT BLOCKED") + "\n", encoding="utf-8")
            self.assertEqual(consumer_launcher.consumer_agent_result(transcript), "BLOCKED")
            transcript.write_text(
                "\n".join(
                    [
                        event("agent_message", "CONSUMER_RESULT CONSUMER_READY"),
                        event("agent_message", "CONSUMER_RESULT BLOCKED"),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(consumer_launcher.consumer_agent_result(transcript))
            transcript.write_text(
                event("command_execution", "CONSUMER_RESULT CONSUMER_READY") + "\n", encoding="utf-8"
            )
            self.assertIsNone(consumer_launcher.consumer_agent_result(transcript))
            transcript.write_text("not-json\n", encoding="utf-8")
            self.assertIsNone(consumer_launcher.consumer_agent_result(transcript))

    def test_consumer_rpc_client_forwards_a_fresh_request_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            work, requests = run_dir / "work", run_dir / "work" / "rpc" / "requests"
            responses, archive = run_dir / "gateway-responses", run_dir / "gateway-request-archive"
            work.mkdir()
            requests.mkdir(parents=True)
            calls: list[dict] = []
            spool = gateway.FileSpoolGateway(
                requests=requests,
                responses=responses,
                archive=archive,
                audit_path=run_dir / "gateway.jsonl",
                api_key="not-a-real-secret",
                upstream=lambda request: (calls.append(request) or (200, {"content-type": "application/json"}, {"ok": True})),
                request_allowed=lambda request: consumer_gateway.consumer_request_allowed(
                    request, "project-1", "ontology-1"
                ),
            )
            stop = threading.Event()

            def serve() -> None:
                while not stop.is_set():
                    spool.process_once()
                    time.sleep(0.005)

            thread = threading.Thread(target=serve)
            thread.start()
            try:
                run_tag = "m3-consumer-test"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(CONSUMER_RPC_CLIENT),
                        "--id",
                        "consumer01",
                        "--method",
                        "GET",
                        "--path",
                        "/api/health",
                        "--receipt-log",
                        str(work / "spool-consumption-receipts.jsonl"),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env={
                        **os.environ,
                        "M3_API_REQUEST_DIR": str(requests),
                        "M3_API_RESPONSE_DIR": str(responses),
                        "M3_RUN_TAG": run_tag,
                    },
                )
            finally:
                stop.set()
                thread.join(timeout=2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [{"id": "consumer01", "method": "GET", "path": "/api/health", "headers": {"accept": "application/json"}, "body": None}])
            receipt_log = work / "spool-consumption-receipts.jsonl"
            receipt = json.loads(receipt_log.read_text(encoding="utf-8"))
            self.assertEqual(receipt["request_id"], "consumer01")
            self.assertEqual(receipt["response_read_confirmed"], True)
            self.assertEqual(json.loads(result.stdout)["id"], "consumer01")
            receipt_log_sha256 = consumer_launcher.producer.sha256(receipt_log)
            summary = (
                f"M3_RECEIPT_SUMMARY run_tag={run_tag} receipt_count=1 "
                f"receipt_log_sha256={receipt_log_sha256}"
            )
            invalid_runtime = {
                "run_tag": run_tag,
                "spool_receipt_log": "spool-consumption-receipts.jsonl",
                "spool_receipts": [receipt],
            }
            runtime_path = work / "runtime-record.json"
            runtime_path.write_text(json.dumps(invalid_runtime), encoding="utf-8")
            (run_dir / "agent-transcript.jsonl").write_text(summary + "\n", encoding="utf-8")
            rejected_audit = consumer_launcher.consumer_receipt_audit(run_dir, run_tag)
            self.assertFalse(rejected_audit["passed"])
            self.assertIn("runtime record receipt log summary differs from Agent receipt log", rejected_audit["errors"])
            finalized = subprocess.run(
                [
                    sys.executable,
                    str(CONSUMER_RPC_CLIENT),
                    "--finalize-runtime-record",
                    "--receipt-log",
                    str(receipt_log),
                    "--runtime-record",
                    str(runtime_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "M3_RUN_TAG": run_tag},
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            self.assertEqual(finalized.stdout.strip(), summary)
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            self.assertEqual(
                runtime["spool_receipt_log"],
                {"path": "spool-consumption-receipts.jsonl", "sha256": receipt_log_sha256, "count": 1},
            )
            self.assertEqual(runtime["spool_receipts"], [receipt])
            (run_dir / "agent-transcript.jsonl").write_text(finalized.stdout, encoding="utf-8")
            self.assertTrue(consumer_launcher.consumer_receipt_audit(run_dir, run_tag)["passed"])
            self.assertTrue(consumer_launcher.consumer_operation_audit(run_dir)["passed"])
            self.assertNotIn('"policy": "rejected"', (run_dir / "gateway.jsonl").read_text(encoding="utf-8"))

    def test_submit_action_uses_public_batch_envelope_without_session_id_extra(self) -> None:
        class StrictBatchApiFixture:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, object]] = []

            def call(self, method: str, path: str, body: object = None):
                self.calls.append((method, path, body))
                if method == "GET":
                    return 200, {"workspace": {"workspace_version": "version-after"}}
                if not isinstance(body, dict) or "session_id" in body:
                    return 422, {"detail": [{"type": "extra_forbidden", "loc": ["body", "session_id"]}]}
                if len([call for call in self.calls if call[0] == "POST"]) == 1:
                    return 200, {"batch_status": "open", "attempt_status": "validated"}
                return 200, {"batch_status": "applied", "attempt_status": "applied"}

        environment = {
            "ontology_id": "00000000-0000-4000-8000-000000000002",
            "session_id": "00000000-0000-4000-8000-000000000003",
            "workspace_version": "version-before",
            "lease_token": "tester-lease",
        }
        api = StrictBatchApiFixture()
        result = mutations.submit_action(api, environment, {"id": "tester-action", "items": []})
        self.assertEqual(result["apply"]["actual"]["attempt_status"], "applied")
        self.assertEqual(environment["workspace_version"], "version-after")
        batch_payloads = [body for method, path, body in api.calls if method == "POST" and path.endswith("/modeling-batches")]
        self.assertEqual(len(batch_payloads), 2)
        self.assertTrue(all("session_id" not in payload for payload in batch_payloads if isinstance(payload, dict)))
        self.assertEqual(
            set(batch_payloads[0]),
            {"client_batch_id", "ontology_id", "idempotency_key", "mode", "expected_workspace_version", "items"},
        )
        self.assertEqual(
            set(batch_payloads[1]),
            {
                "client_batch_id",
                "ontology_id",
                "idempotency_key",
                "mode",
                "expected_workspace_version",
                "lease_token",
                "items",
            },
        )

        class LegacyStatusFixture:
            def call(self, _method: str, _path: str, _body: object = None):
                return 200, {"status": "validated"}

        legacy_result = mutations.submit_action(
            LegacyStatusFixture(), environment, {"id": "legacy-status-action", "items": []}
        )
        self.assertEqual(legacy_result["apply"]["skipped"], "platform dry-run was not validated")

    def test_gateway_policy_rejects_consumer_write_before_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests, responses, archive = root / "requests", root / "responses", root / "archive"
            requests.mkdir()
            calls: list[dict] = []
            spool = gateway.FileSpoolGateway(
                requests=requests,
                responses=responses,
                archive=archive,
                audit_path=root / "audit.jsonl",
                api_key="not-a-real-secret",
                upstream=lambda request: (calls.append(request) or (200, {}, {})),
                request_allowed=lambda _request: False,
            )
            request = {"id": "consumerwrite1", "method": "POST", "path": "/api/projects", "headers": {}, "body": {}}
            (requests / "consumerwrite1.json").write_bytes(gateway.canonical_json(request))
            spool.process_once()
            self.assertEqual(calls, [])
            self.assertIn("gateway operation policy", (root / "audit.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
