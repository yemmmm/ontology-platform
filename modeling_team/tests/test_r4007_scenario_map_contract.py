"""The mounted multiview contract alone supplies inherited artifact syntax."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from modeling_team.scenario_map import load_scenario_map, validate_scenario_map


CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "references/r4-0-007-scenario-map-contract.json"
)


def test_mounted_syntax_example_loads_and_validates(tmp_path):
    contract = json.loads(CONTRACT.read_text())["scenario_map"]
    example = contract["syntax_example"]
    assert set(example) == {"schema_version", *contract["identity_fields"],
                            *contract["required_sections"]}
    assert all(set(s) == set(contract["slices_item_fields"]) for s in example["slices"])
    artifact = tmp_path / "scenario-map.json"
    artifact.write_text(json.dumps(example))
    assert validate_scenario_map(load_scenario_map(artifact)) == ()


@pytest.mark.parametrize(
    "section,fields",
    [
        ("cross_slice_dependencies", {"from_slice", "to_slice", "direction", "connection_points"}),
        ("cross_slice_competency_questions", {"question_id", "question", "spans_slices"}),
        ("explicit_unknowns", {"topic", "needed_from", "status"}),
    ],
)
def test_inherited_shapes_are_explicit_and_fixable(section, fields):
    contract = json.loads(CONTRACT.read_text())["scenario_map"]
    assert set(contract[section]["fields"]) == fields
    example = contract["syntax_example"]
    assert set(example[section][0]) == fields
    for field in fields:
        broken = deepcopy(example)
        del broken[section][0][field]
        assert any(i.reason_code == "map_schema_mismatch" for i in validate_scenario_map(broken))
        broken[section][0][field] = example[section][0][field]
        assert validate_scenario_map(broken) == ()
    empty = deepcopy(example)
    empty[section] = []
    assert validate_scenario_map(empty) == ()


@pytest.mark.parametrize("state", ["pending", "modeled", "unknown", "not_applicable"])
def test_progress_notes_preserve_four_states_and_closed_shape(state):
    contract = json.loads(CONTRACT.read_text())["scenario_map"]
    viewpoints = contract["viewpoints"]
    assert set(viewpoints["status_meanings"]) == set(viewpoints["status"])
    assert viewpoints["fields"] == ["viewpoint", "status", "note"]
    example = deepcopy(contract["syntax_example"])
    entry = deepcopy(viewpoints["note_example"])
    entry["status"] = state
    example["slices"][0]["viewpoints"] = [entry]
    assert validate_scenario_map(example) == ()
    # Ordinary staleness and incomplete progress remain role feedback, not a hard gate.
    entry["note"] = "Old candidate location; not yet checked after emergency save."
    assert validate_scenario_map(example) == ()
    entry["candidate_refs"] = []
    assert any(i.reason_code == "map_schema_mismatch" for i in validate_scenario_map(example))
