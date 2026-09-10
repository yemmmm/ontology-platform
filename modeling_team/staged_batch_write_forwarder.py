"""Host-side write forwarder for the protocol staged submission channel.

The staged capability ``protocol_staged_submit_modeling_batch`` only records a durable
submission intent; the platform write itself is the host's job, because the Runner -- not
the Protocol agent -- holds the credential authority for the canonical backend (design
section 3.6).  Until this module existed, no production ``TeamRunner`` ever received a
``staged_batch_forwarder``, so every staged submission stopped at the fail-closed guard in
``TeamRunner._handle_staged_submit_modeling_batch`` and no batch was ever written.

Shape: one synchronous function that owns exactly one canonical stdio MCP child per batch
call.  The Runner invokes it from the capability endpoint's plain serving thread
(``capability_mcp.RunnerCapabilityEndpoint._serve``), which runs no event loop, so
``asyncio.run`` is safe there and the child is created, used and torn down inside the one
call.  Deliberately no queue, worker thread, cached session, start/stop lifecycle or tool
allowlist surface: the callable accepts a batch and can only reach the one fixed write
tool, so the CLI may bind it right after ``prepare`` and resolve the per-run protocol key
lazily.

The batch envelope is forwarded verbatim.  Responses are classified against the Runner's
existing failure taxonomy rather than a new one.  ``StagedBatchForwardError`` (definite,
nothing written) is reserved for what the canonical code proves is pre-write: a refusal by
this host before the child is handed the batch, the MCP argument-validation rejection that
runs before the tool body, and the service's own explicit precondition rejections.  Every
other reply that carries no write evidence is ``StagedBatchForwardUnknown`` (timeout,
transport loss, unparseable reply, success without a batch identity, and any error code the
submit path can reach *after* it commits) -- the Runner then marks the intent unknown and
latches its submission kill switch, which is why an uncertain batch must never be reported
as definite regardless of backend idempotency.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .protocol_mcp_launch import canonical_protocol_mcp_mode_contract
from .staged_decisions import StagedBatchForwardError, StagedBatchForwardUnknown

#: The only tool this forwarder can reach: the canonical batch write.
WRITE_TOOL = "submit_modeling_batch"

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

#: FastMCP validates the call against the tool signature before the tool body runs, and names
#: its generated argument model ``<tool>Arguments``; a reply carrying this marker is the one
#: tool-level error that proves the batch never reached the service.
_ARGS_VALIDATION_MARKER = f"for {WRITE_TOOL}Arguments"


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
    backend ``data`` mapping, which always carries the ``batch_id`` the Runner needs for its
    receipt.
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
            _forward_once(
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
            # Startup, handshake and authentication all happen before the batch is handed
            # over, so a failure up to here is provably pre-write.
            await session.initialize()
            state["dispatched"] = True
            result = await session.call_tool(
                WRITE_TOOL, dict(payload), read_timeout_seconds=read_timeout
            )
    return _decode_write_result(result)


def _decode_write_result(result: Any) -> Mapping[str, Any]:
    """Classify one backend tool reply onto the Runner's forwarder contract."""

    detail = _text_body(result)
    if getattr(result, "isError", False):
        if detail is not None and _ARGS_VALIDATION_MARKER in detail:
            # Argument validation precedes the tool body, so the service never saw this batch.
            raise StagedBatchForwardError(
                f"{WRITE_TOOL} rejected the batch envelope before any write: {detail}"
            )
        # Any other tool-level failure may have happened inside or after the body.
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} failed at the tool boundary, so the batch outcome is unknown: "
            f"{detail or 'no detail'}"
        )
    envelope = getattr(result, "structuredContent", None)
    if not isinstance(envelope, Mapping):
        if detail is None:
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} returned no readable body, so the batch outcome is unknown"
            )
        try:
            envelope = json.loads(detail)
        except ValueError as exc:
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} returned an unparseable body, so the batch outcome is unknown"
            ) from exc
    if not isinstance(envelope, Mapping):
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} returned a non-envelope body, so the batch outcome is unknown"
        )
    if envelope.get("ok") is False:
        code = str(envelope.get("error_code") or "")
        message = envelope.get("error") or "no detail"
        if code in DEFINITE_REJECTION_CODES:
            raise StagedBatchForwardError(
                f"{WRITE_TOOL} was rejected before any write ({code}): {message}"
            )
        # The submit path commits before it builds this response, so an error here can follow
        # a committed attempt: never claim the batch was not written.
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} reported {code or 'an unclassified error'} after dispatch and the "
            f"batch outcome is unknown: {message}"
        )
    if envelope.get("ok") is not True:
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} returned no accepted/rejected verdict, so the batch outcome is unknown"
        )
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} was acknowledged without a batch payload, so the batch outcome is unknown"
        )
    if not data.get("batch_id"):
        # Accepted but unidentifiable: the Runner cannot receipt it and must not claim
        # the batch was not written.
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} was acknowledged without a batch identity, so the batch outcome is unknown"
        )
    return dict(data)


def _text_body(result: Any) -> str | None:
    """The first text part of an MCP tool reply, if the server sent one."""

    for part in getattr(result, "content", None) or ():
        text = getattr(part, "text", None)
        if isinstance(text, str) and text:
            return text
    return None
