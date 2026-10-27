from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recovery_probe import (  # noqa: E402
    checkpoint_snapshot,
    launch_worker,
    ledger_rows,
    run_r3,
    run_recovery_scenario,
)


def test_sigkill_window_has_effect_but_no_node_checkpoint(tmp_path: Path) -> None:
    result = run_recovery_scenario(tmp_path, "naive")
    assert result["crash_returncode"] == -9
    assert len(result["rows_after_crash"]) == 1
    assert result["before_resume_checkpoint"]["count"] == 2
    assert result["before_resume_checkpoint"]["next"] == ["effect"]
    assert result["before_resume_checkpoint"]["values"]["operation_id"] == "operation-naive"
    assert result["after_resume_checkpoint"]["next"] == []
    assert result["node_started_count"] == 2, "the resumed graph really re-entered the node"
    events = [
        json.loads(line) for line in (tmp_path / "naive" / "events.jsonl").read_text().splitlines()
    ]
    assert sum(event["event"] == "effect_committed" for event in events) == 2


def test_naive_recovery_duplicates_external_effect(tmp_path: Path) -> None:
    result = run_recovery_scenario(tmp_path, "naive")
    assert len(result["rows_after_resume"]) == 2
    assert {row["operation_id"] for row in result["rows_after_resume"]} == {"operation-naive"}


def test_operation_identity_and_reconciliation_keep_effect_once(tmp_path: Path) -> None:
    result = run_recovery_scenario(tmp_path, "idempotent")
    assert len(result["rows_after_crash"]) == 1
    assert len(result["rows_after_resume"]) == 1
    assert result["rows_after_resume"][0]["operation_id"] == "operation-idempotent"
    assert result["node_started_count"] == 2


def test_r3_does_not_treat_unknown_as_not_written(tmp_path: Path) -> None:
    result = run_r3(tmp_path)
    assert result["decisions"] == {
        "committed": "read_back_existing_effect",
        "confirmed_not_written": "applied_once",
        "unknown": "deferred_for_reconciliation",
    }
    assert len(result["rows"]) == 2
    assert result["real_timeout_nodes"]["committed"]["returncode"] == 1
    assert len(result["real_timeout_nodes"]["committed"]["rows"]) == 1
    assert result["real_timeout_nodes"]["committed"]["decision"] == "read_back_existing_effect"
    assert result["real_timeout_nodes"]["unknown"]["returncode"] == 1
    assert result["real_timeout_nodes"]["unknown"]["rows"] == []
    assert result["real_timeout_nodes"]["unknown"]["decision"] == "deferred_for_reconciliation"


def test_completed_checkpoint_replay_still_uses_stable_operation_identity(tmp_path: Path) -> None:
    output = tmp_path / "completed"
    output.mkdir()
    operation_id, thread_id = "operation-complete", "thread-complete"
    launch_worker(output, "idempotent", "start", operation_id, thread_id)
    first = ledger_rows(output / "application-ledger.sqlite")
    first_checkpoint = checkpoint_snapshot(output / "langgraph-checkpoints.sqlite", thread_id)
    launch_worker(output, "idempotent", "completed", operation_id, thread_id)
    second = ledger_rows(output / "application-ledger.sqlite")
    second_checkpoint = checkpoint_snapshot(output / "langgraph-checkpoints.sqlite", thread_id)
    assert len(first) == len(second) == 1
    assert second == first
    assert second[0]["operation_id"] == operation_id
    assert first_checkpoint["count"] >= 3
    assert second_checkpoint["count"] == first_checkpoint["count"]
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    assert sum(event["event"] == "node_started" for event in events) == 1
