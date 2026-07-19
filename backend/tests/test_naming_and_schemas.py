import pytest
from pydantic import ValidationError

from app.api.schemas import ProjectCreate
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


def test_schema_rejects_empty_project_name() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="")
