import copy
from datetime import datetime, timedelta, timezone

import pytest

from modeling_team.efficiency import begin_round, summarize_round


def record(tmp_path):
    return begin_round(tmp_path / "round.json", identity={
        "materials_digest": "frozen-material", "question_set": "public17-hidden10",
        "model_effort": "unchanged", "configuration": "config-ref", "code_commit": "commit-ref",
        "scope": "industrial-service-v3-complete27",
    }, start_reference="authorized-start-with-ready-inputs", started_at="2026-10-09T08:00:00Z")


def test_retry_never_overwrites_round_start(tmp_path):
    before = record(tmp_path)
    with pytest.raises(FileExistsError):
        begin_round(tmp_path / "round.json", identity=before["identity"],
                    start_reference="retry", started_at="2026-10-09T09:00:00Z")
    before["run_ids"] = ["first", "quality-repair", "reacceptance"]
    result = summarize_round(before, observed_at="2026-10-09T10:00:00Z")
    assert result["total_wall_seconds"] == 7200
    assert not result["completion_recorded"]
    assert result["active_work_seconds"] is None
    assert result["performance_acceptance"] == "not_judged_by_timing_tool"


def test_faults_union_only_critical_path_and_waiting_stays_in_wall(tmp_path):
    before = record(tmp_path)
    before["intervals"] = [
        {"category": kind, "started_at": f"2026-10-09T08:{a}:00Z",
         "ended_at": f"2026-10-09T08:{b}:00Z", "evidence_reference": "retained-evidence",
         "blocks_critical_path": blocking}
        for kind, a, b, blocking in [
            ("platform-contract", "10", "30", True),
            ("runtime/infrastructure", "20", "40", True),
            ("runtime/infrastructure", "45", "50", False),
            ("human-wait", "10", "50", True),
            ("modeling-quality", "00", "55", True),
        ]
    ]
    result = summarize_round(before, observed_at="2026-10-09T09:00:00+00:00")
    assert result["total_wall_seconds"] == 3600
    assert result["critical_path_fault_seconds"] == 1800
    assert result["fault_adjusted_wall_seconds"] == 1800
    assert result["category_wall_seconds"]["human-wait"] == 2400
    assert result["category_wall_seconds"]["modeling-quality"] == 3300


@pytest.mark.parametrize("missing", ["independent_full_pass", "acceptance_references", "cleanup_reference", "completed_at"])
def test_end_requires_recorded_full_pass_and_cleanup(tmp_path, missing):
    before = record(tmp_path)
    before["completion"] = {"independent_full_pass": True, "acceptance_references": ["public17", "hidden10"],
                            "cleanup_reference": "cleanup", "completed_at": "2026-10-09T09:30:00Z"}
    assert summarize_round(before, observed_at="2026-10-09T10:00:00Z")["total_wall_seconds"] == 5400
    del before["completion"][missing]
    result = summarize_round(before, observed_at="2026-10-09T10:00:00Z")
    assert result["total_wall_seconds"] == 7200
    assert result["completion_references"] is None


def test_missing_activity_proof_stays_unknown_and_bad_window_is_rejected(tmp_path):
    before = record(tmp_path)
    before["intervals"] = [{"category": "semantic-work", "started_at": "2026-10-09T08:10:00Z"}]
    result = summarize_round(before, observed_at="2026-10-09T10:00:00Z")
    assert result["category_wall_seconds"] == {}
    assert "unknown" in result["limitations"][0]
    bad = copy.deepcopy(before)
    bad["intervals"][0].update(ended_at="2026-10-09T08:00:00Z", evidence_reference="evidence")
    with pytest.raises(ValueError, match="window"):
        summarize_round(bad, observed_at="2026-10-09T10:00:00Z")
    with pytest.raises(ValueError, match="timezone"):
        summarize_round(before, observed_at="2026-10-09T10:00:00")


def test_delivery_tool_records_progress_without_exposing_start_override(tmp_path):
    from modeling_team.delivery import DeliverySession
    from modeling_team.tests.test_delivery_session import ROOT
    identity = record(tmp_path)["identity"]
    started_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    config = {"session_id": "timed", "model_profile": "openai-sol-medium",
              "authorization_reference": "authorized-round", "allowed_sources": [],
              "allowed_operations": ["read"], "run_ids": [], "efficiency_round": {
                  "identity": identity, "start_reference": "ready-execution-instruction",
                  "started_at": started_at,
              }}
    host = DeliverySession(repository_root=ROOT, session_root=tmp_path / "session", config=config)
    result = host.call_tool("record_efficiency_progress", {"counts": {"turns": 2}, "question_set": "freeze-complete27"})
    assert result["ok"], result
    assert result["data"]["counts"] == {"turns": 2}
    assert result["data"]["identity"]["question_set"] == "freeze-complete27"
    assert not result["data"]["completion_recorded"]
    assert not host.call_tool("record_efficiency_progress", {"started_at": "2026-10-09T09:00:00Z"})["ok"]
    restored = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=config, resume=True)
    assert restored.call_tool("record_efficiency_progress", {})["data"]["started_at"] == started_at
    altered = copy.deepcopy(config)
    altered["efficiency_round"]["started_at"] = "2026-10-09T09:00:00Z"
    with pytest.raises(ValueError, match="reset"):
        DeliverySession(repository_root=ROOT, session_root=host.session_root, config=altered, resume=True)


def test_delivery_without_host_timing_config_gives_recoverable_feedback(tmp_path):
    from modeling_team.tests.test_delivery_session import session
    host = session(tmp_path)
    result = host.call_tool("record_efficiency_progress", {})
    assert not result["ok"]
    assert "Host configuration" in result["error"]["message"]
    assert not host.finished
