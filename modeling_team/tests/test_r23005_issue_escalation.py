from __future__ import annotations

import json
import os
import subprocess
import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest

from modeling_team.acceptance import CoordinatorPhaseController
from modeling_team.candidate_progress import FormalCandidateProgress
from modeling_team.interventions import IssueControl, IssueError, IssueResolution
from modeling_team.runner import TeamConfigurationError, TeamRunner
from modeling_team.runtimes.base import RuntimeDispatchReceipt, RuntimeDelivery
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


def _candidate() -> dict[str, object]:
    return {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": "rev-1",
        "scope": "new",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "class-1",
                "item_kind": "class",
                "semantic": {"label": "Example"},
            }
        ],
    }


class IssueEscalationTests(unittest.TestCase):
    def test_staged_transport_starts_as_standalone_script(self) -> None:
        """The isolated Runtime must not need the repository package on sys.path."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "agent-home"
            home.mkdir()
            for name in ("transport_mcp.py", "interventions.py"):
                shutil.copyfile(Path(__file__).parents[1] / name, home / name)
            completed = subprocess.run(
                ["/usr/bin/python3", str(home / "transport_mcp.py")],
                input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "TEAM_TRANSPORT_SOCKET": str(home / "missing.sock")},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            response = json.loads(completed.stdout)
            self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")

    def test_strict_report_issue_and_one_active_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker"
            callbacks: list[dict[str, object]] = []
            broker = TeamTransportBroker(
                root,
                {
                    ("modeling", "coordinator"),
                    ("coordinator", "modeling"),
                },
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
                issue_event_callback=callbacks.append,
            )
            response = mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "report_issue",
                        "arguments": {
                            "category": "protocol_guidance",
                            "summary": "receipt interpretation needs guidance",
                            "failing_operation": "build_candidate_receipt",
                            "error": "model cannot distinguish parsing from semantic rebuild",
                            "mutation_state": "not_started",
                            "requested_action": "explain mechanical parsing",
                        },
                    },
                },
                broker=broker,
                agent_id="modeling",
            )
            report = json.loads(response["content"][0]["text"])
            self.assertEqual(report["issue_id"], "issue-1")
            self.assertEqual(report["state"], "reported")
            self.assertEqual(callbacks[0]["kind"], "issue_report")
            with self.assertRaisesRegex(RoutingError, "active issue"):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "report_issue",
                            "arguments": {
                                "category": "protocol_guidance",
                                "summary": "duplicate",
                                "failing_operation": "same",
                                "error": "same",
                                "mutation_state": "not_started",
                                "requested_action": "same",
                            },
                        },
                    },
                    broker=broker,
                    agent_id="modeling",
                )
            with self.assertRaisesRegex(RoutingError, "active issue"):
                broker.report("modeling", "blocked", "must wait")

    def test_pause_resolution_resume_is_cas_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            report = broker.report_issue(
                "modeling",
                category="protocol_guidance",
                summary="guidance needed",
                failing_operation="receipt",
                error="ambiguous contract",
                mutation_state="not_started",
                requested_action="clarify parse",
            )
            pause = broker.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="pause",
                control_epoch=1,
            )
            self.assertEqual(pause["action"], "pause")
            resolution = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="modeling",
                resolution_type="guidance",
                control_epoch=1,
                resolution_text="Parse JSON mechanically without changing any field.",
            )
            broker.persist_issue_resolution(resolution)
            resumed = broker.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="resume",
                control_epoch=1,
                resolution=resolution,
            )
            self.assertEqual(resumed["action"], "resume")
            broker.mark_issue_dispatch(
                TeamRunner._issue_control_from_payload(  # type: ignore[misc]
                    object.__new__(TeamRunner), resumed
                )
            )
            self.assertFalse(broker.issue_ledger.pending)

    def test_issue_control_normalizes_nullable_optional_fields_for_pause_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("protocol", "coordinator"), ("coordinator", "protocol")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            listed = mcp_response(
                {"method": "tools/list"}, broker=broker, agent_id="coordinator"
            )
            issue_tool = next(tool for tool in listed["tools"] if tool["name"] == "issue_control")
            schema = issue_tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            # 2026-09-11: the advertised schema is flat; the oneOf form made
            # the model emit empty tool-call arguments, wedging the pause
            # dispatch at state `reported` (auth006-start9).  The server-side
            # normalize/validate keeps every action-specific rule.
            self.assertNotIn("oneOf", schema)
            self.assertEqual(
                schema["required"],
                ["issue_id", "reporter_id", "action", "control_epoch"],
            )
            properties = schema["properties"]
            self.assertEqual(properties["action"]["enum"], ["pause", "resume", "abort"])
            for field in (
                "reason",
                "resolution_type",
                "resolution_text",
                "repair_component",
                "before_digest",
                "after_digest",
                "verification_reference",
                "mutation_reconciliation",
            ):
                self.assertIn(field, properties)
            report = broker.report_issue(
                "protocol",
                category="protocol_guidance",
                summary="guidance needed",
                failing_operation="receipt",
                error="ambiguous contract",
                mutation_state="not_started",
                requested_action="clarify parse",
            )
            nullable_optionals = {
                "resolution_type": None,
                "resolution_text": None,
                "repair_component": None,
                "before_digest": None,
                "after_digest": None,
                "verification_reference": None,
                "mutation_reconciliation": None,
                "reason": None,
            }
            pause = mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "issue_control",
                        "arguments": {
                            "issue_id": report["issue_id"],
                            "reporter_id": "protocol",
                            "action": "pause",
                            "control_epoch": 1,
                            **nullable_optionals,
                        },
                    },
                },
                broker=broker,
                agent_id="coordinator",
            )
            pause_payload = json.loads(pause["content"][0]["text"])
            self.assertEqual(pause_payload["action"], "pause")
            self.assertEqual(broker.issue_ledger.state, "waiting_owner")

            resolution = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="protocol",
                resolution_type="guidance",
                control_epoch=1,
                resolution_text="Use the frozen receipt fields.",
            )
            broker.persist_issue_resolution(resolution)
            resume = mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "issue_control",
                        "arguments": {
                            "issue_id": report["issue_id"],
                            "reporter_id": "protocol",
                            "action": "resume",
                            "control_epoch": 1,
                            "resolution_type": "guidance",
                            "resolution_text": resolution.resolution_text,
                            "repair_component": None,
                            "before_digest": None,
                            "after_digest": None,
                            "verification_reference": None,
                            "mutation_reconciliation": None,
                            "reason": None,
                        },
                    },
                },
                broker=broker,
                agent_id="coordinator",
            )
            resume_payload = json.loads(resume["content"][0]["text"])
            self.assertEqual(resume_payload["action"], "resume")
            self.assertEqual(resume_payload["resolution"]["resolution_type"], "guidance")

    def test_issue_control_mcp_abort_requires_persisted_reason_without_resolution_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("protocol", "coordinator"), ("coordinator", "protocol")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            report = broker.report_issue(
                "protocol",
                category="runtime_recovery",
                summary="runtime cannot continue",
                failing_operation="tool_call",
                error="runtime unavailable",
                mutation_state="not_started",
                requested_action="request outer disposition",
            )
            mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "issue_control",
                        "arguments": {
                            "issue_id": report["issue_id"],
                            "reporter_id": "protocol",
                            "action": "pause",
                            "control_epoch": 1,
                        },
                    },
                },
                broker=broker,
                agent_id="coordinator",
            )
            with self.assertRaisesRegex(RoutingError, "issue_control abort fields are invalid"):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "issue_control",
                            "arguments": {
                                "issue_id": report["issue_id"],
                                "reporter_id": "protocol",
                                "action": "abort",
                                "control_epoch": 1,
                            },
                        },
                    },
                    broker=broker,
                    agent_id="coordinator",
                )
            abort = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="protocol",
                resolution_type="abort",
                control_epoch=1,
                resolution_text="Stop this run.",
            )
            broker.persist_issue_resolution(abort)
            with self.assertRaisesRegex(RoutingError, "issue_control abort fields are invalid"):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "issue_control",
                            "arguments": {
                                "issue_id": report["issue_id"],
                                "reporter_id": "protocol",
                                "action": "abort",
                                "control_epoch": 1,
                                "reason": abort.resolution_text,
                                "resolution_type": "abort",
                            },
                        },
                    },
                    broker=broker,
                    agent_id="coordinator",
                )
            result = mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "issue_control",
                        "arguments": {
                            "issue_id": report["issue_id"],
                            "reporter_id": "protocol",
                            "action": "abort",
                            "control_epoch": 1,
                            "reason": abort.resolution_text,
                        },
                    },
                },
                broker=broker,
                agent_id="coordinator",
            )
            payload = json.loads(result["content"][0]["text"])
            self.assertEqual(payload["action"], "abort")
            self.assertEqual(payload["reason"], abort.resolution_text)
            self.assertFalse(broker.issue_ledger.pending)

    def test_issue_control_rejects_unknown_and_non_null_pause_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("protocol", "coordinator"), ("coordinator", "protocol")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            with self.assertRaisesRegex(IssueError, "non-abort control cannot contain a reason"):
                IssueControl(
                    run_id="run-1",
                    issue_id="issue-1",
                    coordinator_id="coordinator",
                    reporter_id="protocol",
                    action="pause",
                    control_epoch=1,
                    reason="not allowed",
                )
            with self.assertRaisesRegex(RoutingError, "issue_control arguments are invalid"):
                mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "issue_control",
                            "arguments": {
                                "issue_id": "issue-1",
                                "reporter_id": "protocol",
                                "action": "pause",
                                "control_epoch": 1,
                                "unknown": None,
                            },
                        },
                    },
                    broker=broker,
                    agent_id="coordinator",
                )

    def test_candidate_active_clock_freezes_while_paused(self) -> None:
        now = [0.0]
        progress = FormalCandidateProgress(clock=lambda: now[0], timeout_seconds=10)
        delivery = SimpleNamespace(
            sender_id="modeling",
            recipient_id="protocol",
            expects_reply=True,
            reply_to_delivery_id=None,
            delivery_id="delivery-1",
            text=json.dumps(_candidate()),
        )
        progress.observe_delivery(
            delivery,
            modeling_agent_id="modeling",
            protocol_agent_id="protocol",
            run_id="run-1",
            protocol_thread_id="thread-1",
        )
        progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"), now=now[0])
        now[0] = 8
        progress.pause(now=now[0])
        now[0] = 1000
        progress.check_deadline(now=now[0])
        self.assertTrue(progress.paused)
        self.assertFalse(progress.redrive_ready(now=now[0]))
        progress.resume(now=now[0])
        self.assertFalse(progress.check_deadline(now=1001))
        self.assertTrue(progress.check_deadline(now=1002))

    def test_unknown_write_cannot_resume_via_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            report = broker.report_issue(
                "modeling",
                category="platform_repair",
                summary="apply result is unknown",
                failing_operation="apply_atomic",
                error="receipt was not returned",
                mutation_state="apply result uncertain",
                requested_action="reconcile receipt and readback",
            )
            broker.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="pause",
                control_epoch=1,
            )
            guidance = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="modeling",
                resolution_type="guidance",
                control_epoch=1,
                resolution_text="Continue with the same candidate.",
            )
            with self.assertRaisesRegex(RoutingError, "requires formal reconciliation"):
                broker.persist_issue_resolution(guidance)
            self.assertEqual(broker.issue_ledger.state, "waiting_repair")

    def test_outer_abort_cannot_be_recast_as_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            report = broker.report_issue(
                "modeling",
                category="runtime_recovery",
                summary="runtime cannot continue",
                failing_operation="tool_call",
                error="runtime unavailable",
                mutation_state="not_started",
                requested_action="request outer disposition",
            )
            broker.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="pause",
                control_epoch=1,
            )
            abort = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="modeling",
                resolution_type="abort",
                control_epoch=1,
                resolution_text="Stop this run.",
            )
            broker.persist_issue_resolution(abort)
            with self.assertRaisesRegex(RoutingError, "cannot carry an abort"):
                broker.issue_control(
                    "coordinator",
                    issue_id=report["issue_id"],
                    reporter_id="modeling",
                    action="resume",
                    control_epoch=1,
                    resolution=abort,
                )
            with self.assertRaisesRegex(RoutingError, "does not match"):
                broker.issue_control(
                    "coordinator",
                    issue_id=report["issue_id"],
                    reporter_id="modeling",
                    action="abort",
                    control_epoch=1,
                    reason="Different reason.",
                )
            control = broker.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="abort",
                control_epoch=1,
                reason="Stop this run.",
            )
            self.assertEqual(control["action"], "abort")
            self.assertFalse(broker.issue_ledger.pending)

    def test_runner_issue_control_uses_runtime_delivery_not_pause_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = SimpleNamespace(
                run_id="run-1",
                root=root,
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(agent_id="coordinator", package=SimpleNamespace(role="coordinator")),
                            SimpleNamespace(agent_id="modeling", package=SimpleNamespace(role="modeling")),
                        ]
                    ),
                ),
            )

            class Adapter:
                agents: dict[str, object] = {}

                def __init__(self) -> None:
                    self.sent: list[RuntimeDelivery] = []
                    self.pause_called = False

                def send_message(self, _agent_id: str, delivery: RuntimeDelivery) -> RuntimeDispatchReceipt:
                    self.sent.append(delivery)
                    return RuntimeDispatchReceipt("start", "turn-2")

                def pause(self) -> None:
                    self.pause_called = True

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = run
            runner.adapter = adapter
            runner.transport = TeamTransportBroker(
                root / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            runner._candidate_progress = None
            runner._issue_abort_requested = False
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._state = lambda *_args, **_kwargs: None
            report = runner.transport.report_issue(
                "modeling",
                category="protocol_guidance",
                summary="guidance",
                failing_operation="receipt",
                error="ambiguous",
                mutation_state="not_started",
                requested_action="clarify",
            )
            runner.transport.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="pause",
                control_epoch=1,
            )
            controls = runner.transport.issue_ledger.drain_controls()
            self.assertEqual(len(controls), 1)
            # The main loop dispatches this control through RuntimeDelivery; it
            # never calls RuntimeAdapter.pause or turn/interrupt.
            output: list[dict[str, object]] = []
            runner._dispatch_issue_control(controls[0], output)
            self.assertFalse(adapter.pause_called)
            self.assertEqual(adapter.sent[0].kind, "issue-control")
            self.assertEqual(output[0]["type"], "issue")
            self.assertEqual(output[0]["issue"]["state"], "waiting_owner")

    def test_runner_resume_requires_reporter_to_finish_paused_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = SimpleNamespace(
                run_id="run-1",
                root=root,
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(
                                agent_id="coordinator",
                                package=SimpleNamespace(role="coordinator"),
                            ),
                            SimpleNamespace(
                                agent_id="modeling",
                                package=SimpleNamespace(role="modeling"),
                            ),
                        ]
                    )
                ),
            )

            class Adapter:
                def __init__(self) -> None:
                    self.sent: list[RuntimeDelivery] = []
                    self.agents = {
                        "modeling": SimpleNamespace(
                            process=None,
                            thread_id="thread-1",
                            active_turn_id="turn-active",
                        )
                    }

                def send_message(
                    self, _agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append(delivery)
                    return RuntimeDispatchReceipt("steer", "turn-active")

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = run
            runner.adapter = adapter
            runner.transport = TeamTransportBroker(
                root / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            runner._candidate_progress = None
            runner._issue_abort_requested = False
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._state = lambda *_args, **_kwargs: None
            report = runner.transport.report_issue(
                "modeling",
                category="protocol_guidance",
                summary="guidance",
                failing_operation="receipt",
                error="ambiguous",
                mutation_state="not_started",
                requested_action="clarify",
            )
            runner.transport.bind_issue_context(
                issue_id=report["issue_id"],
                reporter_id="modeling",
                thread_id="thread-1",
                candidate_identity=None,
            )
            pause = runner.transport.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="pause",
                control_epoch=1,
            )
            runner.transport.mark_issue_dispatch(runner._issue_control_from_payload(pause))
            resolution = IssueResolution(
                run_id=report["run_id"],
                issue_id=report["issue_id"],
                reporter_id="modeling",
                resolution_type="guidance",
                control_epoch=1,
                resolution_text="Use the frozen receipt fields.",
            )
            runner.transport.persist_issue_resolution(resolution)
            resume = runner.transport.issue_control(
                "coordinator",
                issue_id=report["issue_id"],
                reporter_id="modeling",
                action="resume",
                control_epoch=1,
                resolution=resolution,
            )
            with self.assertRaisesRegex(TeamConfigurationError, "requires an idle reporter"):
                runner._dispatch_issue_control(runner._issue_control_from_payload(resume), [])
            self.assertEqual(adapter.sent, [])
            self.assertEqual(runner.transport.issue_ledger.state, "rebind_required")

    def test_cleanup_is_deferred_while_issue_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = object.__new__(TeamRunner)
            runner._cleanup_evidence_cache = None
            runner._issue_abort_requested = False
            runner._state = lambda *_args, **_kwargs: None
            runner.transport = TeamTransportBroker(
                Path(directory) / "modeling-runs" / "run-1" / "transport" / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
            )
            report = runner.transport.report_issue(
                "modeling",
                category="protocol_guidance",
                summary="guidance",
                failing_operation="receipt",
                error="ambiguous",
                mutation_state="not_started",
                requested_action="clarify",
            )
            result = runner.cleanup()
            self.assertEqual(
                result,
                {
                    "status": "paused",
                    "issue_id": report["issue_id"],
                    "state": "reported",
                    "cleanup_deferred": True,
                },
            )

    def test_acceptance_issue_binds_numeric_runtime_thread_and_pauses_without_exit(self) -> None:
        """Acceptance may report before its ticket; Runner must keep the run recoverable."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-early-acceptance"
            root.mkdir(parents=True)
            actual_thread_id = "019fd181-0bce-7161-a0ff-fa2917f40dbe"

            class Adapter:
                def __init__(self) -> None:
                    self.agents = {
                        "acceptance": SimpleNamespace(
                            thread_id=actual_thread_id,
                            active_turn_id=None,
                            process=None,
                        )
                    }
                    self.sent: list[tuple[str, RuntimeDelivery]] = []

                def send_message(
                    self, agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append((agent_id, delivery))
                    return RuntimeDispatchReceipt("steer", "turn-issue")

                def receive_messages(self) -> list[object]:
                    return []

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(
                run_id="run-early-acceptance",
                root=root,
                configuration=SimpleNamespace(
                    task=SimpleNamespace(
                        schema_version=2,
                        task_id="r2-3-005-formal-acceptance",
                    ),
                    profile=SimpleNamespace(
                        profile_id="r2-3-005-modeling-team",
                        agents=[
                            SimpleNamespace(
                                agent_id="coordinator", package=SimpleNamespace(role="coordinator")
                            ),
                            SimpleNamespace(
                                agent_id="acceptance", package=SimpleNamespace(role="acceptance")
                            ),
                        ],
                    ),
                ),
            )
            runner.adapter = adapter
            runner._candidate_progress = None
            # ``object.__new__`` skips ``__init__``; this legacy fixture runs
            # with competency questions disabled, which the constructor would
            # otherwise have established.
            runner._competency_questions = False
            runner._append_evidence = lambda *_args, **_kwargs: None
            states: list[tuple[str, dict[str, object]]] = []
            runner._state = lambda value, **extra: states.append((value, extra))
            runner._issue_abort_requested = False
            runner._issue_event_queue = []
            runner._issue_event_lock = threading.Lock()
            runner._coordination_runtime_queue = []
            runner._coordination_runtime_lock = threading.Lock()
            runner._coordination_runtime_message_ids = set()
            runner.transport = TeamTransportBroker(
                root / "transport" / "broker",
                {("acceptance", "coordinator"), ("coordinator", "acceptance")},
                coordinator_agent_id="coordinator",
                issue_escalation_enabled=True,
                issue_event_callback=runner._issue_event_queue.append,
            )
            report = runner.transport.report_issue(
                "acceptance",
                category="runtime_recovery",
                summary="Acceptance started before the round ticket was available",
                failing_operation="acceptance_get_ticket",
                error="no acceptance round has been delivered yet",
                mutation_state="not_started",
                requested_action="wait for Runner acceptance-start delivery",
            )

            output = runner.drain()

            active_issue = runner.transport.issue_ledger.active_issue
            self.assertIsNotNone(active_issue)
            assert active_issue is not None
            self.assertEqual(active_issue.thread_id, actual_thread_id)
            self.assertEqual(runner.transport.issue_ledger.state, "reported")
            self.assertEqual(states[-1][0], "WAITING_OWNER")
            self.assertEqual(output, [])
            self.assertEqual(len(adapter.sent), 1)
            self.assertEqual(adapter.sent[0][0], "coordinator")
            self.assertEqual(adapter.sent[0][1].kind, "issue")
            delivered_issue = json.loads(adapter.sent[0][1].text)
            self.assertEqual(delivered_issue["issue_id"], report["issue_id"])
            self.assertEqual(delivered_issue["thread_id"], actual_thread_id)

    def test_acceptance_start_from_mcp_path_queues_one_runtime_delivery(self) -> None:
        """Agent-side send_coordination must deliver the fixed ticket arguments."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-acceptance-start"

            class Adapter:
                def __init__(self) -> None:
                    self.sent: list[tuple[str, RuntimeDelivery]] = []

                def send_message(
                    self, agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append((agent_id, delivery))
                    return RuntimeDispatchReceipt("steer", "turn-acceptance-start")

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(
                run_id="run-acceptance-start",
                root=root,
                configuration=SimpleNamespace(
                    task=SimpleNamespace(
                        schema_version=2,
                        task_id="r2-3-005-formal-acceptance",
                    ),
                    profile=SimpleNamespace(
                        profile_id="r2-3-005-modeling-team",
                        agents=[
                            SimpleNamespace(
                                agent_id="coordinator", package=SimpleNamespace(role="coordinator")
                            ),
                            SimpleNamespace(
                                agent_id="modeling", package=SimpleNamespace(role="modeling")
                            ),
                            SimpleNamespace(
                                agent_id="protocol", package=SimpleNamespace(role="protocol")
                            ),
                            SimpleNamespace(
                                agent_id="acceptance", package=SimpleNamespace(role="acceptance")
                            ),
                        ],
                    ),
                ),
            )
            runner.adapter = adapter
            runner.acceptance = SimpleNamespace(acceptance_id="acceptance")
            runner.coordinator_phase = CoordinatorPhaseController()
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._coordination_runtime_queue = []
            runner._coordination_runtime_lock = threading.Lock()
            runner._coordination_runtime_message_ids = set()
            runner.transport = TeamTransportBroker(
                root / "transport" / "broker",
                {
                    ("modeling", "coordinator"),
                    ("protocol", "coordinator"),
                    ("coordinator", "acceptance"),
                },
                coordinator_agent_id="coordinator",
                coordination_phase_callback=runner._coordination_phase_callback,
                coordination_event_observer=runner._coordination_transport_event_observer,
            )
            runner.coordinator_phase.start()
            runner.coordinator_phase.assign_slice(sender_id="coordinator", objective="bounded slice")
            generation = runner.coordinator_phase.generation
            for agent_id, message_kind in (
                ("modeling", "ready_for_acceptance"),
                ("protocol", "silent_for_acceptance"),
            ):
                response = mcp_response(
                    {
                        "method": "tools/call",
                        "params": {
                            "name": "send_coordination",
                            "arguments": {
                                "recipient_id": "coordinator",
                                "message_kind": message_kind,
                                "text": "",
                                "generation": generation,
                            },
                        },
                    },
                    broker=runner.transport,
                    agent_id=agent_id,
                )
                self.assertIn("coordination-", response["content"][0]["text"])
            runner._drain_coordination_runtime_deliveries()
            self.assertEqual(len(adapter.sent), 2)
            for (recipient_id, delivery), expected_kind in zip(
                adapter.sent,
                ("ready_for_acceptance", "silent_for_acceptance"),
                strict=True,
            ):
                self.assertEqual(recipient_id, "coordinator")
                self.assertEqual(delivery.kind, "coordination-phase")
                self.assertEqual(delivery.sender_id, "runner/coordination")
                self.assertEqual(delivery.recipient_id, "coordinator")
                self.assertIsNotNone(delivery.delivery_id)
                payload = json.loads(delivery.text)
                self.assertEqual(payload["message_kind"], expected_kind)
                self.assertEqual(payload["sender_id"], "modeling" if expected_kind == "ready_for_acceptance" else "protocol")
                self.assertEqual(payload["recipient_id"], "coordinator")
                self.assertEqual(payload["generation"], generation)
                self.assertEqual(payload["coordination_message_id"], delivery.delivery_id)
            start_response = mcp_response(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "send_coordination",
                        "arguments": {
                            "recipient_id": "acceptance",
                            "message_kind": "acceptance_start",
                            "text": "round-1",
                            "generation": generation,
                        },
                    },
                },
                broker=runner.transport,
                agent_id="coordinator",
            )
            start_envelope = json.loads(start_response["content"][0]["text"])
            self.assertEqual(runner.coordinator_phase.phase.value, "ACCEPTANCE_ROUND_ACTIVE")
            self.assertEqual(len(adapter.sent), 2)

            runner._drain_coordination_runtime_deliveries()

            self.assertEqual(len(adapter.sent), 3)
            recipient_id, delivery = adapter.sent[2]
            self.assertEqual(recipient_id, "acceptance")
            self.assertEqual(delivery.kind, "acceptance-start")
            self.assertEqual(delivery.delivery_id, start_envelope["message_id"])
            self.assertEqual(
                json.loads(delivery.text),
                {
                    "acceptance_id": "acceptance",
                    "coordination_message_id": start_envelope["message_id"],
                    "generation": generation,
                    "round_id": "round-1",
                },
            )
            runner._drain_coordination_runtime_deliveries()
            self.assertEqual(len(adapter.sent), 3)

    def test_readiness_delivery_deduplicates_same_generation_signal(self) -> None:
        """A repeated validated readiness signal cannot steer Coordinator twice."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-readiness-dedupe"
            root.mkdir(parents=True)

            class Adapter:
                def __init__(self) -> None:
                    self.sent: list[tuple[str, RuntimeDelivery]] = []

                def send_message(
                    self, agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append((agent_id, delivery))
                    return RuntimeDispatchReceipt("start", "turn-ready")

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(
                run_id="run-readiness-dedupe",
                root=root,
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(
                                agent_id="coordinator", package=SimpleNamespace(role="coordinator")
                            ),
                            SimpleNamespace(
                                agent_id="modeling", package=SimpleNamespace(role="modeling")
                            ),
                            SimpleNamespace(
                                agent_id="protocol", package=SimpleNamespace(role="protocol")
                            ),
                            SimpleNamespace(
                                agent_id="acceptance", package=SimpleNamespace(role="acceptance")
                            ),
                        ]
                    )
                ),
            )
            runner.adapter = adapter
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._coordination_runtime_queue = []
            runner._coordination_runtime_lock = threading.Lock()
            runner._coordination_runtime_message_ids = set()
            runner._coordination_runtime_signal_keys = set()
            event = {
                "sender_id": "modeling",
                "recipient_id": "coordinator",
                "message_kind": "ready_for_acceptance",
                "message_id": "coordination-1",
                "text": "ready",
                "timestamp": 1.0,
                "terminal": False,
                "settles": False,
                "phase_event": {"generation": 1},
            }
            runner._coordination_transport_event_observer(event)
            with self.assertRaisesRegex(TeamConfigurationError, "readiness delivery was queued twice"):
                runner._coordination_transport_event_observer(
                    {**event, "message_id": "coordination-2"}
                )
            runner._drain_coordination_runtime_deliveries()
            self.assertEqual(len(adapter.sent), 1)
            self.assertEqual(adapter.sent[0][1].delivery_id, "coordination-1")

    def test_verdict_route_delivery_preserves_identity_and_generation(self) -> None:
        """A validated Acceptance verdict reaches Coordinator without rewriting its JSON."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-verdict-route"
            root.mkdir(parents=True)

            class Adapter:
                def __init__(self) -> None:
                    self.sent: list[tuple[str, RuntimeDelivery]] = []

                def send_message(
                    self, agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append((agent_id, delivery))
                    return RuntimeDispatchReceipt("start", "turn-verdict")

            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(
                run_id="run-verdict-route",
                root=root,
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(
                                agent_id="coordinator", package=SimpleNamespace(role="coordinator")
                            ),
                            SimpleNamespace(
                                agent_id="modeling", package=SimpleNamespace(role="modeling")
                            ),
                            SimpleNamespace(
                                agent_id="protocol", package=SimpleNamespace(role="protocol")
                            ),
                            SimpleNamespace(
                                agent_id="acceptance", package=SimpleNamespace(role="acceptance")
                            ),
                        ]
                    )
                ),
            )
            runner.adapter = adapter
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._coordination_runtime_queue = []
            runner._coordination_runtime_lock = threading.Lock()
            runner._coordination_runtime_message_ids = set()
            runner._coordination_runtime_signal_keys = set()
            verdict_text = json.dumps(
                {"verdict": "BLOCKED", "blocked_reason": "upstream retrieval conflict"},
                ensure_ascii=False,
                sort_keys=True,
            )
            event = {
                "sender_id": "acceptance",
                "recipient_id": "coordinator",
                "message_kind": "acceptance_verdict_route",
                "message_id": "coordination-verdict-1",
                "text": verdict_text,
                "timestamp": 1.0,
                "terminal": False,
                "settles": False,
                "phase_event": {"generation": 4},
            }
            runner._coordination_transport_event_observer(event)
            runner._drain_coordination_runtime_deliveries()
            self.assertEqual(len(adapter.sent), 1)
            recipient_id, delivery = adapter.sent[0]
            self.assertEqual(recipient_id, "coordinator")
            self.assertEqual(delivery.kind, "coordination-phase")
            self.assertEqual(delivery.delivery_id, event["message_id"])
            self.assertEqual(delivery.sender_id, "runner/coordination")
            self.assertEqual(
                json.loads(delivery.text),
                {
                    "coordination_message_id": event["message_id"],
                    "generation": 4,
                    "message_kind": "acceptance_verdict_route",
                    "recipient_id": "coordinator",
                    "sender_id": "acceptance",
                    "text": verdict_text,
                },
            )
            with self.assertRaisesRegex(TeamConfigurationError, "delivery was queued twice"):
                runner._coordination_transport_event_observer(event)

    def test_non_default_agent_ids_map_all_coordination_deliveries(self) -> None:
        """Role routing uses configured IDs rather than role-name defaults."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "modeling-runs" / "run-non-default-coordination-ids"
            root.mkdir(parents=True)

            class Adapter:
                def __init__(self) -> None:
                    self.sent: list[tuple[str, RuntimeDelivery]] = []

                def send_message(
                    self, agent_id: str, delivery: RuntimeDelivery
                ) -> RuntimeDispatchReceipt:
                    self.sent.append((agent_id, delivery))
                    return RuntimeDispatchReceipt("start", "turn-non-default")

            role_agents = [
                SimpleNamespace(agent_id="coord-c", package=SimpleNamespace(role="coordinator")),
                SimpleNamespace(agent_id="model-a", package=SimpleNamespace(role="modeling")),
                SimpleNamespace(agent_id="proto-b", package=SimpleNamespace(role="protocol")),
                SimpleNamespace(agent_id="accept-d", package=SimpleNamespace(role="acceptance")),
            ]
            adapter = Adapter()
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(
                run_id="run-non-default-coordination-ids",
                root=root,
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(agents=role_agents)
                ),
            )
            runner.adapter = adapter
            runner.acceptance = SimpleNamespace(acceptance_id="accept-d")
            runner._append_evidence = lambda *_args, **_kwargs: None
            runner._coordination_runtime_queue = []
            runner._coordination_runtime_lock = threading.Lock()
            runner._coordination_runtime_message_ids = set()
            runner._coordination_runtime_signal_keys = set()

            events = [
                {
                    "sender_id": "model-a",
                    "recipient_id": "coord-c",
                    "message_kind": "ready_for_acceptance",
                    "message_id": "coordination-non-default-ready",
                    "text": "ready",
                    "timestamp": 1.0,
                    "terminal": False,
                    "settles": False,
                    "phase_event": {"generation": 1},
                },
                {
                    "sender_id": "proto-b",
                    "recipient_id": "coord-c",
                    "message_kind": "silent_for_acceptance",
                    "message_id": "coordination-non-default-silent",
                    "text": "silent",
                    "timestamp": 2.0,
                    "terminal": False,
                    "settles": False,
                    "phase_event": {"generation": 1},
                },
                {
                    "sender_id": "coord-c",
                    "recipient_id": "accept-d",
                    "message_kind": "acceptance_start",
                    "message_id": "coordination-non-default-start",
                    "text": "round-1",
                    "timestamp": 3.0,
                    "terminal": False,
                    "settles": False,
                    "phase_event": {"generation": 1},
                },
                {
                    "sender_id": "accept-d",
                    "recipient_id": "coord-c",
                    "message_kind": "acceptance_verdict_route",
                    "message_id": "coordination-non-default-verdict",
                    "text": json.dumps(
                        {"verdict": "BLOCKED", "blocked_reason": "retrieval conflict"},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "timestamp": 4.0,
                    "terminal": False,
                    "settles": False,
                    "phase_event": {"generation": 1},
                },
            ]
            for event in events:
                runner._coordination_transport_event_observer(event)

            runner._drain_coordination_runtime_deliveries()

            self.assertEqual(
                [recipient for recipient, _delivery in adapter.sent],
                ["coord-c", "coord-c", "accept-d", "coord-c"],
            )
            self.assertEqual(
                [delivery.kind for _recipient, delivery in adapter.sent],
                ["coordination-phase", "coordination-phase", "acceptance-start", "coordination-phase"],
            )
            for (_recipient, delivery), event in zip(adapter.sent, events, strict=True):
                self.assertEqual(delivery.delivery_id, event["message_id"])
                payload = json.loads(delivery.text)
                self.assertEqual(payload["generation"], 1)
                self.assertEqual(payload["coordination_message_id"], event["message_id"])
                if event["message_kind"] == "acceptance_start":
                    self.assertEqual(
                        payload,
                        {
                            "acceptance_id": "accept-d",
                            "coordination_message_id": event["message_id"],
                            "generation": 1,
                            "round_id": "round-1",
                        },
                    )
                else:
                    self.assertEqual(payload["sender_id"], event["sender_id"])
                    self.assertEqual(payload["recipient_id"], event["recipient_id"])
                    self.assertEqual(payload["message_kind"], event["message_kind"])
                    self.assertEqual(payload["text"], event["text"])


if __name__ == "__main__":
    unittest.main()
