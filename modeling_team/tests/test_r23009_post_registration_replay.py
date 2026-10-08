"""R2.3-009 start1: post-registration retained-candidate re-fetch via receipt replay.

In the start1 live run the Protocol Agent built and registered the canonical
receipt, then lost reliable access to the exact retained candidate for the
platform translation stage (``translate_candidate_to_batches``).  Its second
``protocol_build_candidate_receipt`` call failed with an opaque -32001
("typed candidate is not awaiting a Protocol response") because progress was
already ``complete``, and the Agent correctly refused to transcribe the
candidate from transcript text, escalating the gap instead of mutating with a
drifted plan.

The authorized re-fetch is now a read-only replay: when progress is complete
and the registered response for that delivery is a receipt, the repeat receipt
call returns the retained candidate and byte-identical receipt
(``idempotent_replay``) without reopening any Team Transport reply slot.
Rejections after a conflict, terminal progress, and foreign IDs are unchanged.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.candidate_progress import (
    FORMAL_CANDIDATE_KIND,
    FormalCandidateProgress,
)
from modeling_team.contracts import TeamConfigurationError, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt


def _candidate() -> dict[str, object]:
    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": "rev-1",
        "scope": "new",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "class-1",
                "item_kind": "class",
                "semantic": {"label": "Example"},
            }
        ],
    }


def _delivery(text: str, delivery_id: str = "delivery-1") -> RuntimeDelivery:
    return RuntimeDelivery(
        "modeling",
        "protocol",
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=True,
        reply_to_delivery_id=None,
    )


class PostRegistrationReplayTests(unittest.TestCase):
    """Deterministic, zero-model coverage for the start1 defect."""

    root = repository_root()

    def _runner(self) -> tuple[TeamRunner, FormalCandidateProgress, str]:
        candidate = _candidate()
        progress = FormalCandidateProgress(clock=lambda: 0.0)
        self.assertEqual(
            progress.observe_delivery(
                _delivery(json.dumps(candidate), "delivery-1"),
                modeling_agent_id="modeling",
                protocol_agent_id="protocol",
                run_id="run-1",
                protocol_thread_id="thread-1",
            ),
            "candidate",
        )
        progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
        runner = TeamRunner(repository_root=self.root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(
            run_id="run-1",
            scope={"model_revision": 1},
            configuration=SimpleNamespace(
                task=SimpleNamespace(
                    schema_version=2, task_id="r2-3-005-formal-acceptance"
                ),
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
        directory = tempfile.mkdtemp(prefix="r23009-post-registration-replay-")
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

    def test_post_registration_replay_returns_retained_candidate_read_only(self) -> None:
        runner, progress, delivery_id = self._runner()
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        first = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        # The start1 sequence: the receipt was sent and registered, moving the
        # formal candidate progress to complete before translation started.
        progress.pending.state = "complete"  # type: ignore[union-attr]
        second = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertIs(second.get("idempotent_replay"), True)
        self.assertEqual(second["receipt"], first["receipt"])
        self.assertEqual(second["receipt_json"], first["receipt_json"])
        self.assertEqual(second["candidate"], first["candidate"])
        # The replay never reopened the reply slot or the response binding.
        self.assertEqual(runner._protocol_candidate_responses[delivery_id], "receipt")
        self.assertFalse(progress.terminal_failure_latched)

    def test_replay_after_post_receipt_conflict_is_still_rejected(self) -> None:
        runner, progress, delivery_id = self._runner()
        progress._allow_post_receipt_revision = True
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        progress.pending.state = "complete"  # type: ignore[union-attr]
        conflict = carrier.protocol_build_candidate_conflict(
            protocol_id="protocol",
            delivery_id=delivery_id,
            conflict_code="post_receipt_context_drift",
            conflict_detail="workspace version drifted",
            capability=token,
        )
        self.assertEqual(conflict["conflict"]["status"], "conflict")
        with self.assertRaisesRegex(TeamConfigurationError, "already built|not awaiting"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )

    def test_replay_after_terminal_failure_is_still_rejected(self) -> None:
        runner, progress, delivery_id = self._runner()
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        progress.pending.state = "complete"  # type: ignore[union-attr]
        progress.mark_terminal_failure()
        with self.assertRaisesRegex(TeamConfigurationError, "terminal"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )

    def test_complete_state_without_prior_receipt_is_still_rejected(self) -> None:
        runner, progress, delivery_id = self._runner()
        carrier = self._carrier(runner)
        token = carrier.capability_token("protocol")
        progress.pending.state = "complete"  # type: ignore[union-attr]
        with self.assertRaisesRegex(TeamConfigurationError, "not awaiting"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
