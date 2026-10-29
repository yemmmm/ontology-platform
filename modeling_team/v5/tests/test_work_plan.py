"""Dynamic recursive work uses the same graph, with retained siblings and one model writer."""

import json

from psycopg import sql
from test_framework_flow import Actor, Platform

from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.multi_unit import MultiUnitFlow
from ontoweave_modeling.team import TeamChannel
from ontoweave_modeling.work_plan import WorkPlan


def test_host_tree_cli_reads_dynamic_members_and_pages_one_level(binding, workspace, monkeypatch):
    from ontoweave_modeling import cli

    plan = WorkPlan(binding.data, workspace)
    plan.delegate("a", "First scope")
    plan.delegate("b", "Second scope")
    WorkPlan(binding.data, workspace, "a").delegate("detail", "Nested scope")
    monkeypatch.setattr(cli, "repository", lambda selected: (workspace, {}))
    args = cli.parser().parse_args(["work-tree", "--run-dir", str(binding.root), "--limit", "1"])
    result = cli.dispatch(args)
    assert result["total"] == 2 and len(result["units"]) == 1 and result["next_offset"] == 1
    assert plan.tree("a")["units"][0]["unit_id"] == "detail"


def test_late_child_completion_does_not_leave_a_stale_parent_wait(binding, workspace, saver):
    plan = WorkPlan(binding.data, workspace)
    plan.delegate("ready-child", "Already completed scope")
    selected = plan.binding(binding)
    child = WorkUnitFlow(selected.for_unit("ready-child"), workspace, Platform(), None)
    child._save({**child.initialize(), "status": "proposal_ready"})
    platform = Platform()
    actor = Actor(selected, platform)
    calls = []

    def invoke(root, purpose, prompt, inputs):
        calls.append(purpose)
        result = actor(root, purpose, prompt, inputs)
        if len(calls) == 1:
            response = json.loads(result["final_response"])
            response.update(status="waiting_children", candidate=None, changes=None)
            result["final_response"] = json.dumps(response)
        return result

    final = WorkUnitFlow(selected, workspace, platform, invoke).advance(saver)
    assert final["status"] == "handoff_ready"
    assert calls == ["modeling", "modeling", "self_check"]


def test_reentry_requested_during_turn_preserves_candidate_but_does_not_apply_old_generation(
    binding, workspace, saver
):
    plan = WorkPlan(binding.data, workspace)
    plan.delegate("child", "Local scope")
    selected = plan.binding(binding)
    child = WorkUnitFlow(selected.for_unit("child"), workspace, Platform(), None)
    child._save({**child.initialize(), "status": "proposal_ready"})
    platform = Platform()
    actor = Actor(
        selected,
        platform,
        lambda purpose: plan.reopen("child", "New scoped input") if purpose == "modeling" else None,
    )
    final = WorkUnitFlow(selected, workspace, platform, actor).advance(saver)
    assert final["status"] == "work_change_pending" and not platform.effects
    assert final["candidate_ref"] and actor.calls == ["modeling"]


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


def test_four_parent_thirty_slice_navigation_and_reconstruction_stays_bounded(binding, workspace):
    plan = WorkPlan(binding.data, workspace)
    for p in range(4):
        parent = f"part-{p}"
        plan.delegate(parent, f"Business part {p}", material_ids=["source"])
        children = WorkPlan(binding.data, workspace, parent)
        for child in range(30):
            children.delegate(
                f"{parent}-{child}", f"Bounded slice {child}", material_ids=["source"]
            )
    reconstructed = WorkPlan(binding.data, workspace)
    root = reconstructed.tree()
    assert root["total"] == 4 and all(u["child_count"] == 30 for u in root["units"])
    assert len(json.dumps(root)) < 5000
    for p in range(4):
        ids, offset = [], 0
        while offset is not None:
            page = reconstructed.tree(f"part-{p}", offset, 7)
            assert len(page["units"]) <= 7 and page["coverage"] == "direct_children_only"
            ids.extend(u["unit_id"] for u in page["units"])
            offset = page["next_offset"]
        assert len(set(ids)) == 30 and all(i.startswith(f"part-{p}-") for i in ids)
    selected = reconstructed.binding(binding).for_unit("part-2-15")
    assert selected.data["assigned_material_ids"] == ["source"] and not selected.direct_units


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
