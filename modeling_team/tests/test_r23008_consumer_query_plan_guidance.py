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

    def test_modeling_instructions_pin_shape_min_count_for_probes(self) -> None:
        text = (
            self.root
            / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        self.assertIn("min_count", text)
        self.assertIn("imposes no presence constraint", text)
        self.assertIn("internally inconsistent", text)
        self.assertIn('"min_count": 1', text)

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
        min_count_rule = reference["candidate_envelope"]["shape_path_min_count"]
        self.assertIn("no presence constraint", min_count_rule["rule"])
        self.assertIn("internally inconsistent", min_count_rule["rule"])
        checklist_text = "\n".join(reference["closure_checklist"])
        self.assertIn("bare predicate local name", checklist_text)
        self.assertIn("never a full path expression or an IRI", checklist_text)
        self.assertIn("explicit min_count", checklist_text)
        # The example itself must not repeat the start11 inconsistency: the
        # shape path its own negative_probe relies on carries min_count.
        items = reference["example_candidate"]["items"]
        shape = next(i for i in items if i["item_kind"] == "shape")
        probe = next(i for i in items if i["item_kind"] == "negative_probe")
        paths = {p["path_id"]: p for p in shape["semantic"]["paths"]}
        probed_path = paths[probe["semantic"]["path"]]
        self.assertEqual(probed_path.get("min_count"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
