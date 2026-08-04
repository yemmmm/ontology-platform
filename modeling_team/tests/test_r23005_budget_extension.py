from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from modeling_team import __main__ as team_main
from modeling_team.contracts import TeamConfigurationError
from modeling_team.start_ledger import (
    StartLedger,
    resolve_ledger_config,
)


class R23005BudgetExtensionTests(unittest.TestCase):
    now = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)

    def _ledger(self, root: Path, requirement_id: str = "R2.3-005") -> StartLedger:
        return StartLedger(root, now=lambda: self.now, requirement_id=requirement_id)

    def _begin(self, ledger: StartLedger, run_id: str, baseline: str) -> None:
        ledger.reserve(run_id, baseline, self.now.isoformat())
        ledger.mark_semantic_start(run_id)

    def _first_failure(self, ledger: StartLedger, run_id: str = "run-one") -> None:
        self._begin(ledger, run_id, "baseline-one")
        ledger.terminal_failure(run_id, "collaboration/routing", False)

    def _authorized_first_repair(self, ledger: StartLedger) -> None:
        self._first_failure(ledger)
        ledger.authorize_budget(3, "authorization-one", "user-reference-one")
        ledger.authorize_repair("run-one", "repair-one", "baseline-two")

    def _retained_like_10_8_0_prefix(self, ledger: StartLedger) -> None:
        """Build a temporary formal ledger matching the retained 10/8/0 shape."""
        self._begin(ledger, "run-1", "baseline-1")
        ledger.terminal_failure("run-1", "collaboration/routing", False)
        ledger.authorize_budget(3, "authorization-1", "reference-1")
        ledger.authorize_repair("run-1", "repair-2", "baseline-2")

        for index, baseline, next_baseline in (
            (2, "baseline-2", "baseline-3"),
            (3, "baseline-3", "baseline-4"),
        ):
            run_id = f"run-{index}"
            self._begin(ledger, run_id, baseline)
            ledger.terminal_failure(run_id, "collaboration/routing", False)
            ledger.authorize_repair(run_id, f"repair-{index + 1}", next_baseline)

        self._begin(ledger, "run-4", "baseline-4")
        ledger.terminal_failure("run-4", "collaboration/routing", False)
        ledger.authorize_budget(3, "authorization-2", "reference-2")
        ledger.authorize_repair("run-4", "repair-5", "baseline-5")

        for index, baseline, next_baseline in (
            (5, "baseline-5", "baseline-6"),
            (6, "baseline-6", "baseline-7"),
        ):
            run_id = f"run-{index}"
            self._begin(ledger, run_id, baseline)
            ledger.terminal_failure(run_id, "collaboration/routing", False)
            ledger.authorize_repair(run_id, f"repair-{index + 1}", next_baseline)

        self._begin(ledger, "run-7", "baseline-7")
        ledger.terminal_failure("run-7", "collaboration/routing", False)
        ledger.authorize_budget(3, "authorization-3", "reference-3")
        ledger.authorize_repair("run-7", "repair-8", "baseline-8")

        self._begin(ledger, "run-8", "baseline-8")
        ledger.terminal_failure("run-8", "modeling-quality", False)
        self.assertEqual(ledger._start_cap(ledger._records()), 10)
        self.assertEqual(ledger._semantic_start_count(ledger._records()), 8)
        self.assertEqual(
            {
                record.get("run_id")
                for record in ledger._records()
                if record.get("event") == "reservation"
            }
            - {
                record.get("run_id")
                for record in ledger._records()
                if record.get("event") in {"semantic_start", "presemantic_release"}
            },
            set(),
        )

    def test_c61_resolver_has_only_two_fixed_policies_and_rejects_drift_before_access(self) -> None:
        legacy = resolve_ledger_config()
        formal = resolve_ledger_config("R2.3-005")
        self.assertEqual((legacy.initial_start_cap, legacy.authorization_increment), (2, 2))
        self.assertEqual((formal.initial_start_cap, formal.authorization_increment), (1, 3))
        self.assertFalse(legacy.allow_incomplete_modeling_quality_repair)
        self.assertTrue(formal.allow_incomplete_modeling_quality_repair)
        self.assertEqual(legacy.ledger_filename, ".r2-3-002-start-ledger.jsonl")
        self.assertEqual(formal.ledger_filename, ".r2-3-005-start-ledger.jsonl")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kwargs in (
                {"requirement_id": "R2.3-999"},
                {"requirement_id": "R2.3-005", "ledger_filename": legacy.ledger_filename},
                {"requirement_id": "R2.3-005", "initial_start_cap": 2},
                {"requirement_id": "R2.3-005", "authorization_increment": 2},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(TeamConfigurationError):
                    StartLedger(root, **kwargs)
                self.assertEqual(list(root.iterdir()), [])

    def test_c62_exact_plus_three_replays_cap_four_with_three_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._first_failure(ledger)
            before = ledger.path.read_bytes()
            ledger.authorize_budget(3, "authorization-one", "user-reference-one")
            self.assertEqual(ledger._start_cap(ledger._records()), 4)
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 1)
            self.assertEqual(before != ledger.path.read_bytes(), True)
            ledger.authorize_repair("run-one", "repair-one", "baseline-two")
            ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 1)

    def test_c63_malformed_or_forged_budget_is_byte_stable(self) -> None:
        malformed = (1, 2, 4, True, "3")
        for additional_starts in malformed:
            with self.subTest(additional_starts=additional_starts), tempfile.TemporaryDirectory() as directory:
                ledger = self._ledger(Path(directory))
                self._first_failure(ledger)
                before = ledger.path.read_bytes()
                with self.assertRaises(TeamConfigurationError):
                    ledger.authorize_budget(additional_starts, "authorization-one", "user-reference-one")
                self.assertEqual(ledger.path.read_bytes(), before)
        for authorization_id, reference in (("", "reference"), ("authorization", "")):
            with self.subTest(authorization_id=authorization_id), tempfile.TemporaryDirectory() as directory:
                ledger = self._ledger(Path(directory))
                self._first_failure(ledger)
                before = ledger.path.read_bytes()
                with self.assertRaises(TeamConfigurationError):
                    ledger.authorize_budget(3, authorization_id, reference)
                self.assertEqual(ledger.path.read_bytes(), before)
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            ledger.path.parent.mkdir(parents=True, exist_ok=True)
            ledger.path.write_text(
                json.dumps(
                    {
                        "event": "budget_authorization",
                        "additional_starts": 3,
                        "authorization_id": "forged",
                        "reference": "forged",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger._start_cap(ledger._records())
            self.assertEqual(ledger.path.read_bytes(), before)

    def test_c84_second_exact_plus_three_tranche_progresses_to_cap_seven(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            # Consume the first authorized tranche: four starts, with the fourth
            # ending in a retryable failure so the next authorization has the
            # exact predecessor required by the strict sequence.
            self._first_failure(ledger, "run-one")
            ledger.authorize_budget(3, "authorization-one", "reference-one")
            ledger.authorize_repair("run-one", "repair-one", "baseline-two")
            sequence = (
                (2, "baseline-two", "baseline-three"),
                (3, "baseline-three", "baseline-four"),
                (4, "baseline-four", "baseline-five"),
            )
            for index, baseline, next_baseline in sequence:
                run_id = f"run-{index}"
                ledger.reserve(run_id, baseline, self.now.isoformat())
                ledger.mark_semantic_start(run_id)
                ledger.terminal_failure(run_id, "collaboration/routing", False)
                if index < 4:
                    ledger.authorize_repair(run_id, f"repair-{index}", next_baseline)
            self.assertEqual(ledger._start_cap(ledger._records()), 4)
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 4)
            self.assertEqual(
                {record["event"] for record in ledger._records() if record["event"] == "reservation"},
                {"reservation"},
            )

            before = ledger.path.read_bytes()
            ledger.authorize_budget(3, "authorization-two", "reference-two")
            self.assertNotEqual(before, ledger.path.read_bytes())
            self.assertEqual(ledger._start_cap(ledger._records()), 7)
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 4)
            self.assertEqual(
                len(
                    {
                        record["run_id"]
                        for record in ledger._records()
                        if record["event"] == "reservation"
                        and not any(
                            prior.get("event") in {"semantic_start", "presemantic_release"}
                            and prior.get("run_id") == record.get("run_id")
                            for prior in ledger._records()
                        )
                    }
                ),
                0,
            )

            # The resumed fifth reservation is authorized by a fresh repair
            # baseline and consumes exactly one new semantic start.
            ledger.authorize_repair("run-4", "repair-five", "baseline-five")
            ledger.reserve("run-five", "baseline-five", self.now.isoformat())
            ledger.mark_semantic_start("run-five")
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 5)

    def test_c85_second_tranche_invalid_duplicate_concurrent_and_interrupted_paths_are_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._first_failure(ledger)
            ledger.authorize_budget(3, "authorization-one", "reference-one")
            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(2, "authorization-two", "reference-two")
            self.assertEqual(ledger.path.read_bytes(), before)
            ledger.authorize_repair("run-one", "repair-one", "baseline-two")
            # Consume starts two through four without a second authorization yet.
            sequence = (
                (2, "baseline-two", "baseline-three"),
                (3, "baseline-three", "baseline-four"),
                (4, "baseline-four", "baseline-five"),
            )
            for index, baseline, next_baseline in sequence:
                run_id = f"run-{index}"
                ledger.reserve(run_id, baseline, self.now.isoformat())
                ledger.mark_semantic_start(run_id)
                ledger.terminal_failure(run_id, "runtime/infrastructure", False)
                if index < 4:
                    ledger.authorize_repair(run_id, f"repair-{index}", next_baseline)
            ledger.authorize_budget(3, "authorization-two", "reference-two")
            stable = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(3, "authorization-two", "reference-three")
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(3, "authorization-three", "reference-two")
            self.assertEqual(ledger.path.read_bytes(), stable)

            outcomes: list[str] = []

            def contend(authorization_id: str) -> None:
                try:
                    ledger.authorize_budget(3, authorization_id, f"concurrent-{authorization_id}")
                    outcomes.append("accepted")
                except TeamConfigurationError:
                    outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(contend, ("authorization-three", "authorization-four")))
            self.assertEqual(sorted(outcomes), ["rejected", "rejected"])

            # A presemantic interruption is idempotent; no second release or
            # semantic-start count can be manufactured while resuming.
            ledger.authorize_repair("run-4", "repair-five", "baseline-five")
            ledger.reserve("run-five", "baseline-five", self.now.isoformat())
            self.assertTrue(ledger.release_presemantic("run-five", "interrupted"))
            interrupted = ledger.path.read_bytes()
            self.assertFalse(ledger.release_presemantic("run-five", "interrupted-again"))
            self.assertEqual(ledger.path.read_bytes(), interrupted)
            with self.assertRaises(TeamConfigurationError):
                ledger.mark_semantic_start("run-five")

    def test_c64_legacy_default_keeps_exact_plus_two_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory), requirement_id="R2.3-002")
            self._begin(ledger, "legacy-one", "baseline-one")
            ledger.terminal_failure("legacy-one", "runtime/infrastructure", False)
            ledger.authorize_repair("legacy-one", "repair-one", "baseline-two")
            self._begin(ledger, "legacy-two", "baseline-two")
            ledger.terminal_failure("legacy-two", "runtime/infrastructure", False)
            legacy_before = ledger.path.read_bytes()
            ledger.authorize_budget(2, "legacy-authorization", "legacy-reference")
            self.assertEqual(ledger._start_cap(ledger._records()), 4)
            self.assertNotEqual(legacy_before, ledger.path.read_bytes())

    def test_c61_cli_default_is_legacy_and_formal_requires_explicit_selector(self) -> None:
        def invoke(root: Path, argv: list[str]) -> int:
            with patch.object(team_main, "repository_root", return_value=root), patch.object(
                sys, "argv", ["modeling-team", *argv]
            ):
                return team_main.main()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_root = root / "workspaces" / "modeling-runs"
            legacy = self._ledger(legacy_root, requirement_id="R2.3-002")
            self._begin(legacy, "legacy-one", "legacy-baseline-one")
            legacy.terminal_failure("legacy-one", "runtime/infrastructure", False)
            legacy.authorize_repair("legacy-one", "legacy-repair", "legacy-baseline-two")
            self._begin(legacy, "legacy-two", "legacy-baseline-two")
            legacy.terminal_failure("legacy-two", "runtime/infrastructure", False)
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-budget",
                        "--additional-starts",
                        "2",
                        "--authorization-id",
                        "legacy-cli",
                        "--reference",
                        "legacy-cli-reference",
                    ],
                ),
                0,
            )
            self.assertEqual(legacy._start_cap(legacy._records()), 4)

            formal = self._ledger(legacy_root)
            self._first_failure(formal)
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-budget",
                        "--requirement-id",
                        "R2.3-005",
                        "--additional-starts",
                        "3",
                        "--authorization-id",
                        "formal-cli",
                        "--reference",
                        "formal-cli-reference",
                    ],
                ),
                0,
            )
            self.assertEqual(formal._start_cap(formal._records()), 4)
            formal.authorize_repair("run-one", "formal-repair-two", "formal-baseline-two")
            for index, baseline, next_baseline in (
                (2, "formal-baseline-two", "formal-baseline-three"),
                (3, "formal-baseline-three", "formal-baseline-four"),
                (4, "formal-baseline-four", "formal-baseline-five"),
            ):
                run_id = f"formal-run-{index}"
                formal.reserve(run_id, baseline, self.now.isoformat())
                formal.mark_semantic_start(run_id)
                formal.terminal_failure(run_id, "collaboration/routing", False)
                if index < 4:
                    formal.authorize_repair(run_id, f"formal-repair-{index + 1}", next_baseline)
            legacy_bytes_before_second_formal_auth = (
                root / "workspaces" / "modeling-runs" / ".r2-3-002-start-ledger.jsonl"
            ).read_bytes()
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-budget",
                        "--requirement-id",
                        "R2.3-005",
                        "--additional-starts",
                        "3",
                        "--authorization-id",
                        "formal-cli-second",
                        "--reference",
                        "formal-cli-second-reference",
                    ],
                ),
                0,
            )
            self.assertEqual(formal._start_cap(formal._records()), 7)
            self.assertEqual(
                (root / "workspaces" / "modeling-runs" / ".r2-3-002-start-ledger.jsonl").read_bytes(),
                legacy_bytes_before_second_formal_auth,
            )
            before = (root / "workspaces" / "modeling-runs" / ".r2-3-002-start-ledger.jsonl").read_bytes()
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-budget",
                        "--requirement-id",
                        "UNKNOWN",
                        "--additional-starts",
                        "3",
                        "--authorization-id",
                        "unknown",
                        "--reference",
                        "unknown",
                    ],
                ),
                2,
            )
            self.assertEqual(
                (root / "workspaces" / "modeling-runs" / ".r2-3-002-start-ledger.jsonl").read_bytes(),
                before,
            )
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-budget",
                        "--requirement-id",
                        "R2.3-005",
                        "--ledger-root",
                        str(root / "alternate"),
                        "--additional-starts",
                        "3",
                        "--authorization-id",
                        "alternate",
                        "--reference",
                        "alternate",
                    ],
                ),
                2,
            )

    def test_c65_ordering_and_exact_run_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._first_failure(ledger)
            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("wrong-run", "repair", "baseline-two")
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-one", "repair", "baseline-two")
            self.assertEqual(ledger.path.read_bytes(), before)
            ledger.authorize_budget(3, "authorization-one", "user-reference-one")
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-one", "repair", "baseline-one")
            ledger.authorize_repair("run-one", "repair", "baseline-two")
            ledger.reserve("run-two", "baseline-two", self.now.isoformat())

    def test_c66_concurrent_terminal_budget_and_repair_have_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._begin(ledger, "run-one", "baseline-one")
            outcomes: list[str] = []

            def fail(_value: str) -> None:
                try:
                    ledger.terminal_failure("run-one", "runtime/infrastructure", False)
                    outcomes.append("failure")
                except TeamConfigurationError:
                    outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(fail, ("a", "b")))
            self.assertEqual(sorted(outcomes), ["failure", "rejected"])

            outcomes.clear()

            def budget(authorization_id: str) -> None:
                try:
                    ledger.authorize_budget(3, authorization_id, f"reference-{authorization_id}")
                    outcomes.append("budget")
                except TeamConfigurationError:
                    outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(budget, ("a", "b")))
            self.assertEqual(sorted(outcomes), ["budget", "rejected"])
            ledger.authorize_repair("run-one", "repair", "baseline-two")
            outcomes.clear()

            def repair(baseline: str) -> None:
                try:
                    ledger.authorize_repair("run-one", f"repair-{baseline}", baseline)
                    outcomes.append("repair")
                except TeamConfigurationError:
                    outcomes.append("rejected")

            ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            ledger.release_presemantic("run-two", "presemantic")
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(repair, ("baseline-three", "baseline-four")))
            self.assertEqual(sorted(outcomes), ["rejected", "repair"])

    def test_c67_cap_or_interrupted_prefix_cannot_reserve_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._first_failure(ledger)
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            ledger.authorize_budget(3, "authorization-one", "reference-one")
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            ledger.authorize_repair("run-one", "repair", "baseline-two")
            ledger.reserve("run-two", "baseline-two", self.now.isoformat())

    def test_c68_complete_modeling_quality_failure_stops_even_with_remaining_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._begin(ledger, "run-one", "baseline-one")
            ledger.terminal_failure("run-one", "modeling-quality", True)
            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-one", "repair-one", "baseline-two")
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(3, "authorization-one", "reference-one")
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            self.assertEqual(ledger.path.read_bytes(), before)

    def test_c68_incomplete_modeling_quality_direct_repair_replays_and_reserves_without_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._retained_like_10_8_0_prefix(ledger)
            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(3, "authorization-four", "reference-four")
            self.assertEqual(ledger.path.read_bytes(), before)

            gate = {
                "proof_matrix_path": "proof-matrix.json",
                "proof_matrix_digest": "a" * 64,
                "p2a_pass_path": "p2a-pass.json",
                "p2a_pass_digest": "b" * 64,
                "source_run_id": "run-8",
            }
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-8", "repair-invalid", "baseline-8")
            self.assertEqual(ledger.path.read_bytes(), before)
            ledger.authorize_repair("run-8", "repair-9", "baseline-9", gate_binding=gate)
            records = ledger._records()
            self.assertEqual(
                len([record for record in records if record.get("event") == "budget_authorization"]),
                3,
            )

            replay = self._ledger(Path(directory))
            replay._validate_strict_replay(replay._records())
            before_gate_mismatch = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("run-9", "baseline-9", self.now.isoformat())
            self.assertEqual(ledger.path.read_bytes(), before_gate_mismatch)
            ledger.reserve("run-9", "baseline-9", self.now.isoformat(), gate_binding=gate)
            self.assertEqual(ledger._start_cap(ledger._records()), 10)
            self.assertEqual(ledger._semantic_start_count(ledger._records()), 8)

    def test_c68_incomplete_modeling_quality_repair_is_serialized_and_r23002_stays_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            formal = self._ledger(root / "formal")
            self._retained_like_10_8_0_prefix(formal)
            outcomes: list[str] = []

            def repair(baseline: str) -> None:
                try:
                    formal.authorize_repair("run-8", f"repair-{baseline}", baseline)
                    outcomes.append("accepted")
                except TeamConfigurationError:
                    outcomes.append("rejected")

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(repair, ("baseline-9", "baseline-10")))
            self.assertEqual(sorted(outcomes), ["accepted", "rejected"])
            accepted_baseline = [
                record["baseline_hash"]
                for record in formal._records()
                if record.get("event") == "repair_authorization"
                and record.get("run_id") == "run-8"
            ][0]
            formal.reserve("run-9", accepted_baseline, self.now.isoformat())

            legacy = self._ledger(root / "legacy", requirement_id="R2.3-002")
            self._begin(legacy, "legacy-one", "legacy-baseline-one")
            legacy.terminal_failure("legacy-one", "modeling-quality", False)
            before = legacy.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                legacy.authorize_repair("legacy-one", "legacy-repair", "legacy-baseline-two")
            self.assertEqual(legacy.path.read_bytes(), before)

    def test_c68_cli_selector_allows_formal_incomplete_repair_only(self) -> None:
        def invoke(root: Path, argv: list[str]) -> int:
            with patch.object(team_main, "repository_root", return_value=root), patch.object(
                sys, "argv", ["modeling-team", *argv]
            ):
                return team_main.main()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            formal = self._ledger(root / "workspaces" / "modeling-runs")
            self._retained_like_10_8_0_prefix(formal)
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-repair",
                        "--requirement-id",
                        "R2.3-005",
                        "--failed-run-id",
                        "run-8",
                        "--baseline-hash",
                        "baseline-9",
                        "--repair-reference",
                        "formal-cli-repair",
                    ],
                ),
                0,
            )
            self.assertEqual(formal._records()[-1]["event"], "repair_authorization")
            self.assertEqual(formal._records()[-1]["baseline_hash"], "baseline-9")

            legacy = self._ledger(root / "workspaces" / "modeling-runs", requirement_id="R2.3-002")
            self._begin(legacy, "legacy-one", "legacy-baseline-one")
            legacy.terminal_failure("legacy-one", "modeling-quality", False)
            before = legacy.path.read_bytes()
            self.assertEqual(
                invoke(
                    root,
                    [
                        "authorize-repair",
                        "--requirement-id",
                        "R2.3-002",
                        "--failed-run-id",
                        "legacy-one",
                        "--baseline-hash",
                        "legacy-baseline-two",
                        "--repair-reference",
                        "legacy-cli-repair",
                    ],
                ),
                2,
            )
            self.assertEqual(legacy.path.read_bytes(), before)

    def test_c69_c73_rebind_requires_one_released_fresh_reservation_per_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._authorized_first_repair(ledger)
            ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            ledger.release_presemantic("run-two", "presemantic-one")
            ledger.authorize_repair("run-one", "rebind-one", "baseline-three")
            ledger.reserve("run-three", "baseline-three", self.now.isoformat())
            ledger.release_presemantic("run-three", "presemantic-two")
            ledger.authorize_repair("run-one", "rebind-two", "baseline-four")
            self.assertEqual(
                [item["baseline_hash"] for item in ledger._records() if item.get("event") == "repair_authorization"],
                ["baseline-two", "baseline-three", "baseline-four"],
            )

            before = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-one", "duplicate", "baseline-four")
            self.assertEqual(ledger.path.read_bytes(), before)

    def test_c70_and_i15_temporary_formal_ledger_is_isolated_from_legacy_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = self._ledger(root / "legacy", requirement_id="R2.3-002")
            legacy.path.parent.mkdir(parents=True, exist_ok=True)
            legacy.path.write_text('{"event":"semantic_start","run_id":"legacy"}\n', encoding="utf-8")
            legacy_bytes = legacy.path.read_bytes()
            formal = self._ledger(root / "formal")
            self._authorized_first_repair(formal)
            records = formal._records()
            active = {
                item.get("run_id")
                for item in records
                if item.get("event") == "reservation"
            } - {
                item.get("run_id")
                for item in records
                if item.get("event") in {"semantic_start", "presemantic_release"}
            }
            self.assertEqual(active, set())
            self.assertEqual(formal._start_cap(records), 4)
            self.assertEqual(formal._semantic_start_count(records), 1)
            self.assertEqual(legacy.path.read_bytes(), legacy_bytes)
            self.assertEqual(hashlib.sha256(legacy.path.read_bytes()).hexdigest(), hashlib.sha256(legacy_bytes).hexdigest())

    def test_c71_interrupted_failure_and_budget_prefix_resumes_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = self._ledger(Path(directory))
            self._first_failure(ledger)
            failure_prefix = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_repair("run-one", "wrong-order", "baseline-two")
            self.assertEqual(ledger.path.read_bytes(), failure_prefix)
            ledger.authorize_budget(3, "authorization-one", "reference-one")
            budget_prefix = ledger.path.read_bytes()
            with self.assertRaises(TeamConfigurationError):
                ledger.authorize_budget(3, "authorization-two", "reference-two")
            self.assertEqual(ledger.path.read_bytes(), budget_prefix)
            ledger.authorize_repair("run-one", "repair", "baseline-two")
            ledger.reserve("run-two", "baseline-two", self.now.isoformat())
            self.assertEqual(
                [item["event"] for item in ledger._records()][-3:],
                ["budget_authorization", "repair_authorization", "reservation"],
            )

    def test_c73_unreleased_started_unused_wrong_run_and_concurrent_rebind_fail_closed(self) -> None:
        for mode in ("unused", "active", "started", "wrong-run", "equal"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                ledger = self._ledger(Path(directory))
                self._authorized_first_repair(ledger)
                if mode == "active":
                    ledger.reserve("run-two", "baseline-two", self.now.isoformat())
                elif mode == "started":
                    self._begin(ledger, "run-two", "baseline-two")
                elif mode == "equal":
                    ledger.reserve("run-two", "baseline-two", self.now.isoformat())
                    ledger.release_presemantic("run-two", "released")
                elif mode == "wrong-run":
                    ledger.reserve("run-two", "baseline-two", self.now.isoformat())
                    ledger.release_presemantic("run-two", "released")
                    before = ledger.path.read_bytes()
                    with self.assertRaises(TeamConfigurationError):
                        ledger.authorize_repair("wrong-run", "wrong", "baseline-three")
                    self.assertEqual(ledger.path.read_bytes(), before)
                    continue
                before = ledger.path.read_bytes()
                baseline = "baseline-two" if mode == "equal" else "baseline-three"
                with self.assertRaises(TeamConfigurationError):
                    ledger.authorize_repair("run-one", "invalid", baseline)
                self.assertEqual(ledger.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
