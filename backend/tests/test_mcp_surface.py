import asyncio

from app.mcp.server import mcp
from app.mcp.tools import register_all


# Stage 3 B2 hard-cut: the only surviving MCP tool families are
# - system (platform health probe)
# - interview (brief, competency-questions CRUD — Stage 1 disposition K)
# - semantic (the new RDF/graph-set stack)
ALLOWED_TOOLS = {
    "check_platform_health",
    "get_build_context",
    "get_project_build_context",
    "create_build_session",
    "get_build_session",
    "resume_build_session",
    "save_build_checkpoint",
    "complete_build_session",
    "cancel_build_session",
    "acquire_ontology_lease",
    "renew_ontology_lease",
    "release_ontology_lease",
    "get_ontology_workspace_context",
    "repair_ontology_workspace",
    "get_project_brief",
    "save_interview_answer",
    "update_project_brief",
    "list_competency_questions",
    "propose_competency_questions",
    "validate_competency_question",
    "create_evidence_reference",
    "list_evidence_references",
    "get_evidence_reference",
    "associate_evidence_reference",
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
    "get_semantic_read_model",
    "export_semantic_graph_set",
    "inspect_semantic_projection_status",
    "start_semantic_projection_job",
    "inspect_semantic_statement_provenance",
    "preflight_semantic_migration",
    "create_semantic_migration_run",
    "run_next_semantic_migration_batch",
    "run_semantic_migration_parity_check",
    "cutover_semantic_migration_run",
    "rollback_semantic_migration_run",
    "compile_and_apply_canonical_command",
}


# Tools that must never come back: legacy governance/publication/catalog/
# graph/documents/facts machinery is gone for good post-B2.
FORBIDDEN_TOOLS = {
    "approve_proposal",
    "apply_approved_proposal",
    "review_fact_claim",
    "resolve_conflict",
    "publish_version",
    "deprecate_version",
    "get_review_workspace_link",
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


def test_check_platform_health_takes_no_arguments() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools["check_platform_health"].inputSchema
    assert schema.get("properties", {}) == {}
    assert schema.get("required", []) == []
