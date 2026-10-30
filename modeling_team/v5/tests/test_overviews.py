"""Consumer navigation uses actual reads, survives changes as stale, and keeps views separate."""

import json

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.overviews import read_overview, refresh_overview
from ontoweave_modeling.semantic_workspace import SemanticWorkspace


class Model:
    revision = 3
    allowed = True

    def call(self, action):
        assert action == "snapshot"
        if not self.allowed:
            raise FrameworkError("forbidden")
        return {"model_revisions": {"ontology": self.revision}, "ontology_ids": ["ontology"]}


def reader(model, *, change=False, unknown_iri=False):
    def invoke(root, purpose, prompt, inputs):
        assert purpose == "overview" and inputs == []
        assert "secret-production" not in prompt
        revision = model.revision
        event = {
            "method": "item/completed",
            "params": {
                "item": {
                    "tool": "query_semantic_context",
                    "arguments": {"queries": ["all definitions"]},
                    "status": "completed",
                    "result": {
                        "structuredContent": {
                            "scope": {
                                "ontologies": [
                                    {"ontology_id": "ontology", "model_revision": revision}
                                ]
                            },
                            "resources": [
                                {"iri": "urn:actual:condition", "text": "Only after approval"}
                            ],
                        }
                    },
                }
            },
        }
        (root / "agent").mkdir()
        (root / "agent/events.jsonl").write_text(json.dumps(event))
        if change:
            model.revision += 1
        return {
            "status": "completed",
            "final_response": json.dumps(
                {
                    "summary": "Navigate to approval",
                    "sections": [
                        {
                            "title": "Approval",
                            "body": "Only after approval",
                            "evidence_iris": [
                                "urn:invented" if unknown_iri else "urn:actual:condition"
                            ],
                        }
                    ],
                    "open_items": ["Deadline is not specified"],
                    "limitations": "Current authorized model only",
                    "model_revisions": {"ontology": revision},
                }
            ),
        }

    return invoke


def test_model_only_overview_does_not_consume_inputs_or_expose_production_notes(binding, workspace):
    model = Model()
    SemanticWorkspace(workspace, binding.data).write(
        "secret-production", "decision", "Private candidate", "Never applied"
    )
    TaskControl(workspace).enqueue("human-new-input", "input", "pending clarification")
    result = refresh_overview(
        binding, workspace, model, "business", "Business", invoke=reader(model)
    )
    record = result["record"]
    assert record["view"] == "consumer" and record["authority"] == "model_navigation"
    assert record["freshness"]["state"] == "current"
    assert (
        SemanticWorkspace(workspace, binding.data).read("overview-consumer-business")["state"]
        == "not_found"
    )
    assert TaskControl(workspace).view()["messages"][0]["status"] == "queued"
    model.revision = 4
    stale = read_overview(binding, workspace, model, "business")
    assert stale["freshness"]["state"] == "needs_review" and stale["model_basis"] == {"ontology": 3}
    model.allowed = False
    with pytest.raises(FrameworkError, match="forbidden"):
        read_overview(binding, workspace, model, "business")


def test_change_during_generation_is_saved_with_its_original_basis(binding, workspace):
    model = Model()
    record = refresh_overview(
        binding, workspace, model, "changing", "Topic", invoke=reader(model, change=True)
    )["record"]
    assert record["model_basis"] == {"ontology": 3}
    assert record["freshness"]["state"] == "needs_review"


def test_unread_reference_gets_recoverable_feedback_not_a_valid_summary(binding, workspace):
    model = Model()
    with pytest.raises(FrameworkError, match="overview_needs_correction"):
        refresh_overview(
            binding, workspace, model, "wrong", "Topic", invoke=reader(model, unknown_iri=True)
        )
    assert read_overview(binding, workspace, model, "wrong")["state"] == "not_found"


@pytest.mark.parametrize("unknown_leaf", [False, True])
def test_nested_topics_keep_shared_references_and_validate_leaf_reads(
    binding, workspace, unknown_leaf
):
    model = Model()
    base = reader(model)

    def invoke(*args):
        result = base(*args)
        report = json.loads(result["final_response"])
        shared = "urn:actual:condition"
        report["sections"] = [
            {
                "title": "Operations",
                "body": "Approval conditions",
                "evidence_iris": [shared],
                "children": [
                    {
                        "title": "Repair",
                        "body": "Only after approval",
                        "evidence_iris": [shared],
                        "children": [
                            {
                                "title": "Boundary",
                                "body": "Precise condition",
                                "evidence_iris": ["urn:invented" if unknown_leaf else shared],
                            }
                        ],
                    },
                    {
                        "title": "Installation",
                        "body": "Same shared approval definition",
                        "evidence_iris": [shared],
                    },
                ],
            }
        ]
        result["final_response"] = json.dumps(report)
        return result

    if unknown_leaf:
        with pytest.raises(FrameworkError, match="overview_needs_correction") as error:
            refresh_overview(binding, workspace, model, "nested", "Operations", invoke=invoke)
        assert error.value.detail["detail"] == "overview_reference_not_read"
        assert read_overview(binding, workspace, model, "nested")["state"] == "not_found"
    else:
        result = refresh_overview(binding, workspace, model, "nested", "Operations", invoke=invoke)
        report = json.loads(result["record"]["body"])
        children = report["sections"][0]["children"]
        assert children[0]["children"][0]["evidence_iris"] == children[1]["evidence_iris"]
        model.revision += 1
        assert (
            read_overview(binding, workspace, model, "nested")["freshness"]["state"]
            == "needs_review"
        )
