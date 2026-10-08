"""Fixed, asynchronous Host verification of one completed bounded repair.

This module cannot accept shell commands. It checks the owned paths, runs the
repository's prescribed suites, and optionally restarts the one local app unit.
It never supplies a semantic verdict or alters a modeling run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from .delivery_ops import get_repair_status, reconcile_write_state


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop('DEEPSEEK_API_KEY', None)
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    environment['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'
    environment['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{os.getuid()}/bus'
    return environment


def execute_verification(request: dict, *, runner: Callable | None = None,
                         reconciler: Callable | None = None) -> dict:
    root = Path(request['repository_root'])
    paths = request['owned_paths']
    targets = {name: _digest(root / name) for name in paths}
    result = {'operation_id': request['operation_id'], 'authorization_reference': request['authorization_reference'],
              'status': 'checking', 'effect_verified': False, 'deployment_verified': False,
              'semantic_acceptance': 'not_evaluated', 'checks': [], 'target_digests': targets}
    expected = request['target_digests']
    if expected and targets != expected:
        return dict(result, status='target_drift')

    def run(argv: list[str], cwd: Path) -> bool:
        if runner is None:
            print(json.dumps({'argv': argv, 'cwd': str(cwd)}), flush=True)
            code = subprocess.run(argv, cwd=cwd, env=_environment(), check=False).returncode
        else:
            code = runner(argv, cwd)
        result['checks'].append({'argv': argv, 'cwd': str(cwd), 'exit_code': code})
        return code == 0

    backend = any(name.startswith('backend/') or name == 'scripts/start-local.sh' for name in paths)
    frontend = any(name.startswith('frontend/') or name == 'scripts/start-local.sh' for name in paths)
    team = any(name.startswith('modeling_team/') for name in paths)
    python = str(root / 'backend/.venv/bin/python')
    plan = [(['git', 'diff', '--check', '--', *paths], root)]
    if backend:
        plan.append(([python, '-m', 'pytest'], root / 'backend'))
    if frontend:
        plan.extend([(['npm', 'run', 'build'], root / 'frontend'),
                     (['npx', 'playwright', 'test'], root / 'frontend')])
    if team:
        plan.append(([python, '-m', 'pytest', '../modeling_team/tests', '--tb=short'], root / 'backend'))
    for argv, cwd in plan:
        if not run(argv, cwd):
            return dict(result, status='checks_failed')
    if {name: _digest(root / name) for name in paths} != targets:
        return dict(result, status='target_drift')
    if backend or frontend:
        if request.get('allow_deployment') is not True:
            return dict(result, status='deployment_not_authorized')
        # Long checks must not turn an old readback into permission to deploy.
        # Reuse the existing readonly reconciliation immediately before restart.
        result['reconciliation_checks'] = []
        for scope in request.get('reconciliation_scopes', []):
            readback = (reconciler or reconcile_write_state)(
                **scope, repository_root=root, base_url=request.get('base_url'))
            proof = readback.get('reconciliation', {})
            result['reconciliation_checks'].append({
                'run_id': scope['run_id'], 'blocked': proof.get('blocked'),
                'scope_drift': proof.get('scope_drift'),
            })
            if proof.get('blocked') != [] or proof.get('scope_drift') != []:
                return dict(result, status='write_state_unreconciled')
        # The named unit must run this checkout, not an unrelated clone.
        if runner is None:
            unit_root = subprocess.run(
                ['systemctl', '--user', 'show', 'ontology-platform.service',
                 '--property=WorkingDirectory', '--value'],
                env=_environment(), capture_output=True, text=True, check=False,
            )
            if unit_root.returncode or Path(unit_root.stdout.strip()).resolve() != root.resolve():
                return dict(result, status='deployment_checkout_mismatch')
        deployment = [
            ['systemctl', '--user', 'restart', 'ontology-platform.service'],
            ['systemctl', '--user', 'is-active', '--quiet', 'ontology-platform.service'],
            ['curl', '--fail', '--retry', '10', '--retry-delay', '1', '--retry-connrefused',
             '--max-time', '10', 'http://127.0.0.1:8001/api/health'],
            ['curl', '--fail', '--retry', '10', '--retry-delay', '1', '--retry-connrefused',
             '--max-time', '10', 'http://127.0.0.1:5173/'],
        ]
        for argv in deployment:
            if not run(argv, root):
                return dict(result, status='checks_failed')
        result['deployment_verified'] = True
    if {name: _digest(root / name) for name in paths} != targets:
        return dict(result, status='target_drift', deployment_verified=False)
    return dict(result, status='verified', effect_verified=True)


def start_verification(*, operation_id: str, repository_root: Path, session_root: Path,
                       authorization_reference: str, allow_deployment: bool,
                       reconciliation_scopes: list[dict] | None = None,
                       base_url: str | None = None) -> dict:
    repair = get_repair_status(operation_id=operation_id, repository_root=repository_root)
    if repair['outcome'] != 'completed' or repair['exit_code'] != 0:
        raise ValueError('repair process has not completed successfully')
    binding = repair['request_binding']
    if binding['authorization_reference'] != authorization_reference:
        raise ValueError('repair authorization does not match the Delivery session')
    paths = binding['owned_paths']
    for name in paths:
        path = (repository_root / name).resolve()
        if not path.is_relative_to(repository_root.resolve()) or not path.is_file():
            raise ValueError('repair target is outside the owned checkout')
    attempts = session_root / 'repair-verification' / operation_id
    if (attempts / 'current.json').exists():
        existing = verification_status(operation_id=operation_id, session_root=session_root)
        if existing['process']['state'] == 'running' or (existing.get('result') or {}).get('effect_verified') is True:
            return existing
    attempts.mkdir(parents=True, exist_ok=True, mode=0o700)
    attempt_id = len(list(attempts.glob('attempt-*'))) + 1
    directory = attempts / f'attempt-{attempt_id}'
    directory.mkdir(parents=True, mode=0o700)
    request = {'operation_id': operation_id, 'repository_root': str(repository_root),
               'owned_paths': paths, 'authorization_reference': authorization_reference,
               'allow_deployment': allow_deployment,
               'reconciliation_scopes': reconciliation_scopes or [], 'base_url': base_url,
               'target_digests': {name: _digest(repository_root / name) for name in paths}}
    _atomic(directory / 'request.json', request)
    _atomic(directory / 'process.json', {'state': 'starting', 'pid': None})
    stdout = (directory / 'stdout.log').open('a')
    stderr = (directory / 'stderr.log').open('a')
    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'modeling_team.delivery_verification', '--request',
             str(directory / 'request.json')], cwd=repository_root, env=_environment(),
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True,
        )
        _atomic(directory / 'process.json', {'state': 'running', 'pid': process.pid})
    except Exception:
        _atomic(directory / 'process.json', {'state': 'launch_failed', 'pid': None})
        raise
    finally:
        stdout.close()
        stderr.close()
    _atomic(attempts / 'current.json', {'attempt_id': attempt_id})

    def reap() -> None:
        code = process.wait()
        _atomic(directory / 'process.json', {'state': 'exited', 'pid': process.pid, 'exit_code': code})

    threading.Thread(target=reap, daemon=True).start()
    return verification_status(operation_id=operation_id, session_root=session_root)


def verification_status(*, operation_id: str, session_root: Path) -> dict:
    attempts = session_root / 'repair-verification' / operation_id
    attempt_id = json.loads((attempts / 'current.json').read_text())['attempt_id']
    directory = attempts / f'attempt-{attempt_id}'
    request = json.loads((directory / 'request.json').read_text())
    process = json.loads((directory / 'process.json').read_text())
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    if result is not None and result['operation_id'] != operation_id:
        raise ValueError('verification result operation mismatch')
    # A retained PASS is stale after any owned target changes.
    current = {name: _digest(Path(request['repository_root']) / name) for name in request['owned_paths']}
    if result is not None and current != request['target_digests']:
        result = dict(result, status='target_drift', effect_verified=False, deployment_verified=False)
    tails = {}
    for name in ('stdout', 'stderr'):
        path = directory / (name + '.log')
        if path.exists():
            with path.open('rb') as handle:
                handle.seek(max(0, path.stat().st_size - 4096))
                tails[name] = handle.read().decode('utf-8', errors='replace')
    return {'operation_id': operation_id, 'attempt_id': attempt_id, 'process': process, 'result': result,
            'request': request, 'record_path': str(result_path),
            'log_tails': tails,
            'logs': {'stdout': str(directory / 'stdout.log'), 'stderr': str(directory / 'stderr.log')}}


def stop_verification(*, operation_id: str, session_root: Path) -> dict:
    status = verification_status(operation_id=operation_id, session_root=session_root)
    pid = status['process'].get('pid')
    if pid is None or status['process']['state'] != 'running':
        return {'stopped': False, 'status': status}
    expected = str(session_root / 'repair-verification' / operation_id / f"attempt-{status['attempt_id']}" / 'request.json')
    try:
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if expected.encode() not in command or os.getpgid(pid) != pid:
            raise ValueError('verification process ownership mismatch')
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, FileNotFoundError):
        return {'stopped': False, 'status': status}
    return {'stopped': True, 'pid': pid}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    try:
        result = execute_verification(request)
    except Exception as exc:
        result = {'operation_id': request['operation_id'], 'status': 'verification_failed',
                  'effect_verified': False, 'error_type': type(exc).__name__}
    _atomic(args.request.parent / 'result.json', result)
    return 0 if result['effect_verified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
