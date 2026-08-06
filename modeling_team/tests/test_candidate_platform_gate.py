from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from modeling_team.candidate_platform_gate import (
    CANDIDATE_PLATFORM_GATE_SCHEMA,
    CandidatePlatformGate,
)
from modeling_team.protocol_mcp_launch import protocol_mcp_launch_spec
from modeling_team.runtimes.codex import _Agent, CodexRuntimeAdapter
from modeling_team.runtimes.base import RuntimeDelivery
from modeling_team.contracts import repository_root


def _identity() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "protocol_agent_id": "protocol",
        "protocol_thread_id": "thread-1",
        "original_delivery_id": "delivery-1",
        "candidate_revision": 1,
        "semantic_digest": "a" * 64,
        "candidate_digest": "b" * 64,
    }


def _state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_platform_gate_is_closed_until_runner_opens_it(tmp_path: Path) -> None:
    gate = CandidatePlatformGate.ensure(tmp_path / "candidate-gate")
    assert _state(gate.state_path) == {
        "schema_version": CANDIDATE_PLATFORM_GATE_SCHEMA,
        "state": "closed",
        "reason_code": "awaiting_candidate_receipt",
    }

    gate.open(_identity())
    assert _state(gate.state_path)["state"] == "open"
    gate.close("protocol_conflict")
    assert _state(gate.state_path)["state"] == "closed"


def test_candidate_platform_gate_reuses_existing_state(tmp_path: Path) -> None:
    gate = CandidatePlatformGate.ensure(tmp_path / "candidate-gate")
    gate.open(_identity())
    same = CandidatePlatformGate.ensure(tmp_path / "candidate-gate")
    assert _state(same.state_path)["state"] == "open"


def test_launch_contract_injects_gate_only_when_requested(tmp_path: Path) -> None:
    formal = protocol_mcp_launch_spec(
        frozenset({"check_platform_health"}),
        schema_version=2,
        candidate_gate_path="/opt/candidate-gate/state.json",
    )
    formal_lines = formal.config_lines(api_key="key")
    assert 'FORMAL_CANDIDATE_GATE_PATH = "/opt/candidate-gate/state.json"' in formal_lines

    legacy = protocol_mcp_launch_spec(
        frozenset({"check_platform_health"}),
        schema_version=1,
        candidate_gate_path="/opt/candidate-gate/state.json",
    )
    assert all("FORMAL_CANDIDATE_GATE_PATH" not in line for line in legacy.config_lines(api_key="key"))


def _protocol_agent(root: Path, name: str = "protocol") -> _Agent:
    home, work, skills = (root / f"{name}-home", root / f"{name}-work", root / f"{name}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True)
    package = SimpleNamespace(role="protocol")
    return _Agent(
        name,
        package,
        home,
        work,
        skills,
        platform_tools=frozenset({"check_platform_health"}),
        schema_version=2,
    )


def _run_for_gate(root: Path, *, formal: bool) -> SimpleNamespace:
    (root / "sources" / "protocol").mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        run_id="run-formal-gate" if formal else "run-legacy-v2",
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(
                schema_version=2,
                task_id="r2-3-005-formal-acceptance" if formal else "ordinary-v2",
            )
        ),
    )


def test_codex_formal_config_and_namespace_bind_gate_read_only(monkeypatch, tmp_path: Path) -> None:
    root = repository_root()
    base = tmp_path / "formal"
    base.mkdir()
    run = _run_for_gate(base, formal=True)
    agent = _protocol_agent(base)
    host_auth = base / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter = CodexRuntimeAdapter(repository_root=root)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    adapter._write_config(run, agent)
    config = (agent.home / "config.toml").read_text(encoding="utf-8")
    assert 'FORMAL_CANDIDATE_GATE_PATH = "/opt/candidate-gate/state.json"' in config
    assert (base / "candidate-gate" / "state.json").is_file()

    adapter._run_root = base
    adapter._candidate_platform_gate_enabled = True
    command = adapter.namespace_command(agent)
    mount = ["--ro-bind", str(base / "candidate-gate"), "/opt/candidate-gate"]
    assert any(command[index : index + 3] == mount for index in range(len(command) - 2))


def test_codex_nonformal_v2_has_no_candidate_gate_env_or_mount(monkeypatch, tmp_path: Path) -> None:
    root = repository_root()
    base = tmp_path / "legacy"
    base.mkdir()
    run = _run_for_gate(base, formal=False)
    agent = _protocol_agent(base)
    host_auth = base / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    adapter = CodexRuntimeAdapter(repository_root=root)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    adapter._write_config(run, agent)
    config = (agent.home / "config.toml").read_text(encoding="utf-8")
    assert "FORMAL_CANDIDATE_GATE_PATH" not in config
    assert not (base / "candidate-gate").exists()

    adapter._run_root = base
    adapter._candidate_platform_gate_enabled = False
    command = adapter.namespace_command(agent)
    assert "/opt/candidate-gate" not in command


def test_codex_direct_delivery_preserves_receipt_wakeup_kind_and_fact() -> None:
    delivery = RuntimeDelivery(
        sender_id="runner/candidate-gate",
        recipient_id="protocol",
        kind="candidate-receipt-registered",
        text='{"schema_version":"r2-3-005-candidate-receipt-registered/v1"}',
        delivery_id="candidate-receipt-registered:receipt-1",
        reply_to_delivery_id="receipt-1",
    )
    rendered = json.loads(CodexRuntimeAdapter._delivery_input(delivery)[0]["text"])
    assert rendered["kind"] == "candidate-receipt-registered"
    assert rendered["text"] == delivery.text
    assert rendered["delivery_id"] == delivery.delivery_id
    assert rendered["reply_to_delivery_id"] == delivery.reply_to_delivery_id
