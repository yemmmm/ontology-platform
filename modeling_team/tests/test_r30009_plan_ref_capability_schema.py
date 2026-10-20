"""Capability-entry contracts for the current R4.3-024/025 write boundary.

The old ``plan_ref`` argument belonged to the retired per-batch dry-run and
translation-proof handshake.  Current Modeling submits an explicit
``r4-3-025-model-changes/v1`` request through ``modeling_submit_model_changes``
and the retained Protocol recovery surface accepts ``apply_atomic`` only.

The legacy staged helper remains covered here only for its closed external
schema boundary; historical positive receipts are exercised by the recovery
fixtures.  Every case uses the prepared run's real capability endpoint over
its AF_UNIX socket.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from modeling_team.capability_mcp import DIRECT_MODELING_OPERATIONS, STAGED_PROTOCOL_OPERATION
from modeling_team.staged_decisions import staged_decision_artifact_paths
from modeling_team.tests.test_r30008b_runner_wiring import (
    _ForwarderRecorder,
    _socket_request,
)
from modeling_team.tests.test_r30009_runner_wiring import (
    _batch_items,
    _open_platform_gate_unified,
    _unified_args,
    _UnifiedRunner,
)

PLAN_REF = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"


@contextmanager
def _protocol_capability(staged):
    """The run's own protocol capability endpoint, started on its socket."""

    endpoint = staged.runner.acceptance.capability_endpoint("protocol")
    endpoint.start()
    try:
        yield endpoint
    finally:
        endpoint.stop()


def _call(endpoint, arguments) -> dict:
    return _socket_request(
        endpoint.socket_path,
        endpoint.token,
        "tools/call",
        name=STAGED_PROTOCOL_OPERATION,
        arguments=arguments,
    )


def _audit_records(staged) -> list[dict]:
    audit = staged.run_root / "evidence" / "capability-calls.jsonl"
    if not audit.exists():
        return []
    return [
        json.loads(line)
        for line in audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _intent_files(staged, *, unified: bool) -> list[Path]:
    intents_dir = staged_decision_artifact_paths(staged.run_root, unified=unified)[
        "intents_dir"
    ]
    return sorted(intents_dir.iterdir()) if intents_dir.exists() else []


def test_025_modeling_capability_advertises_direct_change_contract(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    endpoint = staged.runner.acceptance.capability_endpoint("modeling")
    endpoint.start()
    try:
        response = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        tools = {entry["name"]: entry for entry in response["result"]["tools"]}
        assert set(tools) == set(DIRECT_MODELING_OPERATIONS)

        submit = tools["modeling_submit_model_changes"]
        schema = submit["inputSchema"]
        request = schema["properties"]["request"]
        assert schema["required"] == ["modeling_id"]
        assert schema["properties"]["request_ref"]["required"] == ["material_id"]
        assert request["required"] == ["schema_version", "candidate_ref", "changes"]
        assert request["properties"]["schema_version"]["enum"] == [
            "r4-3-025-model-changes/v1"
        ]
        assert request["properties"]["candidate_ref"]["type"] == ["string", "null"]
        assert "mode" not in request["properties"]
        assert "plan_ref" not in request["properties"]
        assert "translation_approval" not in request["properties"]
    finally:
        endpoint.stop()
        staged.cleanup()


# --- the external boundary stays closed --------------------------------------


def test_009_capability_entry_still_rejects_unknown_or_mistyped_fields(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        with _protocol_capability(staged) as endpoint:
            extra = _unified_args(_batch_items(), PLAN_REF)
            extra["plan_ref_copy"] = PLAN_REF
            unknown = _call(endpoint, extra)
            mistyped = _unified_args(_batch_items(), PLAN_REF)
            mistyped["plan_ref"] = 7
            wrong_type = _call(endpoint, mistyped)

        # Both stay opaque at the entry, before any dispatch or write.
        assert unknown["error"]["code"] == -32001
        assert wrong_type["error"]["code"] == -32001
        assert forwarder.calls == []
        assert _intent_files(staged, unified=True) == []
        assert [record["error_type"] for record in _audit_records(staged)] == [
            "schema_or_operation_rejected",
            "schema_or_operation_rejected",
        ]
    finally:
        staged.cleanup()


def test_025_direct_submit_rejects_retired_dry_run_shape_before_forwarding(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        request = {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                {
                    "change_id": "change-1",
                    "action": "create",
                    "resource_kind": "entity",
                }
            ],
            "mode": "dry_run",
        }
        endpoint = staged.runner.acceptance.capability_endpoint("modeling")
        endpoint.start()
        try:
            response = _socket_request(
                endpoint.socket_path,
                endpoint.token,
                "tools/call",
                name="modeling_submit_model_changes",
                arguments={"modeling_id": "modeling", "request": request},
            )
        finally:
            endpoint.stop()

        assert response["error"]["code"] == -32001
        assert forwarder.calls == []
        assert _audit_records(staged)[-1]["error_type"] == "schema_or_operation_rejected"
    finally:
        staged.cleanup()


def test_025_protocol_plan_execution_schema_allows_apply_only(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    endpoint = staged.runner.acceptance.capability_endpoint("protocol")
    endpoint.start()
    try:
        response = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        tools = {entry["name"]: entry for entry in response["result"]["tools"]}
        execute = tools["protocol_execute_approved_plans"]
        assert execute["inputSchema"]["properties"]["mode"]["enum"] == ["apply_atomic"]
        assert "dry_run" not in execute["description"]
        assert "translation approval" not in execute["description"].lower()
    finally:
        endpoint.stop()
        staged.cleanup()
