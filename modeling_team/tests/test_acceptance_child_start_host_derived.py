"""R2.3-005 step-3: acceptance_child_start Host-derived mechanics.

The Acceptance examiner-child orchestration is deterministic: the Host (carrier)
derives every mechanical field (child-input projection, ticket digest, attempt)
from the immutable round/ticket state.  The LLM-facing capability schema accepts
only ``acceptance_id``, ``round_id``, ``kind``, and ``request_id``.  These tests
mirror the start56 failure evidence: a real platform ``project_id`` is a UUID
whose first character is a digit, so any caller-supplied ``input_ref`` that
re-validated that identifier through the stricter stable-id rule failed.  The
Host projection uses the platform-identifier rule and always wins.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    model_state_digest,
    modeling_receipt_digest,
    ticket_digest,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ticket_with_platform_project_id(project_id: str, round_suffix: str = "1") -> dict:
    """Build a complete formal ticket whose platform_read_scope uses ``project_id``.

    Mirrors the ``_ticket`` helper in ``test_r23005_contracts`` but lets the test
    pick a realistic UUID-shaped platform identifier (the kind a live Platform API
    actually returns, including a digit-first UUID like start56's).
    """

    state = {
        "project_id": project_id,
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
        receipts.append(
            {
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
        )
        receipts[-1]["receipt_digest"] = modeling_receipt_digest(receipts[-1])
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


# A live platform Project identifier is a UUID whose first character is a digit.
# This is the exact shape that surfaced "project_id must be a safe stable
# identifier" in start56 when an LLM-supplied input_ref re-validated it.
START56_PROJECT_ID = "2480506c-a9f8-4c2b-804d-aec6e993a4f8"


class AcceptanceChildStartHostDerivedTests(unittest.TestCase):
    def test_minimal_args_succeed_with_real_uuid_platform_project_id(self) -> None:
        ticket = _ticket_with_platform_project_id(START56_PROJECT_ID)
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance"
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
            expected_projection, expected_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="platform"
            )
            # The Host projection's project_id is the safe platform identifier
            # (a digit-first UUID), not a stable-id-compatible string.
            self.assertEqual(
                expected_projection["platform_read_scope"]["project_id"],
                START56_PROJECT_ID,
            )
            endpoint = carrier._capability_endpoints["acceptance"]
            # The minimal LLM surface: only acceptance_id, round_id, kind, request_id.
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "token": carrier.capability_token("acceptance"),
                    "method": "tools/call",
                    "params": {
                        "name": "acceptance_child_start",
                        "arguments": {
                            "acceptance_id": "acceptance",
                            "round_id": ticket["acceptance_round_id"],
                            "kind": "platform",
                            "request_id": "minimal-start",
                        },
                    },
                }
            )
            self.assertNotIn("error", response)
            data = response["result"]["structuredContent"]["data"]
            self.assertEqual(data["input_digest"], expected_digest)
            self.assertEqual(data["ticket_digest"], ticket["ticket_digest"])
            carrier.cleanup()

    def test_dispatch_ignores_caller_supplied_input_ticket_and_attempt(self) -> None:
        ticket = _ticket_with_platform_project_id(START56_PROJECT_ID)
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance"
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
            projection, digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="source"
            )
            # Direct dispatch bypasses the schema.  Even wildly wrong mechanical
            # arguments are ignored: the Host derives projection, ticket digest,
            # and attempt from the immutable round/ticket state.
            handle = carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_start",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "kind": "source",
                    "request_id": "host-overrides-mechanics",
                    "input_ref": {"ticket_digest": ticket["ticket_digest"], "junk": True},
                    "input_digest": "0" * 64,
                    "ticket_digest": "1" * 64,
                    "attempt": 7,
                },
            )
            self.assertEqual(handle.input_digest, digest)
            self.assertEqual(handle.ticket_digest, ticket["ticket_digest"])
            self.assertEqual(handle.attempt, 0)
            carrier.cleanup()

    def test_attempt_auto_tracks_zero_then_retry_then_round_blocks(self) -> None:
        ticket = _ticket_with_platform_project_id(START56_PROJECT_ID, round_suffix="att")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
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

            def start(request_id: str) -> object:
                return carrier._dispatch_capability(
                    "acceptance",
                    "acceptance_child_start",
                    {
                        "acceptance_id": "acceptance",
                        "round_id": ticket["acceptance_round_id"],
                        "kind": "source",
                        "request_id": request_id,
                    },
                )

            # First start: Host auto-tracks attempt 0 (no caller-supplied attempt).
            handle0 = start("att-0")
            self.assertEqual(handle0.attempt, 0)
            # An infrastructure failure + recycle authorizes the single retry.
            failure = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle0,
                failure_category="runtime",
                reason_code="examiner-process-crash",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle0,
                completion_ref={"infrastructure_failure_digest": failure.failure_digest},
                request_id="recycle-0",
            )
            # Second start: Host auto-tracks attempt 1 (the permitted retry).
            handle1 = start("att-1")
            self.assertEqual(handle1.attempt, 1)
            failure1 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle1,
                failure_category="runtime",
                reason_code="examiner-process-crash",
            )
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle1,
                completion_ref={"infrastructure_failure_digest": failure1.failure_digest},
                request_id="recycle-1",
            )
            # After a second infrastructure failure the round is BLOCKED; a third
            # start is rejected at the round-status guard (the realistic guard the
            # Acceptance agent owns).
            with self.assertRaises(AcceptanceContractError):
                start("att-2")
            self.assertEqual(
                carrier.round_summary(ticket["acceptance_round_id"])["status"],
                "blocked",
            )
            carrier.cleanup()

    def test_derive_next_attempt_emits_structured_diagnostics(self) -> None:
        # Unit-test the Host attempt tracker directly so both structured
        # diagnostics are covered without depending on the round-blocking side
        # effect that follows a second infrastructure failure.
        ticket = _ticket_with_platform_project_id(START56_PROJECT_ID, round_suffix="dnav")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance"
            )
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            round_data = carrier._rounds[ticket["acceptance_round_id"]]
            # No prior attempt: first start is attempt 0.
            self.assertEqual(carrier._derive_next_attempt(round_data, "source"), 0)
            # Prior attempt 0 but kind not authorized for retry: structured
            # examiner_retry_not_authorized diagnostic.
            round_data["attempts"]["source"] = 0
            with self.assertRaises(AcceptanceContractError) as caught:
                carrier._derive_next_attempt(round_data, "source")
            self.assertEqual(
                caught.exception.data,
                {
                    "reason": "examiner_retry_not_authorized",
                    "kind": "source",
                    "prior_attempt": 0,
                },
            )
            # Prior attempt 1: budget exhausted, structured diagnostic.
            round_data["attempts"]["source"] = 1
            with self.assertRaises(AcceptanceContractError) as caught:
                carrier._derive_next_attempt(round_data, "source")
            self.assertEqual(
                caught.exception.data,
                {
                    "reason": "examiner_retry_budget_exhausted",
                    "kind": "source",
                    "prior_attempt": 1,
                },
            )
            carrier.cleanup()

    def test_round_sequencing_guard_is_structured(self) -> None:
        first = _ticket_with_platform_project_id(START56_PROJECT_ID, round_suffix="seq-1")
        second = _ticket_with_platform_project_id(START56_PROJECT_ID, round_suffix="seq-2")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=first["task_id"], acceptance_id="acceptance"
            )
            for ticket in (first, second):
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
            # Start a source child in the first round but do not recycle it, so
            # the second round cannot begin before prior cleanup.
            handle = carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_start",
                {
                    "acceptance_id": "acceptance",
                    "round_id": first["acceptance_round_id"],
                    "kind": "source",
                    "request_id": "seq-first-start",
                },
            )
            self.assertEqual(handle.attempt, 0)
            with self.assertRaises(AcceptanceContractError) as caught:
                carrier._dispatch_capability(
                    "acceptance",
                    "acceptance_child_start",
                    {
                        "acceptance_id": "acceptance",
                        "round_id": second["acceptance_round_id"],
                        "kind": "source",
                        "request_id": "seq-second-start",
                    },
                )
            data = caught.exception.data
            self.assertEqual(data["reason"], "prior_round_cleanup_required")
            self.assertEqual(len(data["unresolved_rounds"]), 1)
            entry = data["unresolved_rounds"][0]
            self.assertEqual(entry["acceptance_round_id"], first["acceptance_round_id"])
            self.assertEqual(entry["status"], "active")
            self.assertEqual(entry["active_kinds"], ["source"])
            carrier.cleanup()

    def test_ticket_digest_argument_is_accepted_but_ignored(self) -> None:
        ticket = _ticket_with_platform_project_id(START56_PROJECT_ID, round_suffix="tdi")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance"
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
            endpoint = carrier._capability_endpoints["acceptance"]
            # ticket_digest/attempt remain in the schema as optional properties;
            # a caller may pass them but the Host ignores the values and derives
            # the correct bindings from the round.
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "token": carrier.capability_token("acceptance"),
                    "method": "tools/call",
                    "params": {
                        "name": "acceptance_child_start",
                        "arguments": {
                            "acceptance_id": "acceptance",
                            "round_id": ticket["acceptance_round_id"],
                            "kind": "source",
                            "request_id": "tdi-start",
                            "ticket_digest": "0" * 64,
                            "attempt": 1,
                        },
                    },
                }
            )
            self.assertNotIn("error", response)
            data = response["result"]["structuredContent"]["data"]
            self.assertEqual(data["ticket_digest"], ticket["ticket_digest"])
            carrier.cleanup()


if __name__ == "__main__":
    unittest.main()
