"""Current contribution completion and deterministic partial receipt handoff."""

import json

import pytest
from test_role_team_flow import RolePlatform
from test_role_team_flow import role_binding as role_binding  # noqa: PLC0414

from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.role_work import application_failure, pending_units
from ontoweave_modeling.work_plan import WorkPlan


@pytest.fixture
def progress_flow(role_binding, workspace):
    platform = RolePlatform()
    flow = WorkUnitFlow(role_binding, workspace, platform, None)
    flow.initialize()
    manager = WorkPlan(role_binding.data, workspace)

    def configure(plan):
        plan["units"]["modeler"]["work_phase"] = "propose"
        plan["units"]["cq-public"]["status"] = "retired"

    manager.change(configure)
    return flow, manager, platform


@pytest.mark.parametrize(
    "status,has_changes,integrated,applied,expected",
    [
        ("no_change", True, True, False, []),
        ("no_change", True, False, True, ["modeler"]),
        ("proposed", True, True, False, ["modeler"]),
        ("proposed", True, True, True, []),
        ("proposed", False, True, False, []),
        ("proposed", False, False, False, ["modeler"]),
    ],
)
def test_pending_uses_current_no_change_integration_and_real_proposed_application(
    progress_flow, workspace, status, has_changes, integrated, applied, expected
):
    flow, manager, _ = progress_flow
    changes = workspace.put_reference(
        "retained-changes", "model_changes", {"changes": [{"change_id": "old-update"}]}, 0
    )
    result = workspace.put_reference(
        "current-result",
        "role_work_result",
        {"status": status, "changes_ref": changes if has_changes else None},
        0,
    )
    child = flow.binding.for_unit("modeler")
    workspace.put_reference(
        child.identity + ":work",
        "work",
        {"status": "proposal_ready", "work_generation": 0, "role_result_ref": result},
        0,
    )
    composition = workspace.put_reference(
        "current-composition",
        "candidate",
        {"status": status, "contribution_refs": [result] if integrated else []},
        0,
    )
    flow._save({**workspace.get(flow.work_id)["content"], "candidate_ref": composition})
    if applied:
        workspace.put_reference(
            "previous-application",
            "role_application",
            {"origins": {"qualified": {"result_ref": result, "change_id": "old-update"}}},
            0,
        )
    assert pending_units(flow, manager.row()["content"]) == expected


@pytest.mark.parametrize("defect", ["missing", "waiting_peer", "old_generation"])
def test_pending_does_not_accept_unready_or_stale_no_change(progress_flow, workspace, defect):
    flow, manager, _ = progress_flow
    result = workspace.put_reference(
        "current-result", "role_work_result", {"status": "no_change", "changes_ref": None}, 0
    )
    composition = workspace.put_reference(
        "current-composition", "candidate", {"contribution_refs": [result]}, 0
    )
    flow._save({**workspace.get(flow.work_id)["content"], "candidate_ref": composition})
    if defect != "missing":
        workspace.put_reference(
            flow.binding.for_unit("modeler").identity + ":work",
            "work",
            {
                "status": "waiting_peer" if defect == "waiting_peer" else "proposal_ready",
                "work_generation": 1 if defect == "old_generation" else 0,
                "role_result_ref": result,
            },
            0,
        )
    assert pending_units(flow, manager.row()["content"]) == ["modeler"]


@pytest.mark.parametrize(
    "status,errors,expected",
    [
        ("partial", [{"change_id": "failed-change"}], {"modeler", "modeler-b"}),
        ("not_written", [{"change_id": "failed-change"}], {"modeler"}),
        ("not_written", [], {"modeler", "modeler-b", "applied-owner"}),
        ("uncertain", [{"change_id": "failed-change"}], set()),
        ("completed", [], set()),
    ],
)
def test_failure_handoff_preserves_full_receipt_and_reopens_only_affected_owners(
    progress_flow, workspace, status, errors, expected
):
    flow, manager, platform = progress_flow
    for owner in ("modeler-b", "applied-owner"):
        manager.delegate(owner, "Preserve approved meaning", role_id="modeling")
    origins = {
        "failed-change": {"owner_work_id": "modeler", "change_id": "local-one"},
        "batch-peer": {"owner_work_id": "modeler-b", "change_id": "local-two"},
        "successful-change": {"owner_work_id": "applied-owner", "change_id": "local-three"},
    }
    candidate = {"origins": origins}
    receipt = {
        "status": status,
        "errors": errors,
        "batches": [
            {"write_state": "applied", "change_ids": ["successful-change"]},
            {"write_state": "not_written", "change_ids": ["failed-change", "batch-peer"]},
        ]
        if status == "partial"
        else [],
    }
    state = {
        "operation_ref": workspace.put_reference("apply-one", "application_reference", receipt, 0),
        "candidate_ref": workspace.put_reference("composition", "candidate", candidate, 0),
    }
    application_failure(flow, state)
    messages = flow.team.messages()
    assert {message["target"] for message in messages} == expected
    plan = manager.row()["content"]
    for owner in ("modeler", "modeler-b", "applied-owner"):
        assert plan["units"][owner]["generation"] == (1 if owner in expected else 0)
    if expected:
        material = workspace.read_reference(messages[0]["metadata"]["material_refs"][0])
        assert json.loads(material["text"]) == {
            "operation_ref": state["operation_ref"],
            "receipt": receipt,
            "origins": origins,
        }
        if status == "partial":
            assert all("partial" in message["body"] for message in messages)
            assert all("confirmed not_written" not in message["body"] for message in messages)
    else:
        assert not workspace.list_kind("team_material")
    assert workspace.read_reference(state["operation_ref"]) == receipt
    assert workspace.read_reference(state["candidate_ref"]) == candidate
    assert not workspace.list_kind("role_application")
    assert not platform.calls
