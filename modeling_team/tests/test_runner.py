from __future__ import annotations

import json
import tempfile
import unittest
from shutil import rmtree
from pathlib import Path
from io import StringIO

from modeling_team.__main__ import _foreground_event_loop
from modeling_team.contracts import repository_root
from modeling_team.runner import TeamRunner
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


class RunnerTests(unittest.TestCase):
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
            for agent_id in ("coordinator", "modeling", "protocol"):
                runner.transport.report(agent_id, "completed", f"{agent_id} complete")

            first = runner.drain()
            second = runner.drain()

            self.assertEqual([item["type"] for item in first].count("settled"), 1)
            self.assertNotIn("settled", [item["type"] for item in second])
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
            runner.transport.report("modeling", "completed", "done")
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
            runner.transport.report("modeling", "completed", "modeling complete")
            runner.transport.report("protocol", "blocked", "protocol blocked")

            first = runner.drain()
            second = runner.drain()

            forwarded = [
                item for item in first if item["type"] == "terminal-result-coordinator-handoff"
            ]
            self.assertEqual([item["result"]["agent_id"] for item in forwarded], ["modeling", "protocol"])
            self.assertEqual([item for item in second if item["type"] == "terminal-result-coordinator-handoff"], [])
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
            self.assertIn(
                (
                    "modeling",
                    RuntimeDelivery("coordinator", "modeling", "outer-forward", exact),
                ),
                adapter.messages,
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
            for agent_id in ("coordinator", "modeling", "protocol"):
                runner.transport.report(agent_id, "completed", f"{agent_id} complete")

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
