from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.api.schemas import (
    ConnectorQueryRequest,
    ConnectorTemplateCreate,
    ConnectorTemplateUpdate,
    DataResourceUpdate,
    ExternalFieldUpdate,
    IdentifierResolutionRequest,
    SemanticMappingCreate,
)
from app.repositories.models import (
    ConnectorTemplateModel,
    DataResourceModel,
    DataSourceModel,
    ExternalFieldModel,
    OntologyModel,
    SemanticMappingModel,
)
from app.services import catalog


def test_analyze_identifier_resolution_returns_overlap_without_same_as() -> None:
    result = catalog.analyze_identifier_resolution(
        IdentifierResolutionRequest(
            left_values=["s1", "s2", "s2", "s3"],
            right_values=["s2", "s3", "s4"],
        )
    )

    assert result == {
        "left_count": 3,
        "right_count": 3,
        "overlap_count": 2,
        "left_coverage": 2 / 3,
        "right_coverage": 2 / 3,
        "one_to_one": False,
        "unmapped_left": ["s1"],
        "unmapped_right": ["s4"],
    }


def test_connector_query_denies_restricted_field_without_approval() -> None:
    session = Mock()
    template = ConnectorTemplateModel(
        id="template",
        project_id="project",
        data_source_id="source",
        name="student score lookup",
        allowed_field_ids=["field"],
        parameter_schema={},
        result_schema={},
        access_policy="allow",
    )
    source = DataSourceModel(
        id="source",
        project_id="project",
        name="sis",
        source_type="postgres",
        authority_level="authoritative",
        status="available",
        connection_policy={},
    )
    field = ExternalFieldModel(
        id="field",
        project_id="project",
        data_source_id="source",
        data_resource_id="resource",
        name="id_card_number",
        data_type="string",
        sensitivity="restricted",
        access_policy="approval_required",
        audit_required=True,
    )
    session.get.side_effect = lambda model, _id: (
        template
        if model is ConnectorTemplateModel
        else source
        if model is DataSourceModel
        else None
    )
    session.scalars.return_value = [field]

    with patch.object(catalog, "new_id", return_value="audit"):
        result = catalog.run_connector_query(
            session,
            "project",
            "template",
            ConnectorQueryRequest(parameters={"student_number": "S1"}, actor_id="agent"),
        )

    assert result["authorized"] is False
    assert result["denial_reason"] == "Approval required for restricted fields: id_card_number"
    assert result["audit"]["audit_id"] == "audit"
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_connector_query_returns_matching_rows_and_masks_fields() -> None:
    session = Mock()
    template = ConnectorTemplateModel(
        id="template",
        project_id="project",
        data_source_id="source",
        name="student score lookup",
        allowed_field_ids=["score", "id-card"],
        parameter_schema={},
        result_schema={
            "rows": [
                {"student_number": "S1", "midterm_score": 42, "id_card_number": "123456"},
                {"student_number": "S2", "midterm_score": 88, "id_card_number": "654321"},
            ]
        },
        access_policy="allow",
    )
    source = DataSourceModel(
        id="source",
        project_id="project",
        name="sis",
        source_type="postgres",
        authority_level="authoritative",
        status="available",
        connection_policy={},
    )
    fields = [
        ExternalFieldModel(
            id="score",
            project_id="project",
            data_source_id="source",
            data_resource_id="resource",
            name="midterm_score",
            data_type="number",
            sensitivity="internal",
            access_policy="allow",
            audit_required=True,
        ),
        ExternalFieldModel(
            id="id-card",
            project_id="project",
            data_source_id="source",
            data_resource_id="resource",
            name="id_card_number",
            data_type="string",
            sensitivity="confidential",
            access_policy="mask",
            masking_rule="***-masked",
            audit_required=True,
        ),
    ]
    session.get.side_effect = lambda model, _id: (
        template
        if model is ConnectorTemplateModel
        else source
        if model is DataSourceModel
        else None
    )
    session.scalars.return_value = fields

    with patch.object(catalog, "new_id", return_value="audit"):
        result = catalog.run_connector_query(
            session,
            "project",
            "template",
            ConnectorQueryRequest(parameters={"student_number": "S1"}, actor_id="agent"),
        )

    assert result["authorized"] is True
    assert result["rows"] == [
        {"student_number": "S1", "midterm_score": 42, "id_card_number": "***-masked"}
    ]
    assert result["audit"]["audit_id"] == "audit"


def test_create_semantic_mapping_materializes_external_location() -> None:
    session = Mock()
    ontology = OntologyModel(id="ontology", project_id="project", name="campus")
    field = ExternalFieldModel(
        id="field",
        project_id="project",
        data_source_id="source",
        data_resource_id="resource",
        name="midterm_score",
        data_type="number",
        sensitivity="internal",
        access_policy="allow",
    )
    resource = DataResourceModel(
        id="resource",
        project_id="project",
        data_source_id="source",
        name="assessment_results",
        resource_type="table",
    )
    session.get.side_effect = lambda model, _id: (
        ontology
        if model is OntologyModel
        else field
        if model is ExternalFieldModel
        else resource
        if model is DataResourceModel
        else None
    )

    with patch.object(catalog, "new_id", return_value="mapping"):
        mapping = catalog.create_semantic_mapping(
            session,
            "project",
            SemanticMappingCreate(
                ontology_id="ontology",
                target_type="entity",
                target_id="student-li-si",
                field_id="field",
                join_key={"entity_property": "student_number", "external_field": "student_no"},
                owner="registrar",
            ),
        )

    assert mapping.external_resource_name == "assessment_results"
    assert mapping.external_field_name == "midterm_score"
    assert mapping.data_source_id == "source"
    assert mapping.resource_id == "resource"
    session.add.assert_called_once_with(mapping)


def test_update_data_resource_renames_catalog_without_ontology_change() -> None:
    session = Mock()
    resource = DataResourceModel(
        id="resource",
        project_id="project",
        data_source_id="source",
        name="old_assessment_results",
        resource_type="table",
    )
    mapping = SemanticMappingModel(
        id="mapping",
        project_id="project",
        ontology_id="ontology",
        target_type="entity",
        target_id="student-li-si",
        data_source_id="source",
        resource_id="resource",
        field_id="field",
        external_resource_name="old_assessment_results",
        external_field_name="midterm_score",
        join_key={},
        confidence=1.0,
        status="active",
    )
    session.get.return_value = resource
    session.scalars.return_value = [mapping]

    result = catalog.update_data_resource(
        session,
        "project",
        "resource",
        DataResourceUpdate(name="assessment_results_2026"),
    )

    assert result.name == "assessment_results_2026"
    assert mapping.external_resource_name == "assessment_results_2026"
    assert mapping.ontology_id == "ontology"
    session.commit.assert_called_once()


def test_update_external_field_renames_mapping_location() -> None:
    session = Mock()
    field = ExternalFieldModel(
        id="field",
        project_id="project",
        data_source_id="source",
        data_resource_id="resource",
        name="score_old",
        data_type="number",
        sensitivity="internal",
        access_policy="allow",
    )
    mapping = SemanticMappingModel(
        id="mapping",
        project_id="project",
        ontology_id="ontology",
        target_type="entity",
        target_id="student-li-si",
        data_source_id="source",
        resource_id="resource",
        field_id="field",
        external_resource_name="assessment_results",
        external_field_name="score_old",
        join_key={},
        confidence=1.0,
        status="active",
    )
    session.get.return_value = field
    session.scalars.return_value = [mapping]

    result = catalog.update_external_field(
        session,
        "project",
        "field",
        ExternalFieldUpdate(name="midterm_score"),
    )

    assert result.name == "midterm_score"
    assert mapping.external_field_name == "midterm_score"
    session.commit.assert_called_once()


def test_create_connector_template_rejects_fields_from_another_source() -> None:
    session = Mock()
    source = DataSourceModel(
        id="source",
        project_id="project",
        name="sis",
        source_type="postgres",
        authority_level="authoritative",
        status="available",
        connection_policy={},
    )
    wrong_field = SimpleNamespace(id="field", data_source_id="other-source")
    session.get.return_value = source
    session.scalars.return_value = [wrong_field]

    try:
        catalog.create_connector_template(
            session,
            "project",
            ConnectorTemplateCreate(
                data_source_id="source",
                name="lookup",
                allowed_field_ids=["field"],
            ),
        )
    except Exception as exc:
        assert getattr(exc, "status_code") == 400
        assert "same data source" in str(getattr(exc, "detail"))
    else:
        raise AssertionError("Expected connector template validation to fail")


def test_update_connector_template_validates_allowed_field_source() -> None:
    session = Mock()
    template = ConnectorTemplateModel(
        id="template",
        project_id="project",
        data_source_id="source",
        name="lookup",
        allowed_field_ids=[],
        parameter_schema={},
        result_schema={},
        access_policy="allow",
    )
    wrong_field = SimpleNamespace(id="field", data_source_id="other-source")
    session.get.return_value = template
    session.scalars.return_value = [wrong_field]

    try:
        catalog.update_connector_template(
            session,
            "project",
            "template",
            ConnectorTemplateUpdate(allowed_field_ids=["field"]),
        )
    except Exception as exc:
        assert getattr(exc, "status_code") == 400
        assert "same data source" in str(getattr(exc, "detail"))
    else:
        raise AssertionError("Expected connector template validation to fail")
