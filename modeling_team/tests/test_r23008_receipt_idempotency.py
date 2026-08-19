"""R2.3-008 start9: repeat typed receipt requests replay instead of rejecting.

In start9 the Protocol Agent built the canonical receipt, its first
hand-written reply was quarantined, and after the redrive its repeat
``protocol_build_candidate_receipt`` call failed with an opaque -32001
("typed candidate response was already built").  The Agent escalated a
cooperative issue instead of delivering the receipt it already held, and the
run died as ``candidate-redrive-exhausted``.

The receipt builder is now idempotent for the same still-answerable candidate
(awaiting_receipt/redrive_sent, same delivery_id): the repeat returns the
identical canonical receipt rebuilt deterministically from Runner-retained
state, verified against the registered digest.  Refusals after a conflict, for
terminal progress, and the R2.3-003 post-receipt conflict path are unchanged.
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


def _candidate(revision: object = "rev-1") -> dict[str, object]:
    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": revision,
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


def _r23003_candidate() -> dict[str, object]:
    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": 1,
        "scope": "retained",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "predicate-field",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "field",
                    "predicate_kind": "fact",
                    "range": "string",
                },
            },
            {
                "item_id": "delete-a",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-cross-release-output-meaning",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
            {
                "item_id": "delete-b",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-b-no-score-behavior",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
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


class ReceiptIdempotencyTests(unittest.TestCase):
    """Deterministic, zero-model coverage for the start9 defect."""

    root = repository_root()

    def _runner(
        self,
        candidate: dict[str, object],
        *,
        profile_id: str = "r2-3-005-modeling-team",
        task_id: str = "r2-3-005-formal-acceptance",
        integer_revisions: bool = False,
    ) -> tuple[TeamRunner, FormalCandidateProgress, str]:
        progress = FormalCandidateProgress(
            clock=lambda: 0.0,
            allow_post_receipt_revision=integer_revisions,
            integer_revisions=integer_revisions,
        )
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
            scope={"workspace_version": "v1"},
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id=task_id),
                profile=SimpleNamespace(
                    profile_id=profile_id,
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

    def _carrier(self, runner: TeamRunner, *, task_id: str) -> RunnerAcceptanceCarrier:
        directory = tempfile.mkdtemp(prefix="r23008-receipt-idempotency-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        carrier = RunnerAcceptanceCarrier(
            Path(directory),
            task_id=task_id,
            acceptance_id="acceptance",
            candidate_receipt_builder=runner._build_protocol_candidate_receipt,
            candidate_conflict_builder=runner._build_protocol_candidate_conflict,
        )
        runner.acceptance = carrier
        self.addCleanup(carrier.cleanup)
        return carrier

    def test_first_build_then_repeat_replays_identical_receipt(self) -> None:
        runner, progress, delivery_id = self._runner(_candidate())
        carrier = self._carrier(runner, task_id="r2-3-005-formal-acceptance")
        token = carrier.capability_token("protocol")
        first = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertNotIn("idempotent_replay", first)
        # The start9 sequence: the Agent retries the same capability call.
        second = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertIs(second.get("idempotent_replay"), True)
        self.assertEqual(second["receipt"], first["receipt"])
        self.assertEqual(second["receipt_json"], first["receipt_json"])
        self.assertEqual(second["candidate"], first["candidate"])
        self.assertFalse(progress.terminal_failure_latched)

    def test_repeat_in_redrive_sent_state_replays_receipt(self) -> None:
        runner, progress, delivery_id = self._runner(_candidate())
        carrier = self._carrier(runner, task_id="r2-3-005-formal-acceptance")
        token = carrier.capability_token("protocol")
        first = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        # The quarantined-reply transition the redrive turn reopens.
        progress.pending.state = "redrive_sent"  # type: ignore[union-attr]
        second = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertIs(second.get("idempotent_replay"), True)
        self.assertEqual(second["receipt_json"], first["receipt_json"])

    def test_repeat_receipt_after_conflict_is_still_rejected(self) -> None:
        runner, _progress, delivery_id = self._runner(_candidate())
        carrier = self._carrier(runner, task_id="r2-3-005-formal-acceptance")
        token = carrier.capability_token("protocol")
        carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        carrier.protocol_build_candidate_conflict(
            protocol_id="protocol",
            delivery_id=delivery_id,
            conflict_code="missing_label",
            conflict_detail="label requires a source-grounded value",
            capability=token,
        )
        with self.assertRaisesRegex(TeamConfigurationError, "already built"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )

    def test_repeat_receipt_after_terminal_progress_is_still_rejected(self) -> None:
        runner, progress, delivery_id = self._runner(_candidate())
        carrier = self._carrier(runner, task_id="r2-3-005-formal-acceptance")
        token = carrier.capability_token("protocol")
        carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        progress.mark_terminal_failure()
        with self.assertRaisesRegex(TeamConfigurationError, "terminal"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )

    def test_r23003_receipt_replay_keeps_integer_revision_and_conflict_guards(self) -> None:
        runner, progress, delivery_id = self._runner(
            _r23003_candidate(),
            profile_id="r2-3-003-modeling-team",
            task_id="r2-3-003-existing-scope-incremental",
            integer_revisions=True,
        )
        carrier = self._carrier(runner, task_id="r2-3-003-existing-scope-incremental")
        token = carrier.capability_token("protocol")
        first = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertEqual(first["receipt"]["candidate_revision"], 1)
        second = carrier.protocol_build_candidate_receipt(
            protocol_id="protocol", delivery_id=delivery_id, capability=token
        )
        self.assertIs(second.get("idempotent_replay"), True)
        self.assertEqual(second["receipt_json"], first["receipt_json"])
        self.assertEqual(second["receipt"]["candidate_revision"], 1)
        # The R2.3-003 post-receipt zero-mutation conflict path stays available.
        progress.pending.state = "complete"  # type: ignore[union-attr]
        conflict = carrier.protocol_build_candidate_conflict(
            protocol_id="protocol",
            delivery_id=delivery_id,
            conflict_code="post_receipt_context_drift",
            conflict_detail="workspace version drifted",
            capability=token,
        )
        self.assertEqual(conflict["conflict"]["status"], "conflict")
        # After the post-receipt conflict, a receipt request is refused again
        # (state is complete and invalidated, so the replay path is closed).
        with self.assertRaisesRegex(TeamConfigurationError, "already built|not awaiting"):
            carrier.protocol_build_candidate_receipt(
                protocol_id="protocol", delivery_id=delivery_id, capability=token
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
