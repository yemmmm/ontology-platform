from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import app.mcp.runtime as mcp_runtime


def _write_gate(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_formal_candidate_gate_closed_blocks_resources_and_tool(monkeypatch, tmp_path: Path) -> None:
    gate = tmp_path / "state.json"
    _write_gate(
        gate,
        {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "closed",
            "reason_code": "protocol_conflict",
        },
    )
    effects: list[str] = []

    def unexpected_resources():
        raise AssertionError("closed gate must not acquire backend resources")

    monkeypatch.setattr(mcp_runtime, "get_resources", unexpected_resources)
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(gate))

    def call_tool():
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("called") or {"ok": True}
        )

    result = call_tool()
    assert result == {
        "ok": False,
        "error": "candidate receipt required before platform call",
        "error_code": "candidate_receipt_required",
    }
    assert effects == []


def test_formal_candidate_gate_open_allows_tool_and_conflict_closes_it(
    monkeypatch, tmp_path: Path
) -> None:
    gate = tmp_path / "state.json"
    _write_gate(
        gate,
        {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "open",
            "candidate_digest": "b" * 64,
        },
    )
    effects: list[str] = []

    @contextmanager
    def session_factory():
        yield object()

    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (session_factory, None, None))
    monkeypatch.setattr(mcp_runtime, "_authorize_tool", lambda *_args: None)
    monkeypatch.setattr(mcp_runtime, "scan_domain_payload", lambda *_args: None)
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(gate))

    def call_tool():
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("called") or {"ok": True}
        )

    assert call_tool() == {"ok": True, "data": {"ok": True}}
    assert effects == ["called"]

    _write_gate(
        gate,
        {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "closed",
            "reason_code": "protocol_conflict",
        },
    )
    assert call_tool()["error_code"] == "candidate_receipt_required"
    assert effects == ["called"]


def test_legacy_without_candidate_gate_keeps_original_tool_path(monkeypatch) -> None:
    effects: list[str] = []

    @contextmanager
    def session_factory():
        yield object()

    monkeypatch.delenv("FORMAL_CANDIDATE_GATE_PATH", raising=False)
    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (session_factory, None, None))
    monkeypatch.setattr(mcp_runtime, "_authorize_tool", lambda *_args: None)
    monkeypatch.setattr(mcp_runtime, "scan_domain_payload", lambda *_args: None)

    def call_tool():
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("called") or {"ok": True}
        )

    assert call_tool() == {"ok": True, "data": {"ok": True}}
    assert effects == ["called"]


def test_formal_candidate_gate_rejects_malformed_or_oversized_state(
    monkeypatch, tmp_path: Path
) -> None:
    effects: list[str] = []

    def unexpected_resources():
        raise AssertionError("invalid gate must not acquire backend resources")

    monkeypatch.setattr(mcp_runtime, "get_resources", unexpected_resources)
    gate = tmp_path / "state.json"
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(gate))

    gate.write_text("not-json", encoding="utf-8")

    def call_tool():
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("called") or {"ok": True}
        )

    assert call_tool()["error_code"] == "candidate_receipt_required"
    gate.write_bytes(b"{" + b'\"schema_version\":\"r2-3-005-candidate-platform-gate/v1\",' + b'\"state\":\"open\"' + b"," + b'\"x\":\"a\"' * 20000 + b"}")
    assert call_tool()["error_code"] == "candidate_receipt_required"
    gate.unlink()
    target = tmp_path / "target-state.json"
    _write_gate(
        target,
        {"schema_version": "r2-3-005-candidate-platform-gate/v1", "state": "open"},
    )
    gate.symlink_to(target)
    assert call_tool()["error_code"] == "candidate_receipt_required"
    assert effects == []
