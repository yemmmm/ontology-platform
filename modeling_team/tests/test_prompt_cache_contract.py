"""Prompt-cache contract for schema-v2 Team task prompts (R3.0-002/006).

Two prompt-level properties are under contract here:

1. The varying ``task.objective`` is a single trailing ``Task objective:``
   section on every schema-v2 return branch, so a production role's static
   role/collaboration instruction prefix stays byte-identical when only the
   objective changes.  Schema-v1 text stays byte-identical to the legacy shape.
2. The shared production read instruction keeps its mandatory initial complete
   read and adds within-thread reuse guidance, while Acceptance keeps its
   isolated no-source-reading branch.

The prompts are built through the real ``TeamRunner._task_text`` entry point
over the shipped Task/Profile fixtures; nothing here re-implements it.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from modeling_team.contracts import (
    load_formal_team_configuration,
    load_task,
    load_team_configuration,
    repository_root,
)
from modeling_team.runner import TeamRunner

ROOT = repository_root()
V2_PROFILE = ROOT / "modeling_team/profiles/base-three-agent.yaml"
V2_TASK = ROOT / "modeling_team/tasks/new-scope-business-slice.yaml"
FORMAL_PROFILE = ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
FORMAL_TASK = ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"
V1_TASK = ROOT / "modeling_team/tasks/base-capability-smoke.yaml"

OBJECTIVE_SUFFIX = "\n\nTask objective:\n"
PRODUCTION_ROLES = ("coordinator", "modeling", "protocol", "competency-question")
SOURCE_PREFIX = "/agent/home/sources/"
PROTOCOL_CONTEXT = {
    "project_id": "project-1",
    "ontology_id": "ontology-1",
    "workspace_version": "v1",
}

# One spec per schema-v2 return branch: acceptance, coordinator, modeling,
# protocol (with and without the mechanical scope context), the R3.0-011
# competency-question branch, and the generic fall-through.
V2_BRANCHES = (
    ("acceptance", "acceptance", {}),
    ("coordinator", "coordinator", {}),
    ("modeling", "modeling", {}),
    (
        "protocol-with-scope-context",
        "protocol",
        {"protocol_context": PROTOCOL_CONTEXT},
    ),
    ("protocol-without-scope-context", "protocol", {"protocol_context": None}),
    ("competency-question", "competency-question", {"competency_questions": True}),
    ("generic", "observability", {}),
)

# Objectives whose first character (and encoding class) differs, so a prompt
# that still hoists or rewrites the objective is caught immediately.
DISTINCT_OBJECTIVES = (
    "'ZZZ-LEAD' objective variant one with an ending marker",
    "Ω目标 variant two, non-ASCII lead, with a different ending marker",
)

READ_REUSE_PHRASES = (
    "Before requesting any teammate work or reporting a terminal result, read every staged",
    "Complete that initial read of every staged source in full",
    "reuse the already-read unchanged material and its exact locators",
    "printing or re-reading a full file again on every teammate turn",
    "authorized sources and authorized teammate handoffs",
    "never access another role's private sources, inherit another run's conversation, "
    "or use hidden material",
    "compaction lost them or the relevant content is missing, stale, changed, or truncated",
    "never skips a task-required live workspace read, a refresh, a validation, "
    "or a full evidence obligation",
)


def _with_objective(configuration, objective: str):
    task = dataclasses.replace(configuration.task, objective=objective)
    return dataclasses.replace(configuration, task=task)


def _v2_configuration(*, objective: str | None = None):
    configuration = load_team_configuration(V2_PROFILE, V2_TASK, root=ROOT)
    return configuration if objective is None else _with_objective(configuration, objective)


def _formal_configuration(*, objective: str | None = None):
    configuration = load_formal_team_configuration(FORMAL_PROFILE, FORMAL_TASK, root=ROOT)
    return configuration if objective is None else _with_objective(configuration, objective)


def _text_for(
    configuration,
    role: str,
    *,
    protocol_context=None,
    competency_questions: bool = False,
) -> str:
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(
        configuration=configuration,
        protocol_context=protocol_context,
        gate_binding=None,
    )
    runner._competency_questions = competency_questions
    return runner._task_text(role)


def _expected_role_sources(configuration, role: str) -> list[str]:
    return sorted(
        f"{SOURCE_PREFIX}{source.relative_path.as_posix()}"
        for source in configuration.task.role_sources
        if role in source.roles
    )


def _split_prefix(text: str, objective: str) -> str:
    """Return everything before the trailing objective section, asserting it is last."""

    suffix = OBJECTIVE_SUFFIX + objective
    assert text.endswith(suffix), "objective section must be the final section"
    return text[: -len(suffix)]


@pytest.mark.parametrize("label,role,kwargs", V2_BRANCHES, ids=[item[0] for item in V2_BRANCHES])
def test_every_v2_return_branch_ends_with_one_objective_section(label, role, kwargs) -> None:
    configuration = _v2_configuration()
    objective = configuration.task.objective
    text = _text_for(configuration, role, **kwargs)

    assert text.endswith(OBJECTIVE_SUFFIX + objective), label
    assert text.count(OBJECTIVE_SUFFIX) == 1, label
    assert text.count(objective) == 1, label


@pytest.mark.parametrize("label,role,kwargs", V2_BRANCHES, ids=[item[0] for item in V2_BRANCHES])
def test_v2_static_prefix_is_identical_across_distinct_objectives(label, role, kwargs) -> None:
    baseline = _v2_configuration()
    baseline_prefix = _split_prefix(
        _text_for(baseline, role, **kwargs), baseline.task.objective
    )

    prefixes = []
    for objective in DISTINCT_OBJECTIVES:
        text = _text_for(_v2_configuration(objective=objective), role, **kwargs)
        assert text.count(objective) == 1, label
        prefixes.append(_split_prefix(text, objective))

    assert prefixes[0] == prefixes[1] == baseline_prefix, label


@pytest.mark.parametrize("objective", DISTINCT_OBJECTIVES)
def test_v2_objective_is_unmodified_and_never_hoisted_to_the_front(objective: str) -> None:
    configuration = _v2_configuration(objective=objective)
    for label, role, kwargs in V2_BRANCHES:
        text = _text_for(configuration, role, **kwargs)
        prefix = _split_prefix(text, objective)
        assert objective not in prefix, label
        assert not text.startswith(objective), label
        assert text.count(objective) == 1, label


def test_coordinator_and_modeling_role_instructions_precede_the_objective() -> None:
    configuration = _v2_configuration()
    objective = configuration.task.objective

    coordinator = _split_prefix(_text_for(configuration, "coordinator"), objective)
    for phrase in (
        "dependency rejection is not recorded",
        "reply_to_delivery_id set to the current Modeling question delivery_id",
        "exactly once before ending",
    ):
        assert phrase in coordinator, phrase

    modeling = _split_prefix(_text_for(configuration, "modeling"), objective)
    for phrase in (
        "Emit only ready_for_acceptance",
        "expects_reply=true",
        "only blocked, never completed",
    ):
        assert phrase in modeling, phrase


def test_protocol_scope_context_stays_before_the_trailing_objective() -> None:
    configuration = _v2_configuration()
    objective = configuration.task.objective
    text = _text_for(
        configuration,
        "protocol",
        protocol_context=PROTOCOL_CONTEXT,
    )

    assert '"workspace_version": "v1"' in text
    assert text.index("Mechanical platform scope") < text.index(OBJECTIVE_SUFFIX)
    assert text.endswith(OBJECTIVE_SUFFIX + objective)


def test_formal_acceptance_branch_carries_the_objective_and_stays_source_isolated() -> None:
    configuration = _formal_configuration()
    objective = configuration.task.objective
    text = _text_for(configuration, "acceptance")

    assert text.endswith(OBJECTIVE_SUFFIX + objective)
    assert text.count(objective) == 1
    assert "Do not read staged source paths" in text
    assert "non-final cq-001 PASS" in text
    assert SOURCE_PREFIX not in text


@pytest.mark.parametrize("role", PRODUCTION_ROLES)
def test_production_roles_keep_the_initial_read_and_add_reuse_guidance(role: str) -> None:
    configuration = _v2_configuration()
    text = _text_for(configuration, role, competency_questions=role == "competency-question")

    for phrase in READ_REUSE_PHRASES:
        assert phrase in text, phrase

    expected = _expected_role_sources(configuration, role)
    # The competency-question role learns its slice set from the Runner's
    # delivery and legitimately stages no business source; the three
    # source-reading production roles must still enumerate their own.
    if role != "competency-question":
        assert expected, role
    for path in expected:
        assert text.count(path) == 1, path
    for source in configuration.task.role_sources:
        marker = f"{SOURCE_PREFIX}{source.relative_path.as_posix()}"
        if marker not in expected:
            assert marker not in text, marker


def test_production_read_instruction_excludes_other_runs_and_hidden_material() -> None:
    configuration = _v2_configuration()
    for role in PRODUCTION_ROLES:
        text = _text_for(configuration, role, competency_questions=role == "competency-question")
        assert "Read only these role-private sources." in text, role
        assert "another run's conversation" in text, role
        assert "hidden material" in text, role


def test_acceptance_branch_never_receives_the_production_read_instruction() -> None:
    for configuration in (_v2_configuration(), _formal_configuration()):
        text = _text_for(configuration, "acceptance")
        for phrase in READ_REUSE_PHRASES:
            assert phrase not in text, phrase
        assert "Do not read staged source paths" in text
        assert SOURCE_PREFIX not in text


def test_v1_task_text_stays_byte_identical_and_gets_no_objective_suffix() -> None:
    task = load_task(V1_TASK, root=ROOT)
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(
        configuration=SimpleNamespace(task=task),
        protocol_context=None,
        gate_binding=None,
    )
    text = runner._task_text("modeling")

    expected = (
        task.objective
        + "\nAllowed sources: "
        + ", ".join(f"{SOURCE_PREFIX}{path.name}" for path in task.allowed_sources)
        + "\nUse Team Transport for direct messages and call report_task_result exactly once "
        "before ending. "
        + "Protocol must call check_platform_health once; do not call another platform tool."
    )
    assert text == expected
    assert OBJECTIVE_SUFFIX not in text
    for phrase in READ_REUSE_PHRASES:
        assert phrase not in text
