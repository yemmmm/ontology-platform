from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from pathlib import Path

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
from .acceptance_runtime import build_platform_batch_packet
from .competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
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
    validate_model_binding,
)
from .outer_input import OuterInputFifo, OuterInputFramingError
from .platform_scope import PlatformScope
from .preflight import normalize_scope_for_contract
from .runner import TeamRunner
from .candidate_publication import validate_candidate_publication
from .candidate_progress import FormalCandidateProgressTimeout
from .runtimes.codex import CodexRuntimeAdapter
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
    """

    transport = getattr(runner, "transport", None)
    issue_ledger = getattr(transport, "issue_ledger", None)
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
    model_profile_id: str | None, formal_contract: FormalRunContract | None
) -> str | None:
    """Resolve the shared ``--model-profile`` selection for all three commands.

    ``validate``/``baseline``/``run`` accept only a restricted profile ID, never a
    path, URL, or environment override.  Omitting the flag keeps the formal run
    contract default; a non-formal fixture can never be promoted to a formal
    provider route.
    """

    if model_profile_id is None:
        return None if formal_contract is None else formal_contract.default_model_profile_id
    if formal_contract is None:
        raise TeamConfigurationError(
            "model profile selection requires a formal run contract"
        )
    return model_profile_id


_CQ_RUN_CONTRACT_SCHEMA = "r3-0-011-run-contract/v1"


def _read_json_object(path: Path) -> dict[str, object]:
    """Read one JSON object file, raising ``TeamConfigurationError`` on any drift."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TeamConfigurationError(f"{path} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError(f"{path} must contain a JSON object")
    return value


def _run_cq_acceptance(args: argparse.Namespace, root: Path) -> int:
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
        post_binding = handoff.get("post_batch_model_binding")
        if not isinstance(post_binding, dict):
            raise TeamConfigurationError(
                "cq_model_binding_missing: model handoff carries no post-batch state recheck"
            )
        post = model_binding_drift(binding, post_binding)
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
                authorized_scope=[str(item) for item in authorized],
                model_binding=binding,
                authorized_read_tools=[
                    str(tool) for tool in binding["ontologies"][0]["authorized_read_tools"]
                ],
                report_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
                session={"mode": "single-continuous-batch", "ordered": True},
            )
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
        if packet is not None:
            _write_host_only_json(
                report_dir / "batch-packet.json",
                {"schema_version": packet.schema_version, "canonical_digest": packet.canonical_digest},
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
                baseline_formal_contract = None
            else:
                baseline_formal_contract = formal_run_contract_for(
                    load_formal_team_configuration(args.profile, args.task, root=root)
                )
            _resolve_model_profile_selection(
                args.model_profile, baseline_formal_contract
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
            args.model_profile, formal_contract
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
