"""R3.0-016 S1 host-only MCP tool surface (交付设计 §3/§4).

A stdio MCP server named ``modeling-team-host`` exposing exactly the fixed
12 S1 tools over the local operation layer :mod:`modeling_team.host_ops`.
Every tool is a thin typed wrapper: parameters map to the op-layer function,
``HostOpError`` becomes the design §9 ``{ok: False, error}`` envelope, and
success returns ``{ok: True, data}``.  No business semantics, natural-language
interpretation, auto-approval or S2 lifecycle action lives here.

Run via ``backend/.venv/bin/python -m modeling_team.host_ops_mcp`` from the
repository root (see ``.claude/modeling-team-host-mcp.json``).  The server is
host-side only: it never enters the production ``backend/app/mcp/tools``
registry or any role agent-package mount.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .host_ops import (
    HostOpError,
    answer_question,
    complete_cq_acceptance,
    complete_cq_handoff,
    freeze_cq,
    get_pending_actions,
    get_request_result,
    get_run_events,
    get_run_status,
    recover_provider,
    register_question,
    resolve_issue,
    submit_cq_review,
)

mcp: FastMCP = FastMCP("modeling-team-host")


def _call(function, /, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "data": function(*args, **kwargs)}
    except HostOpError as exc:
        return {"ok": False, "error": exc.as_envelope()}


@mcp.tool(name="get_run_status")
def tool_get_run_status(run_id: str) -> dict[str, Any]:
    """Read-only status snapshot of one modeling Team run (design §7.1).

    Returns recorded state, stage, last verifiable activity, semantic
    progress, first blocker, pending summary, terminal conclusion, the
    three-way liveness observation (recorded state / process observation
    with evidence / FIFO presence as an independent fact) and limitations.
    run_id is the modeling Team run id, not a platform session id.
    """
    return _call(get_run_status, run_id)


@mcp.tool(name="get_run_events")
def tool_get_run_events(
    run_id: str,
    cursor: str | None = None,
    limit: int | None = 200,
) -> dict[str, Any]:
    """Incrementally read run evidence events (design §6).

    ``cursor`` is the opaque continuation token from a previous call; the
    first call omits it.  ``limit`` bounds the event count (default 200,
    clamped to 1000).  Events carry their source file and in-source line
    number; ordering is recorded_at-approximate across sources, never a
    claim of causality.  Strictly read-only: no drain, no writes.
    """
    return _call(get_run_events, run_id, cursor=cursor, limit=limit)


@mcp.tool(name="get_pending_actions")
def tool_get_pending_actions(run_id: str) -> dict[str, Any]:
    """List pending host actions derived from run evidence (design §7.2).

    Pending owner questions, the CQ interview window, CQ review items,
    freeze/handoff/acceptance closure states, issue waits and provider
    waits, each with stable bindings for the matching submission tool.
    File-derived facts only; the Runner re-checks every binding at
    admission time.
    """
    return _call(get_pending_actions, run_id)


@mcp.tool(name="answer_question")
def tool_answer_question(
    run_id: str,
    channel: str,
    text: str,
    question_delivery_id: str | None = None,
    wait_for_draft: bool | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Answer one pending question through the outer-input FIFO.

    ``channel='user'`` answers a displayed owner question and requires the
    ``question_delivery_id`` binding from ``get_pending_actions``;
    ``channel='cq_interview'`` answers the competency-question interview
    window.  The two channels are not interchangeable.  ``text`` is passed
    through verbatim (multi-line Chinese text is fine).  ``request_id``
    (optional, unique per submission content) enables later
    ``get_request_result`` correlation and idempotent replay.
    """
    return _call(
        answer_question,
        run_id,
        channel=channel,
        text=text,
        question_delivery_id=question_delivery_id,
        wait_for_draft=wait_for_draft,
        request_id=request_id,
    )


@mcp.tool(name="register_question")
def tool_register_question(
    run_id: str,
    delivery_id: str,
    text: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Register an owner question with an explicit host delivery id.

    Only for the two-step registration mode when the existing channel
    requires the host to register the question first; answers then go
    through ``answer_question(channel='user')``.  Never used to silently
    replace a failed answer.
    """
    return _call(
        register_question,
        run_id,
        delivery_id=delivery_id,
        text=text,
        request_id=request_id,
    )


@mcp.tool(name="submit_cq_review")
def tool_submit_cq_review(
    run_id: str,
    review_id: str,
    question_id: str,
    decision: str,
    content_version: int,
    content_digest: str,
    revision: int,
    modified_question: str | None = None,
    note: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Submit one competency-question review decision.

    All bindings come from the current ``cq_review`` pending item
    (``get_pending_actions``); the tool fills the schema_version itself and
    the Runner validates every binding against the review snapshot.  A
    stale revision/digest/question binding is rejected with the original
    Runner code.
    """
    return _call(
        submit_cq_review,
        run_id,
        review_id=review_id,
        question_id=question_id,
        decision=decision,
        content_version=content_version,
        content_digest_value=content_digest,
        revision=revision,
        modified_question=modified_question,
        note=note,
        request_id=request_id,
    )


@mcp.tool(name="freeze_cq")
def tool_freeze_cq(run_id: str, request_id: str | None = None) -> dict[str, Any]:
    """Freeze the reviewed competency-question pool.

    Review and freeze are different actions: freezing requires a recorded
    user decision for every published question, otherwise the Runner
    rejection is passed through unchanged.
    """
    return _call(freeze_cq, run_id, request_id=request_id)


@mcp.tool(name="complete_cq_handoff")
def tool_complete_cq_handoff(
    run_id: str,
    freeze_id: str,
    freeze_digest: str,
    delivery_binding: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Release the CQ production handoff after the pool is frozen.

    Bindings come from the ``cq_handoff`` pending item.  Success moves the
    run to ``acceptance_pending`` and reports the acceptance attempt id and
    report directory; in-flight or unknown staged writes keep their
    original typed rejection.  A completed handoff is not the whole run's
    completion.
    """
    return _call(
        complete_cq_handoff,
        run_id,
        freeze_id=freeze_id,
        freeze_digest=freeze_digest,
        delivery_binding=delivery_binding,
        request_id=request_id,
    )


@mcp.tool(name="complete_cq_acceptance")
def tool_complete_cq_acceptance(
    run_id: str,
    acceptance_attempt_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Close the acceptance loop after the CLI ``cq-acceptance`` report.

    The tool computes ``report_digest`` and ``cq_verdict`` from the retained
    ``batch-report.json`` of the registered attempt and submits the strict
    ``cq_acceptance_complete`` envelope; the Runner re-verifies with the
    same pure helpers.  Completion success is not an acceptance PASS.
    """
    return _call(
        complete_cq_acceptance,
        run_id,
        acceptance_attempt_id=acceptance_attempt_id,
        request_id=request_id,
    )


@mcp.tool(name="resolve_issue")
def tool_resolve_issue(
    run_id: str,
    issue_id: str,
    reporter_id: str,
    control_epoch: int,
    resolution_type: str,
    resolution_text: str | None = None,
    repair_component: str | None = None,
    before_digest: str | None = None,
    after_digest: str | None = None,
    verification_reference: str | None = None,
    mutation_reconciliation: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Submit the cooperative resolution for the current issue wait.

    Bindings come from the ``issue_wait`` pending item; guidance and abort
    resolutions require ``resolution_text``, repair_completed additionally
    binds ``repair_component``.  This is the only issue-resolution channel:
    plain answer texts never impersonate a repair notice, and stale
    epoch/reporter bindings keep the original Runner rejection.
    """
    return _call(
        resolve_issue,
        run_id,
        issue_id=issue_id,
        reporter_id=reporter_id,
        control_epoch=control_epoch,
        resolution_type=resolution_type,
        resolution_text=resolution_text,
        repair_component=repair_component,
        before_digest=before_digest,
        after_digest=after_digest,
        verification_reference=verification_reference,
        mutation_reconciliation=mutation_reconciliation,
        request_id=request_id,
    )


@mcp.tool(name="recover_provider")
def tool_recover_provider(
    run_id: str,
    text: str,
    agent_id: str | None = None,
    role: str | None = None,
    wait_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Take over one pending provider wait with a host recovery text.

    Exactly one of ``agent_id`` or ``role`` identifies the wait (bindings
    from the ``provider_wait`` pending item).  Recovery does not switch
    models, rebuild threads or open a new run; the Runner re-checks the
    pending wait at admission time.
    """
    return _call(
        recover_provider,
        run_id,
        text=text,
        agent_id=agent_id,
        role=role,
        wait_id=wait_id,
        request_id=request_id,
    )


@mcp.tool(name="get_request_result")
def tool_get_request_result(
    run_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Check the processing result of one submitted request (design §5.4).

    Outcome order: Runner receipt ``accepted``/``rejected`` with evidence
    references; ledger-only while the run may still be alive →
    ``submitted``; ledger-only after a terminal state or channel loss →
    ``unknown``; no ledger entry → ``request_id_unknown``.  Acceptance is
    not modeling progress: follow the consumption evidence.
    """
    return _call(get_request_result, run_id, request_id=request_id)


# The 12 fixed S1 tool names exposed on the wire (each ``@mcp.tool(name=...)``
# above registers exactly one; S2 lifecycle/checkpoint names are absent).
TOOL_NAMES = (
    "get_run_status",
    "get_run_events",
    "get_pending_actions",
    "answer_question",
    "register_question",
    "submit_cq_review",
    "freeze_cq",
    "complete_cq_handoff",
    "complete_cq_acceptance",
    "resolve_issue",
    "recover_provider",
    "get_request_result",
)


def main() -> None:
    """Run the stdio MCP server (host-side process)."""

    mcp.run()


if __name__ == "__main__":
    main()
