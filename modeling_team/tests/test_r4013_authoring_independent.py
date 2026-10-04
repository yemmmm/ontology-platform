"""Opt-in isolated CQ authoring and externally reviewed synthetic material.

Only the CQ role is launched. No business production roster or platform writer
is started, and review notes must come from an actor other than this tester.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.transport_mcp import TeamTransportBroker
from modeling_team.tests.test_r3011_runner_wiring import _CQRunner
from modeling_team.tests.test_r4013_semantic_diagnostics import controlled_cq_authoring_inputs


@pytest.mark.skipif(os.getenv('R4013_LIVE_AUTHORING') != '1', reason='controlled CQ role opt-in')
def test_isolated_cq_publishes_unpredicted_draft_and_accepts_external_host_review():
    evidence = Path(os.environ['R4013_AUTHORING_EVIDENCE']).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    harness = _CQRunner()
    runner = harness.prepare()
    root = runner.repository_root
    stderr_file = tempfile.TemporaryFile(mode='w+b')
    launches = []

    def process_factory(command, **kwargs):
        launches.append(command)
        kwargs['stderr'] = stderr_file
        return subprocess.Popen(command, **kwargs)

    adapter = CodexRuntimeAdapter(repository_root=root, process_factory=process_factory)
    broker = None
    materials = controlled_cq_authoring_inputs()
    run = runner.run
    try:
        source = run.root / 'sources/competency-question'
        for p in source.rglob('*'):
            if p.is_file():
                p.unlink()
        policy = source / materials['source_name']
        policy.write_text(materials['source_content'])
        contract = source / 'modeling_team/references/r3-0-011-competency-question-contract.json'
        contract.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / 'modeling_team/references/r3-0-011-competency-question-contract.json',
                        contract)
        manifest = [{'path':materials['source_name'], 'classification':'approved-business-source',
                     'roles':['competency-question'],
                     'sha256':hashlib.sha256(policy.read_bytes()).hexdigest()}]
        (run.root / 'source-manifest.json').write_text(json.dumps({'sources':manifest}))
        (evidence / 'approved-source.md').write_text(materials['source_content'])
        (evidence / 'authoring-task.txt').write_text(materials['task'])
        agent = next(a for a in run.configuration.profile.agents
                     if a.agent_id == 'competency-question')
        for name, p in [('role.md',agent.package.instructions_path),
                        ('skill.md',agent.package.required_skills[0])]:
            shutil.copyfile(p, evidence / name)
        shutil.copyfile(contract, evidence / 'cq-contract.json')
        broker = TeamTransportBroker(run.root / 'transport/independent-cq', set(),
                                     coordinator_agent_id='coordinator',
                                     issue_escalation_enabled=runner._staged_decisions)
        broker.start(['competency-question'])
        run.transport_root = broker.root
        (run.root / 'transport-root').write_text(str(broker.root))
        runner.acceptance.start_cq_endpoint()
        run.team_model_profile = load_team_model_profile(root, 'openai-sol-medium')
        adapter.start_roster(run, [agent])
        # Keep actual review delivery in the same native CQ thread.
        runner.adapter = adapter
        prompt = (materials['task'] + '\nOnly approved business source: '
                  '/agent/home/sources/' + materials['source_name']
                  + '\nExact CQ contract: /agent/home/sources/modeling_team/references/'
                    'r3-0-011-competency-question-contract.json. '
                    'Use evidence_refs.source exactly service-reservation-policy.md. '
                    'All questions in this controlled public functional test are public. '
                    'No private/historical business source or expected draft is provided. '
                    'After publication wait for the host review without a terminal report.')
        (evidence / 'first-turn.txt').write_text(prompt)
        adapter.start_task(agent.agent_id, prompt,
                           [str(p) for p in agent.package.required_skills], [agent.agent_id])
        deadline = time.monotonic() + 600
        draft_path = run.root / 'competency-questions/private/draft-0001.json'
        while not draft_path.exists() and time.monotonic() < deadline:
            adapter.receive_messages()
            failures = adapter.consume_runtime_failures()
            if failures:
                (evidence / 'runtime-failures.json').write_text(json.dumps(failures,default=str))
                pytest.fail('CQ role failed before actual draft publication; read retained evidence')
            time.sleep(1)
        assert draft_path.is_file(), 'actual CQ publication did not arrive in bounded observation'
        shutil.copyfile(draft_path, evidence / 'actual-draft.json')
        review = run.root / 'competency-questions/reviews/cq-review-0001.json'
        shutil.copyfile(review, evidence / 'actual-review-window.json')
        (evidence / 'ready-for-external-review.json').write_text(json.dumps({
            'run_id':run.run_id, 'draft':'actual-draft.json', 'source':'approved-source.md',
            'review_window':'actual-review-window.json', 'semantic_starts':0,
            'expected_review_file':'external-host-review.json'}))
        print('ACTUAL_DRAFT_READY ' + str(evidence), flush=True)
        review_file = evidence / 'external-host-review.json'
        deadline = time.monotonic() + 900
        while not review_file.exists() and time.monotonic() < deadline:
            time.sleep(1)
        assert review_file.is_file(), 'independent external host review missing'
        host_reviews = json.loads(review_file.read_text())['reviews']
        receipts = []
        for payload in host_reviews:
            # Mechanical transfer only: no note rewriting or invented decision.
            receipts.append(runner.handle_cq_outer_input(payload))
        (evidence / 'host-review-receipts.json').write_text(json.dumps(receipts,default=str,
                                                                    ensure_ascii=False,indent=2))
        decisions = list((run.root / 'competency-questions/reviews').glob('decision-*.json'))
        assert len(decisions) == len(host_reviews)
        target = evidence / 'actual-decisions'
        target.mkdir()
        for p in decisions:
            shutil.copyfile(p, target / p.name)
    finally:
        cleanup = adapter.stop()
        (evidence / 'runtime-cleanup.json').write_text(json.dumps(cleanup,default=str,indent=2))
        (evidence / 'runtime-commands.json').write_text(json.dumps(launches,indent=2))
        stderr_file.seek(0)
        stderr = stderr_file.read()
        for secret in adapter._secret_audit_values:
            stderr = stderr.replace(secret, b'[redacted]')
        (evidence / 'native-stderr.txt').write_text(stderr.decode(errors='replace'))
        stderr_file.close()
        if broker is not None:
            broker.stop()
        if run.root.exists():
            shutil.copytree(run.root / 'competency-questions', evidence / 'cq-output',
                            dirs_exist_ok=True)
            if (run.root / 'evidence').is_dir():
                shutil.copytree(run.root / 'evidence', evidence / 'runner-evidence',
                                dirs_exist_ok=True)
        # The original harness only deletes its own synthetic run and ledger.
        harness.cleanup()


@pytest.mark.skipif(os.getenv('R4013_REPLAY_REVIEW') != '1', reason='retained real-draft review opt-in')
def test_retained_actual_draft_accepts_external_review_without_changing_reasons():
    evidence = Path(os.environ['R4013_AUTHORING_EVIDENCE']).resolve()
    target = evidence / 'review-replay'
    target.mkdir(exist_ok=False)
    authored = json.loads((evidence/'actual-draft.json').read_text())
    original_window = json.loads((evidence/'actual-review-window.json').read_text())
    reviews = json.loads((evidence/'external-host-review-enveloped.json').read_text())['reviews']
    harness = _CQRunner()
    runner = harness.prepare()
    run = runner.run
    try:
        for role in ('competency-question','coordinator','modeling'):
            source = run.root/'sources'/role/'service-reservation-policy.md'
            source.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(evidence/'approved-source.md',source)
        (run.root/'source-manifest.json').write_text(json.dumps({'sources':[{
            'path':'service-reservation-policy.md','roles':['competency-question'],
            'sha256':hashlib.sha256((evidence/'approved-source.md').read_bytes()).hexdigest()}]}))
        authored.pop('content_digest',None)
        runner._publish_cq_question_draft({'cq_id':'competency-question','draft':authored})
        current = json.loads((run.root/'competency-questions/reviews/cq-review-0001.json').read_text())
        assert current['content_digest'] == original_window['content_digest']
        assert current['content_version'] == original_window['content_version']
        receipts = [runner.handle_cq_outer_input(payload) for payload in reviews]
        (target/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
        decisions = list((run.root/'competency-questions/reviews').glob('decision-*.json'))
        assert len(decisions) == len(reviews)
        original_notes = {p['question_id']:p['note'] for p in reviews}
        for path in decisions:
            decision = json.loads(path.read_text())['decision']
            assert decision['note'] == original_notes[decision['question_id']]
        assert all(note not in json.dumps(runner._cq_public_projection(),ensure_ascii=False)
                   for note in original_notes.values())
        runner.handle_cq_outer_input({'action':'cq_freeze'})
        frozen = json.loads((run.root/'competency-questions/frozen/freeze-0001.json').read_text())
        by_id = {q['question_id']:q for q in frozen['questions']}
        for q in authored['questions']:
            assert by_id[q['question_id']]['question'] == q['question']
            assert by_id[q['question_id']]['answer_points'] == q['answer_points']
            assert by_id[q['question_id']]['content_version'] == q['content_version']
        assert len(by_id) == len(authored['questions'])
        shutil.copytree(run.root/'competency-questions',target/'cq-output')
    finally:
        harness.cleanup()
