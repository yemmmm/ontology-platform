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

from modeling_team import host_ops, host_ops_mcp
from modeling_team.contracts import repository_root
from modeling_team.outer_input import OuterInputFifo

REPO_ROOT = repository_root()
RUNS_ROOT = REPO_ROOT / "workspaces" / "modeling-runs"

# Names that must never appear on the host surface: phantom or renamed tools.
FORBIDDEN_TOOL_NAMES = {
    "resume_run",
    "abort_run",
    "checkpoint_run",
    "rollback_run",
    "create_run",
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


def test_checkpoint_resume_model_profile_passes_through_mcp(monkeypatch):
    captured = []

    def resume(**kwargs):
        captured.append(kwargs)
        return {"launched": True}

    monkeypatch.setattr(host_ops_mcp, "resume_from_checkpoint", resume)

    async def call(client):
        return _payload(await client.call_tool("resume_from_checkpoint", {
            "source_run_id": "source", "checkpoint_id": "production_handoff-0001",
            "new_run_id": "continued", "mode": "acceptance",
            "authorization_reference": "auth-test", "model_profile": "openai-sol-medium",
            "question_visibility": "public",
            "service_tier": "default",
        }))

    result, = _session([call])
    assert result["ok"] is True
    assert captured[0]["model_profile"] == "openai-sol-medium"
    assert captured[0]["question_visibility"] == "public"
    assert captured[0]["service_tier"] == "default"


def test_start_service_tier_passes_through_mcp(monkeypatch):
    captured = []
    monkeypatch.setattr(host_ops_mcp, "start_run", lambda **kwargs: captured.append(kwargs) or {})

    async def call(client):
        return _payload(await client.call_tool("start_run", {
            "run_id": "fixture", "task": "task.yaml", "profile": "profile.yaml",
            "model_profile": "openai-sol-medium", "scope": "scope.yaml",
            "freeze_started_at": "2026-10-04T00:00:00+00:00", "service_tier": "fast",
        }))

    result, = _session([call])
    assert result["ok"] is True
    assert captured[0]["service_tier"] == "fast"


def test_host_session_ref_and_repository_root_pass_through_mcp(monkeypatch, tmp_path):
    captured = []

    def start(**kwargs):
        captured.append(kwargs)
        return {}

    monkeypatch.setattr(host_ops_mcp, "start_run", start)

    async def call(client):
        return _payload(
            await client.call_tool(
                "start_run",
                {
                    "run_id": "session-ref",
                    "task": "task.yaml",
                    "profile": "profile.yaml",
                    "model_profile": "openai-sol-medium",
                    "scope": "scope.yaml",
                    "freeze_started_at": "2026-10-04T00:00:00+00:00",
                    "host_session_ref": "host-session-7",
                    "repository_root": str(tmp_path),
                },
            )
        )

    assert _session([call])[0]["ok"] is True
    assert captured[0]["host_session_ref"] == "host-session-7"
    assert captured[0]["repository_root"] == tmp_path


def test_cold_start_exposes_s1_s2_and_delivery_extensions():
    async def list_names(client):
        listing = await client.list_tools()
        return [tool.name for tool in listing.tools]

    names = _session([list_names])[0]
    assert sorted(names) == sorted(host_ops_mcp.TOOL_NAMES)
    assert len(names) == len(host_ops_mcp.S1_TOOL_NAMES) + len(host_ops_mcp.S2_TOOL_NAMES) + len(host_ops_mcp.DELIVERY_TOOL_NAMES)
    assert set(names) == (
        set(host_ops_mcp.S1_TOOL_NAMES)
        | set(host_ops_mcp.S2_TOOL_NAMES)
        | set(host_ops_mcp.DELIVERY_TOOL_NAMES)
    )
    assert len(host_ops_mcp.S1_TOOL_NAMES) == 12
    assert len(host_ops_mcp.S2_TOOL_NAMES) == 10
    assert len(host_ops_mcp.DELIVERY_TOOL_NAMES) == 9
    assert not set(names) & FORBIDDEN_TOOL_NAMES
    # Every registered tool carries a schema, so a host cannot guess names.
    async def schemas(client):
        listing = await client.list_tools()
        return {tool.name: tool.inputSchema for tool in listing.tools}

    schemas_by_name = _session([schemas])[0]
    for name in host_ops_mcp.S2_TOOL_NAMES:
        assert schemas_by_name[name]["type"] == "object"
        assert schemas_by_name[name].get("required"), name


def test_production_and_role_surfaces_expose_no_host_only_tool_name():
    """S2-ISO-001 (A07): host-only names stay off production role surfaces.

    The production ``backend/app/mcp/tools`` registry, the role capability
    operation registry and every role agent package are scanned for the S2
    tool names; none of them may advertise one.  The independent Delivery
    package is intentionally excluded from the production-role scan.
    """

    import ast

    tools_directory = REPO_ROOT / "backend" / "app" / "mcp" / "tools"
    production_names: set[str] = set()
    for path in sorted(tools_directory.glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                targets = list(node.decorator_list)
            for decorator in targets:
                called = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(called, ast.Attribute) and called.attr == "tool":
                    production_names.add(node.name)
    assert production_names, "the production tool registry moved; update this test"
    private_tool_names = set(host_ops_mcp.S2_TOOL_NAMES) | set(host_ops_mcp.DELIVERY_TOOL_NAMES)
    assert not production_names & private_tool_names

    from modeling_team import capability_mcp

    role_operations = {
        operation
        for operations in capability_mcp.ROLE_OPERATIONS.values()
        for operation in operations
    }
    assert not role_operations & private_tool_names

    packages = REPO_ROOT / "modeling_team" / "agent-packages"
    package_blob = "\n".join(
        path.read_text("utf-8", errors="replace")
        for path in sorted(packages.rglob("*"))
        if path.is_file() and "agent-packages/delivery/" not in path.as_posix()
    )
    assert not private_tool_names & {
        name for name in private_tool_names if f"'{name}'" in package_blob
    }
    for name in private_tool_names:
        assert name not in package_blob


def test_host_server_configuration_has_no_env_block_or_credential():
    """S2-ISO-004: the config only gains tool registrations, never secrets."""

    config_path = REPO_ROOT / ".claude" / "modeling-team-host-mcp.json"
    raw = config_path.read_text("utf-8")
    assert "env" not in json.loads(raw)
    for marker in ("API_KEY", "api_key", "ADMIN_KEY", "secret"):
        assert marker not in raw
    assert "start_run" not in raw  # tool registration lives in the server module


def test_s2_tools_surface_the_design9_error_envelope():
    async def bad_run_id(client):
        return _payload(
            await client.call_tool(
                "start_run",
                {
                    "run_id": "../escape",
                    "task": "modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
                    "profile": "modeling_team/profiles/r3-0-002-modeling-team.yaml",
                    "model_profile": "glm-flash-high",
                    "scope": "modeling_team/scopes/create-scope.yaml",
                    "freeze_started_at": "2026-09-18T08:00:00+00:00",
                },
            )
        )

    async def bad_freeze(client):
        return _payload(
            await client.call_tool(
                "start_run",
                {
                    "run_id": "s2mcpfreeze",
                    "task": "modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
                    "profile": "modeling_team/profiles/r3-0-002-modeling-team.yaml",
                    "model_profile": "glm-flash-high",
                    "scope": "modeling_team/scopes/create-scope.yaml",
                    "freeze_started_at": "2026-09-18 08:00",
                },
            )
        )

    async def resume_without_credential(client):
        return _payload(
            await client.call_tool(
                "resume_from_checkpoint",
                {
                    "source_run_id": "s2mcpmissing",
                    "checkpoint_id": "materialization_progress-0001",
                    "new_run_id": "s2mcpresume",
                    "mode": "acceptance",
                    "authorization_reference": "auth-x/resume (user-approved t)",
                    "model_profile": "openai-sol-medium",
                },
            )
        )

    async def settle_without_credential(client):
        return _payload(
            await client.call_tool(
                "settle_source_run",
                {"source_run_id": "s2mcpmissing", "stop_reference": "stop-1"},
            )
        )

    bad_run_id_out, bad_freeze_out, resume_out, settle_out = _session(
        [bad_run_id, bad_freeze, resume_without_credential, settle_without_credential]
    )
    assert bad_run_id_out["ok"] is False
    assert bad_run_id_out["error"]["code"] == "run_id_invalid"
    assert bad_freeze_out["ok"] is False
    assert bad_freeze_out["error"]["code"] == "freeze_started_at_invalid"
    assert resume_out["ok"] is False
    assert resume_out["error"]["code"] == "host_credential_missing"
    assert settle_out["ok"] is False
    assert settle_out["error"]["code"] == "host_credential_missing"


def test_start_run_reaches_the_managed_launch_through_the_mcp_surface(tmp_path, monkeypatch):
    """The tool maps its parameters onto the op layer, which owns isolation."""

    import functools

    calls: list[dict] = []

    def fake_launch(argv, *, cwd, env, stdout, stderr):
        calls.append({"argv": argv, "cwd": cwd})
        run_id = argv[argv.index("--run-id") + 1]
        root = Path(cwd) / "workspaces" / "modeling-runs" / run_id
        (root / "control").mkdir(parents=True, exist_ok=True)
        (root / "state.json").write_text(
            json.dumps({"state": "PREPARING", "run_id": run_id}), encoding="utf-8"
        )

        class _Process:
            pid = 987654

            @staticmethod
            def wait(timeout=None):
                return 0

        return _Process()

    monkeypatch.setattr(
        host_ops_mcp,
        "start_run",
        functools.partial(
            host_ops.start_run,
            repository_root=tmp_path,
            launcher=fake_launch,
            run_root_wait_seconds=2.0,
        ),
    )

    async def launch(client):
        return _payload(
            await client.call_tool(
                "start_run",
                {
                    "run_id": "s2mcplaunch",
                    "task": "modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
                    "profile": "modeling_team/profiles/r3-0-002-modeling-team.yaml",
                    "model_profile": "glm-flash-high",
                    "scope": "modeling_team/scopes/create-scope.yaml",
                    "freeze_started_at": "2026-09-18T08:00:00+00:00",
                    "request_id": "mcp-start-1",
                },
            )
        )

    result = _session([launch])[0]
    assert result["ok"] is True
    data = result["data"]
    assert data["run_id"] == "s2mcplaunch"
    assert data["pid"] == 987654
    assert data["supervisor_ref"] == "control/host-supervisor.json"
    assert data["launch_record"]["request_id"] == "mcp-start-1"
    assert "--enable-outer-input-fifo" in data["launch_record"]["argv"]
    (call,) = calls
    assert call["cwd"] == str(tmp_path.resolve())


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
