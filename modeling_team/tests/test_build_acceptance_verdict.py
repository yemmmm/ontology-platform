"""R2.3-005 step-4: Host-built acceptance verdict constructor.

The Acceptance agent no longer hand-assembles the 28-field verdict JSON.  It
calls ``build_acceptance_verdict`` with only its business judgment plus
identifiers; the Host fills every mechanical field from the bound ticket, the
round's examiner terminal reports, and the tracked infrastructure failures,
then computes the canonical ``verdict_digest``.  These tests reconstruct the
start57 evidence shape (a source terminal report, a platform examiner that
crashed twice with cleaned infrastructure failures) and assert the Host-built
envelope passes ``validate_verdict`` unchanged and that its digest matches the
canonical preimage.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    canonical_digest,
    model_state_digest,
    modeling_receipt_digest,
    report_digest,
    ticket_digest,
    validate_verdict,
    verdict_digest,
)
from modeling_team.capability_mcp import _matches_schema


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ticket(round_suffix: str = "1") -> dict:
    state = {
        "project_id": "2480506c-a9f8-4c2b-804d-aec6e993a4f8",
        "ontology_id": "3c52a819-feb6-468d-a6dc-2e9dbf5f9b24",
        "workspace_version": "workspace-1",
        "source_signature": "source-1",
        "build_session_id": "session-r23005",
        "graph_set_id": "731daa4c-eff0-5702-bcee-32b64275736d",
    }
    state["state_digest"] = model_state_digest(state)
    sources = [{"path": "source.md", "sha256": "b" * 64}]
    source_bundle_digest = _sha(sources)
    artifact = {"path": "acceptance/standard.json", "digest": "d" * 64}
    receipts = []
    for stage, status in (
        ("dry-run", "validated"),
        ("apply", "applied"),
        ("readback", "complete"),
        ("validation", "succeeded"),
        ("reasoning", "succeeded"),
    ):
        ref = {
            "type": "platform_read",
            "ref_id": f"ref-{stage.replace('-', '')}",
            "ticket_digest": None,
            "model_state_digest": state["state_digest"],
            "tool": "get_modeling_context",
            "request_digest": "e" * 64,
            "response_digest": "f" * 64,
            "artifact_path": f"evidence/{stage}.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }
        receipt = {
            "stage": stage,
            "status": status,
            "receipt_digest": None,
            "run_id": "producer-r23005",
            "project_id": state["project_id"],
            "ontology_id": state["ontology_id"],
            "slice_revision": "slice-1",
            "model_state_digest": state["state_digest"],
            "evidence_ref": ref,
        }
        receipt["receipt_digest"] = modeling_receipt_digest(receipt)
        receipts.append(receipt)
    ticket = {
        "schema_version": "r2-3-005-slice-acceptance-ticket/v1",
        "ticket_id": f"ticket-r23005-{round_suffix}",
        "acceptance_round_id": f"round-r23005-{round_suffix}",
        "task_id": "task-r23005",
        "producer_run_id": "producer-r23005",
        "slice_id": "slice-r23005",
        "slice_revision": "slice-1",
        "question_id": "cq1",
        "question": "Which output is consumed?",
        "approved_sources": sources,
        "source_bundle_digest": source_bundle_digest,
        "platform_read_scope": {
            "project_id": state["project_id"],
            "ontology_id": state["ontology_id"],
            "graph_set_id": state["graph_set_id"],
        },
        "model_state": state,
        "model_state_digest": state["state_digest"],
        "competency_questions": [{"id": "cq1", "question": "Which output is consumed?"}],
        "allowed_read_tools": sorted(
            {
                "get_modeling_context",
                "list_semantic_validation_runs",
                "get_semantic_validation_run",
                "list_semantic_reasoning_runs",
                "get_semantic_reasoning_run",
            }
        ),
        "modeling_receipts": receipts,
        "timeout_seconds": 60,
        "quality_standard_ref": "docs/requirements/requirements-v2.3.md#R2.3-005",
        "quality_standard_digest": "c" * 64,
        "quality_standard_artifact": artifact,
        "unknown_policy": "preserve-explicit-unknown",
        "ticket_revision": 1,
        "ticket_digest": None,
    }
    digest = ticket_digest(ticket)
    ticket["ticket_digest"] = digest
    for receipt in ticket["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = digest
    return ticket


class _FakeResource:
    """Minimal child resource that satisfies the recycle destroy/stop contract."""

    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.stopped = 0
        self.destroyed = 0

    def stop(self) -> None:
        self.stopped += 1

    def destroy(self) -> None:
        self.destroyed += 1


def _report(ticket: dict, handle, *, kind: str, conclusion: str = "confirmed") -> dict:
    if kind == "source":
        # Build the canonical approved_source ref the carrier itself produces
        # from a ``{"location": "source.md#answer"}`` locator, so the rebuilt
        # verdict ref matches the examiner report's ref exactly.
        artifact_digest = "b" * 64
        location = "source.md#answer"
        ref_id = "approved-source-" + _sha({
            "schema_version": "r2-3-005-approved-source-ref/v1",
            "ticket_digest": ticket["ticket_digest"],
            "acceptance_round_id": ticket["acceptance_round_id"],
            "path": "source.md",
            "artifact_digest": artifact_digest,
        })
        evidence_refs = [{
            "type": "approved_source",
            "ref_id": ref_id,
            "ticket_digest": ticket["ticket_digest"],
            "source_bundle_digest": ticket["source_bundle_digest"],
            "location": location,
            "artifact_path": (
                f"acceptance/{ticket['acceptance_round_id']}/approved-source/source.md.json"
            ),
            "artifact_digest": artifact_digest,
        }]
        source_bundle_digest = ticket["source_bundle_digest"]
    else:
        evidence_refs = [{
            "type": "platform_read",
            "ref_id": "platform-ref",
            "ticket_digest": ticket["ticket_digest"],
            "model_state_digest": ticket["model_state_digest"],
            "tool": "get_modeling_context",
            "request_digest": "e" * 64,
            "response_digest": "f" * 64,
            "artifact_path": "evidence/platform.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }]
        source_bundle_digest = None
    report = {
        "task_id": ticket["task_id"],
        "acceptance_round_id": ticket["acceptance_round_id"],
        "ticket_digest": ticket["ticket_digest"],
        "examiner_kind": kind,
        "child_handle_digest": handle.digest,
        "child_session_id": handle.session_id,
        "child_input_digest": handle.input_digest,
        "source_bundle_digest": source_bundle_digest,
        "answerability": "answerable",
        "conclusion": conclusion,
        "evidence": [{"ref_id": evidence_refs[0]["ref_id"], "summary": "bound evidence"}],
        "coverage": {"queries_or_sections": ["cq1"], "complete": True},
        "gaps": [],
        "model_state": ticket["model_state"],
        "evidence_refs": evidence_refs,
        "report_digest": None,
    }
    report["report_digest"] = report_digest(report)
    return report


_CHECK_KEYS = (
    "source_fidelity",
    "scope",
    "ontology_structure",
    "explicit_unknowns",
    "validation_reasoning",
    "governed_retrieval",
    "evidence_lineage",
    "competency_questions",
)


def _pass_checks() -> dict[str, str]:
    return {key: "PASS" for key in _CHECK_KEYS}


def _source_locator(ref: Mapping[str, Any]) -> dict[str, Any]:
    """The verdict agent cites a source by location only; the Host rebuilds."""

    return {"location": ref["location"]}


def _platform_locator(ref: Mapping[str, Any]) -> dict[str, Any]:
    """The verdict agent cites a platform read by its receipt coordinate set."""

    return {
        key: ref[key]
        for key in (
            "ref_id",
            "tool",
            "request_digest",
            "response_digest",
            "artifact_path",
            "page",
        )
    }


def _cq_result(*, status: str, answer: str, locators: list) -> dict[str, Any]:
    # The agent supplies ONLY status/answer/locators; the Host fills the id.
    return {"status": status, "answer": answer, "evidence_refs": locators}


class BuildAcceptanceVerdictTests(unittest.TestCase):
    def _carrier(self, ticket: dict, directory: str) -> RunnerAcceptanceCarrier:
        carrier = RunnerAcceptanceCarrier(
            Path(directory),
            task_id=ticket["task_id"],
            acceptance_id="acceptance",
            child_factory=_FakeResource,
        )
        carrier.publish_ticket(
            ticket,
            coordinator_id="coordinator",
            owner_revision=ticket["quality_standard_ref"],
        )
        carrier.ack_ticket(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            ticket_digest_value=ticket["ticket_digest"],
        )
        return carrier

    def _start_and_report(self, carrier, ticket, *, kind: str, request_id: str):
        projection, digest = carrier.project_child_input(
            round_id=ticket["acceptance_round_id"], kind=kind
        )
        handle = carrier.start_child(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            kind=kind,
            input_ref=projection,
            input_digest=digest,
            ticket_digest_value=ticket["ticket_digest"],
            request_id=request_id,
            attempt=0,
        )
        report = carrier.ingest_report(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            handle=handle,
            report=_report(ticket, handle, kind=kind),
        )
        return handle, report

    def test_pass_verdict_host_built_validates(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-0"
            )
            evidence_refs = [
                _source_locator(source_report["evidence_refs"][0]),
                _platform_locator(platform_report["evidence_refs"][0]),
            ]
            built = carrier.build_acceptance_verdict(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                verdict="PASS",
                failure_layer=None,
                blocked_reason=None,
                evidence_refs=evidence_refs,
                checks=_pass_checks(),
                competency_question_results=[_cq_result(
                    status="PASS",
                    answer=source_report["conclusion"],
                    locators=evidence_refs,
                )],
                recommended_action="advance",
                summary="source and platform agree",
                capability=carrier.capability_token("acceptance"),
            )
            verdict_json = built["verdict_json"]
            # The Host filled exactly the 28 canonical keys (no drift).
            self.assertEqual(len(verdict_json), 28)
            self.assertEqual(built["verdict_digest"], verdict_json["verdict_digest"])
            # Mechanical fields come from the bound ticket and reports, not the agent.
            self.assertEqual(verdict_json["ticket_digest"], ticket["ticket_digest"])
            self.assertEqual(verdict_json["modeling_receipts"], ticket["modeling_receipts"])
            self.assertEqual(
                verdict_json["source_report_digest"], source_report["report_digest"]
            )
            self.assertEqual(
                verdict_json["platform_report_digest"], platform_report["report_digest"]
            )
            # A PASS has no tracked infrastructure failures, so the Host cites none.
            self.assertEqual(verdict_json["failure_evidence_refs"], [])
            self.assertEqual(verdict_json["failure_evidence_digests"], [])
            self.assertEqual(verdict_json["infrastructure_failure_digests"], [])
            # The agent supplied only locators; the Host rebuilt the typed refs.
            for ref in verdict_json["evidence_refs"]:
                self.assertIn(ref["type"], {"approved_source", "platform_read"})
                self.assertEqual(ref["ticket_digest"], ticket["ticket_digest"])
            # The rebuilt approved_source ref matches the examiner report's ref
            # (deterministic Host assembly from the same ticket).
            self.assertEqual(
                verdict_json["evidence_refs"][0],
                source_report["evidence_refs"][0],
            )
            # The Host filled the ticket-bound CQ id; the agent did not supply it.
            self.assertEqual(
                verdict_json["competency_question_results"][0]["id"],
                ticket["question_id"],
            )
            # The Host-built envelope passes validate_verdict unchanged.
            normalized = validate_verdict(
                verdict_json,
                ticket=ticket,
                source_report=source_report,
                platform_report=platform_report,
            )
            self.assertEqual(normalized["verdict_digest"], built["verdict_digest"])
            carrier.cleanup()

    def test_fail_verdict_host_built_validates(self) -> None:
        ticket = _ticket(round_suffix="fail")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-fail-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-fail-0"
            )
            evidence_refs = [_source_locator(source_report["evidence_refs"][0])]
            checks = _pass_checks()
            checks["ontology_structure"] = "FAIL"
            built = carrier.build_acceptance_verdict(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                verdict="FAIL",
                failure_layer="modeling-quality",
                blocked_reason=None,
                evidence_refs=evidence_refs,
                checks=checks,
                competency_question_results=[_cq_result(
                    status="PASS",
                    answer=source_report["conclusion"],
                    locators=evidence_refs,
                )],
                recommended_action="model-repair",
                summary="ontology structure check failed",
                capability=carrier.capability_token("acceptance"),
            )
            normalized = validate_verdict(
                built["verdict_json"],
                ticket=ticket,
                source_report=source_report,
                platform_report=platform_report,
            )
            self.assertEqual(normalized["verdict"], "FAIL")
            self.assertEqual(normalized["failure_layer"], "modeling-quality")
            carrier.cleanup()

    def test_runtime_blocked_verdict_host_built_validates_like_start57(self) -> None:
        # start57 shape: the source examiner produced a terminal report, the
        # platform examiner crashed twice (attempt 0 and the retry attempt 1),
        # both recycled with infrastructure-failure cleanups.  The Host must
        # derive both failure refs and their digest lists; the agent passes none.
        ticket = _ticket(round_suffix="blocked")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-blk-0"
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=source_handle,
                completion_ref={"terminal_report_digest": source_report["report_digest"]},
                request_id="recycle-src-blk",
            )
            platform_projection, platform_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="platform"
            )
            platform0 = carrier.start_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                kind="platform",
                input_ref=platform_projection,
                input_digest=platform_digest,
                ticket_digest_value=ticket["ticket_digest"],
                request_id="plt-blk-0",
                attempt=0,
            )
            failure0 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform0,
                failure_category="runtime",
                reason_code="child-timeout",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform0,
                completion_ref={"infrastructure_failure_digest": failure0.failure_digest},
                request_id="recycle-plt-blk-0",
            )
            platform1 = carrier.start_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                kind="platform",
                input_ref=platform_projection,
                input_digest=platform_digest,
                ticket_digest_value=ticket["ticket_digest"],
                request_id="plt-blk-1",
                attempt=1,
            )
            failure1 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform1,
                failure_category="runtime",
                reason_code="child-timeout",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform1,
                completion_ref={"infrastructure_failure_digest": failure1.failure_digest},
                request_id="recycle-plt-blk-1",
            )
            checks = _pass_checks()
            checks["validation_reasoning"] = "BLOCKED"
            built = carrier.build_acceptance_verdict(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                verdict="BLOCKED",
                failure_layer="runtime",
                blocked_reason="runtime-infrastructure",
                evidence_refs=[],
                checks=checks,
                competency_question_results=[_cq_result(
                    status="BLOCKED",
                    answer="platform examiner did not return a terminal report",
                    locators=[],
                )],
                recommended_action="retry-after-recovery",
                summary="platform examiner timed out twice",
                capability=carrier.capability_token("acceptance"),
            )
            verdict_json = built["verdict_json"]
            # The Host derived exactly the two cleaned platform failures.
            cited = sorted({failure0.failure_digest, failure1.failure_digest})
            self.assertEqual(verdict_json["failure_evidence_digests"], cited)
            self.assertEqual(verdict_json["infrastructure_failure_digests"], cited)
            self.assertEqual(len(verdict_json["failure_evidence_refs"]), 2)
            for ref in verdict_json["failure_evidence_refs"]:
                self.assertEqual(ref["type"], "infrastructure_failure")
                self.assertIn(ref["failure_digest"], cited)
            # platform_report_digest is None because the platform examiner never
            # produced a terminal report; source_report_digest is bound.
            self.assertIsNone(verdict_json["platform_report_digest"])
            self.assertEqual(
                verdict_json["source_report_digest"], source_report["report_digest"]
            )
            normalized = validate_verdict(
                verdict_json,
                ticket=ticket,
                source_report=source_report,
                platform_report=None,
                infrastructure_failures=[failure0, failure1],
            )
            self.assertEqual(normalized["verdict"], "BLOCKED")
            carrier.cleanup()

    def test_failure_without_infra_cleanup_is_not_cited(self) -> None:
        # start57 also recorded a source attempt-0 failure whose child was later
        # recycled with a terminal report (no infrastructure cleanup receipt).
        # That failure is not durable BLOCKED evidence and must not be cited.
        ticket = _ticket(round_suffix="nocite")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_projection, source_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="source"
            )
            source0 = carrier.start_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                kind="source",
                input_ref=source_projection,
                input_digest=source_digest,
                ticket_digest_value=ticket["ticket_digest"],
                request_id="src-nocite-0",
                attempt=0,
            )
            uncleaned = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=source0,
                failure_category="runtime",
                reason_code="child-timeout",
            )
            # The child eventually produced a terminal report and was recycled
            # with that report digest (not the failure digest).  No cleanup
            # receipt binds this failure digest, so it is intentionally absent
            # from Host-derived refs.
            source_report = carrier.ingest_report(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=source0,
                report=_report(ticket, source0, kind="source"),
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=source0,
                completion_ref={"terminal_report_digest": source_report["report_digest"]},
                request_id="recycle-nocite-src",
            )
            refs = carrier._host_failure_evidence_refs(ticket["acceptance_round_id"])
            self.assertEqual(refs, [])
            # The failure is still tracked, but not citable in a verdict envelope.
            self.assertIn(uncleaned.failure_digest, carrier._failures)
            carrier.cleanup()

    def test_dispatch_merged_submit_records_verdict_found_by_coordinator(self) -> None:
        # start59 fix: the agent calls ONE merged ``submit_acceptance_result``
        # with only its judgment + identifiers + a fresh request_id.  The Host
        # assembles the 28-field envelope, validates it, and records the verdict
        # internally; the large verdict_json never transits the codex CLI
        # tool-result.  The recorded verdict must be findable by
        # ``coordinator_get_verdict`` (and ``acceptance_get_verdict``).
        ticket = _ticket(round_suffix="e2e")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-e2e-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-e2e-0"
            )
            evidence_refs = [
                _source_locator(source_report["evidence_refs"][0]),
                _platform_locator(platform_report["evidence_refs"][0]),
            ]
            endpoint = carrier._capability_endpoints["acceptance"]
            token = carrier.capability_token("acceptance")
            submit = endpoint.handle({
                "jsonrpc": "2.0",
                "id": 1,
                "token": token,
                "method": "tools/call",
                "params": {
                    "name": "submit_acceptance_result",
                    "arguments": {
                        "acceptance_id": "acceptance",
                        "round_id": ticket["acceptance_round_id"],
                        "verdict": "PASS",
                        "failure_layer": None,
                        "blocked_reason": None,
                        "evidence_refs": evidence_refs,
                        "checks": _pass_checks(),
                        "competency_question_results": [_cq_result(
                            status="PASS",
                            answer=source_report["conclusion"],
                            locators=evidence_refs,
                        )],
                        "recommended_action": "advance",
                        "summary": "source and platform agree",
                        "request_id": "submit-e2e",
                    },
                },
            })
            self.assertNotIn("error", submit)
            receipt = submit["result"]["structuredContent"]["data"]
            # The agent receives only the small verdict receipt/digest, never the
            # 28-field verdict_json.  There is nothing to display-truncate.
            self.assertEqual(set(receipt), {
                "task_id",
                "acceptance_round_id",
                "request_id",
                "verdict_digest",
                "receipt_digest",
                "verdict",
            })
            self.assertEqual(receipt["verdict"], "PASS")
            self.assertEqual(receipt["request_id"], "submit-e2e")
            self.assertEqual(receipt["acceptance_round_id"], ticket["acceptance_round_id"])
            # The Host-recorded verdict is findable by coordinator_get_verdict
            # and acceptance_get_verdict (independent readers).
            coordinator_receipt = carrier.coordinator_get_verdict(
                coordinator_id="coordinator",
                round_id=ticket["acceptance_round_id"],
                verdict_digest_value=None,
                capability=carrier.capability_token("coordinator"),
            )
            self.assertEqual(coordinator_receipt.verdict_digest, receipt["verdict_digest"])
            acceptance_receipt = carrier.get_verdict(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                verdict_digest_value=receipt["verdict_digest"],
                capability=carrier.capability_token("acceptance"),
            )
            self.assertEqual(acceptance_receipt.request_id, "submit-e2e")
            carrier.cleanup()

    def test_dispatch_merged_submit_idempotent_retry_same_judgment(self) -> None:
        # A retry with the SAME judgment + SAME request_id is idempotent: the
        # deterministic assembly yields the same verdict_digest, so the Host
        # returns the existing receipt.  A retry with a DIFFERENT judgment
        # produces a different digest and is rejected as a conflicting retry.
        ticket = _ticket(round_suffix="retry")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-retry-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-retry-0"
            )
            evidence_refs = [
                _source_locator(source_report["evidence_refs"][0]),
                _platform_locator(platform_report["evidence_refs"][0]),
            ]
            endpoint = carrier._capability_endpoints["acceptance"]
            token = carrier.capability_token("acceptance")
            common = {
                "acceptance_id": "acceptance",
                "round_id": ticket["acceptance_round_id"],
                "verdict": "PASS",
                "failure_layer": None,
                "blocked_reason": None,
                "evidence_refs": evidence_refs,
                "checks": _pass_checks(),
                "competency_question_results": [_cq_result(
                    status="PASS",
                    answer=source_report["conclusion"],
                    locators=evidence_refs,
                )],
                "recommended_action": "advance",
                "summary": "source and platform agree",
                "request_id": "submit-retry",
            }
            first = endpoint.handle({
                "jsonrpc": "2.0", "id": 1, "token": token, "method": "tools/call",
                "params": {"name": "submit_acceptance_result", "arguments": dict(common)},
            })
            self.assertNotIn("error", first)
            replay = endpoint.handle({
                "jsonrpc": "2.0", "id": 2, "token": token, "method": "tools/call",
                "params": {"name": "submit_acceptance_result", "arguments": dict(common)},
            })
            self.assertNotIn("error", replay)
            self.assertEqual(
                first["result"]["structuredContent"]["data"]["receipt_digest"],
                replay["result"]["structuredContent"]["data"]["receipt_digest"],
            )
            # A different judgment (different summary) drifts the digest; the
            # Host rejects the conflicting retry with the opaque capability error.
            conflicting = dict(common)
            conflicting["summary"] = "a different judgment"
            conflicting["request_id"] = "submit-different"
            rejected = endpoint.handle({
                "jsonrpc": "2.0", "id": 3, "token": token, "method": "tools/call",
                "params": {"name": "submit_acceptance_result", "arguments": conflicting},
            })
            self.assertIn("error", rejected)
            carrier.cleanup()

    def test_dispatch_merged_submit_blocked_like_start59_records_and_finds(self) -> None:
        # start59 shape: the source examiner produced a terminal report, the
        # platform examiner crashed twice (attempt 0 + the retry attempt 1),
        # both recycled with infrastructure-failure cleanups.  The merged call
        # must assemble a BLOCKED/runtime/runtime-infrastructure verdict that
        # cites exactly the two platform failures, validate it, and record it so
        # coordinator_get_verdict finds it.  The agent supplies only judgment;
        # there is no verdict_json to display-truncate (the start59 root cause).
        ticket = _ticket(round_suffix="merged-blk")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-mblk-0"
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=source_handle,
                completion_ref={"terminal_report_digest": source_report["report_digest"]},
                request_id="recycle-src-mblk",
            )
            platform_projection, platform_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="platform"
            )
            platform0 = carrier.start_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                kind="platform",
                input_ref=platform_projection,
                input_digest=platform_digest,
                ticket_digest_value=ticket["ticket_digest"],
                request_id="plt-mblk-0",
                attempt=0,
            )
            failure0 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform0,
                failure_category="runtime",
                reason_code="child-timeout",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform0,
                completion_ref={"infrastructure_failure_digest": failure0.failure_digest},
                request_id="recycle-plt-mblk-0",
            )
            platform1 = carrier.start_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                kind="platform",
                input_ref=platform_projection,
                input_digest=platform_digest,
                ticket_digest_value=ticket["ticket_digest"],
                request_id="plt-mblk-1",
                attempt=1,
            )
            failure1 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform1,
                failure_category="runtime",
                reason_code="child-timeout",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=platform1,
                completion_ref={"infrastructure_failure_digest": failure1.failure_digest},
                request_id="recycle-plt-mblk-1",
            )
            checks = _pass_checks()
            checks["validation_reasoning"] = "BLOCKED"
            endpoint = carrier._capability_endpoints["acceptance"]
            token = carrier.capability_token("acceptance")
            submit = endpoint.handle({
                "jsonrpc": "2.0",
                "id": 1,
                "token": token,
                "method": "tools/call",
                "params": {
                    "name": "submit_acceptance_result",
                    "arguments": {
                        "acceptance_id": "acceptance",
                        "round_id": ticket["acceptance_round_id"],
                        "verdict": "BLOCKED",
                        "failure_layer": "runtime",
                        "blocked_reason": "runtime-infrastructure",
                        "evidence_refs": [],
                        "checks": checks,
                        "competency_question_results": [_cq_result(
                            status="BLOCKED",
                            answer="platform examiner did not return a terminal report",
                            locators=[],
                        )],
                        "recommended_action": "retry-after-recovery",
                        "summary": "platform examiner timed out twice",
                        "request_id": "submit-mblk",
                    },
                },
            })
            self.assertNotIn("error", submit)
            receipt = submit["result"]["structuredContent"]["data"]
            self.assertEqual(receipt["verdict"], "BLOCKED")
            self.assertEqual(receipt["request_id"], "submit-mblk")
            # The Host-derived envelope (inspected via the recorded verdict)
            # cites exactly the two cleaned platform failures and is the exact
            # 28-field shape validate_verdict accepts.
            recorded = carrier._rounds[ticket["acceptance_round_id"]]["verdict"]
            cited = sorted({failure0.failure_digest, failure1.failure_digest})
            self.assertEqual(recorded["failure_evidence_digests"], cited)
            self.assertEqual(recorded["infrastructure_failure_digests"], cited)
            self.assertEqual(len(recorded), 28)
            renormalized = validate_verdict(
                recorded,
                ticket=ticket,
                source_report=source_report,
                platform_report=None,
                infrastructure_failures=[failure0, failure1],
            )
            self.assertEqual(renormalized["verdict_digest"], receipt["verdict_digest"])
            # round_summary exposes the BLOCKED verdict to the Coordinator
            # (coordinator_get_verdict only retrieves PASS verdicts by design;
            # the merged recording path persists the BLOCKED verdict regardless).
            self.assertEqual(
                carrier.round_summary(ticket["acceptance_round_id"])["verdict"],
                "BLOCKED",
            )
            carrier.cleanup()

    def test_build_rejects_unknown_round_and_bad_capability(self) -> None:
        ticket = _ticket(round_suffix="guard")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id="round-not-published",
                    verdict="PASS",
                    failure_layer=None,
                    blocked_reason=None,
                    evidence_refs=[],
                    checks=_pass_checks(),
                    competency_question_results=[_cq_result(
                        status="PASS", answer="ok", locators=[],
                    )],
                    recommended_action="advance",
                    summary="x",
                    capability=carrier.capability_token("acceptance"),
                )
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    verdict="PASS",
                    failure_layer=None,
                    blocked_reason=None,
                    evidence_refs=[],
                    checks=_pass_checks(),
                    competency_question_results=[_cq_result(
                        status="PASS", answer="ok", locators=[],
                    )],
                    recommended_action="advance",
                    summary="x",
                    capability="not-the-token",
                )
            carrier.cleanup()

    def test_verdict_digest_is_canonical_self_reference_safe(self) -> None:
        ticket = _ticket(round_suffix="dig")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-dig-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-dig-0"
            )
            evidence_refs = [_source_locator(source_report["evidence_refs"][0])]
            built = carrier.build_acceptance_verdict(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                verdict="PASS",
                failure_layer=None,
                blocked_reason=None,
                evidence_refs=evidence_refs,
                checks=_pass_checks(),
                competency_question_results=[_cq_result(
                    status="PASS",
                    answer=source_report["conclusion"],
                    locators=evidence_refs,
                )],
                recommended_action="advance",
                summary="ok",
                capability=carrier.capability_token("acceptance"),
            )
            verdict_json = built["verdict_json"]
            # The Host digest equals the public canonical preimage helper, not a
            # private re-implementation.
            self.assertEqual(
                built["verdict_digest"],
                canonical_digest(verdict_json, self_field="verdict_digest"),
            )
            self.assertEqual(built["verdict_digest"], verdict_digest(verdict_json))
            # Mutating the returned envelope must invalidate the digest: the
            # agent cannot tamper with a Host-built field after the fact.
            tampered = dict(verdict_json)
            tampered["summary"] = "tampered"
            self.assertNotEqual(
                canonical_digest(tampered, self_field="verdict_digest"),
                built["verdict_digest"],
            )
            carrier.cleanup()

    def test_host_rejects_typed_evidence_ref_inputs(self) -> None:
        # start61 root cause: the agent hand-assembled the approved_source
        # typed-ref field set and got it wrong.  The merged submit must accept
        # ONLY locators; a typed ref (or any structure carrying Host-owned
        # digests/paths) is rejected at assembly time, before validate_verdict.
        ticket = _ticket(round_suffix="driftref")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-driftref-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-driftref-0"
            )
            typed_ref = source_report["evidence_refs"][0]
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    verdict="PASS",
                    failure_layer=None,
                    blocked_reason=None,
                    evidence_refs=[typed_ref],
                    checks=_pass_checks(),
                    competency_question_results=[_cq_result(
                        status="PASS", answer="ok", locators=[],
                    )],
                    recommended_action="advance",
                    summary="typed ref must be rejected",
                    capability=carrier.capability_token("acceptance"),
                )
            carrier.cleanup()

    def test_host_rejects_drifted_checks_key_set(self) -> None:
        # start61 root cause: the agent passed ``checks`` with the wrong key
        # set.  The Host owns the eight CHECK_KEYS exactly; an unknown key or a
        # missing key is rejected at assembly time.
        ticket = _ticket(round_suffix="driftchecks")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-dc-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-dc-0"
            )
            extra = _pass_checks()
            extra["ontology_structure"] = "FAIL"
            extra["unknown_check"] = "FAIL"
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    verdict="FAIL",
                    failure_layer="modeling-quality",
                    blocked_reason=None,
                    evidence_refs=[],
                    checks=extra,
                    competency_question_results=[_cq_result(
                        status="PASS", answer="ok", locators=[],
                    )],
                    recommended_action="model-repair",
                    summary="unknown check key must be rejected",
                    capability=carrier.capability_token("acceptance"),
                )
            missing = _pass_checks()
            del missing["evidence_lineage"]
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    verdict="PASS",
                    failure_layer=None,
                    blocked_reason=None,
                    evidence_refs=[],
                    checks=missing,
                    competency_question_results=[_cq_result(
                        status="PASS", answer="ok", locators=[],
                    )],
                    recommended_action="advance",
                    summary="missing check key must be rejected",
                    capability=carrier.capability_token("acceptance"),
                )
            carrier.cleanup()

    def test_host_rejects_cq_result_with_agent_supplied_id(self) -> None:
        # The CQ id is ticket-bound and Host-owned.  If the agent supplies an
        # ``id`` field (even the correct one), the Host rejects the extra key.
        ticket = _ticket(round_suffix="driftcq")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-dcq-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-dcq-0"
            )
            with self.assertRaises(AcceptanceContractError):
                carrier.build_acceptance_verdict(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    verdict="PASS",
                    failure_layer=None,
                    blocked_reason=None,
                    evidence_refs=[],
                    checks=_pass_checks(),
                    competency_question_results=[{
                        "id": ticket["question_id"],
                        "status": "PASS",
                        "answer": "ok",
                        "evidence_refs": [],
                    }],
                    recommended_action="advance",
                    summary="agent-supplied CQ id must be rejected",
                    capability=carrier.capability_token("acceptance"),
                )
            carrier.cleanup()

    def test_simplified_submit_records_verdict_passing_validate(self) -> None:
        # The end-to-end contract the start61 fix targets: the agent supplies
        # ONLY locators + the flat checks mapping + CQ status/answer/locators.
        # The Host rebuilds every typed structure; the recorded verdict passes
        # validate_verdict unchanged and is findable by an independent reader.
        ticket = _ticket(round_suffix="simple")
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(ticket, directory)
            source_handle, source_report = self._start_and_report(
                carrier, ticket, kind="source", request_id="src-simple-0"
            )
            platform_handle, platform_report = self._start_and_report(
                carrier, ticket, kind="platform", request_id="plt-simple-0"
            )
            locators = [
                _source_locator(source_report["evidence_refs"][0]),
                _platform_locator(platform_report["evidence_refs"][0]),
            ]
            endpoint = carrier._capability_endpoints["acceptance"]
            token = carrier.capability_token("acceptance")
            submit = endpoint.handle({
                "jsonrpc": "2.0",
                "id": 1,
                "token": token,
                "method": "tools/call",
                "params": {
                    "name": "submit_acceptance_result",
                    "arguments": {
                        "acceptance_id": "acceptance",
                        "round_id": ticket["acceptance_round_id"],
                        "verdict": "PASS",
                        "failure_layer": None,
                        "blocked_reason": None,
                        "evidence_refs": locators,
                        "checks": _pass_checks(),
                        "competency_question_results": [_cq_result(
                            status="PASS",
                            answer=source_report["conclusion"],
                            locators=locators,
                        )],
                        "recommended_action": "advance",
                        "summary": "source and platform agree",
                        "request_id": "submit-simple",
                    },
                },
            })
            self.assertNotIn("error", submit)
            receipt = submit["result"]["structuredContent"]["data"]
            self.assertEqual(receipt["verdict"], "PASS")
            recorded = carrier._rounds[ticket["acceptance_round_id"]]["verdict"]
            # The Host rebuilt typed refs that exactly match the examiner
            # reports (deterministic assembly from the same ticket).
            self.assertEqual(
                recorded["evidence_refs"][0],
                source_report["evidence_refs"][0],
            )
            self.assertEqual(
                recorded["evidence_refs"][1],
                platform_report["evidence_refs"][0],
            )
            self.assertEqual(
                recorded["competency_question_results"][0]["id"],
                ticket["question_id"],
            )
            # Independent re-validation against the recorded envelope succeeds.
            renormalized = validate_verdict(
                recorded,
                ticket=ticket,
                source_report=source_report,
                platform_report=platform_report,
            )
            self.assertEqual(renormalized["verdict_digest"], receipt["verdict_digest"])
            carrier.cleanup()


class CapabilitySchemaArraySupportTests(unittest.TestCase):
    def test_build_acceptance_verdict_schema_accepts_judgment_arrays(self) -> None:
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["build_acceptance_verdict"]
        self.assertTrue(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict": "BLOCKED",
                    "failure_layer": "runtime",
                    "blocked_reason": "runtime-infrastructure",
                    # Evidence LOCATORS (source location / platform coordinate set),
                    # never the typed-ref structure the Host owns.
                    "evidence_refs": [
                        {"location": "source.md#anchor"},
                        {
                            "ref_id": "plt-1",
                            "tool": "get_modeling_context",
                            "request_digest": "e" * 64,
                            "response_digest": "f" * 64,
                            "artifact_path": "evidence/platform.json",
                            "page": {
                                "ordinal": 0,
                                "input_cursor": None,
                                "output_cursor": None,
                                "has_more": False,
                                "sequence_complete": True,
                            },
                        },
                    ],
                    "checks": {"source_fidelity": "PASS"},
                    "competency_question_results": [
                        {"status": "PASS", "answer": "ok", "evidence_refs": []},
                    ],
                    "recommended_action": "wait",
                    "summary": "blocked",
                },
                schema,
            )
        )

    def test_submit_acceptance_result_schema_accepts_judgment_and_request_id(self) -> None:
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["submit_acceptance_result"]
        self.assertTrue(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict": "BLOCKED",
                    "failure_layer": "runtime",
                    "blocked_reason": "runtime-infrastructure",
                    "evidence_refs": [{"location": "source.md#anchor"}],
                    "checks": {"source_fidelity": "PASS"},
                    "competency_question_results": [
                        {"status": "BLOCKED", "answer": "blocked", "evidence_refs": []},
                    ],
                    "recommended_action": "retry-after-recovery",
                    "summary": "blocked",
                    "request_id": "submit-1",
                },
                schema,
            )
        )

    def test_submit_acceptance_result_schema_rejects_verdict_json_relay(self) -> None:
        # The merged submit surface must NOT accept the large verdict_json /
        # verdict_digest relay: that was the start59 root cause (codex CLI
        # display-truncated the assembled verdict in the tool-result view).
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["submit_acceptance_result"]
        self.assertFalse(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict_json": {"verdict": "PASS"},
                    "verdict_digest": "0" * 64,
                    "request_id": "submit-1",
                },
                schema,
            )
        )

    def test_submit_acceptance_result_schema_rejects_missing_request_id(self) -> None:
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["submit_acceptance_result"]
        self.assertFalse(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict": "PASS",
                    "failure_layer": None,
                    "blocked_reason": None,
                    "evidence_refs": [],
                    "checks": {},
                    "competency_question_results": [],
                    "recommended_action": "advance",
                    "summary": "ok",
                },
                schema,
            )
        )

    def test_schema_rejects_extra_judgment_field(self) -> None:
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["build_acceptance_verdict"]
        self.assertFalse(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict": "PASS",
                    "failure_layer": None,
                    "blocked_reason": None,
                    "evidence_refs": [],
                    "checks": {},
                    "competency_question_results": [],
                    "recommended_action": "advance",
                    "summary": "ok",
                    # The agent must not pass a Host-owned mechanical field.
                    "verdict_digest": "0" * 64,
                },
                schema,
            )
        )

    def test_schema_rejects_non_array_evidence_refs(self) -> None:
        from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS

        schema = CAPABILITY_TOOL_SCHEMAS["build_acceptance_verdict"]
        self.assertFalse(
            _matches_schema(
                {
                    "acceptance_id": "acceptance",
                    "round_id": "round-1",
                    "verdict": "PASS",
                    "failure_layer": None,
                    "blocked_reason": None,
                    "evidence_refs": {"not": "a list"},
                    "checks": {},
                    "competency_question_results": [],
                    "recommended_action": "advance",
                    "summary": "ok",
                },
                schema,
            )
        )


if __name__ == "__main__":
    unittest.main()
