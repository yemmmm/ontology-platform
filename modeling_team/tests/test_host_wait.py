import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from modeling_team.delivery_host_actions import (
    append_session_event,
    record_host_action_result,
    request_host_action,
)
from modeling_team.host_wait import wait_for_host_work


def request(root, request_id="cq-1"):
    return request_host_action(
        root,
        "delivery-1",
        {"run-1"},
        "auth-1",
        {
            "request_id": request_id,
            "run_id": "run-1",
            "kind": "cq_review",
            "bindings": {
                "review_id": "review-1",
                "content_version": 1,
                "content_digest": "sha256:" + "a" * 64,
                "question_ids": ["q-1"],
                "review_snapshot_ref": "competency-questions/reviews/review-1.json",
            },
        },
    )


def test_pending_request_wakes_without_private_body_or_acknowledgement(tmp_path):
    request(tmp_path)
    journal = tmp_path / "session-events.jsonl"
    before = journal.read_bytes()
    result = wait_for_host_work(tmp_path)
    assert result["reason"] == "host_action"
    assert result["requests"] == [
        {"request_id": "cq-1", "run_id": "run-1", "kind": "cq_review"}
    ]
    assert "review_snapshot_ref" not in json.dumps(result)
    assert journal.read_bytes() == before


def test_new_request_interrupts_wait_instead_of_waiting_for_card_timeout(tmp_path):
    append_session_event(tmp_path, {"event": "ordinary_status"})
    timer = threading.Timer(0.1, request, args=(tmp_path,))
    timer.start()
    try:
        result = wait_for_host_work(tmp_path, timeout=5)
    finally:
        timer.join()
    assert result["reason"] == "host_action"
    assert result["elapsed_seconds"] < 3


def test_ordinary_events_do_not_wake_or_reset_periodic_deadline(tmp_path):
    append_session_event(tmp_path, {"event": "ordinary_status"})
    timer = threading.Timer(
        0.02, append_session_event, args=(tmp_path, {"event": "heartbeat"})
    )
    timer.start()
    try:
        result = wait_for_host_work(tmp_path, timeout=0.08)
    finally:
        timer.join()
    assert result["reason"] == "periodic_check"
    assert result["elapsed_seconds"] >= 0.08
    assert result["requests"] == []


def test_default_period_is_three_minutes(tmp_path, monkeypatch):
    from modeling_team import host_wait

    elapsed = [0.0]
    monkeypatch.setattr(host_wait.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        host_wait.time,
        "sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )
    result = wait_for_host_work(tmp_path)
    assert result["reason"] == "periodic_check"
    assert result["elapsed_seconds"] == 180


def test_completed_requests_do_not_wake_and_blocked_results_remain_actionable(tmp_path):
    request(tmp_path, "done")
    request(tmp_path, "blocked")
    result_path = tmp_path / "host-results/result.json"
    result_path.parent.mkdir()
    result_path.write_text('{"private": "body"}')
    record_host_action_result(tmp_path, "done", "completed", result_path)
    record_host_action_result(tmp_path, "blocked", "blocked", result_path)
    result = wait_for_host_work(tmp_path, timeout=0)
    assert [item["request_id"] for item in result["requests"]] == ["blocked"]
    assert wait_for_host_work(tmp_path, timeout=0, seen_request_ids=["blocked"])[
        "reason"
    ] == ("periodic_check")


def test_incomplete_journal_is_reported_instead_of_silent_timeout(tmp_path):
    (tmp_path / "session-events.jsonl").write_bytes(b'{"event":')
    result = wait_for_host_work(tmp_path, timeout=0)
    assert result["reason"] == "journal_incomplete"
    assert result["limitations"]


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf")])
def test_invalid_timeout_is_rejected(tmp_path, timeout):
    with pytest.raises(ValueError, match="timeout"):
        wait_for_host_work(tmp_path, timeout=timeout)


def test_real_cli_returns_request_and_rejects_missing_session(tmp_path):
    request(tmp_path)
    command = [sys.executable, "-m", "modeling_team.host_wait", "--session-root"]
    completed = subprocess.run(
        [*command, str(tmp_path), "--timeout", "0"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["data"]["reason"] == "host_action"
    missing = subprocess.run(
        [*command, str(tmp_path / "missing"), "--timeout", "0"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["error"]["code"] == "host_journal_unavailable"
