from unittest.mock import MagicMock, patch

from app.repositories.models import (
    ClassModel,
    FactClaimModel,
    OntologyModel,
    OntologyVersionModel,
    PropertyDefModel,
    UnanchoredKnowledgeModel,
)
from app.services import facts


def _claim(**overrides) -> FactClaimModel:
    values = {
        "id": "claim",
        "claim_key": "claim-key",
        "project_id": "project",
        "ontology_id": "ontology",
        "ontology_version_id": "version",
        "claim_type": "direct",
        "layer": "entity_assertion",
        "subject": {"entity_id": "entity"},
        "predicate": "predicate",
        "value": "value",
        "anchor": {"type": "entity", "target_id": "entity"},
        "graph_path": [],
        "evidence_ids": [],
        "generation_reason": "direct_user_statement",
        "confidence": 1.0,
        "audit_status": "approved",
    }
    values.update(overrides)
    return FactClaimModel(**values)


def test_v05_minimal_acceptance_rule_class_override_and_background_recall() -> None:
    """v0.5 minimum: rules derive Assertions, class defaults can be overridden, background stays separate."""

    session = MagicMock()
    version = OntologyVersionModel(id="version", ontology_id="ontology", version_number=1, status="draft")
    ontology = OntologyModel(id="ontology", project_id="project", name="Campus")
    student_class = ClassModel(
        id="Student", ontology_id="ontology", name="Student", normalized_label="student"
    )
    average_score = PropertyDefModel(
        id="average_score", class_id="Student", name="average_score", type="number"
    )
    student_status = PropertyDefModel(
        id="student_status", class_id="Student", name="student_status",
        type="string", enum_values=["excellent", "normal"],
    )
    session.get.side_effect = lambda model, _id: {
        OntologyVersionModel: version,
        OntologyModel: ontology,
        ClassModel: student_class,
    }.get(model)
    session.scalars.return_value = [average_score, student_status]

    rule = facts.create_rule_definition(
        session,
        "version",
        {
            "rule_type": "classification",
            "scope": {"class": "Student"},
            "condition": {">": [{"property": "average_score"}, 90]},
            "conclusion": {"assert": {"predicate": "student_status", "value": "excellent"}},
            "evidence_ids": ["evidence-rule"],
        },
    )
    rule.id = "rule-excellent"

    session.add.reset_mock()
    session.commit.reset_mock()
    session.refresh.reset_mock()
    session.scalars.side_effect = [[rule], []]
    graph = {
        "entities": [
            {
                "id": "student-1", "class_id": "Student", "name": "小明",
                "properties": {"average_score": 93}, "ontology_version_id": "version",
            }
        ],
        "relations": [],
    }
    with patch.object(facts, "_graph_snapshot", return_value=graph):
        derived = facts.execute_rule_definitions(session, MagicMock(), "version")

    assert derived[0].claim_type == "derived"
    assert derived[0].predicate == "student_status"
    assert derived[0].value == "excellent"
    assert derived[0].generation_reason == "rule:rule-excellent"

    class_default = _claim(
        id="class-close", claim_key="class-close", layer="class_assertion",
        subject={"class_id": "TeachingBuilding"}, predicate="closes_at", value="23:00",
        anchor={"type": "class", "target_id": "TeachingBuilding", "scope": "default_for_instances"},
    )
    override = _claim(
        id="lab-close", claim_key="lab-close", layer="entity_assertion",
        subject={"entity_id": "building-1"}, predicate="closes_at", value="22:30",
        anchor={"type": "entity", "target_id": "building-1"},
        override_of_claim_id="class-close",
    )
    background = UnanchoredKnowledgeModel(
        id="background-sleep",
        project_id="project",
        ontology_id="ontology",
        ontology_version_id="version",
        text="8 小时睡眠能保证上课状态",
        source={"source_type": "conversation"},
        summary="Sleep can affect class readiness.",
        embedding=[1.0, 0.0],
        tags=["sleep"],
        confidence=0.5,
        applicability="background only",
    )
    session.scalars.side_effect = [[class_default, override, derived[0]], [background]]

    recalled = facts.recall_entity_knowledge(
        session,
        "version",
        {
            "id": "building-1",
            "class_id": "TeachingBuilding",
            "parent_class_ids": [],
            "properties": {"name": "实验教学楼"},
        },
        background_query="sleep",
    )

    assert any(item["source_type"] == "entity_property" for item in recalled)
    assert any(item.get("claim_id") == "lab-close" and item["value"] == "22:30" for item in recalled)
    assert any(item.get("claim_id") == "class-close" and item.get("overridden") for item in recalled)
    background_hits = [item for item in recalled if item["source_type"] == "background_recall"]
    assert background_hits[0]["core_fact"] is False
    assert background_hits[0]["text"] == "8 小时睡眠能保证上课状态"
