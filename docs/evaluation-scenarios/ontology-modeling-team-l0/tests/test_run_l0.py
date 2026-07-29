from __future__ import annotations

import hashlib
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

import run_l0 as launcher  # noqa: E402


def write_jsonl(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def root_events() -> list[dict[str, object]]:
    return [
        {"type": "thread.started", "thread_id": "coordinator-1"},
        {
            "type": "item.completed",
            "item": {
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "receiver_thread_ids": ["model-child"],
                "arguments": {"agent_type": "modeling_agent", "fork_turns": "none"},
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "receiver_thread_ids": ["protocol-child"],
                "arguments": {"agent_type": "platform_protocol_agent", "fork_turns": "none"},
            },
        },
        {"type": "item.completed", "item": {"type": "agent_message", "text": launcher.NEEDS_ANSWER}},
    ]


def child_events(thread: str, role: str, mcp: bool = False) -> list[dict[str, object]]:
    role_event = {
        "type": "item.completed",
        "item": {"type": "agent_configuration", "agent_type": role, "fork_turns": "none"},
    }
    result: list[dict[str, object]] = [{"type": "thread.started", "thread_id": thread}, role_event]
    if mcp:
        result.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "input": "tools.ontology_platform__check_platform_health({})",
                },
            }
        )
    return result


def codex_mcp_events(thread: str, error: str | None = None) -> list[dict[str, object]]:
    result = child_events(thread, "platform_protocol_agent")
    result.extend(
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "namespace": "mcp__ontology_platform",
                    "name": "check_platform_health",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "invocation": {"server": "ontology_platform", "tool": "check_platform_health"},
                    "result": {"Err": error} if error else {"Ok": {"postgres": True}},
                },
            },
        ]
    )
    return result


class L0LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_manifest_staging_is_exact_and_read_only(self) -> None:
        manifest = launcher.read_manifest()
        staging = self.root / "staging"
        evidence = launcher.stage_agent_input(manifest, staging)
        self.assertEqual({item["path"] for item in evidence["files"]}, {"coordinator-task.md", "modeling-source.md"})
        self.assertEqual(
            {path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()},
            {"manifest.json", "coordinator-task.md", "modeling-source.md"},
        )

    def test_manifest_rejects_extra_file_and_hash_drift(self) -> None:
        copied = self.root / "agent-input"
        shutil.copytree(launcher.AGENT_INPUT, copied)
        (copied / "unexpected.txt").write_text("no", encoding="utf-8")
        original = launcher.AGENT_INPUT
        launcher.AGENT_INPUT = copied
        try:
            with self.assertRaisesRegex(launcher.L0Error, "file set"):
                launcher.read_manifest()
        finally:
            launcher.AGENT_INPUT = original

    def test_spawn_contract_and_child_rollout_evidence_are_required(self) -> None:
        root = root_events()
        roles = launcher.spawn_contracts(root)
        codex_home = self.root / "codex-home"
        write_jsonl(codex_home / "sessions" / "model.jsonl", child_events("model-child", "modeling_agent"))
        write_jsonl(
            codex_home / "sessions" / "protocol.jsonl",
            child_events("protocol-child", "platform_protocol_agent", mcp=True),
        )
        coordinator = codex_home / "sessions" / "coordinator.jsonl"
        write_jsonl(coordinator, [{"type": "thread.started", "thread_id": "coordinator-1"}])
        evidence = launcher.audit_children(codex_home, roles, coordinator)
        self.assertEqual(evidence["platform_protocol_agent"]["mcp_calls"], ["check_platform_health"])
        self.assertEqual(evidence["modeling_agent"]["mcp_calls"], [])

    def test_raw_codex_rollout_links_spawn_call_to_distinct_child_thread(self) -> None:
        raw = [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "model-call",
                    "arguments": '{"agent_type":"modeling_agent","fork_turns":"none"}',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "protocol-call",
                    "arguments": '{"agent_type":"platform_protocol_agent","fork_turns":"none"}',
                },
            },
            {
                "type": "event_msg",
                "payload": {"type": "sub_agent_activity", "event_id": "model-call", "agent_thread_id": "model-child"},
            },
            {
                "type": "event_msg",
                "payload": {"type": "sub_agent_activity", "event_id": "protocol-call", "agent_thread_id": "protocol-child"},
            },
        ]
        self.assertEqual(
            launcher.spawn_contracts(raw),
            {"modeling_agent": "model-child", "platform_protocol_agent": "protocol-child"},
        )

    def test_root_marker_cannot_substitute_for_missing_child_or_mcp_evidence(self) -> None:
        codex_home = self.root / "codex-home"
        roles = launcher.spawn_contracts(root_events())
        write_jsonl(codex_home / "model.jsonl", child_events("model-child", "modeling_agent"))
        write_jsonl(codex_home / "protocol.jsonl", child_events("protocol-child", "platform_protocol_agent"))
        coordinator = codex_home / "coordinator.jsonl"
        write_jsonl(coordinator, [{"type": "thread.started", "thread_id": "coordinator-1"}])
        with self.assertRaisesRegex(launcher.L0Error, "health MCP"):
            launcher.audit_children(codex_home, roles, coordinator)

    def test_audit_rejects_coordinator_or_modeling_mcp_call(self) -> None:
        codex_home = self.root / "codex-home"
        roles = launcher.spawn_contracts(root_events())
        write_jsonl(codex_home / "model.jsonl", child_events("model-child", "modeling_agent", mcp=True))
        write_jsonl(
            codex_home / "protocol.jsonl",
            child_events("protocol-child", "platform_protocol_agent", mcp=True),
        )
        coordinator = codex_home / "coordinator.jsonl"
        write_jsonl(coordinator, [{"type": "thread.started", "thread_id": "coordinator-1"}])
        with self.assertRaisesRegex(launcher.L0Error, "modeling child"):
            launcher.audit_children(codex_home, roles, coordinator)
        write_jsonl(
            coordinator,
            [{"type": "response_item", "payload": {"type": "custom_tool_call", "input": "ontology_platform"}}],
        )
        with self.assertRaisesRegex(launcher.L0Error, "coordinator"):
            launcher.audit_children(codex_home, roles, coordinator)

    def test_audit_accepts_standard_mcp_function_call_and_rejects_error_result(self) -> None:
        codex_home = self.root / "codex-home"
        roles = launcher.spawn_contracts(root_events())
        write_jsonl(codex_home / "model.jsonl", child_events("model-child", "modeling_agent"))
        protocol = codex_home / "protocol.jsonl"
        write_jsonl(protocol, codex_mcp_events("protocol-child"))
        coordinator = codex_home / "coordinator.jsonl"
        write_jsonl(coordinator, [{"type": "thread.started", "thread_id": "coordinator-1"}])
        evidence = launcher.audit_children(codex_home, roles, coordinator)
        self.assertEqual(evidence["platform_protocol_agent"]["mcp_calls"], ["check_platform_health"])
        write_jsonl(protocol, codex_mcp_events("protocol-child", "user cancelled MCP tool call"))
        with self.assertRaisesRegex(launcher.L0Error, "did not return a real response"):
            launcher.audit_children(codex_home, roles, coordinator)

    def test_root_config_has_the_sole_platform_mcp_and_agent_files_do_not(self) -> None:
        home = self.root / "codex-home"
        home.mkdir()
        launcher.write_run_configuration(home, "temporary-read-key")
        config = (home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.ontology_platform]", config)
        self.assertIn("check_platform_health", config)
        self.assertIn("required = true", config)
        self.assertIn('default_tools_approval_mode = "approve"', config)
        self.assertIn('"--directory", "/backend", "--no-sync"', config)
        for path in (home / "agents").glob("*.toml"):
            self.assertNotIn("mcp_servers", path.read_text(encoding="utf-8"))

    def test_invalid_fork_contract_and_duplicate_roles_fail_closed(self) -> None:
        invalid = root_events()
        invalid[1]["item"]["arguments"]["fork_turns"] = "all"  # type: ignore[index]
        with self.assertRaisesRegex(launcher.L0Error, "explicit role"):
            launcher.spawn_contracts(invalid)
        duplicate = root_events()
        duplicate[2]["item"]["receiver_thread_ids"] = ["model-child"]  # type: ignore[index]
        with self.assertRaisesRegex(launcher.L0Error, "duplicate"):
            launcher.spawn_contracts(duplicate)

    def test_bwrap_mount_set_has_only_required_runtime_and_scenario_paths(self) -> None:
        paths = {name: self.root / name for name in ("staging", "work", "codex_home")}
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        original_binary = launcher.CODEX_BINARY
        launcher.CODEX_BINARY = Path(sys.executable)
        try:
            command = launcher.bwrap_command(paths, ["/bin/true"])
        finally:
            launcher.CODEX_BINARY = original_binary
        text = " ".join(command)
        self.assertIn("/opt", text)
        self.assertIn("/work", text)
        self.assertIn("/codex-home", text)
        runtime_root = (launcher.BACKEND_ROOT / ".venv" / "bin" / "python").resolve().parent.parent
        self.assertIn(f"--ro-bind {runtime_root} {runtime_root}", text)
        self.assertNotIn(str(launcher.SCENARIO_ROOT / "tester-only"), text)
        self.assertNotIn(f"--ro-bind {launcher.REPOSITORY_ROOT} {launcher.REPOSITORY_ROOT}", text)

    def test_start_command_is_persistent_and_resume_reuses_id(self) -> None:
        start = launcher.codex_command()
        resume = launcher.codex_command("coordinator-1")
        self.assertNotIn("--ephemeral", start)
        self.assertIn("--ask-for-approval", start)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", start)
        self.assertEqual(
            resume[:7], ["/codex", "--ask-for-approval", "never", "exec", "resume", "--json", "--skip-git-repo-check"]
        )
        self.assertEqual(resume[-2:], ["coordinator-1", "-"])
        self.assertNotIn("--sandbox", resume)

    def test_strict_config_command_and_placeholder_do_not_start_with_a_real_key(self) -> None:
        self.assertEqual(launcher.strict_config_command(), ["/codex", "--strict-config", "doctor", "--json"])
        self.assertEqual(launcher.STRICT_CONFIG_PLACEHOLDER, "strict-parse-placeholder")

    def test_marker_count_uses_decoded_jsonl_text(self) -> None:
        path = self.root / "transcript.jsonl"
        write_jsonl(path, root_events())
        self.assertEqual(launcher.marker_count(launcher.jsonl_items(path), launcher.NEEDS_ANSWER), 1)

    def test_save_state_can_replace_terminal_state(self) -> None:
        directory = self.root / "run"
        launcher.save_state(directory, {"state": "WAITING_FOR_ANSWER"})
        launcher.save_state(directory, {"state": "COMPLETE"})
        self.assertEqual(json.loads((directory / "audit" / "state.json").read_text())["state"], "COMPLETE")

    def test_write_audit_is_idempotent_read_only_and_normalizes_io_failure(self) -> None:
        directory = self.root / "run"
        path = launcher.write_audit(directory, "final-audit.json", {"round": 1})
        launcher.write_audit(directory, "final-audit.json", {"round": 2})
        self.assertEqual(json.loads(path.read_text()), {"round": 2})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        with patch.object(launcher.os, "write", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(launcher.L0Error, "audit evidence publication failed"):
                launcher.write_audit(directory, "io-failure.json", {"round": 3})

    def test_write_audit_preserves_existing_receipt_after_partial_write_failure(self) -> None:
        directory = self.root / "run"
        path = launcher.write_audit(directory, "final-audit.json", {"round": 1})
        real_write = launcher.os.write
        writes = 0

        def partial_then_fail(descriptor: int, data: bytes) -> int:
            nonlocal writes
            writes += 1
            if writes == 1:
                return real_write(descriptor, data[:1])
            raise OSError("disk unavailable")

        with patch.object(launcher.os, "write", side_effect=partial_then_fail):
            with self.assertRaisesRegex(launcher.L0Error, "audit evidence publication failed"):
                launcher.write_audit(directory, "final-audit.json", {"round": 2})
        self.assertEqual(json.loads(path.read_text()), {"round": 1})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        self.assertEqual(list(path.parent.glob(".final-audit.json.*")), [])

    def test_write_audit_bounds_replace_failure_and_cleans_temp(self) -> None:
        directory = self.root / "run"
        path = launcher.write_audit(directory, "final-audit.json", {"round": 1})
        with patch.object(launcher.os, "replace", side_effect=OSError("replace unavailable")):
            with self.assertRaisesRegex(launcher.L0Error, "audit evidence publication failed"):
                launcher.write_audit(directory, "final-audit.json", {"round": 2})
        self.assertEqual(json.loads(path.read_text()), {"round": 1})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        self.assertEqual(list(path.parent.glob(".final-audit.json.*")), [])

    def test_write_audit_bounds_temp_protection_failure_and_preserves_receipt(self) -> None:
        directory = self.root / "run"
        path = launcher.write_audit(directory, "final-audit.json", {"round": 1})
        with patch.object(launcher.os, "fchmod", side_effect=OSError("chmod unavailable")):
            with self.assertRaisesRegex(launcher.L0Error, "audit evidence publication failed"):
                launcher.write_audit(directory, "final-audit.json", {"round": 2})
        self.assertEqual(json.loads(path.read_text()), {"round": 1})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        self.assertEqual(list(path.parent.glob(".final-audit.json.*")), [])

    def test_secret_and_host_path_scan_fails_closed(self) -> None:
        artifact = self.root / "artifact.jsonl"
        artifact.write_text("secret-value " + str(launcher.REPOSITORY_ROOT), encoding="utf-8")
        result = launcher.scan_forbidden([artifact], "secret-value")
        self.assertFalse(result["passed"])
        self.assertTrue(result["secret_found"])

    def test_audit_rejects_nonterminal_or_unrevoked_run(self) -> None:
        directory = self.root / "run"
        (directory / "audit").mkdir(parents=True)
        (directory / "audit" / "state.json").write_text(
            json.dumps({"state": "WAITING_FOR_ANSWER", "temporary_key": {"key_id": "key", "scopes": "read"}}),
            encoding="utf-8",
        )
        original = launcher.RUNTIME_ROOT
        launcher.RUNTIME_ROOT = self.root
        try:
            with self.assertRaisesRegex(launcher.L0Error, "terminal"):
                launcher.audit("run")
        finally:
            launcher.RUNTIME_ROOT = original

    def test_answer_is_hashed_not_written_to_state(self) -> None:
        answer = "accepted"
        self.assertEqual(hashlib.sha256(answer.encode()).hexdigest(), hashlib.sha256(b"accepted").hexdigest())


if __name__ == "__main__":
    unittest.main()
