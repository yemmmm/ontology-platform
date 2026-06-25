"""Catalog, mapping, connector, and identifier analysis MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.schemas import (
    ConnectorQueryRequest,
    ConnectorTemplateCreate,
    ConnectorTemplateRead,
    ConnectorTemplateUpdate,
    DataResourceCreate,
    DataResourceRead,
    DataResourceUpdate,
    DataSourceCreate,
    DataSourceRead,
    DataSourceUpdate,
    ExternalFieldCreate,
    ExternalFieldRead,
    ExternalFieldUpdate,
    IdentifierResolutionRequest,
    SemanticMappingCreate,
    SemanticMappingRead,
    SemanticMappingUpdate,
)
from app.mcp.runtime import _run_tool
from app.services import catalog as catalog_service


def _serialize(model: Any, schema: type[Any]) -> dict[str, Any]:
    return schema.model_validate(model).model_dump(mode="json", exclude_none=True)


def _serialize_list(models: list[Any], schema: type[Any]) -> list[dict[str, Any]]:
    return [_serialize(model, schema) for model in models]


def register_catalog(server: FastMCP) -> None:
    @server.tool()
    def list_data_sources(project_id: str) -> dict[str, Any]:
        """List registered external systems, owners, and authority levels."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize_list(
                catalog_service.list_data_sources(session, project_id), DataSourceRead
            )
        )

    @server.tool()
    def create_data_source(project_id: str, data_source: dict[str, Any]) -> dict[str, Any]:
        """Register an external system that hosts catalog resources and fields."""
        payload = DataSourceCreate.model_validate(data_source)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.create_data_source(session, project_id, payload), DataSourceRead
            )
        )

    @server.tool()
    def update_data_source(
        project_id: str, data_source_id: str, update: dict[str, Any]
    ) -> dict[str, Any]:
        """Update external system metadata, owner, or connection policy."""
        payload = DataSourceUpdate.model_validate(update)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.update_data_source(session, project_id, data_source_id, payload),
                DataSourceRead,
            )
        )

    @server.tool()
    def list_data_resources(project_id: str) -> dict[str, Any]:
        """List catalog resources (tables, endpoints, files) per project."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize_list(
                catalog_service.list_data_resources(session, project_id), DataResourceRead
            )
        )

    @server.tool()
    def create_data_resource(project_id: str, data_resource: dict[str, Any]) -> dict[str, Any]:
        """Register a table, endpoint, or file-like resource under a data source."""
        payload = DataResourceCreate.model_validate(data_resource)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.create_data_resource(session, project_id, payload), DataResourceRead
            )
        )

    @server.tool()
    def update_data_resource(
        project_id: str, resource_id: str, update: dict[str, Any]
    ) -> dict[str, Any]:
        """Update resource metadata; renaming propagates to mapping location names."""
        payload = DataResourceUpdate.model_validate(update)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.update_data_resource(session, project_id, resource_id, payload),
                DataResourceRead,
            )
        )

    @server.tool()
    def list_external_fields(project_id: str) -> dict[str, Any]:
        """List catalog fields, including sensitivity and access policy metadata."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize_list(
                catalog_service.list_external_fields(session, project_id), ExternalFieldRead
            )
        )

    @server.tool()
    def create_external_field(project_id: str, external_field: dict[str, Any]) -> dict[str, Any]:
        """Register field sensitivity, access policy, masking, approval, and audit metadata."""
        payload = ExternalFieldCreate.model_validate(external_field)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.create_external_field(session, project_id, payload), ExternalFieldRead
            )
        )

    @server.tool()
    def update_external_field(
        project_id: str, field_id: str, update: dict[str, Any]
    ) -> dict[str, Any]:
        """Update field sensitivity, access policy, masking, or audit metadata."""
        payload = ExternalFieldUpdate.model_validate(update)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.update_external_field(session, project_id, field_id, payload),
                ExternalFieldRead,
            )
        )

    @server.tool()
    def list_semantic_mappings(
        project_id: str,
        ontology_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        """List ontology-to-external-system mappings for semantic routing."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize_list(
                catalog_service.list_semantic_mappings(
                    session,
                    project_id,
                    ontology_id=ontology_id,
                    target_type=target_type,
                    target_id=target_id,
                ),
                SemanticMappingRead,
            )
        )

    @server.tool()
    def create_semantic_mapping(project_id: str, semantic_mapping: dict[str, Any]) -> dict[str, Any]:
        """Map a class, property, relation type, or entity to a cataloged external field."""
        payload = SemanticMappingCreate.model_validate(semantic_mapping)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.create_semantic_mapping(session, project_id, payload),
                SemanticMappingRead,
            )
        )

    @server.tool()
    def update_semantic_mapping(
        project_id: str, mapping_id: str, update: dict[str, Any]
    ) -> dict[str, Any]:
        """Update mapping target, join key, validity window, confidence, or owner."""
        payload = SemanticMappingUpdate.model_validate(update)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.update_semantic_mapping(session, project_id, mapping_id, payload),
                SemanticMappingRead,
            )
        )

    @server.tool()
    def list_connector_templates(project_id: str) -> dict[str, Any]:
        """List whitelisted connector templates per project."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize_list(
                catalog_service.list_connector_templates(session, project_id),
                ConnectorTemplateRead,
            )
        )

    @server.tool()
    def create_connector_template(
        project_id: str, connector_template: dict[str, Any]
    ) -> dict[str, Any]:
        """Define a whitelisted connector query template and the fields it may return."""
        payload = ConnectorTemplateCreate.model_validate(connector_template)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.create_connector_template(session, project_id, payload),
                ConnectorTemplateRead,
            )
        )

    @server.tool()
    def update_connector_template(
        project_id: str, template_id: str, update: dict[str, Any]
    ) -> dict[str, Any]:
        """Update connector template fields, schemas, or access policy."""
        payload = ConnectorTemplateUpdate.model_validate(update)
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                catalog_service.update_connector_template(session, project_id, template_id, payload),
                ConnectorTemplateRead,
            )
        )

    @server.tool()
    def run_connector_query(
        project_id: str,
        template_id: str,
        parameters: dict[str, Any] | None = None,
        actor_id: str | None = None,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Run a whitelisted connector template after deterministic policy checks."""
        request = ConnectorQueryRequest(
            parameters=parameters or {},
            actor_id=actor_id,
            approved=approved,
        )
        return _run_tool(
            lambda session, _driver, _embedding_client: catalog_service.run_connector_query(
                session, project_id, template_id, request
            )
        )

    @server.tool()
    def analyze_identifier_resolution(
        left_values: list[str],
        right_values: list[str],
    ) -> dict[str, Any]:
        """Return deterministic overlap stats without asserting SAME_AS identity."""
        request = IdentifierResolutionRequest(left_values=left_values, right_values=right_values)
        return _run_tool(
            lambda _session, _driver, _embedding_client: catalog_service.analyze_identifier_resolution(
                request
            )
        )
