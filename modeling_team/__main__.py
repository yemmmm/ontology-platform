from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from pathlib import Path

import yaml

from .contracts import TeamConfigurationError, load_formal_team_configuration, repository_root
from .handoff import publish_offline_scope_handoff
from .monitor_handoff import (
    HANDOFF_CONTRACT_RELATIVE_PATH,
    HANDOFF_ENV,
    load_handoff_contract,
    output_digest,
    read_phase,
    write_runner_phase,
)
from .platform_scope import PlatformScope
from .preflight import normalize_formal_scope
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
    {"question", "issue_resolution", "user", "status", "pause", "resume", "stop"}
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


def _foreground_event_loop(runner, stream, emit, *, select_fn=select.select) -> None:
    """Pump App Server events even when an outer user sends no further input."""

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

    while True:
        output = runner.drain()
        if output:
            emit_and_observe(output)
        if _terminal_report_complete(runner):
            return
        readable, _, _ = select_fn([stream], [], [], 0.1)
        if not readable:
            continue
        line = stream.readline()
        if not line:
            return
        try:
            message = _decode_foreground_message(line)
        except TeamConfigurationError:
            emit_outer_input_rejection()
            continue
        action = message.get("action")
        if not isinstance(action, str) or action not in _KNOWN_OUTER_ACTIONS:
            # A missing/unknown action is a malformed outer control-plane
            # message.  Reject only this line so a later valid command can
            # still drive the live Runner; admitted actions retain the
            # existing fatal receive_outer boundary below.
            emit_outer_input_rejection()
            continue
        if (
            action == "issue_resolution"
            and not _foreground_issue_resolution_is_ready(runner)
        ):
            emit_outer_input_rejection()
            continue
        # Once the input is admitted by the narrow cooperative issue gate,
        # preserve the existing fatal boundary.  In particular, do not catch
        # TeamConfigurationError raised by receive_outer's internal drain or
        # by persistence/Runtime delivery failures.
        output = runner.receive_outer(message)
        if output:
            emit_and_observe(output)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="R2.3-001 foreground Team Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--profile", required=True, type=Path)
    validate.add_argument("--task", required=True, type=Path)
    validate.add_argument("--task-overlay", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", required=True, type=Path)
    run.add_argument("--task", required=True, type=Path)
    run.add_argument("--task-overlay", type=Path)
    run.add_argument("--run-id", required=True)
    run.add_argument("--scope", required=True, type=Path)
    run.add_argument("--base-url", default="http://127.0.0.1:8001")
    run.add_argument("--freeze-started-at")
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
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--run-id", required=True)
    baseline.add_argument("--profile", required=True, type=Path)
    baseline.add_argument("--task", required=True, type=Path)
    baseline.add_argument("--task-overlay", type=Path)
    handoff = subparsers.add_parser("publish-handoff")
    handoff.add_argument("--run-id", required=True)
    handoff.add_argument("--phase-a-verdict", required=True, type=Path)
    handoff.add_argument("--destination", required=True, type=Path)
    handoff.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
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
    if args.command == "baseline":
        try:
            manifest, baseline_hash = TeamRunner.preview_baseline(
                repository_root=root,
                run_id=args.run_id,
                profile_path=args.profile,
                task_path=args.task,
                task_overlay_path=args.task_overlay,
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
        configuration = load_formal_team_configuration(args.profile, args.task, root=root)
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

    try:
        adapter = CodexRuntimeAdapter(repository_root=root)
        scope = yaml.safe_load(args.scope.read_text(encoding="utf-8"))
        if not isinstance(scope, dict):
            raise TeamConfigurationError("scope must be a YAML object")
        schema_version = getattr(getattr(configuration, "task", None), "schema_version", 1)
        formal_acceptance = (
            schema_version == 2
            and (
                getattr(getattr(configuration, "task", None), "task_id", None)
                == "r2-3-005-formal-acceptance"
                or getattr(getattr(configuration, "profile", None), "profile_id", None)
                == "r2-3-005-modeling-team"
            )
        )
        if formal_acceptance:
            # Reject existing identifiers before constructing the scope owner or
            # touching the bootstrap credential path.  TeamRunner repeats this
            # check so non-CLI callers cannot bypass the boundary.
            scope = normalize_formal_scope(scope)
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
        )
        runner.prepare(
            run_id=args.run_id,
            profile_path=args.profile,
            task_path=args.task,
            scope=scope,
            task_overlay_path=args.task_overlay,
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
        # Host Codex auth is inspected only after TeamRunner has completed its
        # clean-checkout/canonical/health gate.  No Agent is started until this
        # defensive source check succeeds.
        getattr(adapter, "preflight_host_auth", lambda: None)()
        if formal_acceptance:
            # Bootstrap is intentionally reachable only after the no-start
            # checkout/canonical-mode gate has passed and the run root exists.
            create, revoke = _bootstrap_helpers(root)
            runner.scope_factory = lambda item: PlatformScope(
                args.base_url, item.run_id, create, revoke
            )
        if handoff_root is not None:
            write_runner_phase(handoff_root, "prepared", run_root=runner.run.root)
        runner.start()
        _foreground_event_loop(
            runner,
            sys.stdin,
            lambda output: print(json.dumps(output, ensure_ascii=False), flush=True),
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
        print(f"run failed: {exc}", file=sys.stderr)
        return 2
    else:
        cleanup_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
