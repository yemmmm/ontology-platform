"""R2.3-009 follow-up (start5 live evidence 2026-08-20): examiner-terminal wake.

Both cq-002 Examiner children in start5 ended their single turn without an
accepted report (empty ``evidence_refs``), the watchdog recorded child-timeout
infrastructure failures, and the persistent Acceptance role -- which had ended
its turn "awaiting terminal reports" -- had no wake mechanism, so the run
deadlocked into T3.  The carrier now queues every child terminal transition
(ingested report or recorded infrastructure failure) and the Host drain loop
wakes Acceptance with one mechanical notification.  These tests stay below the
semantic boundary: a deterministic child resource and a stub carrier prove the
queue and the wake without a model or provider process.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.runtimes.base import RuntimeDelivery
from modeling_team.runtimes.codex import _CodexChildResource
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_r23005_candidate_progress import (
    _FormalProgressAdapter,
    _formal_progress_runner,
)
from modeling_team.tests.test_r23005_contracts import _report, _ticket


class _ProbeProcess:
    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _start(carrier: RunnerAcceptanceCarrier, ticket: dict, *, request_id: str):
    projection, digest = carrier.project_child_input(
        round_id=ticket["acceptance_round_id"], kind="source"
    )
    return carrier.start_child(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        kind="source",
        input_ref=projection,
        input_digest=digest,
        ticket_digest_value=ticket["ticket_digest"],
        request_id=request_id,
        attempt=0,
    )


def _carrier(directory: str, ticket: dict, resources: list | None = None) -> RunnerAcceptanceCarrier:
    def factory(spec: dict) -> _CodexChildResource:
        # Bounded watchdog so the failure-first path records on its own.
        spec["timeout_seconds"] = 0.03
        resource = _CodexChildResource(spec, _ProbeProcess())
        if resources is not None:
            resources.append(resource)
        return resource

    carrier = RunnerAcceptanceCarrier(
        Path(directory),
        task_id=ticket["task_id"],
        acceptance_id="acceptance",
        child_factory=factory,
    )
    carrier.publish_ticket(
        ticket,
        coordinator_id="coordinator",
        owner_revision=ticket["quality_standard_ref"],
    )
    carrier.ack_ticket(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        ticket_digest_value=ticket["ticket_digest"],
    )
    return carrier


class ExaminerTerminalEventTests(unittest.TestCase):
    def test_report_and_failure_each_queue_one_terminal_event(self) -> None:
        with tempfile.TemporaryDirectory() as report_directory:
            resources: list[_CodexChildResource] = []
            carrier = _carrier(report_directory, _ticket("start5-report-event"), resources)
            ticket = carrier._tickets[_ticket("start5-report-event")["acceptance_round_id"]]
            handle = _start(carrier, ticket, request_id="report-event")
            resource = resources[0]
            report = resource.spec["report_submit"](_report(ticket, handle, kind="source"))
            events = carrier.drain_child_terminal_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["outcome"], "report")
            self.assertEqual(events[0]["examiner_kind"], "source")
            self.assertEqual(events[0]["report_digest"], report["report_digest"])
            # Draining clears the queue: no duplicate wake on the next drain.
            self.assertEqual(carrier.drain_child_terminal_events(), [])
            carrier.cleanup()

    def test_infrastructure_failure_queues_terminal_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resources: list[_CodexChildResource] = []
            carrier = _carrier(directory, _ticket("start5-failure-event"), resources)
            ticket = carrier._tickets[_ticket("start5-failure-event")["acceptance_round_id"]]
            handle = _start(carrier, ticket, request_id="failure-event")
            resource = resources[0]
            self.assertTrue(resource._record_failure("runtime", "child-timeout"))
            # A late duplicate failure callback must not queue a second event.
            self.assertFalse(resource._record_failure("runtime", "late-watchdog"))
            events = carrier.drain_child_terminal_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["outcome"], "failure")
            self.assertEqual(events[0]["reason_code"], "child-timeout")
            self.assertIn("failure_digest", events[0])
            carrier.cleanup()


class _StubAcceptanceCarrier:
    def __init__(self, events: list[dict]) -> None:
        self.is_settled = False
        self._events = events

    def drain_child_terminal_events(self) -> list[dict]:
        events = self._events
        self._events = []
        return events


class _IssuePendingLedger:
    pending = True


class ExaminerTerminalWakeTests(unittest.TestCase):
    def test_runner_wakes_acceptance_once_per_terminal_event(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path as _Path

            adapter = _FormalProgressAdapter()
            runner = _formal_progress_runner(_Path(directory), adapter)
            runner.acceptance = _StubAcceptanceCarrier(
                [
                    {
                        "acceptance_round_id": "round-1",
                        "examiner_kind": "platform",
                        "outcome": "failure",
                        "failure_digest": "a" * 64,
                        "reason_code": "child-timeout",
                    }
                ]
            )
            runner.drain()
            wakes = [
                delivery
                for recipient, delivery in adapter.sent
                if recipient == "acceptance" and delivery.kind == "examiner-terminal"
            ]
            self.assertEqual(len(wakes), 1)
            self.assertEqual(wakes[0].sender_id, "runner/examiner-terminal")
            event = json.loads(wakes[0].text)
            self.assertEqual(event["acceptance_round_id"], "round-1")
            self.assertEqual(event["outcome"], "failure")
            # The queue was drained: a second drain sends no duplicate wake.
            runner.drain()
            self.assertEqual(
                len(
                    [
                        delivery
                        for recipient, delivery in adapter.sent
                        if recipient == "acceptance" and delivery.kind == "examiner-terminal"
                    ]
                ),
                1,
            )

    def test_runner_keeps_events_queued_while_issue_pending(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path as _Path

            adapter = _FormalProgressAdapter()
            runner = _formal_progress_runner(_Path(directory), adapter)
            stub = _StubAcceptanceCarrier(
                [
                    {
                        "acceptance_round_id": "round-1",
                        "examiner_kind": "source",
                        "outcome": "report",
                        "report_digest": "b" * 64,
                    }
                ]
            )
            runner.acceptance = stub
            runner.transport._issues = _IssuePendingLedger()
            runner.drain()
            self.assertEqual(
                [
                    delivery
                    for recipient, delivery in adapter.sent
                    if delivery.kind == "examiner-terminal"
                ],
                [],
            )
            # The event is still queued and fires once the issue resolves.
            runner.transport._issues = None
            runner.drain()
            self.assertEqual(
                len(
                    [
                        delivery
                        for recipient, delivery in adapter.sent
                        if delivery.kind == "examiner-terminal"
                    ]
                ),
                1,
            )

    def test_runner_skips_wake_once_acceptance_settled(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path as _Path

            adapter = _FormalProgressAdapter()
            runner = _formal_progress_runner(_Path(directory), adapter)
            runner.acceptance = _StubAcceptanceCarrier(
                [
                    {
                        "acceptance_round_id": "round-1",
                        "examiner_kind": "source",
                        "outcome": "report",
                        "report_digest": "c" * 64,
                    }
                ]
            )
            runner.acceptance.is_settled = True
            runner.drain()
            self.assertEqual(
                [
                    delivery
                    for _, delivery in adapter.sent
                    if delivery.kind == "examiner-terminal"
                ],
                [],
            )
