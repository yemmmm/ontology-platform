from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.schemas import ClassUpdate, ProjectCreate, PropertyDefRead, RelationTypeUpdate
from app.repositories import graph as graph_repository
from app.repositories.models import ClassModel, PropertyDefModel, RelationTypeModel
from app.services import metadata


def test_create_project_normalizes_label_and_commits() -> None:
    session = MagicMock()

    project = metadata.create_project(session, ProjectCreate(name="Data Platform"))

    assert project.name == "Data Platform"
    assert project.normalized_label == "Data_Platform"
    session.add.assert_called_once_with(project)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(project)


def test_commit_or_409_rolls_back_integrity_error() -> None:
    session = MagicMock()
    session.commit.side_effect = IntegrityError("statement", {}, Exception("duplicate"))

    with pytest.raises(HTTPException) as exc_info:
        metadata.commit_or_409(session, "Duplicate resource")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Duplicate resource"
    session.rollback.assert_called_once_with()


def test_update_class_rejects_self_inheritance_before_commit() -> None:
    session = MagicMock()
    class_ = ClassModel(
        id="person",
        ontology_id="ontology",
        name="Person",
        normalized_label="Person",
        aliases=[],
        parent_class_ids=[],
        external_mappings={},
    )

    with patch.object(metadata, "get_class", return_value=class_):
        with pytest.raises(HTTPException, match="cannot inherit from itself") as exc_info:
            metadata.update_class(
                session,
                "person",
                ClassUpdate(parent_class_ids=["person"]),
            )

    assert exc_info.value.status_code == 400
    session.commit.assert_not_called()


def test_update_relation_type_rejects_self_parent() -> None:
    session = MagicMock()
    relation_type = RelationTypeModel(
        id="reports-to",
        ontology_id="ontology",
        name="reports to",
        normalized_type="REPORTS_TO",
        aliases=[],
        source_class_id="person",
        target_class_id="person",
        external_mappings={},
    )

    with patch.object(metadata, "get_relation_type", return_value=relation_type):
        with pytest.raises(HTTPException, match="cannot inherit from itself"):
            metadata.update_relation_type(
                session,
                "reports-to",
                RelationTypeUpdate(parent_relation_type_id="reports-to"),
            )

    session.commit.assert_not_called()


def test_property_read_defaults_legacy_null_json_fields() -> None:
    now = datetime.now(UTC)
    property_ = PropertyDefModel(
        id="status",
        class_id="person",
        name="status",
        type="string",
        required=False,
        multi_valued=False,
        enum_values=None,
        constraints=None,
        external_mappings=None,
        created_at=now,
        updated_at=now,
    )

    result = PropertyDefRead.model_validate(property_)

    assert result.enum_values == []
    assert result.constraints == {}
    assert result.external_mappings == {}


def test_graph_property_encoding_round_trips() -> None:
    values = {"id": "entity", "properties": {"name": "测试", "rank": 1}}

    encoded = graph_repository._encode_graph_values(values)
    decoded = graph_repository._decode_properties(encoded)

    assert "properties" not in encoded
    assert decoded == values["properties"]
    assert values["properties"] == {"name": "测试", "rank": 1}


@pytest.mark.parametrize("raw", [None, "invalid-json", "[]"])
def test_decode_properties_returns_empty_dict_for_invalid_data(raw: str | None) -> None:
    assert graph_repository._decode_properties({"properties_json": raw}) == {}


def test_entity_from_node_returns_api_shape() -> None:
    result = graph_repository._entity_from_node(
        {
            "id": "entity",
            "project_id": "project",
            "ontology_id": "ontology",
            "class_id": "person",
            "class_label": "Person",
            "name": "Alice",
            "aliases": ["A"],
            "properties_json": '{"age": 30}',
        }
    )

    assert result["ontology_version_id"] is None
    assert result["properties"] == {"age": 30}
    assert result["aliases"] == ["A"]
