from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.mcp.runtime as mcp_runtime


def _write_gate(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _r23003_gate(candidate_digest: str = "candidate-v1") -> dict[str, Any]:
    return {
        "schema_version": "r2-3-005-candidate-platform-gate/v1",
        "state": "open",
        "run_id": "run-r23003",
        "candidate_digest": candidate_digest,
        "modeling_context": {
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "workspace_version": "workspace-v1",
            "context_receipt_digest": "context-receipt",
            "response_digest": "modeling-response",
            "call_receipt_digest": "modeling-call",
        },
        "protocol_revalidation": {"state": "required"},
    }


def _context(version: str = "workspace-v1") -> dict[str, Any]:
    return {
        "project": {"id": "project-1"},
        "ontology": {"id": "ontology-1"},
        "workspace": {"state": "ready", "workspace_version": version, "issues": []},
        "resource_counts": {"classes": 1},
        "derived_state": {"stale_count": 0, "warning": None},
        "lease": {"active": False},
        "recovering": {"active": False},
    }


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


def test_r23003_protocol_stateful_tools_require_exact_o_revalidation_and_detect_drift(
    monkeypatch, tmp_path: Path
) -> None:
    gate = tmp_path / "state.json"
    _write_gate(gate, _r23003_gate())
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(gate))
    effects: list[str] = []

    @contextmanager
    def session_factory():
        yield object()

    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (session_factory, None, None))
    monkeypatch.setattr(mcp_runtime, "_authorize_tool", lambda *_args: None)
    monkeypatch.setattr(mcp_runtime, "scan_domain_payload", lambda *_args: None)
    live_context = {"value": _context()}
    monkeypatch.setattr(
        mcp_runtime,
        "_read_live_modeling_context",
        lambda _session, _ontology_id: live_context["value"],
    )

    def submit_modeling_batch() -> dict[str, Any]:
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("stateful") or {"submitted": True}
        )

    def get_modeling_context(value: dict[str, Any]) -> dict[str, Any]:
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: value
        )

    def get_ontology_read_model() -> dict[str, Any]:
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("read") or {"read": True}
        )

    blocked = submit_modeling_batch()
    assert blocked["error_code"] == "modeling_context_revalidation_required"
    assert effects == []
    assert get_ontology_read_model() == {"ok": True, "data": {"read": True}}
    assert effects == ["read"]

    wrong = get_modeling_context(_context("workspace-v2"))
    assert wrong["error_code"] == "modeling_context_revalidation_failed"
    assert effects == ["read"]
    assert submit_modeling_batch()["error_code"] == "modeling_context_revalidation_required"
    assert effects == ["read"]

    assert get_modeling_context(_context()) == {"ok": True, "data": _context()}
    assert submit_modeling_batch() == {"ok": True, "data": {"submitted": True}}
    assert effects == ["read", "stateful"]

    live_context["value"] = _context("workspace-v2")
    drifted = submit_modeling_batch()
    assert drifted["error_code"] == "modeling_context_revalidation_failed"
    assert drifted["data"]["mutation_state"] == "zero-mutation"
    assert effects == ["read", "stateful"]

    _write_gate(gate, _r23003_gate("candidate-v2"))
    assert submit_modeling_batch()["error_code"] == "modeling_context_revalidation_required"
    assert effects == ["read", "stateful"]


def test_r23003_revalidation_normalizes_recent_batch_datetimes_and_keeps_005_gate_isolated(
    monkeypatch, tmp_path: Path
) -> None:
    gate = tmp_path / "state.json"
    _write_gate(gate, _r23003_gate())
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(gate))
    effects: list[str] = []

    @contextmanager
    def session_factory():
        yield object()

    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (session_factory, None, None))
    monkeypatch.setattr(mcp_runtime, "_authorize_tool", lambda *_args: None)
    monkeypatch.setattr(mcp_runtime, "scan_domain_payload", lambda *_args: None)
    recent_batch_time = datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc)
    observed = _context()
    observed["recent_batches"] = [
        {"batch_id": "batch-1", "created_at": recent_batch_time, "completed_at": recent_batch_time}
    ]
    live_context = {"value": observed}
    monkeypatch.setattr(
        mcp_runtime,
        "_read_live_modeling_context",
        lambda _session, _ontology_id: live_context["value"],
    )

    def get_modeling_context() -> dict[str, Any]:
        return mcp_runtime._run_tool(lambda _session, _driver, _embedding: observed)

    def submit_modeling_batch() -> dict[str, Any]:
        return mcp_runtime._run_tool(
            lambda _session, _driver, _embedding: effects.append("stateful") or {"submitted": True}
        )

    revalidated = get_modeling_context()
    assert revalidated["ok"] is True
    assert revalidated["data"]["recent_batches"][0]["created_at"] == str(recent_batch_time)
    assert (str(gate), "candidate-v1") in mcp_runtime._protocol_revalidations
    assert submit_modeling_batch() == {"ok": True, "data": {"submitted": True}}
    assert effects == ["stateful"]

    live_context["value"] = _context("workspace-v2")
    drifted = submit_modeling_batch()
    assert drifted["error_code"] == "modeling_context_revalidation_failed"
    assert drifted["data"]["mutation_state"] == "zero-mutation"
    assert effects == ["stateful"]

    legacy_gate = tmp_path / "legacy-state.json"
    _write_gate(
        legacy_gate,
        {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "open",
            "candidate_digest": "legacy-candidate",
        },
    )
    monkeypatch.setenv("FORMAL_CANDIDATE_GATE_PATH", str(legacy_gate))
    assert submit_modeling_batch() == {"ok": True, "data": {"submitted": True}}
    assert effects == ["stateful", "stateful"]
