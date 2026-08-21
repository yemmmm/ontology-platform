from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.candidate_progress import (
    FORMAL_CANDIDATE_KIND,
    FormalCandidateError,
    FormalCandidateProgress,
    canonical_digest,
    formal_candidate_digests,
)
from modeling_team.candidate_platform_gate import (
    CANDIDATE_RECEIPT_REGISTERED_KIND,
    CandidatePlatformGate,
)
from modeling_team.contracts import TeamConfigurationError, load_profile, repository_root
from modeling_team.interventions import IssueResolution
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_conflict,
    build_candidate_receipt,
    build_existing_scope_candidate_conflict,
)
from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker
from modeling_team.runtimes.base import AgentState, RuntimeDelivery, RuntimeDispatchReceipt


def _candidate(revision: object = "rev-1") -> dict[str, object]:
    return {
        "candidate_kind": FORMAL_CANDIDATE_KIND,
        "candidate_revision": revision,
        "scope": "dify-workflow",
        "constraints": ["preserve explicit unknowns"],
        "items": [
            {
                "item_id": "workflow-1",
                "item_kind": "entity",
                "semantic": {"label": "Workflow"},
                "evidence_citations": [{"document": "tools.mdx"}],
            }
        ],
    }


def _delivery(sender: str, recipient: str, text: str, delivery_id: str, *, reply_to: str | None = None) -> RuntimeDelivery:
    return RuntimeDelivery(
        sender,
        recipient,
        "peer",
        text,
        delivery_id=delivery_id,
        expects_reply=True,
        reply_to_delivery_id=reply_to,
    )


def _progress(clock):
    return FormalCandidateProgress(clock=clock)


def _formal_profile_with_timeout(tmp_path: Path, value: str) -> Path:
    source = repository_root() / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
    content = source.read_text(encoding="utf-8").replace(
        "  candidate_progress_timeout_seconds: 300\n",
        f"  candidate_progress_timeout_seconds: {value}\n",
    )
    path = tmp_path / "formal-profile.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_formal_profile_timeout_is_loaded_from_the_profile_parameters(tmp_path: Path) -> None:
    profile = load_profile(_formal_profile_with_timeout(tmp_path, "300"), strict=True)
    assert profile.parameters["candidate_progress_timeout_seconds"] == 300


def test_missing_timeout_keeps_the_120_second_default_for_formal_and_nonformal_profiles(
    tmp_path: Path,
) -> None:
    formal_source = repository_root() / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
    formal_without_timeout = tmp_path / "formal-without-timeout.yaml"
    formal_without_timeout.write_text(
        formal_source.read_text(encoding="utf-8").replace(
            "  candidate_progress_timeout_seconds: 300\n", ""
        ),
        encoding="utf-8",
    )
    formal = load_profile(formal_without_timeout, strict=True)
    nonformal = load_profile(repository_root() / "modeling_team/profiles/base-three-agent.yaml")
    assert formal.parameters.get("candidate_progress_timeout_seconds", 120.0) == 120.0
    assert nonformal.parameters.get("candidate_progress_timeout_seconds", 120.0) == 120.0


@pytest.mark.parametrize("value", ["true", "not-a-number", ".nan", ".inf", "0", "-1", "601"])
def test_formal_profile_timeout_rejects_malformed_or_out_of_range_values(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(TeamConfigurationError, match="candidate progress timeout"):
        load_profile(_formal_profile_with_timeout(tmp_path, value), strict=True)


def test_nonformal_profile_cannot_configure_formal_candidate_timeout(tmp_path: Path) -> None:
    source = repository_root() / "modeling_team/profiles/base-three-agent.yaml"
    path = tmp_path / "nonformal-profile.yaml"
    path.write_text(
        source.read_text(encoding="utf-8").replace(
            "parameters: {}\n",
            "parameters:\n  candidate_progress_timeout_seconds: 300\n",
        ),
        encoding="utf-8",
    )
    with pytest.raises(TeamConfigurationError, match="restricted to the formal Profile"):
        load_profile(path)


def test_conflict_builder_binds_complete_formal_candidate() -> None:
    value = build_candidate_conflict(_candidate(), "missing_label", "label is required")
    assert set(value) == {
        "status",
        "candidate_revision",
        "semantic_digest",
        "candidate_digest",
        "conflict_code",
        "conflict_detail",
    }
    assert value["status"] == "conflict"
    assert value["candidate_revision"] == "rev-1"

    malformed = dict(_candidate())
    malformed["unexpected"] = True
    with pytest.raises(ProtocolRetrievalFallbackError):
        build_candidate_conflict(malformed, "invalid", "must fail")


def test_formal_progress_accepts_only_exact_bound_receipt() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    candidate = _candidate()
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    invalid = _delivery(
        "protocol",
        "modeling",
        json.dumps({"status": "accepted", "candidate_revision": 1}),
        "r1",
        reply_to="d1",
    )
    assert progress.observe_delivery(
        invalid,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) is None
    assert progress.state == "awaiting_receipt"
    identity = progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "r2", reply_to="d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "accepted"
    assert progress.state == "complete"


def test_conflict_requires_full_revision_and_rebinds_pending_identity() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    candidate = _candidate()
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    identity = progress.identity
    assert identity is not None
    conflict = build_candidate_conflict(candidate, "unsupported", "relation is not declared")
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(conflict), "c1", reply_to="d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "conflict"
    assert progress.state == "awaiting_revision"
    revised = _candidate("rev-2")
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(revised), "d2", reply_to="c1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "revision"
    assert progress.identity is not None and progress.identity.original_delivery_id == "d2"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    revised_identity = progress.identity
    assert revised_identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": revised_identity.candidate_revision,
        "semantic_digest": revised_identity.semantic_digest,
        "candidate_digest": revised_identity.candidate_digest,
    }
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "r2", reply_to="d2"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    ) == "accepted"


def test_r23003_receipt_v1_binding_mismatch_invalidates_receipt_and_accepts_revision_v2() -> None:
    """A live Workflow/InvokingWorkflow mismatch must reopen only the bound revision path."""

    now = [0.0]
    progress = FormalCandidateProgress(
        clock=lambda: now[0],
        allow_post_receipt_revision=True,
        integer_revisions=True,
    )
    candidate = _candidate(1)
    candidate["items"][0]["item_id"] = "workflow-b"
    candidate["items"][0]["item_kind"] = "existing_entity_ref"
    candidate["items"][0]["semantic"] = {
        "semantic_id": "workflow-b",
        "expected_class": "Workflow",
        "actual_class": "InvokingWorkflow",
    }
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "delivery-5"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    identity = progress.identity
    assert identity is not None
    receipt = build_candidate_receipt(candidate)
    receipt_delivery = _delivery(
        "protocol",
        "modeling",
        json.dumps(receipt),
        "delivery-6",
        reply_to="delivery-5",
    )
    assert progress.observe_delivery(
        receipt_delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    assert progress.state == "complete"

    conflict = build_existing_scope_candidate_conflict(
        candidate,
        "existing_entity_binding_mismatch",
        "workflow-b expected Workflow but live projection is InvokingWorkflow",
        original_delivery_id="delivery-5",
        receipt_digest=canonical_digest(receipt),
        workspace_version="workspace-v1",
    )
    assert progress.observe_delivery(
        _delivery(
            "protocol",
            "modeling",
            json.dumps(conflict),
            "delivery-7",
        ),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) == "conflict"
    assert progress.state == "awaiting_revision"

    # Receipt-v1 is invalidated and cannot be replayed after the conflict.
    assert progress.observe_delivery(
        _delivery(
            "protocol",
            "modeling",
            json.dumps(receipt),
            "delivery-6-replay",
            reply_to="delivery-5",
        ),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) is None

    revised = _candidate(2)
    revised["items"][0]["item_id"] = "workflow-b"
    revised["items"][0]["item_kind"] = "existing_entity_ref"
    revised["items"][0]["semantic"] = {
        "semantic_id": "workflow-b",
        "expected_class": "InvokingWorkflow",
        "actual_class": "InvokingWorkflow",
    }
    assert progress.observe_delivery(
        _delivery(
            "modeling",
            "protocol",
            json.dumps(revised),
            "delivery-8",
            reply_to="delivery-7",
        ),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) == "revision"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    revised_identity = progress.identity
    assert revised_identity is not None
    revised_receipt = {
        "status": "accepted",
        "candidate_revision": revised_identity.candidate_revision,
        "semantic_digest": revised_identity.semantic_digest,
        "candidate_digest": revised_identity.candidate_digest,
    }
    assert progress.observe_delivery(
        _delivery(
            "protocol",
            "modeling",
            json.dumps(revised_receipt),
            "delivery-9",
            reply_to="delivery-8",
        ),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start7-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    assert progress.state == "complete"


def test_r23009_plain_post_receipt_conflict_reopens_revision_after_receipt() -> None:
    """start6: the plain six-field conflict must repair a completed receipt.

    T0 defense review (user 2026-08-20): R2.3-008/009 progress accepts the
    plain builder conflict in the complete state, binds the revision to its
    delivery ID, and must not classify it as an invalid response.
    """

    now = [0.0]
    progress = FormalCandidateProgress(
        clock=lambda: now[0],
        allow_post_receipt_revision=True,
        plain_post_receipt_conflict=True,
    )
    candidate = _candidate()
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "delivery-10"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    receipt = build_candidate_receipt(candidate)
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "delivery-11", reply_to="delivery-10"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    assert progress.state == "complete"

    conflict = build_candidate_conflict(
        candidate,
        "post_receipt_context_drift",
        "workspace version drifted after the receipt",
    )
    conflict_delivery = _delivery(
        "protocol",
        "modeling",
        json.dumps(conflict),
        "delivery-12",
    )
    assert progress.observe_delivery(
        conflict_delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) == "conflict"
    assert progress.state == "awaiting_revision"
    assert progress.pending is not None
    assert progress.pending.conflict_delivery_id == "delivery-12"
    assert progress.is_invalid_response(
        conflict_delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
    ) is False

    revised = _candidate("rev-2")
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(revised), "delivery-13", reply_to="delivery-12"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) == "revision"
    assert progress.identity is not None
    assert progress.identity.original_delivery_id == "delivery-13"


def test_plain_post_receipt_conflict_still_rejected_without_the_r23009_flag() -> None:
    """R2.3-003/005 progress keeps requiring the typed post-receipt envelope."""

    now = [0.0]
    progress = FormalCandidateProgress(
        clock=lambda: now[0],
        allow_post_receipt_revision=True,
    )
    candidate = _candidate()
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "delivery-10"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    receipt = build_candidate_receipt(candidate)
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "delivery-11", reply_to="delivery-10"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    conflict = build_candidate_conflict(candidate, "post_receipt_context_drift", "drift")
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(conflict), "delivery-12"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start6-fixture",
        protocol_thread_id="protocol-thread",
    ) is None
    assert progress.state == "complete"
    assert progress.is_invalid_response(
        _delivery("protocol", "modeling", json.dumps(conflict), "delivery-12"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
    ) is True


def test_r23003_broker_allows_standalone_post_receipt_conflict_and_revision_reply(
    tmp_path: Path,
) -> None:
    """A receipt-occupied request gets one independent conflict/revision reply chain."""

    broker = TeamTransportBroker(
        tmp_path / "transport",
        {("modeling", "protocol"), ("protocol", "modeling")},
        modeling_agent_id="modeling",
    )
    progress = FormalCandidateProgress(
        clock=lambda: 0.0, allow_post_receipt_revision=True, integer_revisions=True
    )
    candidate = _candidate(1)
    original = broker.send(
        "modeling", "protocol", json.dumps(candidate), expects_reply=True
    )
    assert progress.observe_delivery(
        original,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start8-fixture",
        protocol_thread_id="protocol-thread",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    receipt = build_candidate_receipt(candidate)
    receipt_delivery = broker.send(
        "protocol", "modeling", json.dumps(receipt), reply_to_delivery_id=original.delivery_id
    )
    assert progress.observe_delivery(
        receipt_delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start8-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    broker.ack_delivery(receipt_delivery.delivery_id)

    conflict = build_existing_scope_candidate_conflict(
        candidate,
        "missing_class_dependency",
        "candidate references a class absent from the retained ontology",
        original_delivery_id=original.delivery_id,
        receipt_digest=canonical_digest(receipt),
        workspace_version="workspace-v1",
    )
    standalone = broker.send(
        "protocol", "modeling", json.dumps(conflict), expects_reply=True
    )
    assert standalone.reply_to_delivery_id is None
    assert progress.is_invalid_response(
        standalone, modeling_agent_id="modeling", protocol_agent_id="protocol"
    ) is False
    assert progress.observe_delivery(
        standalone,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start8-fixture",
        protocol_thread_id="protocol-thread",
    ) == "conflict"
    assert progress.pending is not None
    assert progress.pending.conflict_delivery_id == standalone.delivery_id

    # The old receipt reply chain is stale; the revised candidate must bind to
    # the standalone conflict request instead.
    stale_receipt = _delivery(
        "protocol", "modeling", json.dumps(receipt), "receipt-v1-replay", reply_to=original.delivery_id
    )
    assert progress.observe_delivery(
        stale_receipt,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start8-fixture",
        protocol_thread_id="protocol-thread",
    ) is None
    revised = _candidate(2)
    revision = broker.send(
        "modeling",
        "protocol",
        json.dumps(revised),
        expects_reply=True,
        reply_to_delivery_id=standalone.delivery_id,
    )
    assert revision.reply_to_delivery_id == standalone.delivery_id
    assert progress.observe_delivery(
        revision,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start8-fixture",
        protocol_thread_id="protocol-thread",
    ) == "revision"


def test_r23003_post_receipt_revision_rejects_same_revision_and_accepts_next() -> None:
    """A standalone conflict invalidates receipt-v1 and requires a strictly newer full candidate."""

    progress = FormalCandidateProgress(
        clock=lambda: 0.0, allow_post_receipt_revision=True, integer_revisions=True
    )
    candidate = _candidate(1)
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "delivery-6"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start12-fixture",
        protocol_thread_id="protocol-thread",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    receipt = build_candidate_receipt(candidate)
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(receipt), "delivery-7", reply_to="delivery-6"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start12-fixture",
        protocol_thread_id="protocol-thread",
    ) == "accepted"

    conflict = build_existing_scope_candidate_conflict(
        candidate,
        "delete_target_binding_missing",
        "each delete target needs a standalone existing_entity_ref binding",
        original_delivery_id="delivery-6",
        receipt_digest=canonical_digest(receipt),
        workspace_version="workspace-v1",
    )
    assert progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(conflict), "delivery-8"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start12-fixture",
        protocol_thread_id="protocol-thread",
    ) == "conflict"

    with pytest.raises(FormalCandidateError, match="strictly newer"):
        progress.observe_delivery(
            _delivery(
                "modeling",
                "protocol",
                json.dumps(_candidate(1)),
                "delivery-9-same-revision",
                reply_to="delivery-8",
            ),
            modeling_agent_id="modeling",
            protocol_agent_id="protocol",
            run_id="start12-fixture",
            protocol_thread_id="protocol-thread",
        )

    assert progress.observe_delivery(
        _delivery(
            "modeling",
            "protocol",
            json.dumps(_candidate(2)),
            "delivery-9-next-revision",
            reply_to="delivery-8",
        ),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="start12-fixture",
        protocol_thread_id="protocol-thread",
    ) == "revision"


def test_turn_barrier_allows_bounded_redrives_then_reports_exhaustion() -> None:
    now = [0.0]
    progress = FormalCandidateProgress(clock=lambda: now[0], redrive_limit=1)
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(_candidate()), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    states = [AgentState("protocol", "idle", "turn-1", "turn-1")]
    assert progress.observe_states(states, protocol_agent_id="protocol")
    assert progress.redrive_ready()
    progress.mark_redrive_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    progress.observe_states([AgentState("protocol", "idle", "turn-2", "turn-2")], protocol_agent_id="protocol")
    # R2.3-009 T1: the quota end is a boolean signal for cooperative
    # escalation, never a raise and never a terminal state.
    assert progress.redrive_ready() is False
    assert progress.redrive_exhausted is True
    assert progress.state not in progress._TERMINAL_STATES
    # The quota guard stays purely defensive: the channel is never re-armed
    # past the limit, so no further dispatch can be marked.
    assert progress.redrive_ready() is False


def test_deadline_miss_reports_a_boolean_without_latching() -> None:
    now = [0.0]
    progress = _progress(lambda: now[0])
    progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(_candidate()), "d1"),
        modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
    )
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    now[0] = 119.9
    assert progress.check_deadline() is False
    now[0] = 120.0
    assert progress.check_deadline() is True
    # The query is repeatable and never mutates progress into a terminal state.
    assert progress.check_deadline() is True
    assert progress.state == "awaiting_receipt"


def _started_progress(
    now: list[float], *, redrive_limit: int | None = None
) -> tuple[FormalCandidateProgress, dict[str, object]]:
    candidate = _candidate()
    progress = (
        FormalCandidateProgress(clock=lambda: now[0], redrive_limit=redrive_limit)
        if redrive_limit is not None
        else _progress(lambda: now[0])
    )
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(candidate), "d1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    progress.bind_dispatch(RuntimeDispatchReceipt("start", "turn-1"))
    return progress, candidate


def _receipt_for(progress: FormalCandidateProgress) -> dict[str, object]:
    identity = progress.identity
    assert identity is not None
    return {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }


def _observe_late(
    progress: FormalCandidateProgress,
    payload: dict[str, object],
    delivery_id: str,
    *,
    reply_to: str = "d1",
) -> str | None:
    return progress.observe_delivery(
        _delivery("protocol", "modeling", json.dumps(payload), delivery_id, reply_to=reply_to),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    )


def test_redrive_quota_end_still_accepts_the_late_receipt() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now, redrive_limit=1)
    progress.observe_states([AgentState("protocol", "idle", "turn-1", "turn-1")], protocol_agent_id="protocol")
    assert progress.redrive_ready()
    progress.mark_redrive_dispatch(RuntimeDispatchReceipt("start", "turn-2"))
    progress.observe_states([AgentState("protocol", "idle", "turn-2", "turn-2")], protocol_agent_id="protocol")
    assert progress.redrive_exhausted is True
    # R2.3-009: the nudge budget end is not terminal; the late typed
    # response still completes the channel instead of burning the run.
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") == "accepted"
    assert progress.state == "complete"


def test_deadline_missed_receipt_is_still_accepted() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    now[0] = 120.0
    assert progress.check_deadline() is True
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") == "accepted"
    assert progress.state == "complete"
    # A late conflict for the already-completed channel stays ignored.
    conflict = build_candidate_conflict(candidate, "late", "late response")
    assert _observe_late(progress, conflict, "late-conflict") is None


def test_deadline_missed_revision_is_still_accepted() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    conflict = build_candidate_conflict(candidate, "needs_revision", "revise item")
    assert _observe_late(progress, conflict, "conflict-1") == "conflict"
    now[0] = 120.0
    assert progress.check_deadline() is True
    revised = _candidate("rev-2")
    revision = _delivery(
        "modeling",
        "protocol",
        json.dumps(revised),
        "late-revision",
        reply_to="conflict-1",
    )
    assert progress.observe_delivery(
        revision,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "revision"
    assert progress.state == "awaiting_receipt"


def test_terminal_failure_latch_ignores_all_late_progress() -> None:
    now = [0.0]
    progress, candidate = _started_progress(now)
    identity = progress.identity
    progress.mark_terminal_failure()
    conflict = build_candidate_conflict(candidate, "late", "late response")
    revised = _candidate("rev-2")
    assert _observe_late(progress, _receipt_for(progress), "late-receipt") is None
    assert _observe_late(progress, conflict, "late-conflict") is None
    assert progress.observe_delivery(
        _delivery("modeling", "protocol", json.dumps(revised), "late-revision", reply_to="conflict-1"),
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) is None
    assert progress.state == "awaiting_receipt"
    assert progress.identity == identity
    assert progress.terminal_failure_latched is True


def test_formal_candidate_rejects_non_string_constraints() -> None:
    invalid = _candidate()
    invalid["constraints"] = ["ok", {"not": "a string"}]
    with pytest.raises(FormalCandidateError):
        FormalCandidateProgress(clock=lambda: 0.0).observe_delivery(
            _delivery("modeling", "protocol", json.dumps(invalid), "d1"),
            modeling_agent_id="modeling", protocol_agent_id="protocol", run_id="run-1", protocol_thread_id="thread-1"
        )


def test_redrive_retains_exact_candidate_bytes_and_runtime_attribution() -> None:
    original_text = (
        '{"candidate_kind":"platform-neutral-candidate-v2",'
        '"candidate_revision":"rev-1","scope":"工作流-é",'
        '"constraints":["preserve explicit unknowns"],'
        '"items":[{"item_id":"workflow-1","item_kind":"entity",'
        '"semantic":{"label":"工作流"},'
        '"evidence_citations":[{"document":"tools.mdx"}]}]}\n  '
    )
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    delivery = _delivery("modeling", "protocol", original_text, "d1")
    assert progress.observe_delivery(
        delivery,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-1",
        protocol_thread_id="thread-1",
    ) == "candidate"
    attribution = progress.original_runtime_attribution
    assert attribution is not None
    assert attribution.text == original_text
    assert progress.redrive_text() == original_text
    assert attribution.sender_id == delivery.sender_id
    assert attribution.recipient_id == delivery.recipient_id
    assert attribution.delivery_id == delivery.delivery_id
    assert attribution.expects_reply == delivery.expects_reply
    assert attribution.reply_to_delivery_id == delivery.reply_to_delivery_id


def test_formal_broker_reopens_one_occupied_or_acknowledged_reply_slot(tmp_path: Path) -> None:
    for acknowledged in (False, True):
        broker = TeamTransportBroker(
            tmp_path / ("acknowledged" if acknowledged else "occupied"),
            {("modeling", "protocol"), ("protocol", "modeling")},
            modeling_agent_id="modeling",
        )
        request = broker.send("modeling", "protocol", "candidate", expects_reply=True)
        invalid = broker.send(
            "protocol",
            "modeling",
            "not-json",
            expects_reply=True,
            reply_to_delivery_id=request.delivery_id,
        )
        if acknowledged:
            broker.ack_delivery(invalid.delivery_id)
        broker.reopen_formal_reply_slot(
            original_delivery_id=request.delivery_id,
            invalid_reply_delivery_id=invalid.delivery_id,
            modeling_agent_id="modeling",
            protocol_agent_id="protocol",
            formal_candidate=True,
        )
        if not acknowledged:
            broker.ack_delivery(invalid.delivery_id)
        replacement = broker.send(
            "protocol",
            "modeling",
            "valid-receipt",
            expects_reply=True,
            reply_to_delivery_id=request.delivery_id,
        )
        broker.ack_delivery(replacement.delivery_id)
        with pytest.raises(RoutingError, match="active reversed"):
            broker.send(
                "protocol",
                "modeling",
                "duplicate",
                reply_to_delivery_id=request.delivery_id,
            )
        assert len(broker._delivery_by_id) == 3
        with pytest.raises(RoutingError, match="already consumed"):
            broker.reopen_formal_reply_slot(
                original_delivery_id=request.delivery_id,
                invalid_reply_delivery_id=invalid.delivery_id,
                modeling_agent_id="modeling",
                protocol_agent_id="protocol",
                formal_candidate=True,
            )


def test_runner_reopens_invalid_reply_then_accepts_exact_redrive_reply(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate_text = json.dumps(_candidate(), ensure_ascii=False, separators=(",", ":"))
    original = runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)
    runner.transport.send(
        "protocol",
        "modeling",
        "Please resend the candidate",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    redrives = [delivery for _, delivery in adapter.sent if delivery.kind == "candidate-redrive"]
    assert len(redrives) == 1
    assert not any(
        recipient == "modeling" and delivery.text == "Please resend the candidate"
        for recipient, delivery in adapter.sent
    )
    assert redrives[0].text == candidate_text
    assert redrives[0].delivery_id == original.delivery_id
    identity = runner._candidate_progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(receipt),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "complete"
    assert len([delivery for _, delivery in adapter.sent if delivery.kind == "candidate-redrive"]) == 1
    assert len(runner.transport._delivery_by_id) == 3


def test_runner_delivers_post_receipt_standalone_nonconflict_as_ordinary_peer(
    tmp_path: Path,
) -> None:
    """start1 dead end: a post-receipt standalone Protocol note reaches Modeling."""

    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    # start1 ran under the R2.3-009 carrier contract, which enables
    # post-receipt standalone conflicts; the shared helper defaults it off.
    runner._candidate_progress = FormalCandidateProgress(
        clock=lambda: 0.0, allow_post_receipt_revision=True
    )
    candidate = _candidate()
    candidate_text = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
    original = runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)
    runner.drain()
    identity = runner._candidate_progress.identity
    assert identity is not None
    _, semantic_digest = formal_candidate_digests(candidate)
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(receipt, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "complete"

    # A standalone post-receipt conflict-shaped reply that fails exact typing
    # used to disappear into quarantine (start1's final dead end): Protocol
    # thought it had sent a usable conflict, Modeling never saw anything.
    imperfect_conflict = build_candidate_conflict(
        candidate, "competency_question_count_mismatch", "scope mismatch"
    )
    imperfect_conflict["receipt_digest"] = "not-the-accepted-receipt-digest"
    standalone = runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(imperfect_conflict, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
    )
    runner.drain()
    assert any(
        recipient == "modeling" and delivery.delivery_id == standalone.delivery_id
        for recipient, delivery in adapter.sent
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "run" / "evidence" / "formal-candidate-progress.jsonl")
        .read_text()
        .splitlines()
    ]
    event_names = [event["event"] for event in events]
    assert "invalid-standalone-conflict-delivered-as-ordinary" in event_names
    assert "invalid-response-quarantined" not in event_names
    # The ordinary message cannot advance the formal state machine.
    assert runner._candidate_progress.state == "complete"


def test_runner_quarantines_invalid_guidance_then_binds_revision_to_formal_conflict(
    tmp_path: Path,
) -> None:
    """A malformed Protocol guidance response cannot become a revision anchor."""

    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate = _candidate()
    original = runner.transport.send(
        "modeling",
        "protocol",
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
    )
    guidance = runner.transport.send(
        "protocol",
        "modeling",
        "Please send a complete, self-contained candidate revision",
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )

    # The malformed guidance is reopened for the formal slot and then dropped;
    # the only Runtime dispatch is the bounded candidate redrive.
    runner.drain()
    assert runner._candidate_progress.state == "redrive_sent"
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    assert not any(
        recipient == "modeling" and delivery.delivery_id == guidance.delivery_id
        for recipient, delivery in adapter.sent
    )
    progress_events = [
        json.loads(line)
        for line in (tmp_path / "run" / "evidence" / "formal-candidate-progress.jsonl")
        .read_text()
        .splitlines()
    ]
    progress_event_names = [event["event"] for event in progress_events]
    assert progress_event_names.index("invalid-response-quarantined") > progress_event_names.index(
        "invalid-response-slot-reopened"
    )

    conflict = build_candidate_conflict(candidate, "competency_question_count_mismatch", "scope mismatch")
    conflict_delivery = runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(conflict, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "awaiting_revision"
    assert any(
        recipient == "modeling" and delivery.delivery_id == conflict_delivery.delivery_id
        for recipient, delivery in adapter.sent
    )

    revised = _candidate("rev-2")
    # After the formal conflict, the original request is no longer an active
    # revision slot; only the conflict delivery may be reversed by Modeling.
    with pytest.raises(RoutingError, match="active reversed"):
        runner.transport.send(
            "modeling",
            "protocol",
            json.dumps(revised, ensure_ascii=False, separators=(",", ":")),
            expects_reply=True,
            reply_to_delivery_id=original.delivery_id,
        )
    revision_delivery = runner.transport.send(
        "modeling",
        "protocol",
        json.dumps(revised, ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
        reply_to_delivery_id=conflict_delivery.delivery_id,
    )
    candidate_digest, semantic_digest = formal_candidate_digests(revised)
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(
            {
                "status": "accepted",
                "candidate_revision": revised["candidate_revision"],
                "semantic_digest": semantic_digest,
                "candidate_digest": candidate_digest,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        reply_to_delivery_id=revision_delivery.delivery_id,
    )
    runner.drain()
    assert runner._candidate_progress.state == "complete"


class _FormalProgressAdapter:
    def __init__(self, *, missing_receipt: bool = False) -> None:
        self.missing_receipt = missing_receipt
        self.sent: list[tuple[str, RuntimeDelivery]] = []
        self.turns = {"protocol": (None, None)}

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        self.sent.append((recipient, delivery))
        if recipient == "protocol" and delivery.kind == "peer":
            if self.missing_receipt:
                return None
            self.turns["protocol"] = ("turn-1", "turn-1")
            return RuntimeDispatchReceipt("start", "turn-1")
        if recipient == "protocol" and delivery.kind == "candidate-redrive":
            self.turns["protocol"] = ("turn-2", "turn-2")
            return RuntimeDispatchReceipt("start", "turn-2")
        return RuntimeDispatchReceipt("start", "other")

    def receive_messages(self):
        return []

    def get_agent_states(self):
        started, completed = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, completed)]


class _IssueRecoveryProgressAdapter(_FormalProgressAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.complete_original = False

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        if recipient == "protocol" and delivery.kind == "peer":
            self.sent.append((recipient, delivery))
            self.turns["protocol"] = ("candidate-turn", None)
            return RuntimeDispatchReceipt("start", "candidate-turn")
        if recipient == "protocol" and delivery.kind == "candidate-redrive":
            self.sent.append((recipient, delivery))
            self.turns["protocol"] = ("redrive-turn", None)
            return RuntimeDispatchReceipt("start", "redrive-turn")
        return super().send_message(recipient, delivery)

    def get_agent_states(self):
        if self.complete_original:
            self.turns["protocol"] = ("candidate-turn", "candidate-turn")
        started, completed = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, completed)]


def _formal_progress_runner(
    tmp_path: Path,
    adapter: _FormalProgressAdapter,
    *,
    issue_escalation_enabled: bool = False,
) -> TeamRunner:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=agents, parameters={}),
    )
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True)
    runner = TeamRunner(repository_root=tmp_path, adapter=adapter, monotonic_clock=lambda: 0.0)
    runner.run = SimpleNamespace(run_id="run-1", root=run_root, scope={"mode": "create"}, configuration=configuration)
    permissions = {("modeling", "protocol"), ("protocol", "modeling")}
    if issue_escalation_enabled:
        permissions.update({("modeling", "coordinator"), ("coordinator", "modeling")})
    runner.transport = TeamTransportBroker(
        run_root / "broker",
        permissions,
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
        terminal_dependencies={},
        issue_escalation_enabled=issue_escalation_enabled,
    )
    runner._candidate_progress = FormalCandidateProgress(clock=lambda: 0.0)
    return runner


def test_runner_missing_formal_turn_id_fails_platform_contract(tmp_path: Path) -> None:
    from modeling_team.candidate_progress import FormalCandidatePlatformContractError

    runner = _formal_progress_runner(tmp_path, _FormalProgressAdapter(missing_receipt=True))
    runner.transport.send("modeling", "protocol", json.dumps(_candidate()), expects_reply=True)
    with pytest.raises(FormalCandidatePlatformContractError):
        runner.drain()
    assert json.loads((tmp_path / "run" / "state.json").read_text())[
        "state"
    ] == "TERMINAL_FAILURE_PENDING_CLEANUP"


def test_runner_turn_barrier_sends_one_candidate_redrive(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    candidate_text = json.dumps(_candidate())
    original = runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)
    runner.drain()
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    redrive = adapter.sent[-1][1]
    assert redrive.text == candidate_text
    assert redrive.sender_id == original.sender_id
    assert redrive.recipient_id == original.recipient_id
    assert redrive.delivery_id == original.delivery_id
    assert redrive.expects_reply == original.expects_reply
    assert redrive.reply_to_delivery_id == original.reply_to_delivery_id


def test_runner_opens_platform_gate_only_after_registered_receipt(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    gate = CandidatePlatformGate.ensure(tmp_path / "run" / "candidate-gate")
    runner._candidate_platform_gate = gate
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()
    assert json.loads(gate.state_path.read_text())["state"] == "closed"

    identity = runner._candidate_progress.identity
    assert identity is not None
    receipt = {
        "status": "accepted",
        "candidate_revision": identity.candidate_revision,
        "semantic_digest": identity.semantic_digest,
        "candidate_digest": identity.candidate_digest,
    }
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(receipt),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert json.loads(gate.state_path.read_text())["state"] == "open"


def test_runner_wakes_protocol_once_after_accepted_receipt_and_not_on_duplicate_drain(
    tmp_path: Path,
) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    gate = CandidatePlatformGate.ensure(tmp_path / "run" / "candidate-gate")
    runner._candidate_platform_gate = gate
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()
    identity = runner._candidate_progress.identity
    assert identity is not None
    accepted = runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(
            {
                "status": "accepted",
                "candidate_revision": identity.candidate_revision,
                "semantic_digest": identity.semantic_digest,
                "candidate_digest": identity.candidate_digest,
            }
        ),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    wakeups = [
        delivery
        for recipient, delivery in adapter.sent
        if recipient == "protocol" and delivery.kind == CANDIDATE_RECEIPT_REGISTERED_KIND
    ]
    assert len(wakeups) == 1
    assert wakeups[0].reply_to_delivery_id == accepted.delivery_id
    notice = json.loads(wakeups[0].text)
    assert set(notice) == {
        "schema_version",
        "run_id",
        "original_delivery_id",
        "accepted_receipt_delivery_id",
        "candidate_digest",
    }
    assert notice["run_id"] == "run-1"
    assert notice["original_delivery_id"] == identity.original_delivery_id
    assert notice["accepted_receipt_delivery_id"] == accepted.delivery_id
    assert notice["candidate_digest"] == identity.candidate_digest

    runner.drain()
    assert len(
        [
            delivery
            for recipient, delivery in adapter.sent
            if recipient == "protocol" and delivery.kind == CANDIDATE_RECEIPT_REGISTERED_KIND
        ]
    ) == 1


def test_runner_keeps_platform_gate_closed_after_protocol_conflict(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    gate = CandidatePlatformGate.ensure(tmp_path / "run" / "candidate-gate")
    runner._candidate_platform_gate = gate
    candidate = _candidate()
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(candidate), expects_reply=True
    )
    runner.drain()
    conflict = build_candidate_conflict(candidate, "unsupported", "relation is not declared")
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(conflict),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert json.loads(gate.state_path.read_text())["state"] == "closed"
    assert not any(
        delivery.kind == CANDIDATE_RECEIPT_REGISTERED_KIND
        for _, delivery in adapter.sent
    )


def test_legacy_without_platform_gate_does_not_wake_protocol(tmp_path: Path) -> None:
    adapter = _FormalProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    runner._candidate_platform_gate = None
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()
    identity = runner._candidate_progress.identity
    assert identity is not None
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(
            {
                "status": "accepted",
                "candidate_revision": identity.candidate_revision,
                "semantic_digest": identity.semantic_digest,
                "candidate_digest": identity.candidate_digest,
            }
        ),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    runner.drain()
    assert not any(
        delivery.kind == CANDIDATE_RECEIPT_REGISTERED_KIND
        for _, delivery in adapter.sent
    )


class _WakeupFailureAdapter(_FormalProgressAdapter):
    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        if delivery.kind == CANDIDATE_RECEIPT_REGISTERED_KIND:
            raise RuntimeError("wakeup transport failed")
        return super().send_message(recipient, delivery)


def test_receipt_wakeup_failure_closes_gate_and_latches_runtime_failure(tmp_path: Path) -> None:
    adapter = _WakeupFailureAdapter()
    runner = _formal_progress_runner(tmp_path, adapter)
    gate = CandidatePlatformGate.ensure(tmp_path / "run" / "candidate-gate")
    runner._candidate_platform_gate = gate
    original = runner.transport.send(
        "modeling", "protocol", json.dumps(_candidate()), expects_reply=True
    )
    runner.drain()
    identity = runner._candidate_progress.identity
    assert identity is not None
    runner.transport.send(
        "protocol",
        "modeling",
        json.dumps(
            {
                "status": "accepted",
                "candidate_revision": identity.candidate_revision,
                "semantic_digest": identity.semantic_digest,
                "candidate_digest": identity.candidate_digest,
            }
        ),
        expects_reply=True,
        reply_to_delivery_id=original.delivery_id,
    )
    with pytest.raises(TeamConfigurationError, match="registration wakeup failed"):
        runner.drain()
    assert json.loads(gate.state_path.read_text())["state"] == "closed"
    assert runner._formal_failure_latched is True


def test_issue_pending_latches_candidate_before_recovery_turn_overwrites_state(tmp_path: Path) -> None:
    adapter = _IssueRecoveryProgressAdapter()
    runner = _formal_progress_runner(tmp_path, adapter, issue_escalation_enabled=True)
    candidate_text = json.dumps(_candidate())
    runner.transport.send("modeling", "protocol", candidate_text, expects_reply=True)

    # The original dispatch is started, but its completion notification has not
    # arrived during this drain.  The issue is then reported before the next
    # main-loop iteration.
    runner.drain()
    progress = runner._candidate_progress
    assert progress is not None and progress.pending is not None
    assert progress.pending.turn_barrier_complete is False
    identity = progress.identity
    assert identity is not None
    ledger = runner.transport.issue_ledger
    assert ledger is not None
    issue = ledger.report(
        reporter_id="modeling",
        category="runtime_recovery",
        summary="Protocol needs recovery guidance",
        failing_operation="receipt",
        error="recovery turn required",
        mutation_state="not_started",
        requested_action="pause and resume",
        thread_id="runtime-agent:protocol",
        candidate_identity=identity.__dict__,
    )

    # While the issue is pending, Runner must retain the original delivery and
    # observe its completion, but must not redrive yet.
    adapter.complete_original = True
    runner.drain()
    assert progress.pending is not None and progress.pending.turn_barrier_complete is True
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer"]

    # A later recovery turn overwrites the adapter's last-completed turn.  Once
    # the issue is resolved, the latched barrier still permits exactly one
    # candidate redrive.
    adapter.complete_original = False
    adapter.turns["protocol"] = ("recovery-turn", "recovery-turn")
    pause = ledger.control(
        issue_id=issue.issue_id,
        coordinator_id="coordinator",
        reporter_id="modeling",
        action="pause",
        control_epoch=issue.control_epoch,
    )
    ledger.mark_dispatch(pause)
    resolution = IssueResolution(
        run_id=issue.run_id,
        issue_id=issue.issue_id,
        reporter_id="modeling",
        resolution_type="guidance",
        control_epoch=issue.control_epoch,
        resolution_text="Resume the same candidate turn.",
    )
    ledger.persist_resolution(resolution)
    resume = ledger.control(
        issue_id=issue.issue_id,
        coordinator_id="coordinator",
        reporter_id="modeling",
        action="resume",
        control_epoch=issue.control_epoch,
        resolution=resolution,
    )
    ledger.mark_dispatch(resume)

    runner.drain()
    assert [delivery.kind for _, delivery in adapter.sent] == ["peer", "candidate-redrive"]
    assert progress.state == "redrive_sent"


def test_channel_open_tracks_terminal_candidate_states() -> None:
    # R2.3-009 start17: the idle inquiry reads ``channel_open`` to decide
    # whether a candidate handoff still owns progress.  The pending record
    # survives every terminal state ("complete", "exhausted",
    # "terminal_failure"), so openness must key on the state, not on the
    # pending record's existence.
    progress = FormalCandidateProgress(clock=lambda: 0.0)
    assert progress.channel_open is False

    progress.pending = SimpleNamespace(state="awaiting_receipt")
    assert progress.channel_open is True
    progress.pending = SimpleNamespace(state="redrive_sent")
    assert progress.channel_open is True

    progress.pending = SimpleNamespace(state="complete")
    assert progress.channel_open is False
    progress.pending = SimpleNamespace(state="exhausted")
    assert progress.channel_open is False
    progress.pending = SimpleNamespace(state="terminal_failure")
    assert progress.channel_open is False
