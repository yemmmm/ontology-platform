from __future__ import annotations

import json
import shutil
import signal
import sys
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modeling_team.contracts import repository_root
from modeling_team.foreground_monitor import extract_adverse_order, load_contract, run_foreground
from modeling_team.runner import TeamRunner


class ForegroundMonitorTests(unittest.TestCase):
    @staticmethod
    def _write_jsonl(path: Path, values: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
            encoding="utf-8",
        )

    def _adverse_fixture(self, root: Path) -> None:
        (root / "runtime" / "protocol" / "home").mkdir(parents=True, exist_ok=True)
        evidence = root / "evidence"
        self._write_jsonl(
            evidence / "team-transport-events.jsonl",
            [
                {
                    "agent": "protocol",
                    "tool": "report_task_result",
                    "status": "rejected",
                    "category": "missing_modeling_handoff",
                    "ack": "not_applicable",
                    "recorded_at_ns": 10,
                },
                {
                    "agent": "protocol",
                    "tool": "report_task_result",
                    "status": "accepted",
                    "category": "terminal_report_accepted",
                    "ack": "not_applicable",
                    "recorded_at_ns": 40,
                },
            ],
        )
        self._write_jsonl(
            evidence / "terminal-result-handoff.jsonl",
            [
                {
                    "source_id": "modeling",
                    "recipient_id": "protocol",
                    "handoff_id": "terminal-handoff-1",
                    "sequence": 1,
                    "recorded_at_ns": 20,
                }
            ],
        )
        self._write_jsonl(
            evidence / "terminal-handoff-ack.jsonl",
            [
                {
                    "agent": "protocol",
                    "tool": "ack_terminal_handoff",
                    "status": "accepted",
                    "source_id": "modeling",
                    "ack": True,
                    "handoff_id": "terminal-handoff-1",
                    "sequence": 2,
                    "recorded_at_ns": 30,
                }
            ],
        )
        self._write_jsonl(
            evidence / "settled.jsonl",
            [
                {
                    "recorded_at_ns": 50,
                    "results": {
                        role: {"status": "completed", "summary": "private"}
                        for role in ("coordinator", "modeling", "protocol")
                    },
                }
            ],
        )

    def test_descriptor_is_exact_and_lifecycle_is_append_only(self) -> None:
        root = repository_root()
        descriptor = root / "modeling_team/references/p2-monitor-contract.json"
        contract = load_contract(descriptor)
        self.assertEqual(contract["schema_version"], "p2-monitor-contract/v1")
        self.assertEqual(contract["parent_pm_boundary_count"], 1)
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            secrets = run_root / "secrets"
            secrets.mkdir()
            (secrets / "auth.json").write_text("secret", encoding="utf-8")
            evidence = run_root / "evidence" / "monitor.jsonl"
            result = run_foreground(
                descriptor,
                command=[sys.executable, "-c", "pass"],
                run_root=run_root,
                evidence_path=evidence,
            )
            self.assertEqual(result, 0)
            events = [json.loads(line) for line in evidence.read_text().splitlines()]
            self.assertEqual(
                [event["stage"] for event in events],
                contract["required_stages"],
            )
            self.assertFalse((secrets / "auth.json").exists())

    def test_adverse_order_extractor_writes_only_safe_order_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adverse_fixture(root)
            records = extract_adverse_order(root)
            self.assertEqual(records[0]["category"], "missing_modeling_handoff")
            self.assertEqual(records[-1]["category"], "all_three_settled")
            self.assertEqual([record["order"] for record in records], list(range(1, len(records) + 1)))
            for record in records:
                self.assertEqual(
                    set(record), {"stage", "agent", "tool", "status", "order", "category", "ack"}
                )
                self.assertNotIn("private", json.dumps(record))

    def test_adverse_order_extractor_fails_without_real_handoff_or_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adverse_fixture(root)
            (root / "evidence" / "terminal-result-handoff.jsonl").unlink()
            with self.assertRaisesRegex(ValueError, "handoff"):
                extract_adverse_order(root)
            output = root / "evidence" / "p2-adverse-order.jsonl"
            self.assertFalse(output.exists())
            self._adverse_fixture(root)
            import shutil

            shutil.rmtree(root / "runtime")
            with self.assertRaisesRegex(ValueError, "live private runtime"):
                extract_adverse_order(root)
            self.assertFalse(output.exists())

    def test_runner_transport_sink_is_consumable_by_current_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime" / "protocol" / "home").mkdir(parents=True)
            evidence = root / "evidence"
            runner = object.__new__(TeamRunner)
            runner.run = SimpleNamespace(root=root)
            runner._append_team_transport_event(
                {
                    "agent": "protocol",
                    "tool": "report_task_result",
                    "status": "rejected",
                    "category": "missing_modeling_handoff",
                    "ack": "not_applicable",
                    "recorded_at_ns": 10,
                }
            )
            runner._append_team_transport_event(
                {
                    "agent": "protocol",
                    "tool": "report_task_result",
                    "status": "accepted",
                    "category": "terminal_report_accepted",
                    "ack": "not_applicable",
                    "recorded_at_ns": 40,
                }
            )
            self._write_jsonl(
                evidence / "terminal-result-handoff.jsonl",
                [
                    {
                        "source_id": "modeling",
                        "recipient_id": "protocol",
                        "handoff_id": "terminal-handoff-1",
                        "sequence": 1,
                    }
                ],
            )
            self._write_jsonl(
                evidence / "terminal-handoff-ack.jsonl",
                [
                    {
                        "agent": "protocol",
                        "tool": "ack_terminal_handoff",
                        "status": "accepted",
                        "source_id": "modeling",
                        "ack": True,
                        "handoff_id": "terminal-handoff-1",
                        "sequence": 2,
                    }
                ],
            )
            self._write_jsonl(
                evidence / "settled.jsonl",
                [
                    {
                        "results": {
                            role: {"status": "completed"}
                            for role in ("coordinator", "modeling", "protocol")
                        }
                    }
                ],
            )
            records = extract_adverse_order(root)
            self.assertEqual(records[0]["category"], "missing_modeling_handoff")
            self.assertEqual(records[3]["category"], "terminal_report_accepted")

    def test_adverse_monitor_defers_target_evidence_and_extracts_before_cleanup(self) -> None:
        descriptor = repository_root() / "modeling_team/references/p2-monitor-contract.json"
        with tempfile.TemporaryDirectory() as directory:
            fake_repo = Path(directory)
            (fake_repo / "workspaces" / "modeling-runs").mkdir(parents=True)
            (fake_repo / "modeling_team" / "references").mkdir(parents=True)
            shutil.copyfile(
                repository_root() / "modeling_team/references/p2-monitor-handoff-contract.json",
                fake_repo / "modeling_team/references/p2-monitor-handoff-contract.json",
            )
            run_id = "r23002-monitor-handoff-fixture"
            run_root = fake_repo / "workspaces" / "modeling-runs" / run_id
            evidence = run_root / "evidence" / "p2-monitor.jsonl"
            child = textwrap.dedent(
                """
                import json, os, shutil, time
                from pathlib import Path
                from modeling_team.monitor_handoff import HANDOFF_ENV, read_phase, write_runner_phase
                handoff = Path(os.environ[HANDOFF_ENV])
                metadata = json.loads((handoff / "metadata.json").read_text())
                root = Path(metadata["expected_run_root"])
                root.mkdir(mode=0o700)
                (root / "evidence").mkdir(mode=0o700)
                (root / "runtime").mkdir(mode=0o700)
                evidence = root / "evidence"
                def write(name, values):
                    (evidence / name).write_text("".join(json.dumps(value, sort_keys=True) + "\\n" for value in values))
                write("team-transport-events.jsonl", [
                    {"agent":"protocol","tool":"report_task_result","status":"rejected","category":"missing_modeling_handoff","ack":"not_applicable","recorded_at_ns":10},
                    {"agent":"protocol","tool":"report_task_result","status":"accepted","category":"terminal_report_accepted","ack":"not_applicable","recorded_at_ns":40},
                ])
                write("terminal-result-handoff.jsonl", [{"source_id":"modeling","recipient_id":"protocol","handoff_id":"terminal-handoff-1","sequence":1}])
                write("terminal-handoff-ack.jsonl", [{"agent":"protocol","tool":"ack_terminal_handoff","status":"accepted","source_id":"modeling","ack":True,"handoff_id":"terminal-handoff-1","sequence":2}])
                write("settled.jsonl", [{"results": {role: {"status":"completed"} for role in ("coordinator","modeling","protocol")}}])
                write_runner_phase(handoff, "prepared", run_root=root)
                write_runner_phase(handoff, "cleanup_pending", run_root=root)
                deadline = time.monotonic() + 10
                while read_phase(handoff, "foreground_monitor", "extraction_complete") is None:
                    if read_phase(handoff, "foreground_monitor", "extraction_failed") is not None:
                        raise RuntimeError("monitor rejected fixture")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("monitor did not acknowledge fixture")
                    time.sleep(0.02)
                shutil.rmtree(root / "runtime")
                """
            )
            environment = {"PYTHONPATH": str(repository_root())}
            with patch("modeling_team.foreground_monitor.repository_root", return_value=fake_repo):
                result = run_foreground(
                    descriptor,
                    command=[sys.executable, "-c", child],
                    run_root=run_root,
                    evidence_path=evidence,
                    env=environment,
                    extract_order=True,
                )
            self.assertEqual(result, 0)
            self.assertTrue(evidence.is_file())
            stages = [json.loads(line)["stage"] for line in evidence.read_text().splitlines()]
            self.assertEqual(stages, load_contract(descriptor)["required_stages"])
            self.assertTrue((run_root / "evidence" / "p2-adverse-order.jsonl").is_file())
            self.assertFalse((run_root / "runtime").exists())

    def test_adverse_monitor_rejects_preexisting_target_without_starting_child(self) -> None:
        descriptor = repository_root() / "modeling_team/references/p2-monitor-contract.json"
        with tempfile.TemporaryDirectory() as directory:
            fake_repo = Path(directory)
            (fake_repo / "workspaces" / "modeling-runs").mkdir(parents=True)
            run_root = fake_repo / "workspaces" / "modeling-runs" / "r23002-monitor-existing"
            run_root.mkdir(mode=0o700)
            with patch("modeling_team.foreground_monitor.repository_root", return_value=fake_repo):
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    run_foreground(
                        descriptor,
                        command=[sys.executable, "-c", "raise SystemExit(99)"],
                        run_root=run_root,
                        extract_order=True,
                    )

    def test_adverse_monitor_uses_foreground_deadline_not_short_handshake(self) -> None:
        descriptor = repository_root() / "modeling_team/references/p2-monitor-contract.json"

        class FakeClock:
            def __init__(self) -> None:
                self.now = 0.0

            def monotonic(self) -> float:
                return self.now

            def sleep(self, seconds: float) -> None:
                self.now += seconds * 20.0

        def execute(cleanup_after: float) -> dict[str, object]:
            outcome: dict[str, object] = {}
            with tempfile.TemporaryDirectory() as directory:
                fake_repo = Path(directory)
                (fake_repo / "workspaces" / "modeling-runs").mkdir(parents=True)
                (fake_repo / "modeling_team" / "references").mkdir(parents=True)
                shutil.copyfile(
                    repository_root() / "modeling_team/references/p2-monitor-handoff-contract.json",
                    fake_repo / "modeling_team/references/p2-monitor-handoff-contract.json",
                )
                run_root = fake_repo / "workspaces" / "modeling-runs" / "r23002-monitor-clock"
                evidence = run_root / "evidence" / "p2-monitor.jsonl"
                clock = FakeClock()

                class FakeProcess:
                    pid = 2**30

                    def __init__(self, env: dict[str, str]) -> None:
                        from modeling_team.monitor_handoff import (
                            HANDOFF_ENV,
                            read_phase,
                            write_runner_phase,
                        )

                        self.handoff = Path(env[HANDOFF_ENV])
                        self.returncode: int | None = None
                        self.prepared = False
                        self.cleanup_written = False
                        self.signals: list[int] = []
                        self._read_phase = read_phase
                        self._write_runner_phase = write_runner_phase
                        self.root = Path(
                            json.loads((self.handoff / "metadata.json").read_text())["expected_run_root"]
                        )

                    def _prepare(self) -> None:
                        self.root.mkdir(mode=0o700)
                        self._test_case._adverse_fixture(self.root)
                        self._write_runner_phase(self.handoff, "prepared", run_root=self.root)
                        self.prepared = True

                    def poll(self) -> int | None:
                        if self.returncode is not None:
                            return self.returncode
                        if not self.prepared:
                            self._prepare()
                        elif not self.cleanup_written and clock.now >= cleanup_after:
                            self._write_runner_phase(self.handoff, "cleanup_pending", run_root=self.root)
                            self.cleanup_written = True
                        elif self._read_phase(self.handoff, "foreground_monitor", "extraction_complete"):
                            shutil.rmtree(self.root / "runtime", ignore_errors=True)
                            self.returncode = 0
                        return self.returncode

                    def wait(self, timeout: float | None = None) -> int:
                        if self.returncode is not None:
                            return self.returncode
                        if timeout is not None:
                            raise subprocess.TimeoutExpired("fake-foreground", timeout)
                        raise AssertionError("fake process must be settled before an unbounded wait")

                    def send_signal(self, value: int) -> None:
                        self.signals.append(value)
                        shutil.rmtree(self.root / "runtime", ignore_errors=True)
                        self.returncode = 130

                    def terminate(self) -> None:
                        self.send_signal(signal.SIGTERM)

                    def kill(self) -> None:
                        self.send_signal(signal.SIGKILL)

                FakeProcess._test_case = self
                process_holder: dict[str, FakeProcess] = {}

                def fake_popen(_command, *, env, **_kwargs):
                    process = FakeProcess(env)
                    process_holder["process"] = process
                    return process

                with (
                    patch("modeling_team.foreground_monitor.repository_root", return_value=fake_repo),
                    patch("modeling_team.foreground_monitor.subprocess.Popen", side_effect=fake_popen),
                    patch("modeling_team.foreground_monitor._monotonic", side_effect=clock.monotonic),
                    patch("modeling_team.foreground_monitor._sleep", side_effect=clock.sleep),
                ):
                    try:
                        outcome["result"] = run_foreground(
                            descriptor,
                            command=["fake-foreground"],
                            run_root=run_root,
                            evidence_path=evidence,
                            env={"PYTHONPATH": str(repository_root())},
                            extract_order=True,
                        )
                    except BaseException as exc:  # noqa: BLE001 - preserve timeout type for assertion
                        outcome["error"] = exc
                outcome["clock"] = clock.now
                outcome["runtime_exists"] = (run_root / "runtime").exists()
                outcome["process"] = process_holder["process"]
                outcome["adverse_exists"] = (run_root / "evidence" / "p2-adverse-order.jsonl").exists()
            return outcome

        completed = execute(31.0)
        self.assertEqual(completed.get("result"), 0)
        self.assertGreater(completed["clock"], 30.0)
        self.assertLess(completed["clock"], 120.0)
        self.assertFalse(completed["runtime_exists"])
        self.assertTrue(completed["adverse_exists"])

        timed_out = execute(121.0)
        self.assertIsInstance(timed_out.get("error"), TimeoutError)
        self.assertFalse(timed_out["runtime_exists"])
        self.assertFalse(timed_out["adverse_exists"])
        self.assertTrue(timed_out["process"].signals)
