"""R3.0-016 S1 MCP surface tests (shared plan §3 cold-start and M-layer).

The server under test is the real :mod:`modeling_team.host_ops_mcp` FastMCP
instance driven through the in-memory MCP client session -- the same wire
contract a host gets over stdio, without spawning a process per test.

Isolation (shared plan §2): each test creates its own throwaway run root under
the real ``workspaces/modeling-runs`` (random id, removed afterwards) because
the MCP tools resolve ``run_id`` against the repository workspace; no existing
run, credential or platform is touched.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from shutil import rmtree

from mcp.shared.memory import create_connected_server_and_client_session

from modeling_team import host_ops_mcp
from modeling_team.contracts import repository_root
from modeling_team.outer_input import OuterInputFifo

REPO_ROOT = repository_root()
RUNS_ROOT = REPO_ROOT / "workspaces" / "modeling-runs"

# S2 lifecycle/checkpoint tool names that must NOT appear on the S1 surface.
S2_DENY_NAMES = {
    "pause_run",
    "resume_run",
    "abort_run",
    "checkpoint_run",
    "rollback_run",
    "create_run",
    "start_run",
    "cleanup_run",
    "set_budget",
    "authorize",
    "publish_handoff",
    "cq_acceptance_cli",
}


class _Run:
    """A throwaway run root under the real workspace, removed afterwards."""

    def __init__(self, prefix: str) -> None:
        self.run_id = (
            f"{prefix}-{hashlib.sha256(str(id(self)).encode()).hexdigest()[:10]}"
        )
        self.root = RUNS_ROOT / self.run_id
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "control").mkdir(parents=True)
        (self.root / "state.json").write_text(
            json.dumps({"state": "RUNNING", "run_id": self.run_id}), encoding="utf-8"
        )
        with (self.root / "evidence" / "alpha.jsonl").open("w", encoding="utf-8") as handle:
            for index in range(5):
                handle.write(
                    json.dumps({"n": index, "recorded_at": f"2026-09-18T10:00:0{index}+00:00"})
                    + "\n"
                )

    def __enter__(self) -> "_Run":
        return self

    def __exit__(self, *exc) -> None:
        rmtree(self.root, ignore_errors=True)


def _payload(result) -> dict:
    texts = [item.text for item in result.content if hasattr(item, "text")]
    assert len(texts) == 1
    return json.loads(texts[0])


def _session(calls):
    """Run one client session over the real server and return its results."""

    async def scenario():
        async with create_connected_server_and_client_session(host_ops_mcp.mcp) as client:
            await client.initialize()
            return [await call(client) for call in calls]

    return asyncio.run(scenario())


def test_cold_start_exposes_exactly_the_12_fixed_s1_tools():
    async def list_names(client):
        listing = await client.list_tools()
        return [tool.name for tool in listing.tools]

    names = _session([list_names])[0]
    assert sorted(names) == sorted(host_ops_mcp.TOOL_NAMES)
    assert len(names) == 12
    assert not set(names) & S2_DENY_NAMES


def test_read_tools_return_ok_data_envelopes():
    with _Run("r3016mcp") as run:

        async def status(client):
            return _payload(await client.call_tool("get_run_status", {"run_id": run.run_id}))

        async def events(client):
            return _payload(
                await client.call_tool("get_run_events", {"run_id": run.run_id, "limit": 3})
            )

        async def pending(client):
            return _payload(
                await client.call_tool("get_pending_actions", {"run_id": run.run_id})
            )

        status_out, events_out, pending_out = _session([status, events, pending])
        assert status_out["ok"] is True
        assert status_out["data"]["run_id"] == run.run_id
        assert status_out["data"]["recorded_state"]["state"] == "RUNNING"
        assert events_out["ok"] is True
        assert len(events_out["data"]["events"]) == 3
        assert events_out["data"]["has_more"] is True
        assert pending_out["ok"] is True
        assert pending_out["data"]["limitations"] == ["none"]


def test_error_tools_return_the_design9_error_envelope():
    async def escape(client):
        return _payload(await client.call_tool("get_run_status", {"run_id": "../escape"}))

    envelope = _session([escape])[0]
    assert envelope["ok"] is False
    error = envelope["error"]
    assert error["code"] == "run_id_invalid"
    assert isinstance(error["reason"], str) and error["reason"]
    assert error["retryable"] is False
    assert "next_action" in error


def test_limit_clamp_and_invalid_cursor_are_surfaced_as_limitations_or_errors():
    with _Run("r3016mcp") as run:

        async def at_cap(client):
            return _payload(
                await client.call_tool(
                    "get_run_events", {"run_id": run.run_id, "limit": 1000}
                )
            )

        async def clamped(client):
            return _payload(
                await client.call_tool(
                    "get_run_events", {"run_id": run.run_id, "limit": 5000}
                )
            )

        async def invalid(client):
            return _payload(
                await client.call_tool(
                    "get_run_events", {"run_id": run.run_id, "cursor": "%not-base64%"}
                )
            )

        at_cap_out, clamped_out, invalid_out = _session([at_cap, clamped, invalid])
        assert at_cap_out["ok"] is True
        assert "clamped" not in " ".join(at_cap_out["data"]["limitations"])
        assert clamped_out["ok"] is True
        assert any("clamped to 1000" in item for item in clamped_out["data"]["limitations"])
        assert invalid_out["ok"] is False
        assert invalid_out["error"]["code"] == "cursor_invalid"


def test_submission_and_result_correlation_through_the_mcp_surface():
    with _Run("r3016mcp") as run:
        fifo = OuterInputFifo(Path(run.root) / "control" / "outer-input.fifo")
        fifo.open()
        try:

            async def submit(client):
                return _payload(
                    await client.call_tool(
                        "answer_question",
                        {
                            "run_id": run.run_id,
                            "channel": "cq_interview",
                            "text": "多行\n回答",
                            "request_id": "mcp-req-1",
                        },
                    )
                )

            async def result(client):
                return _payload(
                    await client.call_tool(
                        "get_request_result",
                        {"run_id": run.run_id, "request_id": "mcp-req-1"},
                    )
                )

            async def unknown(client):
                return _payload(
                    await client.call_tool(
                        "get_request_result",
                        {"run_id": run.run_id, "request_id": "never-submitted"},
                    )
                )

            submit_out, result_out, unknown_out = _session([submit, result, unknown])
            assert submit_out["ok"] is True
            assert submit_out["data"]["status"] == "submitted"
            assert result_out["ok"] is True
            assert result_out["data"]["outcome"] == "submitted"
            assert result_out["data"]["request_id"] == "mcp-req-1"
            assert unknown_out["ok"] is False
            assert unknown_out["error"]["code"] == "request_id_unknown"
            fifo.read_ready()
            line = fifo.pop_line()
            assert line is not None
            assert json.loads(line) == {
                "action": "cq_interview",
                "text": "多行\n回答",
                "request_id": "mcp-req-1",
            }
        finally:
            fifo.close()


def test_submit_cq_review_maps_the_wire_digest_parameter():
    with _Run("r3016mcp") as run:
        fifo = OuterInputFifo(Path(run.root) / "control" / "outer-input.fifo")
        fifo.open()
        try:

            async def submit(client):
                return _payload(
                    await client.call_tool(
                        "submit_cq_review",
                        {
                            "run_id": run.run_id,
                            "review_id": "cq-review-0001",
                            "question_id": "cq-1",
                            "decision": "approve",
                            "content_version": 1,
                            "content_digest": "sha256:abc",
                            "revision": 1,
                            "request_id": "mcp-req-2",
                        },
                    )
                )

            (payload,) = _session([submit])
            assert payload["ok"] is True
            fifo.read_ready()
            envelope = json.loads(fifo.pop_line())
            assert envelope["content_digest"] == "sha256:abc"
            assert envelope["schema_version"] == "r3-0-011-cq-review/v1"
        finally:
            fifo.close()


def test_hidden_private_content_never_appears_in_mcp_read_outputs():
    with _Run("r3016mcp") as run:
        marker = "MCP-HIDDEN-MARKER-91c2"
        private = Path(run.root) / "competency-questions" / "private"
        private.mkdir(parents=True)
        (private / "interview-0001.json").write_text(
            json.dumps({"schema_version": "r3-0-011-cq-interview/v1", "text": marker}),
            encoding="utf-8",
        )

        async def status(client):
            return _payload(await client.call_tool("get_run_status", {"run_id": run.run_id}))

        async def events(client):
            return _payload(await client.call_tool("get_run_events", {"run_id": run.run_id}))

        async def pending(client):
            return _payload(
                await client.call_tool("get_pending_actions", {"run_id": run.run_id})
            )

        for payload in _session([status, events, pending]):
            assert marker not in json.dumps(payload, ensure_ascii=False)


def test_config_json_registers_the_stdio_command_for_this_checkout():
    config = json.loads(
        (REPO_ROOT / ".claude" / "modeling-team-host-mcp.json").read_text(encoding="utf-8")
    )
    server = config["mcpServers"]["modeling-team-host"]
    assert server["command"] == str(REPO_ROOT / "backend" / ".venv" / "bin" / "python")
    assert server["args"] == ["-m", "modeling_team.host_ops_mcp"]
    assert Path(server["cwd"]) == REPO_ROOT
