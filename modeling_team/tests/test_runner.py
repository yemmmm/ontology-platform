from __future__ import annotations

import json
import sys
import tempfile
import unittest
from shutil import rmtree
from pathlib import Path
from io import StringIO
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from modeling_team import __main__ as team_main
from modeling_team.__main__ import _foreground_event_loop
from modeling_team.contracts import repository_root
from modeling_team.monitor_handoff import create_handoff_root
from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import RoutingError, mcp_response
from modeling_team.runtimes.base import (
    AgentRuntimeIdentity,
    RuntimeAdapter,
    RuntimeDelivery,
    RuntimeMessage,
)


class CapturingAdapter(RuntimeAdapter):
    def __init__(self) -> None:
        self.messages: list[tuple[str, RuntimeDelivery]] = []
        self.started: list[str] = []

    def start_roster(self, run, agents):
        return [AgentRuntimeIdentity(agent.agent_id, "private") for agent in agents]

    def probe_role_visibility(self, run):
        return {agent.agent_id: {"probe": "passed"} for agent in run.configuration.profile.agents}

    def start_task(self, agent_id, task_text, skill_paths, roster):
        self.started.append(agent_id)

    def send_message(self, agent_id, delivery):
        self.messages.append((agent_id, delivery))

    def receive_messages(self):
        return [RuntimeMessage("coordinator", "exact reply")]

    def get_agent_states(self):
        return []

    def wait_settled(self, agent_ids, timeout):
        return True

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass

    def cleanup_identifiers(self):
        return {}


class PostSettlementAdapter(CapturingAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.inbox: list[RuntimeMessage] = []

    def send_message(self, agent_id, delivery):
        super().send_message(agent_id, delivery)
        if agent_id == "coordinator" and delivery.text.startswith("Runtime settlement is complete."):
            self.inbox.append(RuntimeMessage("coordinator", "Final user-facing summary."))

    def receive_messages(self):
        messages, self.inbox = self.inbox, []
        return messages


class GuardingAdapter(CapturingAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.terminal_guard_calls: list[tuple[str, bool]] = []

    def terminal_report_blocked(self, agent_id, already_synchronized=False):
        self.terminal_guard_calls.append((agent_id, already_synchronized))
        return False


class RunnerTests(unittest.TestCase):
    def test_runner_transport_observer_writes_exact_events_for_extractor(self) -> None:
        root = repository_root()
        run_id = f"transport-events-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        runner = TeamRunner(repository_root=root, adapter=CapturingAdapter())
        request = {
            "method": "tools/call",
            "params": {
                "name": "report_task_result",
                "arguments": {"status": "completed", "summary": "private"},
            },
        }
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling"):
                mcp_response(request, broker=runner.transport, agent_id="protocol")
            runner.transport.report("modeling", "blocked", "private modeling")
            runner.transport.ack_terminal_handoff("protocol", "modeling")
            mcp_response(request, broker=runner.transport, agent_id="protocol")
            event_path = run_root / "evidence" / "team-transport-events.jsonl"
            events = [json.loads(line) for line in event_path.read_text().splitlines()]
            self.assertEqual(
                [(event["status"], event["category"]) for event in events],
                [
                    ("rejected", "missing_modeling_handoff"),
                    ("accepted", "terminal_report_accepted"),
                ],
            )
            for event in events:
                self.assertEqual(
                    set(event),
                    {"agent", "tool", "status", "category", "ack", "recorded_at_ns"},
                )
                self.assertNotIn("private", json.dumps(event))
            self.assertEqual(event_path.stat().st_mode & 0o777, 0o600)
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_runner_binds_runtime_terminal_guard_to_broker(self) -> None:
        root = repository_root()
        run_id = f"terminal-guard-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        adapter = GuardingAdapter()
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "runtime guard binding")
            self.assertEqual(adapter.terminal_guard_calls, [("modeling", False)])
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_coordinator_retries_after_terminal_handoffs_for_v1_and_v2(self) -> None:
        root = repository_root()
        profile = root / "modeling_team/profiles/base-three-agent.yaml"
        cases = (
            ("base-capability-smoke.yaml", False),
            ("new-scope-business-slice.yaml", True),
        )
        for task_name, needs_ledger in cases:
            with self.subTest(task=task_name), tempfile.TemporaryDirectory() as directory:
                run_id = f"terminal-dependency-{task_name[:4]}-{__import__('uuid').uuid4().hex}"
                run_root = root / "workspaces" / "modeling-runs" / run_id
                adapter = CapturingAdapter()
                options = {}
                if needs_ledger:
                    options = {
                        "ledger_root": Path(directory) / "ledger",
                        "freeze_started_at": datetime.now(UTC).isoformat(),
                    }
                runner = TeamRunner(repository_root=root, adapter=adapter, **options)
                try:
                    runner.prepare(
                        run_id=run_id,
                        profile_path=profile,
                        task_path=root / "modeling_team/tasks" / task_name,
                        scope={"mode": "create"},
                    )
                    runner.start()
                    assert runner.transport is not None
                    with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling, protocol"):
                        runner.transport.report("coordinator", "completed", "premature")
                    self.assertNotIn("coordinator", runner.transport.results)
                    runner.transport.report("modeling", "blocked", "modeling handoff")
                    with self.assertRaisesRegex(RoutingError, "terminal handoffs: modeling"):
                        runner.transport.report("protocol", "blocked", "protocol handoff")
                    modeling_handoffs = runner.drain()
                    self.assertEqual(
                        [item["type"] for item in modeling_handoffs].count("terminal-result-handoff"), 2
                    )
                    runner.transport.report("protocol", "blocked", "protocol handoff")
                    handoffs = runner.drain()
                    self.assertEqual(
                        [item["type"] for item in handoffs].count("terminal-result-handoff"), 1
                    )
                    runner.transport.report("coordinator", "completed", "retry")
                    settled = runner.drain()
                    self.assertIn("settled", [item["type"] for item in settled])
                    cleanup = runner.cleanup()
                    self.assertEqual(json.loads((run_root / "state.json").read_text())["state"], "CLEANED")
                    self.assertIn("runtime", cleanup)
                finally:
                    if run_root.exists():
                        rmtree(run_root)

    def test_foreground_loop_pumps_events_without_followup_user_input(self) -> None:
        class PumpingRunner:
            def __init__(self):
                self.drains = 0

            def drain(self):
                self.drains += 1
                return [{"type": "settled"}] if self.drains == 2 else []

            def receive_outer(self, _message):
                raise AssertionError("the test provides no user message")

        runner = PumpingRunner()
        stream = StringIO("")
        polls = iter([([], [], []), ([stream], [], [])])
        emitted = []
        _foreground_event_loop(
            runner, stream, emitted.append, select_fn=lambda *_args: next(polls)
        )
        self.assertEqual(emitted, [[{"type": "settled"}]])
        self.assertGreaterEqual(runner.drains, 2)

    def test_foreground_loop_returns_after_terminal_report_without_waiting_for_stdin(self) -> None:
        class TerminalRunner:
            def __init__(self, root):
                self.run = SimpleNamespace(root=root)
                self.drains = 0

            def drain(self):
                self.drains += 1
                (self.run.root / "state.json").write_text(
                    json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}), encoding="utf-8"
                )
                return [{"type": "coordinator", "text": "final"}]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = TerminalRunner(root)
            emitted = []
            _foreground_event_loop(
                runner,
                StringIO(""),
                emitted.append,
                select_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("must not wait for stdin")),
            )
            self.assertEqual(emitted, [[{"type": "coordinator", "text": "final"}]])
            self.assertEqual(runner.drains, 1)

    def test_main_cleans_up_and_returns_on_keyboard_interrupt(self) -> None:
        created = []

        class InterruptingRunner:
            def __init__(self, **_kwargs):
                self.cleaned = False
                created.append(self)

            def prepare(self, **_kwargs):
                pass

            def start(self):
                raise KeyboardInterrupt

            def cleanup(self):
                self.cleaned = True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = root / "scope.yaml"
            scope.write_text("{}", encoding="utf-8")
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(root / "profile.yaml"),
                "--task",
                str(root / "task.yaml"),
                "--run-id",
                "interrupt-run-1",
                "--scope",
                str(scope),
            ]
            with (
                patch.object(team_main, "repository_root", return_value=root),
                patch.object(team_main, "load_team_configuration", return_value=SimpleNamespace()),
                patch.object(team_main, "_bootstrap_helpers", return_value=(lambda: ("key", "id"), lambda _id: True)),
                patch.object(team_main, "CodexRuntimeAdapter", return_value=SimpleNamespace()),
                patch.object(team_main, "TeamRunner", side_effect=InterruptingRunner),
                patch.object(sys, "argv", argv),
            ):
                self.assertEqual(team_main.main(), 130)
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].cleaned)

    def test_monitor_extraction_ack_timeout_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_repo = Path(directory)
            runs = fake_repo / "workspaces" / "modeling-runs"
            runs.mkdir(parents=True)
            references = fake_repo / "modeling_team" / "references"
            references.mkdir(parents=True)
            source_contract = repository_root() / "modeling_team/references/p2-monitor-handoff-contract.json"
            (references / source_contract.name).write_bytes(source_contract.read_bytes())
            run_root = runs / "r23002-cli-ack-timeout"
            handoff_root, _ = create_handoff_root(fake_repo, run_root)
            fake_now = [0.0]

            def monotonic() -> float:
                return fake_now[0]

            def sleep(seconds: float) -> None:
                fake_now[0] += seconds * 20.0

            with (
                patch.object(team_main, "repository_root", return_value=fake_repo),
                patch.object(team_main.time, "monotonic", side_effect=monotonic),
                patch.object(team_main.time, "sleep", side_effect=sleep),
                self.assertRaisesRegex(
                    TimeoutError, "extraction acknowledgement timed out"
                ),
            ):
                team_main._await_monitor_extraction(handoff_root, run_root)

    def test_outer_user_text_goes_only_to_coordinator(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=root, adapter=adapter)
            # Use an isolated root only for the run tree while all validated committed inputs stay immutable.
            runner.repository_root = Path(directory)
            # This test exercises delivery with a prepared in-memory run directory through the normal input paths.
            runner.repository_root = root
            run_id = "unit-run-123"
            run_root = root / "workspaces/modeling-runs" / run_id
            if run_root.exists():
                self.skipTest("leftover run directory")
            try:
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                    task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                    scope={"mode": "create"},
                )
                runner.start()
                output = runner.receive_outer({"action": "user", "text": "status?"})
                self.assertEqual(
                    adapter.messages,
                    [
                        (
                            "coordinator",
                            RuntimeDelivery("user/outer", "coordinator", "outer-user", "status?"),
                        )
                    ],
                )
                self.assertEqual(
                    output, [{"type": "coordinator", "text": "exact reply"}]
                )
            finally:
                runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_settled_is_emitted_once_after_all_agent_results(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        run_id = "unit-run-124"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "modeling complete")
            runner.drain()
            runner.transport.report("protocol", "completed", "protocol complete")
            runner.drain()
            runner.transport.report("coordinator", "completed", "coordinator complete")

            first = runner.drain()
            second = runner.drain()

            self.assertEqual([item["type"] for item in first].count("settled"), 1)
            self.assertNotIn("settled", [item["type"] for item in second])
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_runner_acknowledges_reply_only_after_delivery_then_allows_modeling_terminal(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        run_id = "unit-run-reply-ack"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            candidate = runner.transport.send("modeling", "protocol", "candidate", expects_reply=True)
            receipt = runner.transport.send(
                "protocol", "modeling", "receipt", reply_to_delivery_id=candidate.delivery_id
            )
            with self.assertRaisesRegex(RoutingError, "delivered reply"):
                runner.transport.report("modeling", "completed", "queued receipt")
            runner.drain()
            delivered = next(
                item[1] for item in adapter.messages if item[0] == "modeling" and item[1].text == "receipt"
            )
            self.assertEqual(
                (delivered.delivery_id, delivered.expects_reply, delivered.reply_to_delivery_id),
                (receipt.delivery_id, False, candidate.delivery_id),
            )
            runner.transport.report("modeling", "completed", "delivered receipt")
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_runner_does_not_ack_reply_when_runtime_delivery_fails(self) -> None:
        class FailingReplyAdapter(CapturingAdapter):
            def send_message(self, agent_id, delivery):
                if delivery.text == "receipt":
                    raise RuntimeError("runtime delivery failed")
                super().send_message(agent_id, delivery)

        root = repository_root()
        adapter = FailingReplyAdapter()
        run_id = "unit-run-reply-failure"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            candidate = runner.transport.send("modeling", "protocol", "candidate", expects_reply=True)
            runner.transport.send("protocol", "modeling", "receipt", reply_to_delivery_id=candidate.delivery_id)
            with self.assertRaisesRegex(RuntimeError, "runtime delivery failed"):
                runner.drain()
            with self.assertRaisesRegex(RoutingError, "delivered reply"):
                runner.transport.report("modeling", "completed", "must remain pending")
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_terminal_recipient_does_not_receive_later_peer_turn(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        run_id = "unit-run-125"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "done")
            runner.transport.send("coordinator", "modeling", "late supplement")

            runner.drain()

            self.assertNotIn(
                ("modeling", RuntimeDelivery("coordinator", "modeling", "peer", "late supplement")),
                adapter.messages,
            )
            blocked = (run_root / "evidence" / "terminal-delivery-blocked.jsonl").read_text()
            self.assertIn("recipient already reported terminal result", blocked)
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_each_non_coordinator_terminal_result_is_forwarded_once(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        run_id = "unit-run-126"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "modeling complete")
            first = runner.drain()
            runner.transport.report("protocol", "blocked", "protocol blocked")
            second = runner.drain()
            third = runner.drain()

            forwarded = [
                item for item in first if item["type"] == "terminal-result-handoff"
            ]
            self.assertEqual(
                {(item["recipient_id"], item["source_id"]) for item in forwarded},
                {("protocol", "modeling"), ("coordinator", "modeling")},
            )
            self.assertEqual(
                [(item["recipient_id"], item["source_id"]) for item in second if item["type"] == "terminal-result-handoff"],
                [("coordinator", "protocol")],
            )
            self.assertEqual([item for item in third if item["type"] == "terminal-result-handoff"], [])
            texts = [delivery.text for recipient, delivery in adapter.messages if recipient == "coordinator"]
            self.assertTrue(any('"agent_id": "modeling"' in text for text in texts))
            self.assertTrue(any('"agent_id": "protocol"' in text for text in texts))
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_coordinator_outer_forward_is_attributed_without_changing_unicode_text(self) -> None:
        root = repository_root()
        adapter = CapturingAdapter()
        run_id = "unit-run-128"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        exact = "补充\n汉字 and \\\"quoted\\\""
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            runner.receive_outer({"action": "user", "text": exact})
            assert runner.transport is not None
            runner.transport.send("coordinator", "modeling", exact)
            runner.drain()
            forwarded = next(
                delivery
                for recipient, delivery in adapter.messages
                if recipient == "modeling" and delivery.text == exact
            )
            self.assertEqual(
                forwarded,
                RuntimeDelivery(
                    "coordinator",
                    "modeling",
                    "outer-forward",
                    exact,
                    delivery_id="delivery-1",
                ),
            )
            self.assertNotIn(
                (
                    "modeling",
                    RuntimeDelivery("modeling", "protocol", "outer-forward", exact),
                ),
                adapter.messages,
            )
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_post_settlement_summary_follows_settled_evidence_once(self) -> None:
        root = repository_root()
        adapter = PostSettlementAdapter()
        run_id = "unit-run-127"
        run_root = root / "workspaces/modeling-runs" / run_id
        if run_root.exists():
            self.skipTest("leftover run directory")
        runner = TeamRunner(repository_root=root, adapter=adapter)
        try:
            runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            runner.start()
            assert runner.transport is not None
            runner.transport.report("modeling", "blocked", "modeling complete")
            runner.drain()
            runner.transport.report("protocol", "completed", "protocol complete")
            runner.drain()
            runner.transport.report("coordinator", "completed", "coordinator complete")

            first = runner.drain()
            second = runner.drain()
            third = runner.drain()

            self.assertIn("settled", [item["type"] for item in first])
            self.assertEqual(second, [{"type": "coordinator", "text": "Final user-facing summary."}])
            self.assertEqual(third, [])
            prompts = [delivery.text for recipient, delivery in adapter.messages if recipient == "coordinator"]
            self.assertEqual(sum(text.startswith("Runtime settlement is complete.") for text in prompts), 1)
            self.assertTrue(all(f'"agent_id": "{agent_id}"' in prompts[-1] for agent_id in ("coordinator", "modeling", "protocol")))
            settled = json.loads((run_root / "evidence" / "settled.jsonl").read_text())
            final = json.loads((run_root / "evidence" / "coordinator-final.jsonl").read_text())
            self.assertLess(settled["recorded_at"], final["recorded_at"])
            self.assertEqual(json.loads((run_root / "state.json").read_text())["state"], "TERMINAL_REPORT_COMPLETE")
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)
