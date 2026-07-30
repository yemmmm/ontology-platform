from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

import run_l1 as launcher  # noqa: E402


class L1LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _paths(self) -> dict[str, Path]:
        paths = launcher.paths_for(self.root / "run")
        for name in ("coordinator_input", "protocol_input", "coordinator_work", "protocol_work", "coordinator_home", "protocol_home"):
            paths[name].mkdir(parents=True, exist_ok=True)
        return paths

    def test_manifest_stages_only_declared_pinned_inputs_read_only(self) -> None:
        manifest = launcher.read_manifest()
        stage = self.root / "stage"
        evidence = launcher.stage_input(manifest, stage)
        self.assertEqual(
            set(evidence["files"]),
            {"coordinator-task.md", "official/version-control.mdx", "public-protocol.md"},
        )
        self.assertEqual(
            {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()},
            set(evidence["files"]),
        )
        self.assertEqual(stat.S_IMODE((stage / "official/version-control.mdx").stat().st_mode), 0o444)
        self.assertEqual(
            launcher.sha256(stage / "official/version-control.mdx"),
            launcher.sha256(launcher.SNAPSHOT_SOURCE),
        )

    def test_manifest_rejects_extra_file_and_source_hash_drift(self) -> None:
        copied = self.root / "agent-input"
        shutil.copytree(launcher.AGENT_INPUT, copied)
        (copied / "surprise.txt").write_text("not declared", encoding="utf-8")
        original = launcher.AGENT_INPUT
        launcher.AGENT_INPUT = copied
        try:
            with self.assertRaisesRegex(launcher.L1Error, "set differs"):
                launcher.read_manifest()
        finally:
            launcher.AGENT_INPUT = original

    def test_coordinator_namespace_has_no_backend_or_protocol_mount(self) -> None:
        paths = self._paths()
        with patch.object(launcher, "_runtime_root", return_value=self.root / "venv"):
            command = launcher._bwrap_base(
                paths,
                role="coordinator",
                command=["/bin/true"],
                settings={
                    "DATABASE_URL": "postgresql://must-not-enter-coordinator",
                    "OXIGRAPH_URL": "http://must-not-enter-coordinator",
                    "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                },
            )
        text = " ".join(command)
        self.assertIn("/opt", text)
        self.assertIn("/work", text)
        self.assertNotIn("/backend/app", text)
        self.assertNotIn(f"--ro-bind {launcher.REPOSITORY_ROOT} {launcher.REPOSITORY_ROOT}", text)
        self.assertNotIn("protocol-codex-home", text)
        self.assertNotIn("DATABASE_URL", text)
        self.assertNotIn("OXIGRAPH_URL", text)
        self.assertNotIn("SEMANTIC_PRODUCT_WRITE_MODE", text)

    def test_protocol_namespace_mounts_only_app_not_backend_dotenv_or_repository(self) -> None:
        paths = self._paths()
        with patch.object(launcher, "_runtime_root", return_value=self.root / "venv"):
            command = launcher._bwrap_base(paths, role="protocol", command=["/bin/true"], settings={})
        text = " ".join(command)
        self.assertIn("/backend/app", text)
        self.assertNotIn(f"--ro-bind {launcher.BACKEND_ROOT} /backend", text)
        self.assertNotIn("/backend/.env", text)
        self.assertNotIn(f"--ro-bind {launcher.REPOSITORY_ROOT} {launcher.REPOSITORY_ROOT}", text)
        self.assertNotIn("coordinator-codex-home", text)

    def test_protocol_config_has_scoped_mcp_and_coordinator_role_configs_have_none(self) -> None:
        protocol_home = self.root / "protocol-home"
        launcher.write_protocol_config(protocol_home, "run-model-key", {"DATABASE_URL": "postgresql://test"})
        config = (protocol_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.ontology_platform]", config)
        self.assertIn('cwd = "/backend"', config)
        self.assertIn('default_tools_approval_mode = "approve"', config)
        self.assertIn("run-model-key", config)
        for tool in launcher.PROTOCOL_TOOLS:
            self.assertIn(json.dumps(tool), config)
        for role_config in launcher.AGENT_CONFIG.glob("*.toml"):
            self.assertNotIn("mcp_servers", role_config.read_text(encoding="utf-8"))

    def test_dispatch_rejects_items_and_hash_drift(self) -> None:
        candidate = {
            "business_question": "draft versus latest",
            "synthetic_workflow": "SyntheticReleaseWorkflow",
            "concepts": ["Workflow", "WorkflowVersion"],
            "states": ["current draft", "latest version"],
            "minimum_constraint": "one workflow and one state classification",
        }
        dispatch = {
            "task_id": "l1-task",
            "candidate_sha256": launcher.hashlib.sha256(launcher.canonical_json(candidate)).hexdigest(),
            "requested_outcome": "apply_version_state",
        }
        work = self.root / "work"
        work.mkdir()
        (work / "approved-candidate.json").write_text(json.dumps(candidate), encoding="utf-8")
        (work / "protocol-dispatch.json").write_text(json.dumps(dispatch), encoding="utf-8")
        normalized_candidate, normalized_dispatch = launcher._candidate_and_dispatch(work)
        self.assertEqual(normalized_candidate, candidate)
        self.assertEqual(
            normalized_dispatch["candidate_sha256"],
            launcher.hashlib.sha256(launcher.canonical_json(candidate)).hexdigest(),
        )
        candidate["concepts"] = ["Modeling Items"]
        (work / "approved-candidate.json").write_text(json.dumps(candidate), encoding="utf-8")
        with self.assertRaisesRegex(launcher.L1Error, "leaks"):
            launcher._candidate_and_dispatch(work)

    def test_protocol_result_requires_immutable_transition_negative_dry_run_and_generic_read(self) -> None:
        result = {
            "build_session_id": "session",
            "structural": {
                "dry_run": {"batch_id": "batch-id", "client_batch_id": "batch", "items_sha256": "frozen", "attempt_status": "validated"},
                "apply": {"batch_id": "batch-id", "client_batch_id": "batch", "items_sha256": "frozen", "attempt_status": "applied"},
            },
            "negative_dry_run": {"batch_id": "invalid-id", "attempt_status": "validation_failed", "applied": False},
            "workspace": {"before": "v1", "after": "v2"},
            "read_model": {"generic": True, "draft_latest_distinct": True},
        }
        self.assertEqual(launcher.validate_protocol_result(result), result)
        result["structural"]["apply"]["items_sha256"] = "changed"
        with self.assertRaisesRegex(launcher.L1Error, "candidate drift"):
            launcher.validate_protocol_result(result)

    def test_mcp_missing_run_key_must_fail_authentication(self) -> None:
        paths = self._paths()
        import subprocess

        failed = subprocess.CompletedProcess([], 1, "", "RuntimeError: ONTOLOGY_MCP_API_KEY is required")
        with patch.object(launcher, "_bwrap_base", return_value=["fake"]), patch.object(launcher.subprocess, "run", return_value=failed):
            launcher.probe_mcp_requires_run_key(paths, {"SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary"})
        succeeded = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(launcher, "_bwrap_base", return_value=["fake"]), patch.object(launcher.subprocess, "run", return_value=succeeded):
            with self.assertRaisesRegex(launcher.L1Error, "did not reject"):
                launcher.probe_mcp_requires_run_key(paths, {"SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary"})

    def test_s0_audit_requires_no_write_result_and_distinct_role_evidence(self) -> None:
        paths = self._paths()
        paths["transcripts"].mkdir(exist_ok=True)
        (paths["transcripts"] / "s0.jsonl").write_text(
            '\n'.join((
                '{"type":"thread.started","thread_id":"s0-thread"}',
                '{"type":"response.output_text.delta","delta":"modeling_agent protocol_planning_agent"}',
            )),
            encoding="utf-8",
        )
        sessions = paths["coordinator_home"] / "sessions"
        sessions.mkdir(parents=True)
        for thread_id in ("s0-thread", "modeler-thread", "planner-thread"):
            (sessions / f"{thread_id}.jsonl").write_text(
                json.dumps({"type": "thread.started", "thread_id": thread_id}) + "\n", encoding="utf-8"
            )
        (paths["coordinator_work"] / "s0-result.json").write_text('{"no_platform_write":true}', encoding="utf-8")
        self.assertEqual(launcher.audit_s0(paths)["thread_id"], "s0-thread")
        (paths["coordinator_work"] / "s0-result.json").write_text('{"no_platform_write":false}', encoding="utf-8")
        with self.assertRaisesRegex(launcher.L1Error, "no-write"):
            launcher.audit_s0(paths)

    def test_resume_command_and_closure_require_original_thread_and_marker(self) -> None:
        paths = self._paths()
        paths["transcripts"].mkdir(exist_ok=True)
        (paths["transcripts"] / "s1-coordinator-closure.jsonl").write_text(
            '{"type":"thread.started","thread_id":"coordinator-thread"}\nL1_COORDINATOR_CLOSED\n', encoding="utf-8"
        )
        closure = {
            "task_id": "l1-task",
            "coordinator_thread_id": "coordinator-thread",
            "state": "CLOSED",
            "marker": "L1_COORDINATOR_CLOSED",
        }
        (paths["coordinator_work"] / "coordinator-closure.json").write_text(json.dumps(closure), encoding="utf-8")
        self.assertEqual(launcher.audit_coordinator_closure(paths, "coordinator-thread", "l1-task"), closure)
        self.assertIn("resume", launcher.codex_command("coordinator-thread"))

    def test_agent_execution_streams_jsonl_and_retains_stderr(self) -> None:
        paths = self._paths()
        paths["transcripts"].mkdir(exist_ok=True)
        transcript = paths["transcripts"] / "stream.jsonl"
        command = ["/bin/sh", "-c", "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"stream-thread\"}'; printf 'diagnostic\\n' >&2"]
        with patch.object(launcher, "_bwrap_base", return_value=command):
            result = launcher.execute_agent(paths, "coordinator", "prompt", transcript, {})
        self.assertEqual(result["thread_id"], "stream-thread")
        self.assertIn("thread.started", transcript.read_text(encoding="utf-8"))
        self.assertIn("diagnostic", transcript.with_suffix(".stderr.log").read_text(encoding="utf-8"))

    def test_platform_audit_rejects_self_reported_pass_when_immutable_facts_disagree(self) -> None:
        items = [{"client_item_id": "i1", "command_kind": "create_class", "payload": {}}]
        items_hash = launcher.hashlib.sha256(launcher.canonical_json(items)).hexdigest()
        protocol = {
            "build_session_id": "session", "workspace": {"before": "v1", "after": "v2"},
            "structural": {"dry_run": {"batch_id": "structural", "client_batch_id": "batch", "items_sha256": items_hash, "attempt_status": "validated"}, "apply": {"batch_id": "structural", "client_batch_id": "batch", "items_sha256": items_hash, "attempt_status": "applied"}},
            "negative_dry_run": {"batch_id": "negative", "attempt_status": "validation_failed", "applied": False},
            "read_model": {"generic": True, "draft_latest_distinct": True},
        }
        session = {"session": {"status": "completed"}, "leases": [{"ontology_id": "ontology", "state": "released"}]}
        items.extend([
            {"command_kind": "create_relation", "payload": {"source_entity_iri": "urn:SyntheticReleaseWorkflowCurrentDraft", "target_entity_iri": "urn:CurrentDraft"}},
            {"command_kind": "create_relation", "payload": {"source_entity_iri": "urn:SyntheticReleaseWorkflowLatestVersion", "target_entity_iri": "urn:LatestVersion"}},
        ])
        items_hash = launcher.hashlib.sha256(launcher.canonical_json(items)).hexdigest()
        protocol["structural"]["dry_run"]["items_sha256"] = items_hash
        protocol["structural"]["apply"]["items_sha256"] = items_hash
        structural = {"batch_id": "structural", "build_session_id": "session", "ontology_id": "ontology", "batch_status": "applied", "client_batch_id": "batch", "items": items, "attempts": [{"attempt_status": "validated", "mode": "dry_run"}, {"attempt_status": "applied", "mode": "apply_atomic", "workspace": {"before_version": "v1", "after_version": "v2"}}]}
        negative = {"batch_id": "negative", "build_session_id": "session", "ontology_id": "ontology", "batch_status": "validation_failed", "items": items, "attempts": [{"attempt_status": "validation_failed", "mode": "dry_run"}]}
        generic = {"items": [{"label": "SyntheticReleaseWorkflow"}, {"label": "Current Draft"}, {"label": "Latest Version"}]}
        responses = iter(({"status": 200, "body": session}, {"status": 200, "body": structural}, {"status": 200, "body": negative}, {"status": 200, "body": generic}))
        with patch.object(launcher, "http_request", side_effect=lambda *_args, **_kwargs: next(responses)):
            self.assertTrue(launcher.audit_platform_facts("http://test", "admin", {"ontology_id": "ontology"}, protocol)["generic_read"])
        protocol["structural"]["apply"]["items_sha256"] = "forged"
        responses = iter(({"status": 200, "body": session}, {"status": 200, "body": structural}))
        with patch.object(launcher, "http_request", side_effect=lambda *_args, **_kwargs: next(responses)):
            with self.assertRaisesRegex(launcher.L1Error, "hash"):
                launcher.audit_platform_facts("http://test", "admin", {"ontology_id": "ontology"}, protocol)

    def test_protocol_rollout_requires_allowed_required_tools_and_one_modeling_child(self) -> None:
        paths = self._paths()
        paths["transcripts"].mkdir(exist_ok=True)
        (paths["transcripts"] / "s1-coordinator.jsonl").write_text('{"type":"thread.started","thread_id":"coordinator"}\n', encoding="utf-8")
        calls = "\n".join(json.dumps({"item": {"type": "mcp_tool_call", "server": "ontology_platform", "tool": tool}}) for tool in ("check_platform_health", "get_modeling_context", "create_build_session", "get_build_session", "acquire_ontology_lease", "submit_modeling_batch", "get_modeling_batch", "get_ontology_read_model", "save_build_checkpoint", "complete_build_session"))
        (paths["transcripts"] / "s1-protocol.jsonl").write_text('{"type":"thread.started","thread_id":"protocol"}\n' + calls, encoding="utf-8")
        sessions = paths["coordinator_home"] / "sessions"
        sessions.mkdir(parents=True)
        for thread_id in ("coordinator", "modeler"):
            (sessions / f"{thread_id}.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": thread_id}) + "\n", encoding="utf-8")
        self.assertEqual(launcher.audit_s1_rollouts(paths, "coordinator", "protocol")["modeling_child_thread_id"], "modeler")

    def test_run_refuses_mutation_without_explicit_execute(self) -> None:
        with self.assertRaisesRegex(launcher.L1Error, "without --execute"):
            launcher.run("l1-safe", execute=False)

    def test_forbidden_scan_rejects_host_key_markers_and_paths(self) -> None:
        artifact = self.root / "artifact.json"
        artifact.write_text(f"{launcher.REPOSITORY_ROOT} sk_admin_secret", encoding="utf-8")
        result = launcher.scan_forbidden([artifact])
        self.assertFalse(result["passed"])
        self.assertEqual(result["forbidden_files"], [str(artifact)])


if __name__ == "__main__":
    unittest.main()
