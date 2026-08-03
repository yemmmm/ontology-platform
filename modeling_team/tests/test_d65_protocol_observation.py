from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import load_profile, repository_root
from modeling_team.runtimes.codex import _Agent, CodexRuntimeAdapter
from modeling_team.transport_mcp import TeamTransportBroker


def _protocol_package(root: Path):
    profile = load_profile(root / "modeling_team/profiles/base-three-agent.yaml", root=root)
    return next(agent.package for agent in profile.agents if agent.package.role == "protocol")


def _native_item(
    item_id: str,
    *,
    status: str = "completed",
    arguments: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": item_id,
        "type": "mcpToolCall",
        "server": "protocol_mechanics",
        "tool": "verify_scoped_retrieval_fallback",
        "status": status,
        "arguments": arguments or {"mode": "create"},
    }
    if result is not None:
        item["result"] = result
    if error is not None:
        item["error"] = error
    return item


def _notify(adapter: CodexRuntimeAdapter, agent: _Agent, item: dict[str, object]) -> None:
    adapter._notification(agent, {"method": "item/completed", "params": {"item": item}})


def test_prior_complete_native_success_is_observed_and_real_report_still_returns() -> None:
    root = repository_root()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter._run_root = base
        agent = _Agent(
            "protocol",
            _protocol_package(root),
            base / "home",
            base / "work",
            base / "skills",
            schema_version=2,
            fallback_eligible=True,
        )
        agent.process = SimpleNamespace(stdin=StringIO())
        agent.retrieval_state = "complete"
        adapter.agents[agent.agent_id] = agent
        broker = TeamTransportBroker(
            base / "broker", set(), terminal_report_guard=adapter.terminal_report_blocked
        )
        broker.start([agent.agent_id])
        (base / "transport-root").write_text(str(broker.root), encoding="utf-8")
        try:
            secret = "retrieval-secret"
            _notify(
                adapter,
                agent,
                _native_item(
                    "native-complete",
                    arguments={"mode": "create", "secret": secret},
                    result={"structuredContent": {"complete": True, "proof_version": 2}},
                ),
            )
            assert agent.retrieval_state == "complete"
            response = adapter._dynamic_tool_result(
                agent,
                "mcp__team_transport__report_task_result",
                {"status": "blocked", "summary": "native result observed"},
            )
            assert response["success"] is True
            assert broker.results[agent.agent_id].status == "blocked"
            events = [
                json.loads(line)
                for line in (base / "evidence/native-verifier-events.jsonl").read_text().splitlines()
            ]
            assert len(events) == 1
            assert set(events[0]) == {
                "role",
                "tool",
                "status",
                "complete",
                "proof_arguments_sha256",
                "result_envelope_sha256",
                "category",
                "recorded_at_ns",
            }
            assert events[0]["status"] == "accepted"
            assert events[0]["complete"] is True
            assert secret not in json.dumps(events[0])
        finally:
            broker.stop()


def test_fallback_required_native_success_satisfies_only_fallback_gate() -> None:
    root = repository_root()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter._run_root = base
        agent = _Agent(
            "protocol",
            _protocol_package(root),
            base / "home",
            base / "work",
            base / "skills",
            schema_version=2,
            fallback_eligible=True,
        )
        adapter.agents[agent.agent_id] = agent
        agent.retrieval_state = "fallback_required"
        _notify(
            adapter,
            agent,
            _native_item(
                "native-fallback",
                result={"structuredContent": {"ok": True, "data": {"complete": True}}},
            ),
        )
        assert agent.retrieval_state == "fallback_satisfied"


def test_failed_or_incomplete_native_results_are_rejected_without_satisfying_gate() -> None:
    root = repository_root()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        adapter = CodexRuntimeAdapter(repository_root=root)
        adapter._run_root = base
        agent = _Agent(
            "protocol",
            _protocol_package(root),
            base / "home",
            base / "work",
            base / "skills",
            schema_version=2,
            fallback_eligible=True,
        )
        adapter.agents[agent.agent_id] = agent
        for item in (
            _native_item("native-failed", status="failed", error={"code": -32602}),
            _native_item(
                "native-incomplete",
                result={"structuredContent": {"ok": True, "data": {"complete": False}}},
            ),
        ):
            agent.retrieval_state = "fallback_required"
            _notify(adapter, agent, item)
            assert agent.retrieval_state == "fallback_required"
        events = [
            json.loads(line)
            for line in (base / "evidence/native-verifier-events.jsonl").read_text().splitlines()
        ]
        assert [event["status"] for event in events] == ["rejected", "rejected"]
        assert all(event["complete"] is False for event in events)
