"""R2.3-008 start10/start11 prevention: candidate authoring contracts are pinned.

Defect 8 made an illegal retrieval plan a typed, revisable rejection, but no
Modeling-readable surface stated the format, so the Modeling Agent guessed a
path expression in start10.  start11 then exposed the same gap for shape
cardinality: a negative_probe expected rejection while its shape path omitted
``min_count``, an internally inconsistent accepted candidate that no in-run
repair can settle.  These assertions guard both prevention surfaces: the
modeling instructions and the scenario-neutral authoring reference must state
the bare-local-name contract and the shape ``min_count`` contract.
"""

from __future__ import annotations

import json
import unittest

from modeling_team.contracts import repository_root


class ConsumerQueryPlanGuidanceTests(unittest.TestCase):
    root = repository_root()

    def test_modeling_instructions_pin_bare_local_name_required_paths(self) -> None:
        text = (
            self.root
            / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertIn("bare predicate local name", text)
        self.assertIn("required_paths", text)
        self.assertIn("currentlyConsumesOutput", text)
        self.assertIn("subject--predicate-->object", text)
        self.assertIn("complete revised candidate", text)


    def test_modeling_instructions_pin_one_connected_binding_for_queries(self) -> None:
        """start13 issue-1: the uniqueness rule recurred undocumented on surfaces."""
        text = " ".join(
            (
                self.root
                / "modeling_team/agent-packages/modeling/instructions.md"
            ).read_text(encoding="utf-8").split()
        )
        self.assertIn("exactly one connected binding", text)
        self.assertIn("one subject-object pair", text)
        self.assertIn("consumer-query-plan-invalid", text)
        self.assertIn("dedicated single-instance predicate", text)

    def test_neutral_authoring_reference_pins_the_same_contract(self) -> None:
        reference = json.loads(
            (
                self.root
                / "modeling_team/references/platform-neutral-candidate-authoring.json"
            ).read_text(encoding="utf-8")
        )
        rule = reference["candidate_envelope"]["consumer_query_required_paths"]
        self.assertEqual(rule["items"], "bare predicate local name string")
        self.assertIn("neutralAssociation", rule["rule"])
        self.assertIn("one complete revised candidate", rule["rule"])
        binding_rule = reference["candidate_envelope"]["consumer_query_one_connected_binding"]
        self.assertIn("one subject-object pair", binding_rule["rule"])
        self.assertIn("consumer-query-plan-invalid", binding_rule["rule"])
        self.assertIn("dedicated single-instance predicate", binding_rule["rule"])
        checklist_text = "\n".join(reference["closure_checklist"])
        self.assertIn("bare predicate local name", checklist_text)
        self.assertIn("never a full path expression or an IRI", checklist_text)
        self.assertNotIn("explicit min_count", checklist_text)
        self.assertIn("exactly one relation (or fact) item", checklist_text)
        self.assertFalse(any(i["item_kind"] in {"shape", "negative_probe"}
                             for i in reference["example_candidate"]["items"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
