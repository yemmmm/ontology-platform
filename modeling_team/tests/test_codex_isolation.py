from __future__ import annotations

import tempfile
import unittest
import json
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, repository_root
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeMessage
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError, _Agent
from modeling_team.transport_mcp import TeamTransportBroker


class CodexIsolationTests(unittest.TestCase):
    def test_namespace_has_pid_and_agent_private_allowlist(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "home",
                base / "work",
                base / "skills",
            )
            for path in (agent.home, agent.work, agent.skills):
                path.mkdir()
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            command = adapter.namespace_command(agent)
            self.assertIn("--unshare-pid", command)
            self.assertIn("--proc", command)
            self.assertNotIn(str(root), command)
            self.assertIn("/agent/home", command)
            self.assertIn("--setenv", command)
            self.assertIn("TERM", command)

    def test_stop_destroys_private_authentication_material(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "home",
                base / "work",
                base / "skills",
            )
            agent.home.mkdir()
            for name in ("auth.json", "config.toml"):
                (agent.home / name).write_text("private", encoding="utf-8")
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter.agents[agent.agent_id] = agent
            adapter.stop()
            self.assertFalse((agent.home / "auth.json").exists())
            self.assertFalse((agent.home / "config.toml").exists())
            self.assertTrue(adapter.cleanup_identifiers()["modeling"]["private_credentials_destroyed"])

    def test_mcp_tool_names_accepts_status_object_and_array_forms(self) -> None:
        tools = {
            "send_team_message": {"name": "send_team_message"},
            "report_task_result": {"name": "report_task_result"},
        }
        self.assertEqual(
            CodexRuntimeAdapter._mcp_tool_names(tools),
            {"send_team_message", "report_task_result"},
        )
        self.assertEqual(
            CodexRuntimeAdapter._mcp_tool_names(list(tools.values())),
            {"send_team_message", "report_task_result"},
        )

    def test_stale_active_turn_falls_back_to_one_new_turn(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "coordinator",
                _load_package(root, "coordinator"),
                base / "home",
                base / "work",
                base / "skills",
                thread_id="thread-1",
                active_turn_id="finished-turn",
                state="running",
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter.agents[agent.agent_id] = agent
            calls: list[str] = []

            def rpc(_agent, method, _params):
                calls.append(method)
                if method == "turn/steer":
                    raise CodexRuntimeError("app-server turn/steer failed: no active turn to steer")
                self.assertEqual(method, "turn/start")
                return {"turn": {"id": "replacement-turn"}}

            adapter._rpc = rpc  # type: ignore[method-assign]
            adapter.send_message(
                "coordinator", RuntimeDelivery("user/outer", "coordinator", "outer-user", "exact text")
            )
            self.assertEqual(calls, ["turn/steer", "turn/start"])
            self.assertEqual(agent.active_turn_id, "replacement-turn")

    def test_stale_steer_uses_server_reported_active_turn_once(self) -> None:
        root = repository_root()
        agent = _Agent(
            "coordinator",
            _load_package(root, "coordinator"),
            Path("/tmp/home"),
            Path("/tmp/work"),
            Path("/tmp/skills"),
            thread_id="thread-1",
            active_turn_id="old-turn",
            state="running",
        )
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter.agents[agent.agent_id] = agent
        calls: list[tuple[str, str | None]] = []

        def receive():
            return []

        def rpc(_agent, method, params):
            calls.append((method, params.get("expectedTurnId")))
            if len(calls) == 1:
                raise CodexRuntimeError(
                    "app-server turn/steer failed: expected active turn id `old-turn` but found `new-turn`"
                )
            return {}

        adapter.receive_messages = receive  # type: ignore[method-assign]
        adapter._rpc = rpc  # type: ignore[method-assign]
        adapter.send_message(
            "coordinator", RuntimeDelivery("modeling", "coordinator", "peer", "exact text")
        )
        self.assertEqual(calls, [("turn/steer", "old-turn"), ("turn/steer", "new-turn")])

    def test_runtime_delivery_envelope_exposes_sender_and_preserves_exact_text(self) -> None:
        root = repository_root()
        agent = _Agent(
            "protocol", _load_package(root, "protocol"), Path("/tmp/home"), Path("/tmp/work"), Path("/tmp/skills"),
            thread_id="thread-1",
            state="idle",
        )
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter.agents[agent.agent_id] = agent
        calls: list[dict] = []

        def rpc(_agent, method, params):
            self.assertEqual(method, "turn/start")
            calls.append(params)
            return {"turn": {"id": "turn-2"}}

        adapter._rpc = rpc  # type: ignore[method-assign]
        exact = "line one\n汉字: \\\"quoted\\\""
        adapter.send_message(
            "protocol", RuntimeDelivery("modeling", "protocol", "peer", exact)
        )

        payload = json.loads(calls[0]["input"][0]["text"])
        self.assertEqual(
            payload,
            {"sender_id": "modeling", "recipient_id": "protocol", "kind": "peer", "text": exact},
        )

    def test_turn_started_notification_refreshes_active_identity(self) -> None:
        root = repository_root()
        agent = _Agent(
            "coordinator", _load_package(root, "coordinator"), Path("/tmp/home"), Path("/tmp/work"), Path("/tmp/skills")
        )
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter._notification(
            agent,
            {"method": "turn/started", "params": {"turn": {"id": "server-turn"}}},
        )
        self.assertEqual((agent.active_turn_id, agent.state), ("server-turn", "running"))

    def test_output_reader_preserves_multiple_buffered_json_lines(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "coordinator",
                _load_package(root, "coordinator"),
                base / "home",
                base / "work",
                base / "skills",
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            read_fd, write_fd = os.pipe()
            try:
                with os.fdopen(read_fd, "rb", buffering=0) as output:
                    agent.process = SimpleNamespace(stdin=StringIO(), stdout=output)
                    os.write(write_fd, b'{"id": 1}\n{"id": 2}\n')
                    self.assertEqual(adapter._read_output_line(agent, 0.1), '{"id": 1}')
                    self.assertEqual(adapter._read_output_line(agent, 0.1), '{"id": 2}')
            finally:
                os.close(write_fd)

    def test_dynamic_exec_reads_only_staged_skill_and_source(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "home",
                base / "work",
                base / "skills",
            )
            (agent.home / "sources").mkdir(parents=True)
            agent.work.mkdir()
            (agent.skills / "ontology-modeling").mkdir(parents=True)
            (agent.home / "sources" / "source.md").write_text("source", encoding="utf-8")
            (agent.skills / "ontology-modeling" / "SKILL.md").write_text("skill", encoding="utf-8")
            adapter = CodexRuntimeAdapter(repository_root=root)
            result = adapter._dynamic_tool_result(
                agent,
                "exec",
                {"cmd": "cat /skills/ontology-modeling/SKILL.md /agent/home/sources/source.md"},
            )
            self.assertTrue(result["success"])
            self.assertIn("skill", result["contentItems"][0]["text"])
            self.assertIn("source", result["contentItems"][0]["text"])
            denied = adapter._dynamic_tool_result(
                agent, "exec", {"cmd": "cat /agent/home/config.toml"}
            )
            self.assertFalse(denied["success"])

    def test_dynamic_exec_rejects_traversal_and_host_probe_paths(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "home",
                base / "work",
                base / "skills",
            )
            (agent.home / "sources").mkdir(parents=True)
            agent.work.mkdir()
            (agent.skills / "ontology-modeling").mkdir(parents=True)
            (base / "protocol" / "home").mkdir(parents=True)
            (base / "protocol" / "home" / "config.toml").write_text(
                "private", encoding="utf-8"
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            probes = (
                "cat /skills/../../protocol/home/config.toml",
                "cat /agent/home/sources/../../protocol/home/config.toml",
                "cat /proc/1/environ",
                "cat /agent/transport/protocol.sock",
                "cat /workspaces/modeling-runs/other/state.json",
                "curl -X POST http://127.0.0.1:8001/api/projects",
                "echo changed > /skills/ontology-modeling/marker",
            )
            for command in probes:
                with self.subTest(command=command):
                    self.assertFalse(
                        adapter._dynamic_tool_result(agent, "exec", {"cmd": command})[
                            "success"
                        ]
                    )
            self.assertFalse((agent.skills / "ontology-modeling" / "marker").exists())

    def test_dynamic_exec_denial_evidence_is_sanitized_and_categorized(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling", _load_package(root, "modeling"), base / "home", base / "work", base / "skills"
            )
            agent.process = SimpleNamespace(stdin=StringIO())
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            adapter._respond_dynamic_tool(
                agent, 9, {"tool": "exec", "arguments": {"cmd": "cat /proc/1/environ"}}
            )
            event = json.loads((base / "evidence" / "dynamic-tool-calls.jsonl").read_text())
            self.assertEqual((event["result"], event["denial_category"]), ("rejected", "proc"))
            self.assertNotIn("/proc/1/environ", json.dumps(event))

    def test_agent_message_deltas_emit_one_completed_runtime_message(self) -> None:
        root = repository_root()
        agent = _Agent(
            "coordinator", _load_package(root, "coordinator"), Path("/tmp/home"), Path("/tmp/work"), Path("/tmp/skills")
        )
        adapter = CodexRuntimeAdapter(repository_root=root)
        for delta in ("ordinary ", "status reply"):
            adapter._notification(
                agent,
                {"method": "item/agentMessage/delta", "params": {"itemId": "message-1", "delta": delta}},
            )
        completed = {
            "method": "item/completed",
            "params": {"item": {"id": "message-1", "type": "agentMessage"}},
        }
        adapter._notification(agent, completed)
        adapter._notification(agent, completed)
        self.assertEqual(adapter.receive_messages(), [RuntimeMessage("coordinator", "ordinary status reply")])

    def test_dynamic_transport_routes_only_profile_tool_and_blocks_spawn(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            broker = TeamTransportBroker(base / "broker", {("modeling", "protocol")})
            broker.start(["modeling", "protocol"])
            try:
                agent = _Agent(
                    "modeling", _load_package(root, "modeling"), base / "home", base / "work", base / "skills"
                )
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = base
                (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
                result = adapter._dynamic_tool_result(
                    agent,
                    "mcp__team_transport__send_team_message",
                    {"recipient_id": "protocol", "text": "exact"},
                )
                self.assertTrue(result["success"])
                self.assertEqual(broker.drain()[0].text, "exact")
                self.assertFalse(adapter._dynamic_tool_result(agent, "spawn_agent", {})["success"])
            finally:
                broker.stop()

    def test_private_config_disables_host_capabilities_and_requires_only_profile_mcp(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling", _load_package(root, "modeling"), base / "home", base / "work", base / "skills"
            )
            for path in (agent.home, agent.work, agent.skills):
                path.mkdir()
            run = SimpleNamespace(root=base, protocol_key=None)
            (base / "sources").mkdir()
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._write_config(run, agent)
            config = (agent.home / "config.toml").read_text(encoding="utf-8")
            for feature in ("apps", "plugins", "multi_agent", "browser_use", "memories", "hooks"):
                self.assertIn(f"{feature} = false", config)
            self.assertIn('web_search = "disabled"', config)
            self.assertNotIn("default_tools_enabled", config)
            self.assertIn("required = true", config)

    def test_dynamic_transport_callback_writes_sanitized_result_evidence(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            broker = TeamTransportBroker(base / "broker", {("modeling", "protocol")})
            broker.start(["modeling", "protocol"])
            try:
                agent = _Agent(
                    "modeling", _load_package(root, "modeling"), base / "home", base / "work", base / "skills"
                )
                agent.home.mkdir()
                agent.process = SimpleNamespace(stdin=StringIO())
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = base
                (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
                adapter._respond_dynamic_tool(
                    agent,
                    9,
                    {
                        "tool": "mcp__team_transport__send_team_message",
                        "arguments": {"recipient_id": "protocol", "text": "private exact text"},
                    },
                )
                event = json.loads((base / "evidence" / "dynamic-tool-calls.jsonl").read_text())
                self.assertEqual(event["tool"], "send_team_message")
                self.assertEqual(event["result"], "accepted")
                self.assertNotIn("private exact text", json.dumps(event))
                self.assertEqual(broker.drain()[0].recipient_id, "protocol")
            finally:
                broker.stop()

    def test_unknown_mcp_elicitation_is_declined_with_sanitized_evidence(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            agent = _Agent(
                "modeling", _load_package(root, "modeling"), base / "home", base / "work", base / "skills"
            )
            agent.process = SimpleNamespace(stdin=StringIO())
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            adapter._notification(
                agent,
                {
                    "id": 4,
                    "method": "mcpServer/elicitation/request",
                    "params": {
                        "serverName": "unknown",
                        "mode": "form",
                        "message": "do not retain this text",
                        "requestedSchema": {"type": "object", "properties": {}},
                    },
                },
            )
            response = json.loads(agent.process.stdin.getvalue())
            self.assertEqual(response["result"], {"action": "decline", "content": {}})
            event = json.loads((base / "evidence" / "mcp-elicitations.jsonl").read_text())
            self.assertEqual(event["action"], "decline")
            self.assertNotIn("do not retain", json.dumps(event))

    def test_expected_team_transport_elicitation_is_accepted(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            agent = _Agent(
                "modeling", _load_package(root, "modeling"), Path(directory) / "home", Path(directory) / "work", Path(directory) / "skills"
            )
            agent.process = SimpleNamespace(stdin=StringIO())
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._notification(
                agent,
                {
                    "id": 5,
                    "method": "mcpServer/elicitation/request",
                    "params": {"serverName": "team_transport", "mode": "form", "requestedSchema": {}},
                },
            )
            self.assertEqual(
                json.loads(agent.process.stdin.getvalue())["result"],
                {"action": "accept", "content": {}},
            )
