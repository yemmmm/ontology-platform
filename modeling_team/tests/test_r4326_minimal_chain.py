"""R4.3-026 configuration/staging contracts; no model calls or semantic verdicts."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

from modeling_team.capability_mcp import DIRECT_MODELING_OPERATIONS
from modeling_team.competency_questions import validate_draft_document
from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.runner import TeamRunner
from modeling_team.scenario_map import validate_scenario_map, validate_topology_decision
from modeling_team.staged_decisions import (
    UNIFIED_CANDIDATE_FIELDS,
    UNIFIED_CANDIDATE_ITEM_FIELDS,
    UNIFIED_CANDIDATE_ITEM_OPTIONAL_FIELDS,
)
from modeling_team.tests.test_runner import CapturingAdapter

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "docs/evaluation-scenarios/minimal-installation-chain"
PROFILE = ROOT / "modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml"
TASK = ROOT / "modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml"


def read(path):
    return json.loads(path.read_text())


def test_pair_loads_current_direct_route_without_protocol_or_checkpoint_experiment():
    config = load_multi_slice_team_configuration(PROFILE, TASK, root=ROOT)
    assert {a.package.role for a in config.profile.agents} == {
        "coordinator", "modeling", "competency-question",
    }
    assert config.profile.communication == frozenset({
        ("coordinator", "modeling"), ("modeling", "coordinator"),
    })
    assert config.task.parameters["unified_semantic_graph"] is True
    assert config.task.parameters["acceptance_target"] == "cq_semantic"
    assert not config.task.parameters.get("modeling_checkpoints")
    business = [s for s in config.task.role_sources if s.classification == "business-source"]
    assert len(business) == 1
    assert business[0].path == SCENARIO / "modeling-input/scenario.md"
    manifest = read(SCENARIO / "modeling-input/input-manifest.json")
    assert manifest["business_sources"] == [{
        "path": business[0].relative_path.as_posix(),
        "sha256": hashlib.sha256(business[0].path.read_bytes()).hexdigest(),
    }]
    for agent in config.profile.agents:
        assert agent.package.package_id.startswith("minimal-chain-")
        assert not agent.package.references  # No implicit full manuals behind compact sources.
    modeling = next(a.package for a in config.profile.agents if a.agent_id == "modeling")
    assert [s.parent.name for s in modeling.required_skills] == ["minimal-chain-modeling"]


def test_compact_candidate_and_map_shapes_match_the_existing_contracts():
    compact = read(ROOT / "modeling_team/references/r4-3-026-minimal-chain-contract.json")
    candidate = compact["candidate"]
    assert set(candidate["fields"]) == UNIFIED_CANDIDATE_FIELDS
    assert set(candidate["item_fields"]) == UNIFIED_CANDIDATE_ITEM_FIELDS
    assert set(candidate["item_optional_fields"]) == UNIFIED_CANDIDATE_ITEM_OPTIONAL_FIELDS
    canonical = read(ROOT / "modeling_team/references/r4-0-007-scenario-map-contract.json")
    for key in ("schema_version", "required_sections", "identity_fields", "slices_item_fields",
                "cross_slice_dependencies", "cross_slice_competency_questions",
                "explicit_unknowns"):
        assert compact["scenario_map"][key] == canonical["scenario_map"][key]
    for key in ("required_fields", "optional_fields", "status", "candidate_ref_fields"):
        assert compact["scenario_map"]["shared_terms"][key] == \
            canonical["scenario_map"]["shared_terms"][key]
    for key in ("schema_version", "fields", "required_option_ids", "option_fields",
                "dimensions", "optional_fields"):
        assert compact["topology_decision"][key] == canonical["topology_decision"][key]

    # Exercise the documented map/topology shape against the actual validators.
    # owner_slice is a slice ID, despite a misleading rule in the longer reference.
    scenario_map = {
        "schema_version": compact["scenario_map"]["schema_version"],
        "scenario_id": "syntax-test", "topology_decision_ref": "topology-decision.json",
        "slices": [{"slice_id": "slice-test", "name": "syntax", "scope": "syntax",
                    "owner": "coordinator", "status": "pending", "viewpoints": []}],
        "shared_terms": [{"term": "syntax", "used_by_slices": ["slice-test"],
                          "owner_slice": "slice-test", "definition_id": "definition-test",
                          "meaning_scope": "syntax", "status": "proposed", "candidate_refs": []}],
        "cross_slice_dependencies": [], "cross_slice_competency_questions": [],
        "explicit_unknowns": [], "adjustments": [],
    }
    assert not validate_scenario_map(scenario_map)
    scenario_map["shared_terms"][0]["owner_slice"] = "coordinator"
    assert validate_scenario_map(scenario_map)
    topology = compact["topology_decision"]
    assert not validate_topology_decision({
        "schema_version": topology["schema_version"], "scenario_id": "syntax-test",
        "options": [{"option_id": option, "assessment": dict.fromkeys(topology["dimensions"],
                                                                      "syntax-only comparison")}
                    for option in topology["required_option_ids"]],
        "selected_option": "single_ontology", "rationale": "syntax-only", "decided_by": "coordinator",
    })


def test_private_seeds_can_form_separate_current_cq_review_drafts():
    seeds = read(SCENARIO / "cq-private/question-seeds.json")
    config = load_multi_slice_team_configuration(PROFILE, TASK, root=ROOT)
    seed_source = next(s for s in config.task.role_sources if s.path.name == "question-seeds.json")
    assert seed_source.roles == {"competency-question"}
    assert seeds["status"] == "unreviewed"
    assert len({q["question_id"] for q in seeds["questions"]}) == 4
    for kind, phase in (("panorama", "panorama-review"), ("slice", "slice-review")):
        questions = []
        for seed in seeds["questions"]:
            if seed["scope_kind"] != kind:
                continue
            question = {k: v for k, v in seed.items() if k != "scope_kind"}
            question.update(scope={"kind": kind, "slice_ids": [] if kind == "panorama"
                                   else ["syntax-test-slice"]}, content_version=1)
            for ref in question["evidence_refs"]:
                assert ROOT / ref["source"] == SCENARIO / "modeling-input/scenario.md"
                assert ref["locator"]
            questions.append(question)
        draft = validate_draft_document({
            "schema_version": "r3-0-011-cq-draft/v1", "phase": phase,
            "draft_id": "syntax-test-" + kind, "questions": questions,
            "superseded_draft_id": None, "note": "Schema check only, no review or freeze.",
        })
        assert draft["questions"]
        assert {q["proposed_visibility"] for q in questions} == {
            "public" if kind == "panorama" else "hidden",
        }


def test_runner_stages_exact_private_sources_and_freezes_compact_packages(tmp_path):
    run_id = "r4326-contract-" + uuid4().hex[:10]
    run_root = ROOT / "workspaces/modeling-runs" / run_id
    adapter = CapturingAdapter()
    runner = TeamRunner(repository_root=ROOT, adapter=adapter,
                        ledger_root=tmp_path / "ledger",
                        freeze_started_at=datetime.now(UTC).isoformat())
    try:
        run = runner.prepare(run_id=run_id, profile_path=PROFILE, task_path=TASK,
                             scope={"mode": "create"})
        assert adapter.started == []
        assert set(DIRECT_MODELING_OPERATIONS) <= set(
            runner.acceptance.capability_descriptors["modeling"]["operations"]
        )
        assert not (run.root / "sources/protocol").exists()
        manifest = read(run.root / "source-manifest.json")["sources"]
        assert len(manifest) == len(run.configuration.task.role_sources)
        for agent in run.configuration.profile.agents:
            role = agent.package.role
            expected = {s.relative_path.as_posix() for s in run.configuration.task.role_sources
                        if role in s.roles}
            staged = run.root / "sources" / role
            assert {p.relative_to(staged).as_posix() for p in staged.rglob("*")
                    if p.is_file()} == expected
            text = runner._task_text(role)
            prompt_paths = {line.removeprefix("- /agent/home/sources/")
                            for line in text.splitlines()
                            if line.startswith("- /agent/home/sources/")}
            assert prompt_paths == expected
            for entry in manifest:
                if role in entry["roles"]:
                    assert hashlib.sha256((staged / entry["path"]).read_bytes()).hexdigest() \
                        == entry["sha256"]
            if role != "competency-question":
                assert not any("cq-private" in path for path in expected)
                assert "question-seeds.json" not in text.split("Task objective:")[0]
                assert "r4-3-025-direct-modeling-contract.json" in text
        baseline, _ = TeamRunner.preview_baseline(
            repository_root=ROOT, run_id=run_id, profile_path=PROFILE, task_path=TASK,
        )
        for agent in run.configuration.profile.agents:
            assert baseline["files"]["instructions:" + agent.package.package_id] == \
                hashlib.sha256(agent.package.instructions_path.read_bytes()).hexdigest()
        assert all("industrial-service-v3" not in entry["path"]
                   and "checkpoint-minimal" not in entry["path"] for entry in manifest)
    finally:
        runner.cleanup()
        rmtree(run_root, ignore_errors=True)


@pytest.mark.parametrize("task_name", [
    "r4-0-009-asset-fault-workorder", "r4-0-009-multiview-semantic-acceptance",
    "r3-0-015-minimal-flow",
])
def test_retained_tasks_still_load_with_their_existing_profile(task_name):
    config = load_multi_slice_team_configuration(
        ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml",
        ROOT / f"modeling_team/tasks/{task_name}.yaml", root=ROOT,
    )
    assert config.task.task_id == task_name
    assert all(not a.package.package_id.startswith("minimal-chain-")
               for a in config.profile.agents)
