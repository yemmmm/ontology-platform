"""Host-authoritative planned identity closes the existing first L3 Batch path."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from modeling_team.staged_decisions import (
    build_identity_binding,
    unified_identity_issue,
    validate_staged_submission,
)
from modeling_team.tests.test_r30008b_staged_decisions import (
    _confirmed_entry,
    _conclusions,
    _envelope,
    _materialize_unlock,
    _trace,
)


@pytest.fixture()
def combined_stage():
    registry = ModelingCommandHandlerRegistry(Settings())
    entity = {"entity_id": "explicit-l3-probe", "label": "Neutral syntax probe"}
    args = dict(
        batch_id="probe-batch",
        ontology_id="probe-ontology",
        client_item_id="l3-create",
        command_kind="create_entity",
    )
    intended = registry.outputs_for(**args, payload=entity)
    enum = {
        "name": "Neutral syntax probe",
        "property_iri": "https://example.test/prop/placeholder-status",
        "enum_value": "placeholder-alpha",
        "business_meaning": "Neutral syntax probe",
        "schema_source": "probe-schema",
        "semantic_value": intended["resource_iri"],
    }
    items = [
        dict(
            client_item_id="l3-create",
            command_kind="create_entity",
            payload=entity,
            depends_on=[],
            rationale=None,
            competency_question_ids=[],
        ),
        dict(
            client_item_id="enum-create",
            command_kind="create_enum_meaning",
            payload=enum,
            depends_on=["l3-create"],
            rationale=None,
            competency_question_ids=[],
        ),
    ]
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope(items),
        "value_traces": [_trace(command_index=1)],
        "l3_nodes": [
            {
                "command_index": 0,
                "entity_id": entity["entity_id"],
                "semantic_value_iri": intended["resource_iri"],
            }
        ],
    }
    conclusions = _conclusions([_confirmed_entry(confirmed_level="L3", proposed_level="L3")])
    unlock = _materialize_unlock()
    unlock["confirmed_codes"][0]["confirmed_level"] = "L3"
    return registry, args, intended, payload, conclusions, unlock


def issues(payload, conclusions, unlock):
    return validate_staged_submission(
        payload, gate_open=True, conclusions=conclusions, unlock=unlock, unified=True
    )


def test_combined_stage_compiles_and_keeps_future_identity_binding(combined_stage):
    registry, args, intended, payload, conclusions, unlock = combined_stage
    assert (
        registry.outputs_for(
            **{**args, "batch_id": "another-internal-id", "client_item_id": "another-item"},
            payload=payload["batch"]["items"][0]["payload"],
        )
        == intended
    )
    assert issues(payload, conclusions, unlock) == ()
    for item in payload["batch"]["items"]:
        actual = registry.prepare(
            **{
                **args,
                "client_item_id": item["client_item_id"],
                "command_kind": item["command_kind"],
            },
            payload=item["payload"],
        )
        assert actual.compiled.delta.inserts
        if item["command_kind"] == "create_entity":
            assert actual.outputs == intended
    binding = build_identity_binding(candidate_item_id="neutral-node", receipt_ref="plan/batch/l3")
    projection = {
        "identity_bindings": [binding],
        "items": payload["batch"]["items"],
        "decision_bindings": [{"command_index": 0, "candidate_item_ids": ["neutral-node"]}],
    }
    assert unified_identity_issue(projection, {"neutral-node": {"item_kind": "entity"}}) is None
    assert binding["resource_iri"] is None and binding["evidence_ref"] is None


def test_attachment_iri_mismatch_is_rejected(combined_stage):
    _, _, _, payload, conclusions, unlock = combined_stage
    payload = deepcopy(payload)
    payload["l3_nodes"][0]["semantic_value_iri"] = "https://example.test/wrong-value"
    codes = {i.reason_code for i in issues(payload, conclusions, unlock)}
    assert "staged_l3_unapproved" in codes
    assert "staged_dangling_semantic_value" in codes


@pytest.mark.parametrize("status,level", [("analyzed", "L3"), ("confirmed", "L2")])
def test_intended_identity_does_not_release_unconfirmed_or_non_l3_content(
    combined_stage, status, level
):
    _, _, _, payload, conclusions, unlock = combined_stage
    conclusions = deepcopy(conclusions)
    conclusions["entries"][0].update(status=status, confirmed_level=level)
    assert "staged_l3_unapproved" in {i.reason_code for i in issues(payload, conclusions, unlock)}


def test_mounted_contracts_describe_host_planned_identity_without_new_guard():
    root = Path(__file__).resolve().parents[1] / "references"
    for name in (
        "modeling-batch-item-contract.json",
        "r3-0-009-unified-graph-contract.json",
        "r3-0-008b-staged-decisions-contract.json",
    ):
        value = json.loads((root / name).read_text())
        assert "outputs_for" in json.dumps(value)
        assert "intended" in json.dumps(value)
