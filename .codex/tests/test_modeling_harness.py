from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


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


def prepare_fast_worker(repo: str, values: dict[str, str], queue: multiprocessing.Queue) -> None:
    try:
        harness.prepare_fast_cli(harness.Paths(Path(repo)), argparse.Namespace(**values))
        queue.put("ok")
    except Exception as exc:
        queue.put(type(exc).__name__)


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

    def test_activation_command_parser_accepts_harmless_trailing_shell_tokens(self) -> None:
        command = (
            "python3 .codex/hooks/modeling_harness.py activate "
            f"--run-id {self.run_id} --activation-nonce {self.nonce} "
            "--build-session-id build-session-1 --project-id project-1"
        )
        self.assertEqual(harness.activation_args(command), self.values)
        self.assertEqual(harness.activation_args(command + " 2>/dev/null ; true"), self.values)
        self.assertIsNone(harness.activation_args(command.replace("--project-id", "--unknown")))

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


class DualClaudeHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dual-harness-test-")
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
        self.run_id = "dual-run-12345678"
        self.base = {
            "run_id": self.run_id,
            "build_session_id": "build-session-dual",
            "project_id": "project-dual",
            "runtime": "claude",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def activate_participant(self, role: str, session: str, nonce: str) -> None:
        values = {
            **self.base,
            "participant_role": role,
            "activation_nonce": nonce,
        }
        hook = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "session_id": session,
            "cwd": str(self.repo),
            "tool_use_id": f"activate-{role}-{session}",
        }
        harness.acknowledge_activation(self.paths, hook, values)
        harness.activate_cli(self.paths, argparse.Namespace(**values))

    def activate_dual(self) -> Path:
        self.activate_participant("simulated_user", "claude-user-session", "u" * 32)
        metadata = harness.read_json(self.paths.run(self.run_id) / "metadata.json")
        self.assertEqual(metadata["status"], "activating")
        self.activate_participant("modeling_agent", "claude-model-session", "m" * 32)
        return self.paths.run(self.run_id)

    def hook(self, role: str, event: str, **values: object) -> dict[str, object]:
        session = "claude-user-session" if role == "simulated_user" else "claude-model-session"
        return {
            "hook_event_name": event,
            "session_id": session,
            "cwd": str(self.repo),
            **values,
        }

    def authorize(self, role: str, command: str, tool_id: str) -> None:
        harness.handle_hook(
            self.paths,
            self.hook(
                role,
                "PreToolUse",
                tool_name="Bash",
                tool_use_id=tool_id,
                tool_input={"command": command},
            ),
        )

    def test_dual_activation_is_role_bound_ready_and_idempotent(self) -> None:
        run_dir = self.activate_dual()
        metadata = harness.read_json(run_dir / "metadata.json")
        self.assertEqual(metadata["status"], "active")
        self.assertEqual(set(metadata["participants"]), harness.PARTICIPANT_ROLES)
        self.assertNotEqual(
            metadata["participants"]["simulated_user"]["session_id"],
            metadata["participants"]["modeling_agent"]["session_id"],
        )
        self.activate_participant("modeling_agent", "claude-model-session", "m" * 32)
        activated = [
            event for event in harness.load_events(run_dir) if event["kind"] == "activated"
        ]
        self.assertEqual(len(activated), 2)
        conflicting = {
            **self.base,
            "participant_role": "simulated_user",
            "activation_nonce": "x" * 32,
        }
        with self.assertRaises(harness.HarnessError):
            harness.acknowledge_activation(
                self.paths,
                self.hook("modeling_agent", "PreToolUse", tool_name="Bash"),
                conflicting,
            )

    def test_checked_in_claude_hooks_and_agent_definitions_are_complete(self) -> None:
        settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        required = {
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "SubagentStart",
            "SubagentStop",
            "TaskCreated",
            "TaskCompleted",
            "TeammateIdle",
            "Stop",
            "StopFailure",
            "SessionEnd",
        }
        self.assertEqual(set(settings["hooks"]), required)
        for entries in settings["hooks"].values():
            for entry in entries:
                for hook in entry["hooks"]:
                    self.assertIn("${CLAUDE_PROJECT_DIR}", hook["command"])
        expected_agents = {
            "simulated-user",
            "ontology-modeling-agent",
            "source-extractor",
            "semantic-analyst",
            "ontology-reviewer",
        }
        self.assertEqual(
            {path.stem for path in (REPO / ".claude" / "agents").glob("*.md")},
            expected_agents,
        )

    def test_activation_nonce_is_removed_from_visible_prompt(self) -> None:
        run_dir = self.activate_dual()
        nonce = "nonce-value-must-never-persist-123456"
        harness.handle_hook(
            self.paths,
            self.hook(
                "modeling_agent",
                "UserPromptSubmit",
                prompt=f"run activate --activation-nonce {nonce} --project-id project-dual",
                prompt_id="prompt-with-nonce",
            ),
        )
        persisted = (run_dir / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(nonce, persisted)
        self.assertIn("--activation-nonce REDACTED", persisted)

    def test_message_receipts_are_single_use_and_simulated_decisions_are_labeled(self) -> None:
        run_dir = self.activate_dual()
        operation = "operation-send-001"
        command = (
            "python3 .codex/hooks/modeling_harness.py message send "
            f"--run-id {self.run_id} --operation-id {operation} "
            "--recipient-role modeling_agent --message-kind approval "
            "--content 'I approve the simulated proposal'"
        )
        args = harness.command_arguments(command)
        assert args
        with self.assertRaisesRegex(harness.HarnessError, "no Hook-issued receipt"):
            harness.message_cli(self.paths, args)
        self.authorize("simulated_user", command, "authorize-message")
        tampered = harness.command_arguments(
            command.replace("simulated proposal", "other proposal")
        )
        assert tampered
        with self.assertRaisesRegex(harness.HarnessError, "does not match"):
            harness.message_cli(self.paths, tampered)
        output = StringIO()
        with redirect_stdout(output):
            harness.message_cli(self.paths, args)
        message_id = output.getvalue().strip()
        event = harness.load_events(run_dir)[-1]
        self.assertEqual(event["kind"], "mailbox_message")
        self.assertTrue(event["payload"]["simulated"])
        self.assertEqual(event["payload"]["report_source"], "agent_reported")
        self.assertEqual(event["payload"]["runtime_session_id"], "claude-user-session")
        with self.assertRaisesRegex(harness.HarnessError, "stale, consumed"):
            harness.message_cli(self.paths, args)

        poll = argparse.Namespace(
            message_command="poll",
            run_id=self.run_id,
            participant_role="modeling_agent",
        )
        polled = StringIO()
        with redirect_stdout(polled):
            harness.message_cli(self.paths, poll)
        self.assertEqual(json.loads(polled.getvalue())[0]["message_id"], message_id)

        ack_command = (
            "python3 .codex/hooks/modeling_harness.py message ack "
            f"--run-id {self.run_id} --operation-id operation-ack-001 "
            f"--message-id {message_id}"
        )
        self.authorize("modeling_agent", ack_command, "authorize-ack")
        ack_args = harness.command_arguments(ack_command)
        assert ack_args
        with redirect_stdout(StringIO()):
            harness.message_cli(self.paths, ack_args)
        self.assertIn(
            message_id,
            harness.read_json(run_dir / "state.json")["message_acks"]["modeling_agent"],
        )

    def test_replacement_invalidates_old_session_and_receipt_epoch(self) -> None:
        run_dir = self.activate_dual()
        command = (
            "python3 .codex/hooks/modeling_harness.py message send "
            f"--run-id {self.run_id} --operation-id operation-stale-001 "
            "--recipient-role modeling_agent --message-kind answer --content old"
        )
        self.authorize("simulated_user", command, "authorize-stale")
        nonce_output = StringIO()
        with redirect_stdout(nonce_output):
            harness.replace_participant_cli(
                self.paths,
                argparse.Namespace(run_id=self.run_id, participant_role="simulated_user"),
            )
        before = len(harness.load_events(run_dir))
        harness.handle_hook(
            self.paths,
            self.hook("simulated_user", "Stop", last_assistant_message="late old-session output"),
        )
        self.assertEqual(len(harness.load_events(run_dir)), before)
        args = harness.command_arguments(command)
        assert args
        with self.assertRaisesRegex(harness.HarnessError, "stale, consumed"):
            harness.message_cli(self.paths, args)
        self.activate_participant(
            "simulated_user", "claude-user-session-new", nonce_output.getvalue().strip()
        )
        participant = harness.read_json(run_dir / "metadata.json")["participants"]["simulated_user"]
        self.assertEqual(participant["epoch"], 2)
        self.assertEqual(participant["session_id"], "claude-user-session-new")

    def test_nested_agent_task_lifecycle_and_modeling_authority_are_role_scoped(self) -> None:
        run_dir = self.activate_dual()
        original = harness.invoke_claude
        harness.invoke_claude = lambda _run, _prompt: delta()
        try:
            harness.handle_hook(
                self.paths,
                self.hook(
                    "modeling_agent",
                    "PreToolUse",
                    tool_name="Agent",
                    tool_use_id="agent-dispatch",
                    tool_input={"subagent_type": "source-extractor", "prompt": "Extract facts"},
                ),
            )
            harness.handle_hook(
                self.paths,
                self.hook(
                    "modeling_agent",
                    "SubagentStop",
                    agent_id="extractor-1",
                    agent_type="source-extractor",
                    agent_transcript_path="/must/not/persist",
                    last_assistant_message="Extraction complete",
                ),
            )
            for event_name in ("TaskCreated", "TaskCompleted", "TeammateIdle", "StopFailure"):
                harness.handle_hook(
                    self.paths,
                    self.hook(
                        "modeling_agent",
                        event_name,
                        task_id="task-1",
                        subject="Extract evidence",
                        status="completed",
                        error="synthetic failure" if event_name == "StopFailure" else "",
                    ),
                )
        finally:
            harness.invoke_claude = original
        persisted = (run_dir / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("source-extractor", persisted)
        self.assertIn("taskcreated", persisted)
        self.assertNotIn("must/not/persist", persisted)

        platform_hook = self.hook(
            "simulated_user",
            "PostToolUse",
            tool_name="record_modeling_execution_event",
            tool_use_id="user-platform-call",
            tool_input={"event_type": "review_completed", "phase": "review"},
            tool_response={"success": True, "status": "completed"},
        )
        harness.handle_hook(self.paths, platform_hook)
        self.assertEqual(harness.read_json(run_dir / "state.json")["pending_checkpoints"], {})

    def test_dual_checkpoint_requires_modeler_receipt(self) -> None:
        run_dir = self.activate_dual()
        command = (
            "python3 .codex/hooks/modeling_harness.py checkpoint "
            f"--run-id {self.run_id} --phase review --event-type review_completed "
            "--summary 'review passed' --client-checkpoint-id checkpoint-dual-1 "
            "--operation-id operation-checkpoint-1"
        )
        args = harness.command_arguments(command)
        assert args
        with self.assertRaisesRegex(harness.HarnessError, "no Hook-issued receipt"):
            harness.checkpoint_cli(self.paths, args)
        self.authorize("modeling_agent", command, "authorize-checkpoint")
        with redirect_stdout(StringIO()):
            harness.checkpoint_cli(self.paths, args)
        checkpoint = harness.read_json(run_dir / "state.json")["pending_checkpoints"][
            "modeling_agent"
        ]
        self.assertEqual(checkpoint["event_type"], "review_completed")

        denied = command.replace("operation-checkpoint-1", "operation-checkpoint-user")
        self.authorize("simulated_user", denied, "authorize-user-checkpoint")
        denied_args = harness.command_arguments(denied)
        assert denied_args
        with self.assertRaisesRegex(harness.HarnessError, "only modeling_agent"):
            harness.checkpoint_cli(self.paths, denied_args)

    def test_claude_summarizer_requires_structured_output_and_isolated_command(self) -> None:
        run_dir = self.activate_dual()
        completed = mock.Mock(returncode=0, stdout=json.dumps({"structured_output": delta()}))
        with mock.patch.object(harness.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                harness.invoke_claude(run_dir, "bounded prompt")["summary"], "A bounded summary"
            )
        command = run.call_args.args[0]
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--json-schema", command)
        self.assertEqual(run.call_args.kwargs["input"], "bounded prompt")
        self.assertNotEqual(Path(run.call_args.kwargs["cwd"]), self.repo)
        with mock.patch.object(
            harness.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout=json.dumps({"result": delta()})),
        ):
            with self.assertRaisesRegex(harness.HarnessError, "structured_output"):
                harness.invoke_claude(run_dir, "bounded prompt")

    def test_claude_command_removes_only_unsupported_schema_declaration(self) -> None:
        schema_path = self.paths.schema
        original_bytes = schema_path.read_bytes()
        original = json.loads(original_bytes)

        command = harness.claude_command(self.paths)
        adapted = json.loads(command[command.index("--json-schema") + 1])

        self.assertNotIn("$schema", adapted)
        self.assertEqual(
            adapted, {key: value for key, value in original.items() if key != "$schema"}
        )
        self.assertEqual(adapted["additionalProperties"], False)
        self.assertEqual(adapted["required"], original["required"])
        self.assertEqual(adapted["properties"], original["properties"])
        self.assertEqual(adapted["$defs"], original["$defs"])
        self.assertEqual(schema_path.read_bytes(), original_bytes)


class FastLocalHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="fast-harness-test-")
        self.repo = Path(self.temporary.name)
        (self.repo / ".git").mkdir()
        (self.repo / ".codex" / "hooks").mkdir(parents=True)
        (self.repo / ".claude" / "scenarios").mkdir(parents=True)
        (self.repo / "docs" / "modeling-retrospectives").mkdir(parents=True)
        for relative in (
            Path(".codex/hooks.json"),
            Path(".codex/hooks/modeling_harness.py"),
            Path(".codex/hooks/summary.schema.json"),
        ):
            target = self.repo / relative
            target.write_bytes((REPO / relative).read_bytes())
        (self.repo / ".claude" / "scenarios" / "fixture.json").write_text(
            '{"scenario":"fixture"}\n', encoding="utf-8"
        )
        self.paths = harness.Paths(self.repo)
        self.values = {
            "run_id": "fast-run-12345678",
            "build_session_id": "build-fast-1",
            "project_id": "project-fast-1",
            "scenario": ".claude/scenarios/fixture.json",
            "launch_intent_hash": "a" * 64,
            "simulated_user_session_id": "11111111-1111-4111-8111-111111111111",
            "modeling_agent_session_id": "22222222-2222-4222-8222-222222222222",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self, **changes: str) -> Path:
        values = {**self.values, **changes}
        with redirect_stdout(StringIO()):
            harness.prepare_fast_cli(self.paths, argparse.Namespace(**values))
        return self.paths.run(values["run_id"])

    def test_prepare_fast_commits_whole_identity_and_is_idempotent(self) -> None:
        run_dir = self.prepare()
        metadata = harness.read_json(run_dir / "metadata.json")
        self.assertEqual(metadata["evaluation_profile"], "fast_local")
        self.assertEqual(metadata["summary_policy"], "explicit")
        self.assertTrue(metadata["preparation_complete"])
        self.assertEqual(metadata["status"], "active")
        self.assertEqual(set(metadata["participants"]), harness.PARTICIPANT_ROLES)
        for role, session_id in metadata["fast_identity"]["sessions"].items():
            participant = metadata["participants"][role]
            self.assertEqual(participant["session_id"], session_id)
            self.assertIsNotNone(participant["activated_at"])
            registry = harness.read_json(self.paths.registry / f"{session_id}.json")
            self.assertEqual(registry["preparation_id"], metadata["preparation_id"])
        before = (run_dir / "events.jsonl").read_bytes()
        self.prepare()
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), before)
        hook = {
            "session_id": self.values["modeling_agent_session_id"],
            "cwd": str(self.repo),
        }
        binding = harness.active_binding(self.paths, hook)
        self.assertIsNotNone(binding)
        assert binding
        self.assertEqual(binding.participant_role, "modeling_agent")

        status = StringIO()
        with redirect_stdout(status):
            harness.status_cli(self.paths, argparse.Namespace(run_id=self.values["run_id"]))
        value = json.loads(status.getvalue())
        self.assertTrue(value["ready"])
        self.assertEqual(value["evaluation_profile"], "fast_local")
        self.assertNotIn("session_id", status.getvalue())

    def test_prepare_fast_rejects_conflicts_invalid_sessions_and_outside_scenario(self) -> None:
        self.prepare()
        with self.assertRaisesRegex(harness.HarnessError, "conflicting"):
            self.prepare(build_session_id="other-build")
        with self.assertRaisesRegex(harness.HarnessError, "distinct"):
            self.prepare(
                run_id="fast-run-distinct",
                modeling_agent_session_id=self.values["simulated_user_session_id"],
            )
        outside = Path(self.temporary.name).parent / "outside-fast-scenario.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaisesRegex(harness.HarnessError, "inside the repository"):
                self.prepare(run_id="fast-run-outside1", scenario=str(outside))
        finally:
            outside.unlink()

    def test_incomplete_preparation_is_hook_invisible_and_retry_repairs_each_write(self) -> None:
        original_atomic = harness.atomic_json
        original_append = harness.append_event_locked
        cases = [("atomic", index) for index in range(1, 6)] + [
            ("append", index) for index in range(1, 4)
        ]
        for case_index, (kind, fail_at) in enumerate(cases):
            values = {
                **self.values,
                "run_id": f"fast-fault-{case_index:08d}",
                "simulated_user_session_id": str(uuid.UUID(int=100 + case_index)),
                "modeling_agent_session_id": str(uuid.UUID(int=200 + case_index)),
            }
            calls = 0

            def atomic(path: Path, value: dict[str, object]) -> None:
                nonlocal calls
                calls += 1
                if kind == "atomic" and calls == fail_at:
                    raise OSError("injected atomic failure")
                original_atomic(path, value)

            append_calls = 0

            def append(*args, **kwargs):
                nonlocal append_calls
                append_calls += 1
                if kind == "append" and append_calls == fail_at:
                    raise OSError("injected append failure")
                return original_append(*args, **kwargs)

            with (
                mock.patch.object(harness, "atomic_json", atomic),
                mock.patch.object(harness, "append_event_locked", append),
            ):
                with self.assertRaises(OSError):
                    harness.prepare_fast_cli(self.paths, argparse.Namespace(**values))
            metadata_path = self.paths.run(values["run_id"]) / "metadata.json"
            if metadata_path.exists():
                metadata = harness.read_json(metadata_path)
                self.assertIsNot(metadata.get("preparation_complete"), True)
            hook = {"session_id": values["simulated_user_session_id"], "cwd": str(self.repo)}
            self.assertIsNone(harness.active_binding(self.paths, hook))
            with redirect_stdout(StringIO()):
                harness.prepare_fast_cli(self.paths, argparse.Namespace(**values))
            metadata = harness.read_json(metadata_path)
            self.assertTrue(metadata["preparation_complete"])
            events = harness.load_events(self.paths.run(values["run_id"]))
            self.assertEqual(
                sum(event["kind"] == "fast_preparation_started" for event in events), 1
            )
            self.assertEqual(sum(event["kind"] == "activated" for event in events), 2)

    def test_shared_registry_lock_allows_exactly_one_cross_run_claim(self) -> None:
        queue: multiprocessing.Queue = multiprocessing.Queue()
        first = dict(self.values, run_id="fast-race-first1")
        second = dict(
            self.values,
            run_id="fast-race-second",
            modeling_agent_session_id="33333333-3333-4333-8333-333333333333",
        )
        processes = [
            multiprocessing.Process(
                target=prepare_fast_worker, args=(str(self.repo), values, queue)
            )
            for values in (first, second)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in processes), ["HarnessError", "ok"])
        registry = harness.read_json(
            self.paths.registry / f"{self.values['simulated_user_session_id']}.json"
        )
        self.assertIn(registry["run_id"], {first["run_id"], second["run_id"]})
        rejected = second if registry["run_id"] == first["run_id"] else first
        rejected_metadata = self.paths.run(rejected["run_id"]) / "metadata.json"
        self.assertFalse(rejected_metadata.exists())

    def test_explicit_summary_stays_local_until_publish_is_requested(self) -> None:
        run_dir = self.prepare()
        calls = 0

        def summarize(_run: Path, _prompt: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return delta()

        self.assertIsNone(harness.finalize_run(self.paths, run_dir, "completed", summarize))
        self.assertEqual(calls, 0)
        self.assertEqual(
            harness.read_json(run_dir / "state.json")["finalization_status"], "local_only"
        )
        target = harness.finalize_run(
            self.paths,
            run_dir,
            "completed",
            summarize,
            publish_requested=True,
        )
        self.assertIsNotNone(target)
        self.assertGreater(calls, 0)


if __name__ == "__main__":
    unittest.main()
