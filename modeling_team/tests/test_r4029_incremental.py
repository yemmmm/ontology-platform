"""Developer tests for current-read reuse and normal incremental task inputs."""
from copy import deepcopy
import json

import pytest

from modeling_team.staged_decisions import (
    build_identity_binding, projection_digest, staged_decision_artifact_paths,
    validate_materialization_plan, StagedSubmissionRejection,
)
from modeling_team.tests.test_v43_production_refs import production, PLAN1, CANDIDATE  # noqa: F401

# pytest discovers the imported fixture.
# ruff: noqa: F811


def reuse_plan(production):
    runner = production.runner
    path = production.run_root / PLAN1
    plan = json.loads(path.read_text())
    ontology = plan['projection']['ontology_id']
    iri = 'https://example.test/existing/definition'
    response = runner.acceptance.register_platform_tool_result(
        tool='get_ontology_read_model', arguments={'ontology_id': ontology, 'model_name': 'entity-list'},
        result={'structuredContent': {'ok': True, 'data': {
            'model_revision': 1, 'items': [{'iri': iri}]}}},
    )
    plan['projection']['items'] = []
    plan['projection']['decision_bindings'] = []
    plan['projection']['identity_bindings'] = [build_identity_binding(
        candidate_item_id='item-entity', resource_iri=iri, evidence_ref=response['artifact_path'])]
    plan['projection_digest'] = projection_digest(plan['projection'])
    path.write_text(json.dumps(plan))
    return plan, response


def coverage(production):
    return production.runner._handle_check_plan_coverage({
        'candidate_ref': CANDIDATE, 'plan_refs': [PLAN1], 'dispositions': []})


def test_reused_read_covers_only_existing_item_without_writes(production):
    plan, _ = reuse_plan(production)
    assert not validate_materialization_plan(plan)
    result = coverage(production)
    assert result['unaccounted_item_ids'] == ['relation-1']
    row = next(row for row in result['items'] if row['candidate_item_id'] == 'item-entity')
    assert row['reuse_binding']['resource_iri'] == 'https://example.test/existing/definition'
    assert not row['applied_plan_refs']
    assert not production.calls


def test_all_reuse_executes_no_empty_batch_and_can_close(production):
    plan, _ = reuse_plan(production)
    # The unrelated new relation remains an explicit pending disposition.
    result = production.runner._handle_check_plan_coverage({
        'candidate_ref': CANDIDATE, 'plan_refs': [PLAN1], 'dispositions': [
            {'candidate_item_id': 'relation-1', 'disposition': 'deferred', 'reason': 'business decision pending'}]})
    assert result['status'] == 'COMPLETE'
    execution = production.runner._handle_execute_approved_plans({'protocol_id': 'protocol', 'plan_refs': [PLAN1]})
    assert execution['ok'] and execution['completed'][0]['status'] == 'reused'
    assert not production.calls


def test_reuse_drift_and_fabricated_read_are_recoverable(production):
    _, response = reuse_plan(production)
    original = production.runner.staged_plan_read_forwarder
    def drift(tool, args):
        data = deepcopy(original(tool, args))
        data['data']['workspace']['model_revision'] = 2
        return data
    production.runner.staged_plan_read_forwarder = drift
    with pytest.raises(StagedSubmissionRejection) as exc:
        coverage(production)
    assert exc.value.data['reason_code'] == 'approval_stale'
    production.runner.staged_plan_read_forwarder = original
    assert coverage(production)['items'][0]['reuse_binding']
    target = production.run_root / response['artifact_path']
    target.chmod(0o600)
    target.write_text('{}')
    with pytest.raises(StagedSubmissionRejection) as exc:
        coverage(production)
    assert exc.value.data['reason_code'] == 'reuse_read_invalid'


def test_reuse_requires_current_candidate_content_approval(production):
    reuse_plan(production)
    path = staged_decision_artifact_paths(production.run_root, unified=True)['approvals']
    approvals = json.loads(path.read_text())
    approvals['decisions'][0]['content_digest'] = 'sha256:' + '0' * 64
    path.write_text(json.dumps(approvals))
    with pytest.raises(StagedSubmissionRejection) as exc:
        coverage(production)
    assert exc.value.data['reason_code'] == 'approval_content_mismatch'


def test_failed_existing_topology_does_not_latch_out_same_run_retry(production):
    from types import SimpleNamespace
    from modeling_team.platform_scope import PlatformScopeError

    runner = production.runner
    notifications = []
    runner._multi_slice_gate_reject = lambda *args: notifications.append(args)
    runner._multi_slice_gate_opened = True
    def fail(plan):
        raise PlatformScopeError('ontology creation is not authorized; correct scope/topology')
    original_scope = runner.scope
    runner.scope = SimpleNamespace(mode='existing', apply_ontology_plan=fail)
    runner._apply_multi_slice_ontology_plan({'ontology_plan': [{'name': 'new', 'slice_ids': ['s']}]})
    assert runner._multi_slice_gate_opened is False
    runner.scope = original_scope
    assert notifications[0][0] == 'topology_apply_incomplete'
    assert 'not authorized' in notifications[0][-1]
    assert not production.calls
