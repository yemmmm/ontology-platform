"""R3.0-006 full real Task entry (v3 execution-gap closure, design §3.G1).

Covers test plan T-G1-1…T-G1-3: the single complete real Task loads through the
real configuration seam with all four selectors, both frozen legacy opt-in
assets still load byte-unchanged, and the Modeling instruction text for the
stage 3 slot contract field matches the ``validate_stage3_slot`` dispatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.staged_decisions import validate_stage3_slot

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
FULL_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-006-real-full.yaml"
LEGACY_008B_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
LEGACY_009_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-009-unified-graph-real.yaml"
MODELING_INSTRUCTIONS = (
    REPO_ROOT / "modeling_team" / "agent-packages" / "modeling" / "instructions.md"
)

# Frozen legacy opt-in assets.  The one-time baseline comparison against
# 6047d381 (git diff --quiet 6047d381 -- <asset>) was recorded as delivery
# evidence in developer-progress.md; the persistent test pins the same bytes by
# content digest so a source/shallow checkout needs no Git history.
FROZEN_ASSET_SHA256 = {
    LEGACY_008B_TASK: "e6c86912cf229789c9f624bc702c37526d345d38c9e4871f7199581913688ae9",
    LEGACY_009_TASK: "99a07715f622ed36c28c0f782b600f4cb6290c5616a962fb7836c5f5a05fdddb",
}


def _slot(*, unified: bool) -> dict:
    return {
        "schema_version": "r3-0-009-stage3-slot/v1" if unified else "r3-0-008b-stage3-slot/v1",
        "scenario_id": "scenario",
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/candidates/candidate.json"],
        "candidate_contract" if unified else "deferred_contract": (
            "r3-0-009-unified-graph/v1" if unified else "R3.0-009"
        ),
        "slot_note": None,
    }


def test_t_g1_1_full_real_task_loads_with_four_selectors() -> None:
    configuration = load_multi_slice_team_configuration(PROFILE, FULL_TASK)
    task = configuration.task
    assert task.task_id == "r3-0-006-real-full"
    assert task.parameters == {
        "multi_slice_workflow": True,
        "staged_modeling_decisions": True,
        "unified_semantic_graph": True,
        "competency_question_acceptance": True,
    }
    roles = {agent.agent_id for agent in configuration.profile.agents}
    assert roles == {"coordinator", "modeling", "protocol", "competency-question"}
    # Business inputs are staged exactly per the R3.0-008B real-task precedent,
    # including the competency-question role reading the four approved inputs.
    by_path = {source.path.name: source for source in task.role_sources}
    assert set(by_path) == {
        "scenario-brief.md",
        "business-terms.md",
        "schema.sql",
        "sample-data.sql",
        "r3-0-002-scenario-map-contract.json",
        "r3-0-008b-staged-decisions-contract.json",
        "r3-0-009-unified-graph-contract.json",
        "platform-neutral-candidate-authoring.json",
        "modeling-batch-item-contract.json",
        "r3-0-011-competency-question-contract.json",
    }
    assert by_path["scenario-brief.md"].roles == frozenset(
        {"coordinator", "modeling", "competency-question"}
    )
    assert by_path["schema.sql"].roles == frozenset({"modeling", "competency-question"})
    for name in (
        "r3-0-002-scenario-map-contract.json",
        "r3-0-008b-staged-decisions-contract.json",
        "r3-0-009-unified-graph-contract.json",
    ):
        assert by_path[name].roles == frozenset({"coordinator", "modeling", "protocol"})
    assert by_path["platform-neutral-candidate-authoring.json"].roles == frozenset(
        {"modeling", "protocol"}
    )
    assert by_path["modeling-batch-item-contract.json"].roles == frozenset({"protocol"})
    assert by_path["r3-0-011-competency-question-contract.json"].roles == frozenset(
        {"competency-question"}
    )
    # The Protocol tool whitelist stays without submit_modeling_batch.
    assert "submit_modeling_batch" not in task.protocol_tools
    assert task.retain_nonempty is True
    assert task.semantic_start_evidence == (
        "clean-checkout-and-empty-status",
        "canonical-mode-http-200-rdf-primary",
        "role-visible-source-manifest",
        "frozen-runtime-baseline",
    )
    # Terminal evidence is the 008B ∪ 009 union plus the two CQ items and never
    # a "batch acceptance PASS" item: acceptance runs outside the run terminal.
    evidence = set(task.expected_terminal_evidence)
    assert {
        "stage3-neutral-slot-with-009-contract",
        "009-candidates-published-with-evidence",
        "009-approvals-decisions-and-translation-approvals-recorded",
        "009-materialization-plan-with-approved-projection",
        "cq-public-projection-published",
        "cq-question-pool-frozen-hidden-host-only",
        "conclusions-analyzed-not-materialized-chain",
        "joint-acceptance-checklist-seven-items",
    } <= evidence
    assert not any("acceptance-pass" in item or "batch-pass" in item for item in evidence)


LEGACY_TASK_PROFILES = {
    LEGACY_008B_TASK: PROFILE,
    # The 009 asset has no CQ selector, so it keeps the three-role profile.
    LEGACY_009_TASK: REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml",
}


@pytest.mark.parametrize(
    ("task_path", "profile_path"),
    sorted(LEGACY_TASK_PROFILES.items(), key=lambda item: str(item[0])),
)
def test_t_g1_2_legacy_real_tasks_unchanged_and_loadable(
    task_path: Path, profile_path: Path
) -> None:
    import hashlib

    digest = hashlib.sha256(task_path.read_bytes()).hexdigest()
    assert digest == FROZEN_ASSET_SHA256[task_path], (
        f"{task_path.name} drifted from the frozen asset"
    )
    configuration = load_multi_slice_team_configuration(profile_path, task_path)
    assert configuration.task.task_id == task_path.stem


def test_t_g1_3_slot_contract_text_matches_validator_dispatch() -> None:
    text = MODELING_INSTRUCTIONS.read_text(encoding="utf-8")
    # The staged sentence dispatches on the mounted contract instead of
    # hard-coding the 008B deferred form.
    assert "deferred_contract: R3.0-009" in text
    assert "candidate_contract: r3-0-009-unified-graph/v1" in text
    assert "unified_semantic_graph: true" in text
    assert "materialization-plans" in text
    # The 008B-only slot form is exactly what the non-unified validator wants.
    assert validate_stage3_slot(_slot(unified=False)) == ()
    assert validate_stage3_slot(_slot(unified=False), unified=True) != ()
    # The 008B+009 slot form is exactly what the unified validator wants, and
    # the deferred form is not an accepted unified contract value.
    assert validate_stage3_slot(_slot(unified=True), unified=True) == ()
    assert validate_stage3_slot(_slot(unified=False), unified=True) != ()
    # The full real Task objective never reinstates a deferred_contract path.
    configuration = load_multi_slice_team_configuration(PROFILE, FULL_TASK)
    assert "deferred_contract" not in configuration.task.objective
    assert "candidate_contract r3-0-009-unified-graph/v1" in configuration.task.objective
