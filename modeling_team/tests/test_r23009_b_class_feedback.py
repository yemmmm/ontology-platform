"""R2.3-009 B-class: candidate-channel protocol violations become typed feedback.

A revision that is not strictly newer, a revision that reuses the invalidated
candidate digest, a malformed candidate envelope, and a rejected one-shot reply
slot reopen used to kill the whole run through the formal candidate failure
latch.  Under R2.3-009 B-class these sites instead (1) persist the offending
delivery to evidence, (2) record an ``observed-issue`` event, (3) deliver a
typed readable conflict to the responsible Agent through the Runner channel,
and (4) leave the run alive waiting for a compliant delivery.  The gates
themselves keep rejecting the delivery; only the run-kill becomes feedback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modeling_team.protocol_mechanics import build_candidate_conflict
from modeling_team.runtimes.base import AgentState

from test_r23005_candidate_progress import (
    _FormalProgressAdapter,
    _candidate,
    _formal_progress_runner,
)


def _evidence(runner: Any, name: str) -> list[dict[str, Any]]:
    path = runner.run.root / "evidence" / f"{name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _conflict_deliveries(adapter: _FormalProgressAdapter, recipient: str) -> list[Any]:
    return [
        delivery
        for addressee, delivery in adapter.sent
        if addressee == recipient and delivery.kind == "candidate-conflict"
    ]


def test_revision_not_newer_is_typed_feedback_and_run_continues(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()
    conflict = build_candidate_conflict(_candidate(), "unsupported", "relation is not declared")
    conflict_delivery = runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(conflict),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    progress = runner._candidate_progress
    assert progress is not None and progress.pending is not None
    assert progress.pending.state == "awaiting_revision"

    stale_text = json.dumps(_candidate())  # same revision and same digest
    violating = runner.transport.send(
        "modeling",
        "protocol",
        stale_text,
        expects_reply=True,
        reply_to_delivery_id=conflict_delivery.delivery_id,
    )
    runner.drain()  # must not raise TeamConfigurationError

    assert runner._formal_failure_latched is False
    assert progress.pending.state == "awaiting_revision"

    issues = _evidence(runner, "observed-issue")
    assert issues, "the violation must be recorded as an observed issue"
    assert issues[-1]["code"] == "revision-not-strictly-newer"
    assert issues[-1]["issue_class"] == "B"
    assert issues[-1]["responsible_agent"] == "modeling"
    assert issues[-1]["original_text"] == stale_text
    assert issues[-1]["original_delivery_id"] == violating.delivery_id

    # The original delivery bytes are preserved before the judgment.
    deliveries = _evidence(runner, "deliveries")
    assert any(entry.get("text") == stale_text for entry in deliveries)

    conflicts = _conflict_deliveries(adapter, "modeling")
    assert conflicts, "Modeling must receive one typed conflict delivery"
    notice = json.loads(conflicts[-1].text)
    assert notice["conflict_code"] == "revision-not-strictly-newer"
    assert notice["original_delivery_id"] == violating.delivery_id
    assert notice["remediation"]

    feedback = [
        entry
        for entry in _evidence(runner, "validation-feedback")
        if entry.get("kind") == "candidate-conflict"
    ]
    assert feedback
    assert feedback[-1]["responsible_agent"] == "modeling"
    assert feedback[-1]["code"] == "revision-not-strictly-newer"
    assert feedback[-1]["channel"] == 2


def test_violation_code_mapping_covers_the_typed_gate_messages(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    from modeling_team.candidate_progress import FormalCandidateError

    mapping = (
        ("formal candidate revision is not strictly newer than the invalidated receipt",
         "revision-not-strictly-newer"),
        ("formal candidate revision reuses the invalidated candidate digest",
         "revision-digest-reused"),
        ("formal candidate Runtime attribution is invalid", "candidate-attribution-invalid"),
        ("formal candidate delivery ID is not bound", "candidate-delivery-id-not-bound"),
    )
    for message, code in mapping:
        assert runner._formal_candidate_violation_code(FormalCandidateError(message)) == code
    assert (
        runner._formal_candidate_violation_code(FormalCandidateError("formal candidate fields are not exact"))
        == "candidate-envelope-invalid"
    )


class _RedriveNeverCompletesAdapter(_FormalProgressAdapter):
    """The dispatched protocol turn never completes, so the redrive stays open.

    Without this the run reaches the (still-fatal, pre-R2.3-009-step-4)
    redrive-exhausted latch before the second invalid response is delivered.
    """

    def get_agent_states(self):
        started, _ = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, None)]


def test_rejected_reply_slot_reopen_is_typed_feedback_to_protocol(tmp_path: Path) -> None:
    adapter = _RedriveNeverCompletesAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()

    # First invalid bound response consumes the one-shot reopen.
    runner.transport.send(
        "protocol",
        "modeling",
        "not a receipt",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()

    # The reopen slot is already consumed, so the second invalid response is
    # rejected by the reopen gate: B-class feedback to Protocol, not a kill.
    second = runner.transport.send(
        "protocol",
        "modeling",
        "still not a receipt",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()  # must not raise

    assert runner._formal_failure_latched is False
    issues = _evidence(runner, "observed-issue")
    assert issues[-1]["code"] == "formal-reply-slot-reopen-rejected"
    assert issues[-1]["responsible_agent"] == "protocol"
    assert issues[-1]["original_delivery_id"] == second.delivery_id
    assert issues[-1]["original_text"] == "still not a receipt"

    conflicts = _conflict_deliveries(adapter, "protocol")
    assert conflicts, "Protocol must receive one typed conflict delivery"
    notice = json.loads(conflicts[-1].text)
    assert notice["conflict_code"] == "formal-reply-slot-reopen-rejected"
    assert notice["remediation"]

    feedback = _evidence(runner, "validation-feedback")
    assert any(
        entry.get("responsible_agent") == "protocol"
        and entry.get("code") == "formal-reply-slot-reopen-rejected"
        for entry in feedback
    )


def test_malformed_candidate_envelope_is_feedback_with_default_code(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)

    # Candidate-shaped initial delivery with an invalid revision label: the
    # envelope validator inside observe_delivery rejects it, which used to be
    # the ``candidate-envelope-invalid`` run kill.
    malformed = dict(_candidate())
    malformed["candidate_revision"] = 17
    malformed_text = json.dumps(malformed)
    violating = runner.transport.send(
        "modeling", "protocol", malformed_text, expects_reply=True
    )
    runner.drain()  # must not raise

    assert runner._formal_failure_latched is False
    issues = _evidence(runner, "observed-issue")
    assert issues[-1]["code"] == "candidate-envelope-invalid"
    assert issues[-1]["responsible_agent"] == "modeling"
    assert issues[-1]["original_delivery_id"] == violating.delivery_id
    assert issues[-1]["original_text"] == malformed_text
    conflicts = _conflict_deliveries(adapter, "modeling")
    assert conflicts
    assert json.loads(conflicts[-1].text)["conflict_code"] == "candidate-envelope-invalid"
