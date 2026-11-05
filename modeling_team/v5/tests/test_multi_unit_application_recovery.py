"""The scheduler may resume its exact active apply, never a different operation."""

import pytest
from test_framework_flow import Platform

from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.multi_unit import MultiUnitFlow


@pytest.mark.parametrize("active_operation", ["apply-00007", "apply-00008", "snapshot-00007"])
def test_scheduler_resumes_only_its_original_active_application(
    binding, workspace, saver, monkeypatch, active_operation
):
    scheduler = MultiUnitFlow(
        binding, workspace, Platform(), workspace.schema + "_cp", lambda selected: None
    )
    parent = scheduler.parent
    state = parent.initialize()
    parent._save({**state, "activity": "apply", "status": "blocked", "round": 7})
    unit = binding.data["work_unit_id"] + ":platform"
    assert parent.control.begin_activity(unit, active_operation)["admitted"]
    resumed = []

    def resume_original(flow, checkpointer):
        current = workspace.get(flow.work_id)["content"]
        assert current["activity"] == "apply" and current["round"] == 7
        assert flow.control.view()["active"][unit] == "apply-00007"
        resumed.append("apply-00007")
        flow.control.finish_turn(unit, "apply-00007")
        return flow._save({**current, "activity": "handoff", "status": "handoff_ready"})

    monkeypatch.setattr(WorkUnitFlow, "advance", resume_original)
    result = scheduler.advance()
    if active_operation == "apply-00007":
        assert resumed == [active_operation]
        assert result["work"]["status"] == "handoff_ready"
        assert not parent.control.view()["active"]
    else:
        assert not resumed
        assert result["work"]["status"] == "blocked"
        assert parent.control.view()["active"] == {unit: active_operation}
