"""Focused assertions for the deterministic LangGraph risk probes."""

from pathlib import Path

from scripts.v5_langgraph_risks.parallel_probe import run_p1, run_p2, run_p3, run_p4


def test_p1_proves_native_send_overlap(tmp_path: Path) -> None:
    result = run_p1(tmp_path)
    assert result["status"] == "PASS"
    assert result["observed_parallel_overlap"] is True
    assert {event["agent"] for event in result["events"] if event["event"] == "started"} == {
        "agent-a",
        "agent-b",
    }


def test_p2_records_single_thread_interrupt_limitation(tmp_path: Path) -> None:
    result = run_p2(tmp_path)
    assert result["status"] == "LIMITATION_OBSERVED"
    before = [event["event"] for event in result["events_before_resume"]]
    after = [event["event"] for event in result["events"]]
    assert "follow_step" not in before
    assert after.index("follow_step") > after.index("after_interrupt")
    assert result["checkpoint_before_resume"]["next"] == ["waiting_agent"]


def test_p3_reopens_disk_checkpoint_and_keeps_a_waiting(tmp_path: Path) -> None:
    result = run_p3(tmp_path)
    assert result["status"] == "PASS"
    assert result["checkpoint_a_while_waiting"]["next"] == ["agent_a_wait"]
    assert result["checkpoint_a_after_b_before_resume"]["next"] == ["agent_a_wait"]
    assert result["checkpoint_b_done"]["next"] == []
    assert result["restart_observed"] is True


def test_p4_consumed_payload_changes_decision_and_reentry(tmp_path: Path) -> None:
    result = run_p4(tmp_path)
    assert result["status"] == "PASS"
    scenarios = {item["scenario"]: item for item in result["scenarios"]}
    assert "B-used:accepted:installation" in scenarios["installation"]["first_b"]["result"]
    assert (
        "finalized:fact-installation-acceptance-v1:scope=installation"
        in scenarios["installation"]["resumed_a"]
    )
    assert "B-used:rejected:repair" in scenarios["repair"]["first_b"]["result"]
    assert "rejected:fact-repair-acceptance-v1:scope=repair" in scenarios["repair"]["resumed_a"]
    for scenario in scenarios.values():
        assert scenario["graph_call_overlap"] is True
        assert scenario["failures"] == []
        assert scenario["checkpoints"]["A_while_waiting"]["next"] == ["a_wait"]
        assert scenario["checkpoints"]["A_after_B_before_resume"]["next"] == ["a_wait"]
        assert any(row[1] == "consumed" for row in scenario["workspace_exchanges"])
        assert any(row[1] == "consumer_decision" for row in scenario["workspace_exchanges"])
