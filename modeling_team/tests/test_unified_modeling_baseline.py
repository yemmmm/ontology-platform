"""The minimal business fixture must exercise the ordinary modeling instructions."""

import json
from pathlib import Path

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.direct_modeling import compile_model_changes
from modeling_team.runner import TeamRunner


ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "modeling_team/tasks"
PROFILES = ROOT / "modeling_team/profiles"
MINIMAL_TASK = TASKS / "r4-3-026-minimal-installation-chain.yaml"


@pytest.mark.parametrize("runtime", ["codex", "dsh"])
@pytest.mark.parametrize("business_task", [
    "r4-0-009-asset-fault-workorder", "r4-0-009-multiview-semantic-acceptance",
])
def test_business_fixtures_load_identical_general_role_instructions(runtime, business_task):
    suffix = "-dsh" if runtime == "dsh" else ""
    profile = PROFILES / f"unified-modeling{suffix}.yaml"
    minimal = load_multi_slice_team_configuration(profile, MINIMAL_TASK, root=ROOT)
    ordinary = load_multi_slice_team_configuration(
        profile, TASKS / f"{business_task}.yaml", root=ROOT,
    )
    assert minimal.profile.runtime == ordinary.profile.runtime == runtime
    assert minimal.task.parameters == ordinary.task.parameters
    for small, other in zip(minimal.profile.agents, ordinary.profile.agents, strict=True):
        assert small.package.package_id == other.package.package_id == small.package.role
        assert small.package.instructions_path == other.package.instructions_path
        assert small.package.required_skills == other.package.required_skills
        assert small.package.references == other.package.references
        assert runtime in small.package.runtime
    assert {s.relative_path for s in minimal.task.role_sources
            if s.classification == "business-source"} != {
                s.relative_path for s in ordinary.task.role_sources
                if s.classification == "business-source"
            }
    common_sources = {s.relative_path: s.roles for s in minimal.task.role_sources
                      if s.relative_path.as_posix().startswith("modeling_team/")}
    assert common_sources == {
        s.relative_path: s.roles for s in ordinary.task.role_sources
        if s.relative_path.as_posix().startswith("modeling_team/")
    }
    assert "r4-0-012-modeling-contract.json" in {p.name for p in common_sources}
    assert "r4-3-026-minimal-chain-contract.json" not in {p.name for p in common_sources}
    for role in ("coordinator", "modeling"):
        assert all("cq-private" not in s.relative_path.parts
                   for s in minimal.task.role_sources if role in s.roles)


@pytest.mark.parametrize("suffix", ["", "-dsh"])
def test_existing_minimal_profile_names_select_the_same_general_baseline(suffix):
    old = load_multi_slice_team_configuration(
        PROFILES / f"r4-3-026-minimal-installation-chain{suffix}.yaml", MINIMAL_TASK, root=ROOT,
    )
    common = load_multi_slice_team_configuration(
        PROFILES / f"unified-modeling{suffix}.yaml", MINIMAL_TASK, root=ROOT,
    )
    assert old.profile.agents == common.profile.agents
    assert old.profile.communication == common.profile.communication
    assert old.profile.parameters == common.profile.parameters


def test_frozen_role_and_skill_digests_are_equal_across_business_fixtures():
    profile = PROFILES / "unified-modeling.yaml"
    small, _ = TeamRunner.preview_baseline(
        repository_root=ROOT, run_id="baseline-minimal", profile_path=profile,
        task_path=MINIMAL_TASK,
    )
    ordinary, _ = TeamRunner.preview_baseline(
        repository_root=ROOT, run_id="baseline-ordinary", profile_path=profile,
        task_path=TASKS / "r4-0-009-asset-fault-workorder.yaml",
    )
    instruction_files = {key: digest for key, digest in small["files"].items()
                         if key.startswith(("instructions:", "skill:"))}
    assert instruction_files == {
        key: digest for key, digest in ordinary["files"].items()
        if key.startswith(("instructions:", "skill:"))
    }
    assert "instructions:modeling" in instruction_files
    assert "skill:modeling:SKILL.md" in instruction_files
    assert all("minimal-chain" not in key for key in instruction_files)


def test_shared_fields_only_example_compiles_the_declared_role_without_instances():
    contract = json.loads(
        (ROOT / "modeling_team/references/r4-3-025-direct-modeling-contract.json").read_text()
    )
    request = contract["fields_only_example"]["request"]
    change = request["changes"][0]
    batches, _ = compile_model_changes(
        request, candidate=None, ontology_by_item={change["change_id"]: "test-ontology"},
        resolve_binding=lambda _ref: None,
    )
    commands = [item for batch in batches for item in batch["items"]]
    assert [item["command_kind"] for item in commands] == ["create_class"]
    declaration = commands[0]["payload"]["semantic_definition"]
    assert declaration == change["fields"]["semantic_definition"]
    assert declaration["semantic_role"] == "object"
    assert declaration["business_meaning"] and declaration["applicability"]
    assert declaration["unknowns"]


def test_direct_gate_retains_write_integrity_checks_with_shared_contracts(tmp_path):
    from modeling_team.staged_decisions import staged_decision_artifact_paths
    from modeling_team.tests.test_r30009_runner_wiring import _UnifiedRunner

    staged = _UnifiedRunner(tmp_path)
    try:
        staged.prepare()
        assert staged.runner._check_staged_decision_gates() is True
        paths = staged_decision_artifact_paths(staged.run_root, unified=True)
        (paths["receipts_dir"] / "receipt-1.json").write_text("{broken json")
        assert staged.runner._check_staged_decision_gates() is False
        assert staged.runner._staged_gate_killed is True
    finally:
        staged.cleanup()
