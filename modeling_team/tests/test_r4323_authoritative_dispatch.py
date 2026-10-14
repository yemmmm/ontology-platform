"""R4.3-023 Runner/role contracts, without provider calls or platform writes.

These checks prove task delivery and mounted contracts, not semantic coverage.
Actual bounded role-output evidence is recorded separately from these assertions.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_r3011_runner_wiring import _CQRunner, PROFILE

ROOT = repository_root()
TASK = ROOT / "modeling_team/tasks/r4-0-009-asset-fault-workorder.yaml"
MAPPINGS = {
    "r4-0-010-relational-mapping-contract.json",
    "r4-0-011-api-mapping-contract.json",
}


@pytest.mark.parametrize("objective", [None, "Ω原任务\n逐字正文，不由派单替代。"])
def test_actual_start_delivers_identity_objective_skills_and_private_sources(objective):
    harness = _CQRunner()
    runner = harness.runner
    calls = {}
    harness.adapter.start_task = lambda agent_id, text, skills, roster: calls.update(
        {agent_id: (text, skills, roster)}
    )
    try:
        run = runner.prepare(
            run_id=harness.run_id, profile_path=PROFILE, task_path=TASK,
            scope={"mode": "create"},
        )
        if objective is not None:
            run.configuration = replace(
                run.configuration, task=replace(run.configuration.task, objective=objective),
            )
        runner.start()
        assert set(calls) == {a.agent_id for a in run.configuration.profile.agents}
        task = run.configuration.task
        for agent in run.configuration.profile.agents:
            text, skills, roster = calls[agent.agent_id]
            assert text.endswith(f"Task identity: {task.task_id}\n\nTask objective:\n{task.objective}")
            assert text.count(f"Task identity: {task.task_id}") == 1
            assert text.count(task.objective) == 1
            assert skills == [str(p) for p in agent.package.required_skills]
            assert set(roster) == set(calls)
            for source in task.role_sources:
                alias = f"/agent/home/sources/{source.relative_path.as_posix()}"
                staged = run.root / "sources" / agent.agent_id / source.relative_path
                if agent.package.role in source.roles:
                    assert alias in text
                    assert staged.read_bytes() == source.path.read_bytes()
                else:
                    assert alias not in text
                    assert not staged.exists()
            assert "tester-only" not in text
            assert "task.snapshot.yaml" not in text
            assert not any(name in text for name in MAPPINGS)
        modeling_text = calls["modeling"][0]
        assert "r4-0-012-modeling-contract.json" in modeling_text
        assert "platform-neutral-candidate-authoring.json" in modeling_text
        assert "schema.sql" in modeling_text
        assert "schema.sql" not in calls["coordinator"][0]
        assert "schema.sql" not in calls["protocol"][0]
    finally:
        harness.cleanup()


def test_task_identity_is_in_variable_tail_and_continuation_is_preserved():
    config = load_multi_slice_team_configuration(PROFILE, TASK, root=ROOT)
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=config, protocol_context=None, gate_binding=None)
    first = runner._task_text("modeling")
    runner.run.configuration = replace(config, task=replace(config.task, task_id="another-task"))
    second = runner._task_text("modeling")
    assert first.split("\n\nTask identity:")[0] == second.split("\n\nTask identity:")[0]
    assert "Task identity: another-task\n\nTask objective:\n" in second
    runner._resume_plan = SimpleNamespace(role_packets={"modeling": {"next_step": "保留当前版本"}})
    continued = runner._task_text("modeling")
    assert continued.startswith(second)
    assert "Checkpoint continuation for this role (Runner-verified):" in continued
    assert '"next_step": "保留当前版本"' in continued


def test_only_bounded_chain_drops_mapping_sources_and_retains_necessary_contracts():
    config = load_multi_slice_team_configuration(PROFILE, TASK, root=ROOT)
    names = {s.path.name for s in config.task.role_sources}
    assert not names & MAPPINGS
    assert "This Task selects unified_semantic_graph=true" in config.task.objective
    assert "r3-0-009-unified-graph/v2" in config.task.objective
    assert config.task.parameters["unified_semantic_graph"] is True
    assert {
        "schema.sql", "sample-data.sql", "scenario-brief.md", "business-terms.md",
        "r4-0-012-modeling-contract.json", "platform-neutral-candidate-authoring.json",
        "r4-0-007-scenario-map-contract.json", "r3-0-008b-staged-decisions-contract.json",
        "r3-0-009-unified-graph-contract.json", "r4-0-024-model-check-contract.json",
        "r3-0-011-competency-question-contract.json", "modeling-batch-item-contract.json",
        "acceptance-stage-handoff-contract.json",
    } <= names
    full = load_multi_slice_team_configuration(
        PROFILE, ROOT / "modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml", root=ROOT,
    )
    assert MAPPINGS <= {s.path.name for s in full.task.role_sources}


def test_isolated_acceptance_does_not_receive_production_identity():
    config = load_multi_slice_team_configuration(PROFILE, TASK, root=ROOT)
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=config, protocol_context=None, gate_binding=None)
    text = runner._task_text("acceptance")
    assert "Task identity:" not in text
    assert "/agent/home/sources/" not in text
