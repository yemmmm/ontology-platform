"""Independent bounded runtime checks; neutral fixtures, no model or business API."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
import yaml

from modeling_team.checkpoints import (
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    CheckpointError,
    inspect_checkpoints,
)
from modeling_team.staged_batch_write_forwarder import (
    DEFINITE_REJECTION_CODES,
    WRITE_TOOL,
    _decode_tool_result,
)
from modeling_team.staged_decisions import (
    StagedSubmissionRejection,
    read_submission_intents,
    read_submission_receipts,
)
from modeling_team.tests.test_llm_inactivity_timeout import _make_adapter, _make_agent
from modeling_team.tests.test_r30009_runner_wiring import (
    UNIFIED_TASK,
    _UnifiedRunner,
    _batch_items,
    _open_platform_gate_unified,
    _unified_args,
)
from modeling_team.tests.test_r30015_checkpoints import (
    _bound_runner_scope,
    _read_manifest,
    _settled_apply_intent,
    checkpoint_data_standin as _capture_fixture,
)

checkpoint_data_standin = _capture_fixture


def _event(
    method, item_id="neutral-sleep", *, thread="neutral-thread", turn="neutral-turn", kind="sleep"
):
    return {
        "method": method,
        "params": {
            "item": {"type": kind, "id": item_id, "durationMs": 43200000},
            "threadId": thread,
            "turnId": turn,
            "startedAtMs": 0,
        },
    }


def _runtime(tmp_path):
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.15
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    agent.thread_id = "neutral-thread"
    agent.active_turn_id = agent.last_started_turn_id = "neutral-turn"
    agent.last_output_monotonic = time.monotonic() - 1201
    return adapter, agent


def test_native_sleep_matching_completion_resets_then_silence_times_out(tmp_path):
    adapter, agent = _runtime(tmp_path)
    adapter._notification(agent, _event("item/started"))
    # Make the inactivity clock overdue without spending twelve hours asleep.
    agent.last_output_monotonic = time.monotonic() - 1201
    adapter._start_inactivity_watchdog(agent)
    try:
        time.sleep(0.3)
        assert agent.runtime_failure is None
        adapter._notification(agent, _event("item/completed", "other-item"))
        agent.last_output_monotonic = time.monotonic() - 1201
        time.sleep(0.2)
        assert agent.runtime_failure is None
        before = time.monotonic()
        adapter._notification(agent, _event("item/completed"))
        assert agent.last_output_monotonic >= before
        time.sleep(0.05)
        assert agent.runtime_failure is None
        deadline = time.monotonic() + 2
        while agent.runtime_failure is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert agent.runtime_failure["reason"] == "llm-inactivity-timeout"
    finally:
        agent.inactivity_watchdog_stop.set()
        agent.inactivity_watchdog_thread.join(timeout=2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"thread": "unrelated-thread"},
        {"turn": "unrelated-turn"},
        {"kind": "commandExecution"},
    ],
)
def test_unrelated_or_non_sleep_items_do_not_suspend_timeout(tmp_path, overrides):
    adapter, agent = _runtime(tmp_path)
    adapter._notification(agent, _event("item/started", **overrides))
    agent.last_output_monotonic = time.monotonic() - 1201
    adapter._on_inactivity_timeout(agent, 0.15)
    assert agent.runtime_failure["reason"] == "llm-inactivity-timeout"


def test_final_timeout_latch_cannot_race_a_concurrent_sleep_notification(tmp_path, monkeypatch):
    adapter, agent = _runtime(tmp_path)
    original = adapter._latch_runtime_failure

    attempted = threading.Event()
    completed = threading.Event()
    lock_results = []

    def notify_sleep():
        acquired = agent.state_lock.acquire(blocking=False)
        lock_results.append(acquired)
        if acquired:
            agent.state_lock.release()
        attempted.set()
        adapter._notification(agent, _event("item/started"))
        completed.set()

    worker = threading.Thread(target=notify_sleep)

    def race(at_agent, detail, **kwargs):
        worker.start()
        assert attempted.wait(2)
        assert lock_results == [False], "sleep can interleave after the eligibility check"
        assert not completed.is_set()
        return original(at_agent, detail, **kwargs)

    monkeypatch.setattr(adapter, "_latch_runtime_failure", race)
    # The final eligibility/latch boundary must be atomic to real notification
    # threads. Here timeout obtained the lock first, so its failure is legitimate.
    assert adapter._on_inactivity_timeout(agent, 0.15) is True
    worker.join(timeout=2)
    assert completed.is_set()
    assert agent.runtime_failure["reason"] == "llm-inactivity-timeout"


def test_sleep_observed_before_timeout_decision_keeps_watchdog_armed(tmp_path):
    adapter, agent = _runtime(tmp_path)
    worker = threading.Thread(target=adapter._notification, args=(agent, _event("item/started")))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert adapter._on_inactivity_timeout(agent, 0.15) is False
    assert agent.runtime_failure is None
    assert adapter.consume_runtime_failures() == []
    assert adapter.consume_inactivity_failures() == []


@pytest.mark.parametrize("overrides", [{"thread": "other-thread"}, {"turn": "other-turn"}])
def test_stale_completion_cannot_close_current_sleep(tmp_path, overrides):
    adapter, agent = _runtime(tmp_path)
    adapter._notification(agent, _event("item/started"))
    adapter._notification(agent, _event("item/completed", **overrides))
    agent.last_output_monotonic = time.monotonic() - 1201
    assert adapter._on_inactivity_timeout(agent, 0.15) is False
    assert agent.runtime_failure is None
    adapter._notification(agent, _event("item/completed"))
    agent.last_output_monotonic = time.monotonic() - 1201
    assert adapter._on_inactivity_timeout(agent, 0.15) is True
    assert agent.runtime_failure["reason"] == "llm-inactivity-timeout"


@pytest.mark.parametrize("failure_kind", ["definite", "unknown", "generic"])
def test_forward_outcome_controls_actual_checkpoint_save(
    tmp_path, checkpoint_data_standin, failure_kind
):
    def forward(_batch):
        if failure_kind == "generic":
            raise RuntimeError("batch_limit_exceeded text is not typed proof")
        code = "batch_limit_exceeded" if failure_kind == "definite" else "internal_error"
        return _decode_tool_result(
            SimpleNamespace(
                isError=False,
                structuredContent={
                    "ok": False,
                    "error_code": code,
                    "error": "neutral fixture refusal",
                },
                content=[],
            ),
            tool=WRITE_TOOL,
            definite_codes=DEFINITE_REJECTION_CODES,
        )

    task = yaml.safe_load(UNIFIED_TASK.read_text())
    task["parameters"]["modeling_checkpoints"] = True
    task_path = tmp_path / "checkpoint-task.yaml"
    task_path.write_text(yaml.safe_dump(task))
    harness = _UnifiedRunner(tmp_path, forwarder=forward)
    try:
        harness.prepare(task_path=task_path)
        _open_platform_gate_unified(harness)
        runner = harness.runner
        runner.scope = _bound_runner_scope()
        # A separate previously settled operation supplies checkpoint history;
        # the rejected operation must never acquire a fabricated receipt.
        _settled_apply_intent(runner)
        args = _unified_args(
            _batch_items(), "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
        )
        with pytest.raises(StagedSubmissionRejection):
            runner._handle_staged_submit_modeling_batch(args)
        intents = read_submission_intents(harness.run_root)
        failed = next(item for item in intents if item["ordinal"] == 2)
        assert (
            failed["status"]
            == {"definite": "rejected", "unknown": "unknown", "generic": "submitted"}[failure_kind]
        )
        assert [item["intent_ordinal"] for item in read_submission_receipts(harness.run_root)] == [
            1
        ]
        if failure_kind != "definite":
            with pytest.raises(CheckpointError) as exc:
                runner._save_run_checkpoint(
                    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
                )
            assert exc.value.reason_code == "checkpoint_write_unreconciled"
            return
        result = runner._save_run_checkpoint(
            CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
        )
        assert result["status"] == "saved"
        manifest = _read_manifest(harness.run_root, result["checkpoint_id"])
        positions = manifest["write_positions"]["positions"]
        rejected_position = next(item for item in positions if item["ordinal"] == 2)
        assert rejected_position["state"] == "rejected"
        assert rejected_position["receipt_ordinal"] is None
        assert rejected_position["batch_id"] is None
        reconciliation = inspect_checkpoints(harness.run_root, result["checkpoint_id"])[
            "checkpoint"
        ]["write_reconciliation"]
        assert reconciliation["completed_operations"] == ["idem-1"]
        assert reconciliation["unreconciled"] == []
    finally:
        harness.cleanup()
