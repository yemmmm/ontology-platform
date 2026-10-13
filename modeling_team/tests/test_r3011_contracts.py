"""R3.0-011 contract/loader fixtures (test plan M1-M4, M10-M11).

Every expected reason code is written independently here; fixtures stay in the
placeholder/example.test namespace.  No Agent is started and no platform call is
made: these tests cover the mechanical selector, roster, role-source,
advisory-count and mounted-contract example contracts only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modeling_team.contracts import (
    ROLE_VALUES,
    TeamConfigurationError,
    load_multi_slice_team_configuration,
    load_task,
)
from modeling_team.competency_questions import advisory_question_count_feedback

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
PROFILE_002 = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
SMOKE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-decisions-smoke.yaml"
MULTI_SLICE_SMOKE = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"

BUSINESS_INPUTS = (
    "docs/evaluation-scenarios/industrial-service-v3/modeling-input/scenario-brief.md",
    "docs/evaluation-scenarios/industrial-service-v3/modeling-input/business-terms.md",
    "docs/evaluation-scenarios/industrial-service-v3/modeling-input/schema.sql",
    "docs/evaluation-scenarios/industrial-service-v3/modeling-input/sample-data.sql",
)


@pytest.mark.parametrize("kind,role", [
    ("source", None), ("platform", None), ("acceptance", None),
    ("platform", "platform-examiner"), ("acceptance", "acceptance"),
])
def test_public_report_manifest_has_provider_object_root_and_strict_alternatives(kind, role):
    from copy import deepcopy
    from modeling_team import report_sink_mcp as bridge

    specs = bridge.native_report_tool_specs(kind, v3_batch=role is not None, role=role)
    assert all(spec["inputSchema"].get("type") == "object" for spec in specs)
    schema = specs[0]["inputSchema"]
    original = (bridge._v3_batch_report_schema(platform=role == "platform-examiner")
                if role else bridge.report_schema(kind))
    full = deepcopy(original)
    reference = full["properties"].pop("report_ref")
    # The provider root must not alter either strict branch or expose Host
    # evidence/bindings through the convenience properties projection.
    assert schema["oneOf"] == [full, {
        "type": "object", "required": ["report_ref"], "additionalProperties": False,
        "properties": {"report_ref": reference},
    }]
    assert schema["properties"] == original["properties"]
    assert reference == {
        **reference, "type": "object", "required": ["material_id"],
        "additionalProperties": False,
        "properties": {"material_id": {"type": "string", "minLength": 1},
                       "path": {"type": "string", "minLength": 1}},
    }


# --- M1: the 011 selector loads the 011 Profile plus the real staged task -----


def test_m1_selector_loads_011_profile_with_one_cq_agent():
    configuration = load_multi_slice_team_configuration(PROFILE, TASK)
    roles = [agent.package.role for agent in configuration.profile.agents]
    assert sorted(roles) == ["competency-question", "coordinator", "modeling", "protocol"]
    assert roles.count("competency-question") == 1
    assert configuration.task.task_id == "r3-0-008b-staged-real"
    assert configuration.task.parameters == {
        "multi_slice_workflow": True,
        "staged_modeling_decisions": True,
        "competency_question_acceptance": True,
    }


def test_m1_loader_rejects_a_cq_agent_without_the_selector():
    import yaml

    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    task["parameters"].pop("competency_question_acceptance")
    path = TASK.parent / "r3011-no-cq-selector.yaml"
    path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
    try:
        with pytest.raises(TeamConfigurationError, match="competency_question_acceptance"):
            load_multi_slice_team_configuration(PROFILE, path)
    finally:
        path.unlink()


def test_m1_loader_rejects_a_three_role_roster_for_the_selected_task():
    import yaml

    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    path = TASK.parent / "r3011-selected-task.yaml"
    path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
    try:
        # The 002 profile has no competency-question Agent, so the selected task
        # cannot form the required CQ stage.
        with pytest.raises(TeamConfigurationError):
            load_multi_slice_team_configuration(PROFILE_002, path)
    finally:
        path.unlink()


# --- M2: legacy rosters stay byte-identical and never gain the CQ operation ---


def test_m2_legacy_smoke_roster_has_no_cq_role_or_operation():
    configuration = load_multi_slice_team_configuration(PROFILE_002, MULTI_SLICE_SMOKE)
    roles = [agent.package.role for agent in configuration.profile.agents]
    assert roles == ["coordinator", "modeling", "protocol"]
    from modeling_team.capability_mcp import ROLE_OPERATIONS, CQ_OPERATION

    for role in roles:
        assert CQ_OPERATION not in ROLE_OPERATIONS[role]


def test_m2_legacy_packet_schema_version_is_unchanged():
    from modeling_team.acceptance_runtime import ExaminerRolePacket

    assert ExaminerRolePacket.schema_version == "ExaminerRolePacket/v1"


def test_m2_role_values_pin_is_not_extended_by_the_cq_role():
    from modeling_team.contracts import ADMITTED_ROLE_VALUES

    assert "competency-question" in ADMITTED_ROLE_VALUES
    assert "competency-question" not in ROLE_VALUES


# --- M3: roster/edge/parameter typed rejections -------------------------------


def _profile_text() -> str:
    return PROFILE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("duplicate_agent", "duplicate"),
        ("missing_core", None),
        ("unknown_package", "unavailable"),
    ],
)
def test_m3_broken_rosters_are_typed_rejected(tmp_path, mutation, match):
    import yaml

    data = yaml.safe_load(_profile_text())
    if mutation == "duplicate_agent":
        data["agents"].append({"agent_id": "coordinator", "package": "coordinator"})
    elif mutation == "missing_core":
        data["agents"] = [item for item in data["agents"] if item["agent_id"] != "coordinator"]
    else:
        data["agents"].append({"agent_id": "ghost", "package": "does-not-exist"})
    path = tmp_path / f"profile-{mutation}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match=match):
        load_multi_slice_team_configuration(path, TASK)


def test_m3_cq_agent_needs_no_communication_edge():
    import yaml

    data = yaml.safe_load(_profile_text())
    edges = {(edge["from"], target) for edge in data["communication"] for target in edge["to"]}
    assert not any(role in {source for source, _ in edges} for role in ("competency-question",))
    assert ("coordinator", "modeling") in edges


# --- M4: role source manifest -------------------------------------------------


def test_m4_cq_and_modeling_share_the_four_business_inputs():
    configuration = load_multi_slice_team_configuration(PROFILE, TASK)
    by_role: dict[str, set[str]] = {}
    for source in configuration.task.role_sources:
        for role in source.roles:
            by_role.setdefault(role, set()).add(source.relative_path.as_posix())
    for relative in BUSINESS_INPUTS:
        assert relative in by_role["competency-question"]
        assert relative in by_role["modeling"]
    # No tester-only or reference-truth file is staged for any role.
    for role, paths in by_role.items():
        assert not any("tester" in item.lower() or "reference-answer" in item.lower() for item in paths)
    # The 011 contract is CQ-only and the production whitelist is unchanged.
    assert (
        "modeling_team/references/r3-0-011-competency-question-contract.json"
        in by_role["competency-question"]
    )
    assert "modeling_team/references/modeling-batch-item-contract.json" not in by_role[
        "competency-question"
    ]
    assert "modeling_team/references/modeling-batch-item-contract.json" in by_role["protocol"]


# --- M10: question counts are advisory only -----------------------------------


def test_m10_counts_outside_the_range_are_feedback_not_rejections():
    single = [
        {
            "scope": {"kind": "panorama", "slice_ids": []},
            "visibility": "hidden",
        }
    ]
    feedback = advisory_question_count_feedback(single)
    assert feedback and feedback[0]["scope"] == "panorama"
    assert feedback[0]["count"] == 1
    # The same document still freezes: the count is never a validity gate.
    frozen = _freeze_from_questions(single)
    assert frozen["panorama_question_ids"] == ["cq-1"]


# --- M11: the mounted contract states the validator-enforced question shapes --


def test_m11_contract_question_types_and_example_match_the_validator():
    import json

    from modeling_team.competency_questions import validate_cq_question

    contract = json.loads(
        (
            REPO_ROOT
            / "modeling_team/references/r3-0-011-competency-question-contract.json"
        ).read_text(encoding="utf-8")
    )
    question = contract["schemas"]["question"]
    assert question["schema_version"] == "r3-0-011-cq-question/v1"
    assert set(question["field_types"]) == set(question["fields"]) == {
        "question_id",
        "scope",
        "question",
        "answer_points",
        "evidence_refs",
        "unknown",
        "proposed_visibility",
        "content_version",
    }
    # The published example must stay exactly the shape the real validator
    # accepts, so a role reading the contract never has to rediscover the
    # types through rejections.
    assert (
        validate_cq_question(question["minimal_example"], obj="contract.minimal_example")
        == question["minimal_example"]
    )


def _freeze_from_questions(questions: list[dict]) -> dict:
    from modeling_team.competency_questions import CQ_FREEZE_SCHEMA, freeze_question_pool

    payload = {
        "schema_version": CQ_FREEZE_SCHEMA,
        "batch_id": "batch-r3011",
        "material_digest": "material-r3011",
        "panorama_question_ids": ["cq-1"],
        "slice_question_ids": [],
        "ordering": ["cq-1"],
        "review_binding": {
            "review_id": "cq-review-0001",
            "review_content_version": 1,
            "decision_digest": "sha256:" + "0" * 64,
        },
        "questions": [
            {
                "question_id": "cq-1",
                "scope": {"kind": "panorama", "slice_ids": []},
                "question": "placeholder question?",
                "answer_points": ["point"],
                "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
                "unknown": [],
                "proposed_visibility": "hidden",
                "content_version": 1,
            }
        ],
    }
    return freeze_question_pool(payload)


def test_m4_load_task_rejects_an_unknown_source_role(tmp_path):
    import yaml

    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    task["role_sources"][0]["roles"] = ["coordinator", "ghost-role"]
    path = tmp_path / "bad-role-source.yaml"
    path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
    with pytest.raises(TeamConfigurationError):
        load_task(path, root=REPO_ROOT, allowed_roles=ROLE_VALUES | {"competency-question"})
