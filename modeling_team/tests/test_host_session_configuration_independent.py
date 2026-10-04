"""Independent R4.0-018/019/021 boundary probes; no model/provider/platform calls."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from modeling_team import host_ops
from modeling_team.checkpoint_recovery import acquire_root_run_lock
from modeling_team.checkpoints import CheckpointError


# This independent subprocess constructs runtime inputs directly. It imports
# no development test helpers and stops before the app-server process boundary.
CONFIG_PROBE = r'''
import hashlib, json, shutil, sys, tomllib
from pathlib import Path
from types import SimpleNamespace
from modeling_team.contracts import _load_package, repository_root
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

out = Path(sys.argv[1]); out.mkdir(parents=True)
repo = repository_root()
auth = out / 'fixture-auth.json'; auth.write_text('{}')
def adapter():
    a = CodexRuntimeAdapter(repository_root=repo, use_bwrap=False)
    a._coordination_enabled = True
    a._team_model_profile = load_team_model_profile(repo, 'openai-sol-medium')
    a.preflight_host_auth = lambda: auth
    return a

runroot = out / 'run'; runroot.mkdir()
for role in ('coordinator', 'modeling', 'protocol', 'acceptance'):
    (runroot / 'sources' / role).mkdir(parents=True)
run = SimpleNamespace(
    root=runroot, run_id='independent-config', protocol_key='fixture-protocol',
    formal_contract=SimpleNamespace(requirement_id='R2.3-008'), acceptance=None,
    configuration=SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id='r2-3-008-formal-acceptance'),
        profile=SimpleNamespace(profile_id='r2-3-008-modeling-team')),
    scope={'mode':'create'})
for role in ('coordinator', 'modeling', 'protocol', 'acceptance'):
    a = adapter()
    paths = [out / role / part for part in ('home','work','skills')]
    for p in paths: p.mkdir(parents=True, mode=0o700)
    agent = _Agent(role, _load_package(repo, role), *paths)
    try: a._write_config(run, agent)
    finally: a.stop()

class ConfigReached(RuntimeError): pass
def process_boundary(*args, **kwargs): raise ConfigReached()
for kind in ('source', 'platform', 'acceptance'):
    a = adapter(); a.process_factory = process_boundary
    private = out / (kind + '-examiner'); private.mkdir(mode=0o700)
    (private / 'sources').mkdir()
    (private / 'sources/source.md').write_text('Independent approved synthetic source')
    inp = out / (kind + '-input.json'); inp.write_text('{}')
    spec = {'kind':kind, 'task_id':'r2-3-008-formal-acceptance',
            'private_root':str(private), 'private_input':str(inp),
            'child_handle_digest':hashlib.sha256(kind.encode()).hexdigest()}
    if kind == 'platform':
        spec.update(read_key_plaintext='fixture-reader',
          platform_read_scope={'project_id':'fixture-project','ontology_id':'fixture-ontology',
                               'graph_set_id':'fixture-graph'},
          ticket_digest='c'*64, model_state_digest='d'*64,
          acceptance_round_id='independent-round', allowed_read_tools=['query_semantic_context'])
    try:
        try: a._launch_acceptance_child_impl(spec)
        except ConfigReached: pass
        else: raise AssertionError('process boundary was not reached')
    finally:
        for key in ('_runtime_report_sink','_runtime_proxy'):
            resource = spec.get(key)
            if resource is not None: resource.stop()
        socket = spec.get('_runtime_socket_root')
        if isinstance(socket,str): shutil.rmtree(socket)
        a.stop()
configs = list(out.rglob('config.toml'))
projection = {}
for p in configs:
    t = tomllib.loads(p.read_text())
    projection[str(p.relative_to(out))] = {
      'model':t.get('model'), 'provider':t.get('model_provider'),
      'effort':t.get('model_reasoning_effort'),
      'service_tier':t.get('service_tier'), 'fast_mode':t.get('features',{}).get('fast_mode')}
(out / 'safe-projection.json').write_text(json.dumps(projection,indent=2))
'''


def _digests(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('entry', ['start', 'production', 'public', 'hidden'])
@pytest.mark.parametrize('tier,ambient', [('unset', None), ('unset', 'fast'),
                                        ('fast', None), ('default', 'fast')])
def test_independent_real_config_subprocess_for_each_host_entry(tmp_path, monkeypatch, entry,
                                                              tier, ambient):
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, 'independent-not-a-real-key')
    if ambient is None:
        monkeypatch.delenv('MODELING_TEAM_CODEX_SERVICE_TIER', raising=False)
    else:
        monkeypatch.setenv('MODELING_TEAM_CODEX_SERVICE_TIER', ambient)
    before_env = dict(os.environ)
    source = tmp_path / 'workspaces/modeling-runs/source'
    source.mkdir(parents=True)
    (source / 'state.json').write_text('{"state":"CLEANED"}')
    (source / 'historical-evidence').write_text('old immutable evidence')
    source_before = _digests(source)
    old = tmp_path / 'old-thread-config.toml'
    old.write_text('service_tier = "fast"\n[features]\nfast_mode = true\n')
    old_before = old.read_bytes()
    child = []
    captured = []

    def launch(argv, **kwargs):
        captured.append((argv, dict(kwargs['env'])))
        probe = 'import sys; sys.path.insert(0, ' + repr(str(host_ops.default_repository_root())) + ')\n'
        p = subprocess.Popen([sys.executable, '-c', probe + CONFIG_PROBE, str(tmp_path / 'actual')],
                             **kwargs)
        child.append(p)
        return p

    common = dict(repository_root=tmp_path, launcher=launch, run_root_wait_seconds=0,
                  service_tier=tier)
    if entry == 'start':
        result = host_ops.start_run(run_id='isolated', task='task.yaml', profile='profile.yaml',
                  scope='scope.yaml', model_profile='openai-sol-medium',
                  freeze_started_at='2026-10-04T00:00:00+00:00', **common)
    else:
        extra = ({'freeze_started_at':'2026-10-04T00:00:00+00:00'} if entry == 'production'
                 else {'model_profile':'openai-sol-medium', 'question_visibility':entry})
        result = host_ops.resume_from_checkpoint(source_run_id='source', checkpoint_id='fixture',
                  new_run_id='isolated', mode='production' if entry == 'production' else 'acceptance',
                  authorization_reference='independent-fixture-authorized', **extra, **common)
    assert child[0].wait(timeout=60) == 0, (
        tmp_path / 'workspaces/modeling-runs/.host-launches/isolated.err.log').read_text()
    values = json.loads((tmp_path / 'actual/safe-projection.json').read_text())
    assert len(values) == 7
    fast = tier == 'fast' or (tier == 'unset' and ambient == 'fast')
    for role, value in values.items():
        assert value == {'model':'gpt-6.1-sol', 'provider':'openai', 'effort':'medium',
                         'service_tier':'fast' if fast else None,
                         'fast_mode':True if fast else None}, role
    argv, env = captured[0]
    assert env.get('MODELING_TEAM_CODEX_SERVICE_TIER') == ('fast' if fast else None)
    assert dict(os.environ) == before_env
    assert old.read_bytes() == old_before
    assert _digests(source) == source_before
    launch_json = json.loads((tmp_path / 'workspaces/modeling-runs/.host-launches/isolated.json')
                             .read_text())
    assert launch_json['service_tier'] == tier
    assert 'independent-not-a-real-key' not in json.dumps(launch_json)
    assert 'env' not in launch_json
    if entry == 'production':
        assert '--model-profile' not in argv
        assert '1 semantic start' in result['semantic_starts_note']
    elif entry != 'start':
        assert argv[argv.index('--model-profile')+1] == 'openai-sol-medium'
        assert 'consumes 0' in result['semantic_starts_note']


def test_independent_production_model_override_refuses_before_launch(tmp_path, monkeypatch):
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, 'independent-not-a-real-key')
    with pytest.raises(host_ops.HostOpError) as failure:
        host_ops.resume_from_checkpoint(source_run_id='source', checkpoint_id='fixture',
            new_run_id='new', mode='production', authorization_reference='fixture-auth',
            freeze_started_at='2026-10-04T00:00:00+00:00', model_profile='openai-sol-medium',
            launcher=lambda *a, **k: pytest.fail('unsupported override launched'),
            repository_root=tmp_path)
    assert failure.value.code == 'launch_arguments_invalid'
    assert failure.value.obj == 'model_profile'
    assert failure.value.retryable
    assert not list(tmp_path.rglob('*.json'))


def test_independent_new_off_child_does_not_change_live_old_fast_child(tmp_path, monkeypatch):
    monkeypatch.setenv('MODELING_TEAM_CODEX_SERVICE_TIER', 'fast')
    parent_before = dict(os.environ)
    prefix = ('import sys; sys.path.insert(0, '
              + repr(str(host_ops.default_repository_root())) + ')\n')
    old_script = (prefix + CONFIG_PROBE
                  + "\nprint('configs-ready', flush=True)\ninput()\n"
                  + "import os\n(out/'old-env.json').write_text(json.dumps({'tier':"
                    "os.environ.get('MODELING_TEAM_CODEX_SERVICE_TIER')}))\n")
    old = subprocess.Popen([sys.executable, '-c', old_script, str(tmp_path / 'old')],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, env=dict(os.environ))
    try:
        assert old.stdout.readline().strip() == 'configs-ready'
        before = _digests(tmp_path / 'old')
        assert old.poll() is None
        new_env = dict(os.environ)
        new_env.pop('MODELING_TEAM_CODEX_SERVICE_TIER')
        new = subprocess.run([sys.executable, '-c', prefix + CONFIG_PROBE, str(tmp_path / 'new')],
                             env=new_env, capture_output=True, text=True, timeout=60)
        assert new.returncode == 0, new.stderr
        projection = json.loads((tmp_path / 'new/safe-projection.json').read_text())
        assert len(projection) == 7
        assert all(v['service_tier'] is None and v['fast_mode'] is None
                   for v in projection.values())
        assert _digests(tmp_path / 'old') == before
        assert old.poll() is None
        old.communicate('\n', timeout=60)
        assert old.returncode == 0
        assert json.loads((tmp_path / 'old/old-env.json').read_text()) == {'tier':'fast'}
        assert dict(os.environ) == parent_before
    finally:
        if old.poll() is None:
            old.kill()
            old.communicate(timeout=10)


def test_independent_same_root_mutex_and_readonly_status(tmp_path):
    source = tmp_path / 'workspaces/modeling-runs/synthetic-source'
    (source / 'evidence').mkdir(parents=True)
    (source / 'state.json').write_text('{"state":"RUNNING","run_id":"synthetic-source"}')
    (source / 'evidence/semantic-start.jsonl').write_text('{"recorded_at":"2026-10-04T00:00:00Z"}\n')
    before = _digests(source)
    first = acquire_root_run_lock('root-x', tmp_path / 'locks')
    try:
        with pytest.raises(CheckpointError) as conflict:
            acquire_root_run_lock('root-x', tmp_path / 'locks')
        assert conflict.value.reason_code == 'source_active'
        assert conflict.value.retryable
        acquire_root_run_lock('independent-root', tmp_path / 'locks').release()
    finally:
        first.release()
    acquire_root_run_lock('root-x', tmp_path / 'locks').release()
    status = host_ops.get_run_status('synthetic-source', repository_root=tmp_path)
    assert status['recorded_state']['state'] == 'RUNNING'
    assert status['terminal_conclusion']['is_terminal_state'] is False
    assert status['liveness']['process_observation']['basis'] == 'unknown'
    assert status['limitations']
    assert status['observed_at']
    assert _digests(source) == before
