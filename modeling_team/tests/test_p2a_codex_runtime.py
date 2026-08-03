from __future__ import annotations

import hashlib
import json
import os
import stat
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.p2a_batch_plan import validate_overlay_contract
from modeling_team.runtimes import p2a_codex
from modeling_team.runtimes.base import RuntimeDelivery
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
from modeling_team.runtimes.p2a_codex import P2ACodexRuntimeAdapter


ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOBAL_SURFACES = {
    "modeling_team/runner.py": "d6a2f1bce9ecf52c0c4e087f419f8e84c588c35dc6fd3e0197b08b2f1e2ee806",
    "modeling_team/protocol_mechanics.py": "f8e8aff440136b652d093ff6b040168d692193ef91ef1e6df1203613f05f49ea",
    "modeling_team/protocol_retrieval_mcp.py": "dbf1d7f376c227ada0a711288a95507a729eab58768298cc36f0a4f0a9560742",
    "modeling_team/runtimes/codex.py": "036430d806f5972b31c082b51bbe46c04d02e5bcc70f4edd3ceb49f03ff0bf18",
    "backend/app/api/schemas.py": "bce7e92dffa6d07a43cba87f60d5436b8a9fd91bed7793928500a529821bdef6",
}


def _run(tmp_path: Path, task_id: str = "p2a-protocol-production"):
    task = SimpleNamespace(task_id=task_id, schema_version=2)
    return SimpleNamespace(
        root=tmp_path / "run",
        run_id="p2a-runtime-1",
        configuration=SimpleNamespace(task=task),
    )


def test_normal_runtime_and_platform_surfaces_remain_byte_frozen():
    assert {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in FROZEN_GLOBAL_SURFACES
    } == FROZEN_GLOBAL_SURFACES


def _agent(tmp_path: Path):
    return SimpleNamespace(
        agent_id="protocol",
        package=SimpleNamespace(role="protocol"),
        proof_v2_path=ROOT / "modeling_team/proof_v2.py",
        home=tmp_path / "home",
        platform_tools=frozenset({"check_platform_health"}),
        schema_version=2,
        retrieval_asset_fds=(),
        thread_id="thread-p2a",
        active_turn_id="turn-p2a",
        process=SimpleNamespace(stdin=StringIO()),
    )


def _typed_proof_v2_arguments() -> dict[str, object]:
    return {
        "mode": "create",
        "initial_modeling_context": {},
        "final_modeling_context": {},
        "workspace_context": {},
        "batch_inventory": {},
        "batch_details": [],
        "entities_read": {},
        "statements_read": {},
        "candidate_required_assertions": {},
        "term_bindings": [],
        "materialized_quads": [],
        "materialized_digest": "digest",
        "evidence_bindings": [],
        "statement_lineage": [],
        "pagination": {},
    }


def _skip_normal_stage(monkeypatch):
    def stage(_self, _run_value, agent):
        agent.proof_v2_path = ROOT / "modeling_team/proof_v2.py"

    monkeypatch.setattr(CodexRuntimeAdapter, "_stage_protocol_retrieval_mcp", stage)


def test_p2a_overlay_staging_materializes_exact_run_contract(monkeypatch, tmp_path):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path)
    run.root.mkdir()
    agent = _agent(tmp_path)
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)

    adapter._stage_protocol_retrieval_mcp(run, agent)

    paths = adapter._overlay_paths["protocol"]
    assert [path.name for path in paths] == [
        "p2a_batch_plan.py",
        "p2a_protocol_overlay_mcp.py",
        "p2a-overlay-contract.json",
    ]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in paths)
    contract = json.loads(paths[-1].read_text())
    validate_overlay_contract(contract, expected_run_id=run.run_id)


@pytest.mark.parametrize("task_id", ["ordinary-task", "p2a-protocol-production-extra"])
def test_overlay_staging_rejects_non_p2a_tasks(monkeypatch, tmp_path, task_id):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path, task_id)
    run.root.mkdir()
    with pytest.raises(CodexRuntimeError, match="task/run/role"):
        P2ACodexRuntimeAdapter(repository_root=ROOT)._stage_protocol_retrieval_mcp(
            run,
            _agent(tmp_path),
        )


def test_overlay_config_is_appended_only_by_p2a_subclass(monkeypatch, tmp_path):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path)
    run.root.mkdir()
    agent = _agent(tmp_path)
    agent.home.mkdir()
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    adapter._stage_protocol_retrieval_mcp(run, agent)

    def normal_config(_self, _run_value, agent_value):
        (agent_value.home / "config.toml").write_text("normal = true\n")

    monkeypatch.setattr(CodexRuntimeAdapter, "_write_config", normal_config)
    adapter._write_config(run, agent)
    config = (agent.home / "config.toml").read_text()
    assert config.startswith("normal = true\n")
    assert config.count("[mcp_servers.p2a_protocol_overlay]") == 1
    assert 'P2A_RUNTIME_TASK_ID = "p2a-protocol-production"' in config
    assert stat.S_IMODE((agent.home / "config.toml").stat().st_mode) == 0o600


def _server(name: str, tools: set[str]) -> dict[str, object]:
    return {"name": name, "tools": [{"name": tool} for tool in sorted(tools)]}


def _status(agent, *, extra: bool = False) -> dict[str, object]:
    values = [
        _server("team_transport", {"send_team_message", "report_task_result"}),
        _server("ontology_platform", set(agent.platform_tools)),
        _server(
            "protocol_mechanics",
            {
                "build_candidate_receipt",
                "verify_scoped_retrieval_fallback",
                "write_candidate_item_evidence_map",
            },
        ),
        _server("p2a_protocol_overlay", p2a_codex.OVERLAY_TOOLS),
    ]
    if extra:
        values.append(_server("unexpected", {"tool"}))
    return {"data": values}


def test_preflight_keeps_exact_normal_three_and_exact_overlay(monkeypatch, tmp_path):
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    agent = _agent(tmp_path)
    monkeypatch.setattr(adapter, "_rpc", lambda *_args: _status(agent))
    adapter._require_expected_mcp_servers(agent)
    assert adapter._overlay_preflight_agents == {agent.agent_id}


def test_preflight_rejects_any_extra_server(monkeypatch, tmp_path):
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    agent = _agent(tmp_path)
    monkeypatch.setattr(adapter, "_rpc", lambda *_args: _status(agent, extra=True))
    times = iter((0.0, 1.0, 26.0))
    monkeypatch.setattr(p2a_codex.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(p2a_codex.time, "sleep", lambda _seconds: None)
    with pytest.raises(CodexRuntimeError, match="preflight failed"):
        adapter._require_expected_mcp_servers(agent)
    assert not adapter._overlay_preflight_agents


def _ready_elicitation_adapter(monkeypatch, tmp_path: Path):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path)
    run.root.mkdir()
    agent = _agent(tmp_path)
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    adapter._run_root = run.root
    adapter._run_id = run.run_id
    adapter.agents[agent.agent_id] = agent
    adapter._stage_protocol_retrieval_mcp(run, agent)
    monkeypatch.setattr(adapter, "_rpc", lambda *_args: _status(agent))
    adapter._require_expected_mcp_servers(agent)
    return run, agent, adapter


def _elicitation(agent, tool_name: str) -> dict[str, object]:
    return {
        "id": 72,
        "method": "mcpServer/elicitation/request",
        "params": {
            "_meta": {
                "codex_approval_kind": "mcp_tool_call",
                "tool_params": {"private": "must-not-be-retained"},
            },
            "message": (
                f'Allow the p2a_protocol_overlay MCP server to run tool "{tool_name}"?'
            ),
            "mode": "form",
            "requestedSchema": {"type": "object", "properties": {}},
            "serverName": "p2a_protocol_overlay",
            "threadId": agent.thread_id,
            "turnId": agent.active_turn_id,
        },
    }


@pytest.mark.parametrize("tool_name", sorted(p2a_codex.OVERLAY_TOOLS))
def test_exact_overlay_tool_elicitation_is_accepted_without_raw_args(
    monkeypatch,
    tmp_path,
    tool_name,
):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)

    adapter._notification(agent, _elicitation(agent, tool_name))

    response = json.loads(agent.process.stdin.getvalue())
    assert response["result"] == {"action": "accept", "content": {}}
    evidence = (adapter._run_root / "evidence" / "mcp-elicitations.jsonl").read_text()
    assert json.loads(evidence)["action"] == "accept"
    assert tool_name not in evidence
    assert "must-not-be-retained" not in evidence


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "extra",
        "wrong-tool",
        "wrong-meta-tool",
        "wrong-server",
        "wrong-role",
        "wrong-task",
        "wrong-run",
        "no-preflight",
        "tamper",
    ],
)
def test_overlay_elicitation_context_drift_delegates_to_normal_decline(
    monkeypatch,
    tmp_path,
    case,
):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)
    request = _elicitation(agent, "build_p2a_batch_plan")
    if case == "missing":
        request["params"].pop("turnId")
    elif case == "extra":
        request["params"]["unexpected"] = "value"
    elif case == "wrong-tool":
        request["params"]["message"] = (
            'Allow the p2a_protocol_overlay MCP server to run tool "unexpected"?'
        )
    elif case == "wrong-meta-tool":
        request["params"]["_meta"]["tool_name"] = "unexpected"
    elif case == "wrong-server":
        request["params"]["serverName"] = "unexpected"
    elif case == "wrong-role":
        agent.package.role = "modeling"
    elif case == "wrong-task":
        adapter._overlay_contracts[agent.agent_id]["task_id"] = "unexpected"
    elif case == "wrong-run":
        adapter._run_id = "unexpected-run"
    elif case == "no-preflight":
        adapter._overlay_preflight_agents.clear()
    else:
        adapter._overlay_contracts[agent.agent_id]["tools"].append("unexpected")

    adapter._notification(agent, request)

    response = json.loads(agent.process.stdin.getvalue())
    assert response["result"] == {"action": "decline", "content": {}}


@pytest.mark.parametrize(
    ("server_name", "role", "schema_version", "action"),
    [
        ("team_transport", "modeling", 1, "accept"),
        ("ontology_platform", "protocol", 2, "accept"),
        ("protocol_mechanics", "protocol", 2, "accept"),
        ("unknown", "protocol", 2, "decline"),
    ],
)
def test_non_overlay_elicitation_keeps_normal_policy(
    tmp_path,
    server_name,
    role,
    schema_version,
    action,
):
    agent = _agent(tmp_path)
    agent.package.role = role
    agent.schema_version = schema_version
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    adapter._run_root = tmp_path
    request = _elicitation(agent, "build_p2a_batch_plan")
    request["params"]["serverName"] = server_name

    adapter._notification(agent, request)

    response = json.loads(agent.process.stdin.getvalue())
    assert response["result"] == {"action": action, "content": {}}


def test_overlay_descriptor_mounts_fail_closed_on_metadata_drift(monkeypatch, tmp_path):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path)
    run.root.mkdir()
    agent = _agent(tmp_path)
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    adapter._stage_protocol_retrieval_mcp(run, agent)
    adapter._run_root = run.root
    adapter.agents[agent.agent_id] = agent
    paths = adapter._overlay_paths[agent.agent_id]

    descriptors = adapter._open_overlay_assets(agent, paths)
    assert len(descriptors) == 3
    adapter._close_overlay_asset_fds(agent.agent_id)

    paths[0].chmod(0o600)
    with pytest.raises(CodexRuntimeError, match="metadata"):
        adapter._open_overlay_assets(agent, paths)


def test_failed_native_verifier_records_only_safe_p2a_classification(monkeypatch, tmp_path):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)
    agent.completed_mcp_item_ids = set()
    secret = "must-never-be-retained"
    cases = [
        (
            "failed-arguments",
            -32602,
            {"mode": "create", "extra": secret},
            "argument_contract",
            False,
            False,
        ),
        (
            "failed-proof",
            -32010,
            _typed_proof_v2_arguments(),
            "proof_validation",
            True,
            True,
        ),
    ]
    for item_id, error_code, arguments, layer, top_level_exact, types_valid in cases:
        adapter._notification(
            agent,
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "id": item_id,
                        "type": "mcpToolCall",
                        "server": "protocol_mechanics",
                        "tool": "verify_scoped_retrieval_fallback",
                        "status": "failed",
                        "arguments": arguments,
                        "result": {"raw": secret},
                        "meta": {"secret": secret},
                        "error": {
                            "message": f"tools/call failed: Mcp error: {error_code}: {layer}:{secret}",
                            "data": {"raw": secret},
                        },
                    }
                },
            },
        )
        event = json.loads(
            (tmp_path / "run/evidence/native-verifier-events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[-1]
        )
        assert set(event) == {
            "error_code",
            "failure_layer",
            "error_message_sha256",
            "top_level_exact",
            "types_valid",
            "mode_create",
        }
        assert event == {
            "error_code": error_code,
            "failure_layer": layer,
            "error_message_sha256": hashlib.sha256(
                f"tools/call failed: Mcp error: {error_code}: {layer}:{secret}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            "top_level_exact": top_level_exact,
            "types_valid": types_valid,
            "mode_create": True,
        }
    retained = (tmp_path / "run/evidence/native-verifier-events.jsonl").read_text(
        encoding="utf-8"
    )
    assert secret not in retained
    assert all(token not in retained for token in ('"arguments"', '"result"', '"meta"', '"raw"'))


def _native_verifier_elicitation(agent, *, tool_name="verify_scoped_retrieval_fallback"):
    return {
        "id": 91,
        "method": "mcpServer/elicitation/request",
        "params": {
            "_meta": {
                "codex_approval_kind": "mcp_tool_call",
                "tool_name": tool_name,
                "tool_params": {"secret": "must-not-be-retained"},
            },
            "message": (
                f'Allow the protocol_mechanics MCP server to run tool "{tool_name}"?'
            ),
            "mode": "form",
            "requestedSchema": {"type": "object", "properties": {}},
            "serverName": "protocol_mechanics",
            "threadId": agent.thread_id,
            "turnId": agent.active_turn_id,
        },
    }


def test_p2a_native_verifier_approval_hard_caps_three_and_retains_safe_count(
    monkeypatch,
    tmp_path,
):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)
    responses = []
    for index in range(4):
        if index == 2:
            agent.active_turn_id = "continuation-turn"
        agent.process.stdin = StringIO()
        request = _native_verifier_elicitation(agent)
        request["id"] = index + 1
        adapter._notification(agent, request)
        responses.append(json.loads(agent.process.stdin.getvalue())["result"]["action"])

    assert responses == ["accept", "accept", "accept", "decline"]
    assert agent.p2a_native_call_count == 3
    retained = (
        tmp_path / "run/evidence/native-verifier-attempt-events.jsonl"
    ).read_text(encoding="utf-8")
    events = [json.loads(line) for line in retained.splitlines()]
    assert [event["native_call_count"] for event in events] == [1, 2, 3, 3]
    assert [event["action"] for event in events] == ["accept", "accept", "accept", "decline"]
    assert all(
        set(event) == {"event", "native_call_count", "action", "created_at_ns"}
        for event in events
    )
    assert "must-not-be-retained" not in retained


def test_wrong_protocol_mechanics_tool_does_not_consume_native_budget(monkeypatch, tmp_path):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)
    request = _native_verifier_elicitation(agent, tool_name="build_candidate_receipt")

    adapter._notification(agent, request)

    assert not hasattr(agent, "p2a_native_call_count")
    assert not (tmp_path / "run/evidence/native-verifier-attempt-events.jsonl").exists()
    assert json.loads(agent.process.stdin.getvalue())["result"]["action"] == "accept"


def test_inherited_idle_send_message_reuses_exact_thread(monkeypatch, tmp_path):
    _run_value, agent, adapter = _ready_elicitation_adapter(monkeypatch, tmp_path)
    agent.active_turn_id = None
    agent.state = "idle"
    calls = []
    monkeypatch.setattr(adapter, "receive_messages", lambda: [])

    def rpc(_agent_value, method, params):
        calls.append((method, params))
        return {"turn": {"id": "continuation-turn"}}

    monkeypatch.setattr(adapter, "_rpc", rpc)
    adapter.send_message(
        agent.agent_id,
        RuntimeDelivery(
            sender_id="p2a-host",
            recipient_id="protocol",
            kind="p2a-native-correction",
            text="fixed",
            delivery_id="p2a-runtime-1-native-continuation-1",
        ),
    )

    assert calls[0][0] == "turn/start"
    assert calls[0][1]["threadId"] == "thread-p2a"
    assert agent.thread_id == "thread-p2a"
    assert agent.active_turn_id == "continuation-turn"


def test_namespace_combines_normal_and_overlay_fds_for_start_and_visibility(
    monkeypatch,
    tmp_path,
):
    _skip_normal_stage(monkeypatch)
    run = _run(tmp_path)
    run.root.mkdir()
    agent = _agent(tmp_path)
    adapter = P2ACodexRuntimeAdapter(repository_root=ROOT)
    adapter._stage_protocol_retrieval_mcp(run, agent)
    adapter._run_root = run.root
    adapter.agents[agent.agent_id] = agent
    normal_fds = tuple(os.open("/dev/null", os.O_RDONLY) for _ in range(3))

    def normal_namespace(_self, agent_value):
        agent_value.retrieval_asset_fds = normal_fds
        return ["bwrap", "--chdir", "/agent/work", "--", "codex"]

    monkeypatch.setattr(CodexRuntimeAdapter, "namespace_command", normal_namespace)
    command = adapter.namespace_command(agent)
    assert len(agent.retrieval_asset_fds) == 6
    assert command.count("--ro-bind") == 3
    assert all(
        f"/proc/self/fd/{descriptor}" in command
        for descriptor in agent.retrieval_asset_fds[3:]
    )

    adapter._close_retrieval_asset_fds(agent)
    assert agent.retrieval_asset_fds == ()
    assert agent.agent_id not in adapter._overlay_fds
