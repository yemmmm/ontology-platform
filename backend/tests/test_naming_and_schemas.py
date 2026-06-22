import pytest
from pydantic import ValidationError

from app.api.schemas import AgentTestRequest, EntityCreate, ProjectCreate
from app.domain.naming import normalize_neo4j_label, normalize_neo4j_relationship_type


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Person", "Person"),
        ("Business Unit", "Business_Unit"),
        ("123 category", "Class_123_category"),
        ("---", "Thing"),
    ],
)
def test_normalize_neo4j_label(value: str, expected: str) -> None:
    assert normalize_neo4j_label(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("reports to", "REPORTS_TO"),
        ("owns/assets", "OWNS_ASSETS"),
        ("42 related", "REL_42_RELATED"),
        ("---", "RELATION"),
    ],
)
def test_normalize_neo4j_relationship_type(value: str, expected: str) -> None:
    assert normalize_neo4j_relationship_type(value) == expected


def test_entity_create_uses_independent_mutable_defaults() -> None:
    first = EntityCreate(class_id="person", name="Alice")
    second = EntityCreate(class_id="person", name="Bob")

    first.aliases.append("A")
    first.properties["age"] = 30

    assert second.aliases == []
    assert second.properties == {}


def test_schema_rejects_empty_project_name() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="")


def test_agent_request_rejects_temperature_outside_supported_range() -> None:
    with pytest.raises(ValidationError):
        AgentTestRequest(ontology_id="ontology", question="Who is Alice?", temperature=2.1)
