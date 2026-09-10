"""R3.0-009 recoverable feedback for a malformed ``candidate_content_digests``.

auth005-start1: a plan whose ``projection.decision_bindings[].
candidate_content_digests`` carried ``[digest]`` instead of the contract's
``{item_id: digest}`` object left the capability as a raw ``AttributeError``
(``'list' object has no attribute 'values'``, audit ``error_type:
AttributeError``): the handler evaluated all three close checks eagerly, so the
later approval validator crashed before the typed issue the earlier plan check
had already produced could be returned, and the Agent got no actionable
feedback.  No intent, receipt or forward had happened, so the input was
repairable -- which is exactly what these tests pin down.

The repair is deliberately narrow: the plan/binding boundary rejects the
malformed shape with the existing typed ``unified_schema_mismatch`` naming the
field and its required shape, the three close checks short-circuit on their
first issue, and the corrected plan is accepted on the same runner and
capability instance.  Every case below uses the real capability entry -- the
prepared run's own ``RunnerCapabilityEndpoint`` over its AF_UNIX socket, wired
to the real ``RunnerAcceptanceCarrier._dispatch_capability`` chain -- and the
downstream platform write is a recorder, so no semantic run starts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modeling_team import runner as runner_module
from modeling_team.staged_decisions import (
    DECISION_BINDING_FIELDS,
    StagedSubmissionRejection,
    UNIFIED_INTENT_FIELDS,
    UNIFIED_SUBMISSION_INTENT_SCHEMA,
    projection_digest,
    staged_decision_artifact_paths,
    staged_intent_schema_issue,
)
from modeling_team.tests.test_r30008b_runner_wiring import (
    _ForwarderRecorder,
    _write_json,
)
from modeling_team.tests.test_r30009_plan_ref_capability_schema import (
    PLAN_REF,
    _audit_records,
    _call,
    _protocol_capability,
)
from modeling_team.tests.test_r30009_runner_wiring import (
    _UnifiedRunner,
    _batch_items,
    _open_platform_gate_unified,
    _unified_args,
)


def _plan_path(staged) -> Path:
    return (
        staged_decision_artifact_paths(staged.run_root, unified=True)[
            "materialization_plans_dir"
        ]
        / "plan-1-r1.json"
    )


def _rewrite_plan(staged, mutate) -> dict:
    """Rewrite the published plan, keeping its projection digest consistent."""

    plan = json.loads(_plan_path(staged).read_text(encoding="utf-8"))
    mutate(plan["projection"])
    plan["projection_digest"] = projection_digest(plan["projection"])
    _write_json(_plan_path(staged), plan)
    return plan


def _digests_as_lists(projection: dict) -> None:
    """The live auth005 mistake: a bare ``[digest]``, not ``{item_id: digest}``."""

    for binding in projection["decision_bindings"]:
        binding["candidate_content_digests"] = list(
            binding["candidate_content_digests"].values()
        )


def _json_files(directory: Path) -> list[Path]:
    return sorted(directory.iterdir()) if directory.exists() else []


# --- the live failure input is now a typed, recoverable rejection ------------


def test_malformed_digest_list_is_a_typed_rejection_then_the_repair_succeeds(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    paths = staged_decision_artifact_paths(staged.run_root, unified=True)
    forwarder.intents_dir = paths["intents_dir"]
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        arguments = _unified_args(_batch_items(), PLAN_REF)
        pristine_plan = _plan_path(staged).read_text(encoding="utf-8")
        _rewrite_plan(staged, _digests_as_lists)

        with _protocol_capability(staged) as endpoint:
            # 1) The live failure input: typed feedback naming the exact field
            #    and correction, never a raw AttributeError, and zero writes.
            response = _call(endpoint, arguments)
            assert "result" in response, response
            structured = response["result"]["structuredContent"]
            assert structured["ok"] is False, structured
            error = structured["error"]
            assert error["reason_code"] == "unified_schema_mismatch"
            assert "candidate_content_digests" in error["detail"]
            assert "JSON object" in error["detail"] and "item_id" in error["detail"]
            assert "has no attribute" not in error["detail"]
            assert forwarder.calls == []
            assert _json_files(paths["intents_dir"]) == []
            assert _json_files(paths["receipts_dir"]) == []
            rejection_record = _audit_records(staged)[-1]
            assert rejection_record["error_type"] == "StagedSubmissionRejection"
            assert rejection_record["diagnostic"]["reason_code"] == "unified_schema_mismatch"

            # 2) The Team republishes the corrected ``{item_id: digest}``
            #    object; the SAME runner and capability instance accept it, so
            #    the rejected input was recoverable without reopening a gate,
            #    restarting the run or touching any artifact outside the plan.
            _plan_path(staged).write_text(pristine_plan, encoding="utf-8")
            corrected = json.loads(_plan_path(staged).read_text(encoding="utf-8"))
            assert all(
                isinstance(binding["candidate_content_digests"], dict)
                for binding in corrected["projection"]["decision_bindings"]
            )
            accepted = _call(endpoint, arguments)
            structured = accepted["result"]["structuredContent"]
            assert structured["ok"] is True, structured

        assert len(forwarder.calls) == 1
        assert forwarder.calls[0]["batch"]["items"] == arguments["batch"]["items"]
        assert forwarder.calls[0]["intents_at_call"] == ["intent-1.json"]
        assert [path.name for path in _json_files(paths["intents_dir"])] == ["intent-1.json"]
        assert [path.name for path in _json_files(paths["receipts_dir"])] == ["receipt-1.json"]
    finally:
        staged.cleanup()


# --- the close checks short-circuit on their first issue --------------------


def test_close_checks_stop_at_the_first_issue(tmp_path, monkeypatch):
    """A later close check must never be evaluated after an earlier one already
    returned a typed issue -- that eager evaluation is what turned the plan
    issue into the live AttributeError."""

    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        evaluated: list[str] = []

        def _spy_candidate(run_root, projection):
            evaluated.append("candidate")
            return None

        def _spy_approval(approvals, projection):
            evaluated.append("approval")
            return None

        monkeypatch.setattr(runner_module, "unified_candidate_issue", _spy_candidate)
        monkeypatch.setattr(runner_module, "unified_approval_issue", _spy_approval)

        # A drifted payload fails the first close check (the plan comparison).
        item = _batch_items()[0]
        drifted = [{**item, "payload": {**item["payload"], "label": "drifted"}}]
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(
                _unified_args(drifted, PLAN_REF)
            )
        assert rejection.value.data["reason_code"] == "approval_content_mismatch"
        assert evaluated == []
        assert forwarder.calls == []

        # With no earlier issue the later checks do run, in order and once each.
        result = staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )
        assert result["ok"] is True
        assert evaluated == ["candidate", "approval"]
        assert len(forwarder.calls) == 1
    finally:
        staged.cleanup()


# --- the plan and the stored intent share one binding validator -------------


def test_the_same_binding_shape_is_rejected_at_the_intent_boundary():
    record = {field: None for field in UNIFIED_INTENT_FIELDS}
    record["schema_version"] = UNIFIED_SUBMISSION_INTENT_SCHEMA
    record["plan_ref"] = PLAN_REF
    record["projection"] = {}
    record["projection_digest"] = projection_digest({})
    binding = {field: None for field in DECISION_BINDING_FIELDS}
    binding["candidate_content_digests"] = ["sha256:" + "1" * 64]
    record["decision_bindings"] = [binding]

    issue = staged_intent_schema_issue(record)
    assert issue is not None
    assert issue.reason_code == "unified_schema_mismatch"
    assert "candidate_content_digests" in issue.detail

    binding["candidate_content_digests"] = {"item-entity": "sha256:" + "1" * 64}
    assert staged_intent_schema_issue(record) is None
