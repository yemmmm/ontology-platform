from __future__ import annotations

import copy
import concurrent.futures
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "shared_modeling_directory.py"
SPEC = importlib.util.spec_from_file_location("shared_modeling_directory", MODULE_PATH)
assert SPEC and SPEC.loader
smd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smd)


class SharedModelingDirectoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "sales.md").write_text("Customer places Order.\n", encoding="utf-8")
        (self.repo / "docs" / "support.md").write_text("Ticket has an owner.\n", encoding="utf-8")
        self.run_dir = self.repo / "workspaces" / "modeling-runs" / "run-1"
        self.spec = self._spec()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _spec(self) -> dict:
        return {
            "run_id": "run-1",
            "repository_root": str(self.repo),
            "project_ref": {"project_id": "project-1", "build_session_id": None},
            "brief": "Model customer sales and support with evidence-backed retrieval.",
            "allowed_command_kinds": [
                "create_class",
                "create_entity",
                "create_relation",
                "create_relation_type",
            ],
            "sources": [
                {
                    "source_id": "sales",
                    "locator": "docs/sales.md",
                    "scope": {"ontology_ids": ["sales-ontology"]},
                },
                {
                    "source_id": "support",
                    "locator": "docs/support.md",
                    "scope": {"ontology_ids": ["support-ontology"]},
                },
            ],
            "competency_questions": [
                {
                    "competency_question_id": "cq-sales",
                    "ontology_id": "sales-ontology",
                    "text": "Which customer placed an order?",
                    "acceptance": {"must_return": ["Customer", "Order"]},
                },
                {
                    "competency_question_id": "cq-support",
                    "ontology_id": "support-ontology",
                    "text": "Who owns a ticket?",
                    "acceptance": {"must_return": ["Ticket"]},
                },
            ],
            "coverage_items": [
                {
                    "coverage_id": "coverage-sales",
                    "ontology_id": "sales-ontology",
                    "work_unit_id": "sales-unit",
                    "source_ids": ["sales"],
                    "competency_question_ids": ["cq-sales"],
                    "status": "planned",
                },
                {
                    "coverage_id": "coverage-support",
                    "ontology_id": "support-ontology",
                    "work_unit_id": "support-unit",
                    "source_ids": ["support"],
                    "competency_question_ids": ["cq-support"],
                    "status": "planned",
                },
            ],
            "work_units": [
                {
                    "work_unit_id": "sales-unit",
                    "ontology_id": "sales-ontology",
                    "source_ids": ["sales"],
                    "coverage_ids": ["coverage-sales"],
                    "competency_question_ids": ["cq-sales"],
                    "dependency_work_unit_ids": [],
                    "input_paths": ["shared/brief.md", "docs/sales.md"],
                    "output_contract": {
                        "result_schema": "shared-modeling-result-v1",
                        "allowed_command_kinds": [
                            "create_class",
                            "create_entity",
                            "create_relation",
                            "create_relation_type",
                        ],
                    },
                },
                {
                    "work_unit_id": "support-unit",
                    "ontology_id": "support-ontology",
                    "source_ids": ["support"],
                    "coverage_ids": ["coverage-support"],
                    "competency_question_ids": ["cq-support"],
                    "dependency_work_unit_ids": [],
                    "input_paths": ["shared/brief.md", "docs/support.md"],
                    "output_contract": {
                        "result_schema": "shared-modeling-result-v1",
                        "allowed_command_kinds": ["create_class", "create_entity"],
                    },
                },
            ],
            "ontologies": [
                {"ontology_id": "sales-ontology"},
                {"ontology_id": "support-ontology"},
            ],
        }

    def _initialize(self) -> None:
        smd.initialize_run(self.run_dir, self.spec)

    def _entry(self, unit_id: str) -> dict:
        run = smd._read_json(self.run_dir / "run.json")
        return next(item for item in run["work_units"] if item["work_unit_id"] == unit_id)

    def _ready(self, unit_id: str, items: list[dict], *, terms: list[dict] | None = None) -> dict:
        entry = self._entry(unit_id)
        task = smd._read_json(self.run_dir / entry["task_path"])
        result = {
            "schema_version": smd.SCHEMA_VERSION,
            "work_unit_id": unit_id,
            "ontology_id": entry["ontology_id"],
            "input_fingerprint": smd.compute_unit_input_fingerprint(self.run_dir, unit_id),
            "source_ids": task["source_ids"],
            "coverage_ids": task["coverage_ids"],
            "competency_question_ids": task["competency_question_ids"],
            "modeling_items": items,
            "gaps": [],
            "summary": f"Completed {unit_id}",
            "terms": terms or [],
        }
        smd._atomic_write_json(self.run_dir / entry["result_path"], result)
        smd._atomic_write_json(
            self.run_dir / entry["status_path"],
            {
                "schema_version": smd.SCHEMA_VERSION,
                "work_unit_id": unit_id,
                "ontology_id": entry["ontology_id"],
                "state": "ready",
                "blockers": [],
                "updated_at": "2026-07-22T00:00:00+00:00",
            },
        )
        return result

    @staticmethod
    def _item(
        item_id: str,
        *,
        kind: str = "create_entity",
        depends_on: list[str] | None = None,
        payload: dict | None = None,
        evidence_count: int = 0,
        excerpt: str = "source",
    ) -> dict:
        return {
            "client_item_id": item_id,
            "command_kind": kind,
            "payload": payload or {"name": item_id},
            "depends_on": depends_on or [],
            "evidence_reference_ids": [],
            "evidence": [
                {"document_name": "source.md", "excerpt": excerpt} for _ in range(evidence_count)
            ],
            "rationale": "Required by a competency question",
            "competency_question_ids": ["cq-sales"],
        }

    @staticmethod
    def _attempts() -> list[dict]:
        return [
            {
                "mode": "dry_run",
                "idempotency_key": "dry-attempt",
                "expected_workspace_version": "workspace-v1",
                "lease_token_chars": 0,
            },
            {
                "mode": "apply_atomic",
                "idempotency_key": "apply-attempt",
                "expected_workspace_version": "workspace-v1",
                "lease_token_chars": 64,
            },
        ]

    @staticmethod
    def _limits(**overrides: int) -> dict:
        limits = {
            "modeling_batch_max_items": 100,
            "modeling_batch_max_request_bytes": 1_048_576,
            "modeling_batch_max_inline_evidence": 100,
            "modeling_batch_max_evidence_excerpt_chars": 20_000,
        }
        limits.update(overrides)
        return limits

    def _review(self, ontology_id: str, candidate_hash: str, verdict: str = "PASS") -> None:
        path = self.run_dir / "ontologies" / ontology_id / "review.json"
        smd._atomic_write_json(
            path,
            {
                "schema_version": smd.SCHEMA_VERSION,
                "ontology_id": ontology_id,
                "candidate_hash": candidate_hash,
                "verdict": verdict,
                "findings": [],
            },
        )

    def test_initialize_inspect_validate_and_reject_secret_or_mailbox(self) -> None:
        inspection = smd.initialize_run(self.run_dir, self.spec)
        self.assertTrue(inspection["validation"]["valid"])
        self.assertEqual({item["state"] for item in inspection["units"]}, {"pending"})
        for relative in (
            "run.json",
            "shared/brief.md",
            "shared/source-index.json",
            "shared/coverage.json",
            "units/sales-unit/task.json",
            "units/sales-unit/status.json",
        ):
            self.assertTrue((self.run_dir / relative).is_file(), relative)
        self.assertFalse((self.run_dir / "units/sales-unit/result.json").exists())
        (self.run_dir / "mailbox.json").write_text("{}", encoding="utf-8")
        self.assertFalse(smd.validate_run(self.run_dir)["valid"])
        secret_spec = self._spec()
        secret_spec["api_key"] = "must-not-persist"
        with self.assertRaisesRegex(smd.DirectoryContractError, "forbidden secret"):
            smd.initialize_run(self.repo / "other-run", secret_spec)
        body_spec = self._spec()
        body_spec["sources"][0]["content"] = "full source body must not be copied"
        with self.assertRaisesRegex(smd.DirectoryContractError, "not embed its body"):
            smd.initialize_run(self.repo / "body-run", body_spec)

    def test_local_profile_and_cq_binding_are_fixed_and_non_secret(self) -> None:
        spec = self._spec()
        spec["execution_profile"] = "local"
        smd.initialize_run(self.run_dir, spec)
        result = smd.bind_platform_competency_questions(
            self.run_dir, {"cq-sales": "platform-cq-sales"}
        )
        self.assertEqual(result["competency_question_bindings"]["cq-sales"], "platform-cq-sales")
        smd.bind_local_execution(
            self.run_dir, build_session_id="build-local-1", harness_run_id="run-1"
        )
        report = smd.validate_run(self.run_dir)
        self.assertTrue(report["valid"], report["errors"])
        with self.assertRaisesRegex(smd.DirectoryContractError, "another platform ID"):
            smd.bind_platform_competency_questions(
                self.run_dir, {"cq-sales": "different-platform-cq"}
            )

    def test_local_cq_binding_projects_platform_ids_through_task_candidate_and_batch(self) -> None:
        spec = self._spec()
        spec["execution_profile"] = "local"
        smd.initialize_run(self.run_dir, spec)
        bindings = smd.bind_platform_competency_questions(
            self.run_dir,
            {"cq-support": "platform-cq-support", "cq-sales": "platform-cq-sales"},
        )
        self.assertEqual(
            bindings["competency_question_bindings"],
            {"cq-sales": "platform-cq-sales", "cq-support": "platform-cq-support"},
        )
        coverage = smd._read_json(self.run_dir / "shared/coverage.json")
        sales_question = next(
            item
            for item in coverage["competency_questions"]
            if item["local_competency_question_id"] == "cq-sales"
        )
        self.assertEqual(sales_question["competency_question_id"], "platform-cq-sales")
        self.assertEqual(coverage["items"][0]["competency_question_ids"], ["platform-cq-sales"])
        task = smd._read_json(self.run_dir / "units/sales-unit/task.json")
        self.assertEqual(task["competency_question_ids"], ["platform-cq-sales"])
        item = self._item("platform-cq-item")
        item["competency_question_ids"] = ["platform-cq-sales"]
        result = self._ready("sales-unit", [item])
        self.assertEqual(result["competency_question_ids"], ["platform-cq-sales"])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self.assertEqual(
            candidate["modeling_items"][0]["competency_question_ids"], ["platform-cq-sales"]
        )
        self._review("sales-ontology", candidate["candidate_hash"])
        plan = smd.plan_batches(self.run_dir, "sales-ontology", self._limits(), self._attempts())
        request = smd.materialize_batch(
            self.run_dir,
            "sales-ontology",
            plan["batches"][0]["client_batch_id"],
            self._attempts(),
        )
        serialized = json.dumps(request["items"])
        self.assertIn("platform-cq-sales", serialized)
        self.assertNotIn('"cq-sales"', serialized)

    def test_local_cq_binding_rejects_any_late_modeling_progress(self) -> None:
        spec = self._spec()
        spec["execution_profile"] = "local"
        smd.initialize_run(self.run_dir, spec)
        status_path = self.run_dir / "units/sales-unit/status.json"
        status = smd._read_json(status_path)
        status["state"] = "working"
        smd._atomic_write_json(status_path, status)
        with self.assertRaisesRegex(smd.DirectoryContractError, "binding is too late"):
            smd.bind_platform_competency_questions(self.run_dir, {"cq-sales": "platform-cq-sales"})

    def test_missing_and_cross_scope_references_fail_actionably(self) -> None:
        self._initialize()
        task_path = self.run_dir / "units/sales-unit/task.json"
        task = smd._read_json(task_path)
        task["source_ids"] = ["support"]
        smd._atomic_write_json(task_path, task)
        report = smd.validate_run(self.run_dir)
        self.assertFalse(report["valid"])
        self.assertIn("outside unit sales-unit ontology scope", report["errors"][0])
        (self.run_dir / "shared/brief.md").unlink()
        report = smd.validate_run(self.run_dir)
        self.assertFalse(report["valid"])
        self.assertIn("brief", report["errors"][0])

    def test_reset_only_named_unit_and_dependency_blocks_until_ready(self) -> None:
        spec = self._spec()
        support = spec["work_units"][1]
        support["dependency_work_unit_ids"] = ["sales-unit"]
        smd.initialize_run(self.run_dir, spec)
        self._ready("support-unit", [self._item("ticket")])
        with self.assertRaisesRegex(
            smd.DirectoryContractError, "dependency sales-unit is incomplete"
        ):
            smd.merge_ontology(self.run_dir, "support-ontology")
        sales_result = self._ready("sales-unit", [self._item("customer")])
        support_entry = self._entry("support-unit")
        support_task_path = self.run_dir / support_entry["task_path"]
        support_task = smd._read_json(support_task_path)
        support_task["input_fingerprint"] = smd.compute_unit_input_fingerprint(
            self.run_dir, "support-unit"
        )
        smd._atomic_write_json(support_task_path, support_task)
        self._ready("support-unit", [self._item("ticket")])
        smd.reset_unit(self.run_dir, "sales-unit")
        self.assertFalse((self.run_dir / self._entry("sales-unit")["result_path"]).exists())
        self.assertTrue((self.run_dir / support_entry["result_path"]).exists())
        self.assertEqual(
            smd._read_json(self.run_dir / self._entry("sales-unit")["status_path"])["state"],
            "pending",
        )
        self.assertEqual(sales_result["work_unit_id"], "sales-unit")

    def test_two_independent_workers_write_disjoint_ontology_units(self) -> None:
        self._initialize()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self._ready, "sales-unit", [self._item("customer")]),
                executor.submit(self._ready, "support-unit", [self._item("ticket")]),
            ]
            results = [future.result() for future in futures]
        self.assertEqual(
            {result["work_unit_id"] for result in results}, {"sales-unit", "support-unit"}
        )
        inspection = smd.inspect_run(self.run_dir)
        self.assertEqual({item["state"] for item in inspection["units"]}, {"ready"})
        for unit_id in ("sales-unit", "support-unit"):
            task = smd._read_json(self.run_dir / self._entry(unit_id)["task_path"])
            self.assertTrue(task["input_paths"])
            self.assertTrue(task["output_contract"]["result_schema"])

    def test_stale_result_requires_explicit_semantic_no_change_rebind(self) -> None:
        self._initialize()
        original = self._ready("sales-unit", [self._item("customer")])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        old_hash = candidate["candidate_hash"]
        (self.repo / "docs/sales.md").write_text(
            "Customer places Order. Editorial whitespace changed.\n", encoding="utf-8"
        )
        source_index_path = self.run_dir / "shared/source-index.json"
        source_index = smd._read_json(source_index_path)
        source_index["sources"][0]["content_hash"] = smd.file_hash(self.repo / "docs/sales.md")
        smd._atomic_write_json(source_index_path, source_index)
        report = smd.validate_run(self.run_dir)
        self.assertFalse(report["valid"])
        self.assertIn("stale input fingerprint", report["errors"][0])
        rebound = smd.rebind_no_change(
            self.run_dir,
            "sales-unit",
            copy.deepcopy(original),
            "Source wording changed; the assessed semantic items and gaps are byte-identical.",
        )
        self.assertEqual(rebound["input_rebind"]["decision"], "no_change")
        self.assertTrue(smd.validate_run(self.run_dir)["valid"])
        self.assertEqual(
            smd.merge_ontology(self.run_dir, "sales-ontology")["candidate_hash"], old_hash
        )
        changed = copy.deepcopy(rebound)
        changed["modeling_items"][0]["payload"]["name"] = "Different"
        with self.assertRaisesRegex(smd.DirectoryContractError, "changed normalized semantic"):
            smd.rebind_no_change(self.run_dir, "sales-unit", changed, "Not actually no change")

    def test_candidate_hash_is_canonical_and_review_is_hash_gated(self) -> None:
        self._initialize()
        entity = self._item("entity-b", payload={"label": "B", "entity_id": "entity-b"})
        relation = self._item(
            "relation",
            kind="create_relation",
            depends_on=["entity-b", "entity-a"],
            payload={
                "source": {"item_ref": {"client_item_id": "entity-a", "output": "resource_id"}},
                "target": {"item_ref": {"client_item_id": "entity-b", "output": "resource_id"}},
            },
        )
        entity_a = self._item("entity-a", payload={"entity_id": "entity-a", "label": "A"})
        self._ready("sales-unit", [relation, entity, entity_a])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self.assertEqual(
            [item["client_item_id"] for item in candidate["modeling_items"]],
            ["entity-a", "entity-b", "relation"],
        )
        reordered = copy.deepcopy(candidate)
        reordered["modeling_items"][0]["payload"] = {"label": "A", "entity_id": "entity-a"}
        self.assertEqual(smd.candidate_hash(reordered), candidate["candidate_hash"])
        self._review("sales-ontology", "wrong-hash")
        with self.assertRaisesRegex(smd.DirectoryContractError, "review is stale"):
            smd.validate_review(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        self.assertEqual(smd.validate_review(self.run_dir, "sales-ontology")["verdict"], "PASS")

    def test_merge_rejects_duplicate_ids_conflicts_and_unresolved_refs(self) -> None:
        self._initialize()
        duplicate = [self._item("same"), self._item("same")]
        self._ready("sales-unit", duplicate)
        with self.assertRaisesRegex(smd.DirectoryContractError, "duplicate client_item_id"):
            smd.merge_ontology(self.run_dir, "sales-ontology")
        self._ready(
            "sales-unit",
            [self._item("relation", kind="create_relation", depends_on=["missing"])],
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "unresolved item references"):
            smd.merge_ontology(self.run_dir, "sales-ontology")
        self._ready(
            "sales-unit",
            [self._item("a")],
            terms=[
                {"term": "Customer", "definition": "Buyer"},
                {"term": "customer", "definition": "Support requester"},
            ],
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "conflicting shared terminology"):
            smd.merge_ontology(self.run_dir, "sales-ontology")

    def test_planner_is_deterministic_and_uses_item_and_evidence_limits(self) -> None:
        self._initialize()
        items = [self._item(f"entity-{index}", evidence_count=1) for index in range(5)]
        self._ready("sales-unit", items)
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        limits = self._limits(
            modeling_batch_max_items=2,
            modeling_batch_max_inline_evidence=2,
        )
        first = smd.plan_batches(self.run_dir, "sales-ontology", limits, self._attempts())
        second = smd.plan_batches(self.run_dir, "sales-ontology", limits, self._attempts())
        self.assertEqual(first, second)
        self.assertEqual(
            smd.validate_batch_plan(self.run_dir, "sales-ontology")["candidate_hash"],
            candidate["candidate_hash"],
        )
        self.assertEqual([len(batch["item_ids"]) for batch in first["batches"]], [2, 2, 1])
        evidence_limits = self._limits(
            modeling_batch_max_items=10,
            modeling_batch_max_inline_evidence=1,
        )
        evidence_plan = smd.plan_batches(
            self.run_dir, "sales-ontology", evidence_limits, self._attempts()
        )
        self.assertEqual(len(evidence_plan["batches"]), 5)

    def test_planner_splits_on_serialized_bytes_and_blocks_unsplittable_content(self) -> None:
        self._initialize()
        items = [
            self._item("a", payload={"name": "a" * 80}),
            self._item("b", payload={"name": "b" * 80}),
        ]
        self._ready("sales-unit", items)
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        attempts = self._attempts()
        single_id = smd._client_batch_id(
            "run-1", "sales-ontology", candidate["candidate_hash"], ["a"]
        )
        pair_id = smd._client_batch_id(
            "run-1", "sales-ontology", candidate["candidate_hash"], ["a", "b"]
        )
        single_bytes = max(
            len(
                smd.canonical_json_bytes(
                    smd._request_envelope(
                        "sales-ontology", single_id, [candidate["modeling_items"][0]], attempt
                    )
                )
            )
            for attempt in attempts
        )
        pair_bytes = max(
            len(
                smd.canonical_json_bytes(
                    smd._request_envelope(
                        "sales-ontology", pair_id, candidate["modeling_items"], attempt
                    )
                )
            )
            for attempt in attempts
        )
        self.assertGreater(pair_bytes, single_bytes)
        plan = smd.plan_batches(
            self.run_dir,
            "sales-ontology",
            self._limits(modeling_batch_max_request_bytes=single_bytes + 5),
            attempts,
        )
        self.assertEqual(len(plan["batches"]), 2)
        with self.assertRaisesRegex(smd.CapacityError, "cannot fit"):
            smd.plan_batches(
                self.run_dir,
                "sales-ontology",
                self._limits(modeling_batch_max_request_bytes=single_bytes - 1),
                attempts,
            )
        overlong = self._item("too-long", evidence_count=1, excerpt="x" * 11)
        self._ready("sales-unit", [overlong])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        with self.assertRaisesRegex(smd.CapacityError, "excerpt length"):
            smd.plan_batches(
                self.run_dir,
                "sales-ontology",
                self._limits(modeling_batch_max_evidence_excerpt_chars=10),
                attempts,
            )

    def test_cross_batch_materialization_and_platform_identity_binding(self) -> None:
        self._initialize()
        entity = self._item("customer", payload={"name": "Customer"})
        relation = self._item(
            "customer-order",
            kind="create_relation",
            depends_on=["customer"],
            payload={
                "source_entity_id": {
                    "item_ref": {"client_item_id": "customer", "output": "resource_id"}
                },
                "target_entity_id": "existing-order-id",
            },
        )
        self._ready("sales-unit", [relation, entity])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        plan = smd.plan_batches(
            self.run_dir,
            "sales-ontology",
            self._limits(modeling_batch_max_items=1),
            self._attempts(),
        )
        first, second = plan["batches"]
        first_request = smd.materialize_batch(
            self.run_dir, "sales-ontology", first["client_batch_id"], self._attempts()
        )
        same_identity = smd.materialize_batch(
            self.run_dir,
            "sales-ontology",
            first["client_batch_id"],
            [
                {
                    "mode": "dry_run",
                    "idempotency_key": "different-dry",
                    "expected_workspace_version": "w2",
                },
                {
                    "mode": "apply_atomic",
                    "idempotency_key": "different-apply",
                    "expected_workspace_version": "w2",
                },
            ],
        )
        self.assertEqual(
            first_request["immutable_content_hash"], same_identity["immutable_content_hash"]
        )
        dry_response = {
            "client_batch_id": first["client_batch_id"],
            "batch_id": "platform-batch-1",
            "attempt_status": "validated",
        }
        smd.bind_platform_response(
            self.run_dir,
            "sales-ontology",
            first["client_batch_id"],
            "dry_run",
            first_request["immutable_content_hash"],
            dry_response,
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "submitted immutable Batches"):
            smd.plan_batches(
                self.run_dir,
                "sales-ontology",
                self._limits(modeling_batch_max_items=1),
                self._attempts(),
            )
        with self.assertRaisesRegex(smd.DirectoryContractError, "different platform batch_id"):
            smd.bind_platform_response(
                self.run_dir,
                "sales-ontology",
                first["client_batch_id"],
                "apply_atomic",
                first_request["immutable_content_hash"],
                {"batch_id": "wrong-batch", "attempt_status": "applied", "items": []},
            )
        smd.bind_platform_response(
            self.run_dir,
            "sales-ontology",
            first["client_batch_id"],
            "apply_atomic",
            first_request["immutable_content_hash"],
            {
                "client_batch_id": first["client_batch_id"],
                "batch_id": "platform-batch-1",
                "attempt_status": "applied",
                "items": [
                    {
                        "client_item_id": "customer",
                        "resource_outputs": {
                            "resource_id": "stable-customer-id",
                            "resource_iri": "https://example.test/customer",
                        },
                    }
                ],
            },
            context_refreshed=True,
        )
        second_request = smd.materialize_batch(
            self.run_dir, "sales-ontology", second["client_batch_id"], self._attempts()
        )
        relation_item = second_request["items"][0]
        self.assertEqual(relation_item["depends_on"], [])
        self.assertEqual(relation_item["payload"]["source_entity_id"], "stable-customer-id")
        self.assertNotIn("item_ref", json.dumps(relation_item))

    def test_materialization_repartitions_only_unsubmitted_oversized_batch(self) -> None:
        self._initialize()
        entity = self._item("a-entity")
        filler = self._item("b-filler")
        relations = [
            self._item(
                f"z-relation-{index}",
                kind="create_relation",
                depends_on=["a-entity"],
                payload={
                    "source": {
                        "item_ref": {
                            "client_item_id": "a-entity",
                            "output": "resource_iri",
                        }
                    },
                    "target": f"target-{index}",
                },
            )
            for index in range(2)
        ]
        self._ready("sales-unit", relations + [filler, entity])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        initial = smd.plan_batches(
            self.run_dir,
            "sales-ontology",
            self._limits(modeling_batch_max_items=2),
            self._attempts(),
        )
        first, second = initial["batches"]
        unresolved_pair = [
            item
            for item in candidate["modeling_items"]
            if item["client_item_id"] in second["item_ids"]
        ]
        logical_bytes = max(
            len(
                smd.canonical_json_bytes(
                    smd._request_envelope(
                        "sales-ontology", second["client_batch_id"], unresolved_pair, attempt
                    )
                )
            )
            for attempt in self._attempts()
        )
        limits = self._limits(
            modeling_batch_max_items=2,
            modeling_batch_max_request_bytes=logical_bytes + 40,
        )
        plan = smd.plan_batches(self.run_dir, "sales-ontology", limits, self._attempts())
        first, second = plan["batches"]
        request = smd.materialize_batch(
            self.run_dir, "sales-ontology", first["client_batch_id"], self._attempts()
        )
        for mode, status in (("dry_run", "validated"), ("apply_atomic", "applied")):
            smd.bind_platform_response(
                self.run_dir,
                "sales-ontology",
                first["client_batch_id"],
                mode,
                request["immutable_content_hash"],
                {
                    "batch_id": "platform-first",
                    "attempt_status": status,
                    "items": [
                        {
                            "client_item_id": item_id,
                            "resource_outputs": {
                                "resource_id": f"id:{item_id}",
                                "resource_iri": "https://example.test/" + "x" * 220,
                            },
                        }
                        for item_id in first["item_ids"]
                    ],
                },
                context_refreshed=mode == "apply_atomic",
            )
        replacement = smd.materialize_batch(
            self.run_dir, "sales-ontology", second["client_batch_id"], self._attempts()
        )
        self.assertEqual(
            replacement["replaced_unsubmitted_client_batch_id"], second["client_batch_id"]
        )
        replaced_plan = smd._read_json(self.run_dir / "ontologies/sales-ontology/batch-plan.json")
        self.assertEqual(replaced_plan["batches"][0]["state"], "applied")
        self.assertEqual(replaced_plan["batches"][0]["client_batch_id"], first["client_batch_id"])
        self.assertEqual(len(replaced_plan["batches"]), 3)

    def test_hundreds_of_items_complete_ordered_simulated_batch_binding(self) -> None:
        self._initialize()
        entities = [self._item(f"entity-{index:03d}") for index in range(205)]
        relations = [
            self._item(
                f"relation-{index:03d}",
                kind="create_relation",
                depends_on=[f"entity-{index:03d}", f"entity-{index + 1:03d}"],
                payload={
                    "source": {
                        "item_ref": {
                            "client_item_id": f"entity-{index:03d}",
                            "output": "resource_iri",
                        }
                    },
                    "target": {
                        "item_ref": {
                            "client_item_id": f"entity-{index + 1:03d}",
                            "output": "resource_iri",
                        }
                    },
                },
            )
            for index in range(5)
        ]
        self._ready("sales-unit", relations + list(reversed(entities)))
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        plan = smd.plan_batches(
            self.run_dir,
            "sales-ontology",
            self._limits(modeling_batch_max_items=100),
            self._attempts(),
        )
        self.assertEqual([len(batch["item_ids"]) for batch in plan["batches"]], [100, 100, 10])
        for index, batch in enumerate(plan["batches"]):
            request = smd.materialize_batch(
                self.run_dir, "sales-ontology", batch["client_batch_id"], self._attempts()
            )
            platform_id = f"platform-{index}"
            smd.bind_platform_response(
                self.run_dir,
                "sales-ontology",
                batch["client_batch_id"],
                "dry_run",
                request["immutable_content_hash"],
                {"batch_id": platform_id, "attempt_status": "validated"},
            )
            smd.bind_platform_response(
                self.run_dir,
                "sales-ontology",
                batch["client_batch_id"],
                "apply_atomic",
                request["immutable_content_hash"],
                {
                    "batch_id": platform_id,
                    "attempt_status": "applied",
                    "items": [
                        {
                            "client_item_id": item_id,
                            "resource_outputs": {
                                "resource_id": f"id:{item_id}",
                                "resource_iri": f"https://example.test/{item_id}",
                            },
                        }
                        for item_id in batch["item_ids"]
                    ],
                },
                context_refreshed=True,
            )
        applied = smd._read_json(self.run_dir / "ontologies/sales-ontology/batch-plan.json")
        self.assertTrue(all(batch["state"] == "applied" for batch in applied["batches"]))

    def test_verification_binds_candidate_batches_and_all_questions(self) -> None:
        self._initialize()
        self._ready("sales-unit", [self._item("customer")])
        candidate = smd.merge_ontology(self.run_dir, "sales-ontology")
        self._review("sales-ontology", candidate["candidate_hash"])
        plan = smd.plan_batches(self.run_dir, "sales-ontology", self._limits(), self._attempts())
        batch = plan["batches"][0]
        request = smd.materialize_batch(
            self.run_dir, "sales-ontology", batch["client_batch_id"], self._attempts()
        )
        for mode, status in (("dry_run", "validated"), ("apply_atomic", "applied")):
            smd.bind_platform_response(
                self.run_dir,
                "sales-ontology",
                batch["client_batch_id"],
                mode,
                request["immutable_content_hash"],
                {
                    "batch_id": "platform-batch",
                    "attempt_status": status,
                    "items": [
                        {
                            "client_item_id": "customer",
                            "resource_outputs": {"resource_id": "customer-id"},
                        }
                    ],
                },
                context_refreshed=mode == "apply_atomic",
            )
        verification = {
            "schema_version": smd.SCHEMA_VERSION,
            "ontology_id": "sales-ontology",
            "candidate_hash": candidate["candidate_hash"],
            "batches": [
                {
                    "client_batch_id": batch["client_batch_id"],
                    "platform_batch_id": "platform-batch",
                    "immutable_content_hash": request["immutable_content_hash"],
                }
            ],
            "checks": [
                {
                    "competency_question_id": "cq-sales",
                    "status": "passed",
                    "query": "context query for customer order",
                    "returned_resources": ["customer-id"],
                }
            ],
            "gaps": [],
            "verdict": "PASS",
        }
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", verification
        )
        self.assertEqual(
            smd.validate_verification(self.run_dir, "sales-ontology")["verdict"], "PASS"
        )

        missing_evidence = copy.deepcopy(verification)
        missing_evidence["checks"] = [{"competency_question_id": "cq-sales", "status": "passed"}]
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", missing_evidence
        )
        with self.assertRaisesRegex(
            smd.DirectoryContractError, "lacks an executed query/check description"
        ):
            smd.validate_verification(self.run_dir, "sales-ontology")

        missing_result = copy.deepcopy(verification)
        missing_result["checks"][0].pop("returned_resources")
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", missing_result
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "lacks structured result evidence"):
            smd.validate_verification(self.run_dir, "sales-ontology")

        malformed_evidence = copy.deepcopy(verification)
        malformed_evidence["checks"][0]["returned_resources"] = {"resource_id": "customer-id"}
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", malformed_evidence
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "must be a structured result list"):
            smd.validate_verification(self.run_dir, "sales-ontology")

        explicit_empty = copy.deepcopy(verification)
        explicit_empty["checks"] = [
            {
                "competency_question_id": "cq-sales",
                "status": "passed",
                "check_description": "Confirm no deprecated customer resource is returned.",
                "returned_resources": [],
                "empty_result": {
                    "expected": True,
                    "observed_count": 0,
                    "assertion": "The competency question expects no deprecated resource.",
                },
            }
        ]
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", explicit_empty
        )
        self.assertEqual(
            smd.validate_verification(self.run_dir, "sales-ontology")["verdict"], "PASS"
        )

        malformed_empty = copy.deepcopy(explicit_empty)
        malformed_empty["checks"][0]["empty_result"]["observed_count"] = 1
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", malformed_empty
        )
        with self.assertRaisesRegex(
            smd.DirectoryContractError, "expected=true and observed_count=0"
        ):
            smd.validate_verification(self.run_dir, "sales-ontology")

        verification["checks"] = []
        smd._atomic_write_json(
            self.run_dir / "ontologies/sales-ontology/verification.json", verification
        )
        with self.assertRaisesRegex(smd.DirectoryContractError, "every competency question"):
            smd.validate_verification(self.run_dir, "sales-ontology")


if __name__ == "__main__":
    unittest.main()
