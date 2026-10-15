from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from subprocess import PIPE
from pathlib import Path

import pytest

from modeling_team.modeling_readonly import (
    MODELING_READ_TOOLS,
    ModelingContextDrift,
    ModelingContextGate,
    ModelingReadError,
    ModelingReadKeyLifecycle,
    ModelingReadProxy,
)
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker


def _context(version: str = 1) -> dict[str, object]:
    return {
        "project": {"id": "P"},
        "ontology": {"id": "O"},
        "workspace": {"state": "ready", "model_revision": version, "issues": []},
        "resource_counts": {"classes": 1, "entities": 2, "facts": 3, "rules": 0},
        "derived_state": {"stale_count": 0, "warning": None},
        "lease": {"active": False},
        "recovering": {"active": False},
    }


def test_modeling_proxy_exact_tools_scope_and_zero_backend_request() -> None:
    calls: list[tuple[str, dict[str, object], str]] = []
    gate = ModelingContextGate(run_id="run-1", project_id="P", ontology_id="O")

    def forward(tool: str, arguments: dict[str, object], key: str) -> dict[str, object]:
        calls.append((tool, arguments, key))
        return {"ok": True, "data": _context()} if tool == "get_modeling_context" else {"tool": tool}

    proxy = ModelingReadProxy(
        socket_path=Path("/tmp/r23003-modeling-read-test.sock"),
        token="proxy-token",
        read_key="read-key",
        project_id="P",
        ontology_id="O",
        forward=forward,
        on_context=lambda response, receipt: gate.observe(response, call_receipt=receipt),
    )
    assert proxy.handle({"token": "proxy-token", "operation": "tools/list"})["tools"] == list(
        MODELING_READ_TOOLS
    )
    assert proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_modeling_context",
            "arguments": {"ontology_id": "O"},
        }
    )["ok"] is True
    assert proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_ontology_read_model",
            "arguments": {"ontology_id": "O", "model_name": "classes"},
        }
    )["ok"] is True
    denied = proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_project_build_context",
            "arguments": {"project_id": "P"},
        }
    )
    assert denied["code"] == "read-tool-denied"
    wrong_scope = proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {
                "project_id": "P",
                "scope_mode": "project",
                "query": "x",
                "ontology_ids": ["O"],
            },
        }
    )
    assert wrong_scope["ok"] is False
    assert len(calls) == 2
    assert calls[1][1]["allow_stale_derived"] is False
    assert gate.state == "context_observed"


@pytest.mark.parametrize("ontology_ids", [["O"], ["O", "O2"]])
def test_staged_modeling_bridge_projects_each_tool_to_real_proxy_and_advertises_schema(
    tmp_path: Path, ontology_ids: list[str],
) -> None:
    socket_path = tmp_path / "modeling-read-proxy.sock"
    token_path = tmp_path / "modeling-read-proxy.token"
    staged_bridge = tmp_path / "read_proxy_mcp.py"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "read_proxy_mcp.py", staged_bridge)
    token_path.write_text("proxy-token\n", encoding="utf-8")
    forwarded: list[tuple[str, dict[str, object], str]] = []

    def forward(tool: str, arguments: dict[str, object], key: str) -> dict[str, object]:
        forwarded.append((tool, dict(arguments), key))
        if tool == "get_modeling_context":
            return {"ok": True, "data": _context()}
        return {"ok": True, "data": {"tool": tool, "arguments": dict(arguments)}}

    proxy = ModelingReadProxy(
        socket_path=socket_path,
        token="proxy-token",
        read_key="read-key",
        project_id="P",
        ontology_id="O",
        ontology_ids=ontology_ids,
        forward=forward,
    )
    proxy.start()
    env = {
        **os.environ,
        "PLATFORM_PROXY_MODE": "modeling",
        "PLATFORM_PROXY_PROJECT_ID": "P",
        "PLATFORM_PROXY_ONTOLOGY_ID": "O",
        "PLATFORM_PROXY_ONTOLOGY_IDS": json.dumps(ontology_ids),
    }
    process = subprocess.Popen(
        [sys.executable, str(staged_bridge), "--stdio", "--socket", str(socket_path), "--token-file", str(token_path)],
        stdin=PIPE,
        stdout=PIPE,
        text=True,
        env=env,
    )

    def request(request_id: int, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
            + "\n"
        )
        process.stdin.flush()
        line = process.stdout.readline()
        assert line
        return json.loads(line)

    try:
        listed = request(1, "tools/list")["result"]["tools"]
        assert {item["name"] for item in listed} == set(MODELING_READ_TOOLS)
        schemas = {item["name"]: item["inputSchema"] for item in listed}
        assert schemas["get_modeling_context"]["required"] == ["ontology_id"]
        assert schemas["get_ontology_read_model"]["required"] == ["ontology_id", "model_name"]
        assert schemas["query_semantic_context"]["required"] == ["project_id", "scope_mode"]
        assert schemas["query_semantic_context"]["properties"]["scope_mode"]["const"] == "ontologies"
        assert schemas["query_semantic_context"]["properties"]["expansion_strategy"]["default"] == "adaptive"
        assert schemas["query_semantic_context"]["properties"]["context_order"]["default"] == "relevance"

        context_response = request(
            2,
            "tools/call",
            {"name": "get_modeling_context", "arguments": {}},
        )
        assert "error" not in context_response
        model_response = request(
            3,
            "tools/call",
            {"name": "get_ontology_read_model", "arguments": {"model_name": "classes"}},
        )
        assert "error" not in model_response
        query_response = request(
            4,
            "tools/call",
            {
                "name": "query_semantic_context",
                "arguments": {
                    "query": "quality",
                    "project_id": "P",
                    "scope_mode": "ontologies",
                    "ontology_ids": ["O"],
                },
            },
        )
        assert "error" not in query_response
        assert [item[0] for item in forwarded] == list(MODELING_READ_TOOLS)
        assert forwarded[0][1] == {"ontology_id": "O"}
        assert forwarded[1][1] == {
            "model_name": "classes",
            "ontology_id": "O",
            "allow_stale_derived": False,
        }
        assert forwarded[2][1] == {
            "query": "quality",
            "project_id": "P",
            "scope_mode": "ontologies",
            "ontology_ids": ["O"],
        }

        denied = (
            {"name": "get_modeling_context", "arguments": {"ontology_id": "foreign-ontology"}},
            {"name": "get_ontology_read_model", "arguments": {"model_name": "classes", "project_id": "foreign-project"}},
            {"name": "query_semantic_context", "arguments": {"query": "quality", "ontology_ids": ["foreign-ontology"]}},
        )
        for request_id, arguments in enumerate(denied, start=5):
            response = request(request_id, "tools/call", arguments)
            assert response["error"]["code"] == -32000
        malformed = (
            {"name": "get_modeling_context", "arguments": {"ontology_id": None}},
            {"name": "get_ontology_read_model", "arguments": {}},
            {"name": "query_semantic_context", "arguments": {"query": ""}},
        )
        for request_id, arguments in enumerate(malformed, start=8):
            response = request(request_id, "tools/call", arguments)
            assert response["error"]["code"] == -32000
        assert len(forwarded) == 3
        if len(ontology_ids) > 1:
            followup = request(20, "tools/call", {
                "name": "query_semantic_context", "arguments": {
                    "query": "https://example.org/core", "ontology_ids": ["O2"],
                    "expansion_strategy": "adaptive", "context_order": "relevance",
                    "depth": None, "context_detail": "full",
                },
            })
            assert "error" not in followup, followup
            assert forwarded[-1][1]["ontology_ids"] == ["O2"]
            assert forwarded[-1][1]["query"] == "https://example.org/core"
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=2)
        proxy.destroy()


def test_modeling_context_receipt_is_immutable_and_version_drift_closes_gate() -> None:
    gate = ModelingContextGate(run_id="run-1", project_id="P", ontology_id="O")
    first = gate.observe({"ok": True, "data": _context()}, call_receipt={"ordinal": 0})
    assert first.model_revision == 1
    gate.bind_candidate("delivery-1", "candidate-digest")
    with pytest.raises(ModelingContextDrift):
        gate.revalidate(_context(2), call_receipt={"ordinal": 1})
    assert gate.state == "closed"
    with pytest.raises(ModelingReadError):
        gate.bind_candidate("delivery-2", "candidate-digest")
    refreshed_context = _context(2)
    refreshed_context["lease"] = {"active": True, "lease_id": "run-owned-lease"}
    refreshed_context["derived_state"] = {
        "stale_count": 1,
        "warning": "derived_state_stale",
    }
    refreshed = gate.observe(refreshed_context, call_receipt={"ordinal": 2})
    assert refreshed.model_revision == 2
    assert gate.state == "context_observed"


def test_modeling_context_gate_accepts_mcp_envelope_and_rejects_error_or_malformed_data() -> None:
    gate = ModelingContextGate(run_id="run-1", project_id="P", ontology_id="O")
    receipt = gate.observe({"ok": True, "data": _context()}, call_receipt={"ordinal": 0})
    assert receipt.project_id == "P"
    assert receipt.ontology_id == "O"
    for response in (
        {"ok": False, "error": {"code": "backend-error"}},
        {"ok": True, "data": None},
        {"ok": True, "data": {"project": {"id": "P"}}},
    ):
        with pytest.raises(ModelingReadError):
            gate.observe(response, call_receipt={"ordinal": 1})


class _FakeForwarder:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def forward(self, tool: str, arguments: dict[str, object], key: str) -> dict[str, object]:
        return {"tool": tool, "key": key, "arguments": arguments}


class _FakeScope:
    key_user_id = "operator-user"
    admin_key = "admin"
    project_id = "P"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object, str]] = []

    def request(self, method: str, path: str, body: object, key: str):
        self.calls.append((method, path, body, key))
        if method == "POST" and path == "/api/api-keys":
            return 201, {"id": "key-1", "plaintext_key": "plaintext"}
        if method == "POST" and path.endswith(":revoke"):
            return 200, {"revoked_at": "2026-08-11T00:00:00Z"}
        if method == "GET" and path == "/api/api-keys/key-1":
            return 200, {"id": "key-1", "revoked_at": "2026-08-11T00:00:00Z"}
        if method == "GET" and path == "/api/projects/P" and key == "plaintext":
            return 401, {"detail": "revoked"}
        raise AssertionError((method, path, body, key))


def test_modeling_key_lifecycle_revokes_reads_back_and_drops_plaintext(tmp_path: Path) -> None:
    forwarder = _FakeForwarder()
    scope = _FakeScope()
    lifecycle = ModelingReadKeyLifecycle(
        scope,
        repository_root=tmp_path,
        forwarder_factory=lambda **_: forwarder,
    )
    record = lifecycle.create(project_id="P", ontology_id="O", run_id="run-1")
    assert lifecycle.plaintext_for(record.key_id) == "plaintext"
    lifecycle.forwarder_for(record.key_id)("get_modeling_context", {"ontology_id": "O"}, "plaintext")
    assert forwarder.started
    revoked = lifecycle.revoke(record.key_id)
    assert revoked.status == "revoked"
    assert revoked.revoked_at
    assert forwarder.stopped
    with pytest.raises(ModelingReadError):
        lifecycle.plaintext_for(record.key_id)
    assert all("plaintext" not in str(value) for value in lifecycle.evidence(record.key_id).values())


def test_transport_candidate_is_blocked_until_context_receipt(tmp_path: Path) -> None:
    gate = ModelingContextGate(run_id="run-1", project_id="P", ontology_id="O")
    candidate = (
        '{"candidate_kind":"semantic","candidate_revision":1,"scope":{},'
        '"constraints":{},"items":[]}'
    )

    def validate(sender: str, recipient: str, text: str, expects_reply: bool, reply_to: str | None) -> None:
        assert (sender, recipient, expects_reply, reply_to) == ("modeling", "protocol", True, None)
        if gate.state != "context_observed":
            raise RoutingError("context receipt required")

    broker = TeamTransportBroker(
        tmp_path / "broker",
        {("modeling", "protocol")},
        pre_send_validator=validate,
    )
    with pytest.raises(RoutingError):
        broker.send("modeling", "protocol", candidate, expects_reply=True)
    gate.observe(_context(), call_receipt={"ordinal": 0})
    delivery = broker.send("modeling", "protocol", candidate, expects_reply=True)
    assert delivery.delivery_id == "delivery-1"


def test_direct_modeling_reads_authorized_scope_and_followup_questions(tmp_path: Path) -> None:
    calls = []
    responses = [
        {"ok": True, "data": {"model_revision": 4, "warnings": ["lexical_fallback"]}},
        {"ok": True, "data": {"model_revision": 4, "truncated": True}},
        {"ok": False, "error": {"code": "cursor_stale"}},
    ]
    proxy = ModelingReadProxy(
        socket_path=tmp_path / "read.sock", token="token", read_key="key",
        project_id="P", ontology_id="O", ontology_ids=["O", "O2"],
        forward=lambda tool, args, key: (calls.append((tool, args)) or responses.pop(0)),
    )

    def query(**overrides):
        arguments = {
            "project_id": "P", "scope_mode": "ontologies", "ontology_ids": ["O", "O2"],
            "query": "How are work orders related to faults?", "depth": None,
            "expansion_strategy": "adaptive", "context_order": "relevance",
        }
        arguments.update(overrides)
        return proxy.handle({"token": "token", "operation": "tools/call",
                             "tool": "query_semantic_context", "arguments": arguments})

    first = query()
    assert first["result"]["data"]["warnings"] == ["lexical_fallback"]
    second = query(query="https://example.org/work-order", ontology_ids=["O2"], context_detail="full")
    assert second["result"]["data"]["truncated"] is True
    stale = query(query="https://example.org/work-order", match_cursor="old-revision")
    assert stale["result"]["error"]["code"] == "cursor_stale"
    for overrides in ({"ontology_ids": ["foreign"]}, {"project_id": "foreign"},
                      {"scope_mode": "project"}, {"ontology_ids": []}):
        assert query(**overrides)["ok"] is False
    assert len(calls) == 3


def test_modeling_bridge_selects_authorized_ontology_subset() -> None:
    from modeling_team.read_proxy_mcp import _project_modeling_arguments

    scope = {"PLATFORM_PROXY_PROJECT_ID": "P", "PLATFORM_PROXY_ONTOLOGY_ID": "O",
             "PLATFORM_PROXY_ONTOLOGY_IDS": '["O", "O2"]'}
    query = _project_modeling_arguments(
        "query_semantic_context", {"query": "x", "ontology_ids": ["O2"]}, scope,
    )
    assert query["ontology_ids"] == ["O2"]
    assert query["project_id"] == "P"
    assert _project_modeling_arguments("get_modeling_context", {"ontology_id": "O2"}, scope) == {
        "ontology_id": "O2",
    }
    # The live proxy, not a stale child environment, checks topology additions.
    assert _project_modeling_arguments(
        "query_semantic_context", {"query": "x", "ontology_ids": ["new-authorized"]}, scope,
    )["ontology_ids"] == ["new-authorized"]
