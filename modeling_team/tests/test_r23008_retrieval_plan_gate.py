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
2. Registration failures at the accepted-receipt observation are latched as a
   typed ``platform-contract`` terminal failure instead of an unclassified
   exception.

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
from modeling_team.contracts import TeamConfigurationError, repository_root
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

    def test_registration_rejection_after_accepted_receipt_is_typed_terminal(self) -> None:
        # Reproduce the start10 crash path: an exact hand-built receipt bytes
        # bypass the receipt builder, so registration is the first plan check.
        runner, progress, delivery_id = self._runner(_illegal_candidate())
        self._carrier(runner)
        identity = progress.identity
        assert identity is not None
        receipt = {
            "status": "accepted",
            "candidate_revision": identity.candidate_revision,
            "semantic_digest": identity.semantic_digest,
            "candidate_digest": identity.candidate_digest,
        }
        with self.assertRaisesRegex(
            TeamConfigurationError, "accepted candidate registration failed"
        ) as raised:
            runner._observe_formal_candidate_delivery(
                _delivery(
                    "protocol",
                    "modeling",
                    json.dumps(receipt),
                    "receipt-1",
                    reply_to=delivery_id,
                )
            )
        self.assertIsInstance(raised.exception.__cause__, AcceptanceContractError)
        self.assertTrue(progress.terminal_failure_latched)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
