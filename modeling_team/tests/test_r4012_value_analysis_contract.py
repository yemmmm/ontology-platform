"""Mounted value-analysis syntax is usable without guessing platform identities."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from modeling_team.staged_decisions import VALUE_LEVELS, validate_analysis_conclusions


REFERENCES = Path(__file__).resolve().parents[1] / "references"


def contract():
    return json.loads((REFERENCES / "r4-0-012-modeling-contract.json").read_text())["value_conclusions"]


def test_mounted_analysis_example_and_closed_fields():
    value = contract()
    example = value["syntax_example"]
    assert set(example) == set(value["fields"])
    assert set(example["entries"][0]) == set(value["entry_fields"])
    assert set(value["value_levels"]) == set(VALUE_LEVELS)
    assert validate_analysis_conclusions(example) == ()
    neutral = json.loads((REFERENCES / "platform-neutral-candidate-authoring.json").read_text())
    assert "r4-0-012-modeling-contract.json" in neutral["semantic_handoff"]["value_analysis_boundary"][0]


@pytest.mark.parametrize("level", VALUE_LEVELS)
def test_value_expression_levels_are_accepted_with_neutral_analysis_urn(level):
    example = deepcopy(contract()["syntax_example"])
    example["entries"][0]["proposed_level"] = level
    assert validate_analysis_conclusions(example) == ()


@pytest.mark.parametrize(
    "field,invalid",
    [("proposed_level", "reference_value"), ("mapped_property", "neutral-property-key")],
)
def test_original_failure_fields_can_be_corrected_without_confirmation(field, invalid):
    example = contract()["syntax_example"]
    broken = deepcopy(example)
    broken["entries"][0][field] = invalid
    assert any(field in i.detail for i in validate_analysis_conclusions(broken))
    broken["entries"][0][field] = example["entries"][0][field]
    assert validate_analysis_conclusions(broken) == ()
    assert broken["entries"][0]["status"] == "analyzed"
    assert broken["entries"][0]["confirmed_by"] is None
