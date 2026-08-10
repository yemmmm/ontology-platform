from __future__ import annotations

import tempfile
import unittest
import os
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from io import StringIO
from uuid import uuid4
from unittest.mock import patch

from modeling_team import __main__ as team_main
from modeling_team.__main__ import _decode_foreground_message, _foreground_event_loop
from modeling_team.contracts import TeamConfigurationError, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeMessage
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker


class _OwnerAnswerAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []
        self.inbox: list[RuntimeMessage] = []
        self.fail_owner = False
        self.emit_prompt = True

    def send_message(self, recipient: str, delivery: object) -> None:
        self.sent.append((recipient, delivery))
        if self.fail_owner and getattr(delivery, "kind", None) == "owner-answer":
            raise RuntimeError("adapter delivery failed")
        if (
            self.emit_prompt
            and recipient == "coordinator"
            and getattr(delivery, "text", None).startswith("candidate")
        ):
            self.inbox.append(RuntimeMessage("coordinator", "Coordinator displayed candidate?"))

    def receive_messages(self) -> list[RuntimeMessage]:
        messages, self.inbox = self.inbox, []
        return messages

    def wait_settled(self, _agent_ids: list[str], _timeout: float) -> bool:
        return False


class _LiveProjectScope:
    """No-network PlatformScope test double that creates one owned binding."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.project_id: str | None = None
        self.ontology_id: str | None = None
        self.protocol_key: str | None = None
        self.retain_nonempty = False
        self.active_resources: set[str] = set()
        self.prepare_inputs: list[dict[str, str]] = []
        self.cleanup_calls = 0
        self.terminal_results = None

    def prepare(self, scope: dict[str, str]) -> None:
        self.prepare_inputs.append(dict(scope))
        if scope != {"mode": "create"}:
            raise AssertionError("formal scope must be normalized before live preparation")
        self.project_id = f"live-project-{self.run_id}"
        self.ontology_id = f"live-ontology-{self.run_id}"
        self.protocol_key = f"live-protocol-key-{self.run_id}"
        self.active_resources.update({self.project_id, self.ontology_id, self.protocol_key})

    def read_protocol_context(self) -> dict[str, str]:
        assert self.project_id is not None
        assert self.ontology_id is not None
        return {"project_id": self.project_id, "ontology_id": self.ontology_id}

    def cleanup(self) -> dict[str, object]:
        self.cleanup_calls += 1
        residue = sorted(self.active_resources)
        self.active_resources.clear()
        return {
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "scope_disposition": "deleted-empty",
            "released_test_double_resources": residue,
            "test_double_residue": sorted(self.active_resources),
        }


class _StartAdapter(_OwnerAnswerAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.started_tasks: list[str] = []
        self.model_calls = 0

    def start_roster(self, _run: object, agents: list[object]) -> list[SimpleNamespace]:
        return [SimpleNamespace(agent_id=agent.agent_id) for agent in agents]

    def probe_role_visibility(self, run: object) -> dict[str, dict[str, str]]:
        configuration = run.configuration
        return {
            agent.agent_id: {"probe": "passed"}
            for agent in configuration.profile.agents
        }

    def start_task(
        self,
        agent_id: str,
        _task_text: str,
        _skill_paths: list[str],
        _roster: list[str],
    ) -> None:
        self.started_tasks.append(agent_id)

    def cleanup_identifiers(self) -> dict[str, object]:
        return {"private_credentials_destroyed": True}

    def send_message(self, recipient: str, delivery: object) -> None:
        self.sent.append((recipient, delivery))
        if self.fail_owner and getattr(delivery, "kind", None) == "owner-answer":
            raise RuntimeError("adapter delivery failed")
        if recipient == "coordinator" and getattr(delivery, "kind", None) == "peer":
            self.inbox.append(RuntimeMessage("coordinator", f"Prompt: {delivery.text}"))

    def stop(self) -> None:
        return None


def _formal_runner(root: Path) -> tuple[TeamRunner, _OwnerAnswerAdapter]:
    run_root = root / "run"
    (run_root / "evidence").mkdir(parents=True)
    agents = [
        SimpleNamespace(agent_id="modeling", package=SimpleNamespace(role="modeling")),
        SimpleNamespace(agent_id="coordinator", package=SimpleNamespace(role="coordinator")),
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(
            profile_id="r2-3-005-modeling-team", agents=agents, parameters={}
        ),
    )
    adapter = _OwnerAnswerAdapter()
    runner = TeamRunner(repository_root=root, adapter=adapter)
    runner.run = SimpleNamespace(
        run_id="run-1", root=run_root, scope={"mode": "create"}, configuration=configuration
    )
    # Formal production shape: normalized TeamRun.scope is mode-only and the
    # generated Project identity lives on the separately prepared live scope.
    runner.scope = SimpleNamespace(project_id="project-1")
    runner.transport = TeamTransportBroker(
        run_root / "broker",
        {
            ("modeling", "coordinator"),
            ("protocol", "coordinator"),
            ("modeling", "protocol"),
            ("coordinator", "modeling"),
        },
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
    )
    return runner, adapter


def _drain_and_observe(runner: TeamRunner) -> list[dict[str, object]]:
    """Mirror the production foreground emit-success acknowledgement in tests."""
    output = runner.drain()
    runner.observe_foreground_output(output)
    return output


class RunnerR23005OwnerAnswerTests(unittest.TestCase):
    def test_foreground_decoder_rejects_nonobjects_malformed_and_duplicate_keys(self) -> None:
        self.assertEqual(_decode_foreground_message('{"action":"status"}'), {"action": "status"})
        for line in (
            "[]",
            "null",
            "1",
            '{"action":"status","action":"pause"}',
            '{"action":{"nested":1,"nested":2}}',
            '{"action":"status"',
        ):
            with self.assertRaises(TeamConfigurationError):
                _decode_foreground_message(line)

    def test_foreground_loop_rejects_decoder_error_and_continues(self) -> None:
        class Runner:
            def __init__(self, root) -> None:
                self.received: list[dict[str, object]] = []
                self.observed: list[list[dict[str, object]]] = []
                self.drains = 0
                self.run = SimpleNamespace(root=root)

            def drain(self):
                self.drains += 1
                if self.drains >= 3:
                    (self.run.root / "state.json").write_text(
                        json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                        encoding="utf-8",
                    )
                return []

            def receive_outer(self, message):
                self.received.append(message)
                return [{"type": "accepted"}]

            def observe_foreground_output(self, output):
                self.observed.append(output)

        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(Path(directory))
            emitted: list[list[dict[str, object]]] = []
            stream = StringIO('{"action":"status","action":"pause"}\n{"action":"status"}\n')
            _foreground_event_loop(
                runner,
                stream,
                emitted.append,
                select_fn=lambda *_args: ([stream], [], []),
            )
        self.assertEqual(
            emitted,
            [
                [{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": True}],
                [{"type": "accepted"}],
            ],
        )
        self.assertEqual(runner.received, [{"action": "status"}])
        self.assertEqual(runner.observed, [[{"type": "accepted"}]])

    def test_foreground_loop_rejects_missing_action_and_keeps_run_for_next_input(self) -> None:
        class Runner:
            def __init__(self, root) -> None:
                self.received: list[dict[str, object]] = []
                self.cleaned = 0
                self.drains = 0
                self.run = SimpleNamespace(root=root)

            def drain(self):
                self.drains += 1
                if self.drains >= 3:
                    (self.run.root / "state.json").write_text(
                        json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                        encoding="utf-8",
                    )
                return []

            def receive_outer(self, message):
                self.received.append(message)
                return [{"type": "accepted"}]

            def cleanup(self):
                self.cleaned += 1

        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(Path(directory))
            emitted: list[list[dict[str, object]]] = []
            stream = StringIO('{"type":"issue-resolution"}\n{"action":"status"}\n')
            _foreground_event_loop(
                runner,
                stream,
                emitted.append,
                select_fn=lambda *_args: ([stream], [], []),
            )
        self.assertEqual(
            emitted,
            [
                [{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": True}],
                [{"type": "accepted"}],
            ],
        )
        self.assertEqual(runner.received, [{"action": "status"}])
        self.assertEqual(runner.cleaned, 0)

    def test_classify_failure_requires_explicit_requirement_before_ledger_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stderr = StringIO()
            with (
                patch.object(team_main, "repository_root", return_value=root),
                patch.object(
                    team_main.sys,
                    "argv",
                    [
                        "modeling-team",
                        "classify-failure",
                        "--run-id",
                        "start29",
                        "--classification",
                        "collaboration/routing",
                    ],
                ),
                patch.object(team_main.sys, "stderr", stderr),
            ):
                with self.assertRaises(SystemExit) as raised:
                    team_main.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(list((root / "workspaces").rglob("*")) if (root / "workspaces").exists() else [], [])
            self.assertIn("the following arguments are required: --requirement-id", stderr.getvalue())

    def test_foreground_loop_rejects_early_issue_resolution_then_retries_after_pause(self) -> None:
        class Ledger:
            state = "reported"

        class Runner:
            def __init__(self, root) -> None:
                self.transport = SimpleNamespace(issue_ledger=Ledger())
                self.drains = 0
                self.received: list[dict[str, object]] = []
                self.run = SimpleNamespace(root=root)

            def drain(self):
                self.drains += 1
                if self.drains == 2:
                    self.transport.issue_ledger.state = "waiting_owner"
                if self.drains >= 3:
                    (self.run.root / "state.json").write_text(
                        json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                        encoding="utf-8",
                    )
                return []

            def receive_outer(self, message):
                self.assert_resolution_gate()
                self.received.append(message)
                return [{"type": "resolution-accepted"}]

            def assert_resolution_gate(self) -> None:
                assert self.transport.issue_ledger.state == "waiting_owner"

        resolution = {
            "action": "issue_resolution",
            "issue_id": "issue-1",
            "reporter_id": "modeling",
            "control_epoch": 1,
            "resolution_type": "guidance",
            "resolution_text": "Use the already retained protocol receipt.",
        }
        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(Path(directory))
            emitted: list[list[dict[str, object]]] = []
            stream = StringIO(
                json.dumps(resolution, ensure_ascii=False)
                + "\n"
                + json.dumps(resolution, ensure_ascii=False)
                + "\n"
            )
            _foreground_event_loop(
                runner,
                stream,
                emitted.append,
                select_fn=lambda *_args: ([stream], [], []),
            )
        self.assertEqual(
            emitted,
            [
                [{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": True}],
                [{"type": "resolution-accepted"}],
            ],
        )
        self.assertEqual(runner.received, [resolution])

    def test_foreground_loop_keeps_internal_drain_configuration_errors_fatal(self) -> None:
        class Runner:
            def drain(self):
                raise TeamConfigurationError("internal drain secret")

        with self.assertRaisesRegex(TeamConfigurationError, "internal drain secret"):
            _foreground_event_loop(
                Runner(),
                StringIO('{"action":"status"}\n'),
                lambda _output: None,
                select_fn=lambda *_args: (["readable"], [], []),
            )

    def test_foreground_loop_keeps_admitted_receive_outer_errors_fatal(self) -> None:
        class Runner:
            def drain(self):
                return []

            def receive_outer(self, _message):
                raise TeamConfigurationError("receive validation failed")

        with self.assertRaisesRegex(TeamConfigurationError, "receive validation failed"):
            _foreground_event_loop(
                Runner(),
                StringIO('{"action":"status"}\n'),
                lambda _output: None,
                select_fn=lambda *_args: (["readable"], [], []),
            )

    def test_main_rejects_invalid_foreground_shape_without_killing_run(self) -> None:
        invalid_lines = (
            "[]\n",
            "1\n",
            "null\n",
            '{"action":"status","action":"pause"}\n',
            '{"action":"status"\n',
        )
        for invalid_line in invalid_lines:
            with self.subTest(invalid_line=invalid_line), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                scope_path = root / "scope.yaml"
                scope_path.write_text("{}", encoding="utf-8")
                run_root = root / "run"
                run_root.mkdir()
                created: list[object] = []

                class FakeRunner:
                    def __init__(self, **_kwargs):
                        self.cleaned = 0
                        self.prepared = 0
                        self.started = 0
                        self.received = 0
                        self.drains = 0
                        self.run = SimpleNamespace(root=run_root)
                        created.append(self)

                    def prepare(self, **_kwargs):
                        self.prepared += 1

                    def start(self):
                        self.started += 1

                    def drain(self):
                        self.drains += 1
                        # The foreground loop now runs until the terminal-report
                        # gate fires (stdin EOF no longer ends it).  Reject the
                        # invalid line, then retire the loop at the next drain.
                        if self.drains >= 2:
                            (self.run.root / "state.json").write_text(
                                json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                                encoding="utf-8",
                            )
                        return []

                    def receive_outer(self, _message):
                        self.received += 1
                        raise AssertionError("invalid foreground JSON reached Runner")

                    def cleanup(self):
                        self.cleaned += 1

                read_fd, write_fd = os.pipe()
                os.write(write_fd, invalid_line.encode("utf-8"))
                os.close(write_fd)
                stream = os.fdopen(read_fd, "r", encoding="utf-8")
                argv = [
                    "modeling-team",
                    "run",
                    "--profile",
                    str(root / "profile.yaml"),
                    "--task",
                    str(root / "task.yaml"),
                    "--run-id",
                    "invalid-json-run",
                    "--scope",
                    str(scope_path),
                ]
                configuration = SimpleNamespace(
                    task=SimpleNamespace(schema_version=1),
                    profile=SimpleNamespace(profile_id="legacy"),
                )
                stdout = StringIO()
                with (
                    patch.object(team_main, "repository_root", return_value=root),
                    patch.object(team_main, "load_formal_team_configuration", return_value=configuration),
                    patch.object(
                        team_main,
                        "_bootstrap_helpers",
                        return_value=(lambda: ("key", "id"), lambda _id: True),
                    ),
                    patch.object(team_main, "CodexRuntimeAdapter", return_value=SimpleNamespace()),
                    patch.object(team_main, "TeamRunner", FakeRunner),
                    patch.object(team_main.sys, "argv", argv),
                    patch.object(team_main.sys, "stdin", stream),
                    patch.object(team_main.sys, "stdout", stdout),
                ):
                    self.assertEqual(team_main.main(), 0)
                stream.close()
                self.assertEqual(len(created), 1)
                self.assertEqual(created[0].prepared, 1)
                self.assertEqual(created[0].started, 1)
                self.assertEqual(created[0].received, 0)
                self.assertEqual(created[0].cleaned, 1)
                self.assertEqual(
                    json.loads(stdout.getvalue()),
                    [{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": True}],
                )

    def test_formal_question_display_and_owner_answer_go_directly_to_modeling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate?", expects_reply=True
            )

            stream = StringIO('{"action":"user","text":"未知"}\n')
            polls = iter([([stream], [], []), ([stream], [], [])])
            emitted: list[list[dict[str, object]]] = []

            # The foreground loop now runs until the terminal-report gate fires
            # (stdin EOF no longer ends it).  Drive exactly one owner answer,
            # then signal terminal completion on the next drain so the loop
            # returns without consuming the rest of the polls double.
            _original_receive_outer = runner.receive_outer

            def _terminating_receive_outer(message):
                output = _original_receive_outer(message)
                (runner.run.root / "state.json").write_text(
                    json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                    encoding="utf-8",
                )
                return output

            runner.receive_outer = _terminating_receive_outer  # type: ignore[method-assign]
            _foreground_event_loop(
                runner,
                stream,
                emitted.append,
                select_fn=lambda *_args: next(polls),
            )
            runner.receive_outer = _original_receive_outer  # type: ignore[method-assign]
            first = emitted[0]
            self.assertEqual(first[0]["delivery_id"], question.delivery_id)
            self.assertTrue(runner._outer_questions[question.delivery_id]["displayed"])
            self.assertTrue((runner.run.root / "evidence/outer-question.jsonl").is_file())

            # The strict schema-v2 envelope contains no operator-supplied question ID.
            second = emitted[1]
            owner = second[0]
            self.assertEqual(owner["recipient_id"], "modeling")
            self.assertEqual(owner["reply_to_delivery_id"], question.delivery_id)
            self.assertTrue(owner["owner_answer_id"].startswith("owner-answer-"))
            self.assertEqual(owner["release_id"], owner["delivery_id"])
            self.assertEqual(
                [recipient for recipient, _ in adapter.sent], ["coordinator", "modeling"]
            )
            self.assertEqual(adapter.sent[1][1].kind, "owner-answer")
            self.assertTrue(
                runner.transport.report("modeling", "completed", "answered")
            )

            with self.assertRaisesRegex(TeamConfigurationError, "no unanswered"):
                runner.receive_outer({"action": "user", "text": "未知"})

    def test_formal_explicit_question_id_selects_one_of_multiple_questions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            first = runner.transport.send(
                "modeling", "coordinator", "candidate first", expects_reply=True
            )
            second = runner.transport.send(
                "modeling", "coordinator", "candidate second", expects_reply=True
            )
            displayed = _drain_and_observe(runner)
            self.assertEqual(
                [
                    envelope["delivery_id"]
                    for envelope in displayed
                    if envelope.get("type") == "delivery"
                ],
                [first.delivery_id, second.delivery_id],
            )

            # Text-only inference remains fail-closed when two questions are
            # currently eligible; the explicit ID is the only disambiguator.
            with self.assertRaisesRegex(TeamConfigurationError, "matches multiple"):
                runner.receive_outer({"action": "user", "text": "ambiguous"})

            selected_output = runner.receive_outer(
                {
                    "action": "user",
                    "text": "answer for second",
                    "question_delivery_id": second.delivery_id,
                }
            )
            self.assertEqual(selected_output[0]["reply_to_delivery_id"], second.delivery_id)
            self.assertTrue(runner._outer_questions[second.delivery_id]["consumed"])
            self.assertFalse(runner._outer_questions[first.delivery_id]["consumed"])
            owner = runner._owner_answers[(second.delivery_id, "answer for second")]
            self.assertEqual(owner["question_delivery_id"], second.delivery_id)
            outer_user = json.loads(
                (runner.run.root / "evidence/outer-user.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertEqual(outer_user["question_delivery_id"], second.delivery_id)
            self.assertEqual(outer_user["delivery_id"], outer_user["release_id"])

            # Once only the first question remains eligible, the legacy
            # text-only path still resolves it without an explicit ID.
            fallback_output = runner.receive_outer({"action": "user", "text": "answer for first"})
            self.assertEqual(fallback_output[0]["reply_to_delivery_id"], first.delivery_id)
            self.assertTrue(runner._outer_questions[first.delivery_id]["consumed"])

    def test_formal_explicit_question_id_rejects_forged_undisplayed_replay_and_wrong_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            undisplayed = runner.transport.send(
                "modeling", "coordinator", "candidate not displayed", expects_reply=True
            )
            output = runner.drain()
            with self.assertRaisesRegex(TeamConfigurationError, "requires a question delivery ID"):
                runner.receive_outer(
                    {"action": "user", "text": "null ID", "question_delivery_id": None}
                )
            with self.assertRaisesRegex(TeamConfigurationError, "not been displayed"):
                runner.receive_outer(
                    {
                        "action": "user",
                        "text": "undisplayed answer",
                        "question_delivery_id": undisplayed.delivery_id,
                    }
                )
            runner.observe_foreground_output(output)

            with self.assertRaisesRegex(TeamConfigurationError, "unknown"):
                runner.receive_outer(
                    {"action": "user", "text": "forged answer", "question_delivery_id": "delivery-forged"}
                )

            runner.receive_outer(
                {
                    "action": "user",
                    "text": "first answer",
                    "question_delivery_id": undisplayed.delivery_id,
                }
            )
            with self.assertRaisesRegex(TeamConfigurationError, "already consumed"):
                runner.receive_outer(
                    {
                        "action": "user",
                        "text": "replayed answer",
                        "question_delivery_id": undisplayed.delivery_id,
                    }
                )

            wrong_binding = runner.transport.send(
                "modeling", "coordinator", "candidate wrong binding", expects_reply=True
            )
            _drain_and_observe(runner)
            record = runner._outer_questions[wrong_binding.delivery_id]
            record["project_id"] = "project-forged"
            with self.assertRaisesRegex(TeamConfigurationError, "project binding drifts"):
                runner.receive_outer(
                    {
                        "action": "user",
                        "text": "wrong project",
                        "question_delivery_id": wrong_binding.delivery_id,
                    }
                )
            record["project_id"] = runner.scope.project_id
            record["run_id"] = "run-forged"
            with self.assertRaisesRegex(TeamConfigurationError, "run binding drifts"):
                runner.receive_outer(
                    {
                        "action": "user",
                        "text": "wrong run",
                        "question_delivery_id": wrong_binding.delivery_id,
                    }
                )
            self.assertFalse(record["consumed"])

    def test_formal_live_binding_prepare_start_drain_and_owner_release_without_model(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ledger_root = base / "ledger"
            credential_path = base / "deepseek.env"
            credential_path.write_text("DEEPSEEK_API_KEY=round23-owner-test\n", encoding="utf-8")
            credential_path.chmod(0o600)
            adapter = _StartAdapter()
            scopes: list[_LiveProjectScope] = []

            def scope_factory(run: object) -> _LiveProjectScope:
                scope = _LiveProjectScope(run.run_id)
                scopes.append(scope)
                return scope

            runner = TeamRunner(
                repository_root=root,
                adapter=adapter,
                scope_factory=scope_factory,
                deepseek_credential_path=credential_path,
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=lambda **_kwargs: {
                    "status_code": 200,
                    "product_write_mode": "rdf_primary",
                },
            )
            # Keep this deterministic integration isolated from both live ledgers.
            runner._canonical_ledger_root = lambda: ledger_root
            profile_path = root / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
            task_path = root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"
            run_id = f"r23005-live-binding-{uuid4().hex}"

            def remove_run_root() -> None:
                if runner.run is not None:
                    runner.cleanup()
                run_root = root / "workspaces" / "modeling-runs" / run_id
                if run_root.exists():
                    rmtree(run_root)

            self.addCleanup(remove_run_root)
            with self.assertRaisesRegex(TeamConfigurationError, "unsupported fields"):
                runner.prepare(
                    run_id="r23005-live-binding-smuggle",
                    profile_path=profile_path,
                    task_path=task_path,
                    scope={"mode": "create", "project_id": "caller-project"},
                )
            with patch(
                "modeling_team.preflight.capture_clean_checkout",
                return_value={
                    "repository_root": str(root),
                    "head": "a" * 40,
                    "status_porcelain": "",
                    "status_digest": "b" * 64,
                },
            ):
                run = runner.prepare(
                    run_id=run_id,
                    profile_path=profile_path,
                    task_path=task_path,
                    scope={"mode": "create"},
                )
            self.assertEqual(run.scope, {"mode": "create"})
            runner.start()
            self.assertEqual(len(scopes), 1)
            live_scope = scopes[0]
            assert live_scope.project_id is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate live binding", expects_reply=True
            )
            first = _drain_and_observe(runner)
            self.assertEqual(first[0]["delivery_id"], question.delivery_id)
            self.assertEqual(
                runner._outer_questions[question.delivery_id]["project_id"],
                live_scope.project_id,
            )
            self.assertTrue(runner._outer_questions[question.delivery_id]["displayed"])

            owner_output = runner.receive_outer({"action": "user", "text": "captured answer"})
            self.assertEqual(owner_output[0]["recipient_id"], "modeling")
            owner = runner._owner_answers[(question.delivery_id, "captured answer")]
            self.assertEqual(owner["project_id"], live_scope.project_id)
            self.assertEqual(owner["run_id"], run.run_id)
            self.assertEqual(owner["question_delivery_id"], question.delivery_id)
            self.assertEqual(adapter.model_calls, 0)

            outer_question_records = [
                json.loads(line)
                for line in (run.root / "evidence/outer-question.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                any(record.get("project_id") == live_scope.project_id for record in outer_question_records)
            )
            outer_user = json.loads(
                (run.root / "evidence/outer-user.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertEqual(outer_user["project_id"], live_scope.project_id)
            self.assertEqual(outer_user["owner_answer_id"], owner["owner_answer_id"])

            cleanup = runner.cleanup()
            self.assertEqual(cleanup["scope"]["test_double_residue"], [])
            self.assertEqual(live_scope.active_resources, set())
            self.assertEqual(live_scope.cleanup_calls, 1)

    def test_failed_foreground_emit_does_not_bind_or_evidence_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate emit failure", expects_reply=True
            )

            def fail_emit(_output: object) -> None:
                raise OSError("foreground emit failed")

            with self.assertRaisesRegex(OSError, "foreground emit failed"):
                _foreground_event_loop(
                    runner,
                    StringIO(""),
                    fail_emit,
                    select_fn=lambda *_args: ([], [], []),
                )
            self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
            self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())
            with self.assertRaisesRegex(TeamConfigurationError, "not been displayed"):
                runner.receive_outer({"action": "user", "text": "未知"})

    def test_display_envelope_integrity_rejects_unknown_and_all_binding_drift(self) -> None:
        # An unknown delivery is ordinary foreground output and cannot create a
        # formal question record.
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            runner.observe_foreground_output(
                [{"type": "delivery", "delivery_id": "unknown-delivery"}]
            )
            self.assertEqual(runner._outer_questions, {})

        envelope_fields = {
            "sequence": 999,
            "timestamp": 0.0,
            "sender_id": "spoofed-modeling",
            "recipient_id": "spoofed-coordinator",
            "text": "spoofed question",
            "expects_reply": False,
            "reply_to_delivery_id": "old-question",
        }
        for field, value in envelope_fields.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                runner, _adapter = _formal_runner(Path(directory))
                assert runner.transport is not None
                question = runner.transport.send(
                    "modeling", "coordinator", "candidate integrity", expects_reply=True
                )
                output = runner.drain()
                candidate = next(item for item in output if item.get("delivery_id") == question.delivery_id)
                candidate[field] = value
                with self.assertRaisesRegex(TeamConfigurationError, "display envelope"):
                    runner.observe_foreground_output(output)
                self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
                self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())

        for record_field, value in (("run_id", "other-run"), ("project_id", "other-project"), ("origin_agent_id", "protocol")):
            with self.subTest(record_field=record_field), tempfile.TemporaryDirectory() as directory:
                runner, _adapter = _formal_runner(Path(directory))
                assert runner.transport is not None
                question = runner.transport.send(
                    "modeling", "coordinator", "candidate binding", expects_reply=True
                )
                output = runner.drain()
                runner._outer_questions[question.delivery_id][record_field] = value
                with self.assertRaisesRegex(TeamConfigurationError, "display binding"):
                    runner.observe_foreground_output(output)
                self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
                self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())

    def test_display_replay_is_idempotent_and_multiple_questions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate replay", expects_reply=True
            )
            output = runner.drain()
            runner.observe_foreground_output(output)
            runner.observe_foreground_output(output)
            records = (runner.run.root / "evidence/outer-question.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 1)
            runner._release_owner_answer("coordinator", "未知", question.delivery_id)
            runner.observe_foreground_output(output)
            self.assertTrue(runner._outer_questions[question.delivery_id]["consumed"])
            self.assertEqual(
                len((runner.run.root / "evidence/outer-question.jsonl").read_text(encoding="utf-8").splitlines()),
                1,
            )

        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            first = runner.transport.send("modeling", "coordinator", "first", expects_reply=True)
            second = runner.transport.send("modeling", "coordinator", "second", expects_reply=True)
            output = runner.drain()
            runner.observe_foreground_output(output)
            self.assertTrue(runner._outer_questions[first.delivery_id]["displayed"])
            self.assertTrue(runner._outer_questions[second.delivery_id]["displayed"])
            with self.assertRaisesRegex(TeamConfigurationError, "multiple unanswered"):
                runner.receive_outer({"action": "user", "text": "未知"})

    def test_mixed_valid_and_contradictory_display_batch_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            first = runner.transport.send("modeling", "coordinator", "first atomic", expects_reply=True)
            second = runner.transport.send("modeling", "coordinator", "second atomic", expects_reply=True)
            output = runner.drain()
            second_envelope = next(item for item in output if item.get("delivery_id") == second.delivery_id)
            second_envelope["sender_id"] = "forged-modeling"
            with self.assertRaisesRegex(TeamConfigurationError, "display envelope"):
                runner.observe_foreground_output(output)
            self.assertFalse(runner._outer_questions[first.delivery_id]["displayed"])
            self.assertFalse(runner._outer_questions[second.delivery_id]["displayed"])
            self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())

    def test_receive_outer_emit_failure_does_not_bind_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate receive failure", expects_reply=True
            )
            original_drain = runner.drain
            drain_calls = 0

            def delayed_drain() -> list[dict[str, object]]:
                nonlocal drain_calls
                drain_calls += 1
                if drain_calls == 1:
                    return []
                return original_drain()

            runner.drain = delayed_drain  # type: ignore[method-assign]
            receive_calls = 0
            original_receive = runner.receive_outer

            def count_receive(message: dict[str, object]) -> list[dict[str, object]]:
                nonlocal receive_calls
                receive_calls += 1
                return original_receive(message)

            runner.receive_outer = count_receive  # type: ignore[method-assign]

            def fail_emit(_output: object) -> None:
                raise OSError("receive-outer foreground emit failed")

            stream = StringIO('{"action":"status"}\n')
            with self.assertRaisesRegex(OSError, "receive-outer foreground emit failed"):
                _foreground_event_loop(
                    runner,
                    stream,
                    fail_emit,
                    select_fn=lambda *_args: ([stream], [], []),
                )
            self.assertEqual(receive_calls, 1)
            self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
            self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())

    def test_foreground_evidence_failure_precedes_available_owner_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate evidence ordering", expects_reply=True
            )
            receive_calls = 0

            def forbidden_receive(_message: dict[str, object]) -> list[dict[str, object]]:
                nonlocal receive_calls
                receive_calls += 1
                raise AssertionError("owner input was read before evidence failure")

            runner.receive_outer = forbidden_receive  # type: ignore[method-assign]
            stream = StringIO('{"action":"user","text":"未知"}\n')
            select_calls = 0

            def available(_readers: object, _writers: object, _errors: object, _timeout: float):
                nonlocal select_calls
                select_calls += 1
                return ([stream], [], [])

            original_append = runner._append_evidence

            def fail_outer_question_evidence(name: str, value: dict[str, object]) -> None:
                if name == "outer-question":
                    raise OSError("foreground outer-question evidence failed")
                original_append(name, value)

            with patch.object(runner, "_append_evidence", side_effect=fail_outer_question_evidence):
                with self.assertRaisesRegex(OSError, "foreground outer-question evidence failed"):
                    _foreground_event_loop(runner, stream, lambda _output: None, select_fn=available)
            self.assertEqual(select_calls, 0)
            self.assertEqual(receive_calls, 0)
            self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
            self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())

    def test_receive_outer_output_uses_post_emit_display_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate receive outer", expects_reply=True
            )
            original_drain = runner.drain
            calls = 0

            def delayed_drain() -> list[dict[str, object]]:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return []
                if calls >= 3:
                    # The foreground loop now runs until the terminal-report
                    # gate fires; retire the loop once the post-emit display
                    # hook has been exercised.
                    (runner.run.root / "state.json").write_text(
                        json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                        encoding="utf-8",
                    )
                return original_drain()

            runner.drain = delayed_drain  # type: ignore[method-assign]
            stream = StringIO('{"action":"status"}\n')
            polls = iter([([stream], [], []), ([stream], [], [])])
            emitted: list[list[dict[str, object]]] = []
            _foreground_event_loop(
                runner,
                stream,
                emitted.append,
                select_fn=lambda *_args: next(polls),
            )
            self.assertEqual(emitted[0][0]["delivery_id"], question.delivery_id)
            self.assertTrue(runner._outer_questions[question.delivery_id]["displayed"])

    def test_display_evidence_failure_never_marks_question(self) -> None:
        import modeling_team.runner as runner_module

        for stage in ("open", "write", "fsync"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                runner, _adapter = _formal_runner(Path(directory))
                assert runner.transport is not None
                question = runner.transport.send(
                    "modeling", "coordinator", f"candidate {stage}", expects_reply=True
                )
                output = runner.drain()
                if stage == "open":
                    failure = patch.object(Path, "open", side_effect=OSError("outer evidence open failed"))
                elif stage == "write":
                    class FailingStream:
                        def __enter__(self):
                            return self

                        def __exit__(self, *_args):
                            return False

                        def write(self, _value):
                            raise OSError("outer evidence write failed")

                        def flush(self):
                            return None

                        def fileno(self):
                            return 0

                    failure = patch.object(Path, "open", return_value=FailingStream())
                else:
                    failure = patch.object(runner_module.os, "fsync", side_effect=OSError("outer evidence fsync failed"))
                with failure, self.assertRaisesRegex(OSError, "outer evidence"):
                    runner.observe_foreground_output(output)
                self.assertFalse(runner._outer_questions[question.delivery_id]["displayed"])
                with self.assertRaisesRegex(TeamConfigurationError, "not been displayed"):
                    runner.receive_outer({"action": "user", "text": "未知"})

    def test_formal_missing_live_binding_fails_before_outer_question_or_owner_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            runner.scope = SimpleNamespace(project_id="")
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate without live binding", expects_reply=True
            )
            with self.assertRaisesRegex(TeamConfigurationError, "outer question project binding is missing"):
                runner.drain()
            self.assertEqual(runner._outer_questions, {})
            self.assertFalse((runner.run.root / "evidence/outer-question.jsonl").exists())
            self.assertFalse((runner.run.root / "evidence/outer-user.jsonl").exists())
            self.assertEqual(runner.run.scope, {"mode": "create"})
            self.assertNotIn(question.delivery_id, runner._owner_answer_consumed)

    def test_schema_v2_nonformal_owner_answer_keeps_run_scope_project_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            runner.run.configuration.task.task_id = "r2-3-002-t"
            runner.run.configuration.profile.profile_id = "r2-3-002-profile"
            runner.run.scope = {"project_id": "legacy-project"}
            runner.scope = SimpleNamespace(project_id="live-project-must-not-be-used")
            runner._record_outer_question(
                {"action": "question", "delivery_id": "legacy-question", "text": "legacy"}
            )
            runner._release_owner_answer("coordinator", "legacy answer", "legacy-question")
            owner = runner._owner_answers[("legacy-question", "legacy answer")]
            self.assertEqual(owner["project_id"], "legacy-project")
            self.assertEqual(runner._outer_questions["legacy-question"]["project_id"], "legacy-project")

    def test_formal_owner_answer_publication_keeps_modeling_terminal_blocked_until_ack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate?", expects_reply=True
            )
            _drain_and_observe(runner)
            runner._release_owner_answer("coordinator", "release", question.delivery_id)
            with self.assertRaisesRegex(RoutingError, "delivered reply"):
                runner.transport.report("modeling", "completed", "too early")
            runner.drain()
            runner.transport.report("modeling", "completed", "answered")

    def test_persistence_failures_consume_question_and_reject_same_or_different_replay(self) -> None:
        import modeling_team.runner as runner_module

        for stage in ("open", "write", "fsync"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                runner, _adapter = _formal_runner(Path(directory))
                assert runner.transport is not None
                question = runner.transport.send(
                    "modeling", "coordinator", "candidate?", expects_reply=True
                )
                _drain_and_observe(runner)

                if stage == "open":
                    failure = patch.object(runner_module.os, "open", side_effect=OSError("open failed"))
                elif stage == "write":
                    failure = patch.object(runner_module.os, "write", side_effect=OSError("write failed"))
                else:
                    original_fsync = runner_module.os.fsync
                    calls = 0

                    def fail_first_fsync(fd):
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            raise OSError("fsync failed")
                        return original_fsync(fd)

                    failure = patch.object(runner_module.os, "fsync", side_effect=fail_first_fsync)
                with failure:
                    with self.assertRaises(OSError):
                        runner._release_owner_answer("coordinator", "answer", question.delivery_id)
                with self.assertRaisesRegex(TeamConfigurationError, "previously failed"):
                    runner._release_owner_answer("coordinator", "answer", question.delivery_id)
                with self.assertRaisesRegex(TeamConfigurationError, "already consumed"):
                    runner._release_owner_answer("coordinator", "different", question.delivery_id)
                self.assertEqual(runner.transport.drain(), [])

    def test_adapter_and_broker_publication_failures_consume_question_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate?", expects_reply=True
            )
            _drain_and_observe(runner)
            adapter.fail_owner = True
            runner._release_owner_answer("coordinator", "adapter answer", question.delivery_id)
            with self.assertRaisesRegex(RuntimeError, "adapter delivery failed"):
                runner.drain()
            with self.assertRaisesRegex(TeamConfigurationError, "already consumed"):
                runner._release_owner_answer("coordinator", "different", question.delivery_id)

        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate?", expects_reply=True
            )
            _drain_and_observe(runner)
            with patch.object(
                runner.transport,
                "publish_owner_answer",
                side_effect=RoutingError("publish failed"),
            ):
                with self.assertRaisesRegex(RoutingError, "publish failed"):
                    runner._release_owner_answer("coordinator", "broker answer", question.delivery_id)
            with self.assertRaisesRegex(TeamConfigurationError, "already consumed"):
                runner._release_owner_answer("coordinator", "different", question.delivery_id)
            self.assertEqual(runner.transport.drain(), [])

    def test_formal_owner_envelope_allows_question_id_and_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            with self.assertRaisesRegex(TeamConfigurationError, "invalid fields"):
                runner.receive_outer(
                    {"action": "user", "text": "answer", "unexpected": "x"}
                )
            with self.assertRaisesRegex(TeamConfigurationError, "unknown outer Runner action"):
                runner.receive_outer({"action": "unexpected", "text": "answer"})

            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate with explicit ID", expects_reply=True
            )
            _drain_and_observe(runner)
            output = runner.receive_outer(
                {
                    "action": "user",
                    "text": "answer bound by ID",
                    "question_delivery_id": question.delivery_id,
                }
            )
            self.assertEqual(output[0]["reply_to_delivery_id"], question.delivery_id)
            self.assertEqual(
                runner._owner_answers[(question.delivery_id, "answer bound by ID")][
                    "question_delivery_id"
                ],
                question.delivery_id,
            )

    def test_only_active_modeling_questions_can_be_observed_and_displayed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, adapter = _formal_runner(Path(directory))
            invalid_deliveries = (
                SimpleNamespace(
                    sender_id="protocol",
                    recipient_id="coordinator",
                    text="protocol candidate",
                    delivery_id="protocol-1",
                    expects_reply=True,
                    reply_to_delivery_id=None,
                ),
                SimpleNamespace(
                    sender_id="modeling",
                    recipient_id="protocol",
                    text="wrong recipient",
                    delivery_id="wrong-1",
                    expects_reply=True,
                    reply_to_delivery_id=None,
                ),
                SimpleNamespace(
                    sender_id="modeling",
                    recipient_id="coordinator",
                    text="no reply expected",
                    delivery_id="not-question-1",
                    expects_reply=False,
                    reply_to_delivery_id=None,
                ),
                SimpleNamespace(
                    sender_id="modeling",
                    recipient_id="coordinator",
                    text="revision receipt",
                    delivery_id="reply-1",
                    expects_reply=True,
                    reply_to_delivery_id="revision-1",
                ),
            )
            for delivery in invalid_deliveries:
                runner._observe_modeling_question(delivery)
            self.assertEqual(runner._outer_questions, {})

            adapter.emit_prompt = False
            question = runner.transport.send(
                "modeling", "coordinator", "candidate hidden", expects_reply=True
            )
            runner.drain()
            with self.assertRaisesRegex(TeamConfigurationError, "not been displayed"):
                runner.receive_outer({"action": "user", "text": "answer"})
            self.assertNotIn(question.delivery_id, runner._owner_answer_consumed)

    def test_coordinator_prose_never_binds_formal_display(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            adapter.emit_prompt = False
            first = runner.transport.send(
                "modeling", "coordinator", "candidate one", expects_reply=True
            )
            runner.drain()
            with self.assertRaisesRegex(TeamConfigurationError, "not been displayed"):
                runner.receive_outer({"action": "user", "text": "answer"})
            runner._observe_coordinator_message(RuntimeMessage("coordinator", "unrelated prompt"))
            self.assertFalse(runner._outer_questions[first.delivery_id]["displayed"])

            second = runner.transport.send(
                "modeling", "coordinator", "candidate two", expects_reply=True
            )
            runner.drain()
            runner._observe_coordinator_message(
                RuntimeMessage("coordinator", "candidate one and candidate two")
            )
            self.assertFalse(runner._outer_questions[first.delivery_id]["displayed"])
            self.assertFalse(runner._outer_questions[second.delivery_id]["displayed"])

    def test_codex_owner_answer_payload_adds_only_owner_fields(self) -> None:
        owner = RuntimeDelivery(
            "user/outer",
            "modeling",
            "owner-answer",
            "release",
            delivery_id="release-1",
            reply_to_delivery_id="question-1",
            owner_answer_id="owner-1",
            release_id="release-1",
        )
        payload = json.loads(CodexRuntimeAdapter._delivery_input(owner)[0]["text"])
        self.assertEqual(
            payload,
            {
                "sender_id": "user/outer",
                "recipient_id": "modeling",
                "kind": "owner-answer",
                "text": "release",
                "delivery_id": "release-1",
                "expects_reply": False,
                "reply_to_delivery_id": "question-1",
                "owner_answer_id": "owner-1",
                "release_id": "release-1",
            },
        )

    def test_broker_owner_answer_enforces_direction_ack_and_id_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "broker",
                {("modeling", "coordinator"), ("coordinator", "modeling")},
                modeling_agent_id="modeling",
                coordinator_agent_id="coordinator",
            )
            question = broker.send("modeling", "coordinator", "candidate", expects_reply=True)
            broker.drain()
            broker.ack_delivery(question.delivery_id)
            owner = broker.publish_owner_answer(
                question_delivery_id=question.delivery_id,
                owner_answer_id="owner-1",
                release_id="release-1",
                text="answer",
            )
            self.assertEqual((owner.recipient_id, owner.owner_answer_id, owner.release_id), ("modeling", "owner-1", "release-1"))
            with self.assertRaisesRegex(RoutingError, "active acknowledged"):
                broker.publish_owner_answer(
                    question_delivery_id=question.delivery_id,
                    owner_answer_id="owner-2",
                    release_id="release-2",
                    text="replay",
                )

            question2 = broker.send("modeling", "coordinator", "candidate 2", expects_reply=True)
            broker.drain()
            broker.ack_delivery(question2.delivery_id)
            with self.assertRaisesRegex(RoutingError, "collision"):
                broker.publish_owner_answer(
                    question_delivery_id=question2.delivery_id,
                    owner_answer_id="owner-1",
                    release_id="release-2",
                    text="collision",
                )
            self.assertNotIn(question2.delivery_id, broker._owner_answer_by_question)
            self.assertNotIn("release-2", broker._owner_answer_by_release)

            wrong_direction = broker.send(
                "coordinator", "modeling", "wrong", expects_reply=True
            )
            broker.drain()
            broker.ack_delivery(wrong_direction.delivery_id)
            with self.assertRaisesRegex(RoutingError, "active acknowledged"):
                broker.publish_owner_answer(
                    question_delivery_id=wrong_direction.delivery_id,
                    owner_answer_id="owner-3",
                    release_id="release-3",
                    text="wrong",
                )

            no_reply = broker.send("modeling", "coordinator", "not a question")
            broker.drain()
            broker.ack_delivery(no_reply.delivery_id)
            with self.assertRaisesRegex(RoutingError, "active acknowledged"):
                broker.publish_owner_answer(
                    question_delivery_id=no_reply.delivery_id,
                    owner_answer_id="owner-4",
                    release_id="release-4",
                    text="wrong",
                )


class _FakeOuterInput:
    """FIFO double for foreground-loop admission tests (see test_runner.py)."""

    def __init__(self, lines=None) -> None:
        self.lines: list[str] = list(lines or [])
        self.read_ready_calls = 0
        self.pop_calls = 0

    def fileno(self) -> int:
        return 4242

    def read_ready(self) -> None:
        self.read_ready_calls += 1

    def pop_line(self):
        self.pop_calls += 1
        if self.lines:
            return self.lines.pop(0)
        return None


class RunnerR23005FifoOuterInputTests(unittest.TestCase):
    def test_foreground_loop_rejects_early_issue_resolution_via_fifo_then_retries(self) -> None:
        # The FIFO line routes through the same cooperative issue gate as
        # stdin: a premature resolution is rejected, and a later one admitted
        # once the Coordinator pause lands the ledger in waiting_owner.
        class Ledger:
            state = "reported"

        class Runner:
            def __init__(self, root) -> None:
                self.transport = SimpleNamespace(issue_ledger=Ledger())
                self.drains = 0
                self.received: list[dict[str, object]] = []
                self.run = SimpleNamespace(root=root)

            def drain(self):
                self.drains += 1
                if self.drains == 2:
                    self.transport.issue_ledger.state = "waiting_owner"
                if self.drains >= 3:
                    (self.run.root / "state.json").write_text(
                        json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                        encoding="utf-8",
                    )
                return []

            def receive_outer(self, message):
                assert self.transport.issue_ledger.state == "waiting_owner"
                self.received.append(message)
                return [{"type": "resolution-accepted"}]

        resolution = {
            "action": "issue_resolution",
            "issue_id": "issue-1",
            "reporter_id": "modeling",
            "control_epoch": 1,
            "resolution_type": "guidance",
            "resolution_text": "Use the already retained protocol receipt.",
        }
        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(Path(directory))
            fifo = _FakeOuterInput(
                [json.dumps(resolution), json.dumps(resolution)]
            )
            emitted: list[list[dict[str, object]]] = []
            polls = iter([([fifo], [], []), ([fifo], [], [])])
            _foreground_event_loop(
                runner,
                StringIO(""),
                emitted.append,
                outer_input=fifo,
                select_fn=lambda *_args: next(polls),
            )
        self.assertEqual(
            emitted,
            [
                [{"type": "outer-input-rejected", "code": "invalid_outer_input", "retryable": True}],
                [{"type": "resolution-accepted"}],
            ],
        )
        self.assertEqual(runner.received, [resolution])

    def test_formal_owner_answer_via_fifo_requires_displayed_question(self) -> None:
        # An owner answer through the FIFO follows the identical emit-then-
        # observe-then-receive_outer contract as stdin: the displayed question
        # is bound first, then the FIFO owner answer releases to modeling.
        with tempfile.TemporaryDirectory() as directory:
            runner, adapter = _formal_runner(Path(directory))
            assert runner.transport is not None
            question = runner.transport.send(
                "modeling", "coordinator", "candidate via fifo", expects_reply=True
            )
            fifo = _FakeOuterInput(['{"action":"user","text":"captured"}'])
            emitted: list[list[dict[str, object]]] = []
            _original_receive_outer = runner.receive_outer

            def _terminating_receive_outer(message):
                output = _original_receive_outer(message)
                (runner.run.root / "state.json").write_text(
                    json.dumps({"state": "TERMINAL_REPORT_COMPLETE"}),
                    encoding="utf-8",
                )
                return output

            runner.receive_outer = _terminating_receive_outer  # type: ignore[method-assign]
            try:
                polls = iter([([fifo], [], []), ([fifo], [], [])])
                _foreground_event_loop(
                    runner,
                    StringIO(""),
                    emitted.append,
                    outer_input=fifo,
                    select_fn=lambda *_args: next(polls),
                )
            finally:
                runner.receive_outer = _original_receive_outer  # type: ignore[method-assign]

        self.assertEqual(emitted[0][0]["delivery_id"], question.delivery_id)
        self.assertTrue(runner._outer_questions[question.delivery_id]["displayed"])
        owner = emitted[1][0]
        self.assertEqual(owner["recipient_id"], "modeling")
        self.assertEqual(owner["reply_to_delivery_id"], question.delivery_id)
        self.assertTrue(owner["owner_answer_id"].startswith("owner-answer-"))
        self.assertEqual(adapter.sent[1][1].kind, "owner-answer")

    def test_formal_owner_answer_via_fifo_without_displayed_question_is_fatal(self) -> None:
        # With no displayed question, the FIFO owner answer hits the same
        # strict receive_outer boundary as stdin: the fatal
        # TeamConfigurationError propagates and tears the run down rather than
        # being swallowed into outer-input-rejected.
        with tempfile.TemporaryDirectory() as directory:
            runner, _adapter = _formal_runner(Path(directory))
            fifo = _FakeOuterInput(['{"action":"user","text":"no question"}'])
            with self.assertRaisesRegex(TeamConfigurationError, "no unanswered"):
                _foreground_event_loop(
                    runner,
                    StringIO(""),
                    lambda _output: None,
                    outer_input=fifo,
                    select_fn=lambda *_args: ([fifo], [], []),
                )


if __name__ == "__main__":
    unittest.main()
