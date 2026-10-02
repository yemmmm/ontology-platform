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
from modeling_team.r23005_producer_smoke import neutral_candidate
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
    """Build the current v3 envelope while retaining the fixture's revision/scope."""

    # The checked-in r1/r2 artifacts are historical v2 counterexamples.  The
    # authoring progression below uses a literal v3 candidate so the tests can
    # exercise semantic closure without a compatibility or recursive-strip path.
    return {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": candidate["candidate_revision"],
        "scope": copy.deepcopy(candidate["scope"]),
        "constraints": [
            "Every declared path is unique in this candidate.",
            "Object targets resolve through the declared common superclass.",
        ],
        "items": [
            {
                "item_id": "class-neutral-subject",
                "item_kind": "class",
                "semantic": {"class_id": "NeutralSubject"},
            },
            {
                "item_id": "class-neutral-dependency",
                "item_kind": "class",
                "semantic": {"class_id": "NeutralDependency"},
            },
            {
                "item_id": "class-neutral-left",
                "item_kind": "class",
                "semantic": {"class_id": "NeutralLeft", "superclass": "NeutralSubject"},
            },
            {
                "item_id": "class-neutral-right",
                "item_kind": "class",
                "semantic": {"class_id": "NeutralRight", "superclass": "NeutralSubject"},
            },
            {
                "item_id": "predicate-neutral-label",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "label",
                    "predicate_kind": "fact",
                    "domain": "NeutralSubject",
                    "range": "string",
                },
            },
            {
                "item_id": "predicate-neutral-affected-subject",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "affectedSubject",
                    "predicate_kind": "fact",
                    "domain": "NeutralSubject",
                    "range": "resource",
                },
            },
            {
                "item_id": "entity-neutral-left",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": "neutral-left",
                    "class": "NeutralLeft",
                    "values": {"label": "left", "affectedSubject": "item-neutral-dependency"},
                },
            },
            {
                "item_id": "entity-neutral-right",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": "neutral-right",
                    "class": "NeutralRight",
                    "values": {"label": "right", "affectedSubject": "item-neutral-left"},
                },
            },
            {
                "item_id": "entity-neutral-dependency",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": "neutral-dependency",
                    "class": "NeutralDependency",
                    "values": {"label": "dependency", "affectedSubject": "item-neutral-right"},
                },
            },
            {
                "item_id": "relation-neutral-left-right",
                "item_kind": "relation",
                "semantic": {
                    "relation_id": "relation-neutral-left-right",
                    "predicate": "relatesTo",
                    "subject": "neutral-left",
                    "object": "neutral-right",
                },
            },
            {
                "item_id": "relation-neutral-dependency-left",
                "item_kind": "relation",
                "semantic": {
                    "relation_id": "relation-neutral-dependency-left",
                    "predicate": "dependsOn",
                    "subject": "neutral-dependency",
                    "object": "neutral-left",
                },
            },
        ],
    }


def _declare_r2_predicates(candidate: dict[str, Any]) -> None:
    """Declare the relation predicates used by the current v3 candidate."""

    declared = {
        item["semantic"].get("predicate")
        for item in candidate["items"]
        if item.get("item_kind") == "predicate"
    }
    for item in candidate["items"]:
        if item.get("item_kind") != "relation":
            continue
        semantic = item["semantic"]
        predicate = semantic["predicate"]
        if predicate in declared:
            continue
        candidate["items"].append(
            {
                "item_id": f"predicate-{predicate}",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": predicate,
                    "predicate_kind": "relation",
                    "domain": "NeutralSubject",
                    "range": "NeutralSubject",
                },
            }
        )
        declared.add(predicate)


def _declare_common_subject_range(candidate: dict[str, Any]) -> None:
    classes = {
        item["semantic"]["class_id"]: item
        for item in candidate["items"]
        if item.get("item_kind") == "class"
    }
    if "UnknownAffectedSubject" not in classes:
        candidate["items"].append(
            {
                "item_id": "class-unknown-affected-subject",
                "item_kind": "class",
                "semantic": {"class_id": "UnknownAffectedSubject"},
            }
        )
    classes["UnknownAffectedSubject"] = next(
        item
        for item in candidate["items"]
        if item.get("item_kind") == "class"
        and item["semantic"].get("class_id") == "UnknownAffectedSubject"
    )
    target_classes = {
        "item-neutral-dependency": "NeutralDependency",
        "item-neutral-left": "NeutralLeft",
        "item-neutral-right": "NeutralRight",
    }
    for class_id in set(target_classes.values()):
        classes[class_id]["semantic"]["superclass"] = "UnknownAffectedSubject"

    affected_subject = next(
        item
        for item in candidate["items"]
        if item.get("item_kind") == "predicate"
        and item["semantic"].get("predicate") == "affectedSubject"
    )
    affected_subject["semantic"]["range"] = "UnknownAffectedSubject"
    affected_subject["semantic"]["target_class_bindings"] = target_classes


def _declare_shape_and_probe_paths(candidate: dict[str, Any]) -> None:
    candidate["items"].extend(
        [
            {
                "item_id": "predicate-invalid-value",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "invalidValue",
                    "predicate_kind": "fact",
                    "domain": "NeutralSubject",
                    "range": "string",
                },
            },
            {
                "item_id": "shape-neutral-subject",
                "item_kind": "shape",
                "semantic": {
                    "shape_id": "shape-neutral-subject",
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
                            "min_count": 1,
                        },
                    ],
                },
            },
            {
                "item_id": "probe-neutral-shape",
                "item_kind": "negative_probe",
                "semantic": {
                    "probe_id": "probe-neutral-shape",
                    "shape_id": "shape-neutral-subject",
                    "path": "path-invalid",
                    "expected_result": "rejected",
                    "invalid_instance": {
                        "class": "NeutralSubject",
                        "label": "Invalid neutral subject",
                        "values": {},
                    },
                },
            },
        ]
    )


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

    class_items = {
        item["semantic"].get("class_id"): item
        for item in items
        if item["item_kind"] == "class"
    }
    predicate_items = [item for item in items if item["item_kind"] == "predicate"]
    properties = {
        item["semantic"].get("predicate"): item["semantic"]
        for item in predicate_items
        if item["semantic"].get("predicate_kind") == "fact"
    }
    declared_relations = {
        item["semantic"].get("predicate")
        for item in predicate_items
        if item["semantic"].get("predicate_kind") == "relation"
    }
    relation_items = [item for item in items if item["item_kind"] == "relation"]
    for relation in relation_items:
        predicate = relation["semantic"].get("predicate")
        if predicate not in declared_relations:
            raise CandidateAuthoringError(f"undeclared relation predicate: {predicate}")

    property_ids = [item["semantic"].get("predicate") for item in predicate_items]
    if len(property_ids) != len(set(property_ids)):
        raise CandidateAuthoringError("fact predicate is declared more than once")
    affected_subject = properties.get("affectedSubject")
    if affected_subject is None:
        raise CandidateAuthoringError("affectedSubject predicate is undeclared")
    if affected_subject.get("range") in {"resource", "external", "external_placeholder"}:
        raise CandidateAuthoringError("heterogeneous object range is not closed")

    common = affected_subject.get("range")
    bindings = affected_subject.get("target_class_bindings")
    if not isinstance(bindings, dict):
        raise CandidateAuthoringError("heterogeneous object targets lack subclass bindings")
    for target, class_id in bindings.items():
        if class_id not in class_items or class_items[class_id]["semantic"].get("superclass") != common:
            raise CandidateAuthoringError(f"target binding is outside common superclass: {target}")
    affected_values = {
        item["semantic"].get("values", {}).get("affectedSubject")
        for item in items
        if item["item_kind"] in {"entity", "explicit_unknown"}
        and "affectedSubject" in item["semantic"].get("values", {})
    }
    if affected_values != set(bindings):
        raise CandidateAuthoringError("affectedSubject target bindings are incomplete")

    shape_items = [item for item in items if item["item_kind"] == "shape"]
    shapes = [item["semantic"] for item in shape_items]
    if not isinstance(shapes, list) or not shapes:
        raise CandidateAuthoringError("Shape predicate/path declarations are missing")
    shape_ids = {shape.get("shape_id") for shape in shapes}
    path_ids: set[str] = set()
    for shape in shapes:
        if shape.get("target_class") not in class_items:
            raise CandidateAuthoringError("Shape target class is outside the candidate")
        for path in shape.get("paths", []):
            path_id = path.get("path_id")
            if path_id in path_ids:
                raise CandidateAuthoringError("Shape path is declared more than once")
            path_ids.add(path_id)
            if path.get("predicate") not in properties and path.get("predicate") not in declared_relations:
                raise CandidateAuthoringError("Shape path predicate is undeclared")

    probe_items = [item for item in items if item["item_kind"] == "negative_probe"]
    probe = probe_items[0]["semantic"] if probe_items else {}
    if probe.get("shape_id") not in shape_ids or probe.get("path") not in path_ids:
        raise CandidateAuthoringError("negative-probe path is not closed")


def _validate_create_entity_labels(candidate: dict[str, Any]) -> None:
    """Require semantic labels for every neutral item Protocol materializes as an entity."""

    for item in candidate.get("items", []):
        if not isinstance(item, dict):
            continue
        semantic = item.get("semantic", {})
        item_kind = item.get("item_kind")
        if item_kind in {"entity", "explicit_unknown"}:
            values = semantic.get("values")
            label = values.get("label") if isinstance(values, dict) else None
            if not isinstance(label, str) or not label.strip():
                raise CandidateAuthoringError(
                    f"{item_kind} create_entity materialization requires semantic.values.label"
                )
        elif item_kind == "negative_probe" and "invalid_instance" in semantic:
            invalid_instance = semantic["invalid_instance"]
            label = invalid_instance.get("label") if isinstance(invalid_instance, dict) else None
            if not isinstance(label, str) or not label.strip():
                raise CandidateAuthoringError(
                    "negative_probe invalid_instance create_entity materialization requires label"
                )


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
        # The historical artifact is intentionally exercised unchanged first; its
        # retired top-level fields must be rejected before item interpretation.
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "unsupported fields"):
            build_candidate_receipt(candidate)
        wrapper_only = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": candidate["candidate_revision"],
            "scope": copy.deepcopy(candidate["scope"]),
            "constraints": [
                f"{constraint['id']}: {'; '.join(constraint['requirements'])}"
                for constraint in candidate["constraints"]
            ],
            "items": copy.deepcopy(candidate["items"]),
        }
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
        # Once the envelope is projected into the current five-field shape, the
        # object-valued constraints are the next deterministic rejection.
        envelope = {
            "candidate_kind": "platform-neutral-candidate-v3",
            "candidate_revision": candidate["candidate_revision"],
            "scope": copy.deepcopy(candidate["scope"]),
            "constraints": copy.deepcopy(candidate["constraints"]),
            "items": copy.deepcopy(candidate["items"]),
        }
        calls: list[dict[str, Any]] = []
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "constraints"):
            _exact_protocol_receipt(envelope, calls)
        self.assertEqual(calls, [envelope])

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
        handoff = reference["semantic_handoff"]
        self.assertEqual(
            set(handoff),
            {
                "candidate_integrity",
                "protocol_translation",
                "stage_atomicity",
                "receipt_binding",
                "modeling_exclusions",
                "value_analysis_boundary",
            },
        )
        self.assertIn("complete, self-contained, immutable semantic object", handoff["candidate_integrity"])
        self.assertIn("not to one platform transaction", handoff["candidate_integrity"])
        self.assertIn("Protocol alone", handoff["protocol_translation"])
        self.assertIn("dependency-ordered platform stages", handoff["protocol_translation"])
        self.assertIn("independently", handoff["stage_atomicity"])
        self.assertIn("dry_run", handoff["stage_atomicity"])
        self.assertIn("apply_atomic", handoff["stage_atomicity"])
        self.assertIn("preceding formal receipts", handoff["receipt_binding"])
        value_boundary = "\n".join(handoff["value_analysis_boundary"])
        self.assertIn("L1 ordinary literal, L2 enum meaning mapping, or L3 first-class semantic value", value_boundary)
        self.assertIn("neutral absolute semantic-property URN", value_boundary)
        self.assertIn("no automatic neutral-URN alias conversion", value_boundary)
        self.assertEqual(
            handoff["modeling_exclusions"],
            [
                "Platform execution strategy",
                "Fresh Project/Ontology scope or IDs",
                "Build Session/Lease details",
                "Batch or Item IDs and envelopes",
                "dry_run/apply_atomic commands",
                "Receipt-bound IDs or IRIs",
                "Dependency stage ordering",
                "A whole-candidate atomic-apply instruction",
            ],
        )
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
        checklist_text = "\n".join(reference["closure_checklist"])
        for phrase in (
            "semantic.values.label",
            "semantic.invalid_instance",
            "never derives or invents",
        ):
            self.assertIn(phrase, checklist_text)

        reference_text = json.dumps(reference, ensure_ascii=False).lower()
        # R4 declarations/examples use business_role/business_meaning as generic vocabulary;
        # all other scenario-specific forbidden terms still apply to the full contract.
        base_reference_text = json.dumps(
        {key: value for key, value in reference.items()
         if key not in {"multiview_semantic_definition", "process_binding_semantics",
                        "process_binding_example_candidate", "business_rule_semantics",
                        "relational_mapping", "interface_mapping"}}, ensure_ascii=False
        ).lower()
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
            self.assertNotIn(forbidden, base_reference_text if forbidden == "business" else reference_text)
            self.assertNotIn(forbidden, fixture_text)
        self.assertIsNone(re.search(r"\b[abc]\s*->\s*[abc]\b", reference_text))

        # The boundary may describe excluded mechanics, but every neutral candidate example and
        # fixture constraint remains semantic-only; no runtime/platform instruction is authored in
        # the object that Modeling sends.
        forbidden_constraint_terms = (
            "fresh project",
            "fresh ontology",
            "project_id",
            "ontology_id",
            "batch",
            "dry_run",
            "apply_atomic",
            "platform execution",
            "atomic apply",
            "stage ordering",
        )
        fixtures = json.loads((root / STRUCTURAL_FIXTURE).read_text(encoding="utf-8"))
        for candidate in [example, *(value for value in fixtures.values() if isinstance(value, dict))]:
            constraints_text = json.dumps(
                candidate.get("constraints", []), ensure_ascii=False
            ).lower()
            for term in forbidden_constraint_terms:
                self.assertNotIn(term, constraints_text)

        _validate_create_entity_labels(example)

        smoke_candidate = neutral_candidate()
        smoke_constraints = json.dumps(
            smoke_candidate["constraints"], ensure_ascii=False
        ).lower()
        for term in forbidden_constraint_terms:
            self.assertNotIn(term, smoke_constraints)

        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Whole-candidate integrity means",
            "Protocol alone translates",
            "Atomicity applies independently",
            "Candidate `constraints` are source-grounded semantic",
            "Never put platform execution strategy",
            "whole-candidate atomic-apply instruction",
            "semantic.values.label",
            "semantic.invalid_instance",
            "derive or invent labels",
        ):
            self.assertIn(phrase, modeling_instructions)
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "candidate's whole-candidate/immutable rule is semantic integrity",
            "dependency-ordered platform translation",
            "preceding formal receipt or required read",
            "semantic.values.label",
            "semantic.invalid_instance",
            "derive or invent one",
        ):
            self.assertIn(phrase, protocol_instructions)
        self.assertRegex(protocol_instructions, r"Atomicity applies\s+independently")
        self.assertRegex(
            protocol_instructions,
            r"Do not\s+interpret a whole immutable candidate as one atomic Batch",
        )

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

        corrected_fixture = copy.deepcopy(fixtures["corrected"])
        corrected_fixture["candidate_kind"] = "platform-neutral-candidate-v3"
        self.assertEqual(set(corrected_fixture), NEUTRAL_FIELDS)
        _validate_create_entity_labels(corrected_fixture)
        corrected_calls: list[dict[str, Any]] = []
        corrected_receipt = _exact_protocol_receipt(corrected_fixture, corrected_calls)
        self.assertEqual(corrected_receipt["status"], "accepted")
        self.assertEqual(corrected_calls, [corrected_fixture])

        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        for phrase in (
            "candidate's whole-candidate/immutable rule is semantic integrity",
            "each required apply stage is independently atomic",
            "generated IDs/IRIs come only from preceding formal receipts",
            "must never appear in Modeling's semantic constraints",
            "source-grounded semantic invariants only",
            "semantic.values.label",
            "semantic.invalid_instance",
            "never derives or invents them",
        ):
            self.assertIn(phrase, configuration.task.objective)
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

    def test_c105_materialized_entity_labels_are_required_and_not_derived(self) -> None:
        root = repository_root()
        reference = json.loads((root / NEUTRAL_REFERENCE).read_text(encoding="utf-8"))
        baseline = copy.deepcopy(reference["example_candidate"])
        cases = (
            ("entity", "semantic.values.label"),
            ("explicit_unknown", "semantic.values.label"),
            ("negative_probe", "semantic.invalid_instance.label"),
        )
        for item_kind, path in cases:
            candidate = copy.deepcopy(baseline)
            if item_kind == "entity":
                item = next(item for item in candidate["items"] if item["item_kind"] == "entity")
                item["semantic"]["values"].pop("label")
            elif item_kind == "explicit_unknown":
                candidate["items"].append(
                    {
                        "item_id": "unknown-neutral",
                        "item_kind": "explicit_unknown",
                        "semantic": {
                            "entity_id": "unknown-neutral",
                            "class": "NeutralSubject",
                            "values": {"unknownQuestion": "Which subject is unknown?"},
                        },
                    }
                )
            else:
                probe = next(
                    item for item in candidate["items"] if item["item_kind"] == "negative_probe"
                )
                probe["semantic"]["invalid_instance"].pop("label")
            with self.subTest(item_kind=item_kind, path=path):
                with self.assertRaisesRegex(CandidateAuthoringError, "requires"):
                    _validate_create_entity_labels(candidate)

    def test_r23005_prompt_contract_freezes_receipt_relation_and_cursor_gates(self) -> None:
        root = repository_root()
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        protocol = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        modeling = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        objective = configuration.task.objective

        self.assertIn("status,candidate_revision,semantic_digest,candidate_digest", protocol)
        for text in (modeling, objective):
            self.assertIn("status=accepted", text)
            self.assertIn("neutral envelope", text)
            self.assertIn("semantic/candidate digests", text)
            self.assertIn("dry_run", text)
            self.assertIn("apply_atomic", text)
            self.assertIn("governed retrieval", text)
        for text in (protocol,):
            self.assertIn("dry_run", text)
            self.assertIn("apply_atomic", text)
            self.assertIn("governed retrieval", text)
        self.assertIn("silent_for_acceptance", protocol)
        self.assertIn("ready_for_acceptance", modeling)
        self.assertIn("build_candidate_conflict", protocol)
        self.assertIn("same complete candidate", protocol)
        for text in (protocol, modeling, objective):
            self.assertIn("source-grounded", text)

        for field in (
            "query",
            "project_id",
            "scope_mode",
            "ontology_ids",
            "resource_types",
            "assertion_types",
            "search_mode",
            "depth",
            "limit",
            "context_limit",
        ):
            self.assertIn(f"`{field}`", objective)
        self.assertIn("context continuation may change only `context_cursor`", objective)
        self.assertIn("match continuation may change only `match_cursor`", objective)
        self.assertIn("new context chain", objective)
        self.assertIn("across competency questions", objective)


if __name__ == "__main__":
    unittest.main()
