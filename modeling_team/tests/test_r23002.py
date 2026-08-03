from __future__ import annotations

import hashlib
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
    verify_scoped_retrieval_fallback,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
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
            "create_class", "create_property", "create_relation_type", "create_shape", "create_entity", "create_relation"
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
        self.assertEqual(property_contract["required"], ["class_id", "name"])
        self.assertEqual(property_contract["one_or_more_required"], ["datatype", "object_class_id"])
        self.assertEqual(property_contract["fields"]["datatype"]["type"], "string")
        self.assertIn("both fields", property_contract["fields"]["object_class_id"]["branch"])
        shape_contract = reference["create_payloads"]["create_shape"]
        self.assertEqual(shape_contract["fields"]["constraints"]["type"], "array")
        constraint = reference["shape_constraint"]
        self.assertEqual(constraint["required"], ["path_id"])
        self.assertEqual(constraint["additional_properties"], "accepted-and-ignored-by-current-compiler")
        self.assertEqual(constraint["fields"]["min_count"]["type"], "integer")
        self.assertEqual(constraint["fields"]["enum_values"]["type"], "array")
        self.assertEqual(reference["create_payloads"]["create_entity"]["fields"]["properties"]["type"], "object")
        self.assertTrue(all(
            field["format"] == "absolute-rdf-iri"
            for field in reference["create_payloads"]["create_relation"]["fields"].values()
        ))

        registry = ModelingCommandHandlerRegistry(Settings())
        with self.assertRaisesRegex(InvalidCommandPayload, "either datatype"):
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="property", command_kind="create_property",
                payload={"class_id": "class", "name": "property"},
            )
        both_property_branches = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="property-both", command_kind="create_property",
            payload={"class_id": "class", "name": "property", "datatype": "xsd:string", "object_class_id": "target"},
        )
        self.assertTrue(both_property_branches.compiled.metadata["is_object_property"])
        with self.assertRaisesRegex(InvalidCommandPayload, "absolute RDF IRI"):
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="relation", command_kind="create_relation",
                payload={"source_entity_iri": "relative", "relation_type_iri": "https://example.test/relation", "target_entity_iri": "https://example.test/target"},
            )
        with self.assertRaisesRegex(InvalidCommandPayload, "Missing required field: path_id"):
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="shape", command_kind="create_shape",
                payload={"target_class_id": "class", "constraints": [{}]},
            )
        accepted_unknown = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="shape-known", command_kind="create_shape",
            payload={"target_class_id": "class", "constraints": [{"path_id": "property", "future_constraint": "ignored"}]},
        )
        self.assertTrue(accepted_unknown.compiled and accepted_unknown.compiled.delta.inserts)
        self.assertIn("MUST send a string", property_contract["fields"]["name"]["server_current_acceptance"])
        self.assertIn("numeric strings are currently accepted", constraint["fields"]["min_count"]["compiler_behavior"])
        self.assertTrue(
            registry.prepare(
                batch_id="batch", ontology_id="ontology", client_item_id="class-number", command_kind="create_class",
                payload={"name": 7},
            ).compiled
        )
        numeric_constraint = registry.prepare(
            batch_id="batch", ontology_id="ontology", client_item_id="shape-number", command_kind="create_shape",
            payload={"target_class_id": "class", "constraints": [{"path_id": "property", "min_count": "2"}]},
        )
        self.assertTrue(numeric_constraint.compiled)

        class Session:
            def __init__(self) -> None:
                self.values = iter([
                    SimpleNamespace(status="active", project_id="project"),
                    SimpleNamespace(project_id="project"),
                ])

            def scalar(self, _statement):
                return next(self.values)

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

    def test_object_property_relation_and_shape_path_binding_is_protocol_explicit(self) -> None:
        from app.core.config import Settings
        from app.services.modeling_handlers import ModelingCommandHandlerRegistry

        root = repository_root()
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(
                encoding="utf-8"
            )
        )
        binding = reference["cross_batch_application_contract"][
            "object_property_shape_relation_binding"
        ]
        self.assertIn("create_property and object_class_id", binding["object_predicate_rule"])
        self.assertIn("formal create_property resource_iri", binding["relation_binding"])
        self.assertIn("formal create_property resource_id", binding["shape_path_resolution"])
        self.assertIn("create_relation_type for the same predicate", binding["forbidden"][0])
        self.assertIn("concrete translation conflict", binding["binding_conflict"])

        helper_rule = reference["semantic_retrieval_completion_contract"]["fallback"][
            "deterministic_helper"
        ]["rule"]
        self.assertIn("mode field MUST equal the exact string create; fresh_create is not accepted", helper_rule)

        instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "create_property` and `object_class_id`",
            "create-property formal `resource_iri`",
            "Shape `path_id` to the same formal create-property `resource_id`",
            "Do not create `create_relation_type` for the same predicate",
            "concrete pre-write translation\nconflict",
            "only the exact literal\n`create`; `fresh_create` is not accepted",
        ):
            self.assertIn(phrase, instructions)

        registry = ModelingCommandHandlerRegistry(Settings())
        property_command = registry.prepare(
            batch_id="binding-batch",
            ontology_id="ontology",
            client_item_id="object-predicate",
            command_kind="create_property",
            payload={
                "property_id": "same-id",
                "class_id": "source-class",
                "name": "links to",
                "object_class_id": "target-class",
            },
        )
        property_iri = property_command.outputs["resource_iri"]
        shape_command = registry.prepare(
            batch_id="binding-batch",
            ontology_id="ontology",
            client_item_id="required-link",
            command_kind="create_shape",
            payload={
                "target_class_id": "source-class",
                "constraints": [{"path_id": property_command.outputs["resource_id"], "min_count": 1}],
            },
        )
        relation_command = registry.prepare(
            batch_id="binding-batch",
            ontology_id="ontology",
            client_item_id="bound-relation",
            command_kind="create_relation",
            payload={
                "source_entity_iri": "https://example.test/entity/source",
                "relation_type_iri": property_iri,
                "target_entity_iri": "https://example.test/entity/target",
            },
        )
        shape_path = next(
            object_
            for _subject, predicate, object_, _graph in shape_command.compiled.delta.inserts
            if predicate == "<http://www.w3.org/ns/shacl#path>"
        )
        relation_predicate = relation_command.compiled.delta.inserts[0][1]
        self.assertEqual(shape_path, f"<{property_iri}>")
        self.assertEqual(relation_predicate, shape_path)

        forbidden_relation_type = registry.prepare(
            batch_id="binding-batch",
            ontology_id="ontology",
            client_item_id="forbidden-relation-type",
            command_kind="create_relation_type",
            payload={
                "relation_type_id": property_command.outputs["resource_id"],
                "name": "links to",
                "source_class_id": "source-class",
                "target_class_id": "target-class",
            },
        )
        forbidden_relation = registry.prepare(
            batch_id="binding-batch",
            ontology_id="ontology",
            client_item_id="forbidden-relation",
            command_kind="create_relation",
            payload={
                "source_entity_iri": "https://example.test/entity/source",
                "relation_type_iri": forbidden_relation_type.outputs["resource_iri"],
                "target_entity_iri": "https://example.test/entity/target",
            },
        )
        self.assertNotEqual(forbidden_relation_type.outputs["resource_iri"], property_iri)
        self.assertNotEqual(forbidden_relation.compiled.delta.inserts[0][1], shape_path)

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
        self.assertIn("only blocked, never completed", modeling_task)
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
        self.assertIn("classes,\nproperties, relations, Shapes, entities, evidence, explicit unknowns, and dependencies", modeling_instructions)
        self.assertIn("do not author exact platform\nitems", modeling_instructions)
        self.assertIn("Protocol mechanically translates", modeling_instructions)
        self.assertIn("expects_reply=true", modeling_instructions)
        self.assertIn("delivered conflict's `delivery_id`", modeling_instructions)
        self.assertIn("only `blocked`, never `completed`", modeling_instructions)
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
                "dependency_safe_shape",
            ],
        )
        self.assertEqual(
            contract["ordered_schedule"],
            "class -> property/relation type -> entity -> receipt/read bind generated IDs/IRIs -> "
            "relation -> only dependency-safe Shape",
        )
        self.assertEqual(
            contract["applied_stages"]["class"]["command_kinds"], ["create_class"]
        )
        self.assertEqual(
            contract["applied_stages"]["property_or_relation_type"]["command_kinds"],
            ["create_property", "create_relation_type"],
        )
        self.assertEqual(
            contract["applied_stages"]["entity"]["command_kinds"], ["create_entity"]
        )
        self.assertEqual(
            contract["applied_stages"]["relation"]["command_kinds"], ["create_relation"]
        )
        self.assertEqual(
            contract["applied_stages"]["dependency_safe_shape"]["command_kinds"], ["create_shape"]
        )
        self.assertTrue(
            all(
                stage["execution"] == "independent dry_run then apply_atomic"
                for stage in contract["applied_stages"].values()
            )
        )
        self.assertIn("formal apply receipt or required platform read", contract["formal_binding"]["workspace_version"])
        self.assertIn("never guess, synthesize, or forward-reference", contract["formal_binding"]["generated_identifiers"])
        self.assertIn("immediately validates later Batches", contract["shape_activation"])
        self.assertIn("must not mutate candidate meaning or reorder candidate semantics", contract["candidate_invariant"])
        self.assertEqual(
            contract["forbidden"],
            [
                "Shape-first application",
                "unbound forward reference",
                "semantic candidate mutation or reordering",
                "delete or deactivate an applied Shape",
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
            "dry_run` followed by\n`apply_atomic",
            "must not mutate or reorder candidate meaning",
            "immediately validates later Batches",
            "unbound forward reference",
            "Never delete or deactivate an applied Shape\nor weaken validation",
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

    def test_semantic_validation_contract_is_protocol_private_and_baseline_bound(self) -> None:
        root = repository_root()
        reference_path = root / "modeling_team/references/modeling-batch-item-contract.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        contract = reference["semantic_validation_invocation_contract"]
        self.assertIn("no business semantics, scenario target, or acceptance answer", contract["purpose"])
        validation_scope = contract["validation_scope"]
        self.assertEqual(validation_scope["allowed"], ["asserted_only", "asserted_plus_reasoning"])
        self.assertIn("concrete pre-call translation conflict", validation_scope["other_scope_conflict"])
        separated_flow = contract["separated_validation_and_reasoning_flow"]
        self.assertEqual(separated_flow["validation_scope"], "asserted_only")
        self.assertIn("R2.3-002 separated validation and reasoning flow", separated_flow["rule"])
        reasoning_scope = contract["asserted_plus_reasoning"]
        self.assertIn("intended validation includes the reasoning result graph", reasoning_scope["permitted_only_when"])
        self.assertIn("formal reasoning receipt", reasoning_scope["permitted_only_when"])
        self.assertIn("reasoning_result_graph_iri", reasoning_scope["reasoning_result_graph_iri"])
        self.assertIn("never guess, synthesize, or use an unbound graph IRI", reasoning_scope["reasoning_result_graph_iri"])
        self.assertIn("concrete pre-call translation conflict", reasoning_scope["missing_graph_conflict"])

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
            "only `asserted_only` or `asserted_plus_reasoning`",
            "any other scope is a concrete pre-call translation conflict",
            "separated validation and reasoning flow explicitly uses `asserted_only`",
            "formal reasoning receipt binds `reasoning_result_graph_iri`",
            "unbound reasoning graph IRI",
            "conflict instead of invoking validation",
        ):
            self.assertIn(phrase, protocol_instructions)
        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("asserted_plus_reasoning", modeling_instructions)

        baseline, _baseline_hash = TeamRunner.preview_baseline(
            repository_root=root,
            run_id=f"r23002-validation-scope-{uuid4().hex}",
            profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=root / "modeling_team/tasks/new-scope-business-slice.yaml",
        )
        self.assertEqual(
            baseline["files"]["source:modeling_team/references/modeling-batch-item-contract.json"],
            digest_file(reference_path),
        )
        v1 = load_task(root / "modeling_team/tasks/base-capability-smoke.yaml", root=root)
        self.assertNotIn(reference_path, v1.allowed_sources)

    def test_attempt_fourteen_material_gap_and_retrieval_fallback_contract(self) -> None:
        root = repository_root()
        reference = json.loads(
            (root / "modeling_team/references/modeling-batch-item-contract.json").read_text(encoding="utf-8")
        )
        retrieval = reference["semantic_retrieval_completion_contract"]
        self.assertIn("no business semantics, tester answer, answer count", retrieval["purpose"])
        self.assertEqual(
            retrieval["successful_receipt_requires"],
            [
                "ontology-scoped generic query",
                "no truncation",
                "required Evidence and lineage",
                "no cross-ontology fact",
                "successful continuation whenever paging is required",
            ],
        )
        self.assertIn("same-subject facts both block", retrieval["fallback"]["facts_read"])
        self.assertNotIn("may use", retrieval["fallback"]["allowed"].lower())
        self.assertEqual(
            retrieval["fallback"]["mandatory_sequence"],
            [
                "A generic query result with complete=true is successful retrieval evidence.",
                "For an eligible fresh-create incomplete, degraded, or truncated generic query, collect every formal proof response below unmodified.",
                "Call the native Protocol-only MCP verifier verify_scoped_retrieval_fallback with that formal proof before deciding terminal conflict.",
                "A native verifier result with complete=true is successful retrieval evidence.",
                "Only after a native verifier tool/protocol error or incomplete result, fail closed with a terminal retrieval-completeness conflict.",
            ],
        )
        self.assertEqual(
            retrieval["fallback"]["deterministic_helper"],
            {
                "mcp_server": "protocol_mechanics",
                "tool": "verify_scoped_retrieval_fallback",
                "command": "/usr/bin/python3 /opt/protocol-retrieval-mcp.py",
                "rule": "Call this native Protocol-only MCP tool with the ten mechanical proof fields as direct arguments, never under a proof wrapper and with no missing or extra field, before deciding terminal conflict. The mode field MUST equal the exact string create; fresh_create is not accepted. The wrapper rejects malformed arguments with -32602. A complete=true result is successful retrieval evidence; only a tool/protocol error or incomplete result fails closed as a retrieval-completeness conflict.",
            },
        )
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
            "otherwise incomplete retrieval proof as a conflict",
        ):
            self.assertIn(phrase, modeling_instructions)
        self.assertNotIn("C -> B -> A", modeling_instructions)
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "semantic_retrieval_completion_contract",
            "truncation, missing required Evidence/lineage, cross-ontology facts",
            "unmodified full",
            "fact IDs",
            "exact non-truncated statement lineage",
            "use SPARQL or a new\nAPI",
        ):
            self.assertIn(phrase, protocol_instructions)
        self.assertNotIn("may use the specified\nfallback", protocol_instructions.lower())
        protocol_ordered_phrases = (
            "generic query result with `complete=true` is successful retrieval evidence",
            "you MUST collect every formal fallback\nproof response below unmodified",
            "you MUST call native MCP server `protocol_mechanics`, tool\n`verify_scoped_retrieval_fallback`, with those ten proof fields as direct arguments (never nest a\n`proof` object, omit a field, or add a wrapper field) before deciding terminal conflict",
            "native\nverifier result with `complete=true` is successful retrieval evidence",
            "only after a native\nverifier tool/protocol error or incomplete result, fail closed with a terminal\nretrieval-completeness conflict",
        )
        self.assertEqual(
            [protocol_instructions.index(phrase) for phrase in protocol_ordered_phrases],
            sorted(protocol_instructions.index(phrase) for phrase in protocol_ordered_phrases),
        )

        task_text = (root / "modeling_team/tasks/new-scope-business-slice.yaml").read_text(encoding="utf-8")
        self.assertNotIn("may use", task_text.lower())
        task_ordered_phrases = (
            "Protocol MUST first collect the formal fallback proof and call the native verifier",
            "it must not directly block",
            "Generic-query or native-verifier complete=true is successful retrieval\n  evidence",
            "Only a native verifier tool/protocol error or incomplete result is a fail-closed\n  retrieval-completeness conflict",
        )
        self.assertEqual(
            [task_text.index(phrase) for phrase in task_ordered_phrases],
            sorted(task_text.index(phrase) for phrase in task_ordered_phrases),
        )

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

        def envelope(data: dict[str, object]) -> dict[str, object]:
            return {"ok": True, "data": data}

        graphs = {
            "asserted_ontology": "graph:ontology",
            "asserted_data": "graph:data",
            "shapes": "graph:shapes",
        }
        counts = {
            "classes": 1,
            "properties": 1,
            "relation_types": 1,
            "shapes": 1,
            "entities": 3,
            "relations": 1,
            "facts": 3,
        }

        def quad(subject: str, predicate: str, object_: str, graph: str) -> list[str]:
            return [f"<{subject}>", f"<{predicate}>", f"<{object_}>", graph]

        def delta_hash(delta: dict[str, object]) -> str:
            encoded = json.dumps(delta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(encoded.encode()).hexdigest()

        def fact_id(subject: str, predicate: str, object_: str, graph: str) -> str:
            canonical = f"<{subject}> <{predicate}> <{object_}> <{graph}>"
            return hashlib.sha256(canonical.encode()).hexdigest()

        def statement(subject: str, predicate: str, object_: str) -> dict[str, str]:
            return {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "object_kind": "iri",
                "object_datatype": None,
                "object_language": None,
                "source_graph_iri": graphs["asserted_data"],
            }

        commands = [
            ("class", "create_class", "class-1", graphs["asserted_ontology"]),
            ("property", "create_property", "property-1", graphs["asserted_ontology"]),
            ("relation-type", "create_relation_type", "relation-type-1", graphs["asserted_ontology"]),
            ("shape", "create_shape", "shape-1", graphs["shapes"]),
            ("source", "create_entity", "entity-source", graphs["asserted_data"]),
            ("target-one", "create_entity", "entity-target-one", graphs["asserted_data"]),
            ("target-two", "create_entity", "entity-target-two", graphs["asserted_data"]),
        ]
        inserts = [
            quad(iri, "type", command_kind.removeprefix("create_"), graph)
            for _, command_kind, iri, graph in commands
        ]
        inserts += [
            quad("entity-source", "relation", "entity-target-one", graphs["asserted_data"]),
            quad("entity-source", "relation", "entity-target-two", graphs["asserted_data"]),
        ]
        applied_delta = {"inserts": inserts, "deletes": [], "clear_graphs": [], "drop_graphs": []}
        write_items = [
            {
                "item_id": item_id,
                "command_kind": command_kind,
                "payload": {},
                "resource_outputs": {"resource_id": item_id, "resource_iri": iri},
            }
            for item_id, command_kind, iri, _ in commands
        ] + [
            {
                "item_id": "relation-one",
                "command_kind": "create_relation",
                "payload": {
                    "source_entity_iri": "entity-source",
                    "relation_type_iri": "relation",
                    "target_entity_iri": "entity-target-one",
                },
                "resource_outputs": {},
            },
            {
                "item_id": "relation-two",
                "command_kind": "create_relation",
                "payload": {
                    "source_entity_iri": "entity-source",
                    "relation_type_iri": "relation",
                    "target_entity_iri": "entity-target-two",
                },
                "resource_outputs": {},
            },
        ]
        applied_results = [
            {
                "item_id": item["item_id"],
                "status": "applied",
                "resource_outputs": item["resource_outputs"],
            }
            for item in write_items
        ]
        write_detail = {
            "batch_id": "batch-write",
            "ontology_id": "ontology-1",
            "build_session_id": "session-1",
            "items": write_items,
            "attempts": [
                {"mode": "dry_run", "attempt_status": "validated"},
                {
                    "mode": "apply_atomic",
                    "attempt_status": "applied",
                    "workspace": {"before_version": "workspace-0", "after_version": "workspace-1"},
                    "normalized_delta": applied_delta,
                    "delta_hash": delta_hash(applied_delta),
                    "items": applied_results,
                },
            ],
        }
        rejected_shape_detail = {
            "batch_id": "batch-rejected-shape",
            "ontology_id": "ontology-1",
            "build_session_id": "session-1",
            "items": [{"item_id": "bad-shape", "command_kind": "create_shape", "payload": {}}],
            "attempts": [{"mode": "dry_run", "attempt_status": "validation_failed"}],
        }
        facts = [
            statement("entity-source", "type", "entity"),
            statement("entity-target-one", "type", "entity"),
            statement("entity-target-two", "type", "entity"),
            statement("entity-source", "relation", "entity-target-one"),
            statement("entity-source", "relation", "entity-target-two"),
        ]
        assertions = [
            {
                "graph_role": "asserted_data",
                "subject": item["subject"],
                "predicate": item["predicate"],
                "object": item["object"],
                "object_kind": item["object_kind"],
                "object_datatype": item["object_datatype"],
                "object_language": item["object_language"],
            }
            for item in facts[-2:]
        ]

        def lineage(assertion: dict[str, str]) -> dict[str, object]:
            computed_fact_id = fact_id(
                assertion["subject"], assertion["predicate"], assertion["object"], graphs["asserted_data"]
            )
            return envelope(
                {
                    "ontology_id": "ontology-1",
                    "target": {"type": "statement", "id": computed_fact_id},
                    "truncated": False,
                    "items": [
                        {
                            "statement_id": computed_fact_id,
                            "statement": {
                                "subject": assertion["subject"],
                                "predicate": assertion["predicate"],
                                "object": f"<{assertion['object']}>",
                            },
                            "technical_trace": {"graph_iri": graphs["asserted_data"]},
                            "origins": [{"kind": "modeling_item"}],
                            "supporting_context": {"evidence_references": [{"id": "evidence-1"}]},
                        }
                    ],
                }
            )

        initial_counts = {name: 0 for name in counts}
        proof = {
            "mode": "create",
            "initial_modeling_context": envelope(
                {"ontology": {"id": "ontology-1"}, "workspace": {"workspace_version": "workspace-0"}, "resource_counts": initial_counts}
            ),
            "final_modeling_context": envelope(
                {"ontology": {"id": "ontology-1"}, "workspace": {"workspace_version": "workspace-1"}, "resource_counts": counts}
            ),
            "workspace_context": envelope(
                {
                    "ontology_id": "ontology-1",
                    "state": "ready",
                    "default_graph_set_id": "graph-set-1",
                    "source_signature": "source-signature-1",
                    "members": [
                        {"role": role, "graph_iri": graph, "owner_type": "ontology", "owner_id": "ontology-1"}
                        for role, graph in graphs.items()
                    ],
                }
            ),
            "batch_inventory": {
                "requested_limit": 3,
                "cursor": None,
                "status_filter": None,
                "response": envelope({"batches": [{"batch_id": "batch-write"}, {"batch_id": "batch-rejected-shape"}], "next_cursor": None}),
            },
            "batch_details": [envelope(write_detail), envelope(rejected_shape_detail)],
            "entities_read": envelope(
                {
                    "graph_set_id": "graph-set-1",
                    "source_signature": "source-signature-1",
                    "model_name": "entity-list",
                    "include": "asserted",
                    "items": [
                        {"iri": iri, "source_graph_iri": graphs["asserted_data"]}
                        for iri in ["entity-source", "entity-target-one", "entity-target-two"]
                    ],
                }
            ),
            "statements_read": {
                "requested_limit": 6,
                "response": envelope(
                    {
                        "graph_set_id": "graph-set-1",
                        "source_signature": "source-signature-1",
                        "model_name": "statement-list",
                        "include": "asserted",
                        "items": facts,
                    }
                ),
            },
            "candidate_required_assertions": {},
            "statement_lineage": {},
        }
        semantic_payload = {"schema_version": "candidate-required-assertions/v1", "statements": assertions}
        semantic_digest = hashlib.sha256(
            json.dumps(semantic_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        candidate_binding = {
            "schema_version": "candidate-required-assertions/v1",
            "candidate_revision": "candidate-revision-1",
            "delivery_id": "delivery-candidate-1",
            "reply_chain": ["delivery-candidate-1"],
            "semantic_digest": semantic_digest,
        }
        candidate_digest = hashlib.sha256(
            json.dumps(candidate_binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        materialized_quads = [
            {**item, "source_graph_iri": graphs["asserted_data"]}
            for item in assertions
        ]
        materialized_quads.sort(
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        materialized_digest = hashlib.sha256(
            json.dumps(
                {"candidate_digest": candidate_digest, "quads": materialized_quads},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        proof["candidate_required_assertions"] = {
            **candidate_binding,
            "candidate_digest": candidate_digest,
            "items": assertions,
            "materialized_digest": materialized_digest,
            "materialized_quads": materialized_quads,
        }
        proof["statement_lineage"] = {
            **candidate_binding,
            "candidate_digest": candidate_digest,
            "materialized_digest": materialized_digest,
            "max_depth": 2,
            "records": [
                {
                    "fact_id": fact_id(item["subject"], item["predicate"], item["object"], graphs["asserted_data"]),
                    "quad": {**item, "source_graph_iri": graphs["asserted_data"]},
                    "response": lineage({**item, "source_graph_iri": graphs["asserted_data"]}),
                }
                for item in assertions
            ],
        }
        result = verify_scoped_retrieval_fallback(proof)
        self.assertEqual(result["complete"], True)
        self.assertEqual(result["ontology_id"], "ontology-1")
        self.assertEqual(result["expected_triple_count"], len(facts))
        self.assertEqual(result["fact_subject_count"], 3)
        self.assertEqual(result["relation_source_count"], 1)
        self.assertEqual(result["candidate_digest"], candidate_digest)
        self.assertEqual(result["materialized_digest"], materialized_digest)

        def invalid_copy() -> dict[str, object]:
            return json.loads(json.dumps(proof))

        wrong_ontology = invalid_copy()
        wrong_ontology["final_modeling_context"]["data"]["ontology"]["id"] = "ontology-other"
        count_drift = invalid_copy()
        count_drift["final_modeling_context"]["data"]["resource_counts"]["classes"] = 2
        same_subject_missing_and_extra = invalid_copy()
        changed = same_subject_missing_and_extra["statements_read"]["response"]["data"]["items"][-1]
        changed["object"] = "entity-unexpected"
        missing_provenance = invalid_copy()
        missing_provenance["statement_lineage"]["records"][0]["response"]["data"]["items"][0]["supporting_context"] = {"evidence_references": []}
        inventory_cursor = invalid_copy()
        inventory_cursor["batch_inventory"]["response"]["data"]["next_cursor"] = "more"
        insufficient_capacity = invalid_copy()
        insufficient_capacity["statements_read"]["requested_limit"] -= 1
        false_envelope = invalid_copy()
        false_envelope["entities_read"]["ok"] = False
        root_data = invalid_copy()
        root_data["entities_read"] = {"ok": True, "ontology_id": "ontology-1", "items": []}
        extra_envelope = invalid_copy()
        extra_envelope["entities_read"]["extra"] = "not-a-response-field"
        inventory_mismatch = invalid_copy()
        inventory_mismatch["batch_details"].pop()
        rejected_shape_counted = invalid_copy()
        rejected_shape_counted["batch_details"][1]["data"]["attempts"][0].update(
            {"mode": "apply_atomic", "attempt_status": "applied"}
        )
        graph_mismatch = invalid_copy()
        bad_delta = graph_mismatch["batch_details"][0]["data"]["attempts"][1]["normalized_delta"]
        bad_delta["inserts"][0][3] = graphs["asserted_data"]
        graph_mismatch["batch_details"][0]["data"]["attempts"][1]["delta_hash"] = delta_hash(bad_delta)
        delta_hash_drift = invalid_copy()
        delta_hash_drift["batch_details"][0]["data"]["attempts"][1]["delta_hash"] = "wrong"
        workspace_break = invalid_copy()
        workspace_break["batch_details"][0]["data"]["attempts"][1]["workspace"]["before_version"] = "workspace-other"
        bad_fact_id = invalid_copy()
        bad_fact_id["statements_read"]["response"]["data"]["items"][0]["fact_id"] = "wrong"
        delta_fact_drift = invalid_copy()
        drift_delta = delta_fact_drift["batch_details"][0]["data"]["attempts"][1]["normalized_delta"]
        drift_delta["inserts"][-1][2] = "<entity-unexpected>"
        delta_fact_drift["batch_details"][0]["data"]["attempts"][1]["delta_hash"] = delta_hash(drift_delta)
        entity_iri_drift = invalid_copy()
        entity_iri_drift["entities_read"]["data"]["items"][0]["iri"] = "entity-other"
        workspace_graph_set_drift = invalid_copy()
        workspace_graph_set_drift["workspace_context"]["data"]["default_graph_set_id"] = "graph-set-other"
        entity_envelope_drift = invalid_copy()
        entity_envelope_drift["entities_read"]["data"]["source_signature"] = "source-signature-other"
        statement_envelope_drift = invalid_copy()
        statement_envelope_drift["statements_read"]["response"]["data"]["model_name"] = "entity-list"
        entity_graph_drift = invalid_copy()
        entity_graph_drift["entities_read"]["data"]["items"][0]["source_graph_iri"] = graphs["asserted_ontology"]
        lineage_record_drift = invalid_copy()
        lineage_record_drift["statement_lineage"]["records"][0]["fact_id"] = "wrong"
        lineage_target_drift = invalid_copy()
        lineage_target_drift["statement_lineage"]["records"][0]["response"]["data"]["target"]["id"] = "wrong"
        for invalid, message in (
            (wrong_ontology, "identity drifts"),
            (count_drift, "count drifts"),
            (same_subject_missing_and_extra, "exactly equal"),
            (missing_provenance, "exact statement lineage"),
            (inventory_cursor, "batch inventory is incomplete"),
            (insufficient_capacity, "capacity is unknown or insufficient"),
            (false_envelope, "full successful MCP envelope"),
            (root_data, "full successful MCP envelope"),
            (extra_envelope, "full successful MCP envelope"),
            (inventory_mismatch, "inventory does not exactly match details"),
            (rejected_shape_counted, "applied attempt is invalid"),
            (graph_mismatch, "graph role"),
            (delta_hash_drift, "delta hash drifts"),
            (workspace_break, "workspace chain is not contiguous"),
            (bad_fact_id, "fact ID is invalid"),
            (delta_fact_drift, "relation payload does not match applied data"),
            (entity_iri_drift, "identity drifts"),
            (workspace_graph_set_drift, "does not bind the verified workspace"),
            (entity_envelope_drift, "does not bind the verified workspace"),
            (statement_envelope_drift, "does not bind the verified workspace"),
            (entity_graph_drift, "outside the asserted-data graph"),
            (lineage_record_drift, "statement lineage fact_id is invalid"),
            (lineage_target_drift, "statement lineage scope is invalid"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ProtocolRetrievalFallbackError, message):
                    verify_scoped_retrieval_fallback(invalid)

        boundary = invalid_copy()
        boundary_delta = boundary["batch_details"][0]["data"]["attempts"][1]["normalized_delta"]
        boundary_delta["inserts"].extend(
            quad("entity-source", f"extra-{index}", "entity-target-one", graphs["asserted_data"])
            for index in range(995)
        )
        boundary["batch_details"][0]["data"]["attempts"][1]["delta_hash"] = delta_hash(boundary_delta)
        hidden = statement("entity-source", "hidden", "entity-target-two")
        boundary["statements_read"]["response"]["data"]["items"].append(hidden)
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "capacity is unknown or insufficient"):
            verify_scoped_retrieval_fallback(boundary)

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
                    baseline["files"]["protocol_retrieval_verifier"],
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
                            "verify_scoped_retrieval_fallback",
                            "write_candidate_item_evidence_map",
                        ],
                    },
                )
                self.assertEqual(
                    baseline["files"]["protocol_reasoner_script"],
                    digest_file(root / "backend/scripts/dev_owl_reasoner.py"),
                )
                self.assertEqual(
                    baseline["runtime_contract"]["protocol_mcp_mode_env"],
                    {
                        "SEMANTIC_CANONICAL_STORE": "rdf",
                        "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                        "SEMANTIC_READ_MODE": "canonical",
                    },
                )
                self.assertEqual(
                    baseline["runtime_contract"]["protocol_mcp_reasoner_env"],
                    {
                        "SEMANTIC_REASONER_COMMAND": "/backend/scripts/dev_owl_reasoner.py",
                        "PATH": "/backend/.venv/bin:/usr/bin:/bin",
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
                self.assertEqual(adapter.started, ["coordinator", "modeling", "protocol"])
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
            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
                ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")
            ledger = self._ledger(Path(directory) / "fresh")
            ledger.reserve("run-one", "baseline-one", "2026-07-31T10:00:00+00:00")
            ledger.mark_semantic_start("run-one")
            ledger.terminal_failure("run-one", "runtime/infrastructure", False)
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
            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
                ledger.reserve("run-three-wrong-baseline", "wrong-baseline", "2026-07-31T10:00:00+00:00")

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

            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
                ledger.reserve("run-eleven-without-repair", "baseline-eleven", "2026-07-31T10:00:00+00:00")
            ledger.authorize_repair("run-ten", "tested tenth repair", "baseline-eleven")
            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
                ledger.reserve("run-eleven-wrong-baseline", "wrong-baseline", "2026-07-31T10:00:00+00:00")
            with self.assertRaisesRegex(TeamConfigurationError, "20-minute"):
                ledger.reserve("run-eleven-expired", "baseline-eleven", "2026-07-31T09:39:00+00:00")
            ledger.reserve("run-eleven", "baseline-eleven", "2026-07-31T10:00:00+00:00")

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
            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
                ledger.reserve("run-two", "baseline-two", "2026-07-31T10:00:00+00:00")

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
            with self.assertRaisesRegex(TeamConfigurationError, "tested repair"):
                ledger.authorize_repair("run-one", "focused evidence", "")
            ledger.authorize_repair("run-one", "focused evidence", "baseline-two")
            with self.assertRaisesRegex(TeamConfigurationError, "next start"):
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
                    with self.assertRaisesRegex(TeamConfigurationError, "immutable"):
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
            self.assertEqual(sorted(rebind_outcomes), ["authorized", "rejected"])

    def test_cli_host_auth_preflight_precedes_prepare_and_has_no_run_side_effect(self) -> None:
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
                patch.object(CodexRuntimeAdapter, "preflight_host_auth", side_effect=CodexRuntimeError("missing auth")),
                patch.object(TeamRunner, "prepare", side_effect=AssertionError("prepare must not run")),
                patch.object(team_main, "_bootstrap_helpers", side_effect=AssertionError("bootstrap must not run")),
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
            terminal_results={role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol")},
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
            "candidate_required_assertions": "modeling_team/references/candidate-required-assertions-v1.json",
            "native_retrieval_proof": "modeling_team/references/native-retrieval-proof-v1.json",
            "p2_monitor_contract": "modeling_team/references/p2-monitor-contract.json",
        }.items():
            self.assertEqual(manifest["files"][name], digest_file(root / relative))
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

        reasoner = root / "backend/scripts/dev_owl_reasoner.py"

        def changed_reasoner_digest(path: Path) -> str:
            return "e" * 64 if path == reasoner else original_digest(path)

        with patch("modeling_team.runner.digest_file", side_effect=changed_reasoner_digest):
            changed_reasoner_manifest, changed_reasoner_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=manifest["run_id"],
                profile_path=profile,
                task_path=task,
            )
        self.assertNotEqual(
            changed_reasoner_manifest["files"]["protocol_reasoner_script"],
            manifest["files"]["protocol_reasoner_script"],
        )
        self.assertNotEqual(changed_reasoner_hash, baseline_hash)

        with patch(
            "modeling_team.runner.protocol_mcp_reasoner_contract",
            return_value={
                "SEMANTIC_REASONER_COMMAND": "/backend/scripts/other.py",
                "PATH": "/backend/.venv/bin:/usr/bin:/bin",
            },
        ):
            changed_reasoner_contract_manifest, changed_reasoner_contract_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=manifest["run_id"],
                profile_path=profile,
                task_path=task,
            )
        self.assertNotEqual(changed_reasoner_contract_manifest["runtime_contract"], manifest["runtime_contract"])
        self.assertNotEqual(changed_reasoner_contract_hash, baseline_hash)

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
                terminal_results={role: {"status": "completed", "summary": "credential-canary-should-not-persist"} for role in ("coordinator", "modeling", "protocol")},
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
                {role: "completed" for role in ("coordinator", "modeling", "protocol")},
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
                terminal_results={role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol")},
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
                    for role in ("coordinator", "modeling", "protocol")
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
                "terminal_results": results or {role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol")},
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
                        "terminal_statuses": {role: "completed" for role in ("coordinator", "modeling", "protocol")},
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
                json.dumps(state({"coordinator": {"status": "completed"}, "modeling": {"status": "completed"}, "protocol": {"status": "blocked"}})),
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
            statuses = {role: {"status": "completed", "summary": "state may retain details"} for role in ("coordinator", "modeling", "protocol")}
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
                    "terminal_statuses": {role: "completed" for role in ("coordinator", "modeling", "protocol")},
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
