"""Independent R4.3-015 operation/body checks; no external model or production run."""
from __future__ import annotations

import hashlib
import json
import threading
import time

import pytest

from modeling_team import delivery_ops
from modeling_team.tests.test_delivery_ops import _Process, _run_root
from modeling_team.tests.test_delivery_session import session
from modeling_team.tests.test_r30009_plan_ref_capability_schema import _protocol_capability
from modeling_team.tests.test_v43_production_refs import (
    PLAN1, PLAN2, call, execute_args, production,
)
from modeling_team.staged_decisions import platform_content_hash


def _start(tmp_path, *, launcher, operation_id="feedback-original"):
    return delivery_ops.start_evaluation(
        run_id="bound", operation_id=operation_id, mode="public-feedback",
        freeze_id="freeze-public", checkpoint_id="checkpoint-current",
        question_ids=["cq-public"], model_profile="openai-sol-medium",
        repository_root=tmp_path, launcher=launcher,
    )


def _status(tmp_path):
    return delivery_ops.get_evaluation_status(
        operation_id="feedback-original", repository_root=tmp_path,
    )


def _ended(tmp_path):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = _status(tmp_path)
        if status["ended_at"] is not None:
            return status
        time.sleep(0.005)
    pytest.fail("original controlled evaluation did not end")


def _publish(root, *, status="observed", **changes):
    path = root / "early-feedback/current/feedback.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "run_id": "bound", "freeze_id": "freeze-public",
        "checkpoint_id": "checkpoint-current", "question_ids": ["cq-public"],
        "model_profile": "openai-sol-medium", "status": status,
        "formal_acceptance": False,
        "reports": [{"question_id": "cq-public", "answer": "source-supported answer"}],
        **changes,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("exit_code", [0, 9])
@pytest.mark.parametrize("outcome", ["observed", "partial", "superseded", "not-executed"])
def test_original_public_operation_ends_without_owner_independent_of_quality(
    tmp_path, exit_code, outcome,
):
    root = _run_root(tmp_path, "bound")
    launches = []

    def launcher(argv, **_kwargs):
        launches.append(list(argv))
        return _Process(exit_code=exit_code)

    _start(tmp_path, launcher=launcher)
    _publish(root, status=outcome)
    status = _ended(tmp_path)
    assert status["operation_id"] == "feedback-original"
    assert status["status"] == "exited" and status["exit_code"] == exit_code
    assert status["ended_at"] is not None
    assert status["work_state"] == "working" and status["lifecycle"] == "unknown"
    assert status["report_binding"]["valid"] is True
    assert status["report_binding"]["summary"]["status"] == outcome
    assert status["report_binding"]["summary"]["formal_acceptance"] is False
    assert "--owner-root" not in launches[0]
    assert len(launches) == 1


def test_running_original_operation_is_observable_without_starting_replacement(tmp_path):
    _run_root(tmp_path, "bound")
    released = threading.Event()
    launches = []

    class WaitingProcess(_Process):
        def wait(self):
            assert released.wait(3), "test did not release controlled process"
            return 0

    def launcher(argv, **_kwargs):
        launches.append(list(argv))
        return WaitingProcess()

    _start(tmp_path, launcher=launcher)
    try:
        pending = _status(tmp_path)
        assert pending["status"] == "running" and pending["ended_at"] is None
        assert pending["exit_code"] is None and pending["report_binding"] is None
        assert pending["request_binding"]["checkpoint_id"] == "checkpoint-current"
    finally:
        released.set()
    ended = _ended(tmp_path)
    assert ended["operation_id"] == pending["operation_id"]
    assert len(launches) == 1


def test_report_binding_summary_is_not_body_and_changed_digest_is_detectable(tmp_path):
    root = _run_root(tmp_path, "bound")
    old = root / "early-feedback/old/feedback.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"answer":"old unbound report"}')
    _start(tmp_path, launcher=lambda *_args, **_kwargs: _Process())
    assert _ended(tmp_path)["report_binding"] is None
    path = _publish(root)
    binding = _status(tmp_path)["report_binding"]
    assert binding["valid"] is True and binding["preexisted"] is False
    assert "source-supported answer" not in json.dumps(binding["summary"])

    host = session(tmp_path)
    host.repository_root = tmp_path
    host.run_ids = {"bound"}
    actual = host.call_tool("read_delivery_artifact", {"path": binding["path"]})
    assert actual["ok"] is True
    body = actual["data"]
    assert json.loads(body["text"])["reports"][0]["answer"] == "source-supported answer"
    assert body["content_digest"] == binding["digest"]
    assert body["content_digest"] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    path.write_text(path.read_text() + "\n")
    changed = host.call_tool("read_delivery_artifact", {"path": binding["path"]})
    assert changed["ok"] is True
    assert changed["data"]["content_digest"] != binding["digest"]
    # The original binding is retained; eligibility requires comparing the actual bytes.
    assert _status(tmp_path)["report_binding"]["digest"] == binding["digest"]


@pytest.mark.parametrize("changes", [
    {"run_id": "foreign"}, {"freeze_id": "old-freeze"},
    {"checkpoint_id": "old-checkpoint"}, {"question_ids": ["cq-hidden"]},
])
def test_rejected_public_binding_does_not_erase_actual_operation_end(tmp_path, changes):
    root = _run_root(tmp_path, "bound")
    _start(tmp_path, launcher=lambda *_args, **_kwargs: _Process(exit_code=7))
    _publish(root, **changes)
    status = _ended(tmp_path)
    assert status["status"] == "exited" and status["exit_code"] == 7
    assert status["work_state"] == "working"
    assert status["report_status"] == "new_report_rejected"
    assert status["report_binding"]["valid"] is False
    assert status["report_binding"]["validation_errors"]


@pytest.mark.parametrize("terminal", ["failed", "validation_failed"])
def test_second_apply_failure_retains_first_success_and_retry_does_not_replay(
    production, terminal,
):
    original = production.runner.staged_batch_forwarder
    second_ontology = production.plans[1]["projection"]["ontology_id"]

    def fail_second(batch):
        if batch["mode"] == "apply_atomic" and batch["ontology_id"] == second_ontology:
            production.calls.append(dict(batch))
            version = production.versions[second_ontology]
            return {
                "batch_id": batch["client_batch_id"],
                "client_batch_id": batch["client_batch_id"],
                "attempt_id": f"attempt-{len(production.calls)}",
                "idempotency_key": batch["idempotency_key"], "mode": batch["mode"],
                "attempt_status": terminal, "content_hash": platform_content_hash(batch),
                "workspace": {"before_version": version, "after_version": version},
                "findings": [{"message": "controlled second-plan failure"}],
            }
        return original(batch)

    production.runner.staged_batch_forwarder = fail_second
    with _protocol_capability(production) as endpoint:
        failed = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert failed["status"] == "PARTIAL" and failed["ok"] is False
        assert failed["error"]["stage"] == "apply"
        assert failed["error"]["plan_ref"] == PLAN2
        assert failed["error"]["reason_code"] == "staged_plan_apply_incomplete"
        assert len(failed["completed"]) == 1
        assert failed["completed"][0]["plan_ref"] == PLAN1
        assert failed["completed"][0]["status"] == "applied"
        assert failed["completed"][0]["resource_readback_status"] == "not_evaluated"
        first_calls = list(production.calls)
        production.runner.staged_batch_forwarder = original
        fixed = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert fixed["ok"] is True
        assert [row["status"] for row in fixed["completed"]] == ["already_applied", "applied"]
        assert production.calls[:len(first_calls)] == first_calls
        assert len(production.calls) == len(first_calls) + 1
        assert production.calls[-1]["ontology_id"] == second_ontology
