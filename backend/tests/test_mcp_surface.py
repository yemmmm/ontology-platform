import asyncio

from app.mcp.server import mcp
from app.mcp.tools import register_all


ALLOWED_TOOLS = {
    "check_platform_health",
    "search_entities",
    "get_entity",
    "find_related_entities",
    "validate_entity",
    "explain_entity",
    "list_data_sources",
    "create_data_source",
    "update_data_source",
    "list_data_resources",
    "create_data_resource",
    "update_data_resource",
    "list_external_fields",
    "create_external_field",
    "update_external_field",
    "list_semantic_mappings",
    "create_semantic_mapping",
    "update_semantic_mapping",
    "list_connector_templates",
    "create_connector_template",
    "update_connector_template",
    "run_connector_query",
    "analyze_identifier_resolution",
    "submit_proposal",
    "submit_proposal_json",
    "propose_schema_changes",
    "propose_entities",
    "propose_relations",
    "propose_entity_merges",
    "propose_rules",
    "validate_proposal",
    "validate_draft",
    "get_proposal_status",
    "get_build_context",
    "get_project_brief",
    "save_interview_answer",
    "update_project_brief",
    "list_competency_questions",
    "propose_competency_questions",
    "validate_competency_question",
    "list_evidence_artifacts",
    "get_evidence_artifact_status",
    "get_evidence_artifact_chunks",
    "list_source_documents",
    "get_source_document_status",
    "get_source_document_chunks",
    "generate_fact_claims",
    "list_fact_claims",
    "sample_fact_claims",
    "execute_rule_definitions",
    "recall_background_knowledge",
    "get_publication_readiness",
    "semantic_sparql_query",
    "submit_semantic_edit",
    "list_semantic_edit_audits",
    "describe_semantic_graph_set",
    "list_semantic_derived_pointers",
    "check_semantic_staleness",
    "get_semantic_governance_status",
    "run_semantic_validation",
    "run_semantic_reasoning",
    "submit_semantic_rule_definition",
    "run_semantic_rule",
    "inspect_semantic_missing_evidence",
    "get_semantic_read_model",
    "export_semantic_graph_set",
    "inspect_semantic_projection_status",
    "start_semantic_projection_job",
    "inspect_semantic_statement_provenance",
}


FORBIDDEN_TOOLS = {
    "approve_proposal",
    "apply_approved_proposal",
    "review_fact_claim",
    "resolve_conflict",
    "publish_version",
    "deprecate_version",
    "get_review_workspace_link",
}


def _tool_names() -> set[str]:
    tools = asyncio.run(mcp.list_tools())
    return {tool.name for tool in tools}


def test_mcp_surface_matches_registry_exactly() -> None:
    names = _tool_names()
    assert names == ALLOWED_TOOLS
    assert names.isdisjoint(FORBIDDEN_TOOLS)


def test_register_all_is_idempotent() -> None:
    before = _tool_names()
    register_all(mcp)
    after = _tool_names()
    assert before == after == ALLOWED_TOOLS


def test_compatibility_tools_use_scalar_arguments() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    assert tools["submit_proposal_json"].inputSchema["required"] == ["proposal_json"]
    assert tools["submit_proposal_json"].inputSchema["properties"]["proposal_json"]["type"] == "string"
    assert set(tools["get_source_document_chunks"].inputSchema["properties"]) == {
        "document_id",
        "offset",
        "limit",
    }
    assert set(tools["get_evidence_artifact_chunks"].inputSchema["properties"]) == {
        "artifact_id",
        "offset",
        "limit",
    }


def test_catalog_crud_tools_take_project_id_and_body() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    create_tools = [
        "create_data_source",
        "create_data_resource",
        "create_external_field",
        "create_semantic_mapping",
        "create_connector_template",
    ]
    update_tools = [
        "update_data_source",
        "update_data_resource",
        "update_external_field",
        "update_semantic_mapping",
        "update_connector_template",
    ]
    for name in create_tools:
        schema = tools[name].inputSchema
        assert schema["required"] == ["project_id", _body_field_for(name)], name
        assert schema["properties"]["project_id"]["type"] == "string", name
        assert schema["properties"][_body_field_for(name)]["type"] == "object", name
    for name in update_tools:
        schema = tools[name].inputSchema
        assert schema["required"] == ["project_id", _id_field_for(name), "update"], name
        assert schema["properties"]["update"]["type"] == "object", name


def _body_field_for(name: str) -> str:
    return name[len("create_") :]


def _id_field_for(name: str) -> str:
    suffix = name[len("update_") :]
    if suffix == "data_source":
        return "data_source_id"
    if suffix == "data_resource":
        return "resource_id"
    if suffix == "external_field":
        return "field_id"
    if suffix == "semantic_mapping":
        return "mapping_id"
    if suffix == "connector_template":
        return "template_id"
    raise AssertionError(f"unknown update tool: {name}")


def test_check_platform_health_takes_no_arguments() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["check_platform_health"].inputSchema
    assert schema.get("properties", {}) == {}
    assert schema.get("required", []) == []
