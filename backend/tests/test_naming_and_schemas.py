import pytest
from pydantic import ValidationError

from app.api.schemas import AgentTestRequest, ProjectCreate
from app.core.config import Settings
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


def test_agent_request_contains_only_test_input() -> None:
    # Stage 4 §7.2 added ``graph_set_id`` as a required input so agent-test
    # can fetch the agent-test-context read model before the LLM call.
    request = AgentTestRequest(
        ontology_id="ontology",
        graph_set_id="gs-1",
        question="Who is Alice?",
    )

    assert request.model_dump() == {
        "ontology_id": "ontology",
        "graph_set_id": "gs-1",
        "question": "Who is Alice?",
    }
    assert {"model", "base_url", "temperature"}.isdisjoint(AgentTestRequest.model_fields)


def test_agent_request_rejects_model_overrides() -> None:
    with pytest.raises(ValidationError):
        AgentTestRequest(
            ontology_id="ontology",
            graph_set_id="gs-1",
            question="Who is Alice?",
            model="request-level-model",
        )


def test_settings_rejects_temperature_outside_supported_range() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_temperature=2.1, _env_file=None)
