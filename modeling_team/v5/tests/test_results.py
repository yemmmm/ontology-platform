import json

import pytest

from ontoweave_modeling.results import ResultContractError, decode_json_result

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"references": {"type": "array", "items": {"type": "string"}}},
    "required": ["references"],
}


@pytest.mark.parametrize("wrapper", ["{}", "Read completed.\n\n```json\n{}\n```\n"])
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
