from __future__ import annotations

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


def _context(version: str = "v1") -> dict[str, object]:
    return {
        "project": {"id": "P"},
        "ontology": {"id": "O"},
        "workspace": {"state": "ready", "workspace_version": version, "issues": []},
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


def test_modeling_context_receipt_is_immutable_and_version_drift_closes_gate() -> None:
    gate = ModelingContextGate(run_id="run-1", project_id="P", ontology_id="O")
    first = gate.observe({"ok": True, "data": _context()}, call_receipt={"ordinal": 0})
    assert first.workspace_version == "v1"
    gate.bind_candidate("delivery-1", "candidate-digest")
    with pytest.raises(ModelingContextDrift):
        gate.revalidate(_context("v2"), call_receipt={"ordinal": 1})
    assert gate.state == "closed"
    with pytest.raises(ModelingReadError):
        gate.bind_candidate("delivery-2", "candidate-digest")
    refreshed = gate.observe(_context("v2"), call_receipt={"ordinal": 2})
    assert refreshed.workspace_version == "v2"
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
