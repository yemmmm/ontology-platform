"""R2.3-008 start10 prevention: the consumer_query plan format is pinned.

Defect 8 made an illegal retrieval plan a typed, revisable rejection, but no
Modeling-readable surface stated the format, so the Modeling Agent guessed a
path expression in start10.  These assertions guard the prevention surface:
the modeling instructions and the scenario-neutral authoring reference must
both state the bare-local-name contract.
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
        checklist_text = "\n".join(reference["closure_checklist"])
        self.assertIn("bare predicate local name", checklist_text)
        self.assertIn("never a full path expression or an IRI", checklist_text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
