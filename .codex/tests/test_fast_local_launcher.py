from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / ".codex" / "fast_local_launcher.py"
SPEC = importlib.util.spec_from_file_location("fast_local_launcher", MODULE_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher
SPEC.loader.exec_module(launcher)
REAL_PROBE = launcher.probe_claude_mcp_isolation


class FakePlatform(BaseHTTPRequestHandler):
    key = "fixture-local-key-value-123456789"
    project_id = "project-fast-fixture"
    posts: list[dict[str, object]] = []
    sessions: dict[str, dict[str, object]] = {}

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_json(self, status: int, value: dict[str, object]) -> None:
        encoded = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return
        prefix = "/api/build-sessions/"
        if self.path.startswith(prefix):
            if self.headers.get("Authorization") != f"Bearer {self.key}":
                self.send_json(401, {"detail": "denied"})
                return
            session_id = self.path[len(prefix) :]
            session = self.sessions.get(session_id)
            if not session:
                self.send_json(404, {"detail": "missing"})
                return
            self.send_json(200, {"session": session})
            return
        self.send_json(404, {})

    def do_POST(self) -> None:
        expected = f"/api/projects/{self.project_id}/build-sessions"
        if self.path != expected:
            self.send_json(404, {})
            return
        if self.headers.get("Authorization") != f"Bearer {self.key}":
            self.send_json(401, {"detail": "denied"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.posts.append(payload)
        client_id = payload["client_session_id"]
        existing = next(
            (value for value in self.sessions.values() if value["client_session_id"] == client_id),
            None,
        )
        if existing:
            self.send_json(200, {"session": existing})
            return
        session_id = f"build-{len(self.sessions) + 1}"
        session = {
            "id": session_id,
            "project_id": self.project_id,
            "client_session_id": client_id,
            "status": "active",
            "revision": 1,
        }
        self.sessions[session_id] = session
        self.send_json(201, {"session": session})


class FastLocalLauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="fast-launcher-test-")
        self.repo = Path(self.temporary.name)
        (self.repo / ".git").mkdir()
        for relative in (
            ".codex/hooks/modeling_harness.py",
            ".codex/hooks/summary.schema.json",
            ".codex/hooks.json",
            ".claude/empty-mcp.json",
            ".claude/ontology-mcp.json",
            ".claude/scenarios/dify-foundations-v1.json",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / relative).read_bytes())
        corpus_relative = (
            "docs/evaluation-corpora/dify-foundations/snapshots/"
            "dify-foundations-2026-07-18-5396c1a/manifest.json"
        )
        corpus = self.repo / corpus_relative
        corpus.parent.mkdir(parents=True, exist_ok=True)
        corpus.write_text("{}\n", encoding="utf-8")

        FakePlatform.posts = []
        FakePlatform.sessions = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakePlatform)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config_relative = "workspaces/ontology-harness/fast-local.json"
        config = self.repo / self.config_relative
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "project_id": FakePlatform.project_id,
                    "api_base_url": f"http://127.0.0.1:{self.server.server_port}/api",
                    "api_key": FakePlatform.key,
                    "terminal_executable": "fake-terminal",
                    "claude_executable": sys.executable,
                }
            ),
            encoding="utf-8",
        )
        self.probe_patch = mock.patch.object(launcher, "probe_claude_mcp_isolation")
        self.probe = self.probe_patch.start()

    def tearDown(self) -> None:
        self.probe_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temporary.cleanup()

    def args(self, **changes: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "config": self.config_relative,
            "scenario": launcher.DEFAULT_SCENARIO,
            "run_id": "fast-launch-12345678",
            "build_session_id": None,
            "replace_active_locator": False,
            "no_launch": True,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def completed(self, returncode: int = 0) -> mock.Mock:
        return mock.Mock(returncode=returncode, stdout="prepared", stderr="")

    def test_no_launch_posts_once_and_emits_isolated_safe_argv(self) -> None:
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed()) as run:
            result = launcher.run(self.args(), self.repo)
        self.assertEqual(len(FakePlatform.posts), 1)
        self.assertFalse(result["launched"])
        self.assertNotIn(FakePlatform.key, json.dumps(result))
        self.assertEqual(run.call_args.args[0][2], "prepare-fast")
        commands = result["commands"]
        user = commands["simulated_user"]
        modeler = commands["modeling_agent"]
        self.assertIn("--strict-mcp-config", user)
        self.assertIn("--strict-mcp-config", modeler)
        self.assertIn("--setting-sources=project", user)
        self.assertIn("--setting-sources=project", modeler)
        self.assertEqual(sum(token.startswith("--mcp-config=") for token in user), 1)
        self.assertEqual(sum(token.startswith("--mcp-config=") for token in modeler), 1)
        self.assertIn("empty-mcp.json", next(token for token in user if token.startswith("--mcp")))
        self.assertIn(
            "ontology-mcp.json", next(token for token in modeler if token.startswith("--mcp"))
        )
        self.assertNotIn("--mcp-config", user)
        self.assertNotIn("--mcp-config", modeler)
        self.assertTrue(user[-1].startswith("Read only the scenario"))
        self.assertTrue(modeler[-1].startswith("Use ontology-platform MCP"))
        self.assertEqual(user[user.index("--session-id") + 1], result["simulated_user_session_id"])
        self.assertEqual(
            modeler[modeler.index("--session-id") + 1], result["modeling_agent_session_id"]
        )

    def test_no_launch_executes_real_harness_preparation(self) -> None:
        result = launcher.run(self.args(run_id="fast-real-prepare1"), self.repo)
        metadata = json.loads(
            (self.repo / "workspaces/ontology-harness/fast-real-prepare1/metadata.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(metadata["preparation_complete"])
        self.assertEqual(metadata["evaluation_profile"], "fast_local")
        self.assertEqual(metadata["build_session_id"], result["build_session_id"])
        self.assertEqual(set(metadata["participants"]), {"simulated_user", "modeling_agent"})

    def test_crash_after_create_reuses_durable_intent_and_identical_payload(self) -> None:
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed(2)):
            with self.assertRaisesRegex(launcher.LauncherError, "recoverable"):
                launcher.run(self.args(run_id="fast-crash-12345678"), self.repo)
        intent_path = (
            self.repo / "workspaces/ontology-harness/launch-intents/fast-crash-12345678.json"
        )
        self.assertTrue(intent_path.is_file())
        first_payload = FakePlatform.posts[0]
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed()):
            result = launcher.run(self.args(run_id="fast-crash-12345678"), self.repo)
        self.assertEqual(len(FakePlatform.posts), 2)
        self.assertEqual(FakePlatform.posts[1], first_payload)
        self.assertEqual(result["build_session_id"], "build-1")
        self.assertEqual(len(FakePlatform.sessions), 1)

        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        intent["create_payload"]["initial_checkpoint"]["current_step"] = "changed"
        intent["intent_hash"] = launcher.sha256_json(
            {key: value for key, value in intent.items() if key != "intent_hash"}
        )
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed()):
            with self.assertRaisesRegex(launcher.LauncherError, "payload has changed"):
                launcher.run(self.args(run_id="fast-crash-12345678"), self.repo)

    def test_active_locator_blocks_before_post_without_explicit_replacement(self) -> None:
        root = self.repo / "workspaces" / "ontology-harness"
        metadata = root / "older-fast-run" / "metadata.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text('{"terminal_state":null}\n', encoding="utf-8")
        (root / "active-run.json").write_text('{"run_id":"older-fast-run"}\n', encoding="utf-8")
        with self.assertRaisesRegex(launcher.LauncherError, "non-terminal"):
            launcher.run(self.args(), self.repo)
        self.assertEqual(FakePlatform.posts, [])
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed()):
            launcher.run(self.args(replace_active_locator=True), self.repo)
        self.assertEqual(len(FakePlatform.posts), 1)

    def test_recovery_requires_active_owned_build_session(self) -> None:
        FakePlatform.sessions = {
            "terminal": {
                "id": "terminal",
                "project_id": FakePlatform.project_id,
                "client_session_id": "terminal",
                "status": "cancelled",
            },
            "foreign": {
                "id": "foreign",
                "project_id": "other-project",
                "client_session_id": "foreign",
                "status": "active",
            },
            "owned": {
                "id": "owned",
                "project_id": FakePlatform.project_id,
                "client_session_id": "owned",
                "status": "active",
            },
        }
        for session_id, message in (
            ("missing", "status 404"),
            ("terminal", "not active"),
            ("foreign", "another Project"),
        ):
            with self.assertRaisesRegex(launcher.LauncherError, message):
                launcher.run(
                    self.args(run_id=f"fast-recover-{session_id}", build_session_id=session_id),
                    self.repo,
                )
        with mock.patch.object(launcher.subprocess, "run", return_value=self.completed()):
            result = launcher.run(
                self.args(run_id="fast-recover-owned1", build_session_id="owned"), self.repo
            )
        self.assertEqual(result["build_session_id"], "owned")
        self.assertEqual(FakePlatform.posts, [])

    def test_gui_launch_uses_two_argv_processes_without_secret(self) -> None:
        processes: list[list[str]] = []
        with (
            mock.patch.object(launcher.subprocess, "run", return_value=self.completed()),
            mock.patch.object(launcher.shutil, "which", side_effect=lambda value: f"/fake/{value}"),
            mock.patch.object(
                launcher.subprocess,
                "Popen",
                side_effect=lambda command, **_kwargs: processes.append(command) or mock.Mock(),
            ),
        ):
            result = launcher.run(self.args(no_launch=False), self.repo)
        self.assertTrue(result["launched"])
        self.assertEqual(len(processes), 2)
        self.assertTrue(all(command[0] == "/fake/fake-terminal" for command in processes))
        serialized = json.dumps(processes)
        self.assertNotIn(FakePlatform.key, serialized)
        self.assertIn("--agent", serialized)
        self.assertIn("--strict-mcp-config", serialized)

    def test_inventory_probe_uses_project_settings_and_exact_server_sets(self) -> None:
        completed = [
            mock.Mock(
                returncode=0,
                stdout=(
                    "\x1b[32mChecking MCP server health...\x1b[0m\n"
                    "ontology-platform: command - ✓ Connected\n"
                ),
                stderr="",
            ),
            mock.Mock(
                returncode=0,
                stdout=("No MCP servers configured. Use `claude mcp add` to add a server.\n"),
                stderr="",
            ),
        ]
        with mock.patch.object(launcher.subprocess, "run", side_effect=completed) as run:
            REAL_PROBE(self.repo, "/fake/claude")
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertIn("--setting-sources=project", command)
            self.assertIn("--strict-mcp-config", command)
            self.assertEqual(sum(token.startswith("--mcp-config=") for token in command), 1)
            self.assertNotIn("--mcp-config", command)
            self.assertEqual(command[-2:], ["mcp", "list"])

    def test_inventory_probe_rejects_shadow_detail_substring_and_failed_state(self) -> None:
        invalid_outputs = (
            "ontology-platform-shadow: command - ✓ Connected\n",
            "other-server: /path/containing/ontology-platform - ✓ Connected\n",
            "ontology-platform: command - ✗ Failed to connect\n",
        )
        for output in invalid_outputs:
            with (
                self.subTest(output_kind=invalid_outputs.index(output)),
                mock.patch.object(
                    launcher.subprocess,
                    "run",
                    return_value=mock.Mock(returncode=0, stdout=output, stderr=""),
                ),
            ):
                with self.assertRaisesRegex(launcher.LauncherError, "cannot prove"):
                    REAL_PROBE(self.repo, "/fake/claude")

    def test_inventory_parser_rejects_unknown_ambiguous_or_mixed_output(self) -> None:
        for output in (
            "ontology-platform: command - ? Maybe\n",
            "unexpected warning with no bounded format\n",
            (
                "No MCP servers configured. Use `claude mcp add` to add a server.\n"
                "ontology-platform: command - ✓ Connected\n"
            ),
        ):
            with self.subTest(output=output):
                with self.assertRaises(launcher.LauncherError):
                    launcher._parse_mcp_inventory(output)

    def test_run_fails_before_http_when_inventory_cannot_be_proven(self) -> None:
        with mock.patch.object(
            launcher,
            "probe_claude_mcp_isolation",
            side_effect=launcher.LauncherError("incompatible runtime"),
        ):
            with self.assertRaisesRegex(launcher.LauncherError, "incompatible"):
                launcher.run(self.args(), self.repo)
        self.assertEqual(FakePlatform.posts, [])
        self.assertEqual(FakePlatform.sessions, {})

    def test_scenario_validation_rejects_missing_corpus_and_secret_like_content(self) -> None:
        scenario = self.repo / launcher.DEFAULT_SCENARIO
        value = json.loads(scenario.read_text(encoding="utf-8"))
        value["corpus"]["path"] = "docs/missing.json"
        scenario.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(launcher.LauncherError, "corpus does not exist"):
            launcher.load_scenario(self.repo, launcher.DEFAULT_SCENARIO)
        value["corpus"]["path"] = (
            "docs/evaluation-corpora/dify-foundations/snapshots/"
            "dify-foundations-2026-07-18-5396c1a/manifest.json"
        )
        value["simulated_user"]["facts"].append("api_key=fixture-secret-value-123456")
        scenario.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(launcher.LauncherError, "secret-like"):
            launcher.load_scenario(self.repo, launcher.DEFAULT_SCENARIO)

    def test_scenario_corpus_accepts_repo_directory_but_json_inputs_require_files(self) -> None:
        scenario_path = self.repo / launcher.DEFAULT_SCENARIO
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        corpus = self.repo / "docs" / "directory-corpus"
        corpus.mkdir(parents=True)
        scenario["corpus"]["path"] = "docs/directory-corpus"
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        _, loaded, _ = launcher.load_scenario(self.repo, launcher.DEFAULT_SCENARIO)
        self.assertEqual(loaded["corpus"]["path"], "docs/directory-corpus")

        config_directory = self.repo / "workspaces" / "config-directory"
        config_directory.mkdir()
        with self.assertRaisesRegex(launcher.LauncherError, "does not exist"):
            launcher.load_config(self.repo, "workspaces/config-directory")
        scenario_directory = self.repo / ".claude" / "scenarios" / "directory"
        scenario_directory.mkdir()
        with self.assertRaisesRegex(launcher.LauncherError, "does not exist"):
            launcher.load_scenario(self.repo, ".claude/scenarios/directory")

        outside = Path(self.temporary.name).parent / "outside-corpus-directory"
        outside.mkdir(exist_ok=True)
        try:
            scenario["corpus"]["path"] = str(outside)
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            with self.assertRaisesRegex(launcher.LauncherError, "inside the repository"):
                launcher.load_scenario(self.repo, launcher.DEFAULT_SCENARIO)
        finally:
            outside.rmdir()


if __name__ == "__main__":
    unittest.main()
