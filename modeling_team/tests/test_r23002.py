from __future__ import annotations

import json
import sys
import tempfile
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modeling_team import __main__ as team_main
from modeling_team.contracts import (
    SAFE_PROTOCOL_TOOLS,
    TeamConfigurationError,
    digest_file,
    load_task,
    load_team_configuration,
    repository_root,
)
from modeling_team.handoff import HANDOFF_FIELDS, publish_offline_scope_handoff, publish_scope_handoff
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_receipt,
    translate_candidate_to_batches,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.start_ledger import StartLedger


class R23002Tests(unittest.TestCase):
    @staticmethod
    def _ledger(path: Path, now: datetime | None = None) -> StartLedger:
        clock = now or datetime(2026, 7, 31, 10, 0, tzinfo=UTC)
        return StartLedger(path, now=lambda: clock)

    def test_v1_task_regression_and_v2_role_private_contract(self) -> None:
        root = repository_root()
        v1 = load_task(root / "modeling_team/tasks/base-capability-smoke.yaml", root=root)
        v2 = load_task(root / "modeling_team/tasks/new-scope-business-slice.yaml", root=root)
        self.assertEqual(v1.schema_version, 1)
        self.assertEqual(v1.protocol_tools, ())
        self.assertEqual(v2.schema_version, 2)
        self.assertTrue(v2.retain_nonempty)
        self.assertTrue(v2.protocol_tools)
        self.assertEqual(set(v2.protocol_tools), SAFE_PROTOCOL_TOOLS)
        self.assertIn("save_build_checkpoint", v2.protocol_tools)
        self.assertTrue(all("tester-only" not in item.path.as_posix() for item in v2.role_sources))
        self.assertEqual(
            {item.relative_path.as_posix() for item in v2.role_sources if "protocol" in item.roles},
            {
                "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/public-protocol.md",
                "modeling_team/references/modeling-batch-item-contract.json",
            },
        )

    def test_protocol_batch_item_reference_matches_handler_and_mcp_envelopes(self) -> None:
        from app.api.schemas import ModelingBatchSubmit
        from app.mcp.tools.modeling_batches import McpModelingItemInput
        from app.core.config import Settings
        from app.services.modeling_handlers import ALLOWED_FIELDS, FORBIDDEN_TARGET_FIELDS, ModelingCommandHandlerRegistry
        from app.services.semantic_command_compiler import InvalidCommandPayload
        from app.services.modeling_batches import ModelingBatchError, ModelingBatchService

        root = repository_root()
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(encoding="utf-8")
        )
        required_commands = {
            "create_class", "create_property", "create_relation_type", "create_entity", "create_relation", "create_operation",
            "create_table_mapping", "create_join_mapping", "create_enum_meaning", "create_metric_definition",
        }
        self.assertEqual(set(reference["create_payloads"]), required_commands)
        self.assertEqual(
            {name: set(value["fields"]) for name, value in reference["create_payloads"].items()},
            {name: ALLOWED_FIELDS[name] for name in required_commands},
        )
        self.assertEqual(set(reference["forbidden_target_fields"]), FORBIDDEN_TARGET_FIELDS)
        self.assertEqual(
            set(reference["item_envelope"]["fields"]),
            set(McpModelingItemInput.model_fields),
        )
        self.assertEqual(
            set(reference["batch_envelope"]["fields"]) - {"session_id"},
            set(ModelingBatchSubmit.model_fields) - {"actor"},
        )
        property_contract = reference["create_payloads"]["create_property"]
        self.assertEqual(property_contract["required"], ["name"])
        self.assertEqual(property_contract["at_most_one_required"], ["datatype", "object_class_id"])
        self.assertEqual(property_contract["fields"]["datatype"]["type"], "string")
        self.assertIn("mutually exclusive", property_contract["fields"]["object_class_id"]["branch"])
        self.assertEqual(reference["create_payloads"]["create_entity"]["fields"]["properties"]["type"], "object")
        self.assertTrue(all(
            field["format"] == "absolute-rdf-iri"
            for field in reference["create_payloads"]["create_relation"]["fields"].values()
        ))

        registry = ModelingCommandHandlerRegistry(Settings())
        # R3.0-009 §4.3: the approved domain and the ObjectProperty range are
        # optional; a datatype property still carries its real datatype.
        constraint_free_property = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="property-free", command_kind="create_property",
            payload={"name": "property"},
        )
        self.assertTrue(constraint_free_property.compiled.metadata["is_object_property"])
        self.assertTrue(constraint_free_property.compiled)
        with self.assertRaisesRegex(InvalidCommandPayload, "not both"):
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="property-both", command_kind="create_property",
                payload={"name": "property", "datatype": "xsd:string", "object_class_id": "target"},
            )
        ranged_property = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="property-ranged", command_kind="create_property",
            payload={"class_id": "class", "name": "property", "object_class_id": "target"},
        )
        self.assertTrue(ranged_property.compiled.metadata["is_object_property"])
        typed_property = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="property-typed", command_kind="create_property",
            payload={"name": "property", "datatype": "xsd:string"},
        )
        self.assertFalse(typed_property.compiled.metadata["is_object_property"])
        with self.assertRaisesRegex(InvalidCommandPayload, "absolute RDF IRI"):
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="relation", command_kind="create_relation",
                payload={"source_entity_iri": "relative", "relation_type_iri": "https://example.test/relation", "target_entity_iri": "https://example.test/target"},
            )
        self.assertIn("MUST send a string", property_contract["fields"]["name"]["server_current_acceptance"])
        self.assertTrue(
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="class-number", command_kind="create_class",
                payload={"name": 7},
            ).compiled
        )

        class Session:
            def __init__(self) -> None:
                self.values = iter([
                    "project",
                    SimpleNamespace(status="active", project_id="project"),
                    SimpleNamespace(project_id="project"),
                ])

            def scalar(self, _statement):
                return next(self.values)

            def scalars(self, _statement):
                return []

        def batch(mode: str, lease_token: str | None) -> ModelingBatchSubmit:
            return ModelingBatchSubmit(
                client_batch_id="batch", ontology_id="ontology", idempotency_key=f"{mode}-{lease_token}",
                expected_workspace_version="version", mode=mode, lease_token=lease_token,
                items=[{"client_item_id": "item", "command_kind": "create_class", "payload": {"name": "name"}}],
            )

        with self.assertRaisesRegex(ModelingBatchError, "dry_run must omit lease_token"):
            ModelingBatchService(Session(), Settings()).submit("session", batch("dry_run", "lease"))
        with self.assertRaisesRegex(ModelingBatchError, "apply requires lease_token"):
            ModelingBatchService(Session(), Settings()).submit("session", batch("apply_atomic", None))
        lease_invariants = reference["batch_envelope"]["fields"]["lease_token"]["invariants"]
        self.assertEqual(lease_invariants["dry_run"], "MUST be omitted or null")
        self.assertIn("non-empty string", lease_invariants["apply_atomic"])


    def test_property_identity_stays_receipt_bound_without_shape_contract(self) -> None:
        from app.core.config import Settings
        from app.services.modeling_handlers import ModelingCommandHandlerRegistry
        reference = json.loads((repository_root() / "modeling_team/references/modeling-batch-item-contract.json").read_text())
        self.assertNotIn("object_property_shape_relation_binding", reference)
        registry = ModelingCommandHandlerRegistry(Settings())
        prepared = registry.prepare(batch_id="b", ontology_id="o", client_item_id="p",
                                    command_kind="create_property",
                                    payload={"property_id": "hasObject", "name": "hasObject", "object_class_id": "Object"})
        self.assertTrue(prepared.compiled.metadata["is_object_property"])
        self.assertEqual(prepared.outputs["resource_id"], "hasObject")


    def test_protocol_task_text_gets_scope_context_but_other_roles_do_not(self) -> None:
        root = repository_root()
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(
            configuration=load_team_configuration(
                root / "modeling_team/profiles/base-three-agent.yaml",
                root / "modeling_team/tasks/new-scope-business-slice.yaml",
                root=root,
            ),
            protocol_context={"project_id": "project-1", "ontology_id": "ontology-1", "workspace_version": "v1"},
        )
        protocol = runner._task_text("protocol")
        self.assertIn('"project_id": "project-1"', protocol)
        self.assertIn('"workspace_version": "v1"', protocol)
        self.assertNotIn("project-1", runner._task_text("coordinator"))
        self.assertNotIn("ontology-1", runner._task_text("modeling"))
        self.assertNotIn("admin", protocol.lower())
        self.assertNotIn("secret", protocol.lower())
        self.assertIn("dependency rejection is not recorded", runner._task_text("coordinator"))
        self.assertIn("reply_to_delivery_id set to the current Modeling question delivery_id", runner._task_text("coordinator"))
        coordinator_instructions = (root / "modeling_team/agent-packages/coordinator/instructions.md").read_text()
        self.assertIn("that rejection is not recorded", coordinator_instructions)
        self.assertIn("reply_to_delivery_id", coordinator_instructions)

    def test_v2_task_text_enumerates_only_each_role_staged_sources_and_declares_ownership(self) -> None:
        root = repository_root()
        configuration = load_team_configuration(
            root / "modeling_team/profiles/base-three-agent.yaml",
            root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        all_paths = {
            f"/agent/home/sources/{source.relative_path.as_posix()}" for source in configuration.task.role_sources
        }
        for role in ("coordinator", "modeling", "protocol"):
            with self.subTest(role=role):
                text = runner._task_text(role)
                expected = sorted(
                    f"/agent/home/sources/{source.relative_path.as_posix()}"
                    for source in configuration.task.role_sources
                    if role in source.roles
                )
                self.assertIn("Before requesting any teammate work or reporting a terminal result, read every staged", text)
                self.assertEqual([text.index(path) for path in expected], sorted(text.index(path) for path in expected))
                for path in expected:
                    self.assertEqual(text.count(path), 1)
                for path in all_paths - set(expected):
                    self.assertNotIn(path, text)
                self.assertNotIn("/agent/home/sources/tester-only", text)
                self.assertNotIn("/home/yangxiang/", text)

        protocol = runner._task_text("protocol")
        self.assertIn("items as Array<unknown>", protocol)
        self.assertIn("platform-general nested construction contract", protocol)
        self.assertIn("Protocol alone translates", protocol)
        self.assertIn("must not require Modeling to author exact items", protocol)
        self.assertIn("reply_to_delivery_id", protocol)
        self.assertIn("Runner delivers Modeling's terminal-handoff", protocol)
        self.assertIn("/opt/mechanics-contract.json", protocol)
        self.assertIn("initial_checkpoint omitted or null", protocol)
        self.assertIn("mandatory initial checkpoint before lease acquisition", protocol)
        self.assertIn("reread the Session before saving the mandatory final", protocol)
        self.assertIn("completed Session", protocol)
        self.assertIn("exact receipt bindings and checkpoint fields", protocol)
        modeling_task = runner._task_text("modeling")
        self.assertIn("expects_reply=true", modeling_task)
        self.assertIn("returned delivery_id", modeling_task)
        self.assertIn("if you cannot revise", modeling_task)
        self.assertIn(
            "Do not create a reply request solely to unlock a terminal result", modeling_task
        )
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertIn("modeling-batch-item-contract.json", protocol_instructions)
        self.assertIn("Array<unknown>", protocol_instructions)
        self.assertIn("platform-general nested construction contract", protocol_instructions)
        self.assertIn("Do not require Modeling to author", protocol_instructions)
        self.assertIn("reply_to_delivery_id", protocol_instructions)
        self.assertIn("terminal-handoff", protocol_instructions)
        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertIn("structured platform-neutral semantic candidate", modeling_instructions)
        self.assertIn("classes,\nproperties, relations, entities, explicit unknowns, and dependencies", modeling_instructions)
        self.assertIn("do not author exact platform\nitems", modeling_instructions)
        self.assertIn("Protocol mechanically translates", modeling_instructions)
        self.assertIn("expects_reply=true", modeling_instructions)
        self.assertIn("delivered conflict's `delivery_id`", modeling_instructions)
        self.assertIn(
            "do not create a reply request solely to unlock a terminal result",
            modeling_instructions,
        )
        task_objective = configuration.task.objective
        self.assertIn("grounded Tool-binding question", task_objective)
        self.assertIn("outer answer", task_objective)
        self.assertIn("explicit_unknown", task_objective)
        self.assertNotIn("Version 2", task_objective)

    def test_cross_batch_contract_is_protocol_private_and_baseline_bound(self) -> None:
        root = repository_root()
        reference_path = root / "modeling_team/references/modeling-batch-item-contract.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        contract = reference["cross_batch_application_contract"]
        self.assertEqual(
            contract["stage_order"],
            [
                "class",
                "property_or_relation_type",
                "entity",
                "receipt_or_read_bind_generated_identifiers",
                "relation",
            ],
        )
        self.assertEqual(
            contract["ordered_schedule"],
            "class -> property/relation type -> entity -> receipt/read bind generated IDs/IRIs -> "
            "relation",
        )
        self.assertEqual(
            contract["applied_stages"]["class"]["command_kinds"], ["create_class"]
        )
        self.assertEqual(
            contract["applied_stages"]["property_or_relation_type"]["command_kinds"],
            ["create_property", "create_relation_type"],
        )
        self.assertEqual(
            contract["applied_stages"]["entity"]["command_kinds"], ["create_entity", "create_operation"]
        )
        self.assertEqual(
            contract["applied_stages"]["relation"]["command_kinds"], ["create_relation"]
        )
        self.assertTrue(
            all(
                stage["execution"] == "independent dry_run then apply_atomic"
                for stage in contract["applied_stages"].values()
            )
        )
        self.assertIn("formal apply receipt or required platform read", contract["formal_binding"]["workspace_version"])
        self.assertIn("never guess, synthesize, or forward-reference", contract["formal_binding"]["generated_identifiers"])
        self.assertIn("must not mutate candidate meaning or reorder candidate semantics", contract["candidate_invariant"])
        self.assertEqual(
            contract["forbidden"],
            [
                "unbound forward reference",
                "semantic candidate mutation or reordering",
                "weaken validation",
                "delegate exact Batch Items to Modeling",
            ],
        )
        self.assertIn("before the dangerous write", contract["binding_conflict"])

        configuration = load_team_configuration(
            root / "modeling_team/profiles/base-three-agent.yaml",
            root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=root,
        )
        contract_source = next(
            source
            for source in configuration.task.role_sources
            if source.path == reference_path
        )
        self.assertEqual(contract_source.roles, frozenset({"protocol"}))
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        staged_path = "/agent/home/sources/modeling_team/references/modeling-batch-item-contract.json"
        self.assertIn(staged_path, runner._task_text("protocol"))
        self.assertNotIn(staged_path, runner._task_text("coordinator"))
        self.assertNotIn(staged_path, runner._task_text("modeling"))
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "receipt/read binding of generated IDs/IRIs",
            "dry_run` followed immediately by\nits `apply_atomic`",
            "with the plan's `apply_idempotency_key`",
            "trailing `-vN` incremented (`v1` -> `v2`)",
            "must not mutate or reorder candidate meaning",
            "unbound forward reference",
            "delegate exact Batch Items back to Modeling",
        ):
            self.assertIn(phrase, protocol_instructions)
        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("receipt/read binding of generated IDs/IRIs", modeling_instructions)

        baseline, _baseline_hash = TeamRunner.preview_baseline(
            repository_root=root,
            run_id=f"r23002-cross-batch-{uuid4().hex}",
            profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
        )
        self.assertEqual(
            baseline["files"]["source:modeling_team/references/modeling-batch-item-contract.json"],
            digest_file(reference_path),
        )
        v1 = load_task(root / "modeling_team/tasks/base-capability-smoke.yaml", root=root)
        self.assertNotIn(reference_path, v1.allowed_sources)

    def test_retired_semantic_validation_contract_is_not_mounted(self) -> None:
        reference = json.loads((repository_root() / "modeling_team/references/modeling-batch-item-contract.json").read_text())
        self.assertNotIn("semantic_validation_invocation_contract", reference)
        self.assertNotIn("shape_constraint", reference)


    def test_attempt_fourteen_material_gap_and_retrieval_fallback_contract(self) -> None:
        root = repository_root()
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(encoding="utf-8")
        )
        retrieval = reference["semantic_retrieval_completion_contract"]
        self.assertIn("no business semantics or source-tracing payload", retrieval["purpose"])
        self.assertEqual(
            retrieval["successful_receipt_requires"],
            [
                "ontology-scoped generic query",
                "no truncation",
                "no cross-ontology fact",
                "predicate/value and identity binding",
                "successful continuation whenever paging is required",
            ],
        )
        self.assertIn("ordinary scoped readback path", retrieval["fallback"]["allowed"])
        self.assertIn("exact predicate/value and scope checks", retrieval["fallback"]["readback"])
        self.assertNotIn("deterministic_helper", retrieval["fallback"])
        self.assertNotIn("C -> B -> A", json.dumps(retrieval))
        self.assertNotIn("quality_rating", json.dumps(retrieval))

        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "visible sources and consumer questions",
            "one grounded plain question at a\ntime",
            "reassess every remaining material gap",
            "tester answer set, answer count, scenario target, or expected ontology",
            "otherwise\nincomplete semantic retrieval as a conflict",
        ):
            self.assertIn(phrase, modeling_instructions)
        self.assertNotIn("C -> B -> A", modeling_instructions)
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Accept the source-neutral platform candidate",
            "Do not require assertion matrices, proof-only envelopes, source attachments or a fallback verifier.",
            "normal result without retired tracing metadata still passes",
            "complete,\nnon-degraded statement result",
        ):
            self.assertIn(phrase, protocol_instructions)
        self.assertNotIn("verify_scoped_retrieval_fallback", protocol_instructions)
        self.assertNotIn("write_candidate_item_evidence_map", protocol_instructions)

        task_text = (root / "modeling_team/tasks/new-scope-business-slice.yaml").read_text(encoding="utf-8")
        self.assertIn("Before freezing a candidate", task_text)

        configuration = load_team_configuration(
            root / "modeling_team/profiles/base-three-agent.yaml",
            root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        self.assertIn("material gaps", runner._task_text("modeling"))
        self.assertIn("retrieval-completeness conflict", runner._task_text("protocol"))
        staged_reference = "/agent/home/sources/modeling_team/references/modeling-batch-item-contract.json"
        self.assertNotIn(staged_reference, runner._task_text("coordinator"))
        self.assertNotIn(staged_reference, runner._task_text("modeling"))

        candidate = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": "r23002-candidate-1",
            "scope": {"ontology": "ontology-1"},
            "constraints": ["source-grounded", "scope-correct"],
            "items": [
                {
                    "item_id": "class-1",
                    "item_kind": "class",
                    "semantic": {
                        "class_id": "Entity",
                        "name": "Entity",
                        "description": "A semantic entity.",
                    },
                }
            ],
        }
        receipt = build_candidate_receipt(candidate)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["candidate_revision"], candidate["candidate_revision"])
        self.assertEqual(
            set(receipt),
            {"status", "candidate_revision", "semantic_digest", "candidate_digest"},
        )
        plan = translate_candidate_to_batches(candidate)
        self.assertEqual([batch["stage_kind"] for batch in plan["batches"]], ["class"])
        self.assertEqual(plan["batches"][0]["items"][0]["client_item_id"], "class-1")

        source_trace_candidate = json.loads(json.dumps(candidate))
        source_trace_candidate["items"][0]["evidence_citations"] = [{"document": "source.md"}]
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "unsupported fields"):
            build_candidate_receipt(source_trace_candidate)

        unsupported_candidate_field = json.loads(json.dumps(candidate))
        unsupported_candidate_field["candidate_required_assertions"] = {}
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "unsupported fields"):
            build_candidate_receipt(unsupported_candidate_field)

    def test_v1_task_text_remains_unchanged(self) -> None:
        root = repository_root()
        configuration = load_team_configuration(
            root / "modeling_team/profiles/base-three-agent.yaml",
            root / "modeling_team/tasks/base-capability-smoke.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration)
        expected = (
            configuration.task.objective
            + "\nAllowed sources: "
            + ", ".join(
                f"/agent/home/sources/{path.name}" for path in configuration.task.allowed_sources
            )
            + "\nUse Team Transport for direct messages and call report_task_result exactly once before ending. "
            + "Protocol must call check_platform_health once; do not call another platform tool."
        )
        self.assertEqual(runner._task_text("modeling"), expected)

    def test_v2_rejects_forbidden_source_and_tool(self) -> None:
        root = repository_root()
        task = (root / "modeling_team/tasks/new-scope-business-slice.yaml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "bad.yaml"
            candidate.write_text(task.replace("check_platform_health", "create_api_key", 1), encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "Protocol tool"):
                load_task(candidate, root=root)
            candidate.write_text(
                task.replace(
                    "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/public-protocol.md",
                    "docs/evaluation-scenarios/ontology-modeling-team-l3/tester-only/answer-contract.json",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(TeamConfigurationError, "not Agent-visible"):
                load_task(candidate, root=root)
            candidate.write_text(task.replace("roles: [protocol]", "roles: [source-specialist]", 1), encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "source roles"):
                load_team_configuration(
                    root / "modeling_team/profiles/base-three-agent.yaml", candidate, root=root
                )
            link = root / "modeling_team/tests/r23002-source-link"
            link.unlink(missing_ok=True)
            link.symlink_to(
                root
                / "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/public-protocol.md"
            )
            try:
                candidate.write_text(
                    task.replace(
                        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/public-protocol.md",
                        "modeling_team/tests/r23002-source-link",
                        1,
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(TeamConfigurationError, "unavailable"):
                    load_task(candidate, root=root)
            finally:
                link.unlink(missing_ok=True)

    def test_runner_stages_relative_role_sources_and_baseline(self) -> None:
        root = repository_root()
        run_id = f"r23002-stage-{uuid4().hex}"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        with tempfile.TemporaryDirectory() as ledger_directory:
            runner = TeamRunner(
            repository_root=root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                ledger_root=Path(ledger_directory),
                freeze_started_at="2026-07-31T10:00:00+00:00",
                ledger_now=lambda: datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
            )
            try:
                run = runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
                scope={"mode": "create"},
            )
                source = "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md"
                self.assertTrue((run.root / "sources/modeling" / source).is_file())
                self.assertFalse((run.root / "sources/protocol" / source).exists())
                manifest = json.loads((run.root / "source-manifest.json").read_text())
                self.assertTrue(all("sha256" in item for item in manifest["sources"]))
                baseline = json.loads((run.root / "baseline-manifest.json").read_text())
                self.assertIn("mcp:backend/app/mcp/server.py", baseline["files"])
                self.assertIn("team_transport", baseline["files"])
                self.assertIn("protocol_mcp_launch", baseline["files"])
                self.assertIn("protocol_mechanics", baseline["files"])
                self.assertEqual(
                    baseline["files"]["protocol_retrieval_mcp"],
                    digest_file(root / "modeling_team/protocol_retrieval_mcp.py"),
                )
                self.assertEqual(
                    baseline["files"]["protocol_mechanics"],
                    digest_file(root / "modeling_team/protocol_mechanics.py"),
                )
                self.assertEqual(
                    baseline["runtime_contract"]["protocol_retrieval_mcp"],
                    {
                        "server": "protocol_mechanics",
                        "command": "/usr/bin/python3",
                        "args": ["/opt/protocol-retrieval-mcp.py"],
                        "runtime_run_id_env": "PROTOCOL_RUNTIME_RUN_ID",
                        "runtime_context_path": "/opt/mechanics-contract.json",
                        "tools": [
                            "build_candidate_receipt",
                            "build_unified_resource_binding_receipt",
                            "translate_candidate_to_batches",
                            "inspect_model_associations",
                        ],
                    },
                )
                self.assertEqual(
                    baseline["runtime_contract"]["protocol_mcp_mode_env"],
                    {
                        "SEMANTIC_CANONICAL_STORE": "rdf",
                        "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                        "SEMANTIC_READ_MODE": "canonical",
                    },
                )
                self.assertIsNotNone(run.baseline_hash)
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    __import__("shutil").rmtree(run_root)

    def test_protocol_config_uses_exact_v2_allowlist(self) -> None:
        root = repository_root()
        task = load_task(root / "modeling_team/tasks/new-scope-business-slice.yaml", root=root)
        self.assertNotIn("create_api_key", task.protocol_tools)
        self.assertIn("submit_modeling_batch", task.protocol_tools)
        self.assertIn("save_build_checkpoint", task.protocol_tools)
        self.assertEqual(set(task.protocol_tools), SAFE_PROTOCOL_TOOLS)

    def test_visibility_probe_precedes_semantic_start_and_has_no_leak(self) -> None:
        root = repository_root()
        run_id = f"r23002-probe-{uuid4().hex}"
        run_root = root / "workspaces/modeling-runs" / run_id
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(
                repository_root=root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                ledger_root=Path(directory),
                freeze_started_at="2026-07-31T10:00:00+00:00",
                ledger_now=lambda: datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
            )
            try:
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                    task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
                    scope={"mode": "create"},
                )
                runner._probe_role_visibility()
                probe = json.loads((run_root / "evidence/role-visibility-probe.jsonl").read_text())
                self.assertTrue(probe["passed"])
                self.assertFalse((run_root / "evidence/semantic-start.jsonl").exists())
                protocol_paths = set(probe["roles"]["protocol"]["paths"])
                self.assertEqual(
                    protocol_paths,
                    {
                        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/public-protocol.md",
                        "modeling_team/references/modeling-batch-item-contract.json",
                    },
                )
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    __import__("shutil").rmtree(run_root)

    def test_runtime_probe_occurs_before_first_v2_task_turn(self) -> None:
        class ProbeAdapter:
            def __init__(self) -> None:
                self.probed = False
                self.started = []

            def start_roster(self, run, agents):
                return [SimpleNamespace(agent_id=agent.agent_id) for agent in agents]

            def probe_role_visibility(self, run):
                self.probed = True
                return {agent.agent_id: {"namespace": "passed"} for agent in run.configuration.profile.agents}

            def start_task(self, agent_id, task_text, skill_paths, roster):
                self.started.append(agent_id)
                assert self.probed

            def stop(self):
                pass

            def cleanup_identifiers(self):
                return {}

            def receive_messages(self):
                return []

            def wait_settled(self, agent_ids, timeout):
                return False

            def pause(self):
                pass

            def resume(self):
                pass

            def send_message(self, agent_id, delivery):
                pass

        root = repository_root()
        run_id = f"r23002-runtime-probe-{uuid4().hex}"
        run_root = root / "workspaces/modeling-runs" / run_id
        adapter = ProbeAdapter()
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(
                repository_root=root,
                adapter=adapter,
                ledger_root=Path(directory),
                freeze_started_at=datetime.now(UTC).isoformat(),
            )
            try:
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                    task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
                    scope={"mode": "create"},
                )
                runner.start()
                self.assertEqual(adapter.started, ["coordinator", "modeling", "protocol", "acceptance"])
                self.assertTrue((run_root / "evidence/runtime-visibility-probe.jsonl").exists())
                self.assertTrue((run_root / "evidence/semantic-start.jsonl").exists())
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    __import__("shutil").rmtree(run_root)

    def test_start_ledger_enforces_two_starts_and_narrow_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-one")
            ledger.terminal_failure("run-one", "modeling-quality", True, "baseline-two")
            # The authorize-repair gate has been removed: a fresh reservation
            # now succeeds directly after the latest terminal failure, with no
            # authorize_repair prerequisite and no baseline-match check.
            ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-two")
            with self.assertRaisesRegex(TeamConfigurationError, "budget"):
                ledger.reserve("run-three", "baseline-three", "2026-07-31T10:00:00+00:00")
            ledger = self._ledger(Path(directory) / "fresh")
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-one")
            ledger.terminal_failure("run-one", "runtime/infrastructure", False)
            # authorize_repair remains an accepted advisory history record.
            ledger.authorize_repair("run-one", "focused test evidence", "baseline-two")
            ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-two")
            with self.assertRaisesRegex(TeamConfigurationError, "budget"):
                ledger.reserve("run-three", "baseline-three", "2026-07-31T10:00:00+00:00")

    def test_budget_authorizations_replay_consumption_and_preserve_narrow_repair_gate(self) -> None:
        def begin(ledger: StartLedger, run_id: str, baseline: str) -> None:
            ledger.reserve(run_id, baseline, "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start(run_id)

        def repair(ledger: StartLedger, run_id: str, baseline: str) -> None:
            ledger.terminal_failure(run_id, "runtime/infrastructure", False)
            ledger.authorize_repair(run_id, f"tested repair for {run_id}", baseline)

        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            begin(ledger, "run-one", "baseline-one")
            repair(ledger, "run-one", "baseline-two")
            begin(ledger, "run-two", "baseline-two")
            repair(ledger, "run-two", "baseline-three")
            with self.assertRaisesRegex(TeamConfigurationError, "budget"):
                ledger.reserve("run-three", "baseline-three", "2026-07-31T10:00:00+00:00")

            ledger.authorize_budget(2, "approval-one", "user authorization one")
            self.assertEqual(ledger._start_cap(ledger._records()), 4)
            original = ledger.path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "not yet consumed"):
                ledger.authorize_budget(2, "approval-too-early", "unconsumed tranche")
            self.assertEqual(ledger.path.read_text(encoding="utf-8"), original)
            with self.assertRaisesRegex(TeamConfigurationError, "immutable"):
                ledger.authorize_budget(2, "approval-one", "different reference")
            with self.assertRaisesRegex(TeamConfigurationError, "invalid"):
                ledger.authorize_budget(1, "malformed", "malformed authorization")
            # The authorize-repair gate has been removed, so a reservation no
            # longer needs a matching repair baseline. There is nothing to
            # reject here; the concurrent reservation below starts clean.

            reserve_outcomes: list[str] = []

            def reserve(run_id: str) -> None:
                try:
                    ledger.reserve(run_id, "baseline-three", "2026-07-31T10:00:00+00:00")
                    reserve_outcomes.append(run_id)
                except TeamConfigurationError:
                    reserve_outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(reserve, ("run-three", "run-three-contender")))
            winner = next(item for item in reserve_outcomes if item != "rejected")
            self.assertEqual(reserve_outcomes.count("rejected"), 1)
            ledger.mark_semantic_start(winner)
            repair(ledger, winner, "baseline-four")
            begin(ledger, "run-four", "baseline-four")
            repair(ledger, "run-four", "baseline-five")
            ledger.authorize_budget(2, "approval-two", "user authorization two")
            self.assertEqual(ledger._start_cap(ledger._records()), 6)
            begin(ledger, "run-five", "baseline-five")
            repair(ledger, "run-five", "baseline-six")
            begin(ledger, "run-six", "baseline-six")
            repair(ledger, "run-six", "baseline-seven")
            ledger.authorize_budget(2, "approval-three", "user authorization three")
            self.assertEqual(ledger._start_cap(ledger._records()), 8)
            begin(ledger, "run-seven", "baseline-seven")
            repair(ledger, "run-seven", "baseline-eight")
            begin(ledger, "run-eight", "baseline-eight")
            repair(ledger, "run-eight", "baseline-nine")
            ledger.authorize_budget(2, "approval-four", "user authorization four")
            self.assertEqual(ledger._start_cap(ledger._records()), 10)

            original = ledger.path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "not yet consumed"):
                ledger.authorize_budget(2, "approval-five-too-early", "unconsumed cap ten")
            self.assertEqual(ledger.path.read_text(encoding="utf-8"), original)

            begin(ledger, "run-nine", "baseline-nine")
            repair(ledger, "run-nine", "baseline-ten")
            begin(ledger, "run-ten", "baseline-ten")
            ledger.terminal_failure("run-ten", "collaboration/routing", False)

            authorization_outcomes: list[str] = []

            def authorize(authorization_id: str) -> None:
                try:
                    ledger.authorize_budget(2, authorization_id, f"reference for {authorization_id}")
                    authorization_outcomes.append("authorized")
                except TeamConfigurationError:
                    authorization_outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(authorize, ("approval-five-a", "approval-five-b")))
            self.assertEqual(authorization_outcomes.count("authorized"), 1)
            self.assertEqual(authorization_outcomes.count("rejected"), 1)
            self.assertEqual(ledger._start_cap(ledger._records()), 12)

            # The authorize-repair gate has been removed: a fresh reservation
            # succeeds directly after the latest terminal failure, with no
            # authorize_repair prerequisite and no baseline-match check.
            ledger.reserve("run-eleven", "baseline-eleven", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-eleven")
            ledger.terminal_failure("run-eleven", "runtime/infrastructure", False)
            # authorize_repair remains an accepted advisory history record,
            # including a duplicate baseline and a rebind after the next start.
            ledger.authorize_repair("run-ten", "tested tenth repair", "baseline-eleven")
            ledger.authorize_repair("run-eleven", "tested eleventh repair", "baseline-twelve")
            # Freeze-time gate still rejects a stale reservation regardless of
            # the removed repair gate.
            with self.assertRaisesRegex(TeamConfigurationError, "20-minute"):
                ledger.reserve("run-twelve-expired", "baseline-twelve", "2026-07-31T09:39:00+00:00")

    def test_budget_authorization_cli_requires_consumption_and_never_appends_invalid_records(self) -> None:
        def invoke(root: Path, additional_starts: int, authorization_id: str, reference: str) -> int:
            argv = [
                "modeling-team",
                "authorize-budget",
                "--additional-starts",
                str(additional_starts),
                "--authorization-id",
                authorization_id,
                "--reference",
                reference,
            ]
            with patch.object(team_main, "repository_root", return_value=root), patch.object(sys, "argv", argv):
                return team_main.main()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "workspaces" / "modeling-runs" / ".r2-3-002-start-ledger.jsonl"
            self.assertEqual(invoke(root, 1, "too-small", "approved"), 2)
            self.assertFalse(path.exists())
            self.assertEqual(invoke(root, 3, "too-large", "approved"), 2)
            self.assertFalse(path.exists())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(json.dumps({"event": "semantic_start", "run_id": run_id}) for run_id in ("one", "two"))
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(invoke(root, 2, "only-approval", "approved"), 0)
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(invoke(root, 2, "only-approval", "approved"), 2)
            self.assertEqual(invoke(root, 2, "second-approval", "different approval"), 2)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 3)

    def test_forged_budget_authorizations_fail_closed_without_expanding_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.path.parent.mkdir(parents=True, exist_ok=True)
            ledger.path.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in (
                        {"event": "semantic_start", "run_id": "one"},
                        {"event": "semantic_start", "run_id": "two"},
                        {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "first", "reference": "first"},
                        {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "second", "reference": "second"},
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            original = ledger.path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "budget authorization ledger"):
                ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            self.assertEqual(ledger.path.read_text(encoding="utf-8"), original)

    def test_forged_budget_authorization_values_or_duplicates_fail_closed(self) -> None:
        for authorizations in (
            (
                {"event": "budget_authorization", "additional_starts": 1, "authorization_id": "first", "reference": "first"},
            ),
            (
                {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "same", "reference": "first"},
                {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "same", "reference": "second"},
            ),
            (
                {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "first", "reference": "same"},
                {"event": "budget_authorization", "additional_starts": 2, "authorization_id": "second", "reference": "same"},
            ),
        ):
            with self.subTest(authorizations=authorizations), tempfile.TemporaryDirectory() as directory:
                ledger = self._ledger(Path(directory))
                ledger.path.write_text(
                    "\n".join(json.dumps(record) for record in authorizations) + "\n", encoding="utf-8"
                )
                with self.assertRaisesRegex(TeamConfigurationError, "budget authorization ledger"):
                    ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")

    def test_budget_chain_rejects_modeling_quality_or_missing_latest_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-one")
            ledger.terminal_failure("run-one", "modeling-quality", False)
            # The authorize-repair gate has been removed: a fresh reservation
            # succeeds directly after the latest terminal failure, with no
            # authorize_repair prerequisite.
            ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-two")
            with self.assertRaisesRegex(TeamConfigurationError, "budget"):
                ledger.reserve("run-three", "baseline-three", "2026-07-31T10:00:00+00:00")

    def test_start_ledger_enforces_freeze_to_start_gate(self) -> None:
        now = __import__("datetime").datetime
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory), now.fromisoformat("2026-07-31T10:21:00+00:00"))
            with self.assertRaisesRegex(TeamConfigurationError, "20-minute"):
                ledger.reserve("run-one", "baseline", "2026-07-31T10:00:00+00:00")
            self.assertFalse(ledger.path.exists())
            with self.assertRaisesRegex(TeamConfigurationError, "future"):
                ledger.reserve("future-run", "baseline", "2026-07-31T10:23:00+00:00")

    def test_semantic_start_rechecks_elapsed_freeze_after_valid_reservation(self) -> None:
        clock = [datetime(2026, 7, 31, 10, 0, tzinfo=UTC)]
        with tempfile.TemporaryDirectory() as directory:
            ledger = StartLedger(Path(directory), now=lambda: clock[0])
            ledger.reserve("run-one", "baseline", "2026-07-31T10:00:00+00:00")
            clock[0] = datetime(2026, 7, 31, 10, 21, tzinfo=UTC)
            with self.assertRaisesRegex(TeamConfigurationError, "20-minute"):
                ledger.mark_semantic_start("run-one")

    def test_v2_elapsed_freeze_rejects_before_run_directory_or_scope(self) -> None:
        root = repository_root()
        run_id = f"r23002-stale-freeze-{uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        frozen_now = datetime(2026, 7, 31, 10, 21, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(
                repository_root=root,
                adapter=SimpleNamespace(),
                ledger_root=Path(directory),
                freeze_started_at="2026-07-31T10:00:00+00:00",
                ledger_now=lambda: frozen_now,
            )
            with self.assertRaisesRegex(TeamConfigurationError, "20-minute"):
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                    task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
                    scope={"mode": "create"},
                )
            self.assertFalse(run_root.exists())
            self.assertFalse((Path(directory) / ".r2-3-002-start-ledger.jsonl").exists())

    def test_v2_missing_freeze_rejects_before_run_directory_or_scope(self) -> None:
        root = repository_root()
        run_id = f"r23002-no-freeze-{uuid4().hex}"
        run_root = root / "workspaces/modeling-runs" / run_id
        runner = TeamRunner(
            repository_root=root,
            adapter=SimpleNamespace(),
            ledger_root=Path(tempfile.mkdtemp()),
        )
        try:
            with self.assertRaisesRegex(TeamConfigurationError, "explicit freeze"):
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                    task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
                    scope={"mode": "create"},
                )
            self.assertFalse(run_root.exists())
        finally:
            __import__("shutil").rmtree(runner.ledger_root)

    def test_repair_authorization_requires_exact_nonempty_new_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-one")
            ledger.terminal_failure("run-one", "runtime/infrastructure", False)
            # Entry validation for authorize_repair is still kept, so an empty
            # baseline hash is rejected.
            with self.assertRaisesRegex(TeamConfigurationError, "tested repair"):
                ledger.authorize_repair("run-one", "focused evidence", "")
            ledger.authorize_repair("run-one", "focused evidence", "baseline-two")
            # The authorize-repair gate has been removed, so the next reservation
            # no longer has to match the advisory repair baseline and succeeds
            # directly after the latest terminal failure.
            ledger.reserve("run-two", "different-baseline", "2026-07-31T10:00:00+00:00")

    def test_start_ledger_allows_only_presemantic_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.reserve("run-one", "baseline", "2026-07-31T10:00:00+00:00")
            self.assertTrue(ledger.release_presemantic("run-one", "visibility probe failed"))
            self.assertFalse(ledger.release_presemantic("run-one", "late duplicate cleanup"))
            records = ledger._records()
            releases = [record for record in records if record.get("event") == "presemantic_release"]
            self.assertEqual(len(releases), 1)
            self.assertEqual(releases[0]["reason"], "visibility probe failed")
            with self.assertRaisesRegex(TeamConfigurationError, "active unique"):
                ledger.mark_semantic_start("run-one")
            ledger.reserve("run-two", "baseline", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-two")
            with self.assertRaisesRegex(TeamConfigurationError, "cannot be uncounted"):
                ledger.release_presemantic("run-two", "too late")

    def test_presemantic_release_race_has_one_record_and_repair_rebind_is_fail_closed(self) -> None:
        def begin(ledger: StartLedger, run_id: str, baseline: str) -> None:
            ledger.reserve(run_id, baseline, "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start(run_id)

        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            outcomes: list[bool] = []
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda reason: outcomes.append(ledger.release_presemantic("run-one", reason)), ("first", "second")))
            self.assertEqual(sorted(outcomes), [False, True])
            self.assertEqual(
                len([record for record in ledger._records() if record.get("event") == "presemantic_release"]),
                1,
            )
            with self.assertRaisesRegex(TeamConfigurationError, "active unique"):
                ledger.mark_semantic_start("run-one")

            ledger = self._ledger(Path(directory) / "rebind")
            begin(ledger, "run-one", "baseline-one")
            ledger.terminal_failure("run-one", "runtime/infrastructure", False)
            ledger.authorize_repair("run-one", "first repair", "baseline-two")
            ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            self.assertTrue(ledger.release_presemantic("run-two", "preflight failure"))
            self.assertFalse(ledger.release_presemantic("run-two", "historical duplicate"))
            ledger.authorize_repair("run-one", "rebind repair", "baseline-three")
            with self.assertRaisesRegex(TeamConfigurationError, "active unique"):
                ledger.mark_semantic_start("run-two")
            consumed_before = len([record for record in ledger._records() if record.get("event") == "semantic_start"])
            ledger.reserve("run-three", "baseline-three", "2026-07-31T10:00:00+00:00")
            self.assertTrue(ledger.release_presemantic("run-three", "second preflight failure"))
            ledger.authorize_repair("run-one", "second rebind", "baseline-four")
            ledger.reserve("run-four", "baseline-four", "2026-07-31T10:00:00+00:00")
            self.assertEqual(
                len([record for record in ledger._records() if record.get("event") == "semantic_start"]),
                consumed_before,
            )

            for mode in ("unused", "same-baseline", "started", "foreign"):
                with self.subTest(mode=mode):
                    candidate = self._ledger(Path(directory) / mode)
                    begin(candidate, "run-one", "baseline-one")
                    candidate.terminal_failure("run-one", "runtime/infrastructure", False)
                    candidate.authorize_repair("run-one", "first repair", "baseline-two")
                    if mode == "unused":
                        pass
                    elif mode == "same-baseline":
                        candidate.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
                        candidate.release_presemantic("run-two", "released")
                    elif mode == "started":
                        begin(candidate, "run-two", "baseline-two")
                    else:
                        candidate.path.write_text(
                            "\n".join(
                                json.dumps(record)
                                for record in (
                                    *candidate._records(),
                                    {"event": "reservation", "run_id": "foreign", "baseline_hash": "foreign-baseline", "freeze_started_at": "2026-07-31T10:00:00+00:00"},
                                    {"event": "presemantic_release", "run_id": "foreign", "reason": "foreign"},
                                )
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                    baseline = "baseline-two" if mode == "same-baseline" else "baseline-three"
                    # Repair rebind immutability has been removed: authorize_repair
                    # is advisory history, so an additional record (including a
                    # duplicate baseline) is accepted in every mode.
                    candidate.authorize_repair("run-one", "invalid rebind", baseline)

            concurrent = self._ledger(Path(directory) / "concurrent")
            begin(concurrent, "run-one", "baseline-one")
            concurrent.terminal_failure("run-one", "runtime/infrastructure", False)
            concurrent.authorize_repair("run-one", "first repair", "baseline-two")
            concurrent.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            concurrent.release_presemantic("run-two", "released")
            rebind_outcomes: list[str] = []

            def rebind(baseline: str) -> None:
                try:
                    concurrent.authorize_repair("run-one", f"repair {baseline}", baseline)
                    rebind_outcomes.append("authorized")
                except TeamConfigurationError:
                    rebind_outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(rebind, ("baseline-three", "baseline-four")))
            # Repair rebind immutability has been removed: both advisory
            # authorize_repair records are accepted.
            self.assertEqual(sorted(rebind_outcomes), ["authorized", "authorized"])

    def test_cli_host_auth_preflight_waits_for_runner_prepare_and_has_no_run_side_effect(self) -> None:
        root = repository_root()
        run_id = f"r23002-auth-{uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        with tempfile.TemporaryDirectory() as directory:
            scope = Path(directory) / "scope.yaml"
            scope.write_text("mode: create\n", encoding="utf-8")
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(root / "modeling_team/profiles/base-three-agent.yaml"),
                "--task",
                str(root / "modeling_team/tasks/new-scope-business-slice.yaml"),
                "--run-id",
                run_id,
                "--scope",
                str(scope),
                "--freeze-started-at",
                "2026-07-31T10:00:00+00:00",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(CodexRuntimeAdapter, "preflight_host_auth", side_effect=AssertionError("auth must wait for prepare")),
                patch.object(TeamRunner, "prepare", side_effect=TeamConfigurationError("clean/canonical preflight failed")),
                patch.object(team_main, "_bootstrap_helpers", return_value=(lambda: ("key", "id"), lambda _id: True)),
            ):
                self.assertEqual(team_main.main(), 2)
            self.assertFalse(run_root.exists())

    def test_handoff_requires_phase_a_and_is_exactly_once(self) -> None:
        class Scope:
            def recheck_retained_producer(self):
                return {
                    "project_id": "project-1",
                    "ontology_id": "ontology-1",
                    "workspace_version": "revision-1",
                    "scope_disposition": "retained-pending-acceptance",
                }

        run = SimpleNamespace(
            run_id="r23002-handoff",
            terminal_results={
                "coordinator": {"status": "completed"},
                "modeling": {"status": "completed"},
                "protocol": {"status": "completed"},
                "acceptance": {"status": "completed"},
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            with self.assertRaisesRegex(TeamConfigurationError, "PHASE_A_PASS"):
                publish_scope_handoff(Scope(), run, "FAIL", path)
            publish_scope_handoff(Scope(), run, "PHASE_A_PASS", path)
            self.assertEqual(set(json.loads(path.read_text())), set(HANDOFF_FIELDS))
            with self.assertRaisesRegex(TeamConfigurationError, "already published"):
                publish_scope_handoff(Scope(), run, "PHASE_A_PASS", path)
            path.unlink()
            with self.assertRaisesRegex(TeamConfigurationError, "already published"):
                publish_scope_handoff(Scope(), run, "PHASE_A_PASS", path)

    def test_handoff_concurrent_publication_has_one_winner(self) -> None:
        class Scope:
            def recheck_retained_producer(self):
                return {
                    "project_id": "project-1",
                    "ontology_id": "ontology-1",
                    "workspace_version": "revision-1",
                    "scope_disposition": "retained-pending-acceptance",
                }

        run = SimpleNamespace(
            run_id="r23002-concurrent",
            terminal_results={role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol", "acceptance")},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"

            def publish() -> str:
                try:
                    publish_scope_handoff(Scope(), run, "PHASE_A_PASS", path)
                    return "published"
                except TeamConfigurationError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: publish(), range(2)))
            self.assertEqual(sorted(outcomes), ["published", "rejected"])

    def test_baseline_preview_has_prepare_exact_hash_without_creating_state(self) -> None:
        root = repository_root()
        run_id = f"r23002-baseline-{uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        profile = root / "modeling_team/profiles/base-three-agent.yaml"
        task = root / "modeling_team/tasks/new-scope-business-slice.yaml"
        manifest, baseline_hash = TeamRunner.preview_baseline(
            repository_root=root, run_id=run_id, profile_path=profile, task_path=task
        )
        for name, relative in {
            "foreground_monitor": "modeling_team/foreground_monitor.py",
            "p2_monitor_contract": "modeling_team/references/p2-monitor-contract.json",
        }.items():
            self.assertEqual(manifest["files"][name], digest_file(root / relative))
        self.assertNotIn("candidate_required_assertions", manifest["files"])
        self.assertNotIn("native_retrieval_proof", manifest["files"])
        self.assertEqual(manifest["call_sites"]["runner.prepare"], manifest["files"]["runner"])
        self.assertEqual(manifest["call_sites"]["codex.start_roster"], manifest["files"]["codex_adapter"])
        self.assertEqual(manifest["call_sites"]["transport.ack_terminal_handoff"], manifest["files"]["team_transport"])
        self.assertFalse(run_root.exists())
        with tempfile.TemporaryDirectory() as ledger_directory:
            self.assertFalse((Path(ledger_directory) / ".r2-3-002-start-ledger.jsonl").exists())
            runner = TeamRunner(
                repository_root=root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                ledger_root=Path(ledger_directory),
                freeze_started_at=datetime.now(UTC).isoformat(),
            )
            try:
                prepared = runner.prepare(run_id=run_id, profile_path=profile, task_path=task, scope={"mode": "create"})
                self.assertEqual(json.loads((prepared.root / "baseline-manifest.json").read_text()), manifest)
                self.assertEqual(prepared.baseline_hash, baseline_hash)
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    __import__("shutil").rmtree(run_root)

    def test_team_transport_digest_binds_baseline_and_runtime_core_evidence(self) -> None:
        root = repository_root()
        profile = root / "modeling_team/profiles/base-three-agent.yaml"
        task = root / "modeling_team/tasks/new-scope-business-slice.yaml"
        transport = root / "modeling_team/transport_mcp.py"
        manifest, baseline_hash = TeamRunner.preview_baseline(
            repository_root=root,
            run_id=f"r23002-transport-{uuid4().hex}",
            profile_path=profile,
            task_path=task,
        )
        self.assertEqual(manifest["files"]["team_transport"], digest_file(transport))

        original_digest = digest_file

        def changed_transport_digest(path: Path) -> str:
            return "f" * 64 if path == transport else original_digest(path)

        with patch("modeling_team.runner.digest_file", side_effect=changed_transport_digest):
            changed_manifest, changed_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=manifest["run_id"],
                profile_path=profile,
                task_path=task,
            )
        self.assertNotEqual(changed_manifest["files"]["team_transport"], manifest["files"]["team_transport"])
        self.assertNotEqual(changed_hash, baseline_hash)

        with patch(
            "modeling_team.runner.canonical_protocol_mcp_mode_contract",
            return_value={
                "SEMANTIC_CANONICAL_STORE": "alternative",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            },
        ):
            changed_contract_manifest, changed_contract_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=manifest["run_id"],
                profile_path=profile,
                task_path=task,
            )
        self.assertNotEqual(changed_contract_manifest["runtime_contract"], manifest["runtime_contract"])
        self.assertNotEqual(changed_contract_hash, baseline_hash)

        self.assertNotIn("protocol_reasoner_script", manifest["files"])
        self.assertNotIn("protocol_mcp_reasoner_env", manifest["runtime_contract"])
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            (run_root / "evidence").mkdir()
            runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
            runner.run = SimpleNamespace(root=run_root)
            runner._record_runtime_core_hashes("before_start")
            runner._record_runtime_core_hashes("after_cleanup")
            records = [
                json.loads(line)
                for line in (run_root / "evidence" / "runtime-core-hashes.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([record["phase"] for record in records], ["before_start", "after_cleanup"])
            self.assertEqual(
                [record["transport_mcp_sha256"] for record in records],
                [manifest["files"]["team_transport"], manifest["files"]["team_transport"]],
            )

    def test_retained_handoff_input_is_exactly_once_and_non_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=Path(directory), adapter=SimpleNamespace())
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            runner.run = SimpleNamespace(
                run_id="r23002-retained", root=run_root,
                terminal_results={role: {"status": "completed", "summary": "credential-canary-should-not-persist"} for role in ("coordinator", "modeling", "protocol", "acceptance")},
            )
            scope = {
                "mode": "create", "owned": True, "project_id": "project-1", "ontology_id": "ontology-1",
                "sessions_terminal": True, "protocol_key_revoked": True, "admin_key_revoked": True,
                "workspace_version": "version-1", "completed_session_id": "session-1",
                "scope_disposition": "retained-pending-acceptance",
                "cleanup_metadata": {"source": "platform cleanup"},
                "secret_canary": "must-not-persist",
            }
            runner._write_retained_handoff_evidence(scope)
            contents = (run_root / "evidence" / "retained-handoff-input.json").read_text()
            self.assertNotIn("key", contents.lower())
            self.assertNotIn("credential-canary", contents)
            self.assertNotIn("must-not-persist", contents)
            payload = json.loads(contents)
            self.assertEqual(
                payload["scope"],
                {
                    "project_id": "project-1", "ontology_id": "ontology-1",
                    "workspace_version": "version-1", "completed_session_id": "session-1",
                    "scope_disposition": "retained-pending-acceptance", "owned": True,
                },
            )
            self.assertEqual(
                payload["terminal_statuses"],
                {role: "completed" for role in ("coordinator", "modeling", "protocol", "acceptance")},
            )
            with self.assertRaisesRegex(TeamConfigurationError, "immutable"):
                runner._write_retained_handoff_evidence(scope)

    def test_retained_handoff_input_rejects_non_retained_or_non_owned_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=Path(directory), adapter=SimpleNamespace())
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            runner.run = SimpleNamespace(
                run_id="r23002-deleted", root=run_root,
                terminal_results={role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol", "acceptance")},
            )
            deleted = {
                "mode": "create", "owned": True, "project_id": "project-1", "ontology_id": "ontology-1",
                "sessions_terminal": True, "protocol_key_revoked": True, "admin_key_revoked": True,
                "workspace_version": "version-1", "completed_session_id": "session-1",
                "scope_disposition": "deleted-empty",
            }
            with self.assertRaisesRegex(TeamConfigurationError, "successful owned producer"):
                runner._write_retained_handoff_evidence(deleted)
            self.assertFalse((run_root / "evidence" / "retained-handoff-input.json").exists())

    def test_retained_handoff_input_rejects_missing_or_false_cleanup_safety_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=Path(directory), adapter=SimpleNamespace())
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            runner.run = SimpleNamespace(
                run_id="r23002-retained-safety",
                root=run_root,
                terminal_results={
                    role: {"status": "completed"}
                    for role in ("coordinator", "modeling", "protocol", "acceptance")
                },
            )
            successful_cleanup = {
                "mode": "create", "owned": True, "project_id": "project-1", "ontology_id": "ontology-1",
                "sessions_terminal": True, "protocol_key_revoked": True, "admin_key_revoked": True,
                "workspace_version": "version-1", "completed_session_id": "session-1",
                "scope_disposition": "retained-pending-acceptance", "extra_cleanup_metadata": "accepted",
            }
            for field in ("mode", "sessions_terminal", "protocol_key_revoked", "admin_key_revoked"):
                with self.subTest(field=field, state="missing"):
                    missing = dict(successful_cleanup)
                    del missing[field]
                    with self.assertRaisesRegex(TeamConfigurationError, "cleanup safety gate"):
                        runner._write_retained_handoff_evidence(missing)
                with self.subTest(field=field, state="false"):
                    false = dict(successful_cleanup)
                    false[field] = False
                    with self.assertRaisesRegex(TeamConfigurationError, "cleanup safety gate"):
                        runner._write_retained_handoff_evidence(false)
            wrong_mode = dict(successful_cleanup)
            wrong_mode["mode"] = "existing"
            with self.assertRaisesRegex(TeamConfigurationError, "cleanup safety gate"):
                runner._write_retained_handoff_evidence(wrong_mode)
            self.assertFalse((run_root / "evidence" / "retained-handoff-input.json").exists())

    def test_offline_handoff_rechecks_retained_scope_without_runtime(self) -> None:
        class Client:
            def __init__(self) -> None:
                self.version = "version-1"

            def __call__(self, method, path, body, key):
                if path.endswith("/modeling-context"):
                    return 200, {
                        "project": {"id": "project-1"},
                        "ontology": {"id": "ontology-1"},
                        "workspace": {"state": "ready", "workspace_version": self.version},
                    }
                if path.endswith("/build-context"):
                    return 200, {"agent_state": {"active_sessions": [], "recent_sessions": [{"id": "session-1"}]}}
                if path == "/api/build-sessions/session-1":
                    return 200, {
                        "session": {"id": "session-1", "project_id": "project-1", "status": "completed", "revision": 1},
                        "involved_ontology_ids": ["ontology-1"],
                        "modeling_batches": [],
                        "leases": [{"state": "released"}],
                    }
                raise AssertionError(f"unexpected request: {method} {path}")

        def state(results=None):
            return {
                "state": "CLEANED",
                "run_id": "r23002-offline",
                "terminal_results": results or {role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol", "acceptance")},
                "cleanup": {"scope": {
                    "owned": True, "project_id": "project-1", "ontology_id": "ontology-1",
                    "workspace_version": "version-1", "completed_session_id": "session-1",
                    "scope_disposition": "retained-pending-acceptance",
                }},
            }

        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            (run_root / "state.json").write_text(json.dumps(state()), encoding="utf-8")
            (run_root / "evidence").mkdir()
            (run_root / "evidence" / "retained-handoff-input.json").write_text(
                json.dumps(
                    {
                        "run_id": "r23002-offline",
                        "terminal_statuses": {role: "completed" for role in ("coordinator", "modeling", "protocol", "acceptance")},
                        "scope": state()["cleanup"]["scope"],
                    }
                ),
                encoding="utf-8",
            )
            verdict = Path(directory) / "phase-a.json"
            verdict.write_text('{"verdict":"PHASE_A_PASS"}', encoding="utf-8")
            destination = Path(directory) / "handoff.json"
            def publish() -> Path:
                return publish_offline_scope_handoff(
                run_root=run_root, expected_run_id="r23002-offline", base_url="http://example", phase_a_verdict_artifact=verdict,
                    destination=destination, bootstrap_admin=lambda: ("admin", "admin-id"),
                    revoke_admin=lambda _: True, request=client,
                )
            def publish_once() -> str:
                try:
                    publish()
                    return "published"
                except TeamConfigurationError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                self.assertEqual(sorted(executor.map(lambda _: publish_once(), range(2))), ["published", "rejected"])
            self.assertEqual(json.loads(destination.read_text())["workspace_version"], "version-1")
            verdict.write_text('{"verdict":"PHASE_A_FAIL"}', encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "PHASE_A_PASS"):
                publish()
            verdict.write_text('{"verdict":"PHASE_A_PASS"}', encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "already published"):
                publish()
            destination.unlink()
            with self.assertRaisesRegex(TeamConfigurationError, "already published"):
                publish()
            client.version = "version-2"
            second = Path(directory) / "drifted.json"
            with self.assertRaisesRegex(TeamConfigurationError, "scope recheck failed"):
                publish_offline_scope_handoff(
                    run_root=run_root, expected_run_id="r23002-offline", base_url="http://example", phase_a_verdict_artifact=verdict,
                    destination=second, bootstrap_admin=lambda: ("admin", "admin-id"),
                    revoke_admin=lambda _: True, request=client,
                )
            client.version = "version-1"
            (run_root / "state.json").write_text(
                json.dumps(state({"coordinator": {"status": "completed"}, "modeling": {"status": "completed"}, "protocol": {"status": "blocked"}, "acceptance": {"status": "completed"}})),
                encoding="utf-8",
            )
            (run_root / "evidence" / "retained-handoff-input.json").write_text(
                json.dumps(
                    {
                        "run_id": "r23002-offline",
                        "terminal_statuses": {"coordinator": "completed", "modeling": "completed", "protocol": "blocked"},
                        "scope": state()["cleanup"]["scope"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(TeamConfigurationError, "completed"):
                publish_offline_scope_handoff(
                    run_root=run_root, expected_run_id="r23002-offline", base_url="http://example", phase_a_verdict_artifact=verdict,
                    destination=Path(directory) / "failed" / "handoff.json", bootstrap_admin=lambda: ("admin", "admin-id"),
                    revoke_admin=lambda _: True, request=client,
                )

    def test_offline_handoff_rejects_state_evidence_mismatch_before_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            statuses = {role: {"status": "completed", "summary": "state may retain details"} for role in ("coordinator", "modeling", "protocol", "acceptance")}
            scope = {
                "owned": True, "project_id": "project-1", "ontology_id": "ontology-1",
                "workspace_version": "version-1", "completed_session_id": "session-1",
                "scope_disposition": "blocked",
            }
            (run_root / "state.json").write_text(
                json.dumps({"state": "CLEANED", "run_id": "r23002-mismatch", "terminal_results": statuses, "cleanup": {"scope": scope}}),
                encoding="utf-8",
            )
            (run_root / "evidence" / "retained-handoff-input.json").write_text(
                json.dumps({
                    "run_id": "r23002-mismatch",
                    "terminal_statuses": {role: "completed" for role in ("coordinator", "modeling", "protocol", "acceptance")},
                    "scope": {**scope, "scope_disposition": "retained-pending-acceptance"},
                }),
                encoding="utf-8",
            )
            verdict = Path(directory) / "phase-a.json"
            verdict.write_text('{"verdict":"PHASE_A_PASS"}', encoding="utf-8")
            calls: list[str] = []
            with self.assertRaisesRegex(TeamConfigurationError, "scope drifted"):
                publish_offline_scope_handoff(
                    run_root=run_root, expected_run_id="r23002-mismatch", base_url="http://example",
                    phase_a_verdict_artifact=verdict, destination=Path(directory) / "handoff.json",
                    bootstrap_admin=lambda: (calls.append("bootstrap") or "admin", "admin-id"),
                    revoke_admin=lambda _: True, request=lambda *_: (_ for _ in ()).throw(AssertionError("no query")),
                )
            self.assertEqual(calls, [])

    def test_offline_handoff_phase_a_fail_is_before_state_or_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verdict = root / "phase-a.json"
            verdict.write_text('{"verdict":"PHASE_A_FAIL"}', encoding="utf-8")
            destination = root / "new" / "handoff.json"
            calls: list[str] = []
            with self.assertRaisesRegex(TeamConfigurationError, "PHASE_A_PASS"):
                publish_offline_scope_handoff(
                    run_root=root / "missing-run", expected_run_id="r23002-phase-fail", base_url="http://example",
                    phase_a_verdict_artifact=verdict, destination=destination,
                    bootstrap_admin=lambda: (calls.append("bootstrap") or "admin", "admin-id"),
                    revoke_admin=lambda _: True, request=lambda *_: calls.append("request"),
                )
            self.assertEqual(calls, [])
            self.assertFalse(destination.parent.exists())
            self.assertFalse((destination.parent / ".r2-3-002-handoff-publications.jsonl").exists())
            self.assertFalse((destination.parent / ".r2-3-002-handoff-publications.lock").exists())
