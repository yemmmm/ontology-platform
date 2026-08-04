from __future__ import annotations

import copy
import json
import re
import unittest
from types import SimpleNamespace
from typing import Any

from modeling_team.contracts import load_formal_team_configuration, repository_root
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_receipt,
)
from modeling_team.runner import TeamRunner


STRUCTURAL_FIXTURE = "modeling_team/tests/fixtures/r23005-neutral-candidate-authoring-fixtures.json"
NEUTRAL_REFERENCE = "modeling_team/references/platform-neutral-candidate-authoring.json"
NEUTRAL_FIELDS = {
    "candidate_kind",
    "candidate_revision",
    "scope",
    "constraints",
    "items",
}


class CandidateAuthoringError(ValueError):
    """Offline authoring-check failure used by the C99-C104 fixtures."""


def _fixture_candidate(revision: str) -> dict[str, Any]:
    """Read one immutable, production-shaped neutral fixture without workspace dependencies."""

    root = repository_root()
    fixtures = json.loads((root / STRUCTURAL_FIXTURE).read_text(encoding="utf-8"))
    fixture_key = {
        "cba-slice-r1": "r1",
        "cba-slice-r2": "r2",
        "neutral-r1": "r1",
        "neutral-r2": "r2",
    }.get(revision)
    if fixture_key is None:
        raise AssertionError(f"structural fixture candidate {revision!r} is missing")
    return copy.deepcopy(fixtures[fixture_key])


def _mechanically_correct_r2(candidate: dict[str, Any]) -> dict[str, Any]:
    """Apply only the mechanical envelope repair; semantic closure remains unresolved."""

    corrected = copy.deepcopy(candidate)
    corrected["constraints"] = [
        f"{constraint['id']}: {'; '.join(constraint['requirements'])}"
        for constraint in corrected["constraints"]
    ]
    # These are Team Transport metadata, not neutral semantic fields.
    corrected.pop("delivery_id", None)
    corrected.pop("reply_chain", None)
    return corrected


def _declare_r2_predicates(candidate: dict[str, Any]) -> None:
    """Make the retained candidate's missing predicate declarations explicit for the next gate."""

    vocabulary = candidate["vocabulary"]
    properties = vocabulary.setdefault("properties", [])
    declared = {entry.get("id") for entry in properties if isinstance(entry, dict)}
    for item in candidate["items"]:
        semantic = item.get("semantic", {})
        for predicate in semantic:
            if predicate not in declared:
                properties.append(
                    {
                        "id": predicate,
                        "domain": "NeutralSemanticItem",
                        "range": "string",
                        "cardinality": "optional",
                    }
                )
                declared.add(predicate)

    vocabulary["relations"] = [
        {
            "id": relation["predicate"],
            "domain": "NeutralSubject",
            "range": "NeutralSubject",
        }
        for relation in candidate["relations"]
    ]


def _declare_common_subject_range(candidate: dict[str, Any]) -> None:
    vocabulary = candidate["vocabulary"]
    classes = vocabulary["classes"]
    classes.append({"id": "UnknownAffectedSubject"})
    target_classes = {
        "item-neutral-dependency": "NeutralDependency",
        "item-neutral-left": "NeutralLeft",
        "item-neutral-right": "NeutralRight",
    }
    for class_id in set(target_classes.values()):
        next(entry for entry in classes if entry["id"] == class_id)[
            "superclass"
        ] = "UnknownAffectedSubject"

    affected_subject = next(
        entry for entry in vocabulary["properties"] if entry["id"] == "affectedSubject"
    )
    affected_subject["range"] = "UnknownAffectedSubject"
    affected_subject["target_class_bindings"] = target_classes


def _declare_shape_and_probe_paths(candidate: dict[str, Any]) -> None:
    vocabulary = candidate["vocabulary"]
    properties = {entry["id"] for entry in vocabulary["properties"]}
    if "invalidValue" not in properties:
        vocabulary["properties"].append(
            {
                "id": "invalidValue",
                "domain": "NeutralSubject",
                "range": "string",
                "cardinality": "optional",
            }
        )
    vocabulary["shapes"] = [
        {
            "id": "shape-neutral-subject",
            "target_class": "NeutralSubject",
            "paths": [
                {"path_id": "path-label", "predicate": "label", "range": "string"},
                {
                    "path_id": "path-affected-subject",
                    "predicate": "affectedSubject",
                    "range": "UnknownAffectedSubject",
                },
                {
                    "path_id": "path-invalid",
                    "predicate": "invalidValue",
                    "range": "string",
                },
            ],
        }
    ]
    candidate["negative_validation_probe"]["shape_id"] = "shape-neutral-subject"
    candidate["negative_validation_probe"]["path"] = "path-invalid"


def _validate_candidate_closure(candidate: dict[str, Any]) -> None:
    """Check the neutral checklist against a retained production-shaped candidate.

    This is deliberately test-local.  The production neutral mechanics remain unchanged and only
    validate the public receipt envelope; these checks model the authoring contract that precedes
    it.
    """

    if not isinstance(candidate.get("constraints"), list) or any(
        not isinstance(value, str) or not value.strip() for value in candidate["constraints"]
    ):
        raise CandidateAuthoringError("constraints must be a list of non-empty strings")
    items = candidate.get("items")
    if not isinstance(items, list) or not items:
        raise CandidateAuthoringError("items are empty")
    item_ids = [item.get("item_id") for item in items if isinstance(item, dict)]
    if len(item_ids) != len(set(item_ids)) or any(
        not isinstance(value, str) or not value for value in item_ids
    ):
        raise CandidateAuthoringError("item IDs are not unique")
    if any(
        not isinstance(item.get("item_kind"), str)
        or not item["item_kind"]
        or not isinstance(item.get("semantic"), dict)
        for item in items
    ):
        raise CandidateAuthoringError("item wrapper is invalid")

    vocabulary = candidate.get("vocabulary", {})
    relations = candidate.get("relations", [])
    declared_relations = {
        entry.get("id") for entry in vocabulary.get("relations", []) if isinstance(entry, dict)
    }
    for relation in relations:
        predicate = relation.get("predicate")
        if predicate not in declared_relations:
            raise CandidateAuthoringError(f"undeclared relation predicate: {predicate}")

    properties = {
        entry.get("id"): entry
        for entry in vocabulary.get("properties", [])
        if isinstance(entry, dict)
    }
    property_ids = [
        entry.get("id") for entry in vocabulary.get("properties", []) if isinstance(entry, dict)
    ]
    if len(property_ids) != len(set(property_ids)):
        raise CandidateAuthoringError("fact predicate is declared more than once")
    relation_ids = [
        entry.get("id") for entry in vocabulary.get("relations", []) if isinstance(entry, dict)
    ]
    if len(relation_ids) != len(set(relation_ids)):
        raise CandidateAuthoringError("relation predicate is declared more than once")
    for item in items:
        for predicate in item["semantic"]:
            if predicate not in properties:
                raise CandidateAuthoringError(f"undeclared fact predicate: {predicate}")
    affected_subject = properties.get("affectedSubject")
    if affected_subject is None:
        raise CandidateAuthoringError("affectedSubject predicate is undeclared")
    if affected_subject.get("range") in {"resource", "external", "external_placeholder"}:
        raise CandidateAuthoringError("heterogeneous object range is not closed")

    classes = {
        entry.get("id"): entry
        for entry in vocabulary.get("classes", [])
        if isinstance(entry, dict)
    }
    common = affected_subject.get("range")
    bindings = affected_subject.get("target_class_bindings")
    if not isinstance(bindings, dict):
        raise CandidateAuthoringError("heterogeneous object targets lack subclass bindings")
    for target, class_id in bindings.items():
        if class_id not in classes or classes[class_id].get("superclass") != common:
            raise CandidateAuthoringError(f"target binding is outside common superclass: {target}")
    affected_values = {
        item["semantic"]["affectedSubject"]
        for item in items
        if "affectedSubject" in item["semantic"]
    }
    if affected_values != set(bindings):
        raise CandidateAuthoringError("affectedSubject target bindings are incomplete")

    shapes = vocabulary.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        raise CandidateAuthoringError("Shape predicate/path declarations are missing")
    shape_ids = {shape.get("id") for shape in shapes}
    path_ids: set[str] = set()
    for shape in shapes:
        if shape.get("target_class") not in classes:
            raise CandidateAuthoringError("Shape target class is outside the candidate")
        for path in shape.get("paths", []):
            path_id = path.get("path_id")
            if path_id in path_ids:
                raise CandidateAuthoringError("Shape path is declared more than once")
            path_ids.add(path_id)
            if path.get("predicate") not in properties:
                raise CandidateAuthoringError("Shape path predicate is undeclared")

    probe = candidate.get("negative_validation_probe", {})
    if probe.get("shape_id") not in shape_ids or probe.get("path") not in path_ids:
        raise CandidateAuthoringError("negative-probe path is not closed")

    item_id_set = set(item_ids)
    for relation in relations:
        for field in ("from", "to", "evidence_item"):
            if relation.get(field) not in item_id_set:
                raise CandidateAuthoringError(f"relation reference is outside candidate: {field}")
    for dependency in candidate.get("dependencies", []):
        for field in ("from", "to"):
            if dependency.get(field) not in item_id_set:
                raise CandidateAuthoringError(f"dependency reference is outside candidate: {field}")


def _exact_protocol_receipt(
    candidate: dict[str, Any], calls: list[dict[str, Any]]
) -> dict[str, Any]:
    """Model Protocol's required order without changing the mechanics implementation."""

    calls.append(copy.deepcopy(candidate))
    return build_candidate_receipt(candidate)


class R23005CandidateAuthoringTests(unittest.TestCase):
    def test_c99_fixture_r1_rejects_the_public_item_wrapper(self) -> None:
        candidate = _fixture_candidate("cba-slice-r1")
        self.assertEqual(set(candidate["items"][0]), {"id", "type", "facts", "evidence_citations"})
        # The structural artifact is intentionally exercised unchanged first; its object constraints
        # are the earlier mechanical failure and must not hide the wrapper regression.
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "constraints"):
            build_candidate_receipt(candidate)
        wrapper_only = copy.deepcopy(candidate)
        wrapper_only["constraints"] = [
            f"{constraint['id']}: {'; '.join(constraint['requirements'])}"
            for constraint in wrapper_only["constraints"]
        ]
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "item_id"):
            build_candidate_receipt(wrapper_only)

    def test_c100_fixture_r2_is_complete_but_exact_receipt_rejects_object_constraints(
        self,
    ) -> None:
        candidate = _fixture_candidate("cba-slice-r2")
        item_ids = [item["item_id"] for item in candidate["items"]]
        self.assertGreaterEqual(len(item_ids), 3)
        self.assertEqual(len(item_ids), len(set(item_ids)))
        self.assertTrue(
            all(
                "semantic" in item and isinstance(item["semantic"], dict)
                for item in candidate["items"]
            )
        )
        self.assertTrue(all(isinstance(value, dict) for value in candidate["constraints"]))
        self.assertIn("dependencies", candidate)
        self.assertIn("consumer_queries", candidate)
        for patch_field in ("revision_basis", "revision_operation", "replace_item_id"):
            self.assertNotIn(patch_field, candidate)
        calls: list[dict[str, Any]] = []
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "constraints"):
            _exact_protocol_receipt(candidate, calls)
        self.assertEqual(calls, [candidate])

    def test_c101_mechanical_envelope_correction_rejects_undeclared_relation_vocabulary(
        self,
    ) -> None:
        candidate = _mechanically_correct_r2(_fixture_candidate("cba-slice-r2"))
        with self.assertRaisesRegex(CandidateAuthoringError, "undeclared relation predicate: relatesTo"):
            _validate_candidate_closure(candidate)

    def test_c102_declared_predicates_still_reject_the_resource_range(self) -> None:
        candidate = _mechanically_correct_r2(_fixture_candidate("cba-slice-r2"))
        _declare_r2_predicates(candidate)
        with self.assertRaisesRegex(CandidateAuthoringError, "heterogeneous object range"):
            _validate_candidate_closure(candidate)

    def test_c103_common_superclass_still_requires_shape_and_probe_paths(self) -> None:
        candidate = _mechanically_correct_r2(_fixture_candidate("cba-slice-r2"))
        _declare_r2_predicates(candidate)
        _declare_common_subject_range(candidate)
        with self.assertRaisesRegex(CandidateAuthoringError, "Shape predicate/path"):
            _validate_candidate_closure(candidate)

    def test_c104_corrected_candidate_receipt_projection_and_scope_boundaries(self) -> None:
        root = repository_root()
        reference = json.loads((root / NEUTRAL_REFERENCE).read_text(encoding="utf-8"))
        example = reference["example_candidate"]
        self.assertEqual(set(example), NEUTRAL_FIELDS)
        self.assertTrue(
            all(isinstance(value, str) and value.strip() for value in example["constraints"])
        )
        example_item_ids = [item["item_id"] for item in example["items"]]
        self.assertEqual(len(example_item_ids), len(set(example_item_ids)))
        self.assertTrue(
            all(
                isinstance(item["item_kind"], str)
                and item["item_kind"]
                and isinstance(item["semantic"], dict)
                for item in example["items"]
            )
        )
        self.assertTrue(
            all(
                "evidence_citations" not in item
                or (
                    isinstance(item["evidence_citations"], list)
                    and all(isinstance(citation, dict) for citation in item["evidence_citations"])
                )
                for item in example["items"]
            )
        )

        reference_text = json.dumps(reference, ensure_ascii=False).lower()
        fixture_text = (root / STRUCTURAL_FIXTURE).read_text(encoding="utf-8").lower()
        for forbidden in (
            "dify",
            "workflow",
            "quality_score",
            "quality_rating",
            "expected_answer",
            "project_id",
            "ontology_id",
            "batch_id",
            "platform_id",
            "live model",
            "business",
            "source text",
            "answer",
        ):
            self.assertNotIn(forbidden, reference_text)
            self.assertNotIn(forbidden, fixture_text)
        self.assertIsNone(re.search(r"\b[abc]\s*->\s*[abc]\b", reference_text))

        candidate = _mechanically_correct_r2(_fixture_candidate("cba-slice-r2"))
        _declare_r2_predicates(candidate)
        _declare_common_subject_range(candidate)
        _declare_shape_and_probe_paths(candidate)
        _validate_candidate_closure(candidate)
        calls: list[dict[str, Any]] = []
        receipt = _exact_protocol_receipt(candidate, calls)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(calls, [candidate])
        self.assertEqual(receipt, build_candidate_receipt(candidate))

        # The reference's five-field example is also a complete exact-current neutral object;
        # Protocol receives that object unchanged rather than a reduced projection.
        example_calls: list[dict[str, Any]] = []
        example_receipt = _exact_protocol_receipt(example, example_calls)
        self.assertEqual(example_receipt["status"], "accepted")
        self.assertEqual(example_calls, [example])

        fixtures = json.loads((root / STRUCTURAL_FIXTURE).read_text(encoding="utf-8"))
        corrected_fixture = fixtures["corrected"]
        self.assertEqual(set(corrected_fixture), NEUTRAL_FIELDS)
        corrected_calls: list[dict[str, Any]] = []
        corrected_receipt = _exact_protocol_receipt(corrected_fixture, corrected_calls)
        self.assertEqual(corrected_receipt["status"], "accepted")
        self.assertEqual(corrected_calls, [corrected_fixture])

        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        neutral_sources = [
            source
            for source in configuration.task.role_sources
            if source.relative_path.as_posix() == NEUTRAL_REFERENCE
        ]
        self.assertEqual(len(neutral_sources), 1)
        self.assertEqual(neutral_sources[0].roles, frozenset({"modeling", "protocol"}))
        self.assertNotIn("acceptance", neutral_sources[0].roles)
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        for role in ("modeling", "protocol"):
            prompt = runner._task_text(role)
            self.assertIn(NEUTRAL_REFERENCE, prompt)
            prompt_lower = prompt.lower()
            self.assertIn("before the first candidate", prompt_lower)
            self.assertIn("before every full revision", prompt_lower)
        for instructions in (
            root / "modeling_team/agent-packages/modeling/instructions.md",
            root / "modeling_team/agent-packages/protocol/instructions.md",
        ):
            text = instructions.read_text(encoding="utf-8")
            self.assertIn(NEUTRAL_REFERENCE, text)
            self.assertIn("before every full revision", text)

        proof = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-002-t.yaml",
            root / "modeling_team/tasks/r2-3-002-t.yaml",
            root=root,
        )
        self.assertIsNotNone(proof.profile.expected_matrix_binding)
        self.assertIsNotNone(proof.task.expected_matrix_binding)
        self.assertIsNone(configuration.profile.expected_matrix_binding)
        self.assertIsNone(configuration.task.expected_matrix_binding)


if __name__ == "__main__":
    unittest.main()
