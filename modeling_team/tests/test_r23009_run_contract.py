"""R2.3-009 real-run carrier: the Luna route contract under the relaxed gates.

R8 of the R2.3-009 test plan needs a fresh 3-start budget on the same Luna
full-stack scenario that R2.3-008 exercised.  The carrier is a closed-registry
contract pair (profile/task) plus a strict, refund-capable ledger config so
agent-blocked and T3 outcomes can earn ``budget_refund`` events, exactly like
the R2.3-008 ledger but on a new requirement namespace.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modeling_team.contracts import repository_root
from modeling_team.formal_runs import (
    R2_3_009_CONTRACT,
    formal_run_contract_for,
    load_formal_run_configuration,
    validate_formal_run_contract_assets,
)
from modeling_team.start_ledger import StartLedger, resolve_ledger_config

ROOT = repository_root()
PROFILE_PATH = ROOT / "modeling_team/profiles/r2-3-009-modeling-team.yaml"
TASK_PATH = ROOT / "modeling_team/tasks/r2-3-009-formal-acceptance.yaml"


class R23009RunContractTests(unittest.TestCase):
    def test_new_pair_resolves_the_closed_r23009_contract(self) -> None:
        configuration, contract = load_formal_run_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
        self.assertIs(contract, R2_3_009_CONTRACT)
        self.assertIs(formal_run_contract_for(configuration), R2_3_009_CONTRACT)
        self.assertIs(
            formal_run_contract_for(
                profile_id="r2-3-009-modeling-team", task_id="r2-3-009-formal-acceptance"
            ),
            R2_3_009_CONTRACT,
        )
        self.assertEqual(contract.scope_mode, "create")
        self.assertEqual(contract.default_model_profile_id, "openai-luna-medium")
        self.assertEqual(contract.ledger_requirement_id, "R2.3-009")
        # The scenario payload itself is the accepted R2.3-008 Luna baseline:
        # the carrier reuses the same acceptance standard and slice contract.
        self.assertEqual(
            contract.acceptance_standard_path,
            "modeling_team/references/r2-3-008-acceptance-standard-v2.json",
        )
        validate_formal_run_contract_assets(R2_3_009_CONTRACT)

    def test_pair_is_not_cross_wired_with_r23008_identities(self) -> None:
        self.assertIsNone(
            formal_run_contract_for(
                profile_id="r2-3-009-modeling-team", task_id="r2-3-008-formal-acceptance"
            )
        )
        self.assertIsNone(
            formal_run_contract_for(
                profile_id="r2-3-008-modeling-team", task_id="r2-3-009-formal-acceptance"
            )
        )

    def test_ledger_config_is_strict_refund_capable_with_cap_three(self) -> None:
        config = resolve_ledger_config("R2.3-009")
        self.assertEqual(config.initial_start_cap, 3)
        self.assertEqual(config.authorization_increment, 3)
        self.assertTrue(config.strict_sequence)
        self.assertEqual(config.ledger_filename, ".r2-3-009-start-ledger.jsonl")

    def test_ledger_supports_blocked_settlement_and_refund(self) -> None:
        from datetime import datetime, timezone

        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            ledger = StartLedger(Path(tmp), requirement_id="R2.3-009")
            ledger.reserve("run-1", "baseline-1", now.isoformat())
            ledger.mark_semantic_start("run-1")
            self.assertTrue(ledger.record_terminal_settlement("run-1", outcome="agent_blocked"))
            self.assertTrue(ledger.refund_budget("run-1"))
            # The refunded start is immediately usable again.
            ledger.reserve("run-2", "baseline-2", now.isoformat())
            ledger.mark_semantic_start("run-2")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
