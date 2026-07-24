#!/usr/bin/env python3
"""Focused offline contract tests for the M2 rehearsal package."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
RUNNER_PATH = PACKAGE / "run_rehearsal.py"
SPEC = importlib.util.spec_from_file_location("m2_rehearsal", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class M2ScenarioContractTest(unittest.TestCase):
    def test_constrained_predicates_are_properties_and_shape_paths_reference_them(self) -> None:
        items = RUNNER.tbox_and_shapes_items(["evidence"])
        by_id = {entry["client_item_id"]: entry for entry in items}
        for predicate, (_domain, target) in RUNNER.OBJECT_PROPERTIES.items():
            with self.subTest(predicate=predicate):
                entry = by_id[predicate]
                self.assertEqual(entry["command_kind"], "create_property")
                self.assertIn("object_class_id", entry["payload"])
                self.assertEqual(entry["payload"]["object_class_id"]["item_ref"]["client_item_id"], target)
        self.assertEqual(RUNNER.OBJECT_PROPERTIES["previous_version"], ("change_set", "workflow_version"))
        # ChangeSet inherits the publication-bearing class through its explicit parent.
        self.assertEqual(by_id["change_set"]["payload"]["parent_class_ids"], [{"item_ref": {"client_item_id": "publication_state_bearing", "output": "resource_id"}}])
        constraints = [
            constraint
            for entry in items
            if entry["command_kind"] == "create_shape"
            for constraint in entry["payload"]["constraints"]
        ]
        paths = {constraint["path_id"]["item_ref"]["client_item_id"] for constraint in constraints}
        self.assertIn("invokes_tool", paths)
        self.assertIn("call_site_location", paths)
        change_shape = by_id["change-shape"]["payload"]["constraints"]
        change_paths = {constraint["path_id"]["item_ref"]["client_item_id"] for constraint in change_shape}
        self.assertTrue({"previous_version", "publication_state", "change_applies_to_version", "deletes_variable"} <= change_paths)
        self.assertTrue(paths <= set(RUNNER.OBJECT_PROPERTIES) | set(RUNNER.DATATYPE_PROPERTIES))

    def test_fixture_relations_use_property_iris_and_entity_refs(self) -> None:
        iris = {key: f"https://example.test/property/{key}" for key in RUNNER.OBJECT_PROPERTIES}
        iris.update({key: f"https://example.test/property/{key}" for key in RUNNER.DATATYPE_PROPERTIES})
        iris.update({key: f"https://example.test/class/{key}" for key in {
            "workflow", "workflow_version", "published_workflow_version", "workflow_tool", "tool_invocation", "variable", "variable_binding", "variable_use", "change_set", "explicit_gap_component"
        }})
        relations = [entry for entry in RUNNER.published_fixture_items(iris, ["evidence"]) if entry["command_kind"] == "create_relation"]
        self.assertGreater(len(relations), 10)
        for relation in relations:
            payload = relation["payload"]
            self.assertIn(payload["relation_type_iri"], {iris[key] for key in RUNNER.OBJECT_PROPERTIES})
            self.assertIn("item_ref", payload["source_entity_iri"])
            self.assertIn("item_ref", payload["target_entity_iri"])
        by_id = {entry["client_item_id"]: entry for entry in RUNNER.published_fixture_items(iris, ["evidence"])}
        self.assertEqual(by_id["published-delete-quality"]["payload"]["properties"][iris["publication_state"]], "latest")
        self.assertEqual(by_id["rel-published-delete-quality-previous_version-c-v1"]["payload"]["target_entity_iri"]["item_ref"]["client_item_id"], "c-v1")
        self.assertNotIn("rel-c-v2-previous_version-c-v1", by_id)
        self.assertEqual(by_id["rel-c-content-declared_by_version-c-v2"]["payload"]["target_entity_iri"]["item_ref"]["client_item_id"], "c-v2")
        published_iris = {name: f"https://example.test/entity/{name}" for name in ("c", "c-v2", "c-quality-score")}
        draft = {
            entry["client_item_id"]: entry
            for entry in RUNNER.draft_fixture_items(iris, ["evidence"], published_iris)
        }
        self.assertEqual(draft["draft-delete-quality"]["payload"]["properties"][iris["publication_state"]], "current-draft")
        self.assertIn("rel-draft-delete-quality-previous_version-c-v2", draft)
        self.assertEqual(draft["rel-c-has_version-c-draft"]["payload"]["source_entity_iri"], published_iris["c"])
        self.assertIn("item_ref", draft["rel-c-has_version-c-draft"]["payload"]["target_entity_iri"])
        self.assertIn("item_ref", draft["rel-c-draft-version_of-c"]["payload"]["source_entity_iri"])
        self.assertEqual(draft["rel-c-draft-version_of-c"]["payload"]["target_entity_iri"], published_iris["c"])
        self.assertEqual(draft["rel-draft-delete-quality-previous_version-c-v2"]["payload"]["target_entity_iri"], published_iris["c-v2"])
        self.assertEqual(draft["rel-draft-delete-quality-deletes_variable-c-quality-score"]["payload"]["target_entity_iri"], published_iris["c-quality-score"])

    def test_scoped_query_contract_requires_one_or_more_call_chain_and_every_context_link(self) -> None:
        iris = {key: f"https://example.test/property/{key}" for key in (*RUNNER.OBJECT_PROPERTIES, *RUNNER.DATATYPE_PROPERTIES)}
        entities = {key: f"https://example.test/entity/{key}" for key in ("a", "b", "c", "c-v1", "c-v2", "c-content", "c-quality-score", "b-v1", "a-v1", "tool-c", "tool-b", "b-c-invocation", "a-b-invocation", "b-content-binding", "b-content-source", "b-quality-binding", "b-quality-score", "b-if-use", "b-approved-content", "a-approved-binding", "a-publish-content", "a-publish-use", "published-delete-quality")}
        queries = RUNNER.scoped_query_texts(iris, entities)
        self.assertIn(")+ <https://example.test/entity/c-v2>", queries["callers"])
        self.assertNotIn(")* <https://example.test/entity/c-v2>", queries["callers"])
        for predicate in ("change_applies_to_version", "previous_version", "deletes_variable", "declared_by_version", "binding_at_invocation", "binding_source", "binding_target", "has_use", "uses_variable", "produces_variable", "call_site_id", "call_site_location"):
            self.assertIn(iris[predicate], queries["context"])
        for entity in entities.values():
            self.assertIn(entity, queries["context"])

    def test_no_bypass_route_or_secret_persistence_is_in_the_executable_candidate(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"/api/semantic/edits"', source)
        self.assertNotIn("datasets:load", source)
        self.assertNotIn("validate=false", source)
        self.assertIn('"/api/semantic/graph-sets/{graph_set_id}/validation-runs"', source)
        self.assertIn('member.get("role") == "shapes"', source)
        self.assertIn("shape_graph_iris", source)
        safe = RUNNER._safe({"Authorization": "secret", "lease_token": "lease", "ok": "kept"})
        self.assertEqual(safe, {"Authorization": "[redacted]", "lease_token": "[redacted]", "ok": "kept"})
        self.assertNotIn("api_key", json.dumps(safe).lower())
        self.assertIn("model_contract", source)
        self.assertIn("fixture_evidence_ids", source)
        self.assertIn("_append_failure_log", source)
        self.assertIn("_write_runtime_record(record)", source)
        self.assertIn("runtime-record-{record['run_tag']}.json", source)
        self.assertIn("corrects_run_tag", source)
        self.assertIn("_batch_trace", source)

    def test_invalid_candidates_are_dry_run_only_in_execution_path(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        invalid_line = next(line for line in source.splitlines() if '"invalid-invocation", "dry_run"' in line)
        bad_line = next(line for line in source.splitlines() if '"bad-shape", "dry_run"' in line)
        self.assertIn('"dry_run"', invalid_line)
        self.assertIn('"dry_run"', bad_line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
