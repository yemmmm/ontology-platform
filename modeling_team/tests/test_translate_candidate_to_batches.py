"""Golden-fixture test for translate_candidate_to_batches (R2.3-005 systemic fix).

The candidate -> platform-batch translation is deterministic mechanics that the
Protocol LLM previously hand-translated with run-to-run variance (start52 used
create_relation_type for an object predicate; start54 dropped the candidate
entity_id/property_id binding and produced UUID IRIs).  This test pins the
deterministic tool against start53's actually-applied golden batches so the two
classes of regression cannot silently return.

The golden batches live in a gitignored workspace run directory; when those
fixtures are absent the test skips instead of failing, so it remains authoritative
in any checkout that has the start53 evidence on disk.
"""

from __future__ import annotations

import glob
import json
import unittest
from typing import Any

from modeling_team.contracts import repository_root
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    translate_candidate_to_batches,
)

CANDIDATE_PATH = (
    repository_root()
    / "modeling_team/.continuations/r23005-start24-r3-exact-candidate.json"
)
GOLDEN_RESPONSES_DIR = (
    repository_root()
    / "workspaces/modeling-runs/r23005-real-20260807-deepseek-start53"
    / "evidence/platform-responses"
)
PLATFORM_IRI_BASE = "http://ontology-platform.local/semantic"

# Golden stage suffix -> plan stage_kind.  The start53 batch ids look like
# ``r23005-cba-stage{N}-{suffix}-apply``; only the suffix is needed to align a
# golden apply batch with the deterministic plan stage.
_GOLDEN_SUFFIX_TO_STAGE = {
    "classes": "class",
    "properties": "property",
    "entities": "entity",
    "relations": "relation",
    "shape": "shape",
}
_STAGE_TO_COMMAND = {
    "class": "create_class",
    "property": "create_property",
    "entity": "create_entity",
    "relation": "create_relation",
    "shape": "create_shape",
}
_COMMAND_RESOURCE_FIELD = {
    "create_class": "class_id",
    "create_property": "property_id",
    "create_entity": "entity_id",
    "create_shape": "shape_id",
}
_COMMAND_RESOURCE_KIND = {
    "create_class": "class",
    "create_property": "property",
    "create_entity": "entity",
    "create_shape": "shape",
}


def _extract_payload(envelope: Any) -> dict[str, Any] | None:
    """Return the ``{ok, data}`` payload carried by a platform-response file."""
    if not isinstance(envelope, dict):
        return None
    structured = envelope.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("data"), dict):
        return structured
    content = envelope.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                try:
                    parsed = json.loads(item["text"])
                except (TypeError, ValueError):
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
                    return parsed
    return None


def _load_golden_apply_batches() -> dict[str, dict[str, Any]]:
    """Return golden apply batches keyed by plan stage_kind."""
    batches: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(GOLDEN_RESPONSES_DIR / "*.json"))):
        with open(path) as handle:
            envelope = json.load(handle)
        payload = _extract_payload(envelope)
        if not payload or payload.get("ok") is not True:
            continue
        data = payload["data"]
        if data.get("mode") != "apply_atomic" or data.get("attempt_status") != "applied":
            continue
        client_batch_id = data.get("client_batch_id")
        if not isinstance(client_batch_id, str):
            continue
        stage = None
        for suffix, candidate_stage in _GOLDEN_SUFFIX_TO_STAGE.items():
            if f"-{suffix}-" in client_batch_id or client_batch_id.endswith(f"-{suffix}"):
                stage = candidate_stage
                break
        if stage is None:
            continue
        batches[stage] = data
    return batches


class TranslateCandidateToBatchesGoldenTest(unittest.TestCase):
    """Assert the deterministic plan reproduces start53's golden apply batches."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CANDIDATE_PATH.exists():
            raise unittest.SkipTest(f"start53 candidate fixture absent: {CANDIDATE_PATH}")
        if not GOLDEN_RESPONSES_DIR.exists():
            raise unittest.SkipTest(
                f"start53 golden responses directory absent: {GOLDEN_RESPONSES_DIR}"
            )
        cls.golden = _load_golden_apply_batches()
        if set(cls.golden) != set(_GOLDEN_SUFFIX_TO_STAGE.values()):
            raise unittest.SkipTest(
                f"start53 golden apply batches incomplete: {sorted(cls.golden)}"
            )
        with open(CANDIDATE_PATH) as handle:
            continuation = json.load(handle)
        candidate = continuation.get("candidate")
        if not isinstance(candidate, dict):
            raise unittest.SkipTest("start53 continuation has no candidate envelope")
        cls.candidate = candidate
        cls.plan = translate_candidate_to_batches(candidate)

    def test_stage_order_matches_cross_batch_dependency_contract(self) -> None:
        self.assertEqual(
            self.plan["stage_order"],
            ["class", "property", "entity", "relation", "shape"],
        )
        self.assertEqual(
            [batch["stage_kind"] for batch in self.plan["batches"]],
            ["class", "property", "entity", "relation", "shape"],
        )

    def test_no_conflicts_or_untranslatable_items(self) -> None:
        self.assertEqual(
            self.plan["conflicts"], [], "expected a conflict-free golden translation"
        )

    def test_plan_client_item_ids_track_candidate_item_ids(self) -> None:
        """client_item_id is the deterministic candidate correlation handle.

        start53's LLM hand-translation was inconsistent: it used the candidate
        item_id for most items but the semantic.entity_id for one explicit_unknown
        (``unknown-cross-release-meaning`` -> ``unknown-cross-release-output-meaning``).
        The deterministic tool always uses the candidate item_id so every plan item
        maps 1:1 to a candidate item; the platform identity is carried by the
        resource_id in the payload, which is matched against golden separately.
        """
        plan_ids = {
            item["client_item_id"]
            for batch in self.plan["batches"]
            for item in batch["items"]
        }
        candidate_ids = {
            item["item_id"]
            for item in self.candidate["items"]
            if item["item_kind"]
            not in {"consumer_query", "negative_probe"}
        }
        self.assertEqual(plan_ids, candidate_ids)

    def test_each_stage_resource_ids_match_golden(self) -> None:
        """The actual platform identity (resource_id) must match start53 per stage."""
        for stage, golden_batch in self.golden.items():
            plan_batch = next(
                batch for batch in self.plan["batches"] if batch["stage_kind"] == stage
            )
            command = _STAGE_TO_COMMAND[stage]
            golden_resource_ids = {
                item.get("resource_outputs", {}).get("resource_id")
                for item in golden_batch["items"]
                if isinstance(item, dict) and item.get("resource_outputs")
            }
            if command in _COMMAND_RESOURCE_FIELD:
                resource_field = _COMMAND_RESOURCE_FIELD[command]
                plan_resource_ids = {
                    item["payload"][resource_field] for item in plan_batch["items"]
                }
                self.assertEqual(
                    plan_resource_ids,
                    golden_resource_ids,
                    f"stage {stage} resource_id drift",
                )
            else:
                # create_relation carries no resource_outputs; triples are asserted separately.
                self.assertEqual(len(plan_batch["items"]), len(golden_batch["items"]))

    def test_command_kind_per_stage_and_item_envelope(self) -> None:
        for batch in self.plan["batches"]:
            command = _STAGE_TO_COMMAND[batch["stage_kind"]]
            for item in batch["items"]:
                self.assertEqual(item["command_kind"], command)
                self.assertIn("client_item_id", item)
                self.assertIsInstance(item["payload"], dict)
                self.assertIsInstance(item["evidence"], list)
                for citation in item["evidence"]:
                    self.assertEqual(set(citation), {"document_name", "excerpt"})

    def test_create_payloads_bind_candidate_ids_to_readable_resource_iris(self) -> None:
        """Every create_* carries the candidate ID; IRIs are readable, not UUIDs (start54 regression)."""
        for batch in self.plan["batches"]:
            command = _STAGE_TO_COMMAND[batch["stage_kind"]]
            if command not in _COMMAND_RESOURCE_FIELD:
                continue
            golden_batch = self.golden[batch["stage_kind"]]
            golden_outputs = {
                item.get("resource_outputs", {}).get("resource_id"): item.get("resource_outputs")
                for item in golden_batch["items"]
                if isinstance(item, dict) and item.get("resource_outputs")
            }
            resource_field = _COMMAND_RESOURCE_FIELD[command]
            resource_kind = _COMMAND_RESOURCE_KIND[command]
            for item in batch["items"]:
                resource_id = item["payload"][resource_field]
                expected_iri = f"{PLATFORM_IRI_BASE}/{resource_kind}/{resource_id}"
                outputs = golden_outputs[resource_id]
                self.assertIsNotNone(outputs, f"resource_id {resource_id} absent from golden")
                assert outputs is not None  # for the type checker
                self.assertEqual(
                    outputs["resource_id"],
                    resource_id,
                    f"{item['client_item_id']} candidate resource_id drift",
                )
                self.assertEqual(
                    outputs["resource_iri"],
                    expected_iri,
                    f"{item['client_item_id']} IRI is not readable/deterministic",
                )

    def test_object_predicates_use_create_property_with_object_class_id(self) -> None:
        property_batch = next(b for b in self.plan["batches"] if b["stage_kind"] == "property")
        declared = {
            item["semantic"]["predicate"]: item["semantic"]
            for item in self.candidate["items"]
            if item["item_kind"] == "predicate"
        }
        seen_relation_predicates: set[str] = set()
        for item in property_batch["items"]:
            self.assertEqual(item["command_kind"], "create_property")
            payload = item["payload"]
            predicate_name = payload["property_id"]
            semantic = declared[predicate_name]
            if semantic["predicate_kind"] == "relation":
                seen_relation_predicates.add(predicate_name)
                self.assertIn("object_class_id", payload, f"{predicate_name} must be ObjectProperty")
                self.assertEqual(payload["object_class_id"], semantic["range"])
                self.assertNotIn("datatype", payload, f"{predicate_name} must not carry a datatype")
            else:
                self.assertIn("datatype", payload, f"{predicate_name} must be DatatypeProperty")
                self.assertNotIn(
                    "object_class_id", payload, f"{predicate_name} must not be ObjectProperty"
                )
        # Every relation predicate declared in the candidate is emitted via create_property.
        declared_relation_predicates = {
            name for name, semantic in declared.items() if semantic["predicate_kind"] == "relation"
        }
        self.assertEqual(seen_relation_predicates, declared_relation_predicates)

    def test_relation_triples_match_golden_normalized_delta_inserts(self) -> None:
        relation_batch = next(b for b in self.plan["batches"] if b["stage_kind"] == "relation")
        golden = self.golden["relation"]
        golden_triples = {
            (quad[0], quad[1], quad[2])
            for quad in golden["normalized_delta"]["inserts"]
            if isinstance(quad, list) and len(quad) >= 3
        }
        plan_triples = set()
        for item in relation_batch["items"]:
            self.assertEqual(item["command_kind"], "create_relation")
            payload = item["payload"]
            triple = (
                f"<{payload['source_entity_iri']}>",
                f"<{payload['relation_type_iri']}>",
                f"<{payload['target_entity_iri']}>",
            )
            plan_triples.add(triple)
        self.assertEqual(
            plan_triples,
            golden_triples,
            "relation statement triples do not match start53 applied deltas",
        )
        self.assertEqual(len(plan_triples), len(relation_batch["items"]))

    def test_relation_predicates_resolve_to_property_resource_iris(self) -> None:
        """The start52 regression: relation_type_iri must be /property/{id}, never /relation-type/."""
        relation_batch = next(b for b in self.plan["batches"] if b["stage_kind"] == "relation")
        for item in relation_batch["items"]:
            relation_type_iri = item["payload"]["relation_type_iri"]
            self.assertTrue(
                relation_type_iri.startswith(f"{PLATFORM_IRI_BASE}/property/"),
                f"relation predicate must resolve to /property/: {relation_type_iri}",
            )
            self.assertNotIn("/relation-type/", relation_type_iri)

    def test_consumer_queries_and_negative_probes_emit_no_create_items(self) -> None:
        plan_ids = {
            item["client_item_id"]
            for batch in self.plan["batches"]
            for item in batch["items"]
        }
        for item in self.candidate["items"]:
            if item["item_kind"] in {"consumer_query", "negative_probe"}:
                self.assertNotIn(item["item_id"], plan_ids)

    def test_explicit_unknown_items_materialize_as_create_entity(self) -> None:
        entity_batch = next(b for b in self.plan["batches"] if b["stage_kind"] == "entity")
        plan_entity_ids = {
            item["payload"]["entity_id"] for item in entity_batch["items"]
        }
        for item in self.candidate["items"]:
            if item["item_kind"] == "explicit_unknown":
                self.assertIn(
                    item["semantic"]["entity_id"],
                    plan_entity_ids,
                    "explicit_unknown must materialize as create_entity",
                )

    def test_shape_path_id_is_predicate_resource_id_not_local_path_id(self) -> None:
        """The compiler resolves /property/{path_id}; path_id must be the predicate, not the local id."""
        shape_batch = next(
            (b for b in self.plan["batches"] if b["stage_kind"] == "shape"), None
        )
        if shape_batch is None:
            self.skipTest("candidate has no shape stage")
        declared_paths = {
            path["predicate"]: path
            for item in self.candidate["items"]
            if item["item_kind"] == "shape"
            for path in item["semantic"].get("paths", [])
        }
        for item in shape_batch["items"]:
            for constraint in item["payload"]["constraints"]:
                self.assertIn(
                    constraint["path_id"],
                    declared_paths,
                    f"shape path_id {constraint['path_id']} is not a declared predicate",
                )


class TranslateCandidateToBatchesContractTest(unittest.TestCase):
    """Pure-function contract checks that do not depend on the start53 workspace."""

    def _example_candidate(self) -> dict[str, Any]:
        return {
            "candidate_kind": "platform-neutral-candidate-v2",
            "candidate_revision": "contract-example-1",
            "scope": {"name": "contract-example"},
            "constraints": ["One declared path."],
            "items": [
                {
                    "item_id": "class-a",
                    "item_kind": "class",
                    "semantic": {"class_id": "ClassA", "description": "root"},
                },
                {
                    "item_id": "class-b",
                    "item_kind": "class",
                    "semantic": {"class_id": "ClassB", "superclass": "ClassA"},
                },
                {
                    "item_id": "predicate-fact",
                    "item_kind": "predicate",
                    "semantic": {
                        "predicate": "label",
                        "predicate_kind": "fact",
                        "domain": "ClassA",
                        "range": "string",
                    },
                },
                {
                    "item_id": "predicate-rel",
                    "item_kind": "predicate",
                    "semantic": {
                        "predicate": "refersTo",
                        "predicate_kind": "relation",
                        "domain": "ClassA",
                        "range": "ClassB",
                    },
                },
                {
                    "item_id": "entity-a",
                    "item_kind": "entity",
                    "semantic": {
                        "entity_id": "a",
                        "class": "ClassA",
                        "values": {"label": "Instance A", "refersTo": "b"},
                    },
                    "evidence_citations": [
                        {"document_name": "doc.md", "excerpt": "supports A"}
                    ],
                },
            ],
        }

    def test_rejects_non_platform_neutral_candidate(self) -> None:
        with self.assertRaises(ProtocolRetrievalFallbackError):
            translate_candidate_to_batches({"candidate_kind": "other"})

    def test_does_not_mutate_caller_candidate(self) -> None:
        candidate = self._example_candidate()
        snapshot = json.loads(json.dumps(candidate))
        translate_candidate_to_batches(candidate)
        self.assertEqual(candidate, snapshot)

    def test_empty_stage_is_omitted_and_evidence_carried(self) -> None:
        plan = translate_candidate_to_batches(self._example_candidate())
        stages = [batch["stage_kind"] for batch in plan["batches"]]
        self.assertEqual(stages, ["class", "property", "entity"])
        entity_item = next(
            item
            for batch in plan["batches"]
            for item in batch["items"]
            if item["client_item_id"] == "entity-a"
        )
        self.assertEqual(
            entity_item["evidence"], [{"document_name": "doc.md", "excerpt": "supports A"}]
        )

    def test_untranslatable_items_collect_conflicts_without_emitting(self) -> None:
        candidate = self._example_candidate()
        candidate["items"].append(
            {
                "item_id": "broken-relation",
                "item_kind": "relation",
                "semantic": {
                    "relation_id": "broken",
                    "predicate": "refersTo",
                    "subject": "missing-subject",
                    "object": "b",
                },
            }
        )
        candidate["items"].append(
            {"item_id": "unknown-kind", "item_kind": "mystery", "semantic": {"x": 1}}
        )
        plan = translate_candidate_to_batches(candidate)
        codes = {conflict["code"] for conflict in plan["conflicts"]}
        self.assertIn("unbound_relation_subject", codes)
        self.assertIn("unsupported_item_kind", codes)
        plan_ids = {
            item["client_item_id"]
            for batch in plan["batches"]
            for item in batch["items"]
        }
        self.assertNotIn("broken-relation", plan_ids)
        self.assertNotIn("unknown-kind", plan_ids)


if __name__ == "__main__":
    unittest.main()
