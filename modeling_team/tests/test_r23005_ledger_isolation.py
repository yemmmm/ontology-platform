from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from modeling_team.contracts import TeamConfigurationError, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.start_ledger import StartLedger


_TEST_FORMAL_CREDENTIAL = Path(tempfile.mkdtemp(prefix="r23005-ledger-credential-")) / "deepseek.env"
_TEST_FORMAL_CREDENTIAL.write_text("DEEPSEEK_API_KEY=round23-test-sentinel\n", encoding="utf-8")
_TEST_FORMAL_CREDENTIAL.chmod(0o600)


class R23005LedgerIsolationTests(unittest.TestCase):
    root = repository_root()

    @staticmethod
    def _clean_checkout() -> dict[str, str]:
        return {
            "repository_root": str(repository_root()),
            "head": "a" * 40,
            "status_porcelain": "",
            "status_digest": "b" * 64,
        }

    @staticmethod
    def _write_exhausted_legacy_ledger(root: Path) -> bytes:
        records: list[dict[str, object]] = []
        for index in range(1, 19):
            records.append({"event": "semantic_start", "run_id": f"legacy-{index}"})
            if index % 2 == 0 and index < 18:
                tranche = index // 2
                records.append(
                    {
                        "event": "budget_authorization",
                        "additional_starts": 2,
                        "authorization_id": f"legacy-approval-{tranche}",
                        "reference": f"legacy-reference-{tranche}",
                    }
                )
        path = root / ".r2-3-002-start-ledger.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        ledger = StartLedger(root)
        assert ledger._start_cap(ledger._records()) == 18
        return path.read_bytes()

    def _runner(
        self,
        ledger_root: Path,
        *,
        formal: bool = True,
        preflight=None,
    ) -> TeamRunner:
        ledger_factory = None
        runner_ledger_root = ledger_root
        if formal:
            # Formal production runs are canonical-root bound.  Temporary
            # ledgers are available only through this explicit deterministic
            # factory seam; the seam honors the canonical root supplied by
            # Runner rather than redirecting it to a caller-owned path.
            def ledger_factory(*, root, config, now):
                return StartLedger(root, config=config, now=now)

            runner_ledger_root = None
        runner = TeamRunner(
            repository_root=self.root,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            ledger_root=runner_ledger_root,
            deepseek_credential_path=_TEST_FORMAL_CREDENTIAL if formal else None,
            ledger_factory=ledger_factory,
            freeze_started_at=datetime.now(UTC).isoformat(),
            prestart_preflight=(
                preflight
                if preflight is not None
                else (lambda **_kwargs: {"status_code": 200, "product_write_mode": "rdf_primary"})
            )
            if formal
            else None,
        )
        if formal:
            # The test's temporary repository-owned namespace is the canonical
            # root for this deterministic seam; production keeps the default
            # resolver bound to repository_root/workspaces/modeling-runs.
            runner._canonical_ledger_root = lambda: ledger_root
        return runner

    def _prepare_formal(self, runner: TeamRunner, run_id: str):
        with patch(
            "modeling_team.preflight.capture_clean_checkout",
            return_value=self._clean_checkout(),
        ):
            return runner.prepare(
                run_id=run_id,
                profile_path=self.root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                task_path=self.root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                scope={"mode": "create"},
            )

    @staticmethod
    def _cleanup(runner: TeamRunner, run_root: Path) -> None:
        try:
            runner.cleanup()
        finally:
            if run_root.exists():
                rmtree(run_root)

    def test_constructor_rejects_ledger_path_escape_and_exposes_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("../escape.jsonl", "/tmp/escape.jsonl", "nested/escape.jsonl", r"nested\escape.jsonl"):
                with self.subTest(value=value), self.assertRaisesRegex(
                    TeamConfigurationError, "filename is invalid"
                ):
                    StartLedger(root, ledger_filename=value)
            with self.assertRaisesRegex(TeamConfigurationError, "filenames must differ"):
                StartLedger(root, ledger_filename="same", lock_filename="same")
            ledger = StartLedger(
                root,
                ledger_filename=".r2-3-005-start-ledger.jsonl",
                lock_filename=".r2-3-005-start-ledger.lock",
                initial_start_cap=1,
                requirement_id="R2.3-005",
            )
            self.assertEqual(
                ledger.identity,
                {"filename": ".r2-3-005-start-ledger.jsonl", "requirement_id": "R2.3-005"},
            )

    def test_formal_runner_rejects_alternate_ledger_root_before_file_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "alternate-ledger"
            run_id = f"r23005-canonical-reject-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = TeamRunner(
                repository_root=self.root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                deepseek_credential_path=_TEST_FORMAL_CREDENTIAL,
                ledger_root=alternate,
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=lambda **_kwargs: {"status_code": 200, "product_write_mode": "rdf_primary"},
            )
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value=self._clean_checkout(),
                ), self.assertRaisesRegex(TeamConfigurationError, "alternate ledger_root"):
                    runner.prepare(
                        run_id=run_id,
                        profile_path=self.root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                        task_path=self.root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                        scope={"mode": "create"},
                    )
                self.assertFalse(alternate.exists())
                self.assertFalse(run_root.exists())
            finally:
                runner.cleanup()

    def test_formal_factory_cannot_redirect_ledger_before_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            canonical = base / "canonical"
            attacker = base / "attacker"
            run_id = f"r23005-factory-redirect-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = TeamRunner(
                repository_root=self.root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                deepseek_credential_path=_TEST_FORMAL_CREDENTIAL,
                ledger_factory=lambda *, root, config, now: StartLedger(
                    attacker, config=config, now=now
                ),
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=lambda **_kwargs: {
                    "status_code": 200,
                    "product_write_mode": "rdf_primary",
                },
            )
            # Keep all source/configuration reads on the real checkout while
            # giving this test a temporary repository-owned canonical ledger
            # namespace.  The malicious factory still receives (and ignores)
            # that canonical root.
            runner._canonical_ledger_root = lambda: canonical
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value=self._clean_checkout(),
                ), self.assertRaisesRegex(
                    TeamConfigurationError, "outside the canonical ledger root"
                ):
                    self._prepare_formal(runner, run_id)
                self.assertIsNone(runner._ledger)
                self.assertFalse(attacker.exists())
                self.assertFalse(canonical.exists())
                self.assertFalse(run_root.exists())
            finally:
                runner.cleanup()

    def test_formal_ledger_is_independent_and_cap_one_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            old_before = self._write_exhausted_legacy_ledger(ledger_root)
            run_id = f"r23005-ledger-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = self._runner(ledger_root)
            try:
                run = self._prepare_formal(runner, run_id)
                self.assertIsNone(run.gate_binding)
                old_path = ledger_root / ".r2-3-002-start-ledger.jsonl"
                new_path = ledger_root / ".r2-3-005-start-ledger.jsonl"
                new_lock = ledger_root / ".r2-3-005-start-ledger.lock"
                self.assertEqual(old_path.read_bytes(), old_before)
                self.assertTrue(new_path.is_file())
                self.assertTrue(new_lock.is_file())
                records = runner._ledger._records()
                self.assertEqual(runner._ledger.identity["requirement_id"], "R2.3-005")
                self.assertEqual(
                    runner._ledger.path.resolve(),
                    (ledger_root / ".r2-3-005-start-ledger.jsonl").resolve(),
                )
                self.assertEqual(
                    runner._ledger.lock_path.resolve(),
                    (ledger_root / ".r2-3-005-start-ledger.lock").resolve(),
                )
                self.assertEqual(runner._ledger._start_cap(records), 1)
                self.assertEqual([item["event"] for item in records], ["reservation"])
                reservation_evidence = json.loads(
                    (run.root / "evidence/start-ledger.jsonl").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    reservation_evidence["ledger_identity"],
                    {"filename": ".r2-3-005-start-ledger.jsonl", "requirement_id": "R2.3-005"},
                )
                runner._ledger.mark_semantic_start(run_id)
                self.assertEqual(old_path.read_bytes(), old_before)
                second_bytes = new_path.read_bytes()
                second_run_id = f"r23005-ledger-second-{uuid4().hex}"
                second = self._runner(ledger_root)
                try:
                    with self.assertRaisesRegex(
                        TeamConfigurationError, "R2.3-005 semantic-start budget is exhausted"
                    ):
                        self._prepare_formal(second, second_run_id)
                    self.assertEqual(new_path.read_bytes(), second_bytes)
                    self.assertEqual(old_path.read_bytes(), old_before)
                    self.assertFalse(
                        (self.root / "workspaces/modeling-runs" / second_run_id).exists()
                    )
                finally:
                    self._cleanup(second, self.root / "workspaces/modeling-runs" / second_run_id)
            finally:
                self._cleanup(runner, run_root)

    def test_presemantic_release_does_not_consume_formal_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            first_id = f"r23005-release-one-{uuid4().hex}"
            first_root = self.root / "workspaces/modeling-runs" / first_id
            first = self._runner(ledger_root)
            try:
                self._prepare_formal(first, first_id)
                self._cleanup(first, first_root)
                path = ledger_root / ".r2-3-005-start-ledger.jsonl"
                records = [json.loads(line) for line in path.read_text().splitlines()]
                self.assertEqual([item["event"] for item in records], ["reservation", "presemantic_release"])
                self.assertEqual(StartLedger(ledger_root, ledger_filename=path.name, initial_start_cap=1, requirement_id="R2.3-005")._start_cap(records), 1)
                second_id = f"r23005-release-two-{uuid4().hex}"
                second_root = self.root / "workspaces/modeling-runs" / second_id
                second = self._runner(ledger_root)
                try:
                    self._prepare_formal(second, second_id)
                    self.assertEqual(
                        [item["event"] for item in second._ledger._records()],
                        ["reservation", "presemantic_release", "reservation"],
                    )
                finally:
                    self._cleanup(second, second_root)
            finally:
                if first_root.exists():
                    rmtree(first_root)

    def test_nonformal_schema_two_keeps_legacy_ledger_identity_and_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            run_id = f"r23002-legacy-path-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = self._runner(ledger_root, formal=False)
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value=self._clean_checkout(),
                ):
                    runner.prepare(
                        run_id=run_id,
                        profile_path=self.root / "modeling_team/profiles/base-three-agent.yaml",
                        task_path=self.root / "modeling_team/tasks/new-scope-business-slice.yaml",
                        scope={"mode": "create"},
                    )
                self.assertEqual(runner._ledger.path.name, ".r2-3-002-start-ledger.jsonl")
                self.assertEqual(runner._ledger.identity["requirement_id"], "R2.3-002")
                self.assertEqual(runner._ledger._start_cap(runner._ledger._records()), 2)
                legacy_evidence = json.loads(
                    (run_root / "evidence/start-ledger.jsonl").read_text(encoding="utf-8")
                )
                self.assertNotIn("ledger_identity", legacy_evidence)
                self.assertFalse((ledger_root / ".r2-3-005-start-ledger.jsonl").exists())
            finally:
                self._cleanup(runner, run_root)

    def test_formal_preflight_failure_writes_neither_ledger_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            old_before = self._write_exhausted_legacy_ledger(ledger_root)
            run_id = f"r23005-no-ledger-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id

            def failing_preflight(**_kwargs):
                raise TeamConfigurationError("canonical-mode preflight blocked")

            runner = self._runner(ledger_root, preflight=failing_preflight)
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value=self._clean_checkout(),
                ), self.assertRaisesRegex(TeamConfigurationError, "canonical-mode"):
                    self._prepare_formal(runner, run_id)
                self.assertEqual(
                    (ledger_root / ".r2-3-002-start-ledger.jsonl").read_bytes(), old_before
                )
                self.assertFalse((ledger_root / ".r2-3-005-start-ledger.jsonl").exists())
                self.assertFalse((ledger_root / ".r2-3-005-start-ledger.lock").exists())
                self.assertFalse(run_root.exists())
            finally:
                runner.cleanup()


if __name__ == "__main__":
    unittest.main()
