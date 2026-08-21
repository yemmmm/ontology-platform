"""Fatal host-error ledger settlement in the foreground CLI.

R2.3-009 start18 (2026-08-21): the host wrote an invalid outer ``question``
action into the FIFO of a schema-v2 run.  ``receive_outer`` correctly raised
``TeamConfigurationError("schema-v2 outer questions are Runner-owned")`` and
the run was torn down — but the generic fatal handler in ``modeling_team
.__main__`` only cleaned up; it never settled the start ledger.  The run had
already recorded ``reservation`` and ``semantic_start``, so the consumed
start stayed dangling until the operator manually appended a
``terminal_failure`` via ``classify-failure``.  These tests lock the
narrow repair: a fatal host error after semantic start settles the ledger
as ``runtime/infrastructure`` (host-side fault, start not refunded).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock, TestCase

from modeling_team.__main__ import _settle_ledger_after_fatal_host_failure


def _run(root: Path) -> SimpleNamespace:
    return SimpleNamespace(root=root)


class FatalHostFailureSettlementTests(TestCase):  # noqa: D101
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_semantic_started_run_settles_runtime_infrastructure(self) -> None:
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "evidence" / "semantic-start.jsonl").write_text("{}\n")
        runner = SimpleNamespace(
            run=_run(self.root),
            record_terminal_failure=mock.Mock(),
            _terminal_emitted=False,
        )
        _settle_ledger_after_fatal_host_failure(runner)
        runner.record_terminal_failure.assert_called_once_with(
            "runtime/infrastructure", False
        )

    def test_presemantic_run_and_missing_runner_do_not_settle(self) -> None:
        # Before semantic start the ledger keeps its startup-failure path
        # (release_presemantic inside the runner); the CLI must not classify.
        (self.root / "evidence").mkdir(parents=True)
        runner = SimpleNamespace(
            run=_run(self.root),
            record_terminal_failure=mock.Mock(),
            _terminal_emitted=False,
        )
        _settle_ledger_after_fatal_host_failure(runner)
        runner.record_terminal_failure.assert_not_called()

        _settle_ledger_after_fatal_host_failure(None)  # no runner: no-op

    def test_already_settled_run_is_not_reclassified(self) -> None:
        # A run that already emitted its terminal settlement (the runtime
        # failure path) must not be reclassified by the fatal handler.
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "evidence" / "semantic-start.jsonl").write_text("{}\n")
        runner = SimpleNamespace(
            run=_run(self.root),
            record_terminal_failure=mock.Mock(),
            _terminal_emitted=True,
        )
        _settle_ledger_after_fatal_host_failure(runner)
        runner.record_terminal_failure.assert_not_called()

    def test_ledger_rejection_does_not_mask_the_fatal_error(self) -> None:
        # The settlement is best-effort bookkeeping: a ledger that refuses
        # (e.g. a terminal record raced in from another path) must never
        # replace the original fatal error with a bookkeeping exception.
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "evidence" / "semantic-start.jsonl").write_text("{}\n")
        runner = SimpleNamespace(
            run=_run(self.root),
            record_terminal_failure=mock.Mock(
                side_effect=RuntimeError("already terminal")
            ),
            _terminal_emitted=False,
        )
        _settle_ledger_after_fatal_host_failure(runner)


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
