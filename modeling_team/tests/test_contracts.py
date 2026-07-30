from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modeling_team.contracts import (
    TeamConfigurationError,
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
            ["coordinator", "modeling", "protocol"],
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
