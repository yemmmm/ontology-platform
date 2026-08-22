"""R2.3-009 start15/start20: an owner ruling must reach Modeling mechanically.

The Coordinator's discretionary relay of an owner issue resolution to Modeling
proved unreliable twice: Modeling kept a stale precondition (an unanswered
owner question in start15; a digest-mismatched one-time gate notice in start20)
while the ruling that lifted it never arrived, and the run deadlocked.  The
``issue_resolution`` outer action now also delivers the ruling text to the
Modeling role directly; delivery failure is recorded evidence, never a
teardown of the already-persisted resolution.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import TeamConfigurationError
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt
from modeling_team.transport_mcp import TeamTransportBroker


class _CapturingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, RuntimeDelivery]] = []

    def send_message(self, recipient_id: str, delivery: RuntimeDelivery):
        self.sent.append((recipient_id, delivery))
        return RuntimeDispatchReceipt("start", "turn-1")


def _runner_with_pending_issue(root: Path, *, reporter: str) -> tuple[TeamRunner, dict]:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    run = SimpleNamespace(
        run_id="run-1",
        root=root / "run-1",
        scope={"mode": "create"},
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
            profile=SimpleNamespace(profile_id="p", agents=agents, parameters={}),
        ),
    )
    runner = object.__new__(TeamRunner)
    runner.run = run
    runner.adapter = _CapturingAdapter()
    evidence: list[tuple[object, object]] = []
    runner._append_evidence = lambda name, payload: evidence.append((name, payload))
    runner._state = lambda *_args, **_kwargs: None
    runner._candidate_progress = None
    import threading
    runner._issue_event_lock = threading.Lock()
    runner._issue_event_queue = []
    # ``receive_outer`` pumps ``drain`` once after admission; these tests pin
    # the delivery fan-out only, so the main-loop pump is stubbed out.
    runner.drain = lambda: []  # type: ignore[method-assign]
    runner.transport = TeamTransportBroker(
        root / "modeling-runs" / "run-1" / "transport" / "broker",
        {(reporter, "coordinator"), ("coordinator", reporter)},
        coordinator_agent_id="coordinator",
        issue_escalation_enabled=True,
    )
    report = runner.transport.report_issue(
        reporter,
        category="protocol_guidance",
        summary="guidance",
        failing_operation="receipt",
        error="ambiguous",
        mutation_state="not_started",
        requested_action="clarify",
    )
    runner.transport.bind_issue_context(
        issue_id=report["issue_id"],
        reporter_id=reporter,
        thread_id="thread-1",
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
    return runner, report


def test_owner_resolution_is_delivered_to_modeling_and_coordinator() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runner, report = _runner_with_pending_issue(root, reporter="protocol")
        message = {
            "action": "issue_resolution",
            "issue_id": report["issue_id"],
            "reporter_id": "protocol",
            "control_epoch": 1,
            "resolution_type": "guidance",
            "resolution_text": "The authoritative digest is the accepted receipt.",
        }
        runner.receive_outer(message)
        recipients = [recipient for recipient, _ in runner.adapter.sent]
        assert recipients.count("coordinator") == 1
        assert recipients.count("modeling") == 1
        modeling_delivery = next(
            delivery for recipient, delivery in runner.adapter.sent
            if recipient == "modeling"
        )
        assert modeling_delivery.kind == "issue-resolution"
        assert "authoritative digest" in modeling_delivery.text


def test_modeling_delivery_failure_is_evidence_not_teardown() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runner, report = _runner_with_pending_issue(root, reporter="protocol")

        def fail_modeling(recipient_id: str, delivery: RuntimeDelivery):
            if recipient_id == "modeling":
                raise OSError("modeling runtime unavailable")
            return RuntimeDispatchReceipt("start", "turn-1")

        runner.adapter.send_message = fail_modeling
        evidence: list[tuple[object, object]] = []
        runner._append_evidence = lambda name, payload: evidence.append((name, payload))
        message = {
            "action": "issue_resolution",
            "issue_id": report["issue_id"],
            "reporter_id": "protocol",
            "control_epoch": 1,
            "resolution_type": "guidance",
            "resolution_text": "Proceed with the reconciled binding.",
        }
        runner.receive_outer(message)
        events = [
            payload.get("event") for name, payload in evidence
            if name == "issue-resolution" and isinstance(payload, dict)
        ]
        assert "modeling_delivery_failed" in events


def test_coordinator_delivery_failure_still_raises() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runner, report = _runner_with_pending_issue(root, reporter="protocol")

        def fail_coordinator(recipient_id: str, delivery: RuntimeDelivery):
            if recipient_id == "coordinator":
                raise OSError("coordinator runtime unavailable")
            return RuntimeDispatchReceipt("start", "turn-1")

        runner.adapter.send_message = fail_coordinator
        message = {
            "action": "issue_resolution",
            "issue_id": report["issue_id"],
            "reporter_id": "protocol",
            "control_epoch": 1,
            "resolution_type": "guidance",
            "resolution_text": "Proceed.",
        }
        try:
            runner.receive_outer(message)
        except TeamConfigurationError as exc:
            assert "Coordinator delivery failed" in str(exc)
        else:
            raise AssertionError("coordinator delivery failure must raise")
