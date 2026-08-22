"""R2.3-009 start19: the agent-blocked exit must settle, not deadlock to T3.

The terminal-report guard already lets every role report ``blocked`` for a run
the roles judge unrepairable (T0 defense review 2026-08-20).  The settlement
gate in ``drain`` still demanded a settled Acceptance carrier, so a unanimous
blocked run where Acceptance never started (no handoff existed) could never
emit the ``settled`` envelope and burned to the T3 fallback timeout.  These
tests pin the repaired gate: a unanimous-blocked result set settles without a
carrier, while any non-blocked result still requires Acceptance settlement.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import TaskResult

from test_r23009_timeout_tiers import _TierAdapter, _tier_runner


class _BlockedTransport:
    issue_escalation_enabled = False

    def __init__(self, statuses: dict[str, str]) -> None:
        self.issue_ledger = SimpleNamespace(pending=False)
        self.terminal_dependencies = {}
        self.results = {
            agent_id: TaskResult(
                agent_id=agent_id, status=status, summary="summary", timestamp=0.0
            )
            for agent_id, status in statuses.items()
        }

    def drain(self):
        return []

    def requeue(self, deliveries):
        return None


class _SettledAdapter(_TierAdapter):
    def wait_settled(self, agent_ids, timeout):
        return True


def _blocked_runner(tmp_path: Path, statuses: dict[str, str]) -> TeamRunner:
    runner = _tier_runner(tmp_path, _SettledAdapter(), lambda: 0.0)
    runner.transport = _BlockedTransport(statuses)
    runner.acceptance = SimpleNamespace(is_settled=False, has_live_children=False)
    return runner


def test_unanimous_blocked_results_settle_without_acceptance_carrier(
    tmp_path: Path,
) -> None:
    runner = _blocked_runner(
        tmp_path,
        {role: "blocked" for role in ("modeling", "protocol", "coordinator", "acceptance")},
    )
    output = runner.drain()
    settled = [entry for entry in output if entry.get("type") == "settled"]
    assert len(settled) == 1
    assert runner._terminal_emitted is True
    assert set(runner.run.terminal_results) == {
        "modeling",
        "protocol",
        "coordinator",
        "acceptance",
    }
    assert all(
        result["status"] == "blocked"
        for result in runner.run.terminal_results.values()
    )


def test_any_completed_result_still_requires_acceptance_settlement(
    tmp_path: Path,
) -> None:
    statuses = {role: "blocked" for role in ("modeling", "protocol", "coordinator", "acceptance")}
    statuses["acceptance"] = "completed"
    runner = _blocked_runner(tmp_path, statuses)
    output = runner.drain()
    assert not [entry for entry in output if entry.get("type") == "settled"]
    assert runner._terminal_emitted is False


def test_settled_acceptance_carrier_still_settles_mixed_run(tmp_path: Path) -> None:
    statuses = {role: "blocked" for role in ("modeling", "protocol", "coordinator")}
    statuses["acceptance"] = "completed"
    runner = _blocked_runner(tmp_path, statuses)
    runner.acceptance = SimpleNamespace(is_settled=True, has_live_children=False)
    output = runner.drain()
    assert [entry.get("type") for entry in output].count("settled") == 1


def test_pending_issue_blocks_blocked_exit_settlement(tmp_path: Path) -> None:
    statuses = {role: "blocked" for role in ("modeling", "protocol", "coordinator", "acceptance")}
    runner = _blocked_runner(tmp_path, statuses)
    runner.transport.issue_ledger = SimpleNamespace(pending=True)
    # A pending issue short-circuits drain before the settlement gate, so no
    # settled envelope can be produced while owner guidance is outstanding.
    output = runner.drain()
    assert not [entry for entry in output if entry.get("type") == "settled"]
    assert runner._terminal_emitted is False
