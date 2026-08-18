"""R2.3-008: the candidate revision type contract is unified end to end.

Before this fix the neutral envelope accepted a positive integer revision for
every task while ``register_accepted_candidate`` demanded a safe stable string
identifier for everything except R2.3-003.  A Modeling Agent choosing an
integer therefore passed the envelope and the acceptance gate, then killed the
complete run inside registration.  The task-aware gate in
``FormalCandidateProgress`` now rejects non-safe-string revisions at the first
delivery with a typed, correctable ``FormalCandidateError``; R2.3-003 keeps the
historical positive-integer sequence unchanged.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier
from modeling_team.candidate_progress import (
    FORMAL_CANDIDATE_KIND,
    FormalCandidateError,
    FormalCandidateProgress,
    validate_formal_candidate,
)
from modeling_team.runtimes.base import RuntimeDelivery


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


def _delivery(text: str, delivery_id: str = "d1") -> RuntimeDelivery:
    return RuntimeDelivery(
        "modeling",
        "protocol",
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=True,
        reply_to_delivery_id=None,
    )


def _observe(progress: FormalCandidateProgress, candidate: dict[str, object]) -> str | None:
    return progress.observe_delivery(
        _delivery(json.dumps(candidate)),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    )


class RevisionTypeContractTests(unittest.TestCase):
    def test_task_agnostic_neutral_envelope_still_accepts_integer_revisions(self) -> None:
        """The pure protocol validator has no task context and stays permissive."""

        self.assertEqual(validate_formal_candidate(_candidate(1))["candidate_revision"], 1)

    def test_integer_revision_for_non_003_is_rejected_at_first_delivery(self) -> None:
        progress = FormalCandidateProgress(clock=lambda: 0.0)
        with self.assertRaises(FormalCandidateError) as raised:
            _observe(progress, _candidate(1))
        self.assertIn("[a-z][a-z0-9-]{1,127}", str(raised.exception))
        self.assertIn("R2.3-003", str(raised.exception))
        # Nothing was latched as pending: the Agent can correct and redeliver.
        self.assertIsNone(progress.pending)

    def test_unsafe_string_revisions_for_non_003_are_rejected(self) -> None:
        for revision in ("Rev-1", "rev 1", "", "1", "rev_1", None, [], 0, -1):
            with self.subTest(revision=revision):
                with self.assertRaises(FormalCandidateError):
                    _observe(FormalCandidateProgress(clock=lambda: 0.0), _candidate(revision))

    def test_safe_string_revisions_are_accepted_end_to_end_into_registration(self) -> None:
        progress = FormalCandidateProgress(clock=lambda: 0.0)
        self.assertEqual(_observe(progress, _candidate("rev-1")), "candidate")
        identity = progress.identity
        assert identity is not None
        self.assertEqual(identity.candidate_revision, "rev-1")
        # Registration accepts exactly the same revision the envelope accepted.
        with tempfile.TemporaryDirectory(prefix="r23008-revision-") as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "r23008",
                task_id="r2-3-005-new-scope-greenfield",
                acceptance_id="acceptance",
            )
            registered = carrier.register_accepted_candidate(
                candidate_revision=identity.candidate_revision,
                candidate_digest=identity.candidate_digest,
            )
        self.assertEqual(registered["candidate_revision"], "rev-1")

    def test_r2_3_003_integer_revisions_pass_the_flagged_gate(self) -> None:
        progress = FormalCandidateProgress(
            clock=lambda: 0.0,
            allow_post_receipt_revision=True,
            integer_revisions=True,
        )
        self.assertEqual(_observe(progress, _candidate(1)), "candidate")
        self.assertEqual(progress.identity.candidate_revision, 1)

    def test_registration_rejects_integer_revisions_for_non_003(self) -> None:
        # The registration-side rule is unchanged; the envelope now agrees.
        with tempfile.TemporaryDirectory(prefix="r23008-revision-invalid-") as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "r23008",
                task_id="r2-3-005-new-scope-greenfield",
                acceptance_id="acceptance",
            )
            with self.assertRaises(AcceptanceContractError) as raised:
                carrier.register_accepted_candidate(
                    candidate_revision=1,
                    candidate_digest="a" * 64,
                )
        self.assertIn("safe stable identifier", str(raised.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
