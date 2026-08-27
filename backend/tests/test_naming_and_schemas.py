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


def test_context_query_resource_types_accept_mapping_and_metric() -> None:
    from app.api.schemas import SemanticContextQueryRequest

    payload = {
        "project_id": "p",
        "scope_mode": "ontologies",
        "ontology_ids": ["o"],
        "query": "工单表映射",
    }
    accepted = SemanticContextQueryRequest(**payload, resource_types=["mapping", "metric"])
    assert set(accepted.resource_types) == {"mapping", "metric"}
    legacy = SemanticContextQueryRequest(**payload, resource_types=["concept", "fact"])
    assert set(legacy.resource_types) == {"concept", "fact"}
    with pytest.raises(ValidationError):
        SemanticContextQueryRequest(**payload, resource_types=["mapping", "unknown_kind"])
