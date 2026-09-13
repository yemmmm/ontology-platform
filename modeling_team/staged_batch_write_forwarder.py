"""Host-side write forwarders for the protocol staged channel.

The staged capabilities only project a platform write into the Protocol role's private
surface; the write itself is the host's job, because the Runner -- not the Protocol agent --
holds the credential authority for the canonical backend (design section 3.6).  There are
two projections, one function each:

* ``protocol_staged_submit_modeling_batch`` -> ``forward_staged_modeling_batch``.  Until
  this module existed, no production ``TeamRunner`` ever received a
  ``staged_batch_forwarder``, so every staged submission stopped at the fail-closed guard in
  ``TeamRunner._handle_staged_submit_modeling_batch`` and no batch was ever written.
* ``protocol_staged_associate_evidence`` -> ``forward_staged_associate_evidence``
  (R3.0-008B/#17).  A staged batch materializes items whose lineage the terminal retrieval
  gate scores, so the staged run must also be able to attach the owner-authorized evidence
  those items need; without this projection the gate is unsatisfiable for any run that
  materializes before the owner answers (auth010 start4, item ``e80f85b1``).

Shape: one synchronous function that owns exactly one canonical stdio MCP child per call.
The Runner invokes it from the capability endpoint's plain serving thread
(``capability_mcp.RunnerCapabilityEndpoint._serve``), which runs no event loop, so
``asyncio.run`` is safe there and the child is created, used and torn down inside the one
call.  Deliberately no queue, worker thread, cached session, start/stop lifecycle or tool
allowlist surface: each callable accepts its own envelope and can only reach its own fixed
tools — the batch forwarder its canonical write plus the single controlled
``get_modeling_batch`` read-back of what that write produced (R3.0-014 design §3.2), the
evidence forwarder its one association — so the CLI may bind them right after ``prepare``
and resolve the per-run protocol key lazily.

Both envelopes are forwarded verbatim.  Responses are classified against the Runner's
existing failure taxonomy rather than a new one.  ``StagedBatchForwardError`` (definite,
nothing written) is reserved for what the canonical code proves is pre-write: a refusal by
this host before the child is handed the envelope, the MCP argument-validation rejection
that runs before the tool body, and the service's own explicit rejection codes as listed
per tool.  Every other reply that carries no write evidence is ``StagedBatchForwardUnknown``
(timeout, transport loss, unparseable reply, an acknowledgement without the payload the
caller needs, and any error code that tool's path can reach *after* it commits).  The batch
caller then marks the intent unknown and latches its submission kill switch, which is why an
uncertain batch must never be reported as definite regardless of backend idempotency; the
evidence caller has no such latch because the association is idempotent by
``(ontology, target, reference)``, so an indeterminate or definite refusal is simply
retryable.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .protocol_mcp_launch import canonical_protocol_mcp_mode_contract
from .staged_decisions import StagedBatchForwardError, StagedBatchForwardUnknown

#: The only tool the batch forwarder can reach: the canonical batch write.
WRITE_TOOL = "submit_modeling_batch"

#: R3.0-014 (design §3.2): the only read the batch forwarder may perform, in the
#: same child/session directly after a successful write, to carry back the
#: stored ``content_hash`` and the authoritative Batch/Attempt listing the
#: Runner's apply gate proofs bind to.  A read-back failure never re-submits;
#: it leaves the already-dispatched write to the existing reconciliation.
READ_TOOL = "get_modeling_batch"

#: The only tool the evidence forwarder can reach: the canonical evidence association.
ASSOCIATE_EVIDENCE_TOOL = "associate_evidence_reference"

#: Bounded budget for the whole call, matching the slowest existing canonical tool latency.
DEFAULT_CALL_TIMEOUT_SECONDS = 120.0

#: The service's own explicit precondition rejections, and the only ``ok: false`` codes that
#: prove the batch was refused before anything was committed.  Every one of these is raised
#: by ``ModelingBatchService.submit``/``BuildSessionService.authorize_apply`` (or by
#: ``_check_capacity`` / ``_authorize_tool``) ahead of the first ``session.commit()`` in the
#: submit path (``backend/app/services/modeling_batches.py``, ``build_sessions.py``), so none
#: of them can follow a graph write.  Anything else -- ``dependency_error``,
#: ``internal_error``, the generic ``validation_error``/``not_found``/``conflict`` mappings of
#: ``map_exception``, or a code this build does not know -- may be raised by the commit
#: response or the execute phase and therefore stays indeterminate.
DEFINITE_REJECTION_CODES = frozenset(
    {
        # permission
        "forbidden",
        "forbidden_scope",
        # request shape
        "request_too_large",
        "batch_limit_exceeded",
        "operation_secret_forbidden",
        "invalid_lease_token",
        # build session
        "build_session_not_found",
        "build_session_not_active",
        "session_terminal",
        "session_revision_conflict",
        "in_flight_batch",
        # ontology and workspace
        "ontology_not_found",
        "project_not_found",
        "workspace_revision_conflict",
        "ontology_write_fenced",
        # ontology lease
        "ontology_lease_conflict",
        "lease_expired",
        "lease_token_invalid",
        "lease_revision_conflict",
        # idempotency and prior attempt state
        "idempotency_conflict",
        "batch_failed",
    }
)

#: The service's own explicit refusals on the evidence path, and the only ``ok: false`` codes
#: that prove the association was rejected before anything was committed.  The whole
#: ``EvidenceReference`` rejection family (``backend/app/services/evidence_reference.py``,
#: mapped by ``app.mcp.runtime.map_exception``) is raised while resolving or validating the
#: target/reference pair, ahead of the single ``session.commit()`` that persists the
#: association; everything else -- ``internal_error``, ``dependency_error``, the generic
#: ``conflict`` mapping, or a code this build does not know -- stays indeterminate.
#: An association is idempotent by ``(ontology, target, reference)``, so an indeterminate
#: reply only costs a retry: it is never reported as definite, and it never needs the batch
#: submission kill switch.
ASSOCIATE_DEFINITE_REJECTION_CODES = frozenset(
    {
        # permission
        "forbidden",
        "forbidden_scope",
        # request shape
        "request_too_large",
        # evidence reference and target scope
        "validation_error",
        "not_found",
    }
)


def _args_validation_marker(tool: str) -> str:
    """FastMCP's generated argument model name: ``<tool>Arguments``.

    Argument validation runs before the tool body, so a reply carrying this marker is the
    one tool-level error that proves the call never reached the service.  FastMCP only
    reports it as free text, so the marker is matched against the tool the caller asked
    for; the same text for another tool would not be evidence about this call.
    """

    return f"for {tool}Arguments"


def forward_staged_modeling_batch(
    batch: Mapping[str, Any],
    *,
    repository_root: str | os.PathLike[str],
    protocol_key: str | None,
    command: str | None = None,
    args: Sequence[str] | None = None,
    call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT_SECONDS,
) -> Mapping[str, Any]:
    """Write one staged batch through the canonical backend MCP server.

    ``batch`` is the platform envelope built by the Runner and is forwarded unmodified.
    ``protocol_key`` is the run's own protocol credential; it is resolved by the caller at
    call time because the run record only carries it once the run has started.  Returns the
    backend ``data`` mapping of the write — which always carries the Attempt identity the
    Runner receipts on — merged with the read-back ``content_hash`` (R3.0-014 design §3.2).

    R3.0-014: after an accepted write the same child/session performs exactly one
    ``get_modeling_batch`` read-back and the reply's Batch/Attempt identity is bound to the
    submitted envelope.  A read-back that cannot be verified is an unknown outcome — the
    write may well have committed — so the caller's existing unknown reconciliation owns it;
    the forwarder never retries or re-submits.
    """

    if not isinstance(batch, Mapping):
        raise StagedBatchForwardError(f"{WRITE_TOOL} requires the platform batch envelope")
    if not isinstance(protocol_key, str) or not protocol_key:
        raise StagedBatchForwardError("the run protocol key is unavailable for the write forwarder")

    root = Path(repository_root)
    backend_root = root / "backend"
    payload = dict(batch)
    state = {"dispatched": False}
    try:
        return asyncio.run(
            _forward_write_with_readback(
                payload,
                env=_child_environment(backend_root=backend_root, protocol_key=protocol_key),
                cwd=str(backend_root),
                command=command or str(backend_root / ".venv" / "bin" / "python"),
                args=list(args or ["-m", "app.mcp.server"]),
                read_timeout=timedelta(seconds=call_timeout_seconds),
                state=state,
            )
        )
    except (StagedBatchForwardError, StagedBatchForwardUnknown):
        raise
    except BaseException as exc:  # noqa: BLE001 - classified below by dispatch state
        if state["dispatched"]:
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} did not return a usable reply after dispatch: {exc}"
            ) from exc
        raise StagedBatchForwardError(
            f"{WRITE_TOOL} could not be reached and nothing was written: {exc}"
        ) from exc


def forward_staged_associate_evidence(
    association: Mapping[str, Any],
    *,
    repository_root: str | os.PathLike[str],
    protocol_key: str | None,
    command: str | None = None,
    args: Sequence[str] | None = None,
    call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT_SECONDS,
) -> Mapping[str, Any]:
    """Attach one evidence association through the canonical backend MCP server.

    ``association`` is exactly the envelope the Protocol role addressed to the capability
    (the capability schema already bounds it to the platform tool's own parameters;
    the ``actor`` argument the platform tool also declares is deliberately not part of
    that envelope, so the platform always derives the actor from the Runner's credential).
    It is forwarded unmodified.  ``protocol_key`` is the run's own protocol credential,
    resolved by the caller at call time because the run record only carries it once the run
    has started.  Returns the backend ``data`` mapping, which always carries the
    ``items``/``total`` the role reads back.
    """

    if not isinstance(association, Mapping):
        raise StagedBatchForwardError(
            f"{ASSOCIATE_EVIDENCE_TOOL} requires the platform association envelope"
        )
    if not isinstance(protocol_key, str) or not protocol_key:
        raise StagedBatchForwardError(
            "the run protocol key is unavailable for the evidence forwarder"
        )

    root = Path(repository_root)
    backend_root = root / "backend"
    payload = dict(association)
    state = {"dispatched": False}
    try:
        return asyncio.run(
            _forward_once(
                payload,
                tool=ASSOCIATE_EVIDENCE_TOOL,
                decode=_decode_associate_result,
                env=_child_environment(backend_root=backend_root, protocol_key=protocol_key),
                cwd=str(backend_root),
                command=command or str(backend_root / ".venv" / "bin" / "python"),
                args=list(args or ["-m", "app.mcp.server"]),
                read_timeout=timedelta(seconds=call_timeout_seconds),
                state=state,
            )
        )
    except (StagedBatchForwardError, StagedBatchForwardUnknown):
        raise
    except BaseException as exc:  # noqa: BLE001 - classified below by dispatch state
        if state["dispatched"]:
            raise StagedBatchForwardUnknown(
                f"{ASSOCIATE_EVIDENCE_TOOL} did not return a usable reply after dispatch: {exc}"
            ) from exc
        raise StagedBatchForwardError(
            f"{ASSOCIATE_EVIDENCE_TOOL} could not be reached and nothing was written: {exc}"
        ) from exc


def _child_environment(*, backend_root: Path, protocol_key: str) -> dict[str, str]:
    """The allowlisted child environment: the protocol key plus the canonical mode contract.

    Mirrors the host-side ``McpReadForwarder`` discipline: nothing is inherited, so no
    broader platform key, proxy, plugin or Codex credential can reach the canonical server.
    """

    environment = {
        "ONTOLOGY_MCP_API_KEY": protocol_key,
        "PYTHONPATH": str(backend_root),
        # The child runs with ``cwd=backend_root`` and therefore reads ``backend/.env``,
        # whose reasoner command is a stale absolute path on this host.  Pin both the
        # reasoner script and the executable path here, as the canonical protocol launch
        # contract does for the sandbox (``protocol_mcp_launch._REASONER_ENV``), so the
        # canonical server never resolves a reasoner that does not exist.
        "SEMANTIC_REASONER_COMMAND": str(backend_root / "scripts" / "dev_owl_reasoner.py"),
        "PATH": f"{backend_root / '.venv' / 'bin'}:/usr/bin:/bin",
        "HOME": str(backend_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    environment.update(canonical_protocol_mcp_mode_contract())
    return environment


async def _forward_once(
    payload: Mapping[str, Any],
    *,
    tool: str,
    decode: Callable[[Any], Mapping[str, Any]],
    env: Mapping[str, str],
    cwd: str,
    command: str,
    args: list[str],
    read_timeout: timedelta,
    state: dict[str, bool],
) -> Mapping[str, Any]:
    """One child, one session, one call: closed by the surrounding contexts either way."""

    parameters = StdioServerParameters(command=command, args=args, env=dict(env), cwd=cwd)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, write_stream, read_timeout_seconds=read_timeout
        ) as session:
            # Startup, handshake and authentication all happen before the envelope is handed
            # over, so a failure up to here is provably pre-write.
            await session.initialize()
            state["dispatched"] = True
            result = await session.call_tool(
                tool, dict(payload), read_timeout_seconds=read_timeout
            )
    return decode(result)


async def _forward_write_with_readback(
    payload: Mapping[str, Any],
    *,
    env: Mapping[str, str],
    cwd: str,
    command: str,
    args: list[str],
    read_timeout: timedelta,
    state: dict[str, bool],
) -> Mapping[str, Any]:
    """R3.0-014: one child, one session, the canonical write, then the read-back.

    The write is decoded with the definite/unknown classification as before; once it is
    accepted, every later failure in this function is an *unknown* outcome (the write may
    have committed), which is exactly how the caller's exception handling classifies it
    because ``state["dispatched"]`` is already true.

    Classification raises only after both contexts have closed, exactly as
    ``_forward_once`` decodes outside them: an exception raised inside the stdio
    context is re-raised by anyio's task group as an ``ExceptionGroup``, which would
    strip the Runner-facing class and message the taxonomy depends on.
    """

    parameters = StdioServerParameters(command=command, args=args, env=dict(env), cwd=cwd)
    readback_result = None
    failure: BaseException | None = None
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, write_stream, read_timeout_seconds=read_timeout
        ) as session:
            await session.initialize()
            state["dispatched"] = True
            write_result = await session.call_tool(
                WRITE_TOOL, dict(payload), read_timeout_seconds=read_timeout
            )
            try:
                data = _decode_write_result(write_result, expected_mode=payload.get("mode"))
            except BaseException as exc:  # noqa: BLE001 - re-raised below, after teardown
                failure = exc
            else:
                # From here the write is accepted: a read-back failure is never
                # re-submitted, it only makes the outcome indeterminate for the
                # existing reconciliation.
                readback_result = await session.call_tool(
                    READ_TOOL,
                    {"batch_id": data["batch_id"]},
                    read_timeout_seconds=read_timeout,
                )
    if failure is not None:
        raise failure
    detail = _decode_readback_result(readback_result)
    return _merge_verified_attempt(data, detail, payload=payload)


def _decode_write_result(result: Any, *, expected_mode: Any = None) -> Mapping[str, Any]:
    """Classify one backend ``submit_modeling_batch`` reply."""

    data = _decode_tool_result(
        result, tool=WRITE_TOOL, definite_codes=DEFINITE_REJECTION_CODES
    )
    if not data.get("batch_id"):
        # Accepted but unidentifiable: the Runner cannot receipt it and must not claim
        # the batch was not written.
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} was acknowledged without a batch identity, so the batch outcome is unknown"
        )
    # R3.0-014 (design §3.2): an accepted reply must name the Attempt it created or
    # replayed.  Without ``attempt_id``/``mode``/``attempt_status`` the Runner has no
    # platform-verifiable result to bind a proof to, so the outcome stays unknown rather
    # than letting a bare receipt pose as one.
    for field in ("attempt_id", "mode", "attempt_status"):
        if not data.get(field):
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} was acknowledged without the Attempt identity field "
                f"{field!r}, so the batch outcome is unknown"
            )
    if expected_mode is not None and data.get("mode") != expected_mode:
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} acknowledged a {data.get('mode')!r} attempt for a "
            f"{expected_mode!r} request, so the batch outcome is unknown"
        )
    return data


def _decode_readback_result(result: Any) -> Mapping[str, Any]:
    """Classify one ``get_modeling_batch`` read-back reply.

    The read follows an accepted write, so there are no definite rejections here at
    all: every failure — transport, error code, missing payload — means the write's
    outcome cannot be verified and stays unknown.
    """

    data = _decode_tool_result(result, tool=READ_TOOL, definite_codes=frozenset())
    if not data.get("batch_id"):
        raise StagedBatchForwardUnknown(
            f"{READ_TOOL} returned no batch identity, so the write outcome is unknown"
        )
    if not isinstance(data.get("attempts"), list):
        raise StagedBatchForwardUnknown(
            f"{READ_TOOL} returned no Attempt listing, so the write outcome is unknown"
        )
    return data


def _merge_verified_attempt(
    data: Mapping[str, Any], detail: Mapping[str, Any], *, payload: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Bind the read-back Batch/Attempt to the submitted envelope (design §3.2).

    The read-back must show the same batch, list the submitted Attempt, and agree with
    both the submit reply and the original request on client batch, idempotency key,
    mode and status.  Any disagreement is a platform-contract failure on a possibly
    committed write: unknown, never definite and never retried here.
    """

    if str(detail.get("batch_id")) != str(data.get("batch_id")):
        raise StagedBatchForwardUnknown(
            f"{READ_TOOL} returned batch {detail.get('batch_id')!r} for "
            f"{data.get('batch_id')!r}, so the write outcome is unknown"
        )
    attempt = next(
        (
            entry
            for entry in detail["attempts"]
            if isinstance(entry, Mapping)
            and str(entry.get("attempt_id")) == str(data.get("attempt_id"))
        ),
        None,
    )
    if attempt is None:
        raise StagedBatchForwardUnknown(
            f"{READ_TOOL} does not list the submitted Attempt {data.get('attempt_id')!r}, "
            "so the write outcome is unknown"
        )
    for field, expected in (
        ("client_batch_id", payload.get("client_batch_id")),
        ("idempotency_key", payload.get("idempotency_key")),
        ("mode", payload.get("mode")),
        ("attempt_status", data.get("attempt_status")),
    ):
        if attempt.get(field) != expected:
            raise StagedBatchForwardUnknown(
                f"{READ_TOOL} attempt disagrees on {field!r} "
                f"({attempt.get(field)!r} != {expected!r}), so the write outcome is unknown"
            )
    content_hash = detail.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash:
        raise StagedBatchForwardUnknown(
            f"{READ_TOOL} returned no batch content hash, so the write outcome is unknown"
        )
    merged = dict(data)
    merged["content_hash"] = content_hash
    return merged


def _decode_associate_result(result: Any) -> Mapping[str, Any]:
    """Classify one backend ``associate_evidence_reference`` reply."""

    data = _decode_tool_result(
        result, tool=ASSOCIATE_EVIDENCE_TOOL, definite_codes=ASSOCIATE_DEFINITE_REJECTION_CODES
    )
    if not isinstance(data.get("items"), list):
        # Acknowledged without the association rows: the role cannot read the
        # association back and the platform outcome must not be reported as definite.
        raise StagedBatchForwardUnknown(
            f"{ASSOCIATE_EVIDENCE_TOOL} was acknowledged without the associated evidence "
            f"items, so the association outcome is unknown"
        )
    return data


def _decode_tool_result(
    result: Any, *, tool: str, definite_codes: frozenset[str]
) -> Mapping[str, Any]:
    """Classify one backend tool reply onto the Runner's forwarder contract."""

    detail = _text_body(result)
    if getattr(result, "isError", False):
        if detail is not None and _args_validation_marker(tool) in detail:
            # Argument validation precedes the tool body, so the service never saw this call.
            raise StagedBatchForwardError(
                f"{tool} rejected the envelope before any write: {detail}"
            )
        # Any other tool-level failure may have happened inside or after the body.
        raise StagedBatchForwardUnknown(
            f"{tool} failed at the tool boundary, so the outcome is unknown: "
            f"{detail or 'no detail'}"
        )
    envelope = getattr(result, "structuredContent", None)
    if not isinstance(envelope, Mapping):
        if detail is None:
            raise StagedBatchForwardUnknown(
                f"{tool} returned no readable body, so the outcome is unknown"
            )
        try:
            envelope = json.loads(detail)
        except ValueError as exc:
            raise StagedBatchForwardUnknown(
                f"{tool} returned an unparseable body, so the outcome is unknown"
            ) from exc
    if not isinstance(envelope, Mapping):
        raise StagedBatchForwardUnknown(
            f"{tool} returned a non-envelope body, so the outcome is unknown"
        )
    if envelope.get("ok") is False:
        code = str(envelope.get("error_code") or "")
        message = envelope.get("error") or "no detail"
        if code in definite_codes:
            raise StagedBatchForwardError(
                f"{tool} was rejected before any write ({code}): {message}"
            )
        # Both write paths commit before they build this response, so an error here can
        # follow a committed attempt: never claim the write did not happen.
        raise StagedBatchForwardUnknown(
            f"{tool} reported {code or 'an unclassified error'} after dispatch and the "
            f"outcome is unknown: {message}"
        )
    if envelope.get("ok") is not True:
        raise StagedBatchForwardUnknown(
            f"{tool} returned no accepted/rejected verdict, so the outcome is unknown"
        )
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise StagedBatchForwardUnknown(
            f"{tool} was acknowledged without a payload, so the outcome is unknown"
        )
    return dict(data)


def _text_body(result: Any) -> str | None:
    """The first text part of an MCP tool reply, if the server sent one."""

    for part in getattr(result, "content", None) or ():
        text = getattr(part, "text", None)
        if isinstance(text, str) and text:
            return text
    return None
