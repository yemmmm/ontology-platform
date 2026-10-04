"""R3.0-016 S1+S2 host-only MCP tool surface (交付设计 §3/§4/§5).

A stdio MCP server named ``modeling-team-host`` exposing exactly the fixed
20 tools over the local operation layer :mod:`modeling_team.host_ops`: the
12 read/submission tools of S1 plus the 8 S2 start/lifecycle/checkpoint
tools (``start_run``, ``pause_run``, ``resume_live_run``, ``stop_run``,
``inspect_checkpoints``, ``save_checkpoint``, ``resume_from_checkpoint``,
``settle_source_run``).  Every tool is a thin typed wrapper: parameters map
to the op-layer function, ``HostOpError`` becomes the design §9
``{ok: False, error}`` envelope, and success returns ``{ok: True, data}``.
No business semantics, natural-language interpretation or auto-approval
lives here: the launch pre-checks, the process registration and the
credential gate are all in the op layer, and the platform credential is
injected through the host process environment only (never a server config
``env`` block, never a tool argument).

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
    inspect_checkpoints,
    pause_run,
    recover_provider,
    register_question,
    resolve_issue,
    resume_from_checkpoint,
    resume_live_run,
    save_checkpoint,
    settle_source_run,
    start_run,
    stop_run,
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


@mcp.tool(name="start_run")
def tool_start_run(
    run_id: str,
    task: str,
    profile: str,
    model_profile: str,
    scope: str,
    freeze_started_at: str,
    task_overlay: str | None = None,
    base_url: str | None = None,
    request_id: str | None = None,
    service_tier: str = "unset",
) -> dict[str, Any]:
    """Start exactly one managed modeling Team run (design §5.1).

    Encapsulates ``python -m modeling_team run`` with the CLI's real
    parameters, detached in its own session, registered under
    ``workspaces/modeling-runs/.host-launches/<run_id>.json`` before the
    process exists.  ``freeze_started_at`` must be the real freeze-start
    record of this round and is only shape-checked (timezone-aware
    ISO-8601); the tool never fills in the current time.  A run id that
    already exists, a live registration or a dead one is reported instead of
    silently reusing it, and no old run is ever stopped implicitly.  Launch
    accepted is not a semantic start: read ``get_run_status``.
    ``service_tier`` is unset (inherit), fast, or default (explicit off),
    affecting only the new child environment, never existing threads.
    """
    return _call(
        start_run,
        run_id=run_id,
        task=task,
        profile=profile,
        model_profile=model_profile,
        scope=scope,
        freeze_started_at=freeze_started_at,
        task_overlay=task_overlay,
        base_url=base_url,
        request_id=request_id,
        service_tier=service_tier,
    )


@mcp.tool(name="pause_run")
def tool_pause_run(run_id: str, request_id: str | None = None) -> dict[str, Any]:
    """Pause one live run through its outer-input FIFO (design §5.2).

    A pause is not a stop: the run keeps its processes, threads and evidence
    and is continued with ``resume_live_run``.  Submitted lines are recorded
    in the host submission ledger and answered by the Runner receipt; poll
    ``get_request_result``.
    """
    return _call(pause_run, run_id, request_id=request_id)


@mcp.tool(name="resume_live_run")
def tool_resume_live_run(
    run_id: str, request_id: str | None = None
) -> dict[str, Any]:
    """Continue the same live thread of a paused run (design §5.2).

    Only continues the existing thread: never rebuilds one, never hot-loads
    code or frozen inputs, and never silently becomes a 015 checkpoint
    continuation — a stopped or already ended run continues exclusively
    through ``resume_from_checkpoint``.
    """
    return _call(resume_live_run, run_id, request_id=request_id)


@mcp.tool(name="stop_run")
def tool_stop_run(
    run_id: str,
    reason: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Stop one run through its existing stop channel (design §5.2).

    Stop is not pause: it carries the existing cleanup and keeps unknown
    writes behind their own reconciliation boundary.  ``reason`` is only
    recorded in the host submission ledger and its digest — the Runner's
    stop branch does not read it.  After the stop, follow-up work goes
    through the retained CLI records or ``settle_source_run``.
    """
    return _call(stop_run, run_id, reason=reason, request_id=request_id)


@mcp.tool(name="inspect_checkpoints")
def tool_inspect_checkpoints(
    run_id: str, checkpoint_id: str | None = None
) -> dict[str, Any]:
    """Read-only inspection of a run's published checkpoint packages (§5.3).

    Passes through the existing 015 inspection: the package list, or the
    detail of one explicit ``checkpoint_id`` (production resume bindings,
    verify results, semantic-start accounting).  Nothing is modified, no
    recovery is triggered, and no platform write or model call happens.
    """
    return _call(
        inspect_checkpoints, run_id, checkpoint_id=checkpoint_id
    )


@mcp.tool(name="save_checkpoint")
def tool_save_checkpoint(
    run_id: str,
    kind: str,
    scope_refs: dict[str, Any] | None = None,
    command: str = "save",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Ask a live run to publish one checkpoint package (design §5.4).

    Submits the outer ``action=checkpoint`` envelope with the single
    top-level ``request_id`` that also lands in the 015 manifest provenance;
    kind and selector validation stays with the Runner, so its original
    codes (``checkpoint_invalid_kind``, ``checkpoint_write_unreconciled``,
    ...) come back unchanged.  Frozen results are never edited and no
    historical checkpoint is back-filled.
    """
    return _call(
        save_checkpoint,
        run_id,
        kind=kind,
        scope_refs=scope_refs,
        command=command,
        request_id=request_id,
    )


@mcp.tool(name="resume_from_checkpoint")
def tool_resume_from_checkpoint(
    source_run_id: str,
    checkpoint_id: str,
    new_run_id: str,
    mode: str,
    authorization_reference: str,
    freeze_started_at: str | None = None,
    session_timeout: float | None = None,
    model_profile: str | None = None,
    question_visibility: str = "hidden",
    request_id: str | None = None,
    fork_reason: str | None = None,
    service_tier: str = "unset",
) -> dict[str, Any]:
    """Resume one explicit published checkpoint as a fresh managed run (§5.5).

    ``--run-id`` is the SOURCE run id and ``new_run_id`` the fresh one; the
    checkpoint id is never auto-selected.  ``mode='production'`` requires
    the NEW run's real ``freeze_started_at`` (never the source run's old
    timepoint); ``mode='acceptance'`` rejects it and may pass
    ``session_timeout`` and an explicit ``model_profile`` for Examiner/Judge.
    The platform credential must be present in the
    host environment (``ONTOLOGY_PLATFORM_ADMIN_API_KEY``) or the tool
    refuses before starting anything.  The source run is never overwritten.
    ``service_tier`` has the same per-child unset/fast/default semantics as
    start_run. Production resumes keep the source model profile; only
    acceptance mode supports an explicit model_profile override.
    """
    return _call(
        resume_from_checkpoint,
        source_run_id=source_run_id,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        mode=mode,
        authorization_reference=authorization_reference,
        freeze_started_at=freeze_started_at,
        session_timeout=session_timeout,
        model_profile=model_profile,
        question_visibility=question_visibility,
        request_id=request_id,
        service_tier=service_tier,
        **({"fork_reason": fork_reason} if fork_reason is not None else {}),
    )


@mcp.tool(name="settle_source_run")
def tool_settle_source_run(
    source_run_id: str,
    stop_reference: str,
    base_url: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Record the settlement of an existing controlled stop (design §5.6).

    Calls the same in-process 015 settlement the CLI uses, with the same
    readback construction and the same
    ``workspaces/modeling-runs/.recovery-settlements/<run_id>.json`` record
    path.  A refusal keeps its original typed code: an unfound process is
    never treated as proof that the writer stopped, unknown writes are not
    cleared, and no authorization judgement is made.  Requires the host
    platform credential in the environment.
    """
    return _call(
        settle_source_run,
        source_run_id,
        stop_reference=stop_reference,
        **({"base_url": base_url} if base_url is not None else {}),
        request_id=request_id,
    )


# The fixed tool names exposed on the wire (each ``@mcp.tool(name=...)`` above
# registers exactly one): the 12 S1 read/submission tools plus the 8 S2
# start/lifecycle/checkpoint tools.  Nothing outside these 20 may appear on
# this server, and none of them may appear on a production or role surface.
S1_TOOL_NAMES = (
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
S2_TOOL_NAMES = (
    "start_run",
    "pause_run",
    "resume_live_run",
    "stop_run",
    "inspect_checkpoints",
    "save_checkpoint",
    "resume_from_checkpoint",
    "settle_source_run",
)
TOOL_NAMES = S1_TOOL_NAMES + S2_TOOL_NAMES


def main() -> None:
    """Run the stdio MCP server (host-side process)."""

    mcp.run()


if __name__ == "__main__":
    main()
