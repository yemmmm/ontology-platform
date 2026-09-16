from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Mapping

import yaml

from .contracts import (
    TeamConfigurationError,
    load_formal_team_configuration,
    load_multi_slice_team_configuration,
    repository_root,
    task_declares_multi_slice_workflow,
)
from .formal_runs import (
    FORMAL_PROFILE_IDS,
    FORMAL_TASK_IDS,
    FormalRunContract,
    formal_run_contract_for,
    load_formal_run_configuration,
)
from .model_routing import load_team_model_profile
from .handoff import publish_offline_scope_handoff
from .monitor_handoff import (
    HANDOFF_CONTRACT_RELATIVE_PATH,
    HANDOFF_ENV,
    load_handoff_contract,
    output_digest,
    read_phase,
    write_runner_phase,
)
from .acceptance_runtime import (
    ChildRuntimeError,
    ExaminerRuntimeBlocked,
    McpReadForwarder,
    PLATFORM_PROXY_READ_TOOLS,
    PLATFORM_READ_ARTIFACT_SCHEMA,
    build_acceptance_judge_packet,
    build_platform_batch_packet,
    canonical_read_digest,
)
from .competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
    CQ_EVIDENCE_BUNDLE_SCHEMA,
    CQ_FREEZE_SCHEMA,
    CQContractError,
    acceptance_mode_evidence,
    batch_report_is_full_pass,
    blind_batch_label,
    build_batch_report,
    content_digest,
    model_binding_drift,
    read_exposure_evidence,
    reload_frozen_pool,
    validate_evidence_bundle,
    validate_model_binding,
)
from .outer_input import OuterInputFifo, OuterInputFramingError
from .interventions import RecoverableOuterInputError
from .checkpoints import CheckpointError, inspect_checkpoints
from .checkpoint_recovery import (
    ACCEPTANCE_CONTINUATION_SCHEMA,
    acquire_root_run_lock,
    checkpoint_root_run_id,
    http_readback,
    prepare_acceptance_continuation,
    safe_new_run_id,
    scope_missing_rejection,
    write_acceptance_continuation_record,
    write_acceptance_origin,
)
from .platform_scope import PlatformScope, PlatformScopeMissingError
from .preflight import normalize_scope_for_contract
from .runner import TeamRunner
from .candidate_publication import validate_candidate_publication
from .candidate_progress import FormalCandidateProgressTimeout
from .runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
from .staged_batch_write_forwarder import (
    forward_staged_associate_evidence,
    forward_staged_modeling_batch,
)
from .start_ledger import StartLedger
from .task_overlay import load_task_input_overlay


def _bootstrap_helpers(root: Path):
    """Reuse the accepted narrow local bootstrap; Platform lifecycle remains HTTP-based."""
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    from app.core.config import Settings
    from app.repositories.models import ApiKeyModel
    from app.repositories.postgres import create_session_factory
    from app.security.auth import create_api_key, revoke_key

    def create() -> tuple[str, str]:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            record, plaintext = create_api_key(
                session,
                name="r2-3-001-team-runner-admin",
                project_id=None,
                scopes=["admin"],
            )
        return plaintext, record.id

    def revoke(key_id: str) -> bool:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            record = session.get(ApiKeyModel, key_id)
            return bool(record and revoke_key(session, record).revoked_at)

    return create, revoke


def _terminal_report_complete(runner) -> bool:
    run_root = getattr(getattr(runner, "run", None), "root", None)
    if not isinstance(run_root, Path):
        return False
    state_path = run_root / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(state, dict) and state.get("state") == "TERMINAL_REPORT_COMPLETE"


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _decode_foreground_message(line: str) -> dict[str, object]:
    if not isinstance(line, str):
        raise TeamConfigurationError("outer JSON input is invalid")
    try:
        value = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError("outer JSON input is invalid") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError("outer JSON input must be an object")
    return value


_OUTER_INPUT_REJECTION = {
    "type": "outer-input-rejected",
    "code": "invalid_outer_input",
    "retryable": True,
}
_KNOWN_OUTER_ACTIONS = frozenset(
    {
        "question",
        "issue_resolution",
        "user",
        "status",
        "pause",
        "resume",
        "stop",
        # 2026-09-14 provider-recovery: host-takeover recovery after the outer
        # owner confirms the external condition lifted.  Bound input errors are
        # typed, no-side-effect rejections; the loop keeps reading.
        "recover_provider",
        # R3.0-011: competency-question direct-channel inputs.  They are
        # dispatched by the narrow CQ branch below and never reach
        # ``receive_outer``.
        "cq_interview",
        "cq_review",
        "cq_freeze",
        "cq_handoff_complete",
        # R3.0-012: the host-only acceptance completion summary Delivery
        # sends after the independent cq-acceptance process exits.
        "cq_acceptance_complete",
        # R3.0-015 S1: host/Coordinator-originated checkpoint save/inspect
        # requests.  The Runner dispatch verifies actual published artifacts
        # on disk; agents gain no new write permission through this action.
        "checkpoint",
    }
)

# R3.0-011 competency-question direct-channel actions (dispatched before the
# fatal ``receive_outer`` boundary, and only when the runner carries CQ input
# support).  ``cq_freeze`` is the Delivery-host freeze trigger (Round 1 F2).
_CQ_OUTER_ACTIONS = frozenset(
    {
        "cq_interview",
        "cq_review",
        "cq_freeze",
        "cq_handoff_complete",
        # R3.0-012 (design §4.5): dispatched on the existing foreground FIFO
        # path; pending runs keep polling it, and the Examiner/Judge never
        # see this channel.
        "cq_acceptance_complete",
    }
)


def _foreground_issue_resolution_is_ready(runner: object) -> bool:
    """Check the cooperative issue gate without mutating Runner state.

    An outer resolution can arrive while the Runner has only recorded the
    Broker's ``reported`` callback.  Calling ``receive_outer`` in that window
    would reject the resolution and, in the foreground CLI, tear down the
    whole run.  The Coordinator pause is the boundary that makes the same
    resolution actionable; all other receive paths remain unchanged and
    retain their fatal-error behavior.

    2026-09-11 auth006-start9: ``transport.issue_ledger`` is a bound method
    on the Broker, so reading ``.state`` directly on it always returned None
    and the FIFO gate rejected every outer resolution.  Call the accessor
    first, then read the ledger state.
    """

    transport = getattr(runner, "transport", None)
    accessor = getattr(transport, "issue_ledger", None)
    issue_ledger = accessor() if callable(accessor) else accessor
    return getattr(issue_ledger, "state", None) in {"waiting_owner", "waiting_repair"}


def _handle_cq_outer_message(runner, message, emit_and_observe) -> bool:
    """R3.0-011 narrow competency-question dispatch (design §3.2).

    Returns ``True`` when ``message`` was handled here, whether accepted or
    rejected.  Expected input errors -- including a legacy run that never
    selected ``competency_question_acceptance`` (typed
    ``cq_selector_incompatible`` from the Runner selector, not a crash) --
    surface as a typed rejection envelope (object, phase, reason code, retry
    guidance) for this line only: no hidden question/answer text is echoed and
    the CLI/FIFO loop keeps reading the next input.  The same rules apply to
    stdin and FIFO lines because this helper sits on the shared foreground
    admission path.  Only a runner object without CQ input support at all (an
    embedded legacy ``Runner`` stub, not the foreground ``TeamRunner``) falls
    through to the unchanged fatal ``receive_outer`` boundary (Round 1 F5).
    """

    handler = None
    if message.get("action") in _CQ_OUTER_ACTIONS:
        handler = getattr(runner, "handle_cq_outer_input", None)
    if handler is None:
        return False
    try:
        output = handler(message)
    except CQContractError as exc:
        emit_and_observe([{"type": "cq-input-rejected", **exc.data}])
        return True
    if output:
        emit_and_observe([output])
    return True


def _handle_foreground_message(runner, line, emit_and_observe, emit_outer_input_rejection):
    """Admit one outer line through the shared stdin/FIFO admission path.

    Decode, the known-action gate, the cooperative issue-readiness gate,
    ``receive_outer``, and the foreground emit/observe acknowledgement are
    identical for stdin and FIFO lines.  Only the framing (readline vs FIFO
    byte buffering) differs; this helper owns everything after a complete line
    exists.  Typed no-side-effect outer input rejections are emitted for this
    line and the loop continues; persistence, Runtime delivery, and internal
    ``TeamConfigurationError`` failures still propagate and tear the run down.
    """
    try:
        message = _decode_foreground_message(line)
    except TeamConfigurationError:
        emit_outer_input_rejection()
        return []
    action = message.get("action")
    if not isinstance(action, str) or action not in _KNOWN_OUTER_ACTIONS:
        # A missing/unknown action is a malformed outer control-plane message.
        # Reject only this line so a later valid command can still drive the
        # live Runner; admitted actions retain the existing fatal receive_outer
        # boundary below.
        emit_outer_input_rejection()
        return []
    if (
        action == "issue_resolution"
        and not _foreground_issue_resolution_is_ready(runner)
    ):
        emit_outer_input_rejection()
        return []
    if _handle_cq_outer_message(runner, message, emit_and_observe):
        # R3.0-011: CQ inputs are fully handled ahead of the fatal boundary.
        return []
    # Only the dedicated no-side-effect outer rejection is recoverable here.
    # Persistence, Runtime delivery, and internal invariant failures retain the
    # existing fatal boundary and are deliberately not caught.
    try:
        output = runner.receive_outer(message)
    except RecoverableOuterInputError as exc:
        emit_outer_input_rejection(exc.as_dict())
        return []
    if output:
        emit_and_observe(output)
    return output


def _loop_should_exit(output) -> bool:
    """True when an admitted outer action ended the run from the host side.

    2026-09-13 auth014-start1 live evidence: after the FIFO ``stop`` action ran
    ``cleanup()`` and emitted ``[{"type": "stopped"}]``, the loop kept pumping,
    the next ``drain()`` read the destroyed children's closed App-Server stdout
    and the CLI died with ``run failed: app-server closed its output`` (exit 2)
    instead of acknowledging the requested stop.  Only the host-requested stop
    output exits here; every other output keeps the loop on its previous path.
    """

    return bool(output) and any(
        isinstance(item, dict) and item.get("type") == "stopped" for item in output
    )


def _foreground_event_loop(
    runner, stream, emit, *, outer_input=None, select_fn=select.select
) -> None:
    """Pump Runner output and admit outer input from stdin and/or the FIFO.

    Without ``outer_input`` the loop is byte-for-byte identical to the
    pre-FIFO implementation, including the immediate-EOF keep-pumping path:
    a non-interactive host may close stdin before the first read, so EOF
    retires only stdin and the loop keeps draining Runner output until the
    terminal-report gate fires.

    With ``outer_input`` (an :class:`~modeling_team.outer_input.OuterInputFifo`)
    the loop additionally selects the FIFO and applies the order rules from
    the R2.3-005 background-outer-input design:

    * drain and emit Runner output before reading outer input;
    * when stdin and FIFO are both readable, process stdin first;
    * process at most one outer message per loop iteration, then continue so
      Runner pumping is not starved;
    * stdin EOF retires only stdin (the FIFO stays active);
    * a FIFO framing error emits ``outer-input-rejected`` without calling
      ``receive_outer`` and resyncs at the next newline.

    ``select_fn`` remains the open-stream "is there input?" injection point for
    tests; once both sources are retired the real ``select`` timeout throttles
    the idle loop.
    """

    def emit_and_observe(output: list[dict[str, object]]) -> None:
        # The successful emitter return is the deterministic foreground-display
        # boundary.  A formal Runner binds pending Modeling questions only after
        # this call succeeds; lightweight legacy test doubles may not expose the
        # optional observer.
        emit(output)
        observer = getattr(runner, "observe_foreground_output", None)
        if observer is not None:
            observer(output)

    def emit_outer_input_rejection(detail: dict[str, object] | None = None) -> None:
        # This is a control-plane error, not a Runner delivery.  Do not route
        # it through ``observe_foreground_output``: formal display binding
        # must only inspect Runner-generated delivery envelopes.
        payload = dict(_OUTER_INPUT_REJECTION)
        if detail is not None:
            payload.update(detail)
        emit([payload])

    stdin_active = True
    while True:
        output = runner.drain()
        if output:
            emit_and_observe(output)
        if _terminal_report_complete(runner):
            return
        if outer_input is None:
            # stdin-only path: behavior is identical to the pre-FIFO loop,
            # including the immediate-EOF keep-pumping contract.
            if not stdin_active:
                select.select([], [], [], 0.1)
                continue
            readable, _, _ = select_fn([stream], [], [], 0.1)
            if not readable:
                continue
            line = stream.readline()
            if not line:
                # stdin EOF: retire this stream but keep pumping Runner output
                # until the terminal report completes.
                stdin_active = False
                continue
            if _loop_should_exit(
                _handle_foreground_message(
                    runner, line, emit_and_observe, emit_outer_input_rejection
                )
            ):
                return
            continue
        # FIFO path.  stdin takes priority; at most one outer message is
        # admitted per iteration so Runner pumping is never starved.
        readers = []
        if stdin_active:
            readers.append(stream)
        readers.append(outer_input)
        readable, _, _ = select_fn(readers, [], [], 0.1)
        if stdin_active and stream in readable:
            line = stream.readline()
            if not line:
                # stdin EOF retires only stdin; the FIFO stays active.
                stdin_active = False
            else:
                if _loop_should_exit(
                    _handle_foreground_message(
                        runner, line, emit_and_observe, emit_outer_input_rejection
                    )
                ):
                    return
            continue
        if outer_input in readable:
            try:
                outer_input.read_ready()
            except OuterInputFramingError:
                emit_outer_input_rejection()
                continue
        try:
            line = outer_input.pop_line()
        except OuterInputFramingError:
            emit_outer_input_rejection()
            continue
        if line is not None:
            if _loop_should_exit(
                _handle_foreground_message(
                    runner, line, emit_and_observe, emit_outer_input_rejection
                )
            ):
                return
        continue


def _monitor_handoff_root() -> Path | None:
    value = os.environ.get(HANDOFF_ENV)
    if not value:
        return None
    root = Path(value)
    if not root.is_absolute():
        raise TeamConfigurationError("P2 monitor handoff root must be absolute")
    return root


def _write_runner_handoff_failed(handoff_root: Path | None, run_root: Path | None) -> None:
    if handoff_root is None or run_root is None:
        return
    try:
        if read_phase(handoff_root, "runner", "failed") is None:
            write_runner_phase(handoff_root, "failed", run_root=run_root)
    except (OSError, ValueError):
        # The monitor records malformed/lost handoff as a failure; cleanup must still run.
        return


def _runner_root(runner: object | None) -> Path | None:
    value = getattr(getattr(runner, "run", None), "root", None)
    return value if isinstance(value, Path) else None


def _settle_ledger_after_fatal_host_failure(runner: object | None) -> None:
    """Best-effort ledger settlement when a fatal host error kills a live run.

    R2.3-009 start18 (2026-08-21): an invalid outer ``question`` action raised
    ``TeamConfigurationError`` after the run had recorded ``semantic_start``;
    the generic fatal handler cleaned up but left the consumed start dangling
    until a manual ``classify-failure``.  Mirror the Runner's startup-failure
    settlement: a run that semantic-started and never emitted its terminal
    settlement is classified ``runtime/infrastructure`` (host-side fault,
    start not refunded).  Settlement here is bookkeeping only — a ledger that
    refuses (a terminal record raced in from another path) must never mask
    the original fatal error.
    """

    if runner is None:
        return
    run_root = _runner_root(runner)
    settle = getattr(runner, "record_terminal_failure", None)
    if run_root is None or not callable(settle):
        return
    if not (run_root / "evidence" / "semantic-start.jsonl").exists():
        return
    if getattr(runner, "_terminal_emitted", False):
        return
    try:
        settle("runtime/infrastructure", False)
    except Exception:
        # Idempotence is owned by the immutable ledger; a refusal here means
        # another path already classified this run.
        return


def _await_monitor_extraction(handoff_root: Path, run_root: Path) -> None:
    contract = load_handoff_contract(repository_root() / HANDOFF_CONTRACT_RELATIVE_PATH)
    deadline = time.monotonic() + float(contract["phase_deadlines_seconds"]["extraction_complete"])
    acknowledgement = None
    while time.monotonic() < deadline:
        if read_phase(handoff_root, "foreground_monitor", "extraction_failed") is not None:
            raise RuntimeError("foreground monitor rejected adverse-order extraction")
        acknowledgement = read_phase(handoff_root, "foreground_monitor", "extraction_complete")
        if acknowledgement is not None:
            break
        time.sleep(0.05)
    if acknowledgement is None:
        raise TimeoutError("foreground monitor extraction acknowledgement timed out")
    output = run_root / "evidence" / "p2-adverse-order.jsonl"
    digest, length = output_digest(output)
    if (
        acknowledgement.get("output_digest") != digest
        or acknowledgement.get("output_length") != length
    ):
        raise RuntimeError("foreground monitor extraction acknowledgement digest drifted")


def _resolve_model_profile_selection(
    model_profile_id: str | None,
    formal_contract: FormalRunContract | None,
    *,
    multi_slice_workflow: bool = False,
) -> str | None:
    """Resolve the shared ``--model-profile`` selection for all three commands.

    ``validate``/``baseline``/``run`` accept only a restricted profile ID, never a
    path, URL, or environment override.  Omitting the flag keeps the formal run
    contract default; a non-formal fixture outside the multi-slice workflow can
    never be promoted to a formal provider route.  A multi-slice Task may carry
    an explicit Team Model Profile binding (R3.0-006 real validation).
    """

    if model_profile_id is None:
        return None if formal_contract is None else formal_contract.default_model_profile_id
    if formal_contract is None and not multi_slice_workflow:
        raise TeamConfigurationError(
            "model profile selection requires a formal run contract"
        )
    return model_profile_id


_CQ_RUN_CONTRACT_SCHEMA = "r3-0-011-run-contract/v1"
# The read-only acceptance carrier is delivered by the user running this
# command; the read key never has a default and is never echoed or persisted.
_CQ_PLATFORM_READ_KEY_ENV = "R3011_ACCEPTANCE_PLATFORM_READ_KEY"
# Recent formal contracts (R2.3-008/009) default to the Codex builtin route,
# which needs no extra Host credential plumbing; ``--model-profile`` overrides.
_CQ_DEFAULT_MODEL_PROFILE_ID = "openai-luna-medium"
# Platform reads go through the local canonical McpReadForwarder, which starts
# the repository's own backend MCP server; there is no separate platform URL.
# Interview evidence is read from the Runner-owned private interview records
# published in the cq-interview evidence (runner.py `_handle_cq_interview`).
_CQ_INTERVIEW_SCHEMA = "r3-0-011-cq-interview/v1"
_CQ_INTERVIEW_EVIDENCE_PREFIX = "competency-questions/private/"


def _read_json_object(path: Path) -> dict[str, object]:
    """Read one JSON object file, raising ``TeamConfigurationError`` on any drift."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError(f"{path} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError(f"{path} must contain a JSON object")
    return value


def _cq_workspace_payload(response: object, ontology_id: str) -> dict[str, object]:
    """Unwrap one canonical workspace read to the live state it carries.

    The canonical backend MCP server answers every tool through one shared
    runtime wrapper -- ``{"ok": true, "data": ...}`` on success,
    ``{"ok": false, "error": ..., "error_code": ...}`` on a refused call -- and
    the local ``McpReadForwarder`` returns that structured content verbatim.
    Only an explicit success carries live state, so a refused, missing or
    non-canonical response stays a typed failure instead of reading as an
    absent ``None`` workspace.
    """

    if not isinstance(response, Mapping):
        raise TeamConfigurationError(
            f"cq_model_state_missing: workspace read for {ontology_id} returned no object"
        )
    if response.get("ok") is not True:
        reason = response.get("error_code") or response.get("error") or "no ok/data envelope"
        raise TeamConfigurationError(
            f"cq_model_state_missing: ontology {ontology_id} workspace read was not successful "
            f"({reason})"
        )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise TeamConfigurationError(
            f"cq_model_state_missing: ontology {ontology_id} workspace read carried no state object"
        )
    return dict(data)


def _cq_observed_state_entry(
    context: object, project_id: str, ontology_id: str, read_tools: list[str]
) -> dict[str, object]:
    """Summarize one actual read-only workspace observation as a binding entry.

    ``context`` is the unwrapped ``data`` of one successful canonical read
    (``_cq_workspace_payload``), never the raw response envelope.

    The state digests are computed here from the real read with one explicit
    recipe (workspace state/signature plus the default Graph Set identity and
    its member revisions).  The handoff producer must use the same recipe for
    ``model_binding``/``post_batch_model_binding`` so the drift comparison is
    like-for-like; a drift result is therefore never silently swallowed.
    """

    if not isinstance(context, dict):
        raise TeamConfigurationError(
            f"cq_model_state_missing: workspace read for {ontology_id} returned no object"
        )
    state = context.get("state")
    graph_set_id = context.get("default_graph_set_id")
    members = context.get("members")
    if state != "ready":
        raise TeamConfigurationError(
            f"cq_model_state_missing: ontology {ontology_id} workspace state is {state!r}"
        )
    if not isinstance(graph_set_id, str) or not graph_set_id:
        raise TeamConfigurationError(
            f"cq_model_state_missing: ontology {ontology_id} has no default Graph Set"
        )
    if not isinstance(members, list):
        raise TeamConfigurationError(
            f"cq_model_state_missing: ontology {ontology_id} workspace read has no graph members"
        )
    revisions = sorted(
        (item.get("role"), item.get("revision"), item.get("content_hash"))
        for item in members
        if isinstance(item, dict)
    )
    return {
        "project_id": project_id,
        "ontology_id": ontology_id,
        "workspace_state": {
            "state_digest": content_digest(
                {"state": state, "source_signature": context.get("source_signature")}
            )
        },
        "graph_state": {
            "state_digest": content_digest(
                {
                    "graph_set_id": graph_set_id,
                    "status": context.get("graph_set_status"),
                    "revisions": revisions,
                }
            )
        },
        "authorized_read_tools": list(read_tools),
    }


def _cq_observe_model_binding(
    forward: object, read_key: str, binding: dict[str, object]
) -> tuple[dict[str, object], dict[str, str]]:
    """Re-read every bound Ontology's live state through the read-only forwarder."""

    if not callable(forward):
        raise TeamConfigurationError("cq_model_state_missing: platform read path is unavailable")
    observed: list[dict[str, object]] = []
    graph_set_ids: dict[str, str] = {}
    for entry in binding["ontologies"]:
        if not isinstance(entry, dict):
            raise TeamConfigurationError("cq_model_binding_missing: model binding entry is invalid")
        ontology_id = str(entry["ontology_id"])
        response = forward("get_ontology_workspace_context", {"ontology_id": ontology_id}, read_key)
        context = _cq_workspace_payload(response, ontology_id)
        observed_entry = _cq_observed_state_entry(
            context,
            str(entry["project_id"]),
            ontology_id,
            [str(tool) for tool in entry["authorized_read_tools"]],
        )
        observed.append(observed_entry)
        graph_set_ids[ontology_id] = str(context["default_graph_set_id"])
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": binding["batch_id"],
        "freeze_digest": binding["freeze_digest"],
        "bound_at": binding["bound_at"],
        "ontologies": observed,
    }, graph_set_ids


def _cq_decorated_manifest_path(source_name: str) -> str | None:
    """Return the exact path a ``label (path)`` reference carries in parentheses.

    A frozen reference may decorate the approved source's own manifest path with
    a human-readable label in front of it.  Only the text inside the parentheses
    is ever a candidate; the label is never searched, guessed, or matched by
    file name.
    """

    text = source_name.strip()
    if not text.endswith(")"):
        return None
    opening = text.rfind("(")
    if opening < 0:
        return None
    inner = text[opening + 1 : -1].strip()
    return inner or None


def _cq_resolve_manifest_entry(
    manifest: list[object], source_name: str
) -> dict[str, object] | None:
    """Resolve one frozen evidence source to at most one staged source entry.

    The reference is an exact manifest path -- optionally written as
    ``label (path)``, in which case the exact path inside the parentheses is
    what resolves -- or, without that decoration, a bare file name matching
    exactly one manifest entry.  A decorated reference never falls back to file
    names.  Any ambiguity is a typed failure instead of a silent pick, so the
    judge is never handed a guessed source.
    """

    if not source_name:
        return None
    decorated = _cq_decorated_manifest_path(source_name)
    for candidate in (source_name, decorated):
        if candidate is None:
            continue
        exact = [
            item for item in manifest if isinstance(item, dict) and item.get("path") == candidate
        ]
        if len(exact) > 1:
            raise TeamConfigurationError(
                f"cq_evidence_unresolved: evidence source {source_name!r} matches several staged "
                "run sources"
            )
        if len(exact) == 1:
            return exact[0]
    if decorated is not None:
        return None
    name = PurePosixPath(source_name).name
    by_name = [
        item
        for item in manifest
        if isinstance(item, dict) and PurePosixPath(str(item.get("path") or "")).name == name
    ]
    if len(by_name) > 1:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: evidence source {source_name!r} matches several staged "
            "run sources"
        )
    return by_name[0] if by_name else None


def _cq_resolve_interview_record(run_root: Path, source_name: str) -> Path | None:
    """Resolve one frozen evidence source to the Runner's private interview bytes.

    ``TeamRunner._handle_cq_interview`` publishes the run-root-relative
    ``interview_ref`` of ``competency-questions/private/interview-NNNN.json``;
    a frozen reference may carry that path or the bare record file name.
    """

    if not source_name:
        return None
    private_root = run_root / _CQ_INTERVIEW_EVIDENCE_PREFIX
    if source_name.startswith(_CQ_INTERVIEW_EVIDENCE_PREFIX):
        candidates = [run_root / source_name]
    elif source_name.endswith(".json") and PurePosixPath(source_name).name.startswith(
        "interview-"
    ):
        candidates = [private_root / PurePosixPath(source_name).name]
    else:
        return None
    matches = [candidate for candidate in candidates if candidate.is_file()]
    if len(matches) > 1:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview reference {source_name!r} matches several "
            "recorded interview records"
        )
    if not matches:
        return None
    record = matches[0]
    if private_root.resolve() not in record.resolve().parents:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview reference {source_name!r} escapes the "
            "Runner's private interview directory"
        )
    return record


def _cq_read_approved_source_copy(
    run_root: Path, entry: dict[str, object], question_id: str
) -> str:
    """Return one manifest-named source as actual approved bytes.

    The Runner stages one copy per authorized role, so the same source is
    normally mounted more than once; every existing copy must hash to the
    manifest digest and any one of them carries the approved bytes.  A copy
    that differs from the manifest digest is modified material and is rejected
    instead of being re-digested into the bundle.
    """

    relative = str(entry.get("path") or "")
    expected = str(entry.get("sha256") or "")
    if not expected:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: staged source {relative!r} has no manifest digest"
        )
    sources_root = run_root / "sources"
    copies = [
        role_dir / relative
        for role_dir in sorted(sources_root.iterdir())
        if role_dir.is_dir() and (role_dir / relative).is_file()
    ]
    if not copies:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: staged source {relative!r} for question {question_id} "
            "is mounted for no role"
        )
    content = ""
    for copy in copies:
        try:
            raw = copy.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise TeamConfigurationError(
                "cq_evidence_unresolved: staged source "
                f"{copy.relative_to(run_root).as_posix()!r} is unreadable"
            ) from exc
        if hashlib.sha256(raw).hexdigest() != expected:
            raise TeamConfigurationError(
                "cq_evidence_unresolved: staged source "
                f"{copy.relative_to(run_root).as_posix()!r} for question {question_id} does "
                "not match the manifest digest; the staged bytes were modified"
            )
        content = text
    return content


def _cq_read_interview_record(record: Path, question_id: str) -> str:
    """Return one recorded interview's actual bytes, bound to its schema."""

    try:
        raw = record.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview record {record.name!r} for question "
            f"{question_id} is unreadable"
        ) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview record {record.name!r} is not JSON"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != _CQ_INTERVIEW_SCHEMA:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview record {record.name!r} is not an "
            f"{_CQ_INTERVIEW_SCHEMA} record"
        )
    if not isinstance(payload.get("text"), str) or not payload["text"].strip():
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: interview record {record.name!r} carries no text"
        )
    return text


def _cq_platform_read_persistence(artifact_root: Path):
    """Build the attempt-scoped response retention callback (design §4.1).

    The callback runs inside the read proxy at read time and writes the
    canonical ``{schema_version, tool, request, result}`` document under the
    receipt-relative locator inside this attempt's host-only artifact root.
    It persists no key, token or socket; any write failure propagates so the
    proxy can record it and withhold the receipt.
    """

    def persist(artifact_locator: str, document: Mapping[str, object]) -> None:
        locator = PurePosixPath(str(artifact_locator))
        if not artifact_locator or locator.is_absolute() or ".." in locator.parts:
            raise TeamConfigurationError("platform read artifact locator is invalid")
        target = artifact_root.joinpath(*locator.parts)
        resolved_root = artifact_root.resolve()
        resolved = target.resolve(strict=False)
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise TeamConfigurationError(
                "platform read artifact locator escapes the attempt artifact root"
            )
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        temporary = target.with_name(f"{target.name}.tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)

    return persist


def _cq_load_platform_read_artifact(
    artifact_root: Path, receipt: object
) -> dict[str, object]:
    """Load and digest-verify one receipt's retained artifact (design §4.1).

    The locator always comes from the host's own current-session receipt --
    never from a child-submitted path -- and is resolved under the attempt
    artifact root (absolute paths, ``..``, root-escaping or nonexistent files
    are rejected).  Both digests are recomputed from the parsed canonical
    request/result with the existing canonical algorithm; the artifact file
    bytes as a whole are never hashed for comparison.
    """

    locator = PurePosixPath(str(getattr(receipt, "artifact_path", "")))
    if not str(locator) or locator.is_absolute() or ".." in locator.parts:
        raise TeamConfigurationError("platform read artifact locator is invalid")
    path = artifact_root.joinpath(*locator.parts)
    resolved_root = artifact_root.resolve()
    resolved = path.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise TeamConfigurationError(
            "platform read artifact locator escapes the attempt artifact root"
        )
    if path.is_symlink() or not path.is_file():
        raise TeamConfigurationError(
            f"platform read artifact is not a retained file: {locator.as_posix()}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError(
            f"platform read artifact is unreadable: {locator.as_posix()}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        PLATFORM_READ_ARTIFACT_SCHEMA
    ):
        raise TeamConfigurationError(
            f"platform read artifact schema is invalid: {locator.as_posix()}"
        )
    request = payload.get("request")
    result = payload.get("result")
    if not isinstance(request, dict) or not isinstance(result, dict):
        raise TeamConfigurationError(
            f"platform read artifact shape is invalid: {locator.as_posix()}"
        )
    tool = str(getattr(receipt, "tool", ""))
    if canonical_read_digest({"tool": tool, "arguments": dict(request)}) != str(
        getattr(receipt, "request_digest", "")
    ):
        raise TeamConfigurationError(
            f"platform read artifact request digest mismatch: {locator.as_posix()}"
        )
    if canonical_read_digest(result) != str(getattr(receipt, "response_digest", "")):
        raise TeamConfigurationError(
            f"platform read artifact response digest mismatch: {locator.as_posix()}"
        )
    return {"tool": tool, "request": request, "result": result}


def _cq_collect_platform_read_responses(
    reports: list[dict[str, object]],
    receipts: object,
    artifact_root: Path,
    authorized_tools: list[str],
) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    """Bind every Examiner evidence ref to a retained response (design §4.1).

    Each report's ``tool|request_digest|response_digest`` (optionally
    ``|artifact_path``) string selects current-session receipts; the artifact
    is then loaded from the receipt-registered locator and digest-verified.
    The tool segment may carry the MCP-decorated proxy name
    (``mcp__platform_read_proxy__<tool>``) shown to the child; it is reduced to
    the bare tool name before authorization and receipt lookup.
    A ref that matches no current receipt (wrong digest, cross-session or
    unauthorized tool), carries an absolute/escaping/forged locator, or fails
    artifact verification is recorded as rejected and provides no judging
    evidence.  The same receipt may support several questions and repeated
    references are not an error.
    """

    index: dict[tuple[str, str, str], list[object]] = {}
    for receipt in receipts if isinstance(receipts, (list, tuple)) else ():
        key = (
            str(getattr(receipt, "tool", "")),
            str(getattr(receipt, "request_digest", "")),
            str(getattr(receipt, "response_digest", "")),
        )
        index.setdefault(key, []).append(receipt)
    tools = set(authorized_tools)
    responses: dict[str, list[dict[str, object]]] = {}
    rejected: list[dict[str, object]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        question_id = str(report.get("question_id") or "")
        refs = report.get("evidence_refs")
        if not question_id or not isinstance(refs, list):
            continue
        entries: list[dict[str, object]] = []
        seen: set[str] = set()
        for ref in refs:
            summary = str(ref)[:200]
            if not isinstance(ref, str):
                rejected.append({"question_id": question_id, "ref": summary, "reason": "ref-shape"})
                continue
            segments = ref.split("|")
            if len(segments) not in (3, 4) or any(not part for part in segments):
                rejected.append({"question_id": question_id, "ref": summary, "reason": "ref-shape"})
                continue
            tool, request_digest, response_digest = segments[:3]
            if tool not in tools:
                tool = tool.rsplit("__", 1)[-1]
                if tool not in tools:
                    rejected.append(
                        {"question_id": question_id, "ref": summary, "reason": "tool-unauthorized"}
                    )
                    continue
            matches = index.get((tool, request_digest, response_digest), [])
            if not matches:
                # No current-session receipt carries this digest triple: a
                # digest mismatch, a cross-session receipt or an invented ref.
                rejected.append({"question_id": question_id, "ref": summary, "reason": "receipt-unmatched"})
                continue
            if len(segments) == 4:
                submitted = PurePosixPath(segments[3])
                if submitted.is_absolute() or ".." in submitted.parts:
                    rejected.append({"question_id": question_id, "ref": summary, "reason": "locator-invalid"})
                    continue
                if str(submitted) not in {
                    str(getattr(item, "artifact_path", "")) for item in matches
                }:
                    rejected.append({"question_id": question_id, "ref": summary, "reason": "locator-forged"})
                    continue
            for receipt in matches:
                artifact_path = str(getattr(receipt, "artifact_path", ""))
                if artifact_path in seen:
                    continue
                try:
                    loaded = _cq_load_platform_read_artifact(artifact_root, receipt)
                except TeamConfigurationError as exc:
                    rejected.append(
                        {"question_id": question_id, "ref": summary, "reason": str(exc)[:200]}
                    )
                    continue
                seen.add(artifact_path)
                page = getattr(receipt, "page", None)
                entries.append(
                    {
                        "tool": loaded["tool"],
                        "request_digest": request_digest,
                        "response_digest": response_digest,
                        "artifact_path": artifact_path,
                        "page": dict(page) if isinstance(page, Mapping) else {},
                        "result": loaded["result"],
                        # Internal-only: the exact scoped request, so the §4.2
                        # recheck replays the same authorized read.  It is
                        # stripped before the judge packet/report projection,
                        # which keeps the receipt projection's exact fields.
                        "request": dict(loaded["request"]),
                    }
                )
        if entries:
            responses[question_id] = entries
    return responses, rejected


# Non-semantic response noise the evidence recheck must not call drift
# (design §4.2: request ids, durations and sort scores are excluded).
_CQ_RECHECK_NOISE_KEYS = frozenset(
    {
        "request_id",
        "duration_ms",
        "elapsed_ms",
        "took_ms",
        "latency_ms",
        "score",
        "sort_score",
        "timestamp",
    }
)
# Stable identity keys used to order set-like collections before comparison.
_CQ_RECHECK_STABLE_ID_KEYS = (
    "id",
    "resource_id",
    "evidence_id",
    "iri",
    "ref_id",
    "key",
    "name",
)


def _cq_semantic_projection(value: object) -> object:
    """Normalize one retained response for the recheck comparison (§4.2).

    Non-semantic noise keys are dropped at every level; set-like lists whose
    items carry a stable identity key are sorted by that identity so pure
    ordering or score changes never read as semantic drift, while an
    equal-count substitution still compares differently.
    """

    if isinstance(value, dict):
        kept = {
            key: _cq_semantic_projection(item)
            for key, item in value.items()
            if key not in _CQ_RECHECK_NOISE_KEYS
        }
        return {key: kept[key] for key in sorted(kept)}
    if isinstance(value, list):
        items = [_cq_semantic_projection(item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            def stable_key(item: dict) -> tuple[str, str]:
                for key in _CQ_RECHECK_STABLE_ID_KEYS:
                    candidate = item.get(key)
                    if isinstance(candidate, (str, int)) and not isinstance(candidate, bool):
                        return (key, str(candidate))
                return ("", json.dumps(item, ensure_ascii=False, sort_keys=True))

            items.sort(key=stable_key)
        return items
    return value


# The exact per-question projection fields shared by the judge packet and the
# host-only report (design §4.1 item 4); the internal collector additionally
# keeps the scoped ``request`` for the §4.2 replay and never emits it here.
_CQ_RESPONSE_PROJECTION_FIELDS = (
    "tool",
    "request_digest",
    "response_digest",
    "artifact_path",
    "page",
    "result",
)


def _cq_recheck_evidence_responses(
    forward: object,
    read_key: str,
    responses: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    """Replay the referenced authorized reads and compare projections (§4.2).

    Only the receipts this batch's answers actually referenced are re-read
    with the same authorized read-only operation and parameters; the retained
    original responses are never modified.  Semantic drift -- including an
    equal-count substitution -- and an unavailable re-read both keep the
    Examiner answer but block a valid PASS; the unavailable case is recorded
    as ``platform-runtime-incomplete`` for the affected question.
    """

    drift: list[dict[str, object]] = []
    unavailable: list[dict[str, object]] = []
    status: dict[str, str] = {}
    replayed = 0
    for question_id, entries in sorted(responses.items()):
        question_status = "stable"
        for entry in entries:
            tool = str(entry.get("tool") or "")
            request = entry.get("request")
            replayed += 1
            try:
                if not callable(forward) or not isinstance(request, dict):
                    raise TeamConfigurationError("platform recheck read path is unavailable")
                reread = forward(tool, dict(request), read_key)
                if not isinstance(reread, Mapping):
                    raise TeamConfigurationError("platform recheck read returned no object")
            except Exception as exc:  # bounded: recorded, never masks the report
                question_status = "unavailable"
                unavailable.append(
                    {
                        "question_id": question_id,
                        "artifact_path": str(entry.get("artifact_path") or ""),
                        "tool": tool,
                        "error": f"{type(exc).__name__}: {exc}"[:200],
                    }
                )
                continue
            if _cq_semantic_projection(entry.get("result")) != _cq_semantic_projection(
                dict(reread)
            ):
                question_status = "drift"
                drift.append(
                    {
                        "question_id": question_id,
                        "artifact_path": str(entry.get("artifact_path") or ""),
                        "tool": tool,
                    }
                )
        if question_status == "unavailable":
            status[question_id] = "platform-runtime-incomplete"
        else:
            status[question_id] = question_status
    return {
        "replayed_responses": replayed,
        "question_status": status,
        "drift": drift,
        "unavailable": unavailable,
    }


def _cq_build_judge_evidence_bundle(
    run_root: Path, freeze: dict[str, object], hidden: list[dict[str, object]]
) -> tuple[dict[str, object], dict[str, str]]:
    """Assemble the judge evidence bundle from the run's approved bytes.

    Every frozen ``evidence_refs`` entry is resolved to the Runner's staged
    role-source copies (``<run-root>/sources/<role>/<relative_path>``, named by
    ``source-manifest.json``) or to the Runner's private interview records, then
    copied verbatim with its locator, a recomputed content digest and the
    freeze review version.  A reference that resolves to nothing, to an
    ambiguity, or to modified bytes is recorded per question (design §4.3):
    that question alone lacks a valid verdict, and the judge is never handed a
    bare path, a guess, or tampered material.
    """

    manifest_path = run_root / "source-manifest.json"
    manifest: list[object] = []
    if manifest_path.is_file():
        staged = _read_json_object(manifest_path).get("sources")
        if isinstance(staged, list):
            manifest = list(staged)
    review_binding = freeze.get("review_binding")
    review_version = (
        review_binding.get("review_content_version") if isinstance(review_binding, dict) else None
    )
    if isinstance(review_version, bool) or not isinstance(review_version, int) or review_version < 1:
        raise TeamConfigurationError("cq_evidence_unresolved: freeze carries no review version")
    entries: list[dict[str, object]] = []
    failures: dict[str, str] = {}

    def _unresolved(question_id: str, detail: str) -> None:
        failures.setdefault(question_id, f"cq_evidence_unresolved: {detail}")

    for question in hidden:
        question_id = str(question["question_id"])
        refs = question.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            _unresolved(question_id, f"question {question_id} lists no evidence reference")
            continue
        for ref in refs:
            if question_id in failures:
                continue
            if not isinstance(ref, dict):
                _unresolved(
                    question_id,
                    f"question {question_id} has a malformed evidence reference",
                )
                continue
            source_name = str(ref.get("source") or "")
            try:
                entry = _cq_resolve_manifest_entry(manifest, source_name)
                record = _cq_resolve_interview_record(run_root, source_name)
                if entry is not None and record is not None:
                    _unresolved(
                        question_id,
                        f"evidence source {source_name!r} for question {question_id} resolves to "
                        "both a staged source and an interview record",
                    )
                    continue
                if entry is not None:
                    content = _cq_read_approved_source_copy(run_root, entry, question_id)
                elif record is not None:
                    content = _cq_read_interview_record(record, question_id)
                else:
                    _unresolved(
                        question_id,
                        f"evidence source {source_name!r} for question {question_id} matches no "
                        "staged run source or recorded interview",
                    )
                    continue
            except TeamConfigurationError as exc:
                _unresolved(question_id, str(exc).split(":", 1)[-1].strip())
                continue
            entries.append(
                {
                    "question_id": question_id,
                    "source": source_name,
                    "locator": str(ref.get("locator") or ""),
                    "content": content,
                    "content_digest": content_digest(content),
                    "review_content_version": review_version,
                }
            )
    bundle = {
        "schema_version": CQ_EVIDENCE_BUNDLE_SCHEMA,
        "batch_id": freeze["batch_id"],
        "freeze_digest": freeze["snapshot_digest"],
        "entries": entries,
    }
    # An all-failed resolution returns the empty bundle plus the per-question
    # failures (the diagnostics §4.3 wants); no question is judgeable then, so
    # no judge session or PASS can ever be built on it.  A partial bundle is
    # still strictly validated -- the packet seam re-validates it too.
    if entries:
        try:
            validate_evidence_bundle(bundle)
        except ValueError as exc:
            raise TeamConfigurationError(
                f"cq_evidence_unresolved: evidence bundle is invalid: {exc}"
            ) from exc
    # The judge packet seam re-validates the bundle against the same strict
    # exact-fields contract, so the packet must receive the raw schema bundle:
    # ``validate_evidence_bundle``'s return value carries a derived
    # ``bundle_digest`` field that would fail its own re-validation.
    return bundle, failures


_CQ_PLATFORM_ROLE_INSTRUCTIONS = (
    "Answer every hidden batch question in packet order. For each question use only "
    "the authorized read-only platform reads you need, then call submit_examiner_report "
    "exactly once for that question with schema_version, batch_id, question_id, "
    "question_content_version, answer, evidence_refs, explicit_unknown, status, "
    "failure_layer and reason. Never answer a question you did not read for. One "
    "malformed or refused read is corrected through the typed feedback inside the "
    "authorized scope; only a genuinely unavailable valid read becomes status "
    "runtime-incomplete with the actual first failure_layer, never a guess."
)
_CQ_JUDGE_ROLE_INSTRUCTIONS = (
    "Judge every frozen question independently against the attached answer points, "
    "evidence bundle and Examiner reports. Judge the necessary business meaning of "
    "each answer, not verbatim equality; a supported explicit_unknown passes. The "
    "packet's platform_read_responses carry the host-validated retained read-only "
    "responses with their digests, tool and page for each question; judge the answer "
    "against those real responses only -- the Examiner's self-reported answer or IRIs "
    "are claims, not response evidence, and an answer the retained responses do not "
    "support is a failure even when it echoes the reference answer. For each "
    "question call submit_examiner_report exactly once with schema_version, batch_id, "
    "question_id, verdict, failure_layer, conflicting_evidence and note. Do not re-derive "
    "answers from anything outside the packet; use verdict question-answer-review when "
    "the material is genuinely ambiguous or the question or its frozen reference answer "
    "conflicts with the approved material or is unsupported by it. A question whose "
    "required result is a live database measurement outside this read-only scope (for "
    "example a SQL numeric result the CQ read tools cannot query) is judged "
    "question-answer-review with an empty failure_layer and the note "
    "sql-result-outside-cq-scope: the semantic evidence already gathered stays valid, "
    "the other questions are still judged, and no model or infrastructure fault is "
    "recorded for it."
)


def _cq_cleanup_acceptance_resources(
    forwarder: object, child_teardowns: list[dict[str, object]]
) -> dict[str, object]:
    """Observe the real teardown outcome of the resources this batch owned.

    The evidence describes only what this invocation allocated: the forwarder
    instance it started and the v3 children whose teardown the runtime boundary
    observed after ``destroy`` (stopped servers, removed private tree and socket
    root).  Nothing is inferred from a global ``/tmp`` scan, so a concurrently
    running batch can never be reported as this batch's cleanup failure.
    """

    stop_error: str | None = None
    try:
        stop = getattr(forwarder, "stop", None)
        if callable(stop):
            stop()
    except Exception as exc:  # cleanup must record its own failure, not mask the batch outcome
        stop_error = f"{type(exc).__name__}: {exc}"
    still_active = bool(getattr(forwarder, "active", False))
    children = [dict(item) for item in child_teardowns if isinstance(item, dict)]
    return {
        "forwarder_stopped": stop_error is None and not still_active,
        "forwarder_stop_error": stop_error,
        "forwarder_still_active": still_active,
        "children": children,
        "children_destroyed": all(
            item.get("child_destroyed") is True
            and item.get("report_sink_stopped") is True
            and item.get("private_root_removed") is True
            and item.get("socket_root_removed") is True
            and item.get("destroy_error") is None
            for item in children
        ),
    }


def _cq_typed_failure(exc: BaseException) -> dict[str, object]:
    """One typed, JSON-safe failure record for the v3 CLI report.

    ``ExaminerRuntimeBlocked.as_dict`` carries the blocked layer, the role and
    the sanitized evidence (including the runtime boundary's ``reason_code``
    such as ``child-exited``/``batch-incomplete``); the legacy ``str()`` form
    drops exactly those.  Errors without a typed form keep their message.
    """

    as_dict = getattr(exc, "as_dict", None)
    typed = as_dict() if callable(as_dict) else None
    if isinstance(typed, dict):
        return typed
    return {"status": "FAILED", "reason": str(exc) or type(exc).__name__}


def _cq_failure_summary(typed: Mapping[str, object]) -> str:
    """Compact scalar form of one typed failure that still names its codes."""

    evidence = typed.get("evidence")
    code = ""
    if isinstance(evidence, Mapping):
        code = str(evidence.get("reason_code") or "")
    parts = [
        part
        for part in (
            str(typed.get("status") or "FAILED"),
            str(typed.get("blocked_reason") or typed.get("reason") or ""),
            code,
        )
        if part
    ]
    return "/".join(parts) or "unknown-failure"


def _cq_first_examiner_failure(
    reports: list[dict[str, object]],
    failure_reason: str | None,
    typed: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Summarize the first retained batch failure with its typed layer/reason."""

    for report in reports:
        if report.get("status") == "runtime-incomplete":
            return {
                "question_id": str(report.get("question_id") or ""),
                "failure_layer": str(report.get("failure_layer") or ""),
                "reason": str(report.get("reason") or ""),
            }
    blocked_layer = str(typed.get("blocked_reason") or "") if typed else ""
    return {
        "failure_layer": blocked_layer or None,
        "reason": failure_reason,
    }


# R3.0-012 design §3.4/§4.5: the Runner-published verified handoff schema.
_CQ_PRODUCTION_HANDOFF_SCHEMA = "r3-0-012-production-handoff/v1"


def _cq_consume_production_handoff(
    run_root: Path,
    handoff: dict[str, object],
    *,
    contract: dict[str, object],
    batch_id: str,
    freeze_digest: str,
    continuation_output: Path | None = None,
    continuation_attempt: str | None = None,
) -> tuple[Path, dict[str, object]]:
    """Consume the Runner's verified v012 production handoff (design §4.5).

    The submitted handoff must equal the Runner's immutable published record
    (``acceptance-v3/production-handoff.json``) -- an arbitrary user file is
    never trusted -- must carry the settled read-only write phase with no
    unknown staged writes, and must name the attempt-unique report
    directory this CLI writes into; the CLI never allocates an attempt id the
    Runner does not know.  A published batch report at that directory is a
    typed immutable conflict: recovery is a new handoff/attempt, never an
    overwrite.  The batch binding is derived from the handoff's scope binding
    (project/Ontology authorization plus the CQ read-only tool inventory)
    because the v012 handoff deliberately carries no live model state; D5
    keeps state binding on this command's own pre/post reads.

    R3.0-015 S4 continuation inputs (``continuation_output`` +
    ``continuation_attempt``) split the evidence root from the report root
    (design §7): everything is still verified against the SOURCE run's
    published handoff, but the new attempt's report directory and retained
    handoff copy land under the fresh output run root; whatever the terminated
    process published at the handoff's own attempt directory stays untouched.
    """

    published_path = run_root / "acceptance-v3" / "production-handoff.json"
    if not published_path.is_file() or published_path.is_symlink():
        raise TeamConfigurationError(
            "cq_model_binding_missing: the run root has no Runner-published "
            "production handoff to verify the submitted handoff against"
        )
    try:
        published = json.loads(published_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError(
            "cq_model_binding_missing: the Runner-published production handoff "
            "is unreadable"
        ) from exc
    if published != handoff:
        raise TeamConfigurationError(
            "cq_model_binding_missing: the submitted handoff does not match the "
            "Runner-published production handoff"
        )
    if handoff.get("run_id") != contract.get("run_id"):
        raise TeamConfigurationError(
            "cq_model_binding_missing: production handoff run does not match the "
            "run contract"
        )
    if (
        handoff.get("batch_id") != batch_id
        or handoff.get("freeze_id") != batch_id
        or handoff.get("freeze_digest") != freeze_digest
    ):
        raise TeamConfigurationError(
            "cq_model_binding_missing: production handoff is not bound to this "
            "freeze snapshot"
        )
    # Evidence fields first (design §3.1): the derived ready pair is re-checked
    # alongside them, never trusted alone.
    unknown_writes = handoff.get("unknown_writes")
    if (
        handoff.get("write_phase") != "read-only"
        or (isinstance(unknown_writes, list) and unknown_writes)
        or handoff.get("ready") is not True
        or handoff.get("pending_writes") is not False
    ):
        raise TeamConfigurationError(
            "cq_unknown_write_pending: the production handoff is not a settled "
            "read-only handoff"
        )
    attempt_id = str(handoff.get("acceptance_attempt_id") or "")
    if (
        not attempt_id.startswith("attempt-")
        or len(attempt_id) != len("attempt-0000")
        or not attempt_id[len("attempt-") :].isdigit()
    ):
        raise TeamConfigurationError(
            "cq_model_binding_missing: production handoff carries an invalid "
            "acceptance attempt id"
        )
    expected_directory = f"acceptance-v3/reports/{batch_id}/{attempt_id}"
    if handoff.get("report_directory") != expected_directory:
        raise TeamConfigurationError(
            "cq_model_binding_missing: production handoff report directory does "
            "not match its batch and attempt"
        )
    if continuation_output is not None or continuation_attempt is not None:
        # S4: the new attempt lives under the NEW output root; the source
        # run's own attempt directory keeps whatever the terminated process
        # published there (M34), and nothing is appended to the old run.
        if continuation_output is None or continuation_attempt is None:
            raise TeamConfigurationError(
                "cq_model_binding_missing: continuation requires both the "
                "output root and the new attempt id"
            )
        if (
            not continuation_attempt.startswith("attempt-")
            or len(continuation_attempt) != len("attempt-0000")
            or not continuation_attempt[len("attempt-") :].isdigit()
        ):
            raise TeamConfigurationError(
                "cq_model_binding_missing: continuation carries an invalid "
                "acceptance attempt id"
            )
        report_dir = continuation_output.joinpath(
            *PurePosixPath(f"acceptance-v3/reports/{batch_id}/{continuation_attempt}").parts
        )
    else:
        report_dir = run_root.joinpath(*PurePosixPath(expected_directory).parts)
    report_path = report_dir / "batch-report.json"
    if report_path.exists() or report_path.is_symlink():
        raise TeamConfigurationError(
            "cq_handoff_immutable: this attempt already carries a published "
            "batch report; a re-acceptance must request a new handoff to "
            "allocate a new attempt"
        )
    report_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Retain this attempt's handoff copy (design §4.5); a partial re-run that
    # crashed before the report never rewrites the copy either.
    handoff_copy = report_dir / "production-handoff.json"
    if not handoff_copy.exists():
        _write_host_only_json(handoff_copy, handoff)
    scope = handoff.get("scope_binding")
    ontology_ids = scope.get("ontology_ids") if isinstance(scope, dict) else None
    if (
        not isinstance(scope, dict)
        or not isinstance(scope.get("project_id"), str)
        or not scope.get("project_id")
        or not isinstance(ontology_ids, list)
        or not any(
            isinstance(item, str) and item for item in ontology_ids
        )
    ):
        raise TeamConfigurationError(
            "cq_batch_scope_unauthorized: production handoff lists no authorized "
            "Ontology"
        )
    authorized = [item for item in ontology_ids if isinstance(item, str) and item]
    # The v012 handoff records scope authorization only; every tool in the CQ
    # read-only inventory is a platform read, and the ScopedReadProxy/ticket
    # still bound each request to the authorized Ontology set.
    tools = [str(tool) for tool in PLATFORM_PROXY_READ_TOOLS]
    binding = validate_model_binding(
        {
            "schema_version": "r3-0-011-model-binding/v1",
            "batch_id": batch_id,
            "freeze_digest": freeze_digest,
            "bound_at": attempt_id,
            "ontologies": [
                {
                    "project_id": scope["project_id"],
                    "ontology_id": ontology_id,
                    # Opaque handoff markers, never compared with live state
                    # (D5): drift is measured against this command's own
                    # observed pre/post-session bindings.
                    "workspace_state": {
                        "state_digest": content_digest(
                            {"handoff": attempt_id, "kind": "workspace"}
                        )
                    },
                    "graph_state": {
                        "state_digest": content_digest(
                            {"handoff": attempt_id, "kind": "graph"}
                        )
                    },
                    "authorized_read_tools": tools,
                }
                for ontology_id in authorized
            ],
        },
        authorized_ontology_ids=authorized,
    )
    return report_dir, binding


def _cq_execute_batch(
    args: argparse.Namespace,
    root: Path,
    run_root: Path,
    *,
    contract: dict[str, object],
    freeze: dict[str, object],
    batch_id: str,
    freeze_digest: str,
    binding: dict[str, object],
    blind_status: dict[str, object],
    hidden: list[dict[str, object]],
    slices: list[str],
    report_dir: Path,
    forwarder_factory: object = McpReadForwarder,
    artifact_root: Path | None = None,
    continuation: Mapping[str, object] | None = None,
) -> int:
    """Run the real v3 batch lifecycle end to end and write the executed report.

    The batch binding is constructed from this command's actual pre-session
    platform read and persisted in the report; the actual post-session read is
    compared against that observed binding (D5).  Bounded carrier failures after
    the batch started -- post-batch state read, judge evidence assembly, judge
    session -- are recorded and never discard the per-question reports already
    received: the report is always finalized.  The forwarder and both child
    sessions are stopped/destroyed before the report is written and the real
    teardown outcome is recorded, so a failed batch never leaves a live key,
    socket or child behind and never looks like a PASS.

    R3.0-015 S4: ``run_root`` stays the READ-ONLY evidence root (contract,
    freeze, judge evidence bundle -- design §7) while ``artifact_root``
    redirects this attempt's platform-read artifacts to the continuation's
    output root; both default to the original single-root behavior.
    """

    artifacts = run_root if artifact_root is None else Path(artifact_root)
    read_key = os.environ.get(_CQ_PLATFORM_READ_KEY_ENV)
    if not read_key:
        raise TeamConfigurationError(
            f"cq_acceptance_credentials_missing: {_CQ_PLATFORM_READ_KEY_ENV} is not set; "
            "run cq-acceptance only with an authorized platform read key"
        )
    profile_id = getattr(args, "model_profile", None) or _CQ_DEFAULT_MODEL_PROFILE_ID
    profile = load_team_model_profile(root, profile_id)
    read_tools = [str(tool) for tool in binding["ontologies"][0]["authorized_read_tools"]]
    forwarder = forwarder_factory(
        repository_root=root, read_key=read_key, expected_tools=tuple(read_tools)
    )
    sessions: dict[str, object] = {}
    reports: list[dict[str, object]] = []
    verdicts: list[dict[str, object]] = []
    executed: list[str] = []
    failure_reason: str | None = None
    lifecycle_errors: list[dict[str, object]] = []
    pre_binding: dict[str, object] | None = None
    post_binding: dict[str, object] | None = None
    # The Judge session only starts after the actual post-batch state read
    # succeeded; a failed read is runtime evidence, never a silent skip.
    post_read_ok = False
    pre_drift: list[str] = []
    post_drift: list[str] = []
    # Each v3 child reports its own teardown outcome at the runtime boundary;
    # the report below records exactly these, never a global scan.
    child_teardowns: list[dict[str, object]] = []
    # R3.0-012 design §4.1: the host-side observables of the Examiner session
    # -- sanitized receipts (never the key, token or socket) and the
    # retention-failure counter -- captured before teardown.  Declared here so
    # an empty hidden set still reports its (empty) observables.
    examiner_observables: dict[str, object] = {}
    try:
        forwarder.start()
        # D5: the handoff authorizes the project/Ontology/tool scope only -- it
        # is written before the batch and cannot own live platform state, so
        # its carried state digests are opaque markers and are never compared
        # against the live read.  This command's own pre-session observation is
        # the batch binding; drift is measured post-session against it.
        pre_binding, graph_set_ids = _cq_observe_model_binding(forwarder.forward, read_key, binding)
        # One binding identity for the whole batch (D5): the immutable Platform
        # packet is built from the observed pre-session read, so the child, the
        # proxy scope entries, the retained ``batch_model_binding`` and the
        # Judge's binding digest all describe the same state.  The handoff still
        # rules: its authorized project/Ontology/tool set bounds ``pre_binding``.
        packet = None
        if hidden:
            packet = build_platform_batch_packet(
                run_id=str(contract["run_id"]),
                batch_id=batch_id,
                freeze_digest=freeze_digest,
                questions=[
                    {
                        "question_id": question["question_id"],
                        "content_version": question["content_version"],
                        "question": question["question"],
                        "scope": dict(question["scope"]),
                    }
                    for question in hidden
                ],
                authorized_scope=[
                    str(entry["ontology_id"]) for entry in binding["ontologies"]
                ],
                model_binding=pre_binding or binding,
                authorized_read_tools=[
                    str(tool) for tool in binding["ontologies"][0]["authorized_read_tools"]
                ],
                report_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
                session={"mode": "single-continuous-batch", "ordered": True},
            )
        if packet is not None and hidden:
            adapter = CodexRuntimeAdapter(repository_root=root)
            # R3.0-015 S4: the attempt's runtime evidence (elicitation decisions,
            # retained child sessions) belongs beside this attempt's artifacts;
            # ``run_root`` is the read-only source evidence root.
            adapter._run_root = artifacts
            adapter.bind_acceptance_model_profile(profile)
            teardown_platform: dict[str, object] = {}
            typed_failure: dict[str, object] | None = None
            try:
                reports = list(
                    adapter.run_v3_acceptance_child(
                        packet,
                        role_instructions=_CQ_PLATFORM_ROLE_INSTRUCTIONS,
                        reports=reports,
                        read_key=read_key,
                        platform_forwarder=forwarder.forward,
                        response_persistence=_cq_platform_read_persistence(artifacts),
                        examiner_observables=examiner_observables,
                        timeout_seconds=float(
                            getattr(args, "session_timeout", 300.0) or 300.0
                        ),
                        graph_set_ids=graph_set_ids,
                        teardown=teardown_platform,
                    )
                )
            except (ExaminerRuntimeBlocked, ChildRuntimeError, CodexRuntimeError) as exc:
                typed_failure = _cq_typed_failure(exc)
                failure_reason = _cq_failure_summary(typed_failure)
                lifecycle_errors.append(
                    {
                        "stage": "platform-examiner-session",
                        "reason": failure_reason,
                        "failure": typed_failure,
                    }
                )
            finally:
                child_teardowns.append(teardown_platform)
            reported_ids = {
                str(report["question_id"])
                for report in reports
                if isinstance(report, dict) and report.get("question_id")
            }
            # R3.0-012 design §4.3: an executed service failure
            # (``runtime-incomplete``) is still an executed question, retained
            # through its Examiner report -- only a hidden question with no
            # report is unexecuted.  The full-pass verdict-coverage boundary,
            # not this list, decides what a partially judged batch may publish.
            executed = [
                str(question["question_id"])
                for question in hidden
                if str(question["question_id"]) in reported_ids
            ]
            sessions["platform_examiner"] = {
                "mode": "single-continuous-batch",
                "reports": len(reports),
                "missing_question_ids": [
                    str(question["question_id"])
                    for question in hidden
                    if str(question["question_id"]) not in reported_ids
                ],
                "failure_reason": failure_reason,
                "failure": typed_failure,
                "first_failure": _cq_first_examiner_failure(
                    reports, failure_reason, typed_failure
                ),
            }
        try:
            post_binding, _ = _cq_observe_model_binding(forwarder.forward, read_key, binding)
            post_read_ok = True
            # Actual post-session state vs this command's actual pre-session
            # binding -- never against the handoff's marker digests.
            post_drift = model_binding_drift(pre_binding, post_binding)
        except (
            TeamConfigurationError,
            ChildRuntimeError,
            CodexRuntimeError,
            ExaminerRuntimeBlocked,
        ) as exc:
            # A bounded post-read failure is a runtime/infrastructure failure:
            # it blocks the Judge session and stays in the retained report.
            # The canonical forwarder signals a failed read with
            # ``ChildRuntimeError`` (MCP isError decoding), the same concrete
            # runtime failure the platform child boundary already bounds.
            post_failure = _cq_typed_failure(exc)
            post_failure["failure_layer"] = "runtime/infrastructure"
            lifecycle_errors.append(
                {
                    "stage": "post-batch-model-state-read",
                    "reason": str(exc),
                    "failure": post_failure,
                }
            )
            sessions["post_batch_model_state_read"] = {
                "failure_reason": str(exc),
                "failure": post_failure,
                "first_failure": {
                    "failure_layer": "runtime/infrastructure",
                    "reason": str(exc),
                },
            }
        # R3.0-012 design §4.1/§4.2: bind every Examiner evidence ref to a
        # retained response loaded from this attempt's own receipts, then --
        # after the Examiner child has exited -- replay exactly the referenced
        # authorized reads and compare semantic projections.  A ref that no
        # current receipt matches provides no judging evidence, and drift or an
        # unavailable re-read blocks a valid PASS at the report boundary.
        platform_read_responses: dict[str, list[dict[str, object]]] = {}
        response_projection: dict[str, list[dict[str, object]]] = {}
        rejected_refs: list[dict[str, object]] = []
        evidence_recheck: dict[str, object] | None = None
        if packet is not None:
            platform_read_responses, rejected_refs = _cq_collect_platform_read_responses(
                reports,
                examiner_observables.get("receipts") or [],
                artifacts,
                read_tools,
            )
            response_projection = {
                question_id: [
                    {key: entry[key] for key in _CQ_RESPONSE_PROJECTION_FIELDS}
                    for entry in entries
                ]
                for question_id, entries in platform_read_responses.items()
            }
            evidence_recheck = _cq_recheck_evidence_responses(
                forwarder.forward, read_key, platform_read_responses
            )
        # R3.0-012 design §4.3: the old whole-batch completeness gate is split
        # into a judgeable subset.  A hidden question is judgeable when its
        # Examiner report exists and is not a service failure
        # (``completed``/``unanswered`` -- a successful empty query is still a
        # valid response), it carries at least one host-validated retained
        # platform response, and its frozen evidence resolved.  A question that
        # fails any of these keeps its answer/report and merely lacks a valid
        # verdict; the other questions are still judged.
        evidence_bundle: dict[str, object] | None = None
        evidence_failures: dict[str, str] = {}
        if packet is not None:
            try:
                evidence_bundle, evidence_failures = _cq_build_judge_evidence_bundle(
                    run_root, freeze, hidden
                )
            except TeamConfigurationError as exc:
                lifecycle_errors.append(
                    {"stage": "judge-evidence-bundle", "reason": str(exc)}
                )
        report_by_question: dict[str, dict[str, object]] = {
            str(report.get("question_id")): report
            for report in reports
            if isinstance(report, dict) and report.get("question_id")
        }
        judgeable: list[str] = []
        judging_skips: dict[str, str] = {}
        for question in hidden:
            question_id = str(question["question_id"])
            report = report_by_question.get(question_id)
            if report is None:
                judging_skips[question_id] = "no-examiner-report"
            elif report.get("status") not in ("completed", "unanswered"):
                judging_skips[question_id] = "examiner-runtime-incomplete"
            elif question_id in evidence_failures:
                judging_skips[question_id] = (
                    f"evidence-unresolved: {evidence_failures[question_id]}"
                )
            elif not platform_read_responses.get(question_id):
                judging_skips[question_id] = "no-validated-platform-response"
            else:
                judgeable.append(question_id)
        if (
            judgeable
            and evidence_bundle is not None
            and post_read_ok
            and not post_drift
        ):
            judgeable_set = set(judgeable)
            judge_questions = [
                {
                    "question_id": question["question_id"],
                    "content_version": question["content_version"],
                    "question": question["question"],
                    "answer_points": list(question["answer_points"]),
                    "evidence_refs": [dict(ref) for ref in question["evidence_refs"]],
                    "unknown": list(question["unknown"]),
                    "scope": dict(question["scope"]),
                }
                for question in hidden
                if str(question["question_id"]) in judgeable_set
            ]
            teardown_judge: dict[str, object] = {}
            # Judge setup (packet build, adapter bind) is guarded by the same
            # handler as the session itself: a setup failure is serialized into
            # the retained report instead of discarding the examiner reports.
            judge_stage = "acceptance-judge-setup"
            try:
                judge_packet = build_acceptance_judge_packet(
                    run_id=str(contract["run_id"]),
                    batch_id=batch_id,
                    freeze_digest=freeze_digest,
                    questions=judge_questions,
                    model_binding_digest=content_digest(pre_binding or binding),
                    evidence_bundle=evidence_bundle,
                    examiner_reports=[
                        dict(report)
                        for report in reports
                        if str(report.get("question_id")) in judgeable_set
                    ],
                    # R3.0-012 design §4.1/§4.3: the judge sees only
                    # host-validated retained responses (digests recomputed,
                    # tool authorized, locator resolved from the host's own
                    # receipts) for the questions it is asked to judge; a
                    # non-judgeable question carries no entry here and never a
                    # masked empty answer, so a pass verdict on it cannot
                    # survive the report boundary either.
                    platform_read_responses={
                        question_id: response_projection[question_id]
                        for question_id in judgeable
                    },
                    verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
                )
                adapter = CodexRuntimeAdapter(repository_root=root)
                adapter._run_root = artifacts
                adapter.bind_acceptance_model_profile(profile)
                judge_stage = "acceptance-judge-session"
                verdicts = list(
                    adapter.run_v3_acceptance_child(
                        judge_packet,
                        role_instructions=_CQ_JUDGE_ROLE_INSTRUCTIONS,
                        reports=verdicts,
                        timeout_seconds=float(
                            getattr(args, "session_timeout", 300.0) or 300.0
                        ),
                        teardown=teardown_judge,
                    )
                )
                sessions["acceptance_judge"] = {
                    "verdicts": len(verdicts),
                    "judged_question_ids": list(judgeable),
                }
            except (
                ExaminerRuntimeBlocked,
                ChildRuntimeError,
                CodexRuntimeError,
                TeamConfigurationError,
            ) as exc:
                judge_typed = _cq_typed_failure(exc)
                judge_failure = _cq_failure_summary(judge_typed)
                sessions["acceptance_judge"] = {
                    "failure_reason": judge_failure,
                    "failure": judge_typed,
                }
                lifecycle_errors.append(
                    {
                        "stage": judge_stage,
                        "reason": judge_failure,
                        "failure": judge_typed,
                    }
                )
            finally:
                child_teardowns.append(teardown_judge)
        else:
            sessions["acceptance_judge"] = {
                "reason": (
                    "judge session skipped: no question is judgeable (every report is "
                    "a service failure, lacks a validated platform response or has "
                    "unresolved frozen evidence), the judge evidence bundle is "
                    "invalid, the post-batch state read failed or the platform state "
                    "drifted"
                )
            }
    finally:
        # The forwarder is stopped even when a pre-batch gate raised, but the
        # report below records the outcome of the owned-lifecycle teardown.
        cleanup = _cq_cleanup_acceptance_resources(forwarder, child_teardowns)
    cleanup_failed = not cleanup["forwarder_stopped"] or not cleanup["children_destroyed"]
    report = build_batch_report(
        run_id=str(contract["run_id"]),
        batch_id=batch_id,
        freeze_digest=freeze_digest,
        # The observed pre-session binding is the batch identity; the handoff
        # binding only names the authorization scope (D5).
        model_binding_digest=content_digest(pre_binding or binding),
        hidden_questions=hidden,
        examiner_reports=[dict(report) for report in reports],
        verdicts=[dict(verdict) for verdict in verdicts],
        executed_question_ids=executed,
        unexecuted_question_ids=[
            str(question["question_id"])
            for question in hidden
            if str(question["question_id"])
            not in {item for item in executed}
        ],
        slices=slices,
        model_state_drift=post_drift,
        blind_status=blind_status,
        # R3.0-012 design §4.1/§4.2: the executed path always carries the two
        # attempt-produced fields (even empty -- empty is fail-closed at the
        # full-pass boundary); the legacy unexecuted path passes neither and
        # keeps the exact 011 report shape.
        platform_read_responses=response_projection if packet is not None else None,
        evidence_recheck=evidence_recheck if packet is not None else None,
    )
    report["sessions"] = {
        **sessions,
        "model_profile": profile_id,
        "batch_model_binding": pre_binding,
        "post_batch_model_binding": post_binding,
        "pre_batch_model_state_drift": pre_drift,
        "post_batch_model_state_drift": post_drift,
        "lifecycle_errors": lifecycle_errors,
        "cleanup": cleanup,
        # R3.0-012 design §4.3: the per-question judging split -- which hidden
        # questions were judged and why the rest were not (an executed service
        # failure, an unresolved frozen basis, or no validated platform
        # response).  Recorded as host observables, never as lifecycle errors:
        # a partial batch is an outcome, not a host fault.
        "question_judging": {
            "judgeable_question_ids": judgeable,
            "skipped": judging_skips,
        },
        "platform_read_responses": {
            "questions_with_responses": len(platform_read_responses),
            "retained_receipts": len(examiner_observables.get("receipts") or []),
            "persistence_failures": int(
                examiner_observables.get("persistence_failures") or 0
            ),
            # Bounded host-side record of which child refs provided no judging
            # evidence (unmatched digest triple, unauthorized tool, forged
            # locator, failed artifact verification); repeated references to a
            # valid receipt are never recorded here.
            "rejected_refs": rejected_refs[:20],
        },
    }
    report["full_pass"] = (
        batch_report_is_full_pass(report) and not lifecycle_errors and not cleanup_failed
    )
    report_path = report_dir / "batch-report.json"
    # First publication wins: the exclusive create turns a concurrent publisher
    # of this attempt into the typed immutable conflict (T3-18).
    _write_host_only_json(report_path, report, immutable=True)
    _write_host_only_json(
        report_dir / "attribution.json",
        {
            **acceptance_mode_evidence(batch_id=batch_id, freeze_digest=freeze_digest),
            "blind_status": blind_status["blind_status"],
            "exposed_question_ids": blind_status["exposed_question_ids"],
            "exposure_evidence_digest": blind_status["exposure_evidence_digest"],
            "platform_read_path": "local-canonical-mcp-forwarder",
        },
    )
    if packet is not None:
        _write_host_only_json(
            report_dir / "batch-packet.json",
            {
                "schema_version": packet.schema_version,
                "canonical_digest": packet.canonical_digest,
            },
        )
    print(
        json.dumps(
            {
                "run_id": contract["run_id"],
                "batch_id": batch_id,
                "freeze_digest": freeze_digest,
                "report": report_path.as_posix(),
                "acceptance_mode": "read-only-acceptance",
                "blind_status": blind_status["blind_status"],
                "executed_question_ids": executed,
                "unexecuted_question_ids": report["unexecuted_question_ids"],
                "full_pass": report["full_pass"],
                "start_ledger_write": False,
                "consumes_semantic_start": False,
                **(
                    {"acceptance_continuation": dict(continuation)}
                    if continuation is not None
                    else {}
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["full_pass"] else 1


def _run_cq_acceptance(
    args: argparse.Namespace,
    root: Path,
    *,
    forwarder_factory: object = McpReadForwarder,
    continuation: Mapping[str, object] | None = None,
) -> int:
    """Read-only v3 hidden-batch acceptance entry (R3.0-011 design §4.0).

    The command is Delivery-invoked and strictly read-only for the platform: it
    writes no StartLedger record, consumes no fresh semantic start, and never
    starts, continues, or repairs the production run.  A run root without the
    Runner-written v3 configuration snapshot is a legacy R2.3 run and is
    rejected instead of being switched to this contract by the command name.

    R3.0-015 S4: with ``continuation`` set, ``args.run_root`` is the ORIGINAL
    run whose frozen inputs are re-used untouched, while the new attempt's
    report directory and platform-read artifacts land under the continuation's
    fresh output root (design §7 input/output separation).
    """

    run_root = args.run_root
    if not run_root.is_dir():
        print("cq-acceptance failed: --run-root is not a directory", file=sys.stderr)
        return 2
    contract_path = run_root / "acceptance-v3" / "run-contract.json"
    if not contract_path.is_file():
        print(
            "cq-acceptance failed: cq_selector_incompatible: the run root has no "
            "competency-question configuration snapshot",
            file=sys.stderr,
        )
        return 2
    try:
        contract = _read_json_object(contract_path)
        if contract.get("schema_version") != _CQ_RUN_CONTRACT_SCHEMA:
            raise TeamConfigurationError("run configuration snapshot schema is invalid")
        parameters = contract.get("parameters")
        if not isinstance(parameters, dict) or parameters.get(
            "competency_question_acceptance"
        ) is not True:
            raise TeamConfigurationError(
                "cq_selector_incompatible: this run did not select "
                "parameters.competency_question_acceptance"
            )
        freeze_path = run_root / "competency-questions" / "frozen" / f"{args.freeze_id}.json"
        if not freeze_path.is_file():
            raise TeamConfigurationError(f"cq_freeze_schema_mismatch: {args.freeze_id} is not frozen")
        raw_freeze = _read_json_object(freeze_path)
        # The Runner writes the normalized snapshot; reloading it also proves the
        # file was never edited after the freeze.
        freeze = reload_frozen_pool(raw_freeze)
        if freeze["schema_version"] != CQ_FREEZE_SCHEMA:
            raise TeamConfigurationError("cq_freeze_schema_mismatch: freeze snapshot is invalid")
        batch_id = str(freeze["batch_id"])
        freeze_digest = str(freeze["snapshot_digest"])
        handoff = _read_json_object(args.model_handoff)
        if handoff.get("schema_version") == _CQ_PRODUCTION_HANDOFF_SCHEMA:
            # R3.0-012 design §4.5: consume the Runner-registered attempt from
            # the verified production handoff (attempt-unique report directory,
            # retained handoff copy, typed rejection of a published report).
            report_dir, binding = _cq_consume_production_handoff(
                run_root,
                handoff,
                contract=contract,
                batch_id=batch_id,
                freeze_digest=freeze_digest,
                **(
                    {
                        "continuation_output": Path(continuation["output_root"]),
                        "continuation_attempt": continuation["attempt_id"],
                    }
                    if continuation is not None
                    else {}
                ),
            )
        else:
            report_dir = run_root / "acceptance-v3" / "reports" / batch_id
            report_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            # R3.0-012 design §4.3/T3-18: the legacy batch-level path gains the
            # same first-write immutability; a re-acceptance is a new attempt,
            # never an overwrite of a published report.
            legacy_report_path = report_dir / "batch-report.json"
            if legacy_report_path.exists() or legacy_report_path.is_symlink():
                raise TeamConfigurationError(
                    "cq_handoff_immutable: a batch report is already published at "
                    f"{legacy_report_path.as_posix()}; a re-acceptance must request a "
                    "new handoff to allocate a new attempt"
                )
            delivery = handoff.get("production_delivery")
            if not isinstance(delivery, dict):
                raise TeamConfigurationError(
                    "cq_batch_scope_unauthorized: model handoff carries no production "
                    "delivery receipt"
                )
            if delivery.get("ready") is not True or delivery.get("pending_writes") is not False:
                raise TeamConfigurationError(
                    "cq_batch_scope_unauthorized: production delivery is not ready for "
                    "acceptance"
                )
            # The 008B joint checklist stays pending-safe: it is never required
            # to have passed before this command runs (design §4.0).
            authorized = handoff.get("authorized_ontology_ids")
            if not isinstance(authorized, list) or not authorized or any(
                not isinstance(item, str) or not item for item in authorized
            ):
                raise TeamConfigurationError(
                    "cq_batch_scope_unauthorized: model handoff lists no authorized "
                    "Ontology"
                )
            binding = validate_model_binding(
                handoff.get("model_binding"),
                authorized_ontology_ids=[str(item) for item in authorized],
            )
            if binding.get("batch_id") != batch_id:
                raise TeamConfigurationError(
                    "cq_model_binding_missing: model binding batch does not match the "
                    "frozen batch"
                )
            if binding.get("freeze_digest") != freeze_digest:
                raise TeamConfigurationError(
                    "cq_model_binding_missing: model binding is not bound to this freeze "
                    "snapshot"
                )
        # The executed path constructs the batch binding from its own actual
        # pre-session read and re-reads the post-session state itself (D5); the
        # handoff post-batch binding stays an input only for the legacy
        # ``--unexecuted-report`` evidence shape below.
        # Design §5 (Round 2 R4): the exposure label is derived from the
        # Runner-written cq-exposure evidence, not from the frozen snapshot
        # (whose schema intentionally carries no exposure field).  The packet
        # seam stays byte-compatible with the blind child input contract; the
        # report is where the non-blind label is mandatory.
        evidence = read_exposure_evidence(
            run_root / "evidence" / "cq-exposure.jsonl"
        )
        blind_status = blind_batch_label(
            question_ids=[str(item) for item in freeze["ordering"]], evidence=evidence
        )
        hidden = [
            dict(question)
            for question in freeze["questions"]
            if question.get("visibility") == "hidden"
        ]
        ordered_ids = [str(item) for item in freeze["ordering"]]
        hidden.sort(key=lambda question: ordered_ids.index(str(question["question_id"])))
        slices = sorted(
            {
                slice_id
                for question in freeze["questions"]
                if question.get("scope", {}).get("kind") == "slice"
                for slice_id in question.get("scope", {}).get("slice_ids", [])
            }
        )
        if not getattr(args, "unexecuted_report", False):
            # Default: the command owns the real batch lifecycle (platform
            # Examiner session, independent judge, executed/unexecuted report).
            # The immutable Platform packet is built inside the executed path
            # from that path's own observed pre-session binding (D5), so the
            # child, proxy, retained binding and Judge digest all share one
            # binding identity.
            return _cq_execute_batch(
                args,
                root,
                run_root,
                contract=contract,
                freeze=freeze,
                batch_id=batch_id,
                freeze_digest=freeze_digest,
                binding=binding,
                blind_status=blind_status,
                hidden=hidden,
                slices=slices,
                report_dir=report_dir,
                forwarder_factory=forwarder_factory,
                **(
                    {
                        "artifact_root": continuation["output_root"],
                        "continuation": continuation,
                    }
                    if continuation is not None
                    else {}
                ),
            )
        # Explicit ``--unexecuted-report``: the pre-authorization evidence shape
        # (every question recorded as unexecuted, no session is started).
        post_binding = handoff.get("post_batch_model_binding")
        if not isinstance(post_binding, dict):
            raise TeamConfigurationError(
                "cq_model_binding_missing: model handoff carries no post-batch state recheck"
            )
        post = model_binding_drift(binding, post_binding)
        report = build_batch_report(
            run_id=str(contract["run_id"]),
            batch_id=batch_id,
            freeze_digest=freeze_digest,
            model_binding_digest=content_digest(binding),
            hidden_questions=hidden,
            examiner_reports=[],
            verdicts=[],
            executed_question_ids=[],
            unexecuted_question_ids=[
                str(question["question_id"]) for question in hidden
            ],
            slices=slices,
            model_state_drift=post,
            blind_status=blind_status,
        )
        report["sessions"] = {
            "platform_examiner": "not-started",
            "acceptance_judge": "not-started",
            "reason": (
                "real L0/L1 acceptance sessions are blocked on user authorization;"
                " every batch question is recorded as unexecuted"
            ),
        }
        report["full_pass"] = batch_report_is_full_pass(report)
        report_path = report_dir / "batch-report.json"
        _write_host_only_json(report_path, report, immutable=True)
        _write_host_only_json(
            report_dir / "attribution.json",
            {
                **acceptance_mode_evidence(batch_id=batch_id, freeze_digest=freeze_digest),
                "blind_status": blind_status["blind_status"],
                "exposed_question_ids": blind_status["exposed_question_ids"],
                "exposure_evidence_digest": blind_status["exposure_evidence_digest"],
            },
        )
        print(
            json.dumps(
                {
                    "run_id": contract["run_id"],
                    "batch_id": batch_id,
                    "freeze_digest": freeze_digest,
                    "report": report_path.as_posix(),
                    "acceptance_mode": "read-only-acceptance",
                    "blind_status": blind_status["blind_status"],
                    "start_ledger_write": False,
                    "consumes_semantic_start": False,
                    "full_pass": report["full_pass"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (TeamConfigurationError, CQContractError) as exc:
        print(f"cq-acceptance failed: {exc}", file=sys.stderr)
        return 2


def _write_host_only_json(path: Path, value: dict[str, object], *, immutable: bool = False) -> None:
    """Write a host-only report atomically with owner-only permissions.

    ``immutable`` publishes by exclusive create (an atomic hard link from a
    per-process temporary): a report another process published at ``path``
    after this command's admission-time check raises the typed immutable
    conflict instead of being replaced.  The temporary is per-process, so two
    concurrent publications of the same report can never corrupt each other's
    staging bytes either.
    """

    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    try:
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise TeamConfigurationError(
                    "cq_handoff_immutable: this attempt's batch report was published "
                    "by another acceptance process while this command ran; a "
                    "re-acceptance must request a new handoff to allocate a new attempt"
                ) from exc
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _run_checkpoint_inspect(args: argparse.Namespace, root: Path) -> int:
    """R3.0-015 S1 host-only ``checkpoint inspect`` (design §4.1, test plan M08).

    Strictly read-only against the run tree: published package count, sizes,
    retention state and -- with ``--checkpoint-id`` -- the one package's
    reusable artifacts, remaining work, write reconciliation, compatibility
    and estimated authorization consumption.  A malformed run id, a bad or
    nonexistent checkpoint id, and a path-escape attempt are typed rejections
    (stderr, exit 2); the command never silently substitutes another
    checkpoint and never writes the run, an Agent, or the platform.
    """

    run_id = args.run_id
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or run_id.startswith(".")
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
    ):
        print(
            "checkpoint failed: --run-id must be a single run-directory name, "
            "not a path",
            file=sys.stderr,
        )
        return 2
    run_root = root / "workspaces" / "modeling-runs" / run_id
    if not run_root.is_dir():
        print(
            f"checkpoint failed: run root for {run_id!r} does not exist under "
            "workspaces/modeling-runs",
            file=sys.stderr,
        )
        return 2
    try:
        result = inspect_checkpoints(run_root, args.checkpoint_id)
    except CheckpointError as exc:
        # The typed reason code/object/retry tuple goes to the host verbatim;
        # it never includes hidden CQ material or secrets.
        print(
            "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _run_checkpoint_resume_acceptance(
    args: argparse.Namespace, root: Path, *, forwarder_factory: object = McpReadForwarder
) -> int:
    """R3.0-015 S4: acceptance-only continuation of a handoff (design §7).

    Re-executes the production handoff's frozen acceptance batch independently
    of the terminated producer (M33): the read-only re-verification and the
    evidence inputs stay on the ORIGINAL run -- its old handoff, freezes and
    prior partial/fail reports are never rewritten -- while every new attempt,
    report and the host closing record land under the fresh output run root.
    No TeamRunner, Agent, Build Session or write session is ever constructed,
    and nothing is posted to the dead FIFO (M33/M35).  A complete usable PASS
    report means verification and host closing only, never a model re-call
    (M34); the continuation consumes zero semantic starts (M37).
    """

    runs_root = root / "workspaces" / "modeling-runs"
    source_root = runs_root / args.run_id
    if not source_root.is_dir():
        print(
            f"checkpoint failed: run root for {args.run_id!r} does not exist "
            "under workspaces/modeling-runs",
            file=sys.stderr,
        )
        return 2
    try:
        safe_new_run_id(args.new_run_id)
        root_run_id = checkpoint_root_run_id(source_root, args.checkpoint_id)
    except CheckpointError as exc:
        print(
            "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    # The same root-run lock as a production resume: one active recovery
    # process per root run on this machine, kernel-released on death.  The
    # conflict is itself a typed §8 rejection (source_active), so it must
    # reach the host as one in this mode too -- never an uncaught traceback.
    try:
        resume_lock = acquire_root_run_lock(root_run_id, runs_root)
    except CheckpointError as exc:
        print(
            "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    try:
        readback = http_readback(
            args.base_url, os.environ.get("ONTOLOGY_PLATFORM_ADMIN_API_KEY", "")
        )
        try:
            plan = prepare_acceptance_continuation(
                source_run_root=source_root,
                checkpoint_id=args.checkpoint_id,
                new_run_id=args.new_run_id,
                readback=readback,
                authorization_reference=args.authorization_reference,
            )
        except CheckpointError as exc:
            # Typed rejection, host-verbatim; the source run stays untouched.
            print(
                "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
                file=sys.stderr,
            )
            return 2
        output_root = runs_root / plan.new_run_id
        # The origin lands before any execution, so a continuation that dies
        # mid-flight still leaves the machine-checkable reference to its
        # source run and checkpoint (§7; also what later continuations and
        # manual cleanup check).
        write_acceptance_origin(plan, output_root)
        source_run_id = str(plan.origin.get("source_run_id"))
        record = {
            "schema_version": ACCEPTANCE_CONTINUATION_SCHEMA,
            "source_run_id": source_run_id,
            "checkpoint_id": plan.checkpoint_id,
            "new_run_id": plan.new_run_id,
            "batch_id": plan.batch_id,
            "freeze_digest": plan.freeze_digest,
            "attempt_id": plan.attempt_id,
            "prior_attempts": plan.prior_attempts,
            "output_root": str(output_root),
            "authorization_reference": args.authorization_reference,
            "accounting": {
                "semantic_starts": 0,
                "consumes_semantic_start": False,
                "kind": "acceptance_continuation",
                "platform_hard_gate": False,
            },
            "prep_seconds": plan.inspection["prep_timing"]["prep_seconds"],
        }
        if plan.complete_report is not None:
            # M34: a complete usable PASS report exists -> verify and close
            # only.  No Examiner session, no Judge session, no model call.
            write_acceptance_continuation_record(
                output_root,
                {
                    **record,
                    "mode": "verification-only-closing",
                    "verified_report": plan.inspection["complete_report"],
                    "model_sessions_started": 0,
                    "outcome": {"status": "closed", "full_pass": True},
                    "finished_at": datetime.now(UTC).isoformat(),
                },
            )
            print(
                json.dumps(
                    {
                        "source_run_id": source_run_id,
                        "new_run_id": plan.new_run_id,
                        "batch_id": plan.batch_id,
                        "attempt_id": plan.attempt_id,
                        "mode": "verification-only-closing",
                        "full_pass": True,
                        "verified_report": (
                            plan.complete_report_path.as_posix()
                            if plan.complete_report_path is not None
                            else None
                        ),
                        "model_sessions_started": 0,
                        "semantic_starts": 0,
                        "consumes_semantic_start": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        # M33/M34: re-execute the frozen batch's independent acceptance
        # through the existing cq-acceptance execution and Judge path.  The
        # frozen acceptance_target, question denominator and non-blind status
        # are unchanged; a prior partial/fail keeps its own attempt on the
        # source run and this attempt starts from the full denominator.
        cq_args = argparse.Namespace(
            run_root=source_root,
            # The digest-verified snapshot file (the Runner names it
            # freeze-NNNN; the handoff's freeze_id is the batch id).
            freeze_id=plan.freeze_file.stem,
            model_handoff=source_root / "acceptance-v3" / "production-handoff.json",
            model_profile=None,
            session_timeout=getattr(args, "session_timeout", None) or 300.0,
            unexecuted_report=False,
        )
        continuation = {
            "source_run_id": source_run_id,
            "checkpoint_id": plan.checkpoint_id,
            "attempt_id": plan.attempt_id,
            # JSON-safe by design: this mapping is echoed into the executed
            # report's stdout summary; the consumption sites re-wrap with
            # ``Path``.
            "output_root": output_root.as_posix(),
        }
        started = time.monotonic()
        status = 2
        try:
            status = _run_cq_acceptance(
                cq_args,
                root,
                forwarder_factory=forwarder_factory,
                continuation=continuation,
            )
        finally:
            # The host closing record captures the continuation's final state
            # (pass, fail, or a typed refusal after start): the original
            # Delivery/Runner process is gone, so nothing is posted to its
            # dead FIFO and the source run's own failure classification stays
            # exactly as it was.
            report_path = (
                output_root
                / "acceptance-v3"
                / "reports"
                / plan.batch_id
                / plan.attempt_id
                / "batch-report.json"
            )
            published = None
            if report_path.is_file():
                try:
                    published = json.loads(report_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    published = None
            full_pass = bool(
                isinstance(published, dict) and published.get("full_pass") is True
            )
            write_acceptance_continuation_record(
                output_root,
                {
                    **record,
                    "mode": "re-executed",
                    "exit_status": status,
                    "report_published": published is not None,
                    "full_pass": full_pass,
                    "report": report_path.as_posix(),
                    "acceptance_seconds": round(time.monotonic() - started, 3),
                    "outcome": (
                        {"status": "pass"}
                        if full_pass
                        else {
                            "status": "failed" if published is not None else "no-report",
                            "exit_status": status,
                        }
                    ),
                    "finished_at": datetime.now(UTC).isoformat(),
                },
            )
        return status
    finally:
        resume_lock.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="R2.3-001 foreground Team Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--profile", required=True, type=Path)
    validate.add_argument("--task", required=True, type=Path)
    validate.add_argument("--task-overlay", type=Path)
    validate.add_argument("--model-profile")
    run = subparsers.add_parser("run")
    run.add_argument("--profile", required=True, type=Path)
    run.add_argument("--task", required=True, type=Path)
    run.add_argument("--task-overlay", type=Path)
    run.add_argument("--model-profile")
    run.add_argument("--run-id", required=True)
    run.add_argument("--scope", required=True, type=Path)
    run.add_argument("--base-url", default="http://127.0.0.1:8001")
    run.add_argument("--freeze-started-at")
    run.add_argument(
        "--enable-outer-input-fifo",
        action="store_true",
        help=(
            "Create a local FIFO at <run-root>/control/outer-input.fifo so a "
            "background Host can send NDJSON outer actions while stdin is closed"
        ),
    )
    classify = subparsers.add_parser("classify-failure")
    classify.add_argument("--run-id", required=True)
    classify.add_argument(
        "--classification",
        required=True,
        choices=["modeling-quality", "platform-contract", "collaboration/routing", "runtime/infrastructure"],
    )
    classify.add_argument("--requirement-id", required=True)
    classify.add_argument("--ledger-root", type=Path)
    classify.add_argument("--ledger-filename")
    classify.add_argument("--lock-filename")
    classify.add_argument("--complete-modeling-quality-result", action="store_true")
    repair = subparsers.add_parser("authorize-repair")
    repair.add_argument("--requirement-id")
    repair.add_argument("--ledger-root", type=Path)
    repair.add_argument("--ledger-filename")
    repair.add_argument("--lock-filename")
    repair.add_argument("--failed-run-id", required=True)
    repair.add_argument("--baseline-hash", required=True)
    repair.add_argument("--repair-reference", required=True)
    budget = subparsers.add_parser("authorize-budget")
    budget.add_argument("--requirement-id")
    budget.add_argument("--ledger-root", type=Path)
    budget.add_argument("--ledger-filename")
    budget.add_argument("--lock-filename")
    budget.add_argument("--additional-starts", type=int, required=True)
    budget.add_argument("--authorization-id", required=True)
    budget.add_argument("--reference", required=True)
    initial = subparsers.add_parser("authorize-initial")
    initial.add_argument("--requirement-id", default="R2.3-003")
    initial.add_argument("--additional-starts", type=int, default=4)
    initial.add_argument("--authorization-id", default="user-20260811-r23003-start1-4")
    initial.add_argument("--reference", default="user-20260811-r23003-start1-4")
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--run-id", required=True)
    baseline.add_argument("--profile", required=True, type=Path)
    baseline.add_argument("--task", required=True, type=Path)
    baseline.add_argument("--task-overlay", type=Path)
    baseline.add_argument("--model-profile")
    handoff = subparsers.add_parser("publish-handoff")
    handoff.add_argument("--run-id", required=True)
    handoff.add_argument("--phase-a-verdict", required=True, type=Path)
    handoff.add_argument("--destination", required=True, type=Path)
    handoff.add_argument("--base-url", default="http://127.0.0.1:8001")
    cq_acceptance = subparsers.add_parser("cq-acceptance")
    cq_acceptance.add_argument("--run-root", required=True, type=Path)
    cq_acceptance.add_argument("--freeze-id", required=True)
    cq_acceptance.add_argument("--model-handoff", required=True, type=Path)
    cq_acceptance.add_argument("--model-profile", default=None)
    cq_acceptance.add_argument("--session-timeout", type=float, default=300.0)
    cq_acceptance.add_argument(
        "--unexecuted-report",
        action="store_true",
        help="write the all-unexecuted evidence report without starting any session",
    )
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint_subparsers = checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    checkpoint_inspect = checkpoint_subparsers.add_parser(
        "inspect",
        help=(
            "read-only inspection of persistent modeling checkpoints "
            "(R3.0-015 S1: save/inspect only, never a resume)"
        ),
    )
    checkpoint_inspect.add_argument("--run-id", required=True)
    checkpoint_inspect.add_argument(
        "--checkpoint-id",
        default=None,
        help="inspect one published checkpoint; omit to list every package",
    )
    checkpoint_resume = checkpoint_subparsers.add_parser(
        "resume",
        help=(
            "R3.0-015 S2/S4: cross-process resume from one published "
            "checkpoint (production resume or acceptance-only continuation)"
        ),
    )
    checkpoint_resume.add_argument("--run-id", required=True)
    checkpoint_resume.add_argument(
        "--checkpoint-id",
        required=True,
        help="the exact published checkpoint to resume (never auto-selected)",
    )
    checkpoint_resume.add_argument(
        "--new-run-id",
        required=True,
        help="the fresh run identity for the resumed production threads",
    )
    checkpoint_resume.add_argument(
        "--mode",
        required=True,
        choices=["production", "acceptance"],
        help=(
            "production resume (S2) or acceptance-only continuation of a "
            "production_handoff checkpoint (S4)"
        ),
    )
    checkpoint_resume.add_argument(
        "--session-timeout",
        type=float,
        default=300.0,
        help="acceptance-mode continuation: per-child session timeout seconds",
    )
    checkpoint_resume.add_argument(
        "--authorization-reference",
        default=None,
        help="host-recorded authorization reference for the ledger record; "
        "it never becomes an in-code start-count hard gate",
    )
    checkpoint_resume.add_argument("--base-url", default="http://127.0.0.1:8001")
    checkpoint_resume.add_argument(
        "--freeze-started-at",
        help="fresh CQ freeze timepoint for the new run; the old run's "
        "deadline is never inherited (design §4.2)",
    )
    checkpoint_resume.add_argument("--enable-outer-input-fifo", action="store_true")
    args = parser.parse_args()
    resume_requested = args.command == "checkpoint" and args.checkpoint_command == "resume"
    if args.command == "cq-acceptance":
        # R3.0-011: the read-only v3 acceptance entry stays outside the run
        # loader entirely; it never constructs a TeamRunner and never touches
        # the StartLedger.
        return _run_cq_acceptance(args, repository_root())
    if args.command == "checkpoint":
        # R3.0-015 S1+S2 (design §4.1): the host-only checkpoint entry.  It
        # shares ``run``'s host credential channel
        # (``ONTOLOGY_PLATFORM_ADMIN_API_KEY``); missing host credentials fail
        # closed with an accurate error instead of acting outside a host
        # environment.
        if not os.environ.get("ONTOLOGY_PLATFORM_ADMIN_API_KEY"):
            print(
                "checkpoint failed: host platform credential is missing; set "
                "ONTOLOGY_PLATFORM_ADMIN_API_KEY (the same host credential "
                "channel the run command uses)",
                file=sys.stderr,
            )
            return 2
        if args.checkpoint_command == "inspect":
            # Read-only inspection stays outside the run loader like
            # cq-acceptance: no TeamRunner, no Agent, nothing written (M08).
            return _run_checkpoint_inspect(args, repository_root())
        if args.mode == "acceptance":
            # R3.0-015 S4 (design §7): acceptance-only continuation of a
            # production_handoff checkpoint.  It stays outside the run loader
            # entirely -- no TeamRunner, no Agent, no Build Session or write
            # session -- only the read-only re-verification and the
            # independent cq-acceptance execution under a fresh output root.
            return _run_checkpoint_resume_acceptance(args, repository_root())
        # Production resume falls through into the shared run flow below with
        # ``resume_requested`` set; the one-process root-run lock is acquired
        # before reconciliation and released when the process exits.
    runner = None
    cleaned = False
    root = repository_root()
    if args.command == "classify-failure":
        if args.ledger_root is not None or args.ledger_filename is not None or args.lock_filename is not None:
            print("classification failed: ledger identity overrides are not accepted", file=sys.stderr)
            return 2
        try:
            StartLedger(
                root / "workspaces" / "modeling-runs", requirement_id=args.requirement_id
            ).terminal_failure(
                args.run_id, args.classification, args.complete_modeling_quality_result
            )
        except TeamConfigurationError as exc:
            print(f"classification failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "authorize-repair":
        if args.ledger_root is not None or args.ledger_filename is not None or args.lock_filename is not None:
            print("repair authorization failed: ledger identity overrides are not accepted", file=sys.stderr)
            return 2
        try:
            StartLedger(
                root / "workspaces" / "modeling-runs", requirement_id=args.requirement_id
            ).authorize_repair(
                args.failed_run_id, args.repair_reference, args.baseline_hash
            )
        except TeamConfigurationError as exc:
            print(f"repair authorization failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "authorize-budget":
        if args.ledger_root is not None or args.ledger_filename is not None or args.lock_filename is not None:
            print("budget authorization failed: ledger identity overrides are not accepted", file=sys.stderr)
            return 2
        try:
            StartLedger(
                root / "workspaces" / "modeling-runs", requirement_id=args.requirement_id
            ).authorize_budget(
                args.additional_starts, args.authorization_id, args.reference
            )
        except TeamConfigurationError as exc:
            print(f"budget authorization failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "authorize-initial":
        try:
            StartLedger(
                root / "workspaces" / "modeling-runs", requirement_id=args.requirement_id
            ).initial_authorization(
                args.additional_starts, args.authorization_id, args.reference
            )
        except TeamConfigurationError as exc:
            print(f"initial authorization failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "baseline":
        try:
            # R3.0-002 increment 6(b) completion: mirror the validate/run
            # dispatch so a multi-slice Task previews its baseline without the
            # strict four-role loader rejecting the three-role Profile.
            if task_declares_multi_slice_workflow(args.task):
                baseline_multi_slice = True
                baseline_formal_contract = None
            else:
                baseline_multi_slice = False
                baseline_formal_contract = formal_run_contract_for(
                    load_formal_team_configuration(args.profile, args.task, root=root)
                )
            _resolve_model_profile_selection(
                args.model_profile,
                baseline_formal_contract,
                multi_slice_workflow=baseline_multi_slice,
            )
            manifest, baseline_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=args.run_id,
                profile_path=args.profile,
                task_path=args.task,
                task_overlay_path=args.task_overlay,
                model_profile_id=args.model_profile,
            )
        except TeamConfigurationError as exc:
            print(f"baseline failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"run_id": args.run_id, "baseline_hash": baseline_hash, "manifest": manifest}))
        return 0
    if args.command == "publish-handoff":
        try:
            create, revoke = _bootstrap_helpers(root)
            publish_offline_scope_handoff(
                run_root=root / "workspaces" / "modeling-runs" / args.run_id,
                expected_run_id=args.run_id,
                base_url=args.base_url,
                phase_a_verdict_artifact=args.phase_a_verdict,
                destination=args.destination,
                bootstrap_admin=create,
                revoke_admin=revoke,
            )
        except (OSError, TeamConfigurationError) as exc:
            print(f"handoff publish failed: {exc}", file=sys.stderr)
            return 2
        return 0
    try:
        if resume_requested:
            # R3.0-015 S2: the contract comes from the checkpoint manifest;
            # prepare_from_checkpoint re-runs the real loader inside prepare,
            # so no CLI-side profile/task/scope argument exists to load here.
            configuration = None
            formal_contract = None
            task_overlay = None
            multi_slice = True
            selected_model_profile_id = None
            team_model_profile = None
        else:
            # R3.0-002 increment 6(b): multi-slice tasks load through the
            # non-formal three-role branch; every other task keeps the strict
            # formal loader (and its cross-wire guard) unchanged.
            multi_slice = task_declares_multi_slice_workflow(args.task)
            if multi_slice:
                configuration = load_multi_slice_team_configuration(
                    args.profile, args.task, root=root
                )
                formal_contract = None
            else:
                configuration = load_formal_team_configuration(args.profile, args.task, root=root)
                formal_contract = formal_run_contract_for(configuration)
            if formal_contract is not None and formal_contract.requirement_id == "R2.3-003":
                configuration, formal_contract = load_formal_run_configuration(
                    args.profile, args.task, root=root
                )
            elif formal_contract is None and not multi_slice and (
                getattr(getattr(configuration, "profile", None), "profile_id", None)
                in FORMAL_PROFILE_IDS
                or getattr(getattr(configuration, "task", None), "task_id", None)
                in FORMAL_TASK_IDS
            ):
                raise TeamConfigurationError("unknown or cross-wired formal run contract")
            task_overlay = (
                load_task_input_overlay(
                    args.task_overlay,
                    root=root,
                    task_path=args.task,
                    task=configuration.task,
                )
                if args.task_overlay is not None
                else None
            )
            if task_overlay is not None:
                validate_candidate_publication(task_overlay)
            # All three commands share this one loader; validate additionally prints
            # the safe per-role requested/effective projection.
            selected_model_profile_id = _resolve_model_profile_selection(
                args.model_profile, formal_contract, multi_slice_workflow=multi_slice
            )
            # ``run`` deliberately defers the profile load to TeamRunner.prepare,
            # whose formal model gate has zero side effects before platform
            # preflight; only ``validate`` prints the projection eagerly here.
            team_model_profile = None
            if args.command == "validate" and selected_model_profile_id is not None:
                team_model_profile = load_team_model_profile(root, selected_model_profile_id)
    except TeamConfigurationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "profile_id": configuration.profile.profile_id,
                    "task_id": configuration.task.task_id,
                    "task_overlay_id": task_overlay.overlay_id if task_overlay else None,
                    "model_profile": (
                        team_model_profile.as_dict() if team_model_profile else None
                    ),
                    "roster": [
                        agent.agent_id for agent in configuration.profile.agents
                    ],
                }
            )
        )
        return 0
    handoff_root = _monitor_handoff_root()

    def cleanup_once() -> None:
        nonlocal cleaned
        if runner is not None and not cleaned:
            runner.cleanup()
            cleaned = True

    outer_input = None
    resume_lock = None
    try:
        adapter = CodexRuntimeAdapter(repository_root=root)
        formal_acceptance = formal_contract is not None
        if resume_requested:
            # R3.0-015 S2 production resume (design §4.2): the same-machine
            # one-process lock keyed by root_run_id plus the platform
            # Session/Lease/Attempt checks inside the reconciliation prevent a
            # second active production writer; the lock is kernel-released if
            # this process dies.
            runs_root = root / "workspaces" / "modeling-runs"
            source_root = runs_root / args.run_id
            if not source_root.is_dir():
                print(
                    f"checkpoint failed: run root for {args.run_id!r} does not "
                    "exist under workspaces/modeling-runs",
                    file=sys.stderr,
                )
                return 2
            try:
                root_run_id = checkpoint_root_run_id(source_root, args.checkpoint_id)
                resume_lock = acquire_root_run_lock(root_run_id, runs_root)
            except CheckpointError as exc:
                # The lock conflict (source_active) and the checkpoint lookup
                # are typed rejections here too -- they must never degrade to
                # a generic "run failed" line in the production channel.
                print(
                    "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
                    file=sys.stderr,
                )
                return 2
            create, revoke = _bootstrap_helpers(root)

            def resume_scope_factory(item):
                return PlatformScope(args.base_url, item.run_id, create, revoke)

            runner = TeamRunner(
                repository_root=root,
                adapter=adapter,
                scope_factory=resume_scope_factory,
                freeze_started_at=args.freeze_started_at,
                canonical_base_url=args.base_url,
                canonical_admin_key=os.environ.get("ONTOLOGY_PLATFORM_ADMIN_API_KEY"),
            )
            try:
                runner.prepare_from_checkpoint(
                    source_run_root=source_root,
                    checkpoint_id=args.checkpoint_id,
                    new_run_id=args.new_run_id,
                    authorization_reference=args.authorization_reference,
                )
            except CheckpointError as exc:
                # The typed reason tuple reaches the host verbatim (no hidden
                # CQ material, no secrets); the source run stays untouched.
                cleanup_once()
                print(
                    "checkpoint failed: " + json.dumps(exc.data(), ensure_ascii=False),
                    file=sys.stderr,
                )
                return 2
        else:
            scope = yaml.safe_load(args.scope.read_text(encoding="utf-8"))
            if not isinstance(scope, dict):
                raise TeamConfigurationError("scope must be a YAML object")
            if formal_contract is not None:
                # Reject existing identifiers before constructing the scope owner or
                # touching the bootstrap credential path.  TeamRunner repeats this
                # check so non-CLI callers cannot bypass the boundary.
                scope = normalize_scope_for_contract(scope, formal_contract.scope_mode)
                scope_factory = None
            else:
                create, revoke = _bootstrap_helpers(root)

                def scope_factory(item):
                    return PlatformScope(args.base_url, item.run_id, create, revoke)
            runner = TeamRunner(
                repository_root=root,
                adapter=adapter,
                scope_factory=scope_factory,
                freeze_started_at=args.freeze_started_at,
                canonical_base_url=args.base_url,
                canonical_admin_key=os.environ.get("ONTOLOGY_PLATFORM_ADMIN_API_KEY"),
            )
            runner.prepare(
                run_id=args.run_id,
                profile_path=args.profile,
                task_path=args.task,
                scope=scope,
                task_overlay_path=args.task_overlay,
                model_profile_id=args.model_profile,
            )
        if formal_acceptance:
            # The Delivery-only key is needed by the no-start canonical gate,
            # but must not remain available to any later adapter/bootstrap or
            # persistent Agent process.  Formal callers read it from the
            # environment during prepare; scrub both process and runner state
            # immediately after that gate succeeds.
            os.environ.pop("ONTOLOGY_PLATFORM_ADMIN_API_KEY", None)
            if getattr(runner, "canonical_admin_key", None) is not None:
                runner.canonical_admin_key = None
        if getattr(runner, "_staged_decisions", False):
            # The staged write path is fail-closed in TeamRunner until a host-side
            # write forwarder is bound; prepare() has now selected it.  The run's
            # own protocol key is only recorded once start() runs, so it is read
            # per call, and every call owns and closes its own canonical MCP child.
            def staged_batch_write_forwarder(batch):
                return forward_staged_modeling_batch(
                    batch,
                    repository_root=root,
                    protocol_key=runner.run.protocol_key,
                )

            runner.staged_batch_forwarder = staged_batch_write_forwarder

            # #17: the same binding for the evidence-repost projection, which
            # carries the owner-authorized evidence a materialized item's lineage
            # needs.  It reaches ``associate_evidence_reference`` and nothing else.
            def staged_evidence_association_forwarder(association):
                return forward_staged_associate_evidence(
                    association,
                    repository_root=root,
                    protocol_key=runner.run.protocol_key,
                )

            runner.staged_evidence_forwarder = staged_evidence_association_forwarder
        # Host auth is no longer probed unconditionally here.  TeamRunner's
        # prepare already ran the profile-scoped credential preflights
        # (including the conditional Codex ChatGPT subscription check for
        # ``openai-codex`` routes) before any reservation or Agent start, and
        # the runtime re-validates its Host auth source while staging each
        # private role.
        if formal_acceptance:
            # Bootstrap is intentionally reachable only after the no-start
            # checkout/canonical-mode gate has passed and the run root exists.
            create, revoke = _bootstrap_helpers(root)
            runner.scope_factory = lambda item: PlatformScope(
                args.base_url, item.run_id, create, revoke
            )
        if handoff_root is not None:
            write_runner_phase(handoff_root, "prepared", run_root=runner.run.root)
        # The FIFO is created after prepare() (run root exists) and before
        # start() (Agents begin).  A background Host whose stdin is /dev/null
        # can then write NDJSON outer actions to this path for the live run.
        if getattr(args, "enable_outer_input_fifo", False):
            fifo_path = runner.run.root / "control" / "outer-input.fifo"
            outer_input = OuterInputFifo(fifo_path)
            outer_input.open()
            print(f"outer-input-fifo: {fifo_path}", file=sys.stderr)
        runner.start()
        _foreground_event_loop(
            runner,
            sys.stdin,
            lambda output: print(json.dumps(output, ensure_ascii=False), flush=True),
            outer_input=outer_input,
        )
        if not _terminal_report_complete(runner):
            if formal_acceptance:
                runner.record_terminal_failure("collaboration/routing", False)
            if formal_acceptance or handoff_root is not None:
                _write_runner_handoff_failed(handoff_root, runner.run.root)
                raise RuntimeError("foreground CLI ended before terminal report completion")
        if handoff_root is not None:
            write_runner_phase(handoff_root, "cleanup_pending", run_root=runner.run.root)
            _await_monitor_extraction(handoff_root, runner.run.root)
    except KeyboardInterrupt:
        _write_runner_handoff_failed(handoff_root, _runner_root(runner))
        cleanup_once()
        return 130
    except FormalCandidateProgressTimeout as exc:
        _write_runner_handoff_failed(handoff_root, _runner_root(runner))
        # Timeout is a latched terminal failure.  Perform exactly one cleanup
        # attempt, then make its final outcome explicit for the independent
        # Acceptance reader; never fall through to the ordinary CLEANED path.
        try:
            cleanup_once()
        except Exception as cleanup_exc:
            try:
                if runner is not None:
                    runner._state(  # type: ignore[attr-defined]
                        "TERMINAL_FAILURE_CLEANUP_FAILED",
                        cleanup_exception=type(cleanup_exc).__name__,
                        terminal_finalization_complete=False,
                    )
            except Exception:
                pass
            print(f"run failed: {exc}; cleanup failed", file=sys.stderr)
            return 2
        try:
            if runner is not None:
                runner._state(  # type: ignore[attr-defined]
                    "TERMINAL_FAILURE_CLEANED",
                    resource_cleanup_complete=True,
                    terminal_finalization_complete=True,
                )
        except Exception as finalization_exc:
            try:
                if runner is not None:
                    runner._state(  # type: ignore[attr-defined]
                        "TERMINAL_FAILURE_CLEANUP_FINALIZATION_FAILED",
                        resource_cleanup_complete=True,
                        terminal_finalization_complete=False,
                        finalization_exception=type(finalization_exc).__name__,
                    )
            except Exception:
                pass
            print(f"run failed: {exc}; terminal finalization failed", file=sys.stderr)
            return 2
        print(f"run failed: {exc}", file=sys.stderr)
        return 2
    except PlatformScopeMissingError as exc:
        if not resume_requested:
            # Non-resume callers keep the raw platform exception semantics.
            raise
        # R3.0-015 design §5.2/§8: a checkpoint-bound scope resource that no
        # longer exists is the advertised ``scope_missing`` typed rejection --
        # never a generic failure line, and never a blank scope faked as a
        # resume.
        _write_runner_handoff_failed(handoff_root, _runner_root(runner))
        cleanup_once()
        _settle_ledger_after_fatal_host_failure(runner)
        print(
            "checkpoint failed: "
            + json.dumps(scope_missing_rejection(str(exc)).data(), ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, RuntimeError, TeamConfigurationError) as exc:
        _write_runner_handoff_failed(handoff_root, _runner_root(runner))
        cleanup_once()
        _settle_ledger_after_fatal_host_failure(runner)
        print(f"run failed: {exc}", file=sys.stderr)
        return 2
    else:
        cleanup_once()
    finally:
        # The foreground loop has exited on every path; retire the FIFO exactly
        # once regardless of which handler returned.  ``outer_input`` stays
        # ``None`` when the flag was off or before the FIFO was assigned.
        if outer_input is not None:
            outer_input.close()
        if resume_lock is not None:
            # R3.0-015 S2: release the root-run resume lock exactly once; the
            # kernel already released it if this process died mid-run.
            resume_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
