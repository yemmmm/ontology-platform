from __future__ import annotations

import tempfile
import unittest
import json
import stat
import socket
import subprocess
import threading
import time
from unittest.mock import patch
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, load_team_configuration, repository_root
from modeling_team.protocol_mcp_launch import canonical_protocol_mcp_mode_contract, protocol_mcp_launch_spec
from modeling_team.protocol_mechanics import protocol_mechanics_contract, protocol_mechanics_contract_bytes
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeMessage
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter,
    CodexRuntimeError,
    _Agent,
)
from modeling_team.transport_mcp import (
    TERMINAL_REPORT_GUARD_ERROR,
    RoutingError,
    TeamTransportBroker,
)


class CodexIsolationTests(unittest.TestCase):
    def test_host_auth_preflight_accepts_only_a_regular_non_symlink_file(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            codex_home = base / "codex-home"
            codex_home.mkdir()
            auth = codex_home / "auth.json"
            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
                auth.write_text("{}", encoding="utf-8")
                self.assertEqual(adapter.preflight_host_auth(), auth)
                auth.unlink()
                with self.assertRaisesRegex(CodexRuntimeError, "authentication is unavailable"):
                    adapter.preflight_host_auth()
                auth.mkdir()
                with self.assertRaisesRegex(CodexRuntimeError, "authentication is unavailable"):
                    adapter.preflight_host_auth()
                auth.rmdir()
                target = base / "real-auth.json"
                target.write_text("{}", encoding="utf-8")
                auth.symlink_to(target)
                with self.assertRaisesRegex(CodexRuntimeError, "authentication is unavailable"):
                    adapter.preflight_host_auth()

    def test_visibility_probe_uses_real_sibling_app_server_pid_without_persisting_it(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        coordinator = _Agent(
            "coordinator", _load_package(root, "coordinator"), Path("/tmp/coordinator-home"), Path("/tmp/coordinator-work"), Path("/tmp/coordinator-skills"), app_server_host_pid=41001
        )
        modeling = _Agent(
            "modeling", _load_package(root, "modeling"), Path("/tmp/modeling-home"), Path("/tmp/modeling-work"), Path("/tmp/modeling-skills"), app_server_host_pid=41002
        )
        protocol = _Agent(
            "protocol", _load_package(root, "protocol"), Path("/tmp/protocol-home"), Path("/tmp/protocol-work"), Path("/tmp/protocol-skills"), app_server_host_pid=41003
        )
        adapter.agents = {agent.agent_id: agent for agent in (coordinator, modeling, protocol)}
        adapter.namespace_command = lambda agent: ["bwrap", "--proc", "/proc", "--", "/agent/bin/codex", "app-server"]  # type: ignore[method-assign]
        commands: list[list[str]] = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0)

        task = SimpleNamespace(
            role_sources=(
                SimpleNamespace(relative_path=Path("public.md"), roles=frozenset({"coordinator", "modeling", "protocol"})),
            )
        )
        team_run = SimpleNamespace(configuration=SimpleNamespace(task=task))
        with patch("modeling_team.runtimes.codex.subprocess.run", side_effect=fake_run):
            evidence = adapter.probe_role_visibility(team_run)

        scripts = {agent_id: command[-1] for agent_id, command in zip(adapter.agents, commands, strict=True)}
        self.assertTrue(all(command[-3:-1] == ["/bin/sh", "-c"] for command in commands))
        self.assertIn("/proc/41002/environ", scripts["coordinator"])
        self.assertIn("/proc/41003/environ", scripts["coordinator"])
        self.assertNotIn("/proc/41001/environ", scripts["coordinator"])
        self.assertNotIn("/proc/41002/environ", scripts["modeling"])
        self.assertNotIn("41001", json.dumps(evidence))
        self.assertEqual(evidence["coordinator"]["forbidden_path_categories"][-2], "sibling-process")

    def test_visibility_probe_requires_each_sibling_app_server_pid(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter.agents = {
            "coordinator": _Agent("coordinator", _load_package(root, "coordinator"), Path("/tmp/a"), Path("/tmp/a-work"), Path("/tmp/a-skills"), app_server_host_pid=42001),
            "modeling": _Agent("modeling", _load_package(root, "modeling"), Path("/tmp/b"), Path("/tmp/b-work"), Path("/tmp/b-skills")),
        }
        task = SimpleNamespace(role_sources=())
        with self.assertRaisesRegex(CodexRuntimeError, "sibling app-server host PID"):
            adapter.probe_role_visibility(SimpleNamespace(configuration=SimpleNamespace(task=task)))

    def test_app_server_pid_resolves_inner_leaf_not_bwrap_wrapper(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        agent = _Agent(
            "coordinator", _load_package(root, "coordinator"), Path("/tmp/a"), Path("/tmp/a-work"), Path("/tmp/a-skills"), process=SimpleNamespace(pid=43000)
        )
        children = {43000: [43001], 43001: [43002], 43002: []}
        with patch.object(adapter, "_host_child_pids", side_effect=lambda pid: children[pid]):
            with patch.object(adapter, "_host_process_identity", return_value=("bwrap", "bwrap app-server")):
                self.assertEqual(adapter._app_server_host_pid(agent), 43002)

    def test_app_server_pid_ignores_mcp_child_and_selects_app_server(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        agent = _Agent(
            "protocol", _load_package(root, "protocol"), Path("/tmp/a"), Path("/tmp/a-work"), Path("/tmp/a-skills"), process=SimpleNamespace(pid=44000)
        )
        children = {44000: [44001], 44001: [44002], 44002: [44003], 44003: []}
        identities = {
            44001: ("bwrap", "bwrap app-server"),
            44002: ("node", "node /agent/bin/codex app-server"),
            44003: ("python", "python -m app.mcp.server"),
        }
        with patch.object(adapter, "_host_child_pids", side_effect=lambda pid: children[pid]):
            with patch.object(adapter, "_host_process_identity", side_effect=lambda pid: identities[pid]):
                self.assertEqual(adapter._app_server_host_pid(agent), 44002)

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
            separator = command.index("--")
            self.assertEqual(command[separator + 1], "/agent/bin/codex")
            self.assertEqual(command[separator + 2 :], [
                "--config", 'web_search="disabled"', "--disable", "apps", "--disable", "plugins",
                "--disable", "multi_agent", "--disable", "multi_agent_v2", "--disable", "browser_use",
                "--disable", "computer_use", "--disable", "image_generation", "--disable", "memories",
                "--disable", "hooks", "app-server",
            ])

    def test_non_bwrap_namespace_command_retains_v1_app_server_form(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root, use_bwrap=False)
        agent = _Agent(
            "coordinator", _load_package(root, "coordinator"), Path("/tmp/a"), Path("/tmp/a-work"), Path("/tmp/a-skills")
        )
        self.assertEqual(adapter.namespace_command(agent)[-1], "app-server")
        self.assertNotIn("--", adapter.namespace_command(agent))

    def test_v2_protocol_mechanics_contract_is_protocol_only_read_only_runtime_asset(self) -> None:
        root = repository_root()
        expected = {
            "contract_version": 1,
            "run_id": "r23002-mechanics-contract",
            "owner": "protocol_only_deterministic_helper",
            "owns": [
                "stable_ids",
                "canonical_json_and_hashes",
                "atomic_publication",
                "public_request_schema_validation",
                "immutable_batch_freeze_and_replay",
                "workspace_revision_and_lease_state",
                "lease_renewal_and_checkpoint_bodies",
                "response_parsing",
                "cross_batch_platform_identity_binding",
            ],
            "forbidden": ["modeling_item_synthesis", "item_reordering", "semantic_repair", "query_authoring"],
        }
        contract_value = protocol_mechanics_contract("r23002-mechanics-contract")
        self.assertEqual(
            {key: value for key, value in contract_value.items() if key != "build_session_lifecycle"},
            expected,
        )
        lifecycle = {
            "ordered_steps": [
                "create_session_without_nested_checkpoint",
                "save_initial_checkpoint",
                "acquire_lease_using_initial_checkpoint_revision",
                "semantic_batch_application_validation_reasoning_and_query",
                "refresh_session_before_final_checkpoint",
                "save_final_checkpoint",
                "complete_using_final_checkpoint_revision",
                "reread_completed_session",
            ],
            "create_session": {
                "tool": "create_build_session",
                "initial_checkpoint": "omit_or_null",
                "forbidden_nested_fields": ["run_id", "phase", "workspace", "checkpoint"],
                "receipt_bindings": {
                    "session_id": "create_receipt.session.id",
                    "revision": "create_receipt.session.revision",
                },
            },
            "initial_checkpoint": {
                "tool": "save_build_checkpoint",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_checkpoint_id": "r23002-mechanics-contract-initial",
                    "expected_revision": "create_receipt.session.revision",
                    "phase": "modeling",
                    "current_step": "schema_and_instance_modeling",
                    "next_step": "validation_and_reasoning",
                    "ontology_id": "scope.ontology_id",
                    "blockers": [],
                },
                "receipt_binding": "initial_checkpoint_receipt.session.revision",
            },
            "lease": {
                "tool": "acquire_ontology_lease",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "ontology_id": "scope.ontology_id",
                    "client_request_id": "r23002-mechanics-contract-lease",
                    "expected_session_revision": "initial_checkpoint_receipt.session.revision",
                    "rotate_token": False,
                },
            },
            "pre_final_session_refresh": {
                "after": [
                    "semantic_batch_application",
                    "semantic_validation",
                    "semantic_reasoning",
                    "governed_query",
                ],
                "tool": "get_build_session",
                "fields": {"session_id": "create_receipt.session.id"},
                "receipt_binding": "get_build_session_receipt.session.revision",
            },
            "final_checkpoint": {
                "after": ["get_build_session_receipt.session.revision"],
                "tool": "save_build_checkpoint",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_checkpoint_id": "r23002-mechanics-contract-final",
                    "expected_revision": "get_build_session_receipt.session.revision",
                    "phase": "handoff",
                    "current_step": "semantic_acceptance_complete",
                    "next_step": "delivery_handoff",
                    "ontology_id": "scope.ontology_id",
                    "blockers": [],
                },
                "receipt_binding": "final_checkpoint_receipt.session.revision",
            },
            "complete_session": {
                "tool": "complete_build_session",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_request_id": "r23002-mechanics-contract-complete",
                    "expected_revision": "final_checkpoint_receipt.session.revision",
                    "summary": "semantic acceptance complete",
                    "unresolved_items": [],
                },
                "reread": {
                    "tool": "get_build_session",
                    "fields": {"session_id": "create_receipt.session.id"},
                    "required_status": "completed",
                    "receipt_binding": "completed_session_receipt.session.revision",
                },
            },
        }
        self.assertEqual(contract_value["build_session_lifecycle"], lifecycle)
        self.assertEqual(lifecycle["create_session"]["initial_checkpoint"], "omit_or_null")
        self.assertIn("run_id", lifecycle["create_session"]["forbidden_nested_fields"])
        self.assertEqual(
            set(lifecycle["initial_checkpoint"]["fields"]),
            {
                "session_id",
                "client_checkpoint_id",
                "expected_revision",
                "phase",
                "current_step",
                "next_step",
                "ontology_id",
                "blockers",
            },
        )
        self.assertNotIn("run_id", lifecycle["initial_checkpoint"]["fields"])
        self.assertNotIn("run_id", lifecycle["final_checkpoint"]["fields"])
        self.assertNotIn("latest_platform_receipt", json.dumps(lifecycle, sort_keys=True))
        self.assertEqual(
            lifecycle["complete_session"]["fields"],
            {
                "session_id": "create_receipt.session.id",
                "client_request_id": "r23002-mechanics-contract-complete",
                "expected_revision": "final_checkpoint_receipt.session.revision",
                "summary": "semantic acceptance complete",
                "unresolved_items": [],
            },
        )
        expected["build_session_lifecycle"] = lifecycle
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            v2_run = SimpleNamespace(
                root=base,
                run_id="r23002-mechanics-contract",
                configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
            )
            agents = {
                role: _Agent(
                    role,
                    _load_package(root, role),
                    base / role / "home",
                    base / role / "work",
                    base / role / "skills",
                )
                for role in ("coordinator", "modeling", "protocol")
            }
            for agent in agents.values():
                CodexRuntimeAdapter._stage_protocol_mechanics_contract(v2_run, agent)
            contract = base / "runtime-assets" / "protocol" / "mechanics-contract.json"
            self.assertEqual(agents["protocol"].mechanics_contract_path, contract)
            self.assertIsNone(agents["coordinator"].mechanics_contract_path)
            self.assertIsNone(agents["modeling"].mechanics_contract_path)
            self.assertEqual(json.loads(contract.read_text(encoding="utf-8")), expected)
            self.assertEqual(stat.S_IMODE(contract.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(contract.parent.stat().st_mode), 0o700)
            self.assertFalse((agents["protocol"].home / "mechanics-contract.json").exists())
            host_digest = __import__("hashlib").sha256(contract.read_bytes()).hexdigest()

            for path in (agents["protocol"].home, agents["protocol"].work, agents["protocol"].skills):
                path.mkdir(parents=True)
            (base / "transport" / "broker").mkdir(parents=True)
            (base / "transport" / "broker" / "protocol.sock").touch()
            adapter._run_root = base
            adapter._run_id = "r23002-mechanics-contract"
            adapter.agents = agents
            dynamic = adapter._dynamic_tool_result(
                agents["protocol"], "exec", {"cmd": "cat /opt/mechanics-contract.json"}
            )
            self.assertTrue(dynamic["success"])
            self.assertEqual(
                dynamic["contentItems"][0]["text"],
                protocol_mechanics_contract_bytes("r23002-mechanics-contract").decode("utf-8"),
            )
            self.assertNotIn("/opt", adapter.namespace_command(agents["coordinator"]))
            self.assertNotIn("/opt", adapter.namespace_command(agents["modeling"]))
            command = adapter.namespace_command(agents["protocol"])
            self.assertIn(["--ro-bind", str(contract), "/opt/mechanics-contract.json"], [command[index:index + 3] for index in range(len(command) - 2)])
            self.assertEqual(command.count("/opt"), 1)
            separator = command.index("--")
            command[separator:] = [
                "--",
                "/bin/sh",
                "-c",
                "set -eu; test -r /opt/mechanics-contract.json; test ! -e /agent/home/mechanics-contract.json; "
                "if chmod u+w /opt/mechanics-contract.json; then exit 1; fi; "
                "if printf changed >> /opt/mechanics-contract.json; then exit 1; fi",
            ]
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(__import__("hashlib").sha256(contract.read_bytes()).hexdigest(), host_digest)

            v1_agent = _Agent(
                "protocol-v1",
                _load_package(root, "protocol"),
                base / "v1-home",
                base / "v1-work",
                base / "v1-skills",
            )
            v1_run = SimpleNamespace(
                root=base / "v1-run",
                run_id="r23002-v1-mechanics",
                configuration=SimpleNamespace(task=SimpleNamespace(schema_version=1)),
            )
            CodexRuntimeAdapter._stage_protocol_mechanics_contract(v1_run, v1_agent)
            self.assertIsNone(v1_agent.mechanics_contract_path)
            self.assertFalse((v1_run.root / "runtime-assets").exists())
            self.assertNotIn("/opt", adapter.namespace_command(v1_agent))
            adapter.agents = {"protocol": agents["protocol"]}
            adapter.stop()
            self.assertTrue(contract.exists())

    def test_protocol_retrieval_mcp_assets_are_protocol_only_and_fd_bound(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            run = SimpleNamespace(
                root=base,
                run_id="r23002-retrieval-mcp",
                configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
            )
            protocol = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                schema_version=2,
            )
            coordinator = _Agent(
                "coordinator",
                _load_package(root, "coordinator"),
                base / "coordinator-home",
                base / "coordinator-work",
                base / "coordinator-skills",
                schema_version=2,
            )
            for agent in (protocol, coordinator):
                for path in (agent.home, agent.work, agent.skills):
                    path.mkdir(parents=True)
            (base / "transport" / "broker").mkdir(parents=True)
            for agent in (protocol, coordinator):
                (base / "transport" / "broker" / f"{agent.agent_id}.sock").touch()
            adapter._run_root = base
            adapter.agents = {"protocol": protocol, "coordinator": coordinator}
            adapter._stage_protocol_retrieval_mcp(run, protocol)
            adapter._stage_protocol_retrieval_mcp(run, coordinator)
            self.assertIsNotNone(protocol.retrieval_mcp_path)
            self.assertIsNotNone(protocol.retrieval_verifier_path)
            self.assertIsNotNone(protocol.proof_v2_path)
            self.assertIsNone(coordinator.retrieval_mcp_path)
            self.assertEqual(stat.S_IMODE(protocol.retrieval_mcp_path.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(protocol.retrieval_verifier_path.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(protocol.proof_v2_path.stat().st_mode), 0o600)
            command = adapter.namespace_command(protocol)
            descriptor_paths = [value for value in command if value.startswith("/proc/self/fd/")]
            self.assertEqual(len(descriptor_paths), 3)
            self.assertIn("/opt/proof_v2.py", command)
            self.assertNotIn("/opt/protocol-retrieval-mcp.py", adapter.namespace_command(coordinator))
            os.lseek(protocol.retrieval_asset_fds[0], 0, os.SEEK_SET)
            original = os.read(protocol.retrieval_asset_fds[0], 1024)
            os.lseek(protocol.retrieval_asset_fds[0], 0, os.SEEK_SET)
            protocol.retrieval_mcp_path.unlink()
            protocol.retrieval_mcp_path.write_text("replacement", encoding="utf-8")
            os.chmod(protocol.retrieval_mcp_path, 0o444)
            captured: dict[str, object] = {}

            def fake_process(command, **kwargs):
                captured["command"] = command
                captured["pass_fds"] = kwargs["pass_fds"]
                return SimpleNamespace()

            adapter.process_factory = fake_process
            adapter._start_process(protocol)
            self.assertEqual(captured["pass_fds"], tuple(int(path.rsplit("/", 1)[1]) for path in descriptor_paths))
            self.assertEqual(original, root.joinpath("modeling_team/protocol_retrieval_mcp.py").read_bytes()[:1024])
            self.assertEqual(protocol.retrieval_asset_fds, ())

    def test_mcp_preflight_requires_exact_protocol_and_non_protocol_servers(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        protocol = _Agent(
            "protocol",
            _load_package(root, "protocol"),
            Path("/tmp/protocol-home"),
            Path("/tmp/protocol-work"),
            Path("/tmp/protocol-skills"),
            platform_tools=frozenset({"check_platform_health"}),
            schema_version=2,
        )
        expected_protocol = [
            {"name": "team_transport", "tools": [{"name": "send_team_message"}, {"name": "report_task_result"}]},
            {"name": "ontology_platform", "tools": [{"name": "check_platform_health"}]},
            {
                "name": "protocol_mechanics",
                "tools": [
                    {"name": "build_candidate_receipt"},
                    {"name": "verify_scoped_retrieval_fallback"},
                    {"name": "write_candidate_item_evidence_map"},
                ],
            },
        ]
        adapter._rpc = lambda _agent, _method, _params: {"data": expected_protocol}  # type: ignore[method-assign]
        adapter._require_expected_mcp_servers(protocol)
        coordinator = _Agent(
            "coordinator",
            _load_package(root, "coordinator"),
            Path("/tmp/coordinator-home"),
            Path("/tmp/coordinator-work"),
            Path("/tmp/coordinator-skills"),
            schema_version=2,
        )
        cases = {
            "zero": [],
            "wrong-tool": [*expected_protocol[:-1], {"name": "protocol_mechanics", "tools": [{"name": "wrong"}]}],
            "extra-server": [*expected_protocol, {"name": "extra", "tools": []}],
            "wrong-role": [
                {"name": "team_transport", "tools": [{"name": "send_team_message"}, {"name": "report_task_result"}]},
                {"name": "ontology_platform", "tools": [{"name": "check_platform_health"}]},
            ],
        }
        for name, servers in cases.items():
            agent = coordinator if name == "wrong-role" else protocol
            adapter._rpc = lambda _agent, _method, _params, servers=servers: {"data": servers}  # type: ignore[method-assign]
            with self.subTest(case=name), patch(
                "modeling_team.runtimes.codex.time.monotonic", side_effect=[0, 1, 26]
            ), patch("modeling_team.runtimes.codex.time.sleep"):
                with self.assertRaisesRegex(CodexRuntimeError, "MCP preflight failed"):
                    adapter._require_expected_mcp_servers(agent)

    def test_protocol_mechanics_dynamic_read_fails_closed_for_identity_path_and_file_drift(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)

            def prepare(name: str):
                run_root = base / name
                run_root.mkdir()
                run_id = f"r23002-{name}"
                run = SimpleNamespace(
                    root=run_root,
                    run_id=run_id,
                    configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
                )
                agent = _Agent(
                    "protocol",
                    _load_package(root, "protocol"),
                    run_root / "home",
                    run_root / "work",
                    run_root / "skills",
                )
                adapter = CodexRuntimeAdapter(repository_root=root)
                CodexRuntimeAdapter._stage_protocol_mechanics_contract(run, agent)
                adapter._run_root = run_root
                adapter._run_id = run_id
                adapter.agents = {"protocol": agent}
                assert agent.mechanics_contract_path is not None
                return adapter, agent, agent.mechanics_contract_path

            def denied(adapter: CodexRuntimeAdapter, agent: _Agent, path: str = "/opt/mechanics-contract.json") -> None:
                result = adapter._dynamic_tool_result(agent, "exec", {"cmd": f"cat {path}"})
                self.assertFalse(result["success"])

            adapter, agent, _ = prepare("wrong-virtual")
            denied(adapter, agent, "/opt/not-mechanics-contract.json")

            adapter, agent, _ = prepare("wrong-role")
            wrong_role = _Agent("coordinator", _load_package(root, "coordinator"), base / "home", base / "work", base / "skills")
            wrong_role.mechanics_contract_path = agent.mechanics_contract_path
            adapter.agents = {"coordinator": wrong_role}
            denied(adapter, wrong_role)

            adapter, agent, _ = prepare("v1")
            agent.mechanics_contract_path = None
            adapter._run_id = "r23002-v1"
            denied(adapter, agent)

            adapter, agent, _ = prepare("null")
            agent.mechanics_contract_path = None
            denied(adapter, agent)

            adapter, agent, _ = prepare("unregistered")
            unregistered = _Agent("protocol", agent.package, base / "other-home", base / "other-work", base / "other-skills")
            unregistered.mechanics_contract_path = agent.mechanics_contract_path
            denied(adapter, unregistered)

            adapter, agent, _ = prepare("wrong-raw")
            agent.mechanics_contract_path = base / "wrong-raw.json"
            denied(adapter, agent)

            adapter, agent, _ = prepare("wrong-run-root")
            adapter._run_root = base / "another-run-root"
            denied(adapter, agent)

            adapter, agent, contract = prepare("symlink-file")
            target = base / "symlink-file-target.json"
            target.write_bytes(protocol_mechanics_contract_bytes(adapter._run_id or ""))
            os.chmod(target, 0o444)
            contract.unlink()
            contract.symlink_to(target)
            denied(adapter, agent)

            adapter, agent, contract = prepare("symlink-parent")
            replacement = base / "replacement-protocol-dir"
            replacement.mkdir()
            (replacement / contract.name).write_bytes(protocol_mechanics_contract_bytes(adapter._run_id or ""))
            os.chmod(replacement / contract.name, 0o444)
            __import__("shutil").rmtree(contract.parent)
            contract.parent.symlink_to(replacement, target_is_directory=True)
            denied(adapter, agent)

            adapter, agent, contract = prepare("nonregular")
            contract.unlink()
            contract.mkdir()
            denied(adapter, agent)

            adapter, agent, contract = prepare("mode")
            os.chmod(contract, 0o400)
            denied(adapter, agent)

            adapter, agent, contract = prepare("tampered")
            os.chmod(contract, 0o644)
            contract.write_bytes(b"{}")
            os.chmod(contract, 0o444)
            denied(adapter, agent)

    def test_generated_visibility_probe_runs_in_real_bwrap_with_inner_sibling_pid(self) -> None:
        if not __import__("shutil").which("bwrap"):
            self.skipTest("bubblewrap is unavailable")
        root = repository_root()
        configuration = load_team_configuration(
            root / "modeling_team/profiles/base-three-agent.yaml",
            root / "modeling_team/tasks/new-scope-business-slice.yaml",
            root=root,
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_root, transport_root = base / "run", base / "transport"
            run_root.mkdir()
            transport_root.mkdir()
            (run_root / "transport-root").write_text(str(transport_root), encoding="utf-8")
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = run_root
            sockets: list[socket.socket] = []
            processes: list[subprocess.Popen[str]] = []
            try:
                for profile_agent in configuration.profile.agents[:2]:
                    agent_root = base / profile_agent.agent_id
                    agent = _Agent(
                        profile_agent.agent_id,
                        profile_agent.package,
                        agent_root / "home",
                        agent_root / "work",
                        agent_root / "skills",
                    )
                    for path in (agent.home, agent.work, agent.skills):
                        path.mkdir(parents=True)
                    for source in configuration.task.role_sources:
                        if agent.package.role in source.roles:
                            staged = agent.home / "sources" / source.relative_path
                            staged.parent.mkdir(parents=True, exist_ok=True)
                            staged.write_text("safe probe input", encoding="utf-8")
                    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    server.bind(str(transport_root / f"{agent.agent_id}.sock"))
                    sockets.append(server)
                    process = subprocess.Popen(
                        [
                            "bwrap", "--die-with-parent", "--unshare-pid", "--proc", "/proc", "--dev", "/dev",
                            "--ro-bind", "/bin", "/bin", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                            "--ro-bind", "/lib64", "/lib64", "--", "/bin/sh", "-c", "exec sleep 30",
                        ],
                        text=True,
                    )
                    processes.append(process)
                    agent.process = process
                    for _ in range(20):
                        try:
                            agent.app_server_host_pid = adapter._app_server_host_pid(agent)
                            break
                        except CodexRuntimeError:
                            time.sleep(0.05)
                    self.assertIsNotNone(agent.app_server_host_pid)
                    adapter.agents[agent.agent_id] = agent

                evidence = adapter.probe_role_visibility(SimpleNamespace(configuration=configuration))
                self.assertEqual(set(evidence), {"coordinator", "modeling"})
                self.assertTrue(all("sibling-process" in item["forbidden_path_categories"] for item in evidence.values()))
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                for server in sockets:
                    server.close()

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
            "protocol",
            RuntimeDelivery(
                "modeling",
                "protocol",
                "peer",
                exact,
                delivery_id="delivery-9",
                expects_reply=True,
                reply_to_delivery_id="delivery-8",
            ),
        )

        payload = json.loads(calls[0]["input"][0]["text"])
        self.assertEqual(
            payload,
            {
                "sender_id": "modeling",
                "recipient_id": "protocol",
                "kind": "peer",
                "text": exact,
                "delivery_id": "delivery-9",
                "expects_reply": True,
                "reply_to_delivery_id": "delivery-8",
            },
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

    def test_dynamic_transport_reports_terminal_dependency_error_and_retries_after_handoffs(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            broker = TeamTransportBroker(
                base / "broker",
                set(),
                terminal_dependencies={"coordinator": {"modeling", "protocol"}},
            )
            broker.start(["coordinator", "modeling", "protocol"])
            try:
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = base
                (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
                agents = {
                    role: _Agent(
                        role,
                        _load_package(root, role),
                        base / f"{role}-home",
                        base / f"{role}-work",
                        base / f"{role}-skills",
                    )
                    for role in ("coordinator", "modeling", "protocol")
                }
                adapter.agents = agents
                early = adapter._dynamic_tool_result(
                    agents["coordinator"],
                    "mcp__team_transport__report_task_result",
                    {"status": "completed", "summary": "early"},
                )
                self.assertFalse(early["success"])
                self.assertEqual(
                    early["contentItems"][0]["text"],
                    "Team Transport rejected the request: terminal result requires terminal handoffs: modeling, protocol",
                )
                self.assertTrue(
                    adapter._dynamic_tool_result(
                        agents["modeling"],
                        "mcp__team_transport__report_task_result",
                        {"status": "completed", "summary": "modeling handoff"},
                    )["success"]
                )
                self.assertTrue(
                    adapter._dynamic_tool_result(
                        agents["protocol"],
                        "mcp__team_transport__report_task_result",
                        {"status": "blocked", "summary": "protocol handoff"},
                    )["success"]
                )
                broker.ack_terminal_handoff("coordinator", "modeling")
                broker.ack_terminal_handoff("coordinator", "protocol")
                self.assertTrue(
                    adapter._dynamic_tool_result(
                        agents["coordinator"],
                        "mcp__team_transport__report_task_result",
                        {"status": "completed", "summary": "coordinator retry"},
                    )["success"]
                )
            finally:
                broker.stop()

    def test_dynamic_transport_records_safe_adverse_order_metadata(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            broker = TeamTransportBroker(
                base / "broker",
                set(),
                terminal_dependencies={"protocol": {"modeling"}},
            )
            broker.start(["coordinator", "modeling", "protocol"])
            try:
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = base
                (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
                agents = {
                    role: _Agent(
                        role,
                        _load_package(root, role),
                        base / f"{role}-home",
                        base / f"{role}-work",
                        base / f"{role}-skills",
                    )
                    for role in ("coordinator", "modeling", "protocol")
                }
                adapter.agents = agents
                early = adapter._dynamic_tool_result(
                    agents["protocol"],
                    "mcp__team_transport__report_task_result",
                    {"status": "completed", "summary": "early"},
                )
                self.assertFalse(early["success"])
                self.assertTrue(
                    adapter._dynamic_tool_result(
                        agents["modeling"],
                        "mcp__team_transport__report_task_result",
                        {"status": "completed", "summary": "modeling"},
                    )["success"]
                )
                # Satisfy the dependency gate through the real Broker API, then retry Protocol.
                broker.ack_terminal_handoff("protocol", "modeling")
                self.assertTrue(
                    adapter._dynamic_tool_result(
                        agents["protocol"],
                        "mcp__team_transport__report_task_result",
                        {"status": "completed", "summary": "retry"},
                    )["success"]
                )
                records = [
                    json.loads(line)
                    for line in (base / "evidence" / "team-transport-events.jsonl").read_text().splitlines()
                    if json.loads(line).get("agent") == "protocol"
                ]
                self.assertEqual(
                    [(record["status"], record["category"]) for record in records],
                    [
                        ("rejected", "missing_modeling_handoff"),
                        ("accepted", "terminal_report_accepted"),
                    ],
                )
                for record in records:
                    self.assertNotIn("summary", record)
                    self.assertNotIn("result", record)
                    self.assertNotIn("credentials", record)
            finally:
                broker.stop()

    def test_dynamic_transport_rejects_malformed_or_untrusted_error_responses_without_leaking_them(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            agents = {
                role: _Agent(
                    role,
                    _load_package(root, role),
                    base / f"{role}-home",
                    base / f"{role}-work",
                    base / f"{role}-skills",
                )
                for role in ("coordinator", "modeling", "protocol")
            }
            adapter.agents = agents

            def respond(agent: _Agent, raw: bytes) -> dict[str, object]:
                transport = base / "transport"
                transport.mkdir(exist_ok=True)
                (base / "transport-root").write_text(str(transport), encoding="utf-8")
                endpoint = transport / f"{agent.agent_id}.sock"
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(endpoint))
                server.listen(1)

                def serve() -> None:
                    connection, _ = server.accept()
                    with connection:
                        connection.makefile("r", encoding="utf-8").readline()
                        connection.sendall(raw)
                    server.close()

                worker = threading.Thread(target=serve)
                worker.start()
                try:
                    return adapter._dynamic_tool_result(
                        agent,
                        "mcp__team_transport__report_task_result",
                        {"status": "completed", "summary": "ordinary summary"},
                    )
                finally:
                    worker.join(timeout=2)
                    endpoint.unlink(missing_ok=True)

            for raw in (
                b'{"error":"secret-from-untrusted-socket"}\n',
                b'{"error":["secret-from-untrusted-socket"]}\n',
                (b'{"error":"' + b"x" * 201 + b'"}\n'),
            ):
                with self.subTest(raw=raw[:20]):
                    result = respond(agents["coordinator"], raw)
                    self.assertFalse(result["success"])
                    self.assertEqual(result["contentItems"][0]["text"], "Team Transport rejected the request")
                    self.assertNotIn("secret-from-untrusted-socket", result["contentItems"][0]["text"])
            malformed = respond(agents["coordinator"], b"not-json\n")
            self.assertFalse(malformed["success"])
            self.assertEqual(malformed["contentItems"][0]["text"], "Team Transport is unavailable")

            prefix = "terminal result requires terminal roles: "
            for error in (
                prefix + "attacker",
                prefix + "modeling, protocol, canary",
                prefix + "modeling, modeling, protocol",
                prefix + "modeling",
                prefix + "protocol, modeling",
                "canary " + prefix + "modeling, protocol",
                prefix + "modeling, protocol canary",
            ):
                with self.subTest(error=error):
                    result = respond(agents["coordinator"], json.dumps({"error": error}).encode() + b"\n")
                    self.assertFalse(result["success"])
                    self.assertEqual(result["contentItems"][0]["text"], "Team Transport rejected the request")
                    self.assertNotIn(error, result["contentItems"][0]["text"])
            non_coordinator_error = prefix + "modeling, protocol"
            non_coordinator = respond(
                agents["modeling"], json.dumps({"error": non_coordinator_error}).encode() + b"\n"
            )
            self.assertFalse(non_coordinator["success"])
            self.assertEqual(non_coordinator["contentItems"][0]["text"], "Team Transport rejected the request")
            full_roster = adapter.agents
            adapter.agents = {"coordinator": agents["coordinator"], "modeling": agents["modeling"]}
            incomplete_roster = respond(
                agents["coordinator"], json.dumps({"error": non_coordinator_error}).encode() + b"\n"
            )
            self.assertFalse(incomplete_roster["success"])
            self.assertEqual(incomplete_roster["contentItems"][0]["text"], "Team Transport rejected the request")
            adapter.agents = full_roster

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
            codex_home = base / "codex-home"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text("{}", encoding="utf-8")
            original_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(codex_home)
            try:
                adapter._write_config(run, agent)
            finally:
                if original_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = original_home
            config = (agent.home / "config.toml").read_text(encoding="utf-8")
            for feature in ("apps", "plugins", "multi_agent", "browser_use", "memories", "hooks"):
                self.assertIn(f"{feature} = false", config)
            self.assertIn('web_search = "disabled"', config)
            self.assertNotIn("default_tools_enabled", config)
            self.assertIn("required = true", config)

    def test_protocol_config_uses_the_single_canonical_launch_spec(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            codex_home = base / "codex-home"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text("{}", encoding="utf-8")
            for role in ("coordinator", "modeling", "protocol"):
                (base / "sources" / role).mkdir(parents=True)
            run = SimpleNamespace(
                root=base,
                run_id="r23002-config-contract",
                protocol_key="private-key",
                configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "SEMANTIC_REASONER_COMMAND": "/ambient/reasoner.py",
                    "PATH": "/ambient/bin",
                },
                clear=False,
            ):
                configs = {}
                for role in ("coordinator", "modeling", "protocol"):
                    agent = _Agent(
                        role,
                        _load_package(root, role),
                        base / role / "home",
                        base / role / "work",
                        base / role / "skills",
                        platform_tools=frozenset({"submit_modeling_batch", "check_platform_health"}),
                    )
                    for path in (agent.home, agent.work, agent.skills):
                        path.mkdir(parents=True)
                    adapter._write_config(run, agent)
                    configs[role] = (agent.home / "config.toml").read_text(encoding="utf-8")

            spec = protocol_mcp_launch_spec(frozenset({"submit_modeling_batch", "check_platform_health"}))
            self.assertEqual(spec.command, "/backend/.venv/bin/python")
            self.assertEqual(spec.cwd, "/backend")
            self.assertEqual(spec.args, ("-m", "app.mcp.server"))
            self.assertEqual(spec.tools, ("check_platform_health", "submit_modeling_batch"))
            self.assertEqual(dict(spec.reasoner_env), {
                "SEMANTIC_REASONER_COMMAND": "/backend/scripts/dev_owl_reasoner.py",
                "PATH": "/backend/.venv/bin:/usr/bin:/bin",
            })
            self.assertEqual(canonical_protocol_mcp_mode_contract(), {
                "SEMANTIC_CANONICAL_STORE": "rdf",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            })
            self.assertIn("[mcp_servers.ontology_platform]", configs["protocol"])
            self.assertIn("[mcp_servers.protocol_mechanics]", configs["protocol"])
            self.assertIn('command = "/usr/bin/python3"', configs["protocol"])
            self.assertIn('args = ["/opt/protocol-retrieval-mcp.py"]', configs["protocol"])
            self.assertIn(
                'PROTOCOL_RUNTIME_RUN_ID = "r23002-config-contract"', configs["protocol"]
            )
            self.assertIn('ONTOLOGY_MCP_API_KEY = "private-key"', configs["protocol"])
            self.assertIn('ONTOLOGY_MCP_BASE_URL = "http://127.0.0.1:8001"', configs["protocol"])
            self.assertNotIn("/ambient/reasoner.py", configs["protocol"])
            self.assertNotIn("/ambient/bin", configs["protocol"])
            self.assertIn('enabled_tools = ["check_platform_health", "submit_modeling_batch"]', configs["protocol"])
            for name, value in canonical_protocol_mcp_mode_contract().items():
                self.assertIn(f'{name} = "{value}"', configs["protocol"])
                self.assertNotIn(name, configs["coordinator"])
                self.assertNotIn(name, configs["modeling"])
            for name, value in spec.hardening_env:
                self.assertIn(f'{name} = "{value}"', configs["protocol"])
                self.assertNotIn(name, configs["coordinator"])
                self.assertNotIn(name, configs["modeling"])
            for name, value in spec.reasoner_env:
                self.assertIn(f'{name} = "{value}"', configs["protocol"])
                self.assertNotIn(name, configs["coordinator"])
                self.assertNotIn(name, configs["modeling"])
            for role in ("coordinator", "modeling"):
                self.assertNotIn("ontology_platform", configs[role])
                self.assertNotIn("protocol_mechanics", configs[role])

            v1_base = base / "v1"
            (v1_base / "sources").mkdir(parents=True)
            v1_agent = _Agent(
                "protocol-v1",
                _load_package(root, "protocol"),
                v1_base / "home",
                v1_base / "work",
                v1_base / "skills",
                platform_tools=frozenset({"check_platform_health"}),
                schema_version=1,
            )
            for path in (v1_agent.home, v1_agent.work, v1_agent.skills):
                path.mkdir(parents=True)
            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
                adapter._write_config(
                    SimpleNamespace(
                        root=v1_base,
                        protocol_key="private-key",
                        configuration=SimpleNamespace(task=SimpleNamespace(schema_version=1)),
                    ),
                    v1_agent,
                )
            v1_config = (v1_agent.home / "config.toml").read_text(encoding="utf-8")
            for name in dict(spec.reasoner_env):
                self.assertNotIn(f"\n{name} = ", v1_config)
            self.assertNotIn("protocol_mechanics", v1_config)
            self.assertNotIn("PROTOCOL_RUNTIME_RUN_ID", v1_config)

    def test_protocol_config_runtime_binding_fails_closed_for_missing_or_drifting_run(self) -> None:
        root = repository_root()
        adapter = CodexRuntimeAdapter(repository_root=root)
        agent = _Agent(
            "protocol",
            _load_package(root, "protocol"),
            Path("/tmp/protocol-config-home"),
            Path("/tmp/protocol-config-work"),
            Path("/tmp/protocol-config-skills"),
            schema_version=2,
        )
        task = SimpleNamespace(schema_version=2)
        with self.assertRaisesRegex(CodexRuntimeError, "requires a run ID"):
            adapter._write_config(
                SimpleNamespace(configuration=SimpleNamespace(task=task)), agent
            )
        adapter._run_id = "run-active"
        with self.assertRaisesRegex(CodexRuntimeError, "drifts"):
            adapter._write_config(
                SimpleNamespace(
                    run_id="run-foreign", configuration=SimpleNamespace(task=task)
                ),
                agent,
            )

    def test_v2_protocol_reasoner_mount_is_exact_read_only_and_fail_closed(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            protocol = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                schema_version=2,
            )
            coordinator = _Agent(
                "coordinator",
                _load_package(root, "coordinator"),
                base / "coordinator-home",
                base / "coordinator-work",
                base / "coordinator-skills",
                schema_version=2,
            )
            modeling = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "modeling-home",
                base / "modeling-work",
                base / "modeling-skills",
                schema_version=2,
            )
            v1_protocol = _Agent(
                "protocol-v1",
                _load_package(root, "protocol"),
                base / "v1-home",
                base / "v1-work",
                base / "v1-skills",
                schema_version=1,
            )
            for agent in (protocol, coordinator, modeling, v1_protocol):
                for path in (agent.home, agent.work, agent.skills):
                    path.mkdir(parents=True)
            (base / "transport" / "broker").mkdir(parents=True)
            for agent in (protocol, coordinator, modeling, v1_protocol):
                (base / "transport" / "broker" / f"{agent.agent_id}.sock").touch()
            adapter._run_root = base
            script = root / "backend/scripts/dev_owl_reasoner.py"
            script_digest = __import__("hashlib").sha256(script.read_bytes()).hexdigest()
            command = adapter.namespace_command(protocol)
            self.assertIn(
                ["--ro-bind", str(script), "/backend/scripts/dev_owl_reasoner.py"],
                [command[index:index + 3] for index in range(len(command) - 2)],
            )
            self.assertNotIn(["--ro-bind", str(script.parent), "/backend/scripts"], [command[index:index + 3] for index in range(len(command) - 2)])
            self.assertNotIn("SEMANTIC_REASONER_COMMAND", command)
            self.assertNotIn("PATH", command)
            for agent in (coordinator, modeling, v1_protocol):
                self.assertNotIn("/backend/scripts/dev_owl_reasoner.py", adapter.namespace_command(agent))
            separator = command.index("--")
            command[separator:] = [
                "--",
                "/bin/sh",
                "-c",
                "set -eu; test -r /backend/scripts/dev_owl_reasoner.py; "
                "test ! -e /backend/scripts/not-mounted.py; "
                "if chmod u+w /backend/scripts/dev_owl_reasoner.py; then exit 1; fi; "
                "if printf changed >> /backend/scripts/dev_owl_reasoner.py; then exit 1; fi",
            ]
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(__import__("hashlib").sha256(script.read_bytes()).hexdigest(), script_digest)

            for case in ("missing", "directory", "symlink"):
                with self.subTest(case=case), tempfile.TemporaryDirectory() as invalid_directory:
                    invalid_root = Path(invalid_directory)
                    invalid_script = invalid_root / "backend/scripts/dev_owl_reasoner.py"
                    invalid_script.parent.mkdir(parents=True)
                    if case == "directory":
                        invalid_script.mkdir()
                    elif case == "symlink":
                        target = invalid_root / "reasoner.py"
                        target.write_text("#!/bin/sh\n", encoding="utf-8")
                        invalid_script.symlink_to(target)
                    invalid_adapter = CodexRuntimeAdapter(repository_root=invalid_root)
                    with self.assertRaisesRegex(CodexRuntimeError, "reasoner script is unavailable"):
                        invalid_adapter._protocol_reasoner_script()

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

    def test_protocol_mechanics_elicitation_is_v2_protocol_only_with_sanitized_evidence(self) -> None:
        root = repository_root()
        cases = (
            ("v2-protocol", "protocol", 2, "protocol_mechanics", "accept"),
            ("v1-protocol", "protocol", 1, "protocol_mechanics", "decline"),
            ("v2-modeling", "modeling", 2, "protocol_mechanics", "decline"),
            ("v2-coordinator", "coordinator", 2, "protocol_mechanics", "decline"),
            ("unknown-server", "protocol", 2, "unknown", "decline"),
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence_path = base / "evidence" / "mcp-elicitations.jsonl"
            for request_id, (case, role, schema_version, server_name, action) in enumerate(cases, start=1):
                with self.subTest(case=case):
                    agent = _Agent(
                        case,
                        _load_package(root, role),
                        base / case / "home",
                        base / case / "work",
                        base / case / "skills",
                        schema_version=schema_version,
                    )
                    agent.process = SimpleNamespace(stdin=StringIO())
                    adapter = CodexRuntimeAdapter(repository_root=root)
                    adapter._run_root = base
                    secret_message = f"message-secret-{case}"
                    secret_schema = f"schema-secret-{case}"
                    adapter._notification(
                        agent,
                        {
                            "id": request_id,
                            "method": "mcpServer/elicitation/request",
                            "params": {
                                "serverName": server_name,
                                "mode": "form",
                                "message": secret_message,
                                "requestedSchema": {
                                    "type": "object",
                                    "properties": {secret_schema: {"type": "string"}},
                                },
                            },
                        },
                    )
                    self.assertEqual(
                        json.loads(agent.process.stdin.getvalue())["result"],
                        {"action": action, "content": {}},
                    )
                    event = json.loads(evidence_path.read_text(encoding="utf-8").splitlines()[-1])
                    self.assertEqual(event["agent_id"], case)
                    self.assertEqual(event["server_name"], server_name)
                    self.assertEqual(event["action"], action)
                    self.assertNotIn(secret_message, json.dumps(event))
                    self.assertNotIn(secret_schema, json.dumps(event))

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

    def test_start_roster_derives_retrieval_gate_eligibility_only_for_v2_protocol_create(self) -> None:
        root = repository_root()
        cases = (
            ("v2-protocol-create", "protocol", 2, "create", True),
            ("v1-protocol-create", "protocol", 1, "create", False),
            ("v2-modeling-create", "modeling", 2, "create", False),
            ("v2-protocol-existing", "protocol", 2, "existing", False),
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for case, role, schema_version, scope_mode, expected in cases:
                with self.subTest(case=case):
                    adapter = CodexRuntimeAdapter(repository_root=root)
                    run = SimpleNamespace(
                        root=base / case,
                        run_id=f"run-{case}",
                        scope={"mode": scope_mode},
                        configuration=SimpleNamespace(
                            task=SimpleNamespace(
                                schema_version=schema_version,
                                protocol_tools=("query_semantic_context",),
                            )
                        ),
                    )
                    profile_agent = SimpleNamespace(agent_id=case, package=_load_package(root, role))
                    with (
                        patch.object(adapter, "_stage_protocol_mechanics_contract"),
                        patch.object(adapter, "_stage_protocol_retrieval_mcp"),
                        patch.object(adapter, "_stage_skills"),
                        patch.object(adapter, "_write_config"),
                        patch.object(adapter, "_start_process", return_value=SimpleNamespace()),
                        patch.object(adapter, "_initialize"),
                        patch.object(adapter, "_app_server_host_pid", return_value=None),
                    ):
                        adapter.start_roster(run, [profile_agent])
                    self.assertEqual(adapter.agents[case].fallback_eligible, expected)

    def test_terminal_guard_drains_pending_stdout_and_fails_closed_when_io_is_busy(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            agent = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                schema_version=2,
                fallback_eligible=True,
            )
            read_fd, write_fd = os.pipe()
            stream = os.fdopen(read_fd, "r", encoding="utf-8")
            self.addCleanup(stream.close)
            self.addCleanup(lambda: os.close(write_fd))
            agent.process = SimpleNamespace(stdin=StringIO(), stdout=stream)
            adapter.agents[agent.agent_id] = agent
            broker = TeamTransportBroker(
                base / "broker", set(), terminal_report_guard=adapter.terminal_report_blocked
            )

            def pending(item: dict[str, object]) -> None:
                value = {"method": "item/completed", "params": {"item": item}}
                os.write(write_fd, (json.dumps(value) + "\n").encode())

            pending(
                {
                    "id": "invalidate",
                    "type": "mcpToolCall",
                    "server": "ontology_platform",
                    "tool": "submit_modeling_batch",
                    "status": "completed",
                    "arguments": {"mode": "apply_atomic"},
                    "result": {"structuredContent": {"ok": True, "data": {}}},
                }
            )
            agent.retrieval_state = "complete"
            with self.assertRaisesRegex(RoutingError, f"^{TERMINAL_REPORT_GUARD_ERROR}$"):
                broker.report("protocol", "blocked", "must observe pending invalidation")
            self.assertEqual(agent.retrieval_state, "query_required")
            self.assertEqual(broker.results, {})

            pending(
                {
                    "id": "complete-query",
                    "type": "mcpToolCall",
                    "server": "ontology_platform",
                    "tool": "query_semantic_context",
                    "status": "completed",
                    "arguments": {"scope_mode": "ontologies", "ontology_ids": ["ontology-1"]},
                    "result": {
                        "structuredContent": {
                            "ok": True,
                            "data": {
                                "result_status": "matched",
                                "recall": {"completeness": "complete"},
                                "truncated": False,
                                "matches_page": {"truncated": False, "next_match_cursor": None},
                                "context_page": {"truncated": False, "next_context_cursor": None},
                                "primary_matches": [
                                    {
                                        "ontology_id": "ontology-1",
                                        "assertion_kind": "asserted",
                                        "evidence_status": "supported",
                                        "lineage": {"status": "complete"},
                                        "warnings": [],
                                    }
                                ],
                                "related_context": [],
                                "warnings": [],
                            },
                        }
                    },
                }
            )
            broker.report("protocol", "blocked", "must observe pending complete query")
            self.assertEqual(agent.retrieval_state, "complete")

            busy = TeamTransportBroker(
                base / "busy", set(), terminal_report_guard=adapter.terminal_report_blocked
            )
            locked, release = threading.Event(), threading.Event()

            def hold_io_lock() -> None:
                with agent.io_lock:
                    locked.set()
                    release.wait(timeout=1)

            holder = threading.Thread(target=hold_io_lock)
            holder.start()
            self.assertTrue(locked.wait(timeout=1))
            try:
                with self.assertRaisesRegex(RoutingError, f"^{TERMINAL_REPORT_GUARD_ERROR}$"):
                    busy.report("protocol", "blocked", "retry after foreground reader")
            finally:
                release.set()
                holder.join(timeout=1)
            self.assertEqual(busy.results, {})

    def test_legacy_dynamic_reports_from_rpc_and_receive_messages_do_not_deadlock(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)

            def build(agent_id: str):
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = base
                agent = _Agent(
                    agent_id,
                    _load_package(root, "protocol"),
                    base / f"{agent_id}-home",
                    base / f"{agent_id}-work",
                    base / f"{agent_id}-skills",
                    schema_version=2,
                    fallback_eligible=True,
                )
                read_fd, write_fd = os.pipe()
                stream = os.fdopen(read_fd, "r", encoding="utf-8")
                agent.process = SimpleNamespace(stdin=StringIO(), stdout=stream)
                adapter.agents[agent_id] = agent
                broker = TeamTransportBroker(
                    base / f"broker-{agent_id}",
                    set(),
                    terminal_report_guard=adapter.terminal_report_blocked,
                )
                broker.start([agent_id])
                (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
                return adapter, agent, broker, stream, write_fd

            def dynamic_line(call_id: str) -> dict[str, object]:
                return {
                    "id": call_id,
                    "method": "item/tool/call",
                    "params": {
                        "tool": "mcp__team_transport__report_task_result",
                        "arguments": {"status": "blocked", "summary": "legacy callback"},
                    },
                }

            def invoke_bounded(callback):
                outcome: list[object] = []

                def run() -> None:
                    try:
                        outcome.append(callback())
                    except Exception as exc:  # pragma: no cover - failure is asserted below
                        outcome.append(exc)

                worker = threading.Thread(target=run)
                worker.start()
                worker.join(timeout=1)
                self.assertFalse(worker.is_alive(), "legacy callback deadlocked")
                self.assertFalse(outcome and isinstance(outcome[0], Exception), outcome)
                return outcome[0] if outcome else None

            adapter, agent, broker, stream, write_fd = build("protocol-rpc")
            self.addCleanup(broker.stop)
            self.addCleanup(stream.close)
            self.addCleanup(lambda fd=write_fd: os.close(fd))
            agent.retrieval_state = "fallback_required"
            os.write(
                write_fd,
                (json.dumps(dynamic_line("rpc-blocked")) + "\n" + json.dumps({"id": 1, "result": {}}) + "\n").encode(),
            )
            self.assertEqual(invoke_bounded(lambda: adapter._rpc(agent, "test", {})), {})
            self.assertIn(TERMINAL_REPORT_GUARD_ERROR, agent.process.stdin.getvalue())
            self.assertEqual(broker.results, {})
            agent.retrieval_state = "complete"
            os.write(
                write_fd,
                (json.dumps(dynamic_line("rpc-allowed")) + "\n" + json.dumps({"id": 2, "result": {}}) + "\n").encode(),
            )
            self.assertEqual(invoke_bounded(lambda: adapter._rpc(agent, "test", {})), {})
            self.assertIn("protocol-rpc", broker.results)

            adapter, agent, broker, stream, write_fd = build("protocol-receive")
            self.addCleanup(broker.stop)
            self.addCleanup(stream.close)
            self.addCleanup(lambda fd=write_fd: os.close(fd))
            agent.retrieval_state = "fallback_required"
            os.write(write_fd, (json.dumps(dynamic_line("receive-blocked")) + "\n").encode())
            self.assertEqual(invoke_bounded(adapter.receive_messages), [])
            self.assertIn(TERMINAL_REPORT_GUARD_ERROR, agent.process.stdin.getvalue())
            self.assertEqual(broker.results, {})
            agent.retrieval_state = "complete"
            os.write(write_fd, (json.dumps(dynamic_line("receive-allowed")) + "\n").encode())
            self.assertEqual(invoke_bounded(adapter.receive_messages), [])
            self.assertIn("protocol-receive", broker.results)

    def test_protocol_retrieval_gate_requires_completed_eligible_query_and_current_verifier(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            agent = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                schema_version=2,
                fallback_eligible=True,
            )
            agent.process = SimpleNamespace(stdin=StringIO())
            adapter.agents[agent.agent_id] = agent
            broker = TeamTransportBroker(
                base / "broker", set(), terminal_report_guard=adapter.terminal_report_blocked
            )
            broker.start(["protocol", "protocol-complete"])
            self.addCleanup(broker.stop)
            (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
            sequence = 0

            def formal_query(*, evidence: str = "supported", ontology_id: str = "ontology-1") -> dict[str, object]:
                item = {
                    "ontology_id": ontology_id,
                    "assertion_kind": "asserted",
                    "evidence_status": evidence,
                    "lineage": {"status": "complete"},
                    "warnings": [],
                }
                return {
                    "ok": True,
                    "data": {
                        "result_status": "matched",
                        "recall": {"completeness": "complete"},
                        "truncated": False,
                        "matches_page": {"truncated": False, "next_match_cursor": None},
                        "context_page": {"truncated": False, "next_context_cursor": None},
                        "primary_matches": [item],
                        "related_context": [],
                        "warnings": [],
                    },
                }

            def completed(
                server: str,
                tool: str,
                *,
                status: str = "completed",
                arguments: dict[str, object] | None = None,
                result: object | None = None,
                error: object | None = None,
                item_id: object = None,
            ) -> None:
                nonlocal sequence
                sequence += 1
                item: dict[str, object] = {
                    "id": item_id if item_id is not None else f"mcp-{sequence}",
                    "type": "mcpToolCall",
                    "server": server,
                    "tool": tool,
                    "status": status,
                }
                if arguments is not None:
                    item["arguments"] = arguments
                elif server == "protocol_mechanics" and tool == "verify_scoped_retrieval_fallback":
                    item["arguments"] = {"mode": "create"}
                if result is not None:
                    item["result"] = result
                if error is not None:
                    item["error"] = error
                adapter._notification(agent, {"method": "item/completed", "params": {"item": item}})

            query_arguments = {
                "scope_mode": "ontologies",
                "ontology_ids": ["ontology-1"],
                "queries": ["retrieval-secret"],
            }
            completed(
                "protocol_mechanics",
                "verify_scoped_retrieval_fallback",
                result={"structuredContent": {"complete": True}},
            )
            completed(
                "ontology_platform",
                "query_semantic_context",
                status="in_progress",
                arguments=query_arguments,
                result={"structuredContent": formal_query()},
            )
            completed(
                "ontology_platform",
                "query_semantic_context",
                arguments=query_arguments,
                item_id=17,
                result={"structuredContent": formal_query()},
            )
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (0, "idle"))

            completed(
                "ontology_platform",
                "query_semantic_context",
                status="failed",
                arguments=query_arguments,
                error={"code": -1},
            )
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (1, "fallback_required"))
            blocked = adapter._dynamic_tool_result(
                agent,
                "mcp__team_transport__report_task_result",
                {"status": "blocked", "summary": "do not disclose retrieval-secret"},
            )
            self.assertEqual(
                blocked["contentItems"][0]["text"],
                f"Team Transport rejected the request: {TERMINAL_REPORT_GUARD_ERROR}",
            )
            self.assertEqual(broker.results, {})
            ordinary_message = adapter._dynamic_tool_result(
                agent,
                "mcp__team_transport__send_team_message",
                {"recipient_id": "modeling", "text": "ordinary transport"},
            )
            self.assertNotEqual(
                ordinary_message["contentItems"][0]["text"],
                TERMINAL_REPORT_GUARD_ERROR,
            )

            adapter._notification(
                agent,
                {
                    "id": 9,
                    "method": "mcpServer/elicitation/request",
                    "params": {"serverName": "protocol_mechanics", "requestedSchema": {}},
                },
            )
            self.assertEqual(agent.retrieval_state, "fallback_required")
            completed(
                "protocol_mechanics",
                "verify_scoped_retrieval_fallback",
                result={"structuredContent": {"complete": True}},
            )
            self.assertEqual(agent.retrieval_state, "fallback_satisfied")
            accepted_after_verifier = adapter._dynamic_tool_result(
                agent,
                "mcp__team_transport__report_task_result",
                {"status": "blocked", "summary": "native verifier attempted"},
            )
            self.assertTrue(accepted_after_verifier["success"])
            self.assertEqual(broker.results["protocol"].status, "blocked")

            completed(
                "ontology_platform",
                "query_semantic_context",
                arguments=query_arguments,
                result=formal_query(),
            )
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (2, "fallback_required"))
            completed(
                "protocol_mechanics",
                "verify_scoped_retrieval_fallback",
                status="failed",
                error={"code": -32010},
            )
            self.assertEqual(agent.retrieval_state, "fallback_required")

            completed(
                "ontology_platform",
                "query_semantic_context",
                arguments=query_arguments,
                result={"structuredContent": formal_query()},
            )
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (3, "complete"))
            for invalid_arguments in (
                {"scope_mode": "project", "ontology_ids": ["ontology-1"]},
                {"scope_mode": "ontologies", "ontology_ids": []},
                {"scope_mode": "ontologies", "ontology_ids": ["", 4]},
            ):
                completed(
                    "ontology_platform",
                    "query_semantic_context",
                    arguments=invalid_arguments,
                    result={"structuredContent": formal_query()},
                )
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (3, "complete"))

            complete_agent = _Agent(
                "protocol-complete",
                _load_package(root, "protocol"),
                base / "complete-home",
                base / "complete-work",
                base / "complete-skills",
                schema_version=2,
                fallback_eligible=True,
            )
            adapter.agents[complete_agent.agent_id] = complete_agent
            adapter._notification(
                complete_agent,
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "id": "complete-generic",
                            "type": "mcpToolCall",
                            "server": "ontology_platform",
                            "tool": "query_semantic_context",
                            "status": "completed",
                            "arguments": query_arguments,
                            "result": {"structuredContent": formal_query()},
                        }
                    },
                },
            )
            self.assertEqual(complete_agent.retrieval_state, "complete")
            accepted_after_complete = adapter._dynamic_tool_result(
                complete_agent,
                "mcp__team_transport__report_task_result",
                {"status": "blocked", "summary": "complete generic evidence"},
            )
            self.assertTrue(accepted_after_complete["success"])
            self.assertEqual(broker.results["protocol-complete"].status, "blocked")

            evidence = (base / "evidence" / "protocol-retrieval-gate.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("retrieval-secret", evidence)
            self.assertNotIn('"arguments"', evidence)
            self.assertNotIn('"result"', evidence)

    def test_protocol_retrieval_gate_fails_closed_for_result_quality_and_semantic_state_changes(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._run_root = base
            agent = _Agent(
                "protocol",
                _load_package(root, "protocol"),
                base / "home",
                base / "work",
                base / "skills",
                schema_version=2,
                fallback_eligible=True,
            )
            adapter.agents[agent.agent_id] = agent
            broker = TeamTransportBroker(
                base / "broker", set(), terminal_report_guard=adapter.terminal_report_blocked
            )
            broker.start(["protocol"])
            self.addCleanup(broker.stop)
            (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
            sequence = 0

            def completed(tool: str, *, arguments=None, result=None, status="completed", server="ontology_platform"):
                nonlocal sequence
                sequence += 1
                item = {
                    "id": f"quality-{sequence}",
                    "type": "mcpToolCall",
                    "server": server,
                    "tool": tool,
                    "status": status,
                }
                if arguments is not None:
                    item["arguments"] = arguments
                elif server == "protocol_mechanics" and tool == "verify_scoped_retrieval_fallback":
                    item["arguments"] = {"mode": "create"}
                if result is not None:
                    item["result"] = result
                adapter._notification(agent, {"method": "item/completed", "params": {"item": item}})

            def formal_query(**item_overrides):
                item = {
                    "ontology_id": "ontology-1",
                    "assertion_kind": "asserted",
                    "evidence_status": "supported",
                    "lineage": {"status": "complete"},
                    "warnings": [],
                }
                item.update(item_overrides)
                return {
                    "ok": True,
                    "data": {
                        "result_status": "matched",
                        "recall": {"completeness": "complete"},
                        "truncated": False,
                        "matches_page": {"truncated": False, "next_match_cursor": None},
                        "context_page": {"truncated": False, "next_context_cursor": None},
                        "primary_matches": [item],
                        "related_context": [],
                        "warnings": [],
                    },
                }

            query_arguments = {"scope_mode": "ontologies", "ontology_ids": ["ontology-1"]}
            success = {"structuredContent": {"ok": True, "data": {}}}
            completed("submit_modeling_batch", arguments={"mode": "apply_atomic"}, result=success)
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (0, "query_required"))
            blocked_query_required = adapter._dynamic_tool_result(
                agent,
                "mcp__team_transport__report_task_result",
                {"status": "blocked", "summary": "semantic state changed"},
            )
            self.assertEqual(
                blocked_query_required["contentItems"][0]["text"],
                f"Team Transport rejected the request: {TERMINAL_REPORT_GUARD_ERROR}",
            )
            self.assertEqual(broker.results, {})
            completed(
                "verify_scoped_retrieval_fallback",
                server="protocol_mechanics",
                result={"structuredContent": {"complete": True}},
            )
            self.assertEqual(agent.retrieval_state, "query_required")
            completed("query_semantic_context", arguments=query_arguments, result={"structuredContent": formal_query()})
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (1, "complete"))

            completed("run_semantic_validation", result=success)
            self.assertEqual(agent.retrieval_state, "query_required")
            completed("submit_modeling_batch", arguments={"mode": "dry_run"}, result=success)
            completed("run_semantic_reasoning", result=success, status="failed")
            self.assertEqual(agent.retrieval_state, "query_required")
            completed("query_semantic_context", arguments=query_arguments, result={"structuredContent": formal_query()})
            self.assertEqual((agent.retrieval_episode, agent.retrieval_state), (2, "complete"))

            def with_data(**overrides):
                value = formal_query()
                value["data"].update(overrides)
                return value

            for malformed in (
                formal_query(evidence_status="missing"),
                formal_query(ontology_id="ontology-other"),
                formal_query(lineage={"status": "partial"}),
                with_data(recall={"completeness": "degraded"}),
                with_data(truncated=True),
                with_data(matches_page={"truncated": True, "next_match_cursor": None}),
                with_data(matches_page={"truncated": False, "next_match_cursor": "more"}),
                with_data(result_status="no_match"),
                with_data(warnings=[{"code": "legacy_lineage_unavailable"}]),
                with_data(warnings=None),
                with_data(primary_matches=None),
            ):
                completed("query_semantic_context", arguments=query_arguments, result={"structuredContent": malformed})
                self.assertEqual(agent.retrieval_state, "fallback_required")
                adapter._notification(agent, {"method": "turn/completed", "params": {}})
                adapter._notification(agent, {"method": "turn/started", "params": {"turn": {"id": "later"}}})
                completed(
                    "verify_scoped_retrieval_fallback",
                    server="protocol_mechanics",
                    result={"structuredContent": {"complete": True}},
                )
                self.assertEqual(agent.retrieval_state, "fallback_satisfied")

            noneligible = _Agent(
                "modeling",
                _load_package(root, "modeling"),
                base / "modeling-home",
                base / "modeling-work",
                base / "modeling-skills",
                schema_version=2,
            )
            adapter._notification(
                noneligible,
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "id": "noneligible",
                            "type": "mcpToolCall",
                            "server": "ontology_platform",
                            "tool": "query_semantic_context",
                            "status": "completed",
                            "arguments": query_arguments,
                            "result": {"structuredContent": formal_query()},
                        }
                    },
                },
            )
            self.assertEqual((noneligible.retrieval_episode, noneligible.retrieval_state), (0, "idle"))
