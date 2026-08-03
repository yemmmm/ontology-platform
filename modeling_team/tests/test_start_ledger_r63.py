from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from modeling_team.contracts import TeamConfigurationError
from modeling_team.start_ledger import StartLedger


class StartLedgerRound63Tests(unittest.TestCase):
    def test_gate_binding_is_optional_for_legacy_and_byte_equal_before_start(self) -> None:
        now = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        gate = {
            "proof_matrix_path": "modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json",
            "proof_matrix_digest": "a" * 64,
            "p2a_pass_path": "workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json",
            "p2a_pass_digest": "b" * 64,
            "source_run_id": "r23002-real-20260801s",
        }
        with tempfile.TemporaryDirectory() as directory:
            ledger = StartLedger(Path(directory), now=lambda: now)
            freeze = now.isoformat()
            ledger.reserve("run-one", "baseline-one", freeze, gate)
            with self.assertRaisesRegex(TeamConfigurationError, "gate binding"):
                ledger.mark_semantic_start("run-one", {**gate, "proof_matrix_digest": "c" * 64})
            records = Path(directory, ".r2-3-002-start-ledger.jsonl").read_text(encoding="utf-8")
            self.assertNotIn('"event": "semantic_start"', records)
            ledger.mark_semantic_start("run-one", dict(reversed(list(gate.items()))))
            ledger.terminal_failure("run-one", "platform-contract", False, "baseline-one")
            ledger.authorize_repair("run-one", "repair-evidence", "baseline-two", gate)
            ledger.reserve("run-two", "baseline-two", freeze, gate)
            with self.assertRaisesRegex(TeamConfigurationError, "gate binding"):
                ledger.mark_semantic_start("run-two")
            ledger.mark_semantic_start("run-two", gate)
            with self.assertRaisesRegex(TeamConfigurationError, "budget is exhausted"):
                ledger.reserve("run-three", "baseline-three", freeze, gate)

    def test_invalid_gate_binding_fails_before_any_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = StartLedger(Path(directory), now=lambda: datetime.now(UTC))
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve(
                    "run-one",
                    "baseline",
                    datetime.now(UTC).isoformat(),
                    {"proof_matrix_path": "bad"},
                )
            path = Path(directory, ".r2-3-002-start-ledger.jsonl")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
