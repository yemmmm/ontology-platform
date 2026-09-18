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

import pytest

from modeling_team.contracts import TeamConfigurationError
from modeling_team.interventions import RecoverableOuterInputError
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker


class _CapturingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, RuntimeDelivery]] = []

    def send_message(self, recipient_id: str, delivery: RuntimeDelivery):
        self.sent.append((recipient_id, delivery))
        return RuntimeDispatchReceipt("start", "turn-1")


def _runner_with_pending_issue(
    root: Path, *, reporter: str, wire_issue_events: bool = False
) -> tuple[TeamRunner, dict]:
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

    # Mirrors the ``start()`` wiring: broker controls land in the Runner's
    # issue event queue for main-loop dispatch. Off by default so the legacy
    # fan-out tests keep pinning only the delivery side.
    def issue_event_callback(event: dict) -> None:
        with runner._issue_event_lock:
            runner._issue_event_queue.append(dict(event))

    # ``receive_outer`` pumps ``drain`` once after admission; these tests pin
    # the delivery fan-out only, so the main-loop pump is stubbed out.
    runner.drain = lambda: []  # type: ignore[method-assign]
    runner.transport = TeamTransportBroker(
        root / "modeling-runs" / "run-1" / "transport" / "broker",
        {(reporter, "coordinator"), ("coordinator", reporter)},
        coordinator_agent_id="coordinator",
        issue_escalation_enabled=True,
        issue_event_callback=issue_event_callback if wire_issue_events else None,
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


def test_short_external_service_repair_keeps_optional_legacy_fields_optional() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")
        runner.receive_outer(
            {
                "action": "issue_resolution",
                "run_id": report["run_id"],
                "issue_id": report["issue_id"],
                "reporter_id": "protocol",
                "control_epoch": 1,
                "resolution_type": "repair_completed",
                "repair_component": "external_service",
                "resolution_text": "Temporary HTTP service is healthy again.",
            }
        )
        resolution = runner.transport.issue_ledger.active.resolution
        assert resolution is not None
        assert resolution.repair_component == "external_service"
        assert resolution.before_digest is None
        assert resolution.after_digest is None
        # 2026-09-18 #31 (auth021): the outer resolution now settles the
        # ledger itself (resume control through the broker); the main-loop
        # dispatch that marks it resolved is stubbed out in this harness, so
        # the observable state after ``receive_outer`` is ``resume_sent``.
        assert runner.transport.issue_ledger.state == "resume_sent"


def test_outer_resolution_settles_ledger_and_queues_resume_dispatch() -> None:
    """#31 (auth021): an outer resolution is the host's authoritative settlement.

    The Runner drives the resume control itself through the same broker entry
    point a Coordinator resume would use, instead of waiting for the
    Coordinator model to re-issue a byte-identical resume (start1 stalled
    ~50 min on that model-dependent step while ``pending`` short-circuited
    the idle fallback).
    """
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(
            Path(directory), reporter="protocol", wire_issue_events=True
        )
        runner.receive_outer(
            {
                "action": "issue_resolution",
                "issue_id": report["issue_id"],
                "reporter_id": "protocol",
                "control_epoch": 1,
                "resolution_type": "guidance",
                "resolution_text": "Proceed with the reconciled binding.",
            }
        )
        assert runner.transport.issue_ledger.state == "resume_sent"
        with runner._issue_event_lock:
            queued = list(runner._issue_event_queue)
        resumes = [
            event["control"]
            for event in queued
            if isinstance(event, dict)
            and event.get("kind") == "issue_control"
            and isinstance(event.get("control"), dict)
            and event["control"].get("action") == "resume"
        ]
        assert resumes, "runner settlement must queue a resume control dispatch"
        assert resumes[-1]["issue_id"] == report["issue_id"]
        assert resumes[-1]["reporter_id"] == "protocol"


def test_coordinator_resume_after_runner_settlement_is_typed_rejected() -> None:
    """#31: a Coordinator resume racing the Runner settlement gets the ledger's
    typed stale-state rejection instead of a second dispatch."""
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")
        runner.receive_outer(
            {
                "action": "issue_resolution",
                "issue_id": report["issue_id"],
                "reporter_id": "protocol",
                "control_epoch": 1,
                "resolution_type": "guidance",
                "resolution_text": "Proceed with the reconciled binding.",
            }
        )
        assert runner.transport.issue_ledger.state == "resume_sent"
        persisted = runner.transport.issue_ledger.active.resolution
        assert persisted is not None
        with pytest.raises(RoutingError, match="issue resume requires persisted resolution"):
            runner.transport.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="protocol",
                action="resume",
                control_epoch=1,
                resolution=persisted,
            )


def test_abort_resolution_settles_ledger_to_aborted() -> None:
    """#31: an outer abort resolution settles the ledger terminally — the
    runner drives the abort control with the resolution text as reason."""
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")
        runner.receive_outer(
            {
                "action": "issue_resolution",
                "issue_id": report["issue_id"],
                "reporter_id": "protocol",
                "control_epoch": 1,
                "resolution_type": "abort",
                "resolution_text": "Abandon this run; the upstream task is void.",
            }
        )
        ledger = runner.transport.issue_ledger
        assert ledger.state == "aborted"
        assert ledger.pending is False


def test_legacy_repair_envelope_requires_complete_values_without_run_id() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")
        base = {
            "action": "issue_resolution",
            "issue_id": report["issue_id"],
            "reporter_id": "protocol",
            "control_epoch": 1,
            "resolution_type": "repair_completed",
            "repair_component": "external_service",
        }
        for sparse in (
            {
                "before_digest": None,
                "after_digest": None,
                "verification_reference": None,
                "mutation_reconciliation": None,
            },
            {
                "before_digest": "",
                "after_digest": "",
                "verification_reference": "",
                "mutation_reconciliation": "",
            },
        ):
            with pytest.raises(RecoverableOuterInputError, match="requires run_id"):
                runner._outer_issue_resolution({**base, **sparse})

        runner.receive_outer(
            {
                **base,
                "repair_component": "external_service",
                "before_digest": "before-digest",
                "after_digest": "after-digest",
                "verification_reference": "verification-ref",
                "mutation_reconciliation": "verified",
            }
        )
        resolution = runner.transport.issue_ledger.active.resolution
        assert resolution is not None
        assert resolution.run_id == report["run_id"]
        assert resolution.before_digest == "before-digest"
        assert resolution.mutation_reconciliation == "verified"


def test_outer_repair_rejections_are_typed_and_do_not_consume_issue() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")
        base = {
            "action": "issue_resolution",
            "issue_id": report["issue_id"],
            "reporter_id": "protocol",
            "control_epoch": 1,
            "resolution_type": "repair_completed",
            "repair_component": "external_service",
        }
        cases = (
            ({"action": "user"}, "invalid_issue_resolution"),
            ({"run_id": None}, "issue_run_mismatch"),
            ({"resolution_type": []}, "invalid_issue_resolution"),
            ({"resolution_type": {}}, "invalid_issue_resolution"),
            ({"resolution_type": None}, "invalid_issue_resolution"),
            ({"resolution_type": True}, "invalid_issue_resolution"),
            ({"repair_component": "unsupported"}, "repair_rebind_required"),
        )
        for update, code in cases:
            with pytest.raises(RecoverableOuterInputError) as raised:
                runner._outer_issue_resolution({**base, **update})
            assert raised.value.code == code
        assert runner.transport.issue_ledger.state == "waiting_owner"
        assert runner.transport.issue_ledger.active.resolution is None


def test_internal_persistence_error_remains_fatal_after_outer_validation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runner, report = _runner_with_pending_issue(Path(directory), reporter="protocol")

        def fail_persist(_resolution):
            raise RoutingError("internal persistence failure")

        runner.transport.persist_issue_resolution = fail_persist
        with pytest.raises(RoutingError, match="internal persistence failure"):
            runner.receive_outer(
                {
                    "action": "issue_resolution",
                    "run_id": report["run_id"],
                    "issue_id": report["issue_id"],
                    "reporter_id": "protocol",
                    "control_epoch": 1,
                    "resolution_type": "repair_completed",
                    "repair_component": "external_service",
                }
            )
