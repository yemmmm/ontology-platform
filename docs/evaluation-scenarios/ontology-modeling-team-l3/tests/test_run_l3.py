from __future__ import annotations

import json
from datetime import datetime, timedelta
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
        self.recovery_preparation_started_at = datetime.now().astimezone().isoformat()
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, max_starts=5, run_ids=[])

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
        max_starts: int,
        run_ids: list[str],
        recovery_preparation_started_at: str | None = None,
    ) -> None:
        launcher.EXECUTION_POLICY.write_text(json.dumps({
            "policy_version": 2,
            "live_execution_authorized": live_execution_authorized,
            "state": state,
            "outcome": outcome,
            "category": category,
            "starts_consumed": starts_consumed,
            "max_starts": max_starts,
            "recovery_preparation_started_at": recovery_preparation_started_at or self.recovery_preparation_started_at,
            "run_ids": run_ids,
            "user_authorization": {"authorized_at": "2026-07-30", "additional_starts": max_starts - starts_consumed},
            "recovery_requirements": ["proof", "review", "user authorization"],
        }), encoding="utf-8")

    def _waiting_run(self, run_id: str = "l3-wait") -> Path:
        root = launcher.RUNTIME_ROOT / run_id
        (root / "audit").mkdir(parents=True)
        (root / "team-work").mkdir()
        answer = json.loads(launcher.ANSWER_CONTRACT.read_text(encoding="utf-8"))["answers"][0]
        released = {"answer_id": answer["id"], "answer": answer["answer"], "sha256": __import__("hashlib").sha256(answer["answer"].encode()).hexdigest()}
        (root / "team-work" / "released-answer.json").write_text(json.dumps(released), encoding="utf-8")
        (root / "team-work" / "approved-candidate.json").write_text(json.dumps({"concept": "candidate"}), encoding="utf-8")
        (root / "team-work" / "protocol-dispatch.json").write_text(json.dumps({"task_id": "l3", "candidate_sha256": "PENDING_LAUNCHER_CANONICALIZATION", "requested_outcome": "apply_published_c_b_a_path"}), encoding="utf-8")
        (root / "audit" / "state.json").write_text(json.dumps({"run_id": run_id, "state": "WAITING_FOR_COORDINATOR_OUTPUT", "coordinator": {"coordinator_thread_id": "coordinator-thread"}}), encoding="utf-8")
        return root

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
        at = launcher.first_modeling_deadline() - timedelta(seconds=1)
        launcher.reserve_coordinator_start("l3-start", at)
        with self.assertRaisesRegex(launcher.L3Error, "child Session"):
            launcher.record_modeling_delegation("l3-start", "coordinator", "", at)
        self.assertEqual([event["event"] for event in launcher._read_jsonl(launcher.GLOBAL_LEDGER)], ["coordinator_started"])
        event = launcher.record_modeling_delegation("l3-start", "coordinator", "modeler", at)
        self.assertEqual(event["event"], "modeling_started")

    def test_global_ledger_halts_after_twenty_minutes_and_rejects_future_starts(self) -> None:
        with self.assertRaisesRegex(launcher.L3Error, "20-minute"):
            launcher.reserve_coordinator_start("l3-late", launcher.first_modeling_deadline() + timedelta(seconds=1))
        self.assertEqual(launcher.local_scenario_status()["state"], "PAUSED")
        with self.assertRaisesRegex(launcher.L3Error, "paused"):
            launcher.reserve_coordinator_start("l3-after-halt", launcher.first_modeling_deadline() - timedelta(seconds=1))

    def test_expired_policy_handoff_halts_current_reservation(self) -> None:
        expired = (datetime.now().astimezone() - timedelta(minutes=20, seconds=1)).isoformat()
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, max_starts=5, run_ids=[], recovery_preparation_started_at=expired)
        with self.assertRaisesRegex(launcher.L3Error, "20-minute"):
            launcher.reserve_coordinator_start("l3-expired")
        self.assertEqual(launcher._read_jsonl(launcher.GLOBAL_LEDGER)[-1]["event"], "preparation_halted")

    def test_global_ledger_rejects_sixth_attempt_across_run_ids(self) -> None:
        at = launcher.first_modeling_deadline() - timedelta(seconds=1)
        for index in range(5):
            launcher.reserve_coordinator_start(f"l3-{index}", at)
        with self.assertRaisesRegex(launcher.L3Error, "global coordinator start limit"):
            launcher.reserve_coordinator_start("l3-six", at)
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

    def _write_raw_historical_run(self, run_id: str, *, configured_role: bool) -> tuple[Path, Path]:
        root = launcher.RUNTIME_ROOT / run_id
        audit = root / "audit"
        audit.mkdir(parents=True)
        state = {"run_id": run_id, "state": "INCONCLUSIVE", "category": "runtime/infrastructure"}
        state_path = audit / "state.json"
        transcript_path = audit / "coordinator.jsonl"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        coordinator_id, child_id = f"coordinator-{run_id}", f"child-{run_id}"
        transcript_path.write_text(json.dumps({"type": "thread.started", "thread_id": coordinator_id}) + "\n", encoding="utf-8")
        sessions = root / "coordinator-home" / "sessions"
        sessions.mkdir(parents=True)
        arguments = {"fork_turns": "none", "task_name": "business_ontology_candidate"}
        if configured_role:
            arguments["agent_type"] = "modeling_agent"
        coordinator = [
            {"type": "session_meta", "payload": {"id": coordinator_id}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "call-model", "arguments": json.dumps(arguments)}},
            {"type": "event_msg", "payload": {"type": "sub_agent_activity", "event_id": "call-model", "agent_thread_id": child_id}},
        ]
        child = {"type": "session_meta", "payload": {"id": child_id, "parent_thread_id": coordinator_id, "agent_role": "modeling_agent" if configured_role else None, "source": {"subagent": {"thread_spawn": {"parent_thread_id": coordinator_id, "agent_role": "modeling_agent" if configured_role else None}}}}}
        (sessions / "coordinator.jsonl").write_text("\n".join(json.dumps(value) for value in coordinator) + "\n", encoding="utf-8")
        (sessions / "child.jsonl").write_text(json.dumps(child) + "\n", encoding="utf-8")
        return state_path, transcript_path

    def _write_raw_recovery_waiting_run(self) -> tuple[Path, Path, Path, list[dict[str, object]]]:
        run_id = launcher.RECOVERY_WAIT_RUN_ID
        state_path, transcript_path = self._write_raw_historical_run(run_id, configured_role=True)
        root = launcher.RUNTIME_ROOT / run_id
        child = launcher.raw_verified_modeling_child(root)
        pending = root / "team-work" / "pending-question.json"
        pending.parent.mkdir()
        pending.write_text(json.dumps({"question": "Which published C version?", "sources": ["sources/release-register.md"], "affected_conclusion": "B's consumed behavior"}), encoding="utf-8")
        state_path.write_text(json.dumps({
            "run_id": run_id,
            "state": "PAUSED",
            "outcome": "NOT_PASSED",
            "category": "runtime/infrastructure",
            "error": "20-minute first-modeling gate missed; state is PAUSED/NOT_PASSED",
            "coordinator": child,
            "terminal_outcome": {"event": "terminal_outcome", "run_id": run_id, "category": "runtime/infrastructure", "outcome": "NOT_PASSED"},
        }), encoding="utf-8")
        transcript_path.write_text("\n".join((json.dumps({"type": "thread.started", "thread_id": child["coordinator_thread_id"]}), json.dumps({"item": {"text": "L3_WAITING_FOR_ANSWER"}}))) + "\n", encoding="utf-8")
        events: list[dict[str, object]] = [
            {"event": "coordinator_started", "run_id": run_id},
            {"event": "preparation_halted", "at": "2026-07-30T15:22:23+08:00", "reason": launcher.DUPLICATE_GATE_HALT_REASON},
            {"event": "terminal_outcome", "run_id": run_id, "category": "runtime/infrastructure", "outcome": "NOT_PASSED"},
        ]
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        return state_path, transcript_path, pending, events

    def test_historical_classification_is_append_only_idempotent_and_covers_exact_three_runs(self) -> None:
        for run_id in launcher.HISTORICAL_RUN_IDS:
            self._write_raw_historical_run(run_id, configured_role=run_id != launcher.HISTORICAL_RUN_IDS[0])
        first = launcher.local_scenario_status()
        first_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")
        second = launcher.local_scenario_status()
        corrections = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)
        self.assertEqual(first_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(first["category"], "pending")
        self.assertEqual(second["classification_count"], 3)
        self.assertEqual({entry["run_id"] for entry in corrections}, set(launcher.HISTORICAL_RUN_IDS))
        v2 = [entry for entry in corrections if entry["correction_id"].startswith("l3-child-identity-correction-v2:")]
        self.assertEqual(len(v2), 3)
        self.assertEqual(v2[0]["reason"], "child role not configured: linked child omitted agent_type=modeling_agent")
        self.assertEqual({entry["authoritative"]["category"] for entry in v2[1:]}, {"acceptance-harness"})

    def test_historical_classification_binds_raw_state_and_transcript_hashes(self) -> None:
        paths = [self._write_raw_historical_run(run_id, configured_role=run_id != launcher.HISTORICAL_RUN_IDS[0]) for run_id in launcher.HISTORICAL_RUN_IDS]
        launcher.local_scenario_status()
        correction = next(value for value in launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER) if value["correction_id"].startswith("l3-child-identity-correction-v2:"))
        state_path, transcript_path = paths[0]
        self.assertEqual(correction["evidence"]["state_sha256"], launcher.sha256_path(state_path))
        self.assertEqual(correction["evidence"]["transcript_sha256"], launcher.sha256_path(transcript_path))
        transcript_path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "raw coordinator transcript JSONL"):
            launcher.local_scenario_status()

    def test_committed_disabled_policy_blocks_fresh_runtime_before_root_or_probe(self) -> None:
        self._write_policy(
            live_execution_authorized=False,
            state="PAUSED",
            outcome="NOT_PASSED",
            category="collaboration/routing",
            starts_consumed=3,
            max_starts=5,
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
            self._write_raw_historical_run(run_id, configured_role=run_id != launcher.HISTORICAL_RUN_IDS[0])
        launcher.local_scenario_status()
        self._write_policy(
            live_execution_authorized=True,
            state="READY",
            outcome="PENDING",
            category="pending",
            starts_consumed=2,
            max_starts=5,
            run_ids=list(launcher.HISTORICAL_RUN_IDS[:2]),
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

    def test_protocol_command_reuses_l1_runtime_mount_without_backend_root_exposure(self) -> None:
        command = launcher._protocol_command(
            self.root / "run", {"DATABASE_URL": "postgresql://example"}
        )
        runtime = (launcher.BACKEND_ROOT / ".venv/bin/python").resolve().parent.parent
        triples = [command[index : index + 3] for index in range(len(command) - 2)]
        self.assertIn(["--ro-bind", str(runtime), str(runtime)], triples)
        self.assertNotIn(str(launcher.BACKEND_ROOT), command)

    def test_protocol_retry_accepts_only_empty_cleaned_owned_residue(self) -> None:
        root = self.root / "run"
        audit, work = root / "audit", root / "protocol-work"
        audit.mkdir(parents=True)
        work.mkdir()
        (audit / "protocol-1.jsonl").write_text("", encoding="utf-8")
        (audit / "protocol-1.stderr.log").write_text(
            "required MCP servers failed to initialize\n", encoding="utf-8"
        )
        (audit / "application-rest.log").write_text(
            'POST /api/api-keys/key%3Arevoke HTTP/1.1" 200 OK\n'
            'DELETE /api/projects/project HTTP/1.1" 204 No Content\n',
            encoding="utf-8",
        )

        launcher._prepare_protocol_work(root)
        receipt = json.loads((audit / "protocol-retry-receipt.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["protocol_work_empty"])
        self.assertEqual(receipt["model_key_revoke_status"], 200)
        (work / "unexpected").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "work is not empty"):
            launcher._prepare_protocol_work(root)

    def test_second_protocol_retry_binds_cancelled_probe_and_cleanup(self) -> None:
        root = self.root / "run"
        audit, work = root / "audit", root / "protocol-work"
        audit.mkdir(parents=True)
        work.mkdir()
        launcher.atomic_json(audit / "protocol-retry-receipt.json", {"attempt": 1})
        (audit / "protocol-2.jsonl").write_text(
            '{"item":{"type":"mcp_tool_call","tool":"cancel_build_session",'
            '"result":{"text":"{\\"status\\": \\"cancelled\\"}"}}}\n'
            '{"item":{"type":"agent_message",'
            '"text":"Blocked by the credential lifecycle precondition"}}\n',
            encoding="utf-8",
        )
        (audit / "protocol-2.stderr.log").write_text("", encoding="utf-8")
        (audit / "application-rest-2.log").write_text(
            'POST /api/api-keys/key%3Arevoke HTTP/1.1" 200 OK\n'
            'DELETE /api/projects/project HTTP/1.1" 204 No Content\n',
            encoding="utf-8",
        )

        launcher._prepare_protocol_work(root)
        receipt = json.loads(
            (audit / "protocol-retry-receipt-2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["attempt"], 2)
        self.assertIn("launcher-owned no-key proof", receipt["reason"])

    def test_third_protocol_retry_binds_dry_run_contract_failure_and_cleanup(self) -> None:
        root = self.root / "run"
        audit, work = root / "audit", root / "protocol-work"
        audit.mkdir(parents=True)
        work.mkdir()
        launcher.atomic_json(audit / "protocol-retry-receipt.json", {"attempt": 1})
        launcher.atomic_json(audit / "protocol-retry-receipt-2.json", {"attempt": 2})
        (audit / "protocol-3.jsonl").write_text(
            "Expected RDF IRI, got: 'entity-a-published'\n"
            "ontology_write_fenced\n"
            "Managed read models confirm reasoning is `missing`\n",
            encoding="utf-8",
        )
        (audit / "protocol-3.stderr.log").write_text("", encoding="utf-8")
        (audit / "application-rest-3.log").write_text(
            'POST /api/api-keys/key%3Arevoke HTTP/1.1" 200 OK\n'
            'DELETE /api/projects/project HTTP/1.1" 204 No Content\n',
            encoding="utf-8",
        )

        launcher._prepare_protocol_work(root)
        receipt = json.loads(
            (audit / "protocol-retry-receipt-3.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["attempt"], 3)
        self.assertIn("relative relation IRIs", receipt["reason"])

    def test_fourth_protocol_retry_binds_valid_progress_timeout_and_cleanup(self) -> None:
        root = self.root / "run"
        audit, work = root / "audit", root / "protocol-work"
        audit.mkdir(parents=True)
        work.mkdir()
        launcher.atomic_json(audit / "protocol-retry-receipt.json", {"attempt": 1})
        launcher.atomic_json(audit / "protocol-retry-receipt-2.json", {"attempt": 2})
        launcher.atomic_json(audit / "protocol-retry-receipt-3.json", {"attempt": 3})
        (audit / "protocol-4.jsonl").write_text(
            "The schema and executable SHACL shape are applied atomically.\n"
            "I am materializing only the approved instances and relations.\n",
            encoding="utf-8",
        )
        (audit / "protocol-4.stderr.log").write_text("", encoding="utf-8")
        (audit / "application-rest-4.log").write_text(
            'POST /api/api-keys/key%3Arevoke HTTP/1.1" 200 OK\n'
            'DELETE /api/projects/project HTTP/1.1" 204 No Content\n',
            encoding="utf-8",
        )

        launcher._prepare_protocol_work(root)
        receipt = json.loads(
            (audit / "protocol-retry-receipt-4.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["attempt"], 4)
        self.assertIn("300-second terminal budget", receipt["reason"])
        self.assertEqual(launcher.TERMINAL_TIMEOUT_SECONDS, 300)
        self.assertEqual(launcher.PROTOCOL_TERMINAL_TIMEOUT_SECONDS, 900)

    def test_fifth_protocol_retry_archives_success_rejected_by_old_batch_contract(self) -> None:
        root = self.root / "run"
        audit, work = root / "audit", root / "protocol-work"
        audit.mkdir(parents=True)
        work.mkdir()
        for attempt in range(1, 5):
            name = (
                "protocol-retry-receipt.json"
                if attempt == 1
                else f"protocol-retry-receipt-{attempt}.json"
            )
            launcher.atomic_json(audit / name, {"attempt": attempt})
        (audit / "protocol-5.jsonl").write_text(
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"Created and validated protocol-result.json"}}\n'
            '{"type":"turn.completed"}\n',
            encoding="utf-8",
        )
        (audit / "protocol-5.stderr.log").write_text("", encoding="utf-8")
        (audit / "application-rest-5.log").write_text(
            'POST /api/api-keys/key%3Arevoke HTTP/1.1" 200 OK\n'
            'DELETE /api/projects/project HTTP/1.1" 204 No Content\n',
            encoding="utf-8",
        )
        launcher.atomic_json(
            work / "protocol-result.json",
            {
                "build_session_id": "session",
                "batches": {
                    "applied": [{"batch_id": "schema"}, {"batch_id": "entities"}],
                    "invalid_dry_run": {"batch_id": "invalid"},
                },
                "workspace": {"before": "before", "after": "after"},
                "validation": {"conforms": True},
                "reasoning": {"status": "succeeded", "consistent": True},
                "query": {
                    "complete": True,
                    "published_path": True,
                    "draft_excluded": True,
                    "explicit_unknown": True,
                },
            },
        )

        launcher._prepare_protocol_work(root)

        receipt = json.loads(
            (audit / "protocol-retry-receipt-5.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["attempt"], 5)
        self.assertEqual(receipt["category"], "platform-contract")
        self.assertTrue((audit / "protocol-result-attempt-5.json").is_file())
        self.assertEqual(list(work.iterdir()), [])

    def test_protocol_uses_launcher_credential_proof_without_repeating_probe(self) -> None:
        protocol_input = self.root / "protocol-input"
        protocol_input.mkdir()
        launcher.stage_credential_proof(protocol_input)
        proof = json.loads((protocol_input / "credential-proof.json").read_text(encoding="utf-8"))
        prompt = (launcher.SCENARIO_ROOT / "protocol-agent-prompt.md").read_text(encoding="utf-8")
        self.assertEqual(proof["no_key_probe"], "rejected_before_temporary_key_creation")
        self.assertFalse(proof["contains_credential_material"])
        self.assertIn("Do not repeat the no-key probe", prompt)
        self.assertNotIn("First prove that the MCP command rejects", prompt)
        public_protocol = (launcher.AGENT_INPUT / "public-protocol.md").read_text(encoding="utf-8")
        self.assertIn("A `client_item_id` is never an RDF IRI", public_protocol)
        self.assertIn("platform-returned entity IRIs", public_protocol)

    def test_coordinator_contract_requires_fresh_modeling_child_before_source_review(self) -> None:
        task = (launcher.AGENT_INPUT / "coordinator-task.md").read_text(encoding="utf-8")
        config = (launcher.SCENARIO_ROOT / "agent-config" / "modeling-agent.toml").read_text(encoding="utf-8")
        self.assertIn("spawn_agent", task)
        self.assertIn("returned a child identity", task)
        self.assertIn('name = "modeling_agent"', config)

    def test_resume_command_places_workspace_write_and_cwd_on_exec_parent(self) -> None:
        command = launcher._codex_exec_command("coordinator-session")
        resume = command.index("resume")
        self.assertEqual(command[:4], ["/codex", "--ask-for-approval", "never", "exec"])
        self.assertLess(command.index("--sandbox"), resume)
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertLess(command.index("-C"), resume)
        self.assertEqual(command[command.index("-C") + 1], "/work")
        self.assertEqual(command[resume + 1 :], ["coordinator-session", "-"])

    def test_raw_rollout_audit_accepts_h_i_configured_role_fixtures(self) -> None:
        for suffix in ("h", "i"):
            run_id = f"l3-real-20260730{suffix}"
            self._write_raw_historical_run(run_id, configured_role=True)
            evidence = launcher.raw_verified_modeling_child(launcher.RUNTIME_ROOT / run_id)
            self.assertEqual(evidence["coordinator_thread_id"], f"coordinator-{run_id}")
            self.assertEqual(evidence["modeling_agent_thread_id"], f"child-{run_id}")

    def test_raw_rollout_audit_rejects_g_linked_child_without_agent_type(self) -> None:
        run_id = "l3-real-20260730g"
        self._write_raw_historical_run(run_id, configured_role=False)
        with self.assertRaisesRegex(launcher.L3Error, "agent_type=modeling_agent"):
            launcher.raw_verified_modeling_child(launcher.RUNTIME_ROOT / run_id)

    def test_raw_rollout_audit_rejects_transcript_only_evidence(self) -> None:
        root = launcher.RUNTIME_ROOT / "l3-transcript-only"
        (root / "audit").mkdir(parents=True)
        (root / "audit" / "coordinator.jsonl").write_text('{"type":"thread.started","thread_id":"coordinator"}\n', encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "raw coordinator rollout directory"):
            launcher.raw_verified_modeling_child(root)

    def test_modeling_quality_terminal_blocks_fifth_start_before_resources(self) -> None:
        at = launcher.first_modeling_deadline() - timedelta(seconds=1)
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=3, max_starts=5, run_ids=list(launcher.HISTORICAL_RUN_IDS))
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps({"event": "historical_coordinator_started", "run_id": run_id}) + "\n" for run_id in launcher.HISTORICAL_RUN_IDS), encoding="utf-8")
        launcher.reserve_coordinator_start("l3-four", at)
        launcher.record_terminal_outcome("l3-four", "modeling-quality")
        with self.assertRaisesRegex(launcher.L3Error, "modeling-quality failure"):
            launcher.reserve_coordinator_start("l3-five", at)

    def test_start_five_requires_repairable_start_four_terminal_outcome(self) -> None:
        at = launcher.first_modeling_deadline() - timedelta(seconds=1)
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=3, max_starts=5, run_ids=list(launcher.HISTORICAL_RUN_IDS))
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps({"event": "historical_coordinator_started", "run_id": run_id}) + "\n" for run_id in launcher.HISTORICAL_RUN_IDS), encoding="utf-8")
        launcher.reserve_coordinator_start("l3-four", at)
        with self.assertRaisesRegex(launcher.L3Error, "requires a repairable"):
            launcher.reserve_coordinator_start("l3-five", at)
        launcher.record_terminal_outcome("l3-four", "runtime/infrastructure")
        self.assertEqual(launcher.reserve_coordinator_start("l3-five", at)["run_id"], "l3-five")

    def test_current_recovery_start_four_uses_policy_handoff_without_stale_halt(self) -> None:
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=3, max_starts=5, run_ids=list(launcher.HISTORICAL_RUN_IDS))
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps({"event": "historical_coordinator_started", "run_id": run_id}) + "\n" for run_id in launcher.HISTORICAL_RUN_IDS), encoding="utf-8")
        event = launcher.reserve_coordinator_start("l3-four", datetime.now(launcher.first_modeling_deadline().tzinfo))
        self.assertEqual(event["preparation_started_at"], self.recovery_preparation_started_at)
        self.assertNotIn("preparation_halted", [item["event"] for item in launcher._read_jsonl(launcher.GLOBAL_LEDGER)])

    def test_recovery_wait_marker_is_append_only_corrected_to_collaboration_routing(self) -> None:
        root = launcher.RUNTIME_ROOT / launcher.RECOVERY_RUN_ID
        (root / "audit").mkdir(parents=True)
        (root / "team-work").mkdir()
        state_path = root / "audit" / "state.json"
        transcript_path = root / "audit" / "coordinator-resume-1.jsonl"
        raw_state = {
            "run_id": launcher.RECOVERY_RUN_ID,
            "state": "PAUSED",
            "outcome": "NOT_PASSED",
            "category": "platform-contract",
            "terminal_outcome": {"event": "terminal_outcome", "category": "platform-contract", "outcome": "NOT_PASSED"},
        }
        state_path.write_text(json.dumps(raw_state), encoding="utf-8")
        transcript_path.write_text('{"item":{"text":"L3_WAITING_FOR_ANSWER"}}\n', encoding="utf-8")

        first = launcher.local_scenario_status()
        original_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")
        second = launcher.local_scenario_status()
        correction = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)[0]

        self.assertEqual(first["category"], "collaboration/routing")
        self.assertEqual(second["terminal_correction_count"], 1)
        self.assertEqual(original_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(correction["original"]["category"], "platform-contract")
        self.assertEqual(correction["authoritative"]["category"], "collaboration/routing")
        self.assertEqual(correction["evidence"]["state_sha256"], launcher.sha256_path(state_path))
        self.assertEqual(correction["evidence"]["transcript_sha256"], launcher.sha256_path(transcript_path))

        transcript_path.write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "recovery terminal .*drift"):
            launcher.local_scenario_status()

    def test_terminal_marker_ignores_command_output_and_matches_exact_agent_message(self) -> None:
        transcript = self.root / "coordinator.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "item": {
                                "type": "command_execution",
                                "text": "task file contains L3_WAITING_FOR_ANSWER",
                            }
                        }
                    ),
                    json.dumps(
                        {
                            "item": {
                                "type": "agent_message",
                                "text": "L3_COORDINATOR_DISPATCHED",
                            }
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertFalse(launcher._exact_agent_message_marker(transcript, "L3_WAITING_FOR_ANSWER"))
        self.assertTrue(launcher._exact_agent_message_marker(transcript, "L3_COORDINATOR_DISPATCHED"))

    def test_duplicate_gate_recovery_is_append_only_waiting_and_hash_bound(self) -> None:
        state_path, transcript_path, pending, events = self._write_raw_recovery_waiting_run()
        raw_state = state_path.read_bytes()
        raw_transcript = transcript_path.read_bytes()
        raw_pending = pending.read_bytes()

        first = launcher.local_scenario_status()
        original_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")
        second = launcher.local_scenario_status()
        correction = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)[0]

        self.assertEqual(first["state"], "WAITING_FOR_ANSWER")
        self.assertEqual(first["outcome"], "PENDING")
        self.assertFalse(first["halted"])
        self.assertEqual(second["recovery_correction_count"], 1)
        self.assertEqual(original_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(correction["authoritative"]["modeling_started"]["coordinator_thread_id"], "coordinator-l3-real-20260730k")
        self.assertEqual(correction["evidence"]["state_sha256"], launcher.sha256_path(state_path))
        self.assertEqual(correction["evidence"]["transcript_sha256"], launcher.sha256_path(transcript_path))
        self.assertEqual(correction["evidence"]["pending_question_sha256"], launcher.sha256_path(pending))
        self.assertEqual(correction["supersedes"]["preparation_halted_sha256"], launcher._event_sha256(events[1]))
        self.assertEqual(correction["supersedes"]["terminal_outcome_sha256"], launcher._event_sha256(events[2]))
        self.assertEqual(raw_state, state_path.read_bytes())
        self.assertEqual(raw_transcript, transcript_path.read_bytes())
        self.assertEqual(raw_pending, pending.read_bytes())

        pending.write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "recovery waiting raw role-contract evidence drift"):
            launcher.local_scenario_status()

    def test_continue_accepts_corrected_waiting_state_without_rewriting_raw_or_releasing_answer(self) -> None:
        state_path, _transcript_path, _pending, _events = self._write_raw_recovery_waiting_run()
        raw_state = state_path.read_bytes()

        state = launcher.continue_run(launcher.RECOVERY_WAIT_RUN_ID, execute=True)

        self.assertEqual(state["state"], "WAITING_FOR_ANSWER")
        self.assertEqual(state["outcome"], "PENDING")
        self.assertEqual(raw_state, state_path.read_bytes())
        self.assertFalse((state_path.parent / "coordinator-resume-1.jsonl").exists())

    def test_recovery_snapshot_survives_release_and_resumes_the_same_coordinator(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work = pending.parent
        raw_state = state_path.read_bytes()
        launcher.local_scenario_status()

        launcher._snapshot_recovery_pending_question(work)
        snapshot_path = state_path.parent / "pending-question-before-release.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_bytes = snapshot_path.read_bytes()
        self.assertEqual(snapshot["coordinator_thread_id"], "coordinator-l3-real-20260730k")
        self.assertEqual(snapshot["pending_question_sha256"], launcher.sha256_path(pending))
        self.assertEqual(launcher.local_scenario_status()["state"], "WAITING_FOR_ANSWER")
        revision_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")

        launcher.release_answer(work, "invocation-target")
        self.assertFalse(pending.exists())
        self.assertEqual(snapshot_bytes, snapshot_path.read_bytes())
        self.assertEqual(revision_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(launcher.local_scenario_status()["state"], "WAITING_FOR_ANSWER")
        self.assertEqual(revision_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))

        coordinator_id = snapshot["coordinator_thread_id"]
        executable, auth = self.root / "codex", self.root / "auth.json"
        executable.write_text("placeholder", encoding="utf-8")
        auth.write_text("{}", encoding="utf-8")
        with patch.object(launcher, "CODEX_BINARY", executable), patch.object(launcher, "HOST_CODEX_AUTH", auth), patch.object(launcher, "_execute_command", return_value={"thread_id": coordinator_id}) as resume, patch.object(launcher, "_candidate_and_dispatch", return_value=({"candidate": "model"}, {"task_id": "l3"})), patch.object(launcher, "_apply_protocol") as apply, patch.object(launcher, "_persist_recovery_success"):
            state = launcher.continue_run(launcher.RECOVERY_WAIT_RUN_ID, execute=True)

        self.assertIn(coordinator_id, resume.call_args.args[0])
        self.assertEqual(state["state"], "PASS")
        apply.assert_called_once()
        self.assertEqual(raw_state, state_path.read_bytes())

    def test_recovery_snapshot_and_released_answer_drift_fail_closed(self) -> None:
        _state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work = pending.parent
        launcher._snapshot_recovery_pending_question(work)
        snapshot_path = work.parent / "audit" / "pending-question-before-release.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["coordinator_thread_id"] = "different-coordinator"
        snapshot_path.chmod(0o600)
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "snapshot evidence drift"):
            launcher.local_scenario_status()

    def test_recovery_released_answer_drift_fails_closed(self) -> None:
        _state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work = pending.parent
        launcher.release_answer(work, "invocation-target")
        released = work / "released-answer.json"
        value = json.loads(released.read_text(encoding="utf-8"))
        value["answer"] = "mismatched"
        released.chmod(0o600)
        released.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "released answer does not exactly match"):
            launcher.local_scenario_status()

    def test_recovery_three_question_cycles_preserve_prior_snapshots_and_answers(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work, audit = pending.parent, state_path.parent
        coordinator_id = json.loads(state_path.read_text(encoding="utf-8"))["coordinator"]["coordinator_thread_id"]
        launcher.release_answer(work, "invocation-target")
        for index, answer_id in ((2, "output-continuity"), (3, "missing-score-behavior")):
            (audit / f"coordinator-resume-{index}.jsonl").write_text("\n".join((json.dumps({"type": "thread.started", "thread_id": coordinator_id}), json.dumps({"item": {"text": "L3_WAITING_FOR_ANSWER"}}))) + "\n", encoding="utf-8")
            launcher.record_question(work, {"question": f"question {index}", "sources": ["sources/x.md"], "affected_conclusion": f"conclusion {index}"})
            launcher.release_answer(work, answer_id)
        records = [json.loads((audit / f"recovery-cycle-{index}.json").read_text(encoding="utf-8")) for index in (1, 2, 3)]
        self.assertEqual([record["cycle_index"] for record in records], [1, 2, 3])
        self.assertEqual([record["answer"]["answer_id"] for record in records], ["invocation-target", "output-continuity", "missing-score-behavior"])
        self.assertEqual(records[1]["originating_resume_transcript"].rsplit("/", 1)[-1], "coordinator-resume-2.jsonl")

    def test_recovery_second_answer_appends_revision_and_resumes_same_session_three(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work, audit = pending.parent, state_path.parent
        coordinator_id = json.loads(state_path.read_text(encoding="utf-8"))["coordinator"]["coordinator_thread_id"]
        launcher.release_answer(work, "invocation-target")
        (audit / "coordinator-resume-1.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                    json.dumps(
                        {
                            "item": {
                                "text": (
                                    "Unable to continue: the resumed session is read-only, so "
                                    "/work/pending-question.json could not be written atomically."
                                )
                            }
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (audit / "coordinator-resume-1.stderr.log").write_text(
            "patch rejected: writing is blocked by read-only sandbox\n",
            encoding="utf-8",
        )
        launcher.local_scenario_status()
        (audit / "coordinator-resume-2.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                    json.dumps({"item": {"text": "L3_WAITING_FOR_ANSWER"}}),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        launcher.record_question(
            work,
            {
                "question": "Do the two quality fields have continuous meaning?",
                "sources": ["sources/interface-notes.md"],
                "affected_conclusion": "output continuity",
            },
        )
        starts_before = launcher.GLOBAL_LEDGER.read_bytes()
        launcher.release_answer(work, "output-continuity")
        corrections = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)
        recovery = [value for value in corrections if value.get("event") == "recovery_state_correction"]
        latest, previous = recovery[-1], recovery[-2]
        self.assertEqual(latest["previous_correction_id"], previous["correction_id"])
        self.assertEqual(latest["previous_correction_sha256"], launcher._event_sha256(previous))
        self.assertEqual(latest["cycle_count"], 2)
        self.assertEqual(
            latest["cycle_head_sha256"],
            launcher._event_sha256(json.loads((audit / "recovery-cycle-2.json").read_text(encoding="utf-8"))),
        )

        executable, auth = self.root / "codex", self.root / "auth.json"
        executable.write_text("placeholder", encoding="utf-8")
        auth.write_text("{}", encoding="utf-8")
        with patch.object(launcher, "CODEX_BINARY", executable), patch.object(
            launcher, "HOST_CODEX_AUTH", auth
        ), patch.object(
            launcher,
            "_execute_command",
            return_value={"thread_id": coordinator_id},
        ) as resume, patch.object(
            launcher,
            "_candidate_and_dispatch",
            return_value=({"candidate": "model"}, {"task_id": "l3"}),
        ), patch.object(launcher, "_apply_protocol"), patch.object(
            launcher, "_persist_recovery_success"
        ):
            state = launcher.continue_run(launcher.RECOVERY_WAIT_RUN_ID, execute=True)

        self.assertEqual(state["state"], "PASS")
        self.assertIn(coordinator_id, resume.call_args.args[0])
        self.assertEqual(resume.call_args.args[2].name, "coordinator-resume-3.jsonl")
        self.assertEqual(starts_before, launcher.GLOBAL_LEDGER.read_bytes())

    def test_recovery_cycle_and_revision_chain_tampering_fail_closed(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work, audit = pending.parent, state_path.parent
        coordinator_id = json.loads(state_path.read_text(encoding="utf-8"))["coordinator"]["coordinator_thread_id"]
        launcher.release_answer(work, "invocation-target")
        (audit / "coordinator-resume-2.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                    json.dumps({"item": {"text": "L3_WAITING_FOR_ANSWER"}}),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        launcher.record_question(
            work,
            {
                "question": "Do the two quality fields have continuous meaning?",
                "sources": ["sources/interface-notes.md"],
                "affected_conclusion": "output continuity",
            },
        )
        launcher.release_answer(work, "output-continuity")

        cycle_one = json.loads((audit / "recovery-cycle-1.json").read_text(encoding="utf-8"))
        cycle_two_path = audit / "recovery-cycle-2.json"
        cycle_two = json.loads(cycle_two_path.read_text(encoding="utf-8"))
        cycle_two["pending_question_sha256"] = cycle_one["pending_question_sha256"]
        cycle_two_path.chmod(0o600)
        cycle_two_path.write_text(json.dumps(cycle_two), encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "recovery cycle evidence drift"):
            launcher.local_scenario_status()

        # Restore the cycle, then prove the correction's previous-revision link is also enforced.
        cycle_two["pending_question_sha256"] = __import__("hashlib").sha256(
            launcher.canonical_json(cycle_two["pending_question"])
        ).hexdigest()
        cycle_two_path.write_text(json.dumps(cycle_two), encoding="utf-8")
        lines = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8").splitlines()
        latest = json.loads(lines[-1])
        latest["previous_correction_sha256"] = "0" * 64
        lines[-1] = json.dumps(latest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        launcher.CLASSIFICATION_LEDGER.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "recovery correction revision chain drift"):
            launcher.local_scenario_status()

    def test_ready_for_protocol_skips_coordinator_resume_and_uses_existing_dispatch(self) -> None:
        root = self._waiting_run(launcher.RECOVERY_WAIT_RUN_ID)
        raw = json.loads((root / "audit" / "state.json").read_text(encoding="utf-8"))
        ready = {
            **raw,
            "state": "READY_FOR_PROTOCOL",
            "outcome": "PENDING",
            "category": "pending",
        }
        executable, auth = self.root / "codex", self.root / "auth.json"
        executable.write_text("placeholder", encoding="utf-8")
        auth.write_text("{}", encoding="utf-8")
        with patch.object(
            launcher, "_effective_continuation_state", return_value=(ready, True)
        ), patch.object(launcher, "CODEX_BINARY", executable), patch.object(
            launcher, "HOST_CODEX_AUTH", auth
        ), patch.object(launcher, "_execute_command") as resume, patch.object(
            launcher, "_apply_protocol"
        ) as apply, patch.object(launcher, "_persist_recovery_success") as persist:
            state = launcher.continue_run(launcher.RECOVERY_WAIT_RUN_ID, execute=True)

        resume.assert_not_called()
        apply.assert_called_once()
        persist.assert_called_once()
        self.assertEqual(state["state"], "PASS")
        self.assertEqual(state["outcome"], "PASSED")
        self.assertEqual(state["category"], "passed")

    def test_recovery_protocol_success_appends_hash_bound_terminal_revision(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        root, work, audit = state_path.parent.parent, pending.parent, state_path.parent
        coordinator_id = json.loads(state_path.read_text(encoding="utf-8"))["coordinator"][
            "coordinator_thread_id"
        ]
        launcher.release_answer(work, "invocation-target")
        (audit / "coordinator-resume-1.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                    json.dumps(
                        {
                            "item": {
                                "type": "agent_message",
                                "text": "Unable to continue: the resumed session is read-only",
                            }
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (audit / "coordinator-resume-1.stderr.log").write_text(
            "read-only sandbox\n", encoding="utf-8"
        )
        launcher.local_scenario_status()
        for resume_index, answer_id in (
            (2, "output-continuity"),
            (3, "missing-score-behavior"),
        ):
            (audit / f"coordinator-resume-{resume_index}.jsonl").write_text(
                "\n".join(
                    (
                        json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                        json.dumps(
                            {
                                "item": {
                                    "type": "agent_message",
                                    "text": "L3_WAITING_FOR_ANSWER",
                                }
                            }
                        ),
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            launcher.record_question(
                work,
                {
                    "question": f"question {resume_index}",
                    "sources": ["sources/interface-notes.md"],
                    "affected_conclusion": answer_id,
                },
            )
            launcher.release_answer(work, answer_id)
        candidate = {"concept": "validated business model"}
        (work / "approved-candidate.json").write_text(json.dumps(candidate), encoding="utf-8")
        (work / "protocol-dispatch.json").write_text(
            json.dumps(
                {
                    "task_id": "l3",
                    "candidate_sha256": "PENDING_LAUNCHER_CANONICALIZATION",
                    "requested_outcome": "apply_published_c_b_a_path",
                }
            ),
            encoding="utf-8",
        )
        (audit / "coordinator-resume-4.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": coordinator_id}),
                    json.dumps(
                        {
                            "item": {
                                "type": "agent_message",
                                "text": "L3_COORDINATOR_DISPATCHED",
                            }
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(launcher.local_scenario_status()["state"], "READY_FOR_PROTOCOL")
        for name in ("protocol-result", "protocol-rollout-audit", "platform-fact-audit"):
            launcher.atomic_json(audit / f"{name}.json", {"passed": True})
        final_state = {
            **json.loads(state_path.read_text(encoding="utf-8")),
            "state": "PASS",
            "outcome": "PASSED",
            "category": "passed",
            "scope": {"project_id": "project", "ontology_id": "ontology"},
            "protocol_rollout_audit": {"passed": True},
            "platform_fact_audit": {"passed": True},
            "cleanup": {
                "model_key_revoked": True,
                "project_deleted": True,
                "host_admin_revoked": True,
                "isolated_runtime_exited": True,
                "protocol_credentials": {
                    "protocol_home_removed": True,
                    "credential_files_destroyed": 2,
                    "secret_found_after_cleanup": False,
                },
            },
        }
        launcher.atomic_json(launcher._recovery_final_state_path(root), final_state)

        status = launcher.local_scenario_status()
        recovery = [
            value
            for value in launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)
            if value.get("event") == "recovery_state_correction"
        ]
        latest, previous = recovery[-1], recovery[-2]
        self.assertEqual(status["state"], "PASS")
        self.assertEqual(status["outcome"], "PASSED")
        self.assertEqual(latest["correction_id"].split(":", 1)[0][-2:], "v9")
        self.assertEqual(latest["previous_correction_sha256"], launcher._event_sha256(previous))
        self.assertEqual(
            latest["evidence"]["final_state_sha256"],
            launcher.sha256_path(launcher._recovery_final_state_path(root)),
        )

    def test_resume_read_only_harness_revision_is_idempotent_and_next_resume_is_resume_two(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work = pending.parent
        raw_state = state_path.read_bytes()
        launcher.local_scenario_status()
        launcher.release_answer(work, "invocation-target")
        launcher.local_scenario_status()
        global_events = launcher.GLOBAL_LEDGER.read_text(encoding="utf-8")
        coordinator_id = json.loads((state_path.parent / "pending-question-before-release.json").read_text(encoding="utf-8"))["coordinator_thread_id"]
        resume_one = state_path.parent / "coordinator-resume-1.jsonl"
        resume_one.write_text("\n".join((json.dumps({"type": "thread.started", "thread_id": coordinator_id}), json.dumps({"item": {"text": "Unable to continue: the resumed session is read-only, so /work/pending-question.json could not be written atomically."}}))) + "\n", encoding="utf-8")
        resume_one.with_suffix(".stderr.log").write_text("patch rejected: writing is blocked by read-only sandbox\n", encoding="utf-8")

        first = launcher.local_scenario_status()
        revision_ledger = launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8")
        second = launcher.local_scenario_status()
        correction = launcher._read_jsonl(launcher.CLASSIFICATION_LEDGER)[-1]

        self.assertEqual(first["state"], "WAITING_FOR_ANSWER")
        self.assertEqual(second["state"], "WAITING_FOR_ANSWER")
        self.assertEqual(global_events, launcher.GLOBAL_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(revision_ledger, launcher.CLASSIFICATION_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(correction["correction_id"], f"l3-duplicate-first-modeling-gate-correction-v3:{launcher.RECOVERY_WAIT_RUN_ID}")
        self.assertEqual(correction["harness_failure"]["category"], "runtime/infrastructure")
        self.assertEqual(correction["evidence"]["prior_correction_id"], f"l3-duplicate-first-modeling-gate-correction-v2:{launcher.RECOVERY_WAIT_RUN_ID}")

        executable, auth = self.root / "codex", self.root / "auth.json"
        executable.write_text("placeholder", encoding="utf-8")
        auth.write_text("{}", encoding="utf-8")
        with patch.object(launcher, "CODEX_BINARY", executable), patch.object(launcher, "HOST_CODEX_AUTH", auth), patch.object(launcher, "_execute_command", return_value={"thread_id": coordinator_id}) as resume, patch.object(launcher, "_candidate_and_dispatch", return_value=({"candidate": "model"}, {"task_id": "l3"})), patch.object(launcher, "_apply_protocol"), patch.object(launcher, "_persist_recovery_success"):
            state = launcher.continue_run(launcher.RECOVERY_WAIT_RUN_ID, execute=True)

        self.assertEqual(resume.call_args.args[2].name, "coordinator-resume-2.jsonl")
        self.assertEqual(state["state"], "PASS")
        self.assertEqual(raw_state, state_path.read_bytes())

    def test_resume_harness_transcript_drift_fails_closed(self) -> None:
        state_path, _transcript_path, pending, _events = self._write_raw_recovery_waiting_run()
        work = pending.parent
        launcher.local_scenario_status()
        launcher.release_answer(work, "invocation-target")
        launcher.local_scenario_status()
        resume_one = state_path.parent / "coordinator-resume-1.jsonl"
        resume_one.write_text('{"type":"thread.started","thread_id":"wrong"}\n', encoding="utf-8")
        resume_one.with_suffix(".stderr.log").write_text("read-only sandbox\n", encoding="utf-8")

        with self.assertRaisesRegex(launcher.L3Error, "recovery resume harness evidence drift"):
            launcher.local_scenario_status()

    def test_start_five_remains_allowed_after_valid_first_modeling_before_original_deadline(self) -> None:
        preparation = datetime.now().astimezone()
        self._write_policy(
            live_execution_authorized=True,
            state="READY",
            outcome="PENDING",
            category="pending",
            starts_consumed=3,
            max_starts=5,
            run_ids=list(launcher.HISTORICAL_RUN_IDS),
            recovery_preparation_started_at=preparation.isoformat(),
        )
        first_modeling = preparation + timedelta(seconds=1)
        events = [
            *({"event": "historical_coordinator_started", "run_id": run_id} for run_id in launcher.HISTORICAL_RUN_IDS),
            {"event": "coordinator_started", "run_id": launcher.RECOVERY_RUN_ID},
            {
                "event": "modeling_started",
                "run_id": launcher.RECOVERY_RUN_ID,
                "coordinator_thread_id": "coordinator-j",
                "modeling_agent_thread_id": "modeler-j",
                "first_modeling_started_at": first_modeling.isoformat(),
                "preparation_started_at": preparation.isoformat(),
            },
            {"event": "terminal_outcome", "run_id": launcher.RECOVERY_RUN_ID, "category": "platform-contract", "outcome": "NOT_PASSED"},
        ]
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        correction = {
            "event": "terminal_classification_correction",
            "correction_id": f"test-wait-marker:{launcher.RECOVERY_RUN_ID}",
            "run_id": launcher.RECOVERY_RUN_ID,
            "authoritative": {"category": "collaboration/routing"},
        }
        launcher.CLASSIFICATION_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.CLASSIFICATION_LEDGER.write_text(json.dumps(correction) + "\n", encoding="utf-8")
        self.assertEqual(launcher._authoritative_terminal_category(launcher.RECOVERY_RUN_ID, events, [correction]), "collaboration/routing")

        start_five = launcher.reserve_coordinator_start("l3-five", preparation + timedelta(minutes=21))

        self.assertEqual(start_five["run_id"], "l3-five")
        self.assertNotIn("preparation_halted", [event["event"] for event in launcher._read_jsonl(launcher.GLOBAL_LEDGER)])

    def test_start_five_still_halts_after_deadline_without_valid_first_modeling(self) -> None:
        preparation = datetime.now().astimezone()
        self._write_policy(
            live_execution_authorized=True,
            state="READY",
            outcome="PENDING",
            category="pending",
            starts_consumed=3,
            max_starts=5,
            run_ids=list(launcher.HISTORICAL_RUN_IDS),
            recovery_preparation_started_at=preparation.isoformat(),
        )
        events = [
            *({"event": "historical_coordinator_started", "run_id": run_id} for run_id in launcher.HISTORICAL_RUN_IDS),
            {"event": "coordinator_started", "run_id": launcher.RECOVERY_RUN_ID},
            {"event": "terminal_outcome", "run_id": launcher.RECOVERY_RUN_ID, "category": "collaboration/routing", "outcome": "NOT_PASSED"},
        ]
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True)
        launcher.GLOBAL_LEDGER.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

        with self.assertRaisesRegex(launcher.L3Error, "20-minute first-modeling gate missed"):
            launcher.reserve_coordinator_start("l3-five", preparation + timedelta(minutes=21))

        self.assertEqual(launcher._read_jsonl(launcher.GLOBAL_LEDGER)[-1]["event"], "preparation_halted")

    def test_later_modeling_delegation_skips_duplicate_deadline_after_valid_first_modeling(self) -> None:
        preparation = datetime.now().astimezone()
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, max_starts=5, run_ids=[], recovery_preparation_started_at=preparation.isoformat())
        launcher.reserve_coordinator_start("l3-first", preparation + timedelta(seconds=1))
        launcher.record_modeling_delegation("l3-first", "coordinator-first", "modeler-first", preparation + timedelta(seconds=2))
        launcher.reserve_coordinator_start("l3-later", preparation + timedelta(seconds=3))

        event = launcher.record_modeling_delegation("l3-later", "coordinator-later", "modeler-later", preparation + timedelta(minutes=21))

        self.assertEqual(event["run_id"], "l3-later")
        self.assertNotIn("preparation_halted", [entry["event"] for entry in launcher._read_jsonl(launcher.GLOBAL_LEDGER)])

    def test_first_modeling_delegation_after_deadline_still_halts_without_prior_valid_modeling(self) -> None:
        preparation = datetime.now().astimezone()
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, max_starts=5, run_ids=[], recovery_preparation_started_at=preparation.isoformat())
        launcher.reserve_coordinator_start("l3-first", preparation + timedelta(seconds=1))

        with self.assertRaisesRegex(launcher.L3Error, "20-minute first-modeling gate missed"):
            launcher.record_modeling_delegation("l3-first", "coordinator-first", "modeler-first", preparation + timedelta(minutes=21))

        self.assertEqual(launcher._read_jsonl(launcher.GLOBAL_LEDGER)[-1]["event"], "preparation_halted")

    def test_policy_rejects_missing_or_timezone_free_recovery_handoff_timestamp(self) -> None:
        self._write_policy(live_execution_authorized=True, state="READY", outcome="PENDING", category="pending", starts_consumed=0, max_starts=5, run_ids=[], recovery_preparation_started_at="2026-07-30T14:42:13")
        with self.assertRaisesRegex(launcher.L3Error, "timezone"):
            launcher.read_execution_policy()

    def test_continuation_resumes_exact_recorded_coordinator_then_applies_dispatch(self) -> None:
        self._waiting_run()
        with patch.object(launcher, "_execute_command", return_value={"thread_id": "coordinator-thread"}), patch.object(launcher, "_apply_protocol") as apply:
            state = launcher.continue_run("l3-wait", execute=True)
        self.assertEqual(state["state"], "PASS")
        apply.assert_called_once()

    def test_continuation_stops_non_terminal_for_one_new_question_cycle(self) -> None:
        root = self._waiting_run()
        (root / "team-work" / "approved-candidate.json").unlink()
        (root / "team-work" / "protocol-dispatch.json").unlink()

        def write_pending(*_args: object, **_kwargs: object) -> dict[str, object]:
            (root / "team-work" / "pending-question.json").write_text(json.dumps({"question": "Which?", "sources": ["sources/release-register.md"], "affected_conclusion": "x"}), encoding="utf-8")
            return {"thread_id": "coordinator-thread"}

        with patch.object(launcher, "_execute_command", side_effect=write_pending), patch.object(launcher, "_apply_protocol") as apply:
            state = launcher.continue_run("l3-wait", execute=True)
        self.assertEqual(state["state"], "WAITING_FOR_COORDINATOR_OUTPUT")
        apply.assert_not_called()

    def test_continuation_wait_marker_without_pending_question_is_collaboration_routing(self) -> None:
        root = self._waiting_run()
        (root / "team-work" / "approved-candidate.json").unlink()
        (root / "team-work" / "protocol-dispatch.json").unlink()
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text(json.dumps({"event": "coordinator_started", "run_id": "l3-wait"}) + "\n", encoding="utf-8")

        def write_wait_marker(_command: list[str], _prompt: str, transcript: Path, _role: str) -> dict[str, str]:
            transcript.write_text('{"item":{"text":"L3_WAITING_FOR_ANSWER"}}\n', encoding="utf-8")
            return {"thread_id": "coordinator-thread"}

        with patch.object(launcher, "_execute_command", side_effect=write_wait_marker):
            with self.assertRaisesRegex(launcher.L3Error, "L3_WAITING_FOR_ANSWER without"):
                launcher.continue_run("l3-wait", execute=True)
        state = json.loads((root / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["category"], "collaboration/routing")
        self.assertIn("L3_WAITING_FOR_ANSWER", (root / "audit" / "coordinator-resume-1.jsonl").read_text(encoding="utf-8"))

    def test_continuation_rejects_wrong_resumed_identity_and_records_terminal_category(self) -> None:
        self._waiting_run()
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text(json.dumps({"event": "coordinator_started", "run_id": "l3-wait"}) + "\n", encoding="utf-8")
        with patch.object(launcher, "_execute_command", return_value={"thread_id": "different-thread"}):
            with self.assertRaisesRegex(launcher.L3Error, "did not resume"):
                launcher.continue_run("l3-wait", execute=True)
        state = json.loads((launcher.RUNTIME_ROOT / "l3-wait" / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["category"], "collaboration/routing")
        self.assertEqual(launcher._read_jsonl(launcher.GLOBAL_LEDGER)[-1]["event"], "terminal_outcome")

    def test_continuation_preserves_coordinator_runtime_failure_category(self) -> None:
        self._waiting_run()
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text(json.dumps({"event": "coordinator_started", "run_id": "l3-wait"}) + "\n", encoding="utf-8")
        with patch.object(launcher, "_execute_command", side_effect=launcher.L3Error("coordinator runtime/infrastructure: terminal_timeout")):
            with self.assertRaisesRegex(launcher.L3Error, "runtime/infrastructure"):
                launcher.continue_run("l3-wait", execute=True)
        state = json.loads((launcher.RUNTIME_ROOT / "l3-wait" / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["category"], "runtime/infrastructure")

    def test_continuation_preserves_protocol_runtime_failure_category(self) -> None:
        self._waiting_run()
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text(json.dumps({"event": "coordinator_started", "run_id": "l3-wait"}) + "\n", encoding="utf-8")
        with patch.object(launcher, "_execute_command", return_value={"thread_id": "coordinator-thread"}), patch.object(launcher, "_apply_protocol", side_effect=launcher.L3Error("protocol runtime/infrastructure: exit_1")):
            with self.assertRaisesRegex(launcher.L3Error, "runtime/infrastructure"):
                launcher.continue_run("l3-wait", execute=True)
        state = json.loads((launcher.RUNTIME_ROOT / "l3-wait" / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["category"], "runtime/infrastructure")

    def test_continuation_preserves_isolated_rest_process_exit_category(self) -> None:
        self._waiting_run()
        launcher.GLOBAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        launcher.GLOBAL_LEDGER.write_text(json.dumps({"event": "coordinator_started", "run_id": "l3-wait"}) + "\n", encoding="utf-8")
        with patch.object(launcher, "_execute_command", return_value={"thread_id": "coordinator-thread"}), patch.object(launcher, "_apply_protocol", side_effect=launcher.L3Error("isolated application REST exited before health")):
            with self.assertRaisesRegex(launcher.L3Error, "exited before health"):
                launcher.continue_run("l3-wait", execute=True)
        state = json.loads((launcher.RUNTIME_ROOT / "l3-wait" / "audit" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["category"], "runtime/infrastructure")

    def test_dispatch_integrity_rejects_noncanonical_marker(self) -> None:
        root = self._waiting_run()
        (root / "team-work" / "protocol-dispatch.json").write_text(json.dumps({"task_id": "l3", "candidate_sha256": "wrong", "requested_outcome": "apply_published_c_b_a_path"}), encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "dispatch integrity"):
            launcher._candidate_and_dispatch(root / "team-work")

    def test_protocol_rollout_audit_allows_only_protocol_mcp_contract(self) -> None:
        transcript = self.root / "protocol.jsonl"
        calls = ["check_platform_health", "create_build_session", "acquire_ontology_lease", "submit_modeling_batch", "complete_build_session"]
        transcript.write_text("\n".join(json.dumps({"item": {"type": "mcp_tool_call", "server": "ontology_platform", "tool": tool}}) for tool in calls) + "\n", encoding="utf-8")
        self.assertEqual(launcher._audit_protocol_rollout(transcript)["protocol_mcp_tools"], sorted(calls))

    def test_platform_fact_audit_verifies_every_applied_batch(self) -> None:
        applied_ids = ["schema-batch", "entity-batch", "relation-batch"]
        result = {
            "build_session_id": "session",
            "batches": {
                "applied": [{"batch_id": batch_id} for batch_id in applied_ids],
                "invalid_dry_run": {"batch_id": "invalid-batch"},
            },
        }

        def platform_response(
            _base: str,
            _method: str,
            path: str,
            _body: object = None,
            _key: str | None = None,
            **_kwargs: object,
        ) -> dict[str, object]:
            if path == "/api/build-sessions/session":
                return {
                    "status": 200,
                    "body": {
                        "session": {"status": "completed"},
                        "leases": [{"ontology_id": "ontology", "state": "released"}],
                    },
                }
            batch_id = path.rsplit("/", 1)[-1]
            return {
                "status": 200,
                "body": {
                    "ontology_id": "ontology",
                    "batch_status": (
                        "validation_failed" if batch_id == "invalid-batch" else "applied"
                    ),
                },
            }

        with patch.object(launcher, "http", side_effect=platform_response):
            audit = launcher._audit_platform_facts(
                "http://platform",
                "admin-key",
                {"ontology_id": "ontology"},
                result,
            )

        self.assertEqual(audit["applied_batches"], applied_ids)
        self.assertEqual(audit["invalid_batch"], "invalid-batch")

    def test_protocol_credential_home_is_destroyed_and_exact_secret_absent_after_cleanup(self) -> None:
        root = self.root / "run"
        home = root / "protocol-home"
        home.mkdir(parents=True)
        secret = "model-key-secret"
        (home / "config.toml").write_text(f"ONTOLOGY_MCP_API_KEY = {secret}", encoding="utf-8")
        (home / "auth.json").write_text("provider-auth", encoding="utf-8")
        (root / "audit").mkdir()
        (root / "audit" / "protocol.jsonl").write_text("redacted rollout", encoding="utf-8")
        receipt = launcher._destroy_protocol_home(root, secret)
        self.assertTrue(receipt["protocol_home_removed"])
        self.assertFalse(receipt["secret_found_after_cleanup"])
        self.assertFalse(home.exists())
        self.assertNotIn(secret, "".join(path.read_text(encoding="utf-8") for path in root.rglob("*") if path.is_file()))

    def test_protocol_credential_cleanup_rejects_secret_leak_outside_destroyed_home(self) -> None:
        root = self.root / "run"
        home = root / "protocol-home"
        home.mkdir(parents=True)
        secret = "model-key-secret"
        (home / "config.toml").write_text(secret, encoding="utf-8")
        (root / "audit").mkdir()
        (root / "audit" / "leak.txt").write_text(secret, encoding="utf-8")
        with self.assertRaisesRegex(launcher.L3Error, "retained run-local artifacts"):
            launcher._destroy_protocol_home(root, secret)

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
        prompt = (launcher.SCENARIO_ROOT / "protocol-agent-prompt.md").read_text(encoding="utf-8")
        self.assertIn("credential-proof.json", prompt)
        self.assertIn("Do not repeat the no-key probe", prompt)

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
