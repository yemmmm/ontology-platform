from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import sys
import time
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
    build_acceptance_judge_packet,
    build_platform_batch_packet,
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
from .platform_scope import PlatformScope
from .preflight import normalize_scope_for_contract
from .runner import TeamRunner
from .candidate_publication import validate_candidate_publication
from .candidate_progress import FormalCandidateProgressTimeout
from .runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
from .staged_batch_write_forwarder import forward_staged_modeling_batch
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
        # R3.0-011: competency-question direct-channel inputs.  They are
        # dispatched by the narrow CQ branch below and never reach
        # ``receive_outer``.
        "cq_interview",
        "cq_review",
        "cq_freeze",
        "cq_handoff_complete",
    }
)

# R3.0-011 competency-question direct-channel actions (dispatched before the
# fatal ``receive_outer`` boundary, and only when the runner carries CQ input
# support).  ``cq_freeze`` is the Delivery-host freeze trigger (Round 1 F2).
_CQ_OUTER_ACTIONS = frozenset(
    {"cq_interview", "cq_review", "cq_freeze", "cq_handoff_complete"}
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
    exists.  The fatal ``receive_outer`` boundary is preserved: a
    ``TeamConfigurationError`` raised inside ``receive_outer`` (or its drain)
    propagates and tears the run down, exactly as before.
    """
    try:
        message = _decode_foreground_message(line)
    except TeamConfigurationError:
        emit_outer_input_rejection()
        return
    action = message.get("action")
    if not isinstance(action, str) or action not in _KNOWN_OUTER_ACTIONS:
        # A missing/unknown action is a malformed outer control-plane message.
        # Reject only this line so a later valid command can still drive the
        # live Runner; admitted actions retain the existing fatal receive_outer
        # boundary below.
        emit_outer_input_rejection()
        return
    if (
        action == "issue_resolution"
        and not _foreground_issue_resolution_is_ready(runner)
    ):
        emit_outer_input_rejection()
        return
    if _handle_cq_outer_message(runner, message, emit_and_observe):
        # R3.0-011: CQ inputs are fully handled ahead of the fatal boundary.
        return
    # Once admitted, preserve the existing fatal boundary.  Do not catch
    # TeamConfigurationError raised by receive_outer's internal drain or by
    # persistence/Runtime delivery failures.
    output = runner.receive_outer(message)
    if output:
        emit_and_observe(output)


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

    def emit_outer_input_rejection() -> None:
        # This is a control-plane error, not a Runner delivery.  Do not route
        # it through ``observe_foreground_output``: formal display binding
        # must only inspect Runner-generated delivery envelopes.
        emit([dict(_OUTER_INPUT_REJECTION)])

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
            _handle_foreground_message(
                runner, line, emit_and_observe, emit_outer_input_rejection
            )
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
                _handle_foreground_message(
                    runner, line, emit_and_observe, emit_outer_input_rejection
                )
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
            _handle_foreground_message(
                runner, line, emit_and_observe, emit_outer_input_rejection
            )
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


def _cq_observed_state_entry(
    context: object, project_id: str, ontology_id: str, read_tools: list[str]
) -> dict[str, object]:
    """Summarize one actual read-only workspace observation as a binding entry.

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
        context = forward("get_ontology_workspace_context", {"ontology_id": ontology_id}, read_key)
        observed_entry = _cq_observed_state_entry(
            context,
            str(entry["project_id"]),
            ontology_id,
            [str(tool) for tool in entry["authorized_read_tools"]],
        )
        observed.append(observed_entry)
        graph_set_ids[ontology_id] = str(
            context["default_graph_set_id"] if isinstance(context, dict) else ""
        )
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": binding["batch_id"],
        "freeze_digest": binding["freeze_digest"],
        "bound_at": binding["bound_at"],
        "ontologies": observed,
    }, graph_set_ids


def _cq_resolve_manifest_entry(
    manifest: list[object], source_name: str
) -> dict[str, object] | None:
    """Resolve one frozen evidence source to at most one staged source entry.

    An exact manifest path wins; otherwise the reference must match exactly one
    manifest entry by file name.  Any ambiguity is a typed failure instead of a
    silent pick, so the judge is never handed a guessed source.
    """

    if not source_name:
        return None
    exact = [
        item for item in manifest if isinstance(item, dict) and item.get("path") == source_name
    ]
    if len(exact) > 1:
        raise TeamConfigurationError(
            f"cq_evidence_unresolved: evidence source {source_name!r} matches several staged "
            "run sources"
        )
    if len(exact) == 1:
        return exact[0]
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


def _cq_build_judge_evidence_bundle(
    run_root: Path, freeze: dict[str, object], hidden: list[dict[str, object]]
) -> dict[str, object]:
    """Assemble the judge evidence bundle from the run's approved bytes.

    Every frozen ``evidence_refs`` entry is resolved to the Runner's staged
    role-source copies (``<run-root>/sources/<role>/<relative_path>``, named by
    ``source-manifest.json``) or to the Runner's private interview records, then
    copied verbatim with its locator, a recomputed content digest and the
    freeze review version.  A reference that resolves to nothing, to an
    ambiguity, or to modified bytes is a typed failure: the judge is never
    handed a bare path, a guess, or tampered material.
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
    for question in hidden:
        question_id = str(question["question_id"])
        refs = question.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise TeamConfigurationError(
                f"cq_evidence_unresolved: question {question_id} lists no evidence reference"
            )
        for ref in refs:
            if not isinstance(ref, dict):
                raise TeamConfigurationError(
                    f"cq_evidence_unresolved: question {question_id} has a malformed evidence "
                    "reference"
                )
            source_name = str(ref.get("source") or "")
            entry = _cq_resolve_manifest_entry(manifest, source_name)
            record = _cq_resolve_interview_record(run_root, source_name)
            if entry is not None and record is not None:
                raise TeamConfigurationError(
                    f"cq_evidence_unresolved: evidence source {source_name!r} for question "
                    f"{question_id} resolves to both a staged source and an interview record"
                )
            if entry is not None:
                content = _cq_read_approved_source_copy(run_root, entry, question_id)
            elif record is not None:
                content = _cq_read_interview_record(record, question_id)
            else:
                raise TeamConfigurationError(
                    f"cq_evidence_unresolved: evidence source {source_name!r} for question "
                    f"{question_id} matches no staged run source or recorded interview"
                )
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
    try:
        validate_evidence_bundle(bundle)
    except ValueError as exc:
        raise TeamConfigurationError(f"cq_evidence_unresolved: evidence bundle is invalid: {exc}") from exc
    # The judge packet seam re-validates the bundle against the same strict
    # exact-fields contract, so the packet must receive the raw schema bundle:
    # ``validate_evidence_bundle``'s return value carries a derived
    # ``bundle_digest`` field that would fail its own re-validation.
    return bundle


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
    "each answer, not verbatim equality; a supported explicit_unknown passes. For each "
    "question call submit_examiner_report exactly once with schema_version, batch_id, "
    "question_id, verdict, failure_layer, conflicting_evidence and note. Do not re-derive "
    "answers from anything outside the packet; use verdict question-answer-review when "
    "the material is genuinely ambiguous or the question or its frozen reference answer "
    "conflicts with the approved material or is unsupported by it."
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
    """

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
            executed = [
                str(report["question_id"])
                for report in reports
                if isinstance(report, dict)
                and report.get("status") != "runtime-incomplete"
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
        batch_complete = packet is not None and hidden and not failure_reason and (
            len(reports) == len(hidden)
        )
        evidence_bundle: dict[str, object] | None = None
        if batch_complete:
            try:
                evidence_bundle = _cq_build_judge_evidence_bundle(run_root, freeze, hidden)
            except TeamConfigurationError as exc:
                lifecycle_errors.append(
                    {"stage": "judge-evidence-bundle", "reason": str(exc)}
                )
        if (
            batch_complete
            and evidence_bundle is not None
            and post_read_ok
            and not post_drift
        ):
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
                    examiner_reports=[dict(report) for report in reports],
                    verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
                )
                adapter = CodexRuntimeAdapter(repository_root=root)
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
                sessions["acceptance_judge"] = {"verdicts": len(verdicts)}
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
                    "judge session skipped: the examiner batch is incomplete, the judge "
                    "evidence is unresolved, the post-batch state read failed or the "
                    "platform state drifted"
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
    }
    report["full_pass"] = (
        batch_report_is_full_pass(report) and not lifecycle_errors and not cleanup_failed
    )
    report_path = report_dir / "batch-report.json"
    _write_host_only_json(report_path, report)
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
) -> int:
    """Read-only v3 hidden-batch acceptance entry (R3.0-011 design §4.0).

    The command is Delivery-invoked and strictly read-only for the platform: it
    writes no StartLedger record, consumes no fresh semantic start, and never
    starts, continues, or repairs the production run.  A run root without the
    Runner-written v3 configuration snapshot is a legacy R2.3 run and is
    rejected instead of being switched to this contract by the command name.
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
        report_dir = run_root / "acceptance-v3" / "reports" / batch_id
        report_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        handoff = _read_json_object(args.model_handoff)
        delivery = handoff.get("production_delivery")
        if not isinstance(delivery, dict):
            raise TeamConfigurationError(
                "cq_batch_scope_unauthorized: model handoff carries no production delivery receipt"
            )
        if delivery.get("ready") is not True or delivery.get("pending_writes") is not False:
            raise TeamConfigurationError(
                "cq_batch_scope_unauthorized: production delivery is not ready for acceptance"
            )
        # The 008B joint checklist stays pending-safe: it is never required to
        # have passed before this command runs (design §4.0).
        authorized = handoff.get("authorized_ontology_ids")
        if not isinstance(authorized, list) or not authorized or any(
            not isinstance(item, str) or not item for item in authorized
        ):
            raise TeamConfigurationError(
                "cq_batch_scope_unauthorized: model handoff lists no authorized Ontology"
            )
        binding = validate_model_binding(
            handoff.get("model_binding"), authorized_ontology_ids=[str(item) for item in authorized]
        )
        if binding.get("batch_id") != batch_id:
            raise TeamConfigurationError(
                "cq_model_binding_missing: model binding batch does not match the frozen batch"
            )
        freeze_digest = str(freeze["snapshot_digest"])
        if binding.get("freeze_digest") != freeze_digest:
            raise TeamConfigurationError(
                "cq_model_binding_missing: model binding is not bound to this freeze snapshot"
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
        _write_host_only_json(report_path, report)
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


def _write_host_only_json(path: Path, value: dict[str, object]) -> None:
    """Write a host-only report atomically with owner-only permissions."""

    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


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
    args = parser.parse_args()
    if args.command == "cq-acceptance":
        # R3.0-011: the read-only v3 acceptance entry stays outside the run
        # loader entirely; it never constructs a TeamRunner and never touches
        # the StartLedger.
        return _run_cq_acceptance(args, repository_root())
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
    try:
        adapter = CodexRuntimeAdapter(repository_root=root)
        scope = yaml.safe_load(args.scope.read_text(encoding="utf-8"))
        if not isinstance(scope, dict):
            raise TeamConfigurationError("scope must be a YAML object")
        formal_acceptance = formal_contract is not None
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
