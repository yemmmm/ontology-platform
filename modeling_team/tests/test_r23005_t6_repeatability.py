from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier
from modeling_team.contracts import (
    TeamConfiguration,
    TeamConfigurationError,
    digest_file,
    load_formal_team_configuration,
    repository_root,
)
from modeling_team.preflight import capture_clean_checkout, run_prestart_preflight
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.start_ledger import StartLedger


NO_START_REASON = "preflight/no-semantic-start"
ABORT_REASON = "preflight-no-semantic-start"


def _init_clean_fixture_repo(path: Path, marker: str) -> None:
    """Create a tiny clean checkout used only by the injected preflight seam."""

    path.mkdir(parents=True, mode=0o700)
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t6@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "R23005 T6"], cwd=path, check=True)
    (path / "baseline.marker").write_text(marker, encoding="utf-8")
    subprocess.run(["git", "add", "baseline.marker"], cwd=path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "clean-baseline"], cwd=path, check=True)


def _fake_canonical_probe(**_kwargs: Any) -> dict[str, Any]:
    """A safe fixture for preflight; it never opens a network or platform client."""

    return {
        "service": {
            "unit": "ontology-platform.service",
            "active_state": "active",
            "sub_state": "running",
            "main_pid": 1,
            "active_enter_timestamp": "fixture",
        },
        "process": {
            "unit": "ontology-platform.service",
            "pid": 1,
            "started_at": "fixture",
            "process_env": {
                "SEMANTIC_CANONICAL_STORE": "rdf",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            },
        },
        "health": {
            "backend": {"status_code": 200, "body_digest": "a" * 64},
            "frontend": {"status_code": 200, "body_digest": "b" * 64},
        },
        "canonical": {
            "status_code": 200,
            "response": {
                "canonical_store": "rdf",
                "product_write_mode": "rdf_primary",
                "read_mode": "canonical",
                "legacy_write_blocked": True,
            },
            "response_digest": "c" * 64,
        },
    }


def _asset_manifest(configuration: TeamConfiguration) -> dict[str, str]:
    """Digest only frozen package/Skill assets; no business source bytes are staged."""

    assets: dict[str, str] = {}
    for agent in configuration.profile.agents:
        package = agent.package
        package_yaml = package.instructions_path.parent / "package.yaml"
        assets[f"package:{package.package_id}"] = digest_file(package_yaml)
        assets[f"instructions:{package.package_id}"] = digest_file(package.instructions_path)
        for skill in package.required_skills:
            assets[f"skill:{package.package_id}:{skill.name}"] = digest_file(skill)
    return assets


class _NoStartSequence:
    """Deterministic T6 ordering seam; it has no process, Platform, or ledger calls."""

    def __init__(
        self,
        *,
        runtime_root: Path,
        fixture_repo: Path,
        run_id: str,
        configuration: TeamConfiguration,
        baseline_hash: str,
    ) -> None:
        self.runtime_root = runtime_root
        self.fixture_repo = fixture_repo
        self.run_id = run_id
        self.configuration = configuration
        self.baseline_hash = baseline_hash
        self.events: list[str] = []
        self.phase = "new"

    def preflight(self) -> dict[str, Any]:
        if self.phase != "new":
            raise TeamConfigurationError(NO_START_REASON)
        self.events.append("preflight_probe")
        evidence = run_prestart_preflight(
            repository_root=self.fixture_repo,
            base_url="fixture://canonical",
            admin_key=None,
            probe=_fake_canonical_probe,
        )
        self.events.append("preflight")
        self.phase = "preflighted"
        return evidence

    def stage_frozen_manifest(self) -> Path:
        if self.phase != "preflighted":
            raise TeamConfigurationError(NO_START_REASON)
        roles = [agent.package.role for agent in self.configuration.profile.agents]
        if roles != ["coordinator", "modeling", "protocol", "acceptance"]:
            raise TeamConfigurationError("formal four-role manifest drifted")
        stage_root = self.runtime_root / "runtime-stage"
        stage_root.mkdir(parents=True, mode=0o700)
        manifest = {
            "schema_version": "r2-3-005-t6-no-start/v1",
            "run_id": self.run_id,
            "profile_id": self.configuration.profile.profile_id,
            "task_id": self.configuration.task.task_id,
            "roles": roles,
            "baseline_hash": self.baseline_hash,
            "assets": _asset_manifest(self.configuration),
        }
        path = stage_root / "frozen-runtime-manifest.json"
        path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(path, 0o440)
        self.events.append("staging")
        self.phase = "staged"
        return path

    def forbidden_semantic_start(self) -> None:
        # This fixture is intentionally not wired to Runner.start or an Agent
        # adapter.  A call is still rejected with a fixed typed reason so a
        # repeatability check cannot be mistaken for a second real task.
        raise TeamConfigurationError(NO_START_REASON)


class R23005T6RepeatabilityTests(unittest.TestCase):
    def test_t6_second_fresh_root_stages_capabilities_without_semantic_start(self) -> None:
        repo = repository_root()
        profile_path = repo / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
        task_path = repo / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"
        configuration = load_formal_team_configuration(profile_path, task_path, root=repo)
        # Read-only baseline inventory through the existing Runner seam.  Do not
        # call prepare(): it deliberately reserves StartLedger and stages sources.
        baseline_runner = TeamRunner(
            repository_root=repo,
            adapter=CodexRuntimeAdapter(
                repository_root=repo,
                use_bwrap=False,
                process_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("semantic process start is forbidden in T6")
                ),
            ),
        )
        shared_ledger = repo / "workspaces/modeling-runs/.r2-3-002-start-ledger.jsonl"
        shared_ledger_before = shared_ledger.read_bytes() if shared_ledger.exists() else None

        with tempfile.TemporaryDirectory(prefix="r23005-t6-") as directory:
            temporary_root = Path(directory)
            runs: list[tuple[str, Path, _NoStartSequence, RunnerAcceptanceCarrier, CodexRuntimeAdapter]] = []
            for suffix in ("first", "second"):
                run_id = f"r23005-t6-{suffix}"
                runtime_root = temporary_root / run_id
                fixture_repo = runtime_root / "clean-checkout"
                _init_clean_fixture_repo(fixture_repo, run_id)
                baseline = baseline_runner._baseline_manifest(
                    run_id=run_id,
                    configuration=configuration,
                    profile_path=profile_path,
                    task_path=task_path,
                )
                baseline_hash = StartLedger.baseline_hash(baseline)
                sequence = _NoStartSequence(
                    runtime_root=runtime_root,
                    fixture_repo=fixture_repo,
                    run_id=run_id,
                    configuration=configuration,
                    baseline_hash=baseline_hash,
                )

                # Wrong order is fail-closed and produces no runtime-stage files.
                with self.assertRaisesRegex(TeamConfigurationError, NO_START_REASON):
                    sequence.stage_frozen_manifest()
                self.assertEqual(sequence.events, [])
                preflight_evidence = sequence.preflight()
                self.assertEqual(preflight_evidence["checkout"]["status_porcelain"], "")
                self.assertEqual(sequence.events, ["preflight_probe", "preflight"])
                stage_manifest = sequence.stage_frozen_manifest()
                self.assertTrue(stage_manifest.is_file())
                self.assertEqual(sequence.events, ["preflight_probe", "preflight", "staging"])
                self.assertEqual(capture_clean_checkout(fixture_repo)["status_porcelain"], "")
                retained_manifest = json.loads(stage_manifest.read_text(encoding="utf-8"))
                self.assertEqual(
                    set(retained_manifest),
                    {"schema_version", "run_id", "profile_id", "task_id", "roles", "baseline_hash", "assets"},
                )
                self.assertEqual(
                    retained_manifest["roles"], ["coordinator", "modeling", "protocol", "acceptance"]
                )
                manifest_text = json.dumps(retained_manifest, sort_keys=True).lower()
                for forbidden in (
                    "source",
                    "source_bundle",
                    "candidate",
                    "project",
                    "ontology",
                    "credential",
                    "expected_answer",
                    "answer",
                ):
                    self.assertNotIn(forbidden, manifest_text)

                # Capability staging is Runner-local and child-free.  Distinct
                # carriers/adapters prove no home/socket/token/registry sharing.
                def forbidden_child(_spec: Mapping[str, Any]) -> Any:
                    raise AssertionError("Examiner child start is forbidden in T6")

                carrier = RunnerAcceptanceCarrier(
                    runtime_root / "acceptance-carrier",
                    task_id=f"task-r23005-t6-{suffix}",
                    acceptance_id="acceptance",
                    child_factory=forbidden_child,
                )
                adapter = CodexRuntimeAdapter(
                    repository_root=repo,
                    use_bwrap=False,
                    process_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        AssertionError("persistent Codex start is forbidden in T6")
                    ),
                )
                carrier.start_capability_endpoints()
                endpoint_paths = {
                    carrier.capability_socket_path(role)
                    for role in ("coordinator", "protocol", "acceptance")
                }
                token_paths = {
                    carrier.capability_token_path(role)
                    for role in ("coordinator", "protocol", "acceptance")
                }
                self.assertTrue(all(path.exists() for path in endpoint_paths | token_paths))
                self.assertEqual(adapter.cleanup_identifiers()["acceptance_children"]["active"], 0)
                self.assertEqual(sequence.phase, "staged")

                # The no-start gate has no semantic, ticket, source, candidate,
                # resource, report, verdict, or PASS path and never touches ledger.
                with self.assertRaisesRegex(TeamConfigurationError, NO_START_REASON):
                    sequence.forbidden_semantic_start()
                self.assertNotIn("semantic_start", sequence.events)
                self.assertNotIn("sources", {path.name for path in runtime_root.iterdir()})
                self.assertFalse((runtime_root / "candidate.json").exists())
                for ledger_name in (
                    ".r2-3-002-start-ledger.jsonl",
                    ".r2-3-005-start-ledger.jsonl",
                ):
                    self.assertFalse((runtime_root / ledger_name).exists())
                for lock_name in (
                    ".r2-3-002-start-ledger.lock",
                    ".r2-3-005-start-ledger.lock",
                ):
                    self.assertFalse((runtime_root / lock_name).exists())
                self.assertFalse(carrier._handles)
                self.assertFalse(carrier._resources)
                self.assertFalse(carrier._pending_reports)
                self.assertFalse(carrier._reports)
                self.assertFalse(carrier._verdicts)
                self.assertFalse(carrier.is_settled)
                with self.assertRaisesRegex(AcceptanceContractError, "verdict submission binding"):
                    carrier.submit_verdict(
                        acceptance_id="acceptance",
                        round_id="r23005-t6-no-start",
                        verdict={"verdict": "PASS"},
                        request_id="t6-no-start-pass",
                    )
                with self.assertRaisesRegex(AcceptanceContractError, "explicit model-state reader"):
                    carrier.settle()
                self.assertFalse(carrier._verdicts)
                self.assertFalse((carrier.root / "evidence/settlement.json").exists())

                runs.append((run_id, runtime_root, fixture_repo, sequence, carrier, adapter))

            first, second = runs
            self.assertNotEqual(first[1], second[1])
            self.assertNotEqual(first[4].capability_token_path("acceptance"), second[4].capability_token_path("acceptance"))
            self.assertNotEqual(first[4].capability_socket_path("acceptance"), second[4].capability_socket_path("acceptance"))
            self.assertNotEqual(first[4].capability_token_path("protocol"), second[4].capability_token_path("protocol"))
            self.assertNotEqual(first[4].capability_socket_path("protocol"), second[4].capability_socket_path("protocol"))
            self.assertNotEqual(first[4].capability_token_path("acceptance").read_bytes(), second[4].capability_token_path("acceptance").read_bytes())
            self.assertIsNot(first[5]._acceptance_children, second[5]._acceptance_children)
            self.assertNotEqual(first[0], second[0])

            for _run_id, runtime_root, fixture_repo, _sequence, carrier, adapter in runs:
                cleanup = carrier.abort_cleanup(ABORT_REASON)
                self.assertEqual(cleanup["status"], "aborted")
                self.assertFalse(cleanup["settled"])
                self.assertTrue(cleanup["zero_child_residue"])
                self.assertEqual(cleanup["active_handles"], 0)
                self.assertEqual(carrier.cleanup(), cleanup)
                self.assertFalse(carrier.is_live)
                self.assertFalse(carrier.capability_root.exists())
                self.assertFalse(
                    any(
                        carrier.capability_socket_path(role).exists()
                        for role in ("coordinator", "protocol", "acceptance")
                    )
                )
                self.assertFalse(
                    any(
                        carrier.capability_token_path(role).exists()
                        for role in ("coordinator", "protocol", "acceptance")
                    )
                )
                self.assertFalse(carrier._handles)
                self.assertFalse(carrier._resources)
                self.assertFalse(carrier._pending_reports)
                self.assertFalse(carrier._verdicts)
                self.assertFalse((carrier.root / "acceptance" / "source-report.json").exists())
                self.assertFalse((carrier.root / "acceptance" / "platform-report.json").exists())
                self.assertFalse((carrier.root / "evidence" / "settlement.json").exists())
                self.assertEqual(adapter.cleanup_identifiers()["acceptance_children"]["active"], 0)
                adapter.stop()
                self.assertEqual(adapter.cleanup_identifiers()["acceptance_children"]["active"], 0)
                self.assertEqual(capture_clean_checkout(fixture_repo)["status_porcelain"], "")
                # The carrier keeps only its append-only aborted receipt until the
                # temporary fixture root is removed by this test.
                self.assertTrue((carrier.root / "evidence" / "cleanup.json").is_file())
                shutil.rmtree(runtime_root)
                self.assertFalse(runtime_root.exists())

            for _run_id, _runtime_root, _fixture_repo, _sequence, _carrier, _adapter in runs:
                # Both clean-checkout fixtures were independent and remained clean;
                # their roots were removed with the runtime roots above.
                pass

        if shared_ledger.exists():
            self.assertEqual(shared_ledger.read_bytes(), shared_ledger_before)
        else:
            self.assertIsNone(shared_ledger_before)


if __name__ == "__main__":
    unittest.main()
