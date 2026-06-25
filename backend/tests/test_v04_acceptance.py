from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas import (
    ConnectorQueryRequest,
    IdentifierResolutionRequest,
    RelationCreate,
    SemanticMappingCreate,
)
from app.repositories.models import (
    ClassModel,
    ConnectorTemplateModel,
    DataResourceModel,
    DataSourceModel,
    ExternalFieldModel,
    OntologyModel,
    PropertyDefModel,
    RelationTypeModel,
)
from app.services import catalog, governance, graph


def campus_class(id_: str, name: str, properties: list[PropertyDefModel] | None = None) -> ClassModel:
    class_ = ClassModel(
        id=id_,
        ontology_id="campus-ontology",
        name=name,
        normalized_label=name,
        aliases=[],
        parent_class_ids=[],
        external_mappings={},
    )
    class_.properties = properties or []
    return class_


def campus_property(name: str, type_: str, *, required: bool = False) -> PropertyDefModel:
    return PropertyDefModel(
        id=f"property-{name}",
        class_id="class",
        name=name,
        type=type_,
        required=required,
        multi_valued=False,
        enum_values=[],
        constraints={},
        external_mappings={},
    )


def test_v0_4_campus_acceptance_scenario() -> None:
    """Minimal v0.4 campus flow from competency-driven schema to governed query."""

    schema_proposal = SimpleNamespace(
        id="schema-proposal",
        project_id="campus-project",
        ontology_id="campus-ontology",
        proposal_type="schema_change",
        payload={
            "items": [
                {
                    "key": "student",
                    "kind": "class",
                    "data": {"name": "Student", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-grade"],
                },
                {
                    "key": "course",
                    "kind": "class",
                    "data": {"name": "Course", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-grade"],
                },
                {
                    "key": "assessment",
                    "kind": "class",
                    "data": {"name": "Assessment", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-grade"],
                },
                {
                    "key": "assessment-result",
                    "kind": "class",
                    "data": {"name": "AssessmentResult", "source_kind": "domain_fact"},
                    "competency_question_ids": ["cq-grade"],
                },
                {
                    "key": "dormitory",
                    "kind": "class",
                    "data": {"name": "Dormitory", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-access"],
                },
                {
                    "key": "access-policy",
                    "kind": "class",
                    "data": {"name": "AccessPolicy", "source_kind": "domain_fact"},
                    "competency_question_ids": ["cq-access"],
                },
                {
                    "key": "holiday",
                    "kind": "class",
                    "data": {"name": "Holiday", "source_kind": "domain_fact"},
                    "competency_question_ids": ["cq-calendar"],
                },
                {
                    "key": "regular-class",
                    "kind": "class",
                    "data": {"name": "RegularClass", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-calendar"],
                },
                {
                    "key": "course-offering",
                    "kind": "class",
                    "data": {"name": "CourseOffering", "source_kind": "domain_concept"},
                    "competency_question_ids": ["cq-conflict"],
                },
                {
                    "key": "applies-to",
                    "kind": "relation_type",
                    "data": {
                        "name": "APPLIES_TO",
                        "source_class_key": "access-policy",
                        "target_class_key": "dormitory",
                        "source_kind": "domain_concept",
                    },
                    "competency_question_ids": ["cq-access"],
                },
                {
                    "key": "suspends",
                    "kind": "relation_type",
                    "data": {
                        "name": "SUSPENDS",
                        "source_class_key": "holiday",
                        "target_class_key": "regular-class",
                        "source_kind": "domain_concept",
                    },
                    "competency_question_ids": ["cq-calendar"],
                },
                {
                    "key": "conflicts-with",
                    "kind": "relation_type",
                    "data": {
                        "name": "CONFLICTS_WITH",
                        "source_class_key": "course-offering",
                        "target_class_key": "course-offering",
                        "scope_policy": "entity_only",
                        "symmetric": True,
                        "source_kind": "domain_concept",
                    },
                    "competency_question_ids": ["cq-conflict"],
                },
            ]
        },
    )
    schema_session = Mock()
    schema_session.scalar.return_value = 1
    schema_session.scalars.side_effect = [[], [], []]

    errors, ambiguities = governance._validate_items(schema_session, schema_proposal)

    assert errors == []
    assert ambiguities == []
    assert all(
        item["data"].get("source_kind") != "data_source_structure"
        for item in schema_proposal.payload["items"]
    )

    student = campus_class(
        "student",
        "Student",
        [campus_property("student_number", "string", required=True)],
    )
    dormitory = campus_class("dormitory", "Dormitory", [campus_property("name", "string")])
    access_policy = campus_class(
        "access-policy",
        "AccessPolicy",
        [
            campus_property("name", "string"),
            campus_property("cutoff_time", "string"),
            campus_property("valid_from", "date"),
            campus_property("status", "string"),
        ],
    )
    holiday = campus_class(
        "holiday",
        "Holiday",
        [campus_property("name", "string"), campus_property("valid_from", "date")],
    )
    regular_class = campus_class("regular-class", "RegularClass", [campus_property("name", "string")])
    course_offering = campus_class("course-offering", "CourseOffering", [campus_property("name", "string")])
    classes = {
        row.id: row
        for row in [student, dormitory, access_policy, holiday, regular_class, course_offering]
    }

    graph.validate_entity_properties(
        access_policy,
        classes,
        {
            "name": "寝室门禁规定",
            "cutoff_time": "23:00",
            "valid_from": "2026-01-01",
            "status": "active",
        },
    )
    graph.validate_entity_properties(
        holiday,
        classes,
        {"name": "端午节假期", "valid_from": "2026-06-19"},
    )
    with pytest.raises(HTTPException, match="Unknown properties"):
        graph.validate_entity_properties(
            dormitory,
            classes,
            {"name": "学生寝室", "id_card_number": "PII-must-not-enter-graph"},
        )

    ontology = SimpleNamespace(id="campus-ontology", project_id="campus-project", current_version_id=None)
    applies_to = RelationTypeModel(
        id="applies-to",
        ontology_id="campus-ontology",
        name="APPLIES_TO",
        normalized_type="APPLIES_TO",
        source_class_id="access-policy",
        target_class_id="dormitory",
        external_mappings={},
        scope_policy="both",
    )
    conflicts_with = RelationTypeModel(
        id="conflicts-with",
        ontology_id="campus-ontology",
        name="CONFLICTS_WITH",
        normalized_type="CONFLICTS_WITH",
        source_class_id="course-offering",
        target_class_id="course-offering",
        external_mappings={},
        scope_policy="entity_only",
        symmetric=True,
    )

    with (
        patch.object(graph, "get_ontology", return_value=ontology),
        patch.object(graph, "get_relation_type_for_ontology", return_value=applies_to),
        patch.object(graph, "list_classes_for_ontology", return_value=classes),
        patch.object(
            graph.graph_repo,
            "get_entity_node",
            side_effect=[
                {"id": "policy-23", "class_id": "access-policy"},
                {"id": "dormitory-main", "class_id": "dormitory"},
            ],
        ),
        patch.object(graph.graph_repo, "create_relation_edge", side_effect=lambda _driver, _type, values: values) as create_edge,
    ):
        relation = graph.create_relation(
            Mock(),
            Mock(),
            "campus-ontology",
            RelationCreate(
                relation_type_id="applies-to",
                source_entity_id="policy-23",
                target_entity_id="dormitory-main",
                scope="instance",
                valid_from="2026-01-01",
            ),
        )

    assert relation["scope"] == "instance"
    assert relation["valid_from"] == "2026-01-01"
    create_edge.assert_called_once()

    with (
        patch.object(graph, "get_ontology", return_value=ontology),
        patch.object(graph, "get_relation_type_for_ontology", return_value=conflicts_with),
        patch.object(graph, "list_classes_for_ontology", return_value=classes),
        patch.object(
            graph.graph_repo,
            "get_entity_node",
            side_effect=[
                {"id": "math-wed", "class_id": "course-offering"},
                {"id": "physics-wed", "class_id": "course-offering"},
            ],
        ),
        patch.object(graph.graph_repo, "create_relation_edge", side_effect=lambda _driver, _type, values: values),
    ):
        conflict_relation = graph.create_relation(
            Mock(),
            Mock(),
            "campus-ontology",
            RelationCreate(
                relation_type_id="conflicts-with",
                source_entity_id="math-wed",
                target_entity_id="physics-wed",
                scope="instance",
                properties={"reason": "same time slot"},
            ),
        )

    assert conflict_relation["relation_type"] == "CONFLICTS_WITH"
    assert conflict_relation["scope"] == "instance"
    assert conflict_relation["properties"] == {"reason": "same time slot"}

    catalog_session = Mock()
    catalog_ontology = OntologyModel(id="campus-ontology", project_id="campus-project", name="Campus")
    score_field = ExternalFieldModel(
        id="score-field",
        project_id="campus-project",
        data_source_id="sis",
        data_resource_id="assessment-results",
        name="midterm_score",
        data_type="number",
        sensitivity="internal",
        access_policy="allow",
        audit_required=True,
    )
    pii_field = ExternalFieldModel(
        id="pii-field",
        project_id="campus-project",
        data_source_id="sis",
        data_resource_id="student-pii",
        name="id_card_number",
        data_type="string",
        sensitivity="restricted",
        access_policy="approval_required",
        audit_required=True,
    )
    score_resource = DataResourceModel(
        id="assessment-results",
        project_id="campus-project",
        data_source_id="sis",
        name="assessment_results",
        resource_type="table",
    )
    source = DataSourceModel(
        id="sis",
        project_id="campus-project",
        name="教务系统",
        source_type="postgres",
        authority_level="authoritative",
        status="available",
        connection_policy={},
    )
    catalog_session.get.side_effect = lambda model, _id: (
        catalog_ontology
        if model is OntologyModel
        else score_field
        if model is ExternalFieldModel and _id == "score-field"
        else score_resource
        if model is DataResourceModel
        else source
        if model is DataSourceModel
        else None
    )

    with patch.object(catalog, "new_id", return_value="mapping-score"):
        mapping = catalog.create_semantic_mapping(
            catalog_session,
            "campus-project",
            SemanticMappingCreate(
                ontology_id="campus-ontology",
                target_type="entity",
                target_id="li-si",
                field_id="score-field",
                join_key={"entity_property": "student_number", "external_field": "student_no"},
                owner="registrar",
            ),
        )

    assert mapping.external_resource_name == "assessment_results"
    assert mapping.external_field_name == "midterm_score"
    assert mapping.target_id == "li-si"

    template = ConnectorTemplateModel(
        id="student-grade-template",
        project_id="campus-project",
        data_source_id="sis",
        name="student grade lookup",
        allowed_field_ids=["score-field"],
        parameter_schema={},
        result_schema={
            "rows": [
                {"student_number": "S2026001", "course": "高等数学", "midterm_score": 42},
                {"student_number": "S2026002", "course": "大学物理", "midterm_score": 88},
            ]
        },
        access_policy="allow",
    )
    query_session = Mock()
    query_session.get.side_effect = lambda model, _id: (
        template if model is ConnectorTemplateModel else source if model is DataSourceModel else None
    )
    query_session.scalars.return_value = [score_field]
    with patch.object(catalog, "new_id", return_value="audit-grade"):
        grade_result = catalog.run_connector_query(
            query_session,
            "campus-project",
            "student-grade-template",
            ConnectorQueryRequest(
                parameters={"student_number": "S2026001", "course": "高等数学"},
                actor_id="agent",
            ),
        )

    assert grade_result["authorized"] is True
    assert grade_result["rows"] == [
        {"student_number": "S2026001", "course": "高等数学", "midterm_score": 42}
    ]
    assert grade_result["audit"]["audit_id"] == "audit-grade"

    pii_template = ConnectorTemplateModel(
        id="pii-template",
        project_id="campus-project",
        data_source_id="sis",
        name="restricted pii lookup",
        allowed_field_ids=["pii-field"],
        parameter_schema={},
        result_schema={"rows": [{"student_number": "S2026001", "id_card_number": "123456"}]},
        access_policy="allow",
    )
    pii_session = Mock()
    pii_session.get.side_effect = lambda model, _id: (
        pii_template if model is ConnectorTemplateModel else source if model is DataSourceModel else None
    )
    pii_session.scalars.return_value = [pii_field]
    with patch.object(catalog, "new_id", return_value="audit-pii"):
        pii_result = catalog.run_connector_query(
            pii_session,
            "campus-project",
            "pii-template",
            ConnectorQueryRequest(parameters={"student_number": "S2026001"}, actor_id="agent"),
        )

    assert pii_result["authorized"] is False
    assert pii_result["rows"] == []
    assert "Approval required" in str(pii_result["denial_reason"])

    resolution = catalog.analyze_identifier_resolution(
        IdentifierResolutionRequest(
            left_values=["S2026001", "S2026002", "S2026003"],
            right_values=["S2026001", "S2026002", "CARD-9"],
        )
    )

    assert resolution["overlap_count"] == 2
    assert resolution["one_to_one"] is False
    assert resolution["unmapped_left"] == ["S2026003"]
