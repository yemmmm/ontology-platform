"""R2.3-009 budget refund: terminal settlement markers and refunded starts.

The user confirmed (2026-08-19) that self-repair runs do not consume the
semantic-start budget. The ledger never rewrites history; it appends
``terminal_settlement(outcome=...)`` for Agent-terminal runs and one
``budget_refund`` per eligible run (Agent-blocked exit or T3
``run-fallback-timeout``). Each valid refund makes one consumed start available
again during ``_start_cap`` replay; completed runs and other failure
classifications keep the consumed start.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.candidate_progress import FormalCandidateProgressTimeout
from modeling_team.contracts import TeamConfigurationError
from modeling_team.runner import TeamRunner
from modeling_team.start_ledger import StartLedger

from test_r23009_timeout_tiers import _TierAdapter, _tier_runner

_RUN_FALLBACK_EVIDENCE = {
    "run_id": "run-one",
    "classification": "collaboration/routing",
    "mutation_state": "zero-mutation",
    "reason": "run-fallback-timeout",
}


def _events(ledger: StartLedger) -> list[dict[str, object]]:
    path = Path(ledger.path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _strict_ledger(root: Path) -> StartLedger:
    return StartLedger(root, now=lambda: datetime.now(UTC), requirement_id="R2.3-005")


def _begin(ledger: StartLedger, run_id: str = "run-one", baseline: str = "baseline-one") -> None:
    ledger.reserve(run_id, baseline, datetime.now(UTC).isoformat())
    ledger.mark_semantic_start(run_id)


def test_agent_blocked_settlement_refunds_exactly_one_start(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path)
    _begin(ledger)
    assert ledger.record_terminal_settlement("run-one", outcome="agent_blocked") is True
    assert ledger.refund_budget("run-one") is True
    # The refund is once per run and immutable.
    assert ledger.refund_budget("run-one") is False
    # The refunded start is available again without any new authorization.
    ledger.reserve("run-two", "baseline-two", datetime.now(UTC).isoformat())
    ledger.mark_semantic_start("run-two")
    events = [event.get("event") for event in _events(ledger)]
    assert events.count("budget_refund") == 1
    assert "terminal_settlement" in events


def test_agent_completed_settlement_records_but_never_refunds(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path)
    _begin(ledger)
    assert ledger.record_terminal_settlement("run-one", outcome="agent_completed") is True
    assert ledger.refund_budget("run-one") is False
    # The consumed start is still spent: the next start needs authorization.
    with pytest.raises(TeamConfigurationError, match="budget"):
        ledger.reserve("run-two", "baseline-two", datetime.now(UTC).isoformat())


def test_run_fallback_timeout_failure_is_refund_eligible(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path)
    _begin(ledger)
    ledger.terminal_failure(
        "run-one", "collaboration/routing", False, terminal_evidence=dict(_RUN_FALLBACK_EVIDENCE)
    )
    assert ledger.refund_budget("run-one") is True
    ledger.reserve("run-two", "baseline-two", datetime.now(UTC).isoformat())
    ledger.mark_semantic_start("run-two")


def test_other_failure_classifications_do_not_refund(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path)
    _begin(ledger)
    ledger.terminal_failure("run-one", "collaboration/routing", False)
    assert ledger.refund_budget("run-one") is False


def test_settlement_contract_is_strict(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path)
    _begin(ledger)
    with pytest.raises(TeamConfigurationError, match="outcome"):
        ledger.record_terminal_settlement("run-one", outcome="agent_retired")
    with pytest.raises(TeamConfigurationError, match="latest semantic start"):
        ledger.record_terminal_settlement("run-two", outcome="agent_blocked")
    # A settled run accepts neither a second settlement nor a late failure.
    assert ledger.record_terminal_settlement("run-one", outcome="agent_blocked") is True
    with pytest.raises(TeamConfigurationError, match="immutable"):
        ledger.record_terminal_settlement("run-one", outcome="agent_blocked")
    with pytest.raises(TeamConfigurationError, match="immutable"):
        ledger.terminal_failure("run-one", "collaboration/routing", False)


def test_runner_cleanup_records_blocked_settlement_and_refund(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path / "ledger")
    _begin(ledger, "run-1")
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True)
    (run_root / "evidence" / "semantic-start.jsonl").write_text("{}\n", encoding="utf-8")
    runner = object.__new__(TeamRunner)
    runner.run = SimpleNamespace(
        run_id="run-1",
        root=run_root,
        terminal_results={
            "modeling": {"status": "blocked"},
            "protocol": {"status": "completed"},
        },
    )
    runner._ledger = ledger
    runner._record_terminal_settlement_and_refund()
    events = _events(ledger)
    assert [event.get("event") for event in events[-2:]] == [
        "terminal_settlement",
        "budget_refund",
    ]
    assert events[-2]["outcome"] == "agent_blocked"
    recorded = [
        json.loads(line)
        for line in (run_root / "evidence" / "start-ledger.jsonl").read_text().splitlines()
    ]
    assert recorded[-1]["event"] == "budget_refund"


def test_t3_latch_terminal_evidence_drives_cleanup_refund(tmp_path: Path) -> None:
    ledger = _strict_ledger(tmp_path / "ledger")
    _begin(ledger, "run-1")
    now = [1000.0]
    adapter = _TierAdapter()
    runner = _tier_runner(tmp_path, adapter, lambda: now[0])
    runner.run.run_id = "run-1"  # type: ignore[union-attr]
    runner._ledger = ledger
    (runner.run.root / "evidence" / "semantic-start.jsonl").write_text(  # type: ignore[union-attr]
        "{}\n", encoding="utf-8"
    )
    runner._run_fallback_started = 0.0
    runner._run_fallback_timeout_seconds = 100.0
    try:
        runner.drain()
    except FormalCandidateProgressTimeout:
        pass
    else:
        raise AssertionError("T3 must raise for the CLI cleanup path")
    failure = [event for event in _events(ledger) if event.get("event") == "terminal_failure"]
    assert failure[-1]["terminal_evidence"]["reason"] == "run-fallback-timeout"
    runner._record_terminal_settlement_and_refund()
    assert [event.get("event") for event in _events(ledger)[-1:]] == ["budget_refund"]
    # The refunded start is usable again.
    ledger.reserve("run-2", "baseline-2", datetime.now(UTC).isoformat())
    ledger.mark_semantic_start("run-2")
