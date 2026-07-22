"""Static contracts for the four bounded Claude role assignments."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROLES = {
    "ontology-business-organizer": {
        "references": {
            "assigned_run_root",
            "run_id",
            "brief_path",
            "coverage_path",
            "source_index_path",
            "brief_output_path",
            "coverage_output_path",
            "questions_output_path",
        },
        "candidate_bound": False,
    },
    "ontology-work-unit-modeler": {
        "references": {
            "assigned_run_root",
            "run_id",
            "work_unit_id",
            "task_path",
            "result_path",
            "context_path",
            "output_schema_path",
        },
        "candidate_bound": False,
    },
    "ontology-model-reviewer": {
        "references": {
            "assigned_run_root",
            "run_id",
            "candidate_path",
            "candidate_hash",
            "brief_path",
            "coverage_path",
            "source_index_path",
            "findings_path",
            "review_output_path",
        },
        "candidate_bound": True,
    },
    "ontology-retrieval-evaluator": {
        "references": {
            "assigned_run_root",
            "run_id",
            "candidate_hash",
            "cq_bindings_path",
            "observed_query_evidence_path",
            "verification_schema_path",
            "verification_output_path",
        },
        "candidate_bound": True,
    },
}


class RoleAssignmentContractTest(unittest.TestCase):
    def test_skills_fail_closed_and_confine_assignment_inputs(self) -> None:
        for role, contract in ROLES.items():
            with self.subTest(role=role):
                body = (REPO / "skills" / role / "SKILL.md").read_text(encoding="utf-8")
                gate = "## Assignment gate"
                self.assertIn(gate, body)
                self.assertLess(body.index(gate), body.index("Read"))
                for reference in contract["references"]:
                    self.assertIn(f"`{reference}`", body)
                for marker in (
                    '"status":"BLOCKED"',
                    '"error_code":"missing_reference"',
                    "missing_references",
                    "resolved path is inside",
                    "exact dependency",
                    "Never glob or scan `workspaces/`, another run, or the repo",
                    "different `run_id`",
                ):
                    self.assertIn(marker, body)
                if contract["candidate_bound"]:
                    self.assertIn("`candidate_hash`", body)

    def test_agents_block_before_tool_use_and_defer_path_rules_to_skills(self) -> None:
        expected_block = (
            '`{"status":"BLOCKED","error_code":"missing_reference",'
            '"missing_references":["<reference>"],"next_action":"supply_complete_assignment"}`'
        )
        for role in ROLES:
            with self.subTest(role=role):
                body = (REPO / ".claude" / "agents" / f"{role}.md").read_text(encoding="utf-8")
                self.assertIn("Use the preloaded Skill.", body)
                self.assertIn("Before any `Read`, `Grep`, `Glob`, or search", body)
                self.assertIn(expected_block, body)
                self.assertIn("call no tool", body)
                self.assertIn("cwd, `workspaces/`, another run, or the repo", body)
                self.assertIn("Skill's exact-path, run-root, and mismatch rules", body)


if __name__ == "__main__":
    unittest.main()
