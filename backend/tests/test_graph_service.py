from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.repositories.models import ClassModel, PropertyDefModel
from app.services import graph


def make_property(
    name: str,
    type_: str,
    *,
    required: bool = False,
    multi_valued: bool = False,
    enum_values: list[str] | None = None,
) -> PropertyDefModel:
    return PropertyDefModel(
        id=f"property-{name}",
        class_id="class",
        name=name,
        type=type_,
        required=required,
        multi_valued=multi_valued,
        enum_values=enum_values or [],
        constraints={},
        external_mappings={},
    )


def make_class(
    id_: str,
    *,
    parents: list[str] | None = None,
    properties: list[PropertyDefModel] | None = None,
) -> ClassModel:
    class_ = ClassModel(
        id=id_,
        ontology_id="ontology",
        name=id_.title(),
        normalized_label=id_.title(),
        aliases=[],
        parent_class_ids=parents or [],
        external_mappings={},
    )
    class_.properties = properties or []
    return class_


@pytest.mark.parametrize(
    ("type_", "value"),
    [
        ("string", "Alice"),
        ("number", 42),
        ("number", 3.14),
        ("boolean", True),
        ("date", "2026-06-22"),
        ("date", "2026-06-22T10:30:00"),
        ("enum", "active"),
        ("reference", "entity-id"),
        ("json", {"nested": True}),
    ],
)
def test_validate_property_value_accepts_supported_types(type_: str, value: Any) -> None:
    enum_values = ["active", "inactive"] if type_ == "enum" else []
    graph.validate_property_value(make_property("value", type_, enum_values=enum_values), value)


@pytest.mark.parametrize(
    ("property_", "value", "detail"),
    [
        (make_property("name", "string"), 1, "must be a string"),
        (make_property("score", "number"), True, "must be a number"),
        (make_property("enabled", "boolean"), "true", "must be a boolean"),
        (make_property("birthday", "date"), "not-a-date", "must be an ISO date"),
        (
            make_property("status", "enum", enum_values=["active", "inactive"]),
            "unknown",
            "must be one of",
        ),
        (make_property("tags", "string", multi_valued=True), "tag", "must be a list"),
    ],
)
def test_validate_property_value_rejects_invalid_values(
    property_: PropertyDefModel,
    value: Any,
    detail: str,
) -> None:
    with pytest.raises(HTTPException, match=detail) as exc_info:
        graph.validate_property_value(property_, value)

    assert exc_info.value.status_code == 400


def test_validate_entity_properties_includes_inherited_properties() -> None:
    parent = make_class(
        "parent",
        properties=[make_property("name", "string", required=True)],
    )
    child = make_class(
        "child",
        parents=["parent"],
        properties=[make_property("tags", "string", multi_valued=True)],
    )

    graph.validate_entity_properties(
        child,
        {"parent": parent, "child": child},
        {"name": "Alice", "tags": ["admin", "owner"]},
    )


@pytest.mark.parametrize(
    ("properties", "detail"),
    [
        ({}, "Missing required properties: name"),
        ({"name": "Alice", "other": 1}, "Unknown properties"),
    ],
)
def test_validate_entity_properties_reports_schema_violations(
    properties: dict[str, Any],
    detail: str,
) -> None:
    class_ = make_class(
        "person",
        properties=[make_property("name", "string", required=True)],
    )

    with pytest.raises(HTTPException, match=detail):
        graph.validate_entity_properties(class_, {"person": class_}, properties)


def test_collect_effective_properties_rejects_inheritance_cycle() -> None:
    first = make_class("first", parents=["second"])
    second = make_class("second", parents=["first"])

    with pytest.raises(HTTPException, match="inheritance cycle"):
        graph.collect_effective_properties(first, {"first": first, "second": second})


def test_is_descendant_or_same_walks_parent_hierarchy() -> None:
    root = make_class("root")
    child = make_class("child", parents=["root"])
    grandchild = make_class("grandchild", parents=["child"])
    classes = {item.id: item for item in (root, child, grandchild)}

    assert graph.is_descendant_or_same("grandchild", "root", classes)
    assert graph.is_descendant_or_same("child", "child", classes)
    assert not graph.is_descendant_or_same("root", "child", classes)


def test_limits_are_clamped_to_safe_ranges() -> None:
    assert graph.clamp_limit(0) == 1
    assert graph.clamp_limit(500) == 100
    assert graph.clamp_depth(0) == 1
    assert graph.clamp_depth(10) == 3


def test_delete_relation_scopes_delete_to_ontology() -> None:
    session = Mock()
    driver = Mock()
    ontology = SimpleNamespace(id="ontology", project_id="project")

    with (
        patch.object(graph, "get_ontology", return_value=ontology),
        patch.object(graph.graph_repo, "delete_relation_edge", return_value=True) as delete_edge,
    ):
        graph.delete_relation(session, driver, "ontology", "relation")

    delete_edge.assert_called_once_with(driver, "relation", "project", "ontology")


def test_delete_relation_reports_missing_relation() -> None:
    ontology = SimpleNamespace(id="ontology", project_id="project")

    with (
        patch.object(graph, "get_ontology", return_value=ontology),
        patch.object(graph.graph_repo, "delete_relation_edge", return_value=False),
        pytest.raises(HTTPException) as exc_info,
    ):
        graph.delete_relation(Mock(), Mock(), "ontology", "missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Relation not found"
