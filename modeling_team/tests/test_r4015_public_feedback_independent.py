"""Opt-in real isolated early Consumer over a disposable HTTP/RDF fixture.

No production start, final Judge or external business operation is performed.
Actual reports are independently reviewed in the shared test document.
"""
from __future__ import annotations

import hashlib
import json
import os
from argparse import Namespace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from backend.tests.subject_access_support import create_api_key as create_reader_key
from modeling_team import __main__ as cli
from modeling_team.checkpoints import CheckpointArtifactSpec, StagePackage, file_digest, save_checkpoint
from modeling_team.competency_questions import content_digest
from modeling_team.contracts import repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.staged_decisions import (
    build_attempt_proof, build_submission_intent, build_submission_receipt,
    mark_intent_status, staged_decision_artifact_paths, write_submission_intent,
    write_submission_receipt,
)
from modeling_team.tests.test_r3011_acceptance import _freeze, _question

ROOT = repository_root()
POLICY = ('A reservation becomes confirmed only after a supervisor approves the slot. '
          'A request receipt alone is not confirmation. A confirmed reservation can enter dispatch. '
          'The rescheduling surcharge has not been agreed; no amount or deadline is asserted.')


def _tree_digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.skipif(os.getenv('R4015_LIVE_FEEDBACK') != '1', reason='controlled real child opt-in')
def test_real_early_consumer_without_handoff_attempt_or_production_transition(monkeypatch):
    evidence = Path(os.environ['R4015_FEEDBACK_EVIDENCE']).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id = ontology_id = reader_user = None
    graphs, keys = [], []

    def save(name, value):
        (evidence / name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))

    try:
        with factory() as session:
            key_record, admin = create_api_key(session, name='r4015-functional-' + token,
                project_id=None, scopes=['admin'], bootstrap=True)
            keys.append(key_record.id)
        with httpx.Client(base_url='http://127.0.0.1:8001',
                          headers={'Authorization':'Bearer '+admin}, timeout=120) as client:
            def post(path, data, status=200):
                response = client.post('/api'+path, json=data)
                assert response.status_code == status, response.text
                return response.json()

            def context():
                response = client.get(f'/api/ontologies/{ontology_id}/modeling-context')
                assert response.status_code == 200, response.text
                return response.json()

            project_id = post('/projects', {'name':'R4015 isolated '+token}, 201)['id']
            ontology = post(f'/projects/{project_id}/ontologies',
                            {'name':'Service reservation functional policy'}, 201)
            ontology_id = ontology['id']
            graphs.extend(row['graph_iri'] for row in ontology['workspace']['members'])
            build = post(f'/projects/{project_id}/build-sessions',
                         {'client_session_id':'r4015-'+token}, 201)
            definitions = [
                ('reservation','ServiceReservation',POLICY),
                ('approval','SupervisorApproval',
                 'Approval of the requested slot by a supervisor is required for confirmation.'),
                ('dispatch','Dispatch', 'Only a confirmed reservation is eligible to enter dispatch.'),
            ]
            items = [{'client_item_id':item, 'command_kind':'create_class',
                      'payload':{'name':name,'description':description}}
                     for item,name,description in definitions]
            for item, target, name, description in [
                ('needs-approval','approval','confirmation_requires_supervisor_approval',
                 'A request receipt by itself does not establish this condition.'),
                ('can-dispatch','dispatch','confirmed_reservation_can_enter_dispatch',
                 'Confirmation is the necessary stage for dispatch eligibility.')]:
                items.append({'client_item_id':item, 'command_kind':'create_relation_type',
                    'depends_on':['reservation',target], 'payload':{
                        'name':name, 'description':description,
                        'source_class_id':{'item_ref':{'client_item_id':'reservation','output':'resource_id'}},
                        'target_class_id':{'item_ref':{'client_item_id':target,'output':'resource_id'}},
                        'status':'active'}})

            def apply(commands, suffix):
                request = {'client_batch_id':token+'-'+suffix, 'ontology_id':ontology_id,
                    'mode':'dry_run', 'idempotency_key':token+'-dry-'+suffix,
                    'expected_model_revision':context()['workspace']['model_revision'],
                    'items':commands}
                endpoint = f"/build-sessions/{build['id']}/modeling-batches"
                dry = post(endpoint, request)
                save(suffix+'-dry-run.json',dry)
                assert dry['attempt_status'] == 'validated', dry
                live = client.get(f"/api/build-sessions/{build['id']}")
                assert live.status_code == 200
                lease = post(f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                    {'client_request_id':token+'-lease-'+suffix,
                     'expected_session_revision':live.json()['session']['revision']})
                request.update(mode='apply_atomic', idempotency_key=token+'-apply-'+suffix,
                               lease_token=lease['lease_token'])
                receipt = post(endpoint, request)
                save(suffix+'-apply.json',receipt)
                assert receipt['attempt_status'] == 'applied', receipt
                return receipt

            applied = apply(items,'initial')
            resource_receipts = {row['client_item_id']:row['resource_outputs']
                                 for row in applied['items']}
            save('resource-receipts.json',resource_receipts)
            with factory() as session:
                record, reader = create_reader_key(session, name='r4015-reader-'+token,
                                                    project_id=project_id, scopes=['read'])
                keys.append(record.id)
                reader_user = record.user_id
            monkeypatch.setenv(cli._CQ_PLATFORM_READ_KEY_ENV,reader)
            original_adapter = cli.CodexRuntimeAdapter
            captured = []
            current_case = ''

            class ObservedAdapter(CodexRuntimeAdapter):
                def run_v3_acceptance_child(self, packet, **kwargs):
                    assert packet.role == 'platform-examiner', 'early feedback invoked final Judge'
                    captured.append(packet.to_dict())
                    save(current_case+'-actual-packet.json',packet.to_dict())
                    returned = super().run_v3_acceptance_child(packet, **kwargs)
                    if current_case == 'drift':
                        apply([{'client_item_id':'revision', 'command_kind':'update_class',
                            'payload':{'class_iri':resource_receipts['reservation']['resource_iri'],
                                       'description':POLICY+' Reviewed terminology unchanged.'}}],
                              'post-consumer-drift')
                    return returned

            monkeypatch.setattr(cli,'CodexRuntimeAdapter',ObservedAdapter)
            cases = os.environ.get('R4015_FEEDBACK_CASES','baseline,unknown,drift').split(',')
            assert set(cases) <= {'baseline','unknown','drift'} and cases
            for current_case in cases:
                run = evidence / current_case / 'production'
                run.mkdir(parents=True)
                public = _question('cq-public',visibility='public')
                public['question'] = (
                    '在获准服务预约模型中，仅有请求回执能否确认预约并进入派发？'
                    '请读取预约确认所需条件、派发可行阶段及其关系，依据当前模型回答。'
                )
                if current_case == 'unknown':
                    public['question'] += '改期附加费具体金额和生效期限是什么？未约定时保留未知。'
                public['answer_points'] = ['HOST_PRIVATE_POINTS_NOT_SENT_TO_CONSUMER']
                hidden = _question('cq-private',visibility='hidden')
                hidden['question'] = 'HIDDEN_TEST_MARKER_DO_NOT_DISCLOSE'
                freeze = _freeze([public,hidden])
                source = 'competency-questions/frozen/freeze-0001.json'
                frozen_path = run / source
                frozen_path.parent.mkdir(parents=True)
                frozen_path.write_text(json.dumps(freeze))
                (run / 'phase.json').write_text('{"phase":"production"}')
                (run / 'state.json').write_text('{"state":"RUNNING"}')
                intent = build_submission_intent(1,
                    idempotency_key=token+'-apply-initial',client_batch_id=token+'-initial',
                    session_id=build['id'],mode='apply_atomic',commands=items,value_traces=[],l3_nodes=[])
                write_submission_intent(run,mark_intent_status(intent,'receipted'))
                write_submission_receipt(run,build_submission_receipt(1,intent,
                    batch_id=applied['batch_id'],response_digest=content_digest(applied)))
                # The lean receipt alone never proves the write applied: seed
                # the Runner-shaped applied attempt proof bound to it. The
                # proof needs the read-back content hash, which the attempt
                # response itself never carries — read the batch detail like
                # the forwarder's verification pass does.
                readback = client.get(
                    f"/api/modeling-batches/{applied['batch_id']}")
                assert readback.status_code == 200, readback.text
                proof = build_attempt_proof(
                    intent_ordinal=1, receipt_ordinal=1, plan_ref=None,
                    projection_digest=None,
                    batch={'client_batch_id':token+'-initial','mode':'apply_atomic',
                           'idempotency_key':token+'-apply-initial'},
                    result={'batch_id':applied['batch_id'],'attempt_id':applied['attempt_id'],
                            'mode':'apply_atomic','attempt_status':'applied',
                            'content_hash':readback.json()['content_hash'],
                            'idempotency_key':token+'-apply-initial'},
                    response_digest=content_digest(applied))
                assert proof is not None
                (run / 'evidence').mkdir(exist_ok=True)
                with (run / 'evidence/staged-decisions.jsonl').open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps({**proof,
                        'recorded_at':'2026-10-05T03:32:12.701068Z'})+'\n')
                staged = staged_decision_artifact_paths(run)
                paths = [source]+[p.relative_to(run).as_posix() for name in
                    ('intents_dir','receipts_dir') for p in staged[name].glob('*.json')]
                result = save_checkpoint(run,StagePackage(kind='materialization_progress',
                    scope_refs={'freeze_id':'freeze-0001'},artifacts=[
                        CheckpointArtifactSpec(source=p,owner='host',visible_to=('host',),
                                               host_private=True) for p in paths],
                    platform_bindings={'project_id':project_id,'ontology_ids':[ontology_id],
                        'run_scope':{'mode':'existing','project_id':project_id,'ontology_id':ontology_id},
                        'model_profile_digest':'configured-openai-sol-medium'},
                    write_positions={'positions':[{'state':'applied','ordinal':1}],
                                     'in_flight':[],'unknown':[]},
                    stage_facts={'bindings':[{'artifact':source,'digest':file_digest(frozen_path)}]}),
                    source_run_id='controlled-production-no-start-'+token,
                    configuration={'task_parameters':{'modeling_checkpoints':True,
                                                       'competency_question_acceptance':True}})
                (run / 'evidence').mkdir(exist_ok=True)
                (run / 'evidence/checkpoints.jsonl').write_text(json.dumps({
                    'event':'checkpoint-'+result['status'],'checkpoint_id':result['checkpoint_id'],
                    'manifest_digest':result['manifest_digest']})+'\n')
                before = _tree_digest(run)
                code = cli._run_public_feedback(Namespace(run_root=run,
                    checkpoint_id=result['checkpoint_id'],freeze_id='freeze-0001',
                    question_id=['cq-public'],model_profile='openai-sol-medium',session_timeout=300),ROOT)
                record = json.loads(next((run/'early-feedback').glob('*/feedback.json')).read_text())
                save(current_case+'-result.json',{'exit_code':code,'feedback':record})
                assert {p: _tree_digest(run)[p] for p in before} == before
                assert not (run/'acceptance-v3/production-handoff.json').exists()
                assert not (run/'acceptance-v3/reports').exists()
                assert json.loads((run/'phase.json').read_text())['phase'] == 'production'
                assert json.loads((run/'state.json').read_text())['state'] == 'RUNNING'
                assert record['formal_acceptance'] is False
                assert 'HIDDEN_TEST_MARKER_DO_NOT_DISCLOSE' not in json.dumps(captured)
                assert 'HOST_PRIVATE_POINTS_NOT_SENT_TO_CONSUMER' not in json.dumps(captured)
                assert record['cleanup']['forwarder_stopped'] is True
                assert record['cleanup']['children_destroyed'] is True
                if current_case == 'baseline':
                    # T015-02 explicitly preserves real unknown/partial.
                    # The first raw Consumer gave a correct supported answer
                    # while separately reporting limits; this is not a final
                    # business PASS or grounds to coerce status to observed.
                    assert record['status'] in {'observed','partial'}, record
                    assert record['first_failure'] is None, record
                    assert record['reports'][0]['status'] == 'completed', record
                    assert not record['missing_question_ids'], record
                    assert not record['rejected_evidence_refs'], record
                    assert not record['model_drift'], record
                    assert record['reports'][0]['answer']
                    assert record['platform_read_responses']['cq-public']
                elif current_case == 'unknown':
                    assert record['status'] == 'partial', record
                    assert record['reports'][0]['explicit_unknown'], record
                else:
                    assert record['status'] == 'superseded', record
                    assert record['model_drift']
                    assert record['reports'][0]['answer']
            monkeypatch.setattr(cli,'CodexRuntimeAdapter',original_adapter)
    finally:
        with factory() as session:
            if ontology_id:
                sets=list(session.scalars(select(m.SemanticGraphSetModel.id).where(
                    m.SemanticGraphSetModel.scope_type=='ontology',
                    m.SemanticGraphSetModel.scope_id==ontology_id)))
                session.execute(delete(m.SemanticGraphSetModel).where(m.SemanticGraphSetModel.id.in_(sets)))
            if project_id:
                session.execute(delete(m.ProjectModel).where(m.ProjectModel.id==project_id))
            session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id.in_(keys)))
            if reader_user:
                session.execute(delete(m.UserModel).where(m.UserModel.id==reader_user))
            for model in (m.SemanticGraphRegistryModel,m.SemanticGraphRevisionModel):
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            session.commit()
        for iri in graphs:
            store.drop_named_graph(iri)
            assert not store.graph_exists(iri)
        with factory() as session:
            assert not project_id or session.get(m.ProjectModel,project_id) is None
            assert not list(session.scalars(select(m.ApiKeyModel.id).where(m.ApiKeyModel.id.in_(keys))))
            assert not reader_user or session.get(m.UserModel,reader_user) is None
        save('cleanup.json',{'project_removed':True,'keys_removed':True,'reader_removed':True,
                             'graphs_removed':graphs,'semantic_starts':0,'business_api_calls':0})
