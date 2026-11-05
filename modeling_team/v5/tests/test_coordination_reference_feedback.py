"""Wrong handoff reference kinds must remain recoverable at integration."""

import pytest
from test_role_team_flow import role_binding

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.role_team import _expand_coordination

root_role_binding = role_binding


def test_coordination_rejects_material_reference_with_actionable_feedback(
    root_role_binding, workspace
):
    reference = workspace.put_reference(
        root_role_binding.identity + ":team:material:modeler:handoff",
        "team_material",
        {"text": "A Modeler handoff is not a Coordinator role result."},
        0,
    )
    plan = {
        "schema_version": "integration-plan/v1",
        "plan_id": "wrong-reference-kind",
        "contributions": [],
        "coordination_refs": [reference],
        "shared_decision_refs": [],
        "deferred": [],
        "ontology_targets": {},
        "check_units": [],
    }
    with pytest.raises(FrameworkError) as caught:
        _expand_coordination(root_role_binding, workspace, plan, {"consumed_refs": []})
    assert caught.value.code == "coordination_reference_kind_invalid"
    assert caught.value.detail["reference"] == reference
    assert caught.value.detail["expected_kind"] == "role_work_result"
    assert caught.value.detail["actual_kind"] == "team_material"
