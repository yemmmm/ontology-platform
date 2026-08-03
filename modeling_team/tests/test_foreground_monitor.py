from __future__ import annotations

import json
import sys
import tempfile
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
            with self.assertRaisesRegex(ValueError, "archival-only"):
                run_foreground(
                    descriptor,
                    command=[sys.executable, "-c", "pass"],
                    run_root=run_root,
                    evidence_path=evidence,
                )
            self.assertFalse(evidence.exists())
            self.assertTrue((secrets / "auth.json").exists())

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
            run_root = Path(directory) / "workspaces" / "modeling-runs" / "archival-monitor"
            evidence = run_root / "evidence" / "p2-monitor.jsonl"
            with patch("modeling_team.foreground_monitor.subprocess.Popen") as popen:
                with self.assertRaisesRegex(ValueError, "archival-only"):
                    run_foreground(
                        descriptor,
                        command=[sys.executable, "-c", "pass"],
                        run_root=run_root,
                        evidence_path=evidence,
                        extract_order=True,
                    )
            popen.assert_not_called()
            self.assertFalse(run_root.exists())
            self.assertFalse(evidence.exists())

    def test_adverse_monitor_rejects_preexisting_target_without_starting_child(self) -> None:
        descriptor = repository_root() / "modeling_team/references/p2-monitor-contract.json"
        with tempfile.TemporaryDirectory() as directory:
            fake_repo = Path(directory)
            (fake_repo / "workspaces" / "modeling-runs").mkdir(parents=True)
            run_root = fake_repo / "workspaces" / "modeling-runs" / "r23002-monitor-existing"
            run_root.mkdir(mode=0o700)
            with patch("modeling_team.foreground_monitor.repository_root", return_value=fake_repo):
                with self.assertRaisesRegex(ValueError, "archival-only"):
                    run_foreground(
                        descriptor,
                        command=[sys.executable, "-c", "raise SystemExit(99)"],
                        run_root=run_root,
                        extract_order=True,
                    )

    def test_adverse_monitor_uses_foreground_deadline_not_short_handshake(self) -> None:
        descriptor = repository_root() / "modeling_team/references/p2-monitor-contract.json"
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "workspaces" / "modeling-runs" / "archival-monitor"
            evidence = run_root / "evidence" / "p2-monitor.jsonl"
            with patch("modeling_team.foreground_monitor.subprocess.Popen") as popen:
                with self.assertRaisesRegex(ValueError, "archival-only"):
                    run_foreground(
                        descriptor,
                        command=["fake-foreground"],
                        run_root=run_root,
                        evidence_path=evidence,
                        extract_order=True,
                    )
            popen.assert_not_called()
            self.assertFalse(run_root.exists())
            self.assertFalse(evidence.exists())
