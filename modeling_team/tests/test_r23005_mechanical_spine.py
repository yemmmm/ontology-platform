from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import yaml

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier
from modeling_team.candidate_progress import FormalCandidateProgress, formal_candidate_digests
from modeling_team.candidate_publication import (
    CandidatePublicationError,
    stage_candidate_publication,
    validate_candidate_publication,
)
from modeling_team.capability_mcp import MODELING_OPERATIONS, PROTOCOL_OPERATIONS, PROTOCOL_STAGE_OPERATIONS
from modeling_team.contracts import (
    TeamConfigurationError,
    load_formal_team_configuration,
    load_team_configuration,
    repository_root,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.start_ledger import StartLedger
from modeling_team.task_overlay import load_task_input_overlay
from modeling_team.transport_mcp import TeamTransportBroker


class R23005MechanicalSpineTests(unittest.TestCase):
    root = repository_root()
    task_path = root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"
    profile_path = root / "modeling_team/profiles/r2-3-005-modeling-team.yaml"

    @staticmethod
    def _candidate() -> dict[str, object]:
        return {
            "candidate_kind": "platform-neutral-candidate-v2",
            "candidate_revision": "test-r3",
            "scope": {"business_slice": "runtime-neutral-publication"},
            "constraints": ["Preserve the accepted business meaning."],
            "items": [
                {
                    "item_id": "class-workflow",
                    "item_kind": "class",
                    "semantic": {"values": {"label": "Workflow"}},
                }
            ],
        }

    @classmethod
    def _carrier(cls) -> dict[str, object]:
        candidate = cls._candidate()
        candidate_digest, semantic_digest = formal_candidate_digests(candidate)
        candidate_text = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        accepted_delivery_id = "delivery-accepted-r3"
        source_delivery_id = "delivery-source-r3"
        source_run_id = "r23005-source-r3"
        return {
            "acceptance_scope": {},
            "accepted_delivery_id": accepted_delivery_id,
            "accepted_receipt": {
                "status": "accepted",
                "candidate_revision": candidate["candidate_revision"],
                "semantic_digest": semantic_digest,
                "candidate_digest": candidate_digest,
            },
            "candidate": candidate,
            "candidate_identity": {
                "accepted_delivery_id": accepted_delivery_id,
                "candidate_digest": candidate_digest,
                "candidate_revision": candidate["candidate_revision"],
                "run_id": source_run_id,
                "semantic_digest": semantic_digest,
                "source_delivery_id": source_delivery_id,
            },
            "candidate_text": candidate_text,
            "continuation_directive": {},
            "owner_answers": [],
            "provenance": {},
            "read_only_diagnosis": {},
            "revision_request": {},
            "schema_version": "r2-3-005-continuation/v1",
            "source_delivery_id": source_delivery_id,
            "source_protocol_conflict": {},
            "source_run_id": source_run_id,
            "terminal_blocker": None,
        }

    @contextmanager
    def _overlay_fixture(self, *, overlay_change=None, carrier_change=None):
        continuation_root = self.root / "modeling_team/.continuations"
        continuation_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mechanical-spine-", dir=continuation_root) as value:
            fixture_root = Path(value)
            carrier = self._carrier()
            if carrier_change is not None:
                carrier_change(carrier)
            carrier_path = fixture_root / "candidate.json"
            carrier_bytes = json.dumps(
                carrier,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            carrier_path.write_bytes(carrier_bytes)
            os.chmod(carrier_path, 0o444)
            overlay = {
                "schema_version": 1,
                "overlay_id": f"mechanical-{uuid4().hex[:12]}",
                "base_task": {
                    "path": self.task_path.relative_to(self.root).as_posix(),
                    "task_id": "r2-3-005-formal-acceptance",
                    "sha256": hashlib.sha256(self.task_path.read_bytes()).hexdigest(),
                },
                "candidate_publication": {
                    "path": carrier_path.relative_to(self.root).as_posix(),
                    "sha256": hashlib.sha256(carrier_bytes).hexdigest(),
                    "mode": "0444",
                    "classification": "coordination",
                    "roles": ["modeling"],
                },
            }
            if overlay_change is not None:
                overlay_change(overlay)
            overlay_path = fixture_root / "overlay.yaml"
            overlay_path.write_text(
                yaml.safe_dump(overlay, sort_keys=False),
                encoding="utf-8",
            )
            os.chmod(overlay_path, 0o444)
            yield overlay_path, overlay, carrier_bytes

    def _load(self, overlay_path: Path):
        configuration = load_formal_team_configuration(
            self.profile_path,
            self.task_path,
            root=self.root,
        )
        return load_task_input_overlay(
            overlay_path,
            root=self.root,
            task_path=self.task_path,
            task=configuration.task,
        )

    def test_overlay_binds_authoritative_task_and_exact_candidate_source(self) -> None:
        with self._overlay_fixture() as (overlay_path, overlay_value, carrier_bytes):
            overlay = self._load(overlay_path)
            publication = validate_candidate_publication(overlay)

            self.assertEqual(overlay.base_task_id, "r2-3-005-formal-acceptance")
            self.assertEqual(overlay.base_task_bytes, self.task_path.read_bytes())
            self.assertEqual(publication.carrier_bytes, carrier_bytes)
            self.assertEqual(publication.candidate_text, self._carrier()["candidate_text"])
            self.assertEqual(overlay.manifest()["base_task"]["task_id"], overlay.base_task_id)
            self.assertEqual(overlay.manifest()["candidate_publication"]["roles"], ["modeling"])
            self.assertEqual(overlay.sha256, hashlib.sha256(overlay.overlay_bytes).hexdigest())
            self.assertEqual(overlay.overlay_id, overlay_value["overlay_id"])

    def test_overlay_is_unavailable_to_legacy_tasks(self) -> None:
        with self._overlay_fixture() as (overlay_path, _overlay, _carrier):
            configuration = load_team_configuration(
                self.root / "modeling_team/profiles/base-three-agent.yaml",
                self.root / "modeling_team/tasks/base-capability-smoke.yaml",
                root=self.root,
            )
            with self.assertRaisesRegex(TeamConfigurationError, "formal R2.3.005-only"):
                load_task_input_overlay(
                    overlay_path,
                    root=self.root,
                    task_path=self.root / "modeling_team/tasks/base-capability-smoke.yaml",
                    task=configuration.task,
                )

    def test_overlay_rejects_base_drift_role_drift_and_symlink(self) -> None:
        cases = (
            (lambda value: value["base_task"].__setitem__("sha256", "0" * 64), "digest drifted"),
            (
                lambda value: value["candidate_publication"].__setitem__(
                    "roles", ["modeling", "protocol"]
                ),
                "role is invalid",
            ),
        )
        for change, message in cases:
            with self.subTest(message=message), self._overlay_fixture(
                overlay_change=change
            ) as (overlay_path, _overlay, _carrier), self.assertRaisesRegex(
                TeamConfigurationError, message
            ):
                self._load(overlay_path)

        with self._overlay_fixture() as (overlay_path, _overlay, _carrier):
            symlink = overlay_path.parent / "overlay-link.yaml"
            symlink.symlink_to(overlay_path.name)
            with self.assertRaisesRegex(TeamConfigurationError, "not a regular"):
                self._load(symlink)

            parent_symlink = overlay_path.parent / "parent-link"
            parent_symlink.symlink_to(".", target_is_directory=True)
            with self.assertRaisesRegex(TeamConfigurationError, "contains a symlink"):
                self._load(parent_symlink / overlay_path.name)

        with self._overlay_fixture() as (overlay_path, _overlay, _carrier):
            original = overlay_path.read_bytes()
            os.chmod(overlay_path, 0o644)
            overlay_path.write_bytes(b"schema_version: 1\n" + original)
            os.chmod(overlay_path, 0o444)
            with self.assertRaisesRegex(TeamConfigurationError, "unreadable"):
                self._load(overlay_path)

        with self._overlay_fixture() as (overlay_path, _overlay, _carrier):
            task_link = overlay_path.parent / "formal-task-link.yaml"
            task_link.symlink_to(self.task_path)
            configuration = load_formal_team_configuration(
                self.profile_path,
                self.task_path,
                root=self.root,
            )
            with self.assertRaisesRegex(TeamConfigurationError, "contains a symlink"):
                load_task_input_overlay(
                    overlay_path,
                    root=self.root,
                    task_path=task_link,
                    task=configuration.task,
                )

    def test_candidate_carrier_mismatch_fails_before_preflight_or_reservation(self) -> None:
        def mismatch(value: dict[str, object]) -> None:
            value["candidate_text"] = json.dumps(self._candidate() | {"candidate_revision": "other"})

        with self._overlay_fixture(carrier_change=mismatch) as (
            overlay_path,
            _overlay,
            _carrier,
        ):
            run_id = f"r23005-overlay-invalid-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = TeamRunner(
                repository_root=self.root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=lambda **_kwargs: self.fail("preflight must not run"),
            )
            try:
                with self.assertRaisesRegex(CandidatePublicationError, "text and object differ"):
                    runner.prepare(
                        run_id=run_id,
                        profile_path=self.profile_path,
                        task_path=self.task_path,
                        task_overlay_path=overlay_path,
                        scope={"mode": "create"},
                    )
                self.assertIsNone(runner.run)
                self.assertIsNone(runner._ledger)
                self.assertFalse(run_root.exists())
            finally:
                runner.cleanup()

    def test_preflight_detects_overlay_source_mutation_before_reservation(self) -> None:
        with self._overlay_fixture() as (overlay_path, overlay_value, carrier_bytes):
            carrier_path = self.root / overlay_value["candidate_publication"]["path"]

            def mutating_preflight(**_kwargs):
                os.chmod(carrier_path, 0o644)
                carrier_path.write_bytes(carrier_bytes + b"\n")
                os.chmod(carrier_path, 0o444)
                return {"status_code": 200, "product_write_mode": "rdf_primary"}

            run_id = f"r23005-overlay-drift-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            runner = TeamRunner(
                repository_root=self.root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=mutating_preflight,
            )
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value={
                        "repository_root": str(self.root),
                        "head": "a" * 40,
                        "status_porcelain": "",
                        "status_digest": "b" * 64,
                    },
                ), self.assertRaisesRegex(TeamConfigurationError, "digest drifted"):
                    runner.prepare(
                        run_id=run_id,
                        profile_path=self.profile_path,
                        task_path=self.task_path,
                        task_overlay_path=overlay_path,
                        scope={"mode": "create"},
                    )
                self.assertIsNone(runner.run)
                self.assertIsNone(runner._ledger)
                self.assertFalse(run_root.exists())
            finally:
                runner.cleanup()

    def test_staged_publication_is_exact_role_bound_and_one_shot(self) -> None:
        with self._overlay_fixture() as (
            overlay_path,
            _overlay,
            carrier_bytes,
        ), tempfile.TemporaryDirectory() as value:
            overlay = self._load(overlay_path)
            validated = validate_candidate_publication(overlay)
            run_root = Path(value) / "run"
            run_root.mkdir()
            staged = stage_candidate_publication(overlay, validated, run_root=run_root)
            broker = TeamTransportBroker(
                Path(value) / "transport",
                {("modeling", "protocol")},
            )

            self.assertEqual(staged.staged_path.read_bytes(), carrier_bytes)
            self.assertEqual(stat.S_IMODE(os.lstat(staged.staged_path).st_mode), 0o440)
            with self.assertRaisesRegex(CandidatePublicationError, "Modeling-only"):
                staged.publish(
                    actor_id="protocol",
                    modeling_id="modeling",
                    protocol_id="protocol",
                    send=broker.send,
                )
            self.assertEqual(broker.drain(), [])

            receipt = staged.publish(
                actor_id="modeling",
                modeling_id="modeling",
                protocol_id="protocol",
                send=broker.send,
            )
            deliveries = broker.drain()
            self.assertEqual(len(deliveries), 1)
            self.assertEqual(deliveries[0].text, validated.candidate_text)
            self.assertTrue(deliveries[0].expects_reply)
            self.assertIsNone(deliveries[0].reply_to_delivery_id)
            self.assertEqual(receipt["delivery_id"], deliveries[0].delivery_id)
            self.assertEqual(receipt["source_run_id"], "r23005-source-r3")
            self.assertEqual(receipt["accepted_delivery_id"], "delivery-accepted-r3")

            with self.assertRaisesRegex(CandidatePublicationError, "already published"):
                staged.publish(
                    actor_id="modeling",
                    modeling_id="modeling",
                    protocol_id="protocol",
                    send=broker.send,
                )
            self.assertEqual(broker.drain(), [])

    def test_modeling_capability_is_opt_in_schema_bound_and_codex_projected(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as value:
            plain = RunnerAcceptanceCarrier(Path(value) / "plain", task_id="task", acceptance_id="acceptance")
            self.assertNotIn("modeling", plain.capability_descriptors)
            with self.assertRaises(AcceptanceContractError):
                plain.capability_endpoint("modeling")
            plain.cleanup()

            carrier = RunnerAcceptanceCarrier(
                Path(value) / "overlay",
                task_id="task",
                acceptance_id="acceptance",
                candidate_publisher=lambda modeling_id: calls.append(modeling_id)
                or {"delivery_id": "delivery-1"},
            )
            try:
                descriptor = carrier.capability_descriptors["modeling"]
                self.assertEqual(tuple(descriptor["operations"]), MODELING_OPERATIONS)
                endpoint = carrier.capability_endpoint("modeling")
                token = carrier.capability_token("modeling")
                rejected = endpoint.handle(
                    {
                        "id": 1,
                        "token": token,
                        "method": "tools/call",
                        "params": {
                            "name": MODELING_OPERATIONS[0],
                            "arguments": {"modeling_id": "modeling", "candidate": {}},
                        },
                    }
                )
                self.assertIn("error", rejected)
                self.assertEqual(calls, [])
                accepted = endpoint.handle(
                    {
                        "id": 2,
                        "token": token,
                        "method": "tools/call",
                        "params": {
                            "name": MODELING_OPERATIONS[0],
                            "arguments": {"modeling_id": "modeling"},
                        },
                    }
                )
                self.assertEqual(accepted["result"]["structuredContent"]["data"]["delivery_id"], "delivery-1")
                self.assertEqual(calls, ["modeling"])

                adapter = CodexRuntimeAdapter(repository_root=self.root)
                adapter._acceptance = carrier
                run = SimpleNamespace(
                    configuration=SimpleNamespace(
                        task=SimpleNamespace(
                            task_id="r2-3-005-formal-acceptance",
                            schema_version=2,
                        ),
                        profile=SimpleNamespace(expected_matrix_binding=None),
                    )
                )
                self.assertEqual(
                    adapter._role_capability_operations("modeling", run=run),
                    MODELING_OPERATIONS,
                )
                adapter._coordination_enabled = True
                adapter._run_root = Path(value)
                modeling_home = Path(value) / "modeling-home"
                modeling_work = Path(value) / "modeling-work"
                modeling_skills = Path(value) / "modeling-skills"
                for path in (modeling_home, modeling_work, modeling_skills):
                    path.mkdir()
                modeling_agent = SimpleNamespace(
                    agent_id="modeling",
                    package=SimpleNamespace(role="modeling"),
                    home=modeling_home,
                    work=modeling_work,
                    skills=modeling_skills,
                )
                command = adapter.namespace_command(modeling_agent)
                socket_target = command.index("/agent/home/runner-capability.sock")
                self.assertEqual(command[socket_target - 2], "--bind")
                self.assertEqual(
                    command[socket_target - 1],
                    str(carrier.capability_socket_path("modeling")),
                )
            finally:
                carrier.cleanup()

    def test_typed_protocol_candidate_binding_uses_retained_candidate_and_allows_one_conflict(self) -> None:
        candidate = self._candidate()
        progress = FormalCandidateProgress(clock=lambda: 0.0)
        original_text = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")) + "\n"
        delivery = RuntimeDelivery(
            "modeling",
            "protocol",
            "peer",
            original_text,
            delivery_id="delivery-1",
            expects_reply=True,
            reply_to_delivery_id=None,
        )
        self.assertEqual(
            progress.observe_delivery(
                delivery,
                modeling_agent_id="modeling",
                protocol_agent_id="protocol",
                run_id="run-1",
                protocol_thread_id="thread-1",
            ),
            "candidate",
        )
        progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))

        runner = TeamRunner(repository_root=self.root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(
            run_id="run-1",
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
                profile=SimpleNamespace(
                    profile_id="r2-3-005-modeling-team",
                    agents=[
                        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
                        for role in ("coordinator", "modeling", "protocol", "acceptance")
                    ],
                ),
            ),
        )
        runner.transport = object()
        runner._candidate_progress = progress
        runner._protocol_candidate_responses = {}
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id="r2-3-005-formal-acceptance",
                acceptance_id="acceptance",
                candidate_receipt_builder=runner._build_protocol_candidate_receipt,
                candidate_conflict_builder=runner._build_protocol_candidate_conflict,
            )
            runner.acceptance = carrier
            try:
                self.assertEqual(
                    tuple(carrier.capability_descriptors["protocol"]["operations"]),
                    PROTOCOL_OPERATIONS,
                )
                receipt_result = carrier.protocol_build_candidate_receipt(
                    protocol_id="protocol",
                    delivery_id="delivery-1",
                    capability=carrier.capability_token("protocol"),
                )
                self.assertEqual(receipt_result["candidate"], candidate)
                self.assertEqual(
                    receipt_result["receipt_json"],
                    json.dumps(receipt_result["receipt"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                )
                conflict_result = carrier.protocol_build_candidate_conflict(
                    protocol_id="protocol",
                    delivery_id="delivery-1",
                    conflict_code="missing_label",
                    conflict_detail="label requires a source-grounded value",
                    capability=carrier.capability_token("protocol"),
                )
                self.assertEqual(conflict_result["candidate"], candidate)
                self.assertEqual(
                    conflict_result["conflict_json"],
                    json.dumps(conflict_result["conflict"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                )
                with self.assertRaisesRegex(TeamConfigurationError, "already built"):
                    carrier.protocol_build_candidate_receipt(
                        protocol_id="protocol",
                        delivery_id="delivery-1",
                        capability=carrier.capability_token("protocol"),
                    )
                with self.assertRaisesRegex(TeamConfigurationError, "already built"):
                    carrier.protocol_build_candidate_conflict(
                        protocol_id="protocol",
                        delivery_id="delivery-1",
                        conflict_code="duplicate",
                        conflict_detail="duplicate conflict",
                        capability=carrier.capability_token("protocol"),
                    )
                with self.assertRaisesRegex(TeamConfigurationError, "foreign or stale"):
                    carrier.protocol_build_candidate_receipt(
                        protocol_id="protocol",
                        delivery_id="delivery-foreign",
                        capability=carrier.capability_token("protocol"),
                    )
                progress.pending.state = "complete"  # type: ignore[union-attr]
                with self.assertRaisesRegex(TeamConfigurationError, "not awaiting"):
                    carrier.protocol_build_candidate_receipt(
                        protocol_id="protocol",
                        delivery_id="delivery-1",
                        capability=carrier.capability_token("protocol"),
                    )
            finally:
                carrier.cleanup()

    def test_legacy_protocol_capability_does_not_advertise_typed_candidate_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id="task",
                acceptance_id="acceptance",
            )
            try:
                self.assertEqual(
                    tuple(carrier.capability_descriptors["protocol"]["operations"]),
                    PROTOCOL_STAGE_OPERATIONS,
                )
                endpoint = carrier.capability_endpoint("protocol")
                result = endpoint.handle(
                    {
                        "id": 1,
                        "token": carrier.capability_token("protocol"),
                        "method": "tools/call",
                        "params": {
                            "name": "protocol_build_candidate_receipt",
                            "arguments": {"protocol_id": "protocol", "delivery_id": "delivery-1"},
                        },
                    }
                )
                self.assertIn("error", result)
            finally:
                carrier.cleanup()

    def test_prepare_freezes_overlay_and_carrier_without_replacing_task(self) -> None:
        with self._overlay_fixture() as (
            overlay_path,
            overlay_value,
            carrier_bytes,
        ), tempfile.TemporaryDirectory() as value:
            run_id = f"r23005-overlay-{uuid4().hex}"
            run_root = self.root / "workspaces/modeling-runs" / run_id
            ledger_root = Path(value) / "ledger"
            runner = TeamRunner(
                repository_root=self.root,
                adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
                ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
                freeze_started_at=datetime.now(UTC).isoformat(),
                prestart_preflight=lambda **_kwargs: {
                    "status_code": 200,
                    "product_write_mode": "rdf_primary",
                },
            )
            runner._canonical_ledger_root = lambda: ledger_root
            original_baseline = runner._baseline_manifest
            baseline_calls = 0

            def baseline_then_mutate(**kwargs):
                nonlocal baseline_calls
                result = original_baseline(**kwargs)
                baseline_calls += 1
                if baseline_calls == 2:
                    carrier_path = self.root / overlay_value["candidate_publication"]["path"]
                    os.chmod(carrier_path, 0o644)
                    carrier_path.write_bytes(carrier_bytes + b"\n")
                    os.chmod(carrier_path, 0o444)
                return result

            runner._baseline_manifest = baseline_then_mutate
            try:
                with patch(
                    "modeling_team.preflight.capture_clean_checkout",
                    return_value={
                        "repository_root": str(self.root),
                        "head": "a" * 40,
                        "status_porcelain": "",
                        "status_digest": "b" * 64,
                    },
                ):
                    run = runner.prepare(
                        run_id=run_id,
                        profile_path=self.profile_path,
                        task_path=self.task_path,
                        task_overlay_path=overlay_path,
                        scope={"mode": "create"},
                    )
                self.assertEqual((run.root / "task.snapshot.yaml").read_bytes(), self.task_path.read_bytes())
                self.assertEqual((run.root / "task-overlay.snapshot.yaml").read_bytes(), overlay_path.read_bytes())
                self.assertEqual((run.root / "inputs/candidate-publication.json").read_bytes(), carrier_bytes)
                manifest = json.loads((run.root / "candidate-publication-manifest.json").read_text())
                baseline = json.loads((run.root / "baseline-manifest.json").read_text())
                self.assertEqual(manifest["base_task"]["task_id"], "r2-3-005-formal-acceptance")
                self.assertEqual(
                    stat.S_IMODE(
                        os.lstat(run.root / "candidate-publication-manifest.json").st_mode
                    ),
                    0o444,
                )
                self.assertIn("task_input_overlay", baseline["files"])
                self.assertIn("candidate_publication_source", baseline["files"])
                self.assertEqual(
                    baseline["task_input_overlay"]["candidate_publication"]["mode"],
                    "0444",
                )
                self.assertEqual(
                    baseline["task_input_overlay"]["candidate_publication"]["path"],
                    overlay_value["candidate_publication"]["path"],
                )
                self.assertEqual(
                    baseline["runtime_contract"]["runner_capability_mcp"]["roles"]["modeling"],
                    list(MODELING_OPERATIONS),
                )
                modeling_text = runner._task_text("modeling")
                self.assertIn("modeling_publish_staged_candidate", modeling_text)
                self.assertIn("Do not read or parse a carrier", modeling_text)
            finally:
                runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)


if __name__ == "__main__":
    unittest.main()
