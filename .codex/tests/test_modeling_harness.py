from __future__ import annotations

import argparse
import importlib.util
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / ".codex" / "hooks" / "modeling_harness.py"
SPEC = importlib.util.spec_from_file_location("modeling_harness", MODULE_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def delta(summary: str = "A bounded summary") -> dict[str, object]:
    return {
        "summary": summary,
        "phases": [{"phase": "review", "summary": "Review completed"}],
        "decisions": ["Keep the vertical slice small"],
        "assumptions": ["Sources are current"],
        "rework": ["Clarified one relation"],
        "quality_issues": ["One ambiguity was caught in review"],
        "blockers": [],
        "next_steps": ["Verify persisted state"],
        "optimization_opportunities": ["Tighten the reviewer handoff"],
        "stable_ids": ["build-session-1"],
    }


def append_worker(run_dir: str, index: int) -> None:
    harness.append_sanitized(Path(run_dir), "worker", {"index": index}, f"worker:{index}")


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="harness-test-")
        self.repo = Path(self.temporary.name)
        (self.repo / ".git").mkdir()
        (self.repo / ".codex" / "hooks").mkdir(parents=True)
        (self.repo / "docs" / "modeling-retrospectives").mkdir(parents=True)
        for relative in (
            Path(".codex/hooks.json"),
            Path(".codex/hooks/modeling_harness.py"),
            Path(".codex/hooks/summary.schema.json"),
        ):
            target = self.repo / relative
            target.write_bytes((REPO / relative).read_bytes())
        self.paths = harness.Paths(self.repo)
        self.run_id = "run-12345678"
        self.nonce = "nonce_123456789012345678901234"
        self.values = {
            "run_id": self.run_id,
            "activation_nonce": self.nonce,
            "build_session_id": "build-session-1",
            "project_id": "project-1",
        }
        self.hook = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "session_id": "codex-session-1",
            "cwd": str(self.repo),
            "tool_use_id": "tool-activate",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def activate(self) -> Path:
        harness.acknowledge_activation(self.paths, self.hook, self.values)
        args = argparse.Namespace(**self.values)
        harness.activate_cli(self.paths, args)
        return self.paths.run(self.run_id)

    def test_unknown_session_and_foreign_cwd_are_noop(self) -> None:
        harness.handle_hook(
            self.paths,
            {
                "hook_event_name": "Stop",
                "session_id": "unknown",
                "cwd": str(self.repo),
                "last_assistant_message": "nothing",
            },
        )
        harness.handle_hook(
            self.paths,
            {
                "hook_event_name": "Stop",
                "session_id": "unknown",
                "cwd": str(self.repo / "foreign"),
            },
        )
        self.assertFalse(self.paths.root.exists())

    def test_activation_requires_matching_hook_acknowledgment(self) -> None:
        args = argparse.Namespace(**self.values)
        with self.assertRaisesRegex(harness.HarnessError, "not being recorded"):
            harness.activate_cli(self.paths, args)
        run_dir = self.activate()
        metadata = harness.read_json(run_dir / "metadata.json")
        self.assertEqual(metadata["session_id"], "codex-session-1")
        self.assertEqual(metadata["hook_config_hash"], harness.config_hash(self.paths))
        self.assertEqual(metadata["status"], "active")

    def test_conflicting_session_binding_fails_closed(self) -> None:
        self.activate()
        conflicting = dict(self.values, run_id="run-87654321", activation_nonce="x" * 32)
        with self.assertRaisesRegex(harness.HarnessError, "already bound"):
            harness.acknowledge_activation(self.paths, self.hook, conflicting)

    def test_hook_hash_change_invalidates_active_mapping(self) -> None:
        self.activate()
        with (self.repo / ".codex" / "hooks.json").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        self.assertIsNone(harness.active_run(self.paths, self.hook))

    def test_activation_command_parser_is_strict(self) -> None:
        command = (
            "python3 .codex/hooks/modeling_harness.py activate "
            f"--run-id {self.run_id} --activation-nonce {self.nonce} "
            "--build-session-id build-session-1 --project-id project-1"
        )
        self.assertEqual(harness.activation_args(command), self.values)
        self.assertIsNone(harness.activation_args(command + " --unknown value"))

    def test_concurrent_append_is_contiguous_and_deduplicated(self) -> None:
        run_dir = self.activate()
        processes = [
            multiprocessing.Process(target=append_worker, args=(str(run_dir), index))
            for index in range(20)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        harness.append_sanitized(run_dir, "worker", {"index": 0}, "worker:0")
        events = harness.load_events(run_dir)
        sequences = [event["sequence"] for event in events]
        self.assertEqual(sequences, list(range(1, len(events) + 1)))
        self.assertEqual(sum(event["kind"] == "worker" for event in events), 20)

    def test_secret_rejection_never_persists_original_and_requires_replacement(
        self,
    ) -> None:
        run_dir = self.activate()
        fake_secret = "sk-UniqueHarnessFixture1234567890"
        event, _ = harness.append_sanitized(
            run_dir,
            "user_prompt",
            {"prompt": f"api_key={fake_secret}"},
            "prompt-secret",
        )
        self.assertEqual(event["kind"], "rejected_secret")
        for path in run_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(fake_secret, path.read_text(encoding="utf-8", errors="ignore"))
        state = harness.read_json(run_dir / "state.json")
        self.assertEqual(state["pending_redaction"], [event["sequence"]])
        with self.assertRaisesRegex(harness.HarnessError, "pending_redaction"):
            harness.summarize_pending(run_dir, lambda _run, _prompt: delta())
        harness.redact_cli(
            self.paths,
            argparse.Namespace(
                run_id=self.run_id,
                for_sequence=event["sequence"],
                replacement="A platform credential was removed before recording.",
            ),
        )
        self.assertFalse(harness.read_json(run_dir / "state.json")["pending_redaction"])

    def test_subagent_transcript_and_unknown_fields_are_not_persisted(self) -> None:
        run_dir = self.activate()
        hook = {
            "hook_event_name": "SubagentStop",
            "session_id": "codex-session-1",
            "cwd": str(self.repo),
            "agent_id": "agent-12345678",
            "agent_type": "reviewer",
            "agent_transcript_path": "/forbidden/full-transcript.jsonl",
            "system_prompt": "forbidden system content",
            "last_assistant_message": "Reviewer returned PASS.",
        }
        original = harness.invoke_luna
        harness.invoke_luna = lambda _run, _prompt: delta()
        try:
            harness.handle_hook(self.paths, hook)
        finally:
            harness.invoke_luna = original
        persisted = (run_dir / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("full-transcript", persisted)
        self.assertNotIn("forbidden system content", persisted)
        self.assertIn("Reviewer returned PASS", persisted)

    def test_platform_response_string_extracts_only_stable_fields(self) -> None:
        selected = harness.selected_ids(
            '{"content":"full output must not persist","build_session_id":"build-123",'
            '"finding_fingerprint":"abc123","lease_token":"forbidden"}'
        )
        self.assertEqual(
            selected,
            {"build_session_id": "build-123", "finding_fingerprint": "abc123"},
        )

    def test_handoff_hook_records_only_bounded_manifest_fields(self) -> None:
        run_dir = self.activate()
        secret = "sk-ThisMustNeverBePersisted123456789"
        hook = {
            "hook_event_name": "PostToolUse",
            "session_id": "codex-session-1",
            "cwd": str(self.repo),
            "tool_use_id": "handoff-run-1",
            "tool_name": "exec_command",
            "tool_input": {
                "cmd": (
                    "python3 .codex/modeling_handoff.py inspect "
                    "--build-session-id build-session-1 --artifact-key modeling-draft "
                    "--generation-id generation-1"
                )
            },
            "tool_response": {
                "exit_code": 0,
                "output": (
                    '{"manifest_version":"1","state":"validated",'
                    '"generation_id":"generation-1","artifact_key":"modeling-draft",'
                    '"locator":"/forbidden/absolute/spool",'
                    f'"draft":"{secret}","item_count":27}}'
                ),
            },
        }
        original = harness.invoke_luna
        harness.invoke_luna = lambda _run, _prompt: delta()
        try:
            harness.handle_hook(self.paths, hook)
        finally:
            harness.invoke_luna = original
        persisted = (run_dir / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("modeling_handoff_outcome", persisted)
        self.assertIn('"item_count":27', persisted)
        self.assertNotIn("absolute/spool", persisted)
        self.assertNotIn(secret, persisted)
        self.assertNotIn('"draft"', persisted)

    def test_nested_mcp_business_failure_is_not_tool_success(self) -> None:
        failure = {
            "tool_response": {
                "content": [
                    {"text": ('{"success":false,"status":"failed","error":"business rejected"}')}
                ],
                "isError": False,
            }
        }
        self.assertFalse(harness.tool_succeeded(failure))
        self.assertFalse(harness.authority_succeeded(failure))
        success = {
            "tool_response": {
                "content": [{"text": '{"success":true,"status":"completed"}'}],
                "isError": False,
            }
        }
        self.assertTrue(harness.tool_succeeded(success))
        self.assertTrue(harness.authority_succeeded(success))
        ambiguous = {"tool_response": {"content": [{"text": "plain text"}], "isError": False}}
        self.assertTrue(harness.tool_succeeded(ambiguous))
        self.assertFalse(harness.authority_succeeded(ambiguous))

    def test_failed_or_ambiguous_authority_never_checkpoints_or_finalizes(self) -> None:
        run_dir = self.activate()
        calls: list[str] = []
        original = harness.finalize_run
        harness.finalize_run = lambda _paths, _run, terminal: calls.append(terminal)
        try:
            failed_complete = {
                "hook_event_name": "PostToolUse",
                "session_id": "codex-session-1",
                "cwd": str(self.repo),
                "tool_use_id": "failed-complete",
                "tool_name": "complete_build_session",
                "tool_input": {"build_session_id": "build-session-1"},
                "tool_response": {
                    "content": [
                        {
                            "text": (
                                '{"success":false,"status":"failed","error":"business rejected"}'
                            )
                        }
                    ],
                    "isError": False,
                },
            }
            harness.handle_hook(self.paths, failed_complete)
            ambiguous_phase = {
                "hook_event_name": "PostToolUse",
                "session_id": "codex-session-1",
                "cwd": str(self.repo),
                "tool_use_id": "ambiguous-phase",
                "tool_name": "record_modeling_execution_event",
                "tool_input": {"event_type": "phase_completed", "phase": "review"},
                "tool_response": {
                    "content": [{"text": "transport completed"}],
                    "isError": False,
                },
            }
            harness.handle_hook(self.paths, ambiguous_phase)
        finally:
            harness.finalize_run = original
        self.assertEqual(calls, [])
        self.assertIsNone(harness.read_json(run_dir / "metadata.json")["terminal_state"])
        self.assertIsNone(harness.read_json(run_dir / "state.json")["pending_checkpoint"])

    def test_explicit_nested_success_authorizes_terminal_transition(self) -> None:
        self.activate()
        calls: list[str] = []
        original = harness.finalize_run
        harness.finalize_run = lambda _paths, _run, terminal: calls.append(terminal)
        try:
            harness.handle_hook(
                self.paths,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "codex-session-1",
                    "cwd": str(self.repo),
                    "tool_use_id": "successful-complete",
                    "tool_name": "complete_build_session",
                    "tool_input": {"build_session_id": "build-session-1"},
                    "tool_response": {
                        "content": [
                            {
                                "text": (
                                    '{"success":true,"status":"completed",'
                                    '"build_session_id":"build-session-1"}'
                                )
                            }
                        ],
                        "isError": False,
                    },
                },
            )
        finally:
            harness.finalize_run = original
        self.assertEqual(calls, ["completed"])

    def test_explicit_nested_success_authorizes_phase_checkpoint(self) -> None:
        run_dir = self.activate()
        harness.handle_hook(
            self.paths,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "codex-session-1",
                "cwd": str(self.repo),
                "tool_use_id": "successful-phase",
                "tool_name": "record_modeling_execution_event",
                "tool_input": {"event_type": "review_completed", "phase": "review"},
                "tool_response": {
                    "content": [
                        {"text": ('{"ok":true,"data":{"event":{"execution_event_id":"event-1"}}}')}
                    ],
                    "isError": False,
                },
            },
        )
        checkpoint = harness.read_json(run_dir / "state.json")["pending_checkpoint"]
        self.assertEqual(checkpoint["event_type"], "review_completed")
        self.assertEqual(checkpoint["source"], "platform")

    def test_summary_receives_only_unsummarized_events_and_advances_after_success(
        self,
    ) -> None:
        run_dir = self.activate()
        harness.append_sanitized(run_dir, "turn_output", {"output": "first"}, "one")
        prompts: list[str] = []

        def fake(_run: Path, prompt: str) -> dict[str, object]:
            prompts.append(prompt)
            return delta()

        self.assertTrue(harness.summarize_pending(run_dir, fake))
        first_cursor = harness.read_json(run_dir / "state.json")["summarized_sequence"]
        harness.append_sanitized(run_dir, "turn_output", {"output": "second"}, "two")
        self.assertTrue(harness.summarize_pending(run_dir, fake))
        self.assertNotIn('"output":"first"', prompts[1])
        self.assertIn('"output":"second"', prompts[1])
        self.assertGreater(
            harness.read_json(run_dir / "state.json")["summarized_sequence"],
            first_cursor,
        )

    def test_summary_input_is_bounded_and_retries_oldest_contiguous_events(
        self,
    ) -> None:
        run_dir = self.activate()
        for index in range(14):
            harness.append_sanitized(
                run_dir,
                "turn_output",
                {"output": f"{index}:" + ("x" * 5_500)},
                f"bounded:{index}",
            )
        prompts: list[str] = []

        def fake(_run: Path, prompt: str) -> dict[str, object]:
            prompts.append(prompt)
            return delta()

        harness.summarize_pending(run_dir, fake)
        first_cursor = harness.read_json(run_dir / "state.json")["summarized_sequence"]
        self.assertLess(first_cursor, len(harness.load_events(run_dir)))
        harness.summarize_pending(run_dir, fake)
        self.assertGreater(
            harness.read_json(run_dir / "state.json")["summarized_sequence"],
            first_cursor,
        )
        self.assertNotIn('"output":"0:', prompts[1])

    def test_failed_summary_does_not_advance_cursor_or_replace_markdown(self) -> None:
        run_dir = self.activate()
        harness.append_sanitized(run_dir, "turn_output", {"output": "first"}, "one")
        harness.summarize_pending(run_dir, lambda _run, _prompt: delta("first delta"))
        before_state = harness.read_json(run_dir / "state.json")
        before_markdown = (run_dir / "session.md").read_text(encoding="utf-8")
        harness.append_sanitized(run_dir, "turn_output", {"output": "second"}, "two")
        with self.assertRaises(harness.HarnessError):
            harness.summarize_pending(run_dir, lambda _run, _prompt: {"bad": True})
        after = harness.read_json(run_dir / "state.json")
        self.assertEqual(after["summarized_sequence"], before_state["summarized_sequence"])
        self.assertEqual((run_dir / "session.md").read_text(encoding="utf-8"), before_markdown)

    def test_phase_stop_requires_authoritative_checkpoint(self) -> None:
        run_dir = self.activate()
        stop = {
            "hook_event_name": "Stop",
            "session_id": "codex-session-1",
            "cwd": str(self.repo),
            "last_assistant_message": "ordinary output",
        }
        harness.handle_hook(self.paths, stop)
        self.assertEqual(harness.load_events(run_dir)[-1]["kind"], "turn_output")
        harness.checkpoint_cli(
            self.paths,
            argparse.Namespace(
                run_id=self.run_id,
                phase="review",
                event_type="review_completed",
                summary="Reviewer returned PASS.",
                client_checkpoint_id="checkpoint-1",
            ),
        )
        stop["last_assistant_message"] = "phase output"
        harness.handle_hook(self.paths, stop)
        self.assertEqual(harness.load_events(run_dir)[-1]["kind"], "phase_output")

    def test_luna_command_and_environment_are_isolated(self) -> None:
        empty = self.repo / "empty"
        empty.mkdir()
        command = harness.luna_command(self.paths, empty, empty / "last.json")
        joined = " ".join(command)
        for required in (
            "gpt-5.6-luna",
            'model_reasoning_effort="medium"',
            'web_search="disabled"',
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "read-only",
            "--strict-config",
        ):
            self.assertIn(required, joined)
        for feature in harness.DISABLED_FEATURES:
            self.assertIn(feature, command)
        self.assertEqual(command[-1], "-")
        environment = harness.safe_environment(
            {
                "PATH": "/bin",
                "HOME": "/tmp/home",
                "ONTOLOGY_MCP_API_KEY": "not-preserved",
                "AUTHORIZATION": "not-preserved",
                "HTTPS_PROXY": "https://proxy.example",
            }
        )
        self.assertNotIn("ONTOLOGY_MCP_API_KEY", environment)
        self.assertNotIn("AUTHORIZATION", environment)
        self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.example")

    def test_finalize_publish_is_idempotent_and_paused_stays_local(self) -> None:
        run_dir = self.activate()
        harness.append_sanitized(run_dir, "phase_output", {"output": "verified"}, "verify")
        target = harness.finalize_run(
            self.paths, run_dir, "completed", lambda _run, _prompt: delta()
        )
        self.assertIsNotNone(target)
        assert target
        self.assertTrue(target.exists())
        self.assertEqual(
            target,
            harness.finalize_run(self.paths, run_dir, "completed", lambda _run, _prompt: delta()),
        )
        before_events = (run_dir / "events.jsonl").read_bytes()
        before_retrospective = target.read_bytes()
        harness.handle_hook(
            self.paths,
            {
                "hook_event_name": "Stop",
                "session_id": "codex-session-1",
                "cwd": str(self.repo),
                "last_assistant_message": "must not stale the published record",
            },
        )
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), before_events)
        self.assertEqual(target.read_bytes(), before_retrospective)

        second_values = dict(self.values, run_id="run-paused-1234", activation_nonce="p" * 32)
        second_hook = dict(self.hook, session_id="codex-session-2")
        harness.acknowledge_activation(self.paths, second_hook, second_values)
        harness.activate_cli(self.paths, argparse.Namespace(**second_values))
        paused_dir = self.paths.run(second_values["run_id"])
        self.assertIsNone(
            harness.finalize_run(self.paths, paused_dir, "paused", lambda _run, _prompt: delta())
        )
        published = list(self.paths.retrospectives.glob(f"*-{second_values['run_id']}.md"))
        self.assertEqual(published, [])

    def test_finalize_stays_pending_after_three_failures_then_repair_publishes(
        self,
    ) -> None:
        run_dir = self.activate()
        calls = 0

        def failing(_run: Path, _prompt: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise harness.HarnessError("fixture failure")

        self.assertIsNone(harness.finalize_run(self.paths, run_dir, "cancelled", failing))
        self.assertEqual(calls, 3)
        self.assertEqual(
            harness.read_json(run_dir / "state.json")["finalization_status"],
            "finalization_pending",
        )
        before_events = (run_dir / "events.jsonl").read_bytes()
        retry_calls = 0

        def retry(_run: Path, _prompt: str) -> dict[str, object]:
            nonlocal retry_calls
            retry_calls += 1
            return delta()

        original = harness.invoke_luna
        harness.invoke_luna = retry
        try:
            harness.handle_hook(
                self.paths,
                {
                    "hook_event_name": "Stop",
                    "session_id": "codex-session-1",
                    "cwd": str(self.repo),
                    "last_assistant_message": "must not be appended after terminal state",
                },
            )
        finally:
            harness.invoke_luna = original
        self.assertEqual(retry_calls, 1)
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), before_events)
        self.assertEqual(
            harness.read_json(run_dir / "metadata.json")["status"],
            "finalization_pending",
        )
        self.assertEqual(list(self.paths.retrospectives.glob(f"*-{self.run_id}.md")), [])
        target = harness.finalize_run(
            self.paths, run_dir, "cancelled", lambda _run, _prompt: delta()
        )
        self.assertIsNotNone(target)


if __name__ == "__main__":
    unittest.main()
