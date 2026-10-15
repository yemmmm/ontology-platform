"""Terminal refusals must identify the actual recoverable prerequisite."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_r30008b_staged_decisions import _checklist
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker


@pytest.fixture
def terminal_runner(tmp_path):
    roles = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("coordinator", "modeling")
    ]
    runner = TeamRunner(
        repository_root=Path(__file__).resolve().parents[2],
        adapter=SimpleNamespace(terminal_report_blocked=lambda *_args: False),
    )
    runner.run = SimpleNamespace(
        root=tmp_path,
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="terminal-diagnostic-test"),
            profile=SimpleNamespace(profile_id="terminal-diagnostic-test", agents=roles),
        ),
    )
    runner._staged_decisions = True
    runner._acceptance_target = "cq_semantic"
    # No Agent process runs here; feedback delivery is a separate tested boundary.
    runner._deliver_staged_gate_feedback = lambda *_args: None
    broker = TeamTransportBroker(
        tmp_path / "transport",
        {("modeling", "coordinator"), ("coordinator", "modeling")},
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
        issue_escalation_enabled=True,
        terminal_report_guard=runner._terminal_report_guard,
    )
    runner.transport = broker
    yield runner, broker
    broker.stop()


def test_pending_issue_returns_actual_reason_and_same_run_can_finish(terminal_runner):
    runner, broker = terminal_runner
    ledger = broker.issue_ledger
    issue = ledger.report(
        reporter_id="modeling",
        category="business_clarification",
        summary="Waiting for a required upstream result",
        failing_operation="submission",
        error="upstream pending",
        mutation_state="not_written",
        requested_action="resolve the original issue",
    )
    with pytest.raises(RoutingError) as blocked:
        broker.report("modeling", "completed", "ready")
    assert blocked.value.code == "issue_pending"
    assert "active issue" in str(blocked.value)
    assert "query_semantic_context" not in str(blocked.value)
    assert not broker.results
    # A known resolved wait must not latch a permanent terminal rejection.
    ledger.fail_rebind(issue_id=issue.issue_id, reporter_id="modeling", reason="owner closed")
    assert runner._terminal_report_guard("modeling", status="completed") is False
    assert broker.report("modeling", "completed", "resolved").status == "completed"


@pytest.mark.parametrize("checklist_bytes", [None, "not valid json"])
def test_cq_semantic_coordinator_does_not_require_legacy_joint_checklist(
    terminal_runner, checklist_bytes
):
    runner, broker = terminal_runner
    if checklist_bytes is not None:
        path = runner.run.root / "joint-acceptance/joint-acceptance-checklist.json"
        path.parent.mkdir()
        path.write_text(checklist_bytes)
    assert broker.report("coordinator", "completed", "production ready").status == "completed"


def test_full_joint_still_requires_valid_checklist_and_reports_its_reason(terminal_runner):
    runner, broker = terminal_runner
    runner._acceptance_target = "full_joint"
    # Feedback delivery is independent of whether the terminal report is admitted.
    runner._deliver_staged_gate_feedback = lambda *_args: None
    with pytest.raises(RoutingError) as missing:
        broker.report("coordinator", "completed", "premature")
    assert missing.value.code == "acceptance_checklist_missing"
    assert "checklist" in str(missing.value)
    assert "retrieval" not in str(missing.value)
    path = runner.run.root / "joint-acceptance/joint-acceptance-checklist.json"
    path.parent.mkdir()
    path.write_text(json.dumps(_checklist()))
    assert broker.report("coordinator", "completed", "joint evidence ready").status == "completed"


@pytest.mark.parametrize(
    ("content", "code"),
    [("not json", "acceptance_checklist_unparsable"),
     ("{}", "acceptance_checklist_schema_mismatch")],
)
def test_full_joint_invalid_checklist_has_actionable_native_error(terminal_runner, content, code):
    runner, broker = terminal_runner
    runner._acceptance_target = "full_joint"
    path = runner.run.root / "joint-acceptance/joint-acceptance-checklist.json"
    path.parent.mkdir()
    path.write_text(content)
    with pytest.raises(RoutingError) as error:
        broker.report("coordinator", "completed", "premature")
    assert error.value.code == code
    runtime = CodexRuntimeAdapter(repository_root=Path(__file__).resolve().parents[2])
    assert runtime._safe_transport_error(None, str(error.value)) == str(error.value)
    assert "correct" in str(error.value)
    assert not broker.results


def test_unexpected_guard_failure_does_not_invent_a_retrieval_diagnosis(tmp_path):
    def broken_guard(*_args):
        raise RuntimeError("private diagnostic must not be reflected")

    broker = TeamTransportBroker(tmp_path / "transport", set(), terminal_report_guard=broken_guard)
    with pytest.raises(RoutingError) as error:
        broker.report("modeling", "completed", "done")
    assert "guard failed" in str(error.value)
    assert "private diagnostic" not in str(error.value)
    assert "query_semantic_context" not in str(error.value)
    broker.stop()


def test_native_dynamic_transport_relays_the_pending_issue_reason(terminal_runner):
    _runner, broker = terminal_runner
    broker.issue_ledger.report(
        reporter_id="modeling", category="business_clarification", summary="pending",
        failing_operation="submission", error="upstream pending", mutation_state="not_written",
        requested_action="resolve the original issue",
    )
    with pytest.raises(RoutingError) as error:
        broker.report("modeling", "completed", "ready")
    runtime = CodexRuntimeAdapter(repository_root=Path(__file__).resolve().parents[2])
    assert runtime._safe_transport_error(None, str(error.value)) == str(error.value)
    assert "active issue" in str(error.value)
    assert runtime._safe_transport_error(None, "terminal guard failed: arbitrary private bytes") is None
