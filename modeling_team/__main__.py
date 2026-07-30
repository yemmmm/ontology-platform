from __future__ import annotations

import argparse
import json
import select
import sys
from pathlib import Path

import yaml

from .contracts import TeamConfigurationError, load_team_configuration, repository_root
from .platform_scope import PlatformScope
from .runner import TeamRunner
from .runtimes.codex import CodexRuntimeAdapter


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


def _foreground_event_loop(runner, stream, emit, *, select_fn=select.select) -> None:
    """Pump App Server events even when an outer user sends no further input."""
    while True:
        output = runner.drain()
        if output:
            emit(output)
        readable, _, _ = select_fn([stream], [], [], 0.1)
        if not readable:
            continue
        line = stream.readline()
        if not line:
            return
        output = runner.receive_outer(json.loads(line))
        if output:
            emit(output)


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
    args = parser.parse_args()
    runner = None
    try:
        root = repository_root()
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
    try:
        scope = yaml.safe_load(args.scope.read_text(encoding="utf-8"))
        if not isinstance(scope, dict):
            raise TeamConfigurationError("scope must be a YAML object")
        create, revoke = _bootstrap_helpers(root)
        adapter = CodexRuntimeAdapter(repository_root=root)
        runner = TeamRunner(
            repository_root=root,
            adapter=adapter,
            scope_factory=lambda item: PlatformScope(
                args.base_url, item.run_id, create, revoke
            ),
        )
        runner.prepare(
            run_id=args.run_id,
            profile_path=args.profile,
            task_path=args.task,
            scope=scope,
        )
        runner.start()
        _foreground_event_loop(
            runner,
            sys.stdin,
            lambda output: print(json.dumps(output, ensure_ascii=False), flush=True),
        )
    except (OSError, ValueError, RuntimeError, TeamConfigurationError) as exc:
        if runner is not None:
            runner.cleanup()
        print(f"run failed: {exc}", file=sys.stderr)
        return 2
    else:
        runner.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
