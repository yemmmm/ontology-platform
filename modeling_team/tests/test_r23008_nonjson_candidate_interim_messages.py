"""R2.3-008 start12: non-JSON Modeling->Protocol text must not fail the run.

In start12 the Modeling Agent was still waiting for the owner answers to its
two clarification questions when Protocol's startup barrier requested the
candidate (delivery-6).  Modeling answered the barrier with a prose status
message — ``send_team_message(recipient_id="protocol", expects_reply=true,
text="Modeling clarification is pending from Coordinator ... I will freeze and
send the complete candidate after ...")``.  ``observe_delivery`` treated any
Modeling->Protocol expects-reply/no-reply_to delivery as the initial
candidate, so the prose failed JSON decoding and killed the whole run three
minutes in, classified modeling-quality, before the owner answers were even
delivered.

Parsing belongs to the tool layer, not to modeling quality: an interim
non-candidate message on the candidate channel must be ignored exactly like
JSON that is not candidate-shaped.  The startup barrier/redrive keeps
requesting the candidate, the conflict slot stays open for a proper revision,
and the dispatch deadline still bounds the wait.
"""

from __future__ import annotations

import json

from modeling_team.candidate_progress import FormalCandidateProgress
from modeling_team.protocol_mechanics import build_candidate_conflict
from modeling_team.runtimes.base import RuntimeDispatchReceipt

from test_r23005_candidate_progress import _candidate, _delivery


_START12_PROSE = (
    "Modeling clarification is pending from Coordinator on two material gaps: "
    "whether B's currently consumed published C output is confirmed as Version 2 "
    "quality_rating, and B's behavior when C returns no numeric score. I will "
    "freeze and send the complete candidate after incorporating the received "
    "answer(s)."
)


def _observe(progress, delivery):
    return progress.observe_delivery(
        delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    )


def test_prose_on_initial_candidate_slot_is_ignored_not_fatal() -> None:
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    assert _observe(progress, _delivery("modeling", "protocol", _START12_PROSE, "d0")) is None
    assert progress.pending is None and progress.identity is None
    # The later real candidate still registers as the initial candidate.
    assert _observe(
        progress, _delivery("modeling", "protocol", json.dumps(_candidate()), "d1")
    ) == "candidate"
    assert progress.identity is not None
    assert progress.identity.original_delivery_id == "d1"


def test_prose_reply_to_conflict_keeps_revision_slot_open() -> None:
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    candidate = _candidate()
    assert _observe(
        progress, _delivery("modeling", "protocol", json.dumps(candidate), "d1")
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    conflict = build_candidate_conflict(candidate, "unsupported", "relation is not declared")
    assert _observe(
        progress, _delivery("protocol", "modeling", json.dumps(conflict), "c1", reply_to="d1")
    ) == "conflict"
    assert progress.state == "awaiting_revision"
    # An interim prose reply does not consume or corrupt the revision slot.
    assert _observe(
        progress, _delivery("modeling", "protocol", _START12_PROSE, "d2", reply_to="c1")
    ) is None
    assert progress.state == "awaiting_revision"
    # The proper complete revision is still accepted on the same conflict slot.
    assert _observe(
        progress,
        _delivery("modeling", "protocol", json.dumps(_candidate("rev-2")), "d3", reply_to="c1"),
    ) == "revision"


def test_non_object_json_on_initial_slot_is_also_interim() -> None:
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    # A bare JSON string/number decodes to a non-dict and must be ignored the
    # same way as prose; only a candidate-shaped object registers.
    assert _observe(progress, _delivery("modeling", "protocol", '"status update"', "d0")) is None
    assert _observe(progress, _delivery("modeling", "protocol", "42", "d0b")) is None
    assert _observe(
        progress, _delivery("modeling", "protocol", json.dumps(_candidate()), "d1")
    ) == "candidate"
