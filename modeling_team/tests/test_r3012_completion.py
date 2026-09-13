"""R3.0-012 completion-channel tests (shared test plan T1-12..T1-17 subset).

Mechanical coverage for the host-only ``cq_acceptance_complete`` channel
(design §4.5): the envelope contract, the run/freeze/attempt binding checks,
the digest-and-verdict re-verification against the registered attempt's
retained ``batch-report.json``, the ``cq_acceptance_phase`` lifecycle with its
``cq-acceptance-wait`` window, the pending hold on ``TERMINAL_REPORT_COMPLETE``,
and the T3 exclusion of the acceptance wait.  No Agent process, no platform,
no LLM; the Examiner/Judge packet assembly is a later module.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
import time as _time_module

import pytest
import yaml

from modeling_team import __main__ as main_module
from modeling_team.competency_questions import (
    CQ_ACCEPTANCE_COMPLETE_FIELDS,
    CQ_BATCH_REPORT_SCHEMA,
    CQ_FREEZE_SCHEMA,
    CQ_WAIT_WINDOW_KINDS,
    CQContractError,
    CQWaitWindowTracker,
    build_batch_report,
)
from modeling_team.contracts import (
    ACCEPTANCE_TARGET_CQ_SEMANTIC,
    ACCEPTANCE_TARGET_PARAMETER,
    repository_root,
)
from modeling_team.candidate_progress import FormalCandidateProgressTimeout
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_r3011_runner_wiring import _question, _read_evidence
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = repository_root()
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
BATCH_ID = "batch-r3012"


class _FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _CompletionRunner:
    """A prepared 011 runner whose run root is removed afterwards."""

    def __init__(
        self, *, cq_semantic: bool = False, clock=None
    ) -> None:
        self.run_id = (
            f"r3012c-{hashlib.sha256(str(_time_module.time()).encode()).hexdigest()[:10]}"
        )
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.task_path = TASK
        if cq_semantic:
            task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
            task["task_id"] = "r3012-completion-cq-semantic"
            task["parameters"][ACCEPTANCE_TARGET_PARAMETER] = ACCEPTANCE_TARGET_CQ_SEMANTIC
            self.task_path = TASK.parent / "r3012-completion-cq-semantic.yaml"
            self.task_path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
            monotonic_clock=clock,
        )
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self.task_path,
            scope={"mode": "create"},
        )

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)
        if self.task_path is not TASK:
            self.task_path.unlink(missing_ok=True)


class _SettledTransport:
    """Every profile role reported the given status; drain() is quiescent."""

    def __init__(self, runner: TeamRunner, status: str, *, all_agents: bool = True) -> None:
        roles = None if all_agents else {"coordinator", "modeling", "protocol"}
        self.results = {
            agent.agent_id: type("R", (), {"status": status, "__dict__": {"status": status}})()
            for agent in runner.run.configuration.profile.agents
            if roles is None or agent.package.role in roles
        }

    issue_escalation_enabled = False
    terminal_dependencies: dict = {}

    def drain(self):
        return []

    def requeue(self, deliveries):
        return None

    def stop(self):
        return None


def _freeze(runner: TeamRunner) -> dict:
    return runner.freeze_cq_question_pool(
        {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": BATCH_ID,
            "material_digest": "material-r3012",
            "panorama_question_ids": ["cq-1"],
            "slice_question_ids": [],
            "ordering": ["cq-1"],
            "review_binding": {
                "review_id": "cq-review-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": [_question("cq-1", visibility="hidden")],
        }
    )


def _handoff_message(frozen: dict) -> dict:
    return {
        "action": "cq_handoff_complete",
        "freeze_id": BATCH_ID,
        "freeze_digest": frozen["snapshot_digest"],
        "delivery_binding": {"delivery_id": "d1", "digest": frozen["snapshot_digest"]},
    }


def _pending_scene(*, clock=None) -> tuple[_CompletionRunner, dict]:
    """Publish the handoff on a cq_semantic run and land in acceptance_pending."""

    harness = _CompletionRunner(cq_semantic=True, clock=clock)
    runner = harness.runner
    frozen = _freeze(runner)
    runner.transport = _SettledTransport(runner, "completed")
    ack = runner.handle_cq_outer_input(_handoff_message(frozen))
    assert ack["ok"] is True
    assert runner._cq_acceptance_phase == "acceptance_pending"
    return harness, frozen


def _examiner_entry(status: str = "completed") -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": BATCH_ID,
        "question_id": "cq-1",
        "question_content_version": 1,
        "answer": "answered from the bound model state",
        "evidence_refs": ["ev-1"],
        "explicit_unknown": [],
        "status": status,
        "failure_layer": None,
        "reason": "mechanical fixture entry",
    }


def _verdict_entry(state: str = "pass") -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": BATCH_ID,
        "question_id": "cq-1",
        "verdict": state,
        "failure_layer": None if state == "pass" else "modeling-quality",
        "conflicting_evidence": None,
        "note": "",
    }


def _write_report(runner: TeamRunner, frozen: dict, *, verdicts=None, raw: bytes | None = None):
    """Write the registered attempt's batch-report.json; return (bytes, digest)."""

    report_directory = runner.run.root / runner._cq_acceptance_attempt["report_directory"]
    report_directory.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        encoded = raw
    else:
        report = build_batch_report(
            run_id=runner.run.run_id,
            batch_id=BATCH_ID,
            freeze_digest=frozen["snapshot_digest"],
            model_binding_digest="sha256:" + "2" * 64,
            hidden_questions=[
                question for question in frozen["questions"] if question.get("visibility") == "hidden"
            ],
            examiner_reports=[_examiner_entry()],
            verdicts=[] if verdicts is None else verdicts,
            executed_question_ids=["cq-1"],
            unexecuted_question_ids=[],
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    (report_directory / "batch-report.json").write_bytes(encoded)
    return encoded, f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _completion(
    runner: TeamRunner,
    frozen: dict,
    *,
    report_digest: str,
    cq_verdict: str,
    **overrides,
) -> dict:
    message = {
        "action": "cq_acceptance_complete",
        "run_id": runner.run.run_id,
        "freeze_id": BATCH_ID,
        "freeze_digest": frozen["snapshot_digest"],
        "batch_id": BATCH_ID,
        "acceptance_attempt_id": "attempt-0001",
        "report_digest": report_digest,
        "cq_verdict": cq_verdict,
    }
    message.update(overrides)
    return message


# --- T1-13: the pending phase and its wait window -------------------------------


def test_pending_phase_and_wait_window_open_only_for_cq_semantic():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        assert "cq-acceptance-wait" in runner._cq_wait_windows.open_kinds()
        event = _read_evidence(runner, "cq-handoff-complete")[-1]
        assert event["acceptance_phase"] == "acceptance_pending"
        # The full_joint control: the same handoff leaves the 011 in-run
        # terminal path untouched -- no pending phase, no acceptance window.
        control = _CompletionRunner()
        try:
            control_runner = control.runner
            control_frozen = _freeze(control_runner)
            control_runner.transport = _SettledTransport(control_runner, "completed")
            ack = control_runner.handle_cq_outer_input(_handoff_message(control_frozen))
            assert ack["ok"] is True
            assert control_runner._cq_acceptance_phase is None
            assert control_runner._cq_wait_windows.open_kinds() == []
            assert control_runner._cq_acceptance_hold_pending() is False
        finally:
            control.cleanup()
    finally:
        harness.cleanup()


def test_completion_action_is_registered_in_both_action_sets():
    assert "cq_acceptance_complete" in main_module._KNOWN_OUTER_ACTIONS
    assert "cq_acceptance_complete" in main_module._CQ_OUTER_ACTIONS
    assert set(CQ_ACCEPTANCE_COMPLETE_FIELDS) == {
        "action",
        "run_id",
        "freeze_id",
        "freeze_digest",
        "batch_id",
        "acceptance_attempt_id",
        "report_digest",
        "cq_verdict",
    }


# --- T1-14: typed rejections for a forged or stale completion -------------------


def test_envelope_field_drift_is_rejected():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        with pytest.raises(CQContractError) as extra:
            runner.handle_cq_outer_input(
                _completion(
                    runner,
                    frozen,
                    report_digest="sha256:" + "3" * 64,
                    cq_verdict="pass",
                    extra_field="no host-chosen paths allowed",
                )
            )
        assert extra.value.data["reason_code"] == "cq_selector_incompatible"
        with pytest.raises(CQContractError) as missing:
            message = _completion(
                runner, frozen, report_digest="sha256:" + "3" * 64, cq_verdict="pass"
            )
            del message["cq_verdict"]
            runner.handle_cq_outer_input(message)
        assert missing.value.data["reason_code"] == "cq_selector_incompatible"
    finally:
        harness.cleanup()


def test_full_joint_run_rejects_the_completion_channel():
    harness = _CompletionRunner()
    try:
        runner = harness.runner
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        with pytest.raises(CQContractError) as rejected:
            runner.handle_cq_outer_input(
                _completion(
                    runner,
                    frozen,
                    report_digest=runner._cq_acceptance_attempt["handoff_digest"],
                    cq_verdict="pass",
                )
            )
        assert rejected.value.data["reason_code"] == "cq_selector_incompatible"
    finally:
        harness.cleanup()


def test_stale_run_freeze_and_attempt_bindings_are_rejected():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        digest = "sha256:" + "3" * 64
        with pytest.raises(CQContractError) as stale_run:
            runner.handle_cq_outer_input(
                _completion(runner, frozen, report_digest=digest, cq_verdict="pass", run_id="other")
            )
        assert stale_run.value.data["reason_code"] == "cq_review_stale"
        with pytest.raises(CQContractError) as stale_freeze:
            runner.handle_cq_outer_input(
                _completion(
                    runner,
                    frozen,
                    report_digest=digest,
                    cq_verdict="pass",
                    freeze_digest="sha256:" + "4" * 64,
                )
            )
        assert stale_freeze.value.data["reason_code"] == "cq_review_stale"
        with pytest.raises(CQContractError) as stale_attempt:
            runner.handle_cq_outer_input(
                _completion(
                    runner,
                    frozen,
                    report_digest=digest,
                    cq_verdict="pass",
                    acceptance_attempt_id="attempt-0002",
                )
            )
        assert stale_attempt.value.data["reason_code"] == "cq_review_stale"
    finally:
        harness.cleanup()


def test_unregistered_attempt_without_a_handoff_is_stale():
    harness = _CompletionRunner(cq_semantic=True)
    try:
        runner = harness.runner
        frozen = _freeze(runner)
        with pytest.raises(CQContractError) as rejected:
            runner.handle_cq_outer_input(
                _completion(
                    runner, frozen, report_digest="sha256:" + "3" * 64, cq_verdict="pass"
                )
            )
        assert rejected.value.data["reason_code"] == "cq_review_stale"
    finally:
        harness.cleanup()


def test_missing_report_forged_digest_and_forged_verdict_are_rejected():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        with pytest.raises(CQContractError) as missing:
            runner.handle_cq_outer_input(
                _completion(
                    runner, frozen, report_digest="sha256:" + "3" * 64, cq_verdict="fail"
                )
            )
        assert missing.value.data["reason_code"] == "cq_acceptance_report_mismatch"
        assert runner._cq_acceptance_phase == "acceptance_pending"

        _, digest = _write_report(
            runner, frozen, verdicts=[_verdict_entry("model-recall-insufficient")]
        )
        with pytest.raises(CQContractError) as forged_digest:
            runner.handle_cq_outer_input(
                _completion(runner, frozen, report_digest="sha256:" + "5" * 64, cq_verdict="pass")
            )
        assert forged_digest.value.data["reason_code"] == "cq_acceptance_report_mismatch"

        # The aggregate verdict is recomputed from the report: a full-pass
        # claim over a partial report is a mismatch, never an acceptance.
        with pytest.raises(CQContractError) as forged_verdict:
            runner.handle_cq_outer_input(
                _completion(
                    runner,
                    frozen,
                    report_digest=digest,
                    cq_verdict="pass",
                )
            )
        assert forged_verdict.value.data["reason_code"] == "cq_acceptance_report_mismatch"
        assert runner._cq_acceptance_phase == "acceptance_pending"

        # An unreadable report cannot be verified at all.
        _, raw_digest = _write_report(runner, frozen, raw=b"{not json")
        with pytest.raises(CQContractError) as unreadable:
            runner.handle_cq_outer_input(
                _completion(runner, frozen, report_digest=raw_digest, cq_verdict="fail")
            )
        assert unreadable.value.data["reason_code"] == "cq_acceptance_report_mismatch"
    finally:
        harness.cleanup()


def test_report_binding_drift_is_rejected():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        report = build_batch_report(
            run_id="some-other-run",
            batch_id=BATCH_ID,
            freeze_digest=frozen["snapshot_digest"],
            model_binding_digest="sha256:" + "2" * 64,
            hidden_questions=[
                question for question in frozen["questions"] if question.get("visibility") == "hidden"
            ],
            examiner_reports=[_examiner_entry()],
            verdicts=[_verdict_entry("pass")],
            executed_question_ids=["cq-1"],
            unexecuted_question_ids=[],
        )
        report_directory = runner.run.root / runner._cq_acceptance_attempt["report_directory"]
        report_directory.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        (report_directory / "batch-report.json").write_bytes(encoded)
        digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        with pytest.raises(CQContractError) as rejected:
            runner.handle_cq_outer_input(
                _completion(runner, frozen, report_digest=digest, cq_verdict="pass")
            )
        assert rejected.value.data["reason_code"] == "cq_acceptance_report_mismatch"
    finally:
        harness.cleanup()


# --- T1-13/T1-12: the verified completion ends the wait and releases terminal ----


def test_verified_completion_ends_the_wait_for_every_verdict_state():
    for verdicts, expected in (
        ([_verdict_entry("pass")], "pass"),
        ([_verdict_entry("model-recall-insufficient")], "partial"),
        ([], "fail"),
    ):
        harness, frozen = _pending_scene()
        try:
            runner = harness.runner
            _, digest = _write_report(runner, frozen, verdicts=verdicts)
            result = runner.handle_cq_outer_input(
                _completion(runner, frozen, report_digest=digest, cq_verdict=expected)
            )
            assert result["ok"] is True
            assert result["cq_verdict"] == expected
            assert runner._cq_acceptance_phase == "acceptance_complete"
            assert runner._cq_wait_windows.has_open_window is False
            event = _read_evidence(runner, "cq-acceptance-complete")[-1]
            assert event["cq_verdict"] == expected
            assert event["report_digest"] == digest
            assert event["acceptance_attempt_id"] == "attempt-0001"
        finally:
            harness.cleanup()


def test_duplicate_completion_confirms_and_divergent_duplicate_rejected():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        _, digest = _write_report(runner, frozen, verdicts=[_verdict_entry("pass")])
        first = runner.handle_cq_outer_input(
            _completion(runner, frozen, report_digest=digest, cq_verdict="pass")
        )
        events_before = len(_read_evidence(runner, "cq-acceptance-complete"))
        again = runner.handle_cq_outer_input(
            _completion(runner, frozen, report_digest=digest, cq_verdict="pass")
        )
        assert again["ok"] is True
        assert again.get("idempotent") is True
        assert again["cq_verdict"] == first["cq_verdict"]
        assert len(_read_evidence(runner, "cq-acceptance-complete")) == events_before
        with pytest.raises(CQContractError) as divergent:
            runner.handle_cq_outer_input(
                _completion(
                    runner, frozen, report_digest="sha256:" + "6" * 64, cq_verdict="partial"
                )
            )
        assert divergent.value.data["reason_code"] == "cq_acceptance_report_mismatch"
    finally:
        harness.cleanup()


def test_pending_holds_settlement_then_completion_releases_the_terminal():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        pending_output = runner.drain()
        assert not any(envelope.get("type") == "settled" for envelope in pending_output)
        assert runner._terminal_emitted is False
        state = json.loads((runner.run.root / "state.json").read_text(encoding="utf-8"))
        assert state["state"] != "POST_SETTLEMENT_REPORTING"
        assert state["state"] != "TERMINAL_REPORT_COMPLETE"

        _, digest = _write_report(runner, frozen, verdicts=[_verdict_entry("pass")])
        assert runner.handle_cq_outer_input(
            _completion(runner, frozen, report_digest=digest, cq_verdict="pass")
        )["ok"] is True
        completed_output = runner.drain()
        assert any(envelope.get("type") == "settled" for envelope in completed_output)
        # The coordinator final is captured on a later tick (the post-settlement
        # prompt goes out with the settled envelope); the foreground loop's
        # repeated drains reach TERMINAL_REPORT_COMPLETE exactly once.
        runner.drain()
        state = json.loads((runner.run.root / "state.json").read_text(encoding="utf-8"))
        assert state["state"] == "TERMINAL_REPORT_COMPLETE"
    finally:
        harness.cleanup()


def test_full_joint_settlement_is_unchanged_by_the_hold():
    harness = _CompletionRunner()
    try:
        runner = harness.runner
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        output = runner.drain()
        assert any(envelope.get("type") == "settled" for envelope in output)
        runner.drain()
        state = json.loads((runner.run.root / "state.json").read_text(encoding="utf-8"))
        assert state["state"] == "TERMINAL_REPORT_COMPLETE"
    finally:
        harness.cleanup()


# --- T1-16: the acceptance wait is excluded from the T3 active clock ------------


def test_t3_excludes_the_acceptance_wait_and_latches_on_real_active_time():
    clock = _FakeClock(0.0)
    harness, frozen = _pending_scene(clock=clock)
    try:
        runner = harness.runner
        runner._run_fallback_started = 0.0
        # The handoff opened the wait window at fake t=0.  The pending period
        # crosses the 10800s wall clock with no LLM output; T3 must not latch.
        clock.now = 21000.0
        runner._check_run_fallback_timeout()
        assert _read_evidence(runner, "run-fallback-timeout") == []
        assert runner._cq_acceptance_phase == "acceptance_pending"

        _, digest = _write_report(runner, frozen, verdicts=[_verdict_entry("pass")])
        assert runner.handle_cq_outer_input(
            _completion(runner, frozen, report_digest=digest, cq_verdict="pass")
        )["ok"] is True
        # Closing the window kept the accumulated 21000s exclusion: active time
        # only resumes from now on, and the original threshold still applies.
        clock.now = 31799.0
        runner._check_run_fallback_timeout()
        assert _read_evidence(runner, "run-fallback-timeout") == []
        clock.now = 31800.0
        with pytest.raises(FormalCandidateProgressTimeout):
            runner._check_run_fallback_timeout()
        assert _read_evidence(runner, "run-fallback-timeout") != []
    finally:
        harness.cleanup()


def test_full_joint_run_latches_at_the_threshold_without_a_window():
    clock = _FakeClock(0.0)
    harness = _CompletionRunner(clock=clock)
    try:
        runner = harness.runner
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        assert runner.handle_cq_outer_input(_handoff_message(frozen))["ok"] is True
        assert runner._cq_wait_windows.has_open_window is False
        runner._run_fallback_started = 0.0
        clock.now = 10799.0
        runner._check_run_fallback_timeout()
        assert _read_evidence(runner, "run-fallback-timeout") == []
        clock.now = 10800.0
        with pytest.raises(FormalCandidateProgressTimeout):
            runner._check_run_fallback_timeout()
        assert _read_evidence(runner, "run-fallback-timeout") != []
    finally:
        harness.cleanup()


# --- T1-17: window union, closed-set membership, and stop-time closure ----------


def test_acceptance_wait_unions_with_other_cq_waits():
    assert "cq-acceptance-wait" in CQ_WAIT_WINDOW_KINDS
    tracker = CQWaitWindowTracker()
    tracker.open_window("cq-review-request", 0.0)
    tracker.open_window("cq-acceptance-wait", 5.0)
    tracker.close_window("cq-review-request", 10.0)
    tracker.close_window("cq-acceptance-wait", 15.0)
    # The overlap [5, 10) is deduplicated: the union is [0, 15), not 20s.
    assert tracker.elapsed(20.0) == 15.0
    tracker.open_window("cq-acceptance-wait", 30.0)
    tracker.close_window("cq-acceptance-wait", 40.0)
    assert tracker.elapsed(50.0) == 25.0


def test_stop_closes_open_windows_and_preserves_the_exclusion_evidence():
    harness, frozen = _pending_scene()
    try:
        runner = harness.runner
        assert "cq-acceptance-wait" in runner._cq_wait_windows.open_kinds()
        assert runner.receive_outer({"action": "stop"}) == [{"type": "stopped"}]
        assert runner._cq_wait_windows.open_kinds() == []
        closed = _read_evidence(runner, "cq-wait-windows")[-1]
        assert closed["event"] == "closed-on-exit"
        assert closed["closed_windows"] == ["cq-acceptance-wait"]
        assert closed["open_windows"] == []
        assert closed["merged_windows"], "the accumulated exclusion survives the stop"
    finally:
        harness.cleanup()
