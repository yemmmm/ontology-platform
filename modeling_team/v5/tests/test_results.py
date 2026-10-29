import json

import pytest

from ontoweave_modeling.results import (
    ResultContractError,
    decode_json_result,
    validate_evaluation_binding,
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"references": {"type": "array", "items": {"type": "string"}}},
    "required": ["references"],
}


@pytest.mark.parametrize(
    "indices,revision,verdict,passed",
    [
        ([], 2, "PASS", True),
        ([1], 2, "PASS", True),
        ([1, 1], 2, "PASS", True),
        ([1, 2], 999, "PASS", True),
        ([1, 2], 2, "PASS", False),
    ],
)
def test_evaluation_binding_rejects_incomplete_or_wrong_target(indices, revision, verdict, passed):
    report = {
        "verdict": verdict,
        "target_revision": revision,
        "cases": [{"index": index, "passed": passed} for index in indices],
    }
    with pytest.raises(ResultContractError):
        validate_evaluation_binding(report, case_count=2, target_revision=2)


def test_evaluation_binding_preserves_independent_negative_judgment():
    report = {
        "verdict": "REVISE",
        "target_revision": 2,
        "cases": [{"index": 1, "passed": False}, {"index": 2, "passed": True}],
    }
    validate_evaluation_binding(report, case_count=2, target_revision=2)


@pytest.mark.parametrize("wrapper", ["{}", "Read completed.\n\n```json\n{}\n```\n", "Done.\n{}"])
def test_result_decoding_preserves_agent_content(wrapper):
    payload = {"references": ["source:v1", "definition:v3"]}
    assert decode_json_result(wrapper.format(json.dumps(payload)), SCHEMA) == payload


@pytest.mark.parametrize(
    "message",
    [
        "No JSON was returned.",
        '```json\n{"references": []}\n```\n```json\n{"references": ["other"]}\n```\n',
        '```json\n{"references": [}\n```\n',
        '{"references": "source:v1"}',
        '{"references": [4]}',
        '{"references": [], "extra": "unapproved field"}',
        "{}",
        "null",
    ],
)
def test_invalid_results_require_agent_correction(message):
    with pytest.raises(ResultContractError):
        decode_json_result(message, SCHEMA)


def test_only_top_level_values_are_considered_and_identical_repetition_is_not_ambiguous():
    with pytest.raises(ResultContractError):
        decode_json_result('Done. {"wrapper":{"references":[]}}', SCHEMA)
    assert decode_json_result('Done. {"references":[]}\n{"references":[]}', SCHEMA) == {
        "references": []
    }


@pytest.mark.parametrize("message", ["{}", "Result:\n```json\n{}\n```"])
def test_missing_required_field_feedback_names_the_field(message):
    with pytest.raises(ResultContractError, match="references.*required property"):
        decode_json_result(message, SCHEMA)
