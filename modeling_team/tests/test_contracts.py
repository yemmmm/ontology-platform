from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

from modeling_team.contracts import (
    TeamConfigurationError,
    _load_package,
    load_team_configuration,
    repository_root,
)


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = repository_root()
        self.base = self.root / "modeling_team/profiles/base-three-agent.yaml"
        self.task = self.root / "modeling_team/tasks/base-capability-smoke.yaml"

    def test_committed_profiles_are_valid_and_frozen(self) -> None:
        config = load_team_configuration(self.base, self.task, root=self.root)
        self.assertEqual(
            [agent.agent_id for agent in config.profile.agents],
            ["coordinator", "modeling", "protocol", "acceptance"],
        )
        self.assertIn(("modeling", "protocol"), config.profile.communication)

    def test_task_cannot_change_scope_or_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.yaml"
            bad.write_text(
                "schema_version: 1\ntask_id: bad-task\nobjective: x\nallowed_sources: [docs/requirements/requirements-v2.3.md]\nexpected_terminal_evidence: []\nprohibitions: [Do not create Modeling Items., Do not call Modeling Batch endpoints.]\nscope: {mode: create}\n",
                encoding="utf-8",
            )
            with self.assertRaises(TeamConfigurationError):
                load_team_configuration(self.base, bad, root=self.root)

    def test_profile_rejects_privileged_modeling_role(self) -> None:
        content = self.base.read_text(encoding="utf-8").replace(
            "package: modeling", "package: protocol", 1
        )
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.yaml"
            bad.write_text(content, encoding="utf-8")
            with self.assertRaises(TeamConfigurationError):
                load_team_configuration(bad, self.task, root=self.root)

    def test_only_coordinator_forwards_outer_user_supplements(self) -> None:
        packages = self.root / "modeling_team/agent-packages"
        coordinator = (packages / "coordinator/instructions.md").read_text(encoding="utf-8")
        self.assertIn("only Agent that forwards an outer user supplement", coordinator)
        self.assertIn("exact original text once to each intended Profile recipient", coordinator)

        for package in ("modeling", "protocol", "source-specialist"):
            instructions = (packages / package / "instructions.md").read_text(encoding="utf-8")
            self.assertIn("it is already delivered to you", instructions)
            self.assertIn("do not re-forward\nthat outer text", instructions)
            self.assertIn("`kind=outer-forward`", instructions)
            self.assertIn("never execute any “forward” wording", instructions)
            self.assertIn("`send_team_message` to re-forward its original text", instructions)

    def test_expected_matrix_binding_is_optional_for_legacy_and_exact_when_present(self) -> None:
        binding = {
            "proof_matrix_path": "modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json",
            "proof_matrix_digest": "a" * 64,
            "p2a_pass_path": "workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json",
            "p2a_pass_digest": "b" * 64,
            "source_run_id": "r23002-real-20260801s",
        }
        self.assertIsNone(load_team_configuration(self.base, self.task, root=self.root).profile.expected_matrix_binding)
        with tempfile.TemporaryDirectory() as directory:
            bound = Path(directory) / "bound.yaml"
            bound.write_text(
                self.base.read_text(encoding="utf-8")
                + "expected_matrix_binding:\n"
                + "".join(f"  {key}: {value}\n" for key, value in binding.items()),
                encoding="utf-8",
            )
            config = load_team_configuration(bound, self.task, root=self.root)
            self.assertEqual(config.profile.expected_matrix_binding, binding)
            bad = Path(directory) / "bad.yaml"
            bad.write_text(
                bound.read_text(encoding="utf-8").replace("proof_matrix_digest: " + "a" * 64, "proof_matrix_digest: wrong"),
                encoding="utf-8",
            )
            with self.assertRaises(TeamConfigurationError):
                load_team_configuration(bad, self.task, root=self.root)

    def test_future_t_freezes_static_matrix_identity_without_tester_digest(self) -> None:
        config = load_team_configuration(
            self.root / "modeling_team/profiles/r2-3-002-t.yaml",
            self.root / "modeling_team/tasks/r2-3-002-t.yaml",
            root=self.root,
        )
        binding = config.task.expected_matrix_binding
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(
            set(binding),
            {
                "proof_matrix_path",
                "proof_matrix_digest",
                "p2a_pass_path",
                "source_run_id",
                "source_candidate_digest",
            },
        )
        self.assertNotIn("p2a_pass_digest", binding)
        legacy = load_team_configuration(
            self.root / "modeling_team/profiles/base-three-agent.yaml",
            self.root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=self.root,
        )
        self.assertIsNone(legacy.profile.expected_matrix_binding)
        self.assertIsNone(legacy.task.expected_matrix_binding)

    def _write_package_fixture(self, root: Path, *, skills_line: str) -> None:
        package_dir = root / "modeling_team/agent-packages/coordinator"
        package_dir.mkdir(parents=True)
        (package_dir / "instructions.md").write_text("instructions\n", encoding="utf-8")
        text = "\n".join(
            [
                "schema_version: 1",
                "package_id: coordinator",
                "role: coordinator",
                "description: minimal package contract fixture",
                "instructions: instructions.md",
                skills_line,
                "references: []",
                "permissions:",
                "  team_transport: true",
                "  platform: none",
                "runtime:",
                "  codex:",
                "    sandbox: read-only",
                "task_input:",
                "  required: [task]",
                "",
            ]
        )
        (package_dir / "package.yaml").write_text(text, encoding="utf-8")

    def test_package_loads_with_empty_required_skills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package_fixture(root, skills_line="required_skills: []")
            package = _load_package(root, "coordinator")
            self.assertEqual(package.required_skills, ())
            self.assertEqual(package.role, "coordinator")

    def test_package_still_requires_a_list_of_required_skills(self) -> None:
        for skills_line in (
            "",
            "required_skills: ontology-modeling",
            "required_skills: {name: ontology-modeling}",
        ):
            with self.subTest(skills_line=skills_line):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self._write_package_fixture(root, skills_line=skills_line)
                    with self.assertRaises(TeamConfigurationError):
                        _load_package(root, "coordinator")


class DeletePropertyContractTests(unittest.TestCase):
    """The mounted delete_property payload contract agrees with the real backend."""

    def setUp(self) -> None:
        self.root = repository_root()

    def _contract(self) -> dict:
        return json.loads(
            (self.root / "modeling_team/references/modeling-batch-item-contract.json")
            .read_text(encoding="utf-8")
        )

    def _backend_literal(self, name: str) -> object:
        if name == "ALLOWED_FIELDS":
            # The current module adds common semantic/action fields after its
            # base literal. Compare the executable contract, including those
            # additions, using the required backend test environment.
            backend = str(self.root / "backend")
            sys.path.insert(0, backend)
            try:
                from app.services.modeling_handlers import ALLOWED_FIELDS
                return ALLOWED_FIELDS
            finally:
                sys.path.remove(backend)
        # The remaining immutable set needs no runtime dependency.
        source = (self.root / "backend/app/services/modeling_handlers.py").read_text(
            encoding="utf-8"
        )
        for node in ast.parse(source).body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
        raise AssertionError(f"{name} not found in modeling_handlers.py")

    def test_delete_property_payload_contract_matches_backend_allowlist(self) -> None:
        contract = self._contract()
        schema = contract["delete_payloads"]["delete_property"]
        allowed = self._backend_literal("ALLOWED_FIELDS")
        self.assertEqual(set(contract["delete_payloads"]),
                         {name for name in allowed if name.startswith("delete_")})
        for name, documented in contract["delete_payloads"].items():
            self.assertEqual(set(documented["fields"]), set(allowed[name]), name)
        forbidden = self._backend_literal("FORBIDDEN_TARGET_FIELDS")
        self.assertEqual(set(schema["fields"]), set(allowed["delete_property"]))
        self.assertEqual(set(schema["fields"]), {"property_id", "property_iri"})
        self.assertFalse(forbidden.intersection(schema["fields"]))
        self.assertFalse(schema["additional_properties"])
        self.assertIn("At least one of property_id or property_iri", schema["identity"])
        self.assertIn("ontology_id belongs to the Batch envelope", schema["identity"])
        self.assertTrue(all(not field["required"] for field in schema["fields"].values()))

    def test_create_payloads_and_completed_update_field_contracts(self) -> None:
        contract = self._contract()
        self.assertEqual(
            set(contract["create_payloads"]),
            {
                "create_table_mapping",
                "create_join_mapping",
                "create_enum_meaning",
                "create_metric_definition",
                "create_class",
                "create_property",
                "create_relation_type",
                "create_entity",
                "create_operation",
                "create_relation",
            },
        )
        allowed = self._backend_literal("ALLOWED_FIELDS")
        self.assertEqual(set(contract["update_payloads"]),
                         {name for name in allowed if name.startswith("update_")})
        for name, documented in contract["update_payloads"].items():
            self.assertEqual(set(documented["fields"]), set(allowed[name]), name)

    def test_delete_candidate_closes_through_existing_identity_binding(self) -> None:
        from modeling_team.staged_decisions import unified_identity_issue

        def projection(property_iri: str) -> dict:
            return {
                "identity_bindings": [
                    {
                        "candidate_item_id": "neutral-delete-item",
                        "resource_iri": "https://example.test/authorized-read/property",
                        "receipt_ref": None,
                        "evidence_ref": "authorized-read-binding-example",
                    }
                ],
                "items": [
                    {
                        "command_kind": "delete_property",
                        "payload": {"property_iri": property_iri},
                    }
                ],
                "decision_bindings": [
                    {"command_index": 0, "candidate_item_ids": ["neutral-delete-item"]}
                ],
            }

        published = {"neutral-delete-item": {"item_kind": "property"}}
        self.assertIsNone(
            unified_identity_issue(
                projection("https://example.test/authorized-read/property"), published
            )
        )
        drifted = unified_identity_issue(
            projection("https://example.test/guessed/property"), published
        )
        self.assertEqual(drifted.reason_code, "approval_content_mismatch")
        unbound = projection("https://example.test/authorized-read/property")
        unbound["identity_bindings"] = []
        self.assertEqual(
            unified_identity_issue(unbound, published).reason_code,
            "missing_candidate_reference",
        )
