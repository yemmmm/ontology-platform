"""R2.3-008 start10: illegal consumer_query plans are typed and revisable.

In start10 the Modeling Agent wrote ``required_paths`` as full path-expression
strings (``workflow-b--currentlyConsumesOutput-->quality-rating-field``).  The
retrieval gate's bare-local-name contract rejected the plan only inside
accepted-candidate registration -- after Protocol had already built and
delivered a receipt -- and the ``ProtocolRetrievalGateError`` escaped the run
loop as an unclassified ``run failed:`` exit with no quarantine and no typed
terminal state.

Two narrow guards, both reusing the exact registration-time validator:

1. The typed receipt builder now runs ``ProtocolRetrievalGate`` over the
   candidate before any receipt is issued.  A rejected plan is returned to the
   Protocol Agent as the structured success-path diagnostic
   ``{ok: False, error: {reason: consumer_query_plan_invalid, detail, action}}``
   so the sanctioned conflict/revision loop delivers one complete revised
   candidate instead of a burned run.
2. Registration failures at the accepted-receipt observation are R2.3-009
   A-class typed feedback to Modeling with a reopen for one strictly newer
   revision, instead of a burned run.

The bare-local-name contract itself, ``_extract_plan``, transport
single-acceptance semantics, and the defect-7 idempotent replay are unchanged.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
)
from modeling_team.candidate_progress import (
    FORMAL_CANDIDATE_KIND,
    FormalCandidateProgress,
)
from modeling_team.contracts import repository_root
from modeling_team.formal_runs import R2_3_009_CONTRACT
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt


def _legal_candidate() -> dict[str, object]:
    """Bare local-name plan that mirrors the accepted 005 baseline shape."""

    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": "rev-1",
        "scope": "new",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "predicate-field",
                "item_kind": "predicate",
                "semantic": {"predicate": "field", "predicate_kind": "fact"},
            },
            {
                "item_id": "entity-a",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": "entity-a",
                    "class": "Example",
                    "values": {"label": "Entity A", "field": "value-a"},
                },
            },
            {
                "item_id": "consumer-q",
                "item_kind": "consumer_query",
                "semantic": {
                    "query_id": "q",
                    "question": "What is the field?",
                    "required_paths": ["field"],
                },
            },
        ],
    }


def _illegal_candidate() -> dict[str, object]:
    """The start10 shape: a full path expression instead of a bare local name."""

    candidate = _legal_candidate()
    items = list(candidate["items"])  # type: ignore[arg-type]
    items[2] = {
        "item_id": "consumer-q",
        "item_kind": "consumer_query",
        "semantic": {
            "query_id": "q",
            "question": "What is consumed?",
            "required_paths": ["workflow-b--currentlyConsumesOutput-->quality-rating-field"],
        },
    }
    candidate["items"] = items  # type: ignore[assignment]
    return candidate


def _delivery(
    sender: str,
    recipient: str,
    text: str,
    delivery_id: str,
    *,
    reply_to: str | None = None,
    expects_reply: bool = True,
):
    return RuntimeDelivery(
        sender,
        recipient,
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=expects_reply,
        reply_to_delivery_id=reply_to,
    )


class _RecordingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, RuntimeDelivery]] = []

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        self.sent.append((recipient, delivery))
        return RuntimeDispatchReceipt("start", f"turn-{len(self.sent)}")


def _evidence(runner: TeamRunner, name: str) -> list[dict[str, object]]:
    path = runner.run.root / "evidence" / f"{name}.jsonl"  # type: ignore[union-attr]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class RetrievalPlanGateTests(unittest.TestCase):
    """Deterministic, zero-model coverage for the start10 defect."""

    root = repository_root()

    def _runner(self, candidate: dict[str, object]) -> tuple[TeamRunner, FormalCandidateProgress, str]:
        progress = FormalCandidateProgress(clock=lambda: 0.0)
        self.assertEqual(
            progress.observe_delivery(
                _delivery("modeling", "protocol", json.dumps(candidate), "delivery-1"),
                modeling_agent_id="modeling",
                protocol_agent_id="protocol",
                run_id="run-1",
                protocol_thread_id="thread-1",
            ),
            "candidate",
        )
        progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
        run_root = Path(tempfile.mkdtemp(prefix="r23008-plan-gate-run-"))
        self.addCleanup(shutil.rmtree, run_root, ignore_errors=True)
        (run_root / "evidence").mkdir()
        runner = TeamRunner(repository_root=self.root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(
            run_id="run-1",
            root=run_root,
            scope={},
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
                profile=SimpleNamespace(
                    profile_id="r2-3-005-modeling-team",
                    agents=[
                        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
                        for role in ("coordinator", "modeling", "protocol", "acceptance")
                    ],
                ),
            ),
        )
        runner.transport = object()
        runner._candidate_progress = progress
        runner._protocol_candidate_responses = {}
        runner._protocol_candidate_receipt_digests = {}
        return runner, progress, "delivery-1"

    def _carrier(self, runner: TeamRunner) -> RunnerAcceptanceCarrier:
        directory = tempfile.mkdtemp(prefix="r23008-plan-gate-carrier-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        carrier = RunnerAcceptanceCarrier(
            Path(directory),
            task_id="r2-3-005-formal-acceptance",
            acceptance_id="acceptance",
            candidate_receipt_builder=runner._build_protocol_candidate_receipt,
            candidate_conflict_builder=runner._build_protocol_candidate_conflict,
        )
        runner.acceptance = carrier
        self.addCleanup(carrier.cleanup)
        return carrier

    def test_illegal_required_paths_return_structured_diagnostic_not_receipt(self) -> None:
        runner, _progress, delivery_id = self._runner(_illegal_candidate())
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        with self.assertRaises(AcceptanceContractError) as raised:
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )
        data = getattr(raised.exception, "data", None)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["reason"], "consumer_query_plan_invalid")
        self.assertIn(
            "workflow-b--currentlyConsumesOutput-->quality-rating-field",
            data["detail"],
        )
        self.assertIn("action", data)
        # No receipt was registered; the marker keeps the typed conflict path
        # available for the revision loop.
        self.assertEqual(
            runner._protocol_candidate_responses, {delivery_id: "receipt_rejected"}
        )

    def test_illegal_plan_diagnostic_reaches_the_agent_as_success_path_ok_false(self) -> None:
        runner, _progress, delivery_id = self._runner(_illegal_candidate())
        carrier = self._carrier(runner)
        response = carrier.capability_endpoint("protocol").handle(
            {
                "id": 7,
                "token": carrier.capability_token("protocol"),
                "method": "tools/call",
                "params": {
                    "name": "protocol_build_candidate_receipt",
                    "arguments": {"protocol_id": "protocol", "delivery_id": delivery_id},
                },
            }
        )
        self.assertNotIn("error", response)
        structured = response["result"]["structuredContent"]
        self.assertIs(structured["ok"], False)
        self.assertEqual(structured["error"]["reason"], "consumer_query_plan_invalid")

    def test_conflict_path_stays_available_after_plan_rejection(self) -> None:
        runner, _progress, delivery_id = self._runner(_illegal_candidate())
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        with self.assertRaises(AcceptanceContractError):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )
        # The Protocol Agent still owns the sanctioned revisable response.
        conflict = carrier.protocol_build_candidate_conflict(
            protocol_id="protocol",
            delivery_id=delivery_id,
            conflict_code="consumer_query_plan_invalid",
            conflict_detail="required_paths must be bare predicate local names",
            capability=token,
        )
        self.assertEqual(conflict["conflict"]["status"], "conflict")

    def test_legal_bare_local_name_candidate_full_chain_is_unchanged(self) -> None:
        runner, progress, delivery_id = self._runner(_legal_candidate())
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        built = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertNotIn("idempotent_replay", built)
        identity = progress.identity
        assert identity is not None
        registered = carrier.register_accepted_candidate(
            candidate_revision=identity.candidate_revision,
            candidate_digest=identity.candidate_digest,
            candidate=progress.candidate,
        )
        self.assertEqual(registered["candidate_revision"], "rev-1")
        # Defect-7 replay behavior is preserved for legal candidates.
        replay = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertIs(replay.get("idempotent_replay"), True)
        self.assertEqual(replay["receipt_json"], built["receipt_json"])

    def test_planless_candidate_is_rejected_pre_receipt_not_post_apply(self) -> None:
        # R2.3-009 start6: a candidate with zero consumer_query items left the
        # gate disabled, the receipt succeeded, revision-1 was applied, and the
        # defect surfaced only at governed retrieval time where no revision
        # channel exists.  The same typed pre-receipt rejection now applies.
        candidate = _legal_candidate()
        candidate["items"] = [  # type: ignore[assignment]
            item for item in candidate["items"] if item.get("item_kind") != "consumer_query"  # type: ignore[union-attr]
        ]
        runner, _progress, delivery_id = self._runner(candidate)
        # Governed retrieval became a mandatory stage in R2.3-008; the 005
        # harness contract keeps its accepted planless-candidate behavior.
        runner.run.configuration.profile.profile_id = "r2-3-009-modeling-team"  # type: ignore[union-attr]
        runner.run.configuration.task.task_id = "r2-3-009-formal-acceptance"  # type: ignore[union-attr]
        runner.run.formal_contract = R2_3_009_CONTRACT  # type: ignore[attr-defined]
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        with self.assertRaises(AcceptanceContractError) as raised:
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )
        data = getattr(raised.exception, "data", None)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["reason"], "consumer_query_plan_invalid")
        self.assertIn("no consumer_query item", data["detail"])
        self.assertEqual(
            runner._protocol_candidate_responses, {delivery_id: "receipt_rejected"}
        )
        # The sanctioned conflict/revision loop stays available, exactly like
        # the start10 illegal-plan rejection.
        conflict = carrier.protocol_build_candidate_conflict(
            protocol_id="protocol",
            delivery_id=delivery_id,
            conflict_code="consumer_query_plan_invalid",
            conflict_detail="candidate must carry at least one consumer_query item",
            capability=token,
        )
        self.assertEqual(conflict["conflict"]["status"], "conflict")

    def test_registration_rejection_after_accepted_receipt_is_typed_feedback(self) -> None:
        # Reproduce the start10 crash path: an exact hand-built receipt bytes
        # bypass the receipt builder, so registration is the first plan check.
        # R2.3-009 A-class: the rejection is typed feedback to Modeling plus a
        # reopen for one strictly newer revision, not a terminal failure.
        runner, progress, delivery_id = self._runner(_illegal_candidate())
        carrier = self._carrier(runner)
        adapter = _RecordingAdapter()
        runner.adapter = adapter
        identity = progress.identity
        assert identity is not None
        receipt = {
            "status": "accepted",
            "candidate_revision": identity.candidate_revision,
            "semantic_digest": identity.semantic_digest,
            "candidate_digest": identity.candidate_digest,
        }
        result = runner._observe_formal_candidate_delivery(
            _delivery(
                "protocol",
                "modeling",
                json.dumps(receipt),
                "receipt-1",
                reply_to=delivery_id,
            )
        )
        self.assertIsNone(result)
        self.assertFalse(progress.terminal_failure_latched)
        self.assertFalse(runner._formal_failure_latched)
        self.assertEqual(progress.state, "awaiting_revision")
        self.assertTrue(progress.pending.receipt_invalidated)  # type: ignore[union-attr]
        self.assertIsNone(carrier._accepted_candidate_identity)
        conflicts = [
            delivery
            for recipient, delivery in adapter.sent
            if recipient == "modeling" and delivery.kind == "candidate-conflict"
        ]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            json.loads(conflicts[0].text)["conflict_code"], "consumer-query-plan-invalid"
        )
        issues = _evidence(runner, "observed-issue")
        self.assertEqual(issues[-1]["code"], "consumer-query-plan-invalid")
        self.assertEqual(issues[-1]["responsible_agent"], "modeling")
        feedback = _evidence(runner, "validation-feedback")
        self.assertTrue(feedback and feedback[-1]["retry_allowed"] is True)
        reopened = _evidence(runner, "formal-candidate-progress")
        self.assertTrue(
            any(entry.get("event") == "registration-rejected-reopened" for entry in reopened)
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
