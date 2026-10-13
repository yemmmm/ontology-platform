"""Coverage uses bound application facts without revalidating historical reads."""
from copy import deepcopy
import json

import pytest

from modeling_team.staged_decisions import (
    ATTEMPT_PROOF_EVENT, StagedSubmissionRejection, build_identity_binding, canonical_json_digest,
    candidate_item_digest, projection_digest, read_attempt_proofs,
    staged_decision_artifact_paths,
)
from modeling_team.tests.test_v43_production_refs import (
    CANDIDATE, PLAN1, PLAN2, execute_args, production,  # noqa: F401
)

# pytest discovers the imported fixture.
# ruff: noqa: F811


def save_plan(production, ref, plan):
    plan['projection_digest'] = projection_digest(plan['projection'])
    (production.run_root / ref).write_text(json.dumps(plan))
    paths = staged_decision_artifact_paths(production.run_root, unified=True)
    approvals = json.loads(paths['approvals'].read_text())
    for entry in approvals['translation_approvals']:
        if entry['plan_ref'] == ref:
            entry['projection_digest'] = plan['projection_digest']
    paths['approvals'].write_text(json.dumps(approvals))


def add_shared_reuse(production):
    root, runner = production.run_root, production.runner
    candidate = json.loads((root / CANDIDATE).read_text())
    shared = {**deepcopy(candidate['items'][0]), 'item_id': 'shared-definition'}
    candidate['items'].append(shared)
    (root / CANDIDATE).write_text(json.dumps(candidate))
    plan = json.loads((root / PLAN1).read_text())
    ontology = plan['projection']['ontology_id']
    iri = 'https://example.test/shared/definition'
    read = runner.acceptance.register_platform_tool_result(
        tool='get_ontology_read_model', arguments={'ontology_id': ontology},
        result={'structuredContent': {'ok': True, 'data': {
            'model_revision': 1, 'items': [{'iri': iri}]}}})
    plan['projection']['identity_bindings'].append(build_identity_binding(
        candidate_item_id=shared['item_id'], resource_iri=iri,
        evidence_ref=read['artifact_path']))
    paths = staged_decision_artifact_paths(root, unified=True)
    approvals = json.loads(paths['approvals'].read_text())
    approvals['decisions'].append({**deepcopy(approvals['decisions'][0]),
        'decision_id': 'shared-decision', 'target_id': shared['item_id'],
        'content_digest': candidate_item_digest(shared)})
    paths['approvals'].write_text(json.dumps(approvals))
    for ref in (PLAN1, PLAN2):
        current = plan if ref == PLAN1 else json.loads((root / ref).read_text())
        current['projection']['candidate_digest'] = canonical_json_digest(candidate['items'])
        save_plan(production, ref, current)
    return plan


def check(production, refs=(PLAN1, PLAN2)):
    return production.runner._handle_check_plan_coverage({
        'candidate_ref': CANDIDATE, 'plan_refs': list(refs), 'dispositions': []})


def test_applied_history_keeps_reuse_coverage_after_later_version_changes(production):
    add_shared_reuse(production)
    assert check(production)['status'] == 'COMPLETE'
    args = execute_args(production)
    result = production.runner._handle_execute_approved_plans({**args, 'plan_refs': [PLAN1]})
    assert result['ok'], result
    assert production.versions[production.plans[0]['projection']['ontology_id']] == 2
    result = check(production)
    row = next(row for row in result['items'] if row['candidate_item_id'] == 'shared-definition')
    assert result['status'] == 'COMPLETE'
    assert row['reuse_binding']['status'] == 'covered_by_applied_plan'
    assert len(production.calls) == 2


def test_pending_plan_still_requires_fresh_reuse_even_with_applied_history(production):
    plan = add_shared_reuse(production)
    result = production.runner._handle_execute_approved_plans({
        **execute_args(production), 'plan_refs': [PLAN1]})
    assert result['ok'], result
    pending = json.loads((production.run_root / PLAN2).read_text())
    pending['projection']['identity_bindings'].append(plan['projection']['identity_bindings'][-1])
    save_plan(production, PLAN2, pending)
    production.runner._checkpoint_platform_bindings = lambda: {'ontology_ids': list(production.versions)}
    with pytest.raises(StagedSubmissionRejection) as error:
        check(production)
    assert error.value.data['reason_code'] == 'approval_stale'


def test_applied_history_still_requires_current_reuse_content_approval(production):
    add_shared_reuse(production)
    assert production.runner._handle_execute_approved_plans({
        **execute_args(production), 'plan_refs': [PLAN1]})['ok']
    path = staged_decision_artifact_paths(production.run_root, unified=True)['approvals']
    approvals = json.loads(path.read_text())
    next(row for row in approvals['decisions']
         if row['target_id'] == 'shared-definition')['content_digest'] = 'sha256:' + '0' * 64
    path.write_text(json.dumps(approvals))
    with pytest.raises(StagedSubmissionRejection) as error:
        check(production)
    assert error.value.data['reason_code'] == 'approval_content_mismatch'


def test_changed_plan_projection_cannot_inherit_applied_coverage(production):
    plan = add_shared_reuse(production)
    assert production.runner._handle_execute_approved_plans({
        **execute_args(production), 'plan_refs': [PLAN1]})['ok']
    plan['projection']['client_batch_id'] = 'different-plan-request'
    save_plan(production, PLAN1, plan)
    with pytest.raises(StagedSubmissionRejection) as error:
        check(production)
    assert error.value.data['reason_code'] == 'approval_stale'


@pytest.mark.parametrize('corruption', ['unbound', 'recovering', 'unknown-intent'])
def test_unbound_or_unresolved_proof_does_not_skip_historical_read(production, corruption):
    add_shared_reuse(production)
    assert production.runner._handle_execute_approved_plans({
        **execute_args(production), 'plan_refs': [PLAN1]})['ok']
    evidence = production.run_root / 'evidence/staged-decisions.jsonl'
    rows = [json.loads(line) for line in evidence.read_text().splitlines()]
    for row in rows:
        if row.get('event') == ATTEMPT_PROOF_EVENT and row.get('mode') == 'apply_atomic':
            if corruption == 'unbound':
                row['response_digest'] = 'sha256:' + '0' * 64
            elif corruption == 'recovering':
                row['attempt_status'] = 'recovering'
    evidence.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    if corruption == 'unknown-intent':
        # Locate the persisted apply intent through its ordinary artifact path.
        from modeling_team.staged_decisions import read_submission_intents, write_submission_intent
        intent = next(row for row in read_submission_intents(production.run_root)
                      if row['mode'] == 'apply_atomic')
        write_submission_intent(production.run_root, {**intent, 'status': 'unknown'})
    with pytest.raises(StagedSubmissionRejection) as error:
        check(production)
    assert error.value.data['reason_code'] == 'approval_stale'


def receipt_reuse(production, mutation=None):
    runner = production.runner
    assert runner._handle_execute_approved_plans({
        **execute_args(production), 'plan_refs': [PLAN1]})['ok']
    proof = next(p for p in read_attempt_proofs(production.run_root) if p['mode'] == 'apply_atomic')
    ontology = production.plans[0]['projection']['ontology_id']
    iri = 'https://example.test/created/definition'
    attempt = {key: proof[key] for key in (
        'attempt_id', 'idempotency_key', 'mode', 'attempt_status', 'content_hash')}
    attempt.update(workspace={'before_version': 1, 'after_version': 2},
                   items=[{'status': 'applied', 'resource_outputs': {'resource_iri': iri}}])
    data = {'batch_id': proof['batch_id'], 'ontology_id': ontology, 'attempts': [attempt],
            'items': [{'resource_outputs': {'resource_iri': iri}}]}
    if mutation:
        mutation(data, attempt)
    ref = runner.acceptance.register_platform_tool_result(
        tool='get_modeling_batch', arguments={'batch_id': proof['batch_id']},
        result={'structuredContent': {'ok': True, 'data': data}})
    plan = json.loads((production.run_root / PLAN2).read_text())
    plan['projection']['identity_bindings'] = [build_identity_binding(
        candidate_item_id='item-entity', resource_iri=iri, evidence_ref=ref['artifact_path'])]
    runner._checkpoint_platform_bindings = lambda: {'ontology_ids': list(production.versions)}
    return plan


def test_current_reuse_accepts_applied_attempt_item_identity(production):
    plan = receipt_reuse(production)
    reused = production.runner._validated_reuse_bindings(plan)
    assert reused['item-entity']['model_revision'] == 2


@pytest.mark.parametrize('mutation', [
    lambda data, attempt: attempt.update(attempt_status='validated', mode='dry_run'),
    lambda data, attempt: attempt.update(attempt_status='recovering'),
    lambda data, attempt: attempt.update(attempt_id='unobserved-attempt'),
    lambda data, attempt: attempt['items'][0].update(status='pending'),
    lambda data, attempt: attempt.update(items=[]),
    lambda data, attempt: attempt.update(content_hash='different-content'),
    lambda data, attempt: data.update(ontology_id='foreign-ontology'),
])
def test_current_reuse_rejects_planned_unbound_or_foreign_outputs(production, mutation):
    plan = receipt_reuse(production, mutation)
    with pytest.raises(StagedSubmissionRejection) as error:
        production.runner._validated_reuse_bindings(plan)
    assert error.value.data['reason_code'] == 'reuse_read_invalid'


def test_receipt_identity_does_not_hide_subsequent_drift(production):
    plan = receipt_reuse(production)
    production.versions[production.plans[0]['projection']['ontology_id']] = 3
    with pytest.raises(StagedSubmissionRejection) as error:
        production.runner._validated_reuse_bindings(plan)
    assert error.value.data['reason_code'] == 'approval_stale'
