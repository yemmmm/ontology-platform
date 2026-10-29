"""Dynamic recursive work uses the same graph, with retained siblings and one model writer."""

import json

from psycopg import sql
from test_framework_flow import Actor, Platform

from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.team import TeamChannel
from ontoweave_modeling.work_plan import WorkPlan


def test_delegate_dynamic_members_and_exact_replay(binding, workspace):
    binding.data["work_management"] = True
    plan = WorkPlan(binding.data, workspace)
    first = plan.delegate("a", "Bounded interpretation", material_ids=["source"])
    assert plan.delegate("a", "Bounded interpretation", material_ids=["source"]) == first
    child = WorkPlan(binding.data, workspace, "a")
    child.delegate("a-detail", "Local detail")
    channel = TeamChannel(binding.data, workspace, TaskControl(workspace), "a-detail")
    assert {"a", "a-detail", "modeling"} <= channel.members
    assert plan.ancestors(plan.row()["content"], "a-detail") == ["a-detail", "a", "modeling"]
    plan.update("a-detail", status="retired", reason="No longer a separate slice")
    assert len(plan.binding(binding).data["work_units"]) == 1


def test_recursive_delegation_dependency_and_selective_reentry(binding, workspace):
    binding.data["work_management"] = True
    platform = Platform()
    original = platform.call
    platform.call = lambda action, payload=None: (
        {"config_ref": "read-key"} if action == "read_config" else original(action, payload)
    )
    counts, order = {}, []

    def factory(selected):
        actor = Actor(selected, platform)

        def invoke(root, purpose, prompt, inputs):
            key = (selected.actor, purpose)
            counts[key] = counts.get(key, 0) + 1
            order.append(key)
            result = actor(root, purpose, prompt, inputs)
            response = json.loads(result["final_response"])
            response["consumed_ids"] = [m["id"] for m in inputs]
            if (
                purpose == "modeling"
                and counts[key] == 1
                and selected.actor in {"modeling", "assembly"}
            ):
                plan = WorkPlan(selected.data, workspace, selected.actor)
                if selected.actor == "modeling":
                    plan.delegate("assembly", "Own local concepts and unallocated scope")
                    plan.delegate("review", "Check completed assembly", dependencies=["assembly"])
                else:
                    plan.delegate("definition", "Prepare local definition")
                response.update(status="waiting_children", candidate=None, changes=None)
            elif purpose == "modeling":
                children = json.loads(prompt)["child_results"]
                expected = {"modeling": {"assembly", "review"}, "assembly": {"definition"}}.get(
                    selected.actor, set()
                )
                assert {c["unit_id"] for c in children} == expected
                channel = TeamChannel(
                    selected.data, workspace, TaskControl(workspace), selected.actor
                )
                for item in children:
                    assert (
                        json.loads(channel.read(item["material_ref"])["text"])["status"]
                        == "proposed"
                    )
            result["final_response"] = json.dumps(response)
            return result

        return invoke

    namespace = workspace.schema + "_tree_cp"
    try:
        first = MultiUnitFlow(binding, workspace, platform, namespace, factory).advance()
        assert first["work"]["status"] == "handoff_ready" and len(platform.effects) == 1
        assert order.index(("review", "modeling")) > order.index(("definition", "modeling"))
        assert counts[("assembly", "modeling")] == 2
        assert counts[("modeling", "modeling")] == 2
        retained = first["units"]["review"]["execution_ref"]
        plan = WorkPlan(binding.data, workspace)
        plan.reopen("definition", "Local definition changed; review remains valid in this test")
        second = MultiUnitFlow(binding, workspace, platform, namespace, factory).advance()
        assert second["work"]["status"] == "handoff_ready" and len(platform.effects) == 2
        assert second["units"]["review"]["execution_ref"] == retained
        assert counts[("review", "modeling")] == 1
        assert counts[("definition", "modeling")] == 2
        assert counts[("assembly", "modeling")] == 3
    finally:
        with workspace.connect(autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(namespace))
            )
