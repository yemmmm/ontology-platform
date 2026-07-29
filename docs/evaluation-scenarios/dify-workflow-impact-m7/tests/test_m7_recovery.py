from __future__ import annotations

from pathlib import Path
import sys

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from m7_contract import CONTRACT_VERSION  # noqa: E402
from m7_host import AttemptLedger, HostError  # noqa: E402


def _start(run_id: str, contract_version: str) -> dict[str, str]:
    return {
        "event": "modeling_started",
        "run_id": run_id,
        "agent_id": f"agent-{run_id}",
        "fork_turns": "none",
        "input_manifest_sha256": "input",
        "base_manifest_sha256": "base",
        "contract_version": contract_version,
    }


def _authorization(run_id: str) -> dict[str, object]:
    return {
        "event": "l1_pass_authorized",
        "run_id": run_id,
        "scope": {"project_id": "project", "ontology_id": "ontology", "build_session_id": "session"},
        "judge_verdict_sha256": "judge-verdict",
        "contract_version": CONTRACT_VERSION,
    }


def test_v4_recovery_ledger_preserves_old_attempts_unlocks_only_the_fifth_after_l1_pass(tmp_path: Path) -> None:
    ledger = AttemptLedger(tmp_path / "attempts.jsonl")
    # These are pre-v4 append-only history, accepted exactly as already-recorded events.
    for run_id, version in (("attempt-one", "m7-contract-v1"), ("attempt-two", "m7-contract-v2"), ("attempt-three", "m7-contract-v3-judge")):
        ledger._append(_start(run_id, version))  # noqa: SLF001 - test-only immutable historical fixture
    assert [event["contract_version"] for event in ledger.events()] == ["m7-contract-v1", "m7-contract-v2", "m7-contract-v3-judge"]

    ledger.append_modeling_started(_start("attempt-four", CONTRACT_VERSION))
    with pytest.raises(HostError, match="attempt 5 requires"):
        ledger.append_modeling_started(_start("attempt-five", CONTRACT_VERSION))

    ledger.append_l1_pass_authorized(_authorization("attempt-four"))
    ledger.append_modeling_started(_start("attempt-five", CONTRACT_VERSION))
    with pytest.raises(HostError, match="attempt limit"):
        ledger.append_modeling_started(_start("attempt-six", CONTRACT_VERSION))

    # Cleanup never owns the ledger: reopening it leaves all starts and the single authorization.
    reopened = AttemptLedger(ledger.path)
    assert [event["event"] for event in reopened.events()] == [
        "modeling_started", "modeling_started", "modeling_started", "modeling_started",
        "l1_pass_authorized", "modeling_started",
    ]


def test_l1_pass_authorization_requires_the_paired_active_v4_start(tmp_path: Path) -> None:
    ledger = AttemptLedger(tmp_path / "attempts.jsonl")
    ledger._append(_start("attempt-three", "m7-contract-v3-judge"))  # noqa: SLF001
    with pytest.raises(HostError, match="paired active-v4"):
        ledger.append_l1_pass_authorized(_authorization("attempt-three"))
