from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from pathlib import Path

import yaml

from .contracts import TeamConfigurationError, load_team_configuration, repository_root
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
from .runner import TeamRunner
from .runtimes.codex import CodexRuntimeAdapter
from .start_ledger import StartLedger


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


def _foreground_event_loop(runner, stream, emit, *, select_fn=select.select) -> None:
    """Pump App Server events even when an outer user sends no further input."""
    while True:
        output = runner.drain()
        if output:
            emit(output)
        if _terminal_report_complete(runner):
            return
        readable, _, _ = select_fn([stream], [], [], 0.1)
        if not readable:
            continue
        line = stream.readline()
        if not line:
            return
        output = runner.receive_outer(json.loads(line))
        if output:
            emit(output)


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
    run = subparsers.add_parser("run")
    run.add_argument("--profile", required=True, type=Path)
    run.add_argument("--task", required=True, type=Path)
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
    classify.add_argument("--complete-modeling-quality-result", action="store_true")
    repair = subparsers.add_parser("authorize-repair")
    repair.add_argument("--failed-run-id", required=True)
    repair.add_argument("--baseline-hash", required=True)
    repair.add_argument("--repair-reference", required=True)
    budget = subparsers.add_parser("authorize-budget")
    budget.add_argument("--additional-starts", type=int, required=True)
    budget.add_argument("--authorization-id", required=True)
    budget.add_argument("--reference", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--run-id", required=True)
    baseline.add_argument("--profile", required=True, type=Path)
    baseline.add_argument("--task", required=True, type=Path)
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
        try:
            StartLedger(root / "workspaces" / "modeling-runs").terminal_failure(
                args.run_id, args.classification, args.complete_modeling_quality_result
            )
        except TeamConfigurationError as exc:
            print(f"classification failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "authorize-repair":
        try:
            StartLedger(root / "workspaces" / "modeling-runs").authorize_repair(
                args.failed_run_id, args.repair_reference, args.baseline_hash
            )
        except TeamConfigurationError as exc:
            print(f"repair authorization failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "authorize-budget":
        try:
            StartLedger(root / "workspaces" / "modeling-runs").authorize_budget(
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
        configuration = load_team_configuration(args.profile, args.task, root=root)
    except TeamConfigurationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "profile_id": configuration.profile.profile_id,
                    "task_id": configuration.task.task_id,
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
        # RuntimeAdapter doubles used by the foreground loop do not stage private Codex files.
        # The production Codex adapter always exposes this defensive preflight.
        getattr(adapter, "preflight_host_auth", lambda: None)()
        scope = yaml.safe_load(args.scope.read_text(encoding="utf-8"))
        if not isinstance(scope, dict):
            raise TeamConfigurationError("scope must be a YAML object")
        create, revoke = _bootstrap_helpers(root)
        runner = TeamRunner(
            repository_root=root,
            adapter=adapter,
            scope_factory=lambda item: PlatformScope(
                args.base_url, item.run_id, create, revoke
            ),
            freeze_started_at=args.freeze_started_at,
        )
        runner.prepare(
            run_id=args.run_id,
            profile_path=args.profile,
            task_path=args.task,
            scope=scope,
        )
        if handoff_root is not None:
            write_runner_phase(handoff_root, "prepared", run_root=runner.run.root)
        runner.start()
        _foreground_event_loop(
            runner,
            sys.stdin,
            lambda output: print(json.dumps(output, ensure_ascii=False), flush=True),
        )
        if handoff_root is not None:
            if not _terminal_report_complete(runner):
                _write_runner_handoff_failed(handoff_root, runner.run.root)
                raise RuntimeError("foreground CLI ended before terminal report completion")
            write_runner_phase(handoff_root, "cleanup_pending", run_root=runner.run.root)
            _await_monitor_extraction(handoff_root, runner.run.root)
    except KeyboardInterrupt:
        _write_runner_handoff_failed(handoff_root, _runner_root(runner))
        cleanup_once()
        return 130
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
