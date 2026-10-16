import json
import subprocess
import sys
from pathlib import Path

import pytest

from modeling_team.delivery_host_actions import (
    HOST_RESULTS_DIRECTORY,
    append_session_event,
    host_action_state,
    read_session_journal,
    request_host_action,
    record_host_action_result,
)
from modeling_team.host_ops import HostOpError


ROOT = Path(__file__).resolve().parents[2]


def _platform_request(root: Path, request_id: str = "repair-1", **extra):
    arguments = {
        "request_id": request_id,
        "run_id": "run-1",
        "kind": "platform_repair",
        "bindings": {},
        "expected_behavior": "the governed read returns the applied revision",
        "actual_behavior": "the governed read is missing the revision",
        "blocked_step": "governed readback",
        "checked": ["request receipt", "application record"],
        "hypotheses": ["stale projection"],
        "write_state": "known_applied",
    }
    arguments.update(extra)
    return arguments


def test_append_session_event_returns_lock_serialized_exact_bytes(tmp_path):
    root = tmp_path / "session"
    first = {"event": "first", "value": 1}
    second = {"event": "second", "value": 2}
    offset1, length1 = append_session_event(root, first)
    offset2, length2 = append_session_event(root, second)

    raw = (root / "session-events.jsonl").read_bytes()
    assert offset1 == 0
    assert offset2 == length1
    assert length1 == len(raw[:length1])
    assert length2 == len(raw[offset2:])
    assert json.loads(raw[offset1:offset1 + length1]) == first
    assert json.loads(raw[offset2:offset2 + length2]) == second
    assert (root / "session-events.jsonl.lock").is_file()
    assert read_session_journal(root) == raw


def test_request_is_current_run_bound_and_same_content_is_idempotent(tmp_path):
    root = tmp_path / "session"
    arguments = _platform_request(root)
    first = request_host_action(root, "delivery-1", {"run-1"}, "auth-1", arguments)
    second = request_host_action(root, "delivery-1", {"run-1"}, "auth-1", arguments)
    assert first["request_id"] == second["request_id"] == "repair-1"
    assert first["content_digest"] == second["content_digest"]
    assert len((root / "session-events.jsonl").read_bytes().splitlines()) == 1

    with pytest.raises(HostOpError) as conflict:
        request_host_action(
            root,
            "delivery-1",
            {"run-1"},
            "auth-1",
            _platform_request(root, actual_behavior="a different failure"),
        )
    assert conflict.value.code == "host_action_request_id_conflict"
    assert conflict.value.retryable is True

    with pytest.raises(HostOpError) as unbound:
        request_host_action(root, "delivery-1", {"other-run"}, "auth-1", arguments)
    assert unbound.value.code == "host_action_run_unbound"


def test_cq_request_keeps_only_verified_binding_metadata(tmp_path):
    root = tmp_path / "session"
    request = request_host_action(
        root,
        "delivery-1",
        {"run-1"},
        "auth-1",
        {
            "request_id": "cq-1",
            "run_id": "run-1",
            "kind": "cq_review",
            "bindings": {
                "review_id": "review-1",
                "content_version": 3,
                "content_digest": "sha256:" + "a" * 64,
                "question_ids": ["q-1"],
                "phase": "slice-review",
                "review_snapshot_ref": "competency-questions/reviews/review-1.json",
                "question_text": "must never be copied",
            },
        },
    )
    assert request["bindings"]["review_id"] == "review-1"
    assert "question_text" not in json.dumps(request, ensure_ascii=False)
    assert request["bindings"]["review_snapshot_ref"].startswith("competency-questions/")


def test_host_result_records_metadata_only_and_rebuilds_state(tmp_path):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    results = root / HOST_RESULTS_DIRECTORY
    results.mkdir()
    original = results / "host-report.json"
    original.write_text('{"private_body": "must stay in the original"}', encoding="utf-8")

    result = record_host_action_result(root, "repair-1", "completed", original)
    state = host_action_state(root)
    assert result["source"] == "host_agent"
    assert result["result_ref"]["path"] == "host-results/host-report.json"
    assert result["result_ref"]["byte_length"] == original.stat().st_size
    assert state["pending"] == []
    assert state["completed"][0]["request_id"] == "repair-1"
    journal = (root / "session-events.jsonl").read_text(encoding="utf-8")
    assert "private_body" not in journal
    assert state["results"]["repair-1"]["source"] == "host_agent"


def test_result_cli_and_result_original_boundary(tmp_path):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    results = root / HOST_RESULTS_DIRECTORY
    results.mkdir()
    original = results / "report.json"
    original.write_text("host result", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "modeling_team.delivery_host_actions",
            "--session-root",
            str(root),
            "--request-id",
            "repair-1",
            "--status",
            "completed",
            "--result-path",
            str(original),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["data"]["source"] == "host_agent"

    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(HostOpError) as escaped:
        record_host_action_result(root, "repair-1", "completed", outside)
    assert escaped.value.code == "host_result_path_escape"


def test_missing_or_changed_result_is_recoverable(tmp_path):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    results = root / HOST_RESULTS_DIRECTORY
    results.mkdir()
    original = results / "report.json"
    original.write_text("first", encoding="utf-8")
    record_host_action_result(root, "repair-1", "blocked", original)
    original.unlink()
    with pytest.raises(HostOpError) as missing:
        record_host_action_result(root, "repair-1", "blocked", original)
    assert missing.value.code == "host_result_unavailable"


def test_evidence_reference_uses_resolved_session_or_run_path_and_rejects_private_paths(tmp_path):
    root = tmp_path / "session"
    with pytest.raises(HostOpError) as escaped:
        request_host_action(
            root,
            "delivery-1",
            {"run-1"},
            "auth-1",
            _platform_request(root, evidence_references=[
                {"path": "evidence/../../outside.json", "run_id": "run-1"},
            ]),
        )
    assert escaped.value.code == "host_action_evidence_unbound"
    with pytest.raises(HostOpError) as private:
        request_host_action(
            root,
            "delivery-1",
            {"run-1"},
            "auth-1",
            _platform_request(root, evidence_references=[
                {"path": "evidence/cq-review.jsonl", "run_id": "run-1"},
            ]),
        )
    assert private.value.code == "host_action_evidence_forbidden"
