"""R3.0-016 ledger #20/#22/#30 family: value-free, self-diagnosable refusals.

issue_control refusals used to be bare sentences ("arguments are invalid",
"resolution does not match persisted resolution"), so the Coordinator paid a
full diagnosis round trip to learn which field was rejected, and a terminal
report refusal never explained why fresh retrieval evidence was suddenly
required.  The refusals now name schema fields, summarize the first differing
resolution field as a length plus sha256 prefix, and the retrieval guard names
the reset cause and both exits.  Every dynamic token stays inside a fixed
vocabulary so the codex relay can re-render the sentence without reflecting
socket-controlled bytes.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from modeling_team.interventions import (
    IssueError,
    IssueResolution,
    RecoverableIssueLedger,
    normalize_issue_control_arguments,
)
from modeling_team.transport_mcp import (
    TERMINAL_REPORT_GUARD_ERROR,
    RoutingError,
    _issue_control_field_error,
    issue_control_transport_error,
)


def _resolution(**overrides: object) -> IssueResolution:
    fields: dict[str, object] = {
        "run_id": "run-1",
        "issue_id": "issue-1",
        "reporter_id": "modeling",
        "resolution_type": "guidance",
        "control_epoch": 1,
        "resolution_text": "Resume the same candidate turn.",
        "repair_component": None,
        "before_digest": None,
        "after_digest": None,
        "verification_reference": None,
        "mutation_reconciliation": None,
    }
    fields.update(overrides)
    return IssueResolution(**fields)  # type: ignore[arg-type]


def _paused_ledger() -> tuple[RecoverableIssueLedger, str, int]:
    ledger = RecoverableIssueLedger(run_id="run-1", coordinator_id="coordinator")
    issue = ledger.report(
        reporter_id="modeling",
        category="platform_repair",
        summary="summary",
        failing_operation="operation",
        error="error",
        mutation_state="not_started",
        requested_action="pause and resume",
    )
    ledger.control(
        issue_id=issue.issue_id,
        coordinator_id="coordinator",
        reporter_id="modeling",
        action="pause",
        control_epoch=issue.control_epoch,
    )
    return ledger, issue.issue_id, issue.control_epoch


@pytest.mark.parametrize("resolved", [False, True])
def test_repeated_pause_reports_actual_state_without_mutating_it(resolved: bool) -> None:
    ledger, issue_id, epoch = _paused_ledger()
    if resolved:
        resolution = _resolution(issue_id=issue_id, control_epoch=epoch)
        ledger.persist_resolution(resolution)
        resume = ledger.control(
            issue_id=issue_id, coordinator_id="coordinator", reporter_id="modeling",
            action="resume", control_epoch=epoch, resolution=resolution,
        )
        ledger.mark_dispatch(resume)
    expected = "resolved" if resolved else "waiting_repair"
    before = ledger.evidence()
    with pytest.raises(IssueError) as failure:
        ledger.control(
            issue_id=issue_id, coordinator_id="coordinator", reporter_id="modeling",
            action="pause", control_epoch=epoch,
        )
    message = f"issue pause is not valid in current state: {expected}"
    assert str(failure.value) == message
    assert issue_control_transport_error(message) == message
    assert ledger.state == expected and ledger.evidence() == before
    assert ledger.can_terminal() is resolved


def test_pause_state_relay_accepts_only_known_state_tokens() -> None:
    for value in ["arbitrary_state", "resolved\nsecret", "resolved; resume now"]:
        assert issue_control_transport_error(
            "issue pause is not valid in current state: " + value
        ) is None


# --- normalize: name the rejected arguments -----------------------------------


def test_normalize_names_missing_and_unexpected_fields() -> None:
    with pytest.raises(IssueError) as missing:
        normalize_issue_control_arguments({"action": "pause"})
    assert "missing: control_epoch, issue_id, reporter_id" in str(missing.value)

    with pytest.raises(IssueError) as unexpected:
        normalize_issue_control_arguments(
            {"issue_id": "issue-1", "reporter_id": "modeling", "action": "pause",
             "control_epoch": 1, "bogus_field": 1}
        )
    assert str(unexpected.value) == (
        "issue_control arguments are invalid: unexpected: bogus_field"
    )

    with pytest.raises(IssueError) as both:
        normalize_issue_control_arguments({"action": "pause", "bogus_field": 1})
    message = str(both.value)
    assert "missing: control_epoch, issue_id, reporter_id" in message
    assert "unexpected: bogus_field" in message
    assert issue_control_transport_error(message) == message


def test_normalize_stays_within_the_broker_relay_bound_for_hostile_keys() -> None:
    hostile = {"a" * 400: 1}
    with pytest.raises(IssueError) as excinfo:
        normalize_issue_control_arguments(hostile)
    assert len(str(excinfo.value)) <= 200


# --- resume/abort replay: summarize the differing field, never its value ------


def test_resume_mismatch_names_first_differing_field_without_values() -> None:
    ledger, issue_id, epoch = _paused_ledger()
    resolution = _resolution(issue_id=issue_id, control_epoch=epoch)
    ledger.persist_resolution(resolution)
    drifted = replace(resolution, resolution_text="Different instruction text.")
    with pytest.raises(IssueError) as excinfo:
        ledger.control(
            issue_id=issue_id,
            coordinator_id="coordinator",
            reporter_id="modeling",
            action="resume",
            control_epoch=epoch,
            resolution=drifted,
        )
    message = str(excinfo.value)
    assert message.startswith(
        "issue resume resolution does not match persisted resolution: differing resolution_text "
    )
    assert (
        f"persisted {len(resolution.resolution_text)}ch sha256:" in message
        and f"provided {len(drifted.resolution_text)}ch sha256:" in message
    )
    # Neither the persisted nor the provided text is reflected.
    assert resolution.resolution_text not in message
    assert drifted.resolution_text not in message
    assert len(message) <= 200
    # The relay re-renders the same sentence from the validated tokens.
    assert issue_control_transport_error(message) == message


def test_resume_mismatch_counts_remaining_differing_fields() -> None:
    ledger, issue_id, epoch = _paused_ledger()
    resolution = _resolution(issue_id=issue_id, control_epoch=epoch)
    ledger.persist_resolution(resolution)
    # A guidance resolution forbids the repair fields, so the second drift is
    # the embedded epoch; the first differing field follows _RESOLUTION_FIELDS
    # order and the surplus is only counted, never rendered.
    drifted = replace(
        resolution,
        control_epoch=epoch + 1,
        resolution_text="Different instruction text.",
    )
    with pytest.raises(IssueError) as excinfo:
        ledger.control(
            issue_id=issue_id,
            coordinator_id="coordinator",
            reporter_id="modeling",
            action="resume",
            control_epoch=epoch,
            resolution=drifted,
        )
    message = str(excinfo.value)
    assert "differing control_epoch (persisted sha256:" in message
    assert "(+1 more field(s) differ)" in message
    assert issue_control_transport_error(message) == message


def test_abort_mismatch_names_resolution_text_without_values() -> None:
    ledger, issue_id, epoch = _paused_ledger()
    resolution = _resolution(
        issue_id=issue_id,
        control_epoch=epoch,
        resolution_type="abort",
        resolution_text="Abandon the unrecoverable write path.",
    )
    ledger.persist_resolution(resolution)
    with pytest.raises(IssueError) as excinfo:
        ledger.control(
            issue_id=issue_id,
            coordinator_id="coordinator",
            reporter_id="modeling",
            action="abort",
            control_epoch=epoch,
            reason="A different abort reason.",
        )
    message = str(excinfo.value)
    assert message.startswith(
        "issue abort reason does not match persisted resolution: differing resolution_text "
    )
    assert resolution.resolution_text not in message
    assert "A different abort reason." not in message
    assert len(message) <= 200
    assert issue_control_transport_error(message) == message


# --- facade: field-set refusals name the fields --------------------------------


def test_facade_field_error_lists_missing_and_unexpected() -> None:
    error = _issue_control_field_error(
        "repair",
        {"issue_id": "issue-1", "extra": 1},
        {
            "issue_id",
            "reporter_id",
            "action",
            "control_epoch",
            "resolution_type",
            "repair_component",
        },
    )
    assert str(error) == (
        "issue_control repair fields are invalid "
        "(missing: action, control_epoch, repair_component, reporter_id, resolution_type; "
        "unexpected: extra)"
    )
    assert issue_control_transport_error(str(error)) == str(error)


def test_facade_pause_and_abort_errors_round_trip_through_the_relay() -> None:
    pause = _issue_control_field_error(
        "pause", {"issue_id": "issue-1"}, {"issue_id", "reporter_id", "action", "control_epoch"}
    )
    assert issue_control_transport_error(str(pause)) == str(pause)
    abort = _issue_control_field_error(
        "abort",
        {"issue_id": "issue-1", "reason": "why", "surplus": 1},
        {"issue_id", "reporter_id", "action", "control_epoch", "reason"},
    )
    relayed = issue_control_transport_error(str(abort))
    assert relayed == (
        "issue_control abort fields are invalid "
        "(missing: action, control_epoch, reporter_id; unexpected: surplus)"
    )


# --- relay: hostile or unrelated broker text stays rejected ---------------------


def test_relay_rejects_hostile_and_malformed_variants() -> None:
    assert issue_control_transport_error(None) is None
    assert issue_control_transport_error(42) is None
    assert issue_control_transport_error("x" * 201) is None
    assert (
        issue_control_transport_error(
            "issue_control arguments are invalid: missing: " + "a" * 300
        )
        is None
    )
    assert (
        issue_control_transport_error(
            "issue resume resolution does not match persisted resolution: "
            "differing resolution_text (persisted <script>, provided also-bad)"
        )
        is None
    )
    assert (
        issue_control_transport_error(
            "issue_control pause fields are invalid (unexpected: not a field)trailer"
        )
        is None
    )


# --- retrieval guard: the state machine and both exits are discoverable ---------


def test_terminal_guard_error_keeps_prefix_and_names_reset_and_exits() -> None:
    # The settlement suite asserts on the legacy prefix; category mapping and
    # older regexes must keep matching.
    assert TERMINAL_REPORT_GUARD_ERROR.startswith("Protocol retrieval evidence is incomplete")
    assert "reset it to query_required" in TERMINAL_REPORT_GUARD_ERROR
    assert "query_semantic_context" in TERMINAL_REPORT_GUARD_ERROR
    assert "verify_scoped_retrieval_fallback" in TERMINAL_REPORT_GUARD_ERROR
    # A fixed literal must stay inside the broker relay bound to be reflected.
    assert len(TERMINAL_REPORT_GUARD_ERROR) <= 200


def test_guard_error_is_relayed_as_a_fixed_string() -> None:
    # The fixed-string branch of the codex relay matches the constant directly;
    # the field renderer must not swallow it either.
    assert issue_control_transport_error(TERMINAL_REPORT_GUARD_ERROR) is None
    assert isinstance(
        _issue_control_field_error("pause", {}, {"issue_id"}), RoutingError
    )
