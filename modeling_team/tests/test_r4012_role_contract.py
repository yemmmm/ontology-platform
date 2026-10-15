"""The active v4 Task must give Modeling a usable, role-visible handoff contract."""

import json
from types import SimpleNamespace

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration, repository_root
from modeling_team.staged_decisions import (
    UNIFIED_STAGE3_SLOT_FIELDS,
    UNIFIED_STAGE3_SLOT_SCHEMA,
    validate_stage3_slot,
)
from modeling_team.runner import TeamRunner


def _configuration():
    root = repository_root()
    return load_multi_slice_team_configuration(
        root / "modeling_team/profiles/r3-0-011-competency-question.yaml",
        root / "modeling_team/tasks/r4-0-012-tracing-suspension.yaml",
    )


def test_active_modeling_contract_is_visible_without_protocol_execution_contracts():
    configuration = _configuration()
    sources = {
        source.path.name: source.path
        for source in configuration.task.role_sources
        if "modeling" in source.roles
    }
    assert "r4-0-012-modeling-contract.json" in sources
    assert "platform-neutral-candidate-authoring.json" in sources
    assert "r4-3-025-direct-modeling-contract.json" in sources
    # Modeling reads the unified candidate and the current batch-field syntax;
    # the legacy staged and acceptance handoff schemas stay protocol-only. The
    # direct contract defines the current apply boundary.
    assert "r3-0-009-unified-graph-contract.json" in sources
    assert {
        "r3-0-008b-staged-decisions-contract.json",
        "acceptance-stage-handoff-contract.json",
    }.isdisjoint(sources)
    assert "modeling-batch-item-contract.json" in sources


def test_visible_slot_contract_can_produce_an_accepted_current_slot():
    configuration = _configuration()
    source = next(
        source
        for source in configuration.task.role_sources
        if source.path.name == "r4-0-012-modeling-contract.json" and "modeling" in source.roles
    )
    contract = json.loads(source.path.read_text(encoding="utf-8"))
    slot_contract = contract["stage3_artifacts"]["stage3_slot"]
    assert configuration.task.parameters["unified_semantic_graph"] is True
    assert slot_contract["schema_version"] == UNIFIED_STAGE3_SLOT_SCHEMA
    assert set(slot_contract["fields"]) == UNIFIED_STAGE3_SLOT_FIELDS
    assert slot_contract["candidate_contract"] == contract["unified_candidate"]["schema_version"]
    slot = {
        "schema_version": slot_contract["schema_version"],
        "scenario_id": "scenario",
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/candidates/candidate-r1.json"],
        "candidate_contract": slot_contract["candidate_contract"],
        "slot_note": None,
    }
    assert validate_stage3_slot(slot, unified=True) == ()
    slot["candidate_contract"] = "r3-0-009-unified-graph/v1"
    assert validate_stage3_slot(slot, unified=True)[0].reason_code == "stage3_schema_mismatch"


def test_loaded_role_instructions_name_current_visible_contracts():
    configuration = _configuration()
    packages = {agent.agent_id: agent.package for agent in configuration.profile.agents}
    modeling = packages["modeling"].instructions_path.read_text(encoding="utf-8")
    staged = modeling.split("## Staged modeling decisions", 1)[1]
    assert "modeling_team/references/r4-0-012-modeling-contract.json" in staged
    assert "r3-0-008b-staged-decisions-contract.json" not in staged
    assert "r3-0-009-unified-graph-contract.json" not in staged
    assert "unified_semantic_graph: true" in staged
    assert "candidate_contract: r3-0-009-unified-graph/v2" in staged
    for role in ("modeling", "protocol"):
        instructions = packages[role].instructions_path.read_text(encoding="utf-8")
        assert "r3-0-009-unified-graph/v1" not in instructions


@pytest.mark.parametrize("role", ["coordinator", "modeling", "protocol", "competency-question"])
def test_actual_v4_task_text_keeps_authorized_reads_without_tracing_obligation(role):
    configuration = _configuration()
    runner = TeamRunner(repository_root=repository_root(), adapter=SimpleNamespace())
    runner.run = SimpleNamespace(
        configuration=configuration, protocol_context=None, gate_binding=None
    )
    runner._competency_questions = True
    text = runner._task_text(role)
    assert "full evidence obligation" not in text
    assert "authorization checks, and read/write validation" in text
    assert "Complete that initial read of every staged source in full" in text
    assert "compaction lost them or the relevant content is missing, stale, changed, or truncated" in text
    for source in configuration.task.role_sources:
        mounted_path = f"/agent/home/sources/{source.relative_path.as_posix()}"
        assert (mounted_path in text) == (role in source.roles)
