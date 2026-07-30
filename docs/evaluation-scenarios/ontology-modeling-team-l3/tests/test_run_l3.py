from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_l3 as launcher  # noqa: E402


class L3LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_runtime = launcher.RUNTIME_ROOT
        self.original_ledger = launcher.GLOBAL_LEDGER
        self.original_classifications = launcher.CLASSIFICATION_LEDGER
        self.original_lock = launcher.GLOBAL_LOCK
        self.original_state = launcher.SCENARIO_STATE
        self.original_policy = launcher.EXECUTION_POLICY
        launcher.RUNTIME_ROOT = self.root / "runtime" / "runs"
        launcher.GLOBAL_LEDGER = self.root / "runtime" / "attempt-ledger.jsonl"
        launcher.CLASSIFICATION_LEDGER = self.root / "runtime" / "historical-classification-ledger.jsonl"
        launcher.GLOBAL_LOCK = self.root / "runtime" / "attempt-ledger.lock"
        launcher.SCENARIO_STATE = self.root / "runtime" / "state.json"
        launcher.EXECUTION_POLICY = self.root / "execution-policy.json"
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, run_ids=[])

    def tearDown(self) -> None:
        launcher.RUNTIME_ROOT = self.original_runtime
        launcher.GLOBAL_LEDGER = self.original_ledger
        launcher.CLASSIFICATION_LEDGER = self.original_classifications
        launcher.GLOBAL_LOCK = self.original_lock
        launcher.SCENARIO_STATE = self.original_state
        launcher.EXECUTION_POLICY = self.original_policy
        self.temporary.cleanup()

    def _write_policy(
        self,
        *,
        live_execution_authorized: bool,
        state: str,
        outcome: str,
        category: str,
        starts_consumed: int,
        run_ids: list[str],
    ) -> None:
        launcher.EXECUTION_POLICY.write_text(json.dumps({
            "policy_version": 1,
            "live_execution_authorized": live_execution_authorized,
            "state": state,
            "outcome": outcome,
            "category": category,
            "starts_consumed": starts_consumed,
            "run_ids": run_ids,
            "recovery_requirements": ["proof", "review", "user authorization"],
        }), encoding="utf-8")

    def test_manifest_is_complete_hashed_and_staged_read_only(self) -> None:
        manifest = launcher.read_manifest()
        receipt = launcher.stage_input(manifest, self.root / "agent-visible")
        self.assertEqual(len(receipt["files"]), len(manifest["files"]))
        self.assertNotIn("tester-only", " ".join(receipt["files"]))

    def test_manifest_rejects_undeclared_input(self) -> None:
        copied = self.root / "input"
        import shutil

        shutil.copytree(launcher.AGENT_INPUT, copied)
        (copied / "leak.txt").write_text("unexpected", encoding="utf-8")
        original = launcher.AGENT_INPUT
        launcher.AGENT_INPUT = copied
        try:
            with self.assertRaisesRegex(launcher.L3Error, "set differs"):
                launcher.read_manifest()
        finally:
            launcher.AGENT_INPUT = original

    def test_mechanics_stable_id_and_request_are_deterministic(self) -> None:
        helper = launcher.ProtocolMechanics("l3-test")
        self.assertEqual(helper.stable_id("batch", 1), helper.stable_id("batch", 1))
        self.assertEqual(helper.request("checkpoint", {"a": 1}), helper.request("checkpoint", {"a": 1}))

    def test_mechanics_does_not_synthesize_items_and_requires_exact_replay(self) -> None:
        helper = launcher.ProtocolMechanics("l3-test")
        items = [{"client_item_id": "protocol-supplied", "command_kind": "create_class"}]
        frozen = helper.freeze_batch(items, "batch-1")
        helper.replay(frozen, items, "batch-1")
        with self.assertRaisesRegex(launcher.L3Error, "replay drift"):
            helper.replay(frozen, [{"different": True}], "batch-1")

    def test_mechanics_prepares_lease_and_checkpoint_without_semantic_changes(self) -> None:
        helper = launcher.ProtocolMechanics("l3-test")
        self.assertEqual(helper.lease_renewal("lease", 3)["expected_revision"], 3)
        self.assertEqual(helper.checkpoint("session", 4, {"note": "Protocol supplied"})["body"]["note"], "Protocol supplied")

    def test_question_requires_grounded_single_pending_state(self) -> None:
        work = self.root / "work"
        question = {"question": "Which published version?", "sources": ["sources/release-register.md"], "affected_conclusion": "current invocation"}
        launcher.record_question(work, question)
        with self.assertRaisesRegex(launcher.L3Error, "one grounded"):
            launcher.record_question(work, question)

    def test_answer_requires_pending_question_and_is_verbatim_contract_value(self) -> None:
        work = self.root / "work"
        with self.assertRaisesRegex(launcher.L3Error, "without a pending"):
            launcher.release_answer(work, "invocation-target")
        launcher.record_question(work, {"question": "Which?", "sources": ["x.md"], "affected_conclusion": "x"})
        answer = launcher.release_answer(work, "invocation-target")
        self.assertEqual(answer["answer"], "B invokes C through C's Latest published Version.")
        self.assertFalse((work / "pending-question.json").exists())

    def test_unsupported_question_cannot_receive_invented_answer(self) -> None:
        work = self.root / "work"
        launcher.record_question(work, {"question": "Other?", "sources": ["x.md"], "affected_conclusion": "x"})
        with self.assertRaisesRegex(launcher.L3Error, "unsupported"):
            launcher.release_answer(work, "unfrozen")

    def test_global_ledger_records_modeling_only_after_verified_child_identity(self) -> None:
        at = launcher.FIRST_MODELING_DEADLINE - timedelta(seconds=1)
        launcher.reserve_coordinator_start("l3-start", at)
        with self.assertRaisesRegex(launcher.L3Error, "child Session"):
            launcher.record_modeling_delegation("l3-start", "coordinator", "", at)
        self.assertEqual([event["event"] for event in launcher._read_jsonl(launcher.GLOBAL_LEDGER)], ["coordinator_started"])
        event = launcher.record_modeling_delegation("l3-start", "coordinator", "modeler", at)
        self.assertEqual(event["event"], "modeling_started")

    def test_global_ledger_halts_after_twenty_minutes_and_rejects_future_starts(self) -> None:
        with self.assertRaisesRegex(launcher.L3Error, "20-minute"):
            launcher.reserve_coordinator_start("l3-late", launcher.FIRST_MODELING_DEADLINE + timedelta(seconds=1))
        self.assertEqual(launcher.local_scenario_status()["state"], "PAUSED")
        with self.assertRaisesRegex(launcher.L3Error, "paused"):
            launcher.reserve_coordinator_start("l3-after-halt", launcher.FIRST_MODELING_DEADLINE - timedelta(seconds=1))

    def test_global_ledger_rejects_fourth_attempt_across_run_ids(self) -> None:
        at = launcher.FIRST_MODELING_DEADLINE - timedelta(seconds=1)
        for index in range(3):
            launcher.reserve_coordinator_start(f"l3-{index}", at)
        with self.assertRaisesRegex(launcher.L3Error, "global coordinator start limit"):
            launcher.reserve_coordinator_start("l3-four", at)
        status = launcher.local_scenario_status()
        self.assertEqual(status["state"], "PAUSED")
        self.assertEqual(status["outcome"], "NOT_PASSED")
        self.assertEqual(status["classification_count"], 0)
        self.assertEqual(json.loads(launcher.SCENARIO_STATE.read_text(encoding="utf-8"))["outcome"], "NOT_PASSED")

    def test_global_ledger_preserves_historical_run_roots(self) -> None:
        historical = launcher.RUNTIME_ROOT / "l3-history" / "attempts.jsonl"
        historical.parent.mkdir(parents=True)
        historical.write_text(json.dumps({"event": "modeling_started", "run_id": "l3-history", "first_modeling_started_at": "2026-07-30T12:47:34+08:00"}) + "\n", encoding="utf-8")
        self.assertEqual(launcher.local_scenario_status()["team_starts"], 1)
        self.assertIn("historical_coordinator_started", launcher.GLOBAL_LEDGER.read_text(encoding="utf-8"))

    def _write_raw_historical_run(self, run_id: str) -> tuple[Path, Path]:
        audit = launcher.RUNTIME_ROOT / run_id / "audit"
        audit.mkdir(parents=True)
        state = {"run_id": run_id, "state": "INCONCLUSIVE", "category": "runtime/infrastructure"}
        state_path = audit / "state.json"
        transcript_path = audit / "coordinator.jsonl"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        transcript_path.write_text('{"type":"thread.started","thread_id":"coordinator"}\n', encoding="utf-8")
        return state_path, transcript_path

    def test_historical_classification_is_append_only_idempotent_and_covers_exact_three_runs(self) -> None:
        for run_id in launcher.HISTORICAL_RUN_IDS:
            self._write_raw_historical_run(run_id)
        first = launcher.local_scenario_status()
        first_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")
        second = launcher.local_scenario_status()
        corrections = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)
        self.assertEqual(first_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(first["category"], "collaboration/routing")
        self.assertEqual(second["classification_count"], 3)
        self.assertEqual({entry["run_id"] for entry in corrections}, set(launcher.HISTORICAL_RUN_IDS))
        self.assertTrue(all(entry["authoritative"]["outcome"] == "NOT_PASSED" for entry in corrections))

    def test_historical_classification_binds_raw_state_and_transcript_hashes(self) -> None:
        paths = [self._write_raw_historical_run(run_id) for run_id in launcher.HISTORICAL_RUN_IDS]
        launcher.local_scenario_status()
        correction = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)[0]
        state_path, transcript_path = paths[0]
        self.assertEqual(correction["evidence"]["state_sha256"], launcher.sha256_path(state_path))
        self.assertEqual(correction["evidence"]["transcript_sha256"], launcher.sha256_path(transcript_path))
        transcript_path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "hash drift"):
            launcher.local_scenario_status()

    def test_committed_disabled_policy_blocks_fresh_runtime_before_root_or_probe(self) -> None:
        self._write_policy(
            live_execution_authorized=False,
            state="PAUSED",
            outcome="NOT_PASSED",
            category="collaboration/routing",
            starts_consumed=3,
            run_ids=list(launcher.HISTORICAL_RUN_IDS),
        )
        with self.assertRaisesRegex(launcher.L3Error, "disabled"):
            launcher.run("l3-fresh-clone", execute=True)
        self.assertFalse(launcher.RUNTIME_ROOT.exists())
        status = launcher.scenario_status()
        self.assertFalse(status["local_ledger"]["available"])
        self.assertEqual(status["policy"]["state"], "PAUSED")

    def test_committed_policy_and_local_ledger_mismatch_fails_closed(self) -> None:
        for run_id in launcher.HISTORICAL_RUN_IDS:
            self._write_raw_historical_run(run_id)
        launcher.local_scenario_status()
        self._write_policy(
            live_execution_authorized=False,
            state="PAUSED",
            outcome="NOT_PASSED",
            category="runtime/infrastructure",
            starts_consumed=3,
            run_ids=list(launcher.HISTORICAL_RUN_IDS),
        )
        with self.assertRaisesRegex(launcher.L3Error, "disagree"):
            launcher.scenario_status()

    def test_isolated_command_mounts_only_verified_reasoner_not_repository(self) -> None:
        command = launcher.isolated_command({}, {"DATABASE_URL": "postgresql://example", "OXIGRAPH_URL": "http://example"}, 19001)
        text = " ".join(command)
        self.assertIn("/backend/scripts/dev_owl_reasoner.py", text)
        self.assertIn("SEMANTIC_REASONER_COMMAND", text)
        self.assertNotIn(f"--ro-bind {launcher.REPOSITORY_ROOT} {launcher.REPOSITORY_ROOT}", text)
        self.assertNotIn("/.env", text)

    def test_coordinator_contract_requires_fresh_modeling_child_before_source_review(self) -> None:
        task = (launcher.AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8")
        config = (launcher.SCENARIO_ROOT / "agent-config" / "modeling-agent.toml").read_text(encoding="utf-8")
        self.assertIn("spawn_agent", task)
        self.assertIn("returned a child identity", task)
        self.assertIn('name = "modeling_agent"', config)

    def test_verified_child_requires_spawn_event_with_exact_child_identity(self) -> None:
        transcript = "\n".join((
            '{"type":"thread.started","thread_id":"coordinator"}',
            '{"item":{"type":"collab_tool_call","tool":"spawn_agent","receiver_thread_ids":["modeler"]}}',
        ))
        self.assertEqual(launcher.verified_modeling_child(transcript), ("coordinator", "modeler"))
        with self.assertRaisesRegex(launcher.L3Error, "authoritative"):
            launcher.verified_modeling_child('{"type":"thread.started","thread_id":"coordinator"}')

    def test_role_staging_hides_protocol_from_coordinator_and_scaffolds_protocol_only_files(self) -> None:
        receipt = launcher.stage_role_packs(launcher.read_manifest(), self.root / "run", "l3-role")
        coordinator = self.root / "run" / "coordinator-input"
        protocol = self.root / "run" / "protocol-input"
        self.assertTrue(receipt["coordinator_excludes_public_protocol"])
        self.assertFalse((coordinator / "public-protocol.md").exists())
        self.assertTrue((protocol / "public-protocol.md").is_file())
        mechanics = json.loads((protocol / "mechanics-contract.json").read_text(encoding="utf-8"))
        lifecycle = json.loads((protocol / "credential-lifecycle.json").read_text(encoding="utf-8"))
        self.assertEqual(mechanics["owner"], "protocol_only_deterministic_helper")
        self.assertTrue(lifecycle["no_key_probe_required"])
        self.assertTrue(lifecycle["temporary_key"]["never_written_to_evidence"])

    def test_protocol_handoff_is_opaque_and_never_contains_a_plaintext_key(self) -> None:
        protocol = self.root / "protocol"
        protocol.mkdir()
        receipt = launcher.stage_protocol_handoff(protocol, {"candidate": "agent-owned"}, {"task_id": "l3"}, {"project_id": "project", "ontology_id": "ontology"})
        self.assertEqual(receipt["scope"], "owned")
        self.assertNotIn("plaintext", "".join(path.read_text(encoding="utf-8") for path in protocol.iterdir()))
        self.assertIn("key is absent", (launcher.SCENARIO_ROOT / "protocol-agent-prompt.md").read_text(encoding="utf-8"))

    def test_missing_child_publishes_authoritative_paused_not_passed_state(self) -> None:
        with patch.object(launcher, "reserve_coordinator_start", return_value={"event": "coordinator_started"}), patch.object(launcher, "read_manifest", return_value={"files": []}), patch.object(launcher, "stage_role_packs", return_value={}), patch.object(launcher, "managed_reasoning_preflight", return_value={}), patch.object(launcher, "launch_coordinator", side_effect=launcher.L3Error("coordinator did not evidence one authoritative Modeling Agent child delegation")):
            with self.assertRaises(launcher.L3Error):
                launcher.run("l3-paused", execute=True)
        state = json.loads((launcher.RUNTIME_ROOT / "l3-paused" / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["outcome"], "NOT_PASSED")
        self.assertEqual(state["category"], "collaboration/routing")

    def test_run_requires_explicit_execute(self) -> None:
        with self.assertRaisesRegex(launcher.L3Error, "without --execute"):
            launcher.run("l3-safe", execute=False)


if __name__ == "__main__":
    unittest.main()
