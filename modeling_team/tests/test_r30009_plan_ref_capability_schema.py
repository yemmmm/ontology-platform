"""R3.0-009 capability-entry coverage for the ``plan_ref`` argument.

``protocol_staged_submit_modeling_batch`` is the only platform-write channel.
Its advertised input schema must accept the complete 009 argument set --
``protocol_id``, ``batch``, ``value_traces``, ``l3_nodes`` and ``plan_ref`` --
so a contract-correct request reaches the staged handler.  The handler, never
the schema, owns the 009 requirement: ``plan_ref`` stays optional here so 008B
runs without one keep working, while the existing Runner contract still rejects
a 009 submission that omits it.

Every case below goes through the real capability entry: the prepared run's own
``RunnerCapabilityEndpoint`` over its AF_UNIX socket, wired to the real
``RunnerAcceptanceCarrier._dispatch_capability`` chain.  The downstream platform
write is a recorder, so no semantic run starts.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from modeling_team.capability_mcp import STAGED_PROTOCOL_OPERATION
from modeling_team.staged_decisions import staged_decision_artifact_paths
from modeling_team.tests.test_r30008b_runner_wiring import (
    _capability_args,
    _ForwarderRecorder,
    _materialization_valid,
    _open_platform_gate,
    _socket_request,
    _StagedRunner,
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


# --- 009: the complete argument set must reach the staged handler -------------


def test_009_capability_entry_accepts_plan_ref_and_binds_it_to_the_intent(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    forwarder.intents_dir = staged_decision_artifact_paths(
        staged.run_root, unified=True
    )["intents_dir"]
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        arguments = _unified_args(_batch_items(), PLAN_REF)
        with _protocol_capability(staged) as endpoint:
            response = _call(endpoint, arguments)

        # The request passed the entry: no opaque -32001 and no schema audit record.
        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is True, structured
        assert [record for record in _audit_records(staged) if record.get("ok")] != []

        # It reached the staged handler: the host-side forward ran exactly once
        # with the verbatim platform envelope, which never carries plan_ref.
        assert len(forwarder.calls) == 1
        forwarded = forwarder.calls[0]["batch"]
        assert forwarded["items"] == arguments["batch"]["items"]
        assert "plan_ref" not in forwarded
        assert "value_traces" not in forwarded and "l3_nodes" not in forwarded

        # The full plan_ref is preserved in the durable bindings, unmodified.
        intent = json.loads(
            (
                staged_decision_artifact_paths(staged.run_root, unified=True)[
                    "intents_dir"
                ]
                / "intent-1.json"
            ).read_text(encoding="utf-8")
        )
        assert intent["plan_ref"] == PLAN_REF
        assert intent["schema_version"] == "r3-0-009-submission-intent/v1"
        receipt = json.loads(
            (
                staged_decision_artifact_paths(staged.run_root, unified=True)[
                    "receipts_dir"
                ]
                / "receipt-1.json"
            ).read_text(encoding="utf-8")
        )
        assert receipt["plan_ref"] == PLAN_REF
        assert receipt["submitted_via"] == STAGED_PROTOCOL_OPERATION
    finally:
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


# --- 009 without plan_ref is still the Runner contract's rejection ------------


def test_009_capability_entry_without_plan_ref_still_fails_the_runner_contract(
    tmp_path,
):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        arguments = _unified_args(_batch_items(), None)
        assert "plan_ref" not in arguments
        with _protocol_capability(staged) as endpoint:
            response = _call(endpoint, arguments)

        # The schema admitted the call (no opaque rejection); the typed refusal
        # is the existing 009 contract check, with nothing written or forwarded.
        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is False
        assert structured["error"]["reason_code"] == "missing_candidate_reference"
        assert forwarder.calls == []
        assert _intent_files(staged, unified=True) == []
    finally:
        staged.cleanup()


# --- 008B compatibility -------------------------------------------------------


def test_008b_capability_entry_still_accepts_a_submission_without_plan_ref(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    forwarder.intents_dir = staged_decision_artifact_paths(staged.run_root)[
        "intents_dir"
    ]
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        arguments = _capability_args()
        assert "plan_ref" not in arguments
        with _protocol_capability(staged) as endpoint:
            response = _call(endpoint, arguments)

        assert "error" not in response, response
        assert response["result"]["structuredContent"]["ok"] is True
        assert len(forwarder.calls) == 1
        intent = json.loads(
            (
                staged_decision_artifact_paths(staged.run_root)["intents_dir"]
                / "intent-1.json"
            ).read_text(encoding="utf-8")
        )
        # The 008B intent stays exactly what it was: no 009 sidecar fields.
        assert "plan_ref" not in intent
        assert intent["schema_version"] == "r3-0-008b-submission-intent/v1"
    finally:
        staged.cleanup()
