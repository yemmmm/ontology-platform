"""R2.3-009 A-class: registration rejection reopens for one newer revision.

The start10 defect shape: an illegal consumer_query plan reaches
accepted-candidate registration, where ``ProtocolRetrievalGate`` rejects it.
Under R2.3-009 the rejection is A-class typed feedback — the Runner records
``observed-issue``/``validation-feedback`` evidence, delivers one typed
conflict to the responsible Agent, migrates the complete candidate back to
``awaiting_revision``, and invalidates the acceptance-side registration so the
next strictly newer revision registers through the first-registration path.
Mutation guards that were not part of a reopen stay I-class fatal.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier
from modeling_team.candidate_progress import FormalCandidateProgress
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import RuntimeDelivery, RuntimeDispatchReceipt

from test_r23008_retrieval_plan_gate import _illegal_candidate, _legal_candidate


class _RecordingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, RuntimeDelivery]] = []

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        self.sent.append((recipient, delivery))
        return RuntimeDispatchReceipt("start", f"turn-{len(self.sent)}")


def _delivery(
    sender: str,
    recipient: str,
    text: str,
    delivery_id: str,
    *,
    reply_to: str | None = None,
) -> RuntimeDelivery:
    return RuntimeDelivery(
        sender,
        recipient,
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=True,
        reply_to_delivery_id=reply_to,
    )


def _runner_with_candidate(tmp_base: Path, candidate: dict[str, object]):
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    assert (
        progress.observe_delivery(
            _delivery("modeling", "protocol", json.dumps(candidate), "delivery-1"),
            modeling_agent_id="modeling",
            protocol_agent_id="protocol",
            run_id="run-1",
            protocol_thread_id="thread-1",
        )
        == "candidate"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    run_root = tmp_base / "run"
    (run_root / "evidence").mkdir(parents=True)
    adapter = _RecordingAdapter()
    runner = TeamRunner(repository_root=tmp_base, adapter=adapter)
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
    runner._candidate_progress = progress
    runner._protocol_candidate_responses = {}
    runner._protocol_candidate_receipt_digests = {}
    carrier = RunnerAcceptanceCarrier(
        tmp_base / "carrier",
        task_id="r2-3-005-formal-acceptance",
        acceptance_id="acceptance",
        candidate_receipt_builder=runner._build_protocol_candidate_receipt,
        candidate_conflict_builder=runner._build_protocol_candidate_conflict,
    )
    runner.acceptance = carrier
    return runner, progress, carrier, adapter


def _evidence(runner: TeamRunner, name: str) -> list[dict[str, object]]:
    path = runner.run.root / "evidence" / f"{name}.jsonl"  # type: ignore[union-attr]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _accepted_receipt_delivery(
    progress: FormalCandidateProgress, delivery_id: str, *, reply_to: str = "delivery-1"
):
    identity = progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    return _delivery(
        "protocol", "modeling", json.dumps(receipt), delivery_id, reply_to=reply_to
    )


def test_rejected_registration_reopens_and_next_revision_registers(tmp_path: Path) -> None:
    directory = Path(tempfile.mkdtemp(prefix="r23009-a-class-"))
    try:
        runner, progress, carrier, adapter = _runner_with_candidate(directory, _illegal_candidate())
        # The receipt observation completes the gate, then registration rejects
        # the illegal consumer_query plan (the start10 crash point).
        result = runner._observe_formal_candidate_delivery(
            _accepted_receipt_delivery(progress, "receipt-1")
        )
        assert result is None
        assert runner._formal_failure_latched is False
        assert progress.terminal_failure_latched is False
        assert progress.state == "awaiting_revision"
        assert carrier._accepted_candidate_identity is None

        conflicts = [
            delivery
            for recipient, delivery in adapter.sent
            if recipient == "modeling" and delivery.kind == "candidate-conflict"
        ]
        assert len(conflicts) == 1
        notice = json.loads(conflicts[0].text)
        assert notice["conflict_code"] == "consumer-query-plan-invalid"
        assert notice["remediation"]

        issues = _evidence(runner, "observed-issue")
        assert issues[-1]["issue_class"] == "A"
        assert issues[-1]["code"] == "consumer-query-plan-invalid"
        assert issues[-1]["responsible_agent"] == "modeling"
        feedback = _evidence(runner, "validation-feedback")
        assert feedback[-1]["issue_class"] == "A"
        assert feedback[-1]["responsible_agent"] == "modeling"
        assert feedback[-1]["retry_allowed"] is True
        assert any(
            entry.get("event") == "registration-rejected-reopened"
            for entry in _evidence(runner, "formal-candidate-progress")
        )

        # The self-repair loop: a strictly newer standalone revision with a
        # legal plan re-enters the revision gates, and Protocol's accepted
        # receipt for it registers cleanly through the first-registration path.
        repaired = _legal_candidate()
        repaired["candidate_revision"] = "rev-2"
        assert (
            runner._observe_formal_candidate_delivery(
                _delivery("modeling", "protocol", json.dumps(repaired), "delivery-2")
            )
            == "revision"
        )
        assert progress.state == "awaiting_receipt"
        assert (
            runner._observe_formal_candidate_delivery(
                _accepted_receipt_delivery(progress, "receipt-3", reply_to="delivery-2")
            )
            == "accepted"
        )
        assert progress.state == "complete"
        identity = carrier._accepted_candidate_identity
        assert identity is not None
        assert identity["candidate_revision"] == "rev-2"
        assert carrier._accepted_candidate is not None
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_stale_receipt_after_reopen_is_ignored_not_recompleted(tmp_path: Path) -> None:
    directory = Path(tempfile.mkdtemp(prefix="r23009-a-class-stale-"))
    try:
        runner, progress, _carrier, _adapter = _runner_with_candidate(directory, _illegal_candidate())
        runner._observe_formal_candidate_delivery(
            _accepted_receipt_delivery(progress, "receipt-1")
        )
        assert progress.state == "awaiting_revision"
        # The same (now invalidated) receipt must not re-complete the gate.
        assert (
            runner._observe_formal_candidate_delivery(
                _accepted_receipt_delivery(progress, "receipt-2")
            )
            is None
        )
        assert progress.state == "awaiting_revision"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_identity_payload_mutation_without_reopen_stays_fatal(tmp_path: Path) -> None:
    directory = Path(tempfile.mkdtemp(prefix="r23009-a-class-mutation-"))
    try:
        runner, progress, carrier, _adapter = _runner_with_candidate(directory, _legal_candidate())
        assert (
            runner._observe_formal_candidate_delivery(
                _accepted_receipt_delivery(progress, "receipt-1")
            )
            == "accepted"
        )
        assert carrier._accepted_candidate_identity is not None
        # Same identity, different payload bytes: the I-class mutation guard,
        # opaque (no typed payload) so the Runner classifies it fatal.
        with pytest.raises(AcceptanceContractError, match="semantic payload was mutated") as raised:
            carrier.register_accepted_candidate(
                candidate_revision=progress.identity.candidate_revision,  # type: ignore[union-attr]
                candidate_digest=progress.identity.candidate_digest,  # type: ignore[union-attr]
                candidate={"mutated": True},
            )
        assert raised.value.data is None
        assert runner._classify_registration_rejection(raised.value) is None
    finally:
        shutil.rmtree(directory, ignore_errors=True)
