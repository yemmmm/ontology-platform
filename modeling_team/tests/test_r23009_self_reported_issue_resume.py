"""R2.3-009 start20: a Coordinator-reported issue must be resumable.

The Coordinator reports an issue on its own behalf (``reporter_id`` equals the
coordinator id) and later dispatches the resume control from inside its own
live turn.  The previous resume gate demanded an idle reporter and a freshly
started turn — expectations a self-reporting Coordinator can never satisfy —
so the owner's resolution tore the whole run down with a fatal
``issue resume requires an idle reporter``.  The dispatch must instead skip
the redundant reporter delivery (the Coordinator already holds the ruling it
passed in) and resume the run, while a busy non-coordinator reporter still
fails closed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import TeamConfigurationError
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt
from modeling_team.transport_mcp import IssueResolution, TeamTransportBroker


class _Adapter:
    def __init__(self, busy: dict[str, str | None]) -> None:
        self.agents = {
            agent_id: SimpleNamespace(
                process=None, thread_id=f"thread-{agent_id}", active_turn_id=turn
            )
            for agent_id, turn in busy.items()
        }
        self.sent: list[tuple[str, RuntimeDelivery]] = []

    def send_message(self, recipient_id: str, delivery: RuntimeDelivery):
        self.sent.append((recipient_id, delivery))
        return RuntimeDispatchReceipt("start", "turn-new")


def _runner_with_paused_issue(root: Path, *, reporter: str) -> tuple[TeamRunner, dict]:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    run = SimpleNamespace(
        run_id="run-1",
        root=root / "run-1",
        configuration=SimpleNamespace(
            profile=SimpleNamespace(agents=agents, parameters={})
        ),
    )
    adapter = _Adapter(
        {"coordinator": "turn-live"} if reporter == "coordinator" else {"coordinator": None}
    )
    runner = object.__new__(TeamRunner)
    runner.run = run
    runner.adapter = adapter
    runner._candidate_progress = None
    runner._issue_abort_requested = False
    runner._append_evidence = lambda *_args, **_kwargs: None
    runner._state = lambda *_args, **_kwargs: None
    runner.transport = TeamTransportBroker(
        root / "modeling-runs" / "run-1" / "transport" / "broker",
        {("modeling", "coordinator"), ("coordinator", "modeling")},
        coordinator_agent_id="coordinator",
        issue_escalation_enabled=True,
    )
    report = runner.transport.report_issue(
        reporter,
        category="business_clarification",
        summary="clarification",
        failing_operation="modeling_semantic_clarification",
        error="unanswered",
        mutation_state="no_mutation",
        requested_action="clarify",
    )
    runner.transport.bind_issue_context(
        issue_id=report["issue_id"],
        reporter_id=reporter,
        thread_id=f"thread-{reporter}",
        candidate_identity=None,
    )
    pause = runner.transport.issue_control(
        "coordinator",
        issue_id=report["issue_id"],
        reporter_id=reporter,
        action="pause",
        control_epoch=1,
    )
    runner.transport.mark_issue_dispatch(runner._issue_control_from_payload(pause))
    resolution = IssueResolution(
        run_id=report["run_id"],
        issue_id=report["issue_id"],
        reporter_id=reporter,
        resolution_type="guidance",
        control_epoch=1,
        resolution_text="Preserve the behavior as an explicit unknown.",
    )
    runner.transport.persist_issue_resolution(resolution)
    resume = runner.transport.issue_control(
        "coordinator",
        issue_id=report["issue_id"],
        reporter_id=reporter,
        action="resume",
        control_epoch=1,
        resolution=resolution,
    )
    return runner, resume


def test_self_reported_issue_resumes_from_coordinator_live_turn() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runner, resume = _runner_with_paused_issue(
            Path(directory), reporter="coordinator"
        )
        output: list[dict] = []
        runner._dispatch_issue_control(runner._issue_control_from_payload(resume), output)
        # No reporter delivery is needed: the Coordinator already holds the
        # resolution inside its own live turn.
        assert runner.adapter.sent == []
        assert [entry["type"] for entry in output] == ["issue-control"]
        assert output[0]["action"] == "resume"
        ledger = runner.transport.issue_ledger
        # The resume cleared the owner wait; the ledger is resolved, not torn
        # down to ``rebind_required``.
        assert ledger.state == "resolved"


def test_busy_non_coordinator_reporter_still_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runner, resume = _runner_with_paused_issue(root, reporter="modeling")
        # Put the modeling reporter mid-turn, as in the pre-existing contract.
        runner.adapter.agents["modeling"] = SimpleNamespace(
            process=None, thread_id="thread-modeling", active_turn_id="turn-active"
        )
        try:
            runner._dispatch_issue_control(
                runner._issue_control_from_payload(resume), []
            )
        except TeamConfigurationError as exc:
            assert "requires an idle reporter" in str(exc)
        else:
            raise AssertionError("busy non-coordinator reporter must fail closed")
