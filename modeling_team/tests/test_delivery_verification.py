"""Repair verification must use fixed checks and retain unsuccessful outcomes."""
import importlib
import subprocess
import time


def request(tmp_path, path='backend/app/fix.py', deployment=True):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('fixed\n')
    return {'operation_id': 'repair-one', 'repository_root': str(tmp_path),
            'owned_paths': [path], 'allow_deployment': deployment,
            'authorization_reference': 'user-repair', 'target_digests': {}}


def test_failed_checks_never_restart_or_claim_effectiveness(tmp_path):
    module = importlib.import_module('modeling_team.delivery_verification')
    value = request(tmp_path)
    calls = []
    result = module.execute_verification(value, runner=lambda argv, cwd: calls.append(argv) or 1)
    assert result['effect_verified'] is False
    assert not any('systemctl' in argv for argv in calls)


def test_backend_deployment_requires_explicit_authorization(tmp_path):
    module = importlib.import_module('modeling_team.delivery_verification')
    value = request(tmp_path, deployment=False)
    calls = []
    result = module.execute_verification(value, runner=lambda argv, cwd: calls.append(argv) or 0)
    assert result['status'] == 'deployment_not_authorized'
    assert result['effect_verified'] is False
    assert not any('systemctl' in argv for argv in calls)


def test_fixed_checks_restart_and_health_are_evidenced_separately(tmp_path):
    module = importlib.import_module('modeling_team.delivery_verification')
    calls = []
    result = module.execute_verification(request(tmp_path), runner=lambda argv, cwd: calls.append(argv) or 0)
    assert result['effect_verified'] is True
    assert result['deployment_verified'] is True
    assert any('pytest' in argv for argv in calls)
    assert any(argv[:3] == ['systemctl', '--user', 'restart'] for argv in calls)
    assert any('http://127.0.0.1:8001/api/health' in argv for argv in calls)
    assert result['semantic_acceptance'] == 'not_evaluated'


def test_health_failure_and_target_drift_remain_unverified(tmp_path):
    module = importlib.import_module('modeling_team.delivery_verification')
    value = request(tmp_path)
    result = module.execute_verification(value, runner=lambda argv, cwd: 1 if argv[0] == 'curl' else 0)
    assert result['effect_verified'] is False and result['status'] == 'checks_failed'
    value['target_digests'] = {'backend/app/fix.py': 'wrong-digest'}
    result = module.execute_verification(value, runner=lambda argv, cwd: 0)
    assert result['effect_verified'] is False and result['status'] == 'target_drift'


def test_fresh_unknown_write_after_checks_prevents_restart(tmp_path):
    module = importlib.import_module('modeling_team.delivery_verification')
    value = request(tmp_path)
    value['reconciliation_scopes'] = [{'run_id': 'r', 'project_id': 'p', 'ontology_ids': ['o']}]
    calls = []
    result = module.execute_verification(
        value, runner=lambda argv, cwd: calls.append(argv) or 0,
        reconciler=lambda **kwargs: {'readback_only': True, 'reconciliation': {
            'blocked': [{'reason': 'write_unreconciled'}], 'scope_drift': []}},
    )
    assert result['status'] == 'write_state_unreconciled'
    assert not result['effect_verified']
    assert not any('systemctl' in argv for argv in calls)


def test_failed_verification_retries_in_new_real_process_and_preserves_old_attempt(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.delivery_verification')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    target = tmp_path / 'public.md'
    target.write_text('baseline\n')
    subprocess.run(['git', 'add', 'public.md'], cwd=tmp_path, check=True)
    target.write_text('bad whitespace  \n')
    monkeypatch.setattr(module, 'get_repair_status', lambda **kwargs: {
        'outcome': 'completed', 'exit_code': 0, 'request_binding': {
            'authorization_reference': 'user-repair', 'owned_paths': ['public.md']}})

    def wait():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = module.verification_status(operation_id='retry', session_root=tmp_path / 'session')
            if value['process']['state'] == 'exited':
                return value
            time.sleep(0.02)
        raise AssertionError('offline verification process did not exit')

    kwargs = dict(operation_id='retry', repository_root=tmp_path, session_root=tmp_path / 'session',
                  authorization_reference='user-repair', allow_deployment=False)
    module.start_verification(**kwargs)
    first = wait()
    assert first['result']['status'] == 'checks_failed'
    target.write_text('fixed\n')
    module.start_verification(**kwargs)
    second = wait()
    assert second['result']['effect_verified'] is True
    assert second['attempt_id'] == first['attempt_id'] + 1
    assert second['process']['pid'] != first['process']['pid']
    assert target.parent.joinpath(first['record_path']).is_file()
